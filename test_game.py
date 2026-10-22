import contextlib
import io
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
    r.hmap = {}      # 批32：测试默认纯平地（用例按需注入 r.hmap=...）
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
            "score", 120, True, None)               # 批37 项5：加载后不留明文
        assert r.has_pass and r.check_pass("ab12cd") and not r.check_pass("xx")   # 哈希校验仍有效
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


def test_spawn_cost_logged():
    # 批26⑥：spawn 耗时测量——stdout 日志行 [spawn] + last_spawn_ms 供线上分布取证
    r = fresh(24)
    p = serve.make_player(1, S(), "A", 0)
    r.players[1] = p
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r.spawn_player(p)
    out = buf.getvalue()
    assert "[spawn]" in out and " ms " in out, out
    assert "grid=24x24" in out, out
    assert r.last_spawn_ms >= 0.0, r.last_spawn_ms
    assert p["alive"] and len(p["cells"]) == 3


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


def test_gacha_cap_flag():
    """批27 分镜：捕获明光标识 cap——赢 50/50 的 5★ 才带；大保底/歪/低星不带"""
    import asyncio
    # 纯函数：保底驱动 5★ + 掷骰赢 → cap=True（捕获明光）
    capwin = serve.gacha_roll(_FakeRng([0.3]), False, 89, 0)
    assert capwin["star"] == 5 and capwin["up"] is True and capwin.get("cap") is True, capwin
    # 大保底（上发歪过，非掷骰路径）→ 非捕获
    gtd = serve.gacha_roll(_FakeRng([]), True, 89, 0)
    assert gtd["up"] is True and not gtd.get("cap"), gtd
    # 掷骰歪了 → 非捕获
    loss = serve.gacha_roll(_FakeRng([0.6]), False, 89, 0)
    assert loss["up"] is False and not loss.get("cap"), loss
    # 4★ 不带
    four = serve.gacha_roll(_FakeRng([0.5]), False, 0, 9)
    assert four["star"] == 4 and not four.get("cap"), four
    # 集成：gachares item 仅捕获 roll 带 cap 键；无 cap 字段的 roll（既有打桩形状）不带键
    d, old = _gacha_setup()
    old_roll, old_pick = serve.gacha_roll, serve.pool_pick

    def fake_cap(rng, lose5050, pity5, pity4):
        return {"star": 5, "up": True, "pity5": 0, "pity4": 0,
                "lose5050": False, "cap": True}
    try:
        serve.store.add_stardust("alice", 320)
        serve.pool_pick = lambda rng, star, up: 15
        serve.gacha_roll = fake_cap
        s = _cfg_sess(sid="g6", user="alice")
        s.ip = "3.3.3.8"
        asyncio.run(serve.handle_msg(s, {"t": "gacha", "n": 1}))
        last = s.ws.sent[-1]
        assert last.get("t") == "gachares" and last["items"][0].get("cap") is True, last
        _stub_roll(5, True)                          # 既有桩形状：无 cap 字段（内部已赋值）
        s2 = _cfg_sess(sid="g7", user="alice")
        s2.ip = "3.3.3.9"
        asyncio.run(serve.handle_msg(s2, {"t": "gacha", "n": 1}))
        last2 = s2.ws.sent[-1]
        assert last2.get("t") == "gachares" and "cap" not in last2["items"][0], last2
    finally:
        serve.gacha_roll, serve.pool_pick = old_roll, old_pick
        _gacha_teardown(d, old)
    print("gacha cap flag OK")


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


# ---- 批25 Task3：gacha/gachainfo 消息 + 星尘结算 + 皮肤鉴权 ----
def _gacha_setup(user='alice'):
    """临时账号库：注册 user，返回 (d, old_store) 供还原"""
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp(prefix='snake-gacha-'))
    old = serve.store
    serve.store = serve.Store(d / 'store.json')
    ok, err = serve.store.register(user, '246810')
    assert ok, err
    return d, old


def _gacha_teardown(d, old):
    import shutil
    serve.store = old
    shutil.rmtree(d, ignore_errors=True)


def _stub_roll(star=3, up=False):
    """打桩 gacha_roll：固定星级（消除 1.6% 随机对断言的干扰）"""
    old = serve.gacha_roll

    def fake(rng, lose5050, pity5, pity4):
        return {'star': star, 'up': up,
                'pity5': 0 if star == 5 else pity5 + 1,
                'pity4': 0 if star >= 4 else pity4 + 1,
                'lose5050': lose5050}
    serve.gacha_roll = fake
    return old


def _stub_pool(skin_id):
    """打桩 pool_pick：恒返回指定皮肤"""
    old = serve.pool_pick
    serve.pool_pick = lambda rng, star, up: skin_id
    return old


def test_gacha_invalid_n_rejected():
    """批25 T3：n 不在 (1,10) 白名单 → error 零副作用（n=-1 加币攻击等）。
    终审 MAJOR-1：float/bool/None 也必须拒（True==1、1.0 in (1,10) 相等性穿透）"""
    import asyncio
    d, old = _gacha_setup()
    try:
        s = _cfg_sess(sid='g1', user='alice')
        s.ip = '3.3.3.3'
        serve.store.add_stardust('alice', 1600)   # 余额足够，暴露「扣款后异常」穿透
        for n in (0, -1, 5, 'abc', 10 ** 9, 1.0, 10.0, True, None):
            asyncio.run(serve.handle_msg(s, {'t': 'gacha', 'n': n}))
            last = s.ws.sent[-1]
            assert last.get('t') == 'error', (n, last)
        u = serve.store.users['alice']
        assert u['stardust'] == 1600, u['stardust']   # 一笔都没扣
        assert u['skins'] == []
        assert u['gacha_p5'] == 0 and u['gacha_p4'] == 0 and u['gacha_lose'] is False
    finally:
        _gacha_teardown(d, old)
    print('gacha invalid n OK')


def test_gacha_requires_login():
    """批25 T3：未登录抽卡 → error 含「登录」"""
    import asyncio
    d, old = _gacha_setup()
    try:
        s = _cfg_sess(sid='g2', user=None)
        s.ip = '3.3.3.4'
        asyncio.run(serve.handle_msg(s, {'t': 'gacha', 'n': 1}))
        last = s.ws.sent[-1]
        assert last.get('t') == 'error' and '登录' in last.get('err', ''), last
    finally:
        _gacha_teardown(d, old)
    print('gacha requires login OK')


def test_gacha_identity_mismatch_rejected():
    """批25 T3：入局玩家与登录账号不一致（中途换号）→ error 防跨账号搬资产"""
    import asyncio
    d, old = _gacha_setup()
    try:
        ok, err = serve.store.register('bob', '135792')
        assert ok, err
        serve.store.add_stardust('alice', 1600)
        serve.store.add_stardust('bob', 1600)
        r = fresh(10)
        p = mk(r, 1, 'A', [(5, 5), (4, 5)], (1, 0))
        p['user'] = 'alice'
        s = _cfg_sess(sid='g3', user='bob', room=r)
        s.ip = '3.3.3.5'
        s.pid = 1
        asyncio.run(serve.handle_msg(s, {'t': 'gacha', 'n': 1}))
        last = s.ws.sent[-1]
        assert last.get('t') == 'error', last
        assert serve.store.stardust('alice') == 1600, 'alice 余额不动'
        assert serve.store.stardust('bob') == 1600, 'bob 余额不动'
    finally:
        _gacha_teardown(d, old)
    print('gacha identity mismatch OK')


def test_gachainfo_identity_mismatch_zero():
    """批25 终审 MINOR-2：入局玩家与登录账号不一致 → gachainfo 回零值占位
    （不混出 bob 总账 + alice 玩家 dust 的错配数据）"""
    import asyncio
    d, old = _gacha_setup()
    try:
        ok, err = serve.store.register('bob', '135792')
        assert ok, err
        serve.store.add_stardust('bob', 1600)     # bob 有钱——错配时会泄进回包
        r = fresh(10)
        p = mk(r, 1, 'A', [(5, 5), (4, 5)], (1, 0))
        p['user'] = 'alice'
        p['dust'] = 77                            # 玩家 dust 挂在 alice 玩家上
        s = _cfg_sess(sid='g3b', user='bob', room=r)
        s.ip = '3.3.3.15'
        s.pid = 1
        asyncio.run(serve.handle_msg(s, {'t': 'gachainfo'}))
        last = s.ws.sent[-1]
        assert last.get('t') == 'gachainfo', last
        assert last['balance'] == 0 and last['dust'] == 0 and last['skins'] == [], last
        assert last['p5'] == 0 and last['p4'] == 0 and last['lose'] is False, last
    finally:
        _gacha_teardown(d, old)
    print('gachainfo identity mismatch zero OK')


def test_skin_identity_mismatch_rejected():
    """批25 终审 MINOR-2：换号后 skin → error 不改玩家外观
    （bob 用自己身份改写 alice 冻结玩家的皮肤 = 计划 L18 禁止）"""
    import asyncio
    d, old = _gacha_setup()
    try:
        ok, err = serve.store.register('bob', '135792')
        assert ok, err
        r = fresh(10)
        p = mk(r, 1, 'A', [(5, 5), (4, 5)], (1, 0))
        p['user'] = 'alice'
        p['skin'] = 0
        s = _cfg_sess(sid='g3c', user='bob', room=r)
        s.ip = '3.3.3.16'
        s.pid = 1
        asyncio.run(serve.handle_msg(s, {'t': 'skin', 'i': 2}))
        last = s.ws.sent[-1]
        assert last.get('t') == 'error', last
        assert p['skin'] == 0, p['skin']
    finally:
        _gacha_teardown(d, old)
    print('skin identity mismatch OK')


def test_gacha_in_lobby_works_with_zero_dust():
    """批25 T3：大厅（无房间）可抽卡——dust=0、余额够即可，不卡死无回包"""
    import asyncio
    d, old = _gacha_setup()
    old_roll, old_pick = _stub_roll(), _stub_pool(5)
    try:
        serve.store.add_stardust('alice', 160)
        s = _cfg_sess(sid='g4', user='alice')
        s.ip = '3.3.3.6'
        asyncio.run(serve.handle_msg(s, {'t': 'gacha', 'n': 1}))
        last = s.ws.sent[-1]
        assert last.get('t') == 'gachares', last
        assert last['dust'] == 0 and last['balance'] == 0, last
        assert len(last['items']) == 1 and last['items'][0]['skin'] == 5, last
    finally:
        serve.gacha_roll, serve.pool_pick = old_roll, old_pick
        _gacha_teardown(d, old)
    print('gacha lobby OK')


def test_gacha_insufficient_balance_no_side_effect():
    """批25 T3：余额不足 → error 且库存/保底零变化"""
    import asyncio
    d, old = _gacha_setup()
    old_roll, old_pick = _stub_roll(), _stub_pool(5)
    try:
        s = _cfg_sess(sid='g5', user='alice')
        s.ip = '3.3.3.7'
        asyncio.run(serve.handle_msg(s, {'t': 'gacha', 'n': 1}))
        last = s.ws.sent[-1]
        assert last.get('t') == 'error', last
        u = serve.store.users['alice']
        assert u['skins'] == [] and u['gacha_p5'] == 0 and u['gacha_p4'] == 0
    finally:
        serve.gacha_roll, serve.pool_pick = old_roll, old_pick
        _gacha_teardown(d, old)
    print('gacha insufficient OK')


def test_gacha_deduct_and_result():
    """批25 T3：扣 160 出 3★；重复皮肤返还 10（净扣 150）"""
    import asyncio
    d, old = _gacha_setup()
    old_roll, old_pick = _stub_roll(), _stub_pool(5)
    try:
        serve.store.add_stardust('alice', 1600)
        s = _cfg_sess(sid='g6', user='alice')
        s.ip = '3.3.3.8'
        asyncio.run(serve.handle_msg(s, {'t': 'gacha', 'n': 1}))
        last = s.ws.sent[-1]
        assert last.get('t') == 'gachares' and len(last['items']) == 1, last
        it = last['items'][0]
        assert it['star'] == 3 and it['skin'] == 5 and it['dup'] is False and it['refund'] == 0, it
        assert serve.store.stardust('alice') == 1440, '扣 160'
        assert 5 in serve.store.skins_of('alice')
        # 重复皮肤 → 返还 10（净扣 150）
        asyncio.run(serve.handle_msg(s, {'t': 'gacha', 'n': 1}))
        last = s.ws.sent[-1]
        it = last['items'][0]
        assert it['dup'] is True and it['refund'] == 10, it
        assert last['balance'] == 1440 - 160 + 10 and last['gained'] == 10, last
    finally:
        serve.gacha_roll, serve.pool_pick = old_roll, old_pick
        _gacha_teardown(d, old)
    print('gacha deduct/result OK')


def test_gacha_ten_pull():
    """批25 T3：十连扣 1600、回 10 张卡、9 张重复各返 10"""
    import asyncio
    d, old = _gacha_setup()
    old_roll, old_pick = _stub_roll(), _stub_pool(5)
    try:
        serve.store.add_stardust('alice', 3200)
        s = _cfg_sess(sid='g7', user='alice')
        s.ip = '3.3.3.9'
        asyncio.run(serve.handle_msg(s, {'t': 'gacha', 'n': 10}))
        last = s.ws.sent[-1]
        assert last.get('t') == 'gachares' and len(last['items']) == 10, last
        assert last['items'][0]['dup'] is False and last['items'][1]['dup'] is True
        assert last['gained'] == 90, last['gained']
        assert serve.store.stardust('alice') == 3200 - 1600 + 90, '扣 1600 返 90'
        assert last['balance'] == 1690, last['balance']
    finally:
        serve.gacha_roll, serve.pool_pick = old_roll, old_pick
        _gacha_teardown(d, old)
    print('gacha ten pull OK')


def test_settle_dust_idempotent():
    """批25 T3：当场星尘并账幂等——并账后 dust 清零，重复 settle 不双计；无账号只清零"""
    d, old = _gacha_setup()
    try:
        r = fresh(10)
        p = mk(r, 1, 'A', [(5, 5), (4, 5)], (1, 0))
        p['user'] = 'alice'
        p['dust'] = 7
        serve.settle_dust(p)
        assert serve.store.stardust('alice') == 7 and p['dust'] == 0
        serve.settle_dust(p)
        assert serve.store.stardust('alice') == 7, '重复 settle 不双计'
        q = mk(r, 2, 'B', [(8, 8), (7, 8)], (1, 0))
        q['user'] = None
        q['dust'] = 5
        serve.settle_dust(q)
        assert q['dust'] == 0 and serve.store.stardust('alice') == 7
    finally:
        _gacha_teardown(d, old)
    print('settle dust idempotent OK')


def test_stardust_grant_on_win_and_tie():
    """批25 T3：吃果当场星尘 +10；胜局与平局局末都并账入总账"""
    d, old = _gacha_setup()
    try:
        now = serve.now_ms()
        # (a) 胜局：A 吃果得 dust=10 且分高 → check_win 并账
        r = fresh(10, limit=10)
        p1 = mk(r, 1, 'A', [(4, 4), (3, 4), (2, 4)], (1, 0))
        p2 = mk(r, 2, 'B', [(7, 7), (6, 7), (5, 7)], (1, 0))
        p1['user'] = 'alice'
        p1['score'], p2['score'] = 50, 30
        r.foods = [{'id': 1, 'x': 5, 'y': 4, 'score': 1}]
        p1['last_move'] = 0
        r.step(0.05, now - 5000)
        assert p1['dust'] == 10, p1.get('dust')   # 吃果 +10 星尘
        r.round_started = now - 11000
        r.check_win(now)
        assert r.win_pending == {'winner': 1}
        assert serve.store.stardust('alice') == 10 and p1['dust'] == 0, '胜局并账'
        # (b) 平局：时间到同分 → winner None 也并账
        r2 = fresh(10, limit=10)
        q1 = mk(r2, 1, 'C', [(4, 4), (3, 4)], (1, 0))
        q2 = mk(r2, 2, 'D', [(7, 7), (6, 7)], (1, 0))
        q1['user'] = 'alice'
        q1['score'] = q2['score'] = 40
        q1['dust'] = 3
        r2.round_started = now - 11000
        r2.check_win(now)
        assert r2.win_pending == {'winner': None}
        assert serve.store.stardust('alice') == 13 and q1['dust'] == 0, '平局也并账'
    finally:
        _gacha_teardown(d, old)
    print('stardust grant win/tie OK')


