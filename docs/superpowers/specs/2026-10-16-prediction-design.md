# 自机预测 + 回滚（转向跟手）设计 Spec

> 批28 · 项 C。2026-10-16 · 状态：v5（四轮 oracle 审阅后修订）。v4 关闭 MAJOR-2/MINOR-2/NIT-1/NIT-2；v5 关闭 MAJOR-R（相位重锚改无状态条件 leadCells==0 → 重锚、领先不动，与 §5.0 递减同族）、MINOR-c1（:60 echo 同步 (N+M)）、MINOR-c2（predAdvance 强制 leadCells≤1）、NIT（hook2 moveAt=pred.lastMoveAt 对齐）。四审推演结论：§5.0 位置等式规则四场景自洽、硬边界全满足。待 writing-plans 出实施计划。

## 1. 目标与意图

用户原话：「总感觉转向会落后操作一拍」。

根因（已查证，非 bug 而是架构性延迟）：

- 客户端**无本地预测**：`setDir`（index.html:2124-2139）只 `send({t:'dir'})` + 入 `dirQ`（`dirQ` 仅供跟随视角计算，:883），自机视觉蛇身完全等服务器回传 cells 才转向。
- 服务端**无多余一拍**（排除 bug）：收到 `dir` 立即入队 `p['queue']`（serve.py:2637-2638）；`game_cycle` 对到期蛇**先应用方向队列再用新方向算目标格**（:1314-1318 → :1328-1329），同移动周期生效。
- **延迟三段构成**：网络 RTT/2 + 等下一移动周期（`p['tick']`，基础 150ms/格，量化在 50ms cycle 上，0~50ms 额外排队）+ 渲染插值（`moveDt` 下限 60ms，index.html:2232/2907）。合计在远程服务器上 ≈ 2~3 拍。

目标：按键转向在自机**本地立即生效**并按服务器移动节奏本地推进，不等 RTT/下一帧快照；服务器快照始终是真相，不一致即回滚。开放地（直线/普通转向）应无感跟手；边缘复杂情况允许一次可见回弹。

## 2. 已拍板决策（用户逐项确认）

1. 方向：**客户端自机预测 + 回滚（真·跟手）**——否决「接受现状」「自机插值降滞后（治标）」「降 tick 50→33ms（改玩法数值）」。
2. 精度：**常见移动预测，边缘允许回弹**——否决「完整复刻服务器移动规则」与「仅即时转向反馈（最保守）」。
3. 对账：**方案 A：tick 锚定 + 输入缓冲回放对账**——否决方案 B（每帧硬对账：预测超前会被服务器快照逐帧回拉，产生微抖，抵消顺滑目标）。

## 3. 事实基础（预测所依赖的既有机制，零服务端改动）

