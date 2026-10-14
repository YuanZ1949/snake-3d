import asyncio, json, websockets

URL = "ws://127.0.0.1:28000/"


async def recv_until(ws, t, timeout=5):
    while True:
        m = json.loads(await asyncio.wait_for(ws.recv(), timeout))
        if m.get("t") == t:
            return m


async def main():
    async with websockets.connect(URL) as ws:
        w = await recv_until(ws, "welcome")
        print("1 welcome rooms:", [r["id"] for r in w["rooms"]])

        await ws.send(json.dumps({"t": "register", "user": "tester", "pass": "123456"}))
        a = await recv_until(ws, "auth")
        print("2 register ok=%s err=%s" % (a["ok"], a.get("err")))
        token = a.get("token")

        await ws.send(json.dumps({"t": "register", "user": "tester", "pass": "123456"}))
        a = await recv_until(ws, "auth")
        print("3 dup register ok=%s err=%s" % (a["ok"], a.get("err")))

        await ws.send(json.dumps({"t": "register", "user": "bad", "pass": "abc"}))
        a = await recv_until(ws, "auth")
        print("4 bad pass ok=%s err=%s" % (a["ok"], a.get("err")))

        await ws.send(json.dumps({"t": "login", "user": "tester", "pass": "123456"}))
        a = await recv_until(ws, "auth")
        print("5 login ok=%s stats=%s" % (a["ok"], a.get("stats")))

        await ws.send(json.dumps({"t": "login", "user": "tester", "pass": "000000"}))
        a = await recv_until(ws, "auth")
        print("6 wrong pass ok=%s err=%s" % (a["ok"], a.get("err")))

        await ws.send(json.dumps({"t": "authtoken", "token": token}))
        a = await recv_until(ws, "auth")
        print("7 authtoken ok=%s user=%s" % (a["ok"], a.get("user")))

        await ws.send(json.dumps({"t": "join", "room": "b", "name": "tester", "skin": 1, "size": 16}))
        rok = await recv_until(ws, "room-ok")
        print("8 room-ok:", rok)
        snap = await recv_until(ws, "snap")
        me = [p for p in snap["players"] if p["id"] == 1][0]
        print("9 snap room=%s theme=%s cols=%s walls=%s portals=%s inv=%s eff=%s acct=%s" % (
            snap["room"], snap["theme"], snap["cols"], snap["walls"], snap["portals"], me["inv"], me["eff"], me["acct"]))
        print("   keys:", sorted(snap.keys()))

        await ws.send(json.dumps({"t": "leaderboard"}))
        lb = await recv_until(ws, "leaderboard")
        print("10 leaderboard:", lb["list"][:3])

        await ws.send(json.dumps({"t": "rooms"}))
        rm = await recv_until(ws, "rooms")
        print("11 rooms:", [(r["id"], r["name"], r["players"]) for r in rm["list"]])

        await ws.send(json.dumps({"t": "create", "name": "测试房", "size": 20}))
        rm = await recv_until(ws, "rooms")
        print("12 after create:", [(r["id"], r["name"]) for r in rm["list"]])

    print("ALL WS TESTS DONE")


asyncio.run(main())
