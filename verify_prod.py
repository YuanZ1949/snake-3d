import asyncio, json, websockets

WS = "ws://127.0.0.1:8090/"


async def recv_until(ws, t, timeout=5):
    while True:
        m = json.loads(await asyncio.wait_for(ws.recv(), timeout))
        if m.get("t") == t:
            return m


async def main():
    async with websockets.connect(WS) as ws:
        w = await recv_until(ws, "welcome")
        print("welcome rooms:", [(r["id"], r["name"], r["cols"]) for r in w["rooms"]])
        await ws.send(json.dumps({"t": "join", "room": "a", "name": "prod-check", "skin": 0}))
        ok = await recv_until(ws, "room-ok")
        print("room-ok:", ok)
        snap = await recv_until(ws, "snap")
        keys = sorted(snap.keys())
        print("snap room/theme/cols:", snap.get("room"), snap.get("theme"), snap.get("cols"))
        print("has food id:", (snap.get("food") or {}).get("id") is not None)
        me = [p for p in snap["players"] if p["id"] == ok["id"]]
        print("me cells:", me[0]["cells"] if me else None)
        print("PROD WS OK")


asyncio.run(main())