| 事实 | 位置 |
| --- | --- |
| 服务器每 50ms 向订阅者广播 `snap`，含自机 `cells`/`dir`/`q`/`tick`/`eff`/`off` | serve.py:1731-1744（`q`:1735、`tick`:1736、`eff`:1738、`off`:1743、`'t':'snap'`:1746） |
| `p['tick']` = **移动间隔毫秒**（非计数器）：基础 150（:2022）、速度档位下限 60（:2030-2036）、吃果 -3（:1537-1538） | serve.py:2022, 2030-2036, 1537-1538, 1736 |
| **speed 道具不改 `p['tick']`**：实际间隔 = `tick_of()` = 效果期 `max(60, int(base*0.6))` | serve.py:1044-1048（效果剩余 ms 由 `eff.speed` 下发 :1738，客户端落位 index.html:2240） |
| `q` = 服务端方向队列未消费长度；客户端既有裁剪：先按 `myEnt.dir` 逐条 shift，再按 `q` **只缩不增**截断 | index.html:2565-2572 |
| 移动量化在 50ms cycle（`due` 到期检查），`CYCLE=0.05` | serve.py:19, 1300-1306 |
| **结算窗口/挂起期服务器全房或本蛇冻结移动**：`win_pending` 时 `step()` 直接 return（:1289-1298）；`due` 排除 `off_at`（:1301），snap 仍带 `alive=true`+`off`（:1743） | serve.py:1289-1301 |
| **护盾/偏转效果期服务器照常移动**（护盾=任何地形折返不死；偏转=仅边界墙折返） | serve.py:1411-1414 |
| `applyPlayers` 是 `myEnt.cells` 唯一现实写入者：`cellsChanged` 任一坐标不同即 true（:2192）→ 覆盖 `lastCells/cells/moveAt/moveDt`（:2226-2233）→ 每 snap 无条件覆写 `e.dir`（:2235）；复活清队在 :2252 | index.html:2192-2254 |
| `syncEnt` 每帧无条件 `e.rotT[0]=atan2(e.dir.x,e.dir.y)`（:2901）、`phase`（:2907）；渲染读 `myEnt`（frame :3059 → syncEnt） | index.html:2898-2907, 3035-3079 |
| 客户端持有墙/岩/传送门/果：墙/门 `wallCells/portalCells`（:889，填充于 syncWalls:1712/syncPortals:1727）、岩（:868，applyWorld:2315-2338）、果/bonus（:864） | index.html:864/868/889 + applyWorld:2267-2343；serve.py:1722 DELTA_FIELDS, 1759-1783 |
| snap 处理入口：`applyPlayers`（L2563）→ dirQ 裁剪（L2565-2572）；入局/复活/新一局回 playing 清队 :2597 | index.html:2558-2602 |
| 探针逃逸口先例：`window.__gachaDbg` | index.html:3934 |
| 主逻辑在 IIFE 内，**不能** page.evaluate 直调私有函数 | index.html:836 起 |

## 4. 客户端设计（index.html，仅客户端）

### 4.1 组件：`predictor` 纯函数集（新增，不碰 DOM、可独立推理）

```js
predNextMoveAt(pred)                 // pred.lastMoveAt + pred.interval
predAdvance(pred, inputs, statics, foods, eff)
    // 到期推进一格（相位规则见 §4.3/§5.4）：若 dirQ[pred.appliedInputs] 存在且非反向 → 换向
    //   （pred.moveDir = 该输入；镜像服务器一次一转向），否则直行（moveDir 不变）；
    // 目标=墙/岩/传送门入口/出界(无幽灵) → 悬停（不改 cells，但 lastMoveAt += interval，见 §5.4）；
    // 上限强制（MINOR-c2）：若 leadCells >= 1 → 本拍按悬停处理（不改 cells、不消费输入、lastMoveAt += interval）——
    //   强制 leadCells ≤ 1，保 §5.0 无状态递减规则的前提（后台节流/弱网抖动 >1 interval 时防推进第 2 格）；
    // eff.shield/eff.deflect > 0 时**不悬停**（服务器效果期照常移动，:1411-1414），按普通推进；
    // 落在 foods/bonus 已知格 → 保留尾巴；否则去尾；
    // grow/长度类道具导致的长度差**不预测**（一次长度差属允许回弹，§5.3）
    // 推进成功：prevCells = 旧 cells → cells = 新格；leadCells += 1；本拍消费了输入才 appliedInputs += 1；
    //   相位推进 lastMoveAt += interval（与 §5.4 悬停对称——不推进则 now≥predNextMoveAt 恒真、每帧重入）
predReconcile(pred, serverMy, inputs, statics, foods, eff)
    // 对账算法见 §5.0；返回 'seamless' | 'reanchor' | 'rollback'
```

- `inputs` = 既有 `dirQ`——**只读不移出**；**两个正交游标分开记账**（NEW-B1）：`appliedInputs`（输入游标，恒 ≤ dirQ.length，既有裁剪 dir 循环移除 N 条 + `q` 截断移除 M 条时同步 `-= (N+M)` 并 clamp ≥0）与 `leadCells`（本地超前服务器的**格数**，与 dirQ 长度无关——服务器空队列也移动，:1300-1306）。
- `statics` = 持有的墙/岩/门，`foods` = 持有的果与 bonus。
- `pred = {cells, prevCells, moveDir, appliedInputs, leadCells, lastMoveAt, interval, active}`，只对自机存在。

### 4.2 三个钩子点与渲染归属契约