def test_skin_normalize_and_auth():
    """批25 T3：skin 先归一化再鉴权——负数/越界不绕过拥有检查"""
    import asyncio
    d, old = _gacha_setup()
    try:
        r = fresh(10)
        p = mk(r, 1, 'A', [(5, 5), (4, 5)], (1, 0))
        p['user'] = 'alice'                      # 真实入局不变量：p.user == sess.user
        s = _cfg_sess(sid='g10', user='alice', room=r)
        s.ip = '3.3.3.10'
        s.pid = 1
        # 批35：SKIN_N 16→18，边界值随之换挡（语义不变：先归一化再鉴权）
        # -3 → 15（辉夜 5★ 未拥有）→ error 且 skin 不变
        asyncio.run(serve.handle_msg(s, {'t': 'skin', 'i': -3}))
        assert s.ws.sent[-1].get('t') == 'error' and p['skin'] == 0, s.ws.sent[-1]
        # -18 → 0（免费档）→ 生效不报错
        n0 = len(s.ws.sent)
        asyncio.run(serve.handle_msg(s, {'t': 'skin', 'i': -18}))
        assert p['skin'] == 0 and not any(x.get('t') == 'error' for x in s.ws.sent[n0:]), \
            s.ws.sent[n0:]
        # 23 → 5（赤霞 3★ 未拥有）→ error（终审 NIT-7：原注释误标 4★）
        asyncio.run(serve.handle_msg(s, {'t': 'skin', 'i': 23}))
        assert s.ws.sent[-1].get('t') == 'error' and p['skin'] == 0, s.ws.sent[-1]
        # 拥有 15 后生效
        serve.store.grant_skin('alice', 15)
        asyncio.run(serve.handle_msg(s, {'t': 'skin', 'i': 15}))
        assert p['skin'] == 15, p['skin']
        # 免费档 2 生效
        asyncio.run(serve.handle_msg(s, {'t': 'skin', 'i': 2}))
        assert p['skin'] == 2, p['skin']
        # 批35 T5：角色款 16/17 恒免费（不进卡池、无需持有记录）→ 直接生效
        for i in (16, 17):
            n0 = len(s.ws.sent)
            asyncio.run(serve.handle_msg(s, {'t': 'skin', 'i': i}))
            assert p['skin'] == i, (i, p['skin'])
            assert not any(x.get('t') == 'error' for x in s.ws.sent[n0:]), s.ws.sent[n0:]
        # 免费档外的 5★ 角色款不存在 → 18 越界归一化到 0（免费）不报错
        n0 = len(s.ws.sent)
        asyncio.run(serve.handle_msg(s, {'t': 'skin', 'i': 18}))
        assert p['skin'] == 0 and not any(x.get('t') == 'error' for x in s.ws.sent[n0:]), \
            s.ws.sent[n0:]
        # 'abc' → 回退 0 不炸
        n0 = len(s.ws.sent)
        asyncio.run(serve.handle_msg(s, {'t': 'skin', 'i': 'abc'}))
        assert p['skin'] == 0 and not any(x.get('t') == 'error' for x in s.ws.sent[n0:]), \
            s.ws.sent[n0:]
    finally:
        _gacha_teardown(d, old)
    print('skin normalize/auth OK')


def test_join_skin_fallback_no_reject():
    """批25 T3：join 带未拥有皮肤 → 静默回退 0 正常入局；拥有后 join 生效"""
    import asyncio
    d, old = _gacha_setup()
    try:
        r = serve.Room('ja', 'ja', 10, bots=0)
        serve.rooms['ja'] = r
        try:
            s = _cfg_sess(sid='g11', user='alice')
            s.ip = '3.3.3.11'
            s.joins = 0
            asyncio.run(serve.handle_msg(s, {'t': 'join', 'room': 'ja', 'skin': 15}))
            assert s.ws.sent[-1].get('t') == 'room-ok', s.ws.sent
            assert r.players[s.pid]['skin'] == 0, r.players[s.pid]['skin']
            # 拥有后 join 生效
            serve.store.grant_skin('alice', 15)
            s2 = _cfg_sess(sid='g12', user='alice')
            s2.ip = '3.3.3.12'
            s2.joins = 0
            asyncio.run(serve.handle_msg(s2, {'t': 'join', 'room': 'ja', 'skin': 15}))
            assert r.players[s2.pid]['skin'] == 15, r.players[s2.pid]['skin']
        finally:
            del serve.rooms['ja']
    finally:
        _gacha_teardown(d, old)
    print('join skin fallback OK')


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
    blocked |= set(r.eterrain)   # 批33：元素地形计入占用（M7 单点挂钩，放置类全避开）
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
    r.eterrain = {}      # 批42修复#8：构造时随机撒的元素地形可能占 (8,5) → 磁吸换轴 (9,4) 偶发红（清掉构造性消除）
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
            self.closed = False

        async def send(self, x):
            import json
            self.sent.append(json.loads(x) if isinstance(x, str) else x)

        async def close(self):          # 批30④：adkick 踢人需关连接
            self.closed = True
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


def test_roomcfg_deferred_fields_reported():
    """批28 B：cfgapplied 回执带 deferred=[下局生效字段]——客户端据此提示
    「地形/尺寸改动将在下一局生效」；纯即时字段改回执 deferred 为空表"""
    import asyncio
    s = _cfg_sess(sid='s1')
    r = _cfg_room(s)
    s.room = r
    # 混合改动：theme/size=下局生效，bots=即时
    asyncio.run(serve.handle_msg(s, {'t': 'roomcfg', 'room': 'rc',
                                     'theme': 'day', 'size': 40, 'bots': 2}))
    cap = [x for x in s.ws.sent if x.get('t') == 'cfgapplied'][-1]
    assert cap['changed'] is True
    assert sorted(cap['deferred']) == ['size', 'theme']
    # 纯即时字段：deferred 空表
    s.ws.sent.clear()
    asyncio.run(serve.handle_msg(s, {'t': 'roomcfg', 'room': 'rc', 'bots': 3}))
    cap2 = [x for x in s.ws.sent if x.get('t') == 'cfgapplied'][-1]
    assert cap2['changed'] is True
    assert cap2['deferred'] == []
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


def test_win_zero_window_expires_immediately():
    """批41 修复#4：WIN=0 须立即过期。原 _win_ok 用 `now-rec[0] > win`，
    同一时钟 tick 内差值恰为 0 时 `0 > 0` 为 False → 窗未过期 → 限流误拒
    （test_room_pass_bruteforce_throttle 的时序 flake 根因，构造性钉死）"""
    fails = {}
    t0 = 1000.0
    serve._win_bump(fails, 'k', t0, 0)                  # 记 1 次失败，窗宽 0
    assert serve._win_ok(fails, 'k', t0, 3, 5) is True   # 正常窗内未超限 → 放行（行为不回归）
    assert serve._win_ok(fails, 'k', t0, 1, 0) is True, \
        'WIN=0 且 now==rec[0]（同 tick）必须视为窗过期放行，否则限流误拒'
    print('win zero window expires immediately OK')


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


def test_occupied_foods_cache():
    """批26①：occupied() 果占用集缓存——key=(列表对象身份, 长度)，重绑/append/
    过滤重绑全部失效；构建计数 _food_builds 供断言缓存确实命中（零重建）。"""
    r = fresh(12)
    taken = {c for pl in r.players.values() for c in pl['cells']}

    def free_xy(*ex):
        for xx in range(r.cols):
            for yy in range(r.rows):
                if (xx, yy) in ex or (xx, yy) in taken:
                    continue
                if (xx, yy) in r.walls or (xx, yy) in r.rocks or (xx, yy) in r.portals:
                    continue
                if r.bonus and (r.bonus['x'], r.bonus['y']) == (xx, yy):
                    continue
                return xx, yy
        raise AssertionError('no free cell')

    p = free_xy()
    q = free_xy(p)
    s = free_xy(p, q)
    r.foods = [{'id': 1, 'x': p[0], 'y': p[1], 'score': 10, 'color': '#fff'}]   # fresh() 会清空 foods → 自播一颗
    r._food_cells()                                    # 预热（本次构建）
    b0 = r._food_builds
    cells = r._food_cells()
    assert r._food_builds == b0 and p in cells, r._food_builds   # ① 命中缓存=零重建
    assert r.occupied(*p), '既有果仍被占用拦截'
    # ② append（同对象、len+1）→ 失效重建
    r.foods.append({'id': 9991, 'x': q[0], 'y': q[1], 'score': 10, 'color': '#fff'})
    assert q in r._food_cells()
    assert r._food_builds == b0 + 1, r._food_builds
    assert r.occupied(*q), '新果应被占用判定拦截'
    # ③ 整体重绑（换对象）→ 失效重建且旧果从集合移除
    r.foods = [{'id': 9992, 'x': s[0], 'y': s[1], 'score': 10, 'color': '#fff'}]
    cells = r._food_cells()
    assert r._food_builds == b0 + 2, r._food_builds
    assert s in cells and p not in cells and q not in cells, (cells, p, q, s)
    assert r.occupied(*s) and not r.occupied(*q), '重绑后占用判定未刷新'
    print('occupied foods cache OK')


def test_shutdown_settle():
    """批26③：SIGTERM 优雅关闭——遍历所有房并账当场星尘落盘（有账户入账、
    匿名丢弃、幂等）+ 信号接线（Linux add_signal_handler / Windows signal.signal 降级）"""
    import asyncio
    import signal as _sig
    r = fresh(12)
    a = mk(r, 1, 'A', [(4, 4)], (1, 0)); a['user'] = 'shut_alice'
    b = mk(r, 2, 'B', [(5, 4)], (1, 0)); b['user'] = None
    a['dust'] = 70; b['dust'] = 30
    serve.rooms['sd'] = r
    try:
        serve.store.register('shut_alice', '135790')   # add_stardust 对未知账号直接丢 → 先确保建户（密码须 6 位数字；已存在时返回 err 元组，无害）
        before = serve.store.stardust('shut_alice')
        n = serve.shutdown_settle()
        assert n == 1, n
        assert serve.store.stardust('shut_alice') == before + 70, '在局星尘并账'
        assert a['dust'] == 0 and b['dust'] == 0, (a['dust'], b['dust'])   # 匿名也清零=丢弃
        n2 = serve.shutdown_settle()
        assert n2 == 0, n2                                                 # 幂等
        assert serve.store.stardust('shut_alice') == before + 70, '二次调用不双计'
        # 信号接线：事件槽创建 + SIGTERM 注册（不支持 add_signal_handler 的平台降级）
        async def go():
            serve._shutdown_evt = None
            serve.install_shutdown_handlers()
            assert serve._shutdown_evt is not None, 'shutdown 事件槽未创建'
        asyncio.run(go())
        _sig.signal(_sig.SIGTERM, _sig.SIG_DFL)   # 还原默认，避免影响测试进程
    finally:
        serve.rooms.pop('sd', None)
    print('shutdown settle OK')


def test_proto_ver_handshake():
    """批26⑤：room-ok 三路（入局/resume/观战）必带 ver == PROTO_VER——
    客户端内置常量不等则 location.reload()，关闭 stale-tab 拿旧 JS 续玩"""
    import asyncio
    ver = serve.PROTO_VER
    try:
        # ---- 路径1：新入局 ----
        serve.rooms['t'] = fresh(12)
        s1 = _cfg_sess(sid='pv1'); s1.ip = '1.1.1.1'; s1.joins = 0
        asyncio.run(serve.handle_msg(s1, {'t': 'join', 'room': 't', 'name': 'V'}))
        last = s1.ws.sent[-1]
        assert last.get('t') == 'room-ok', last
        assert last.get('ver') == ver, last
        # ---- 路径2：断线 resume（挂起者同 IP 复活） ----
        r2 = fresh(12)
        p = mk(r2, 1, 'A', [(4, 4)], (1, 0))
        p['off_at'] = serve.now_ms(); p['off_ip'] = '1.1.1.1'
        serve.rooms['t'] = r2
        s2 = _cfg_sess(sid='pv2'); s2.ip = '1.1.1.1'; s2.joins = 0
        asyncio.run(serve.handle_msg(s2, {'t': 'join', 'room': 't', 'name': 'V'}))
        last = s2.ws.sent[-1]
        assert last.get('t') == 'room-ok' and last.get('resumed') is True, last
        assert last.get('ver') == ver, last
        # ---- 路径3：观战 ----
        s3 = _cfg_sess(sid='pv3'); s3.ip = '2.2.2.2'
        asyncio.run(serve.handle_msg(s3, {'t': 'watch', 'room': 't'}))
        last = s3.ws.sent[-1]
        assert last.get('t') == 'room-ok' and last.get('ver') == ver, last
    finally:
        serve.rooms.pop('t', None)
    print('proto ver handshake OK')


def test_update_gift_claim_once():
    """批29④：更新庆祝回馈 90 抽（=GACHA_PRICE×90=14,400）——
    room-ok 带未领标记；claimgift 入账一次性；重复拒零副作用；未登录拒"""
    import asyncio
    d, old = _gacha_setup()          # 临时账号库（注册 alice），teardown 还原
    try:
        serve.rooms['gt'] = fresh(12)
        s = _cfg_sess(sid='gt1', user='alice'); s.ip = '9.9.9.1'; s.joins = 0
        asyncio.run(serve.handle_msg(s, {'t': 'join', 'room': 'gt', 'name': 'G'}))
        last = s.ws.sent[-1]
        assert last.get('t') == 'room-ok', last
        assert last.get('gift') == 14400, '未领标记（金额）应随 room-ok 下发：' + repr(last)
        # 领取：+14400 且记录已领版本
        asyncio.run(serve.handle_msg(s, {'t': 'claimgift'}))
        r = s.ws.sent[-1]
        assert r.get('t') == 'giftres' and r.get('ok'), r
        assert r.get('amount') == 14400, r
        assert serve.store.stardust('alice') == 14400, serve.store.stardust('alice')
        assert serve.store.users['alice'].get('update_ver_claimed') == serve.PROTO_VER
        # 重复领取：拒绝 + 零副作用
        asyncio.run(serve.handle_msg(s, {'t': 'claimgift'}))
        r2 = s.ws.sent[-1]
        assert r2.get('t') == 'error', r2
        assert serve.store.stardust('alice') == 14400, '重复领取不得双计'
        # 已领后 room-ok 不再带 gift 标记
        asyncio.run(serve.handle_msg(s, {'t': 'join', 'room': 'gt', 'name': 'G'}))
        last2 = s.ws.sent[-1]
        assert last2.get('gift') in (None, 0), last2
        # oracle F5-②：观战（watch）路不带 gift——弹窗从属对局链路，观战不触发
        asyncio.run(serve.handle_msg(s, {'t': 'watch', 'room': 'gt'}))
        wl = next(m for m in reversed(s.ws.sent) if m.get('t') == 'room-ok')   # leave_room 会附发 gachainfo，取 room-ok 本体
        assert wl.get('spectate') and wl.get('gift') in (None, 0), wl
        # oracle F5-①：老版本已领（claimed=PROTO_VER-1）在当前版本仍放行（版本键语义）
        serve.store.users['alice']['update_ver_claimed'] = serve.PROTO_VER - 1
        assert serve._update_gift_pending('alice') == 14400, '上一版本领过 → 当前版本应再标待领'
        serve.store.users['alice']['update_ver_claimed'] = serve.PROTO_VER   # 还原为本版本已领
        # oracle F3：降级（PROTO_VER 调小）期间已领大版本 → 拒且不覆写
        real_ver = serve.PROTO_VER
        try:
            serve.PROTO_VER = real_ver - 1
            assert serve._update_gift_pending('alice') == 0, '降级不得再标待领'
            asyncio.run(serve.handle_msg(s, {'t': 'claimgift'}))
            r4 = s.ws.sent[-1]
            assert r4.get('t') == 'error', r4
            assert serve.store.users['alice']['update_ver_claimed'] == real_ver, '降级不得覆写已领版本'
        finally:
            serve.PROTO_VER = real_ver
        # 未登录：拒
        s2 = _cfg_sess(sid='gt2', user=None); s2.ip = '9.9.9.2'; s2.joins = 0
        asyncio.run(serve.handle_msg(s2, {'t': 'claimgift'}))
        r3 = s2.ws.sent[-1]
        assert r3.get('t') == 'error' and '登录' in r3.get('err', ''), r3
    finally:
        serve.rooms.pop('gt', None)
        _gacha_teardown(d, old)
    print('update gift claim OK')


def test_login_gift_batch31():
    """批31：登录即弹回馈——login/register/authtoken 的 auth 回包随带 gift
    （待领金额；已领=0。客户端据 authres 即弹，不再等 room-ok）"""
    import asyncio
    d, old = _gacha_setup()
    try:
        s = _cfg_sess(sid='lg1'); s.ip = '8.8.8.1'; s.joins = 0
        # 注册回包即带未领标记
        asyncio.run(serve.handle_msg(s, {'t': 'register', 'user': 'bob', 'pass': '123456'}))
        r = s.ws.sent[-1]
        assert r.get('t') == 'auth' and r.get('ok'), r
        assert r.get('gift') == 14400, '注册回包应带待领回馈：' + repr(r)
        # 登录回包同样带
        s2 = _cfg_sess(sid='lg2'); s2.ip = '8.8.8.2'; s2.joins = 0
        asyncio.run(serve.handle_msg(s2, {'t': 'login', 'user': 'bob', 'pass': '123456'}))
        r2 = s2.ws.sent[-1]
        assert r2.get('t') == 'auth' and r2.get('ok') and r2.get('gift') == 14400, r2
        # authtoken 回包也带（老标签页恢复登录态）
        tok = r2.get('token')
        s3 = _cfg_sess(sid='lg3'); s3.ip = '8.8.8.3'; s3.joins = 0
        asyncio.run(serve.handle_msg(s3, {'t': 'authtoken', 'token': tok}))
        r3 = s3.ws.sent[-1]
        assert r3.get('t') == 'auth' and r3.get('ok') and r3.get('gift') == 14400, r3
        # 领取后登录不再带（0 语义，客户端 truthy 判断不弹）
        asyncio.run(serve.handle_msg(s2, {'t': 'claimgift'}))
        assert s2.ws.sent[-1].get('ok'), s2.ws.sent[-1]
        asyncio.run(serve.handle_msg(s2, {'t': 'login', 'user': 'bob', 'pass': '123456'}))
        r4 = s2.ws.sent[-1]
        assert r4.get('gift') in (None, 0), '已领后 auth 包不应再标待领：' + repr(r4)
    finally:
        _gacha_teardown(d, old)
    print('login gift batch31 OK')


