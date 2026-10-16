# 自机预测 + 回滚（转向跟手）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让自机转向本地立即生效（预测+回滚），消除 RTT/快照等待造成的「落后一拍」。

**Architecture:** 仅客户端：IIFE 内新增 `predictor` 纯函数集 + 三个钩子（snap 处理游标同步/回放对账、rAF 推进、帧末渲染投影），服务器快照仍是唯一真相，不一致回滚。探针经 `window.__pred*` 逃逸钩子 + `__predGate` 隔离真实 snap 流。

**Tech Stack:** 单文件 index.html（vanilla JS）、Playwright（e2e/pred.spec.js）、PowerShell 门禁。

**Spec:** `docs/superpowers/specs/2026-10-16-prediction-design.md`（v5，四轮 oracle 审阅 PASS）——所有算法细节（双游标、位置等式递减、三分支、相位重锚、悬停相位）以 spec 为准，本计划只锁定文件/签名/断言/顺序。

## Global Constraints

- 零服务端改动：`serve.py`/`test_game.py` 不动；单测恒 **142** 全绿。
- 零协议改动：不 bump `PROTO_VER`、不加 snap 字段。
- 门禁三件套（每任务收尾）：`.venv\Scripts\python.exe test_game.py`（142）；`node scripts\static_check.js index.html`（ALL STATIC CHECKS PASSED，Task 1 落仓后）；`pwsh scripts\local_ci.ps1` ALL GREEN（Task 4/5 全量跑）。
- index.html 主逻辑在 IIFE 内（:836 起）：探针只经 `window.__*` 钩子；`page.evaluate` 不得直调私有函数。
- Playwright 基址 `http://127.0.0.1:8123`（local_ci 自起；单跑需先 `$env:PORT='8123'; Start-Process .venv\Scripts\python.exe -ArgumentList serve.py -WindowStyle Hidden`）。
- 中文 commit message 一律 `-F <UTF-8 无BOM 临时文件>`。
- 不弱化既有 `dirQ` 裁剪/清队与跟随视角；不改插值对其他实体的行为。
- 退路开关（spec §9）：预测实现里留模块级常量 `PRED_ENABLED = true`，hook2 条件首项引用它——不做事后补丁。

## Review Focus（最可能咬人的 5 处，各有归属测试）

1. **gate 关闭瞬间**：首个真实 snap 必触发 reconcile（pred 基于注入态时会回滚）——所有断言必须在 gate 开期间完成（spec §7.1 已注记）；T1/T2/T3 均遵守。
2. **每帧重入推进**：悬停/上限悬停后 `lastMoveAt` 未累加 → `now≥predNextMoveAt` 恒真每帧连推 → T4 固件断言「撞墙悬停后 cells 不变且 lastMoveAt 前移」「连续 predAdvance 两次 leadCells ≤ 1」。
3. **seamless 还原四元组遗漏**：applyPlayers 覆盖未还原 → 20Hz 回摆（方案 B 回归）→ T1 增补「连续两帧同位置 snap 后 `__predState.proj.cells` 仍等于 pred.cells」。
4. **游标与裁剪错位**：appliedInputs 越界/消费错输入 → T4 ③⑤ clamp 固件 + T1 按键后注入 `q:0` snap 不 crash。
5. **interval 漏 speed×0.6**：道具期错相连续回滚 → T4 固件断言 `eff.speed>0 → interval = max(60, floor(tick*0.6))`（公式经 `__predDbg.mkPred` 观测或 interval 计算函数导出）。

---

### Task 1: 静态检查门禁入仓（可复现）

**Files:**
- Create: `scripts/static_check.js`（vendor 自 `C:\Users\yuan\AppData\Local\Temp\opencode\static_check.js`，逐字节复制）
- Modify: `scripts/local_ci.ps1:75-84`（静态检查段）

**Interfaces:**
- Consumes: 无
- Produces: `scripts/static_check.js`（用法 `node scripts\static_check.js index.html`，输出含 `ALL STATIC CHECKS PASSED` 且 exit 0）

- [ ] **Step 1:** 复制 Temp 的 static_check.js 到 `scripts/static_check.js`；改 local_ci.ps1:76 为 `$staticJs = Join-Path $root 'scripts\static_check.js'`，else 分支（:82-84）改为 `Write-Host "  (static_check.js 缺失)" -ForegroundColor Red; Check "静态检查(缺失)" $false`（缺失即 FAIL，spec §7.2）。
- [ ] **Step 2:** Run: `node scripts\static_check.js index.html` → 预期 `ALL STATIC CHECKS PASSED`、exit 0。
- [ ] **Step 3:** Run: `pwsh scripts\local_ci.ps1 -SkipE2E -SkipPlaywright` → 预期单测 142 + 静态检查 PASS，`ALL GREEN`。
- [ ] **Step 4:** Commit（`scripts/static_check.js` + `scripts/local_ci.ps1`）：`chore(b28 C): static_check.js 入仓 + local_ci 静态门禁缺失即 FAIL`。