**归属契约（B1 闭合）**：预测生效时 `myEnt.cells/lastCells/moveAt/moveDt/dir/rotT[0]` 是 pred 的**渲染投影**。`applyPlayers` 仍照旧写服务器真相（不改它），但 hook 3 在**同一 snap 处理内、applyPlayers 之后**统一决定投影去向，使渲染永不出现「被服务器回退一格再前跳」的 20Hz 摆动：

1. **`setDir`（:2124）**：现状入队/发包不变 → **旋转预览只走投影层**（NEW-B2 方案①）：setDir 不改任何 pred 字段；预览朝向由帧末投影用 `dirQ` 尾计算。预览**不写 `pred.moveDir`、不进对账比较域** → 不会被首个 snap 的 reconcile 撤销；下一次 `predAdvance` 消费该输入时才真正换向。**格子推进不在此处**。
2. **渲染循环（rAF，predActive 时）**：条件 = `joined && myEnt && myEnt.alive && !myEnt.off && !spectating && state==='playing' && !winRound && wsOpen`（M3：补 win_pending/off 冻结）。`now ≥ predNextMoveAt` → `predAdvance`，并写投影 `prevCells=旧投影, lastCells=旧投影, cells=pred.cells, moveAt=pred.lastMoveAt（推进后值，与 hook3 还原式同源，NIT 对齐）, moveDt=pred.interval`——滑动从本地时刻起步，不再等快照到达。**帧末（frame 内 syncEnt 之后，且必须在 dirQ 裁剪之后——裁剪依赖 `myEnt.dir`==服务器 dir，:2565-2566）**对自机覆写投影：`myEnt.dir = pred.moveDir`、`myEnt.rotT[0] = atan2(previewDir.x, previewDir.y)`，其中 `previewDir = dirQ.length ? dirQ[dirQ.length-1] : pred.moveDir`（NEW-B2 预览层；相机朝向读 `myEnt.dir`（:3079）随**本地消费拍**响应——早于旧版的快照确认，属预期收益 NEW-N1）。
3. **snap 处理（:2563 applyPlayers 之后、:2565 dirQ 裁剪之后）**：先跑既有裁剪——**任何从 dirQ 头部的移除都同步游标**：dir 匹配循环移除 N 条 + `q` 截断移除 M 条（:2570-2571，服务端清队时的唯一收敛路径）→ `pred.appliedInputs = max(0, pred.appliedInputs - (N+M))` → `predReconcile`，按返回值处置渲染投影：
   - `seamless`（重放 == pred）：**还原本地投影**（NEW-M1：applyPlayers 的 cellsChanged 覆盖已改写四元组，须用 pred 持有的 `prevCells` 还原）——`myEnt.cells = pred.cells; myEnt.lastCells = pred.prevCells; myEnt.moveAt = pred.lastMoveAt; myEnt.moveDt = pred.interval`——渲染零抖动（moveAt 有来源，不沿用 applyPlayers 的 snap 到达时刻，防滑动相位每次回跳）。
   - `reanchor`（服务器与 pred 位置相同但相位漂移，如量化/网络抖动）：同 seamless 还原投影，仅 `pred.lastMoveAt` 校正。
   - `rollback`：`pred.cells = pred.moveDir = 重放结果`（`pred.prevCells = 服务器旧位置`），渲染投影**直接采用 applyPlayers 本次设的锚点**（lastCells=旧服务器位置, cells=服务器位置, moveAt=snap 到达时刻, moveDt=下限插值）——沿用既有滑动，不瞬移。
   - **相位重锚归属（NEW-M2/MAJOR-R）**：reconcile 末尾（§5.0 位置等式递减**之后**）以无状态条件判定——`leadCells == 0`（已被追平/未超前）→ `pred.lastMoveAt = 本次 snap 到达时刻（hook3 的 now）`；`leadCells == 1`（pred 领先）→ **不动相位**（领先时保留自由时钟，防相位被逐 snap 推平、预测收益归零）。恰在 rollback/追平后防 `now ≥ predNextMoveAt` 立即再推进一格。**勿用「本次 snap 发生 cells 变化」作条件**（hook3 在 applyPlayers 之后，无前一拍服务器 cells 可比，谓词语义反转）。

### 4.3 相位锚定与 interval（M1 闭合）