def test_star_tuning_batch29():
    """批29⑤：星星调参——刷新 0.015 / 寿命 12000ms / 充能 +25 / 吃星尘 +15；
    果子收益保持 +10 不动（用户明确「果子数量不增加 增加星星数量」）"""
    assert serve.BONUS_SPAWN_P == 0.015, serve.BONUS_SPAWN_P   # 星星刷新概率（原 0.004）
    assert serve.BONUS_LIFE == 12000, serve.BONUS_LIFE          # 星星在场寿命（原 8000）
    assert serve.ULT_STAR == 25, serve.ULT_STAR                 # 吃星充能（原 15）
    now = serve.now_ms()
    # 吃星星当场星尘 +15（蛇头正对 bonus，远格补粒钉死防随机双吃）
    r = fresh(10)
    p = mk(r, 1, "A", [(2, 5), (1, 5), (0, 5)], (1, 0))
    r.foods = [{"id": 1, "x": 0, "y": 9, "score": 10, "color": "#fff"}]
    r.bonus = {"id": 9, "x": 3, "y": 5, "score": 50, "born": now}
    r.step(0.05, now)
    assert p.get("dust", 0) == 15, p.get("dust")
    # 吃果子仍是 +10（不动）
    r2 = fresh(10)
    q = mk(r2, 1, "B", [(2, 5), (1, 5), (0, 5)], (1, 0))
    r2.foods = [{"id": 2, "x": 3, "y": 5, "score": 10, "color": "#fff"}]
    r2.step(0.05, now)
    assert q.get("dust", 0) == 10, q.get("dust")
    print('star tuning batch29 OK')


def test_newbie_room_cfg_batch30():
    """批30① 新手村配置（用户拍板：24×24、主题保持随每局随机）：
    岩石密度覆盖 0.5、2 条 AI 陪练、死亡可复活（init 自动限时 120s 兜底）；
    b 标准局 / c 大神场保持全默认不动。"""
    saved = {k: serve.rooms.get(k) for k in ('a', 'b', 'c')}
    try:
        serve.init_rooms()                       # 按当前 DEFAULT_ROOMS + 新手村专属配置重建
        a = serve.rooms['a']
        assert a.name == '新手村' and a.cols == 24 and a.rows == 24, (a.name, a.cols, a.rows)
        assert a.theme_fixed is None, '主题保持随每局随机'
        assert a.rock_mult == 0.5, a.rock_mult
        assert a.eff_rock() == 0.5, '岩石覆盖生效（随机到 lava 也按 0.5）'
        assert a.respawn is True, '死亡可复活（解决死一次出局）'
        assert a.limit == 120, '复活房限时兜底'  # limit==0 → respawn 自动补 120s
        assert a.bots == 2, a.bots
        assert len([p for p in a.players.values() if p.get('bot')]) == 2, '2 条 AI 已生成'
        b = serve.rooms['b']
        assert b.cols == 24 and b.theme_fixed is None and b.rock_mult is None, '标准局不动'
        assert b.respawn is False and b.limit == 0 and b.bots == 0, '标准局不动'
        c = serve.rooms['c']
        assert c.cols == 32 and c.theme_fixed is None and c.rock_mult is None, '大神场不动'
        assert c.respawn is False and c.limit == 0 and c.bots == 0, '大神场不动'
    finally:
        for k, v in saved.items():
            if v is None:
                serve.rooms.pop(k, None)
            else:
                serve.rooms[k] = v
    print('newbie room cfg batch30 OK')


def test_online_count_batch30():
    """批30②：在线人数去重计数——登录按用户名去重（同账号多标签=1），
    匿名按会话计；welcome 字段与 'online' 事件的 n 即此值"""
    from types import SimpleNamespace

    class S:                      # 可哈希的最小会话桩
        def __init__(self, sid, user=None):
            self.sid = sid
            self.user = user

    old = set(serve.all_sessions)
    try:
        serve.all_sessions.clear()
        assert serve.online_count() == 0, '空连接 = 0'
        serve.all_sessions.add(S(1))                       # 匿名A
        serve.all_sessions.add(S(2))                       # 匿名B
        serve.all_sessions.add(S(3, 'u1'))                 # 登录
        serve.all_sessions.add(S(4, 'u1'))                 # 同账号第二标签 → 去重
        assert serve.online_count() == 3, serve.online_count()
        assert isinstance(serve.online_count(), int)
    finally:
        serve.all_sessions.clear()
        serve.all_sessions.update(old)
    print('online count batch30 OK')


def test_gchat_batch30():
    """批30③ 公屏聊天：历史 50 条上限 + 1s 限速 + 空白拒/超长截断 +
    全体会话广播 + welcome 携带历史 + 显示名（登录名 / 路人+会话尾号）"""
    import asyncio
    old = set(serve.all_sessions)
    saved_log = list(serve.gchat_log)
    try:
        serve.gchat_log.clear()
        a = _cfg_sess(sid='ga1')                      # 匿名
        b = _cfg_sess(sid='gb1', user='bob')          # 登录
        serve.all_sessions.update({a, b})
        # 1) 匿名发言：去空白进历史 + 广播到全体（含自己）
        asyncio.run(serve.handle_msg(a, {'t': 'gchatin', 'text': ' 你好公屏 '}))
        assert len(serve.gchat_log) == 1, serve.gchat_log
        m0 = serve.gchat_log[0]
        assert m0['text'] == '你好公屏', m0
        assert str(m0['name']).startswith('路人'), m0
        for s in (a, b):
            got = [x for x in s.ws.sent if x.get('t') == 'gchat']
            assert got and got[-1]['m']['text'] == '你好公屏', s.ws.sent
        # 2) welcome 携带公屏历史
        w = serve.welcome_payload(a)
        assert w.get('t') == 'welcome', w
        assert w.get('gchat') and w['gchat'][0]['text'] == '你好公屏', w
        # 3) 1s 限速：同会话立刻再发被丢
        asyncio.run(serve.handle_msg(a, {'t': 'gchatin', 'text': '第二条'}))
        assert len(serve.gchat_log) == 1, '限速应丢弃'
        # 4) 空白拒（不进历史不广播；注意限速槽先于内容校验消耗，与房内 chat 同口径）
        asyncio.run(serve.handle_msg(b, {'t': 'gchatin', 'text': '   '}))
        assert len(serve.gchat_log) == 1, '空白应拒'
        # 5) 超长截断 + 登录显示名（c 新会话，避免撞 b 已消耗的限速槽）
        c = _cfg_sess(sid='gc1', user='carol')
        asyncio.run(serve.handle_msg(c, {'t': 'gchatin', 'text': 'x' * 200}))
        assert len(serve.gchat_log) == 2, serve.gchat_log
        assert serve.gchat_log[-1]['text'] == 'x' * serve.CHAT_MAX
        assert serve.gchat_log[-1]['name'] == 'carol'
        # 6) 历史上限 50（新会话避限速）：发 55 条只留尾 50
        serve.gchat_log.clear()
        for i in range(55):
            s = _cfg_sess(sid=f'f{i}', user=f'u{i}')
            asyncio.run(serve.handle_msg(s, {'t': 'gchatin', 'text': f'm{i}'}))
        assert len(serve.gchat_log) == 50, len(serve.gchat_log)
        assert serve.gchat_log[0]['text'] == 'm5', serve.gchat_log[0]
    finally:
        serve.all_sessions.clear()
        serve.all_sessions.update(old)
        serve.gchat_log.clear()
        serve.gchat_log.extend(saved_log)
    print('gchat batch30 OK')


def test_pause_afk_batch30():
    """批30③b：暂停=挂机——toggle 回执/原地冻结/操作拒收/连接保持不超时回收/恢复续动"""
    import asyncio
    r = fresh(12)
    sess = _cfg_sess(sid='s1', user=None, room=r)
    p = mk(r, 1, "Me", [(4, 4), (4, 5)], (1, 0))
    p['session'] = sess
    sess.pid = 1
    p2 = mk(r, 2, "Other", [(6, 4), (6, 5)], (1, 0))
    # 观战者（在房但 pid=None）发 pause → 静默无回执（handle_msg 房内守卫）
    spy = _cfg_sess(sid='s9', user=None, room=r)
    asyncio.run(serve.handle_msg(spy, {'t': 'pause'}))
    assert not any(x.get('t') == 'pauseres' for x in spy.ws.sent), "观战者不该收到 pauseres"
    # 开：置 off_at+pause（复用挂起保护语义）+ pauseres on
    asyncio.run(serve.handle_msg(sess, {'t': 'pause'}))
    assert any(x.get('t') == 'pauseres' and x.get('on') for x in sess.ws.sent), sess.ws.sent
    assert p.get('pause') is True and p.get('off_at'), p
    # 冻结：暂停蛇原地不动，他蛇照走（批21 冻结语义同轨）
    cells1 = [tuple(c) for c in p['cells']]
    now = serve.now_ms()
    for _ in range(5):
        now += 200
        r.step(0.05, now)
    assert [tuple(c) for c in p['cells']] == cells1, ("暂停蛇应原地冻结", p['cells'])
    assert p2['cells'][0] != (6, 4), "在场蛇应正常移动"
    # 暂停期间操作拒收：dir 不入队、atk 不出弹（原地冻结可开火=无敌炮台）
    sess.ws.sent.clear()
    asyncio.run(serve.handle_msg(sess, {'t': 'dir', 'x': 0, 'y': 1}))
    assert not p['queue'], ("暂停中不该入队", p['queue'])
    asyncio.run(serve.handle_msg(sess, {'t': 'atk'}))
    assert not r.projectiles, ("暂停中不该发射", r.projectiles)
    # 连接保持的挂机超过 RESUME_MS 也不回收（与真断线的区别所在）
    p['off_at'] = serve.now_ms() - serve.RESUME_MS - 5000
    r.step_wrapper(0.05, serve.now_ms())
    assert 1 in r.players, "挂机中（session 在）不应超时移出"
    # 关：清标记 → pauseres off → 恢复移动
    sess.ws.sent.clear()
    asyncio.run(serve.handle_msg(sess, {'t': 'pause'}))
    assert any(x.get('t') == 'pauseres' and not x.get('on') for x in sess.ws.sent), sess.ws.sent
    assert 'pause' not in p and 'off_at' not in p, p
    r.step(0.05, serve.now_ms() + 200)
    assert p['cells'][0] != cells1[0], "恢复后应继续移动"
    # 挂机中断线（session=None）→ 仍按 RESUME_MS 宽限回收（防幽灵障碍永驻）
    p2['off_at'] = serve.now_ms() - serve.RESUME_MS - 5000
    p2['pause'] = True
    p2['session'] = None
    r.step_wrapper(0.05, serve.now_ms())
    assert 2 not in r.players, "挂机+断线超宽限应移出"
    print("pause afk batch30 OK")


def test_pause_counts_as_present_batch30():
    """批30③b：挂机者仍算在场真人——第二人断线时原蛇挂起等恢复，而非直接移出"""
    r = fresh(12)
    sess1 = _cfg_sess(sid='s1', user=None, room=r)
    p1 = mk(r, 1, "Paused", [(4, 4), (4, 5)], (1, 0))
    p1['session'] = sess1
    p1['off_at'] = serve.now_ms()      # 挂机中（连接保持）
    p1['pause'] = True
    sess2 = _cfg_sess(sid='s2', user=None, room=r)
    sess2.pid = 2
    sess2.ip = '9.9.9.9'
    mk(r, 2, "Leaver", [(6, 4), (6, 5)], (1, 0))
    serve.leave_room(sess2, hard=False)   # 断线：房里还有连接中的挂机真人 → 应挂起
    assert 2 in r.players, ("挂机者在场时断线方不该被直接移出", list(r.players))
    assert r.players[2].get('off_at'), "断线方应挂起等恢复"
    assert r.players[2]['session'] is None
    print("pause counts as present batch30 OK")


def test_admin_core_batch30():
    """批30④：管理员白名单——非 admin 发管理消息一律拒；admin 放行；
    welcome/auth 带 admin 标记；踢人断连；禁言拒聊到期自动失效"""
    import asyncio
    import time as _t
    # 白名单判定 + welcome/auth 标记
    adm = _cfg_sess(sid='adm1', user='yuan')
    oth = _cfg_sess(sid='oth1', user='bob')
    anon = _cfg_sess(sid='ano1', user=None)
    assert serve.is_admin(adm) is True
    assert serve.is_admin(oth) is False
    assert serve.is_admin(anon) is False, '匿名永非管理员'
    assert serve.welcome_payload(adm).get('admin') is True
    assert serve.welcome_payload(oth).get('admin') is False
    assert serve.auth_payload('yuan').get('admin') is True
    assert serve.auth_payload('bob').get('admin') is False
    # 非 admin：五个 ad* 消息全拒（零副作用）
    old_mutes = dict(serve.mutes)
    serve.mutes.clear()
    old_all = set(serve.all_sessions)
    serve.all_sessions.clear()
    try:
        for mm in ({'t': 'adkick', 'name': 'yuan'}, {'t': 'admute', 'name': 'bob', 'mins': 5},
                   {'t': 'adnotice', 'text': 'hi'}, {'t': 'adreport'},
                   {'t': 'adgrant', 'name': 'bob', 'amt': 100}):
            asyncio.run(serve.handle_msg(oth, mm))
        assert not serve.mutes, '非 admin 不得写禁言表'
        assert not any(x.get('t') == 'adminres' for x in oth.ws.sent)
        # admin 踢人：目标收 kicked 回执且连接关闭；不在线报错
        vic = _cfg_sess(sid='vic1', user='victim')
        serve.all_sessions.add(vic)
        asyncio.run(serve.handle_msg(adm, {'t': 'adkick', 'name': 'victim'}))
        assert any(x.get('t') == 'kicked' for x in vic.ws.sent), vic.ws.sent
        assert vic.ws.closed is True, '踢出必须关闭目标连接'
        assert any(x.get('t') == 'adminres' and x.get('ok') for x in adm.ws.sent)
        adm.ws.sent.clear()
        asyncio.run(serve.handle_msg(adm, {'t': 'adkick', 'name': 'ghost999'}))
        assert any(x.get('t') == 'adminres' and not x.get('ok') for x in adm.ws.sent)
        # 禁言：到期前拒 gchatin，到期后放行（限速槽先于内容校验，禁言提示需复位 chat_at）
        asyncio.run(serve.handle_msg(adm, {'t': 'admute', 'name': 'victim', 'mins': 5}))
        assert serve.mutes.get('victim', 0) > _t.time()
        vic.chat_at = 0
        asyncio.run(serve.handle_msg(vic, {'t': 'gchatin', 'text': '我说话'}))
        r = vic.ws.sent[-1]
        assert r.get('t') == 'error' and '禁言' in r.get('err', ''), r
        serve.mutes['victim'] = _t.time() - 1     # 到期
        vic.chat_at = 0
        asyncio.run(serve.handle_msg(vic, {'t': 'gchatin', 'text': '我说话'}))
        assert not any(x.get('t') == 'error' and '禁言' in x.get('err', '') for x in vic.ws.sent[-1:])
    finally:
        serve.mutes.clear(); serve.mutes.update(old_mutes)
        serve.all_sessions.clear(); serve.all_sessions.update(old_all)
    print('admin core batch30 OK')