### Task 2: 探针钩子空壳 + pred.spec.js（真 RED）

**Files:**
- Modify: `index.html`（IIFE 尾部 `window.__gachaDbg` 定义处 :3934 旁，新增探针钩子；并让 `__gachaDbg` 打标 `m.__dbg = 1`）
- Create: `e2e/pred.spec.js`

**Interfaces:**
- Produces（空壳，Task 3/4 填充）:
  - `window.__predState()` → `{active:false, id, round, cols, rows, cells:null, moveDir:null, previewDir:null, leadCells:0, appliedInputs:0, snapsApplied:0, lastMoveAt:0, proj:null}`（`id=myEnt?myEnt.id:null, round=roundNo, cols/rows=棋盘模块变量`——按 ensureBoard 写入的实际变量名取）
  - `window.__predGate(on)` → 空壳（记录 `predGateOn=on`，无其他行为）
  - `window.__predDbg` → 空壳 `{}`（Task 3 导出纯函数）
  - `__gachaDbg` 改为 `m => { m.__dbg = 1; onMsg(m); }`（Task 3 gate 用 `!m.__dbg` 区分真实/注入 snap）
  - snap 分支 :2558 `if (m.t === 'snap') {` 后插入 `if (predGateOn && !m.__dbg) return;`（空壳期恒透传）

- [ ] **Step 1:** 写 `e2e/pred.spec.js` 四测（join 载体 = `#btnSolo` 单人练习，先例 smoke.spec.js:46-65）：
  - `T1 本地预测激活与预览不回退`：goto → click #btnSolo → 等 startScreen hidden → `st0=__predState()` → `__predGate(true)` → 注入基准 snap `{t:'snap', round:st0.round, cols:st0.cols, rows:st0.rows, players:[{id:st0.id, name:'P', cells:[[10,12],[9,12],[8,12]], dir:{x:1,y:0}, len:3, q:0, tick:150, alive:true, score:0, eff:{}, off:false}]}`（经 `__gachaDbg`）→ rAF×6 → 按 `ArrowUp` → rAF×12 → 断言 `active===true && leadCells>=1`；再注入同基准 snap → 断言 `previewDir=={x:0,y:-1}` 且 `moveDir=={x:0,y:-1}`；**增补（Review Focus 3）**：再注入同 cells snap → 断言 `proj.cells` 等于 `__predState().cells`；`__predGate(false)`。
  - `T2 矛盾 snap 回滚收敛`：gate(true) → 注入基准（同 T1 形状，cells [[10,12],[9,12],[8,12]] dir E）→ rAF×6 → `ArrowUp` → rAF×12 → 读 `st=__predState()` → 注入追赶 snap（cells=st.cells、dir={x:0,y:-1}、q:0、tick:150）→ 注入矛盾 snap `{players:[{id:st0.id, cells:[[3,3],[2,3],[1,3]], dir:{x:1,y:0}, q:0, tick:150, alive:true, eff:{}, off:false}]}` → rAF×2 → 断言 `__predState().cells` 等于 `[[3,3],[2,3],[1,3]]`；gate(false)。
  - `T3 alive:false 停用预测`：gate(true) → 注入基准 → rAF×6 → 注入 `alive:false` 同形 snap → rAF×3 → 断言 `active===false`；gate(false)。
  - `T4 predictor 固件（对账用例①-⑤ + 悬停/上限/interval）`：goto（无需入局）→ 经 `window.__predDbg` 直调纯函数断言（固件：空场 24×24、蛇 `[[5,5],[4,5],[3,5]]`、dir E、tick 150、eff 空）：
    - ①④ 空队列推进一步后 `predReconcile(pred, server(E,未动), …)` → `'seamless'` 且 `leadCells===1`；
    - ② server cells==pred.cells → `'seamless'` 且 `leadCells===0`；
    - ③⑤ `syncApplied(pred, n)` clamp：`(appliedInputs:2, n:5)→0`、`(2, 1)→1`；
    - 悬停（wall at [6,5]）：`predAdvance` 后 cells 不变且 `lastMoveAt` += interval、leadCells 不增；
    - 上限：连调 `predAdvance` 两次 → `leadCells ≤ 1`；
    - interval：`eff={speed:2000}, tick:150` → interval === 90（`max(60, floor(150*0.6))`）。
