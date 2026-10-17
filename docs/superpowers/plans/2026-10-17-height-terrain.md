# 批32 高度地形与建筑 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 3D 贪吃蛇加入真高度层：服务端权威 heightmap（山/水/楼/草/深渊）+ 碾压/挡弹/爬坡规则 + 客户端几何拔高渲染与房间三旋钮。

**Architecture:** 服务端 `Room.hmap` 稀疏表单源（0=平不存；-2草/-1水/1丘/2峰/3楼/9深渊），逐节高度按格查表（无平行数组）；规则四接入点（_solid/reach_set/step/occupied）；协议 PROTO_VER 28、hmap 走 DELTA_FIELDS；客户端 `hmapD` Map 驱动地形拔高 mesh、蛇逐节 lerp、预测挡崖。spec 见 `docs/superpowers/specs/2026-10-17-height-terrain-design.md`（**已含 §12 计划期修订 6 条，实现一律以修订后语义为准**）。

**Tech Stack:** Python 单文件 serve.py + 原生 JS/Three.js index.html；pytest 无——自研 `test_game.py`（函数 + 底部注册列表）；Playwright e2e；门禁 `pwsh scripts/local_ci.ps1`。

**Spec:** `docs/superpowers/specs/2026-10-17-height-terrain-design.md`

## Global Constraints

- PROTO_VER=28：`serve.py:48` 与 `index.html:1060`（`const PROTO_VER = 28`）同批改。
- 客户端常量 `H_UNIT = 0.35`；渲染映射 `visH(h)`：h≥0→h*H_UNIT，h==-1→-0.12，h==-2→0（规则层始终用原始 h）。
- 非平地预算：全房 `h != 0` 格 ≤ 35% × cols×rows（三类共享）。
- 房间旋钮消息字段 `height` / `water` / `bld`（float 0..4 夹取；0=关；缺省/None=跟随主题）；info() 回传 eff + `heightCustom/waterCustom/bldCustom`。
- 新 reason 值：`cliff`（撞崖）、`crush`（被碾压/反噬）；新 ev：`phit`（子弹撞地形碎裂）。
- 测试约定：`fresh(size, **kw)` / `mk(r, id, name, cells, dir)` 玩家助手（test_game.py 顶部）；每个新测试函数**必须加进文件底部 `]:` 前的注册列表**；跑法 `.venv\Scripts\python.exe test_game.py`（全量）；单测 TDD 迭代用 `python -c "import test_game as t; t.test_x()"`（import 即执行全量列表，先保证基线绿）。
- e2e：本地服 `$env:PORT='8123'; Start-Process .venv\Scripts\python.exe serve.py ...`，`$env:BASE='http://127.0.0.1:8123'; npx playwright test <regex>`；登录用 admin.spec 的 `ensureLogin`（已含 giftPop 关闭逻辑）——height32 使用前须在 `e2e/admin.spec.js` 尾部补 `module.exports = { ensureLogin }`，调用写 `ensureLogin(page, 'yuan', '123456')`；e2e 文件一律放 `e2e/` 目录（playwright.config testDir='./e2e'）。
- 门禁必须 `pwsh scripts/local_ci.ps1`（不能 powershell，GBK 报 ParserError）。
- BACKLOG.md/HANDOVER.md 新增行剥尾部 `\r`（混合行尾陷阱）；commit 前 `git diff --check` 必须 0。
- 客户端本地演示/离线场景不生成高度（hmap 缺省=全 0 平地，自然兼容）；不改 opencode 配置。

## Review Focus

按「最可能先咬人」排序，每条归属任务内有对应用例：

1. **咬击玩法回归**：新碾压规则不得杀死既有咬击（同高=截断照旧）→ `test_crush` 同高分支 + 既有 `test_bite_*` 全部原样通过（每任务全量跑保证）。
2. **判定位错用「目标格高」**：crush/head-on 必须用**撞击前 stance 头格高**（spec §12 修订②同格恒等悖论）→ `test_crush` 各分支用不同当前/目标格高构造。
3. **cells 重排后高度错位**：实现不得引入任何平行数组（平行数组已废除）→ 代码审查点 + `test_bullet_hit_range`/bite 系列回归。
4. **生成预算/可达性回归**：gen 不压 portal/wall、≤35%；既有 `test_place_food_avoids_sealed_pocket`、`test_place_food_reach_time_budget` 不回归 → `test_height_gen_invariants`。
5. **预测与服务端规则漂移**：客户端 advanceStep 挡崖语义须与服务端一致（shield/deflect 门控同路）→ e2e 预测挡崖 + 单测 `test_cliff_move`（含 shield 折返、ghost 穿越、AI 前瞻）。

