# 批47 高山巨图 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 宏伟档地形升级为混合级高山（主脊 h6~11 + 神峰 h14~18）+ 地图上限 128×128，坠落阈值放大为坠亡 ≥8 / 断尾 2~7，阈值收敛为单源常量。

**Architecture:** 只改 serve.py 宏伟档生成分支与阈值散点、index.html 小地图色阶与建房档位、双端 PROTO_VER bump。服务端物理规则内核（批46 已建）不动结构，只换阈值来源。TDD：先写失败单测再改实现，每 task 独立 commit，最终 local_ci 全绿。

**Tech Stack:** Python 3 (websockets, 无框架)、单文件 index.html (Three.js)、Playwright e2e、pwsh local_ci。

**Spec:** `docs/superpowers/specs/2026-10-23-mega-terrain-design.md`

## Global Constraints

- 单源常量（serve.py 模块级）：`FALL_DEATH = 8`、`FALL_BREAK = (2, 7)`（闭区间）——全部阈值判定引用常量，禁止再裸写 -4/2/3/4。
- 双端协议：PROTO_VER 31 → 32（serve.py:48 与 index.html:1173 同步；不等则客户端 reload）。
- MAP_MAX：serve.py:17 `MAP_MIN, MAP_MAX = 12, 96` → `12, 128`。
- `eff_height() < 2.0` 生成分支（serve.py:1010-1020）**逐字节不动**。
- 高度预算维持 `int(0.35 * area)`（serve.py:954），神峰不占主脊条数但共享预算硬顶。
- 净掉节规则：断尾落差 d∈[2,7] 净掉 d-1 节，MIN_LEN=2 保底（沿用批46 cut_one 语义，不改代码只改区间）。
- H_UNIT=0.35 不改；屏幕内不加任何新警戒物；深渊 -9 逻辑不动。
- git 前缀 `git -c safe.directory='C:/MyFile/AICoding/CloudServer'`（workdir 仓库根）。
- local_ci 必须 pwsh + `-WebPort 8125`。

## Review Focus

1. **阈值散点漏改**（裸写 -4/4 未走常量）：spec §2 散 4 处 + 客户端 2 处——T2 步骤 3 逐处列出；grep `<= -4`/`>= 4`/`>= 2` 复核步骤兜底。
2. **阶梯缓坡断裂**（生成时 take 失败致相邻格落差 >1，出现非预期致命边）：T4 步骤 2 的「主脊+缓坡逐格单调递减」不变量单测覆盖。
3. **reach_set 128² 性能**：T6 步骤 1 计时断言（<50ms 现预算，128² 复用同预算）。
4. **test_fall_p46 / height46.spec.js 场景与新阈值错位**（旧场景落差 4=死、3=断尾，新语义 8=死、2~7=断尾，漏改则 e2e 假红/假绿）：T5 步骤 1-2 重算全部场景。
5. **96 档行为回归**（MAP_MAX 放大不能改变 96 及以下档任何输出语义）：T6 步骤 3 既有 size clamp 断言 + local_ci 全绿兜底。

---

### Task 1: 客户端常量与 PROTO_VER 32

**Files:**
- Modify: `index.html:1173`（PROTO_VER 常量）
- Modify: `index.html`（新增 FALL_DEATH/FALL_BREAK 客户端常量，紧邻 PROTO_VER）
- Modify: `index.html:3968`（微震阈值 `>= 4` → `>= FALL_DEATH`）

**Interfaces:**
- Produces: 客户端 `FALL_DEATH = 8`、`FALL_BREAK = [2, 7]`（JS const，供后续 Task 引用）；PROTO_VER = 32。

- [ ] **Step 1: index.html:1173 区改 PROTO_VER = 32，注释改「批47：hmap 值域 0..4 → 0..18 + 坠落阈值放大；须与 serve.PROTO_VER 同步」**

- [ ] **Step 2: 紧邻其下新增**

```js
const FALL_DEATH = 8;      // 批47：坠亡落差（>= 死）——与 serve.FALL_DEATH 同步
const FALL_BREAK = [2, 7]; // 批47：断尾落差闭区间 [2,7]，净掉 落差-1 节——与 serve.FALL_BREAK 同步
```

- [ ] **Step 3: index.html:3968 `if (fx.h0 - fx.h1 >= 4) shake = ...` 改 `>= FALL_DEATH`**（坠亡级落差才微震；断尾级 2~7 不震）

