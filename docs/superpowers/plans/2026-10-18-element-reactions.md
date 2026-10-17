# 原神元素反应（批33）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 四元素（火水冰雷）反应系统——蛇持 aura、元素弹/元素地形附着、命中全算查表反应、反应反哺大招充能，PROTO 29 双端。

**Architecture:** 服务端权威：Room 新增 eterrain 稀疏表与 aura 字段，REACTIONS 常量表 + apply_reaction 统一入口挂在既有三类命中路径（bites 循环 / _step_projectiles）上；复用 projectiles、eff、DELTA_FIELDS、ULT 充能骨架。客户端 index.html 增元素 HUD、光晕、浮字。测试先行（test_game.py 单测 + python E2E + Playwright）。

**Tech Stack:** Python 3 websockets 服务端（serve.py 单文件）、单文件前端（index.html + three.js r160 本地 vendor）、Playwright、pytest 风格单测（test_game.py，unittest 门禁 scripts/local_ci.ps1）。

**Spec:** `docs/superpowers/specs/2026-10-18-element-reactions-design.md`（含 oracle 审核修订 M1-M9；数值均为提案非承诺）

## Global Constraints

- `PROTO_VER = 29`（serve.py:48 与 index.html 客户端常量**同步 bump**；改协议必须双端）。
- 元素 id 仅 `'pyro'|'hydro'|'cryo'|'electro'`；反应表 6 条：frozen=水×冰、vaporize=火×水、melt=火×冰、overload=火×雷、electro=水×雷、superconduct=冰×雷；同元素不反应。
- 常量（提案值，照抄）：`AURA_MS=8000`、`EB_CD=2000`、`EB_SPD=1.2`、`ULT_REACT=15`、`FROZEN_MS=1600`、`SLOW_MS=3000`、反应额外截短 +1 格、eterrain 总数 `clamp(cols*rows*0.015*elem_amt, 0, 60)`、每簇 2-4 格、`elem_amt` 默认 0.6 范围 0-2、`elements` 默认 True。
- aura 反应后**双方双消**；传染（目标无 aura）后攻击方消耗；反应截短不并入 grow、不计分；attacker 已死跳过充能、victim 已死降级纯视觉 ev（spec 决策 18）。
- 大招弹（projectiles 无 `elem` 字段）不查表不附着；eb 基础不截短、不碎岩。
- 不改玩法既有数值（ULT_KILL/水减速/批32 弹道规则等）；地板与元素色板 polygonOffset 用 -2 档（批33 可见性修复）。
- 门禁：`pwsh scripts/local_ci.ps1` ALL GREEN；单测放 test_game.py（先红后绿）；新 DOM id 须入静态检查注册表。

## Review Focus

1. **frozen×顶头组合**：冻结头视作静止障碍——活蛇对头应 force_right 避让、frozen 蛇不累计 hstreak 不判 stuck 死。is_head_on/clash 逻辑遍历 due，frozen 已从 due 排除，需实测 head-on 分支不把 frozen 头当活对手。→ Task 6 Step 2 测试钉住。
2. **eterrain full/DELTA 双路**：晚加入者只收 full 帧——只挂 DELTA 会白屏级 bug。→ Task 3 Step 测试同时断言 full 带 eterrain 且 DELTA 序列化为三元组。
3. **旧档 persist 元素默认**：老房间 JSON 无 elements/elem_amt 字段必须默认 True/0.6，否则升级后全服房间静默关元素。→ Task 7 Step 测试「旧档加载默认值」。
4. **超载/感电密集房滚雪球**：半径内各截 1 格在蛇群中一波多杀；先按 spec 数值实现 + 单测钉住波及范围上界，调参留旋钮。→ Task 5 Step 测试断言攻击者免疫与半径边界。
5. **客户端旧页 PROTO 不匹配**：浏览器缓存旧 index.html 时 ver 拒绝路径是否仍进游戏——沿用既有 ver 拒绝提示即可，但本地探针需用无缓存上下文。→ Task 10 复验步骤注明。

---

### Task 1: 服务端常量 + REACTIONS 查表纯函数

**Files:**
- Modify: `serve.py:48-58`（常量区）
- Test: `test_game.py`

