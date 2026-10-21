"""房间列表 + 地图组合自定义 的端到端测试（跑在 28000 端口的测试服上）"""
import asyncio, json, websockets

WS = "ws://127.0.0.1:28000/"


async def recv_until(ws, t, timeout=5):
    while True:
        m = json.loads(await asyncio.wait_for(ws.recv(), timeout))
        if m.get("t") == t:
            return m


async def main():
    async with websockets.connect(WS) as ws:
        w = await recv_until(ws, "welcome")
        base = {r["id"] for r in w["rooms"]}
        for r in w["rooms"]:
            for k in ("id", "name", "cols", "rows", "theme", "players", "themeFixed", "rock", "portal"):
                assert k in r, (k, r)
        print("welcome rooms:", [(r["id"], r["name"], r["cols"], r["theme"],
                                  r["players"], r["themeFixed"]) for r in w["rooms"]])

        # ---- 1. 创建组合自定义地图 ----
        await ws.send(json.dumps({"t": "create", "name": "自定义局", "size": 40,
                                  "theme": "lava", "rock": 0, "portal": True}))
        rm = await recv_until(ws, "rooms")
        new = [r for r in rm["list"] if r["id"] not in base]
        assert len(new) == 1, [r["id"] for r in rm["list"]]
        rid = new[0]["id"]
        print("create(custom):", new[0])
        assert new[0]["cols"] == 40 and new[0]["rows"] == 40, new[0]
        assert new[0]["theme"] == "lava", new[0]
        assert new[0]["themeFixed"] is True, new[0]
        assert new[0]["rock"] == 0.0, new[0]
        assert new[0]["portal"] is True, new[0]
        cr = await recv_until(ws, "created")
        assert cr["room"] == rid and cr["name"] == "自定义局", cr
        print("created msg:", cr)

        # ---- 2. 非法参数回退为"跟随主题/默认" ----
        await ws.send(json.dumps({"t": "create", "name": "容错局", "size": "xx",
                                  "theme": "nope", "rock": "abc", "portal": "yes"}))
        rm2 = await recv_until(ws, "rooms")
        cr2 = await recv_until(ws, "created")
        f = [r for r in rm2["list"] if r["id"] == cr2["room"]][0]
        print("create(fallback):", f)
        assert f["cols"] == 48 and f["rows"] == 48, f   # 批41：新建房默认尺寸 24→48
        assert f["themeFixed"] is False, f
        assert f["rock"] in (0.5, 0.6, 1.0, 1.7), f
        assert isinstance(f["portal"], bool), f
        await ws.send(json.dumps({"t": "create", "name": "岩石超限", "size": 48, "rock": 99}))
        await recv_until(ws, "rooms")
        cr3 = await recv_until(ws, "created")
        print("created:", cr3["room"])

        # ---- 3. 进房后人数广播 + 快照反映自定义地图 ----
        async with websockets.connect(WS) as ws2:
            w2 = await recv_until(ws2, "welcome")
            await ws2.send(json.dumps({"t": "join", "room": rid, "name": "旁观甲"}))
            rok = await recv_until(ws2, "room-ok")
            print("room-ok:", rok)
            assert rok["room"] == rid and rok["id"] is not None

            rm3 = await recv_until(ws, "rooms")   # 第一个连接应当收到人数变化广播
            r3 = [r for r in rm3["list"] if r["id"] == rid][0]
            print("rooms after join:", r3["players"], r3["alive"])
            assert r3["players"] == 1 and r3["alive"] == 1, r3

            snap = await recv_until(ws2, "snap")
            print("snap: cols=%s theme=%s portals=%s food=%s" % (
                snap["cols"], snap["theme"], snap["portals"], len(snap["foods"])))
            assert snap["cols"] == 40 and snap["theme"] == "lava", snap
            assert snap["portals"], "覆盖项 portal=True 应该生成传送门"
            assert snap["rocks"] == [], snap["rocks"]

        # ---- 4. 断开后人数广播 ----
        rm4 = await recv_until(ws, "rooms")
        r4 = [r for r in rm4["list"] if r["id"] == rid][0]
        print("rooms after disconnect:", r4["players"])
        assert r4["players"] == 0, r4

        # ---- 5. 重连时的房间列表同样带属性 ----
        await ws.send(json.dumps({"t": "rooms"}))
        rm5 = await recv_until(ws, "rooms")
        assert all("themeFixed" in r and "rock" in r for r in rm5["list"])
        print("rooms total:", len(rm5["list"]))
        myrooms = [r["id"] for r in rm5["list"] if r["id"].startswith("r")]
        print("custom rooms while owner online:", myrooms)
        assert rid in myrooms and cr2["room"] in myrooms, myrooms   # 创建者在线 → 房间保留

    # ---- 6. 创建者断线后：新建房 24h 内保留（批6 起语义），默认房常驻 ----
    # 批36 对齐口径：本例原断言「空自定义房立即被回收」是批6 之前的老口径；
    # gc_empty_rooms 现为 ROOM_KEEP_SECS=24h 内一律保留（新#11 需求）。本套件
    # 此前不在任何门禁里（local_ci 9 套/ci.yml 8 套都不含它）→ 腐化无人发现。
    await asyncio.sleep(0.5)   # 等服务端处理完断开
    async with websockets.connect(WS) as ws3:
        w3 = await recv_until(ws3, "welcome")
        ids = [r["id"] for r in w3["rooms"]]
        print("after owner disconnect:", ids)
        assert {"a", "b", "c"} <= set(ids), ids                       # 默认房常驻
        assert rid in ids and cr2["room"] in ids, (ids, rid, cr2["room"])   # 24h 内保留

    print("WS3 (room list + custom map + gc) OK")


asyncio.run(main())
