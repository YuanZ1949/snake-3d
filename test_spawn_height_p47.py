# -*- coding: utf-8 -*-
"""批47 补丁回归：spawn/传送门出口落点不得面朝致命地形（cliff/fall）。

根因（线上抽查发现）：_spawn_player_impl 的 _open_ahead 未传 cur_h →
前方开阔度不查高度 → ~9% 出生点面朝峭壁/深渊，玩家不转向直走 1~4 步
即 cliff（摔下悬崖了）或 fall（坠落身亡）。审查 H-1：传送门出口择向
（serve.step）同根因，宏伟档 17.1% 出口首步即致命。审查 M-1：本回归
原构造未传 height_mult → eff_height<2.0 从未进批47 山脉分支。

断言：
1. spawn 直走前 4 步不得 cliff/fall（墙/岩不算——既有边界行为）；
2. 宏伟档（height_mult=2.6，断言 eff_height>=2.0 证进山脉分支）同 1；
3. 传送门出口（H-1）两级契约：首步 cliff/fall 0 容忍（传送即死）；
   四方向全被围死（max_o<4）时取最优方向的中段撞崖为明示降级
   （可避地形），但若出现 max_o>=4 却选了致命方向 = 择优回归。
"""
import random
import collections

import serve

N = 400
SIZE = 128
MAJESTIC = 2.6          # 批47 宏伟档：eff_height>=2.0 走山脉分支（主脊 h6-11/神峰 14-18）
DIRS4 = ((1, 0), (-1, 0), (0, 1), (0, -1))


def walk4(room, hx, hy, d):
    """模拟从 (hx,hy) 沿 d 直走前 4 步，返回 (cause, step) 或 (None, 4+)。"""
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


def simulate_straight(room, cells, d):
    """模拟蛇直走（不转向）前 4 步，返回 (cause, step) 或 (None, 4+)。"""
    return walk4(room, cells[0][0], cells[0][1], d)


def run(size, n=N, height_mult=None, check_mountain=False):
    bad = collections.Counter()
    for i in range(n):
        room = serve.Room('t%d' % i, 'test', size, height_mult=height_mult)
        if not room.hmap:
            room.build_terrain()
        if check_mountain:
            # M-1：证明进了批47 山脉分支（eff_height>=2.0 → gen_heights 山脉路径）
            assert room.eff_height() >= 2.0, 'eff_height<2.0 未进山脉分支'
        p = {'id': 1, 'name': 't', 'base_tick': 150, 'cells': [], 'dir': (1, 0),
             'alive': True, 'queue': [], 'bot': False, 'score': 0}
        room.players = {1: p}
        room.spawn_player(p)
        cause, step = simulate_straight(room, p['cells'], p['dir'])
        if cause in ('cliff', 'fall'):
            bad[cause] += 1
    return bad


def run_portal(size, n=100, height_mult=None, check_mountain=False):
    """传送门出口安全（审查 H-1）：两级契约。

    ① 必修（0 容忍）：选向后**首步**不得 cliff/fall——即「传送即死」。
    ② 降级策略（审查 fix_hint 认可的明确降级）：出口四方向全被地形围死
       （max _spawn_open < 4，选无可选）时，取最优方向后 4 步内撞崖
       属可避地形（玩家可见可转向）；此时必须同时满足 max_o < 4 且
       step >= 2，否则即择优逻辑回归。

    选向规则复制自 serve.step 传送门分支（order = 进入方向优先 + 三向，
    严格大于择优），改 step 时同步本函数。进入方向遍历 4 种可能。
    """
    first_death = 0               # ① 首步即死（必修项）
    degraded = []                 # ② 降级态样本（须同时满足 max_o<4 且 step>=2）
    exits_checked = 0
    for i in range(n):
        room = serve.Room('p%d' % i, 'test', size, portal_on=True,
                          height_mult=height_mult)
        room.build_terrain()
        if check_mountain:
            assert room.eff_height() >= 2.0, 'eff_height<2.0 未进山脉分支'
        if not room.portals:
            continue
        pmap = room.portal_map()
        for (ex, ey) in pmap:                      # 每个出口格（两端互为出入口）
            for d0 in DIRS4:                       # 进入方向（撞门前朝向）遍历
                order = (d0,) + tuple(d for d in DIRS4 if d != d0)
                best, bo = order[0], -1
                scores = {}
                for d in order:
                    o = room._spawn_open(ex, ey, d, None)
                    scores[d] = o
                    if o > bo:
                        bo, best = o, d
                exits_checked += 1
                cause, step = walk4(room, ex, ey, best)
                if cause not in ('cliff', 'fall'):
                    continue
                if step == 1:
                    first_death += 1
                    degraded.append(('FIRST-DEATH', size, i, (ex, ey), d0,
                                     best, cause, step, dict(scores)))
                elif max(scores.values()) >= 4:
                    degraded.append(('BAD-CHOICE', size, i, (ex, ey), d0,
                                     best, cause, step, dict(scores)))
                else:
                    degraded.append(('enclosed', size, i, (ex, ey), d0,
                                     best, cause, step, dict(scores)))
    return first_death, degraded, exits_checked


def main():
    random.seed(20261024)
    for size in (128, 96):
        bad = run(size)
        total = sum(bad.values())
        print(f'{size}x{size}: cliff/fall 直走4步致死 = {total}/{N} {dict(bad)}')
        assert total == 0, f'{size} 图 spawn 仍面朝致命地形 {total} 次 {dict(bad)}'
    # M-1：宏伟档（山脉分支）spawn 同契约
    for size in (128, 96):
        bad = run(size, n=200, height_mult=MAJESTIC, check_mountain=True)
        total = sum(bad.values())
        print(f'{size}x{size} majestic(h={MAJESTIC}): cliff/fall 直走4步致死 = {total}/200 {dict(bad)}')
        assert total == 0, f'宏伟档 {size} 图 spawn 仍面朝致命地形 {total} 次 {dict(bad)}'
    # H-1：传送门出口（默认 + 宏伟档）——两级契约
    random.seed(20261024)
    total_first = 0
    total_bad_choice = 0
    enclosed_total = 0
    for size in (128, 96):
        for hm in (None, MAJESTIC):
            fd, deg, checked = run_portal(size, height_mult=hm,
                                          check_mountain=(hm is not None))
            bad_choice = [d for d in deg if d[0] == 'BAD-CHOICE']
            enclosed = [d for d in deg if d[0] == 'enclosed']
            label = f'h={hm}' if hm else 'default'
            print(f'{size}x{size} portal[{label}]: 首步即死={fd} 择优回归={len(bad_choice)} '
                  f'四向围死降级={len(enclosed)} (checked={checked})')
            for d in deg[:5]:
                print('   ', d)
            total_first += fd
            total_bad_choice += len(bad_choice)
            enclosed_total += len(enclosed)
            assert fd == 0, f'传送即死（首步 cliff/fall）{fd} 例 —— H-1 必修项回归 {deg[:3]}'
            assert not bad_choice, f'存在 max_o>=4 的更优方向却选了致命方向 {len(bad_choice)} 例 —— 择优回归 {bad_choice[:3]}'
    print(f'PASS: spawn 无 cliff/fall；传送门首步即死=0、择优回归=0'
          f'（四向围死降级 {enclosed_total} 例为可避地形，见 run_portal docstring）')


if __name__ == '__main__':
    main()