**Interfaces:**
- Produces: 常量 `ELEMS, AURA_MS, EB_CD, EB_SPD, ULT_REACT, FROZEN_MS, SLOW_MS, REACTIONS`；函数 `reaction_of(elem: str|None, target_elem: str|None) -> str|None`（返回反应名或 None；键用排序后元素对 tuple）。
- REACTIONS 精确表：`{('cryo','hydro'):'frozen', ('hydro','pyro'):'vaporize', ('cryo','pyro'):'melt', ('electro','pyro'):'overload', ('electro','hydro'):'electro', ('electro','cryo'):'superconduct'}`（tuple 元素按字母序，键即 `tuple(sorted((a,b)))`）。

- [ ] **Step 1: 写失败测试**（test_game.py 末尾，沿用现有 import/夹具风格）
  - `test_reactions_table_complete_batch33`：对 6 个无序元素对（含反序）`reaction_of` 返回对应反应名；共 12 次断言。
  - `test_reaction_same_or_none_elem_batch33`：`reaction_of('pyro','pyro') is None`、`reaction_of('pyro',None) is None`、`reaction_of(None,'hydro') is None`。
- [ ] **Step 2: 跑测试确认失败** —— `python -m pytest test_game.py -k batch33 -v`（或项目既有跑法）→ FAIL（ImportError/AttributeError）。
- [ ] **Step 3: 实现**：serve.py 常量区加常量与 `reaction_of`（模块级纯函数，键 `tuple(sorted((a,b)))` 查表）。
- [ ] **Step 4: 跑测试通过** → PASS。
- [ ] **Step 5: Commit** — `feat(批33): 元素反应表与查表纯函数`

### Task 2: aura 字段、附着/消耗、快照序列化

**Files:**
- Modify: `serve.py`（Room：玩家 dict 字段 `aura`、`spawn_player`、`snapshot` :1945-1961）
- Test: `test_game.py`

**Interfaces:**
- Produces: 玩家字段 `p['aura'] = {'e': elem_id, 'at': now_ms}` 或缺失=无；`Room.set_aura(p, elem, now)`（附着并刷新）；`Room.aura_of(p, now) -> str|None`（TTL 过期视作 None）；`Room.consume_aura(p)`（弹出）。snapshot `players[]` 增 `'aura'`：None 或 `{'e': ..., 't': 剩余ms}`。
- Consumes: Task 1 常量。

- [ ] **Step 1: 失败测试**
  - `test_aura_snapshot_and_ttl_batch33`：set_aura 后 snapshot `aura={'e':'pyro'}`；把 `at` 拨回 9s 前 → `aura_of` None、snapshot `aura is None`。
  - `test_spawn_clears_aura_keeps_on_off_batch33`：死亡 respawn 后 aura 无；置 `off_at`（挂起）aura 仍在（TTL 内）。
- [ ] **Step 2: 跑测试失败**。
- [ ] **Step 3: 实现** `set_aura/aura_of/consume_aura` + spawn_player 清 aura + snapshot 字段。
- [ ] **Step 4: 跑测试通过**。
- [ ] **Step 5: Commit** — `feat(批33): aura 附着/消耗/快照序列化`

### Task 3: eterrain 生成、进格附着、spawn 避让、full/DELTA 下发

**Files:**
- Modify: `serve.py`（Room.__init__ :511-527、`build_terrain` :699 附近、`spawn_player`、`snapshot` full :1977-1986 与 DELTA :1991-2004、`DELTA_FIELDS` :1939、`step` 移动后）
- Test: `test_game.py`

**Interfaces:**
- Produces: `Room.eterrain: dict[(x,y) -> elem_id]`；`build_eterrain()`（build_terrain 内调用）；蛇头进入格触发 `set_aura`（step 中每条成功移动的 due 蛇头格查表）；快照/DELTA 下发 `[[x, y, elem], ...]` 三元组。
- Consumes: Task 2 `set_aura`；`free_cells()`/`free_list()` 单点避让（顺带覆盖 rocks 与动态 items，M7）。

- [ ] **Step 1: 失败测试**
  - `test_eterrain_constraints_batch33`：生成后不与 rocks/walls/portals 重叠、不在 h∈{1,2,3,9} 格、总数 ≤60、四元素各 ≥1（elem_amt=0.6、中等地图）。
  - `test_eterrain_attach_and_spawn_avoid_batch33`：蛇头走到 eterrain 格 → aura=该元素；spawn 出生点不在 eterrain 格。
  - `test_eterrain_full_and_delta_batch33`：`snapshot(full=True)` 带 `eterrain` 三元组列表；改一格后 DELTA 帧 `eterrain` 键出现且同为三元组。
