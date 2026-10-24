# -*- coding: utf-8 -*-
"""批47 补丁回归：spawn 落点不得面朝致命地形（cliff/fall）。

根因（线上抽查发现）：_spawn_player_impl 的 _open_ahead 未传 cur_h →
前方开阔度不查高度 → ~9% 出生点面朝峭壁/深渊，玩家不转向直走 1~4 步
即 cliff（摔下悬崖了）或 fall（坠落身亡）。

断言：N 次 spawn 后直走前 4 步，不得出现 cliff/fall 死因（墙/岩不算——
那是既有边界行为，且 _open_ahead 本就拦）。
"""
import random
import collections

import serve

N = 400
SIZE = 128


def simulate_straight(room, cells, d):
    """模拟蛇直走（不转向）前 4 步，返回 (cause, step) 或 (None, 4+)。"""
    hx, hy = cells[0]
    cur_h = room.hmap.get((hx, hy), 0)
    for step in range(1, 5):
        hx += d[0]
        hy += d[1]
        if hx < 0 or hy < 0 or hx >= room.cols or hy >= room.rows:
            return 'wall', step
        if (hx, hy) in room.rocks or (hx, hy) in room.walls:
            return 'rock', step
        nh = room.hmap.get((hx, hy), 0)
        if nh - cur_h >= 2:
            return 'cliff', step
        if nh - cur_h <= -serve.FALL_DEATH:
            return 'fall', step
        cur_h = nh
    return None, 4


def run(size, n=N):
    bad = collections.Counter()
    for i in range(n):
        room = serve.Room('t%d' % i, 'test', size)
        if not room.hmap:
            room.build_terrain()
        p = {'id': 1, 'name': 't', 'base_tick': 150, 'cells': [], 'dir': (1, 0),
             'alive': True, 'queue': [], 'bot': False, 'score': 0}
        room.players = {1: p}
        room.spawn_player(p)
        cause, step = simulate_straight(room, p['cells'], p['dir'])
        if cause in ('cliff', 'fall'):
            bad[cause] += 1
    return bad


def main():
    random.seed(20261024)
    for size in (128, 96):
        bad = run(size)
        total = sum(bad.values())
        print(f'{size}x{size}: cliff/fall 直走4步致死 = {total}/{N} {dict(bad)}')
        assert total == 0, f'{size} 图 spawn 仍面朝致命地形 {total} 次 {dict(bad)}'
    print('PASS: 所有 spawn 前方 4 格无 cliff/fall 致命地形')


if __name__ == '__main__':
    main()
