# 批46：真 3D 垂直物理地形 —— 实施计划

- 日期：2026-10-23
- Spec：`docs/superpowers/specs/2026-10-23-real-3d-terrain-design.md`（dev@`483d91b`，已获批准）
- 基线：dev@`483d91b`
- 协议：PROTO_VER 30 → 31

## Goal

把「2D 棋盘 + 高度贴片」改成真垂直物理：爬坡减速、坠落断尾、坠亡、真深渊 -9、批41 橙红警戒栅栏退役。交付止于 dev 全绿，不部署生产。

## Architecture

服务端规则内核（serve.py step 管线）→ 生成侧（gen_heights/reach_set/_solid/_deflect_dir/bot Dijkstra）→ 客户端渲染（index.html：井壁、坠落动画、栅栏退役）→ 协议 bump + 双端 e2e → 文档回写。

## Global Constraints

- 蛇仍一格一格移动（无连续空间、无多 tick 腾空态）
- 无 HP 体系；坠落后果只有断尾/坠亡
- 协议消息形状零变化（仅 PROTO_VER 数值 bump）
- ghost 豁免撞崖（cliff）但**不豁免坠落**
- MIN_LEN=2 保底；坠落断尾只掉长度不扣分
- 回归命令：`& .\scripts\local_ci.ps1`；单测：`.venv\Scripts\python.exe test_game.py`
- git 前缀：`git -c safe.directory='C:/MyFile/AICoding/CloudServer' -C 'C:/MyFile/AICoding/CloudServer'`

## Review Focus（执行时重点自查）

1. ghost 交叉：穿崖豁免（Δh≥2 上行）与坠落不豁免（Δh≥4 下行）在同一 tent 判定里的分支顺序
2. shield/deflect 不救坠落，但折返候选方向必须过滤致命坠落（_deflect_dir）
3. 客户端 `hmapD.get(...) || 0` 陷阱：-1/-2/-9 均为 truthy，但缺省格必须仍为 0
4. 坠落 2~3 断尾后 MIN_LEN 再被咬的级联（整条淘汰 cause='bite'）
5. e2e/fatal41.spec.js 是批41 栅栏 spec——栅栏删除后必须同步迁移，否则 local_ci 红

---

## T1 tick_of 爬坡减速（×1.5）

**Files**: serve.py `tick_of`（:1519-1528）；test_game.py 新增 test

**接口**：无签名变化。环插入顺序：speed → 水洼(-1) → **爬坡(Δh=1)** → slow。

**实现**：
- [ ] 在水洼环（:1523-1524）后加：目标格 = 头格+due 时刻 `p['dir']`；`if p['cells'] and self.hmap.get((hx+dx,hy+dy),0) - self.hmap.get(p['cells'][0],0) == 1: t = int(t*1.5)`
- [ ] test_game.py 加 `test_climb_slowdown_batch46`：hmap={(6,5):1}，头(5,5) dir(1,0)，mk 后 `r.tick_of(p, now) == int(150*1.5)`；水洼+爬坡叠加 `int(int(150*1.3)*1.5)`；向下/平走不减速
- [ ] `.venv\Scripts\python.exe test_game.py` 全绿

## T2 坠亡检测（section 4）+ cause='fall'

**Files**: serve.py section 4（:1918-1948）；test_game.py

**接口**：section 4 碰撞循环内，tent 已算出后加坠亡分支；cause 三元链扩为四元（wall/rock/cliff/self → 加 fall）。

