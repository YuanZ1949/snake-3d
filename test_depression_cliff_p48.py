# -*- coding: utf-8 -*-
"""批48：「看不见的悬崖」回归——撞崖/坠亡高度差按物理高度（贴层 0）比较。

生产取证（2026-10-28 usage.log 全量）：cliff 死 183 起中 144 起(79%) 是 h0<0
的「离开凹地」死亡（草-2→平0 / 水-1→台1 被算成爬升≥2 判崖）。客户端把水/草
渲染为地板贴层（视觉海拔 0），故这类死亡视觉完全无崖 =「看不见的悬崖」。

修复语义：物理海拔 = max(h, 0)（只有正高度是真抬升；-9 深渊仍为入口即致命）。
  C1 草(-2)→平(0)：存活（修前 cliff 死）
  C2 水(-1)→h1：存活（修前 cliff 死）
  C3 草(-2)→深渊(-9)：死 cause='fall'（修前 7<FALL_DEATH 存活——反向漏判）
  C4 平(0)→h2：cliff 死不变（真撞崖）
  C5 h9→草(-2)：fall 死不变（物理落差 9≥8）
  C6 h7→水(-1)：存活 + 断尾净掉6节（修前 raw 落差 8 判坠亡死）
"""
import asyncio, json, sys, time

import websockets

import serve


async def recv_until(ws, pred, timeout=6.0):
    loop = asyncio.get_event_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        m = json.loads(await asyncio.wait_for(ws.recv(), timeout=max(0.1, end - loop.time())))
        if pred(m):
            return m
    raise AssertionError('timeout waiting for message')


async def read_snaps(ws, room, n=1, timeout=4.0):
    evs, last = [], None
    for _ in range(n):
        last = await recv_until(ws, lambda m: m.get('t') == 'snap' and m.get('room') == room, timeout)
        evs += last.get('ev') or []
    return last, evs


async def tick(room, n=1, gap=0.16):
    for _ in range(n):
        await serve.game_cycle(time.monotonic(), serve.now_ms())
        await asyncio.sleep(gap)


async def main():
    serve.BONUS_SPAWN_P = 0.0
    serve.Room.spawn_item = lambda self, now: None

    server = await websockets.serve(serve.handler, '127.0.0.1', 0)
    port = server.sockets[0].getsockname()[1]
    ws = await websockets.connect('ws://127.0.0.1:%d' % port, max_size=None)
    await recv_until(ws, lambda m: m.get('t') == 'welcome')

    await ws.send(json.dumps({'t': 'create', 'name': '凹地悬崖测试', 'size': 16}))
    created = await recv_until(ws, lambda m: m.get('t') == 'created')
    rid = created['room']
    await ws.send(json.dumps({'t': 'join', 'room': rid, 'name': 'DepA'}))
    ok = await recv_until(ws, lambda m: m.get('t') == 'room-ok')
    pid = ok['id']
    room = serve.rooms[rid]
    p = room.players[pid]
    print('room=%s pid=%s' % (rid, pid))

    room.rocks = []
    room.walls = []
    room.portals = []
    room.items = []
    room.foods = []
    room.bonus = None
    room.eterrain = {}

    def reset(hmap, cells, d=(1, 0)):
        room.hmap = dict(hmap)
        p['cells'] = list(cells)
        p['dir'] = d
        p['queue'] = []
        p['last_move'] = 0
        p['inv'] = 0
        p['eff'] = {}
        p['grow'] = 0
        p['tick'] = 150
        p['base_tick'] = 150
        p['off_at'] = None
        p['alive'] = True

    # ---- C1) 草(-2)→平(0)：贴层→平地，视觉无落差 → 存活 ----
    reset({(5, 5): -2}, [(5, 5), (5, 6), (4, 6)])
    await tick(room)
    snap, evs = await read_snaps(ws, rid)
    me = [q for q in snap['players'] if q['id'] == pid][0]
    assert me['alive'] is True, 'C1 草→平地 不应死: evs=%r' % (evs,)
    assert [int(c) for c in me['cells'][0]] == [6, 5], 'C1 头应落 (6,5): %r' % (me['cells'][0],)
    print('C1 grass->flat survive: head (6,5)')

    # ---- C2) 水(-1)→h1：出水上一台阶 → 存活 ----
    reset({(10, 10): -1, (11, 10): 1}, [(10, 10), (9, 10), (8, 10)])
    await tick(room)
    snap, evs = await read_snaps(ws, rid)
    me = [q for q in snap['players'] if q['id'] == pid][0]
    assert me['alive'] is True, 'C2 水→h1 不应死: evs=%r' % (evs,)
    print('C2 water->h1 survive')

    # ---- C3) 草(-2)→深渊(-9)：入口即致命 → cause='fall' ----
    reset({(5, 5): -2, (6, 5): -9}, [(5, 5), (5, 6), (4, 6)])
    await tick(room)
    snap, evs = await read_snaps(ws, rid)
    dies = [e for e in evs if e.get('t') == 'die']
    assert dies and dies[0].get('cause') == 'fall', 'C3 草→深渊 应 fall 死: evs=%r' % (evs,)
    assert [q for q in snap['players'] if q['id'] == pid][0]['alive'] is False
    print('C3 grass->abyss die: cause=fall')

    # ---- C4) 平(0)→h2：真撞崖不变（h2 在目的格 (11,5)）----
    reset({(11, 5): 2}, [(10, 5), (9, 5), (8, 5)])
    await tick(room)
    snap, evs = await read_snaps(ws, rid)
    dies = [e for e in evs if e.get('t') == 'die']
    assert dies and dies[0].get('cause') == 'cliff', 'C4 平→h2 应 cliff 死: evs=%r' % (evs,)
    print('C4 flat->h2 die: cause=cliff')

    # ---- C5) h9→草(-2)：物理落差 9≥8 → fall 死不变 ----
    reset({(10, 10): 9, (11, 10): -2}, [(10, 10), (9, 10), (8, 10)])
    await tick(room)
    snap, evs = await read_snaps(ws, rid)
    dies = [e for e in evs if e.get('t') == 'die']
    assert dies and dies[0].get('cause') == 'fall', 'C5 h9→草 应 fall 死: evs=%r' % (evs,)
    print('C5 h9->grass die: cause=fall')

    # ---- C6) h7→水(-1)：物理落差 7 在断尾带 [2,7] → 存活净掉6节（9→3）----
    reset({(5, 5): 7, (6, 5): -1},
          [(5, 5), (5, 6), (4, 6), (4, 7), (3, 7), (3, 8), (2, 8), (2, 9), (1, 9)])
    await tick(room)
    snap, evs = await read_snaps(ws, rid)
    me = [q for q in snap['players'] if q['id'] == pid][0]
    assert me['alive'] is True, 'C6 h7→水 应存活(断尾带): evs=%r' % (evs,)
    assert len(me['cells']) == 3, 'C6 断尾净掉6节(9→3)，实际 %d' % len(me['cells'])
    print('C6 h7->water survive: len 9->3')

    await ws.close()
    server.close()
    print('depression cliff p48 E2E PASS')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except AssertionError as e:
        print('depression cliff p48 E2E FAIL:', e)
        sys.exit(1)
