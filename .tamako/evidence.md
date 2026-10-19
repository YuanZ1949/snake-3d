# 批35 证据（奶龙 / 芙宁娜 角色蛇皮肤 + 迷你 3D 模型）

契约：`.tamako/contract.json` —— 第 2 轮补批：acceptance 1-4（批35 功能）+ 5-7（可复现性补齐）全部 `verdict=pass`，`state=closed`（顶层 8 字段，JSON 可解析）。

## 验收 1 — 模型自产、可复现 ✅

- `node scripts/gen_models.js` 生成 `models/nailong.glb`、`models/furina.glb`
- `node scripts/test_gen_models.js` → `GENERATOR CHECKS PASSED`（16/16）
- 生成器用脚本自建（Sketchfab 下载 API 401、许可不干净 → 已定案不走第三方素材）
- `gltf-loader.js` = three r160 GLTFLoader 由 ESM 机械改写成的 UMD 产物（不引入 ESM 打包器）

## 验收 2 — e2e ✅

- `e2e/skin35.spec.js` → **6/6 passed**（含 GLB 404 静默回退到 skull 的分支）

## 验收 3 — 静态检查与本地 CI ✅

- `node scripts/static_check.js` → `ALL STATIC CHECKS PASSED`
- `pwsh scripts/local_ci.ps1` → `ALL GREEN`

最后一次（探针改造后）：

```
ids=135 dup=0 div=69/69 css=350/350 js=917/917
ALL STATIC CHECKS PASSED
```

## 验收 4 — 进局**可见**迷你模型（决定性视觉证据）✅

### 部署

- 5 文件 scp 到 `ubuntu@193.112.172.83:/home/ubuntu/snake-3d/`（`index.html` + `gltf-loader.js` + `models/nailong.glb` + `models/furina.glb` + `serve.py`），远端重启进程
- 远端 `PROTO_VER = 30`；新 PID 1676685；资源白名单全 200；远端 `index.html` = 249141 B 且 `grep -c myHeadSel` = 3
- 生产运行时：`loader=true`、`skins[16]=nailong` / `skins[17]=furina`、`MOUNT_* node=true skull=false`、`FALLBACK node=false skull=true`

### console 错误（验收 4 后半句）

首轮取证时项目**没有** `prod_verify` 脚本，因此以取证脚本全程收集的 `pageerror` + `console.error` 作为等价证据：三个取证会话（8× A/B 会话 + 两次真实比例会话 skin16/skin17）结束时均输出 `ERRS=[]`，汇总 `ALL_ERRS=[]` —— 即**无新增 console 错误 / 无未捕获异常**。

> 第 2 轮已把这套流程固化为**常驻脚本 `scripts/prod_verify35.js`**（见下方「第 2 轮 · 可复现性补齐」），实跑输出 `ALL_ERRS=[]` —— 验收 4 的后半句现在有可执行件，随时可重跑。

### 探针根因与修复

`applySkin()` 原先把模型挂到**模块级 `head`**，但入局后 `demoBodyShow(false)` 把模块级 `head` 隐藏，屏上真正渲染的是 `myEnt.head`。旧探针瞄错对象 → 裁剪图全是地板、ON/OFF 字节数完全相同（15411）。

修复（`index.html`，已部署）：

| 探针 | 位置 | 作用 |
| --- | --- | --- |
| `myHeadSel()` | index.html:2016 | 优先 `myEnt.head`，回退模块级 `head` |
| `__modelBoxDbg()` | index.html:2020 | 返回盒子（`src` 标明实际选中谁）+ 世界坐标 |
| `__modelShowDbg(on, zoom)` | index.html:2041 | 临时切模型/回退球可见性；`zoom` 只放大**模型节点**（原 scale 存 `node.userData.__zoom0`，不传即还原） |
| `__modelDbg().mine` | index.html | 返回本体挂载状态 `node/skull` |