**实现**：
- [ ] 在 cliff 判定后、guard 判定前加：`if not ghost and (cur_h32 - self.hmap.get((hx,hy),0) >= 4): dead.add(id(p)); p['cause']='fall'; continue`——注意 ghost **不豁免坠落**，故坠亡分支不带 `not ghost` 前缀（重读 spec §2：「ghost 豁免撞崖但坠亡不豁免」→ 坠亡分支对 ghost 同样生效）。最终：`if (cur_h32 - dst_h >= 4): dead.add(id(p)); p['cause']='fall'; continue`
- [ ] shield/deflect 分支对坠亡不适用（坠亡 `continue` 先于 guard）
- [ ] test_game.py `_cliff_case` 语义迁移：`:3379` `0→9` 改为 `0→-9` 且 cause='fall'；新增 `test_fall_death_batch46`：hmap={(6,5):-4}，0→-4 坠亡 cause='fall'；0→-3 坠落断尾不死；ghost 0→-9 也死（cause='fall'，不豁免）；shield 在坠亡前不救（cause='fall' 仍死）
- [ ] test_ghost_cross_height（:3415-3420）迁移：h=9 改 h=2（上行崖 ghost 穿越不死，验证豁免仍在）
- [ ] `.venv\Scripts\python.exe test_game.py` 全绿

## T3 坠落断尾（section 6）+ fall_cut 取代常规缩尾

**Files**: serve.py section 6（:2053-2106）；test_game.py

**接口**：section 6 移动循环内 insert 后、常规缩尾（:2106 `cells.pop()`）前叠放。

**实现**：
- [ ] insert(0,(hx,hy)) 后加：
```python
fall_cut = 0
dst_h = self.hmap.get((hx, hy), 0)
cur_h = self.hmap.get(p['cells'][1], 0)   # insert 后 cells[1] = 移动前头格
if 2 <= cur_h - dst_h <= 3:
    fall_cut = min(cur_h - dst_h - 1, len(p['cells']) - MIN_LEN)
```
- [ ] 常规缩尾（:2106）改：`if fall_cut: p['cells'] = p['cells'][:-fall_cut] elif ate: pass elif grow > 0: grow -= 1 else: cells.pop()`——坠落断尾**取代**本 tick 常规缩尾（吃果不取消坠落伤害）
- [ ] test_game.py 加 `test_fall_cut_batch46`：
  - hmap={(6,5):-2}，蛇 3 节 [(5,5),(4,5),(3,5)]，落差 2 → 2→1 节（len 2，无果），存活，不扣分（score 不变）
  - hmap={(6,5):-3}，落差 3 → 断 2 节
  - hmap={(6,5):-2}，头格(5,5)有果吃果 → 仍掉 1 节（吃果不取消坠落），len 不增反减
  - hmap={(6,5):-2}，蛇 2 节（MIN_LEN）→ 不断尾（fall_cut=min(1,0)=0）
  - 级联：落差 2 断尾后 2 节，下一 tick 被咬 → 整条死 cause='bite'（直接调 r.step 预置 bites 或仅断言 MIN_LEN 保护）
- [ ] `.venv\Scripts\python.exe test_game.py` 全绿

## T4 深渊 -9 生成 + 弹道 + occupied/reach

**Files**: serve.py gen_heights（:948-1045）、occupied（:1062-1083）、reach_set（:1326-1367）、弹道（:2253-2255）；test_game.py test_height_gen_invariants（:3285-3300）

**接口**：深渊哨兵 9→-9；挂 eff_water 旋钮（保熔岩 water=0 天然无深渊）。

**实现**：
- [ ] gen_heights 水洼循环（:1022-1024）后加：`for _ in range(int(area / 450 * self.eff_water())): walk_blob(..., random.randint(2, 4), -9)`——预算 area/450×eff_water，blob 2~4 格
- [ ] occupied（:1066）：`if self.hmap.get((x, y), 0) >= 2 or self.hmap.get((x, y), 0) == -9: return True`
- [ ] 弹道（:2255）：`hh != 9 and hh > pr.get('h', 0)` 删 `hh != 9` 子句（-9 时 `hh > 弹高` 天然 False）
- [ ] reach_set（:1336）：block 集改 `set(self.rocks) | set(self.walls)`（删 h>=2 无条件 block，转移规则移入 T5）；先做最小改动：加 `or hh == -9`，转移规则化留 T5
- [ ] test_game.py test_height_gen_invariants（:3287）：`vals <= {-2,-1,1,2,3,9}` → `vals <= {-2,-1,1,2,3,-9}`；熔岩断言（:3295-3297）加 `-9 not in rl.hmap.values()`；三旋钮全 0（:3298-3300）不变
- [ ] test_bullet_terrain（:3474-3487）：`hmap={(6,5):9}` 弹道飞越 → 改 `-9`（弹道仍飞越，断言语义不变，仅值迁移）
- [ ] `.venv\Scripts\python.exe test_game.py` 全绿

