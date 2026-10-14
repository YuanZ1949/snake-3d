# P1 协议级验收：snap 携带 combo / proj 携带 spd / 新道具可出现在 items
import asyncio, json, sys
import websockets


async def main():
    async with websockets.connect("ws://127.0.0.1:28000/") as ws:
        await ws.send(json.dumps({"t": "join", "room": "a", "name": "p1check"}))
        snap = None
        for _ in range(60):
            m = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            if m.get("t") == "snap":
                snap = m
                break
        assert snap, "no snap received"
        ps = snap["players"]
        assert ps, "no players in snap"
        assert all("combo" in p for p in ps), "players[] missing combo field"
        assert isinstance(ps[0]["combo"], int), ps[0]["combo"]
        # 观战模式下等几帧看 items/proj 字段结构（字段常驻，无论是否有值）
        assert "items" in snap and "proj" in snap
        for pr in snap["proj"]:
            assert "spd" in pr, pr
        # 收满 1 秒快照，验证字段持续存在
        for _ in range(20):
            m = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            if m.get("t") == "snap":
                for p in m["players"]:
                    assert "combo" in p
                for pr in m["proj"]:
                    assert "spd" in pr and pr["spd"] in (1.0, 1.5)
        print("P1 PROTOCOL OK: combo field present on all players, proj spd present")
        # 打印新道具枚举（服务端 ITEM_TYPES 6 种）
        import serve
        assert len(serve.ITEM_TYPES) == 6, serve.ITEM_TYPES
        assert set(serve.ITEM_TYPES) == {"shield", "speed", "ghost", "magnet", "double", "rage"}
        print("ITEM_TYPES:", serve.ITEM_TYPES)


asyncio.run(main())
