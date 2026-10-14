#!/usr/bin/env python3
# 贪吃蛇多人对战服务端：同端口 HTTP + WebSocket（默认 20000，可用环境变量 PORT 覆盖）
import asyncio, json, os, time, mimetypes, random, http, zipfile, io
from pathlib import Path
import websockets

ROOT = Path(__file__).resolve().parent
COLS, ROWS = 24, 24
MAP_MIN, MAP_MAX = 12, 48
FRUITS = [(10, 0xff5f5f), (15, 0xe74c3c), (20, 0xff6b81), (15, 0xa78bfa), (15, 0xffa94d)]
CYCLE = 0.05            # 主循环 50ms
PROJ_SPEED = 22.0       # 弹药格/秒
ATK_COOL = 800          # 攻击冷却 ms
BONUS_LIFE = 8000
EAT_KILL_SCORE = 100
WIN_SCORE = 200

players = {}            # id -> dict
round_ids = set()       # 本局加入过的玩家
ready = set()           # 回合结束后已点"准备"的玩家
food = None
bonus = None
rocks = []              # [(x, y)]
fruits_eaten = 0
projectiles = []        # {owner, x, y, dx, dy}
events = []             # 下个快照附带
next_pid = 1
next_bonus_id = 1
win_pending = None      # {'winner': id 或 None} 表示本回合已结束
round_no = 0
tick_loop_task = None


def now_ms():
    return int(time.monotonic() * 1000)


def ev(t, **kw):
    events.append(dict(t=t, **kw))


def occupied(x, y, skip_pid=None):
    if (x, y) in rocks:
        return True
    if food and (food['x'], food['y']) == (x, y):
        return True
    if bonus and (bonus['x'], bonus['y']) == (x, y):
        return True
    for pid, p in players.items():
        if pid == skip_pid or not p['alive']:
            continue
        if (x, y) in p['cells']:
            return True
    return False