## T5 reach_set 转移规则化

**Files**: serve.py reach_set（:1326-1367）；test_game.py

**接口**：BFS 邻接转移规则：`nh = hmap.get(nb,0); ch = hmap.get(cur,0)`，`nh - ch <= 1 且 ch - nh <= 3 且 nh != -9` 才入队。

**实现**：
- [ ] reach_set BFS 邻接循环（:1340-1360 区间）加转移判定：`if nh - ch >= 2 or ch - nh >= 4 or nh == -9: continue`
- [ ] test_game.py 加 `test_reach_rules_batch46`：
  - hmap={(6,5):3} 无坡 → (6,5) 不在 reach_set
  - hmap={(6,5):3,(5,5):2,(4,5):1} 有坡 → (6,5) 在 reach_set
  - hmap={(6,5):-9} → (6,5) 不在 reach_set
  - hmap={(6,5):-2}（落差 2）→ (6,5) 在 reach_set（可进）
  - hmap={(6,5):-4}（坠亡）→ (6,5) 不在 reach_set
- [ ] place_food 自动生效（reach 过滤），无需改
- [ ] `.venv\Scripts\python.exe test_game.py` 全绿

## T6 _solid 致命坠落 + _deflect_dir 高度过滤

**Files**: serve.py _solid（:1179-1193）、_deflect_dir（:2111+）；test_game.py

**接口**：_solid 加 `or (cur_h is not None and self.hmap.get((x,y),0) <= cur_h - 4)`；_deflect_dir 加 cur_h 参数，候选方向过滤。

**实现**：
- [ ] _solid（:1186 后）加致命坠落判定：`if cur_h is not None and self.hmap.get((x, y), 0) <= cur_h - 4: return True`
- [ ] _deflect_dir 签名改 `def _deflect_dir(self, p, blockset, cur_h=None)`；候选方向 (nx,ny) 过滤：`if cur_h is not None and (self.hmap.get((nx,ny),0) - cur_h >= 2 or cur_h - self.hmap.get((nx,ny),0) >= 4 or self.hmap.get((nx,ny),0) == -9): continue`
- [ ] section 4 guard 分支（:1941）调用改 `self._deflect_dir(p, blockset, cur_h=cur_h32)`
- [ ] test_game.py 加 `test_solid_fatal_fall_batch46`：_solid(6,5,cur_h=0) 当 hmap={(6,5):-4} → True；hmap={(6,5):-3} → False；_deflect_dir 过滤：shield 在崖前折返，候选方向含 -9 时被过滤（不落 -9）
- [ ] test_cliff_move（:3384-3385）shield 折返不死断言复核（_open_ahead :3390-3391 cur_h 判定不变）
- [ ] `.venv\Scripts\python.exe test_game.py` 全绿

## T7 bot 寻路 Dijkstra + cap 4×

**Files**: serve.py _bot_path_step（:1657-1711）；test_game.py

**接口**：BFS deque → heapq 小顶堆 Dijkstra；代价 w=1 平/下浅、2 爬坡、4 坠 2~3；上行≥2/坠≥4/-9 跳过；cap=min(area*?,8000)。

**实现**：
- [ ] _bot_path_step 改 Dijkstra：
  - `import heapq`（若未引入）
  - block 集不变（rocks|walls|portals+全活蛇身，己身除头）
  - 代价函数：`w = 1 if 0 <= ch - nh <= 1 else (2 if nh - ch == 1 else 4)`（nh==ch → w=1；nh>ch+1 → 跳过；nh==ch-1 → w=2；ch-nh ∈[2,3] → w=4；ch-nh>=4 → 跳过）
  - 邻接判定：`if nh - ch >= 2 or ch - nh >= 4 or nh == -9: continue`
  - heap 元素 `(cost, x, y)`，保 prev 结构、反向禁（:1709-1710）、起步直行优先（:1687-1688）
  - cap 改 `min(self.cols * self.rows * 2, 8000)`（4× 原 2000）