- [ ] **Step 2:** Run: 起 8123 → `npx playwright test e2e/pred.spec.js` → 预期 **RED**：T1 失败于 `active===true`、T2 失败于 cells 断言、T3 空壳性通过（守卫测，注记）、T4 失败于 `__predDbg` 未导出。
- [ ] **Step 3:** Commit（index.html 空壳 + e2e/pred.spec.js）：`test(b28 C): 预测探针 RED 基线落盘（__predState/__predGate/__predDbg 空壳 + 4 探针）`。

### Task 3: predictor 纯函数集 + gate + hook2（T1/T4 GREEN）

**Files:**
- Modify: `index.html`（新增 predictor 区块，置于 IIFE 内、`applyPlayers` 定义之前；snap 分支 :2558 起；frame() :3035-3079）

**Interfaces:**
- Consumes: Task 2 空壳与 gate 插槽。
- Produces（Task 4 依赖，签名锁死）:
  - `mkPred(cells, dir, interval, now)` → pred `{cells, prevCells, moveDir, appliedInputs:0, leadCells:0, lastMoveAt:now, interval, active:true}`
  - `predNextMoveAt(pred)` → number
  - `advanceStep(state{cells,dir}, input{x,y}|null, world, foods, eff)` → `{cells, dir, hovered}`——**唯一转移内核**：非反向才换向；墙/岩/门入口/出界 → hovered（`eff.shield||eff.deflect>0` 时不悬停）；落在 foods 保留尾巴；成功 `lastMoveAt` 由调用方累加
  - `predAdvance(pred, dirQ, world, foods, eff)`——消费 `dirQ[pred.appliedInputs]`；`leadCells>=1` → 悬停语义；成功推进 + `leadCells+=1` + 消费才 `appliedInputs+=1` + `lastMoveAt+=interval`
  - `predReconcile(pred, serverMy, dirQ, world, foods, eff)` → `'seamless'|'reanchor'|'rollback'`（spec §5.0 全规则：位置等式递减、`expected=advanceN(…min(appliedInputs,leadCells)-1…)`、比较域 `{cells, moveDir}` 尾长容差 ±1、相位阈 `>interval/3`）
  - `syncApplied(pred, n)` → `appliedInputs = max(0, appliedInputs - n)`
  - `world = {walls:Set('x,y'), rocks:Set, portals:Set, cols, rows}`、`foods = Set('x,y')`（hook 侧从既有 `wallCells/portalCells/rocks/foods/bonus` 构建）
  - `window.__predDbg = {mkPred, advanceStep, predAdvance, predReconcile, syncApplied}`
  - interval 公式：`eff && eff.speed>0 ? Math.max(60, Math.floor(tick*0.6)) : tick`
- [ ] **Step 1:** 实现 predictor 纯函数集（含 advanceStep 同构内核），导出 `__predDbg`；填 `__predState` 预测字段（仍无 hook 时 active 恒 false 不影响——本步结束时 T4 先绿）。
- [ ] **Step 2:** gate 真实现：`predGateOn` 已在 :2559 生效（Task 2 插槽）；确认注入 snap（`m.__dbg`）不受拦截。
- [ ] **Step 3:** hook2（frame() 内、插值/绘制前）：条件 `PRED_ENABLED && joined && myEnt && myEnt.alive && !myEnt.off && !spectating && state==='playing' && !winRound && wsOpen`；首拍有效 snap 已建基准（`pred` 在 snap 分支 :2563 后懒建，见 Task 4 前置——本步允许「无 pred 则跳过」）；`now ≥ predNextMoveAt(pred)` → `predAdvance` 并写投影 `prevCells=旧投影, lastCells=旧投影, cells=pred.cells, moveAt=pred.lastMoveAt, moveDt=pred.interval`；帧末（syncEnt 循环后）`myEnt.dir = pred.moveDir; myEnt.rotT[0] = atan2(previewDir.x, previewDir.y)`（`previewDir = dirQ.length ? dirQ[dirQ.length-1] : pred.moveDir`）。pred 建基准放 snap 分支：`applyPlayers+裁剪后，若 !pred 且条件满足 → mkPred(myEnt.cells, myEnt.dir, interval, now)`。
- [ ] **Step 4:** Run: `npx playwright test e2e/pred.spec.js` → 预期 **T1 PASS、T4 PASS**，T2/T3 仍红（hook3 未接）。
- [ ] **Step 5:** Commit：`feat(b28 C): predictor 纯函数集 + gate + hook2 本地推进（T1/T4 绿）`。

### Task 4: hook3 对账 + 停用/重置点（T2/T3 GREEN）

**Files:**
- Modify: `index.html`（snap 分支裁剪后 :2572；applyPlayers 复活清队 :2252；§6 九处 `dirQ = []` 清队点 :1890/:1943/:1986/:2597/:2611/:2703/:2747/:2794/:2826）