---

### Task 1: 服务端 hmap 生成与房间配置

**Files:**
- Modify: `serve.py`（THEME_CFG ~158-166；Room.__init__ ~500-530；eff_rock/eff_portal 637-646 后；build_terrain 672-700；persist_rooms_dump 1868-1878；load_persist_rooms def ~1892（`rock = d.get('rock')` ~1910 附近仿）；live create 消息解析 ~2325-2332（rock 解析）+ `Room(...)` 构造 ~2373；roomcfg 'rock' 块 2449-2460 后）
- Test: `test_game.py`（新函数 + 底部注册列表）

**Interfaces:**
- Produces: `Room.hmap: dict[(x,y)->int]`（稀疏，0 不存）；`Room.height_mult / water_amt / bld_amt`（float|None）；`Room.eff_height() / eff_water() / eff_bld() -> float`；`Room.gen_heights()`（build_terrain 末尾自动调用）；info() 新增 6 键；消息字段 `height/water/bld`；持久化 JSON 新增三键。
- Consumes: 既有 `THEME_CFG`、`random`、`self._heads()`、`occupied()`。

- [ ] **Step 1: 写失败测试**

`test_height_gen_invariants`：

```python
def test_height_gen_invariants():
    r = fresh(24)                       # 默认主题
    p0 = mk(r, 1, "A", [(12, 12), (11, 12)], (1, 0))   # 造旧蛇头做 ±4 避让验证
    r.build_terrain()
    vals = set(r.hmap.values())
    assert vals                                                # 默认主题必出地形
    assert vals <= {-2, -1, 1, 2, 3, 9}, vals                  # 值域；0 不存
    assert 0 not in vals
    assert -2 in vals                                          # 草丛必有生成来源（spec §7.3 第4类）
    assert len(r.hmap) <= int(0.35 * 24 * 24), len(r.hmap)   # ≤35% 预算
    assert not (set(r.rocks) & set(r.hmap))                  # 不与岩石重叠
    assert not (set(r.walls) & set(r.hmap))                  # 不压墙块
    assert not (set(r.portals) & set(r.hmap))                # 不压传送门
    assert all(abs(x - 12) + abs(y - 12) >= 4 for (x, y) in r.hmap)   # 不压旧蛇头 ±4
    rl = fresh(24, theme_fixed='lava')
    rl.build_terrain()
    assert -1 not in rl.hmap.values() and -2 not in rl.hmap.values()  # 熔岩无水洼无草
    r0 = fresh(16, height_mult=0.0, water_amt=0.0, bld_amt=0.0)
    r0.build_terrain()
    assert r0.hmap == {}                                     # 三旋钮全 0（预算=0 早退）= 纯平地
```

`test_height_cfg_roundtrip`（旋钮夹取/回填/roomcfg 消息级）：

```python
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
```

