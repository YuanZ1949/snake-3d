import asyncio, json, urllib.request, websockets

WS = "ws://127.0.0.1:28000/"
HTTP = "http://127.0.0.1:28000/"


async def recv_until(ws, t, timeout=5):
    while True:
        m = json.loads(await asyncio.wait_for(ws.recv(), timeout))
        if m.get("t") == t:
            return m


def http_get(path):
    with urllib.request.urlopen(HTTP.rstrip("/") + path, timeout=5) as r:
        return r.status, len(r.read())


async def main():
    # HTTP
    st, n = http_get("/")
    print("HTTP / ->", st, n, "bytes")
    st, n = http_get("/three.module.min.js")
    print("HTTP three.module.min.js ->", st, n)
    st, n = http_get("/api/leaderboard")
    print("HTTP /api/leaderboard ->", st, n)

    async with websockets.connect(WS) as ws:
        w = await recv_until(ws, "welcome")
        print("welcome rooms:", [(r["id"], r["name"], r["cols"]) for r in w["rooms"]])

        await ws.send(json.dumps({"t": "register", "user": "p1", "pass": "111111"}))
        a = await recv_until(ws, "auth")
        print("register p1 ok:", a["ok"], "token?", bool(a.get("token")))

        await ws.send(json.dumps({"t": "join", "room": "b", "name": "p1", "skin": 2, "size": 24}))
        rok = await recv_until(ws, "room-ok")
        print("room-ok:", rok)
        assert rok.get("id") is not None, "room-ok must carry player id"

        snap = await recv_until(ws, "snap")
        print("snap keys:", sorted(snap.keys()))
        print("  room=%s theme=%s cols=%s items=%s walls=%s portals=%s" % (
            snap["room"], snap["theme"], snap["cols"], snap["items"], snap["walls"], snap["portals"]))
        me = [p for p in snap["players"] if p["id"] == rok["id"]][0]
        print("  me: inv=%s eff=%s acct=%s skin=%s" % (me["inv"], me["eff"], me["acct"], me["skin"]))
        assert "inv" in me and "eff" in me

        # 造一个第二连接旁观
        async with websockets.connect(WS) as ws2:
            await recv_until(ws2, "welcome")
            await ws2.send(json.dumps({"t": "watch", "room": "b"}))
            rok2 = await recv_until(ws2, "room-ok")
            print("watch room-ok:", rok2)
            snap2 = await recv_until(ws2, "snap")
            print("spectator sees players:", [p["name"] for p in snap2["players"]])

        await ws.send(json.dumps({"t": "leaderboard"}))
        lb = await recv_until(ws, "leaderboard")
        print("leaderboard:", lb["list"])

        await ws.send(json.dumps({"t": "create", "name": "新房", "size": 20}))
        rm = await recv_until(ws, "rooms")
        print("rooms after create:", [(r["id"], r["name"]) for r in rm["list"]])

    print("E2E OK")


asyncio.run(main())