> **zoom 不动相机**：`zoom` 只改模型节点的 `node.scale`，`CAM.h` / `camDist` / 相机矩阵全程未改（符合契约「不改相机」）。
>
> 教训：本会话出现过 3 次 `edit` 报成功但文件未落盘（仍 248063 B）。本次改后验证 `myHeadSel`=3、`__zoom0`=4、249141 B、时间戳更新，远端 `grep -c myHeadSel`=3，才算真正部署。

### 诊断输出（真实比例会话，`__modelBoxDbg` + `__modelShowDbg`）

**skin 16 奶龙：**

```json
BOX={"x":627.286,"y":500.709,"w":27.929,"h":29.324,"src":"myEnt","nodeVis":true,"grpVis":true}
CLIP={"x":471,"y":325,"width":340,"height":380}
SHOW_ON={"node":true,"skull":false}
SHOW_OFF={"node":false,"skull":true}
ERRS=[]
```

**skin 17 芙宁娜：**

```json
BOX={"x":556.003,"y":465.648,"w":16.971,"h":19.993,"src":"myEnt","nodeVis":true,"grpVis":true}
CLIP={"x":394,"y":286,"width":340,"height":380}
SHOW_ON={"node":true,"skull":false}
SHOW_OFF={"node":false,"skull":true}
ERRS=[]
```

`src:"myEnt"` + `grpVis:true` → 探针确认瞄的就是入局后实际渲染的蛇头组；`SHOW_ON/OFF` 证明 `__modelShowDbg` 的 ON/OFF 确实翻转了模型与回退球。

### 存证清单与语义（`docs/evidence/batch35/`，共 10 张首轮存证）

| 文件 | 语义 | 判读结果 |
| --- | --- | --- |
| `prod35_nailong_head.png` (105734 B) | **8× 放大** ON | 金黄低多边形奶龙：圆身、下伸喙、侧耳鳍 |
| `prod35_nailong_headOff.png` (98371 B) | **真实比例** OFF | 原生金色回退球（skull），无龙 |
| `prod35_nailong_ts.png` (88054 B) | **真实比例 ON**（同会话同 clip） | 金黄圆身 + 两颗白眼珠 + 侧鳍 —— 模型可辨 |
| `prod35_nailong_tsOff.png` (78209 B) | **真实比例 OFF**（同上对） | 光滑素金球，无眼无龙 |
| `prod35_furina_head.png` (90783 B) | **8× 放大** ON | 芙宁娜低模：白身 + 深蓝高帽 + 淡蓝领饰 |
| `prod35_furina_headOff.png` (80817 B) | **真实比例** OFF | 原生金色回退球 |
| `prod35_furina_ts.png` (91605 B) | **真实比例 ON**（同会话同 clip） | 白身 + 两侧淡蓝鳍手 —— 模型可辨 |
| `prod35_furina_tsOff.png` (84006 B) | **真实比例 OFF**（同上对） | 素金球 |
| `prod35_nailong_zoomOn.png` (819504 B) | 全帧局内语境图（8× ON） | 模型位于画面中央蛇头上，周围有地板/名牌/分数 |
| `prod35_furina_zoomOn.png` (801320 B) | 全帧局内语境图（8× ON） | 同上 |

**口径说明（重要）**：`*_head.png` 是 **8× 放大**帧、`*_headOff.png` 是**真实比例** OFF 帧，二者**不成对**（历史口径不一致，已定案保留但不作为配对证据）。真正成对的是 `*_ts.png` / `*_tsOff.png` —— **同一会话、同一 clip、真实比例、只切 `__modelShowDbg` 可见性**，这才是回答「进局可见迷你模型」的配对证据；`*_zoomOn.png` 提供全帧局内语境。

已删除的无效/过程存证：`prod35_*_normal.png`（登录页截图，非局内）、`*_full.png`、`prod35_skin0_full*.png`、裸名 `prod35_{furina,nailong}.png`、`ab_/frz_/iso_` 过程帧。

### 肉眼判读（真实比例 A/B，决定性）