- [ ] **Step 2: 跑测试确认红** — `python -c "import test_game as t; t.test_height_gen_invariants()"` → FAIL（height_mult 未定义/`fresh` 不接受未知 kw）。两函数都要红。
- [ ] **Step 3: 实现**
  1. `THEME_CFG` 五主题各加 `'hill'/'water'/'bld'` 键，取值按 spec §7.1（default .9/.6/.5；lava 1.4/0/.3；ice .5/.9/.4；space 1.1/0/.9；day .8/.7/.6）。
  2. `Room.__init__` 增参 `height_mult=None, water_amt=None, bld_amt=None`，存 `self.height_mult/water_amt/bld_amt`，并 `self.hmap = {}`——**必须放在 `self._pick_theme()`（serve.py:579）与 `self.build_terrain()`（580）之前**（与 `self.rocks = []`（561）同区），否则构造即 AttributeError。
  3. eff 三助手镜像 `eff_rock`（None→主题值；写在 eff_portal 后）。
  4. `gen_heights()` 定义在 `build_terrain` 后，并在 build_terrain 墙块循环末尾（line ~700 后）调用。算法按 spec §7.3：预算 `int(0.35*area)` 共享；顺序山包→水洼→建筑→草丛；避开 `portals`、`walls`、`_heads()`±4、已放格。山：种子 `int(area/40*hill)` 个，h=2，70% 全环 h=1、30% 缺一侧成 0→2 立地峭壁；水：`int(area/60*water)` 团，随机游走 3~8 格全 h=-1；建筑：`int(area/80*bld)` 栋，footprint 1×2/2×2/1×3/2×3 均匀高度——h1(40%)/h2(35%，其中 60% 外接一格 h1 入口坡)/h3(25%)；草：`int(area/70*water)` 团（随 water 旋钮），随机游走 2~5 格全 h=-2（water=0/熔岩天然无草）。全程 `hmap` 只写非 0，预算耗尽即停。
  5. 配置通路：`persist_rooms_dump` 加 `'height': r.height_mult, 'water': r.water_amt, 'bld': r.bld_amt`；load 循环仿 `rock` 解析（float 夹 0..4 或 None）传 Room；live create（~2373）同；roomcfg 在 'rock' 块后镜像三块（字段名 height/water/bld → 属性 height_mult/water_amt/bld_amt，`deferred.append` 同名）；`info()` 加 6 键（eff + Custom）。
- [ ] **Step 4: 跑测试确认绿** — 两函数 PASS；全量 `.venv\Scripts\python.exe test_game.py` → `ALL GAME UNIT TESTS PASSED`。
- [ ] **Step 5: Commit** — `git add serve.py test_game.py && git commit -m "feat(批32): 服务端 heightmap 生成与房间三旋钮(hill/water/bld)"`

### Task 2: 通行规则（cliff/水减速/出生h0/AI前瞻）

**Files:**
- Modify: `serve.py`（`_solid` 824-835；`_open_ahead` 837-844；`occupied` 717-736；`reach_set` block 972；`_spawn_player_impl` 889-941；`step()` section4 ~1443-1466；`tick_of` 1072-1076；`_bot_think` 内 `_open_ahead` 调用点）
- Test: `test_game.py`

**Interfaces:**
- Consumes: `hmap`（Task 1）。
- Produces: `_solid(x, y, skip_pid=None, cur_h=None)`（cur_h 传值时 `hmap[(x,y)] - cur_h >= 2` → True，含 9）；`_open_ahead(x, y, d, skip_pid=None, cap=24, cur_h=None)`；`tick_of` 水减速；死亡 reason `cliff`。

- [ ] **Step 1: 写失败测试**

`test_cliff_move`（注入 hmap，逐场景 fresh）：

```python
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
```

`test_water_slowdown`：

```python
def test_water_slowdown():
    r = fresh(16); r.hmap = {(5,5): -1}; r._reach = None
    p = mk(r, 1, "A", [(5,5),(4,5)], (1,0))
    assert r.tick_of(p, serve.now_ms()) == int(150 * 1.3)      # 195
    p2 = mk(r, 2, "B", [(5,8),(4,8)], (1,0))
    assert r.tick_of(p2, serve.now_ms()) == 150                # 平地不减速
    p['eff'] = {'speed': serve.now_ms()+9999}
    assert r.tick_of(p, serve.now_ms()) == int(int(150*0.6) * 1.3)   # 加速再水涉
```

`test_spawn_h0`：

```python
def test_spawn_h0():
    r = fresh(20)
    r.hmap = {(x, y): ((x + y) % 3) + 1 for x in range(0, 20, 3) for y in range(20)}
    r._reach = None
    p = serve.make_player(1, None, "A", "s0")
    r.players[1] = p
    r.spawn_player(p)
    assert p['cells']
    assert all(r.hmap.get(c, 0) == 0 for c in p['cells'])
```

`test_ghost_cross_height`（spec #7，独立小例）：

```python
def test_ghost_cross_height():
    r = fresh(16); r.hmap = {(6,5): 9}; r._reach = None
    p = mk(r, 1, "A", [(5,5),(4,5)], (1,0)); p['inv'] = 0
    p['eff'] = {'ghost': serve.now_ms() + 9999}
    r.step(0.05, serve.now_ms())
    assert p['alive'] and p['cells'][0] == (6,5)
```