- 首次收到自机有效 snap 建基准；此后**仅当 `leadCells == 0`（未超前服务器）**才以本次 snap 到达时刻重锚 `pred.lastMoveAt`（MAJOR-R 无状态条件，与 hook3 一致；pred 领先时不动相位，防推平）（服务器移动量化在 50ms cycle，到达误差 ±50ms，由 150ms/格的插值滑动吸收）。
- **interval 公式（每帧取最新）**：`interval = (myEnt.eff && myEnt.eff.speed > 0) ? Math.max(60, Math.floor(myEnt.tick * 0.6)) : myEnt.tick`——`p['tick']` 不含 speed 道具 ×0.6（tick_of，serve.py:1044-1048），漏算会导致道具期每拍错相连续回滚。吃果/档位改的是 `tick` 本身，自然跟随。
- **超前上限一格**：本地绝不预测超过「上次移动 + interval」的下一格（`leadCells ≤ 1`，也是 §5.0 无状态递减规则成立的前提）。**相位三处更新点**：成功推进（lastMoveAt += interval）、悬停（§5.4 同款累加）、cells 变化锚点校正（§4.2 hook3 相位重锚）。

## 5. 对账与回滚规则

### 5.0 对账算法（B2/M5/NEW-B1/NEW-B2/NEW-M3 闭合，公式化）

- **双游标记账（NEW-B1）**：`appliedInputs` = 输入游标（≤ dirQ.length；既有裁剪 :2565-2572 从 dir 循环移除 N 条 + `q` 截断移除 M 条时，同函数同步 `-= (N+M)` 并 clamp ≥0，MINOR-1）；`leadCells` = 本地超前服务器的**格数**（与 dirQ 长度无关——服务器空队列也无条件移动 :1300-1306）。**服务器推进递减（无状态规则，MAJOR-1）**：reconcile 处以**位置等式**判定（勿复用 :2192 cellsChanged——hook3 在 applyPlayers 之后，其谓词比较对象是 pred 投影，pred 超前一格时恒真会导致每拍误递减）：`serverMy.cells == pred.cells → leadCells = 0`（已被追平）；否则**保持**（服务器未动则 pred 仍超前；服务器动到 `pred.prevCells` 亦不递减，由回放公式自洽）。**前提：`leadCells ≤ 1`（§4.3 超前上限一格）**——若计划放宽上限，须升级为 pred 存 `serverCells` 字段的有状态方案。
- **回放公式**：`expected = advanceN(serverMy.cells, serverMy.dir, dirQ[0 .. min(appliedInputs, leadCells)-1], statics, foods, eff)`——从服务器真相推进 `leadCells` 步到与 pred 同相位；输入不足处（min 截断/空队列）缺输入即直行。`advanceN` 与 `predAdvance` **同构**（NEW-M3：同一转移函数，含悬停/`eff.shield/deflect` 全规则），否则 seamless 永不可能。
- **比较域**：`{cells, moveDir}`——cells 逐格比较（长度差 ≤1 且超出部分为空/果尾时按公共前缀 + 尾长处理，±1 尾长差异不触发回滚）；`moveDir` 仅在 predAdvance 消费输入时变更。**预览朝向不参与比较**（NEW-B2 方案①：预览只在投影层用 dirQ 尾覆写 rotT，pending 输入不触发 rollback）。相位**不参与比较**（相位单独按 §4.3 处理，与三分支正交，NEW-M2）。
- **三分支**：`expected == pred` → seamless（位置一致；服务器慢半拍是常态，不回拉）；位置同但 `pred.lastMoveAt` 相对锚点漂移超阈（>interval/3）→ reanchor（仅校正相位）；位置/方向不一致（撞墙反弹、传送门、对头、眩晕、食物清单滞后等边缘）→ rollback（pred = expected，允许一次可见回弹）。
- **唯一输入源**：重放只用 `dirQ`（裁剪已含 `q` 对账，:2565-2572），杜绝双队列失步。`dirQ` 兼作跟随视角输入（:2130/:883），只读方案不改变其行为。
- **必测对账用例**（NEW-B1 回归）：①直线空队列（leadCells=1、appliedInputs=0 → expected=advanceN(server, 直行, [])=server+1 格 == pred → seamless 不回拉）；②超前一格被服务器追平（serverMy.cells==pred.cells → leadCells=0 → expected == pred → seamless）；③trim 与 cells 变化同帧到达（appliedInputs -= (N+M) 与位置等式同拍，游标不错位）；④leadCells=1 且服务器未动（serverMy.cells==pred.prevCells≠pred.cells → 保持 1，**不得递减**）；⑤服务端清队（dir 未变、q 截断收敛 M 条 → appliedInputs 同步，不越界）。