def test_admin_notice_grant_report_batch30():
    """批30④：公告进公屏历史并全体广播；发奖入账+范围钳制+在线提醒；
    报告字段齐全（在线/今日/累计/近7日/活跃榜）"""
    import asyncio
    d, old_store = _gacha_setup()      # 临时账号库（alice），teardown 还原
    old_log = list(serve.gchat_log)
    old_all = set(serve.all_sessions)
    serve.gchat_log.clear()
    serve.all_sessions.clear()
    try:
        adm = _cfg_sess(sid='adm2', user='yuan')
        alice = _cfg_sess(sid='ali1', user='alice')
        serve.all_sessions.add(alice)
        # 公告：进历史 + 全体广播（发送者显示 📢 公告）
        asyncio.run(serve.handle_msg(adm, {'t': 'adnotice', 'text': '今晚维护'}))
        assert serve.gchat_log and serve.gchat_log[-1] == {'name': '📢 公告', 'text': '今晚维护'}
        assert any(x.get('t') == 'gchat' and x['m']['name'] == '📢 公告' for x in alice.ws.sent)
        # 发奖：alice +500 且在线收到 toast 提醒
        asyncio.run(serve.handle_msg(adm, {'t': 'adgrant', 'name': 'alice', 'amt': 500}))
        assert serve.store.stardust('alice') == 500, serve.store.stardust('alice')
        assert any(x.get('t') == 'toast' for x in alice.ws.sent), '在线受奖者应收到提醒'
        r = adm.ws.sent[-1]
        assert r.get('t') == 'adminres' and r.get('ok'), r
        # 超额拒 + 不存在用户拒
        adm.ws.sent.clear()
        asyncio.run(serve.handle_msg(adm, {'t': 'adgrant', 'name': 'alice', 'amt': 100001}))
        assert any(x.get('t') == 'adminres' and not x.get('ok') for x in adm.ws.sent)
        assert serve.store.stardust('alice') == 500, '超额拒绝零副作用'
        asyncio.run(serve.handle_msg(adm, {'t': 'adgrant', 'name': 'nobody_x', 'amt': 10}))
        assert any(x.get('t') == 'adminres' and not x.get('ok') for x in adm.ws.sent)
        # 报告：字段齐全
        adm.ws.sent.clear()
        asyncio.run(serve.handle_msg(adm, {'t': 'adreport'}))
        rep = [x for x in adm.ws.sent if x.get('t') == 'adreportres']
        assert rep, adm.ws.sent
        txt = '\n'.join(rep[0].get('lines') or [])
        for kw in ('在线', '今日', '累计', '近7日', '活跃'):
            assert kw in txt, (kw, txt)
    finally:
        serve.gchat_log.clear(); serve.gchat_log.extend(old_log)
        serve.all_sessions.clear(); serve.all_sessions.update(old_all)
        _gacha_teardown(d, old_store)
    print('admin notice grant report batch30 OK')


def test_height_gen_invariants():
    r = fresh(24, theme_fixed='default')   # 主题随局随机（lava/space water=0 无草）→ 固定 default
    mk(r, 1, "A", [(12, 12), (11, 12)], (1, 0))   # 造旧蛇头做 ±4 避让验证
    r.build_terrain()
    vals = set(r.hmap.values())
    assert vals                                                # 默认主题必出地形
    assert vals <= {-2, -1, 1, 2, 3, -9}, vals                 # 批46：值域哨兵 9 → -9；0 不存
    assert 0 not in vals
    assert 9 not in vals                                       # 批46：旧哨兵 9 已废除
    assert -2 in vals                                          # 草丛必有生成来源（spec §7.3 第4类）
    assert len(r.hmap) <= int(0.35 * 24 * 24), len(r.hmap)   # ≤35% 预算
    assert not (set(r.rocks) & set(r.hmap))                  # 不与岩石重叠
    assert not (set(r.walls) & set(r.hmap))                  # 不压墙块
    assert not (set(r.portals) & set(r.hmap))                # 不压传送门
    assert all(abs(x - 12) + abs(y - 12) >= 4 for (x, y) in r.hmap)   # 不压旧蛇头 ±4
    rl = fresh(24, theme_fixed='lava')
    rl.build_terrain()
    assert -1 not in rl.hmap.values() and -2 not in rl.hmap.values()  # 熔岩无水洼无草
    assert -9 not in rl.hmap.values()                          # 批46：熔岩 eff_water=0 → 无深渊
    r0 = fresh(16, height_mult=0.0, water_amt=0.0, bld_amt=0.0)
    r0.build_terrain()
    assert r0.hmap == {}                                     # 三旋钮全 0（预算=0 早退）= 纯平地


def test_abyss_gen_batch46():
    """批46 §3：深渊 -9 首次真正生成（挂 eff_water，预算 area/450）；深渊格 occupied 拦截"""
    found = None
    for seed in range(20):
        r = fresh(48, theme_fixed='default')                  # water=0.7，48×48 → 3 次尝试/局
        serve.random.seed(4600 + seed)
        r.build_terrain()
        ab = [c for c, h in r.hmap.items() if h == -9]
        if ab:
            found = (r, ab)
            break
    assert found, '20 个种子内 default 主题必须生成 ≥1 处深渊 -9'
    r, ab = found
    assert all(r.hmap[c] == -9 for c in ab)
    # 每个连通块 ≤4 格（多次 blob 各自 2~4 格，可多处深渊）
    seen_ab, comps = set(), []
    nb46 = lambda c: [(c[0]+1,c[1]), (c[0]-1,c[1]), (c[0],c[1]+1), (c[0],c[1]-1)]
    for c0 in ab:
        if c0 in seen_ab:
            continue
        comp, dq2 = [], [c0]
        seen_ab.add(c0)
        while dq2:
            cc = dq2.pop(); comp.append(cc)
            for q in nb46(cc):
                if q in set(ab) and q not in seen_ab:
                    seen_ab.add(q); dq2.append(q)
        comps.append(comp)
    assert all(1 <= len(cm) <= 4 for cm in comps), comps      # walk_blob 重试可留孤格
    assert all(r.occupied(*c) for c in ab)                    # 深渊格不可出生/占位
    # 熔岩（eff_water=0）：20 局无深渊
    for seed in range(20):
        rl = fresh(48, theme_fixed='lava')
        serve.random.seed(4690 + seed)
        rl.build_terrain()
        assert -9 not in rl.hmap.values()


def test_reach_rules_batch46():
    """批46 §5：reach_set 转移规则——上行≤1/下行≤3 可达；崖/坠亡/深渊不可达"""
    # h3 无坡 → 顶不可达
    r = fresh(16); r.hmap = {(6,5): 3}; r._reach = None
    mk(r, 1, "A", [(2,2),(2,3)], (1,0))
    assert (6,5) not in r.reach_set()
    # h3 有坡（3→2→1→0）→ 顶可达
    r = fresh(16); r.hmap = {(6,5): 3, (5,5): 2, (4,5): 1}; r._reach = None
    mk(r, 1, "A", [(2,2),(2,3)], (1,0))
    assert (6,5) in r.reach_set()
    # 深渊 -9 不可达
    r = fresh(16); r.hmap = {(6,5): -9}; r._reach = None
    mk(r, 1, "A", [(2,2),(2,3)], (1,0))
    assert (6,5) not in r.reach_set()
    # 落差 2 浅坑可达（可进可出）
    r = fresh(16); r.hmap = {(6,5): -2}; r._reach = None
    mk(r, 1, "A", [(2,2),(2,3)], (1,0))
    assert (6,5) in r.reach_set()
    # 落差 4 坠亡坑不可达
    r = fresh(16); r.hmap = {(6,5): -4}; r._reach = None
    mk(r, 1, "A", [(2,2),(2,3)], (1,0))
    assert (6,5) not in r.reach_set()


def test_solid_fatal_fall_batch46():
    """批46 §5：_solid 挡致命坠落（bot 贪心防摔死）；_deflect_dir 过滤致命候选方向"""
    r = fresh(16)
    # cur_h=0 时 -4 坠亡格视为 solid；-3 落差不断尾格不挡
    assert r._solid(6, 5, cur_h=0) is False                       # 平地不挡
    r.hmap = {(6,5): -4}; assert r._solid(6, 5, cur_h=0) is True  # 坠亡格挡
    r.hmap = {(6,5): -3}; assert r._solid(6, 5, cur_h=0) is False # 落差3（断尾）不挡
    r.hmap = {(6,5): -9}; assert r._solid(6, 5, cur_h=0) is True  # 深渊挡
    r.hmap = {(6,5): 2};  assert r._solid(6, 5, cur_h=0) is True  # 既有上行≥2 挡
    r.hmap = {(6,5): -6}; assert r._solid(6, 5, cur_h=-2) is True # 高台上摔下同样挡（-2→-6 落差4）
    # _deflect_dir：shield 在「一边崖一边深渊」夹缝 → 候选全滤掉 → None（照死不折进深渊）
    r = fresh(16); r.hmap = {(5,6): 2, (5,4): -9}; r._reach = None   # 上=崖 下=深渊
    p = mk(r, 1, "A", [(5,5),(4,5)], (1,0)); p['inv'] = 0
    nd = r._deflect_dir(p, set(), cur_h=0)
    assert nd is None
    # 只有一边可走 → 折向安全边
    r2 = fresh(16); r2.hmap = {(5,6): 2}; r2._reach = None
    p2 = mk(r2, 1, "A", [(5,5),(4,5)], (1,0)); p2['inv'] = 0
    assert r2._deflect_dir(p2, set(), cur_h=0) == (0, -1)


def test_bot_dijkstra_batch46():
    """批46 §5：bot 寻路 BFS→Dijkstra 加权——爬坡 2 / 坠落 2~3 为 4 择优绕行；
    崖/坠亡/深渊不可走；cap 4× 大迷宫（旧 2000 必失败）可达"""
    # 峰顶 h3 无坡：目标本身不可进入 → None（回落贪心）
    r = fresh(16); r.hmap = {(6,5): 3}
    p = mk(r, 1, "A", [(5,5),(4,5)], (1,0))
    assert r._bot_path_step(p, (6,5)) is None
    # 直路撞崖（h2）→ 绕行，不返回 (1,0)
    r = fresh(16); r.hmap = {(6,5): 2}
    p = mk(r, 1, "A", [(5,5),(4,5)], (1,0))
    d = r._bot_path_step(p, (7,5))
    assert d in ((0,1), (0,-1)), d
    # 直路落差 3（断尾代价 4）vs 绕行 4 步平地（代价 4）——同价时平局破法不确定，改用落差 2（代价 4，绕行 2 步更优）
    r = fresh(16); r.hmap = {(6,5): -2}
    p = mk(r, 1, "A", [(5,5),(4,5)], (1,0))
    d = r._bot_path_step(p, (7,5))
    assert d in ((0,1), (0,-1)), d
    # 爬坡 1（代价 2+1=3）< 绕行 4 → 直接爬
    r = fresh(16); r.hmap = {(6,5): 1}
    p = mk(r, 1, "A", [(5,5),(4,5)], (1,0))
    assert r._bot_path_step(p, (7,5)) == (1,0)
    # 大迷宫（64×64 三隔间，需 >2000 弹出）：旧 cap 2000 失败返回 None，新 cap 8000 可达
    r = fresh(64)
    r.walls = [(21, yy) for yy in range(63)] + [(42, yy) for yy in range(1, 64)]
    p = mk(r, 1, "A", [(2,2),(2,3)], (1,0))
    d = r._bot_path_step(p, (60,2))
    assert d is not None, '64×64 三隔间迷宫须在 cap 内找到路'


def test_height_majestic_ridge_batch43():
    """批43「宏伟」档（2.6）→ 脊线山脉：连绵 h≥2 脊 + h=3 峰 + 逐级爬升链（h3→h2→h1→0 相邻存在）"""
    def nb(c):
        x, y = c
        return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    r = fresh(48, theme_fixed='default', height_mult=2.6, water_amt=0.0, bld_amt=0.0)
    serve.random.seed(4301)
    r.build_terrain()
    vals = set(r.hmap.values())
    assert 3 in vals, vals                          # 宏伟档必出 h=3 脊峰
    assert 2 in vals and 1 in vals
    assert len(r.hmap) <= int(0.35 * 48 * 48), len(r.hmap)   # 预算不变
    # 逐级爬升链存在：h=3 相邻 h=2、h=2 相邻 h=1、h=1 相邻平地 0
    ok3 = any(any(r.hmap.get(q) == 2 for q in nb(c)) for c, h in r.hmap.items() if h == 3)
    ok2 = any(any(r.hmap.get(q) == 1 for q in nb(c)) for c, h in r.hmap.items() if h == 2)
    ok1 = any(any(r.hmap.get(q, 0) == 0 for q in nb(c)) for c, h in r.hmap.items() if h == 1)
    assert ok3 and ok2 and ok1, 'h3→h2→h1→0 逐级爬升链必须存在'
    # 连绵性：h≥2 脊必须存在大小 ≥6 的 4 邻连通块（非散点山包）
    hi = {c for c, h in r.hmap.items() if h >= 2}
    seen, big = set(), 0
    for s in hi:
        if s in seen:
            continue
        size, comp = 0, [s]
        seen.add(s)
        while comp:
            c = comp.pop()
            size += 1
            for q in nb(c):
                if q in hi and q not in seen:
                    seen.add(q)
                    comp.append(q)
        big = max(big, size)
    assert big >= 6, f'脊必须连绵（最大连通块 {big}）'
    print("majestic ridge OK: h3=", sum(1 for v in r.hmap.values() if v == 3), "big=", big)


def test_height_cfg_roundtrip():
    r = fresh(16, height_mult=0.0, water_amt=2.0, bld_amt=None)
    inf = r.info()
    assert inf['height'] == 0.0 and inf['heightCustom'] == 0.0
    assert inf['water'] == 2.0 and inf['bldCustom'] is None
    r.build_terrain()
    assert any(v == -1 for v in r.hmap.values())             # water=2.0 必出水洼
    # 消息级（仿 test_roomcfg_extended_fields_unified 的 _cfg_sess/_cfg_room 方式）：
    import asyncio
    s = _cfg_sess(sid='s1'); r2 = _cfg_room(s); s.room = r2
    asyncio.run(serve.handle_msg(s, {'t': 'roomcfg', 'room': 'rc',
                                     'height': 0, 'water': 1.5, 'bld': 0}))
    assert r2.height_mult == 0.0 and r2.water_amt == 1.5 and r2.bld_amt == 0.0
    cap = [x for x in s.ws.sent if x.get('t') == 'cfgapplied'][-1]
    assert cap['changed'] is True
    assert sorted(cap['deferred']) == ['bld', 'height', 'water']   # 三字段同 rock：下局生效
    info2 = r2.info()
    assert info2['heightCustom'] == 0.0 and info2['waterCustom'] == 1.5 and info2['bldCustom'] == 0.0
    del serve.rooms['rc']


def _cliff_case(hmap, head, tail, d, eff=None):
    r = fresh(16); r.hmap = dict(hmap); r._reach = None
    p = mk(r, 1, "A", [head] + tail, d); p['inv'] = 0
    if eff: p['eff'] = eff
    r.step(0.05, serve.now_ms())
    return r, p


def test_cliff_move():
    # 0→2 死 cliff
    r, p = _cliff_case({(6,5): 2}, (5,5), [(4,5)], (1,0))
    assert not p['alive'] and p['cause'] == 'cliff'
    assert any(e['t']=='die' and e['cause']=='cliff' for e in r.events)
    # 0→1 活；2→0 活（下行自由）；0→9 死；0→-1 活；0→-2 活；1→3 死
    assert _cliff_case({(6,5):1}, (5,5), [(4,5)], (1,0))[1]['alive']
    r = fresh(16); r.hmap = {(5,5):2}; r._reach = None
    p = mk(r,1,"A",[(5,5),(4,5)],(1,0)); p['inv']=0
    r.step(0.05, serve.now_ms()); assert p['alive']          # 2→0
    assert not _cliff_case({(6,5):9}, (5,5), [(4,5)], (1,0))[1]['alive']
    assert _cliff_case({(6,5):-1}, (5,5), [(4,5)], (1,0))[1]['alive']
    assert _cliff_case({(6,5):-2}, (5,5), [(4,5)], (1,0))[1]['alive']
    assert not _cliff_case({(5,5):1,(6,5):3}, (5,5), [(4,5)], (1,0))[1]['alive']  # 1→3
    # shield：崖前有侧路 → 折返不死
    r, p = _cliff_case({(6,5):2}, (5,5), [(4,5)], (1,0), eff={'shield': serve.now_ms()+9999})
    assert p['alive'] and p['cells'][0] != (6,5)
    # ghost：0→9 穿越不死
    assert _cliff_case({(6,5):9}, (5,5), [(4,5)], (1,0), eff={'ghost': serve.now_ms()+9999})[1]['alive']
    # AI 前瞻：cur_h=0 时 2 视为墙（首格 (6,5) 即峭壁 → 计数 0）；cur_h=1 可沿路 9 格
    r = fresh(16); r.hmap = {(6,5):2}; r._reach = None
    assert r._open_ahead(5, 5, (1,0), cur_h=0) == 0
    assert r._open_ahead(5, 5, (1,0), cur_h=1) >= 2


def test_water_slowdown():
    r = fresh(16); r.hmap = {(5,5): -1}; r._reach = None
    p = mk(r, 1, "A", [(5,5),(4,5)], (1,0))
    assert r.tick_of(p, serve.now_ms()) == int(150 * 1.3)      # 195
    p2 = mk(r, 2, "B", [(5,8),(4,8)], (1,0))
    assert r.tick_of(p2, serve.now_ms()) == 150                # 平地不减速
    p['eff'] = {'speed': serve.now_ms()+9999}
    assert r.tick_of(p, serve.now_ms()) == int(int(150*0.6) * 1.3)   # 加速再水涉


