# 贪吃蛇 3D —— 项目交接文档

> 最后更新：2026-10-19 ｜ 分支 `dev` ｜ 文档描述的功能基线：批36「按整体评估建议逐个修复（P0 落盘/写盘安全、P1 roomcfg 口径/生产备份/门禁补套、P2 拆分起步/热路径减负）」完成（当前 HEAD 用 `git log` 查）
> 生产地址：**http://193.112.172.83:8090/**
> **批34（2026-10-19）**：地形真遮挡——丘/峰/楼/深渊材质 depthWrite=true（撤掉批32「蛇恒可见」妥协），山后之蛇被正确挡住；水/草/元素面片仍 depthWrite=false（否则贴层挡住地板上的蛇）。新增 `e2e/height32.spec.js` 批34 用例（断言各类 dw）、探针 `__heightMeshDump().dw`/`__elemDbgSet`/`__elemMeshDump`。协议 PROTO_VER 未变，纯客户端渲染。
> **批35（2026-10-19）**：新增「奶龙」「芙宁娜」两款角色蛇皮肤（`SKIN_N` 16→18，id 16/17），蛇头挂可辨识低多边形迷你 3D 模型——`scripts/gen_models.js` 自产 `models/{nailong,furina}.glb` + three r160 GLTFLoader 经**机械** ESM→UMD 改写的 `gltf-loader.js`（`<script>` 无模块架构不变）；两款入 `FREE_SKINS` 恒免费、**不进 GACHA_POOL**；`applyOffTint` 断线灰化改为逐实体克隆材质。**`PROTO_VER` 29→30（双端 bump）**，投放方式 = scp 5 文件 + 重启进程。取证探针 `myHeadSel`/`__modelBoxDbg`/`__modelShowDbg(on,zoom)`/`__modelDbg().mine`；证据 `.tamako/evidence.md`、契约 `.tamako/contract.json`（closed，4/4 pass）。

> **批36（2026-10-19）**：按整体评估建议修复——P0：`store.inc/record_best` 脏标记 5s 节流批量落盘（`STORE_SAVE_INTERVAL`，关停自动 flush）、`save_persist_rooms` 改 tmp+`os.replace` 原子写、`Store.load` 损坏先备份 `.corrupt-<时间戳>` 再兜底；P1：roomcfg 口令房仅房主可改（用户拍板，无口令房维持放开）、生产 data/ 备份 tar、`local_ci` python E2E 9→11 套（补 `test_ws3/ws4`，断言对齐批6 GC 口径）+ `ci.yml` 补 `test_reactions_p33`；P2：`handle_msg` 32 分支注册表化为 `MSG_HANDLERS`（逻辑零改动）+ `index.html` JS 分区编号 01-19 索引 + 帧循环 DOM 缓存与榜单脏标记。未部署生产（PROTO_VER 30 不变）。
---

## 1. 项目概览

多人在线 3D 贪吃蛇对战游戏。单文件服务端（HTTP + WebSocket 同端口），单文件前端（CSS/HTML/JS 全在 `index.html`），Three.js 渲染。

**当前已实现的功能**

| 类别 | 内容 |
|---|---|
| 对战玩法 | 多人同房间实时对战、咬蛇截断并入（非致死）、子弹射击缩短对方、岩石/墙块/传送门、星星奖励、道具（护盾/加速/穿墙）、重生无敌、回合胜负判定、**AI 蛇（单人练习/多人加 AI）**、**批33 元素反应（火/水/冰/雷附着 aura + 6 种反应 + 元素弹 eb + 元素地面 eterrain）** |
| 房间系统 | 3 个默认房间 + 自定义房间（尺寸/主题/岩石/传送门/AI 数量 任意组合）、房间卡片列表（人数、属性、🤖AI 标识）、空房自动回收、观战、**主页「单人练习」快捷开局（24×24 + 3 AI 自动进局）** |
| 账户 | 昵称与账号合并（一个输入框）、6 位数字密码、token 恢复登录、可游客游玩 |
| 排行榜/战绩 | 全服排行榜、个人战绩（胜场/击杀/死亡/场次/最高分/吃果数） |
| 界面 | 统一 `.chip` 按钮风格、开始页布局、房间列表、创建面板、排行榜屏、暂停屏、结束屏、**三处 🏠 返回主页**、移动端触屏方向盘 |
| 视听 | 环境光+半球光+平行光、粒子/飘字、音效与背景音乐、**18 款皮肤（7 免费 + 11 抽卡；批35 新增 16 奶龙 / 17 芙宁娜，恒免费 + 迷你 3D 模型）**、5 种地图主题（常规/熔岩/冰原/星空/白天） |
| 抽卡（祈愿） | **批25**：星尘货币（局内吃果 10/颗、**吃星星 15/颗（批29⑤，原 10）** + 局末并账）、卡池 12 款（3★×6 / 4★×3 / 5★ 白金圣蛇+UP 辉夜）、160 星尘/抽、1.6% 5★ + 90 抽硬保底 + 50/50 歪则下个 5★ 必 UP、10 抽必出 4★、重复返还 10/50/200、流星抽卡动画（单抽/十连、最高档压轴、跳过），**批31**：动画原神化重做——夜空天幕（星空+山峦剪影地平线）、长彗尾流星右上入场向中央下方消失点透视飞行（单抽 ~1.4s / 十连每颗 550ms 依次）、落地光柱冲天（5★ 金柱+震动）、单抽剪影 hold→翻牌+星徽光圈绽放、十连流星飞完直接进陈列依次翻卡；五星皮肤高级感三件套（局内 emissive 强脉动+头部星尘拖尾+光环，大厅演示蛇同享；皮肤页 5★ 金框流光大卡 `.s5`/4★ 紫框 `.s4`）；我的皮肤页签（按星级分组点选）、大厅入口 ✨祈愿；**批29④**：版本更新庆祝回馈（每账号每 `PROTO_VER` 一次，14,400 = 90 抽×160，**批31 起登录 auth 即弹**，room-ok 路保留兜底） |
| 后台 | 服务器使用情况记录（`usage.log`/`usage.json` + 报表脚本），**不体现在页面上** |

---

## 2. 交付物清单

```
snake-3d/
├── serve.py          3782 行  服务端：HTTP + WS + 游戏逻辑 + 账户 + 房间 + 用量记录（批36：MSG_HANDLERS 注册表）
├── index.html       5073 行  前端：CSS + HTML + JS 全在一个文件（批36：JS 分区编号 01-19）
├── three.min.js      654 KB  Three.js r160 本地 vendor（批10 从 r128 升级；r160 是最后带 UMD three.min.js 的版本，r161+ 仅 ESM）
├── gltf-loader.js            three r160 GLTFLoader 的 UMD 产物（批35，机械 ESM→UMD 改写，供 <script> 引入）
├── models/                   nailong.glb / furina.glb（批35，由 scripts/gen_models.js 自产的低模，可复现）
├── scripts/                  gen_models.js · test_gen_models.js · static_check.js · local_ci.ps1 …
├── e2e/                      Playwright 用例（_helpers.js · smoke · skin35（批35）…）
├── .tamako/                  契约 contract.json + 证据 evidence.md（每批的验收落点）
├── test_game.py      24 项单元测试（纯逻辑，不起服务）
├── test_ws.py        E2E：入局/移动/攻击/排行榜/房间
├── test_ws2.py       E2E：HTTP 三接口 / 注册登录 / 入局快照 / 观战 / 排行榜 / 建房
├── test_ws3.py       E2E：房间列表 + 自定义地图 + 空房回收
├── test_ws4.py       E2E：96 超大地图 + 速度即时生效 + leave 回主页
├── verify_rooms.py   生产验证（端口 8090，创建房间→进房→断线回收）
├── verify_prod.py    生产 WS 冒烟（进房 a、快照字段、食物唯一 id）
├── test_delta_p1.py  协议验收（批11）：快照增量——首帧全量/稳态缺失沿用/观战者补全量
├── test_reactions_p33.py E2E（批33）：进程内双 ws——附着→咬击/元素弹反应链、aura 双端同步与双消、frozen 冻结（B 不动 A 动）
├── usage_report.py   离线用量报表（天/用户两个维度，支持 --log 明细）
├── DEPLOY.md         部署与回滚说明（部署章节仍然准确）
├── README.txt        最简运行说明（随 /download 打包）
└── .gitignore        __pycache__ / .venv / *.log
```

生产服务器文件位于 `/home/ubuntu/snake-3d/`（额外含 `data/`、`.venv/`、`*.bak-*` 备份）。

---

## 3. 运行环境与依赖

| 项 | 值 | 注意 |
|---|---|---|
| Python | 3.10 | 服务端唯一语言 |
| websockets | **==13.1（锁定）** | `serve.py` 用旧版 `process_request(path, headers)` API；16.x 已移除该 API，升级会导致 HTTP 请求 500 |
| 三方框架 | 无 | 单文件，`pip install websockets` 即可跑 |
| Node.js | 20（静态检查 `node --check` + Playwright 冒烟/CI） | 不参与游戏运行时 |
| 浏览器 | 现代浏览器（需 WebGL） | **批9 起有 Playwright 自动化冒烟 + 截图**（`e2e/smoke.spec.js`，需外部起 8123 服）；720p 短屏已专项修复 |

启动：

```bash
python3 serve.py                 # 默认端口 20000
PORT=8090 python3 serve.py       # 生产用环境变量指定端口
```

---

## 4. 系统架构

### 4.1 服务端（`serve.py`）

```
main() ── websockets.serve(handler, '0.0.0.0', PORT) 启动 HTTP+WS 同端口
  ├─ process_request()   静态文件 / /api/leaderboard / /download（每次请求读盘）
  ├─ handler()           每连接一个协程：解析 JSON → 分发 t == '...'
  │    ├─ 认证段：register/login/authtoken/logout/leaderboard/rooms/create
  │    ├─ 进出段：watch / join / leave          ← 独立于"需在房间内"的闸门
  │    └─ 房间内段：ready/dir/atk/speed/skin/respawn（需 sess.room + sess.pid）
  ├─ game_loop()         每 CYCLE=50ms 遍历所有房间（room_list / gc_empty_rooms）
  │    └─ Room.step_wrapper() → 过期道具/星星刷点/弹道/步进/回合判定/快照广播
  └─ gc_empty_rooms()    回收"无人且创建者已下线"的自定义房间（a/b/c 永不回收）
```

**核心类**

- `Room`：地图（`cols/rows`）、地形（`walls/portals/rocks`）、`players{id: p}`、`subs`（订阅者集合）、`events`（事件缓冲，随快照下发）、`theme_fixed/rock_mult/portal_on/owner`（自定义配置）、`new_round()/spawn_player()/drop_player()/check_win()`。
- `Session`：`sid/ws/user/pid/room/want_play/last_*`，使用量字段 `conn_s/play_ms/play_from/joins/...`。
- `Store`：账户与战绩持久化，PBKDF2-SHA256 加盐（60000 轮），密码必须 6 位数字。
- `Usage`：后台用量记录（见 §9）。

### 4.2 客户端（`index.html` JS 分区）

| 行段 | 分区 | 关键函数 |
|---|---|---|
| 7–376 | `<style>` CSS（含统一 `.chip`、overlay、触屏方向盘） | — |
| 378–533 | `<body>` HTML（HUD、四块 overlay、dpad） | — |
| 545–613 | 常量/配置 | `FRUITS SPEEDS ITEMS THEMES`、localStorage key |
| 614–753 | 3D 场景（灯光、相机、雾） | `buildBoard / ensureBoard / applyTheme` |
| 754–935 | 蛇的连续管状身体与皮肤 | `SKINS paintEnt` |
| 936–1033 | 粒子、飘字、音效 | `burst beep` |
| 1034–1081 | 坐标与模型 | `cw cellW` |
| 1082–1318 | 流程 + 服务器地形 | `reset spawnFromServer`、墙块/传送门/道具 |
| 1319–1377 | 网络层（连接、重连） | `connect onDisconnect` |
| 1378–1559 | 攻击 + 入局流程 | **`goHome start spectate joinIn togglePause`** |
| 1560–1838 | 实体与快照应用 | `applyPlayers applyWorld updateEffectsHud` |
| 1839–2120 | 消息与事件分发 | `onMsg`（switch + `snap` 独立分支）、`applyEvent` |
| 2121–2246 | 渲染 | — |
| 2247–2353 | 屏外方位指示 + 主循环 | `frame` |
| 2354–2529 | 账户 / 房间 / 排行榜 UI | `renderRooms renderLeaderboard` |
| 2530–2654 | 输入（键鼠 / 触屏 / 快捷键）与按钮绑定 | — |

