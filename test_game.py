import time

import serve

serve.init_rooms()


class S:
    def __init__(self):
        self.ws = None
        self.user = None
        self.pid = None
        self.play_from = None
        self.play_ms = 0
        self.last_room = None
        self.last_name = None
        self.last_score = 0
        self.chat_at = 0


def mk(room, pid, name, cells, d):
    s = S()
    p = serve.make_player(pid, s, name, 0)
    p["base_tick"] = 150
    room.players[pid] = p
    room.round_ids.add(pid)
    p["cells"] = list(cells)
    p["dir"] = d
    p["alive"] = True
    p["inv"] = 0
    p["eff"] = {}
    p["last_move"] = 0
    p["tick"] = 150
    return p


def fresh(size=10, **kw):
    r = serve.Room("t", "t", size, **kw)
    r.rocks = []
    r.walls = []
    r.portals = []
    r.items = []
    r.bonus = None
    r.foods = []
    r._reach = None      # 直接改地形绕过失效点 → 手动失效（批15①）
    return r


# ================= 批4 AI蛇 + 单人模式 =================
def test_bots_config_and_info():
    r = fresh(12, bots=99)
    assert r.bots == 7                      # 夹取上限
    r2 = fresh(12, bots="x")
    assert r2.bots == 0                     # 非法值回退 0
    r3 = fresh(12, bots=3)
    assert r3.info()["bots"] == 3


def test_bots_spawned_on_create():
    r = fresh(12, bots=3)
    bots = [p for p in r.players.values() if p.get("bot")]
    assert len(bots) == 3
    for p in bots:
        assert p["alive"] and p["cells"]
        assert p["id"] < 0                  # bot 用负 id，与真人 pid 不冲突
        assert p["id"] in r.round_ids
        assert str(p["name"]).startswith("AI-")


def test_bot_turns_toward_food():
    r = fresh(12, bots=1)
    p = [q for q in r.players.values() if q.get("bot")][0]
    hx, hy = 6, 6
    p["cells"] = [(hx, hy), (hx - 1, hy)]
    p["dir"] = (0, 1)                       # 初始朝下，食物在正右方
    p["queue"] = []
    p["inv"] = 0
    r.foods = [{"id": 999, "x": hx + 4, "y": hy, "score": 10, "color": "#fff"}]
    p["last_move"] = serve.now_ms() - 99999
    r.step(0.05, serve.now_ms())
    assert p["dir"] == (1, 0)               # 应转向食物方向
    assert p["alive"]


def test_bot_avoids_wall_death():
    r = fresh(12, bots=1)
    p = [q for q in r.players.values() if q.get("bot")][0]
    p["cells"] = [(r.cols - 1, 5), (r.cols - 2, 5)]   # 头贴右墙
    p["dir"] = (1, 0)
    p["queue"] = []
    p["inv"] = 0
    r.foods = []                           # 无目标：以空间为准
    p["last_move"] = serve.now_ms() - 99999
    r.step(0.05, serve.now_ms())
    assert p["alive"]                       # 没撞出界
    assert p["dir"] != (1, 0)               # 转离墙壁


def test_single_player_wins_vs_bots():
    r = fresh(12, bots=2)
    mk(r, 1, "Me", [(4, 4), (4, 5)], (1, 0))          # 真人玩家
    for q in [x for x in r.players.values() if x.get("bot")]:
        q["alive"] = False                            # AI 全灭
    r.check_win(serve.now_ms())
    assert r.win_pending is not None
    assert r.win_pending["winner"] == 1               # 单人击杀全部 AI → 获胜


def test_bots_ready_for_round_start():
    r = fresh(12, bots=2)
    mk(r, 1, "Me", [(4, 4), (4, 5)], (1, 0))
    r.win_pending = {"winner": None}
    r.ready.clear()
    r.maybe_start_round()
    assert r.win_pending is not None                  # 真人未 ready，不能开局
    r.ready.add(1)
    r.maybe_start_round()
    assert r.win_pending is None                      # 真人 ready 即开局（AI 视为永远 ready）
    assert r.round_no == 1
    for q in [x for x in r.players.values() if x.get("bot")]:
        assert q["alive"] and q["cells"]              # AI 新一局已重生


def test_bots_removed_when_last_human_leaves():
    r = fresh(12, bots=2)
    mk(r, 1, "Me", [(4, 4), (4, 5)], (1, 0))
    r.drop_player(1)
    assert r.players == {}                            # 最后一个人离开 → AI 一并清掉
    assert not r.round_ids


# ================= 批5 断线重连 + 房间聊天 =================
def test_disconnect_single_room_drops_immediately():
    r = fresh(12)
    mk(r, 1, "Me", [(4, 4), (4, 5)], (1, 0))
    sess = S(); sess.pid = 1; sess.room = r
    r.subs.add(sess)
    serve.leave_room(sess, hard=False)
    assert 1 not in r.players          # 单人房断线：无人可等 → 立即清（保空房回收语义）


def test_disconnect_multi_room_suspends():
    r = fresh(12)
    p1 = mk(r, 1, "Me", [(4, 4), (4, 5)], (1, 0))
    mk(r, 2, "Other", [(6, 4), (6, 5)], (1, 0))     # 另一个真人还在场
    sess = S(); sess.pid = 1; sess.room = r
    r.subs.add(sess)
    serve.leave_room(sess, hard=False)
    assert 1 in r.players and p1.get("off_at")      # 有别人 → 挂起等重连
    assert 2 in r.players


def test_offline_snake_frozen_until_resume():
    r = fresh(12)
    p1 = mk(r, 1, "Me", [(4, 4), (4, 5)], (1, 0))
    p2 = mk(r, 2, "Other", [(6, 4), (6, 5)], (1, 0))
    p1["off_at"] = serve.now_ms()                   # 挂起等重连
    cells1 = [tuple(c) for c in p1["cells"]]
    now = serve.now_ms()
    for _ in range(5):
        now += 200                                  # 超过 tick，真蛇该走
        r.step(0.05, now)
    assert [tuple(c) for c in p1["cells"]] == cells1   # 挂起蛇原地冻结
    assert p2["cells"][0] != (6, 4)                 # 在场蛇正常移动
    p1.pop("off_at")                                # 恢复 → 立刻回到场上
    r.step(0.05, now + 200)
    assert p1["cells"][0] != cells1[0]


# ================= 批6 弱口令 + 房间保留/保存 =================
def test_valid_room_pass():
    ok = serve.valid_room_pass
    assert ok("Game2024") is True and ok("room77x") is True
    assert ok("abc") is False            # 短于 6
    assert ok("a" * 21) is False         # 长于 20
    assert ok("12345678") is False       # 纯数字
    assert ok("abcdefg") is False        # 纯字母
    assert ok("abc-123") is False        # 非字母数字
    assert ok("abc123") is False         # 格式合法但弱口令黑名单
    assert ok(None) is False and ok("") is False
    assert serve.PASS_MIN == 6 and serve.PASS_MAX == 20


def test_room_pass_field_not_leaked():
    r1 = fresh(12, passw="xy1234")
    assert r1.info()["hasPass"] is True
    assert "passw" not in r1.info()      # 口令本身不进房间列表
    r2 = fresh(12)
    assert r2.info()["hasPass"] is False


def test_gc_holds_new_rooms_24h():
    serve.rooms["rgc"] = serve.Room("rgc", "新", 16)
    r = serve.rooms["rgc"]
    assert r.owner is None and not r.players and not r.subs
    serve.gc_empty_rooms()
    assert "rgc" in serve.rooms          # 创建不足 24h → 保留
    r.created -= serve.ROOM_KEEP_SECS + 60
    serve.gc_empty_rooms()
    assert "rgc" not in serve.rooms      # 超过 24h 无人 → 回收


def test_gc_keeps_persist_rooms():
    serve.rooms["rps"] = serve.Room("rps", "常驻", 16)
    r = serve.rooms["rps"]
    r.persist = True
    r.created -= serve.ROOM_KEEP_SECS * 3
    serve.gc_empty_rooms()
    assert "rps" in serve.rooms          # 持久化房间永不回收
    del serve.rooms["rps"]


def test_persist_roundtrip(tmpdir=None):
    import os
    path = os.path.join(os.environ.get("TEMP", "."), "t_persist_rooms.json")
    try:
        serve.rooms["rp1"] = serve.Room(
            "rp1", "回环", 32, theme_fixed="ice", rock_mult=0.5, portal_on=True,
            win_mode="score", limit=120, respawn=True, passw="ab12cd",
            walldeflect=True)   # 批17：碰墙折返随持久化往返
        serve.rooms["rp1"].persist = True
        serve.rooms["rp1"].owner_user = "creator"   # 批18：账号归属随持久化往返
        serve.rooms["rp1"].owner_tok = "tok123"      # 批23 P6：owner 凭据随持久化往返
        serve.save_persist_rooms(path)
        saved = serve.rooms.pop("rp1")
        assert serve.load_persist_rooms(path) == 1
        r = serve.rooms.get("rp1")
        assert r is not None and r.persist is True
        assert r.owner_user == "creator"
        assert r.owner_tok == "tok123"               # 批23 P6
        assert (r.name, r.cols, r.theme_fixed, r.rock_mult, r.portal_on) == (
            "回环", 32, "ice", 0.5, True)
        assert (r.win_mode, r.limit, r.respawn, r.passw) == (
            "score", 120, True, "ab12cd")
        assert r.walldeflect is True
        del serve.rooms["rp1"]
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_chat_appends_and_limits():
    r = fresh(12)
    assert r.chat("A", "  hello  ") is True
    assert r.chat("A", "   ") is False            # 空白不发
    assert r.chat("A", "x" * 200) is True
    evs = r.events
    assert evs[0]["t"] == "chat" and evs[0]["name"] == "A" and evs[0]["text"] == "hello"
    assert len(evs[1]["text"]) == 80              # 截断到 CHAT_MAX
    assert serve.CHAT_MAX == 80


def test_chat_throttle():
    s = S()
    now = serve.now_ms()
    assert serve.chat_throttle(s, now) is True
    assert serve.chat_throttle(s, now) is False   # 1 秒内第二条被限
    assert serve.chat_throttle(s, now + serve.CHAT_COOL) is True


def test_offline_kept_within_grace():
    r = fresh(12, bots=1)
    p = mk(r, 1, "Me", [(4, 4), (4, 5)], (1, 0))
    p["off_at"] = serve.now_ms() - 100            # 刚掉线 100ms
    r.step_wrapper(0.05, serve.now_ms())
    assert 1 in r.players                         # 宽限期内保留原蛇
    assert 1 in r.round_ids


def test_offline_dropped_after_grace():
    r = fresh(12, bots=1)
    p = mk(r, 1, "Me", [(4, 4), (4, 5)], (1, 0))
    p["off_at"] = serve.now_ms() - serve.RESUME_MS - 50
    r.step_wrapper(0.05, serve.now_ms())
    assert 1 not in r.players                     # 超时移除
    assert 1 not in r.round_ids


def test_offline_clears_bots_when_last_human_gone():
    r = fresh(12, bots=2)
    p = mk(r, 1, "Me", [(4, 4), (4, 5)], (1, 0))
    p["off_at"] = serve.now_ms() - serve.RESUME_MS - 50
    r.step_wrapper(0.05, serve.now_ms())
    assert r.players == {}                        # 最后真人超时 → AI 一并清掉


def test_resumable_matching():
    r = fresh(12)
    a = mk(r, 1, "A", [(4, 4)], (1, 0)); a["user"] = "u1"
    b = mk(r, 2, "B", [(5, 4)], (1, 0)); b["user"] = None
    a["off_at"] = b["off_at"] = serve.now_ms()
    assert r.resumable("u1") is a                 # 账户精确匹配
    assert r.resumable("u2") is None              # 账户不匹配不乱捡
    assert r.resumable(None) is None              # 匿名请求遇多个挂起者不恢复
    b.pop("off_at")
    assert r.resumable(None) is None              # 还有别人挂着（有账户）也不恢复
    a.pop("off_at")
    a["off_at"] = serve.now_ms()
    assert r.resumable(None) is None              # 唯一挂起者有账户 → 匿名不恢复
    a["user"] = None
    assert r.resumable(None) is a                 # 唯一挂起者无账户 → 匿名恢复


def test_resume_keeps_snake_state():
    s = S()
    r = fresh(12)
    p = mk(r, 1, "Me", [(4, 4), (4, 5), (4, 6)], (1, 0))
    p["score"] = 77
    p["off_at"] = serve.now_ms()
    r.resume(s, p)
    assert p.get("off_at") is None
    assert p["session"] is s
    assert s in r.subs
    assert r.players[1] is p and r.players[1]["score"] == 77   # 原蛇原分恢复
    assert r.players[1]["alive"]


def test_snapshot_carries_queue_len():
    """批13①：players 快照带 q=队列长度，供客户端 dirQ 对账"""
    r = fresh(12)
    p = mk(r, 1, "A", [(4, 4), (4, 5), (4, 6)], (1, 0))
    p["queue"] = [(0, 1), (1, 0)]
    snap = r.snapshot(0, full=True)
    me = [x for x in snap["players"] if x["id"] == 1][0]
    assert me.get("q") == 2, me.get("q")


def test_broadcast_send_fail_suspends_for_resume():
    """批13③：broadcast 发送失败 → leave_room(hard=False) 挂起等 resume，
    而不是只置 sess.room=None 留下幽灵订阅/双蛇"""
    import asyncio

    class BadWS:
        async def send(self, m):
            raise RuntimeError("closed ws")

    class GoodWS:
        async def send(self, m):
            pass

    r = fresh(12)
    s1, s2 = S(), S()
    s1.ws, s2.ws = BadWS(), GoodWS()
    p1 = mk(r, 1, "A", [(4, 4), (4, 5), (4, 6)], (1, 0))
    p2 = mk(r, 2, "B", [(7, 7), (7, 8), (7, 9)], (1, 0))
    for s, pid in ((s1, 1), (s2, 2)):
        s.room = r
        s.pid = pid
        s.full_sent = True
        r.subs.add(s)
    asyncio.run(r.broadcast())
    assert s1 not in r.subs, "发送失败必须摘除订阅（幽灵订阅会永久占房）"
    assert s1.room is None and s1.pid is None
    assert p1.get("off_at"), "房里另有真人 → 原蛇挂起等 RESUME_MS 内重连恢复"
    assert not p2.get("off_at")
    assert s2 in r.subs, "成功者不受影响"
    assert r.resumable(None) is p1, "重连 resume 必须命中同一条蛇"


def test_ghost_wrap():
    r = fresh(10)
    p = mk(r, 1, "A", [(0, 5), (1, 5), (2, 5)], (-1, 0))
    now = serve.now_ms()
    p["eff"] = {"ghost": now + 9999}
    r.step(0.05, now)
    assert p["alive"], "ghost should survive wall"
    assert p["cells"][0] == (r.cols - 1, 5), p["cells"]
    print("ghost wrap OK ->", p["cells"][0], "(cols=%d)" % r.cols)