def test_climb_slowdown_batch46():
    """批46 §2：爬坡（目标格 Δh=1）tick × 1.5；叠加序 speed → 水洼 → 爬坡 → slow"""
    # 向上爬坡（0→1）：×1.5
    r = fresh(16); r.hmap = {(6,5): 1}; r._reach = None
    p = mk(r, 1, "A", [(5,5),(4,5)], (1,0))
    assert r.tick_of(p, serve.now_ms()) == int(150 * 1.5)            # 225
    # 平地/向下：不减速
    p2 = mk(r, 2, "B", [(5,8),(4,8)], (1,0))
    assert r.tick_of(p2, serve.now_ms()) == 150
    p3 = mk(r, 3, "C", [(6,5),(6,4)], (0,-1))                        # 从 1 走向 0（下坡）
    assert r.tick_of(p3, serve.now_ms()) == 150
    # 叠加：出水洼（-1→0）不算爬坡（目标格非正向地形）→ 仅水减速
    r2 = fresh(16); r2.hmap = {(5,5): -1}; r2._reach = None
    p4 = mk(r2, 1, "A", [(5,5),(4,5)], (1,0))
    assert r2.tick_of(p4, serve.now_ms()) == int(150 * 1.3)
    # speed 先行：int(150*0.6)=90 → 爬坡 int(90*1.5)=135
    r3 = fresh(16); r3.hmap = {(6,5): 1}; r3._reach = None
    p5 = mk(r3, 1, "A", [(5,5),(4,5)], (1,0))
    p5['eff'] = {'speed': serve.now_ms()+9999}
    assert r3.tick_of(p5, serve.now_ms()) == int(int(150 * 0.6) * 1.5)


def test_fall_death_batch46():
    """批46 §2：坠落≥4 = 坠亡 cause='fall'；ghost 不豁免坠落；shield 不救坠落"""
    # 0→-4 坠亡
    r, p = _cliff_case({(6,5): -4}, (5,5), [(4,5)], (1,0))
    assert not p['alive'] and p['cause'] == 'fall'
    assert any(e['t']=='die' and e['cause']=='fall' for e in r.events)
    # 0→-3 坠落断尾不死（T3 实现断尾；此处先断言存活）
    assert _cliff_case({(6,5): -3}, (5,5), [(4,5)], (1,0))[1]['alive']
    # ghost 0→-4 也死 cause='fall'（不豁免）
    assert not _cliff_case({(6,5): -4}, (5,5), [(4,5)], (1,0),
                           eff={'ghost': serve.now_ms()+9999})[1]['alive']
    # 深渊 -9：0→-9 坠亡 cause='fall'
    r9, p9 = _cliff_case({(6,5): -9}, (5,5), [(4,5)], (1,0))
    assert not p9['alive'] and p9['cause'] == 'fall'
    # shield 不救坠落（shield 只折返碰撞类死亡）
    assert not _cliff_case({(6,5): -4}, (5,5), [(4,5)], (1,0),
                           eff={'shield': serve.now_ms()+9999})[1]['alive']
    # ghost 0→2 上行撞崖仍豁免（既有语义回归）
    assert _cliff_case({(6,5): 2}, (5,5), [(4,5)], (1,0),
                       eff={'ghost': serve.now_ms()+9999})[1]['alive']


def test_fall_cut_batch46():
    """批46 §2：落差 2~3 断 N=落差-1 节尾不死（MIN_LEN 保底，不扣分，取代常规缩尾）"""
    # 落差 2：3 节 → 2 节（断 1），存活不扣分（分数前后不变）
    r, p = _cliff_case({(6,5): -2}, (5,5), [(4,5),(3,5)], (1,0))
    assert p['alive'] and len(p['cells']) == 2
    # 落差 3：4 节 → 2 节（断 2）
    r, p = _cliff_case({(6,5): -3}, (5,5), [(4,5),(3,5),(2,5)], (1,0))
    assert p['alive'] and len(p['cells']) == 2
    # 吃果不取消坠落伤害：落差 2 + 落点有果 → 仍断 1 节，但吃果净长 +1-1（3 节吃果 → 3 节）
    r = fresh(16); r.hmap = {(6,5): -2}; r._reach = None
    r.foods = [{'id': 1, 'x': 6, 'y': 5, 'score': 10, 'color': 0}]
    p = mk(r, 1, "A", [(5,5),(4,5),(3,5)], (1,0)); p['inv'] = 0
    r.step(0.05, serve.now_ms())
    assert p['alive'] and len(p['cells']) == 3          # 吃果(+1) 断尾(-1)
    # MIN_LEN 保底：2 节蛇落差 2 → 不断（2-1=1 但 len-MIN_LEN=0）
    r, p = _cliff_case({(6,5): -2}, (5,5), [(4,5)], (1,0))
    assert p['alive'] and len(p['cells']) == 2
    # 级联：落差 2 断到 MIN_LEN 后再被咬 → 整条淘汰（cause='bite'）
    r = fresh(16); r.hmap = {(6,5): -2}; r._reach = None
    p = mk(r, 1, "A", [(5,5),(4,5),(3,5)], (1,0)); p['inv'] = 0
    r.step(0.05, serve.now_ms())                        # 断到 2 节
    assert p['alive'] and len(p['cells']) == 2


def test_spawn_h0():
    r = fresh(20)
    r.hmap = {(x, y): ((x + y) % 3) + 1 for x in range(0, 20, 3) for y in range(20)}
    r._reach = None
    p = serve.make_player(1, None, "A", "s0")
    r.players[1] = p
    r.spawn_player(p)
    assert p['cells']
    assert all(r.hmap.get(c, 0) == 0 for c in p['cells'])


def test_ghost_cross_height():
    r = fresh(16); r.hmap = {(6,5): 2}; r._reach = None        # 批46：9→2（上行崖 ghost 豁免）
    p = mk(r, 1, "A", [(5,5),(4,5)], (1,0)); p['inv'] = 0
    p['eff'] = {'ghost': serve.now_ms() + 9999}
    r.step(0.05, serve.now_ms())
    assert p['alive'] and p['cells'][0] == (6,5)


def _shot(h, x, y=5):
    return {'owner': 1, 'x': x, 'y': y, 'dx': 1, 'dy': 0, 'spd': 1.0, 'h': h}


def test_crush():
    # A 高碾压：头格h2 → 身节h1：对方整条死(crush)，kill 结算归我
    r = fresh(16); r.hmap = {(5,5):2, (6,5):1}; r._reach = None
    p1 = mk(r,1,"A",[(5,5),(4,5)],(1,0)); p2 = mk(r,2,"B",[(7,5),(6,5),(6,6)],(0,1))
    p1['inv']=p2['inv']=0
    r.step(0.05, serve.now_ms())
    assert not p2['alive'] and p2['cause']=='crush' and p2['by']==1
    assert p1['alive'] and p1.get('grow') == 2 and len(p1['cells']) == 3   # cut=3，本 tick 移动消耗 1
    assert p1['score'] == serve.BITE_SCORE_PER_CELL * 3 + serve.WIN_SCORE   # 死斗仅剩我 → check_win 加 WIN_SCORE
    assert any(e['t']=='die' and e['cause']=='crush' for e in r.events)
    # B 同高：正常咬击截断（不判死、分数照旧）
    r = fresh(16); r.hmap = {(5,5):1, (6,5):1}; r._reach = None
    p1 = mk(r,1,"A",[(5,5),(4,5)],(1,0)); p2 = mk(r,2,"B",[(7,5),(6,5),(6,6)],(0,1))
    p1['inv']=p2['inv']=0
    r.step(0.05, serve.now_ms())
    assert p2['alive'] and len(p2['cells']) == serve.MIN_LEN
    assert p1['score'] == serve.BITE_SCORE_PER_CELL
    # C 低咬高反噬：头格h0 → 身节h1：我死(crush)，对方无恙
    r = fresh(16); r.hmap = {(5,5):0, (6,5):1}; r._reach = None
    p1 = mk(r,1,"A",[(5,5),(4,5)],(1,0)); p2 = mk(r,2,"B",[(7,5),(6,5),(6,6)],(0,1))
    p1['inv']=p2['inv']=0
    r.step(0.05, serve.now_ms())
    assert not p1['alive'] and p1['cause']=='crush' and p1['by']==2
    assert p2['alive'] and len(p2['cells']) == 3
    # D head-on 异高：对头同格，高者(头格h2)活并前进，低者(头格h1)死(crush)
    r = fresh(16); r.hmap = {(5,5):2, (6,5):1, (7,5):1}; r._reach = None
    p1 = mk(r,1,"A",[(5,5),(4,5)],(1,0)); p2 = mk(r,2,"B",[(7,5),(8,5)],(-1,0))
    p1['inv']=p2['inv']=0
    r.step(0.05, serve.now_ms())
    assert p1['alive'] and p1['cells'][0] == (6,5)
    assert not p2['alive'] and p2['cause']=='crush' and p2['by']==1
    # E head-on 同高：不即时死（现有右转），双方存活
    r = fresh(16); r.hmap = {(5,5):1, (7,5):1}; r._reach = None
    p1 = mk(r,1,"A",[(5,5),(4,5)],(1,0)); p2 = mk(r,2,"B",[(7,5),(8,5)],(-1,0))
    p1['inv']=p2['inv']=0
    r.step(0.05, serve.now_ms())
    assert p1['alive'] and p2['alive']
    # F 自撞照旧死(self)
    r = fresh(16); r._reach = None
    p = mk(r,1,"A",[(5,5),(5,6),(6,6),(6,5),(5,4)],(0,-1)); p['inv']=0
    r.step(0.05, serve.now_ms())
    assert not p['alive'] and p['cause']=='self'


def test_bullet_terrain():
    now = serve.now_ms()
    step = serve.PROJ_SPEED * 1.0 * 0.05
    r = fresh(16); r.hmap = {(6,5): 1}; r._reach = None
    r.projectiles = [_shot(0, 6.0 - step + 0.1)]
    r.events.clear(); r._step_projectiles(0.05, now)
    assert r.projectiles == [] and any(e['t']=='phit' for e in r.events)   # h0遇1碎
    r.projectiles = [_shot(0, 6.0 - step + 0.1)]; r.hmap = {(6,5): 2}
    r._step_projectiles(0.05, now); assert r.projectiles == []             # 遇2碎
    r.projectiles = [_shot(0, 6.0 - step + 0.1)]; r.hmap = {(6,5): -1}
    r._step_projectiles(0.05, now); assert r.projectiles                   # 过水洼
    r.projectiles = [_shot(0, 6.0 - step + 0.1)]; r.hmap = {(6,5): -9}
    r._step_projectiles(0.05, now); assert r.projectiles                   # 深渊 -9 飞越（批46）
    r.projectiles = [_shot(1, 6.0 - step + 0.1)]; r.hmap = {(6,5): 1}
    r._step_projectiles(0.05, now); assert r.projectiles                   # 弹h1 过 1
    r.projectiles = [_shot(1, 6.0 - step + 0.1)]; r.hmap = {(6,5): 2}
    r._step_projectiles(0.05, now); assert r.projectiles == []             # 弹h1 遇 2 碎


def test_bullet_hit_range():
    now = serve.now_ms()
    step = serve.PROJ_SPEED * 1.0 * 0.05
    # 弹h2 掠过平地节(差2)：不掉血、弹继续
    r = fresh(16); r.hmap = {}; r._reach = None
    p2 = mk(r,2,"B",[(6,5),(7,5)],(1,0)); p2['inv']=0
    r.projectiles = [_shot(2, 6.0 - step + 0.1)]
    r._step_projectiles(0.05, now)
    assert len(p2['cells']) == 2 and r.projectiles
    # 弹h2 命中 h1 节(差1)：截断
    r = fresh(16); r.hmap = {(6,5): 1}; r._reach = None
    p2 = mk(r,2,"B",[(6,5),(7,5),(7,6)],(1,0)); p2['inv']=0
    r.projectiles = [_shot(2, 6.0 - step + 0.1)]
    r._step_projectiles(0.05, now)
    assert len(p2['cells']) == max(serve.MIN_LEN, 3 - serve.BULLET_CUT) and not r.projectiles
    # 弹h2 命中同层 h2 节：命中
    r = fresh(16); r.hmap = {(6,5): 2}; r._reach = None
    p2 = mk(r,2,"B",[(6,5),(7,5),(7,6)],(1,0)); p2['inv']=0
    r.projectiles = [_shot(2, 6.0 - step + 0.1)]
    r._step_projectiles(0.05, now)
    assert not r.projectiles
    # 发弹记 h：try_ult 全部弹带发射者头格高
    r = fresh(16); r.hmap = {(5,5):1}; r._reach = None
    p = mk(r,1,"A",[(5,5),(4,5)],(1,0)); p['inv']=0; p['ult']=100
    r.try_ult(p, serve.now_ms())
    assert r.projectiles and all(pr['h']==1 for pr in r.projectiles)


def test_snapshot_height():
    now = serve.now_ms()
    r = fresh(16); r.hmap = {(3,3): 2}; r._reach = None
    full = r.snapshot(now, full=True)
    assert full['hmap'] == [[3, 3, 2]]
    r.projectiles = [{'owner': 1, 'x': 1.0, 'y': 1.0, 'dx': 1, 'dy': 0, 'spd': 1.0, 'h': 2}]
    r.snapshot(now)                       # 建立增量基线
    r.hmap[(4, 4)] = 1                    # 地形变了
    s = r.snapshot(now)
    assert [4, 4, 1] in s['hmap'] and [3, 3, 2] in s['hmap']
    s2 = r.snapshot(now)                  # 未变 → 不带
    assert 'hmap' not in s2
    assert s['proj'][0]['h'] == 2         # 弹道高度字段随每帧 proj 下发
    src = open('serve.py', encoding='utf-8').read()
    html = open('index.html', encoding='utf-8').read()
    # 双端协议号必须一致且等于服务端常量（批35 起改为动态读，bump 协议不必再改本测试）
    v = serve.PROTO_VER
    assert f'PROTO_VER = {v}' in src, v
    assert f'const PROTO_VER = {v}' in html, v


def test_reactions_table_complete_batch33():
    pairs = {
        ('pyro', 'hydro'): 'vaporize', ('hydro', 'pyro'): 'vaporize',
        ('pyro', 'cryo'): 'melt', ('cryo', 'pyro'): 'melt',
        ('pyro', 'electro'): 'overload', ('electro', 'pyro'): 'overload',
        ('hydro', 'cryo'): 'frozen', ('cryo', 'hydro'): 'frozen',
        ('hydro', 'electro'): 'electro', ('electro', 'hydro'): 'electro',
        ('cryo', 'electro'): 'superconduct', ('electro', 'cryo'): 'superconduct',
    }
    assert len(serve.ELEMS) == 4 and set(serve.ELEMS) == {'pyro', 'hydro', 'cryo', 'electro'}
    for (a, b), kind in pairs.items():
        assert serve.reaction_of(a, b) == kind, ((a, b), kind)


def test_reaction_same_or_none_elem_batch33():
    assert serve.reaction_of('pyro', 'pyro') is None
    assert serve.reaction_of('pyro', None) is None
    assert serve.reaction_of(None, 'hydro') is None


def test_aura_snapshot_and_ttl_batch33():
    r = fresh()
    p = mk(r, 1, 'a', [(1, 1), (1, 2), (1, 3)], (1, 0))
    now = serve.now_ms()
    r.set_aura(p, 'pyro', now)
    assert r.aura_of(p, now) == 'pyro'
    a = [x for x in r.snapshot(now)['players'] if x['id'] == 1][0]['aura']
    assert a == {'e': 'pyro', 't': serve.AURA_MS}, a
    # TTL 过期 → 无 aura、快照 None
    later = now + serve.AURA_MS + 1
    assert r.aura_of(p, later) is None
    a2 = [x for x in r.snapshot(later)['players'] if x['id'] == 1][0]['aura']
    assert a2 is None, a2


def test_spawn_clears_aura_keeps_on_off_batch33():
    r = fresh()
    p = mk(r, 1, 'a', [(1, 1), (1, 2), (1, 3)], (1, 0))
    now = serve.now_ms()
    r.set_aura(p, 'hydro', now)
    r.consume_aura(p)
    assert r.aura_of(p, now) is None, 'consume 后必须无 aura'
    # 重生清 aura
    r.set_aura(p, 'cryo', now)
    r.spawn_player(p)
    assert r.aura_of(p, serve.now_ms()) is None, '重生必须清 aura'
    # 挂起（off_at）不清 aura
    r.set_aura(p, 'cryo', serve.now_ms())
    p['off_at'] = serve.now_ms()
    assert r.aura_of(p, serve.now_ms()) == 'cryo', '挂起不应清 aura'


def test_eterrain_constraints_batch33():
    r = fresh(size=40, elem_amt=1.0)   # 预算 40*40*1.5%*1.0=24 格 → ≥6 簇，round-robin 必覆盖四元素
    assert r.eterrain, 'elem_amt=1.0 必须生成元素地形'
    assert len(r.eterrain) <= 60, len(r.eterrain)
    hard = set(r.rocks) | set(r.walls) | set(r.portals)
    for (x, y), el in r.eterrain.items():
        assert el in serve.ELEMS, el
        assert (x, y) not in hard, ((x, y), 'eterrain 压硬障碍')
        assert r.hmap.get((x, y), 0) in (0, -1, -2), ((x, y), 'eterrain 压非平/水/草')
    assert set(r.eterrain.values()) == set(serve.ELEMS), '四元素必须都有'
    # 关闭开关 → 不生成
    r2 = fresh(size=20, elements=False, elem_amt=1.0)
    assert not r2.eterrain, 'elements=False 不得生成'