- [ ] **Step 2: 跑测试失败**。
- [ ] **Step 3: 实现**：`build_eterrain()`（四元素均匀、每簇 2-4 格、`clamp(cols*rows*0.015*eff_elem_amt,0,60)`）；`elements=False` 或 `elem_amt==0` → 不生成；step 移动后进格附着；spawn 主路径+兜底避让 eterrain；snapshot 双路下发。
- [ ] **Step 4: 跑测试通过** + 既有单测全过（不回归）。
- [ ] **Step 5: Commit** — `feat(批33): 元素地形 eterrain 生成/附着/下发`

### Task 4: eb 元素弹（消息、CD、弹道、命中分支）

**Files:**
- Modify: `serve.py`（消息处理 `atk` :3004 旁加 `elif t == 'eb'`；`_step_projectiles` :1887-1936；snapshot `proj` :1965-1968）
- Test: `test_game.py`

**Interfaces:**
- Produces: 消息 `{'t':'eb','elem':<ELEMS>}` → `p['eb_cd']` 门禁 → `projectiles` 条目含 `'elem'`；`_step_projectiles` 中 elem 弹命中蛇分支（无 aura→set_aura；异→反应；同→刷新；基础不截短；不碎岩——岩石格直接消散）；snapshot proj 带 `'elem'`（仅元素弹）。
- Consumes: Task 1 `reaction_of`、Task 2 `set_aura`；Task 5 `apply_reaction`（本任务先用「附着/刷新」分支，反应分支接 Task 5 的入口，接口先定好）。
- 门禁：`room.elements` 关闭、`not p['alive']`、`p.get('pause')`、frozen（Task 6 前先查 pause/off，frozen 键 Task 6 统一补，此处留 `room.effect_active(p,'frozen',now)` 直接写——eff 键未产生时恒 False，无副作用）。

- [ ] **Step 1: 失败测试**
  - `test_eb_attach_and_cd_batch33`：发 eb → 条目含 elem；2s 内二次拒发；跨 `EB_CD` 可再发。
  - `test_eb_hit_attach_refresh_batch33`：目标无 aura → 命中后有 aura=弹元素、弹消、目标 cells 长度不变（基础不截短）；目标同 aura → `at` 刷新；目标异 aura → 本步断言「ev react 触发」（具体效果 Task 5 补断言，先断言 ev 通道出现）。
  - `test_eb_no_rock_and_gates_batch33`：eb 打岩石不碎岩（rocks 不变、弹消）；`elements=False` 房拒收；死/pause 拒发。
  - `test_eb_cross_layer_batch33`：目标节 h 与弹 h 差 >1 不命中（复用批32 夹具）。
- [ ] **Step 2: 跑测试失败**。
- [ ] **Step 3: 实现**。
- [ ] **Step 4: 跑测试通过**。
- [ ] **Step 5: Commit** — `feat(批33): 元素弹 eb 消息/弹道/命中分支`

### Task 5: apply_reaction 统一入口、咬击/碾压/反噬接入、充能

**Files:**
- Modify: `serve.py`（新方法 `Room.apply_reaction`；bites 循环 :1638-1698 三路径）
- Test: `test_game.py`

**Interfaces:**
- Produces: `Room.apply_reaction(attacker: dict|None, victim: dict, kind: str, x: int, y: int, now: int)`：
  1. `ev('react', kind=kind, by=attacker id or None, victim=victim id, x, y)`；
  2. victim 已死（`not victim['alive']`）→ 到此为止（纯视觉，M6）；
  3. 效果：vaporize/melt → victim 截 1 格（`cells[:-1]`，MIN_LEN 保护）；overload → 命中点半径1内其他蛇（不含 attacker）各截 1；electro → victim 与曼哈顿≤2 内 id 序最小另一条蛇各截 1；superconduct → 半径2内所有蛇（含 victim）`eff['slow']=now+SLOW_MS`；frozen → `victim['eff']['frozen']=now+FROZEN_MS`；
  4. 双方 aura 双消（`consume_aura` ×2）；
  5. attacker 且 `attacker['alive']` → `attacker['ult']=min(ULT_MAX, +ULT_REACT)`。
  - 咬击接入：bites 循环普通截断/碾压/反噬三路径，攻击元素=`aura_of(attacker)`：有且 victim 有异 aura → `apply_reaction`；有且 victim 无 aura → 传染（set_aura(victim)+consume_aura(attacker)）；无 → 无事。
