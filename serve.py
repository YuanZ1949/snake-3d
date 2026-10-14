#!/usr/bin/env python3
# 贪吃蛇多人对战服务端：同端口 HTTP + WebSocket（默认 20000，可用环境变量 PORT 覆盖）
#
# 架构：多房间（Room），每房间独立棋盘与对局状态；连接（Session）可加入房间
# 或旁观。账户与战绩持久化到 data/store.json。协议对旧客户端保持向后兼容：
# 旧客户端不带 room / 账户也能正常游戏（默认进入 "a" 房间、以游客身份游玩）。
import asyncio, json, os, time, random, http, zipfile, io, hashlib, secrets, traceback
from pathlib import Path
import websockets

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / 'data'
STORE_PATH = DATA_DIR / 'store.json'

COLS, ROWS = 24, 24
MAP_MIN, MAP_MAX = 12, 96
FRUITS = [(10, 0xff5f5f), (15, 0xe74c3c), (20, 0xff6b81), (15, 0xa78bfa), (15, 0xffa94d)]
CYCLE = 0.05            # 主循环 50ms
PROJ_SPEED = 22.0       # 弹药格/秒
ATK_COOL = 800          # 攻击冷却 ms
BONUS_LIFE = 8000
WIN_SCORE = 200
SPAWN_INV = 2500        # 重生无敌保护 ms
ITEM_LIFE = 12000       # 道具在地图上的存活时间
EFFECT_MS = 6000        # 道具效果持续时间
MIN_LEN = 2             # 蛇被截断后保留的最少格数
RESPAWN_MS = 3000       # 复活模式：死亡后延迟复活 ms
LIMIT_MAX = 3600        # 战场限时上限（秒）
RESUME_MS = 10000       # 断线宽限：原蛇原地保留等待重连 ms
CHAT_COOL = 1000        # 聊天发送冷却 ms
CHAT_MAX = 80           # 聊天内容长度上限（字符）
BULLET_CUT = 1          # 子弹命中其他蛇时截断的格数（不要太大）
BITE_SCORE_PER_CELL = 8 # 咬断对方每格获得的分数
ITEM_TYPES = ('shield', 'speed', 'ghost', 'magnet', 'double', 'rage', 'deflect')
ULT_MAX = 100          # 大招蓄力上限（攒满才可释放）
ULT_FRUIT = 10         # 吃水果充能
ULT_STAR = 15          # 吃星星充能
ULT_KILL = 30          # 咬蛇淘汰充能
ULT_COOL = 3000        # 大招释放冷却 ms
COMBO_MS = 3000           # 连击窗口：两次吃果间隔超此值则连击重置
COMBO_TIERS = ((15, 2.5), (10, 2.0), (5, 1.5))   # 连击档位：≥15→x2.5, ≥10→x2, ≥5→x1.5
BOTS_MAX = 7              # 单房间 AI 蛇数量上限
DIRS4 = ((1, 0), (0, 1), (-1, 0), (0, -1))       # AI 决策候选方向（不回头）
PASS_MIN = 6               # 房间口令最短位数（C3）
PASS_MAX = 20              # 房间口令最长位数（C3）
ROOM_KEEP_SECS = 86400     # 空房保留期：创建后 24h 内不回收（新#11）
PERSIST_FILE = str(DATA_DIR / 'persist_rooms.json')   # 持久化房间存储
# 弱口令黑名单（C3：前后端同步校验；均为满足 6-20 位字母数字格式的常见弱口令）
WEAK_PASSES = frozenset((
    'abc123', 'abcd1234', 'a123456', '1234567', '12345678', '123123', '654321',
    '000000', '111111', '666666', '888888', '147258', '159357', '1qaz2wsx',
    'qwerty1', 'qwerty123', 'passw0rd', 'password1', 'admin123', 'iloveyou1',
    'monkey12', 'dragon12', 'sunshine1', 'princess1', 'football1', 'baseball1',
    'welcome1', 'letmein1', 'test123', 'login123', 'user1234', 'pass123',
))


def valid_room_pass(p):
    """房间口令校验（C3）：6-20 位字母+数字混合，且不在弱口令黑名单（前后端同步）"""
    if not isinstance(p, str) or not (PASS_MIN <= len(p) <= PASS_MAX):
        return False
    if not p.isalnum() or p.isdigit() or p.isalpha():
        return False                      # 必须字母与数字混合（纯字母/纯数字都不行）
    return p.lower() not in WEAK_PASSES


def chat_throttle(src, now):
    """聊天限速：同一发送源 CHAT_COOL 内只放行一条（src 为 Session 等任意对象）"""
    last = getattr(src, 'chat_at', 0) or 0
    if now - last < CHAT_COOL:
        return False
    src.chat_at = now
    return True


def combo_mult(combo):
    """连击倍率：1-4→x1, 5-9→x1.5, 10-14→x2, 15+→x2.5（封顶）。"""
    for need, m in COMBO_TIERS:
        if combo >= need:
            return m
    return 1.0
THEMES = ('default', 'lava', 'ice', 'space')
# 主题参数：岩石密度倍率 / 是否生成传送门 / 固定墙块数量 / 配色（供前端参考）
THEME_CFG = {
    'default': {'rock': 1.0, 'portal': True,  'walls': 0, 'accent': 0x7ee787},
    'lava':    {'rock': 1.7, 'portal': False, 'walls': 6, 'accent': 0xff6b3d},
    'ice':     {'rock': 0.5, 'portal': False, 'walls': 0, 'accent': 0x61b0ff},
    'space':   {'rock': 0.6, 'portal': True,  'walls': 4, 'accent': 0xb197fc},
}

# 地图尺寸档位 → 房间名（用于默认房间）
DEFAULT_ROOMS = [
    ('a', '新手村', 16),
    ('b', '标准局', 24),
    ('c', '大神场', 32),
]


# ============================================================ 持久化 / 账户
def blank_stats():
    return {'wins': 0, 'kills': 0, 'deaths': 0, 'games': 0, 'best': 0, 'food': 0}


def _hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), salt.encode('utf-8'), 60000).hex()


class Store:
    """账户与战绩的 JSON 持久化。密码要求 6 位数字，加盐 PBKDF2 存储。"""

    def __init__(self, path):
        self.path = path
        self.users = {}
        self.load()

    def load(self):
        try:
            self.users = json.loads(self.path.read_text('utf-8'))
        except Exception:
            self.users = {}

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps(self.users, ensure_ascii=False), 'utf-8')
            tmp.replace(self.path)
        except Exception:
            traceback.print_exc()

    def register(self, name, pw):
        name = (name or '').strip()
        if not (2 <= len(name) <= 12):
            return False, '用户名需 2-12 个字符'
        if not (isinstance(pw, str) and len(pw) == 6 and pw.isdigit()):
            return False, '密码必须是 6 位数字'
        if name in self.users:
            return False, '用户名已存在'
        salt = secrets.token_hex(8)
        self.users[name] = {'salt': salt, 'hash': _hash_pw(pw, salt),
                            'created': int(time.time()), 'stats': blank_stats()}
        self.save()
        return True, None

    def login(self, name, pw):
        u = self.users.get((name or '').strip())
        if not u:
            return False, '用户不存在'
        if not (isinstance(pw, str) and len(pw) == 6 and pw.isdigit()):
            return False, '密码必须是 6 位数字'
        if _hash_pw(pw, u['salt']) != u['hash']:
            return False, '密码错误'
        return True, None

    def stats(self, name):
        u = self.users.get(name)
        return dict(u['stats']) if u else None

    def inc(self, name, key, n=1):
        u = self.users.get(name)
        if not u:
            return
        st = u.setdefault('stats', blank_stats())
        st[key] = st.get(key, 0) + n
        self.save()

    def record_best(self, name, score):
        u = self.users.get(name)
        if not u:
            return
        st = u.setdefault('stats', blank_stats())
        if score > st.get('best', 0):
            st['best'] = score
            self.save()

    def leaderboard(self, limit=20):
        rows = []
        for name, u in self.users.items():
            st = u.get('stats', {})
            rows.append({'name': name, 'best': st.get('best', 0), 'wins': st.get('wins', 0),
                         'kills': st.get('kills', 0), 'games': st.get('games', 0)})
        rows.sort(key=lambda r: (r['best'], r['wins'], r['kills']), reverse=True)
        return rows[:limit]


store = Store(STORE_PATH)

# 登录令牌（内存级，服务重启后需重新登录）
tokens = {}             # token -> username


# ============================================================ 使用情况记录（后台）
# 只落两个文件，页面 / 协议 / 接口一概不体现：
#   data/usage.log   明细，JSONL 一行一个事件（超限轮转成 usage.log.1）
#   data/usage.json  汇总，按天 / 按用户统计
USAGE_LOG = DATA_DIR / 'usage.log'
USAGE_SUM = DATA_DIR / 'usage.json'
USAGE_MAX = 8 * 1024 * 1024          # 明细文件大小上限


def _day_key():
    return time.strftime('%Y-%m-%d')