> ⚠️ 分区注释与实际代码并非严格对应（例如 `goHome/start` 落在"攻击"段内，`onDisconnect` 落在"网络层"段内），按函数名搜索比按段落更可靠。
> **批25 补充**：行段表为批23 前快照，行号已漂移；批25 抽卡相关——`SKINS`（L1104，16 款含 star 字段）、祈愿界面与皮肤页签（L3619 起 `openWish` 等）、抽卡动画状态机（L3698 起，phase: hidden|meteor|flash|reveal|done）、大厅入口绑定（L3785 `btnWishLobby`）、CSS 祈愿（L171 起）/动画（L214 起）、HTML 覆盖层（L703/L728）。

**关键状态机**：`state ∈ idle | joining | playing | over | win`，配合 `joined / spectating / wantPlay / demoPaused` 四个布尔量决定界面与演示世界。

---

## 5. 通信协议

**全部为 JSON 文本帧，字段向后兼容——老客户端仍可正常游玩。**

### 5.1 客户端 → 服务端

| `t` | 字段 | 说明 |
|---|---|---|
| `register` | `user, pass` | 注册（`user` 即账号，**也是昵称来源**；`pass` 为 6 位数字）。**批22 限速**：同 ip 5 分钟窗成功注册满 30 次后拒绝（回「注册过于频繁」，明细记"限速拒绝"；失败不计数） |
| `login` | `user, pass` | 登录，成功回 `token`；**批21 防爆破**：同 (ip, 用户) 5 分钟窗连续失败 10 次后直接拒绝（明细记"限速拒绝"） |
| `authtoken` | `token` | 断线重连恢复登录态（不需要带 user）。**批22 M3**：令牌 `TOKEN_TTL=30` 天过期作废（回「登录已过期」并清字典）；成功鉴权**滑动续期**（活跃用户不过期），见 §6.2 |
| `logout` | — | 退出登录 |
| `leaderboard` | — | 请求全服排行榜 |
| `rooms` | — | 主动请求房间列表 |
| `create` | `name, size, theme, rock, portal, winMode, limit, respawn, bots, pass, wd, height, water, bld` | 创建自定义房间；非法值回退主题默认。**批33**：`elements`(bool，元素反应总开关，默认 true) + `elemAmt`(0–2，元素地面密度，默认 0.6)，建房即生成元素地面。**批32**：`height/water/bld`=地形起伏/水域/建筑密度（夹 0–4，跟随主题=缺省；与 rock 同为地形类，创建即生成、persist/live/roomcfg 全通路镜像）**批1 战场自定义**：`winMode` 只收 `last`(死斗)/`score`(积分)，否则 `last`；`limit` 秒数夹 0–3600（0=不限时；limit=0 时 score 兜底 300s、respawn 兜底 120s）；`respawn` 仅 `true` 生效（无限复活，3s 后原地重生）。**批4 AI**：`bots` 数量夹 0–7（非法回退 0），建房即生成 AI 蛇（负 pid、名字 AI-N、视为永远 ready）。**批6 口令（C3）**：`pass` 可选，给了就必须合法（6-20 位字母+数字混合、非弱口令黑名单，`valid_room_pass()` 前后端同步），非法直接 `error` 拒绝创建（不静默回退）。**批17 H**：`wd` 仅 `true` 生效（碰外墙折返，见 §6.2）。**批22 H3 限速+cap**：单会话 5 分钟窗最多 8 次、同 ip 窗内最多 40 次（超回「建房太频繁」）；全局 `ROOM_MAX=100`，满时先回收「无玩家无观战、超 600s、非 persist、房主不在线」空房，无可回收才拒绝 |
| `roomcfg` | `room, winMode, limit, respawn, wd, bots, height, water, bld` | **批18 E**：房间参数 live 编辑（不重开局、零协议改动——快照/check_win 现读房间字段）。鉴权 `can_edit_room()`：账号匹配 `owner_user`（跨重连有效）**或**仍是在线创建者 `sid` **或（批23 P6）请求带 `otok` 与房间 `owner_tok` `secrets.compare_digest` 一致**，默认/无主房间一律拒绝。语义：`limit` 改小到已超时 → 下一 tick 按时间到结算；score/respawn 房 `limit=0` 兜底 300/120s（与 `__init__` 同不变量）；`bots` 走 `set_bots()` 显式增减（增=补生成、减=优先摘死/挂起再摘低分，不走 drop_player 避开清 AI 级联）；size/theme/rock/portal 属地形**不可编辑**（theme live 改=下局生效为已知限制）；**批32** `height/water/bld` 镜像 rock 走 deferred「下局生效」循环（回执 `changed` 含同名键）；**批33** `elements/elemAmt` 同为 deferred（改后 `new_round` 重建 `eterrain` 生效，回执 `changed` 含同名键）；口令独立安全面不在列。回执 `{t:'cfgapplied', room, changed}` + 变更时 `broadcast_rooms` |
| `watch` | `room, pass` | 进入旁观（会先 `leave_room`）；口令房必须带对口令（批6）。**批22 M5**：同 (ip, 房间) 5 分钟窗口令错试满 10 次后**正确口令也拒**（回「口令尝试过于频繁」） |
| `join` | `room, name, skin, pass` | 入局。**新客户端不再发 `size`**（尺寸只在创建时决定）；老客户端仍带 `size`，空房时生效；口令房必须带对口令（批6，断线自动重连也带记忆的口令）。**批22 M5**：口令错试限速同 `watch`；**M1**：匿名断线恢复唯一候选时校验来源 ip 一致（不一致不复用，fail-open） |
| `leave` | — | **新增**：返回主页，把自己移出房间（旧客户端不发，行为不变） |
| `ready` | — | 回合结束后的下一局确认 |
| `dir` | `x, y` | 转向（服务端做反向与队列校验） |
| `atk` | — | 发射子弹（冷却 `ATK_COOL=800ms`） |
| `eb` | `elem` | **批33 新增**：发射元素弹——`elem` ∈ `pyro/hydro/cryo/electro`（否则静默忽略）。门禁顺序：`elements` 总开关 + 存活 + 非 win_pending + 非挂机（`pause`）+ 非 `frozen` 冻结 → 才查独立冷却 `EB_CD`（未过闸不吞 CD）；弹体入 `projectiles` 带 `elem` 与头格高度 `h`，广播 `ev('fire')` 带 `elem` |
| `ult` | — | **批2 新增**：释放大招（蓄力满 `ULT_MAX=100`、冷却 `ULT_COOL=3s`，否则服务端静默忽略）；8 方向环形弹幕 |
| `speed` | `ms` | 速度档，服务端夹到 80–300，**立即生效** |
| `skin` | `i` | 换皮肤。**批25**：`i %= SKIN_N` 归一化（负值/越界先折返），`i≥5` 必须已拥有（未拥有回 error 静默回退到 `join` 带的 i 或先前值），免费 0–4 恒可选；**批35**：`SKIN_N` 16→18、`FREE_SKINS={0,1,2,3,4,16,17}`（角色款恒免费且不进卡池，故无需持有记录） |
| `gacha` | `n` | **批25 T3 新增**：抽卡，`n` 白名单只收 1/10（其余回「无效的抽数」）；需已登录（否则「抽卡需要先登录」）；入局时玩家 `p.user` 必须与登录账号一致（防中途换号跨账号搬资产）；余额 = 总账 + 当场星尘 ≥ 160×n 才可（扣减先总账后当场，检查→扣减→save 无 await 关键区） |
| `gachainfo` | — | **批25 T3 新增**：拉抽卡状态（进祈愿界面/入局时各拉一次）；未登录回零值占位（防客户端卡死）；**批26**：登录账号与入局玩家 `p.user` 不一致（换号场景）同样回零值占位（与 `gacha` 同口径的身份校验，防跨账号混显总账/当场星尘） |
| `persist` | `room, otok?` | **批6 新增（新#11）**：把房间标记为常驻（成功后广播刷新列表；写盘 `data/persist_rooms.json`，重启重建、永不回收）。鉴权 **批23 P6** 从「仅在线 `owner==sid`」扩为 `can_edit_room()` 三轨（账号 / 在线 sid / `otok` owner 凭据常数时间比对）——匿名断线重连后仍可保存 |
| `chat` | `text` | **批5 新增**：房间聊天（≤80 字，空白不发，1s 限速超限静默丢弃）；观战者也可发，走快照 `ev` 通道 |
| `gchatin` | `text` | **批30③ 新增**：公屏发言（≤80 字截断、空白拒、每连接 1s 限速复用 `chat_throttle`——**限速槽先于内容校验消耗**，与房内 chat 同口径）；登录/匿名都可发，无需在房 |
| `pause` | （无） | **批30③b 新增**：对局暂停 toggle（挂机）——置/清 `off_at`+`pause`，复用挂起保护（原地冻结、不被咬/不顶头，批14/21/22 语义），`dir`/`atk`/`ult` 拒收；session 保持连接故 `step_wrapper` 不按 `RESUME_MS` 回收（挂机≠断线；挂机中断线由 `leave_room` 重置宽限照旧 10s）；挂机者算在场真人（他人断线原蛇挂起不移出）；回执 `pauseres` |
| `adkick` | `name` | **批30④ 新增**：踢人——仅 `ADMIN_USERS` 白名单（`ADMIN_USERS={'yuan'}`，登录名判定，匿名恒否）；命中该用户名全部在线会话：逐个发 `kicked` 后关连接（handler finally 正常清理）；回执 `adminres`；非管理员**静默拒**（只记 `usage.note('adm_denied')`，不回执不报错不泄露权限存在性） |
| `admute` | `name, mins` | **批30④ 新增**：禁言——写内存 `mutes[name]=到期时间戳`，`mins` 缺省 10、钳 1~1440 分钟；到期由 `is_muted()` 自动失效清条目；**仅登录账号可禁**（按用户名，匿名无账号不可禁）；禁言中 `gchatin` 与房内 `chat` 一律拒（回 `error`「你已被禁言」）；回执 `adminres` |
| `adnotice` | `text` | **批30④ 新增**：全局公告——≤200 字截断、空白拒；以显示名「📢 公告」进 `gchat_log` 并 `broadcast_gchat` 全体（复用公屏通道，历史/回显同普通消息）；回执 `adminres` |
| `adgrant` | `name, amt` | **批30④ 新增**：给指定用户发星尘——`amt` 钳 1~100000、目标必须存在于 `store.users`，`store.add_stardust()` 入账并 save；在线受奖者收 `toast` 提醒；回执 `adminres`（含新余额） |
| `adreport` | — | **批30④ 新增**：游玩汇总报告——`admin_report()` 现算（`usage.data` 不落盘）：实时在线/房间数 + 今日/累计（连接/玩局时长/进房/登录/注册/胜场）+ 近7日逐日 + 活跃榜 Top10（按玩局时长）；回执 `adreportres` |
| `respawn` | — | 死亡后重生。**批22 H4**：仅复活房（`room.respawn=true`）且死亡满 `RESPAWN_MS=3s` 才生效，否则服务端拒绝；客户端非复活房死亡直接转观战 |

### 5.2 服务端 → 客户端