- [ ] **Step 4: 验证**

Run: `pwsh -File local_ci.ps1 -Only静态` 或直接目检 grep：`grep -n "FALL_DEATH\|FALL_BREAK\|PROTO_VER = 32" index.html`
Expected: 3 处常量定义 + 3968 引用 FALL_DEATH，无残留 `fx.h0 - fx.h1 >= 4`。

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat(batch47): client FALL_DEATH/FALL_BREAK constants + PROTO_VER 32"
```

---

### Task 2: 服务端阈值单源常量

**Files:**
- Modify: `serve.py:48` 区（新增 FALL_DEATH/FALL_BREAK 常量）
- Modify: `serve.py:48`（PROTO_VER = 32）
- Modify: `serve.py:1971`（坠亡 `<= -4` → `<= -FALL_DEATH`）
- Modify: `serve.py:2105`（断尾区间 `2 <= ... <= 3` → `FALL_BREAK[0] <= ... <= FALL_BREAK[1]`）
- Modify: `serve.py:1374`（reach_set `ch - nh >= 4` → `>= FALL_DEATH`）
- Modify: `serve.py:1729`（bot Dijkstra 同款 `>= 4` → `>= FALL_DEATH`）
- Modify: `serve.py:1194`（_solid `_hs <= cur_h - 4` → `- FALL_DEATH`）
- Modify: `serve.py:2182`（_deflect_dir `_hd <= cur_h - 4` → `- FALL_DEATH`）
- Test: `test_game.py`（新组 test_fall_thresholds_batch47）

**Interfaces:**
- Produces: `serve.FALL_DEATH = 8`、`serve.FALL_BREAK = (2, 7)`；PROTO_VER = 32（与客户端对齐）。

- [ ] **Step 1: 写失败单测**（test_game.py 新增，注册进 :4723 附近清单）

```python
def test_fall_thresholds_batch47():
    """批47 §3：阈值单源常量——坠亡>=8、断尾[2,7]；引用处全部走常量"""
    import serve
    assert serve.FALL_DEATH == 8
    assert serve.FALL_BREAK == (2, 7)
    assert serve.PROTO_VER == 32
    # 坠亡边界：落差8死、落差7断尾不死
    r = fresh(16)
    p = mk(r, 'f1', 'F', [(4, 4), (4, 5), (4, 6)], (1, 0))
    r.hmap = {(4, 4): 8}
    r.step(serve.now_ms())
    assert not p['alive'] and p['cause'] == 'fall'
    r2 = fresh(16)
    p2 = mk(r2, 'f2', 'F', [(4, 4), (4, 5), (4, 6)], (1, 0))
    r2.hmap = {(4, 4): 7}
    r2.step(serve.now_ms())
    assert p2['alive'], '落差7应断尾不死'