### 5.1 不预测进已知实体

墙/岩/传送门入口/无幽灵出界 → 悬停等服务器裁决，避免穿模后大幅回弹（相位语义见 §5.4；`eff.shield/deflect` 期不悬停，见 §4.1）。

### 5.2 回滚表现

采用 applyPlayers 本次锚点滑到位（§4.2 hook3 rollback 分支）；本地推进时 `moveDt=interval`，与现状「每次移动滑一格」节奏一致。

### 5.3 回滚触发即边缘场景（允许一次可见回弹，已拍板）

撞墙反弹、传送门出口朝向、对头强制右转、眩晕/道具干扰、他蛇抢先吃果的滞后清单、grow 道具长度差。

### 5.4 悬停相位语义（M7 闭合）

悬停 = `pred.lastMoveAt += interval`（**丢弃该拍移动、不改 cells、不消费输入**）——服务器对 skip_move 的蛇同样无条件推进 `last_move`（:1306），本地相位必须同步累加，否则 `now≥predNextMoveAt` 恒真、阻塞解除瞬间相位差扩大。阻塞解除后的偏差由 reconcile 相位校正（reanchor）吸收；**连续悬停 ≥2 拍后仍与服务器不一致 → 强制走 rollback 重锚**（兜底，不放大回弹）。

### 5.5 禁止事项

不改变服务器任何判定；不弱化现有 `dirQ` 裁剪/清队；不为回滚引入额外协议字段。

## 6. 关闭/异常路径（预测同步停用或重置）

| 时机 | 动作 |
| --- | --- |
| 死亡 / 新回合 / 换房 / 重连 / 入局 | 既有处理器已清 `dirQ`（:1890/:1943/:1986/:2597/:2611/:2703/:2747/:2794/:2826），同点 `pred = null` |
| **服务器侧复活**（applyPlayers `!wasAlive && p.alive` 清队 :2252） | 同点 `pred = null`（复活主路径，:1986 仅客户端按钮） |
| **`win_pending`（winRound=true）** | hook 2 条件排除（§4.2）；停用预测，结算翻页后以首个 cells 变化 snap 重建基准。注：onWin「我赢/平局」分支不清 dirQ（:2821-2823），停用 + `q` 截断兜底（:2570-2571）足够 |
| **`myEnt.off`（挂起/恢复宽限）** | 停用预测（服务器不移动 :1301），恢复后以首个 cells 变化 snap 重建基准 |
| `myEnt` 变为 null / `myEnt.id` 变化（实体消失、换房、clearEnts :1885/:1946、:2259-2261） | **通用规则**：`pred = null`（覆盖枚举不全） |
| 观战 / 大厅 / 演示蛇 / 未 join | 不启用（hook 2 条件） |
| `wsOpen=false` | 不预测（与批13④ :2127 同口径：没发出去就不许本地超前） |
| 服务器报死亡但客户端未收 die 事件 | snap 兜底路径（:2587-2590）随 `alive=false` 停用预测 |

## 7. 测试计划

### 7.1 前端探针（新增 `e2e/pred.spec.js`，Playwright，BASE=8123）

**测试基础设施（M6 闭合）**——探针与真实 50ms snap 流必须隔离：

- `window.__predGate(on)`：on=**拦截并丢弃**真实 snap（不缓冲、不放行），仅放行 `__gachaDbg` 注入的 snap；off=恢复透传。三段测试均「gate 开 → 注入 → 断言 → gate 关」。注意 gate 关闭瞬间首个真实 snap 必触发一次 reconcile，测试收尾断言避开该窗口。
- `window.__predState()`：返回 `{active, cells, moveDir, previewDir, leadCells, appliedInputs, snapsApplied}`（只读观测）。**实现顺序：先落地返回 `{active:false}` 的空壳**，取得真实 RED（现状无预测 → active 恒 false），再随实现填充——避免「函数不存在的假红」。
- 断言一律**断言状态而非帧时刻**（gate 打开期间无真实 snap 竞态，判据确定）。