class Usage:
    """后台记录用户对服务器的使用情况：连接、进房、时长、登录注册、胜负。"""

    def __init__(self, log=USAGE_LOG, summ=USAGE_SUM):
        self.log = Path(log)
        self.summ = Path(summ)
        self.data = {}
        self._last = 0.0
        self.load()

    def load(self):
        try:
            self.data = json.loads(self.summ.read_text('utf-8'))
        except Exception:
            self.data = {}
        if not isinstance(self.data, dict):
            self.data = {}
        self.data.setdefault('totals', {})
        self.data.setdefault('days', {})
        self.data.setdefault('users', {})

    def save(self):
        self._last = time.time()
        try:
            self.summ.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.summ.with_suffix('.tmp')
            tmp.write_text(json.dumps(self.data, ensure_ascii=False), 'utf-8')
            tmp.replace(self.summ)
        except Exception:
            pass

    def _maybe_save(self):
        # 高频事件（如登录尝试）节流落盘，避免每次登录都重写整个汇总文件
        if time.time() - self._last >= 5:
            self.save()

    def line(self, obj):
        """追加一条明细，超出上限后轮转"""
        try:
            self.log.parent.mkdir(parents=True, exist_ok=True)
            if self.log.exists() and self.log.stat().st_size > USAGE_MAX:
                self.log.replace(self.log.parent / 'usage.log.1')
            with self.log.open('a', encoding='utf-8') as f:
                f.write(json.dumps(obj, ensure_ascii=False) + '\n')
        except Exception:
            pass

    def _day(self):
        return self.data['days'].setdefault(_day_key(), {
            'sessions': 0, 'conn_s': 0, 'play_s': 0, 'joins': 0,
            'logins': 0, 'registers': 0, 'wins': 0, 'users': []})

    def _user(self, name):
        return self.data['users'].setdefault(str(name), {
            'sessions': 0, 'conn_s': 0, 'play_s': 0, 'joins': 0,
            'wins': 0, 'best': 0, 'last': 0})

    def _tot(self, k, n=1):
        t = self.data['totals']
        t[k] = int(t.get(k, 0) or 0) + int(n)

    # ---- 事件 ----
    def session(self, info):
        """一次连接结束：写明细并汇总（连接时长 / 玩局时长 / 进房次数 / 得分）"""
        rec = {'e': 'session', 'at': int(time.time())}
        rec.update(info)
        self.line(rec)
        d = self._day()
        d['sessions'] = int(d.get('sessions', 0) or 0) + 1
        self._tot('sessions')
        for k in ('conn_s', 'play_s', 'joins'):
            v = int(info.get(k) or 0)
            d[k] = int(d.get(k, 0) or 0) + v
            self._tot(k, v)
        u = info.get('user')
        if u:
            us = self._user(u)
            us['sessions'] = int(us.get('sessions', 0) or 0) + 1
            for k in ('conn_s', 'play_s', 'joins'):
                us[k] = int(us.get(k, 0) or 0) + int(info.get(k) or 0)
            us['last'] = rec['at']
            us['best'] = max(int(us.get('best') or 0), int(info.get('score') or 0))
            if u not in d['users'] and len(d['users']) < 400:
                d['users'].append(u)
        self.save()
        return rec

    def auth(self, kind, ok, user=None, ip=None):
        """登录 / 注册 / 令牌校验（含失败原因，便于发现异常尝试）"""
        self.line({'e': 'auth', 'kind': kind, 'ok': bool(ok), 'user': user,
                   'ip': ip, 'at': int(time.time())})
        if not ok:
            return
        k = {'login': 'logins', 'register': 'registers'}.get(kind)
        if not k:
            return
        now = int(time.time())
        d = self._day()
        d[k] = int(d.get(k, 0) or 0) + 1
        self._tot(k)
        us = self._user(user)
        us['last'] = now
        if kind == 'register':
            us.setdefault('first', now)
        self._maybe_save()

    def win(self, room, name, user, score):
        self.line({'e': 'win', 'room': room, 'name': name, 'user': user,
                   'score': int(score or 0), 'at': int(time.time())})
        d = self._day()
        d['wins'] = int(d.get('wins', 0) or 0) + 1
        self._tot('wins')
        if user:
            us = self._user(user)
            us['wins'] = int(us.get('wins', 0) or 0) + 1
            us['best'] = max(int(us.get('best') or 0), int(score or 0))
        self.save()   # 一局结束才一次，立即落盘

    def note(self, kind, **kw):
        """零散事件只写明细，不进汇总"""
        rec = {'e': kind, 'at': int(time.time())}
        rec.update(kw)
        self.line(rec)


usage = Usage()