def test_wall_death_without_ghost():
    r = fresh(10)
    p = mk(r, 1, "A", [(0, 5), (1, 5), (2, 5)], (-1, 0))
    now = serve.now_ms()
    r.step(0.05, now)
    assert not p["alive"] and p["cause"] == "wall", p.get("cause")
    print("wall death OK")


def test_portal():
    r = fresh(10)
    r.portals = [(3, 5), (7, 5)]
    p = mk(r, 1, "A", [(2, 5), (1, 5), (0, 5)], (1, 0))
    now = serve.now_ms()
    r.step(0.05, now)
    assert p["cells"][0] == (7, 5), p["cells"]
    print("portal teleport OK ->", p["cells"][0])


def test_item_pickup():
    r = fresh(10)
    now = serve.now_ms()
    r.items = [{"id": 1, "type": "shield", "x": 6, "y": 5, "born": now}]
    p = mk(r, 1, "A", [(5, 5), (4, 5)], (1, 0))
    r.step(0.05, now)
    assert not r.items, "item should be consumed"
    assert p["eff"].get("shield", 0) > now, p["eff"]
    print("item pickup OK, eff:", p["eff"])


def test_speed_effect():
    r = fresh(10)
    p = mk(r, 1, "A", [(5, 5), (4, 5)], (1, 0))
    p["tick"] = 150
    now = serve.now_ms()
    assert r.tick_of(p, now) == 150
    p["eff"] = {"speed": now + 9999}
    assert r.tick_of(p, now) == 90, r.tick_of(p, now)
    print("speed effect OK ->", r.tick_of(p, now))


def test_shield_immunity():
    r = fresh(10)
    now = serve.now_ms()
    p1 = mk(r, 1, "A", [(5, 5), (4, 5)], (1, 0))
    p2 = mk(r, 2, "B", [(7, 5), (6, 5), (6, 6)], (0, 1))
    p2["inv"] = now + 9999          # 重生保护
    p1["inv"] = 0
    r.step(0.05, now)
    assert p2["alive"], "protected victim should survive"
    assert p1["score"] == 0, p1["score"]
    print("spawn-inv immunity OK; p2 alive")


def test_shield_item_immunity():
    r = fresh(10)
    now = serve.now_ms()
    p1 = mk(r, 1, "A", [(5, 5), (4, 5)], (1, 0))
    p2 = mk(r, 2, "B", [(7, 5), (6, 5), (6, 6)], (0, 1))
    p2["inv"] = 0
    p2["eff"] = {"shield": now + 9999}
    r.step(0.05, now)
    assert p2["alive"], "shielded victim should survive"
    print("shield-item immunity OK")


def test_bite_truncates_not_kills():
    r = fresh(16)
    now = serve.now_ms()
    p1 = mk(r, 1, "A", [(5, 5), (4, 5)], (1, 0))
    p2 = mk(r, 2, "B", [(7, 5), (6, 5), (6, 6)], (0, 1))
    p1["inv"] = 0
    p2["inv"] = 0
    r.step(0.05, now)
    assert p2["alive"], "bitten victim should survive (truncated, not killed)"
    assert (6, 5) not in p2["cells"], p2["cells"]            # 咬点被截掉
    assert len(p2["cells"]) == serve.MIN_LEN, p2["cells"]     # 只剩最低格数
    # 攻击者吞并被截下的 1 格：本 tick 不缩尾，长度 +1，grow 已消耗
    assert len(p1["cells"]) == 3, p1["cells"]
    assert p1["grow"] == 0, p1["grow"]
    assert p1["score"] == serve.BITE_SCORE_PER_CELL, p1["score"]
    print("bite truncate OK: victim len", len(p2["cells"]), "eater len", len(p1["cells"]))


def test_bite_min_len_eliminates():
    # 规则升级（需求方点名）：已是最低 2 格的蛇再被咬 → 整条淘汰
    r = fresh(16)
    now = serve.now_ms()
    p1 = mk(r, 1, "A", [(5, 5), (4, 5)], (1, 0))
    p2 = mk(r, 2, "B", [(7, 5), (6, 5)], (0, 1))   # 已是最低 2 格
    p1["inv"] = 0
    p2["inv"] = 0
    r.events.clear()
    r.step(0.05, now)
    assert not p2["alive"], "2-grid snake should be eliminated"
    assert p2["cause"] == "bite" and p2["by"] == 1, (p2["cause"], p2["by"])
    # 攻击者吞掉剩余 2 格：grow +2，但本 tick 自身移动已消耗 1 → 余 1，身长 +1
    assert p1.get("grow", 0) == 1, p1.get("grow")
    assert len(p1["cells"]) == 3, p1["cells"]
    # 淘汰最后一名对手 → 触发胜局，+WIN_SCORE
    assert r.win_pending == {"winner": 1}, r.win_pending
    assert p1["score"] == 2 * serve.BITE_SCORE_PER_CELL + serve.WIN_SCORE, p1["score"]
    kinds = [e["t"] for e in r.events]
    assert "die" in kinds, kinds
    die = [e for e in r.events if e["t"] == "die"][0]
    assert die["cause"] == "bite" and die["by"] == 1, die
    assert [e for e in r.events if e["t"] == "bite"][0].get("kill") is True
    print("bite elimination OK: victim dead, eater score", p1["score"])


def test_bite_immunity():
    r = fresh(16)
    now = serve.now_ms()
    p1 = mk(r, 1, "A", [(5, 5), (4, 5)], (1, 0))
    p2 = mk(r, 2, "B", [(7, 5), (6, 5), (6, 6), (6, 7)], (0, 1))
    p1["inv"] = 0
    p2["inv"] = now + 9999
    r.step(0.05, now)
    assert len(p2["cells"]) == 4 and (6, 5) in p2["cells"], p2["cells"]
    assert p1["score"] == 0, p1["score"]
    print("bite immunity OK: protected victim not truncated")


def test_bullet_shortens_snake():
    r = fresh(16)
    now = serve.now_ms()
    p1 = mk(r, 1, "A", [(2, 2), (1, 2)], (1, 0))
    p1["inv"] = 0
    p2 = mk(r, 2, "B", [(7, 5), (6, 5), (5, 5), (4, 5)], (1, 0))
    p2["inv"] = 0
    r.projectiles = [{"owner": 1, "x": 5.0, "y": 5.0, "dx": 0.0, "dy": 0.0}]
    r._step_projectiles(0.0, now)
    assert len(p2["cells"]) == 3, p2["cells"]              # 缩短 1 格
    assert (4, 5) not in p2["cells"], p2["cells"]
    assert p1["score"] == 3, p1["score"]
    assert not r.projectiles, "bullet should be consumed"
    print("bullet shorten OK: victim len", len(p2["cells"]))


def test_bullet_ignores_owner_and_immunity():
    r = fresh(16)
    now = serve.now_ms()
    p1 = mk(r, 1, "A", [(5, 5), (4, 5), (3, 5), (2, 5)], (1, 0))
    p1["inv"] = 0
    p2 = mk(r, 2, "B", [(8, 8), (7, 8), (6, 8), (5, 8)], (1, 0))
    p2["inv"] = now + 9999                   # 免疫
    # 子弹停在 p1 自己身上 → 不应截断自己
    r.projectiles = [{"owner": 1, "x": 5.0, "y": 5.0, "dx": 0.0, "dy": 0.0}]
    r._step_projectiles(0.0, now)
    assert len(p1["cells"]) == 4, p1["cells"]
    # 子弹停在免疫的 p2 身上 → 不应截断
    r.projectiles = [{"owner": 1, "x": 8.0, "y": 8.0, "dx": 0.0, "dy": 0.0}]
    r._step_projectiles(0.0, now)
    assert len(p2["cells"]) == 4, p2["cells"]
    print("bullet owner/immunity OK")


def test_spawn_avoids_snakes_and_faces_open():
    r = fresh(24)
    other = mk(r, 9, "X", [(12, 12), (12, 11), (12, 10), (12, 9)], (0, 1))
    other["inv"] = 0
    s = S()
    p = serve.make_player(1, s, "A", 0)
    r.players[1] = p
    for _ in range(25):
        r.spawn_player(p)
        assert p["alive"] and len(p["cells"]) == 3, p["cells"]
        hx, hy = p["cells"][0]
        assert r._nearest_opp(hx, hy, 1) >= 2, ("spawned too close to other snake", p["cells"])
        assert r._open_ahead(hx, hy, p["dir"], 1) >= 4, ("spawn faces too little open space", p["dir"])
        assert all((cx, cy) not in other["cells"] for cx, cy in p["cells"]), p["cells"]
    print("spawn placement OK: dir", p["dir"], "head", p["cells"][0])


def test_food_has_unique_id():
    # 批25 语义：吃一补一后新果 id 不与场上已有 id 重复
    r = fresh(16)
    r.place_food()
    old_ids = {f["id"] for f in r.foods}
    kept_ids = {f["id"] for f in r.foods[1:]}
    r.foods = r.foods[1:]            # 模拟吃掉一颗
    r.place_food()
    new_id = (set(f["id"] for f in r.foods) - kept_ids).pop()
    assert new_id not in old_ids, (new_id, old_ids)
    assert len(r.foods) == len(old_ids)
    print("food unique id OK:", new_id, sorted(old_ids))


# ================= 批25 多果（经济拍板：果=10星尘，场上多果并存） =================
def test_multi_foods_target_and_unique():
    # 目标数 = min(8, max(3, size//8))；坐标互不重复
    r24 = fresh(24)
    r24.place_food()
    assert len(r24.foods) == 3, len(r24.foods)          # 24//8=3
    r96 = fresh(96)
    r96.place_food()
    assert len(r96.foods) == 8, len(r96.foods)          # 上限 8
    r10 = fresh(10)
    r10.place_food()
    assert len(r10.foods) == 3, len(r10.foods)          # 下限 3
    coords = [(f["x"], f["y"]) for f in r24.foods]
    assert len(set(coords)) == len(coords), coords      # 不重叠
    ids = [f["id"] for f in r24.foods]
    assert len(set(ids)) == len(ids), ids               # id 唯一
    print("multi foods OK:", len(r24.foods), len(r96.foods), len(r10.foods))


def test_multi_foods_eat_replenishes():
    # 吃掉一颗 → 列表移除该果并补一颗，保持满员；其余果不动
    r = fresh(24)
    r.place_food()
    before = len(r.foods)
    victim = {"id": 900, "x": 6, "y": 5, "score": 10, "color": 0xff5f5f}
    r.foods = [victim] + r.foods[1:]
    others = [f for f in r.foods[1:]]
    p = mk(r, 1, "A", [(5, 5), (4, 5), (3, 5)], (1, 0))   # 头在果左侧，朝果走
    r.step(0.05, serve.now_ms())                          # 头踏入 (6,5)
    assert len(r.foods) == before, (len(r.foods), before)
    assert all((f["x"], f["y"]) != (6, 5) for f in r.foods), r.foods   # 被吃那颗没了
    for f in others:                                      # 其余果原位保留
        assert any((g["x"], g["y"]) == (f["x"], f["y"]) for g in r.foods), (f, r.foods)
    assert p["score"] > 0, p["score"]
    print("eat replenish OK:", before, "->", len(r.foods))


def test_multi_foods_bot_target_nearest():
    # AI 目标选择：多果时取最近的一颗（bonus 优先级不变）
    r = fresh(24)
    r.place_food()
    far = {"id": 900, "x": 20, "y": 20, "score": 10, "color": 0xff5f5f}
    near = {"id": 901, "x": 6, "y": 5, "score": 10, "color": 0xff5f5f}
    r.foods = [far, near]
    r.bonus = None
    p = serve.make_player(1, None, "t", 0)
    p["cells"] = [(5, 5), (4, 5), (3, 5)]
    p["dir"] = (1, 0)
    p["alive"] = True
    r.players["1"] = p
    r._bot_think(p)
    # 首步应朝最近果 (6,5)（即 +x 直行），而不是 20,20
    assert p["queue"] == [] or p["queue"][0] == (1, 0), p["queue"]
    print("bot nearest food OK")


def test_store_gacha_fields():
    # 批25 T1: Store 星尘/皮肤库存/保底字段（防御式 + 钳制 + 老账号兼容）
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp(prefix="snake-gacha-store-"))
    st = serve.Store(d / "store.json")
    ok, err = st.register("gk", "135790")
    assert ok, err
    assert st.stardust("gk") == 0, st.stardust("gk")
    assert st.skins_of("gk") == [], st.skins_of("gk")
    st.add_stardust("gk", 160)
    assert st.stardust("gk") == 160, st.stardust("gk")
    st.add_stardust("gk", -99999)
    assert st.stardust("gk") == 0, st.stardust("gk")   # 钳制非负
    assert st.grant_skin("gk", 15) is True
    assert st.grant_skin("gk", 15) is False           # 已拥有
    assert st.skins_of("gk") == [15], st.skins_of("gk")
    # 批22 老账号：只有 salt/hash/stats，读不炸且默认值正确
    st.users["old"] = {"salt": "s", "hash": "h", "stats": serve.blank_stats()}
    assert st.stardust("old") == 0
    assert st.skins_of("old") == []
    assert st.grant_skin("old", 5) is True
    assert st.stardust("nobody") == 0                 # 不存在的账号
    print("store gacha fields OK")


class _FakeRng:
    """定点 rng：按序返回给定值，耗尽后恒 0.5"""
    def __init__(self, vals):
        self.vals = list(vals)

    def random(self):
        return self.vals.pop(0) if self.vals else 0.5


def test_gacha_probability_boundaries():
    # 批25 T2: 概率边界定点（0.016 / 0.146）
    assert serve.gacha_roll(_FakeRng([0.015]), False, 0, 0)["star"] == 5
    assert serve.gacha_roll(_FakeRng([0.0159]), False, 0, 0)["star"] == 5
    assert serve.gacha_roll(_FakeRng([0.02]), False, 0, 0)["star"] == 4
    assert serve.gacha_roll(_FakeRng([0.1459]), False, 0, 0)["star"] == 4
    assert serve.gacha_roll(_FakeRng([0.15]), False, 0, 0)["star"] == 3
    print("gacha boundaries OK")


def test_gacha_pity90_hard():
    r = serve.gacha_roll(_FakeRng([]), False, 89, 5)
    assert r["star"] == 5, r
    assert r["pity5"] == 0 and r["pity4"] == 0, r   # 出 5★ 双计数清零
    print("gacha pity90 OK")


def test_gacha_pity10_four():
    # FakeRng 恒 0.5：基础随机必落 3★ 分支 → 4★ 保底强制出货
    r = serve.gacha_roll(_FakeRng([0.5]), False, 0, 9)
    assert r["star"] == 4, r
    assert r["pity4"] == 0 and r["pity5"] == 1, r
    print("gacha pity10 four OK")


def test_gacha_pity_order():
    # 双保底同触：5★ 优先
    r = serve.gacha_roll(_FakeRng([0.5]), False, 89, 9)
    assert r["star"] == 5, r
    print("gacha pity order OK")