def spawn_player(p, fresh_cells=True):
    base = p.get('base_tick', 150)
    p['tick'] = base
    p['alive'] = True
    p['queue'] = []
    p['last_move'] = now_ms()
    p['last_atk'] = 0
    if not fresh_cells and p.get('cells'):
        return
    # 找空位：头在可走方向上有 ≥4 格空间
    for _ in range(400):
        x = random.randint(0, COLS - 1)
        y = random.randint(0, ROWS - 1)
        dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        random.shuffle(dirs)
        for d in dirs:
            cells = [(x, y), (x - d[0], y - d[1]), (x - 2 * d[0], y - 2 * d[1])]
            if any(cx < 0 or cy < 0 or cx >= COLS or cy >= ROWS for cx, cy in cells):
                continue
            if any(occupied(cx, cy) for cx, cy in cells):
                continue
            # 头前方至少 4 格不撞墙
            fx, fy = x + 4 * d[0], y + 4 * d[1]
            if not (0 <= fx < COLS and 0 <= fy < ROWS):
                continue
            p['cells'] = cells
            p['dir'] = d
            return
    p['cells'] = [(COLS // 2, ROWS // 2), (COLS // 2 - 1, ROWS // 2), (COLS // 2 - 2, ROWS // 2)]
    p['dir'] = (1, 0)


def place_food():
    global food
    free = [(x, y) for x in range(COLS) for y in range(ROWS)
            if not occupied(x, y) and not (bonus and (bonus['x'], bonus['y']) == (x, y))
            and all((x, y) not in p['cells'] for p in players.values())]
    # occupied 已含所有玩家，这里再排除死玩家残留无所谓
    if not free:
        food = None
        return
    x, y = random.choice(free)
    s, c = random.choice(FRUITS)
    food = {'x': x, 'y': y, 'score': s, 'color': c}


def maybe_rocks():
    global rocks
    if fruits_eaten % 3 != 0:
        return
    target = min(24, fruits_eaten // 3)
    heads = [p['cells'][0] for p in players.values() if p['alive'] and p['cells']]
    tries = 40
    while len(rocks) < target and tries > 0:
        tries -= 1
        x = random.randint(0, COLS - 1)
        y = random.randint(0, ROWS - 1)
        if (x, y) in rocks:
            continue
        if any(abs(x - hx) + abs(y - hy) < 4 for hx, hy in heads):
            continue
        if any((x, y) == (fx, fy) for fx, fy in [(f['x'], f['y'])] if f) if food else False:
            continue
        if occupied(x, y):
            continue
        rocks.append((x, y))


def force_right(p):
    p['dir'] = (-p['dir'][1], p['dir'][0])
    p['queue'] = []


def check_win(now):
    global win_pending
    if win_pending or not round_ids:
        return
    alive = [pid for pid in round_ids if pid in players and players[pid]['alive']]
    joined = [pid for pid in round_ids if pid in players]
    if len(joined) < 2:
        return
    if len(alive) == 1:
        w = players[alive[0]]
        w['score'] += WIN_SCORE
        win_pending = {'winner': alive[0]}
        ev('win', id=alive[0], name=w['name'], bonus=WIN_SCORE)
    elif len(alive) == 0:
        win_pending = {'winner': None}
        ev('win', id=None, name=None, bonus=0)


def maybe_start_round():
    # 回合结束后：所有仍在线的本局玩家都点"准备" → 开新局
    if not win_pending:
        return
    connected = [pid for pid in round_ids if pid in players]
    if connected and all(pid in ready for pid in connected):
        new_round()


def new_round():
    global win_pending, rocks, fruits_eaten, food, bonus, projectiles, round_no
    win_pending = None
    ready.clear()
    rocks = []
    fruits_eaten = 0
    projectiles = []
    bonus = None
    round_no += 1
    for pid in list(round_ids):
        p = players.get(pid)
        if p:
            spawn_player(p)
    place_food()
    ev('round', n=round_no)


def step_world(dt, now):
    global food, fruits_eaten, bonus
    if win_pending:
        return

    due = [p for p in players.values() if p['alive'] and now - p['last_move'] >= p['tick']]
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

    tent = {id(p): (p['cells'][0][0] + p['dir'][0], p['cells'][0][1] + p['dir'][1])
            for p in due}

    head_on = set()

    def is_head_on(p):
        return id(p) in head_on

    # 2) 对头相撞（同格 / 换格 / 撞静止蛇头）→ 双方强制右转，本回合不移动
    for i, a in enumerate(due):
        for b in due[i + 1:]:
            ta, tb = tent[id(a)], tent[id(b)]
            if ta == tb or (ta == b['cells'][0] and tb == a['cells'][0]):
                force_right(a)
                force_right(b)
                head_on.add(id(a))
                head_on.add(id(b))
                ev('clash', ids=[a['id'], b['id']])
    for a in due:
        if is_head_on(a):
            continue
        for q in players.values():
            if q is a or not q['alive'] or not q['cells']:
                continue
            if tent[id(a)] == q['cells'][0]:
                force_right(a)
                force_right(q)
                head_on.add(id(a))
                head_on.add(id(q))
                ev('clash', ids=[a['id'], q['id']])
                break

    # 3) 普通碰撞判定：墙 / 岩石 / 自己
    dead = set()
    rockset = set(rocks)
    for p in due:
        if is_head_on(p):
            continue
        hx, hy = tent[id(p)]
        if hx < 0 or hy < 0 or hx >= COLS or hy >= ROWS:
            dead.add(id(p))
            p['cause'] = 'wall'
        elif (hx, hy) in rockset:
            dead.add(id(p))
            p['cause'] = 'rock'
        elif (hx, hy) in p['cells'][1:]:
            dead.add(id(p))
            p['cause'] = 'self'

    # 4) 咬到其他蛇身体 → 对方淘汰，咬人者 +100
    kills = {}   # victim_id -> eater_id
    for p in due:
        if is_head_on(p) or id(p) in dead:
            continue
        for q in players.values():
            if q is p or not q['alive'] or not q['cells']:
                continue
            if tent[id(p)] in q['cells'][1:]:
                if q['id'] in kills:
                    continue
                kills[q['id']] = p['id']
    # 互咬 → 双双淘汰
    both = [v for v, e in kills.items() if e in kills]
    for v in both:
        kills.pop(v)
    for v in list(kills):
        if kills[v] in both:
            kills.pop(v)
    for v in both:
        vp = players[v]
        if id(vp) in due:
            dead.add(id(vp))
            vp['cause'] = 'eaten'
        else:
            vp['alive'] = False
            vp['cause'] = 'eaten'
            ev('die', id=v, cause='eaten', by=None)
    for v, e in kills.items():
        vp, ep = players[v], players[e]
        if id(vp) in due:
            dead.add(id(vp))
            vp['cause'] = 'eaten'
            vp['by'] = e
        else:
            vp['alive'] = False
            ev('die', id=v, cause='eaten', by=e)
        ep['score'] += EAT_KILL_SCORE
        ev('kill', eater=e, victim=v, name=ep['name'], bonus=EAT_KILL_SCORE)

    # 淘汰
    for p in due:
        if id(p) in dead:
            p['alive'] = False
            ev('die', id=p['id'], cause=p.get('cause', 'wall'), by=p.get('by'))

    # 5) 存活者移动 + 进食
    for p in due:
        if is_head_on(p) or id(p) in dead or not p['alive']:
            continue
        hx, hy = tent[id(p)]
        p['cells'].insert(0, (hx, hy))
        ate = False
        if food and (hx, hy) == (food['x'], food['y']):
            ate = True
            p['score'] += food['score']
            ev('eat', id=p['id'], x=hx, y=hy, score=food['score'])
            global fruits_eaten
            fruits_eaten += 1
            maybe_rocks()
            place_food()
            if p['tick'] > p.get('base_tick', 150) - 45:
                p['tick'] -= 3
        if bonus and (hx, hy) == (bonus['x'], bonus['y']):
            ate = True
            p['score'] += bonus['score']
            ev('star', id=p['id'], x=hx, y=hy, score=bonus['score'])
            bonus = None
        if not ate:
            p['cells'].pop()
    check_win(now)


def step_world_wrapper(dt, now):
    global bonus
    # 处理星星过期
    if bonus and now - bonus['born'] > BONUS_LIFE:
        ev('expire', id=bonus.get('id'), x=bonus['x'], y=bonus['y'])
        bonus = None
    if not bonus and not win_pending and random.random() < 0.004:
        free = [(x, y) for x in range(COLS) for y in range(ROWS) if not occupied(x, y)]
        if free:
            x, y = random.choice(free)
            global next_bonus_id
            bonus = {'id': next_bonus_id, 'x': x, 'y': y, 'score': 50, 'born': now}
            next_bonus_id += 1
    # 弹药推进
    _step_projectiles(dt)
    step_world(dt, now)


def _step_projectiles(dt):
    global projectiles, rocks
    rockset = set(rocks)
    for pr in projectiles[:]:
        pr['x'] += pr['dx'] * PROJ_SPEED * dt
        pr['y'] += pr['dy'] * PROJ_SPEED * dt
        gx, gy = int(pr['x'] + 0.5), int(pr['y'] + 0.5)
        if 0 <= gx < COLS and 0 <= gy < ROWS and (gx, gy) in rockset:
            rockset.discard((gx, gy))
            rocks[:] = [r for r in rocks if r != (gx, gy)]
            p = players.get(pr['owner'])
            if p:
                p['score'] += 5
            ev('rock', x=gx, y=gy, by=pr['owner'], score=5)
            projectiles.remove(pr)
            continue
        if gx < -1 or gy < -1 or gx > COLS or gy > ROWS:
            projectiles.remove(pr)


def snapshot():
    plist = []
    for pid, p in players.items():
        plist.append({
            'id': pid, 'name': p['name'], 'skin': p['skin'],
            'cells': [list(c) for c in p['cells']],
            'dir': list(p['dir']), 'score': p['score'],
            'alive': p['alive'], 'tick': p['tick'],
        })
    out = {
        't': 'snap',
        'players': plist,
        'food': food,
        'bonus': bonus,
        'rocks': [list(r) for r in rocks],
        'proj': [{'x': round(pr['x'], 2), 'y': round(pr['y'], 2),
                  'dx': pr['dx'], 'dy': pr['dy']} for pr in projectiles],
        'round': round_no,
        'cols': COLS,
        'rows': ROWS,
        'win': None if not win_pending else win_pending['winner'],
        'over': win_pending is not None,
        'ev': events[:],
    }
    events.clear()
    return out


async def broadcast():
    if not players:
        return
    msg = json.dumps(snapshot(), ensure_ascii=False)
    dead = []
    for pid, p in players.items():
        try:
            await p['ws'].send(msg)
        except Exception:
            dead.append(pid)
    for pid in dead:
        drop_player(pid)


def drop_player(pid):
    global win_pending
    players.pop(pid, None)
    round_ids.discard(pid)
    ready.discard(pid)
    # 人数变化可能触发胜负（仅当本回合尚未结束）
    if round_ids and not win_pending:
        alive = [i for i in round_ids if i in players and players[i]['alive']]
        joined = [i for i in round_ids if i in players]
        if len(joined) >= 2 and len(alive) == 1:
            w = players[alive[0]]
            w['score'] += WIN_SCORE
            win_pending = {'winner': alive[0]}
            ev('win', id=alive[0], name=w['name'], bonus=WIN_SCORE)
    # 回合结束且全员离线 → 解除冻结
    if win_pending and not any(i in players for i in round_ids):
        win_pending = None
        ready.clear()
    else:
        maybe_start_round()


async def game_loop():
    last = time.monotonic()
    while True:
        await asyncio.sleep(CYCLE)
        now = time.monotonic()
        dt = now - last
        last = now
        n = now_ms()
        try:
            step_world_wrapper(dt, n)
            await broadcast()
        except Exception:
            import traceback
            traceback.print_exc()


async def handler(ws):
    global next_pid
    pid = next_pid
    next_pid += 1
    p = {
        'ws': ws, 'name': f'玩家{pid}', 'skin': 0, 'cells': [], 'dir': (1, 0),
        'queue': [], 'score': 0, 'alive': False, 'tick': 150, 'base_tick': 150,
        'last_move': 0, 'last_atk': 0, 'id': pid,
    }
    players[pid] = p
    try:
        await ws.send(json.dumps({'t': 'welcome', 'id': pid}))
        async for raw in ws:
            try:
                m = json.loads(raw)
            except Exception:
                continue
            handle_msg(pid, p, m)
    except websockets.ConnectionClosed:
        pass
    finally:
        drop_player(pid)


def handle_msg(pid, p, m):
    global COLS, ROWS, rocks, bonus
    t = m.get('t')
    if t == 'join':
        if m.get('name'):
            p['name'] = str(m.get('name'))[:12]
        if m.get('skin') is not None:
            p['skin'] = int(m.get('skin', 0)) % 5
        # 第一个入局者决定地图尺寸（仅当本局尚无人时生效）
        if not round_ids and m.get('size'):
            sz = max(MAP_MIN, min(MAP_MAX, int(m.get('size', 24))))
            if sz != COLS:
                COLS = ROWS = sz
                rocks = []
                bonus = None
                projectiles.clear()
                place_food()
        if not p['alive']:
            spawn_player(p, fresh_cells=True)
            round_ids.add(pid)
            ev('join', id=pid, name=p['name'])
            if win_pending:
                ready.add(pid)  # 回合结束后加入的玩家视为已准备
            check_win(now_ms())
    elif t == 'ready':
        ready.add(pid)
        maybe_start_round()
    elif t == 'dir':
        if not p['alive'] or win_pending:
            return
        x, y = int(m.get('x', 0)), int(m.get('y', 0))
        if x not in (-1, 0, 1) or y not in (-1, 0, 1) or (x == 0 and y == 0):
            return
        if len(p['queue']) < 4:
            p['queue'].append((x, y))
    elif t == 'atk':
        n = now_ms()
        if not p['alive'] or win_pending:
            return
        if n - p['last_atk'] < ATK_COOL or not p['cells']:
            return
        p['last_atk'] = n
        hx, hy = p['cells'][0]
        projectiles.append({
            'owner': pid, 'x': hx, 'y': hy,
            'dx': p['dir'][0], 'dy': p['dir'][1],
        })
        ev('fire', id=pid, x=hx, y=hy, dx=p['dir'][0], dy=p['dir'][1])
    elif t == 'speed':
        ms = max(80, min(300, int(m.get('ms', 150))))
        p['base_tick'] = ms
        if p['alive']:
            p['tick'] = min(p['tick'], ms)
    elif t == 'skin':
        p['skin'] = int(m.get('i', 0)) % 5
    elif t == 'respawn':
        if not p['alive'] and not win_pending:
            spawn_player(p)
            round_ids.add(pid)
            ev('join', id=pid, name=p['name'])


# ---------------- 静态文件 ----------------
ALLOWED = {'/': ('index.html', 'text/html; charset=utf-8'),
           '/index.html': ('index.html', 'text/html; charset=utf-8'),
           '/three.min.js': ('three.min.js', 'application/javascript; charset=utf-8')}


async def process_request(path, headers):
    # WebSocket 升级请求放行
    if any(k.lower() == 'upgrade' for k in headers.keys()):
        return None
    key = path.split('?')[0]
    # 打包下载整个程序（方便他人复制走）
    if key in ('/download', '/download.zip'):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            for fn in ('index.html', 'serve.py', 'three.min.js'):
                f = ROOT / fn
                if f.is_file():
                    z.writestr(fn, f.read_bytes())
            z.writestr('README.txt',
                       '贪吃蛇 3D 多人对战\n'
                       '==================\n\n'
                       '运行步骤：\n'
                       '  1. pip install websockets\n'
                       '  2. python3 serve.py\n'
                       '  3. 浏览器打开 http://localhost:20000/\n\n'
                       '文件说明：\n'
                       '  serve.py       服务端（HTTP + WebSocket，同端口 20000）\n'
                       '  index.html     前端页面\n'
                       '  three.min.js   Three.js 渲染库\n')
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
    global tick_loop_task
    place_food()
    async with websockets.serve(handler, '0.0.0.0', PORT,
                                process_request=process_request,
                                ping_interval=20, ping_timeout=20,
                                max_size=2 ** 20):
        tick_loop_task = asyncio.create_task(game_loop())
        await asyncio.Future()  # 永久运行


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