def test_eterrain_attach_and_spawn_avoid_batch33():
    r = fresh(size=20, elem_amt=1.0)
    assert r.eterrain
    # spawn 主路径 + 兜底都避开 eterrain
    p = mk(r, 1, 'a', [(0, 0), (0, 1), (0, 2)], (1, 0))
    r.spawn_player(p)
    assert all(c not in r.eterrain for c in p['cells']), p['cells']
    # 蛇头走到 eterrain 格 → 踩格替换：附着该元素（覆盖旧 aura、时长重置）
    tgt, el = next(((c, e) for c, e in r.eterrain.items() if c[0] >= 3), (None, None))
    if tgt is None:
        # 构造性消除随机（同 P7 做法）：20×20 只撒 6 格，偶发全落 x<3 列时本例会红；
        # 且本例依赖前序测试残留的全局 RNG 状态（test_game.py:1931 有 random.seed(42)），
        # 孤立运行失败率 1/300、进套件后被放大 → 落点条件改由测试自己钉死。
        tgt, el = (5, 5), 'hydro'
        r.eterrain[tgt] = el
    assert tgt, '需要一个 x>=3 的元素格做测试落点'
    r.set_aura(p, 'pyro', serve.now_ms())
    p['cells'] = [(tgt[0] - 1, tgt[1]), (tgt[0] - 2, tgt[1]), (tgt[0] - 3, tgt[1])]
    p['dir'] = (1, 0)
    p['queue'] = []
    now = serve.now_ms()
    p['last_move'] = now - 999
    r.step(0.05, now)
    assert p['cells'][0] == tgt, p['cells']
    assert r.aura_of(p, now) == el, '进格必须附着 eterrain 元素（替换旧 aura）'


def test_eterrain_full_and_delta_batch33():
    r = fresh(size=20, elem_amt=1.0)
    now = serve.now_ms()
    full = r.snapshot(now, full=True)
    assert 'eterrain' in full, full.keys()
    assert all(len(t) == 3 and t[2] in serve.ELEMS for t in full['eterrain'])
    r.snapshot(now)                       # 建立增量基线
    r.eterrain[(3, 3)] = 'pyro'           # 变化 → DELTA 必须带三元组
    s = r.snapshot(now)
    assert [3, 3, 'pyro'] in s.get('eterrain', []), s.get('eterrain')
    s2 = r.snapshot(now)
    assert 'eterrain' not in s2, '未变不得重复下发'


def test_bite_reaction_all_six_batch33():
    r = fresh(16)
    now = serve.now_ms()

    def pair():
        r.players.clear()
        r.events.clear()
        a = mk(r, 1, 'A', [(1, 1), (1, 2), (1, 3)], (1, 0))
        b = mk(r, 2, 'B', [(5, 5), (5, 6), (5, 7)], (1, 0))
        a['inv'] = b['inv'] = 0
        return a, b

    # frozen：受害者冻结 1.6s，不截短，双方双消
    a, b = pair()
    r.set_aura(a, 'cryo', now); r.set_aura(b, 'hydro', now)
    r.apply_reaction(a, b, 'frozen', 5, 5, now)
    assert b['eff']['frozen'] == now + serve.FROZEN_MS, b['eff']
    assert len(b['cells']) == 3, 'frozen 不截短'
    assert r.aura_of(a, now) is None and r.aura_of(b, now) is None, '反应双方双消'
    assert any(e['t'] == 'react' and e['kind'] == 'frozen' for e in r.events)
    # vaporize：victim -1（MIN_LEN 保护）
    a, b = pair()
    r.set_aura(a, 'pyro', now); r.set_aura(b, 'hydro', now)
    r.apply_reaction(a, b, 'vaporize', 5, 5, now)
    assert len(b['cells']) == 2, b['cells']
    a['cells'].append((1, 4))   # 还原 3 格
    # melt：victim -1
    a, b = pair()
    r.set_aura(a, 'pyro', now); r.set_aura(b, 'cryo', now)
    r.apply_reaction(a, b, 'melt', 5, 5, now)
    assert len(b['cells']) == 2, b['cells']
    # overload：半径1 内其他蛇各 -1，攻击者免疫（攻击者头就在半径1）
    a, b = pair()
    c = mk(r, 3, 'C', [(4, 5), (4, 6), (4, 7)], (0, 1))
    d = mk(r, 4, 'D', [(7, 7), (7, 8), (7, 9)], (0, 1))
    a['cells'] = [(5, 4), (5, 3), (5, 2)]     # A 头贴影响点 (5,5) → 必须免疫
    c['inv'] = d['inv'] = 0
    r.set_aura(a, 'pyro', now); r.set_aura(b, 'electro', now)
    r.apply_reaction(a, b, 'overload', 5, 5, now)
    assert len(b['cells']) == 2 and len(c['cells']) == 2, (b['cells'], c['cells'])
    assert len(a['cells']) == 3, '攻击者免疫超载'
    assert len(d['cells']) == 3, '半径外不受波及'
    # electro：victim + 曼哈顿≤2 内 id 序最小另一条各 -1
    a, b = pair()
    c = mk(r, 3, 'C', [(5, 7), (5, 8), (5, 9)], (0, 1))   # dist 2, id=3
    d = mk(r, 4, 'D', [(7, 5), (7, 6), (7, 7)], (0, 1))   # dist 2, id=4 → 不该中
    e4 = mk(r, 5, 'E', [(8, 5), (8, 6), (8, 7)], (0, 1))  # dist 3 → 不中
    c['inv'] = d['inv'] = e4['inv'] = 0
    r.set_aura(a, 'hydro', now); r.set_aura(b, 'electro', now)
    r.apply_reaction(a, b, 'electro', 5, 5, now)
    assert len(b['cells']) == 2, b['cells']
    assert len(c['cells']) == 2, 'id 序最小的近邻(id=3)中感电'
    assert len(d['cells']) == 3, 'id 更大不中（确定性）'
    assert len(e4['cells']) == 3, '距离 3 不中'
    # superconduct：半径2 全体 slow（含 victim），attacker 距离外
    a, b = pair()
    c = mk(r, 3, 'C', [(7, 5), (7, 6), (7, 7)], (0, 1))   # dist 2
    d = mk(r, 4, 'D', [(8, 5), (8, 6), (8, 7)], (0, 1))   # dist 3
    c['inv'] = d['inv'] = 0
    r.set_aura(a, 'cryo', now); r.set_aura(b, 'electro', now)
    r.apply_reaction(a, b, 'superconduct', 5, 5, now)
    assert b['eff'].get('slow') == now + serve.SLOW_MS, b['eff']
    assert c['eff'].get('slow') == now + serve.SLOW_MS, '半径2 内应减速'
    assert 'slow' not in d['eff'], '半径外不减速'


def test_reaction_dual_consume_and_infect_batch33():
    # 传染：A 有 aura、B 无 → 咬中后 B 获 aura、A 消耗、不触发反应
    r = fresh(16)
    r.eterrain = {}      # 批33修：seed(42) 后 Room eterrain 确定性落格，步进踩格会重新附着干扰断言
    now = serve.now_ms()
    p1 = mk(r, 1, 'A', [(5, 5), (4, 5)], (1, 0))
    p2 = mk(r, 2, 'B', [(7, 5), (6, 5), (6, 6)], (0, 1))
    p1['inv'] = p2['inv'] = 0
    r.set_aura(p1, 'pyro', now)
    r.events.clear()
    r.step(0.05, now)
    assert p2['alive'] and len(p2['cells']) == serve.MIN_LEN, p2['cells']
    assert r.aura_of(p2, now) == 'pyro', '传染：被咬方获得攻击方元素'
    assert r.aura_of(p1, now) is None, '传染：攻击方 aura 消耗'
    assert not any(e['t'] == 'react' for e in r.events), '同侧无异元素不触发反应'
    # 反应：异元素咬击 → ev react + 双消 + 蒸发额外 -1 + 截短不计分不并 grow
    r2 = fresh(16)
    r2.eterrain = {}     # 批33修：同上，避免 A 步进踩 pyro 地形重新附着（踩格替换是正确行为）
    now2 = serve.now_ms()
    a = mk(r2, 1, 'A', [(5, 8), (4, 8), (3, 8)], (1, 0))
    b = mk(r2, 2, 'B', [(7, 5), (6, 5), (6, 6), (6, 7), (6, 8), (6, 9)], (0, 1))
    a['inv'] = b['inv'] = 0
    r2.set_aura(a, 'pyro', now2)
    r2.set_aura(b, 'hydro', now2)
    r2.events.clear()
    r2.step(0.05, now2)
    react = [e for e in r2.events if e['t'] == 'react']
    assert react and react[0]['kind'] == 'vaporize', r2.events
    assert react[0]['by'] == 1 and react[0]['victim'] == 2, react[0]
    # 咬点 idx=4 → keep=4（bite cut=2）→ 蒸发再 -1 → 3
    assert len(b['cells']) == 3, b['cells']
    assert r2.aura_of(a, now2) is None and r2.aura_of(b, now2) is None, (
        '反应双消', a.get('aura'), b.get('aura'), dict(r2.eterrain),
        list(a['cells']), list(b['cells']), r2.events)
    # 反应截短不并入 grow 不计分：grow=2（咬击）-1（本 tick 消耗），score=2×BITE（无额外）
    assert a.get('grow', 0) == 1, a.get('grow')
    assert a['score'] == 2 * serve.BITE_SCORE_PER_CELL, a['score']


def test_react_charge_and_dead_degrade_batch33():
    r = fresh(16)
    now = serve.now_ms()

    def pair():
        r.players.clear(); r.events.clear()
        a = mk(r, 1, 'A', [(1, 1), (1, 2), (1, 3)], (1, 0))
        b = mk(r, 2, 'B', [(5, 5), (5, 6), (5, 7)], (1, 0))
        a['inv'] = b['inv'] = 0
        return a, b
    # 充能 +15 封顶
    a, b = pair()
    a['ult'] = 95
    r.set_aura(a, 'pyro', now); r.set_aura(b, 'cryo', now)
    r.apply_reaction(a, b, 'melt', 5, 5, now)
    assert a['ult'] == serve.ULT_MAX, a['ult']
    # attacker 已死 → 效果在、跳充能
    a, b = pair()
    a['alive'] = False
    a['ult'] = 0
    r.set_aura(a, 'pyro', now); r.set_aura(b, 'cryo', now)
    r.apply_reaction(a, b, 'melt', 5, 5, now)
    assert len(b['cells']) == 2, 'attacker 已死效果照常'
    assert a['ult'] == 0, 'attacker 已死不充能'
    # victim 已死 → 纯视觉：只 ev，不写效果、不充能、不消耗
    a, b = pair()
    b['alive'] = False
    a['ult'] = 0
    r.set_aura(a, 'pyro', now); r.set_aura(b, 'cryo', now)
    r.apply_reaction(a, b, 'frozen', 5, 5, now)
    assert any(e['t'] == 'react' and e['kind'] == 'frozen' for e in r.events), '纯视觉 ev 必须在'
    assert 'frozen' not in b.get('eff', {}), '已死不写效果'
    assert a['ult'] == 0, '已死降级不充能'
    assert r.aura_of(a, now) == 'pyro', '纯视觉降级不消耗攻击方 aura'


def test_crush_result_unchanged_batch33():
    # 高低差碾压 + 异 aura：cause=crush 照旧，反应走已死降级（纯视觉 ev）
    r = fresh(16)
    r.hmap = {(5, 5): 2, (6, 5): 1}
    r._reach = None
    now = serve.now_ms()
    p1 = mk(r, 1, 'A', [(5, 5), (4, 5)], (1, 0))
    p2 = mk(r, 2, 'B', [(7, 5), (6, 5), (6, 6)], (0, 1))
    p1['inv'] = p2['inv'] = 0
    r.set_aura(p1, 'cryo', now)
    r.set_aura(p2, 'hydro', now)
    p1['ult'] = 0
    r.events.clear()
    r.step(0.05, now)
    assert not p2['alive'] and p2['cause'] == 'crush' and p2['by'] == 1, (p2['alive'], p2.get('cause'))
    react = [e for e in r.events if e['t'] == 'react']
    assert react and react[0]['kind'] == 'frozen', r.events
    assert 'frozen' not in p2.get('eff', {}), '已死降级不写效果'
    # 碾压路自己的 ULT_KILL 照给（30）；victim 已死 → 无 ULT_REACT（有则 45）
    assert p1['ult'] == serve.ULT_KILL, p1['ult']


# ---- 批33：元素弹（eb） ----
def test_eb_attach_and_cd_batch33():
    """批33：元素弹发射——白名单/独立CD/元素开关/暂停/冻结门禁 + fire ev 带 elem + 快照带 elem"""
    import asyncio
    r = fresh(12)
    sess = _cfg_sess(sid='e1', user=None, room=r)
    p = mk(r, 1, 'Me', [(4, 4), (4, 5)], (1, 0))
    p['session'] = sess
    sess.pid = 1
    r.events.clear()
    asyncio.run(serve.handle_msg(sess, {'t': 'eb', 'elem': 'hydro'}))
    assert len(r.projectiles) == 1 and r.projectiles[0]['elem'] == 'hydro', r.projectiles
    assert r.projectiles[0]['spd'] == serve.EB_SPD, r.projectiles[0]
    assert any(e['t'] == 'fire' and e.get('elem') == 'hydro' for e in r.events), r.events
    snap = r.snapshot(serve.now_ms())
    assert snap['proj'][0].get('elem') == 'hydro', snap['proj']
    # 独立 CD：EB_CD 内二发被拒
    asyncio.run(serve.handle_msg(sess, {'t': 'eb', 'elem': 'pyro'}))
    assert len(r.projectiles) == 1, "EB_CD 内二发应拒"
    # 白名单：非四元素拒
    p['eb_at'] = 0
    asyncio.run(serve.handle_msg(sess, {'t': 'eb', 'elem': 'geo'}))
    assert len(r.projectiles) == 1, "非白名单元素应拒"
    # elements 总开关拒
    r.elements = False
    asyncio.run(serve.handle_msg(sess, {'t': 'eb', 'elem': 'pyro'}))
    assert len(r.projectiles) == 1, "elements=False 应拒"
    r.elements = True
    # 暂停拒
    p['pause'] = True
    asyncio.run(serve.handle_msg(sess, {'t': 'eb', 'elem': 'pyro'}))
    assert len(r.projectiles) == 1, "暂停应拒"
    p.pop('pause')
    # 冻结拒（M2：冻结中不开火）
    p['eff']['frozen'] = serve.now_ms() + 9999
    asyncio.run(serve.handle_msg(sess, {'t': 'eb', 'elem': 'pyro'}))
    assert len(r.projectiles) == 1, "冻结应拒"
    p['eff'].pop('frozen')
    # 门禁解除后可发射
    p['eb_at'] = 0
    asyncio.run(serve.handle_msg(sess, {'t': 'eb', 'elem': 'pyro'}))
    assert len(r.projectiles) == 2, "解除门禁后应可发射"
    print("eb attach cd batch33 OK")


def test_eb_hit_attach_refresh_batch33():
    """批33：元素弹命中——无 aura 附着不截短/同元素刷新 TTL/异元素走反应（截短+双消+充能）"""
    r = fresh(12)
    now = serve.now_ms()
    a = mk(r, 1, 'A', [(7, 4), (7, 5)], (1, 0))          # 射手
    v = mk(r, 2, 'V', [(5, 4), (5, 5), (5, 6)], (1, 0))  # 受害者 3 格
    a['inv'] = v['inv'] = 0
    # ① 无 aura 命中 → 附着，不截短
    r.projectiles.append({'owner': 1, 'x': 5.0, 'y': 4.0, 'dx': -1, 'dy': 0,
                          'spd': serve.EB_SPD, 'h': 0, 'elem': 'hydro'})
    r._step_projectiles(0.001, now)
    assert not r.projectiles, "命中后弹应消"
    assert r.aura_of(v, now) == 'hydro', v.get('aura')
    assert len(v['cells']) == 3, "基础附着不截短"
    # ② 同元素刷新：旧 TTL 拨到快过期，命中后重置
    v['aura']['at'] = now - serve.AURA_MS + 100
    r.projectiles.append({'owner': 1, 'x': 5.0, 'y': 4.0, 'dx': -1, 'dy': 0,
                          'spd': serve.EB_SPD, 'h': 0, 'elem': 'hydro'})
    r._step_projectiles(0.001, now + 50)
    assert v['aura']['at'] == now + 50, "同元素命中应刷新 TTL"
    # ③ 异元素 → vaporize（水×火）：victim -1、双消、射手充能、ev react
    r.events.clear()
    a['ult'] = 0
    r.projectiles.append({'owner': 1, 'x': 5.0, 'y': 4.0, 'dx': -1, 'dy': 0,
                          'spd': serve.EB_SPD, 'h': 0, 'elem': 'pyro'})
    r._step_projectiles(0.001, now + 100)
    assert len(v['cells']) == 2, "蒸发应截 1"
    assert r.aura_of(v, now + 100) is None and r.aura_of(a, now + 100) is None, "反应双消"
    assert a['ult'] == serve.ULT_REACT, "触发方应充能"
    assert any(e['t'] == 'react' and e['kind'] == 'vaporize' for e in r.events), r.events
    print("eb hit attach refresh batch33 OK")