- [ ] test_game.py 加 `test_bot_dijkstra_batch46`：
  - hmap={(6,5):3} 无坡，bot 在 (5,5) dir(1,0)，目标 (6,5) → _bot_path_step 返回 None（不可达）或绕路（不撞崖）
  - hmap={(6,5):2}，bot 绕行不进 (6,5)（上行≥2 跳过）
  - cap 边界：大图绕崖路径能找到（cap 8000 足够）
- [ ] `.venv\Scripts\python.exe test_game.py` 全绿

## T8 客户端渲染：visH/hKindOf/井壁/警戒退役

**Files**: index.html（visH :2221、hKindOf :2224、applyHeight :2265-2274、syncHeight :2296、rebuildFatalEdge :2299-2360+、hDeadEdgeMat :2243、探针 __fatalDbg :2023、小地图 :4264-4266）；e2e/fatal41.spec.js

**接口**：visH 加 `h===-9 ? -2.2`；hKindOf 9→-9；applyHeight 'ab' 改井壁；rebuildFatalEdge 全套删。

**实现**：
- [ ] visH（:2221）：`h => h >= 0 ? h * H_UNIT : (h === -1 ? -0.12 : (h === -9 ? -2.2 : 0))`
- [ ] hKindOf（:2224）：`h === 9` → `h === -9`
- [ ] applyHeight（:2265-2274）'ab' 分支：黑柱改井壁（四面内壁渐暗分段盒+底部黑雾面片+口沿青边 0x7fd8ff）；深度视觉封顶 2.2（井底 y≈-2.17）；单 mesh+children 方案避免池化改造
- [ ] syncHeight（:2296）删 `rebuildFatalEdge()` 调用
- [ ] rebuildFatalEdge（:2299-2360+）、hFenceMat（:2305）、hDeadEdgeMat（:2243）、探针 __fatalDbg（:2023）整套删
- [ ] 小地图（:4264-4266）`hv === 9` → `hv === -9`
- [ ] e2e/fatal41.spec.js 迁移：改为断言栅栏 mesh 不存在（scene.traverse 无 0xff5a2e 材质 mesh）
- [ ] `.venv\Scripts\python.exe test_game.py` 全绿（客户端改动不影响 python）

## T9 客户端坠落动画 + 死亡呈现延迟

**Files**: index.html syncBody（:3875+）、die 事件（:3704-3709）、探针 __fallDbg

**接口**：活蛇插值 v0-v1>=2 时 y 改 ease-in；落地帧回弹/尘土/微震；die 呈现延迟到坠落动画结束。

**实现**：
- [ ] syncBody 活蛇插值（:3895-3906）：`if v0 - v1 >= 2: y = v1 + (v0 - v1) * (1 - ph) * (1 - ph)`（ease-in，落地时速度最大）；否则线性插值不变
- [ ] 落地检测：插值 ph→1 时（新 step 开始）若上一 step 是坠落（落差≥2）→ 触发一次性标记：尘土 burst（落差≥2）、相机微震（落差≥4）；落地回弹 -0.03（spine[i].y -= 0.03 一帧）
- [ ] die 事件（:3704-3709）：落差≥2 的坠落步期间挂起该蛇 die 呈现（本地 hmap 判定：die 事件到达时若该蛇头格正处坠落动画，延迟约一个 step 间隔再执行爆散/移除）
- [ ] M5：进行中坠落动画被下一 step 硬替换（不叠加）
- [ ] 探针 `window.__fallDbg = () => ({ cell, targetH, fallH, animating })`（:2051 附近加）
- [ ] `.venv\Scripts\python.exe test_game.py` 全绿