- [ ] **Step 2: 跑测试确认红** — 四函数全 FAIL（cliff 不存在/水不减速/出生可上山）。
- [ ] **Step 3: 实现**
  1. `_solid` 增参 `cur_h=None`：在既有阻挡判定后追加 `if cur_h is not None and self.hmap.get((x, y), 0) - cur_h >= 2: return True`。`_open_ahead` 增参 `cur_h=None` 并透传给 `_solid`（每步同用蛇头当前格高——spec §3.3）。
  2. `_bot_think`：开头算 `cur_h = self.hmap.get(p['cells'][0], 0)`，其内所有 `_open_ahead(...)` 调用补 `cur_h=cur_h`。`_nearest_opp` 纯测距不改。
  3. `occupied()`：OOB 判定后加 `if self.hmap.get((x, y), 0) >= 2: return True`。
  4. `reach_set()`：`block = set(self.rocks) | set(self.walls) | {c for c, hh in self.hmap.items() if hh >= 2}`。
  5. `_spawn_player_impl`：主路径候选（`occupied` 检查处）与兜底①候选加 `or any(self.hmap.get(c, 0) != 0 for c in cells)` 跳过；兜底②不改。
  6. `step()` section4：`blockset` 行后算 `cur_h = self.hmap.get(p['cells'][0], 0)`（循环内）与 `cliff = (not ghost) and (self.hmap.get(tent[id(p)], 0) - cur_h >= 2)`；判定行改 `if not (wall or rock or cliff or own): continue`；死因行改 `p['cause'] = 'wall' if wall else ('rock' if rock else ('cliff' if cliff else 'self'))`。ghost 分支天然豁免（cliff 定义含 not ghost）。
  7. `tick_of`：速度分支重构为先算 `t = max(60, int(base*0.6)) if speed else base`，再 `if p['cells'] and self.hmap.get(p['cells'][0], 0) == -1: t = int(t * 1.3)`，返回 t。
  8. **不改** `cur_h=None` 的既有调用点（有意保持纯几何）：portal 出口朝向（serve.py:1376）、`_deflect_dir`（1604）、spawn 开阔度（898/923/937）——shield 折返可能折向峭壁格，shield 期内只会反复折返不死，不引入回归。
- [ ] **Step 4: 跑测试确认绿** — 四函数 PASS + 全量绿（尤其 reach/spawn 存量用例）。
- [ ] **Step 5: Commit** — `git commit -m "feat(批32): 高度通行规则(cliff/水减速/出生h0/AI前瞻)"`（同 Task 1 文件集）

### Task 3: 战斗语义（crush/咬击调和）与弹道高度

**Files:**
- Modify: `serve.py`（`step()` section3 clash 块 ~1388-1437、section5 bite 块 ~1468-1521；`try_ult` 1609-1626；`atk` handler ~2786-2796；`_step_projectiles` 1709-1750）
- Test: `test_game.py`

**Interfaces:**
- Consumes: `hmap`、Task 2 规则。
- Produces: crush 语义（stance 比较）；`ev('phit', x=, y=, h=, by=)`；弹 dict 增 `'h'`。

- [ ] **Step 1: 写失败测试**

`test_crush`（子场景全 fresh；要点：stance=撞击前头格高）：

```python
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
```

`test_bullet_terrain`：

```python
def _shot(h, x, y=5):
    return {'owner': 1, 'x': x, 'y': y, 'dx': 1, 'dy': 0, 'spd': 1.0, 'h': h}

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
    r.projectiles = [_shot(0, 6.0 - step + 0.1)]; r.hmap = {(6,5): 9}
    r._step_projectiles(0.05, now); assert r.projectiles                   # 深渊飞越
    r.projectiles = [_shot(1, 6.0 - step + 0.1)]; r.hmap = {(6,5): 1}
    r._step_projectiles(0.05, now); assert r.projectiles                   # 弹h1 过 1
    r.projectiles = [_shot(1, 6.0 - step + 0.1)]; r.hmap = {(6,5): 2}
    r._step_projectiles(0.05, now); assert r.projectiles == []             # 弹h1 遇 2 碎
```

`test_bullet_hit_range`：

```python
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
```

