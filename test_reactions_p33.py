# -*- coding: utf-8 -*-
"""批33 E2E：元素反应——进程内起服（直写服务端状态需与 handler 同进程，外服做不到）。

流程：A 踩冰格获得 cryo aura（真实 step+broadcast，客户端从 snap 收到）→
B 直写 hydro aura → A 咬 B → 双端收到 react/frozen 事件 + 双方 aura 双消 +
B 冻结期不移动而 A 照常移动（截断只按基础咬击，冻结不额外截）。
"""
import asyncio
import json
import sys
import time

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


def next_snap(ws, room, timeout=4.0):
    return recv_until(ws, lambda m: m.get('t') == 'snap' and m.get('room') == room, timeout)


async def tick(room, n=1, gap=0.16):
    """手动推进 n 个游戏循环（含 broadcast → 客户端收帧）。"""
    for _ in range(n):
        await serve.game_cycle(time.monotonic(), serve.now_ms())
        await asyncio.sleep(gap)


async def main():
    # 进程内起服：随机端口，不碰 local_ci 的 28000/8090
    server = await websockets.serve(serve.handler, '127.0.0.1', 0)
    port = server.sockets[0].getsockname()[1]
    base = 'ws://127.0.0.1:%d' % port

    ws1 = await websockets.connect(base, max_size=None)
    await recv_until(ws1, lambda m: m.get('t') == 'welcome')
    await ws1.send(json.dumps({'t': 'create', 'name': '元素反应房', 'size': 16}))
    created = await recv_until(ws1, lambda m: m.get('t') == 'created')
    rid = created['room']
    await ws1.send(json.dumps({'t': 'join', 'room': rid, 'name': 'CryoA'}))
    ok1 = await recv_until(ws1, lambda m: m.get('t') == 'room-ok')
    ida = ok1['id']
    wsb = await websockets.connect(base, max_size=None)
    await recv_until(wsb, lambda m: m.get('t') == 'welcome')
    await wsb.send(json.dumps({'t': 'join', 'room': rid, 'name': 'HydroB'}))
    ok2 = await recv_until(wsb, lambda m: m.get('t') == 'room-ok')
    idb = ok2['id']
    print('1 joined: A=%s B=%s room=%s' % (ida, idb, rid))

    room = serve.rooms[rid]
    pa, pb = room.players[ida], room.players[idb]

    # 直写状态：清随机干扰 + 平地 + (6,5) 冰格
    room.rocks = []
    room.walls = []
    room.portals = []
    room.items = []
    room.foods = []
    room.hmap = {}
    room.eterrain = {(6, 5): 'cryo'}
    for p in (pa, pb):
        p['inv'] = 0
        p['eff'] = {}
        p['grow'] = 0
        p['tick'] = 150
        p['base_tick'] = 150
        p['off_at'] = None
        p.pop('aura', None)
    # A 头(5,5) 朝右 → 下一步踩 (6,5) 冰格；B 竖排 x=7，(7,5) 为身体 idx1（A 的咬点）
    pa['cells'] = [(5, 5), (4, 5), (3, 5)]
    pa['dir'] = (1, 0)
    pa['queue'] = []
    pb['cells'] = [(7, 4), (7, 5), (7, 6), (7, 7)]
    pb['dir'] = (0, 1)
    pb['queue'] = []

    # 1) A 踩冰格 → 附着 cryo（走真实 step，客户端从 snap 确认）
    pa['last_move'] = 0
    pb['last_move'] = serve.now_ms() + 10 ** 7      # B 暂不动
    await tick(room)
    snap = await next_snap(ws1, rid)
    me = [p for p in snap['players'] if p['id'] == ida][0]
    assert me.get('aura') and me['aura']['e'] == 'cryo', \
        'A stepping on cryo eterrain should gain aura, got %r' % (me.get('aura'),)
    assert [int(c) for c in me['cells'][0]] == [6, 5], 'A head should be on ice cell: %r' % (me['cells'][0],)
    print('2 aura attach: A aura=%r head=%r' % (me['aura'], me['cells'][0]))

    # 2) B 直写 hydro aura；A 就位咬 B 身体 (7,5) → cryo×hydro = 冻结
    now = serve.now_ms()
    room.set_aura(pb, 'hydro', now)
    pa['cells'] = [(6, 5), (5, 5), (4, 5)]
    pa['last_move'] = 0
    pb['last_move'] = now + 10 ** 7
    await tick(room)
    evs = []
    snap = None
    for _ in range(4):
        m = await next_snap(wsb, rid)
        snap = m                      # react 与状态（aura 双消/截断）同帧广播
        evs += m.get('ev') or []
        if any(e.get('t') == 'react' for e in evs):
            break
    react = [e for e in evs if e.get('t') == 'react']
    assert react, 'B client should receive react event, evs=%r' % (evs,)
    assert react[0].get('kind') == 'frozen', 'expected frozen reaction, got %r' % (react[0],)
    assert react[0].get('victim') == idb, 'victim should be B: %r' % (react[0],)
    # 双端送达：A 客户端也能收到
    evs1 = []
    for _ in range(4):
        m = await next_snap(ws1, rid)
        evs1 += m.get('ev') or []
        if any(e.get('t') == 'react' for e in evs1):
            break
    assert any(e.get('t') == 'react' and e.get('kind') == 'frozen' for e in evs1), \
        'A client should also receive react/frozen, evs=%r' % (evs1,)
    print('3 react frozen delivered to both clients')

    fa = [p for p in snap['players'] if p['id'] == ida][0]
    fb = [p for p in snap['players'] if p['id'] == idb][0]
    assert fa.get('aura') is None and fb.get('aura') is None, \
        'dual consume failed: A=%r B=%r' % (fa.get('aura'), fb.get('aura'))
    assert len(fb['cells']) == 2, \
        'bite keeps max(MIN_LEN,idx)=2 segs, reaction adds no extra cut, got %d' % len(fb['cells'])
    assert fb.get('alive'), 'B should survive frozen bite'
    print('4 dual consume + cut=base only: B len=%d' % len(fb['cells']))

    # 3) 冻结期 B 不移动、A 照常移动
    pb['last_move'] = 0
    pa['last_move'] = 0
    cells_b = [tuple(int(v) for v in c) for c in pb['cells']]
    cells_a = [tuple(int(v) for v in c) for c in fa['cells']]
    await tick(room, 3)
    snap = await next_snap(ws1, rid)
    fb2 = [p for p in snap['players'] if p['id'] == idb][0]
    fa2 = [p for p in snap['players'] if p['id'] == ida][0]
    got_b = [tuple(int(v) for v in c) for c in fb2['cells']]
    got_a = [tuple(int(v) for v in c) for c in fa2['cells']]
    assert got_b == cells_b, 'B moved while frozen: %r -> %r' % (cells_b, got_b)
    assert got_a != cells_a, 'A did not move (test invalid): %r' % (got_a,)
    print('5 frozen holds B still; A moved %r -> %r' % (cells_a, got_a))

    await ws1.close()
    await wsb.close()
    server.close()
    print('reactions E2E PASS')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except AssertionError as e:
        print('reactions E2E FAIL:', e)
        sys.exit(1)