| `t` | 关键字段 | 说明 |
|---|---|---|
| `welcome` | `rooms[], online, gchat, admin` | 连接建立，带完整房间列表；**批30②** `online`=当前在线人数（去重口径，见下 `online` 行）；**批30③** `gchat`=公屏最近 50 条历史；**批30④** `admin`=是否管理员白名单（亮「🛡 管理」Tab） |
| `rooms` | `list[]` | 房间列表（加入/离开/创建时主动广播） |
| `online` | `n` | **批30② 新增**：当前在线人数推送。口径=登录按用户名去重（同账号多标签=1）、匿名按会话计（`online_count()`）；广播时机=会话建立/断开 + 身份变化四消息（register/login/authtoken/logout）；首页 `.roomHead` `#onlineBox` 渲染「🌐 当前在线 N 人」。**纯增量不 bump PROTO_VER**（老客户端忽略未知字段/消息即兼容；bump 会强制 reload 且触发批29④ 每账号 14,400 回馈） |
| `gchat` | `m{name, text}` | **批30③ 新增**：公屏新消息，广播到全体连接（含未进房/观战）；历史仅 welcome 下发（`gchat_log=deque(maxlen=50)` 内存环形、不落盘、重启清空）；显示名=登录名 / 「路人+会话尾号」截 12 字 |
| `pauseres` | `on` | **批30③b 新增**：暂停回执。`on=true` 已挂机（蛇冻结中）/`false` 已恢复；客户端据此切换 `#pauseMask` 胶囊与双暂停键文案（HUD `#btnPauseGame` + dpad 中心键）；重连 `resume` 会连带解除挂机态 |
| `adminres` | `act, ok, msg` | **批30④ 新增**：管理操作回执；客户端管理面板 `#admOut` 渲染「✅/❌ + msg」（面板未开时 toast） |
| `adreportres` | `lines[]` | **批30④ 新增**：游玩报告文本行，`#admOut` 以 `white-space:pre-wrap` 渲染（纯文本非 HTML，防注入） |
| `kicked` | `msg` | **批30④ 新增**：被踢通知（随后服务端关连接）；客户端 toast 提示 |
| `toast` | `msg` | **批30④ 新增**：通用浮层提示（现用于发奖在线提醒「管理员发放 N ✨星尘」） |
| `created` | `room, name, tok` | 创建成功。**批23 P6**：`tok` = 一次性 owner 凭据（`secrets.token_hex(16)`），仅创建者回执携带，客户端存 `localStorage['snake-owner-toks']`（rid→tok 跨刷新），后续 `roomcfg`/`persist` 附 `otok` 恢复修改权；`info()`/room_list 不下发 |
| `room-ok` | `room, spectate, user, id, ver, gift?` | 进房成功，`id` 即 `myId`；**批5**：命中断线恢复时带 `resumed:true`（原 id/身体/分数保留，不重新出生）；**批26⑤**：`ver`=协议版本（`serve.PROTO_VER`，入局/resume/观战三路必带），客户端内置常量不等即 `location.reload()`（关闭「跨部署存活的旧标签页拿旧 JS 续玩」窗口；`ver` 缺省=服务端更旧时不重载，防死循环）。**改协议必须同步 bump 双端常量**（serve.py `PROTO_VER` 与 index.html `PROTO_VER`，忘 bump 的后果=退化为无保护现状而非坏行为）；**批29④**：join/resume 两路附 `gift`=待领更新回馈金额（0=已领/未登录；`_update_gift_pending()`，单调比较 `claimed < PROTO_VER`），客户端据此弹 `#giftPop`；观战（watch）路不带 |
| `left` | `room` | 离开房间回执 |
| `error` | `err` | **批6 新增**：服务端拒绝（口令错误/非法口令/非创建者保存等）；客户端浮层提示，入局中被拒则退回主页 |
| `auth` | `ok, user, token, stats, admin, gift, err` | 认证结果（`auth_payload`）；`authtoken` 失效时客户端自动清理本地态；**批30④** `admin`=白名单标记（登录后即时亮/收管理 Tab，退出/过期清零）；**批31** `gift`=待领更新回馈金额（login/register/authtoken 三路均带，0=已领不弹），客户端登录成功即弹 `#giftPop`（不再等 room-ok；room-ok 路保留兜底） |
| `leaderboard` | `list[]` | `[{name,best,wins,kills,games}]` |
| `gachares` | `items, balance, dust, gained` | **批25 T3 新增**：抽卡结果；`items[]` 按抽取顺序 `{skin, star, up, dup, refund, cap?}`（3★/4★/5★ 星级、up=本次 5★ 是否 UP、dup=重复已拥有、refund=重复返还星尘；**批27**：赢 50/50 的 5★ 额外带 `cap:true`=捕获明光——客户端对单项播「缩回→双星变形 glitch→二次飞行」演出，非 5★/保底/歪均不带此键）；`balance`=抽后纯总账、`dust`=抽后当场星尘（回包时点，refund 已入账）、`gained`=本次总返还 |
| `gachainfo` | `balance, dust, skins, p5, p4, lose` | **批25 T3 新增**：抽卡状态；`balance`=纯总账、`dust`=当前房当场星尘（不在局内=0）、`skins`=已拥有皮肤 id 列表、`p5/p4`=保底计数（距上次 5★/4★ 的抽数）、`lose`=50/50 是否已歪（下个 5★ 必 UP）；未登录回零值 |
| `claimgift`（C→S） | （无） | **批29④ 新增**：领取版本更新庆祝回馈 = `UPDATE_GIFT`（`GACHA_PRICE×90`=14,400 星尘）；**每账号每 `PROTO_VER` 版本一次性**（store 键 `update_ver_claimed`，单调比较防降级重放），校验与入账间无 `await`（单事件循环原子，连发不双计）；未登录/已领回 `error` |
| `giftres` | `ok, amount, balance` | **批29④ 新增**：领取回执；客户端关弹窗 + 刷余额 + 到账 toast |
| `snap` | 见下 | **50ms 一次快照（批11 起为增量协议）** |

**`snap` 字段**：每帧恒在 —— `t, room, theme, cols, rows, players[](含 bot), proj[], ev[], round, win, over, winMode, limit, respawn, remain`；**仅变化时下发**（批11 C1 增量协议，字段缺失=客户端沿用旧值）—— `walls, portals, rocks, items, foods[], bonus`；**批32** `hmap`（高度地形三元组列表 `[[x,y,h],...]`，0=平不存，签变才带；PROTO_VER 27→28 双端）；**批33** `eterrain`（元素地面 `[[x,y,elem],...]`，进 `DELTA_FIELDS` 走 full+DELTA 双路；PROTO_VER 28→**29** 双端）。
> **批33**：`players[]` 每条新增 `aura`=`{e, at}`（元素附着，`AURA_MS=8000` 过期；未附着/已过期不下发；**重生清 aura、断线挂起保留**；玩家落盘前 `p.pop('aura')` 不入存档）；`proj[]` 每条新增 `elem`（元素弹 id）；房间配置新增 `elements`/`elemAmt`。
> **批32**：`proj[]` 每条新增 `h`=发射者头格高度（0=平地），客户端子弹贴该高度渲染。
> **批25 A**：`food` 更名 **`foods`**（列表）——场上多果（每图 3–8 颗，`food_target()` 按 cols×rows 分档），元素 `{id,x,y,score,color}`，`id` 为全局递增（客户端按 id 对齐 mesh，删果即删 mesh）；旧字段名与单果语义废弃，本字段名变更为**批25 唯一协议 break**（同步升级客户端，老客户端不兼容）。
> 批1 新增：`winMode('last'/'score')`、`limit`(秒，0=不限)、`respawn`(bool)、`remain`(限时剩余秒，int，无限制时 0)。
> 批11 增量协议：服务端对 6 个静态字段做签名对比（`Room._field_sig`），变了才带；新订阅者（join/watch/resume）首帧为**全量帧**（6 字段齐全 + `full:1`，由 `Session.full_sent` 控制，`broadcast` 内补组）。稳态实测增量帧较全量帧省 ~31% 字节。协议级验收见 `test_delta_p1.py`（第 8 套 E2E）。

**`players[]` 字段**：`id, name, skin, cells[], dir, q, score, alive, tick, base_tick, inv, eff{shield,speed,ghost,magnet,double,rage,deflect}, user, cause, by, combo, ult, bot, off`（`off`=断线挂起中，批5；**批12 起客户端灰化渲染 + 名字 💤**；`q`=服务端转向队列长度，批13，客户端据此对账截断本地 dirQ）
> `ult` 为大招蓄力（0–100），满 100 可按 `ult` 消息/点 HUD 按钮释放。

**房间信息（`rooms` 列表项）**：`id, name, cols, rows, theme, themeFixed, rock, portal, players, alive, watchers, round, over, winMode, limit, respawn, bots, hasPass, persist, wd`
> `players` 是**已连接人数**（含旁观），`alive` 是存活蛇数。

**事件 `snap.ev[]`**（由 `applyEvent()` 处理）：`join / eat / die / kill / fire / hit / bite / clash / star / rock / phit / expire / round / win / respawn / ult / **react**`
> 顶层消息由 `onMsg` 的 switch 处理，`snap` 在 switch 之外单独分支；事件只随快照下发，不单独成帧。
> `bite{eater,victim,cut,score}`、`hit{x,y,by,victim,cut,score}` 是截断类事件。
> **批32** `phit{x,y,h,by}`：子弹撞高度地形碎裂（`h`=该格高度；仅客户端特效，无得分）；新死亡 cause：`cliff`（上行 ≥2 峭壁）、`crush`（高度差碾压/反噬）。
> **批33** `react{kind,by,victim,x,y}`：元素反应统一出口（`kind` ∈ frozen/vaporize/melt/overload/electro/superconduct，`by`=攻击者 id 可空）——客户端按 `cellW(x,y)` 打反应浮字+粒子；`fire` 事件新增 `elem`。

### 5.3 HTTP 接口

| 路径 | 返回 |
|---|---|
| `/` `/index.html` | 前端页面（**每次请求读盘**，改 `index.html` 不需重启服务） |
| `/three.min.js` | Three.js |
| `/api/leaderboard` | JSON 排行榜 |
| `/download` `/download.zip` | 源码打包 zip |

---

## 6. 核心玩法规则与参数

### 6.1 服务端常量（`serve.py` 顶部，改这里即可调平衡）

| 常量 | 值 | 含义 |
|---|---|---|
| `CYCLE` | 0.05 | 主循环 50ms |
| `PROJ_SPEED` | 22.0 | 子弹格/秒 |
| `ATK_COOL` | 800 | 攻击冷却 ms |
| `BONUS_LIFE` | **12000**（批29⑤，原 8000） | 星星存活 ms（+50 分）；实际 = 基础 × `life_mult()`（批3，随地图放大） |
| `BONUS_SPAWN_P` | **0.015**（批29⑤，原 0.004） | 每 tick 刷新星星概率 |
| `WIN_SCORE` | 200 | 达到该分数触发胜利判定 |
| `SPAWN_INV` | 2500 | 重生无敌 ms |
| `ITEM_LIFE` | 12000 | 道具在地上存活 ms；实际 = 基础 × `life_mult()`（批3，随地图放大） |
| `EFFECT_MS` | 6000 | 道具效果持续 ms |
| `MIN_LEN` | 2 | 被截断后蛇保留的最少格数 |
| `STUCK_TICKS` | 2 | 同格对头僵持连续达到该 tick 数 → 确定性 tie-break 判死（批14） |
| `BULLET_CUT` | 1 | 子弹命中截断的格数（按需求"不要太大"） |
| `BITE_SCORE_PER_CELL` | 8 | 咬下对方每格得分 |
| `COMBO_MS` | 3000 | 连击窗口：两次吃果间隔超此值连击重置 |
| `COMBO_TIERS` | 15/10/5 → x2.5/x2/x1.5 | 连击倍率档位（1-4 连 x1） |
| `MAP_MIN / MAP_MAX` | 12 / **96** | 地图尺寸上下限 |
| `RESPAWN_MS` | 3000 | 无限复活模式下死亡到重生的等待 ms |
| `LIMIT_MAX` | 3600 | 限时模式上限（秒） |
| `ULT_MAX` | 100 | 大招蓄力上限（攒满才可释放） |
| `ULT_FRUIT / ULT_STAR / ULT_KILL` | 10 / **25**（批29⑤，原 15） / 30 | 大招充能：吃水果 / 吃星星 / 咬蛇淘汰 |
| `ULT_COOL` | 3000 | 大招释放冷却 ms |
| `FRUITS` | 10/15/20/15/15 | 5 种水果分值 |
| `ELEMS` | pyro/hydro/cryo/electro | **批33** 元素 id（火/水/冰/雷） |
| `AURA_MS` | 8000 | **批33** 元素附着 `aura` 持续 ms |
| `EB_CD` | 2000 | **批33** 元素弹 `eb` 独立冷却 ms |
| `EB_SPD` | 1.2 | **批33** 元素弹速度（格/tick 口径，慢于普通子弹 22 格/秒） |
| `ULT_REACT` | 15 | **批33** 每触发一次反应给攻击者的充能 |
| `FROZEN_MS` | 1600 | **批33** 冻结时长 ms（不能移动、不能发射，**可被咬、累计得分照旧**） |
| `SLOW_MS` | 3000 | **批33** 超导减速时长 ms（tick ×1.5） |
| `USAGE_MAX` | 8 MB | 用量日志轮转阈值 |

