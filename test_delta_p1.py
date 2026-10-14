# P1 协议级验收（批11 C1）：快照增量协议
# - 首帧全量：新订阅者首帧 snap 携带全部静态字段 + full 标志
# - 稳态增量：静态字段（walls/portals/rocks）变化时才下发，缺失即沿用
# - 中途观战者：第二个连接 watch 后其首帧仍是全量
import asyncio, json
import websockets

DELTA = ("food", "bonus", "rocks", "walls", "portals", "items")


async def recv_snap(ws):
    for _ in range(80):
        m = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        if m.get("t") == "snap":
            return m
    raise AssertionError("no snap received")


async def main():
    async with websockets.connect("ws://127.0.0.1:28000/") as ws1:
        await ws1.send(json.dumps({"t": "join", "room": "a", "name": "delta1"}))
        first = await recv_snap(ws1)
        # 1) 首帧全量：6 静态字段齐全（兼容旧测试直接取 snap["walls"] 的写法）
        for k in DELTA:
            assert k in first, "first snap missing %s" % k
        assert first.get("full") == 1, first.get("full")
        full_bytes = len(json.dumps(first, ensure_ascii=False).encode("utf-8"))
        # 2) 稳态增量：收 30 帧，静态字段 walls/portals 大多缺席（food 可能随吃/刷变化）
        delta_frames, miss_walls, miss_portals, delta_sizes = 0, 0, 0, []
        for _ in range(30):
            m = await recv_snap(ws1)
            assert "players" in m and "proj" in m, "per-frame fields missing"
            delta_frames += 1
            delta_sizes.append(len(json.dumps(m, ensure_ascii=False).encode("utf-8")))
            if "walls" not in m:
                miss_walls += 1
            if "portals" not in m:
                miss_portals += 1
        assert miss_walls >= 25, "walls sent too often: %d/30" % miss_walls
        assert miss_portals >= 25, "portals sent too often: %d/30" % miss_portals
        avg_delta = sum(delta_sizes) // len(delta_sizes)
        # 3) 中途观战者：新连接 watch 后首帧仍全量
        async with websockets.connect("ws://127.0.0.1:28000/") as ws2:
            await ws2.send(json.dumps({"t": "watch", "room": "a"}))
            w2 = await recv_snap(ws2)
            for k in DELTA:
                assert k in w2, "watcher first snap missing %s" % k
            assert w2.get("full") == 1, w2.get("full")
        print("DELTA P1 OK: first=full(%dB) avg_delta=%dB walls_miss=%d/30 portals_miss=%d/30"
              % (full_bytes, avg_delta, miss_walls, miss_portals))


asyncio.run(main())
