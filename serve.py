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
MAP_MIN, MAP_MAX = 12, 48
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
BULLET_CUT = 1          # 子弹命中其他蛇时截断的格数（不要太大）
BITE_SCORE_PER_CELL = 8 # 咬断对方每格获得的分数
ITEM_TYPES = ('shield', 'speed', 'ghost')
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


# ============================================================ 房间
class Room:
    def __init__(self, rid, name, size=24):
        self.id = rid
        self.name = name
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

    def ev(self, t, **kw):
        self.events.append(dict(t=t, **kw))

    # -------- 主题 / 静态地形 --------
    def _pick_theme(self):
        # 首回合随机主题，之后每局更换，带来地图机制变化
        self.theme = random.choice(THEMES)

    def portal_map(self):
        m = {}
        if len(self.portals) == 2:
            a, b = self.portals
            m[a] = b
            m[b] = a
        return m

    def build_terrain(self):
        """根据主题重置静态地形（岩石 / 墙 / 传送门）。"""
        cfg = THEME_CFG[self.theme]
        self.rocks = []
        self.walls = []
        self.portals = []
        if cfg['portal']:
            for _ in range(300):
                a = (random.randint(0, self.cols - 1), random.randint(0, self.rows - 1))
                b = (random.randint(0, self.cols - 1), random.randint(0, self.rows - 1))
                if a != b and abs(a[0] - b[0]) + abs(a[1] - b[1]) > 6 and not self.occupied(*a) and not self.occupied(*b):
                    self.portals = [a, b]
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
        return {'id': self.id, 'name': self.name, 'cols': self.cols, 'rows': self.rows,
                'theme': self.theme, 'players': sum(1 for p in self.players.values() if p['alive']),
                'watchers': len(self.subs) - len(self.players),
                'round': self.round_no, 'over': self.win_pending is not None}

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

    def place_food(self):
        free = [(x, y) for x in range(self.cols) for y in range(self.rows)
                if not self.occupied(x, y)]
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
        cfg = THEME_CFG[self.theme]
        if self.fruits_eaten % 3 != 0:
            return
        target = int(min(24, self.fruits_eaten // 3) * cfg['rock'])
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
        free = [(x, y) for x in range(self.cols) for y in range(self.rows) if not self.occupied(x, y)]
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

    def maybe_start_round(self):
        if not self.win_pending:
            return
        connected = [pid for pid in self.round_ids if pid in self.players]
        if connected and all(pid in self.ready for pid in connected):
            self.new_round()

    def new_round(self):
        self.win_pending = None
        self.ready.clear()
        self.fruits_eaten = 0
        self.projectiles = []
        self.bonus = None
        self.items = []
        self.round_no += 1
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
        if self.round_ids and not self.win_pending:
            alive = [i for i in self.round_ids if i in self.players and self.players[i]['alive']]
            joined = [i for i in self.round_ids if i in self.players]
            if len(joined) >= 2 and len(alive) == 1:
                w = self.players[alive[0]]
                w['score'] += WIN_SCORE
                self.win_pending = {'winner': alive[0]}
                self.ev('win', id=alive[0], name=w['name'], bonus=WIN_SCORE)
                self._credit_win(w)
        if self.win_pending and not any(i in self.players for i in self.round_ids):
            self.win_pending = None
            self.ready.clear()
        else:
            self.maybe_start_round()

    # -------- 世界推进 --------
    def step(self, dt, now):
        if self.win_pending:
            return
        due = [p for p in self.players.values()
               if p['alive'] and now - p['last_move'] >= self.tick_of(p, now)]
        if not due:
            return
        for p in due:
            p['last_move'] = now

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

        # 4) 普通碰撞：墙 / 岩石 / 墙块 / 自己（护盾与幽灵可免疫部分）
        dead = set()
        blockset = set(self.rocks) | set(self.walls)
        for p in due:
            if is_head_on(p):
                continue
            hx, hy = tent[id(p)]
            ghost = self.effect_active(p, 'ghost', now)
            if not ghost and (hx < 0 or hy < 0 or hx >= self.cols or hy >= self.rows):
                dead.add(id(p))
                p['cause'] = 'wall'
            elif (hx, hy) in blockset and not ghost:
                dead.add(id(p))
                p['cause'] = 'rock'
            elif (hx, hy) in p['cells'][1:]:
                dead.add(id(p))
                p['cause'] = 'self'

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
            keep = max(MIN_LEN, idx)
            if keep >= len(q['cells']):
                continue
            cut = len(q['cells']) - keep
            q['cells'] = q['cells'][:keep]
            ep['grow'] = ep.get('grow', 0) + cut     # 截下部分并入攻击者，随后逐格增长
            ep['score'] += BITE_SCORE_PER_CELL * cut
            if ep.get('user'):
                store.inc(ep['user'], 'kills')
            self.ev('bite', eater=eid, victim=vid, cut=cut, score=BITE_SCORE_PER_CELL * cut)

        # 淘汰结算（仅环境致死：撞墙/岩石/自己）
        for p in due:
            if id(p) in dead:
                p['alive'] = False
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
                p['score'] += self.food['score']
                self.ev('eat', id=p['id'], x=hx, y=hy, score=self.food['score'])
                self.fruits_eaten += 1
                if p.get('user'):
                    store.inc(p['user'], 'food')
                self.maybe_rocks()
                self.place_food()
                if p['tick'] > p.get('base_tick', 150) - 45:
                    p['tick'] -= 3
            if self.bonus and (hx, hy) == (self.bonus['x'], self.bonus['y']):
                ate = True
                p['score'] += self.bonus['score']
                self.ev('star', id=p['id'], x=hx, y=hy, score=self.bonus['score'])
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

    def _protected(self, p, now):
        """被咬免疫：重生保护或护盾道具。"""
        return now < p.get('inv', 0) or self.effect_active(p, 'shield', now)

    def step_wrapper(self, dt, now):
        # 星星与道具过期
        if self.bonus and now - self.bonus['born'] > BONUS_LIFE:
            self.ev('expire', id=self.bonus.get('id'), x=self.bonus['x'], y=self.bonus['y'])
            self.bonus = None
        if not self.bonus and not self.win_pending and random.random() < 0.004:
            free = [(x, y) for x in range(self.cols) for y in range(self.rows) if not self.occupied(x, y)]
            if free:
                x, y = random.choice(free)
                self.bonus = {'id': self.next_bonus_id, 'x': x, 'y': y, 'score': 50, 'born': now}
                self.next_bonus_id += 1
        self.items = [it for it in self.items if now - it['born'] <= ITEM_LIFE]
        if not self.win_pending and len(self.items) < 3 and random.random() < 0.0025:
            self.spawn_item(now)
        self._step_projectiles(dt, now)
        self.step(dt, now)

    def _step_projectiles(self, dt, now=None):
        if now is None:
            now = now_ms()
        rockset = set(self.rocks)
        for pr in self.projectiles[:]:
            pr['x'] += pr['dx'] * PROJ_SPEED * dt
            pr['y'] += pr['dy'] * PROJ_SPEED * dt
            gx, gy = int(pr['x'] + 0.5), int(pr['y'] + 0.5)
            if 0 <= gx < self.cols and 0 <= gy < self.rows and (gx, gy) in rockset:
                rockset.discard((gx, gy))
                self.rocks = [r for r in self.rocks if r != (gx, gy)]
                p = self.players.get(pr['owner'])
                if p:
                    p['score'] += 5
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
                        if shooter:
                            shooter['score'] += 3 * cut
                        self.ev('hit', x=gx, y=gy, by=pr['owner'], victim=victim['id'],
                                cut=cut, score=3 * cut)
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
                      'dx': pr['dx'], 'dy': pr['dy']} for pr in self.projectiles],
            'round': self.round_no, 'cols': self.cols, 'rows': self.rows,
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