## T10 PROTO_VER 31 双端

**Files**: serve.py（:48）、index.html（:1173）

**实现**：
- [ ] serve.py `PROTO_VER = 31`
- [ ] index.html `const PROTO_VER = 31`
- [ ] `.venv\Scripts\python.exe test_game.py` 全绿

## T11 e2e height46.spec.js + WS e2e

**Files**: e2e/height46.spec.js（新建）；test_ws.py 或 test_ws5.py

**接口**：height46.spec.js 断言 -9 深渊生成（__hmapDump）；WS e2e 断言 PROTO_VER 31 握手+snapshot hmap 值域无 9 含 -9。

**实现**：
- [ ] e2e/height46.spec.js：参照 height43.spec.js 模式；建房选 #cHeight 2.6；进房等待 hmap 下发；`__hmapDump()` 断言 vals 含 -9（默认主题 eff_water>0）；熔岩主题断言无 -9
- [ ] WS e2e（test_ws5.py 或并入 test_ws.py）：建房→snapshot hmap 值域断言（无 9、含 -9/±1/±2/±3/±0）；PROTO_VER 31 握手
- [ ] `$env:BASE='http://127.0.0.1:8125'; npx playwright test e2e/height46.spec.js` 全绿
- [ ] WS e2e 启动测试服（:28000）后运行全绿

## T12 local_ci 全绿

**Files**: 无（仅运行）

**实现**：
- [ ] `& .\scripts\local_ci.ps1` 全绿（含单测、e2e、静态检查）
- [ ] 修复任何迁移遗漏

## T13 文档回写 + commit

**Files**: HANDOVER.md、BACKLOG.md；git

**实现**：
- [ ] HANDOVER.md：批46 已完成事实回写（规则内核、深渊 -9、坠落动画、栅栏退役、PROTO_VER 31）
- [ ] BACKLOG.md：批46 条目标记完成，剩余风险项（薄血滚雪球、Dijkstra 回归等）登记
- [ ] `git add docs/ serve.py index.html test_game.py e2e/ scripts/`；`git commit -m "批46: 真 3D 垂直物理地形（爬坡减速+坠落断尾+坠亡+深渊-9+栅栏退役）PROTO_VER 31"`
- [ ] `git push origin dev`（或另一远端，双远端同仓）

---

## Review Focus 回答

1. **ghost 交叉**：T2 坠亡分支对 ghost 同样生效（`if cur_h32 - dst_h >= 4` 不带 `not ghost` 前缀）；cliff 判定保持 `not ghost` 豁免——分支顺序：坠亡（无豁免）→ cliff（ghost 豁免）→ guard
2. **shield/deflect 不救坠落**：T2 坠亡 `continue` 先于 guard；T6 _deflect_dir 候选方向过滤致命坠落（折返不落 -9）
3. **客户端 || 0 陷阱**：visH/hmapD.get 用 `|| 0`，-1/-2/-9 均 truthy，缺省格返回 0——无陷阱，符合预期
4. **MIN_LEN 级联**：T3 fall_cut = min(落差-1, len-MIN_LEN)；断尾后 MIN_LEN=2 节，再被咬整条淘汰（既有 bite 逻辑自动生效）
5. **fatal41.spec.js 迁移**：T8 显式列出，改为断言栅栏 mesh 不存在；local_ci 会捕获遗漏

## Proportion

- 服务端：T1-T7（7 任务，核心规则）
- 客户端：T8-T9（2 任务，渲染）
- 协议：T10（1 任务，bump）
- e2e：T11（1 任务，height46 + WS）
- 回归：T12（1 任务，local_ci）
- 文档：T13（1 任务，回写+commit）

服务端规则内核占 7/13 = 54%，符合「规则先行、渲染跟进」的批46 特征。客户端渲染（井壁/坠落动画）与警戒退役是新增功能，但依赖服务端规则判定；协议 bump 是机械操作；e2e 验证双端契约；文档回写收尾。