def test_gacha_5050_guarantee():
    # 保底强制出 5★ 驱动 50/50（不依赖 1.6% 命中）
    loss = serve.gacha_roll(_FakeRng([0.6]), False, 89, 0)   # up 掷骰 0.6 → 歪
    assert loss["star"] == 5 and loss["up"] is False and loss["lose5050"] is True, loss
    win = serve.gacha_roll(_FakeRng([0.3]), False, 89, 0)    # 0.3 → 中
    assert win["up"] is True and win["lose5050"] is False, win
    gtd = serve.gacha_roll(_FakeRng([]), True, 89, 0)        # 大保底必 UP，不耗 rng
    assert gtd["up"] is True and gtd["lose5050"] is False, gtd
    print("gacha 5050 OK")


def test_gacha_ten_pull_pity_carry():
    rng = serve.random.Random(7)
    p5 = p4 = 0
    for i in range(10):
        r = serve.gacha_roll(rng, False, p5, p4)
        if r["star"] == 5:
            assert r["pity5"] == 0 and r["pity4"] == 0, (i, r)
        elif r["star"] == 4:
            assert r["pity4"] == 0 and r["pity5"] == p5 + 1, (i, r)
        else:
            assert r["pity5"] == p5 + 1 and r["pity4"] == p4 + 1, (i, r)
        p5, p4 = r["pity5"], r["pity4"]
    print("gacha ten pull carry OK")


def test_pool_pick_uniform():
    seen3, seen4 = set(), set()
    for i in range(6):
        seen3.add(serve.pool_pick(_FakeRng([i / 6.0]), 3, False))
    for i in range(3):
        seen4.add(serve.pool_pick(_FakeRng([i / 3.0]), 4, False))
    assert seen3 == {5, 6, 7, 8, 9, 10}, seen3
    assert seen4 == {11, 12, 13}, seen4
    assert serve.pool_pick(_FakeRng([]), 5, True) == 15
    assert serve.pool_pick(_FakeRng([]), 5, False) == 14
    print("pool pick uniform OK")


def test_gacha_dist_smoke():
    rng = serve.random.Random(42)
    cnt = {3: 0, 4: 0, 5: 0}
    p5 = p4 = 0
    for _ in range(10000):
        r = serve.gacha_roll(rng, False, p5, p4)
        cnt[r["star"]] += 1
        p5, p4 = r["pity5"], r["pity4"]
    assert 80 <= cnt[5] <= 260, cnt          # 1.6% + 90 硬保底
    assert 1250 <= cnt[4] <= 1750, cnt      # 13% + 10 技保底（计数清零语义）
    print("gacha dist smoke OK:", cnt)


def test_room_custom_config():
    # 尺寸 / 主题 / 岩石 / 传送门 可自由组合
    r = serve.Room("x", "自定义", 40, theme_fixed="lava", rock_mult=0.0, portal_on=True)
    assert (r.cols, r.rows) == (40, 40), (r.cols, r.rows)
    assert r.theme == "lava", r.theme
    assert r.eff_rock() == 0.0, r.eff_rock()
    # 熔岩主题默认不放传送门，但覆盖项优先
    assert r.eff_portal() is True, r.eff_portal()
    assert r.portals, "portal override should place portals"
    # 固定主题换局不变
    r.new_round()
    assert r.theme == "lava", r.theme
    # 岩石覆盖为 0 → 吃再多水果也不出岩石
    r.fruits_eaten = 6
    r.maybe_rocks()
    assert len(r.rocks) == 0, r.rocks
    info = r.info()
    assert info["themeFixed"] is True
    assert info["rock"] == 0.0
    assert info["portal"] is True
    assert info["players"] == 0
    print("custom room OK:", info["cols"], "×", info["rows"], info["theme"],
          info["rock"], info["portal"], "fixed=", info["themeFixed"])

    d = serve.Room("d", "默认", 16)
    assert d.theme_fixed is None and d.info()["themeFixed"] is False
    assert d.eff_rock() == serve.THEME_CFG[d.theme]["rock"]
    assert d.eff_portal() == serve.THEME_CFG[d.theme]["portal"]
    print("default room follows theme OK:", d.theme, d.eff_rock(), d.eff_portal())


def test_usage_log():
    """后台使用记录：只落盘，不进协议"""
    import tempfile, shutil, json as _json
    from pathlib import Path
    d = Path(tempfile.mkdtemp(prefix="snake-usage-"))
    try:
        u = serve.Usage(d / "usage.log", d / "usage.json")
        u.session({"sid": 1, "ip": "1.2.3.4", "user": "alice", "name": "Alice",
                   "room": "a", "score": 42, "conn_s": 100, "play_s": 60,
                   "msgs": 5, "joins": 1})
        u.session({"sid": 2, "ip": "5.6.7.8", "user": None, "name": "游客",
                   "room": "b", "score": 0, "conn_s": 30, "play_s": 0,
                   "msgs": 2, "joins": 0})
        u.auth("login", True, "alice", "1.2.3.4")
        u.auth("login", False, "alice", "9.9.9.9", err="密码错误")   # 失败也要留痕（含原因，批20）
        u.win("a", "Alice", "alice", 42)
        u.note("join", sid=1, room="a", name="Alice")

        lines = [_json.loads(x) for x in (d / "usage.log").read_text("utf-8").splitlines()]
        kinds = [x["e"] for x in lines]
        assert kinds == ["session", "session", "auth", "auth", "win", "join"], kinds
        auths = [x for x in lines if x["e"] == "auth"]
        assert auths[0]["ok"] is True and auths[0]["kind"] == "login"
        assert "err" not in auths[0], auths[0]                        # 成功不记 err
        assert auths[1]["ok"] is False and auths[1]["ip"] == "9.9.9.9"
        assert auths[1]["err"] == "密码错误", auths[1]                 # 失败带具体原因

        s = _json.loads((d / "usage.json").read_text("utf-8"))
        t = s["totals"]
        assert t["sessions"] == 2 and t["conn_s"] == 130 and t["play_s"] == 60, t
        assert t["joins"] == 1 and t["logins"] == 1 and t["wins"] == 1, t
        a = s["users"]["alice"]
        assert a["sessions"] == 1 and a["play_s"] == 60 and a["joins"] == 1, a
        assert a["wins"] == 1 and a["best"] == 42, a
        day = list(s["days"].values())[0]
        assert day["sessions"] == 2 and day["users"] == ["alice"], day

        u2 = serve.Usage(d / "usage.log", d / "usage.json")     # 重新加载
        assert u2.data["totals"]["sessions"] == 2
        print("usage log OK:", kinds, t)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_auth_login_throttle():
    """批21：登录防爆破——同 (ip, 用户) 窗内连续失败超限直接拒绝（不查库，
    明细记"限速拒绝"），窗口过期或成功后计数复位；不同 ip/用户互不影响"""
    import tempfile, shutil, asyncio, json as _json
    from pathlib import Path
    d = Path(tempfile.mkdtemp(prefix="snake-authlim-"))
    old_store, old_usage, old_tokens = serve.store, serve.usage, serve.tokens
    old_win = serve.AUTH_FAIL_WIN
    try:
        serve.store = serve.Store(d / "store.json")
        serve.usage = serve.Usage(d / "usage.log", d / "usage.json")
        serve.tokens = {}
        serve.auth_fails.clear()

        async def run():
            s = _cfg_sess(sid="s1", user=None)
            s.ip = "9.8.7.6"
            await serve.handle_msg(s, {"t": "register", "user": "brt", "pass": "246810"})
            assert s.ws.sent[-1]["ok"] is True, s.ws.sent[-1]
            # 连续失败达上限：正常回执密码错误
            for _ in range(serve.AUTH_FAIL_MAX):
                await serve.handle_msg(s, {"t": "login", "user": "brt", "pass": "111111"})
                assert s.ws.sent[-1]["ok"] is False and s.ws.sent[-1].get("err") == "密码错误", s.ws.sent[-1]
            # 已锁定：正确密码也被拒（不查库），err 含"频繁"
            await serve.handle_msg(s, {"t": "login", "user": "brt", "pass": "246810"})
            assert s.ws.sent[-1]["ok"] is False and "频繁" in s.ws.sent[-1]["err"], s.ws.sent[-1]
            # 窗口过期 → 放行；正确密码成功且计数复位
            serve.AUTH_FAIL_WIN = 0
            await serve.handle_msg(s, {"t": "login", "user": "brt", "pass": "246810"})
            assert s.ws.sent[-1]["ok"] is True, s.ws.sent[-1]
            # 复位验证：恢复窗口后同账号再错一次 = 重新计数（不残留锁）
            serve.AUTH_FAIL_WIN = old_win
            await serve.handle_msg(s, {"t": "login", "user": "brt", "pass": "111111"})
            assert s.ws.sent[-1].get("err") == "密码错误", s.ws.sent[-1]
            # 键隔离：同 ip 不同用户不受他人的锁影响
            s2 = _cfg_sess(sid="s2", user=None)
            s2.ip = "9.8.7.6"
            await serve.handle_msg(s2, {"t": "login", "user": "other", "pass": "111111"})
            assert s2.ws.sent[-1].get("err") == "用户不存在", s2.ws.sent[-1]
            lines = [_json.loads(x) for x in (d / "usage.log").read_text("utf-8").splitlines()]
            lim = [x for x in lines if x.get("e") == "auth" and x.get("err") == "限速拒绝"]
            assert len(lim) == 1, lim
        asyncio.run(run())
        print("auth login throttle OK")
    finally:
        serve.store, serve.usage, serve.tokens = old_store, old_usage, old_tokens
        serve.AUTH_FAIL_WIN = old_win
        serve.auth_fails.clear()
        shutil.rmtree(d, ignore_errors=True)


def test_speed_change_instant():
    # 速度档位切换立即生效：调慢当场变慢、调快当场变快
    r = fresh(24)
    p = mk(r, 1, "A", [(5, 5), (4, 5), (3, 5)], (1, 0))
    p["tick"] = 150
    assert serve.apply_speed(p, 260) == 260          # 切「慢」
    assert p["base_tick"] == 260 and p["tick"] == 215, (p["base_tick"], p["tick"])
    p["tick"] = 110                                   # 吃水果累积加速后的状态
    serve.apply_speed(p, 85)                          # 切「快」
    assert p["base_tick"] == 85 and p["tick"] == 85, (p["base_tick"], p["tick"])
    serve.apply_speed(p, 150)                         # 切回「中」
    assert 105 <= p["tick"] <= 150, p["tick"]
    assert serve.apply_speed(p, 10) == 80             # 越界夹紧
    assert serve.apply_speed(p, 9999) == 300
    print("speed change OK -> base=%d tick=%d" % (p["base_tick"], p["tick"]))


def test_free_cells_big_map():
    # 最大地图（96×96）找空格：结果正确，且不能卡住主循环
    r = fresh(96)
    assert (r.cols, r.rows) == (96, 96), (r.cols, r.rows)
    assert r.cols <= serve.MAP_MAX, (r.cols, serve.MAP_MAX)
    mk(r, 1, "A", [(5, 5), (6, 5), (7, 5)], (1, 0))
    r.rocks = [(10, 10), (11, 11)]
    r.walls = [(0, 0)]
    r.items = [{"x": 20, "y": 20, "kind": "shield", "born": 0}]
    r.foods = [{"id": 1, "x": 30, "y": 30, "score": 1, "color": "red"}]
    blocked = {(5, 5), (6, 5), (7, 5), (10, 10), (11, 11), (0, 0), (20, 20), (30, 30)}
    free = r.free_list()
    assert len(free) == 96 * 96 - len(blocked), len(free)
    assert not (blocked & set(free)), "占用格不该出现在空格里"
    t0 = time.perf_counter()
    for _ in range(20):
        r.free_list()
    ms = (time.perf_counter() - t0) / 20 * 1000
    assert ms < 30, "%.1fms/scan 太慢" % ms
    r.place_food()
    added = [f for f in r.foods if (f["x"], f["y"]) != (30, 30)]   # 批25：只看新补的果
    assert added and all((f["x"], f["y"]) not in blocked for f in added), r.foods
    print("free cells 96x96 OK: free=%d, %.2fms/scan" % (len(free), ms))


def test_combo_increments_and_expires():
    r = fresh(16)
    now = serve.now_ms()
    p = mk(r, 1, "A", [(5, 5), (4, 5), (3, 5)], (1, 0))
    r.foods = [{"id": 1, "x": 6, "y": 5, "score": 10, "color": 0xff5f5f}]
    # 第一次吃果：combo=1，倍率 x1
    r.step(0.05, now)
    assert p["combo"] == 1, p.get("combo")
    assert p["score"] == 10, p["score"]
    # 3 秒内再吃：combo=2，仍 x1（档位 1-4）
    r.foods = [{"id": 2, "x": 7, "y": 5, "score": 10, "color": 0xff5f5f}]
    r.step(0.05, now + 200)
    assert p["combo"] == 2, p["combo"]
    assert p["score"] == 20, p["score"]
    # 超时后再吃：combo 重置为 1
    r.foods = [{"id": 3, "x": 8, "y": 5, "score": 10, "color": 0xff5f5f}]
    r.step(0.05, now + 200 + serve.COMBO_MS + 10)
    assert p["combo"] == 1, p["combo"]
    assert p["score"] == 30, p["score"]
    print("combo chain/reset OK: combo", p["combo"], "score", p["score"])


def test_combo_multiplier_tiers():
    r = fresh(16)
    now = serve.now_ms()
    p = mk(r, 1, "A", [(5, 5), (4, 5), (3, 5)], (1, 0))
    # 直接驱动倍率函数：1-4→x1, 5-9→x1.5, 10-14→x2, 15+→x2.5
    assert serve.combo_mult(1) == 1.0
    assert serve.combo_mult(4) == 1.0
    assert serve.combo_mult(5) == 1.5
    assert serve.combo_mult(9) == 1.5
    assert serve.combo_mult(10) == 2.0
    assert serve.combo_mult(15) == 2.5
    # 连吃 5 个（同 tick 链不现实，直接设 combo 后吃一个）
    p["combo"] = 4
    p["combo_at"] = now
    r.foods = [{"id": 1, "x": 6, "y": 5, "score": 20, "color": 0xff6b81}]
    r.step(0.05, now + 200)
    assert p["combo"] == 5, p["combo"]
    assert p["score"] == int(20 * 1.5), p["score"]   # 30
    print("combo tiers OK: combo", p["combo"], "score", p["score"])


def test_double_item_doubles_score():
    r = fresh(16)
    now = serve.now_ms()
    p = mk(r, 1, "A", [(5, 5), (4, 5), (3, 5)], (1, 0))
    p["eff"] = {"double": now + 9999}
    r.foods = [{"id": 1, "x": 6, "y": 5, "score": 15, "color": 0xe74c3c}]
    r.step(0.05, now)
    assert p["score"] == 30, p["score"]              # 15 × 2
    # 咬蛇得分也翻倍：造一只 2 格蛇
    p2 = mk(r, 2, "B", [(8, 5), (7, 5)], (0, 1))
    p2["inv"] = 0
    r.foods = []
    r.step(0.05, now + 200)
    # 咬杀 2 格：8×2=16 → 双倍 32；再加胜局 200 → 双倍不作用于胜局（只作用于咬蛇/吃果）
    assert p2["alive"] is False, p2["cells"]
    assert p["score"] == 30 + 32 + serve.WIN_SCORE, p["score"]
    print("double item OK: score", p["score"])


