import time

import serve

serve.init_rooms()


class S:
    def __init__(self):
        self.ws = None
        self.user = None
        self.pid = None


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


def fresh(size=10):
    r = serve.Room("t", "t", size)
    r.rocks = []
    r.walls = []
    r.portals = []
    r.items = []
    r.bonus = None
    r.food = None
    return r


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
    r = fresh(16)
    r.place_food()
    a = r.food["id"]
    r.place_food()
    b = r.food["id"]
    assert b != a, (a, b)
    print("food unique id OK:", a, b)


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
        u.auth("login", False, "alice", "9.9.9.9")     # 失败也要留痕
        u.win("a", "Alice", "alice", 42)
        u.note("join", sid=1, room="a", name="Alice")

        lines = [_json.loads(x) for x in (d / "usage.log").read_text("utf-8").splitlines()]
        kinds = [x["e"] for x in lines]
        assert kinds == ["session", "session", "auth", "auth", "win", "join"], kinds
        auths = [x for x in lines if x["e"] == "auth"]
        assert auths[0]["ok"] is True and auths[0]["kind"] == "login"
        assert auths[1]["ok"] is False and auths[1]["ip"] == "9.9.9.9"

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
    r.food = {"id": 1, "x": 30, "y": 30, "score": 1, "color": "red"}
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
    assert r.food and (r.food["x"], r.food["y"]) not in blocked, r.food
    print("free cells 96x96 OK: free=%d, %.2fms/scan" % (len(free), ms))


def test_combo_increments_and_expires():
    r = fresh(16)
    now = serve.now_ms()
    p = mk(r, 1, "A", [(5, 5), (4, 5), (3, 5)], (1, 0))
    r.food = {"id": 1, "x": 6, "y": 5, "score": 10, "color": 0xff5f5f}
    # 第一次吃果：combo=1，倍率 x1
    r.step(0.05, now)
    assert p["combo"] == 1, p.get("combo")
    assert p["score"] == 10, p["score"]
    # 3 秒内再吃：combo=2，仍 x1（档位 1-4）
    r.food = {"id": 2, "x": 7, "y": 5, "score": 10, "color": 0xff5f5f}
    r.step(0.05, now + 200)
    assert p["combo"] == 2, p["combo"]
    assert p["score"] == 20, p["score"]
    # 超时后再吃：combo 重置为 1
    r.food = {"id": 3, "x": 8, "y": 5, "score": 10, "color": 0xff5f5f}
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
    r.food = {"id": 1, "x": 6, "y": 5, "score": 20, "color": 0xff6b81}
    r.step(0.05, now + 200)
    assert p["combo"] == 5, p["combo"]
    assert p["score"] == int(20 * 1.5), p["score"]   # 30
    print("combo tiers OK: combo", p["combo"], "score", p["score"])


def test_double_item_doubles_score():
    r = fresh(16)
    now = serve.now_ms()
    p = mk(r, 1, "A", [(5, 5), (4, 5), (3, 5)], (1, 0))
    p["eff"] = {"double": now + 9999}
    r.food = {"id": 1, "x": 6, "y": 5, "score": 15, "color": 0xe74c3c}
    r.step(0.05, now)
    assert p["score"] == 30, p["score"]              # 15 × 2
    # 咬蛇得分也翻倍：造一只 2 格蛇
    p2 = mk(r, 2, "B", [(8, 5), (7, 5)], (0, 1))
    p2["inv"] = 0
    r.food = None
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
    r.food = {"id": 1, "x": 9, "y": 5, "score": 10, "color": 0xff5f5f}
    r.step_wrapper(0.05, now)
    # 食物朝蛇头移动 1 格
    assert (r.food["x"], r.food["y"]) == (8, 5), r.food
    # 挡路的岩石 → 绕开（换轴移动）
    r.rocks = [(7, 5)]
    r.step_wrapper(0.05, now + 60)
    assert (r.food["x"], r.food["y"]) != (7, 5), r.food
    assert abs(r.food["x"] - 8) + abs(r.food["y"] - 5) == 1, r.food
    # 无磁铁效果 → 不动
    p["eff"] = {}
    r.rocks = []
    r.food = {"id": 2, "x": 9, "y": 5, "score": 10, "color": 0xff5f5f}
    r.step_wrapper(0.05, now + 120)
    assert (r.food["x"], r.food["y"]) == (9, 5), r.food
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


for fn in [test_ghost_wrap, test_wall_death_without_ghost, test_portal,
           test_item_pickup, test_speed_effect, test_shield_immunity,
           test_shield_item_immunity, test_bite_truncates_not_kills,
           test_bite_min_len_eliminates, test_bite_immunity,
           test_bullet_shortens_snake, test_bullet_ignores_owner_and_immunity,
           test_spawn_avoids_snakes_and_faces_open, test_food_has_unique_id,
           test_room_custom_config, test_speed_change_instant,
           test_free_cells_big_map, test_usage_log,
           test_combo_increments_and_expires, test_combo_multiplier_tiers,
           test_double_item_doubles_score, test_magnet_pulls_food,
           test_rage_halves_cooldown_and_speeds_bullet]:
    fn()
print("ALL GAME UNIT TESTS PASSED")