def test_eb_no_rock_and_gates_batch33():
    """批33：元素弹触岩消散（不碎岩不计分）；普通弹对照照碎；高度挡弹对元素弹同样生效"""
    r = fresh(12)
    now = serve.now_ms()
    a = mk(r, 1, 'A', [(7, 4)], (1, 0))
    r.rocks = [(5, 4)]
    r._reach = None
    r.events.clear()
    # 元素弹触岩 → 弹消、岩在、无分、无 rock ev
    r.projectiles.append({'owner': 1, 'x': 5.0, 'y': 4.0, 'dx': -1, 'dy': 0,
                          'spd': serve.EB_SPD, 'h': 0, 'elem': 'hydro'})
    r._step_projectiles(0.001, now)
    assert not r.projectiles, "元素弹触岩应消散"
    assert r.rocks == [(5, 4)], "元素弹不应碎岩"
    assert a['score'] == 0, "元素弹不该计分"
    assert not any(e['t'] == 'rock' for e in r.events), r.events
    # 普通弹对照：照碎照计分
    r.projectiles.append({'owner': 1, 'x': 5.0, 'y': 4.0, 'dx': -1, 'dy': 0,
                          'spd': 1.0, 'h': 0})
    r._step_projectiles(0.001, now)
    assert not r.rocks and a['score'] == 5, (r.rocks, a['score'])
    # 高度挡弹同样生效：地形 h=2 > 弹 h=0 → phit 消散
    r.hmap = {(4, 4): 2}
    r._reach = None
    r.projectiles.append({'owner': 1, 'x': 4.5, 'y': 4.0, 'dx': -1, 'dy': 0,
                          'spd': serve.EB_SPD, 'h': 0, 'elem': 'cryo'})
    r._step_projectiles(0.0001, now)
    assert not r.projectiles, "元素弹应被高地形挡下"
    print("eb no rock gates batch33 OK")


def test_eb_cross_layer_batch33():
    """批33：跨层不命中——弹 h=2 飞过地面蛇不附着不截短（沿用批32 |节h-弹h|≤1）"""
    r = fresh(12)
    now = serve.now_ms()
    mk(r, 1, 'A', [(7, 4)], (1, 0))
    v = mk(r, 2, 'V', [(5, 4), (5, 5)], (1, 0))
    v['inv'] = 0
    r.projectiles.append({'owner': 1, 'x': 5.0, 'y': 4.0, 'dx': -1, 'dy': 0,
                          'spd': serve.EB_SPD, 'h': 2, 'elem': 'hydro'})
    r._step_projectiles(0.001, now)
    assert r.aura_of(v, now) is None, "跨层不该附着"
    assert len(v['cells']) == 2, "跨层不该截短"
    assert r.projectiles, "跨层弹应继续飞行"
    print("eb cross layer batch33 OK")


# ---- 批33：frozen / slow eff 接线 ----
def test_frozen_no_move_and_resume_batch33():
    """frozen：due 排除原地不动，FROZEN_MS 到期恢复移动"""
    r = fresh(16)
    r.eterrain = {}
    now = serve.now_ms()
    p = mk(r, 1, 'A', [(5, 5), (5, 6)], (1, 0))
    p['eff']['frozen'] = now + serve.FROZEN_MS
    cells0 = list(p['cells'])
    for _ in range(4):
        now += 150
        r.step(0.05, now)
    assert [tuple(c) for c in p['cells']] == cells0, "冻结期间应原地不动"
    # 到期 → 恢复移动
    p['eff']['frozen'] = now + 50
    r.step(0.05, now + 200)
    assert tuple(p['cells'][0]) != cells0[0], "解冻后应恢复移动"
    print("frozen no move resume batch33 OK")


def test_frozen_head_static_obstacle_batch33():
    """决策16：冻结头=静止障碍——活蛇对头 force_right 避让，冻结蛇不转向不死不计 hstreak"""
    r = fresh(16)
    r.eterrain = {}
    now = serve.now_ms()
    f = mk(r, 2, 'F', [(5, 5), (5, 6)], (0, 1))
    f['eff']['frozen'] = now + serve.FROZEN_MS * 2
    a = mk(r, 1, 'A', [(3, 5), (3, 6)], (1, 0))
    a['last_move'] = f['last_move'] = 0
    # a 走到 (4,5)：下一 tent 与 F 头对头 → a 右转避让
    r.step(0.05, now)
    r.step(0.05, now + 150)
    assert tuple(a['dir']) == (0, 1), f"活蛇应对冻结头右转避让 {a['dir']}"
    assert a['alive'] and f['alive'], "双方都不该死"
    assert tuple(f['dir']) == (0, 1), "冻结蛇不该被转向"
    assert f['cells'] == [(5, 5), (5, 6)], "冻结蛇应原地"
    assert not f.get('hstreak'), "冻结蛇不累计 hstreak（决策16）"
    print("frozen head obstacle batch33 OK")


def test_frozen_input_gate_batch33():
    """决策17：frozen 期间 dir/atk/ult/eb 拒收"""
    import asyncio
    r = fresh(12)
    r.eterrain = {}
    sess = _cfg_sess(sid='f1', user=None, room=r)
    p = mk(r, 1, 'Me', [(4, 4), (4, 5)], (1, 0))
    p['session'] = sess
    sess.pid = 1
    p['eff']['frozen'] = serve.now_ms() + serve.FROZEN_MS
    p['ult'] = serve.ULT_MAX
    asyncio.run(serve.handle_msg(sess, {'t': 'dir', 'x': 0, 'y': 1}))
    assert not p['queue'], "冻结中不该入队"
    asyncio.run(serve.handle_msg(sess, {'t': 'atk'}))
    asyncio.run(serve.handle_msg(sess, {'t': 'eb', 'elem': 'hydro'}))
    assert not r.projectiles, "冻结中不该开火"
    asyncio.run(serve.handle_msg(sess, {'t': 'ult'}))
    assert p['ult'] == serve.ULT_MAX, "冻结中不该放大招"
    # 解冻后恢复
    p['eff']['frozen'] = serve.now_ms() - 1
    asyncio.run(serve.handle_msg(sess, {'t': 'dir', 'x': 0, 'y': 1}))
    assert p['queue'], "解冻后应恢复入队"
    print("frozen input gate batch33 OK")


def test_frozen_biteable_batch33():
    """frozen 可被咬（不套 _protected）：截断照常生效"""
    r = fresh(16)
    r.eterrain = {}
    now = serve.now_ms()
    f = mk(r, 2, 'F', [(8, 5), (8, 6), (8, 7), (8, 8)], (0, 1))
    f['eff']['frozen'] = now + serve.FROZEN_MS
    f['inv'] = 0
    a = mk(r, 1, 'A', [(7, 6), (6, 6)], (1, 0))
    r.step(0.05, now)
    assert len(f['cells']) < 4 and f['alive'], f"冻结蛇应被截断但不致死 {f['cells']}"
    print("frozen biteable batch33 OK")


def test_slow_tick_multiplier_batch33():
    """slow：tick_of speed 结算后再 ×1.5；到期复原"""
    r = fresh(16)
    now = serve.now_ms()
    p = mk(r, 1, 'A', [(5, 5)], (1, 0))
    p['tick'] = 100
    assert r.tick_of(p, now) == 100
    p['eff']['slow'] = now + serve.SLOW_MS
    assert r.tick_of(p, now) == 150, "slow 应 ×1.5"
    p['eff']['speed'] = now + serve.SLOW_MS
    assert r.tick_of(p, now) == int(60 * 1.5), "speed 后再乘（可叠加）"
    assert r.tick_of(p, now + serve.SLOW_MS) == 100, "到期复原"
    print("slow tick multiplier batch33 OK")


def test_elements_roomcfg_and_persist_batch33():
    """T7：elements/elem_amt 四 ingress——roomcfg 生效、create 透传、persist 往返、旧档缺字段默认 True/0.6"""
    import asyncio
    import json
    import os
    # 默认值
    r0 = fresh(16)
    assert (r0.elements, r0.elem_amt) == (True, 0.6)
    # info() 回传
    d = r0.info()
    assert d['elements'] is True and d['elemAmt'] == 0.6
    # roomcfg 改 False/0 生效（live，下局生效 eterrain 由 elements 控制）
    s = _cfg_sess(sid='s1')
    serve.rooms['rel'] = serve.Room('rel', '元素房', 16)
    r = serve.rooms['rel']
    asyncio.run(serve.handle_msg(s, {'t': 'roomcfg', 'room': 'rel',
                                     'elements': False, 'elemAmt': 0}))
    assert (r.elements, r.elem_amt) == (False, 0.0), (r.elements, r.elem_amt)
    # 非法值忽略不动原值
    asyncio.run(serve.handle_msg(s, {'t': 'roomcfg', 'room': 'rel',
                                     'elements': 'x', 'elemAmt': 'bad'}))
    assert (r.elements, r.elem_amt) == (False, 0.0)
    # elemAmt clamp 0-2
    asyncio.run(serve.handle_msg(s, {'t': 'roomcfg', 'room': 'rel', 'elemAmt': 9}))
    assert r.elem_amt == 2.0
    # create 透传
    s2 = _cfg_sess(sid='s2')
    s2.ip = '9.9.9.9'
    asyncio.run(serve.handle_msg(s2, {'t': 'create', 'name': 'e1',
                                      'elements': False, 'elemAmt': 1.5}))
    created = [x for x in s2.ws.sent if x.get('t') == 'created']
    assert created, s2.ws.sent
    rc = serve.rooms[created[0]['room']]
    assert (rc.elements, rc.elem_amt) == (False, 1.5), (rc.elements, rc.elem_amt)
    del serve.rooms[created[0]['room']]
    # persist 保存→恢复往返保留
    path = os.path.join(os.environ.get('TEMP', '.'), 't_persist_elem.json')
    try:
        r.persist = True
        serve.save_persist_rooms(path)
        serve.rooms.pop('rel')
        assert serve.load_persist_rooms(path) == 1
        rr = serve.rooms.get('rel')
        assert rr is not None and (rr.elements, rr.elem_amt) == (False, 2.0)
        del serve.rooms['rel']
        # 旧档缺字段 → 默认 True/0.6（M3：升级不静默关元素）
        with open(path, encoding='utf-8') as f:
            lst = json.load(f)
        for d2 in lst:
            d2.pop('elements', None)
            d2.pop('elemAmt', None)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(lst, f)
        assert serve.load_persist_rooms(path) == 1
        ro = serve.rooms.get('rel')
        assert ro is not None and (ro.elements, ro.elem_amt) == (True, 0.6)
        del serve.rooms['rel']
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    print("elements roomcfg/persist batch33 OK")


# ---- 批36 P0：store.json 落盘节流（热路径 inc 不再逐次整份重写） ----

def test_store_inc_throttled_batched_save():
    """批36 建议1（先红后绿）：inc 只标脏 + 节流批量落盘。
刚落过盘的节流窗内连发 inc 不得重写 store.json（哨兵必须幸存）；
节流窗过期后的 inc 自动落盘；save() 兜底 flush。"""
    import json as _json
    import tempfile
    from pathlib import Path
    p = Path(tempfile.mkdtemp(prefix='snake-store-throttle-')) / 'store.json'
    st = serve.Store(p)
    ok, err = st.register('alice', '123456')
    assert ok, err
    # 哨兵：与内存状态(food=0)不一致——任何一次真实写盘都会把它抹掉
    raw = p.read_text('utf-8').replace('"food": 0', '"food": 999')
    assert '"food": 999' in raw, '哨兵注入失败（夹具问题）'
    p.write_text(raw, 'utf-8')
    st._last = time.time()                      # 刚落过盘 → 处于节流窗内
    for _ in range(5):
        st.inc('alice', 'food')
    assert '"food": 999' in p.read_text('utf-8'), '节流窗内 inc 不得重写 store.json'
    assert st._dirty is True, 'inc 后必须标脏'
    st._last = time.time() - (serve.STORE_SAVE_INTERVAL + 1)   # 窗口过期
    st.inc('alice', 'food')
    assert st._dirty is False, '窗口过期落盘后脏标记清零'
    data = _json.loads(p.read_text('utf-8'))
    assert data['alice']['stats']['food'] == 6, '窗口过期的 inc 必须落盘'
    st.inc('alice', 'food')                     # 再次标脏
    st.save()                                   # 兜底 flush（关停路径同款）
    assert _json.loads(p.read_text('utf-8'))['alice']['stats']['food'] == 7


def test_store_record_best_and_shutdown_flush():
    """批36 建议1（先红后绿）：record_best 同样标脏不逐次写；
shutdown_settle() 必须 flush 脏数据——否则节流窗内的战绩在优雅关停时丢失。"""
    import json as _json
    import tempfile
    from pathlib import Path
    p = Path(tempfile.mkdtemp(prefix='snake-store-flush-')) / 'store.json'
    keep = serve.store
    try:
        serve.store = serve.Store(p)
        ok, err = serve.store.register('bob', '135792')
        assert ok, err
        raw = p.read_text('utf-8').replace('"best": 0', '"best": 999')
        assert '"best": 999' in raw, '哨兵注入失败（夹具问题）'
        p.write_text(raw, 'utf-8')
        serve.store._last = time.time()         # 节流窗内
        serve.store.record_best('bob', 42)
        assert '"best": 999' in p.read_text('utf-8'), '节流窗内 record_best 不得重写 store.json'
        assert serve.store._dirty is True, 'record_best 后必须标脏'
        serve.shutdown_settle()                 # 优雅关停路径必须 flush
        assert serve.store._dirty is False, 'shutdown_settle 后脏数据必须已落盘'
        data = _json.loads(p.read_text('utf-8'))
        assert data['bob']['stats']['best'] == 42, '关停 flush 后 best 必须在盘上'
    finally:
        serve.store = keep


# ---- 批36 P0-2：写盘安全（原子写 + 损坏留证） ----

def test_store_load_corrupt_backs_up_before_reset():
    """批36 建议2（先红后绿）：store.json 损坏时先备份 .corrupt-<时间戳> 再兜底空表。
原实现静默 users={} 等于清空全服账号且不留任何证据。"""
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp(prefix='snake-store-corrupt-'))
    p = d / 'store.json'
    p.write_text('{oops not json', 'utf-8')
    st = serve.Store(p)
    assert st.users == {}, '兜底仍是空表（服务必须能起来）'
    bak = sorted(d.glob('store.json.corrupt-*'))
    assert bak, '损坏文件必须先备份为 .corrupt-<时间戳> 再兜底'
    assert bak[0].read_text('utf-8') == '{oops not json', '备份必须保留原始内容'


def test_save_persist_rooms_atomic_on_failure():
    """批36 建议2（先红后绿）：persist 房间写盘改 tmp+replace 原子写——
序列化中途失败时不得截断/污染既有文件、不得向上抛异常、不得留半截 tmp。"""
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp(prefix='snake-persist-atomic-'))
    p = d / 'persist_rooms.json'
    keep_rooms, keep_dump = dict(serve.rooms), serve.persist_rooms_dump
    try:
        r = serve.Room('pa', 'pa', 20)
        r.persist = True
        serve.rooms['pa'] = r
        assert serve.save_persist_rooms(str(p)) is True, '夹具：应先写出一份正常文件'
        good = p.read_text('utf-8')
        assert good.strip(), '夹具：正常文件非空'
        serve.persist_rooms_dump = lambda: {'bad': object()}   # 注入序列化失败
        raised = None
        try:
            ok = serve.save_persist_rooms(str(p))
        except Exception as e:
            raised, ok = e, None
        assert raised is None, f'写盘失败必须吞掉并返回 False，不得向上抛：{raised!r}'
        assert ok is False, '序列化失败必须返回 False'
        assert p.read_text('utf-8') == good, '原子写：失败不得破坏既有文件'
        assert not (d / 'persist_rooms.json.tmp').exists(), '失败不得留半截 tmp'
    finally:
        serve.persist_rooms_dump = keep_dump
        serve.rooms.pop('pa', None)