def test_magnet_pulls_food():
    r = fresh(16)
    now = serve.now_ms()
    p = mk(r, 1, "A", [(5, 5), (4, 5), (3, 5)], (1, 0))
    p["eff"] = {"magnet": now + 9999}
    r.foods = [{"id": 1, "x": 9, "y": 5, "score": 10, "color": 0xff5f5f}]
    r.step_wrapper(0.05, now)
    # 食物朝蛇头移动 1 格
    assert (r.foods[0]["x"], r.foods[0]["y"]) == (8, 5), r.foods
    # 挡路的岩石 → 绕开（换轴移动）
    r.rocks = [(7, 5)]
    r.step_wrapper(0.05, now + 60)
    assert (r.foods[0]["x"], r.foods[0]["y"]) != (7, 5), r.foods
    assert abs(r.foods[0]["x"] - 8) + abs(r.foods[0]["y"] - 5) == 1, r.foods
    # 无磁铁效果 → 不动
    p["eff"] = {}
    r.rocks = []
    r.foods = [{"id": 2, "x": 9, "y": 5, "score": 10, "color": 0xff5f5f}]
    r.step_wrapper(0.05, now + 120)
    assert (r.foods[0]["x"], r.foods[0]["y"]) == (9, 5), r.foods
    print("magnet OK")