### 6.2 关键规则

- **咬蛇 = 截断并入；压到 2 格再被咬 → 淘汰**：接触点之后的对方身体被切走并接到自己身上；对方保留 `MIN_LEN=2` 格；**已是 2 格再被咬 → 整条淘汰**（`cause='bite'`，残躯归攻击者，事件 `bite` 带 `kill:true`）。
- **连击 Combo**：`COMBO_MS=3s` 窗口内连续吃果 `combo+1`，超时/死亡/新回合重置；只有**水果**计数（星星/道具/咬蛇不打断也不加）。倍率 `combo_mult()`：1-4→x1、5-9→x1.5、10-14→x2、15+→x2.5 封顶；`snap.players[]` 带 `combo`，`eat` 事件带 `combo/mult`。
- **道具 7 种**（`ITEM_TYPES`）：`shield 护盾 / speed 加速 / ghost 穿墙` + `magnet 磁铁`（食物/星星每 tick 朝自己拉 1 格、绕障碍、停在蛇头旁不落格）、`double 双倍`（一切得分 ×2，走 `score_gain()` 统一入口）、`rage 狂暴`（攻击 CD 减半 + 子弹速度 ×1.5，`proj[]` 带 `spd` 字段）、**`deflect 偏转`（批2：仅撞边界墙时折返不死；场内岩石照死、咬到 <2 照样淘汰）**。
- **护盾强化（批2）**：`shield` 除原被咬免疫外，**任何地形碰撞（边界墙/岩石墙块/自己身体）都折返不死**——折返方向取蛇头垂直两方向中空间最大的可走格（无路可走仍照死），折返时清空转向队列。
- **大招（批2，A6）**：`p.ult` 蓄力 0–100，吃水果 +10、吃星星 +25（批29⑤，原 15）、咬蛇淘汰 +30（封顶 100）；满 100 发 `ult` 消息 → 从蛇头向 **8 方向**发射环形弹幕（对角线方向归一化、`spd=1.5`、命中仍只截断 `BULLET_CUT=1` 格），冷却 `ULT_COOL=3s`，死亡/重生清零。客户端 HUD 蓄力条（满时脉冲高亮），键 `K` 或点按钮释放。
- **子弹**：命中截断 `BULLET_CUT=1` 格，对无敌/护盾无效，不打自己。
- **传送门扩容（批3，新#2）**：`portal_pairs()` = `max(1, min(4, cols/16 就近取整))` 对（12/16→1、24/32→2、40/48→3、64+→4；24×24 起成对）；`portals` 格表按 `[a,b,a2,b2,...]` 扁平存储，`portal_map()` 两两配对互逆；生成时保证两口不同、曼哈顿距离 >6 且不与障碍重叠。**传送后蛇头朝向**取出口处上下左右四方向中 `_open_ahead` 最开阔者（不朝最近的墙；仅改即时朝向，不改玩家转向队列）。
- **资源有效期随地图放大（批3，新#6）**：`life_mult() = clamp((cols×rows)/576, 1, 4)`，星星 `bonus_life()` 与道具 `item_life()` = 基础值 × mult（12×12→×1、24×24→×1、48×48→×4，更大夹 4），`step_wrapper` 过期判断使用放大后的值。
- **死亡**：由撞墙、撞岩石、撞自己、**被咬淘汰（2 格规则）**、断线导致 → 回合结束；普通咬与射击不致死。
- **速度**：客户端三档 `慢260 / 中150 / 快85`（比例约 3 倍），服务端 `apply_speed()` 立即生效，实际 tick 保持在 `[base-45, base]`（吃水果会累积加速），下限 60ms；加速道具再 ×0.6（下限 60）。
- **出生点**：`spawn_player` 会规避其他蛇与障碍，且初始朝向**不指向最近外墙**；出生后 2.5 秒无敌。
- **胜利**：分数 ≥ `WIN_SCORE` 或场上只剩一条存活蛇时进入 `win_pending`，等各客户端 `ready` 后 `new_round()`。
- **战场自定义（批1）**：每房间 `win_mode / limit / respawn` 三参数决定结算（`check_win()` 四级判定，按顺序）：
  1. **限时**（`limit>0`，计时自 `round_started`，新局重置）：时间到 → 当前比分最高者 +`WIN_SCORE` 胜（`ev('win')` 带 `reason:'time'`），并列最高 → 平局；
  2. **无限复活**（`respawn=True`）：死亡不触发淘汰结算，`died_at` 起 3s 后原地重生（`spawn_player` 重建身体 + `ev('respawn')`）；
  3. **积分赛**（`win_mode='score'`）：**全员死亡**才按比分结算（`reason:'score'`）；
  4. **死斗**（默认 `last`）：只剩一条存活 → 胜；全死 → 平局。
  丢人（drop_player）同样走 `check_win`。参数校验：`winMode` 非 last/score 回退 last；`limit` 夹 0–3600；`respawn` 必须布尔；limit=0 时 score→300s、respawn→120s 兜底（score 优先）。
