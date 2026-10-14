#!/usr/bin/env python3
"""后台使用情况报表 —— 读 data/usage.json（汇总）与 data/usage.log（明细）。
这些数据只在服务器上查看：页面上不展示，也没有对外接口。

用法：
    python3 usage_report.py            # 最近 14 天
    python3 usage_report.py 30         # 最近 30 天
    python3 usage_report.py 30 --log   # 另外打印最近 100 条明细
"""
import json
import sys
import time
import unicodedata
from pathlib import Path

DATA = Path(__file__).resolve().parent / 'data'
SUM = DATA / 'usage.json'
LOG = DATA / 'usage.log'


def width(s):
    """终端显示宽度（中文算 2 列）"""
    return sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in str(s))


def L(s, n):
    return str(s) + ' ' * max(0, n - width(s))


def R(s, n):
    return ' ' * max(0, n - width(s)) + str(s)


def dur(sec):
    s = int(sec or 0)
    if s < 60:
        return f'{s}s'
    if s < 3600:
        return f'{s // 60}m{s % 60:02d}s'
    return f'{s // 3600}h{(s % 3600) // 60:02d}m'


def when(ts):
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(ts)) if ts else '-'


def main():
    n, show_log = 14, False
    for a in sys.argv[1:]:
        if a == '--log':
            show_log = True
        else:
            n = int(a)

    try:
        data = json.loads(SUM.read_text('utf-8'))
    except Exception:
        data = {}
    totals, days, users = (data.get(k, {}) for k in ('totals', 'days', 'users'))

    print('=' * 74)
    print('贪吃蛇 3D · 服务器使用情况（后台记录，页面不展示）')
    print('=' * 74)
    print(f"累计连接 {totals.get('sessions', 0)} 次 · 总在线 {dur(totals.get('conn_s'))} · "
          f"玩局 {dur(totals.get('play_s'))} · 进房 {totals.get('joins', 0)} 次")
    print(f"胜利 {totals.get('wins', 0)} 次 · 注册 {totals.get('registers', 0)} · "
          f"登录 {totals.get('logins', 0)} · 汇总账号 {len(users)} 个")

    print('\n最近 %d 天' % n)
    print(L('日期', 12) + R('连接', 6) + R('在线', 9) + R('玩局', 9) + R('进房', 7)
          + R('登录', 6) + R('注册', 6) + R('胜利', 6) + R('活跃账号', 9))
    print('-' * 74)
    for k in sorted(days.keys())[-n:]:
        d = days[k]
        print(L(k, 12) + R(d.get('sessions', 0), 6) + R(dur(d.get('conn_s')), 9)
              + R(dur(d.get('play_s')), 9) + R(d.get('joins', 0), 7)
              + R(d.get('logins', 0), 6) + R(d.get('registers', 0), 6)
              + R(d.get('wins', 0), 6) + R(len(d.get('users', [])), 9))

    top = sorted(users.items(), key=lambda kv: kv[1].get('play_s', 0), reverse=True)[:15]
    if top:
        print('\n账号维度 TOP %d（按玩局时长）' % len(top))
        print(L('账号', 16) + R('玩局', 9) + R('在线', 9) + R('连接', 6) + R('进房', 6)
              + R('胜', 5) + R('最高', 7) + '  ' + '最后活跃')
        print('-' * 74)
        for name, u in top:
            print(L(name, 16) + R(dur(u.get('play_s')), 9) + R(dur(u.get('conn_s')), 9)
                  + R(u.get('sessions', 0), 6) + R(u.get('joins', 0), 6)
                  + R(u.get('wins', 0), 5) + R(u.get('best', 0), 7)
                  + '  ' + when(u.get('last')))

    if LOG.exists():
        lines = LOG.read_text('utf-8', errors='replace').splitlines()
        print('\n明细 data/usage.log：%d 条，%d KB（超 8MB 自动轮转成 usage.log.1）'
              % (len(lines), LOG.stat().st_size // 1024))
        if show_log:
            print('-' * 74)
            for ln in lines[-100:]:
                print('  ' + ln)
    else:
        print('\n（还没有明细 data/usage.log）')


if __name__ == '__main__':
    main()