- Consumes: Task 1/2 全部接口。

- [ ] **Step 1: 失败测试**
  - `test_bite_reaction_all_six_batch33`：构造 6 组 aura 对（夹具直写 `p['aura']`）→ 咬击 → 各反应名 ev、效果数值断言（超载波及断言攻击者免疫与半径上界、感电断言 id 序第二目标、冻结断言 eff 存在）。
  - `test_reaction_dual_consume_and_infect_batch33`：反应后双方 aura 皆无；传染后 victim 获 aura、attacker 消耗。
  - `test_react_charge_and_dead_degrade_batch33`：+ULT_REACT 封顶 ULT_MAX；attacker 已死（反噬路径）不充能但效果在；victim 已死仅 ev。
  - `test_crush_result_unchanged_batch33`：高撞低带异 aura → victim 仍死（cause=crush），反应不改写致死。
- [ ] **Step 2: 跑测试失败**。
- [ ] **Step 3: 实现**。
- [ ] **Step 4: 跑测试通过** + 全量单测不回归。
- [ ] **Step 5: Commit** — `feat(批33): 命中全算反应入口与充能`

### Task 6: frozen / slow eff 接线（due 排除、门禁、tick）

**Files:**
- Modify: `serve.py`（`step` due 过滤（off_at 排除处 :1301 一带）、`tick_of` :1194-1200、消息门禁 dir :2997 / atk :3005 / ult :3017 / eb（Task 4 已写））
- Test: `test_game.py`

**Interfaces:**
- Consumes: Task 5 的 eff 写入。
- Produces: frozen 蛇不移动（due 排除）、不累计 hstreak、可被咬不免疫、`dir/atk/ult/eb` 拒收；`tick_of`：slow 有效时最后乘 1.5（叠加水减速之后）。

- [ ] **Step 1: 失败测试**
  - `test_frozen_no_move_and_recover_batch33`：frozen 蛇 1.6s 内 cells 不变，到期后恢复移动。
  - `test_frozen_bitable_and_no_stuck_batch33`：frozen 蛇可被咬（截断发生）；frozen 蛇与他蛇顶头 hstreak 不累计（`hstreak` 无或 0）、活蛇侧照常 force_right。
  - `test_frozen_input_gates_batch33`：frozen 期间 dir/atk/ult/eb 均无效。
  - `test_slow_ticks_batch33`：slow 有效 tick_of = 基速 ×1.5（整数化后断言）。
- [ ] **Step 2: 跑测试失败**。
- [ ] **Step 3: 实现**（due 过滤加 `not room.effect_active(p,'frozen',now)` 语义；三消息门禁加同一条件；tick_of 尾部乘 1.5）。
- [ ] **Step 4: 跑测试通过** + 全量不回归。
- [ ] **Step 5: Commit** — `feat(批33): 冻结/减速效果接线`

### Task 7: 房间配置 elements / elem_amt（四 ingress + persist 默认）

**Files:**
- Modify: `serve.py`（Room.__init__ :511-527、`eff_elem()`、`info()` :850-881、create :2500-2579、roomcfg :2595/:2678、rooms 列表 :2067、persist 恢复 :2118、persist 保存路径）
- Test: `test_game.py`

**Interfaces:**
- Produces: `self.elements: bool`（默认 True，`isinstance` 防御）、`self.elem_amt: float`（clamp 0-2，默认 None→读 0.6）；info() 增 `'elements'`、`'elemAmt'`；create/roomcfg 支持 `elements`/`elemAmt`；persist 往返含两字段，**旧档缺字段 → True/0.6**。

- [ ] **Step 1: 失败测试**
  - `test_elements_roomcfg_and_persist_batch33`：默认 True/0.6；roomcfg 改 False/0 生效；persist 保存→恢复往返保留。
  - `test_old_persist_defaults_batch33`：构造不含两字段的旧档 dict → 加载后 True/0.6。
- [ ] **Step 2: 跑测试失败**。
- [ ] **Step 3: 实现**。
- [ ] **Step 4: 跑测试通过**。
- [ ] **Step 5: Commit** — `feat(批33): 元素房间旋钮与 persist`

### Task 8: PROTO 29 + 客户端（HUD/光晕/渲染/浮字/罩色/编辑面）