**Interfaces:**
- Consumes: Task 3 全部签名。
- Produces: snap 分支内 `predGateOn` 放行路径的统一后处理（游标同步 → reconcile → 投影三分支处置 → 相位重锚 → `snapsApplied++`）。

- [ ] **Step 1:** 游标同步：:2565-2572 既有裁剪处记录 dir 循环移除数 N 与 `q` 截断移除数 M（`dirQ.length` 差分），裁剪后 `if (pred) syncApplied(pred, N + M)`。
- [ ] **Step 2:** hook3（同分支、裁剪之后）：条件满足时 `const r = predReconcile(pred, myEnt服务器快照副本, dirQ, world, foods, myEnt.eff)`——注意 `serverMy` 须取 applyPlayers 写入前的服务器 cells：在 `applyPlayers(m.players, now)` **之前**暂存本 snap 自机 cells/dir/q/tick 副本传入。按 r 处置：seamless/reanchor → `myEnt.cells=pred.cells; myEnt.lastCells=pred.prevCells; myEnt.moveAt=pred.lastMoveAt; myEnt.moveDt=pred.interval`（reanchor 另校 `pred.lastMoveAt`）；rollback → `pred.cells=pred.moveDir=expected; pred.prevCells=服务器旧位置`（渲染沿用 applyPlayers 锚点，不覆写）。末尾无状态相位重锚：`leadCells==0 → pred.lastMoveAt = now`。`pred.active=false` 时跳过一切投影写回。
- [ ] **Step 3:** 停用/重置（spec §6）：新增 `function clearDirQ(){ dirQ = []; pred = null; }`，§6 九处 `dirQ = []` 全部替换为 `clearDirQ()`（含 :2252 服务器复活点）；`myEnt` null/id 变化通用规则放 hook2/入口处 `if (pred && (!myEnt || pred.id !== myEnt.id)) pred = null`；`!myEnt.alive` → `pred.active=false`；`winRound/off` 已由 hook2 条件排除。
- [ ] **Step 4:** Run: `npx playwright test e2e/pred.spec.js` → 预期 **四测全绿**。
- [ ] **Step 5:** Run: `node scripts\static_check.js index.html` → ALL STATIC CHECKS PASSED。
- [ ] **Step 6:** Commit：`feat(b28 C): hook3 对账回滚 + 停用重置点（pred 4 探针全绿）`。

### Task 5: 全量门禁 + BACKLOG 回写

**Files:**
- Modify: `BACKLOG.md`（批28 段回写 C 项交付记录）

- [ ] **Step 1:** Run: `pwsh scripts\local_ci.ps1` → ALL GREEN（8 E2E + 单测 142 + 静态 + Playwright 全量含 pred 4 项）；若 local_ci 有残留 serve.py 先杀（防 8123 冲突）。
- [ ] **Step 2:** BACKLOG.md 批28 段回写：C 项 done（spec v5 + 本计划 + commit 号），遗留=部署后 §7.3 手感验收（生产 8090 实操）。
- [ ] **Step 3:** Commit：`docs(b28 C): BACKLOG 回写 + 门禁全绿记录`。
- [ ] **Step 4:** 收尾汇报（契约自评 + 剩余风险）；**部署生产 + push 双远端按批27/28 惯例交付后单独询问用户**（本批27/28 累计未 push commit：`25f1b5d`/`c024579`/`320fb8a` + 本计划 commits）。

---

## 计划自评（writing-plans self-review）

1. **Spec 覆盖**：§4.1 纯函数（Task 3）、§4.2 三钩子（Task 2 插槽/Task 3 hook2/Task 4 hook3）、§4.3 interval+相位（Task 3 公式、Task 4 重锚）、§5.0 五用例（T4 固件）、§5.1/§5.4 悬停（T4 固件）、§6 停用表（Task 4 Step 3）、§7.1 四探针（Task 2）、§7.2 门禁（Task 1/5，含 static_check 入仓与缺失即 FAIL）、§9 退路开关（Global Constraints `PRED_ENABLED`）。无缺口。
2. **Step 扫描**：每步一个可判定动作；实现体只给签名与算法定则（算法本体在 spec，未复写）。
3. **类型一致性**：pred 字段名（appliedInputs/leadCells/prevCells/moveDir）与 spec v5 §4.1 一致；`syncApplied/advanceStep/predReconcile` 签名在 Task 3 定义、Task 4/T4 消费一致。
4. **Review Focus**：5 条各有归属测试（T1 增补断言、T4 固件、T1/T2 gate 纪律）。
5. **比例**：计划 ~180 行 ≈ spec 的 1.1 倍，代码块仅签名与断言，无转录。