- **奶龙**：ON = 金黄圆身 + 白眼珠 + 侧鳍 vs OFF = 素金球 → 模型在蛇头上**可见且可辨识**。
- **芙宁娜**：ON = 白身 + 两侧淡蓝鳍手 vs OFF = 素金球 → 模型在蛇头上**可见且可辨识**。

## 第 2 轮 · 可复现性补齐（2026-10-19）

用户拍板「只补备份，先不推」+「补脚本与存证入仓两条都做」。对应 contract 的 acceptance 5/6/7。

### 验收 5 — 生产 predeploy 备份 ✅

```
CREATED=snake-3d-predeploy-20261019-134813.tar.gz
-rw-rw-r-- 1 ubuntu ubuntu 546497 Oct 19 13:48 snake-3d-predeploy-20261019-134813.tar.gz
snake-3d/serve.py
snake-3d/index.html
snake-3d/gltf-loader.js
snake-3d/models/nailong.glb
snake-3d/models/furina.glb
total entries 55
```

- 路径：`/home/ubuntu/snake-3d-predeploy-20261019-134813.tar.gz`（此前最新备份停在 20261017-192553，批34/批35 两次部署都没打 tar）。
- 排除项比 HANDOVER §11.2 配方多了一个 `--exclude=node_modules`（`npm ci` 可重建，tar 从数百 MB 降到 546 KB）；其余排除项一致。

### 验收 6 — 可复现的生产验收脚本 ✅

- 新增 `scripts/prod_verify35.js`（无新依赖，`playwright` 由 `@playwright/test` 带入）。
- 首轮实跑即 PASS（生产 8090，不登录）：

```
STEP ok: probes ready (__modelDbg/__applySkinDbg)
STEP ok: in game (#startScreen hidden)
PAUSE_MASK={"exists":true,"display":"none","rect":{"x":0,"y":0,"w":0,"h":0}}
STEP ok: skin 16 nailong mounted (mine.node=true)
STEP ok: skin 17 furina mounted (mine.node=true)
PER_SKIN=[{"id":16,"name":"nailong","ok":true,"node":true,"off":{"node":false,"skull":true,"src":"myEnt"}},
          {"id":17,"name":"furina","ok":true,"node":true,"off":{"node":false,"skull":true,"src":"myEnt"}}]
ALL_ERRS=[]
VERDICT=pass
--- prod_verify35: PASS (mounted 2/2, errs 0) ---
```

- 用法：`node scripts/prod_verify35.js`（默认生产 8090、图落 `test-results/`）；`--login` 走账号链路；`--base` / `--out` 可换目标与落盘目录；退出码 0=pass / 1=fail / 2=环境致命错误。
- 与首轮口径的唯一差异：**不登录也能过**（16/17 属 `FREE_SKINS`，`__applySkinDbg` 是纯客户端路径），`--login` 保留给要复核账号链路的场景。

### 验收 7 — 存证入仓 ✅

- 10 张首轮存证从 `test-results/`（已被 `.gitignore` 忽略，且 Playwright 每次运行会清空）移入 `docs/evidence/batch35/`，`git ls-files docs/evidence/batch35` 计数 = **10**（验收 7 原文判据）。
- 脚本重跑产出的 4 张 `prod35_{nailong,furina}_{on,off}.png`（nailong 173072/122790 B、furina 115150/106502 B）**不入库**，落 `test-results/`（gitignored）—— 可由 `node scripts/prod_verify35.js` 随时重新生成；`git ls-files docs/evidence/batch35` = **10**。
- `test-results/` 现只剩他批文件：`p33_attach_react.png`、`smoke-home.png`、`smoke-ingame.png`、`.last-run.json`（按契约不动）。

### 生产零漂移复核

```
d0687bb7e4be8dd6…  index.html
874927091e09aa30…  gltf-loader.js
f5ceeb5c6a31d8bf…  serve.py
550fd91156bc2f60…  models/nailong.glb
70c10d91c8ca4cc8…  models/furina.glb
PID 1676685 / HTTP 200 249141B / PROTO_VER = 30
```