```

（`fresh`/`mk` 为 test_game.py 既有 fixture，签名按文件头既有用法。）

- [ ] **Step 2: 跑测确认失败**

Run: `python -m pytest test_game.py -k fall_thresholds -x -q`（或项目惯用的单测运行法）
Expected: FAIL（AttributeError: module 'serve' has no attribute 'FALL_DEATH'）

- [ ] **Step 3: 实现常量替换**

serve.py:48 区（PROTO_VER 行前后）新增：

```python
FALL_DEATH = 8          # 批47 §3：坠亡落差下限（>= 死，cause='fall'）
FALL_BREAK = (2, 7)     # 批47 §3：坠落断尾落差闭区间（净掉 落差-1 节，MIN_LEN=2 保底）
```

`PROTO_VER = 31` → `32`，注释改「批47：hmap 值域 0..4→0..18 + 坠落阈值放大」。
六处替换（每处只把裸数字换成常量表达式，逻辑运算符不动）：

| 行 | 现状 | 改后 |
|---|---|---|
| 1971 | `if dst_h46 - cur_h32 <= -4:` | `if dst_h46 - cur_h32 <= -FALL_DEATH:` |
| 2105 | `if 2 <= cur_h46s - dst_h46s <= 3:` | `if FALL_BREAK[0] <= cur_h46s - dst_h46s <= FALL_BREAK[1]:` |
| 1374 | `if nh - ch >= 2 or ch - nh >= 4 or nh == -9:` | `... or ch - nh >= FALL_DEATH or ...` |
| 1729 | 同 1374 | 同上 |
| 1194 | `if _hs - cur_h >= 2 or _hs <= cur_h - 4:` | `... or _hs <= cur_h - FALL_DEATH:` |
| 2182 | `if _hd - cur_h >= 2 or _hd <= cur_h - 4 or _hd == -9:` | `... or _hd <= cur_h - FALL_DEATH or ...` |

注意：上行阈值 `>= 2`（撞崖）是独立语义（cliff），不在本批调整范围，保持字面量或按同风格引用留待未来——本批不引入 CLIFF 常量（YAGNI，spec 未要求）。

- [ ] **Step 4: 跑测确认通过 + 全量单测**

Run: `python test_game.py`（项目单测为脚本尾行 ALL GAME UNIT TESTS PASSED 模式）
Expected: ALL GAME UNIT TESTS PASSED（含新组；既有 fall_batch46 组若因 7/8 边界断言变化变红则按 §迁移清单在本 task 内同步更新——见 Step 5）

- [ ] **Step 5: 既有阈值测试迁移**

test_game.py 既有批46 组按新阈值重算（grep 定位）：
- `test_reach_rules_batch46`（:3344 区，「落差4 坠亡坑不可达」→ 落差8）
- `test_solid_fatal_fall_batch46`（:3367 区，-4 → -8、-3 → -7）
- `test_bot_dijkstra_batch46`（:3389 区，坠亡落差 4 → 8，代价断言同步）
- `test_fall_death_batch46`（:3540 区，0→-4 坠亡场景 → 0→-8；0→-3 断尾 → 0→-7；ghost/shield/-9 用例同步）
- `test_fall_cut_batch46`（:3562 区，落差 2 断 1 节保持、增补落差 7 断 6 节）
迁移原则：只改阈值数值断言，语义结构（cause、MIN_LEN、吃果不取消伤害）逐条保留。测试名保持 batch46 后缀（它们测的是同一批语义在新常量下的数值）。

- [ ] **Step 6: 全量单测绿**

Run: `python test_game.py`
Expected: ALL GAME UNIT TESTS PASSED

- [ ] **Step 7: Commit**

```bash
git add serve.py test_game.py
git commit -m "feat(batch47): FALL_DEATH=8/FALL_BREAK=(2,7) single-source constants + PROTO_VER 32"
```

---

### Task 3: 客户端断尾呈现同步

**Files:**
- Modify: `index.html:3894`（坠落插值触发 `ch0 - ch1 >= 2` → 保持 ≥2 不变，但注释引 FALL_BREAK 下界）
- Modify: `index.html:3957`（fallFx 起跳 `fh0 - fh1 >= 2` → 同上保持，引用 FALL_BREAK[0]）
- Modify: `index.html:3790`（handleDie 延迟 `drop >= 2` → 引用 FALL_BREAK[0]）

**Interfaces:**
- Consumes: Task 1 的 `FALL_DEATH`/`FALL_BREAK`。

- [ ] **Step 1: 三处 `>= 2` 坠落判定改 `>= FALL_BREAK[0]`**（值仍 2，纯收敛字面量到单源；断尾下界=坠落动画下界语义绑定）

- [ ] **Step 2: 验证**

Run: `grep -n "FALL_BREAK" index.html`
Expected: 定义 1 处 + 引用 ≥3 处（3894/3957/3790）。

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "refactor(batch47): client fall thresholds reference FALL_BREAK constant"
```

---

### Task 4: 宏伟档混合级生成（主脊 h6~11 + 阶梯缓坡 + 神峰）

**Files:**
- Modify: `serve.py:991-1009`（宏伟档分支重写）
- Test: `test_game.py`（新组 test_height_mixed_batch47 + 迁移 test_height_majestic_ridge_batch43）

**Interfaces:**
- Produces: 宏伟档 hmap 值域 0..peak（peak∈[6,11] 主脊、[14,18] 神峰）；`gen_heights` 签名不变。

- [ ] **Step 1: 写失败单测**（test_game.py 新增组，注册进 :4723 清单）

