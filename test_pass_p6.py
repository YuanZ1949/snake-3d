# -*- coding: utf-8 -*-
"""批6 E2E：房间口令（C3）+ 房间保存（新#11）——连 28000"""
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


async def main():
    ws1 = await websockets.connect(BASE, max_size=None)
    await recv_until(ws1, lambda m: m.get('t') == 'welcome')

    # 1) 非法口令建房 → 拒绝（不静默回退）
    await ws1.send(json.dumps({'t': 'create', 'name': '弱口令房', 'size': 16, 'pass': 'abc'}))
    err = await recv_until(ws1, lambda m: m.get('t') == 'error')
    assert '口令' in err.get('err', ''), err
    print('1 weak pass create rejected:', err['err'])

    # 2) 黑名单口令同样拒绝（格式合法但弱口令）
    await ws1.send(json.dumps({'t': 'create', 'name': '黑名单房', 'size': 16, 'pass': 'abc123'}))
    err = await recv_until(ws1, lambda m: m.get('t') == 'error')
    assert '口令' in err.get('err', ''), err
    print('2 blacklisted pass rejected:', err['err'])

    # 3) 合法口令建房成功，info 带 hasPass（rooms 广播可能先于 created 到达，两个都要收）
    await ws1.send(json.dumps({'t': 'create', 'name': '口令房', 'size': 16, 'pass': 'xy1234'}))
    got = {}
    while 'created' not in got or 'rooms' not in got:
        m = await recv_until(ws1, lambda x: x.get('t') in ('created', 'rooms')
                             and x.get('t') not in got)
        got[m['t']] = m
    rid = got['created']['room']
    info = [r for r in got['rooms']['list'] if r['id'] == rid][0]
    assert info['hasPass'] is True and info['persist'] is False, info
    assert 'passw' not in info, 'passw leaked'
    print('3 created with pass: room=%s hasPass=%s' % (rid, info['hasPass']))

    # 4) 第二连接：无口令 join → 拒
    ws2 = await websockets.connect(BASE, max_size=None)
    await recv_until(ws2, lambda m: m.get('t') == 'welcome')
    await ws2.send(json.dumps({'t': 'join', 'room': rid, 'name': '无口令'}))
    err = await recv_until(ws2, lambda m: m.get('t') == 'error')
    assert '口令' in err.get('err', ''), err
    print('4 join without pass rejected:', err['err'])

    # 5) 错口令 join → 拒；对口令 join → 成功
    await ws2.send(json.dumps({'t': 'join', 'room': rid, 'name': '错口令', 'pass': 'xy9999'}))
    err = await recv_until(ws2, lambda m: m.get('t') == 'error')
    assert '口令' in err.get('err', ''), err
    print('5 wrong pass rejected:', err['err'])
    await ws2.send(json.dumps({'t': 'join', 'room': rid, 'name': '访客', 'pass': 'xy1234'}))
    rok = await recv_until(ws2, lambda m: m.get('t') == 'room-ok')
    assert rok['room'] == rid, rok
    print('6 correct pass joined: id=%s' % rok['id'])

    # 6) 观战也要口令
    ws3 = await websockets.connect(BASE, max_size=None)
    await recv_until(ws3, lambda m: m.get('t') == 'welcome')
    await ws3.send(json.dumps({'t': 'watch', 'room': rid}))
    err = await recv_until(ws3, lambda m: m.get('t') == 'error')
    assert '口令' in err.get('err', ''), err
    print('7 watch without pass rejected:', err['err'])

    # 7) 保存：批24 完全放开——非创建者也能保存，回执 rooms persist=true（原：非创建者拒）
    await ws2.send(json.dumps({'t': 'persist', 'room': rid}))
    rooms = await recv_until(ws2, lambda m: m.get('t') == 'rooms'
                              and any(r.get('persist') for r in m.get('list', [])))
    info = [r for r in rooms['list'] if r['id'] == rid][0]
    assert info['persist'] is True, info
    print('8 persist by non-owner allowed: persist=%s' % info['persist'])
    # 创建者再保存（幂等，无报错）仍回 rooms persist=true
    await ws1.send(json.dumps({'t': 'persist', 'room': rid}))
    rooms = await recv_until(ws1, lambda m: m.get('t') == 'rooms'
                              and any(r.get('persist') and r.get('id') == rid
                                      for r in m.get('list', [])))
    info = [r for r in rooms['list'] if r['id'] == rid][0]
    assert info['persist'] is True, info
    print('9 owner persisted: %s persist=%s' % (rid, info['persist']))

    # 8) 断线恢复路径也要口令（join 带 pass 且能 resumed——此处仅验证带口令可进）
    await ws2.close()
    await ws3.close()
    await ws1.close()
    print('PASS+PERSIST E2E OK')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except AssertionError as e:
        print('P6 E2E FAIL:', e)
        sys.exit(1)