- **碰外墙折返（批17，H）**：`create` 带 `wd:1`（布尔，非法回退 False）→ `Room.walldeflect`——全员常驻「仅边界墙折返」（与 deflect 道具同语义：step §4 折返 guard 放行，方向由 `_deflect_dir()` 取垂直两向中空间最大者，仍无路可折照死 `cause='wall'`）。**边界**：正面撞岩石/墙块照死（`cause='rock'`）、撞自己照死、2 格被咬照常整条淘汰（折返不救被咬）；`rooms` 列表项带 `wd`，房间卡片 meta 显示「↩︎碰墙折返」；建房面板「碰墙」下拉（关闭·撞墙即死 / 碰外墙折返）；`wd` 随 persist 持久化往返。
- **房间参数 live 编辑（批18，E）**：新消息 `roomcfg`（见 §5 协议表）——创建者可改 `winMode/limit/respawn/wd/bots`，**live 生效不重开局**。归属：`Room.owner_user`（create 时记 `sess.user`，随 persist 往返）；`can_edit_room()` **三轨鉴权（批23 P6）**：账号跨重连 / 在线 sid / `otok` owner 凭据（`owner_tok` + `secrets.compare_digest`，随 persist 往返，客户端存 `snake-owner-toks`）。客户端：房间卡片「⚙ 设置」（`isMine()` = `myCreated` 或本地有凭据，服务端二次鉴权）→ 复用创建面板（批23 N2）→ `cfgapplied` toast。**已知限制**：地形类参数（size/theme/rock/portal）改动下局生效。
- **登录防爆破限速（批21）**：同 `(ip, 用户)` 在 `AUTH_FAIL_WIN=300s` 窗内连续登录失败满 `AUTH_FAIL_MAX=10` 次 → 直接拒绝**不再查库**（回执 err「尝试过于频繁，请稍后再试」，usage 明细记 `err='限速拒绝'` 供报表排查）；登录成功/窗口过期自动复位；内存 dict 每次计数时顺手清过期键防撑爆（重启清零可接受）。单测 `test_auth_login_throttle` 全覆盖；失败原因明细见批20。
- **批22 安全加固（6 项）**：① **匿名 resume 绑 IP（M1）**：匿名断线恢复只在恰一个无账户挂起者时命中，且其 `off_ip` 与当前来源 ip 一致才复用（不一致 → 当新玩家处理；`off_ip` 缺失 fail-open 兼容旧数据；账号玩家不绑）——防抢号。② **注册限速（M2）**：同 ip 5 分钟窗成功注册满 `REG_MAX=30` 拒（失败不计数）。③ **token TTL（M3）**：`token_at` 记签发/续期时刻，`authtoken` 超 `TOKEN_TTL=30d` 作废清字典；成功鉴权 `tokens_inv` 滑动续期（活跃用户不过期）；logout 同步清理。④ **建房限速+房间 cap（H3）**：单会话窗内 `CREATE_MAX=8` + 同 ip `CREATE_IP_MAX=40`（`CREATE_WIN=300s`）；全局 `ROOM_MAX=100` 满时先回收「无玩家无观战、>600s、非 persist、房主不在线」空房，无可回收才拒。⑤ **口令错试限速（M5）**：同 `(ip, 房间)` 窗内错试满 `PASS_FAIL_MAX=10`（`PASS_FAIL_WIN=300s`）→ **正确口令也拒**（闸在口令比较**之前**，watch/join 两处同构）；错试才计数。⑥ **H4 裸 respawn 门禁**：服务端 respawn 分支要求 `room.respawn` 且死亡满 `RESPAWN_MS=3s`（`died_at` 判定），非复活房发 `respawn` 静默拒绝；客户端 `respawn()` 非复活房直接 `spectate()`、复活房 3.2s 自动补发过延迟。通用窗口闸 `_win_ok/_win_bump`（auth 系列委托复用）。CI 加固：`ci.yml` 加 `permissions: contents: read`。单测 6 新例先红后绿（99 用例）。
- **AI 蛇（批4，A4）**：`create` 带 `bots`(0–7) 建房即生成；条目与普通玩家同结构但 `bot:true`、pid 为负数、名字 `AI-N`、`session=None`。**决策**：step 中该 AI 移动到期且转向队列空时 `_bot_think()`——候选不回头且界内可走；打分 `(是否绝路, 离目标距离, -目标方向对齐度, -前方开阔)`；**目标取 food/bonus 中距离更近者（等距优先星星，批15③**，不再星星无条件压过近处水果**）**，直达被挡时按对齐度绕行而非 DIRS4 定序偏航（批15②），无目标时以最开阔方向为准。AI **视为永远 ready**（只等真人 ready 触发新局）、常驻 `round_ids` 参与胜负计数、死亡/复活/新局逻辑与真人共用。**最后一个真人离开房间时 AI 全部清掉**（否则 AI 占位导致空房永不回收）。
- **单人练习（批4，新#5）**：主页「🐍 单人练习」→ 建房 `{size:24, bots:3}` → `created` 自动入局（断线重连 onopen 补建房）；建房面板「AI蛇」下拉 0/1/2/3/5/7；房间卡片 meta 显示 `🤖AI×N`。
- **断线恢复（批5，B2）**：断线时若房内**还有其他真人** → 原蛇置 `off_at` 挂起（原地冻结、不移动不参与转向）等待 `RESUME_MS=10s`；单人房/无其他真人则立即清房（保空房回收语义）。重连（同账号精确匹配；匿名仅当恰一个无账户挂起者）走原 `join` → `room-ok` 带 `resumed:true`，**原 id/身体/分数全保留不重新出生**；超 10s 未归 → drop（含清 AI）。客户端本有的自动重连（onDisconnect→2s→join）自动命中新路径。挂起者对 `maybe_start_round` 视为 ready。
- **房间聊天（批5，B3）**：`chat` 消息（≤80 字、空白不发、每连接 1s 限速超限静默丢弃）→ 快照 `ev` 通道广播 `{t:'chat',name,text}`；观战者可发（发件人=房内玩家名，否则账户名/'观众'）。客户端按 `/` 或点击输入框进入聊天（输入框早退方向键），左下角消息流 7s 淡出、上限 30 条、textContent 防注入，断线清空。
- **公屏聊天与聊天面板（批30③）**：服务端 `gchatin` → `gchat_log`（`deque(maxlen=50)` 内存不落盘）→ `broadcast_gchat` 全体会话，`welcome_payload()` 带历史（组包已从 handler 拆出）。客户端 `#chatPanel` 双 Tab（💬公屏 / 🏠本房），入口三处：首页房间行「💬 公屏」（恒公屏）、顶栏「💬 聊天」（局内默认本房，**手机可点**，批30 拍板「都做+按钮适配手机」）、键盘 `/`（局内本房/局外公屏）；本房 Tab 局外自动回退公屏；Enter 发送、Esc 关闭。本房消息仍走批5 `ev` 通道（左下角 7s 淡出流不变），面板持久列各 100 条、textContent 防注入；旧 `chatIn` 输入框与 `.chatLog.up` 已移除；断线/换世界清本房列表，公屏历史跨世界保留。
- **对局暂停=挂机（批30③b）**：HUD「⏸ 暂停」`#btnPauseGame` + dpad 中心「暂停」键（对局中=挂机，主页 demo 暂停行为不变）→ `pause` toggle → 服务端原地冻结 + 复用挂起保护（不被咬/不顶头）+ `dir`/`atk`/`ult` 拒收 + session 在不按 `RESUME_MS` 回收；挂机者算在场真人（他人断线原蛇挂起不移出），重连 `resume` 一并解除挂机态。提示胶囊 `#pauseMask`「已挂机 · 点按恢复」为居中小胶囊（非全屏遮挡——**暂停中聊天/HUD 照常可用**），断线/回主页撤提示；协议纯增量不 bump PROTO_VER。门禁：`test_pause_afk_batch30` + `test_pause_counts_as_present_batch30` + `e2e/pause.spec.js`×2。
- **管理员账户（批30④）**：身份=用户名白名单 `ADMIN_USERS={'yuan'}`（登录名判定，匿名恒否；加人改 serve.py 常量）。五权限消息 `adkick/admute/adnotice/adgrant/adreport`（表见 §5.1），非 admin **静默拒**+`usage.note('adm_denied')`，服务端每分支二次校验。踢人=发 `kicked` 后关该用户全部在线会话连接；禁言=内存 `mutes[name]` 到期自动失效（缺省 10 分钟、钳 1~1440，仅登录账号），`gchatin`/房内 `chat` 同拒；公告复用 gchat 通道（显示名「📢 公告」，历史可见）；发奖 `store.add_stardust` 钳 1~100000 且用户须存在，在线受奖者收 `toast`；报告 `admin_report()` 从 `usage.data` 现算文本行（实时/今日/累计/近7日/活跃 Top10）。客户端：`welcome`/`auth` 携带 `admin` 亮聊天面板「🛡 管理」Tab（`#admPane`：目标用户名+踢出/禁言10分/发奖数额/公告框/报告按钮 + `#admOut` 结果区），登出/过期即时收权，非白名单 `hidden` 仅易用性（权限判定恒在服务端）。协议纯增量不 bump PROTO_VER。门禁：`test_admin_core_batch30` + `test_admin_notice_grant_report_batch30` + `e2e/admin.spec.js`×2（公告回显/发奖踢人/非管理员无入口）。
- **高度地形（批32）**：**服务端权威 hmap**（稀疏表 `{(x,y): h}`，0=平不存；编码 -2 草丛/-1 水洼/1 丘/2 峰/3 楼/9 深渊）由 `gen_heights()` 生成（build_terrain 后，山包→水洼→建筑→草丛四类共享 `int(0.35*area)` 预算，避开 portals/walls/旧蛇头±4/已放格；**无平行数组 cellh，逐节查表单源**，spec §12①）。三旋钮 `height/water/bld`（THEME_CFG 五主题各有 hill/water/bld 基准，`*Custom` 覆盖，夹 0–4，persist/live/roomcfg/deferred 全通路镜像 rock）。**通行**：`_solid/_open_ahead/occupied/reach_set` 四接入点，上行 ≥2 峭壁（含深渊 9）挡、下行自由、水洼移动减速 30%（`int(t*1.3)`）、出生点必 h==0；**战斗**：头撞身体节 stance 三分支（撞前头格高：高→碾压整条死 `cause='crush'`、同高→现有咬击截断不变、低→攻击者死）；head-on 高度裁决低者死；子弹贴发射者头高、沿途目标格更高挡弹 `ev('phit')`、蛇身命中需 `abs(节h-弹h)<=1`（大招同规则）；ghost 全穿透。**客户端**（PROTO 28）：`syncHeight` 按 kind 池化重建（h=9 黑柱+Edges 描边为 child、水/草呼吸面；全部 `depthWrite=false` 保证蛇恒可见），蛇逐节 y=visH(hmapD) lerp+头俯仰，预测 `advanceStep` 挡崖与 rock/wall 同走 shield/deflect 门控，`proj[]` 带 `h`，伏击草=对方整蛇淡出 `.35`（自己全亮），水面水花粒子。建房/编辑面三下拉「地形/水域/建筑」。探针：`window.__mapDbgSet/__heightDbg/__mapSelfCorridorSet/__mapSelfCliffBlock`。门禁：`test_height_gen_invariants/test_height_cfg_roundtrip/test_cliff_move/test_water_slowdown/test_spawn_h0/test_ghost_cross_height/test_crush/test_bullet_terrain/test_bullet_hit_range/test_snapshot_height` + `e2e/height32.spec.js`×3。
- **元素反应（批33，原神体系）**：四元素 `ELEMS=pyro/hydro/cryo/electro`，**附着 `aura`（`AURA_MS=8s`）** 三条来路——① 咬击：攻击者带 aura 则感染给被咬者、攻击者消耗（`_bite_reaction`，双方都有则先判反应再消耗）；② 走上元素地面 `eterrain` 格（移动落格时附着/同元素刷新、异元素先反应，重生点规避元素地面）；③ 元素弹 `eb` 命中（不碎岩、跨高度层照打 `abs(节h-弹h)<=1`）。**6 种反应** `REACTIONS`（同元素/一方无 aura → None）：水+冰→`frozen` 冻结 1.6s（不可移动/不可发射，仍可被咬、可得分）、火+水→`vaporize` 与 冰+火→`melt`（victim 截 1 格）、雷+火→`overload`（半径1 爆炸各截 1 格）、雷+水→`electro`（victim + 头旁最近者各截 1 格）、冰+雷→`superconduct`（半径2 全体 slow 1.5×tick）。**统一出口 `apply_reaction()`**：先发 `ev('react')`（victim 已死也发，保证视觉反馈）→ 断言不改既有 `grow`/`MIN_LEN` 语义 → 双方各消耗 aura → 攻击者充能 `ULT_REACT=15`（封顶 `ULT_MAX`，`charge=False` 可关）。**元素弹 `eb`**：独立 `EB_CD=2000ms`、速度 `EB_SPD=1.2`，与普通子弹 `atk`/大招 `ult` 并行不互抢；门禁顺序「开关→存活→非 win_pending→非挂机→非冻结→才查 CD」。**元素地面 `eterrain`**：`(x,y)->elem` 稀疏表，`build_eterrain()` 预算 `min(60, cols*rows*0.015*elemAmt)`，占位计进 `occupied()`（食物/道具/岩石不落元素格）；随 `hmap` 之后生成，进 `DELTA_FIELDS` full+DELTA 双路。**房间旋钮** `elements`(bool 总开关)/`elemAmt`(0–2 密度)：create 即生成、`roomcfg` deferred 下局生效、persist 往返、旧存档缺字段回退默认（True/0.6）。**客户端（PROTO 29）**：HUD `#elemBar` 四按钮（键 `1-4` 切元素、`E` 发射，CD 冷却态 `.cool`）、`aura` 元素色光晕、frozen/slow 罩色、`eterrain` 面片、`react` 3D 浮字、元素弹染色、建房/编辑两旋钮、预测侧 frozen/slow 门控。探针：`window.__stateDbg/__auraDbg/__floatDbg/__projDbg`。门禁：`test_game.py` 批33 ×21（`*_batch33`）+ `test_reactions_p33.py`（第 9 套 E2E）+ `e2e/reactions.spec.js` ×4。
- **房间口令（批6，C3）**：建房可设口令 `pass`（6-20 位字母+数字混合、`WEAK_PASSES` 黑名单前后端同步校验），非法 `error` 拒绝创建；口令房 `join`/`watch` 必须带对口令（先校验再动状态，避免把自己踢出原房）。`info` 带 `hasPass`（口令本身不下发）。客户端：建房面板「口令」输入框（可选）、进房 `prompt` 要一次口令后内存记忆（页面生命周期免重输，含断线自动重连）、创建者免重输、口令错误清记忆并 toast 提示。
- **空房保留/保存（批6，新#11）**：自定义房间创建后 **24h 内不回收**（`ROOM_KEEP_SECS=86400`，之后仍按"没人+没观战+创建者不在线"才删）；创建者可在房间卡片点「⭐ 保存」→ `persist` 消息 → `persist=True` 写盘 `data/persist_rooms.json`，**常驻不回收 + 重启后重建**（`load_persist_rooms()` 于 `main()` 启动时调用）。`info` 带 `persist`，meta 显示「🔒口令」「⭐常驻」。
- **丝滑移动插值（批7，新#3）**：逻辑仍按格走（服务端不动）；客户端渲染在 `prev→next` 格间按 tick 进度**线性插值**——实体位移时记 `moveAt/moveDt`（按观测间隔自适应，夹 60–400ms），`syncBody` 按 `phase=(now-moveAt)/moveDt` 在两格间取插值目标再走脊柱平滑；头部大跳变（>6 格，传送门/跨图出生）不插值直接贴新位置。演示蛇同理按 `(now-lastTick)/180` 插值。
- **边缘提示图标（批7，新#9）**：屏外边缘提示不再一律 🍎——按水果实际颜色映射图标（红→🍎、樱桃红→🍒、粉→🍓、紫→🍇、橙→🍊，`FRUIT_EMOJI`），星星仍 ⭐；每帧 `updateEdgeHints` 同步。
- **白天主题 + 面板配色（批7，新#4/#10）**：主题池新增 `day`（见 §6.3）；客户端 `THEMES.day` 浅色天空 `0x9ecff2`、亮色棋盘格；建房面板主题下拉新增「白天」，且各主题选项文字着该主题原始配色（`wall` 色），与主页场景一致。桌面浏览器未连接时无法截图验收，视觉项以静态检查+单测+E2E 佐证。
- **小地图（批8，B1）**：右上角 150×150 canvas `#miniMap`（≤760px 屏 104×104），入局/观战才显示、每帧 `updateMinimap`：棋盘底+边框、墙块/岩石/传送门（交替紫/蓝，几何来自 `wallCells/portalCells` 缓存）、水果按实际颜色点、星星金点、道具按类型色点、玩家自己绿大点/他人红点（尸体不画）、观战目标白圈。
- **观战切换（批8，新#8）**：观战时 ←/→（或 A/D）与触屏左右滑循环切换被观战者——`spectList()` 名单=存活蛇按分数降序（与「跟随领先者」同序），toast 显示「观战：名（i/N）」；相机优先跟随 `spectTarget`，失效（死亡/离场）自动回退领先者；进观战/入局/回主页重置目标。
- **移动端压缩（批8，B4）**：`@media (max-width:760px)` 压缩标题/HUD chip/开始页文案/聊天与小地图尺寸、开始页可纵向滚动；转向操作已有触屏滑动 + 方向键面板（pointer 事件，含跟随模式左右键布局）覆盖。
- **720p 短屏裁切修复（批9 附带）**：1280×720 下 `scrollH` 曾 768（dpad 第二行 ⚔ 越界 4px）。修复：`resize()` 对 `innerHeight<=760` 用系数 `.60`（其余 `.68`，画布 720p→432px）；`@media (max-height:720px)` 内 `body` 底 padding 44→16、`.dpad` 行 56→46/gap 8→6、`body.follow .dpad` 同步 46px。修复后 scrollH=720 零溢出（Playwright 实测）。
- **方向输入可靠化（批13，D 方向失控）**：① 快照 `players[]` 带 `q`（服务端转向队列长度），客户端 `applyPlayers` 存入 `myEnt.q`，快照循环里超出 q 的本地 dirQ 尾部截断——以服务端为权威，覆盖 deflect/shield 清队、clash 清队、队满丢新项三类服务端清队不同步导致的**队头永久失步锁死**；② 回合切换（handleRound 变更分支）、`round` 事件、onWin else 分支强制 `dirQ=[]`（旧版新局开局携带陈旧队列整局锁死）；③ `setDir` 前置 `wsOpen` 门控（未发出的项不进本地队列）；④ `broadcast` 对订阅者发送失败改调 `leave_room(sess, hard=False)`（旧版仅置 `sess.room=None` 造成幽灵订阅+重连双蛇；新走挂起语义，`off_at`/`resumable` 全保留，10s 内重连 resume 命中同 id）。
- **碰撞与出生加固（批14，F 碰撞卡叠）**：① **spawn** 主路径 `any(_solid(...))` → `any(occupied(...))`（额外避让食物/星星/道具；`occupied()` 顶部补**出界即占用**——旧 `_solid` 独有界检查，直接换函数会生成贴边 OOB 蛇身）；兜底分支弃「居中硬铺 3 格零检查」，改扫 `free_cells` 落四向开阔 ≥4 的安全点，仍失败才回退居中位（由破僵局保底）。② **保护期拦进入**：攻击者欲进出生无敌/护盾蛇的身体 → 本帧 `skip_move`（不插头不咬），不再穿身重叠。③ **对头破僵局**：同格对头连续 `STUCK_TICKS=2` tick → 确定性 tie-break（`str(id)` 大者判死 `cause='stuck'`，客户端文案「与对手僵持卡死」）；单帧内每蛇最多被强制右转一次（防双重右转反向自杀）；hstreak 按 tick 统一计数（不在 pair 循环内加，防三方同格误杀）、成功移动即清。④ **off_at 挂起蛇**：不再参与被咬与顶头强制右转（仍是地形/寻路障碍，`_solid`/`free_cells`/`check_win` 不变）；`resume()` 位置复核（出界/压地形/被活蛇穿入）→ 原地 `spawn_player(fresh_cells)` 重生，杜绝恢复出重叠死锁。⑤ **传送门**：出口被任意活蛇身体占 → 本帧不传送原地停留（`skip_move`）；出口选向打平时**延续进入方向**（旧版方向序首项恒偏东）。⑥ 尸体不阻挡保持不变（已按 alive 全面过滤）。回归：`test_game.py` 79 用例（本批 +10，旧码 9 红）、local_ci ALL GREEN。
- **AI 水果可达性与寻路（批15，C AI 吃不到水果）**：① `place_food` 只放**静态地形可达集**内（`Room.reach_set()`：从活蛇头 flood-fill，只看边界/岩石/墙块，传送门当可走格且与配对口互连；无活蛇取首个非地形格兜底；可达区无空格退化回旧行为）——杜绝水果落进蛇圈/岩石口袋永不可达；缓存 `self._reach`，失效点 build_terrain / maybe_rocks / 子弹碎岩 / drop_player，另每次校验蛇头仍在缓存内（防幽灵跨区漏算），96×96 冷算 ~11ms、命中后仅 O(free) 过滤（计时断言 50ms，`test_place_food_reach_time_budget`）。② bot 直达被挡时按**目标方向对齐度**选绕行向（打分加 `-align` 键），不再按 DIRS4 定序反向偏航绕圈。③ food/bonus 目标改 `min(dist)` 就近选取（等距优先星星）。回归：+4 用例（83），旧码 4 红。
- **死亡结算观战 + 面板下拉暗色（批16，B+G）**：① G：死亡结算屏 `overScreen` 新增「👀 观战」按钮 `btnOverSpectate`（默认 hidden；`onMyDeath` 显示、`showReadyScreen` 隐藏——准备屏不提供以免掉出回合），点击走 `spectate()`（内部 `wantPlay=false`）；`spectate()` 起补 `joined=false`，从局内死亡切入观战与主页观战收敛到同一条已验证路径（服务端 `watch` 自带 `leave_room(sess)`，死蛇正常摘除）。② B：`.createPanel select { color-scheme: dark }` + `option` 暗色兜底——仅作用于建房面板内 8 个原生下拉（cSize/cTheme/cRock/cPortal/cWin/cLimit/cRespawn/cBots），不外溢全站控件（Playwright 断言 body 非 dark）。回归：Playwright 5/5（+2 例，旧码双红）。
- **动态自适应画质（批23，P4 卡顿）**：`frame()` 每帧喂帧耗时 **EMA**（.88/.12），`ema>24ms` 连续 30 样本（≈0.5s，<45fps）降一档、`<17.5ms` 连续 180 样本（≈3s）升一档、档位变更后 2.5s 冷却回差防抖；首帧/切回标签 >1000ms 大间隔不计入。三档 `QUAL_TIERS`：pixelRatio `1.5/1.0/.75`、阴影 `开/开/关`、小地图刷新 `每帧/每2帧/每4帧`；阴影开关 `traverse` 置 `material.needsUpdate` 重编译，pixelRatio 落地统一走 `resize()`。调试钩子 `window.__qual={quality,qualSample,setTier,applyQuality}`（`quality.freeze` 隔离真实帧，探针专用）。探针 `test-results/p4_quality.js`（**会被 local_ci 的 playwright 清空，备份 `Temp\opencode\p4_quality.js`**）。