```python
def test_height_mixed_batch47():
    """批47 §2：宏伟档混合级——主脊 peak∈[6,11]、阶梯缓坡单调递减、神峰∈[14,18]"""
    import serve, random
    random.seed(7)
    r = fresh(48)
    r.theme = 'default'
    # 模拟宏伟档：eff_height 返回 >=2.0（按 test_height_majestic_ridge_batch43 既有做法）
    r.hf = 'majestic'   # 档位字段名以既有 test_height_majestic_ridge_batch43 为准
    r.build_terrain()
    hs = list(r.hmap.values())
    assert hs, '宏伟档应有高度地形'
    main_peaks = [h for h in hs if 6 <= h <= 11]
    assert main_peaks, '应存在主脊 peak∈[6,11]: %r' % (sorted(set(hs)),)
    assert all(h <= 18 for h in hs), '值域上限 18'
    # 神峰：每图 1~2 座（48 图 1 座），h∈[14,18]
    peaks14 = [h for h in hs if h >= 14]
    assert peaks14, '应存在神峰 h>=14'
    # 阶梯缓坡：每个主脊格的缓坡侧相邻格 h 差恰好 1（单调递减链存在）
    r2 = fresh(48); r2.hf = 'majestic'; r2.build_terrain()
    def stepped(rr):
        for (x, y), h in rr.hmap.items():
            if 6 <= h <= 11:
                nb = [rr.hmap.get(c, 0) for c in ((x+1,y),(x-1,y),(x,y+1),(x,y-1))]
                if min(nb) == h - 1:
                    return True
        return False
    assert stepped(r2), '主脊应有阶梯缓坡侧（相邻 h-1）'
    print('mixed height batch47 OK')
```

（fixture 细节——theme/hf 字段名、build_terrain 调用方式——以 test_height_majestic_ridge_batch43 实际写法为准，逐行对齐。）

- [ ] **Step 2: 跑测确认失败**

Run: `python -m pytest test_game.py -k mixed_batch47 -x -q`
Expected: FAIL（peak 上限 3 < 6）

- [ ] **Step 3: 重写宏伟档分支（serve.py:991-1009）**

```
for _ in range(max(2, int(area / 160 * eff_height()))):
    随机起点+方向（沿用现有随机游走骨架）
    peak = randint(9,11) if random()<0.4 else randint(6,8)     # 混合级主脊
    L = randint(6, 14)                                           # 沿用
    sides = (1,) if random()<0.3 else (1, -1)                    # 30% 缺侧=峭壁（peak≥8 天然坠亡级）
    px, py = -dy, dx
    for i in range(L):
        t = 脊中段判定（沿用 t<0.6 取 peak 否则 peak-1）
        if take(x, y, h):
            for s in sides:                                       # 阶梯缓坡：贴脊 peak-1 起每格递减 1 到 0
                for k in range(1, h):
                    if not take(x + px*s*k, y + py*s*k, h - k): break
        随机游走步进（沿用）
# 神峰：主脊条数之外，独立 1 次（area<=96*96）/2 次（128 图）
for _ in range(2 if max(cols,rows) >= 128 else 1):
    peak = randint(14, 18); 小顶 2~3 格（take(x,y,peak) + take 邻格 peak-1）
    仅一侧阶梯缓坡（同上递减规则），其余侧不放格=峭壁
```

关键不变量（实现时自查）：阶梯每格递减 1 → 下行每步落差 ≤1 天然可达；take 失败即 break（预算/占用硬顶，不重试不越界）；`eff_height < 2.0` 分支一行不动。

- [ ] **Step 4: 跑测确认通过**

Run: `python -m pytest test_game.py -k "mixed_batch47 or height" -x -q`
Expected: 新组 PASS；`test_height_majestic_ridge_batch43` 若断言旧 peak 2~3 分布则按混合级语义迁移（保留「脊线连续/缺侧峭壁/预算不超」结构性断言，更新 peak 数值区间）；`test_height_gen_invariants` PASS。

- [ ] **Step 5: 全量单测绿**

Run: `python test_game.py`
Expected: ALL GAME UNIT TESTS PASSED

- [ ] **Step 6: Commit**

```bash
git add serve.py test_game.py
git commit -m "feat(batch47): majestic mixed-height mountains (main ridge 6-11, peaks 14-18, stepped ramps)"
```

---

### Task 5: 地图 128×128 + 建房档位

**Files:**
- Modify: `serve.py:17`（MAP_MAX = 128）
- Modify: `index.html:833-836`（cSize 超大 optgroup 加 128）
- Test: `test_game.py`（新断言组 test_map_128_batch47）

**Interfaces:**
- Produces: 建房 size 上限 128；96 及以下档行为不变。

- [ ] **Step 1: 写失败单测**