发弹记 h 的断言写死在 `test_bullet_hit_range` 尾部：`p = mk(r,1,"A",[(5,5),(4,5)],(1,0)); p['ult']=100; p['inv']=0; r.hmap={(5,5):1}; r.try_ult(p, serve.now_ms()); assert r.projectiles and all(pr['h']==1 for pr in r.projectiles)`。

- [ ] **Step 2: 跑测试确认红** — 三函数 FAIL（无 crush/phit/h 字段）。
- [ ] **Step 3: 实现**
  1. **section3 clash 两处**：`ta == tb or swap` 分支与 `tent[a]==q['cells'][0]` 分支开头各加高度裁决（用 `hmap.get` 取双方**当前**头格高）：`ha != hb` → 低者 `dead.add(id(low))`、`low['cause']='crush'`、`low['by']=对方id`，双方**不** force_right（高者照常）、不进 head_on/hstreak 流程；`ha == hb` → 走原右转/僵持逻辑一行不改（die 事件由现有 dead 结算统一发）。
  2. **section5 bite**：bites 聚合循环不变；结算循环里对每 `(vid,(eid,idx))` 取 `eh = self.hmap.get(ep['cells'][0], 0)`（攻击者 stance——注意其 cells 尚未插入新头，`cells[0]` 即当前头）、`vh = self.hmap.get(q['cells'][idx], 0)`：
     - `eh > vh` → 碾压：镜像 min-len 淘汰分支全套（alive=False、cause='crush'、by、died_at、`ep['grow'] += cut`（cut=len(q['cells'])）、ULT_KILL、`score_gain(BITE_SCORE_PER_CELL*cut)`、kills/deaths store、`ev('bite', ..., kill=True)`、`ev('die', cause='crush')`、settle_dust）。
     - `eh == vh` → 现有截断逻辑原样。
     - `eh < vh` → 攻击者死：`if id(ep) not in dead: dead.add(id(ep)); ep['cause']='crush'; ep['by']=vid`（不套 `_protected`——PVP 接触；victim `_protected` 的 skip_move 在聚合循环已处理，保持在前）。
  3. **发弹记 h**：`try_ult` 与 `atk` handler 的 projectile dict 各加 `'h': self.hmap.get((hx, hy), 0)`（atk 处为 `room.hmap.get(...)`）。
  4. **`_step_projectiles`**：地形判在岩石块后追加：`hh = self.hmap.get((gx, gy), 0)`；`if hh != 9 and hh > pr.get('h', 0): self.projectiles.remove(pr); self.ev('phit', x=gx, y=gy, h=hh, by=pr['owner']); continue`。蛇身命中 if 条件追加 `and abs(self.hmap.get((gx, gy), 0) - pr.get('h', 0)) <= 1`。
- [ ] **Step 4: 跑测试确认绿** — 三函数 PASS + 全量绿（尤其既有 `test_bite_*`、walldeflect 系列零回归）。
- [ ] **Step 5: Commit** — `git commit -m "feat(批32): 碾压/咬击高度调和与弹道高度(挡弹/跨层/phit)"`

### Task 4: 协议快照（PROTO 28 + hmap DELTA + proj.h）

**Files:**
- Modify: `serve.py`（DELTA_FIELDS 1753；snapshot full 块 1790-1798 与 delta elif 链 1803-1809；PROTO_VER ~48）
- Modify: `index.html`（PROTO_VER ~1060）
- Test: `test_game.py`

**Interfaces:**
- Produces: full 帧 `"hmap": [[x,y,h],...]`；增量帧签名变化才带；`proj` 每条含 `"h"`；PROTO_VER=28 双端（room-ok 版本不等自动 reload，index.html ~2866）。

- [ ] **Step 1: 写失败测试**

```python
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
    assert 'PROTO_VER = 28' in src and 'const PROTO_VER = 28' in html
```

- [ ] **Step 2: 跑测试确认红** — KeyError/AssertionError。
- [ ] **Step 3: 实现**
  1. `DELTA_FIELDS = ('foods','bonus','rocks','walls','portals','items','hmap')`。
  2. full 块加 `out['hmap'] = [[x, y, hh] for (x, y), hh in self.hmap.items()]`。
  3. delta elif 链加 `elif k == 'hmap': v = [[x, y, hh] for (x, y), hh in self.hmap.items()]`（**不能**走 `getattr` 直取——元组键 JSON 序列化会炸）。
  4. `proj` 序列化（1779-1781）每条加 `'h': pr.get('h', 0)`。
  5. 双端 `PROTO_VER = 28`。