# ============================================================ 房间
class Room:
    def __init__(self, rid, name, size=24, theme_fixed=None, rock_mult=None, portal_on=None,
                 win_mode='last', limit=0, respawn=False, bots=0, passw=None):
        self.id = rid
        self.name = name
        # ---- 地图自定义（组合配置）：None 表示"跟随主题" ----
        self.theme_fixed = theme_fixed if theme_fixed in THEMES else None  # 固定主题（None=每局随机）
        self.rock_mult = rock_mult          # 岩石密度倍率覆盖
        self.portal_on = portal_on          # 传送门开关覆盖
        # ---- 战场自定义：获胜模式（last=死斗留最后一人 / score=积分赛）/ 限时秒（0=不限）/ 无限复活 ----
        self.win_mode = win_mode if win_mode in ('last', 'score') else 'last'
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 0
        self.limit = max(0, min(LIMIT_MAX, limit))
        self.respawn = isinstance(respawn, bool) and respawn
        # 限时兜底：积分赛必须有终点；复活模式不能靠淘汰结算，也必须限时
        if self.limit == 0:
            if self.win_mode == 'score':
                self.limit = 300
            elif self.respawn:
                self.limit = 120
        self.round_started = now_ms()        # 本局开始时间（限时结算的时钟）
        # ---- 单人/练习：AI 蛇数量（0=无 AI；非法值回退 0）----
        try:
            bots = int(bots)
        except (TypeError, ValueError):
            bots = 0
        self.bots = max(0, min(BOTS_MAX, bots))
        self.next_bot_pid = -1               # AI 用负 id，与真人 pid(≥1) 不冲突
        self.owner = None                   # 创建者会话 id，断开后空房间才回收
        # ---- 房间口令（C3）与持久化（新#11）----
        self.passw = passw if (isinstance(passw, str) and passw) else None   # 进房口令（None=无口令）
        self.persist = False                # 「保存」标记：常驻不回收、重启后重建
        self.cols = self.rows = max(MAP_MIN, min(MAP_MAX, int(size)))
        self.players = {}          # pid -> player dict
        self.subs = set()          # 接收快照的 Session（玩家 + 旁观者）
        self.round_ids = set()
        self.ready = set()
        self.food = None
        self.bonus = None
        self.rocks = []            # [(x,y)] 可被子弹击碎
        self.walls = []            # [(x,y)] 不可摧毁
        self.portals = []          # [(x,y),(x,y)] 成对传送门
        self.theme = 'default'
        self.items = []            # {id,type,x,y,born}
        self.fruits_eaten = 0
        self.projectiles = []
        self.events = []
        self.next_bonus_id = 1
        self.next_item_id = 1
        self.next_food_id = 1
        self.win_pending = None
        self.round_no = 0
        self.created = time.time()
        self.last_step = None
        self._pick_theme()
        self.build_terrain()
        self.place_food()
        if self.bots:
            self.add_bots()

    def add_bots(self):
        """创建 AI 蛇（单人练习/多人加 AI）：常驻 round_ids，视为永远 ready"""
        for i in range(self.bots):
            pid = self.next_bot_pid
            self.next_bot_pid -= 1
            p = make_player(pid, None, f'AI-{i + 1}', i % 5, bot=True)
            self.players[pid] = p
            self.round_ids.add(pid)
            self.spawn_player(p)
            self.ev('join', id=pid, name=p['name'], bot=True)

    def ev(self, t, **kw):
        self.events.append(dict(t=t, **kw))

    # -------- 主题 / 静态地形 --------
    def _pick_theme(self):
        # 固定主题的房间每局保持不变；否则每局随机，带来地图机制变化
        self.theme = self.theme_fixed if self.theme_fixed else random.choice(THEMES)

    def eff_rock(self):
        """岩石密度倍率：房间自定义覆盖优先，否则按主题"""
        if self.rock_mult is not None:
            return self.rock_mult
        return THEME_CFG[self.theme]['rock']

    def eff_portal(self):
        """是否生成传送门：房间自定义覆盖优先，否则按主题"""
        if self.portal_on is not None:
            return self.portal_on
        return bool(THEME_CFG[self.theme]['portal'])

    def life_mult(self):
        """资源有效期随地图放大：base × clamp((cols*rows)/(24*24), 1, 4)（#6）"""
        return max(1.0, min(4.0, (self.cols * self.rows) / (24.0 * 24.0)))

    def item_life(self):
        return int(ITEM_LIFE * self.life_mult())

    def bonus_life(self):
        return int(BONUS_LIFE * self.life_mult())

    def portal_map(self):
        m = {}
        for i in range(0, len(self.portals) - 1, 2):
            a, b = self.portals[i], self.portals[i + 1]
            m[a] = b
            m[b] = a
        return m

    def portal_pairs(self):
        """传送门对数：按地图尺寸放大 clamp(size/16 就近取整, 1, 4) 对。
        12/16→1对、24/32→2对、40/48→3对、64+→4对。"""
        return max(1, min(4, int(self.cols / 16.0 + 0.5)))

    def build_terrain(self):
        """根据主题重置静态地形（岩石 / 墙 / 传送门）。"""
        cfg = THEME_CFG[self.theme]
        self.rocks = []
        self.walls = []
        self.portals = []
        if self.eff_portal():
            used = set()
            for _ in range(self.portal_pairs()):
                for _ in range(300):
                    a = (random.randint(0, self.cols - 1), random.randint(0, self.rows - 1))
                    b = (random.randint(0, self.cols - 1), random.randint(0, self.rows - 1))
                    if (a != b and abs(a[0] - b[0]) + abs(a[1] - b[1]) > 6
                            and a not in used and b not in used
                            and not self.occupied(*a) and not self.occupied(*b)):
                        self.portals += [a, b]
                        used.add(a)
                        used.add(b)
                        break
        placed = 0
        while placed < cfg['walls']:
            x, y = random.randint(0, self.cols - 1), random.randint(0, self.rows - 1)
            if self.occupied(x, y) or (x, y) in self.portals:
                continue
            if any(abs(x - hx) + abs(y - hy) < 4 for hx, hy in self._heads()):
                continue
            self.walls.append((x, y))
            placed += 1

    def _heads(self):
        return [p['cells'][0] for p in self.players.values() if p['alive'] and p['cells']]

    # -------- 基础查询 --------
    def occupied(self, x, y, skip_pid=None):
        if (x, y) in self.rocks or (x, y) in self.walls:
            return True
        if (x, y) in self.portals:
            return True
        if self.food and (self.food['x'], self.food['y']) == (x, y):
            return True
        if self.bonus and (self.bonus['x'], self.bonus['y']) == (x, y):
            return True
        if any(it['x'] == x and it['y'] == y for it in self.items):
            return True
        for pid, p in self.players.items():
            if pid == skip_pid or not p['alive']:
                continue
            if (x, y) in p['cells']:
                return True
        return False

    def info(self):
        """房间列表展示用的属性（id / 名称 / 尺寸 / 主题 / 人数 / 地图配置）"""
        return {
            'id': self.id,
            'name': self.name,
            'cols': self.cols,
            'rows': self.rows,
            'theme': self.theme,
            'themeFixed': self.theme_fixed is not None,   # 主题固定（否则每局随机）
            'rock': self.eff_rock(),                      # 实际岩石密度倍率
            'portal': self.eff_portal(),                  # 是否生成传送门
            'players': len(self.players),                 # 房间内人数（含已阵亡）
            'alive': sum(1 for p in self.players.values() if p['alive']),
            'watchers': max(0, len(self.subs) - len(self.players)),
            'round': self.round_no,
            'over': self.win_pending is not None,
            'winMode': self.win_mode,                  # 获胜模式（last=死斗 / score=积分）
            'limit': self.limit,                       # 限时秒（0=不限）
            'respawn': self.respawn,                   # 是否无限复活
            'bots': self.bots,                         # AI 蛇数量（0=无）
            'hasPass': self.passw is not None,         # 是否口令房（口令本身不下发）
            'persist': self.persist,                   # 「保存」常驻标记（新#11）
        }

    # -------- 房间聊天 / 断线恢复 --------
    def chat(self, name, text):
        """房间聊天：截断/去空白，内容随快照 ev 通道下发给房间内所有人"""
        text = str(text or '')[:CHAT_MAX].strip()
        if not text:
            return False
        self.ev('chat', name=str(name)[:12], text=text)
        return True

    def resumable(self, user):
        """找可恢复的挂起原蛇：登录账户精确匹配；匿名仅在恰好一个且无账户时恢复"""
        cands = [q for q in self.players.values() if q.get('off_at')]
        if user:
            for q in cands:
                if q.get('user') == user:
                    return q
            return None
        if len(cands) == 1 and not cands[0].get('user'):
            return cands[0]
        return None

    def resume(self, sess, p):
        """断线恢复：原蛇原分重新绑定会话（不重新出生）"""
        p.pop('off_at', None)
        p['session'] = sess
        self.subs.add(sess)

    # -------- 玩家生命周期 --------
    def _solid(self, x, y, skip_pid=None):
        """静态阻挡或其它蛇身体（食物/道具/奖励不算阻挡，便于计算前方空间）"""
        if x < 0 or y < 0 or x >= self.cols or y >= self.rows:
            return True
        if (x, y) in self.rocks or (x, y) in self.walls or (x, y) in self.portals:
            return True
        for pid, q in self.players.items():
            if pid == skip_pid or not q['alive']:
                continue
            if (x, y) in q['cells']:
                return True
        return False

    def _open_ahead(self, x, y, d, skip_pid=None, cap=24):
        n = 0
        cx, cy = x + d[0], y + d[1]
        while n < cap and not self._solid(cx, cy, skip_pid):
            n += 1
            cx += d[0]
            cy += d[1]
        return n

    def _nearest_opp(self, x, y, skip_pid=None, cap=12):
        best = cap
        for pid, q in self.players.items():
            if pid == skip_pid or not q['alive'] or not q['cells']:
                continue
            for (cx, cy) in q['cells']:
                d = abs(cx - x) + abs(cy - y)
                if d < best:
                    best = d
        return best

    def spawn_player(self, p, fresh_cells=True):
        base = p.get('base_tick', 150)
        p['tick'] = base
        p['alive'] = True
        p['queue'] = []
        p['last_move'] = now_ms()
        p['last_atk'] = 0
        p['inv'] = now_ms() + SPAWN_INV
        p['eff'] = {}
        p['grow'] = 0
        p['combo'] = 0
        p['combo_at'] = 0
        p['ult'] = 0
        p.pop('died_at', None)
        if not fresh_cells and p.get('cells'):
            return
        pid = p.get('id')
        dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        best = None
        best_score = -1e9
        for _ in range(280):
            x = random.randint(0, self.cols - 1)
            y = random.randint(0, self.rows - 1)
            opp = self._nearest_opp(x, y, pid)
            for d in dirs:
                cells = [(x, y), (x - d[0], y - d[1]), (x - 2 * d[0], y - 2 * d[1])]
                if any(self._solid(cx, cy, pid) for cx, cy in cells):
                    continue
                ahead = self._open_ahead(x, y, d, pid)
                if ahead < 4:
                    continue
                # 前方越开阔越好（自然背对最近的外墙），且尽量远离其它蛇
                score = ahead + opp * 3
                if score > best_score:
                    best_score = score
                    best = (cells, d)
        if best:
            p['cells'], p['dir'] = best[0], best[1]
            return
        # 兜底：居中，并朝最开阔的方向
        cx = max(2, min(self.cols - 3, self.cols // 2))
        cy = max(2, min(self.rows - 3, self.rows // 2))
        bd, ba = (1, 0), -1
        for d in dirs:
            a = self._open_ahead(cx, cy, d, pid)
            if a > ba:
                ba, bd = a, d
        p['dir'] = bd
        p['cells'] = [(cx, cy), (cx - bd[0], cy - bd[1]), (cx - 2 * bd[0], cy - 2 * bd[1])]

    def free_cells(self):
        """一次性构建占用集合，避免逐格调用 occupied() 时反复遍历所有蛇。
        大地图（最高 96×96）扫描一次只需 1-2ms，否则会卡住主循环。"""
        occ = set(self.rocks) | set(self.walls) | set(self.portals)
        if self.food:
            occ.add((self.food['x'], self.food['y']))
        if self.bonus:
            occ.add((self.bonus['x'], self.bonus['y']))
        for it in self.items:
            occ.add((it['x'], it['y']))
        for p in self.players.values():
            if p['alive']:
                occ.update(p['cells'])
        return occ

    def free_list(self):
        occ = self.free_cells()
        return [(x, y) for x in range(self.cols) for y in range(self.rows)
                if (x, y) not in occ]

    def place_food(self):
        free = self.free_list()
        if not free:
            self.food = None
            return
        x, y = random.choice(free)
        s, c = random.choice(FRUITS)
        # 唯一 id：即使水果恰好刷在相同坐标/颜色，客户端也能识别为"新水果"并重建，
        # 避免出现"吃了不消失"的观感问题
        self.food = {'id': self.next_food_id, 'x': x, 'y': y, 'score': s, 'color': c}
        self.next_food_id += 1

    def maybe_rocks(self):
        if self.fruits_eaten % 3 != 0:
            return
        target = int(min(24, self.fruits_eaten // 3) * self.eff_rock())
        # 岩石不会被"无限制"增加；每档位重新投放
        tries = 60
        while len(self.rocks) < target and tries > 0:
            tries -= 1
            x = random.randint(0, self.cols - 1)
            y = random.randint(0, self.rows - 1)
            if self.occupied(x, y):
                continue
            if any(abs(x - hx) + abs(y - hy) < 4 for hx, hy in self._heads()):
                continue
            self.rocks.append((x, y))

    # -------- 道具 --------
    def spawn_item(self, now):
        free = self.free_list()
        if not free:
            return
        x, y = random.choice(free)
        self.items.append({'id': self.next_item_id, 'type': random.choice(ITEM_TYPES),
                           'x': x, 'y': y, 'born': now})
        self.next_item_id += 1

    def apply_item(self, p, it, now):
        p['eff'] = p.get('eff', {})
        p['eff'][it['type']] = max(p['eff'].get(it['type'], 0), now) + EFFECT_MS
        self.ev('item', id=p['id'], x=it['x'], y=it['y'], kind=it['type'],
           score=0)

    def score_gain(self, p, n, now):
        """统一记分入口：双倍道具生效时得分翻倍，返回实得分值。"""
        if self.effect_active(p, 'double', now):
            n *= 2
        p['score'] += n
        return n

    def effect_active(self, p, kind, now):
        return p.get('eff', {}).get(kind, 0) > now

    def tick_of(self, p, now):
        base = p['tick']
        if self.effect_active(p, 'speed', now):
            return max(60, int(base * 0.6))
        return base

    # -------- 回合控制 --------
    def force_right(self, p):
        p['dir'] = (-p['dir'][1], p['dir'][0])
        p['queue'] = []

    def check_win(self, now):
        if self.win_pending or not self.round_ids:
            return
        alive = [pid for pid in self.round_ids if pid in self.players and self.players[pid]['alive']]
        joined = [pid for pid in self.round_ids if pid in self.players]
        if len(joined) < 2:
            return
        # 1) 限时到：一律按当前比分最高者胜（并列 → 平局）
        if self.limit and now - self.round_started >= self.limit * 1000:
            top = max(self.players[pid]['score'] for pid in joined)
            leaders = [pid for pid in joined if self.players[pid]['score'] == top]
            if len(leaders) == 1:
                w = self.players[leaders[0]]
                w['score'] += WIN_SCORE
                self.win_pending = {'winner': leaders[0]}
                self.ev('win', id=leaders[0], name=w['name'], bonus=WIN_SCORE, reason='time')
                self._credit_win(w)
            else:
                self.win_pending = {'winner': None}
                self.ev('win', id=None, name=None, bonus=0, reason='time')
            return
        # 2) 复活模式：淘汰不结算，只等限时
        if self.respawn:
            return
        # 3) 积分赛：直到所有人死亡才按比分结算
        if self.win_mode == 'score':
            if len(alive) == 0:
                top = max(self.players[pid]['score'] for pid in joined)
                leaders = [pid for pid in joined if self.players[pid]['score'] == top]
                if len(leaders) == 1:
                    w = self.players[leaders[0]]
                    w['score'] += WIN_SCORE
                    self.win_pending = {'winner': leaders[0]}
                    self.ev('win', id=leaders[0], name=w['name'], bonus=WIN_SCORE, reason='score')
                    self._credit_win(w)
                else:
                    self.win_pending = {'winner': None}
                    self.ev('win', id=None, name=None, bonus=0, reason='score')
            return
        # 4) 死斗（默认）：最后一人获胜，全灭平局
        if len(alive) == 1:
            w = self.players[alive[0]]
            w['score'] += WIN_SCORE
            self.win_pending = {'winner': alive[0]}
            self.ev('win', id=alive[0], name=w['name'], bonus=WIN_SCORE)
            self._credit_win(w)
        elif len(alive) == 0:
            self.win_pending = {'winner': None}
            self.ev('win', id=None, name=None, bonus=0)

    def _credit_win(self, p):
        name = p.get('user')
        if name:
            store.inc(name, 'wins')
            store.record_best(name, p['score'])
        try:
            usage.win(self.id, p.get('name'), name, p.get('score'))
        except Exception:
            pass

    def maybe_start_round(self):
        if not self.win_pending:
            return
        connected = [pid for pid in self.round_ids if pid in self.players]
        # AI 不发 ready 消息、挂起掉线者不在场：都视为 ready，只等在场真人
        if connected and all(pid in self.ready or self.players[pid].get('bot')
                             or self.players[pid].get('off_at') for pid in connected):
            self.new_round()

    def new_round(self):
        self.win_pending = None
        self.ready.clear()
        self.fruits_eaten = 0
        self.projectiles = []
        self.bonus = None
        self.items = []
        self.round_no += 1
        self.round_started = now_ms()        # 限时模式的时钟随新一局重置
        self._pick_theme()
        self.build_terrain()
        for pid in list(self.round_ids):
            p = self.players.get(pid)
            if p:
                self.spawn_player(p)
                if p.get('user'):
                    store.inc(p['user'], 'games')
        self.place_food()
        self.ev('round', n=self.round_no, theme=self.theme)

    def drop_player(self, pid):
        p = self.players.pop(pid, None)
        self.round_ids.discard(pid)
        self.ready.discard(pid)
        if p and p.get('user'):
            store.record_best(p['user'], p['score'])
        # 最后一个真人离开 → 清掉全部 AI（否则 AI 占位导致空房永远不回收）
        if not any(not q.get('bot') for q in self.players.values()):
            for bid in [bid for bid, q in self.players.items() if q.get('bot')]:
                self.players.pop(bid, None)
                self.round_ids.discard(bid)
                self.ready.discard(bid)
        # 退房也走统一结算（含限时/获胜模式判定），不再内联"剩一人即胜"
        self.check_win(now_ms())
        if self.win_pending and not any(i in self.players for i in self.round_ids):
            self.win_pending = None
            self.ready.clear()
        else:
            self.maybe_start_round()

    # -------- 世界推进 --------
    def _bot_think(self, p):
        """AI 蛇转向：目标优先级 星星 > 水果；候选方向要求界内可走且不走回头路。
        打分 (是否绝路, 离目标距离, -前方空间)——无目标时以开阔空间为准。"""
        if not p['cells']:
            return
        hx, hy = p['cells'][0]
        cur = p['dir']
        opp = (-cur[0], -cur[1])
        tgt = None
        if self.bonus:
            tgt = (self.bonus['x'], self.bonus['y'])
        elif self.food:
            tgt = (self.food['x'], self.food['y'])
        opts = []
        for nd in DIRS4:
            if nd == opp:
                continue
            nx, ny = hx + nd[0], hy + nd[1]
            if self._solid(nx, ny, skip_pid=p['id']):
                continue
            openv = self._open_ahead(nx, ny, nd, skip_pid=p['id'])
            dist = (abs(nx - tgt[0]) + abs(ny - tgt[1])) if tgt else 0
            opts.append(((0 if openv > 0 else 1, dist, -openv), nd))
        if not opts:
            return                      # 被围死：保持当前方向
        opts.sort(key=lambda o: o[0])
        nd = opts[0][1]
        if nd != cur:
            p['queue'] = [nd]

    def step(self, dt, now):
        if self.win_pending:
            return
        due = [p for p in self.players.values()
               if p['alive'] and not p.get('off_at')
               and now - p['last_move'] >= self.tick_of(p, now)]
        if not due:
            return
        for p in due:
            p['last_move'] = now

        # 0) AI 决策：队列空时选下一方向（贪心追食物 + 避障避墙）
        for p in due:
            if p.get('bot') and not p['queue']:
                self._bot_think(p)

        # 1) 应用方向队列
        for p in due:
            if p['queue']:
                nd = p['queue'].pop(0)
                if not (nd[0] == -p['dir'][0] and nd[1] == -p['dir'][1]):
                    p['dir'] = nd

        # 2) 计算目标格（含幽灵穿墙环绕 + 传送门）
        pmap = self.portal_map()
        tent = {}
        for p in due:
            hx = p['cells'][0][0] + p['dir'][0]
            hy = p['cells'][0][1] + p['dir'][1]
            if self.effect_active(p, 'ghost', now):
                hx %= self.cols
                hy %= self.rows
            if (hx, hy) in pmap:
                hx, hy = pmap[(hx, hy)]
                # 出口朝向取出口处最开阔方向（不贴最近的墙，#2）
                best, bo = p['dir'], -1
                for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    o = self._open_ahead(hx, hy, d, p['id'])
                    if o > bo:
                        bo, best = o, d
                p['dir'] = best
            tent[id(p)] = (hx, hy)

        head_on = set()

        def is_head_on(p):
            return id(p) in head_on

        # 3) 对头相撞 → 双方强制右转
        for i, a in enumerate(due):
            for b in due[i + 1:]:
                ta, tb = tent[id(a)], tent[id(b)]
                if ta == tb or (ta == b['cells'][0] and tb == a['cells'][0]):
                    self.force_right(a)
                    self.force_right(b)
                    head_on.add(id(a))
                    head_on.add(id(b))
                    self.ev('clash', ids=[a['id'], b['id']])
        for a in due:
            if is_head_on(a):
                continue
            for q in self.players.values():
                if q is a or not q['alive'] or not q['cells']:
                    continue
                if tent[id(a)] == q['cells'][0]:
                    self.force_right(a)
                    self.force_right(q)
                    head_on.add(id(a))
                    head_on.add(id(q))
                    self.ev('clash', ids=[a['id'], q['id']])
                    break

        # 4) 普通碰撞：墙 / 岩石 / 墙块 / 自己
        #    护盾(shield) = 任何地形碰撞都折返不死；偏转道具(deflect) = 仅边界墙折返；
        #    偏转方向取垂直方向中空间最大的一格（仍无路可走则照死）
        dead = set()
        blockset = set(self.rocks) | set(self.walls)
        for p in due:
            if is_head_on(p):
                continue
            hx, hy = tent[id(p)]
            ghost = self.effect_active(p, 'ghost', now)
            wall = not ghost and (hx < 0 or hy < 0 or hx >= self.cols or hy >= self.rows)
            rock = not ghost and (hx, hy) in blockset
            own = (hx, hy) in p['cells'][1:]
            if not (wall or rock or own):
                continue
            shielded = self.effect_active(p, 'shield', now)
            guard = shielded or (self.effect_active(p, 'deflect', now) and wall)
            if guard:
                nd = self._deflect_dir(p, blockset)
                if nd is not None:
                    p['dir'] = nd
                    p['queue'] = []
                    tent[id(p)] = (p['cells'][0][0] + nd[0], p['cells'][0][1] + nd[1])
                    continue
            dead.add(id(p))
            p['cause'] = 'wall' if wall else ('rock' if rock else 'self')

        # 5) 咬到其他蛇身体 → 截断对方（对方至少保留 MIN_LEN 格，被截下的部分并入攻击者长度）
        bites = {}   # victim_id -> (eater_id, index)
        for p in due:
            if is_head_on(p) or id(p) in dead or not p['alive']:
                continue
            cell = tent[id(p)]
            for q in self.players.values():
                if q is p or not q['alive'] or not q['cells']:
                    continue
                if cell in q['cells'][1:]:
                    if self._protected(q, now):
                        continue
                    idx = q['cells'].index(cell)
                    if q['id'] not in bites or idx < bites[q['id']][1]:
                        bites[q['id']] = (p['id'], idx)
        for vid, (eid, idx) in bites.items():
            q = self.players.get(vid)
            ep = self.players.get(eid)
            if not q or not ep or not q['alive'] or not ep['alive']:
                continue
            if len(q['cells']) <= MIN_LEN:
                # 咬蛇淘汰：已是最低长度的蛇再被咬 → 整条淘汰，残躯归攻击者
                cut = len(q['cells'])
                q['alive'] = False
                q['cause'] = 'bite'
                q['by'] = eid
                q['died_at'] = now
                ep['grow'] = ep.get('grow', 0) + cut
                ep['ult'] = min(ULT_MAX, ep.get('ult', 0) + ULT_KILL)
                gained = self.score_gain(ep, BITE_SCORE_PER_CELL * cut, now)
                if ep.get('user'):
                    store.inc(ep['user'], 'kills')
                if q.get('user'):
                    store.inc(q['user'], 'deaths')
                self.ev('bite', eater=eid, victim=vid, cut=cut, score=gained, kill=True)
                self.ev('die', id=vid, cause='bite', by=eid)
                continue
            keep = max(MIN_LEN, idx)
            if keep >= len(q['cells']):
                continue
            cut = len(q['cells']) - keep
            q['cells'] = q['cells'][:keep]
            ep['grow'] = ep.get('grow', 0) + cut     # 截下部分并入攻击者，随后逐格增长
            gained = self.score_gain(ep, BITE_SCORE_PER_CELL * cut, now)
            if ep.get('user'):
                store.inc(ep['user'], 'kills')
            self.ev('bite', eater=eid, victim=vid, cut=cut, score=gained)

        # 淘汰结算（仅环境致死：撞墙/岩石/自己）
        for p in due:
            if id(p) in dead:
                p['alive'] = False
                p['died_at'] = now
                self.ev('die', id=p['id'], cause=p.get('cause', 'wall'), by=p.get('by'))
                if p.get('user'):
                    store.inc(p['user'], 'deaths')

        # 6) 存活者移动 + 进食 + 拾取道具
        eaten_items = set()
        for p in due:
            if is_head_on(p) or id(p) in dead or not p['alive']:
                continue
            hx, hy = tent[id(p)]
            p['cells'].insert(0, (hx, hy))
            ate = False
            if self.food and (hx, hy) == (self.food['x'], self.food['y']):
                ate = True
                # 连击：3 秒窗口内连续吃果计数递增，超时重置；倍率按档位
                if now - p.get('combo_at', 0) <= COMBO_MS:
                    p['combo'] = p.get('combo', 0) + 1
                else:
                    p['combo'] = 1
                p['combo_at'] = now
                mult = combo_mult(p['combo'])
                base = self.food['score']
                gained = self.score_gain(p, int(base * mult), now)
                self.ev('eat', id=p['id'], x=hx, y=hy, score=gained,
                        combo=p['combo'], mult=mult)
                self.fruits_eaten += 1
                p['ult'] = min(ULT_MAX, p.get('ult', 0) + ULT_FRUIT)
                if p.get('user'):
                    store.inc(p['user'], 'food')
                self.maybe_rocks()
                self.place_food()
                if p['tick'] > p.get('base_tick', 150) - 45:
                    p['tick'] -= 3
            if self.bonus and (hx, hy) == (self.bonus['x'], self.bonus['y']):
                ate = True
                gained = self.score_gain(p, self.bonus['score'], now)
                p['ult'] = min(ULT_MAX, p.get('ult', 0) + ULT_STAR)
                self.ev('star', id=p['id'], x=hx, y=hy, score=gained)
                self.bonus = None
            for it in self.items:
                if it['id'] in eaten_items:
                    continue
                if (hx, hy) == (it['x'], it['y']):
                    eaten_items.add(it['id'])
                    self.apply_item(p, it, now)
            if ate:
                pass                              # 吃到东西本 tick 不缩尾（增长 1）
            elif p.get('grow', 0) > 0:
                p['grow'] -= 1                    # 被咬截断并入的长度逐步生长
            else:
                p['cells'].pop()
        if eaten_items:
            self.items = [it for it in self.items if it['id'] not in eaten_items]
        self.check_win(now)

    def _deflect_dir(self, p, blockset):
        """折返方向：取蛇头垂直两方向中可走（界内、无岩石墙块、无传送门、
        不压自己身体）且前方空间最大的那格；都走不了返回 None（照死）。"""
        hx, hy = p['cells'][0]
        dx, dy = p['dir']
        best, best_open = None, -1
        for nd in ((-dy, dx), (dy, -dx)):
            nx, ny = hx + nd[0], hy + nd[1]
            if not (0 <= nx < self.cols and 0 <= ny < self.rows):
                continue
            if (nx, ny) in blockset or (nx, ny) in self.portals:
                continue
            if (nx, ny) in p['cells'][1:]:
                continue
            o = self._open_ahead(hx, hy, nd, p.get('id'))
            if o > best_open:
                best_open, best = o, nd
        return best

    def try_ult(self, p, now):
        """大招：蓄力满 100 后释放 8 方向环形弹幕（对角线方向做归一化）。"""
        if self.win_pending or not p['alive'] or not p['cells']:
            return False
        if p.get('ult', 0) < ULT_MAX:
            return False
        if now - p.get('last_ult', 0) < ULT_COOL:
            return False
        p['last_ult'] = now
        p['ult'] = 0
        hx, hy = p['cells'][0]
        k = 0.7071
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            f = k if dx and dy else 1.0
            self.projectiles.append({'owner': p['id'], 'x': hx, 'y': hy,
                                     'dx': dx * f, 'dy': dy * f, 'spd': 1.5})
        self.ev('ult', id=p['id'], x=hx, y=hy)
        return True

    def _protected(self, p, now):
        """被咬免疫：重生保护或护盾道具。"""
        return now < p.get('inv', 0) or self.effect_active(p, 'shield', now)

    def _magnet_move(self, x, y, hx, hy, occ):
        """磁铁单步：朝蛇头挪 1 格；蛇头格停下（由蛇头来吃）；被挡则绕行。"""
        dx, dy = hx - x, hy - y
        first = None
        if dx:
            first = (x + (1 if dx > 0 else -1), y)
        elif dy:
            first = (x, y + (1 if dy > 0 else -1))
        if first == (hx, hy):
            return x, y                        # 停在蛇头旁，不落进蛇头格
        cands = []
        if first:
            cands.append(first)
        if dx and dy:
            cands.append((x, y + (1 if dy > 0 else -1)))
        # 直路被挡 → 垂直绕行
        cands += [(x, y - 1), (x, y + 1), (x - 1, y), (x + 1, y)]
        for cx, cy in cands:
            if (cx, cy) == (hx, hy):
                continue
            if 0 <= cx < self.cols and 0 <= cy < self.rows and (cx, cy) not in occ:
                return cx, cy
        return x, y

    def _magnet_pull(self, now):
        """磁铁道具：持有者把食物/星星朝自己头拉 1 格（绕开障碍）。"""
        holders = [p for p in self.players.values()
                   if p['alive'] and p['cells'] and self.effect_active(p, 'magnet', now)]
        if not holders:
            return
        occ = self.free_cells()
        for p in holders:
            hx, hy = p['cells'][0]
            for obj in (self.food, self.bonus):
                if not obj:
                    continue
                occ.discard((obj['x'], obj['y']))
                obj['x'], obj['y'] = self._magnet_move(obj['x'], obj['y'], hx, hy, occ)
                occ.add((obj['x'], obj['y']))

    def atk_cd(self, p, now):
        """攻击冷却：狂暴期间减半。"""
        return ATK_COOL // 2 if self.effect_active(p, 'rage', now) else ATK_COOL

    def step_wrapper(self, dt, now):
        # 断线宽限超时：挂起的原蛇到点移出（drop 内含"最后真人离开清 AI"）
        for pid in list(self.players):
            p = self.players.get(pid)
            if p and p.get('off_at') and now - p['off_at'] >= RESUME_MS:
                self.drop_player(pid)
        # 复活模式：死亡延迟到点后原地重建（限时内不结算淘汰）
        if self.respawn and not self.win_pending:
            for p in list(self.players.values()):
                if not p['alive'] and p.get('died_at') and now - p['died_at'] >= RESPAWN_MS:
                    self.spawn_player(p)
                    p.pop('died_at', None)
                    self.ev('respawn', id=p['id'], name=p['name'])
        self._magnet_pull(now)
        # 星星与道具过期（有效期随地图放大，#6）
        if self.bonus and now - self.bonus['born'] > self.bonus_life():
            self.ev('expire', id=self.bonus.get('id'), x=self.bonus['x'], y=self.bonus['y'])
            self.bonus = None
        if not self.bonus and not self.win_pending and random.random() < 0.004:
            free = self.free_list()
            if free:
                x, y = random.choice(free)
                self.bonus = {'id': self.next_bonus_id, 'x': x, 'y': y, 'score': 50, 'born': now}
                self.next_bonus_id += 1
        self.items = [it for it in self.items if now - it['born'] <= self.item_life()]
        if not self.win_pending and len(self.items) < 3 and random.random() < 0.0025:
            self.spawn_item(now)
        self._step_projectiles(dt, now)
        self.step(dt, now)

    def _step_projectiles(self, dt, now=None):
        if now is None:
            now = now_ms()
        rockset = set(self.rocks)
        for pr in self.projectiles[:]:
            pr['x'] += pr['dx'] * PROJ_SPEED * pr.get('spd', 1.0) * dt
            pr['y'] += pr['dy'] * PROJ_SPEED * pr.get('spd', 1.0) * dt
            gx, gy = int(pr['x'] + 0.5), int(pr['y'] + 0.5)
            if 0 <= gx < self.cols and 0 <= gy < self.rows and (gx, gy) in rockset:
                rockset.discard((gx, gy))
                self.rocks = [r for r in self.rocks if r != (gx, gy)]
                p = self.players.get(pr['owner'])
                if p:
                    self.score_gain(p, 5, now)
                self.ev('rock', x=gx, y=gy, by=pr['owner'], score=5)
                self.projectiles.remove(pr)
                continue
            # 命中其它蛇身体 → 小幅截短（不致死，最低 MIN_LEN 格；无敌/护盾免疫）
            if 0 <= gx < self.cols and 0 <= gy < self.rows:
                victim = None
                for q in self.players.values():
                    if q['id'] == pr['owner'] or not q['alive'] or not q['cells']:
                        continue
                    if (gx, gy) in q['cells'] and not self._protected(q, now):
                        victim = q
                        break
                if victim is not None:
                    cut = min(BULLET_CUT, max(0, len(victim['cells']) - MIN_LEN))
                    if cut > 0:
                        victim['cells'] = victim['cells'][:len(victim['cells']) - cut]
                        shooter = self.players.get(pr['owner'])
                        gained = self.score_gain(shooter, 3 * cut, now) if shooter else 0
                        self.ev('hit', x=gx, y=gy, by=pr['owner'], victim=victim['id'],
                                cut=cut, score=gained)
                    else:
                        self.ev('hit', x=gx, y=gy, by=pr['owner'], victim=victim['id'],
                                cut=0, score=0)
                    self.projectiles.remove(pr)
                    continue
            if gx < -1 or gy < -1 or gx > self.cols or gy > self.rows:
                self.projectiles.remove(pr)

    # -------- 快照 / 广播 --------
    def snapshot(self, now):
        plist = []
        for pid, p in self.players.items():
            plist.append({
                'id': pid, 'name': p['name'], 'skin': p['skin'],
                'cells': [list(c) for c in p['cells']],
                'dir': list(p['dir']), 'score': p['score'],
                'alive': p['alive'], 'tick': p['tick'],
                'inv': max(0, p.get('inv', 0) - now),
                'eff': {k: max(0, v - now) for k, v in p.get('eff', {}).items() if v > now},
                'acct': p.get('user'),
                'combo': p.get('combo', 0),
                'ult': p.get('ult', 0),
                'bot': bool(p.get('bot')),
                'off': bool(p.get('off_at')),
            })
        out = {
            't': 'snap', 'room': self.id, 'theme': self.theme,
            'players': plist,
            'food': self.food,
            'bonus': self.bonus,
            'rocks': [list(r) for r in self.rocks],
            'walls': [list(r) for r in self.walls],
            'portals': [list(r) for r in self.portals],
            'items': [{'id': it['id'], 'type': it['type'], 'x': it['x'], 'y': it['y']} for it in self.items],
            'proj': [{'x': round(pr['x'], 2), 'y': round(pr['y'], 2),
                      'dx': pr['dx'], 'dy': pr['dy'], 'spd': pr.get('spd', 1.0)}
                     for pr in self.projectiles],
            'round': self.round_no, 'cols': self.cols, 'rows': self.rows,
            'winMode': self.win_mode, 'limit': self.limit, 'respawn': self.respawn,
            'remain': max(0, self.limit - int((now - self.round_started) // 1000)) if self.limit else 0,
            'win': None if not self.win_pending else self.win_pending['winner'],
            'over': self.win_pending is not None,
            'ev': self.events[:],
        }
        self.events.clear()
        return out

    async def broadcast(self):
        now = now_ms()
        snap = self.snapshot(now)      # 总是生成快照并清空事件，避免无人订阅时事件堆积
        if not self.subs:
            return
        msg = json.dumps(snap, ensure_ascii=False)
        dead = []
        for sess in self.subs:
            try:
                await sess.ws.send(msg)
            except Exception:
                dead.append(sess)
        for sess in dead:
            sess.room = None


# ============================================================ 房间注册表
rooms = {}


def room_list():
    lst = [r.info() for r in rooms.values()]
    lst.sort(key=lambda r: (r['id']))
    return lst


def new_room_id():
    i = 1
    while f"r{i}" in rooms:
        i += 1
    return f"r{i}"


def init_rooms():
    for rid, name, size in DEFAULT_ROOMS:
        rooms[rid] = Room(rid, name, size)


# ---- 持久化房间（新#11）：「保存」过的房间重启后重建，常驻不回收 ----
def persist_rooms_dump():
    out = []
    for rid, r in rooms.items():
        if not r.persist:
            continue
        out.append({'id': rid, 'name': r.name, 'size': r.cols,
                    'theme': r.theme_fixed, 'rock': r.rock_mult, 'portal': r.portal_on,
                    'winMode': r.win_mode, 'limit': r.limit, 'respawn': r.respawn,
                    'bots': r.bots, 'pass': r.passw})
    return out


def save_persist_rooms(path=PERSIST_FILE):
    """把全部 persist 房间写盘（标记变化时调用）；失败静默（不阻塞游戏）"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(persist_rooms_dump(), f, ensure_ascii=False)
        return True
    except OSError:
        return False


def load_persist_rooms(path=PERSIST_FILE):
    """启动时重建已「保存」的房间（新#11）；文件缺失/损坏返回 0"""
    try:
        with open(path, encoding='utf-8') as f:
            lst = json.load(f)
    except (OSError, ValueError):
        return 0
    n = 0
    for d in (lst if isinstance(lst, list) else []):
        if not isinstance(d, dict):
            continue
        rid = d.get('id')
        if not rid or not isinstance(rid, str) or rid in rooms:
            continue
        try:
            size = int(d.get('size') or 24)
        except (TypeError, ValueError):
            size = 24
        rock = d.get('rock')
        if isinstance(rock, bool) or not isinstance(rock, (int, float)):
            rock = None
        else:
            rock = max(0.0, min(4.0, float(rock)))
        portal = d.get('portal')
        r = Room(rid, str(d.get('name') or rid)[:16], size,
                 theme_fixed=d.get('theme'), rock_mult=rock,
                 portal_on=portal if isinstance(portal, bool) else None,
                 win_mode=d.get('winMode'), limit=d.get('limit') or 0,
                 respawn=d.get('respawn') is True, bots=d.get('bots') or 0,
                 passw=d.get('pass'))
        r.persist = True
        r.created = time.time()            # 持久化房间不回收，创建时间无意义
        rooms[rid] = r
        n += 1
    return n


DEFAULT_ROOM_IDS = {rid for rid, _n, _s in DEFAULT_ROOMS}


def gc_empty_rooms():
    """回收自定义房间：默认房间常驻；persist 常驻；创建 24h 内保留（新#11）；
    之后没人、没人观战、且创建者已断线才删"""
    live = {s.sid for s in all_sessions}
    now = time.time()
    for rid in list(rooms):
        if rid in DEFAULT_ROOM_IDS:
            continue
        r = rooms[rid]
        if r.persist:
            continue                       # 「保存」过的房间永不回收
        if now - r.created < ROOM_KEEP_SECS:
            continue                       # 新建 24h 内先留着（用户需求 #11）
        if r.players or r.subs:
            continue
        if r.owner is not None and r.owner in live:
            continue   # 创建者还挂在开始页，房间给他留着
        del rooms[rid]


# ============================================================ 连接
next_pid = 1
next_sid = 1


class Session:
    def __init__(self, ws):
        global next_sid
        self.ws = ws
        self.sid = next_sid
        next_sid += 1
        self.user = None          # 已登录用户名
        self.room = None          # 当前房间
        self.pid = None           # 房间内玩家 id
        self.want_play = False
        self.chat_at = 0             # 聊天限速时间戳
        # ---- 使用情况统计（仅后台记录，不上页面） ----
        self.t0 = time.time()     # 连接时刻
        self.msgs = 0             # 收到的消息条数
        self.joins = 0            # 进房次数
        self.play_ms = 0          # 作为玩家的累计毫秒
        self.play_from = None     # 本次进房起始时刻
        self.last_room = None     # 最后所在房间
        self.last_name = None     # 最后使用的昵称
        self.last_score = 0       # 本连接内最高得分
        self.ip = None
        self.ua = None


def now_ms():
    return int(time.monotonic() * 1000)


async def game_loop():
    while True:
        await asyncio.sleep(CYCLE)
        now = time.monotonic()
        n = now_ms()
        for room in list(rooms.values()):
            prev = room.last_step or now
            dt = now - prev
            room.last_step = now
            try:
                room.step_wrapper(dt, n)
                await room.broadcast()
            except Exception:
                traceback.print_exc()


def make_player(pid, sess, name, skin, bot=False):
    return {
        'session': sess, 'id': pid, 'name': name or f'玩家{pid}', 'skin': skin,
        'bot': bot, 'user': (sess.user if sess else None),
        'cells': [], 'dir': (1, 0), 'queue': [], 'score': 0, 'alive': False,
        'tick': 150, 'base_tick': 150, 'last_move': 0, 'last_atk': 0,
        'inv': 0, 'eff': {}, 'grow': 0, 'cause': None, 'by': None,
        'combo': 0, 'combo_at': 0,
        'ult': 0, 'last_ult': 0,
    }


def apply_speed(p, ms):
    """切换速度档位并立即生效：调慢当场变慢、调快当场变快。
    同时把 tick 保持在 [base-45, base] 区间，保留吃水果累积的加速。"""
    ms = max(80, min(300, int(ms)))
    p['base_tick'] = ms
    if p['alive']:
        p['tick'] = max(60, max(ms - 45, min(p['tick'], ms)))
    return ms


async def send(sess, obj):
    try:
        await sess.ws.send(json.dumps(obj, ensure_ascii=False))
    except Exception:
        pass


def auth_payload(name):
    return {'t': 'auth', 'ok': True, 'user': name, 'token': tokens_inv(name),
            'stats': store.stats(name)}


def tokens_inv(name):
    for tok, u in tokens.items():
        if u == name:
            return tok
    tok = secrets.token_hex(16)
    tokens[tok] = name
    return tok


async def handle_msg(sess, m):
    global next_pid
    t = m.get('t')
    sess.msgs += 1

    # -------- 账户 --------
    uname = str(m.get('user') or '').strip()
    if t == 'register':
        ok, err = store.register(m.get('user'), m.get('pass'))
        if ok:
            sess.user = uname
            await send(sess, auth_payload(sess.user))
        else:
            await send(sess, {'t': 'auth', 'ok': False, 'err': err})
        usage.auth('register', ok, uname, sess.ip)
        return
    if t == 'login':
        ok, err = store.login(m.get('user'), m.get('pass'))
        if ok:
            sess.user = uname
            await send(sess, auth_payload(sess.user))
        else:
            await send(sess, {'t': 'auth', 'ok': False, 'err': err})
        usage.auth('login', ok, uname, sess.ip)
        return
    if t == 'authtoken':
        name = tokens.get(m.get('token'))
        if name and name in store.users:
            sess.user = name
            await send(sess, auth_payload(name))
        else:
            name = None
            await send(sess, {'t': 'auth', 'ok': False, 'err': '登录已过期'})
        usage.auth('authtoken', name is not None, name, sess.ip)
        return
    if t == 'logout':
        usage.note('logout', user=sess.user, sid=sess.sid, ip=sess.ip)
        if sess.user:
            for tok, u in list(tokens.items()):
                if u == sess.user:
                    tokens.pop(tok, None)
        sess.user = None
        await send(sess, {'t': 'auth', 'ok': False, 'err': '已退出'})
        return
    if t == 'leaderboard':
        await send(sess, {'t': 'leaderboard', 'list': store.leaderboard()})
        return
    if t == 'rooms':
        await send(sess, {'t': 'rooms', 'list': room_list()})
        return
    if t == 'create':
        try:
            size = int(m.get('size', 24))
        except (TypeError, ValueError):
            size = 24
        size = max(MAP_MIN, min(MAP_MAX, size))
        rid = new_room_id()
        name = str(m.get('name') or f'房间{rid}')[:16]
        # ---- 地图组合配置：主题 / 岩石密度 / 传送门（非法值回退为"跟随主题"） ----
        theme = m.get('theme')
        if theme not in THEMES:
            theme = None
        rock = m.get('rock')
        if isinstance(rock, bool) or not isinstance(rock, (int, float)):
            rock = None
        else:
            rock = max(0.0, min(4.0, float(rock)))
        portal = m.get('portal')
        if not isinstance(portal, bool):
            portal = None
        # ---- 战场配置：获胜模式 / 限时秒 / 无限复活（非法值回退默认） ----
        win_mode = m.get('winMode')
        if win_mode not in ('last', 'score'):
            win_mode = 'last'
        try:
            limit = int(m.get('limit', 0))
        except (TypeError, ValueError):
            limit = 0
        limit = max(0, min(LIMIT_MAX, limit))
        respawn = m.get('respawn') is True
        # ---- 单人/练习：AI 蛇数量（非法值回退 0） ----
        try:
            bots = int(m.get('bots', 0))
        except (TypeError, ValueError):
            bots = 0
        bots = max(0, min(BOTS_MAX, bots))
        # ---- 房间口令（C3）：可选；给了就必须合法（非法直接拒绝，不静默回退） ----
        passw = m.get('pass')
        if passw in (None, ''):
            passw = None
        elif not valid_room_pass(str(passw)):
            await send(sess, {'t': 'error', 'err': '口令需 6-20 位字母+数字混合，且不能是弱口令'})
            return
        rooms[rid] = Room(rid, name, size, theme_fixed=theme, rock_mult=rock, portal_on=portal,
                          win_mode=win_mode, limit=limit, respawn=respawn, bots=bots, passw=passw)
        rooms[rid].owner = sess.sid   # 创建者在时房间不回收
        await broadcast_rooms()
        await send(sess, {'t': 'created', 'room': rid, 'name': name})
        return

    # -------- 房间进出 --------
    if t == 'watch':
        rid = m.get('room') or 'a'
        room = rooms.get(rid)
        if not room:
            await send(sess, {'t': 'rooms', 'list': room_list()})
            return
        if room.passw and str(m.get('pass') or '') != room.passw:
            await send(sess, {'t': 'error', 'err': '房间口令错误'})
            return
        leave_room(sess)
        sess.room = room
        room.subs.add(sess)
        gc_empty_rooms()   # 换房后旧房间若已空则回收
        await send(sess, {'t': 'room-ok', 'room': room.id, 'spectate': True, 'user': sess.user})
        return

    if t == 'join':
        rid = m.get('room') or 'a'
        room = rooms.get(rid)
        if not room:
            await send(sess, {'t': 'rooms', 'list': room_list()})
            return
        # 口令房：先校验再动状态（客户端重连也带记忆的口令，含断线恢复路径）
        if room.passw and str(m.get('pass') or '') != room.passw:
            await send(sess, {'t': 'error', 'err': '房间口令错误'})
            return
        leave_room(sess)
        # ---- 断线恢复：宽限期内找回原蛇（原分数/身体/位置） ----
        prev = room.resumable(sess.user)
        if prev is not None:
            room.resume(sess, prev)
            sess.room = room
            sess.want_play = True
            sess.pid = prev['id']
            sess.joins += 1
            sess.play_from = time.time()
            sess.last_room = room.id
            sess.last_name = prev['name']
            usage.note('resume', sid=sess.sid, room=room.id, name=prev['name'],
                       user=sess.user, ip=sess.ip)
            await send(sess, {'t': 'room-ok', 'room': room.id, 'spectate': False,
                              'user': sess.user, 'id': prev['id'], 'resumed': True})
            await broadcast_rooms()
            return
        sess.room = room
        sess.want_play = True
        if m.get('name'):
            pname = str(m.get('name'))[:12]
        elif sess.user:
            pname = sess.user
        else:
            pname = None
        skin = int(m.get('skin', 0) or 0) % 5
        # 第一个入局者决定房间尺寸（空房间时生效）
        if not room.round_ids and m.get('size'):
            sz = max(MAP_MIN, min(MAP_MAX, int(m.get('size', 24))))
            if sz != room.cols:
                room.cols = room.rows = sz
                room.players = {}
                room.build_terrain()
                room.place_food()
        pid = next_pid
        next_pid += 1
        p = make_player(pid, sess, pname, skin)
        sess.pid = pid
        room.players[pid] = p
        room.subs.add(sess)
        room.spawn_player(p, fresh_cells=True)
        room.round_ids.add(pid)
        room.ev('join', id=pid, name=p['name'])
        if room.win_pending:
            room.ready.add(pid)
        if p.get('user'):
            store.inc(p['user'], 'games')
        room.check_win(now_ms())
        # ---- 使用情况（仅后台记录） ----
        sess.joins += 1
        sess.play_from = time.time()
        sess.last_room = room.id
        sess.last_name = p['name']
        usage.note('join', sid=sess.sid, room=room.id, name=p['name'],
                   user=sess.user, ip=sess.ip)
        gc_empty_rooms()   # 换房后旧房间若已空则回收（目标房间已有人，不会被回收）
        await send(sess, {'t': 'room-ok', 'room': room.id, 'spectate': False, 'user': sess.user, 'id': pid})
        await broadcast_rooms()   # 房间人数变化，刷新所有人看到的房间列表
        return

    # -------- 房间保存（新#11）：创建者标记 persist → 常驻不回收、重启后重建 --------
    if t == 'persist':
        room = rooms.get(m.get('room') or '')
        if not room:
            return
        if room.owner != sess.sid:
            await send(sess, {'t': 'error', 'err': '仅创建者可保存房间'})
            return
        if not room.persist:
            room.persist = True
            save_persist_rooms()
        await broadcast_rooms()
        return

    if t == 'leave':
        # 返回主页：把自己移出房间（旧客户端不发此消息，行为不变）
        left = sess.room.id if sess.room else None
        sess.want_play = False
        leave_room(sess)
        gc_empty_rooms()
        await broadcast_rooms()
        await send(sess, {'t': 'left', 'room': left})
        return

    # -------- 房间聊天（观战者/玩家都可发） --------
    if t == 'chat':
        room = sess.room
        if room is None:
            return
        now = now_ms()
        if not chat_throttle(sess, now):
            return
        if sess.pid is not None and sess.pid in room.players:
            who = room.players[sess.pid]['name']
        else:
            who = sess.user or '观众'
        room.chat(who, m.get('text'))
        return

    # 其余消息需要已在房间中
    room = sess.room
    if room is None or sess.pid is None or sess.pid not in room.players:
        return
    p = room.players[sess.pid]
    now = now_ms()

    if t == 'ready':
        room.ready.add(sess.pid)
        room.maybe_start_round()
    elif t == 'dir':
        if not p['alive'] or room.win_pending:
            return
        x, y = int(m.get('x', 0)), int(m.get('y', 0))
        if x not in (-1, 0, 1) or y not in (-1, 0, 1) or (x == 0 and y == 0):
            return
        if len(p['queue']) < 4:
            p['queue'].append((x, y))
    elif t == 'atk':
        if not p['alive'] or room.win_pending:
            return
        if now - p['last_atk'] < room.atk_cd(p, now) or not p['cells']:
            return
        p['last_atk'] = now
        hx, hy = p['cells'][0]
        room.projectiles.append({'owner': sess.pid, 'x': hx, 'y': hy,
                                 'dx': p['dir'][0], 'dy': p['dir'][1],
                                 'spd': 1.5 if room.effect_active(p, 'rage', now) else 1.0})
        room.ev('fire', id=sess.pid, x=hx, y=hy, dx=p['dir'][0], dy=p['dir'][1])
    elif t == 'ult':
        room.try_ult(p, now)
    elif t == 'speed':
        apply_speed(p, m.get('ms', 150))
    elif t == 'skin':
        p['skin'] = int(m.get('i', 0)) % 5
    elif t == 'respawn':
        if not p['alive'] and not room.win_pending:
            room.spawn_player(p)
            room.round_ids.add(sess.pid)
            if p.get('user'):
                store.inc(p['user'], 'games')
            room.ev('join', id=sess.pid, name=p['name'])


def leave_room(sess, hard=True):
    """hard=True：明确退出（leave/换房/测试），直接移出玩家；
    hard=False：断线 —— 房里还有其他真人时原蛇挂起 off_at 等重连恢复，
    单人房（或没别的真人可等）则照旧立即移出，保住空房及时回收。"""
    room = sess.room
    if not room:
        return
    # ---- 使用情况：累计本局时长，并留下最后一局的房间/昵称/得分 ----
    if sess.play_from:
        sess.play_ms += int((time.time() - sess.play_from) * 1000)
        sess.play_from = None
    if sess.pid is not None:
        p = room.players.get(sess.pid)
        if p:
            sess.last_room = room.id
            sess.last_name = p.get('name') or sess.last_name
            sess.last_score = max(sess.last_score, int(p.get('score') or 0))
    room.subs.discard(sess)
    if sess.pid is not None:
        p = room.players.get(sess.pid)
        others = [q for q in room.players.values()
                  if q is not p and not q.get('bot') and not q.get('off_at')]
        if not hard and p and others:
            # 断线且房里还有其他真人 → 挂起原蛇等 RESUME_MS 内重连恢复
            p['off_at'] = now_ms()
            p['session'] = None
        else:
            room.drop_player(sess.pid)
    sess.pid = None
    sess.room = None


async def broadcast_rooms(sess=None):
    lst = room_list()
    targets = [sess] if sess else list(all_sessions)
    for s in targets:
        await send(s, {'t': 'rooms', 'list': lst})


all_sessions = set()


async def handler(ws):
    sess = Session(ws)
    try:
        addr = getattr(ws, 'remote_address', None)
        if addr:
            sess.ip = addr[0]
        hdr = getattr(ws, 'request_headers', None)
        if hdr:
            sess.ua = str(hdr.get('User-Agent') or '')[:160]
    except Exception:
        pass
    all_sessions.add(sess)
    usage.note('conn', sid=sess.sid, ip=sess.ip, ua=sess.ua)
    try:
        await send(sess, {'t': 'welcome', 'id': sess.sid, 'rooms': room_list()})
        async for raw in ws:
            try:
                m = json.loads(raw)
            except Exception:
                continue
            try:
                await handle_msg(sess, m)
            except Exception:
                traceback.print_exc()
    except websockets.ConnectionClosed:
        pass
    finally:
        all_sessions.discard(sess)   # 先下线，自己的自定义房间才能被回收
        leave_room(sess, hard=False)  # 断线挂起原蛇，RESUME_MS 内重连可恢复
        try:                        # 记录这次连接的使用情况（仅后台落盘）
            usage.session({'sid': sess.sid, 'ip': sess.ip, 'ua': sess.ua,
                           'user': sess.user, 'name': sess.last_name,
                           'room': sess.last_room, 'score': sess.last_score,
                           'conn_s': max(0, int(time.time() - sess.t0)),
                           'play_s': int(sess.play_ms / 1000),
                           'msgs': sess.msgs, 'joins': sess.joins})
        except Exception:
            pass
        try:
            gc_empty_rooms()
            await broadcast_rooms()   # 有人退出，刷新其它客户端看到的房间列表
        except Exception:
            pass


# ============================================================ 静态文件
ALLOWED = {'/': ('index.html', 'text/html; charset=utf-8'),
           '/index.html': ('index.html', 'text/html; charset=utf-8'),
           '/three.min.js': ('three.min.js', 'application/javascript; charset=utf-8')}


async def process_request(path, headers):
    if any(k.lower() == 'upgrade' for k in headers.keys()):
        return None
    key = path.split('?')[0]
    if key == '/api/leaderboard':
        body = json.dumps({'list': store.leaderboard()}, ensure_ascii=False).encode()
        return http.HTTPStatus.OK, [('Content-Type', 'application/json; charset=utf-8'),
                                    ('Content-Length', str(len(body)))], body
    if key in ('/download', '/download.zip'):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            for fn in ('index.html', 'serve.py', 'three.min.js'):
                f = ROOT / fn
                if f.is_file():
                    z.writestr(fn, f.read_bytes())
            z.writestr('README.txt',
                       '贪吃蛇 3D 多人对战\n==================\n\n运行步骤：\n'
                       '  1. pip install websockets\n  2. python3 serve.py\n'
                       '  3. 浏览器打开 http://localhost:20000/\n\n'
                       '支持：多房间 / 道具（护盾·加速·穿墙）/ 账户与排行榜 / 多种地图主题\n')
        body = buf.getvalue()
        return http.HTTPStatus.OK, [
            ('Content-Type', 'application/zip'),
            ('Content-Length', str(len(body))),
            ('Content-Disposition', 'attachment; filename="snake-3d.zip"'),
            ('Cache-Control', 'no-store, must-revalidate'),
        ], body
    entry = ALLOWED.get(key)
    if not entry:
        return http.HTTPStatus.NOT_FOUND, [], b'not found'
    fn, ctype = entry
    f = ROOT / fn
    if not f.is_file():
        return http.HTTPStatus.NOT_FOUND, [], b'not found'
    body = f.read_bytes()
    return http.HTTPStatus.OK, [
        ('Content-Type', ctype),
        ('Content-Length', str(len(body))),
        ('Cache-Control', 'no-store, must-revalidate'),
    ], body


PORT = int(os.environ.get('PORT', '20000'))


async def main():
    init_rooms()
    load_persist_rooms()   # 重建「保存」过的房间（新#11）
    usage.note('start', port=PORT, pid=os.getpid() if hasattr(os, 'getpid') else None)
    async with websockets.serve(handler, '0.0.0.0', PORT,
                                process_request=process_request,
                                ping_interval=20, ping_timeout=20,
                                max_size=2 ** 20):
        await game_loop()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