### 6.3 主题（`THEME_CFG`）

| 主题 | 岩石倍率 | 传送门 | 固定墙块 | 地形 hill | 水域 water | 建筑 bld |
|---|---|---|---|---|---|---|
| `default` | 1.0 | 有 | 0 | 0.9 | 0.6 | 0.5 |
| `lava` | 1.7 | 无 | 6 | 1.4 | 0 | 0.3 |
| `ice` | 0.5 | 无 | 0 | 0.5 | 0.9 | 0.4 |
| `space` | 0.6 | 有 | 4 | 1.1 | 0 | 0.9 |
| `day` | 0.8 | 有 | 0 | 0.8 | 0.7 | 0.6 |

房间未固定主题时**每局随机**（池含 5 种主题，批7 新增 `day` 白天：浅色天空、亮堂棋盘）；自定义房间的 `theme_fixed / rock_mult / portal_on` 覆盖主题默认值。传送门开启时按地图大小生成多对（见 §6.2 传送门扩容），快照 `portals` 为扁平坐标列表，客户端按索引两两配对、交替紫/蓝配色。

---

## 7. 房间系统

- **默认房间**：`a` 新手村 24×24、`b` 标准局 24×24、`c` 大神场 32×32 —— **永不回收**。批30①：新手村专属配置（`NEWBIE_ROOM_CFG`，重启重建即生效）——岩石密度固定 0.5 覆盖主题、2 条 AI 陪练、死亡可复活（init 自动限时 120s 比分结算）；主题保持随每局随机；b/c 全默认不动。
- **自定义房间**：`create` 时一次性决定 `size(12–96)/theme/rock(0.0–4.0)/portal(bool)/name(≤16 字)/winMode(last|score)/limit(0–3600 秒)/respawn(bool)`，并在**创建瞬间**构建地形与放置水果（`baa9843` 修复）。
- **尺寸档位（前端下拉，已分组）**：小 12·16 ｜ 标准 24·32 ｜ 大 40·48·64 ｜ 超大 80·96。
- **房间列表**：默认只列**至少 1 人**的房间并按人数倒序，同时始终显示当前选中房间；加入/离开/创建时主动广播刷新。
- **回收规则 `gc_empty_rooms()`**：房间无人（无玩家、无旁观）**且创建者会话已消失**才删除。调用点：`watch`/`join`/`leave` 处理器内（此时目标房间已就位，避免"换房时旧房被误删/新加入的房被删"竞态）以及 handler 的 `finally`（在 `all_sessions.discard` 之后）。

---

## 8. 账户 / 排行榜 / 战绩

- 存储：`data/store.json`，结构 `{账号: {salt, hash, created, stats:{wins,kills,deaths,games,best,food}}}`。
- 密码：**6 位数字**，PBKDF2-HMAC-SHA256 + 随机盐（60000 轮）。
- 登录成功发 `token`，客户端存 `localStorage`，断线重连用 `authtoken` 恢复；token 失效时客户端**自动清空并解锁只读输入框**。
- **昵称与账号合并**：只有一个输入框 `#userIn`；未登录时可填任意昵称，登录后只读并锁定为账号。
- 游客可直接玩（不登录也能入局，`user=null`），但战绩不入库。
- 排行榜来源：`Store.leaderboard()`，同时提供 `/api/leaderboard`。

---

## 9. 后台用量记录（页面不体现）

按需求实现，**不进协议、不进页面、无 HTTP 接口**。

- **明细** `data/usage.log`：JSONL，事件类型 `start / conn / session / join / auth / win / logout`（`auth` 另带 `kind=register|login|authtoken`）；`session` 记录含 `at, sid, ip, ua, user, name, room, score, conn_s, play_s, msgs, joins`；达 8MB 轮转为 `usage.log.1`。
- **汇总** `data/usage.json`：`{totals, days[YYYY-MM-DD], users[账号]}`。`totals/days` 字段 `sessions, conn_s, play_s, joins, registers, wins, logins`；`users` 另含 `best, last`。
- **写入时机**：会话与胜利立即落盘；认证类事件节流（同类 ≥5s 才保存）。
- **查询**（只在服务器上跑，不对外）：

```bash
ssh tencent "cd /home/ubuntu/snake-3d && .venv/bin/python usage_report.py 7"        # 近 7 天 + 用户汇总
ssh tencent "cd /home/ubuntu/snake-3d && .venv/bin/python usage_report.py 7 --log"  # 附带明细
```

---

## 10. 测试体系

