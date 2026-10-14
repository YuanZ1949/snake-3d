"""最大地图 + 速度档位即时生效 + leave(返回主页) 的端到端测试（28000 测试服）"""
import asyncio, json, websockets

WS = "ws://127.0.0.1:28000/"


async def recv_until(ws, t, timeout=6):
    while True:
        m = json.loads(await asyncio.wait_for(ws.recv(), timeout))
        if m.get("t") == t:
            return m


async def snap_with_player(ws, pid):
    """读快照直到其中包含指定玩家，返回 (快照, 玩家条目)"""
    while True:
        s = await recv_until(ws, "snap")
        for p in s["players"]:
            if p["id"] == pid:
                return s, p


async def wait_tick(ws, pid, want, tries=12):
    """速度切换后轮询快照直到 tick 变成期望值（避免读到切换前的旧快照）"""
    me = None
    for _ in range(tries):
        _, me = await snap_with_player(ws, pid)
        if me["tick"] == want:
            return me
        await asyncio.sleep(0.05)
    raise AssertionError("tick 未变成 %s，最后为 %s" % (want, me["tick"]))


async def main():
    async with websockets.connect(WS) as ws:
        w = await recv_until(ws, "welcome")

        # ---- 1. 最大尺寸：96 生效，超过上限被夹到 96 ----
        await ws.send(json.dumps({"t": "create", "name": "超大图", "size": 96}))
        rm = await recv_until(ws, "rooms")
        cr = await recv_until(ws, "created")
        rid = cr["room"]
        big = [r for r in rm["list"] if r["id"] == rid][0]
        print("create(96):", big["id"], big["cols"], big["rows"])
        assert big["cols"] == 96 and big["rows"] == 96, big

        await ws.send(json.dumps({"t": "create", "name": "越界图", "size": 9999}))
        rm2 = await recv_until(ws, "rooms")
        cr2 = await recv_until(ws, "created")
        over = [r for r in rm2["list"] if r["id"] == cr2["room"]][0]
        print("create(9999) -> clamp:", over["cols"])
        assert over["cols"] == 96, over

        # ---- 2. 进 96 图：快照尺寸正确 ----
        await ws.send(json.dumps({"t": "join", "room": rid, "name": "巨蟒"}))
        rok = await recv_until(ws, "room-ok")
        pid = rok["id"]
        assert rok["room"] == rid and pid is not None, rok
        snap, me = await snap_with_player(ws, pid)
        print("96 map snap: cols=%s rows=%s tick=%s alive=%s"
              % (snap["cols"], snap["rows"], me["tick"], me["alive"]))
        assert snap["cols"] == 96 and snap["rows"] == 96, (snap["cols"], snap["rows"])
        assert me["alive"] is True, me
        assert me["tick"] == 150, me

        # ---- 3. 速度档位：切慢立即变慢，切快立即变快 ----
        await ws.send(json.dumps({"t": "speed", "ms": 260}))
        me = await wait_tick(ws, pid, 215)
        print("speed 260 ->", me["tick"])           # 260-45：加速区间上沿

        await ws.send(json.dumps({"t": "speed", "ms": 85}))
        me = await wait_tick(ws, pid, 85)
        print("speed 85 ->", me["tick"])

        # ---- 4. leave：收到 left 回执，自己从房间消失，人数归零 ----
        await ws.send(json.dumps({"t": "leave"}))
        left = await recv_until(ws, "left")
        print("left:", left)
        assert left["room"] == rid, left

        await ws.send(json.dumps({"t": "rooms"}))
        rm3 = await recv_until(ws, "rooms")
        gone = [r for r in rm3["list"] if r["id"] == rid][0]
        print("rooms after leave:", gone["players"], gone["alive"])
        assert gone["players"] == 0 and gone["alive"] == 0, gone
        assert rid in [r["id"] for r in rm3["list"]]   # 创建者在线 → 房间暂不回收

        # 离开后仍可再入局（pid 已清空，服务端会重新分配）
        await ws.send(json.dumps({"t": "join", "room": rid, "name": "巨蟒"}))
        rok2 = await recv_until(ws, "room-ok")
        assert rok2["id"] is not None and rok2["id"] != pid, rok2
        print("rejoin after leave: old=%s new=%s" % (pid, rok2["id"]))
        await ws.send(json.dumps({"t": "leave"}))
        await recv_until(ws, "left")

    # ---- 5. 创建者断线后，超大空房间被回收 ----
    await asyncio.sleep(0.6)
    async with websockets.connect(WS) as ws2:
        w2 = await recv_until(ws2, "welcome")
        ids = [r["id"] for r in w2["rooms"]]
        print("after disconnect:", ids)
        assert rid not in ids and cr2["room"] not in ids, ids
        assert {"a", "b", "c"} <= set(ids), ids

    print("WS4 (max map + speed instant + leave) OK")


asyncio.run(main())