def test_rage_halves_cooldown_and_speeds_bullet():
    r = fresh(16)
    now = serve.now_ms()
    p = mk(r, 1, "A", [(5, 5), (4, 5), (3, 5)], (1, 0))
    # CD 计算：无狂暴 800ms，狂暴 400ms
    assert r.atk_cd(p, now) == serve.ATK_COOL, r.atk_cd(p, now)
    p["eff"] = {"rage": now + 9999}
    assert r.atk_cd(p, now) == serve.ATK_COOL // 2, r.atk_cd(p, now)
    # 子弹速度 ×1.5
    p["eff"] = {}
    r.projectiles = [{"owner": 1, "x": 1.0, "y": 1.0, "dx": 1.0, "dy": 0.0, "spd": 1.5}]
    r._step_projectiles(0.1, now)
    assert abs(r.projectiles[0]["x"] - (1.0 + serve.PROJ_SPEED * 1.5 * 0.1)) < 1e-6, r.projectiles
    print("rage OK: cd", serve.ATK_COOL // 2, "bullet spd x1.5")


def test_battle_mode_config():
    r = serve.Room("t", "t", 10, win_mode="score", limit=60, respawn=True)
    assert r.win_mode == "score" and r.limit == 60 and r.respawn is True
    bad = serve.Room("t", "t", 10, win_mode="hack", limit=-5, respawn="yes")
    assert bad.win_mode == "last" and bad.limit == 0 and bad.respawn is False, (
        bad.win_mode, bad.limit, bad.respawn)
    over = serve.Room("t", "t", 10, limit=99999)
    assert over.limit == 3600, over.limit
    rs = serve.Room("t", "t", 10, respawn=True)
    assert rs.limit == 120, rs.limit            # 无限复活默认 2 分钟
    sc = serve.Room("t", "t", 10, win_mode="score")
    assert sc.limit == 300, sc.limit            # 积分赛默认 5 分钟
    both = serve.Room("t", "t", 10, win_mode="score", respawn=True)
    assert both.limit == 300, both.limit        # 积分赛优先（并列取更长）
    info = r.info()
    assert info["winMode"] == "score" and info["limit"] == 60 and info["respawn"] is True, info
    snap = r.snapshot(serve.now_ms())
    assert snap["winMode"] == "score" and snap["limit"] == 60 and snap["respawn"] is True, snap
    assert isinstance(snap.get("remain"), int) and snap["remain"] > 0, snap.get("remain")
    # 回合时钟随 new_round 重置
    old = r.round_started
    r.round_ids = set()
    r.new_round()
    assert r.round_started >= old, (r.round_started, old)
    print("battle config OK: mode=%s limit=%d respawn=%s" % (
        r.win_mode, r.limit, r.respawn))


def test_time_limit_ends_by_score():
    now = serve.now_ms()
    r = fresh(10, limit=10)
    r.round_started = now - 11000
    p1 = mk(r, 1, "A", [(4, 4), (3, 4), (2, 4)], (1, 0))
    p2 = mk(r, 2, "B", [(7, 7), (6, 7), (5, 7)], (1, 0))
    p1["score"], p2["score"] = 50, 30
    r.check_win(now)
    assert r.win_pending == {"winner": 1}, r.win_pending
    assert p1["score"] == 50 + serve.WIN_SCORE, p1["score"]
    print("time limit OK: winner=higher score")


def test_time_limit_tie_is_draw():
    now = serve.now_ms()
    r = fresh(10, limit=10)
    r.round_started = now - 11000
    p1 = mk(r, 1, "A", [(4, 4), (3, 4), (2, 4)], (1, 0))
    p2 = mk(r, 2, "B", [(7, 7), (6, 7), (5, 7)], (1, 0))
    p1["score"] = p2["score"] = 40
    r.check_win(now)
    assert r.win_pending == {"winner": None}, r.win_pending
    assert p1["score"] == 40 and p2["score"] == 40, "平局不加分"
    print("time limit tie -> draw OK")


def test_score_mode_ends_only_when_all_dead():
    now = serve.now_ms()
    r = fresh(10, win_mode="score")
    assert r.limit == 300, r.limit
    p1 = mk(r, 1, "A", [(4, 4), (3, 4), (2, 4)], (1, 0))
    p2 = mk(r, 2, "B", [(7, 7), (6, 7), (5, 7)], (1, 0))
    p1["score"], p2["score"] = 10, 20
    p1["alive"] = False
    r.check_win(now)
    assert r.win_pending is None, "积分赛一人死不算结束"
    p2["alive"] = False
    r.check_win(now)
    assert r.win_pending == {"winner": 2}, r.win_pending
    assert p2["score"] == 20 + serve.WIN_SCORE, p2["score"]
    print("score mode OK: ends when all dead, higher score wins")


def test_last_mode_survival_win_still_works():
    now = serve.now_ms()
    r = fresh(10)
    p1 = mk(r, 1, "A", [(4, 4), (3, 4), (2, 4)], (1, 0))
    p2 = mk(r, 2, "B", [(7, 7), (6, 7), (5, 7)], (1, 0))
    p2["alive"] = False
    r.check_win(now)
    assert r.win_pending == {"winner": 1}, r.win_pending
    assert p1["score"] == serve.WIN_SCORE, p1["score"]
    # 全灭 → 平局
    r.win_pending = None
    p1["alive"] = False
    r.check_win(now)
    assert r.win_pending == {"winner": None}, r.win_pending
    print("last mode survival/draw OK")


def test_respawn_never_ends_by_elimination():
    now = serve.now_ms()
    r = fresh(10, respawn=True)
    assert r.limit == 120, r.limit
    p1 = mk(r, 1, "A", [(4, 4), (3, 4), (2, 4)], (1, 0))
    p2 = mk(r, 2, "B", [(7, 7), (6, 7), (5, 7)], (1, 0))
    p1["alive"] = False
    r.check_win(now)
    assert r.win_pending is None, "复活模式一人死不结算"
    p2["alive"] = False
    r.check_win(now)
    assert r.win_pending is None, "复活模式全死也不结算（等复活/限时）"
    print("respawn no-elimination OK")


def test_respawn_after_delay():
    now = serve.now_ms()
    r = fresh(10, respawn=True)
    p1 = mk(r, 1, "A", [(5, 5), (4, 5), (3, 5)], (1, 0))
    p2 = mk(r, 2, "B", [(0, 2), (1, 2), (2, 2)], (-1, 0))
    r.step(0.05, now)
    assert not p2["alive"] and p2.get("cause") == "wall", p2.get("cause")
    assert p2.get("died_at") == now, p2.get("died_at")
    r.step_wrapper(0.05, now + serve.RESPAWN_MS - 500)
    assert not p2["alive"], "未到复活时间不该复活"
    r.step_wrapper(0.05, now + serve.RESPAWN_MS + 100)
    assert p2["alive"], "到点应复活"
    assert len(p2["cells"]) == 3, p2["cells"]
    assert r.win_pending is None, "复活模式不因存活人数结算"
    print("respawn delay OK")


# ================= 批2：偏转道具 / 护盾地形偏转 / 大招 =================

def test_deflect_item_wall_bends():
    r = fresh(10)
    p = mk(r, 1, "A", [(0, 5), (1, 5), (2, 5)], (-1, 0))
    now = serve.now_ms()
    p["eff"] = {"deflect": now + 9999}
    r.step(0.05, now)
    assert p["alive"], "deflect 撞边界应折返不死"
    hx, hy = p["cells"][0]
    assert hx == 0 and hy in (4, 6), p["cells"]
    assert p["dir"] in ((0, -1), (0, 1)), p["dir"]
    print("deflect wall bend OK ->", p["cells"][0], p["dir"])


def test_deflect_item_rock_still_kills():
    r = fresh(10)
    r.rocks = [(0, 5)]
    p = mk(r, 1, "A", [(1, 5), (2, 5), (3, 5)], (-1, 0))
    now = serve.now_ms()
    p["eff"] = {"deflect": now + 9999}
    r.step(0.05, now)
    assert not p["alive"] and p["cause"] == "rock", p.get("cause")
    print("deflect rock still dies OK")


def test_shield_bends_wall():
    r = fresh(10)
    p = mk(r, 1, "A", [(0, 5), (1, 5), (2, 5)], (-1, 0))
    now = serve.now_ms()
    p["eff"] = {"shield": now + 9999}
    r.step(0.05, now)
    assert p["alive"], "护盾撞边界应折返不死"
    hx, hy = p["cells"][0]
    assert hx == 0 and hy in (4, 6), p["cells"]
    print("shield wall bend OK ->", p["cells"][0])


def test_shield_bends_rock():
    r = fresh(10)
    r.rocks = [(0, 5)]
    p = mk(r, 1, "A", [(1, 5), (2, 5), (3, 5)], (-1, 0))
    now = serve.now_ms()
    p["eff"] = {"shield": now + 9999}
    r.step(0.05, now)
    assert p["alive"], "护盾撞岩石应折返不死"
    hx, hy = p["cells"][0]
    assert (hx, hy) in ((1, 4), (1, 6)), p["cells"]
    print("shield rock bend OK ->", p["cells"][0])


def test_shield_bends_self():
    r = fresh(10)
    p = mk(r, 1, "A", [(1, 5), (1, 6), (2, 6), (2, 5), (3, 5), (3, 6)], (0, 1))
    now = serve.now_ms()
    p["eff"] = {"shield": now + 9999}
    r.step(0.05, now)
    assert p["alive"], "护盾撞自己应折返不死"
    assert p["cells"][0] == (0, 5), p["cells"]
    print("shield self bend OK ->", p["cells"][0])


def test_ult_fruit_and_star_charge():
    r = fresh(10)
    p = mk(r, 1, "A", [(2, 5), (1, 5), (0, 5)], (1, 0))
    now = serve.now_ms()
    r.foods = [{"id": 1, "x": 3, "y": 5, "score": 10, "color": "#fff"}]
    r.step(0.05, now)
    assert p["ult"] == serve.ULT_FRUIT, p.get("ult")
    # 批23 P7：吃果触发的 place_food() 随机补粒，恰落蛇头下一步 (4,5) 时
    # 第二步与 bonus 一步双吃 → 35≠25（约 1.5% flaky）。夹具把补粒钉到远格消除随机
    r.foods = [{"id": 2, "x": 0, "y": 9, "score": 10, "color": "#fff"}]
    r.bonus = {"id": 9, "x": 4, "y": 5, "score": 50, "born": now}
    r.step(0.05, now + 200)
    assert p["ult"] == serve.ULT_FRUIT + serve.ULT_STAR, p.get("ult")
    print("ult fruit/star charge OK")


def test_ult_kill_charge():
    r = fresh(10)
    p = mk(r, 1, "A", [(3, 5), (2, 5), (1, 5)], (1, 0))
    q = mk(r, 2, "B", [(6, 5), (4, 5)], (1, 0))
    now = serve.now_ms()
    r.step(0.05, now)
    assert not q["alive"] and q["cause"] == "bite", q.get("cause")
    assert p["ult"] == serve.ULT_KILL, p.get("ult")
    print("ult kill charge OK")


def test_ult_requires_full_charge():
    r = fresh(10)
    p = mk(r, 1, "A", [(5, 5), (4, 5), (3, 5)], (1, 0))
    now = serve.now_ms()
    p["ult"] = 99
    assert not r.try_ult(p, now)
    assert not r.projectiles
    assert p["ult"] == 99, p["ult"]
    print("ult needs 100 OK")


def test_ult_fires_barrage_and_resets():
    r = fresh(10)
    p = mk(r, 1, "A", [(5, 5), (4, 5), (3, 5)], (1, 0))
    now = serve.now_ms()
    p["ult"] = serve.ULT_MAX
    assert r.try_ult(p, now)
    assert p["ult"] == 0, p["ult"]
    assert len(r.projectiles) == 8, len(r.projectiles)
    dirs = {(pr["dx"], pr["dy"]) for pr in r.projectiles}
    assert len(dirs) == 8, dirs
    p["ult"] = serve.ULT_MAX
    assert not r.try_ult(p, now + 1000), "冷却内不应连发"
    assert len(r.projectiles) == 8
    assert r.try_ult(p, now + serve.ULT_COOL + 1), "冷却过后应可再发"
    print("ult barrage + cooldown OK")


def test_ult_reset_on_spawn():
    r = fresh(10)
    p = mk(r, 1, "A", [(5, 5), (4, 5), (3, 5)], (1, 0))
    p["ult"] = 60
    p["alive"] = False
    r.spawn_player(p)
    assert p["ult"] == 0, p["ult"]
    print("ult reset on spawn OK")


# ================= 批3：传送门按地图扩容 + 出口朝向 + 资源有效期 =================

def test_portal_pairs_scale_with_map():
    for size, cells_want in ((12, 2), (16, 2), (24, 4), (32, 4), (48, 6), (64, 8), (96, 8)):
        r = fresh(size, theme_fixed="default")
        r.build_terrain()
        assert len(r.portals) == cells_want, (size, r.portals)
    print("portal pairs scale OK: 12/16->1对 24/32->2对 48->3对 64/96->4对")


def test_portal_map_multi_pairs():
    r = fresh(32, theme_fixed="default")
    r.build_terrain()
    m = r.portal_map()
    assert len(m) == len(r.portals) and len(m) == 4, (len(m), r.portals)
    for i in range(0, len(r.portals), 2):
        a, b = r.portals[i], r.portals[i + 1]
        assert m[a] == b and m[b] == a, (a, b, m)
    print("portal map multi-pair OK ->", m)


def test_portal_exit_faces_open_direction():
    r = fresh(10)                      # 实际 12x12
    r.portals = [(3, 5), (7, 5)]
    p = mk(r, 1, "A", [(2, 5), (1, 5), (0, 5)], (1, 0))
    now = serve.now_ms()
    r.step(0.05, now)
    assert p["cells"][0] == (7, 5), p["cells"]
    # 出口 (7,5) 处最开阔方向是向下（6 格：y6..y11），不该保留原朝向
    assert p["dir"] == (0, 1), p["dir"]
    print("portal exit faces open OK ->", p["dir"])


def test_resource_life_scales_with_map():
    r12, r24, r48 = fresh(12), fresh(24), fresh(48)
    assert r12.life_mult() == 1.0 and r24.life_mult() == 1.0, (r12.life_mult(), r24.life_mult())
    assert r48.life_mult() == 4.0, r48.life_mult()
    assert r12.item_life() == serve.ITEM_LIFE
    assert r48.item_life() == serve.ITEM_LIFE * 4
    assert r48.bonus_life() == serve.BONUS_LIFE * 4
    # 到期行为：48x48 道具/星星在 4 倍时长才过期
    now = serve.now_ms()
    r48.win_pending = "t"              # 关掉随机刷新，避免断言被新刷道具干扰
    r48.items = [{"id": 1, "type": "shield", "x": 0, "y": 0, "born": now}]
    r48.step_wrapper(0.05, now + serve.ITEM_LIFE + 100)
    assert r48.items, "1 倍时长不该过期"
    r48.step_wrapper(0.05, now + serve.ITEM_LIFE * 4 + 100)
    assert not r48.items, "4 倍时长应过期"
    r48.bonus = {"id": 1, "x": 1, "y": 1, "score": 50, "born": now}
    r48.step_wrapper(0.05, now + serve.BONUS_LIFE + 100)
    assert r48.bonus, "星星 1 倍时长不该过期"
    r48.step_wrapper(0.05, now + serve.BONUS_LIFE * 4 + 100)
    assert not r48.bonus, "星星 4 倍时长应过期"
    print("resource life scale OK: 48x48 -> 4x")


def test_day_theme_in_pool():
    # 批7 #4：新增白天主题进主题池（TDD 红：当前 THEMES 无 day）
    assert "day" in serve.THEMES, serve.THEMES
    cfg = serve.THEME_CFG["day"]
    assert isinstance(cfg["rock"], (int, float)) and isinstance(cfg["portal"], bool)
    assert "walls" in cfg and "accent" in cfg
    r = serve.Room("dayr", "白天", 24, theme_fixed="day")
    assert r.theme == "day"
    r.build_terrain()      # THEME_CFG[theme] 必须齐备，否则 KeyError
    assert r.eff_rock() >= 0
    assert isinstance(r.eff_portal(), bool)
    # create 消息校验 theme in THEMES（L1540）随元组自动放行 day
    r2 = serve.Room("dayr2", "随机", 24, theme_fixed=None)
    r2.theme = serve.random.choice(serve.THEMES)   # 随机池含 day
    r2.build_terrain()
    print("day theme pool OK:", r.theme, cfg)


# ================= 批14 碰撞卡叠修复 =================
def test_spawn_fallback_safe_point_avoids_food():
    # 批14①：280 次随机全失败 → 兜底线性扫描安全点（不压食物/地形/蛇）。
    # 旧版兜底在中央硬铺 3 格零检查 → 可能压 food，且同格同向死锁源
    from unittest import mock
    r = fresh(12)
    r.foods = [{"id": 1, "x": 6, "y": 6, "score": 10, "color": "#fff"}]
    s = S()
    p = serve.make_player(1, s, "A", 0)
    r.players[1] = p
    calls = [0]

    def fake_randint(a, b):
        calls[0] += 1
        return 6 if calls[0] % 2 == 1 else 6      # 恒采样食物格 (6,6)

    with mock.patch.object(serve.random, "randint", side_effect=fake_randint):
        r.spawn_player(p)
    assert p["alive"] and len(p["cells"]) == 3, p["cells"]
    assert (6, 6) not in p["cells"], ("兜底 spawn 压住了食物", p["cells"])
    for cx, cy in p["cells"]:
        assert 0 <= cx < r.cols and 0 <= cy < r.rows, p["cells"]
    print("spawn fallback avoids food OK ->", p["cells"])


def test_spawn_main_path_avoids_food():
    # 批14①主路径：落食物格的采样应被拒（旧版 _solid 不含 food → 直接压上）。
    # 主循环不提前退出（280 次采满），用 cycle 供值；食物 (2,2) 开阔度 9 高于
    # 填充格 (6,6) 的 6，旧版会把它选成 best（RED），新版恒拒之
    from itertools import cycle
    from unittest import mock
    r = fresh(12)
    r.foods = [{"id": 1, "x": 2, "y": 2, "score": 10, "color": "#fff"}]
    s = S()
    p = serve.make_player(1, s, "A", 0)
    r.players[1] = p
    seq = cycle([6, 6, 2, 2])                    # 交替采样填充格 (6,6) 与食物格 (2,2)
    with mock.patch.object(serve.random, "randint", side_effect=lambda a, b: next(seq)):
        r.spawn_player(p)
    assert (2, 2) not in p["cells"], ("主路径 spawn 压住了食物", p["cells"])
    assert len(p["cells"]) == 3, p["cells"]
    print("spawn main path avoids food OK ->", p["cells"])


def test_protected_body_entry_skips_move():
    # 批14②：进入受保护（出生无敌/护盾）蛇身体 → 本帧不移动（旧版直接插头穿身）
    r = fresh(12)
    now = serve.now_ms()
    q = mk(r, 2, "Q", [(8, 10), (7, 10), (6, 10)], (1, 0))
    q["inv"] = now + 99999                       # 保护期
    q["last_move"] = now                         # q 本帧不动（非 due）
    p = mk(r, 1, "P", [(5, 10), (5, 11), (5, 12)], (1, 0))  # 头将进入 (6,10)
    r.step(0.05, now)
    assert p["cells"][0] == (5, 10), ("受保护身体不可进入，p 不该插头", p["cells"])
    assert len(q["cells"]) == 3 and q["cells"][0] == (8, 10), q["cells"]
    assert p["alive"] and q["alive"]
    print("protected body entry skip OK")


def test_head_on_single_force_per_tick():
    # 批14③：三方同格争顶每蛇只右转一次（旧版同帧双重右转 → 反向 → 咬颈自杀）
    r = fresh(12)
    a = mk(r, 1, "A", [(5, 5), (5, 4), (5, 3)], (1, 0))     # tent (6,5)
    b = mk(r, 2, "B", [(6, 4), (6, 3), (6, 2)], (0, 1))     # tent (6,5)
    c = mk(r, 3, "C", [(6, 6), (6, 7), (6, 8)], (0, -1))    # tent (6,5)
    r.step(0.05, serve.now_ms())
    # 每蛇恰好右转一次：(1,0)→(0,1)、(0,1)→(-1,0)、(0,-1)→(1,0)
    # 旧版双转的 a 会变 (-1,0)、b 变 (0,-1)、c 变 (0,1)
    assert a["dir"] == (0, 1), ("a 应只右转一次", a["dir"])
    assert b["dir"] == (-1, 0), ("b 应只右转一次", b["dir"])
    assert c["dir"] == (1, 0), ("c 应只右转一次", c["dir"])
    assert a["alive"] and b["alive"] and c["alive"]
    print("head_on single force per tick OK")


def test_stuck_head_on_tiebreak():
    # 批14④破僵局：同格同向卡死 ≥2 tick → 按 id 序留一死一（旧版永久右转死锁）
    r = fresh(12)
    a = mk(r, "a1", "A", [(4, 4), (4, 3), (4, 2)], (1, 0))
    b = mk(r, "a2", "B", [(4, 4), (4, 3), (4, 2)], (1, 0))   # 同格同向
    now = serve.now_ms()
    r.step(0.05, now)
    assert a["alive"] and b["alive"], "第1帧仅冻结不应判死"
    r.step(0.05, now + 200)
    dead = [p for p in (a, b) if not p["alive"]]
    assert len(dead) == 1, ("第2帧应破僵局判死一个", a["alive"], b["alive"])
    assert dead[0]["cause"] == "stuck", dead[0]["cause"]
    assert dead[0]["id"] == "a2", ("按 id 序大者出局", dead[0]["id"])
    print("stuck head_on tiebreak OK")


def test_off_at_not_headblock():
    # 批14⑤：挂起蛇头不再顶住活蛇（旧版 force_right 冻结 → 静止幽灵障碍）
    r = fresh(12)
    now = serve.now_ms()
    q = mk(r, 2, "Q", [(8, 8), (8, 9), (8, 10)], (1, 0))
    q["off_at"] = now - 1000                     # 挂起中（未超 RESUME_MS）
    p = mk(r, 1, "P", [(7, 8), (7, 7), (7, 6)], (1, 0))      # tent = q 头 (8,8)
    r.step(0.05, now)
    assert p["cells"][0] == (8, 8), ("挂起蛇头不该顶住活蛇", p["cells"])
    assert q["cells"][0] == (8, 8) and len(q["cells"]) == 3, q["cells"]
    assert p["alive"]
    print("off_at not headblock OK")


def test_off_at_not_bitten():
    # 批14⑤：挂起蛇不可被咬（旧版活蛇路过即可截断静止 10s 的幽灵蛇）
    r = fresh(12)
    now = serve.now_ms()
    q = mk(r, 2, "Q", [(10, 9), (9, 9), (8, 9)], (1, 0))
    q["off_at"] = now - 1000
    p = mk(r, 1, "P", [(8, 8), (8, 7), (8, 6)], (0, 1))      # tent = q 身体 (8,9)
    r.step(0.05, now)
    assert len(q["cells"]) == 3, ("挂起蛇不该被咬", q["cells"])
    assert p["cells"][0] == (8, 9), p["cells"]
    print("off_at not bitten OK")


def test_resume_position_conflict_fresh_spawn():
    # 批14⑤：挂起期原位被活蛇穿入 → resume 不得原地恢复（重叠死锁），改重生
    r = fresh(12)
    now = serve.now_ms()
    q = mk(r, 2, "Q", [(8, 8), (8, 9), (8, 10)], (1, 0))
    q["off_at"] = now - 1000
    p = mk(r, 1, "P", [(8, 8), (7, 8), (6, 8)], (1, 0))      # 已穿进 q 原位
    s2 = S()
    r.resume(s2, q)
    assert "off_at" not in q, "resume 应清除挂起标记"
    assert q["session"] is s2
    overlap = set(q["cells"]) & set(p["cells"])
    assert not overlap, ("位置冲突应重生避开", q["cells"], p["cells"])
    assert len(q["cells"]) == 3, q["cells"]
    print("resume conflict fresh spawn OK ->", q["cells"])


def test_portal_exit_blocked_skip_move():
    # 批14⑥：传送出口被占 → 本帧原地不动（旧版直接传进蛇身：叠体+咬）
    r = fresh(12)
    r.portals = [(5, 5), (9, 9)]
    now = serve.now_ms()
    q = mk(r, 2, "Q", [(9, 10), (9, 9), (9, 8)], (1, 0))
    q["last_move"] = now                         # q 静止，出口持续被占
    p = mk(r, 1, "P", [(4, 5), (3, 5), (2, 5)], (1, 0))      # 进 (5,5) 门 → 出 (9,9)
    r.step(0.05, now)
    assert p["cells"][0] == (4, 5), ("出口被占不该传送", p["cells"])
    assert len(p["cells"]) == 3
    assert p["dir"] == (1, 0), ("原地等待不应改向", p["dir"])
    assert len(q["cells"]) == 3, ("不该被传送进来的蛇咬", q["cells"])
    print("portal exit blocked skip OK")


def test_portal_exit_prefers_arrival_dir_on_tie():
    # 批14⑥复现：出口朝向打平时旧版固定偏东（(1,0) 首位 + 严格大于），应延续
    # 进入方向。大图受 cap=24 制约东西向无法同时打满，故用岩石人工造三向
    # 打平：东/南/西 o 各=1（1 格空后是岩石），北=0（紧贴岩石）
    r = fresh(24)
    r.portals = [(5, 5), (10, 10)]
    r.rocks = [(12, 10), (10, 12), (8, 10), (10, 9)]
    p = mk(r, 1, "A", [(5, 4), (5, 3), (5, 2)], (0, 1))     # 向南进 (5,5) 门 → 出 (10,10)
    r.step(0.05, serve.now_ms())
    assert p["cells"][0] == (10, 10), p["cells"]
    assert p["dir"] == (0, 1), ("打平应延续进入方向而非固定偏东", p["dir"])
    print("portal arrival dir tie OK ->", p["dir"])


def test_bot_liveness_no_permanent_head_clash():
    # 批14活性压力：7 bot 18x18 图 30s 模拟，任何同格对头 ≤2 tick（≥3=疑似死锁）
    serve.random.seed(42)
    r = fresh(16, bots=7)
    r.place_food()
    now = serve.now_ms()
    clash_streak = {}
    eaten_seen = 0
    for _ in range(600):                         # 600 × 50ms = 30s
        now += 50
        r.step(0.05, now)
        if r.win_pending:                        # 模拟 game_loop：结算即重开
            r.win_pending = None
            r.new_round()
        eaten_seen = max(eaten_seen, r.fruits_eaten)
        heads = {}
        for p in r.players.values():
            if p["alive"] and p["cells"]:
                heads.setdefault(p["cells"][0], []).append(p["id"])
        for cell, ids in heads.items():
            if len(ids) > 1:
                clash_streak[cell] = clash_streak.get(cell, 0) + 1
                assert clash_streak[cell] <= 2, (
                    "同格对头超过 2 tick（疑似永久死锁）", cell, ids, clash_streak[cell])
            else:
                clash_streak.pop(cell, None)
    assert eaten_seen > 0, "30s 内 bot 一条水果都没吃到（疑似寻路失效）"
    print("bot liveness OK: eaten_seen=%d" % eaten_seen)


def test_place_food_avoids_sealed_pocket():
    """批15①：封死的角落口袋不放水果（静态可达性过滤 + reach_set）"""
    from unittest import mock
    r = fresh(12)
    r.rocks = [(10, 11), (11, 10)]          # 封死角落 (11,11)：另两侧是出界
    mk(r, 'p1', 'P', [(6, 6), (5, 6), (4, 6)], (1, 0))
    # choice 恒取末位：free_list 按 x 主序，末位自由格正是口袋 (11,11) → 旧码必落口袋
    with mock.patch.object(serve.random, "choice", side_effect=lambda seq: seq[-1]):
        r.place_food()
    assert r.foods
    assert (r.foods[0]['x'], r.foods[0]['y']) != (11, 11), (
        "水果放进封死口袋", r.foods)
    reach = r.reach_set()
    assert (11, 11) not in reach and (6, 6) in reach, reach


def test_place_food_reach_time_budget():
    """批15①：96×96 大图可达集 BFS 计时 + 缓存命中 + build_terrain 失效"""
    import time as _time
    r = fresh(96)
    r.walls = [(x, 48) for x in range(0, 96, 2)]                 # 虚线墙（留缝仍连通）
    r.rocks = [(x, y) for x in range(0, 96, 4) for y in range(0, 96, 8)]
    mk(r, 'p1', 'P', [(1, 1), (1, 2), (1, 3)], (0, -1))
    t0 = _time.perf_counter()
    reach = r.reach_set()
    ms = (_time.perf_counter() - t0) * 1000.0
    assert ms < 50, "可达集 BFS 超时: %.2fms" % ms
    assert (1, 1) in reach
    assert r.reach_set() is reach, "缓存未命中（应返回同一对象）"
    r.build_terrain()
    assert r._reach is None, "build_terrain 未使可达集缓存失效"
    print("reach budget OK: %.2fms" % ms)


def test_bot_reaches_food_around_wall():
    """批24 O5：贪心打分死循环——石列挡道（缺口在远端 (6,8)）时水果 (7,5) 可达
    却 8 步环原地绕圈（确定性复现 test-results/repro_circling.py case_a）。
    距离场路径修复后须在限步内吃到（此前必红：环内永远吃不到）"""
    r = fresh(10)
    r.rocks = [(6, y) for y in range(0, 8)]                 # 石列 x=6，仅留 y=8/9 缺口
    r.foods = [{'id': 1, 'x': 7, 'y': 5, 'score': 15, 'color': '#fff'}]
    p = mk(r, 'b1', 'AI', [(5, 5), (5, 6), (5, 7)], (0, -1))
    p['bot'] = True
    p['score'] = 0
    now = 1_000_000
    for _ in range(400):                                   # 20s 步进（tick 150ms）
        r.step(50, now)
        now += 50
        if p['score'] > 0:
            break
    assert not p['alive'] or p['score'] > 0, \
        'AI 应绕石列缺口吃到水果（复现：8 步环原地绕圈永远吃不到）'
    assert p['score'] > 0, '400 步内未吃到——绕圈死循环复现'


def test_bot_reaches_food_in_pocket():
    """批24 O5：U 型袋开口朝下、水果在袋内（case_c 复现 16 步环）——
    须绕袋口进入吃到，不得在袋外顶壁绕环"""
    r = fresh(12)
    r.rocks = [(x, 4) for x in range(3, 9)] + [(3, y) for y in range(5, 9)] \
        + [(9, y) for y in range(5, 9)]                    # 开口 y=9
    r.foods = [{'id': 1, 'x': 6, 'y': 6, 'score': 15, 'color': '#fff'}]
    p = mk(r, 'b1', 'AI', [(6, 2), (6, 1), (6, 0)], (0, 1))
    p['bot'] = True
    p['score'] = 0
    now = 1_000_000
    for _ in range(500):
        r.step(50, now)
        now += 50
        if p['score'] > 0:
            break
    assert p['score'] > 0, '500 步内未吃到——袋外绕环复现'


def test_bot_turns_toward_target_when_blocked():
    """批15②：直达方向被挡，选与目标方向最接近的开放方向（不再按 DIRS4 定序反向偏航）"""
    r = fresh(24)
    r.rocks = [(11, y) for y in range(5, 16)]    # 东面石列挡直达
    r.foods = [{'id': 1, 'x': 20, 'y': 10, 'score': 15, 'color': '#fff'}]
    p = mk(r, 'b1', 'AI', [(10, 10), (10, 11), (10, 12)], (0, -1))
    r._bot_think(p)
    # 目标在东（首选方向 E）：E 被石列挡、S 是反向 → 候选只剩 W/N，dist 与 openv 打平(11/9)。
    # 新码按对齐度选 N（=当前方向，不写队列）；旧码 DIRS4 稳定序 W 先 → 反向偏航写 [(-1,0)]
    assert p['queue'] == [], p['queue']


def test_bot_picks_nearest_target():
    """批15③：food/bonus 按 min(dist) 选目标（不再星星无条件压过近处水果）"""
    r = fresh(24)
    r.foods = [{'id': 1, 'x': 10, 'y': 13, 'score': 15, 'color': '#fff'}]   # 距 3（南）
    r.bonus = {'id': 1, 'x': 19, 'y': 10, 'score': 50, 'born': 0}         # 距 9（东）
    p = mk(r, 'b1', 'AI', [(10, 10), (9, 10), (8, 10)], (1, 0))
    r._bot_think(p)
    # 新码就近选水果 → 转南 [(0,1)]；旧码 bonus 无条件优先 → 直行不写队列
    assert p['queue'] == [(0, 1)], p['queue']


# ---- 批17 H：碰外墙偏转房间选项（walldeflect）----
def test_walldeflect_room_bounces_at_wall():
    """墙折返房：蛇头撞边界墙 → 垂直折返不死（复用 deflect 道具语义）"""
    r = fresh(10, walldeflect=True)
    p = mk(r, 1, 'a', [(0, 5), (1, 5), (2, 5)], (-1, 0))
    r.step(50, 1000)
    assert p['alive'], 'walldeflect 房撞墙应折返不死'
    assert p['dir'] in ((0, 1), (0, -1)), f'应垂直折返，实际 {p["dir"]}'
    assert p['cells'][0] != (-1, 5)


def test_walldeflect_room_no_escape_dies():
    """墙折返房：垂直两向全被占（岩石+界外）→ 无路可折照死 cause='wall'"""
    r = fresh(10, walldeflect=True)
    r.rocks = [(0, 1)]
    p = mk(r, 1, 'a', [(0, 0), (1, 0), (2, 0)], (-1, 0))
    r.step(50, 1000)
    assert not p['alive'] and p.get('cause') == 'wall'


def test_walldeflect_room_rock_front_still_dies():
    """墙折返房：正面撞岩石照死（折返只对边界墙，cause='rock'）"""
    r = fresh(10, walldeflect=True)
    r.rocks = [(3, 2)]
    p = mk(r, 1, 'a', [(2, 2), (2, 3), (2, 4)], (1, 0))
    r.step(50, 1000)
    assert not p['alive'] and p.get('cause') == 'rock'


def test_walldeflect_bite_min_len_still_dies():
    """墙折返房：2 格蛇被咬照常整条淘汰（折返不救被咬）"""
    r = fresh(10, walldeflect=True)
    q = mk(r, 2, 'q', [(5, 5), (5, 4)], (0, 1))
    q['last_move'] = 1000                      # 受害者本帧不 due
    p = mk(r, 1, 'p', [(5, 3), (5, 2), (5, 1)], (0, 1))
    r.step(50, 1000)
    assert not q['alive'] and q.get('cause') == 'bite'
    assert p['alive']


# ---- 批18 E：房间参数编辑（roomcfg，live 生效） ----
def _cfg_sess(sid='s1', user=None, room=None):
    """会话桩：捕获下发消息，带 sid/user/room"""
    import asyncio  # noqa: F401（保持与 handle_msg 异步调用一致的导入习惯）

    class CapWS:
        def __init__(self):
            self.sent = []

        async def send(self, x):
            import json
            self.sent.append(json.loads(x) if isinstance(x, str) else x)
    s = S()
    s.ws = CapWS()
    s.sid = sid
    s.user = user
    s.room = room
    s.msgs = 0
    return s


def _cfg_room(sess):
    """建一个归属 sess 的测试房"""
    r = serve.Room('rc', 'rc', 10, bots=0)
    r.owner = sess.sid
    r.owner_user = sess.user
    serve.rooms['rc'] = r
    return r


def test_roomcfg_stranger_allowed():
    """批24：房间设置完全放开——非创建者改设置也生效（原批18 拒绝语义已废弃）"""
    import asyncio
    r = _cfg_room(_cfg_sess(sid='s1', user='u1'))
    other = _cfg_sess(sid='s2', user='u2', room=r)
    asyncio.run(serve.handle_msg(other, {'t': 'roomcfg', 'room': 'rc',
                                         'winMode': 'score', 'wd': True}))
    assert not any(x.get('t') == 'error' for x in other.ws.sent)
    assert r.win_mode == 'score' and r.walldeflect is True
    assert any(x.get('t') == 'cfgapplied' for x in other.ws.sent)
    del serve.rooms['rc']


def test_roomcfg_creator_edits_live_without_restart():
    """创建者（sid 在线）live 改参数：字段生效、不重开局（round/身体不变）"""
    import asyncio
    s = _cfg_sess(sid='s1')
    r = _cfg_room(s)
    s.room = r
    p = mk(r, 1, 'a', [(3, 3), (4, 3), (5, 3)], (1, 0))
    cells_before = list(p['cells'])
    before_round = r.round_no
    asyncio.run(serve.handle_msg(s, {'t': 'roomcfg', 'room': 'rc',
                                     'winMode': 'score', 'limit': 90,
                                     'respawn': True, 'wd': True}))
    assert (r.win_mode, r.limit, r.respawn, r.walldeflect) == ('score', 90, True, True)
    assert r.round_no == before_round and p['cells'] == cells_before
    assert any(x.get('t') == 'cfgapplied' for x in s.ws.sent)
    del serve.rooms['rc']


def test_roomcfg_account_owner_survives_reconnect():
    """批18 必改7：账号归属跨会话有效（owner==sid 重连即失效的替代）；
    批24 后身份门槛整体放开，u2 亦可改——保留本例验证账号轨道仍生效不回归"""
    import asyncio
    r = serve.Room('rc', 'rc', 10)
    r.owner = 'oldsid'          # 旧会话已断开
    r.owner_user = 'u1'
    serve.rooms['rc'] = r
    s2 = _cfg_sess(sid='newsid', user='u1')
    asyncio.run(serve.handle_msg(s2, {'t': 'roomcfg', 'room': 'rc', 'bots': 2}))
    assert r.bots == 2
    assert any(x.get('t') == 'cfgapplied' for x in s2.ws.sent)
    s3 = _cfg_sess(sid='x', user='u2')
    asyncio.run(serve.handle_msg(s3, {'t': 'roomcfg', 'room': 'rc', 'bots': 5}))
    assert r.bots == 5   # 批24：陌生人同样放行（原断言 2 = 拒绝语义已废弃）
    del serve.rooms['rc']


def test_created_issues_owner_tok():
    """批23 P6：建房回执下发一次性 owner 凭据（匿名恢复用），且不进房间列表"""
    import asyncio
    orig = dict(serve.rooms)
    try:
        s = _cfg_sess(sid='ot1')
        s.ip = '9.9.9.9'
        asyncio.run(serve.handle_msg(s, {'t': 'create', 'name': '凭据房'}))
        cd = [x for x in s.ws.sent if x.get('t') == 'created']
        assert cd and cd[0].get('tok'), s.ws.sent          # 回执必须带 tok
        rid = cd[0]['room']
        r = serve.rooms[rid]
        assert r.owner_tok == cd[0]['tok'] and len(r.owner_tok) >= 32
        assert 'owner_tok' not in r.info() and 'tok' not in r.info()  # 列表不泄露
    finally:
        serve.rooms.clear()
        serve.rooms.update(orig)


def test_roomcfg_open_to_anyone():
    """批24：房间设置完全放开——任何会话（匿名、无凭据、非创建者）可改任何房间；
    口令格式等业务校验保留（非法口令仍整条原子拒绝）"""
    import asyncio
    r = serve.Room('rc', 'rc', 10)
    r.owner = 'oldsid'
    r.owner_user = None
    r.owner_tok = 'a' * 32
    serve.rooms['rc'] = r
    s3 = _cfg_sess(sid='x', user=None)          # 陌生人（无凭据、非创建者）→ 放行
    asyncio.run(serve.handle_msg(s3, {'t': 'roomcfg', 'room': 'rc', 'bots': 5}))
    assert r.bots == 5
    assert any(x.get('t') == 'cfgapplied' for x in s3.ws.sent)
    s4 = _cfg_sess(sid='y', user=None)          # 另一陌生人 → 同样放行
    asyncio.run(serve.handle_msg(s4, {'t': 'roomcfg', 'room': 'rc', 'bots': 7}))
    assert r.bots == 7
    # 业务校验不随身份门槛一起放开：非法口令仍原子拒绝
    asyncio.run(serve.handle_msg(s4, {'t': 'roomcfg', 'room': 'rc',
                                      'pass': 'weak', 'bots': 3}))
    assert r.bots == 7 and r.passw is None
    assert any(x.get('t') == 'error' for x in s4.ws.sent)
    del serve.rooms['rc']


def test_persist_open_to_anyone():
    """批24：persist 同步放开——陌生人（无凭据、非创建者）也可保存常驻"""
    import asyncio
    old_save = serve.save_persist_rooms
    serve.save_persist_rooms = lambda *a, **k: True   # 不落真实 data/ 文件
    r = serve.Room('rc', 'rc', 10)
    r.owner = 'oldsid'
    r.owner_user = None
    r.owner_tok = 'c' * 32
    serve.rooms['rc'] = r
    try:
        s = _cfg_sess(sid='newsid', user=None)
        asyncio.run(serve.handle_msg(s, {'t': 'persist', 'room': 'rc'}))
        assert r.persist is True, '任何人可保存房间'
        assert not any(x.get('t') == 'error' for x in s.ws.sent)
    finally:
        serve.save_persist_rooms = old_save
        del serve.rooms['rc']


def test_room_live_and_ai_freeze():
    """批24 O3：纯 AI 房自动停止——room_live 三态判定 + game 循环对纯 AI 房
    跳过 step/broadcast（last_step 仍刷新），有真人/观战照常推进"""
    import asyncio

    # 1) room_live 三态
    r = serve.Room('fr', 'fr', 10)
    r.set_bots(3)
    assert all(q.get('bot') for q in r.players.values())
    assert serve.room_live(r) is False, '纯 AI 房应判定不 live'

    class _FakeSess:
        pass
    r.subs.add(_FakeSess())          # 有人类观战 → live
    assert serve.room_live(r) is True, '真人观战应判定 live'
    r.subs.clear()

    class _FakeWs:
        async def send(self, *_a, **_k):
            pass
    class _HumanSess:
        user = None
        ws = _FakeWs()
    r.players[1] = serve.make_player(1, _HumanSess(), '真人', 0, bot=False)
    assert serve.room_live(r) is True, '有真人玩家应判定 live'

    # 2) game 循环：纯 AI 房不 step、有真人房 step（step_wrapper 打桩计数）
    old_rooms = serve.rooms
    try:
        calls = []

        async def _no_bc():
            return None
        r2 = serve.Room('fr2', 'fr2', 10)
        r2.set_bots(2)
        r2.step_wrapper = lambda dt, n: calls.append(('ai', dt))
        r2.broadcast = _no_bc
        r.players[1]['session'] = _HumanSess()
        r.step_wrapper = lambda dt, n: calls.append(('human', dt))
        r.broadcast = _no_bc
        serve.rooms = {'fr2': r2, 'fr': r}
        t0 = time.monotonic()
        asyncio.run(serve.game_cycle(t0, 123456))
        assert not any(c[0] == 'ai' for c in calls), '纯 AI 房应跳过 step'
        assert any(c[0] == 'human' for c in calls), '有真人房应照常 step'
        assert r2.last_step is not None, '冻结房 last_step 仍须刷新（防恢复大 dt 跳跃）'
        # 3) 纯 AI 房（唯一成员）也冻结
        serve.rooms = {'fr2': r2}
        asyncio.run(serve.game_cycle(t0 + 1, 123457))
        assert len([c for c in calls if c[0] == 'ai']) == 0
    finally:
        serve.rooms = old_rooms


def test_delroom_open_to_anyone():
    """批24 O2：删除房间完全放开——陌生人可删任意空闲房；
    有人/观战中的房拒；默认房拒；persist 房删后写盘不再复活"""
    import asyncio
    old_save = serve.save_persist_rooms
    saved = []
    serve.save_persist_rooms = lambda *a, **k: (saved.append(1), True)[1]   # 不落真实文件
    try:
        # 1) 空闲自定义房：任何人删 → 成功回执 + 房间消失
        r = serve.Room('dz', 'dz', 10)
        serve.rooms['dz'] = r
        s = _cfg_sess(sid='stranger', user=None)
        asyncio.run(serve.handle_msg(s, {'t': 'delroom', 'room': 'dz'}))
        assert 'dz' not in serve.rooms, '空闲房应被删除'
        assert any(x.get('t') == 'delok' and x.get('room') == 'dz' for x in s.ws.sent)
        assert not any(x.get('t') == 'error' for x in s.ws.sent)

        # 2) 有人的房：拒，房间仍在
        r2 = serve.Room('busy', 'busy', 10)
        r2.players[1] = {'alive': True, 'bot': False}
        serve.rooms['busy'] = r2
        s2 = _cfg_sess(sid='stranger2', user=None)
        asyncio.run(serve.handle_msg(s2, {'t': 'delroom', 'room': 'busy'}))
        assert 'busy' in serve.rooms, '有人房不能删'
        assert any(x.get('t') == 'error' for x in s2.ws.sent)

        # 3) 默认房：拒（哪怕空闲）
        if serve.DEFAULT_ROOM_IDS:
            did = next(iter(serve.DEFAULT_ROOM_IDS))
            s3 = _cfg_sess(sid='stranger3', user=None)
            asyncio.run(serve.handle_msg(s3, {'t': 'delroom', 'room': did}))
            assert did in serve.rooms, '默认房不能删'
            assert any(x.get('t') == 'error' for x in s3.ws.sent)

        # 4) persist 房：删成功 + 落盘 + dump 不再含
        r4 = serve.Room('ps', 'ps', 10)
        r4.persist = True
        serve.rooms['ps'] = r4
        s4 = _cfg_sess(sid='stranger4', user=None)
        asyncio.run(serve.handle_msg(s4, {'t': 'delroom', 'room': 'ps'}))
        assert 'ps' not in serve.rooms, '常驻房可删'
        assert saved, '删 persist 房必须重写 persist 文件'
        assert all(d.get('id') != 'ps' for d in serve.persist_rooms_dump())

        # 5) 纯 AI 房（仅 bot 占位、无人类玩家/观战）→ 可删（批24 O4 修复：
        #    原实现把 bot 也算「有人」导致 AI 房删不掉）
        r5 = serve.Room('ai', 'ai', 10)
        r5.set_bots(3)
        assert r5.players and all(q.get('bot') for q in r5.players.values())
        serve.rooms['ai'] = r5
        s5 = _cfg_sess(sid='stranger5', user=None)
        asyncio.run(serve.handle_msg(s5, {'t': 'delroom', 'room': 'ai'}))
        assert 'ai' not in serve.rooms, '纯 AI 房应可删除'
        assert any(x.get('t') == 'delok' for x in s5.ws.sent)

        # 6) AI 房但有真人观战 → 仍拒
        r6 = serve.Room('aiw', 'aiw', 10)
        r6.set_bots(2)
        class _FakeWs:
            sent = []
            async def send(self, *_a, **_k):
                pass
        class _FakeSess:
            ws = _FakeWs()
        r6.subs.add(_FakeSess())
        serve.rooms['aiw'] = r6
        s6 = _cfg_sess(sid='stranger6', user=None)
        asyncio.run(serve.handle_msg(s6, {'t': 'delroom', 'room': 'aiw'}))
        assert 'aiw' in serve.rooms, '有真人观战的 AI 房不能删'
        assert any(x.get('t') == 'error' for x in s6.ws.sent)
    finally:
        serve.save_persist_rooms = old_save
        for k in ('dz', 'busy', 'ps', 'ai', 'aiw'):
            serve.rooms.pop(k, None)


def test_roomcfg_bots_live_add_remove():
    """批18 必改7：bots live 增减（set_bots 显式补生成/摘除）"""
    import asyncio
    s = _cfg_sess(sid='s1')
    r = _cfg_room(s)
    s.room = r
    asyncio.run(serve.handle_msg(s, {'t': 'roomcfg', 'room': 'rc', 'bots': 3}))
    n = sum(1 for p in r.players.values() if p.get('bot'))
    assert (r.bots, n) == (3, 3)
    asyncio.run(serve.handle_msg(s, {'t': 'roomcfg', 'room': 'rc', 'bots': 1}))
    n = sum(1 for p in r.players.values() if p.get('bot'))
    assert (r.bots, n) == (1, 1)
    del serve.rooms['rc']


def test_roomcfg_limit_fallback_mirror():
    """批18：live 改动保持 __init__ 不变量——score/respawn 房 limit=0 时兜底限时"""
    import asyncio
    s = _cfg_sess(sid='s1')
    r = _cfg_room(s)
    asyncio.run(serve.handle_msg(s, {'t': 'roomcfg', 'room': 'rc', 'winMode': 'score'}))
    assert r.limit == 300
    asyncio.run(serve.handle_msg(s, {'t': 'roomcfg', 'room': 'rc',
                                     'winMode': 'last', 'limit': 0, 'respawn': True}))
    assert r.limit == 120
    del serve.rooms['rc']


def test_roomcfg_extended_fields_unified():
    """批23 N2：roomcfg 与创建面字段统一——name/theme/rock/portal 即时存（地形类下局
    生效）、size 走 pending_size 下局应用、pass 可改可清；非法口令整条消息原子拒绝"""
    import asyncio
    s = _cfg_sess(sid='s1')
    r = _cfg_room(s)
    s.room = r
    asyncio.run(serve.handle_msg(s, {'t': 'roomcfg', 'room': 'rc',
                                     'name': '新名字', 'theme': 'day',
                                     'rock': 1.8, 'portal': False,
                                     'size': 40}))
    assert r.name == '新名字'
    assert r.theme_fixed == 'day'
    assert r.rock_mult == 1.8 and r.portal_on is False
    assert getattr(r, 'pending_size', None) == 40
    assert r.size == 12 and r.cols == 12      # Room('rc','rc',10) 被 MAP_MIN 夹到 12；当前局不动
    info = r.info()
    assert info['rockCustom'] == 1.8 and info['portalCustom'] is False  # 编辑面回填用
    assert info['pendingSize'] == 40
    r.new_round()
    assert (r.size, r.cols, r.rows) == (40, 40, 40)   # 新局应用 pending 尺寸
    # 非法主题回退为「随机」（与创建面 ""=随机 同语义）
    asyncio.run(serve.handle_msg(s, {'t': 'roomcfg', 'room': 'rc', 'theme': 'bogus'}))
    assert r.theme_fixed is None
    # 口令：非法（弱口令）→ 整条拒绝，同消息的 name 不被应用
    asyncio.run(serve.handle_msg(s, {'t': 'roomcfg', 'room': 'rc',
                                     'name': '不该改', 'pass': 'abc123'}))
    assert any(x.get('t') == 'error' for x in s.ws.sent)
    assert r.name == '新名字' and r.passw is None
    asyncio.run(serve.handle_msg(s, {'t': 'roomcfg', 'room': 'rc', 'pass': 'Kx9m2Q'}))
    assert r.passw == 'Kx9m2Q'
    asyncio.run(serve.handle_msg(s, {'t': 'roomcfg', 'room': 'rc', 'clearPass': True}))
    assert r.passw is None
    # 空 name = 保持原名（不允许置空）
    asyncio.run(serve.handle_msg(s, {'t': 'roomcfg', 'room': 'rc', 'name': ''}))
    assert r.name == '新名字'
    del serve.rooms['rc']


def test_respawn_msg_gated_by_room_mode_and_delay():
    """批22 H4：手动复活仅限复活房且须过 RESPAWN_MS——死斗/积分房裸发复活必须被拒
    （漏洞已本地复现：respawn=False 房死亡后裸发 {t:'respawn'} 立即复活）"""
    import asyncio
    # 非复活房：死亡后发 respawn → 仍然死亡
    r = fresh(10)
    s = _cfg_sess(sid='s1', room=r)
    p = mk(r, 1, 'Me', [(4, 4), (4, 5)], (1, 0))
    s.pid = 1
    p['user'] = None
    p['alive'] = False
    p['died_at'] = serve.now_ms()
    asyncio.run(serve.handle_msg(s, {'t': 'respawn'}))
    assert p['alive'] is False, '非复活房不允许手动复活（H4）'
    # 复活房：延迟未到 → 仍拒；到点 → 放行
    r2 = fresh(10, respawn=True)
    s2 = _cfg_sess(sid='s2', room=r2)
    p2 = mk(r2, 1, 'Me2', [(4, 4), (4, 5)], (1, 0))
    s2.pid = 1
    p2['user'] = None
    p2['alive'] = False
    p2['died_at'] = serve.now_ms()
    asyncio.run(serve.handle_msg(s2, {'t': 'respawn'}))
    assert p2['alive'] is False, 'RESPAWN_MS 延迟未到不允许复活'
    p2['died_at'] = serve.now_ms() - serve.RESPAWN_MS - 10
    asyncio.run(serve.handle_msg(s2, {'t': 'respawn'}))
    assert p2['alive'] is True, '复活房到点后应正常复活'
    print('respawn msg gated OK')


def test_create_rate_limited_and_room_cap():
    """批22 H3：单会话/同 IP 窗内成功建房配额 + 全局房间上限
    （达上限先淘汰最老空置非持久房，无可淘汰则拒）"""
    import asyncio
    orig = dict(serve.rooms)
    old_cmax, old_ipmax = serve.CREATE_MAX, serve.CREATE_IP_MAX
    old_rmax, old_evict = serve.ROOM_MAX, serve.ROOM_EVICT_AGE
    old_cwin, old_ipwin = serve.CREATE_WIN, getattr(serve, 'CREATE_IP_WIN', 300)
    s = _cfg_sess(sid='cs1')
    s.ip = '5.5.5.5'
    try:
        serve.CREATE_MAX = 2
        n0 = len(serve.rooms)
        asyncio.run(serve.handle_msg(s, {'t': 'create', 'name': 'c1'}))
        asyncio.run(serve.handle_msg(s, {'t': 'create', 'name': 'c2'}))
        asyncio.run(serve.handle_msg(s, {'t': 'create', 'name': 'c3'}))
        errs = [x for x in s.ws.sent if x.get('t') == 'error']
        assert len(errs) == 1 and '频繁' in errs[0].get('err', ''), (len(errs), errs)
        assert len(serve.rooms) == n0 + 2, len(serve.rooms)
        # 同 IP 换连接绕过会话配额 → IP 配额兜底（清计数后重新验证 IP 上限）
        serve.CREATE_MAX = 10 ** 9
        serve.create_ip.clear()
        serve.CREATE_IP_MAX = 1
        s2 = _cfg_sess(sid='cs2')
        s2.ip = '5.5.5.5'
        asyncio.run(serve.handle_msg(s2, {'t': 'create', 'name': 'c4'}))
        asyncio.run(serve.handle_msg(s2, {'t': 'create', 'name': 'c5'}))
        errs = [x for x in s2.ws.sent if x.get('t') == 'error']
        assert len(errs) == 1 and '频繁' in errs[0].get('err', ''), (len(errs), errs)
        # 全局上限：先造一个足够老的空置房 → 淘汰它并建成
        serve.CREATE_IP_MAX = 10 ** 9
        victim = serve.Room('vv', 'vv', 10)
        victim.created = serve.time.time() - serve.ROOM_EVICT_AGE - 10
        serve.rooms['vv'] = victim
        serve.ROOM_MAX = len(serve.rooms)
        s3 = _cfg_sess(sid='cs3')
        s3.ip = '6.6.6.6'
        asyncio.run(serve.handle_msg(s3, {'t': 'create', 'name': 'c6'}))
        assert 'vv' not in serve.rooms, '达上限应淘汰最老空置房'
        assert any(x.get('t') == 'created' for x in s3.ws.sent), s3.ws.sent
        # 再达上限且无可淘汰（新建的都太年轻）→ 拒
        serve.ROOM_MAX = len(serve.rooms)
        s4 = _cfg_sess(sid='cs4')
        s4.ip = '7.7.7.7'
        asyncio.run(serve.handle_msg(s4, {'t': 'create', 'name': 'c7'}))
        errs = [x for x in s4.ws.sent if x.get('t') == 'error']
        assert errs and '上限' in errs[0].get('err', ''), errs
    finally:
        serve.rooms.clear()
        serve.rooms.update(orig)
        serve.create_ip.clear()
        serve.CREATE_MAX, serve.CREATE_IP_MAX = old_cmax, old_ipmax
        serve.ROOM_MAX, serve.ROOM_EVICT_AGE = old_rmax, old_evict
        serve.CREATE_WIN, serve.CREATE_IP_WIN = old_cwin, old_ipwin
    print('create rate+cap OK')


def test_register_rate_limited():
    """批22 M2：同 IP 窗内成功注册超限被拒（防批量注册刷 store.json），异 IP/窗过期复位"""
    import tempfile, shutil, asyncio, json as _json
    from pathlib import Path
    d = Path(tempfile.mkdtemp(prefix='snake-reglim-'))
    old_store, old_usage = serve.store, serve.usage
    old_reg = dict(serve.reg_ok)
    old_max, old_win = serve.REG_MAX, serve.REG_WIN
    try:
        serve.store = serve.Store(d / 'store.json')
        serve.usage = serve.Usage(d / 'usage.log', d / 'usage.json')
        serve.reg_ok.clear()
        serve.REG_MAX = 2

        async def run():
            s = _cfg_sess(sid='r1', user=None)
            s.ip = '8.8.8.8'
            for i in range(2):
                await serve.handle_msg(s, {'t': 'register', 'user': 'u%d' % i, 'pass': '246810'})
                assert s.ws.sent[-1]['ok'] is True, s.ws.sent[-1]
            await serve.handle_msg(s, {'t': 'register', 'user': 'u9', 'pass': '246810'})
            assert s.ws.sent[-1]['ok'] is False and '频繁' in s.ws.sent[-1].get('err', ''), \
                s.ws.sent[-1]
            # 别的 IP 不受影响
            s2 = _cfg_sess(sid='r2', user=None)
            s2.ip = '4.4.4.4'
            await serve.handle_msg(s2, {'t': 'register', 'user': 'u8', 'pass': '246810'})
            assert s2.ws.sent[-1]['ok'] is True, s2.ws.sent[-1]
            # 窗口过期 → 复位
            serve.REG_WIN = 0
            await serve.handle_msg(s, {'t': 'register', 'user': 'u7', 'pass': '246810'})
            assert s.ws.sent[-1]['ok'] is True, s.ws.sent[-1]
        asyncio.run(run())
        lines = [_json.loads(x) for x in (d / 'usage.log').read_text('utf-8').splitlines()]
        assert any(x.get('err') == '限速拒绝' for x in lines), lines
    finally:
        serve.store, serve.usage = old_store, old_usage
        serve.reg_ok.clear()
        serve.reg_ok.update(old_reg)
        serve.REG_MAX, serve.REG_WIN = old_max, old_win
        shutil.rmtree(d, ignore_errors=True)
    print('register rate OK')


def test_room_pass_bruteforce_throttle():
    """批22 M5：同 (ip, 房) 口令错试超限 → 含正确口令一并拒（同登录防爆破语义），窗过期复位"""
    import asyncio
    r = fresh(10)
    r.passw = 'xy1234'
    serve.rooms['t'] = r
    old_max, old_win = serve.PASS_FAIL_MAX, serve.PASS_FAIL_WIN
    old_fails = dict(serve.pass_fails)
    try:
        serve.pass_fails.clear()
        serve.PASS_FAIL_MAX = 3
        s = _cfg_sess(sid='pw5')
        s.ip = '3.3.3.3'
        s.joins = 0
        for i in range(3):
            asyncio.run(serve.handle_msg(
                s, {'t': 'join', 'room': 't', 'name': 'x', 'pass': 'wrong%d' % i}))
            assert s.ws.sent[-1].get('err') == '房间口令错误', s.ws.sent[-1]
        asyncio.run(serve.handle_msg(s, {'t': 'join', 'room': 't', 'name': 'x', 'pass': 'xy1234'}))
        assert s.ws.sent[-1].get('t') == 'error' and '频繁' in s.ws.sent[-1].get('err', ''), \
            s.ws.sent[-1]
        # 窗过期 → 正确口令放行
        serve.PASS_FAIL_WIN = 0
        asyncio.run(serve.handle_msg(s, {'t': 'join', 'room': 't', 'name': 'x', 'pass': 'xy1234'}))
        assert s.ws.sent[-1].get('t') == 'room-ok', s.ws.sent[-1]
    finally:
        serve.PASS_FAIL_MAX, serve.PASS_FAIL_WIN = old_max, old_win
        serve.pass_fails.clear()
        serve.pass_fails.update(old_fails)
        serve.rooms.pop('t', None)
    print('room pass throttle OK')


def test_anonymous_resume_ip_bound():
    """批22 M1：匿名挂起蛇只认同 IP（防任意新加入者 10s 窗内抢蛇）；
    登录账户凭账号跨 IP 恢复不变；off_ip 由 leave_room(hard=False) 落标"""
    r = fresh(12)
    p = mk(r, 1, 'Anon', [(4, 4), (4, 5)], (1, 0))
    p['user'] = None
    p['off_at'] = serve.now_ms()
    p['off_ip'] = '1.1.1.1'
    assert r.resumable(None, '1.1.1.1') is p       # 同 IP 恢复
    assert r.resumable(None, '2.2.2.2') is None     # 异 IP 拒绝抢蛇
    p['off_ip'] = None                              # 无记录（旧数据/测试桩）→ 保持旧行为放行
    assert r.resumable(None, '2.2.2.2') is p
    # 登录账户跨 IP 照常恢复（凭据=密码/token，不依赖 IP）
    p2 = mk(r, 2, 'U', [(6, 6)], (1, 0))
    p2['user'] = 'u1'
    p2['off_at'] = serve.now_ms()
    p2['off_ip'] = '1.1.1.1'
    assert r.resumable('u1', '9.9.9.9') is p2
    # leave_room(hard=False) 挂起时记录原 IP
    r2 = fresh(12)
    q = mk(r2, 1, 'M2', [(5, 5)], (1, 0))
    q['user'] = None
    mk(r2, 2, 'B', [(6, 6)], (1, 0))                # 房里还有别的真人 → 走挂起分支
    s = S()
    s.ip = '7.7.7.7'
    s.room = r2
    s.pid = 1
    serve.leave_room(s, hard=False)
    assert q.get('off_at') and q.get('off_ip') == '7.7.7.7', \
        (q.get('off_at'), q.get('off_ip'))
    print('anonymous resume ip bound OK')


def test_token_ttl_expired():
    """批22 M3：令牌过 TOKEN_TTL 作废（回'登录已过期'并从字典清除）；有效令牌成功鉴权滑动续期"""
    import tempfile, shutil, asyncio
    from pathlib import Path
    d = Path(tempfile.mkdtemp(prefix='snake-tokttl-'))
    old_store, old_usage = serve.store, serve.usage
    old_tokens, old_ttl = serve.tokens, serve.TOKEN_TTL
    old_at = getattr(serve, 'token_at', None)
    try:
        serve.store = serve.Store(d / 'store.json')
        serve.usage = serve.Usage(d / 'usage.log', d / 'usage.json')
        serve.tokens = {}
        serve.token_at = {}
        ok, err = serve.store.register('alice', '246810')
        assert ok, err
        now = serve.time.time()
        serve.tokens['deadbeef'] = 'alice'
        serve.token_at['deadbeef'] = now - serve.TOKEN_TTL - 10    # 已过期
        serve.tokens['fresh01'] = 'alice'
        serve.token_at['fresh01'] = now - 60                        # 有效
        t_base = serve.time.time()

        async def run():
            s = _cfg_sess(sid='t1', user=None)
            s.ip = '2.2.2.2'
            await serve.handle_msg(s, {'t': 'authtoken', 'token': 'deadbeef'})
            assert s.ws.sent[-1]['ok'] is False and '过期' in s.ws.sent[-1].get('err', ''), \
                s.ws.sent[-1]
            assert 'deadbeef' not in serve.tokens, '过期令牌应作废'
            await serve.handle_msg(s, {'t': 'authtoken', 'token': 'fresh01'})
            assert s.ws.sent[-1]['ok'] is True, s.ws.sent[-1]
        asyncio.run(run())
        # 成功鉴权 → 滑动续期（在鉴权时刻之后刷新，不能早于基准时刻）
        assert serve.token_at['fresh01'] >= t_base, serve.token_at['fresh01']
    finally:
        serve.store, serve.usage = old_store, old_usage
        serve.tokens = old_tokens
        serve.TOKEN_TTL = old_ttl
        if old_at is None:
            try:
                del serve.token_at
            except AttributeError:
                pass
        else:
            serve.token_at = old_at
        shutil.rmtree(d, ignore_errors=True)
    print('token ttl OK')


def test_room_info_humans_vs_bots():
    """批23 N1：房间列表人数区分真人与 AI（humans 字段，players 语义不变）"""
    r = fresh(12, bots=3)
    i = r.info()
    assert i["players"] == 3            # players 仍含 AI（既有语义不变）
    assert i["humans"] == 0             # 新字段：真人数
    mk(r, 7, "甲", [(2, 2), (2, 3)], (1, 0))
    i = r.info()
    assert i["players"] == 4
    assert i["humans"] == 1
    assert i["players"] - i["humans"] == 3   # AI 数可由差值推出
    print('info humans OK')


def test_win_pending_timeout_forces_new_round():
    """批23 P5②：结算滞留超时强制开新局——在场但不点准备的挂机者/晚加入者不再无限冻结世界。
    win_at 在 win_pending 的首个 step 帧锚定；非 dict 哨兵（如 "t"）不参与超时逻辑"""
    r = fresh(12)
    mk(r, 1, 'A', [(4, 4), (4, 5)], (1, 0))
    mk(r, 2, 'B', [(8, 8), (8, 7)], (1, 0))
    r.win_pending = {"winner": 1}
    now = serve.now_ms()
    r.step(0.05, now)                                   # 首帧锚定滞留起点
    r.step(0.05, now + serve.WIN_PENDING_MAX_MS - 1)
    assert r.win_pending is not None, "窗口内不得强制重开"
    n0 = r.round_no
    r.step(0.05, now + serve.WIN_PENDING_MAX_MS)
    assert r.win_pending is None, "滞留超时应强制开新局"
    assert r.round_no == n0 + 1
    # 既有测试用的非 dict 哨兵不参与超时（防御未来把强制重开写进无差别分支）
    r.win_pending = "t"
    r.step(0.05, now + 10 * serve.WIN_PENDING_MAX_MS)
    assert r.win_pending == "t", "非 dict 哨兵不得被强制重开"
    print('win pending timeout OK')


def test_late_join_starts_round_when_all_ready():
    """批23 P5①：全员就绪（挂起者视为 ready）时，晚加入者的 join 必须立即触发
    maybe_start_round——否则所有人只能等一个永远不会来的 ready 消息（复现脚本 v2 的第二层根因）"""
    import asyncio
    r = fresh(12)
    a = mk(r, 1, 'A', [(4, 4), (4, 5)], (1, 0))
    b = mk(r, 2, 'B', [(8, 8), (8, 7)], (1, 0))
    a['off_at'] = serve.now_ms()                        # 原班人马挂起 → 视为 ready
    b['off_at'] = serve.now_ms()
    a['off_ip'] = b['off_ip'] = '9.9.9.9'               # 防 join 走 resume 分支抢蛇（异 IP 拒）
    r.win_pending = {"winner": 1}
    serve.rooms['t'] = r
    s = _cfg_sess(sid='p5j')
    s.ip = '1.1.1.1'
    s.joins = 0
    try:
        asyncio.run(serve.handle_msg(s, {'t': 'join', 'room': 't', 'name': 'Late'}))
        assert s.ws.sent[-1].get('t') == 'room-ok', s.ws.sent[-1]
        assert r.win_pending is None, "全员就绪时 join 应立即开新局"
    finally:
        serve.rooms.pop('t', None)
    print('late join start OK')


for fn in [test_ghost_wrap, test_wall_death_without_ghost, test_portal,
           test_item_pickup, test_speed_effect, test_shield_immunity,
           test_shield_item_immunity, test_bite_truncates_not_kills,
           test_bite_min_len_eliminates, test_bite_immunity,
           test_bullet_shortens_snake, test_bullet_ignores_owner_and_immunity,
           test_spawn_avoids_snakes_and_faces_open, test_food_has_unique_id,
            test_multi_foods_target_and_unique, test_multi_foods_eat_replenishes, test_multi_foods_bot_target_nearest,
            test_store_gacha_fields,
            test_gacha_probability_boundaries, test_gacha_pity90_hard, test_gacha_pity10_four,
            test_gacha_pity_order, test_gacha_5050_guarantee, test_gacha_ten_pull_pity_carry,
            test_pool_pick_uniform, test_gacha_dist_smoke,
           test_room_custom_config, test_speed_change_instant,
           test_free_cells_big_map, test_usage_log,
           test_auth_login_throttle,
           test_combo_increments_and_expires, test_combo_multiplier_tiers,
           test_double_item_doubles_score, test_magnet_pulls_food,
           test_rage_halves_cooldown_and_speeds_bullet,
           test_battle_mode_config, test_time_limit_ends_by_score,
           test_time_limit_tie_is_draw, test_score_mode_ends_only_when_all_dead,
           test_last_mode_survival_win_still_works,
           test_respawn_never_ends_by_elimination, test_respawn_after_delay,
           test_deflect_item_wall_bends, test_deflect_item_rock_still_kills,
           test_shield_bends_wall, test_shield_bends_rock, test_shield_bends_self,
           test_ult_fruit_and_star_charge, test_ult_kill_charge,
           test_ult_requires_full_charge, test_ult_fires_barrage_and_resets,
           test_ult_reset_on_spawn,
           test_portal_pairs_scale_with_map, test_portal_map_multi_pairs,
           test_portal_exit_faces_open_direction,
           test_resource_life_scales_with_map,
           test_bots_config_and_info, test_bots_spawned_on_create,
           test_bot_turns_toward_food, test_bot_avoids_wall_death,
           test_single_player_wins_vs_bots, test_bots_ready_for_round_start,
           test_bots_removed_when_last_human_leaves,
           test_chat_appends_and_limits, test_chat_throttle,
           test_offline_kept_within_grace, test_offline_dropped_after_grace,
           test_offline_clears_bots_when_last_human_gone,
           test_resumable_matching, test_resume_keeps_snake_state,
           test_disconnect_single_room_drops_immediately,
           test_disconnect_multi_room_suspends,
            test_offline_snake_frozen_until_resume,
            test_valid_room_pass, test_room_pass_field_not_leaked,
            test_gc_holds_new_rooms_24h, test_gc_keeps_persist_rooms,
            test_persist_roundtrip, test_day_theme_in_pool,
            test_snapshot_carries_queue_len,
            test_broadcast_send_fail_suspends_for_resume,
            test_spawn_fallback_safe_point_avoids_food,
            test_spawn_main_path_avoids_food,
            test_protected_body_entry_skips_move,
            test_head_on_single_force_per_tick,
            test_stuck_head_on_tiebreak,
            test_off_at_not_headblock,
            test_off_at_not_bitten,
            test_resume_position_conflict_fresh_spawn,
            test_portal_exit_blocked_skip_move,
            test_portal_exit_prefers_arrival_dir_on_tie,
            test_bot_liveness_no_permanent_head_clash,
            test_place_food_avoids_sealed_pocket,
            test_place_food_reach_time_budget,
            test_bot_turns_toward_target_when_blocked,
            test_bot_reaches_food_around_wall,
            test_bot_reaches_food_in_pocket,
            test_bot_picks_nearest_target,
            test_walldeflect_room_bounces_at_wall,
            test_walldeflect_room_no_escape_dies,
            test_walldeflect_room_rock_front_still_dies,
            test_walldeflect_bite_min_len_still_dies,
            test_roomcfg_stranger_allowed,
            test_roomcfg_creator_edits_live_without_restart,
            test_roomcfg_account_owner_survives_reconnect,
            test_created_issues_owner_tok,
            test_roomcfg_open_to_anyone,
            test_persist_open_to_anyone,
            test_delroom_open_to_anyone,
            test_room_live_and_ai_freeze,
            test_roomcfg_bots_live_add_remove,
            test_roomcfg_limit_fallback_mirror,
            test_roomcfg_extended_fields_unified,
            test_respawn_msg_gated_by_room_mode_and_delay,
            test_create_rate_limited_and_room_cap,
            test_register_rate_limited,
            test_room_pass_bruteforce_throttle,
            test_anonymous_resume_ip_bound,
            test_token_ttl_expired,
            test_room_info_humans_vs_bots,
            test_win_pending_timeout_forces_new_round,
            test_late_join_starts_round_when_all_ready]:
    fn()
print("ALL GAME UNIT TESTS PASSED")