本地与生产 5 文件 sha256 逐字节一致；生产目录无 `_tmp` 散件。

## 方法与工具说明

- 首轮取证脚本为**一次性** `_tmp_*.js`（Playwright + CDP），收口时已全部删除（根目录 `_tmp_*` = NONE）；当时可复现方法只依赖**常驻探针** `index.html` 的 `myHeadSel` / `__modelBoxDbg` / `__modelShowDbg` / `__modelDbg`，**没有可执行的验收脚本**。第 2 轮补齐：`scripts/prod_verify35.js`（常驻，见下节）。
- 截图差分法、严格颜色计数法、投影盒子裁剪对比法均已试过并**证伪**（ON/OFF 字节相同、地板干扰），最终采用**必须放大取证法**（先 OFF 帧再 ON 帧，避免残留）。
- 生产登录：`ensureLogin(page,'yuan','123456')` 在生产超时（`#acctBadge` 始终 hidden）→ 取证脚本内注册随机账号（`fz`+随机名、密码 `351234`，符合 `^\d{6}$` 与 2-12 字符规则），注册后点 `#btnGiftClose` 关掉 `giftPop` 遮挡。
- 取证流程要点：viewport 1280×800、`deviceScaleFactor:2`（clip 为 CSS px）→ `#btnSolo` → 等 `startScreen` hidden → 确认 `#pauseMask` 为 `display:none`（**不挂机**：该胶囊 `position:fixed` 居中、z-index 850，会盖进裁剪区）→ `__applySkinDbg(id)` → 等 `loaded.includes(name) && mine.node===true` → `__modelBoxDbg()` 算 CLIP（中心 ±170/±190）→ `__modelShowDbg(true)` 不传 zoom = 真实比例。
- 生产环境：`ubuntu@193.112.172.83:/home/ubuntu/snake-3d/`，端口 8090，**HTTP（非 HTTPS，https 会 ERR_SSL_PROTOCOL_ERROR）**；`pkill -f serve.py` 会自杀，须精确 PID。

## 相关文件

| 用途 | 路径 |
| --- | --- |
| 契约 | `.tamako/contract.json` |
| 证据 | `.tamako/evidence.md` |
| 模型生成器 | `scripts/gen_models.js` |
| 生成器自测 | `scripts/test_gen_models.js` |
| e2e | `e2e/skin35.spec.js`、`e2e/_helpers.js` |
| 静态检查 | `scripts/static_check.js` |
| 本地 CI | `scripts/local_ci.ps1` |
| 探针 / 挂载 | `index.html`（`myHeadSel`、`__modelBoxDbg`、`__modelShowDbg`、`__modelDbg`） |
| 模型 | `models/nailong.glb`、`models/furina.glb` |
| Loader | `gltf-loader.js` |
| 皮肤表 / 白名单 / 版本 | `serve.py`（SKIN_N、FREE_SKINS、ALLOWED、PROTO_VER=30） |
| 正式存证 | `docs/evidence/batch35/`（**10 张**，`git ls-files` 计数=10） |
| 可复现验收脚本 | `scripts/prod_verify35.js`（第 2 轮新增，实跑 PASS） |
| 交接 / 待办 | `HANDOVER.md`、`BACKLOG.md` |


# 批36 证据（按整体评估建议逐个修复 · P0 落盘/写盘安全、P1 口径/备份/门禁、P2 拆分起步/热路径减负）

契约：`.tamako/contract.json` —— acceptance 1-8 全部 `verdict=pass`，`state=closed`（顶层 8 字段，JSON 可解析）。
全部改动均为本地 commit（db1f509 → 629620f → a0095e1 → 7dda151 → 0b03f4e → 2e160fd → bd270ee），**未 push**（契约 notDo）。

## 验收 1 —— store.inc/record_best 脏标记批量落盘（commit db1f509）

