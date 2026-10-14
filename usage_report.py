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

    # ---- 明细聚合：每小时在线曲线 + 房间热度（批12 增强） ----
    evs = []
    for f in (DATA / 'usage.log.1', LOG):
        if f.exists():
            for ln in f.read_text('utf-8', errors='replace').splitlines():
                try:
                    evs.append(json.loads(ln))
                except Exception:
                    pass
    if evs:
        now_ts = int(time.time())
        last_ts = max(int(o.get('at') or 0) for o in evs)
        # 在线曲线：conn/session(sid 配对) 重建并发连接数，按小时桶取峰值
        open_conn, events = set(), []
        for o in evs:
            t, sid = int(o.get('at') or 0), o.get('sid')
            if o.get('e') == 'conn' and sid is not None:
                open_conn.add(sid)
                events.append((t, 1))
            elif o.get('e') == 'session' and sid is not None:
                if sid in open_conn:
                    open_conn.discard(sid)
                    events.append((t, -1))
        if open_conn:  # 未闭合连接（服务仍在跑）延续到现在
            events.append((now_ts, -len(open_conn)))
        events.sort()
        hour_max, cur, i = {}, 0, 0
        end_h = (max(last_ts, now_ts) // 3600) * 3600
        start_h = end_h - 23 * 3600
        while i < len(events):
            t = events[i][0]
            h = (t // 3600) * 3600
            while i < len(events) and (events[i][0] // 3600) * 3600 == h:
                cur = max(0, cur + events[i][1])
                i += 1
            if h >= start_h:
                hour_max[h] = max(hour_max.get(h, 0), cur)
        peak = max(hour_max.values(), default=0)
        print('\n每小时在线峰值（最近 24h，conn 并发重建）')
        for h in range(start_h, end_h + 1, 3600):
            v = hour_max.get(h, 0)
            bar = '█' * (v * 30 // max(1, peak)) if peak else ''
            print(L(time.strftime('%m-%d %H:00', time.localtime(h)), 14) + R(v, 4) + '  ' + bar)
        # 房间热度：join 事件聚合
        rj, rs, rw = {}, {}, {}
        for o in evs:
            if o.get('e') == 'join' and o.get('room'):
                rj[o['room']] = rj.get(o['room'], 0) + 1
                rs.setdefault(o['room'], set()).add(o.get('sid'))
            elif o.get('e') == 'win' and o.get('room'):
                rw[o['room']] = rw.get(o['room'], 0) + 1
        if rj:
            print('\n房间热度（明细全量聚合）')
            print(L('房间', 10) + R('进房', 8) + R('会话', 8) + R('胜局', 8))
            print('-' * 42)
            for room in sorted(rj, key=rj.get, reverse=True)[:15]:
                print(L(room, 10) + R(rj[room], 8) + R(len(rs.get(room, ())), 8) + R(rw.get(room, 0), 8))
        # IP 分布 / 登录失败 / 匿名访问（批12 追加：按 conn/auth 明细的 ip 维度聚合）
        ip_conn, ip_first, ip_last, ip_sids, ip_uas = {}, {}, {}, {}, {}
        for o in evs:
            if o.get('e') != 'conn' or not o.get('ip'):
                continue
            ip = o['ip']
            ip_conn[ip] = ip_conn.get(ip, 0) + 1
            t = int(o.get('at') or 0)
            ip_first[ip] = min(ip_first.get(ip, t), t) if t else ip_first.get(ip, t)
            ip_last[ip] = max(ip_last.get(ip, 0), t)
            ip_sids.setdefault(ip, set()).add(o.get('sid'))
            if o.get('ua'):
                ip_uas.setdefault(ip, set()).add(str(o['ua'])[:40])
        if ip_conn:
            print('\nIP 分布（TOP 15，按连接次数）')
            print(L('IP', 18) + R('连接', 6) + R('会话', 6) + R('首次', 17) + R('最后', 17) + '  UA')
            print('-' * 74)
            for ip in sorted(ip_conn, key=ip_conn.get, reverse=True)[:15]:
                print(L(ip, 18) + R(ip_conn[ip], 6) + R(len(ip_sids.get(ip, ())), 6)
                      + R(time.strftime('%m-%d %H:%M', time.localtime(ip_first[ip])), 17)
                      + R(time.strftime('%m-%d %H:%M', time.localtime(ip_last[ip])), 17)
                      + '  ' + (' / '.join(sorted(ip_uas.get(ip, ()))[:2]) or '-'))
        fails = [o for o in evs if o.get('e') == 'auth' and not o.get('ok')]
        if fails:
            f_ip, f_user, f_at, f_kind = {}, {}, {}, {}
            for o in fails:
                ip = o.get('ip') or '-'
                f_ip[ip] = f_ip.get(ip, 0) + 1
                if o.get('user'):
                    f_user[o['user']] = f_user.get(o['user'], 0) + 1
                f_at[ip] = max(f_at.get(ip, 0), int(o.get('at') or 0))
                k = '%s:%s' % (o.get('kind'), (o.get('err') or 'fail')[:20])
                f_kind[k] = f_kind.get(k, 0) + 1
            print('\n登录失败（共 %d 次，防爆破排查）' % len(fails))
            print(L('IP', 18) + R('次数', 6) + R('最近', 17) + '  尝试账号')
            print('-' * 74)
            for ip in sorted(f_ip, key=f_ip.get, reverse=True)[:10]:
                print(L(ip, 18) + R(f_ip[ip], 6)
                      + R(time.strftime('%m-%d %H:%M', time.localtime(f_at[ip])), 17)
                      + '  ' + ', '.join(sorted({str(o.get('user')) for o in fails
                                                 if (o.get('ip') or '-') == ip and o.get('user')})[:4]))
            print('  失败类型分布：' + '  '.join('%s×%d' % (k, v) for k, v in sorted(f_kind.items(), key=lambda kv: -kv[1])[:6]))
        logged_ok = {o.get('ip') for o in evs
                     if o.get('e') == 'auth' and o.get('ok') and o.get('kind') in ('login', 'register', 'authtoken')}
        anon = {ip: c for ip, c in ip_conn.items() if ip not in logged_ok}
        if not anon:
            print('\n匿名访问：无（所有 IP 均有登录成功记录）')
        else:
            print('\n匿名访问（未见任何登录成功记录的 IP，TOP 15）')
            print(L('IP', 18) + R('连接', 6) + R('会话', 6) + R('最后活跃', 17) + '  UA')
            print('-' * 74)
            for ip in sorted(anon, key=anon.get, reverse=True)[:15]:
                print(L(ip, 18) + R(anon[ip], 6) + R(len(ip_sids.get(ip, ())), 6)
                      + R(time.strftime('%m-%d %H:%M', time.localtime(ip_last.get(ip, 0))), 17)
                      + '  ' + (' / '.join(sorted(ip_uas.get(ip, ()))[:2]) or '-'))
    else:
        print('\n（还没有明细，无法聚合在线曲线/房间热度）')

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