def test_room_passw_hashed_at_rest():
    """批37 项5（先红后绿）：房口令哈希存储——persist 落盘无明文口令；
加载后的房间内存不留明文，仍可凭原口令进入、错口令被拒。"""
    import tempfile
    import shutil
    from pathlib import Path
    d = Path(tempfile.mkdtemp(prefix='snake-roompw-'))
    p = d / 'persist_rooms.json'
    keep_rooms = dict(serve.rooms)
    try:
        r = serve.Room('hp', 'hp', 12, passw='S3cret!')
        r.persist = True
        serve.rooms['hp'] = r
        assert r.has_pass, '夹具：设了口令应 has_pass'
        assert r.check_pass('S3cret!'), '夹具：原口令应通过'
        assert not r.check_pass('nope'), '夹具：错口令应拒绝'
        assert serve.save_persist_rooms(str(p)) is True
        raw = p.read_text('utf-8')
        assert 'S3cret!' not in raw, 'persist 不得落明文口令'
        assert 'pass_h' in raw, '应落哈希字段 pass_h'
        serve.rooms.pop('hp')
        n = serve.load_persist_rooms(str(p))
        assert n >= 1 and 'hp' in serve.rooms, '夹具：加载失败'
        r2 = serve.rooms['hp']
        assert r2.passw is None, '加载后内存不应保留明文'
        assert r2.has_pass, '加载后仍应视为口令房'
        assert r2.check_pass('S3cret!'), '加载后原口令应通过'
        assert not r2.check_pass('bad'), '加载后错口令应拒绝'
    finally:
        serve.rooms.clear()
        serve.rooms.update(keep_rooms)
        shutil.rmtree(d, ignore_errors=True)


# ---- 批37：口令强度放开（用户拍板「都做」）----

def test_password_policy_accepts_6plus_chars():
    """批37（先红后绿）：账号口令放开为 6-64 位任意字符（旧式 6 位数字仍合法）。
非数字长口令可注册也可登录；短于 6 位或超过 64 位仍拒绝。"""
    import tempfile
    import shutil
    from pathlib import Path
    d = Path(tempfile.mkdtemp(prefix='snake-pw-'))
    keep = serve.store
    try:
        serve.store = serve.Store(d / 'store.json')
        ok, err = serve.store.register('pwuser', 'abc123')
        assert ok, err
        ok, err = serve.store.register('pwuser2', '12345678')
        assert ok, err
        ok, err = serve.store.register('pwuser3', '12345')
        assert not ok, '5 位仍应拒绝'
        ok, err = serve.store.register('pwuser4', 'x' * 65)
        assert not ok, '超长仍应拒绝'
        ok, err = serve.store.register('pwuser5', '123456')
        assert ok, err
        assert serve.store.login('pwuser', 'abc123') == (True, None)
        assert serve.store.login('pwuser5', '123456') == (True, None)
        ok, err = serve.store.login('pwuser', 'abc124')
        assert not ok, '错口令仍应拒绝'
    finally:
        serve.store = keep
        shutil.rmtree(d, ignore_errors=True)


# ---- 批36 P1-3：roomcfg 口径（用户拍板 2026-10-19）----

def test_roomcfg_pass_room_owner_only():
    """拍板原话：「设密码的只有房主能改 没密码的所有人都能改」。
有口令的房间：陌生人改任何字段 → error 且参数不变；房主(sid) 与持 otok 凭据者放行。"""
    import asyncio
    r = serve.Room('rc', 'rc', 10, bots=0)
    r.owner = 'ownersid'
    r.owner_user = None
    r.owner_tok = 'o' * 32
    serve.rooms['rc'] = r
    owner = _cfg_sess(sid='ownersid', user=None, room=r)
    try:
        asyncio.run(serve.handle_msg(owner, {'t': 'roomcfg', 'room': 'rc',
                                             'pass': 'Kx9m2Q'}))
        assert r.passw is not None, '夹具：房主应能给自己的房设口令'
        # 1) 陌生人 → 拒绝且参数不变
        st = _cfg_sess(sid='stranger', user=None, room=r)
        asyncio.run(serve.handle_msg(st, {'t': 'roomcfg', 'room': 'rc',
                                          'bots': 5, 'name': 'hijack'}))
        assert any(x.get('t') == 'error' for x in st.ws.sent), '口令房必须拒绝陌生人'
        assert not any(x.get('t') == 'cfgapplied' for x in st.ws.sent), '拒绝不得回成功'
        assert (r.bots, r.name) == (0, 'rc'), f'拒绝后参数必须不变: bots={r.bots} name={r.name}'
        # 2) 房主（同 sid）→ 放行
        asyncio.run(serve.handle_msg(owner, {'t': 'roomcfg', 'room': 'rc', 'bots': 3}))
        assert r.bots == 3, '房主必须能改自己的口令房'
        assert any(x.get('t') == 'cfgapplied' for x in owner.ws.sent)
        # 3) 持 owner_tok 凭据的新会话 → 放行（跨会话房主）
        tok = _cfg_sess(sid='newsid', user=None, room=r)
        asyncio.run(serve.handle_msg(tok, {'t': 'roomcfg', 'room': 'rc',
                                           'otok': 'o' * 32, 'bots': 4}))
        assert r.bots == 4, '持 owner_tok 凭据者必须能改'
    finally:
        del serve.rooms['rc']


def test_roomcfg_no_pass_anyone_edits():
    """拍板后半句：没口令的房间所有人都能改——含陌生人首次设置口令。"""
    import asyncio
    r = serve.Room('rc', 'rc', 10, bots=0)
    r.owner = 'oldsid'
    r.owner_user = None
    r.owner_tok = 'p' * 32
    serve.rooms['rc'] = r
    try:
        assert r.passw is None, '夹具：无口令房'
        st = _cfg_sess(sid='x', user=None, room=r)
        asyncio.run(serve.handle_msg(st, {'t': 'roomcfg', 'room': 'rc', 'bots': 5}))
        assert r.bots == 5, '无口令房陌生人改设置必须放行'
        # 陌生人首次设口令也算「没密码的所有人都能改」
        asyncio.run(serve.handle_msg(st, {'t': 'roomcfg', 'room': 'rc', 'pass': 'Kx9m2Q'}))
        assert r.passw == 'Kx9m2Q', '无口令房陌生人可设口令'
        # 一旦上了口令，另一个陌生人立刻失去修改权
        st2 = _cfg_sess(sid='y', user=None, room=r)
        asyncio.run(serve.handle_msg(st2, {'t': 'roomcfg', 'room': 'rc', 'bots': 7}))
        assert r.bots == 5, '上口令后第二个陌生人必须被拒'
        assert any(x.get('t') == 'error' for x in st2.ws.sent)
    finally:
        del serve.rooms['rc']


# ---- 批37：运行配置外置（用户拍板「都做」）----

def test_runtime_config_precedence_and_fallback():
    """批37（先红后绿）：配置取值优先级 cfg 字典 > SNAKE_<KEY> 环境变量 > 默认值。
类型非法回退默认、越界钳位到区间；缺省时与历史默认完全一致。"""
    cfg = {'CREATE_IP_MAX': 5}
    assert serve.cfg_val('CREATE_IP_MAX', 40, lo=1, cfg=cfg, env={}) == 5, '文件配置优先'
    assert serve.cfg_val('CREATE_IP_MAX', 40, lo=1, cfg={}, env={'SNAKE_CREATE_IP_MAX': '7'}) == 7, 'env 次之'
    assert serve.cfg_val('CREATE_IP_MAX', 40, lo=1, cfg={}, env={}) == 40, '缺省=原默认'
    assert serve.cfg_val('CREATE_IP_MAX', 40, lo=1, cfg={'CREATE_IP_MAX': 'abc'}, env={}) == 40, '类型非法回退'
    assert serve.cfg_val('ROOM_MAX', 100, lo=1, cfg={'ROOM_MAX': 0}, env={}) == 1, '下界钳位'
    assert serve.cfg_val('PORT', 20000, lo=1, hi=65535, cfg={'PORT': 99999}, env={}) == 65535, '上界钳位'
    assert serve.cfg_val('STORE_SAVE_INTERVAL', 5.0, cast=float, cfg={'STORE_SAVE_INTERVAL': '2.5'}, env={}) == 2.5, 'float 转换'


def test_runtime_config_file_load():
    """批37（先红后绿）：SNAKE_CONFIG 指向的 JSON 配置加载。
合法 dict 正常读取；文件不存在/非法 JSON/根节点非对象 → 优雅返回 {} 不阻断启动。"""
    import tempfile, os, json, shutil
    d = tempfile.mkdtemp(prefix='snake-cfg-')
    try:
        p = os.path.join(d, 'cfg.json')
        with open(p, 'w', encoding='utf-8') as f:
            json.dump({'PORT': 9000, 'ROOM_MAX': 50}, f)
        assert serve.load_runtime_config(p) == {'PORT': 9000, 'ROOM_MAX': 50}, '合法文件读取'
        bad = os.path.join(d, 'bad.json')
        with open(bad, 'w', encoding='utf-8') as f:
            f.write('{not json')
        assert serve.load_runtime_config(bad) == {}, '非法 JSON 回退 {}'
        arr = os.path.join(d, 'arr.json')
        with open(arr, 'w', encoding='utf-8') as f:
            f.write('[1, 2]')
        assert serve.load_runtime_config(arr) == {}, '根节点非对象回退 {}'
        assert serve.load_runtime_config(os.path.join(d, 'none.json')) == {}, '缺文件回退 {}'
        old = os.environ.get('SNAKE_CONFIG')
        try:
            os.environ['SNAKE_CONFIG'] = p
            assert serve.load_runtime_config() == {'PORT': 9000, 'ROOM_MAX': 50}, '无参读 SNAKE_CONFIG'
        finally:
            if old is None:
                os.environ.pop('SNAKE_CONFIG', None)
            else:
                os.environ['SNAKE_CONFIG'] = old
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_runtime_config_wired_defaults_unchanged():
    """批37（先红后绿）：接线后的运行配置在无任何 SNAKE_* 覆盖时保持历史默认（默认行为不变）。"""
    assert serve._RUNTIME_CFG == {}, '未设 SNAKE_CONFIG 时启动加载为空配置'
    assert serve.CREATE_IP_MAX == 40
    assert serve.CREATE_MAX == 8
    assert serve.REG_MAX == 30
    assert serve.ROOM_MAX == 100
    assert serve.ROOM_KEEP_SECS == 86400
    assert serve.STORE_SAVE_INTERVAL == 5.0
    assert 1 <= serve.PORT <= 65535


def test_die_telemetry_batch40():
    """批40：死亡遥测——环境致死（wall/cliff）落 usage.log 明细（头格/致死格/当前高/目标高/邻格高环）"""
    import json as _json
    import shutil
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp(prefix="snake-dietelem-"))
    old_usage = serve.usage
    try:
        serve.usage = serve.Usage(d / "usage.log", d / "usage.json")
        # 1) 撞墙：头在 (0,5) 向左 → 致死格 (-1,5)
        r = fresh(10)
        p = mk(r, 1, "A", [(0, 5), (1, 5), (2, 5)], (-1, 0))
        p["user"] = "u1"
        r.step(0.05, serve.now_ms())
        assert not p["alive"] and p["cause"] == "wall", p.get("cause")
        lines = [_json.loads(x) for x in (d / "usage.log").read_text("utf-8").splitlines()]
        dies = [x for x in lines if x.get("e") == "die"]
        assert len(dies) == 1, dies
        w = dies[0]
        assert w["cause"] == "wall" and w["user"] == "u1" and w["name"] == "A", w
        assert (w["hx"], w["hy"]) == (0, 5) and (w["x"], w["y"]) == (-1, 5), w
        assert w["h0"] == 0 and w["h1"] == 0, w
        assert len(w["ring"]) == 4, w
        # 2) 撞崖：(2,5) 向右踩上 h=2 峰 (3,5)
        r2 = fresh(10)
        r2.hmap[(3, 5)] = 2
        q = mk(r2, 1, "B", [(2, 5), (1, 5), (0, 5)], (1, 0))
        r2.step(0.05, serve.now_ms())
        assert not q["alive"] and q["cause"] == "cliff", q.get("cause")
        lines = [_json.loads(x) for x in (d / "usage.log").read_text("utf-8").splitlines()]
        dies = [x for x in lines if x.get("e") == "die"]
        assert len(dies) == 2, dies
        c = dies[1]
        assert c["cause"] == "cliff" and (c["x"], c["y"]) == (3, 5), c
        assert c["h0"] == 0 and c["h1"] == 2, c
        # 3) 机器人不落盘（防 bot 高频死亡刷爆日志）
        r3 = fresh(10)
        b = mk(r3, 2, "Bot", [(0, 5), (1, 5), (2, 5)], (-1, 0))
        b["bot"] = True
        b["cause"] = "wall"
        r3._die_telemetry(b, (-1, 5))
        lines = [_json.loads(x) for x in (d / "usage.log").read_text("utf-8").splitlines()]
        assert len([x for x in lines if x.get("e") == "die"]) == 2, "bot death must not be logged"
        print("die telemetry OK ->", c)
    finally:
        serve.usage = old_usage
        shutil.rmtree(d, ignore_errors=True)


for fn in [test_die_telemetry_batch40,
           test_ghost_wrap, test_wall_death_without_ghost, test_portal,
           test_item_pickup, test_speed_effect, test_shield_immunity,
           test_shield_item_immunity, test_bite_truncates_not_kills,
           test_bite_min_len_eliminates, test_bite_immunity,
           test_bullet_shortens_snake, test_bullet_ignores_owner_and_immunity,
           test_spawn_avoids_snakes_and_faces_open, test_spawn_cost_logged,
           test_proto_ver_handshake, test_shutdown_settle, test_occupied_foods_cache,
           test_food_has_unique_id,
            test_multi_foods_target_and_unique, test_multi_foods_eat_replenishes, test_multi_foods_bot_target_nearest,
            test_store_gacha_fields,
            test_gacha_probability_boundaries, test_gacha_pity90_hard, test_gacha_pity10_four,
            test_gacha_pity_order, test_gacha_5050_guarantee, test_gacha_ten_pull_pity_carry,
            test_pool_pick_uniform, test_gacha_dist_smoke,
            test_gacha_invalid_n_rejected, test_gacha_requires_login,
    test_gachainfo_identity_mismatch_zero, test_skin_identity_mismatch_rejected,
            test_gacha_identity_mismatch_rejected,
            test_gacha_in_lobby_works_with_zero_dust,
            test_gacha_insufficient_balance_no_side_effect,
            test_gacha_deduct_and_result, test_gacha_ten_pull, test_gacha_cap_flag,
            test_settle_dust_idempotent, test_stardust_grant_on_win_and_tie,
            test_skin_normalize_and_auth, test_join_skin_fallback_no_reject,
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
            test_roomcfg_deferred_fields_reported,
            test_respawn_msg_gated_by_room_mode_and_delay,
            test_create_rate_limited_and_room_cap,
            test_register_rate_limited,
            test_room_pass_bruteforce_throttle,
            test_anonymous_resume_ip_bound,
            test_token_ttl_expired,
            test_room_info_humans_vs_bots,
            test_win_pending_timeout_forces_new_round,
            test_late_join_starts_round_when_all_ready,
            test_update_gift_claim_once,
            test_star_tuning_batch29,
            test_newbie_room_cfg_batch30,
            test_online_count_batch30,
            test_gchat_batch30,
            test_pause_afk_batch30, test_pause_counts_as_present_batch30,
            test_admin_core_batch30, test_admin_notice_grant_report_batch30,
            test_login_gift_batch31,
            test_height_gen_invariants, test_abyss_gen_batch46, test_reach_rules_batch46, test_solid_fatal_fall_batch46, test_bot_dijkstra_batch46, test_height_majestic_ridge_batch43, test_height_cfg_roundtrip,
            test_cliff_move, test_water_slowdown, test_climb_slowdown_batch46, test_fall_death_batch46, test_fall_cut_batch46, test_spawn_h0, test_ghost_cross_height,
            test_crush, test_bullet_terrain, test_bullet_hit_range,
            test_snapshot_height,
            test_reactions_table_complete_batch33, test_reaction_same_or_none_elem_batch33,
            test_aura_snapshot_and_ttl_batch33, test_spawn_clears_aura_keeps_on_off_batch33,
            test_eterrain_constraints_batch33, test_eterrain_attach_and_spawn_avoid_batch33,
            test_eterrain_full_and_delta_batch33,
            test_bite_reaction_all_six_batch33, test_reaction_dual_consume_and_infect_batch33,
            test_react_charge_and_dead_degrade_batch33, test_crush_result_unchanged_batch33,
           test_eb_attach_and_cd_batch33, test_eb_hit_attach_refresh_batch33,
           test_eb_no_rock_and_gates_batch33, test_eb_cross_layer_batch33,
           test_frozen_no_move_and_resume_batch33, test_frozen_head_static_obstacle_batch33,
           test_frozen_input_gate_batch33, test_frozen_biteable_batch33,
           test_slow_tick_multiplier_batch33,
             test_elements_roomcfg_and_persist_batch33,
             test_store_inc_throttled_batched_save,
             test_store_record_best_and_shutdown_flush,
             test_store_load_corrupt_backs_up_before_reset,
             test_save_persist_rooms_atomic_on_failure,
             test_password_policy_accepts_6plus_chars,
             test_room_passw_hashed_at_rest,
             test_roomcfg_pass_room_owner_only,
             test_roomcfg_no_pass_anyone_edits,
             test_runtime_config_precedence_and_fallback,
             test_runtime_config_file_load,
             test_runtime_config_wired_defaults_unchanged,
             test_win_zero_window_expires_immediately]:
    fn()
print("ALL GAME UNIT TESTS PASSED")