```python
def test_map_128_batch47():
    """批47 §4：MAP_MAX=128——clamp 到 128、96 档不变、128 建房-进图往返"""
    import serve
    assert serve.MAP_MAX == 128
    r = fresh(200)
    assert r.cols == 128 and r.rows == 128, '超限应 clamp 128'
    r96 = fresh(96)
    assert r96.cols == 96, '96 档不变'
    r128 = fresh(128)
    assert r128.cols == 128
    r128.build_terrain()   # 128 建房-进图不抛错、hmap 值域 <=18
    assert all(h <= 18 for h in r128.hmap.values())
    print('map 128 batch47 OK')
```

- [ ] **Step 2: 跑测确认失败**

Run: `python -m pytest test_game.py -k map_128 -x -q`
Expected: FAIL（MAP_MAX 仍是 96，fresh(200) 得 96）

- [ ] **Step 3: 实现**

serve.py:17 → `MAP_MIN, MAP_MAX = 12, 128`（注释补「批47：巨图 128」）。
index.html:835 后加 `<option value="128">128×128 巨无霸</option>`（超大 optgroup 内，96 保留）。

- [ ] **Step 4: 跑测确认通过**

Run: `python -m pytest test_game.py -k map_128 -x -q`
Expected: PASS

- [ ] **Step 5: 全量单测绿**

Run: `python test_game.py`
Expected: ALL GAME UNIT TESTS PASSED

- [ ] **Step 6: Commit**

```bash
git add serve.py index.html test_game.py
git commit -m "feat(batch47): MAP_MAX 128 + 128x128 build option"
```

---

### Task 6: reach_set 128² 性能 + 小地图色阶

**Files:**
- Modify: `test_game.py:1977`（test_place_food_reach_time_budget 扩 128 档）
- Modify: `index.html:4279`（小地图高度色阶扩到 0..18）

**Interfaces:**
- Consumes: Task 4 生成的新值域；Task 5 的 128 档。

- [ ] **Step 1: 扩计时单测**（test_place_food_reach_time_budget 内追加 128 段）

```python
    r128 = fresh(128)
    r128.walls = [(x, 64) for x in range(0, 128, 2)]
    r128.rocks = [(x, y) for x in range(0, 128, 4) for y in range(0, 128, 8)]
    mk(r128, 'p2', 'P', [(1, 1), (1, 2), (1, 3)], (0, -1))
    t0 = _time.perf_counter()
    reach128 = r128.reach_set()
    ms128 = (_time.perf_counter() - t0) * 1000.0
    assert ms128 < 50, "128 可达集 BFS 超时: %.2fms" % ms128
    assert (1, 1) in reach128
```

- [ ] **Step 2: 跑测**

Run: `python -m pytest test_game.py -k reach_time -x -q`
Expected: PASS（16384 格 BFS 实测应远低于 50ms）

- [ ] **Step 3: 小地图色阶（index.html:4279）**

现 `g.fillStyle = hv >= 3 ? '#cabfae' : hv === 2 ? '#8a94a6' : '#7c8465';`
改为按 h 分段渐变覆盖 1..18（色相延续现有灰绿→灰白「越高越亮越白」语言，18 段太多则 5 档：1 / 2~5 / 6~11 / 12~15 / 16~18，最后一档接近雪白 #efe9dc）。-9 井、水/草跳过逻辑不动。

- [ ] **Step 4: 验证 + Commit**

Run: `grep -n "cabfae\|efe9dc" index.html`（旧色替换、新档存在）
Expected: 色阶 5 档。

```bash
git add test_game.py index.html
git commit -m "feat(batch47): 128 reach BFS timing test + minimap height color scale to h18"
```

---

### Task 7: fall E2E 场景重算 + Playwright 更新

**Files:**
- Modify: `test_fall_p46.py`（场景 A 落差 3→0 保持断尾语义但按新阈值重算节数据；场景 B 落差 4 死 → 落差 8 死；新增落差 7 断 6 节场景）
- Modify: `e2e/height46.spec.js`（注入阈值按新规则：落差 3 仍是坠落动画 ≥2 断尾级——注入本身 h3→h0 落差 3 ≥2 仍触发坠落步，H6 时序逻辑不变；仅核对断言注释与 FALL_BREAK 一致）
- Modify: `e2e/` 新增 128 建房快照尺寸 spec（或并入既有建房 spec 文件）