- 机制：`STORE_SAVE_INTERVAL=5.0` + `_mark_dirty()`（标脏，距上次真写 ≥5s 才落盘）；register/add_stardust/grant_skin 仍立即写；`shutdown_settle()` 无条件 `store.save()` 兜底 flush。
- RED：哨兵断言失败——「节流窗内 inc 不得重写 store.json」（往盘写与内存不一致的 `"food": 999`/`"best": 999`，任何真写都会抹掉哨兵）。
- GREEN：`test_store_inc_throttled_batched_save`、`test_store_record_best_and_shutdown_flush` 两条先红后绿。
- 套件：`.venv\Scripts\python.exe test_game.py` → `ALL GAME UNIT TESTS PASSED`（189 个 test_）EXIT=0。

## 验收 2 —— 写盘安全：persist 原子写 + store.json 损坏留证（commit 629620f）

- RED ①：原实现先 `open(path,'w')` 截断；注入不可序列化对象时 `TypeError` 不在 `except OSError` 内向上抛（实证 traceback）。
- RED ②：`Store.load` 损坏时静默 `users={}`，无任何留证。
- GREEN：`save_persist_rooms` 改 tmp+`os.replace`（异常吞掉、删半截 tmp、返 False）；`Store.load` 损坏先备份 `store.json.corrupt-<%Y%m%d-%H%M%S>` 再兜底。新测 `test_store_load_corrupt_backs_up_before_reset`、`test_save_persist_rooms_atomic_on_failure` 先红后绿。
- 顺带披露：修既存随机 flaky `test_eterrain_attach_and_spawn_avoid_batch33`（20×20 只撒 6 格 + 依赖全局 RNG 残留；套件内 3 红 2 绿、孤立 1/300）——测试改为钉死 `(5,5)/hydro` 构造性消除。
- 套件：test_game.py 189 全绿 EXIT=0。

## 验收 3 —— roomcfg 拍板口径（commit a0095e1）

- 口径（用户拍板原文）：「设密码的只有房主能改 没密码的所有人都能改」。
- 实现：`_msg_roomcfg`（原 handle_msg roomcfg 分支）内 `if room.passw and not can_edit_room(sess, room, m.get('otok'))` → error 回执并 return；三轨=账号 owner_user / 在线 sid / owner_tok 常数时间比对；无口令房维持放开（含首次设口令）。persist/delroom 未动（契约 notDo）。客户端已带 `otok`，前端零改动。
- 新测 `test_roomcfg_pass_room_owner_only`（陌生人被拒且参数不变、房主三轨放行）、`test_roomcfg_no_pass_anyone_edits` 先红后绿；批23/批24 既有 roomcfg 用例全绿（都跑在无口令房）。

## 验收 4 —— 生产 data/ 备份 tar

- 命令：ssh ubuntu@193.112.172.83 `tar czf /home/ubuntu/snake-3d-data-20261019-153034.tar.gz ... -C /home/ubuntu snake-3d/data`（key `C:/Users/yuan/.ssh/1.pem`）。
- 结果：`snake-3d-data-20261019-153034.tar.gz` 28834 B；`tar tzf` 输出含 `data/ 、data/store.json、data/usage.json、data/persist_rooms.json、data/usage.log` —— **store.json ✓**。

## 验收 5 —— 门禁补套：local_ci 9→11 套 + ci.yml 补 reactions（commit 7dda151）

- `scripts/local_ci.ps1`：suites 数组追加 `'test_ws3.py', 'test_ws4.py'`（放最后），头部注释与 Say 文案 9→11 套同步；文件保持 UTF-8 无 BOM（首字节 `23 20 6c`）。
- `.github/workflows/ci.yml`：round2 在 `python test_delta_p1.py` 后补一行 `python test_reactions_p33.py`（该套自起进程内随机端口 websockets 服务，不依赖外部端口）。
- 前置披露：ws3/ws4 两套断言停在批6 之前（期望创建者断开→自定义房立即回收），与现行 GC 口径（`DEFAULT_ROOM_IDS 常驻 / persist 永不回收 / 24h 内保留`）冲突，接入门禁前先改断言对齐设计（只改测试，两处加「批36 对齐口径」注释）。
- 实跑：`pwsh -ExecutionPolicy Bypass -File scripts\local_ci.ps1` → `ALL GREEN — 本地 CI 全部通过`、LOCAL_CI_EXIT=0；11 套 E2E 全 [PASS]、`ALL GAME UNIT TESTS PASSED`（189）、`ALL STATIC CHECKS PASSED`、Playwright `46 passed (2.2m)`。