- [ ] **Step 4: 跑测试确认绿** — PASS + 全量绿。
- [ ] **Step 5: Commit** — `git commit -m "feat(批32): 协议 PROTO 28 —— hmap 增量下发与弹道高度字段"`

### Task 5: 客户端地形渲染 + 房间编辑面三旋钮 + 探针

**Files:**
- Modify: `index.html`（建房面板 `cRock` 后 ~827；`createRoom` ~3857；编辑回填 ~3907；保存 ~3934；渲染区 rocks 同构处 1031/1749/2647-2672；`syncWalls` 旁）
- Test: `e2e/height32.spec.js`（新建；**Playwright testDir 是 `./e2e` 不是 tests/**）；`e2e/admin.spec.js`（尾部补 `module.exports = { ensureLogin }` 导出 + 扩展一例）

**Interfaces:**
- Consumes: Task 4 协议。
- Produces: 全局 `hmapD = new Map()`（键 `pkey(x,y)`='x,y'，值 h）；`syncHeight(list)`；`heightMeshes[]`（**只存每个 triple 的主 Object3D；h=9 的 Edges 描边挂为 child 不计入计数**）；池化 `heightPool[]` + `take/release` 助手（命名与 rocks 池化同构，2647-2672）；`H_UNIT = 0.35`、`visH(h)`；探针 `window.__mapDbgSet(triples)`、`window.__heightDbg()`（返回 `{meshes, headY, blocked}`——本任务先实现 meshes，headY/blocked 在 Task 6 补全）；三个 select `cHeight/cWater/cBld`。

- [ ] **Step 1: 写失败 e2e** — `e2e/height32.spec.js`（登录助手：先给 `e2e/admin.spec.js` 尾部补 `module.exports = { ensureLogin }`；调用带凭据 `ensureLogin(page, 'yuan', '123456')`）：

```js
const { test, expect } = require('@playwright/test');
const { ensureLogin } = require('./admin.spec');
test('hmap 注入 → 高度地形 mesh 生成', async ({ page }) => {
  await ensureLogin(page, 'yuan', '123456');
  await page.click('#btnSolo');                     // 进单人房（服务端建房）
  await page.waitForSelector('#hud', { state: 'visible' });
  await page.evaluate(() => window.__mapDbgSet([[5,5,2],[5,6,-1],[5,7,-1],[5,8,9],[5,9,1],[5,10,3]]));
  await page.waitForTimeout(300);
  const d = await page.evaluate(() => window.__heightDbg());
  expect(d.meshes).toBe(6);
});
```

编辑面例（并入 height32.spec.js，回填数据即来自服务端 info()，与 spec §9.2-3 的 info 回填断言等价）：打开编辑面板设 `cHeight=0.5/cWater=1/cBld=1` → 保存 → 重开面板 → 三值回填正确。

- [ ] **Step 2: 跑 e2e 确认红** — `__mapDbgSet` undefined → 报错。
- [ ] **Step 3: 实现**
  1. 三个 select（HTML，紧跟 `cRock` label 后，样式同 `nameIn sm`；选项：跟随主题 /0/0.5/1/1.8，`cWater`、`cBld` 同）。
  2. `createRoom`：rock 读取后镜像三行 `msg.height/msg.water/msg.bld`（`!== ''` 才 parseFloat）；编辑回填：`$('cHeight').value = (r.heightCustom == null) ? '' : String(r.heightCustom);` ×3（`cWater/cBld`）；保存消息三字段镜像 rock 写法（~3934）。
  3. JS 常量 `H_UNIT = 0.35`、`visH = h => h >= 0 ? h * H_UNIT : (h === -1 ? -0.12 : 0)`；全局 `let hmapD = new Map(); let heightMeshes = []; const heightPool = [];`。
  4. `syncHeight(list)`：签名 `list.map(t => t.join(',')).join('|')` 对比缓存 `hKey` 才重建；重建=更新 hmapD + 池化同步（照 2647-2672 的 rocks 池化：多余 visible=false、复用、新 take）。mesh 形态（共享/简单几何，全部 `material.depthWrite = false`）：h>0 柱 `BoxGeometry(0.98, 1, 0.98)` 缩放 y=h*H_UNIT、position.y=h*H_UNIT/2，岩色顶亮；h=9 黑柱下挖（position.y=-0.6，深色）+ 顶缘 `EdgesGeometry` 描边；h=-1 半透明蓝面 `PlaneGeometry` y=-0.05 呼吸（opacity=.35+.1*sin(t/900)）；h=-2 贴地染色面 y=0.005。楼（1..3）比山更规整亮色（可用同柱体、色相区分）。渲染循环里对水/草面做呼吸更新。
  5. 快照接入：`if (s.hmap !== undefined) syncHeight(s.hmap);`（挨着 walls/portals 行）；reset 区（~1749 `rocks = []` 旁）清 `hmapD/heightMeshes/hKey`。
  6. 探针：`window.__mapDbgSet = t => syncHeight(t)`（参数已是三元组列表，无需再 map）；`window.__heightDbg = () => ({ meshes: heightMeshes.length, headY: null, blocked: null })`。
- [ ] **Step 4: 跑 e2e 确认绿** — `npx playwright test height32`（含编辑面例）通过；门禁静态 ids 检查不报 dup（新 id 唯一）。
- [ ] **Step 5: Commit** — `git commit -m "feat(批32): 客户端高度地形渲染/编辑面三旋钮/探针"`

### Task 6: 客户端蛇/预测/弹/特效

**Files:**
- Modify: `index.html`（`syncBody` 3261-3305 及其两处调用 3323/3376；`predStatics` 2412-2419；`advanceStep` blocked 2436-2439；`syncProjectiles` 2682-；ev switch `case 'rock'` 3142 旁；cause 文案 ~3180；渲染主循环）
- Test: `e2e/height32.spec.js`（扩展）

**Interfaces:**
- Consumes: `hmapD/visH/H_UNIT/__heightDbg`（Task 5）。
- Produces: 蛇逐节高度 lerp + 头俯仰；预测挡崖；弹体高度；伏击草整蛇淡出；水花；`case 'phit'` 爆裂；cause 文案 `cliff/crush`。

- [ ] **Step 1: 写失败 e2e**（height32.spec.js 追加两例；`ensureLogin(page, 'yuan', '123456')`）

```js
test('蛇节按 hmap 抬升 + 预测挡崖', async ({ page }) => {
  await ensureLogin(page, 'yuan', '123456'); await page.click('#btnSolo');
  await page.waitForSelector('#hud', { state: 'visible' });
  const base = await page.evaluate(() => window.__heightDbg());
  await page.evaluate(() => window.__mapSelfCliffSet(2));   // 注入：头格 h=2、头前一格 h=4（上行2 → 挡崖；h=4 为探针专用值，不属 gen 值域）
  await page.waitForTimeout(400);
  const d = await page.evaluate(() => window.__heightDbg());
  expect(d.headY).toBeGreaterThan(base.headY + 0.5);        // 头格 h=2 → visH=0.7，抬升 ≥0.5
  expect(d.blocked).toBe(true);                             // 预测步被挡 → 不前进
});
```

（`__mapSelfCliffSet(h)` = Task 6 新探针：取 `myEnt.cells[0]` 与其 dir，注入头格 `h`、头前一格 `h+2`（统一用「头格 2 / 前格 4」这组值：既满足上行 ≥2，头格 visH=0.7 又满足 headY 断言）。`__heightDbg` 扩展 `headY = myEnt.spine[0]?.y`、`blocked = advanceStep({cells: myEnt.cells, dir: myEnt.dir}, myEnt.dir, predStatics(), foods, null).hovered === true`——advanceStep 被挡时返回 hovered:true（index.html:2436-2443），这才是被挡语义；新局无道具效果，eff 传 null 即可。）

- [ ] **Step 2: 跑 e2e 确认红** — headY 不变（null/未抬升）。
- [ ] **Step 3: 实现**
  1. `syncBody`：目标 y 计算——插值分支 `_vb.set(f.x + (c.x-f.x)*ph - COLS/2+.5, SEG_H/2+.02 + (visH(hmapD.get(pkey(f.x,f.y))||0) + (visH(hmapD.get(pkey(c.x,c.y))||0) - visH(hmapD.get(pkey(f.x,f.y))||0))*ph), f.y + (c.y-f.y)*ph - ROWS/2+.5)`；静止分支 `cw` 后 `_vb.y += visH(hmapD.get(pkey(c.x,c.y))||0)`。头俯仰：`head.rotation.x` lerp 向 `clamp((h1-h0)*0.6, -0.5, 0.5)`（h0/h1=头/颈 visH）。
  2. `predStatics()` 加 `hmap: hmapD`；`advanceStep` 的 `blocked` 表达式并入 `(!ghost && hT !== undefined && hT - (statics.hmap.get(pkey(head.x, head.y)) || 0) >= 2)`，其中 `const hT = statics.hmap.get(nx + ',' + ny);` 须先声明再进 `&&` 链（不可在链内隐式赋值——非严格模式下会漏建全局）。`pkey` 需在此作用域可用——2410 已定义；9 因 9-0≥2 恒真自动挡。与既有 rock/wall 同走 shield/deflect 门控，不另开分支。
  3. `syncProjectiles`：mesh y = `SEG_H/2+.02 + visH(p.h||0)`（每帧按列表序对应 projMeshes）。
  4. 伏击草：`syncBody` 调用处传 `opts.own`（3323 ents 循环：`own = (e.id === myEnt?.id)`；3376 处 own=true）与 `opts.dt`（渲染循环的帧 dt——syncBody 本身没有 dt 形参，需在两处调用点传入）；syncBody 内算 `inGrass = !own && cells.some(c => (hmapD.get(pkey(c.x,c.y))||0) === -2)`，`bodyMat.transparent = true`，`bodyMat.opacity` 每帧向 `(inGrass ? .35 : 1)` lerp（用 opts.dt）。head/tongue/skull 同随（`head.material` 组整体随 bodyMat 或单独同步 opacity——取实现便手者，保证整条视觉一致）。
  5. 水花：own 头格 `h === -1` → 每 600ms 在 `spine[0]` 处 `burst` 蓝白小粒子（现有 burst 助手）。
  6. ev switch：`case 'phit':` 镜像 `case 'rock'` 的爆裂写法，位置 `cellW(e.x, e.y)`、色随 `e.h`（金/岩灰）。cause 文案 map 加 `cliff: '摔下悬崖了', crush: '被碾压了'`。
- [ ] **Step 4: 跑 e2e + 全量** — `npx playwright test`（32+3+1 例全绿）。
- [ ] **Step 5: Commit** — `git commit -m "feat(批32): 蛇逐节高度渲染/预测挡崖/弹道高度/伏击草与水花"`

### Task 7: 门禁与文档收尾

**Files:**
- Modify: `BACKLOG.md`、`HANDOVER.md`
- 验证: `pwsh scripts/local_ci.ps1`

- [ ] **Step 1: 文档回写**：HANDOVER 新增批32 段（hmap/cellh 不存在/新字段 height/water/bld/新 reason cliff/crush/新 ev phit/新探针 __mapDbgSet/__heightDbg/__mapSelfCliffSet/H_UNIT=0.35）；BACKLOG 顶部加批32 段（**新增行剥 `\r`**）。HANDOVER 测试计数表若顺手可更新为当前实际数（可选项，不强制）。
- [ ] **Step 1.5: 手动验收冒烟（spec §9.3）** — 本地 8123 起服，浏览器逐项打勾：山/水/楼/草四类渲染、爬坡逐节起伏（上 0→1 节节抬升）、碾压击杀、高处挡弹、水面水花、伏击草对方淡出；再开一次 96×96 房做 3~5 秒体感确认 `syncHeight` 全量重建无明显卡顿（oracle 审核残留风险项）。任一不过先修再进门禁。
- [ ] **Step 2: 全量门禁** — `pwsh scripts/local_ci.ps1` → ALL GREEN（Playwright 全量、单测全量、静态 ids/css/js 计数）。任何红先修再提交。
- [ ] **Step 3: Commit + 收尾** — `git add -A && git commit -m "docs(批32): HANDOVER/BACKLOG 回写"`；`git diff --check` 必须 0。向用户报告契约自评，并列出 spec §12 六条修订供否决；部署（tar 回滚点 → scp index.html serve.py test_game.py → `sudo systemctl restart snake-3d`，ssh 命令必须单引号包裹防本地展开）待用户拍板。
