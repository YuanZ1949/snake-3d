"""生产环境验证：房间列表属性 + 地图组合自定义 + 空房间回收（跑在 8090 端口）"""
import asyncio, json, urllib.request, websockets

WS = "ws://127.0.0.1:8090/"
HTTP = "http://127.0.0.1:8090/"


def http_get(p):
    with urllib.request.urlopen(HTTP.rstrip("/") + p, timeout=5) as r:
        return r.status, len(r.read())


async def recv_until(ws, t, timeout=6):
    while True:
        m = json.loads(await asyncio.wait_for(ws.recv(), timeout))
        if m.get("t") == t:
            return m


async def main():
    for p in ("/", "/three.min.js", "/api/leaderboard"):
        print("HTTP", p, "->", http_get(p))

    async with websockets.connect(WS) as ws:
        w = await recv_until(ws, "welcome")
        print("welcome:", [(r["id"], r["name"], r["cols"], r["theme"], r["players"]) for r in w["rooms"]])
        for r in w["rooms"]:
            for k in ("themeFixed", "rock", "portal", "players", "round", "hasPass", "persist"):
                assert k in r, (k, r)

        await ws.send(json.dumps({"t": "create", "name": "验证局", "size": 40,
                                  "theme": "ice", "rock": 0.5, "portal": True}))
        rm = await recv_until(ws, "rooms")
        cr = await recv_until(ws, "created")
        new = [r for r in rm["list"] if r["id"] == cr["room"]][0]
        print("create ->", new)
        assert new["cols"] == 40 and new["rows"] == 40, new
        assert new["theme"] == "ice" and new["themeFixed"] is True, new
        assert new["rock"] == 0.5 and new["portal"] is True, new

        await ws.send(json.dumps({"t": "join", "room": cr["room"], "name": "验证员"}))
        rok = await recv_until(ws, "room-ok")
        snap = await recv_until(ws, "snap")
        print("join ->", rok, "| snap cols=%s theme=%s portals=%s foods=%s" % (
            snap["cols"], snap["theme"], snap["portals"], len(snap["foods"])))
        assert snap["cols"] == 40 and snap["theme"] == "ice" and snap["portals"]
        rid = cr["room"]

    await asyncio.sleep(0.6)
    async with websockets.connect(WS) as ws2:
        w2 = await recv_until(ws2, "welcome")
        ids = [r["id"] for r in w2["rooms"]]
        print("after creator disconnect:", ids)
        # 新#11：自定义房间创建后 24h 内保留（不再随创建者断开立即回收）
        assert rid in ids, ("新建 24h 内的空房应保留", ids)
        assert {"a", "b", "c"} <= set(ids), ids

    print("PROD ROOMS VERIFY OK")


asyncio.run(main())
