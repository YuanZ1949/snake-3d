# -*- coding: utf-8 -*-
"""批46 E2E：致命坠落（fall 死因）+ 坠落额外断尾（落差 2~3 净掉 落差-1 节）。

进程内起服（同 test_reactions_p33 模式）：外服随机地形不可控，直写 hmap
才能确定性构造落差场景。覆盖：
  A) 落差3（3→0）：存活 + 净掉2节（5→3），无 die 事件
  B) 落差4（3→-1，致命线）：ev die cause='fall' + alive=False
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


async def read_snaps(ws, room, n=2, timeout=4.0):
    """读 n 帧快照，返回 (最后一帧, 累计 ev 列表)"""
    evs, last = [], None
    for _ in range(n):
        last = await recv_until(ws, lambda m: m.get('t') == 'snap' and m.get('room') == room, timeout)
        evs += last.get('ev') or []
    return last, evs


async def tick(room, n=1, gap=0.16):
    """手动推进游戏循环（含 broadcast → 客户端收帧）"""
    for _ in range(n):
        await serve.game_cycle(time.monotonic(), serve.now_ms())
        await asyncio.sleep(gap)


async def main():
    # 屏蔽随机星星/道具生成（step_wrapper 内掷骰，可能落在路径格干扰断尾计数）
    serve.BONUS_SPAWN_P = 0.0
    orig_spawn_item = serve.Room.spawn_item
    serve.Room.spawn_item = lambda self, now: None

    server = await websockets.serve(serve.handler, '127.0.0.1', 0)
    port = server.sockets[0].getsockname()[1]
    ws = await websockets.connect('ws://127.0.0.1:%d' % port, max_size=None)
    await recv_until(ws, lambda m: m.get('t') == 'welcome')

    await ws.send(json.dumps({'t': 'create', 'name': '坠落测试', 'size': 16}))
    created = await recv_until(ws, lambda m: m.get('t') == 'created')
    rid = created['room']
    await ws.send(json.dumps({'t': 'join', 'room': rid, 'name': 'FallA'}))
    ok = await recv_until(ws, lambda m: m.get('t') == 'room-ok')
    pid = ok['id']
    room = serve.rooms[rid]
    p = room.players[pid]
    print('room=%s pid=%s' % (rid, pid))

    # 直写清场：空房间 + 平地（hmap 按场景注入；0=平不存）
    room.rocks = []
    room.walls = []
    room.portals = []
    room.items = []
    room.foods = []
    room.bonus = None
    room.eterrain = {}
    p['inv'] = 0
    p['eff'] = {}
    p['grow'] = 0
    p['tick'] = 150
    p['base_tick'] = 150
    p['off_at'] = None

    # ---- A) 落差3（3→0）：存活 + 净掉2节（5→3），头部落在落点格 ----
    room.hmap = {(5, 5): 3, }
    p['cells'] = [(5, 5), (4, 5), (3, 5), (2, 5), (1, 5)]
    p['dir'] = (1, 0)
    p['queue'] = []
    p['last_move'] = 0
    await tick(room)
    snap, evs = await read_snaps(ws, rid, 1)
    me = [q for q in snap['players'] if q['id'] == pid][0]
    assert me['alive'] is True, 'drop3 应存活: %r' % (me,)
    assert [int(c) for c in me['cells'][0]] == [6, 5], '头应落 (6,5): %r' % (me['cells'][0],)
    assert len(me['cells']) == 3, '落差3 净掉2节（5→3），实际 %d' % len(me['cells'])
    assert not any(e.get('t') == 'die' for e in evs), '落差3 不应有 die: %r' % (evs,)
    print('A drop3 survive: len 5->3, head (6,5), no die')

    # ---- B) 落差4（3→-1 = 致命线）：死亡 + cause=fall ----
    room.hmap = {(10, 10): 3, (11, 10): -1}
    p['cells'] = [(10, 10), (9, 10), (8, 10)]
    p['dir'] = (1, 0)
    p['queue'] = []
    p['last_move'] = 0
    await tick(room)
    snap, evs = await read_snaps(ws, rid, 1)
    dies = [e for e in evs if e.get('t') == 'die']
    assert dies, '应收到 die 事件: evs=%r' % (evs,)
    assert dies[0].get('id') == pid, '死者应是 FallA: %r' % (dies[0],)
    assert dies[0].get('cause') == 'fall', '死因应为 fall: %r' % (dies[0],)
    me = [q for q in snap['players'] if q['id'] == pid][0]
    assert me['alive'] is False, 'FallA 应已死亡: %r' % (me,)
    print('B drop4 die: ev die cause=fall, alive=False')

    await ws.close()
    server.close()
    print('fall p46 E2E PASS')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except AssertionError as e:
        print('fall p46 E2E FAIL:', e)
        sys.exit(1)
