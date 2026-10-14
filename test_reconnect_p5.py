# -*- coding: utf-8 -*-
"""批5 E2E：断线重连恢复原蛇（房内须有另一真人，否则单人房直接清）+ 房间聊天限速。"""
import asyncio
import json
import os
import sys

import websockets

BASE = os.environ.get('BASE', 'ws://127.0.0.1:28000')


async def recv_until(ws, pred, timeout=6.0):
    loop = asyncio.get_event_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        m = json.loads(await asyncio.wait_for(ws.recv(), timeout=max(0.1, end - loop.time())))
        if pred(m):
            return m
    raise AssertionError('timeout waiting for message')


async def next_snap(ws, room, timeout=4.0):
    return await recv_until(ws, lambda m: m.get('t') == 'snap' and m.get('room') == room, timeout)


async def main():
    ws1 = await websockets.connect(BASE, max_size=None)
    await recv_until(ws1, lambda m: m.get('t') == 'welcome')
    await ws1.send(json.dumps({'t': 'create', 'name': '重连房', 'size': 16}))
    created = await recv_until(ws1, lambda m: m.get('t') == 'created')
    room = created['room']
    await ws1.send(json.dumps({'t': 'join', 'room': room, 'name': 'Goer'}))
    ok = await recv_until(ws1, lambda m: m.get('t') == 'room-ok')
    old_id = ok['id']
    assert not ok.get('resumed'), 'first join should not be resumed'
    snap = await next_snap(ws1, room)
    me = [p for p in snap['players'] if p['id'] == old_id]
    assert me and me[0]['cells'], 'my snake missing in snapshot'
    old_cells = [tuple(c) for c in me[0]['cells']]
    print('1 joined: id=%s cells=%s' % (old_id, old_cells))

    # 另一个真人留在房里：单人房断线会直接清（挂起恢复只对"还有别人"生效）
    wsh = await websockets.connect(BASE, max_size=None)
    await recv_until(wsh, lambda m: m.get('t') == 'welcome')
    await wsh.send(json.dumps({'t': 'join', 'room': room, 'name': 'Bystander'}))
    await recv_until(wsh, lambda m: m.get('t') == 'room-ok')

    # 重采断线前最后一帧作基准（首帧采样到断线隔了几百 ms，蛇会走几格）
    snap = await next_snap(ws1, room)
    me = [p for p in snap['players'] if p['id'] == old_id]
    assert me and me[0]['cells'], 'my snake missing before disconnect'
    old_cells = [tuple(c) for c in me[0]['cells']]

    await ws1.close()          # Goer 断线 → 挂起原蛇（立即冻结）
    await asyncio.sleep(1.2)   # < RESUME_MS 宽限期

    ws2 = await websockets.connect(BASE, max_size=None)
    await recv_until(ws2, lambda m: m.get('t') == 'welcome')
    await ws2.send(json.dumps({'t': 'join', 'room': room, 'name': 'Goer'}))
    ok = await recv_until(ws2, lambda m: m.get('t') == 'room-ok')
    assert ok.get('resumed') is True, 'expected resumed room-ok, got %r' % (ok,)
    assert ok['id'] == old_id, 'resumed id %s != %s' % (ok['id'], old_id)
    snap = await next_snap(ws2, room)
    me = [p for p in snap['players'] if p['id'] == old_id]
    assert me, 'resumed snake missing'
    new_cells = [tuple(c) for c in me[0]['cells']]
    # 挂起期间蛇冻结；old_cells 采样于断线前最后一帧，允许 ≤2 格漂移，但不许重新出生（长度变）
    dist = sum(abs(a[0] - b[0]) + abs(a[1] - b[1])
               for a, b in zip(new_cells, old_cells)) / float(len(old_cells))
    assert len(new_cells) == len(old_cells), 'snake respawned: len %d != %d' % (
        len(new_cells), len(old_cells))
    assert dist <= 2, 'snake jumped %d cells after resume' % dist
    print('2 resumed: id=%s cells kept (%d segs, drift=%.1f)' % (
        ok['id'], len(old_cells), dist))

    # 聊天：第一条随快照 ev 下发，1 秒内第二条被限速
    await ws2.send(json.dumps({'t': 'chat', 'text': 'hello p5'}))
    ev1 = await recv_until(
        ws2, lambda m: m.get('t') == 'snap' and m.get('room') == room
        and any(e.get('t') == 'chat' and e.get('text') == 'hello p5' for e in m.get('ev', [])))
    who = [e for e in ev1['ev'] if e.get('t') == 'chat'][0]['name']
    print('3 chat delivered: name=%r' % (who,))
    await ws2.send(json.dumps({'t': 'chat', 'text': 'spam second'}))
    loop = asyncio.get_event_loop()
    end = loop.time() + 1.2
    got_second = False
    while loop.time() < end:
        try:
            s = json.loads(await asyncio.wait_for(
                ws2.recv(), timeout=max(0.1, end - loop.time())))
        except asyncio.TimeoutError:
            break
        if s.get('t') == 'snap' and any(e.get('t') == 'chat' for e in s.get('ev', [])):
            got_second = True
            break
    assert not got_second, 'rate limit failed: second chat passed within cooldown'
    print('4 chat throttled ok')

    await ws2.close()
    await wsh.close()
    print('RECONNECT+CHAT E2E OK')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except AssertionError as e:
        print('P5 E2E FAIL:', e)
        sys.exit(1)