## 验收 6 —— handle_msg 注册表化 + index.html 分区编号（commit 0b03f4e）

- serve.py：脚本化平移（断言式：分支数/消息名全集不符即中止不写盘）——原 698 行/32 分支 if-elif 链逐支平移为 28 个 `async def _msg_*(sess, m)`（统一缩进 -4，函数体逐行未改），注册进 `MSG_HANDLERS`；局内 9 名共用 `_room_actor`（=原链尾共享 guard 下移）；`handle_msg` 只剩 msgs 计数 + 查表分发。脚本输出：`OK handlers=28 names=32`，32 名=register…respawn 全集。
- index.html：18 个主分区头注按出现顺序编号 01..18（祈愿区升 19），IIFE 开头插入「批36 P2-2：JS 分区编号索引」注释块（19 头注实测行号 1198…4722）。
- 验证：`node scripts/static_check.js index.html` → `ids=135 dup=0 div=69/69 css=350/350 js=917/917` + `ALL STATIC CHECKS PASSED` EXIT=0；`.venv\Scripts\python.exe test_game.py` → `ALL GAME UNIT TESTS PASSED`（189）EXIT=0。

## 验收 7 —— 帧循环 DOM 缓存 + 榜单脏标记（commit 2e160fd）

- 改动：启动期一次性缓存 `elAtkBtn/elElemBar/elEbBtns`（frame 内不再每帧 `$()`/querySelectorAll；`setElem` 复用同一缓存）；`placeEdge` 的 canvas 包围盒 `_canvasRect` 缓存、`resize()` 置 null 失效；`updateBoard` 加内容签名脏标记（名次/名字/分数/存活/皮肤未变跳过 DOM 重建，款式同 `effHudSig`）。grep 复核：热路径残留命中均为一次性初始化/CSS/vendor 探针。
- 验证：`node scripts/static_check.js index.html` → `ALL STATIC CHECKS PASSED` EXIT=0；`npx playwright test`（BASE=127.0.0.1:8123 起服）→ `46 passed (2.1m)`、PW_EXIT=0。
- 竞态披露（未归因本批、未修——改 spec 属越界）：reactions.spec「元素弹渲染链路」在全量跑中偶发落在已 win 的 solo 局而超时（spec 注释自述既有竞态：solo 蛇撞墙死后不可重开）。本轮 HEAD 全量 4 次 2 挂 2 过；切基线 7dda151 对照 1/1 过；隔离跑 4/4 过；最终验收跑 46/46 过。失败快照显示 state='win'（AI-3 215 分的完整局），与逐行平移/缓存改动无状态机关联。

## 验收 8 —— 逐项独立 commit + 工作区干净

- 提交链（dev，未 push）：db1f509 → 629620f → a0095e1 → 7dda151 → 0b03f4e → 2e160fd → bd270ee（收尾文档+契约结项）→ 本证据补录 commit，共 8 个（≥6 ✓）。
- `git status --short` → 空（契约收尾提交后实测）。

## 复盘与已知问题（披露，均未越界动手）

- reactions.spec 竞态：建议后续让该 spec 落到 win 态时点「准备」重开一局再断言。
- test_ws3 套内一次偶发失败（复跑与孤立跑均绿），时序类。
- `.tamako/` 已被 git 跟踪（沿袭前批实践）；若不想入库：`git rm --cached -r .tamako` 并写入 `.gitignore`。
- 未 push：dev ahead origin/dev 约 24；HANDOVER §10 旧数字（13 spec/39 passed）未动（越界）。