1. **RED 基线**：gate 开 → 注入自机 snap（interval=150）→ 按 ↑ → `await page.evaluate(() => new Promise(requestAnimationFrame))` ×N（等待本地 predActive 与推进）→ 断言 `__predState().active===true` 且 `leadCells>=1`；**随后注入首个基准 snap，断言 `previewDir` 仍为 ↑ 且（若已消费输入）`moveDir` 不回退（NEW-B2 验证点：预览/已消费方向不被 snap 撤销）**（现状实现必红：active 恒 false）。推进判据：`predState.cells` 已含换向后的目标格（或 `snapsApplied` 未增而 leadCells 增 → 证明不等快照）。
2. **回滚**：gate 开 → 注入基准 snap → 按 ↑ 让 pred 推进 → 注入**矛盾 snap**（服务器位置与 pred 不同且无法经回放对齐）→ 断言 `__predState().cells` 回滚等于该 snap 的 cells。
3. **禁用路径**：gate 开 → 注入 `alive:false` 的 snap → 断言 `__predState().active === false`。

### 7.2 门禁

- 单测：服务端零改动 → **142 不变**（回归口径）。
- 静态检查：`static_check.js` 输出 ALL STATIC CHECKS PASSED（重复 id + div/css/js 平衡）。**计划中将其从 Temp 纳入 `scripts/static_check.js` 并让 local_ci 缺失即 FAIL**，保证门禁可复现（当前脚本在 Temp、缺失时 local_ci 只跳过不报错）。
- `scripts/local_ci.ps1` ALL GREEN（8 E2E + 单测 + 静态 + Playwright 全量含 pred 3 项）。

### 7.3 手感验收（部署后）

生产实操：转向明显跟手；开放地无回弹；进传送门/对头时允许一次回弹；吃 speed 道具期间不抖（M1 验证点）；局末结算窗口不抖（M3 验证点）。

## 8. 不做（本期边界）

- 不动服务端：零协议改动、不 bump `PROTO_VER`、不改 tick/数值/`game_cycle` 判定。
- 不预测他蛇、观战者、大厅演示蛇（保持现有插值）。
- 不复刻服务器边缘移动规则（撞墙反弹/传送门/对头右转/眩晕）——允许回弹即为此设计。
- 不移除/不削弱既有插值平滑与 `dirQ` 对账（含跟随视角共用 dirQ）。
- 池内其他项（E/F/D/G/H/I）不越界。

## 9. 风险与假设

- **假设**：「一拍」主因 = 等下一移动周期（最多 150ms）+ RTT + 插值；本地预测移动时机可消掉 RTT/快照等待项。若部署后仍觉迟钝 → 二期再查相位精度（±50ms 量化误差）。
- **假设**：`p['tick']` + `eff.speed` 组合可完整还原服务器实际间隔（tick_of 全分支）；若出现间隔突变导致预测抖动 → 以 reconcile 结果强制重锚。
- **风险**：相位估计误差 + 网络抖动可能造成轻微滑动步调不稳（±50ms 级，150ms/格下大概率无感）；确有可见抖动时的退路是「预测只换向、不本地推进格子」（降级为半预测，仍优于现状）——计划中做成可开关兜底而非事后补丁。
- **风险**：服务器**无输入改向**（传送门出口朝向 :1342-1351 等）后的 ≤50ms 窗口内，dirQ 空时预览/兜底可能取旧方向（`pred.moveDir` 尚未被 rollback 纠正），rollback 落地即自纠——已知窗口，接受（NIT-2）。
- **风险**：探针依赖单 worker 串行 + gate 隔离；后续新增预测测试必须沿用「gate + 断言状态」写法，避免重复踩 flaky。
- **风险**：`q` 截断是只缩不增的单侧修复；若未来引入更复杂的输入撤销（眩晕期服务端丢队但不清空），dirQ 对账与 pred 游标需一起重审。