def make_player(pid, sess, name, skin):
    return {
        'session': sess, 'id': pid, 'name': name or f'玩家{pid}', 'skin': skin,
        'cells': [], 'dir': (1, 0), 'queue': [], 'score': 0, 'alive': False,
        'tick': 150, 'base_tick': 150, 'last_move': 0, 'last_atk': 0,
        'inv': 0, 'eff': {}, 'grow': 0, 'user': sess.user, 'cause': None, 'by': None,
    }


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

    # -------- 账户 --------
    if t == 'register':
        ok, err = store.register(m.get('user'), m.get('pass'))
        if ok:
            sess.user = str(m.get('user')).strip()
            await send(sess, auth_payload(sess.user))
        else:
            await send(sess, {'t': 'auth', 'ok': False, 'err': err})
        return
    if t == 'login':
        ok, err = store.login(m.get('user'), m.get('pass'))
        if ok:
            sess.user = str(m.get('user')).strip()
            await send(sess, auth_payload(sess.user))
        else:
            await send(sess, {'t': 'auth', 'ok': False, 'err': err})
        return
    if t == 'authtoken':
        name = tokens.get(m.get('token'))
        if name and name in store.users:
            sess.user = name
            await send(sess, auth_payload(name))
        else:
            await send(sess, {'t': 'auth', 'ok': False, 'err': '登录已过期'})
        return
    if t == 'logout':
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
        size = max(MAP_MIN, min(MAP_MAX, int(m.get('size', 24))))
        rid = new_room_id()
        name = str(m.get('name') or f'房间{rid}')[:16]
        rooms[rid] = Room(rid, name, size)
        await broadcast_rooms()
        return

    # -------- 房间进出 --------
    if t == 'watch':
        rid = m.get('room') or 'a'
        room = rooms.get(rid)
        if not room:
            await send(sess, {'t': 'rooms', 'list': room_list()})
            return
        leave_room(sess)
        sess.room = room
        room.subs.add(sess)
        await send(sess, {'t': 'room-ok', 'room': room.id, 'spectate': True, 'user': sess.user})
        return

    if t == 'join':
        rid = m.get('room') or 'a'
        room = rooms.get(rid)
        if not room:
            await send(sess, {'t': 'rooms', 'list': room_list()})
            return
        leave_room(sess)
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
        await send(sess, {'t': 'room-ok', 'room': room.id, 'spectate': False, 'user': sess.user, 'id': pid})
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
        if now - p['last_atk'] < ATK_COOL or not p['cells']:
            return
        p['last_atk'] = now
        hx, hy = p['cells'][0]
        room.projectiles.append({'owner': sess.pid, 'x': hx, 'y': hy,
                                 'dx': p['dir'][0], 'dy': p['dir'][1]})
        room.ev('fire', id=sess.pid, x=hx, y=hy, dx=p['dir'][0], dy=p['dir'][1])
    elif t == 'speed':
        ms = max(80, min(300, int(m.get('ms', 150))))
        p['base_tick'] = ms
        if p['alive']:
            p['tick'] = min(p['tick'], ms)
    elif t == 'skin':
        p['skin'] = int(m.get('i', 0)) % 5
    elif t == 'respawn':
        if not p['alive'] and not room.win_pending:
            room.spawn_player(p)
            room.round_ids.add(sess.pid)
            if p.get('user'):
                store.inc(p['user'], 'games')
            room.ev('join', id=sess.pid, name=p['name'])


def leave_room(sess):
    room = sess.room
    if not room:
        return
    room.subs.discard(sess)
    if sess.pid is not None:
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
    all_sessions.add(sess)
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
        leave_room(sess)
        all_sessions.discard(sess)


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