**Files:**
- Modify: `serve.py:48`（PROTO_VER=29）
- Modify: `index.html`（客户端 ver 常量、HUD、渲染、ev switch :3227-3290、房间编辑面板、预测门控）
- Test: 静态检查（scripts/local_ci.ps1 静态检）+ 手动探针

**Interfaces:**
- Consumes: 协议全字段（snap players[].aura、snap eterrain、proj[].elem、eb 消息、react ev、eff slow/frozen、info elements/elemAmt）。

- [ ] **Step 1: 服务端 ver bump** —— serve.py:48 → 29；index.html 客户端 `PROTO_VER` 同步（grep 'PROTO' index.html 找到常量处）。
- [ ] **Step 2: 元素 HUD** —— 四色胶囊按钮 + 键 1-4 切换 + E/HUD 按钮发 `eb`（本地 eb_cd 预估置灰）；`info.elements===false` 时隐藏。默认元素 pyro。
- [ ] **Step 3: aura 光晕** —— 蛇渲染循环按 `ent.aura`（快照 `{e,t}`）给蛇身外圈元素色 emissive/描边，无 aura 撤；自机与他蛇同路径。
- [ ] **Step 4: eterrain 渲染** —— full/DELTA 三元组建/清面片（polygonOffset -2、抬升 0.01、半透明元素色）；eterrain 变更键重建。
- [ ] **Step 5: react 浮字 + eff 罩色** —— ev switch 加 `case 'react'`（世界坐标浮字：反应名中文（冻结/蒸发/融化/超载/感电/超导）+ 元素色）；`slow` 青白罩、`frozen` 冰蓝罩（复用现有 eff 罩管线）。
- [ ] **Step 6: 编辑面两旋钮** —— 仿批32 三旋钮面板加「元素反应」开关与「密度」滑杆，create/roomcfg 消息带 `elements/elemAmt`，info 回填。
- [ ] **Step 7: frozen 预测门控** —— 自机 `eff.frozen` 有效时本地预测暂停推进，解冻恢复。
- [ ] **Step 8: 静态检查** —— 新 DOM id 注册入册（local_ci 静态检 dup=0 / ids 注册齐全）。
- [ ] **Step 9: Commit** — `feat(批33): PROTO 29 客户端元素反应界面`

### Task 9: E2E（python 冻结场景 + Playwright HUD spec）

**Files:**
- Create: `e2e/` 下仿既有 python E2E 模式的反应场景文件（先看既有 `e2e/` 与 test_reconnect_p5.py 模式再落名）
- Create: `e2e/reactions.spec.js`（Playwright）
- Modify: `scripts/local_ci.ps1`（若 E2E 套数显式登记）

- [ ] **Step 1: 写 python E2E** —— 双真人房：A 站**冰** eterrain 获 cryo aura（直写服务端状态或走 eb），B 获 hydro aura，A 咬 B → ev `react kind=frozen` 送达 + B 若干 tick 内 cells 不动 + 截 0（基础不截短，冻结无截）。
- [ ] **Step 2: 写 Playwright spec** —— 元素房 HUD 四按钮可见、键 1-4 切换选中态、E 发弹（`proj` 增长）；`elements=false` 房按钮隐藏。
- [ ] **Step 3: 跑通** —— `pwsh scripts/local_ci.ps1` 内 E2E 全绿。
- [ ] **Step 4: Commit** — `test(批33): 元素反应 E2E`

### Task 10: 门禁、部署、生产复验、文档回写

- [ ] **Step 1: 全量门禁** —— `pwsh scripts/local_ci.ps1` → ALL GREEN（单测/E2E/静态检/Playwright 冒烟）。
- [ ] **Step 2: 部署** —— `scp index.html serve.py tencent:/home/ubuntu/snake-3d/` + `sudo systemctl restart snake-3d` + http 200。
- [ ] **Step 3: 生产复验** —— Playwright（无缓存上下文）登录进局：PROTO 29 生效、元素 HUD 可见、发弹/附着/反应浮字出现、`errs=[]`、截图存证。
- [ ] **Step 4: 文档回写** —— HANDOVER.md（协议表/测试计数/新功能段）、BACKLOG.md（批33 完成记录 + 残余 Deferred）；commit + push。
- [ ] **Step 5: Commit** — `docs(批33): HANDOVER/BACKLOG 回写`