| 测试 | 类型 | 覆盖 |
|---|---|---|
| `test_game.py` | 单元 ×183 | 幽灵穿墙/撞墙死亡/传送门/道具拾取/速度效果/护盾/咬蛇截断与**2格淘汰**与免疫/子弹截断/出生点/水果唯一 id/自定义房间/**apply_speed**/**free_cells 大地图**/usage 日志/**combo 链与超时重置**/**combo 档位倍率**/**双倍得分**/**磁铁吸附**/**狂暴 CD 与子弹加速** + 批1 ×7（战场自定义/限时/积分赛/死斗/复活×2）+ 批2 ×10（deflect/护盾折返/大招充能与释放）+ 批3 ×4（传送门对数随地图/多对互逆/出口朝开阔方向/资源有效期随地图）+ 批4 ×7（AI 配置/生成/追食转向/避墙/单人胜/AI ready/离房清 AI）+ 批5 ×10（聊天×2/挂起宽限与超时/挂起清AI/恢复匹配/状态保留/单人房立即清/多人房挂起/挂起蛇冻结）+ 批6 ×5（口令校验/口令不泄露/24h保留/persist不回收/持久化往返）+ 批7 ×1（白天主题进池/day 建房与地形）+ 批13 ×2（快照 q 字段 / send 失败挂起且 resume 命中）+ 批14 ×10（spawn 主路径与兜底避让/protected 拦截进入/单帧单右转/僵持 tie-break 判死/挂起不顶头/挂起不被咬/resume 冲突重生/portal 出口占位停走/portal 打平延续进入方向/bot 活性守卫）+ 批15 ×4（封死口袋不放水果/可达集 BFS 计时与缓存/bot 被挡按对齐度绕行/bot 就近选目标）+ 批17 ×4（墙折返房撞墙垂直折返/折返无路照死/正面撞岩石照死/2格被咬照常淘汰；persist 往返含 wd）+ 批18 ×5（陌生人拒改/创建者 live 改不重开局/账号归属跨会话/bots live 增减/兜底限时镜像；persist 往返含 ownerUser）+ 批20/21 ×2（usage err 明细/登录防爆破限速）+ 批22 ×6（respawn 消息门禁/建房限速与房间 cap/注册限速/口令错试限速/匿名 resume 绑 IP/token TTL 过期与滑动续期）+ 批23 ×10（humans 字段/roomcfg 统一扩展/win_pending 超时强开/晚加入补准备屏 + owner 凭据 ×3：回执带 tok 与列表不泄露/匿名凭据恢复编辑/persist 三轨凭据；persist 往返含 ownerTok）+ 批33 ×21（反应表完整/同元素与缺元素返 None/aura 快照与 TTL/重生清 aura 断线保留/eterrain 约束与附着避让/full+DELTA/咬击六反应全覆盖/反应双消与感染/反应充能与死伤降级/碰撞碾压结果不变/元素弹附着与 CD/命中刷新/不碎岩与门禁/跨高度层/冻结不移动且恢复/冻结头静止障碍/冻结输入门禁/冻结可被咬/超导 slow×1.5/elements+elemAmt 三入口与旧存档默认） |
| `test_ws.py` | E2E | 连接、入局、移动、攻击、排行榜、房间列表、创建房间 |
| `test_ws2.py` | E2E | HTTP 三接口、注册登录（`user/pass` + token）、入局快照字段、第二连接观战、排行榜、创建房间 |
| `test_ws3.py` | E2E | 房间列表属性、自定义地图（40×熔岩/岩石/传送门）、非法参数回退、人数广播、空房回收 |
| `test_ws4.py` | E2E | 96×96 与 9999 夹紧、快照尺寸、速度 215/85 即时生效、`leave` 清房与回收、离开后可重新入局 |
| `test_p1.py` | 协议 | 连本地服：`snap.players[]` 带 `combo`、`proj[]` 带 `spd`、`ITEM_TYPES` 7 种（批2 同步：+deflect）（需先起 28000 测试服） |
| `test_bots_p4.py` | E2E | 批4 AI：create `bots=3` → 房间列表 `bots/players` 计数 → 快照 3 bot（负 id、AI- 名、存活有 cells）+ 1 人 → 3 秒内 AI 蛇头自主位移（连 28000） |
| `test_reconnect_p5.py` | E2E | 批5：双真人房断线 → 重连 `resumed:true` 同 id、身体长度不变且漂移≤2 格 → chat 首条随快照 ev 送达、1s 内第二条被限速（连 28000） |
| `test_pass_p6.py` | E2E | 批6：弱口令/黑名单口令建房被拒 → 合法口令建房 `hasPass` → 无口令/错口令 join 与 watch 被 `error` → 对口令进房 → persist 非创建者拒、创建者成且列表 `persist=true`（连 28000） |
| `test_delta_p1.py` | 协议 | 批11 C1：join 首帧 6 静态字段齐全 + `full:1` → 稳态 30 帧 walls/portals 缺席 ≥25（缺失=沿用）且 players/proj 每帧恒在 → 中途 watch 者首帧仍全量（连 28000） |
| `test_reactions_p33.py` | E2E | 批33：进程内双 ws（`websockets` 起本地服）——A 带 cryo aura 咬 B 触发 `frozen` → `react` 事件与 `aura` 双端同步送达 → 双方 aura 各消 → 冻结期 B 不动而 A 正常移动（5 断言，`reactions E2E PASS`，连 28000） |
| `verify_rooms.py` | 生产 | HTTP 200 + 创建/进房 + **批6 后：creator 断开后新房间 24h 内保留**（info 带 hasPass/persist） |
| `verify_prod.py` | 生产 | WS 冒烟：进房 `a`、快照字段、食物唯一 id、玩家 cells |
| `e2e/smoke.spec.js` | Playwright ×5 | 批9 冒烟：首页渲染（标题/canvas/布局无溢出）、单人 guest 登录入局（HUD 显示）、观战切换（按钮态/截图落 test-results/）。批16 +2：建房面板下拉暗色（`color-scheme` computed 断言 + body 不外溢）、死亡结算屏→观战衔接（固定视角循环按左撞墙真实死亡 → `btnOverSpectate` 可见 → 点击后结算屏收起 + `btnJoinIn` 出现，无 JS 报错）。**外部起服**（无 webServer 配置），需 `BASE=http://127.0.0.1:8123` |
| `e2e/reactions.spec.js` | Playwright ×4 | 批33：元素 HUD 四按钮+键1切冰+键 e 进 CD（`waitPlaying` 后再按）、playing&alive 帧 40ms 紧采断言 `__projDbg()>0`（元素弹存活极短 ~60-400ms）、注入 `aura{cryo}`+`react{frozen}` 断言 `__auraDbg`/`__floatDbg` 并截图 `test-results/p33_attach_react.png`、`elements=false` 时 `#elemBar` hidden。固定账号 `p33elem`（免疫生产注册限流），**外部起服**，`BASE` 可指生产 |
| `.github/workflows/ci.yml` | CI | push dev/main + PR：单测 → 起 28000/8090 → 8 套 python E2E → 起 8123 → Playwright → upload-artifact（test-results/playwright-report，失败另传 serve 日志） |
| `scripts/local_ci.ps1` | 回归 | 批12.5 一键全量（**批33 起 9 套**）：停服清库→起 28000/8090→9 套 E2E（含 `test_reactions_p33.py`）→单测→停服清库→静态检查→起 8123→Playwright（13 spec / **39 passed**）→汇总 `ALL GREEN`/Exit 1。**必须 pwsh 运行**（powershell 会因 UTF-8 无 BOM 报 ParserError）；可 `-SkipE2E`/`-SkipPlaywright` |

**运行方式**（Windows 本机 / Termux 本机 / 服务器三种都能跑，注释已标平台；下列命令均已实测）：

```bash
# ── 单测 ── Windows 本机（仓库自带 .venv，websockets==13.1）
.venv\Scripts\python.exe test_game.py

# ── 单测 ── Termux 本机 / 或直接在服务器上跑
ssh tencent "cd /home/ubuntu/snake-3d && .venv/bin/python test_game.py"

# ── E2E ── Windows 本机：先起本地测试服（28000，独立 data/）
$env:PORT='28000'; .venv\Scripts\python.exe serve.py     # 占一个终端常驻
.venv\Scripts\python.exe test_ws.py                      # 另开终端跑，同理 test_ws2/3/4.py
#   停本地测试服：
#   Get-NetTCPConnection -LocalPort 28000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
#   本地跑 E2E 会写 data/store.json、data/usage.json（测试账号），见 §14-10

# ── E2E ── Termux/服务器：先起测试服（28000，独立 data/，复用生产 venv）
ssh tencent "fuser -k 28000/tcp; cd /home/ubuntu/snake-test && PORT=28000 setsid nohup /home/ubuntu/snake-3d/.venv/bin/python serve.py > srv.log 2>&1 & " 
ssh tencent "cd /home/ubuntu/snake-test && for f in test_ws*.py; do /home/ubuntu/snake-3d/.venv/bin/python \$f; done"

# ── 生产验证 ── verify_*.py 连的是 127.0.0.1:8090，只能在服务器上跑
ssh tencent "cd /home/ubuntu/snake-3d && .venv/bin/python verify_rooms.py"

# ── 前端静态检查 ── 本机 Node 即可
node --check /path/to/extracted.js        # 从 index.html 抽 <script> 后检查

# ── Playwright 冒烟 ── Windows 本机（批9；$env:PORT 必须在 Start-Process 之前设置）
$env:PORT='8123'; .venv\Scripts\python.exe serve.py     # 占一个终端常驻
$env:BASE='http://127.0.0.1:8123'; npx playwright test # 另开终端（npm install 后）；截图落 test-results/
```

**前端静态检查清单**（无浏览器时的替代手段，`node scripts/static_check.js index.html` 一条跑完，尾行 `ALL STATIC CHECKS PASSED`）：
1. `node --check` 抽出的 JS；
2. JS 里 `$('id')` 引用的 id 必须全部存在于 DOM（当前 135，`dup=0`）；
3. `<div>` 开闭数量相等（当前 69/69）；
4. CSS 花括号配对（当前 350/350）、JS 圆括号配对（878/878）。

---

## 11. 部署与运维（生产）

### 11.1 服务器信息

| 项 | 值 |
|---|---|
| 主机 | 腾讯云 Ubuntu 22.04 `193.112.172.83`（别名 `tencent`，用户 `ubuntu`，密钥 `~/1.pem`，免密 sudo）。**Windows 本机 `~/.ssh/config` 已同时配 `tencent` 与 `vmsz` 两个别名指向同一台**，本文档命令用任一别名都能原样执行 |
| 目录 | `/home/ubuntu/snake-3d/`（生产）、`/home/ubuntu/snake-test/`（28000 测试）、`/home/ubuntu/snake-3d.git`（**git 裸仓库**，只读镜像） |
| 服务 | `snake-3d.service`（开机自启、崩溃自启），`Environment=PORT=8090` |
| 端口 | 安全组仅放行 **22、8090**；`8091` 为 1Panel 仅监听 127.0.0.1 |
| 访问 | 游戏 `http://193.112.172.83:8090/` |

### 11.2 发布流程（批19 起的标准动作：git archive，不再产生 .bak）

```bash
# 0) 部署前必查漂移（上次部署以来生产是否被手改过）
git show <上次部署commit>:serve.py > /tmp/s.py && sha256sum /tmp/s.py
ssh tencent "sha256sum /home/ubuntu/snake-3d/serve.py"   # 不一致 → 停下调查，别覆盖
# 1) 部署前备份（回滚点，整个目录打包，排除 .venv/data/__pycache__/node_modules；node_modules 由 npm ci 重建，可把 tar 从数百 MB 降到数百 KB）
ssh tencent 'tar czf /home/ubuntu/snake-3d-predeploy-$(date +%Y%m%d-%H%M%S).tar.gz \
  --exclude=.venv --exclude=data --exclude=__pycache__ --exclude=node_modules -C /home/ubuntu snake-3d'
# 2) 归档投放（本地 git archive 流式覆盖，无需 push；⚠️ PowerShell 下 $() 会被本地插值，远端命令一律单引号；
#    ⚠️ Windows core.autocrlf=true 会把 LF 转成 CRLF，必须加 -c core.autocrlf=false 得纯 LF，否则服务器 sha256 对不上）
git -c core.autocrlf=false archive --format=tar -o $env:TEMP\deploy.tar dev
scp $env:TEMP\deploy.tar tencent:/tmp/deploy.tar
ssh tencent 'tar -xf /tmp/deploy.tar -C /home/ubuntu/snake-3d && rm /tmp/deploy.tar'
# 3) 重启 + 验证
ssh tencent 'sudo systemctl restart snake-3d && sleep 3 && systemctl is-active snake-3d'
ssh tencent 'curl -s -o /dev/null -w "%{http_code} %{size_download}B\n" http://127.0.0.1:8090/'
ssh tencent 'journalctl -u snake-3d --since "3 minutes ago" --no-pager | grep -iE "error|traceback"'
#   E2E 探针：把 test_delta_p1.py 的 28000 换成 8090 后 scp 上去跑
#   ⚠️ 服务器系统 python3 没装 websockets，必须用 /home/ubuntu/snake-3d/.venv/bin/python
```

### 11.3 回滚

```bash
ssh tencent 'tar xzf /home/ubuntu/snake-3d-predeploy-<时间戳>.tar.gz -C /home/ubuntu && sudo systemctl restart snake-3d'
```

当前生产版本：**dev@`816530d`（批35，已 commit；第 2 轮补批见本段末）** —— 批35「奶龙/芙宁娜 角色皮肤 + 迷你 3D 模型」于 2026-10-19 **直接 `scp` 5 文件 + 重启进程**投放（`index.html` + `gltf-loader.js` + `models/nailong.glb` + `models/furina.glb` + `serve.py`，**未走 git archive**，因改动仍在 dev 工作区未提交）。投放后核验：远端 `PROTO_VER = 30`、新 PID 1676685、资源白名单全 200、远端 `index.html` 249141 B 且 `grep -c myHeadSel` = 3；运行时 `loader=true`、`skins[16]=nailong` / `skins[17]=furina`、`MOUNT_* node=true skull=false`、`FALLBACK node=false skull=true`、取证三会话 `ERRS=[]`（`pageerror` + `console.error` 全空）。注意：**批35 `PROTO_VER` 29→30 双端 bump** —— 老标签页进房即 `location.reload()`，并会再触发批29④ 每账号 14,400 星尘更新回馈（`update_ver_claimed` 单调比较，属预期行为而非 bug）。回滚点：**`snake-3d-predeploy-20261019-134813.tar.gz`**（第 2 轮 2026-10-19 补建，546497 B / 55 条目，含 `index.html`、`serve.py`、`gltf-loader.js`、`models/*.glb`；较 §11.2 配方多排除 `node_modules`，`npm ci` 可重建，tar 从数百 MB 降到 546 KB，其余排除项一致）。上一已提交版本记录：**dev@`d86942c`**（批29 全部 6 项 + 批30 全部 4 项，2026-10-17 02:56 部署，origin/server 双远端均已推送）。

> 第 2 轮（2026-10-19，用户拍板「只补备份，先不推」）：① 生产补建 predeploy 备份 `snake-3d-predeploy-20261019-134813.tar.gz`；② 新增**可复现验收脚本** `scripts/prod_verify35.js`（从本机打生产 8090，实跑 `VERDICT=pass`、`ALL_ERRS=[]`、皮肤 16/17 `mine.node=true`，退出码 0；该脚本**只留在仓库，未投放生产**，它不需要跑在服务器上）；③ 批35 存证图入库 `docs/evidence/batch35/`（**10 张**，`git ls-files` 计数=10；原先在被 `.gitignore` 忽略、且 Playwright 每次运行会清空的 `test-results/` 里；脚本重跑产出的 4 张 ON/OFF 落 `test-results/` 不入库，可由脚本重新生成）；④ `git push` **仍未执行**（`dev` ahead `origin/dev` 16 / ahead `server/dev` 27），须人工拍板。

详细端口/1Panel 说明见 `DEPLOY.md`。

### 11.4 Git

- 分支 **`dev`**（全部开发提交），`main` 停在基线 `f583ce3`。
- **远端**：服务器裸仓库 **`tencent:/home/ubuntu/snake-3d.git`**（本地别名 `server`）。
  - **Termux 本机**：`dev`/`main` 已设上游跟踪，`git push` 不带参数即可同步。
  - **Windows 本机**：clone 得到的远端名叫 `origin`（`dev` 跟踪 `origin/dev`，`main` 只有 `origin/main`），已另补一个同址的 `server` 别名 —— 故 `git push server --all` 与 `git push` 都可用。
- 服务器上查看/克隆历史：`git --git-dir=/home/ubuntu/snake-3d.git log dev` 或 `git clone /home/ubuntu/snake-3d.git ~/repo`
- ⚠️ 生产目录 `/home/ubuntu/snake-3d/` **不是** git 仓库，它只是发布投放点（批19 起靠 predeploy **tar** 回滚，见 §11.3），不要在里面执行 git 操作。
- 提交历史（新→旧）：

```
85ceb6d docs: 交接文档补充服务器裸仓库远端（server）与同步命令
895b0e4 docs: 交接文档头部改为功能基线提交（避免与 HEAD 混淆）
1054411 docs: 新增项目交接文档（架构/协议/玩法参数/测试/部署/技术债/常见坑）
0f0245a feat(game): 环境光提亮 + 速度档拉开 + 随时返回主页 + 地图最大 96
a5a7e56 feat(usage): 后台记录用户服务器使用情况（页面不体现）
646a220 feat(room): 昵称账号合并 + 地图组合自定义 + 房间列表
0458676 style(ui): 统一全局 .chip 按钮样式 + 开始页布局重组
baa9843 fix(room): 房间创建时即构建地形并放置水果
d637c97 feat(gameplay): 咬蛇改为截断并入 + 子弹缩短 + 出生点优化 + 水果唯一id
9e4cf53 feat(backend): 多房间架构 + 道具系统 + 账户注册 + 排行榜战绩 + 重生无敌 + 地图主题
f583ce3 baseline: 贪吃蛇 3D 多人对战（部署版本）
```

---

## 12. 本地开发流程

1. 改 `serve.py` / `index.html`。
2. 本机静态检查：`node --check`、id 引用比对、括号配对（见 §10）。
3. 跑单测 + E2E —— **Windows 本机直接跑**（`.venv\Scripts\python.exe`，见 §10；批11 后为 67 单测 + 8 套 E2E 全绿）；Termux 本机仍上传 `snake-test` 跑。
4. 通过后按 §11.2 发布生产，跑 `verify_rooms.py`。
5. `git add -A && git commit`（中文 feat/fix/style 提交说明）。
6. 通知使用者**强刷页面**（Ctrl/Cmd+Shift+R）确认新前端。

---

## 13. 已知限制与技术债（交接重点）

| # | 问题 | 影响 | 建议 |
|---|---|---|---|
| 1 | ~~咬到"仅剩 2 格"的蛇不会淘汰对方~~ **✅ 已实现（P1）** | — | 已加规则：已是 `MIN_LEN` 再被咬 → 该蛇淘汰，`cause='bite'` |
| 2 | ~~快照每 50ms **全量**广播~~ | **批11 已解**：增量协议——静态字段（walls/portals/rocks/food/bonus/items）签名对比变化才下发，首帧/新订阅者全量（`full:1`）；players/proj/标量每帧恒在 | 无（实测稳态增量帧 −31% 字节） |
| 3 | 仓库远端只有服务器本身（与本机各一份），未托管 GitHub/Gitee | 两处同时损坏才会丢历史 | 加第三方远端，或定期 `git bundle create snake.bundle --all` 归档到别处 |
| 4 | ~~无 CI、无浏览器自动化~~ | **批9 已解**：`.github/workflows/ci.yml`（单测+7 E2E+Playwright）+ `e2e/smoke.spec.js` 3 冒烟 | 已多次 push（origin/server ssh 远端，批23 末 `5deb37c`），但**远端非 GitHub/Gitee → Actions 从未触发**；首跑需先第三方托管（见 #3，用户决策） |
| 5 | 密码强制 6 位数字 | 弱口令 | 定位为小游戏可接受；如需加强要同步改前端校验 |
| 6 | `DEPLOY.md` 未随功能更新 | 部署章节仍准确，功能描述偏旧 | 以本文档为准 |
| 7 | 用量数据积累时间短 | 趋势分析样本少（随时间自然积累） | ~~可加每小时在线曲线/房间热度~~ **批12 已实现** `usage_report.py`（仅余样本量问题） |
| 8 | 本机（Termux）在运营商 CGNAT 后 | 无法从外网回调本机 | 需要对外暴露本机时走隧道/内网穿透 |
| 9 | `three.min.js` 为本地 vendor r160 | **批10 已升级 r128→r160**（冒烟+同主题 A/B 截图验收，用户拍板采用 r160 新 sRGB 默认观感） | **批12 评估结论：维持 r160 不改**。升级 r161+ 需 ESM 改造（主脚本包 boot 函数 + module 脚本 `import * as THREE` 后触发，已核实 index.html 无 inline onclick、方案可行），但新版本特性（WebGPU 等）本项目全用不到，改造需 2130 行主脚本作用域包裹 + 全量视觉回归重做——收益低风险中。除非出现安全公告或需要新 API，否则不动 |
| 10 | **批33 元素反应的三处测试性约束**（非功能 bug） | ① 元素弹 `proj` 生命周期极短（fire 后 ~60–400ms 消失），粗采样采不到；② solo 无人房 1.3–3.5s 撞墙死 → `state='over'` 后 `fireEb` 永久拒绝且无重生；③ 生产注册限流 `REG_MAX=30/REG_WIN=300s` 会让"每轮新账号"的 E2E 撞限 | `e2e/reactions.spec.js` 已内置对策：`waitPlaying()` + `__stateDbg` 判 `playing&&alive` 后才按 e + `page.evaluate` 内 40ms 紧采 800ms + 固定账号 `p33elem`（ensureLogin 先 register「已存在」不计配额、失败兜底 login）。**新增元素弹类 E2E 请沿用同一范式** |
| 11 | `.github/workflows/ci.yml` 的 python E2E 仍是 7 套（未含 `test_reactions_p33.py`） | 本地门禁 `local_ci` 已含 9 套，CI 缺第 9 套；Actions 本身也因远端非 GitHub/Gitee 从未触发（见 #4） | 待 CI 真正可跑时补一行 `python test_reactions_p33.py`（本轮未改 CI，属未在契约范围） |

---

## 14. 常见坑（务必阅读）

1. **Termux 的 python3 没有 `websockets`** —— Termux 上一切测试都要 `ssh tencent` 用 `/home/ubuntu/snake-3d/.venv/bin/python` 跑。**Windows 本机例外**：仓库自带 `.venv`（`websockets==13.1`），单测与 8 套 E2E 可直接本地跑（见 §10）。
2. **`pkill -f <pattern>` 通过 SSH 执行会把自己杀掉**（pattern 匹配到 SSH 命令行本身，exit 255）。用 `fuser -k 28000/tcp`，或写成 `pkill -f 'serve[.]py'`。**Windows 本机没有 `fuser`**，本地停测试服用 `Get-NetTCPConnection -LocalPort 28000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }`。
3. **后台起测试服时 SSH 调用必然超时**，但进程其实已经起来了 —— 用 `ss -ltn | grep 28000` 确认，不要重复起（此坑仅限服务器端；Windows 本地后台起服无此问题）。
4. **Termux 没有 `/tmp`** —— 临时文件放 `$PREFIX/tmp/opencode`（即 `/data/data/com.termux/files/usr/tmp/opencode`）。Windows 本机用 `$env:TEMP`。
5. **`websockets` 不要升到 16.x** —— `process_request` API 已移除，HTTP 会全部 500（见 `DEPLOY.md`）。**已在 Windows 本机复现**：系统 Python 的 16.0 下 `GET /` 返回 500，`serve.py:1310 AttributeError: 'Request' object has no attribute 'keys'` —— 因此本机必须用仓库 `.venv`，别用系统解释器。
6. **改完前端必须强刷** —— 浏览器可能缓存旧 `index.html`；服务端本身是读盘的。
7. **改了 `serve.py` 必须 `systemctl restart snake-3d`**；只改 `index.html` 不用重启。
8. **`node --check` 不能用进程替换 `<(sed ...)`**（Node 读不了管道 fd）——先落地成临时文件再检查。
9. **房间回收的测试要区分"创建者在线/离线"** —— 否则会误判为 bug。

10. **`data/` 永不入库** —— 里面是账户 `store.json` 与用量 `usage.json`/`usage.log`，`.gitignore` 已加 `data/`。本地跑 E2E 会生成测试账号属正常，`git status` 不再显示 `?? data/`。

11. **Windows 上 `git archive` 输出 CRLF** —— 本机 `core.autocrlf=true`（仓库无 `.gitattributes`）会把 blob 的 LF 转成 CRLF，导致部署到 Linux 后 sha256 与 `git show <commit>:` 不一致（曾被误判为"生产被手改"，实为纯换行差异 2231 行）。**部署命令必须写 `git -c core.autocrlf=false archive ...`**（见 §11.2）。

---

## 15. 后续可选方向

- 需求方可能追加：~~蛇压到 2 格再被咬即淘汰~~（**P1 已实现**）；~~用量报表加小时曲线/房间热度~~（**批12 已实现**）。
- 体验优化：（小地图、观战左右键切换、移动端压缩已随批8 完成；房间内聊天、断线重连"回到原房间原蛇"已随批5 完成；720p 短屏 ⚔ 裁切已随批9 修复）
- 工程化：~~git 远端~~（已配 origin/server ssh 双别名并持续推送）、真实 CI 首跑（**BLOCKED**：需 GitHub/Gitee 托管，用户决策）、~~快照增量协议~~（批11 已落地）、配置外置（JSON/TOML，可选未拍板）。

---

## 附：一页速查

```bash
# ── 本机（Windows）开发 ──
.venv\Scripts\python.exe test_game.py                      # 单测 183 项（批33 含 21 项）
$env:PORT='28000'; .venv\Scripts\python.exe serve.py        # 起本地测试服；另开终端跑 test_ws*.py
node --check <抽出的js文件>                                 # 前端静态检查（Node 24 已装）
git status && git push server --all                        # 同步到服务器裸仓库

# ── 生产（下列命令本机已逐条实测可用） ──
# 看状态
ssh tencent "systemctl status snake-3d --no-pager | head -5"
# 看日志
ssh tencent "journalctl -u snake-3d -n 50 --no-pager"
# 跑测试（服务器生产 venv）
ssh tencent "cd /home/ubuntu/snake-3d && .venv/bin/python test_game.py"
# 用量报表
ssh tencent "cd /home/ubuntu/snake-3d && .venv/bin/python usage_report.py 7"
# 登录/注册/令牌失败的具体原因（密码错误/用户不存在/已存在等）自批20 起写入 usage.log，
# 报表「登录失败」节自动按原因细分；历史旧行无 err 字段则显示 kind:fail 兜底
# 发布（scp 的 test_*.py 通配符已实测可展开）
scp serve.py index.html test_*.py tencent:/home/ubuntu/snake-3d/ && ssh tencent "sudo systemctl restart snake-3d"
# 同步仓库到服务器裸仓库
git push server --all
# 服务器上查看完整历史 / 拉一份
ssh tencent "git --git-dir=/home/ubuntu/snake-3d.git log --oneline dev | head"
ssh tencent "git clone /home/ubuntu/snake-3d.git /home/ubuntu/repo"
# 回滚
ssh tencent "cd /home/ubuntu/snake-3d && cp serve.py.bak-<ts> serve.py && sudo systemctl restart snake-3d"

# ⚠️ 下面这行是 Termux 本机专属，Windows 本机不适用（地址不同、且无 CGNAT 问题）：
# 本机地址：回环 127.0.0.1 ｜ 蜂窝 10.2.90.55 ｜ VPN 192.168.193.2 ｜ 公网出口 14.31.16.44（CGNAT，不可入站）
```
