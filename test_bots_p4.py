# -*- coding: utf-8 -*-
"""批4 E2E：单人练习/AI 蛇 —— create bots=3 → info 计数 → 快照 bot 字段 → AI 自主移动。"""
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
    async with websockets.connect(BASE, max_size=None) as ws:
        await recv_until(ws, lambda m: m.get('t') == 'welcome')
        await ws.send(json.dumps({'t': 'create', 'name': 'AI练习', 'size': 16, 'bots': 3}))
        created = await recv_until(ws, lambda m: m.get('t') == 'created')
        room = created['room']

        await ws.send(json.dumps({'t': 'rooms'}))
        rooms = await recv_until(ws, lambda m: m.get('t') == 'rooms')
        info = [r for r in rooms['list'] if r['id'] == room]
        assert info, 'new room missing in list'
        info = info[0]
        assert info['bots'] == 3, 'info.bots=%r' % (info['bots'],)
        assert info['players'] == 3, 'bots should occupy players count: %r' % (info['players'],)
        print('1 info ok: bots=%s players=%s' % (info['bots'], info['players']))

        await ws.send(json.dumps({'t': 'join', 'room': room, 'name': 'T'}))
        await recv_until(ws, lambda m: m.get('t') == 'room-ok')
        snap = await recv_until(ws, lambda m: m.get('t') == 'snap' and m.get('room') == room)
        bots = [p for p in snap['players'] if p.get('bot')]
        humans = [p for p in snap['players'] if not p.get('bot')]
        assert len(bots) == 3, 'snapshot bots=%d' % len(bots)
        assert len(humans) == 1, 'snapshot humans=%d' % len(humans)
        for b in bots:
            assert b['name'].startswith('AI-'), b['name']
            assert b['id'] < 0 and b['alive'] and b['cells'], b
        print('2 snapshot ok: bots=%d humans=%d names=%s' % (
            len(bots), len(humans), [b['name'] for b in bots]))

        # AI 自主移动：3 秒内任一 bot 蛇头位移
        first = {b['id']: tuple(b['cells'][0]) for b in bots}
        moved = False
        loop = asyncio.get_event_loop()
        end = loop.time() + 3
        while loop.time() < end and not moved:
            try:
                s = json.loads(await asyncio.wait_for(
                    ws.recv(), timeout=max(0.1, end - loop.time())))
            except asyncio.TimeoutError:
                break
            if s.get('t') != 'snap' or s.get('room') != room:
                continue
            for b in s['players']:
                if b.get('bot') and b['cells'] and tuple(b['cells'][0]) != first.get(b['id']):
                    moved = True
        assert moved, 'AI bots never moved in 3s'
        print('3 AI moving ok')

    print('BOTS E2E OK')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except AssertionError as e:
        print('BOTS E2E FAIL:', e)
        sys.exit(1)