**Interfaces:**
- Consumes: Task 2 阈值、Task 5 128 档、`__fallDbg`/`__dieDbg` 探针（批46 已有）。

- [ ] **Step 1: 重写 test_fall_p46.py 场景**

- 场景 A：`room.hmap = {(5, 5): 7}`（原 3），cells 8 节 → 落差 7 断 6 节：len 8→2（MIN_LEN=2 保底！断言恰好 2 验证保底链）；或 cells 9 节 → 9-6=3。取后者稳：cells 9 节断后 3 节。
- 场景 B：`room.hmap = {(10,10): 8, (11,10): -1}`（原 3/-1）——落差 9 ≥8 坠亡，cause='fall'。
- 新场景 C（落差 7 不死）：`{(10,10): 7}` → 断 6 节存活（与 A 同构可省，A 即是）→ 改为断言 A 无 die 事件即可，不重复。
- 文件头 docstring 场景说明同步。

- [ ] **Step 2: 跑 test_fall_p46.py**

Run: `python test_fall_p46.py`
Expected: `fall p46 E2E PASS`

- [ ] **Step 3: height46.spec.js 核对**

注入 h3→h0 落差 3：坠落动画下界 FALL_BREAK[0]=2 仍满足，H6 时序断言不动。只在文件头注释把「落差 3」说明补一句「批47 后 3 ∈ FALL_BREAK 断尾级，坠落动画仍触发」。跑该 spec（local_ci 阶段）绿即可。

- [ ] **Step 4: 新增 128 建房 e2e spec**（e2e/map128.spec.js，仿既有建房 spec 模式）

```js
test('批47: 128×128 建房进图快照尺寸', async ({ page }) => {
  await ensureLogin(page, 'yuan', '123456');
  await page.selectOption('#cSize', '128');
  // 建房→进图→快照 cols/rows === 128（断言方式仿既有 size spec；探针/快照字段以仓库既有 e2e 为准）
});
```

具体选择器/断言字段在实现时对齐既有建房 e2e（grep `cSize` e2e/ 目录）。

- [ ] **Step 5: local_ci 全绿**

Run: `pwsh -File local_ci.ps1 -WebPort 8125`
Expected: 12套 E2E + 单测 ALL GAME UNIT TESTS PASSED + 静态 + Playwright 全绿（18+ spec）。

- [ ] **Step 6: Commit**

```bash
git add test_fall_p46.py e2e/height46.spec.js e2e/map128.spec.js
git commit -m "test(batch47): fall e2e scenarios rescaled + 128 map e2e spec"
```

---

### Task 8: 部署 + 文档回写 + 推双远端

**Files:**
- Modify: `HANDOVER.md`（§11 批47 增量行 + 当前生产版本行）
- Modify: `BACKLOG.md`（尾部追加批47 段 + 部署行 ✅）
- Modify: `local_ci/ci.yml`（spec 计数行同步）

**Interfaces:**
- Consumes: Task 1-7 全部绿。

- [ ] **Step 1: local_ci 全绿复核 + 文档回写**

BACKLOG 批47 段（T1-T7 逐行 commit 哈希，批46 段格式）；HANDOVER §11 增量行；ci.yml 表行更新 spec 数与 passed 数。
Commit: `docs(batch47): backlog/handover increment`

- [ ] **Step 2: 部署（§11.2 流程）**

漂移检查（生产 serve.py/index.html sha 对照 HANDOVER 记录）→ predeploy tar（`snake-3d-predeploy-<时间戳>.tar.gz`，记录大小）→ `git -c core.autocrlf=false archive --format=tar -o $env:TEMP\deploy.tar dev` → scp → 生产目录 `tar -xf` → `systemctl restart snake-3d` → 核验：active、HTTP 200、journal 零 error、生产 sha = 本地 dev blob、线上 PROTO_VER=32 双端。

- [ ] **Step 3: 部署记录回写 + push 双远端**

HANDOVER §11 当前生产版本行改 dev@`<hash>`（投放时间）；BACKLOG 部署行 ✅。
`git push origin dev && git push server dev`；`git ls-remote` 双远端齐平。
Commit: `docs(batch47): deploy record`

- [ ] **Step 4: 线上抽查**

浏览器开生产地址：建 128 巨无霸房进图、宏伟档山脉可见（神峰明显高出）、小地图色阶分层、PROTO_VER 32 无 reload 循环。
