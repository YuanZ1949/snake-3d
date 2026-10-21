#!/usr/bin/env python3
"""批41 修复#6：死亡遥测只读统计（分析 data/usage.log 的 die 事件，不改落盘格式）。

用法: python scripts/death_stats.py [path/to/usage.log]   # 默认 data/usage.log
输出: 死因分布 / 主题分布 / 高度迁移(Δh) / 上行摔死(cliff)细分 / top 致死格
退出: 0（无数据也 0，仅提示）
"""
import json
import sys
from collections import Counter
from pathlib import Path


def load_dies(path):
    dies, skipped = [], 0
    try:
        fh = open(path, encoding='utf-8')
    except OSError as e:
        print(f"[warn] cannot open {path}: {e}")
        return dies, skipped
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if d.get('e') == 'die':
                dies.append(d)
    return dies, skipped


def pct(n, total):
    return f"{n} ({n * 100.0 / total:.1f}%)" if total else "0"


def top_cells(dies, k=8):
    c = Counter((d.get('x'), d.get('y'), d.get('room')) for d in dies)
    return c.most_common(k)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else str(Path('data') / 'usage.log')
    dies, skipped = load_dies(path)
    print(f"== death_stats: {path} ==")
    if skipped:
        print(f"[warn] skipped {skipped} unparseable line(s)")
    if not dies:
        print("no die events found")
        return 0
    total = len(dies)
    span = f"at {min(d['at'] for d in dies)}..{max(d['at'] for d in dies)}"
    print(f"total die: {total}  {span}")

    print("\n-- cause --")
    for cause, n in Counter(d.get('cause') for d in dies).most_common():
        print(f"  {str(cause):8s} {pct(n, total)}")

    print("\n-- theme --")
    for theme, n in Counter(str(d.get('theme')) for d in dies).most_common():
        print(f"  {theme:10s} {pct(n, total)}")

    print("\n-- delta height (h1 - h0) --")
    dh = Counter((d.get('h1') or 0) - (d.get('h0') or 0) for d in dies)
    for k in sorted(dh):
        print(f"  dh={k:+d} {pct(dh[k], total)}")

    up = [d for d in dies
          if d.get('cause') == 'cliff' and (d.get('h1') or 0) - (d.get('h0') or 0) >= 2]
    cliff = [d for d in dies if d.get('cause') == 'cliff']
    print(f"\n-- cliff deaths: {len(cliff)}, of which up-step (dh>=2): {len(up)} --")
    if up:
        ring = Counter()
        for d in up:
            for h in d.get('ring') or []:
                ring[h] += 1
        print(f"  up-death ring heights: {dict(sorted(ring.items()))}")

    print("\n-- top fatal cells (x, y, room) --")
    for (x, y, room), n in top_cells(dies):
        print(f"  ({x},{y}) @{room}: {n}")

    humans = [d for d in dies if d.get('user')]
    print(f"\nby logged-in user: {len(humans)} / {total} ({pct(len(humans), total)})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
