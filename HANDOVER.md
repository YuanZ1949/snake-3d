# 贪吃蛇 3D —— 项目交接文档

> 最后更新：2026-10-14 ｜ 分支 `dev` ｜ 文档描述的功能基线：`0f0245a`（当前 HEAD 用 `git log` 查）
> 生产地址：**http://193.112.172.83:8090/**

---

## 1. 项目概览

多人在线 3D 贪吃蛇对战游戏。单文件服务端（HTTP + WebSocket 同端口），单文件前端（CSS/HTML/JS 全在 `index.html`），Three.js 渲染。

**当前已实现的功能**

| 类别 | 内容 |
|---|---|
| 对战玩法 | 多人同房间实时对战、咬蛇截断并入（非致死）、子弹射击缩短对方、岩石/墙块/传送门、星星奖励、道具（护盾/加速/穿墙）、重生无敌、回合胜负判定、**AI 蛇（单人练习/多人加 AI）** |
| 房间系统 | 3 个默认房间 + 自定义房间（尺寸/主题/岩石/传送门/AI 数量 任意组合）、房间卡片列表（人数、属性、🤖AI 标识）、空房自动回收、观战、**主页「单人练习」快捷开局（24×24 + 3 AI 自动进局）** |
| 账户 | 昵称与账号合并（一个输入框）、6 位数字密码、token 恢复登录、可游客游玩 |
| 排行榜/战绩 | 全服排行榜、个人战绩（胜场/击杀/死亡/场次/最高分/吃果数） |
| 界面 | 统一 `.chip` 按钮风格、开始页布局、房间列表、创建面板、排行榜屏、暂停屏、结束屏、**三处 🏠 返回主页**、移动端触屏方向盘 |
| 视听 | 环境光+半球光+平行光、粒子/飘字、音效与背景音乐、5 款皮肤、5 种地图主题（常规/熔岩/冰原/星空/白天） |
| 后台 | 服务器使用情况记录（`usage.log`/`usage.json` + 报表脚本），**不体现在页面上** |

---

## 2. 交付物清单

```
snake-3d/
├── serve.py          1368 行  服务端：HTTP + WS + 游戏逻辑 + 账户 + 房间 + 用量记录
├── index.html       2654 行  前端：CSS(~370) + HTML(~150) + JS(~2130) 全在一个文件
├── three.min.js      603 KB  Three.js 本地 vendor（未升级，避免 API 变动）
├── test_game.py      24 项单元测试（纯逻辑，不起服务）
├── test_ws.py        E2E：入局/移动/攻击/排行榜/房间
├── test_ws2.py       E2E：HTTP 三接口 / 注册登录 / 入局快照 / 观战 / 排行榜 / 建房
├── test_ws3.py       E2E：房间列表 + 自定义地图 + 空房回收
├── test_ws4.py       E2E：96 超大地图 + 速度即时生效 + leave 回主页
├── verify_rooms.py   生产验证（端口 8090，创建房间→进房→断线回收）
├── verify_prod.py    生产 WS 冒烟（进房 a、快照字段、食物唯一 id）
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
| Node.js | 仅用于 `node --check` 静态语法检查 | 不参与运行时 |
| 浏览器 | 现代浏览器（需 WebGL） | 无自动化测试/截图手段 |

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

**关键状态机**：`state ∈ idle | joining | playing | over | win`，配合 `joined / spectating / wantPlay / demoPaused` 四个布尔量决定界面与演示世界。

---

## 5. 通信协议

**全部为 JSON 文本帧，字段向后兼容——老客户端仍可正常游玩。**

### 5.1 客户端 → 服务端

| `t` | 字段 | 说明 |
|---|---|---|
| `register` | `user, pass` | 注册（`user` 即账号，**也是昵称来源**；`pass` 为 6 位数字） |
| `login` | `user, pass` | 登录，成功回 `token` |
| `authtoken` | `token` | 断线重连恢复登录态（不需要带 user） |
| `logout` | — | 退出登录 |
| `leaderboard` | — | 请求全服排行榜 |
| `rooms` | — | 主动请求房间列表 |
| `create` | `name, size, theme, rock, portal, winMode, limit, respawn, bots, pass` | 创建自定义房间；非法值回退主题默认。**批1 战场自定义**：`winMode` 只收 `last`(死斗)/`score`(积分)，否则 `last`；`limit` 秒数夹 0–3600（0=不限时；limit=0 时 score 兜底 300s、respawn 兜底 120s）；`respawn` 仅 `true` 生效（无限复活，3s 后原地重生）。**批4 AI**：`bots` 数量夹 0–7（非法回退 0），建房即生成 AI 蛇（负 pid、名字 AI-N、视为永远 ready）。**批6 口令（C3）**：`pass` 可选，给了就必须合法（6-20 位字母+数字混合、非弱口令黑名单，`valid_room_pass()` 前后端同步），非法直接 `error` 拒绝创建（不静默回退） |
| `watch` | `room, pass` | 进入旁观（会先 `leave_room`）；口令房必须带对口令（批6） |
| `join` | `room, name, skin, pass` | 入局。**新客户端不再发 `size`**（尺寸只在创建时决定）；老客户端仍带 `size`，空房时生效；口令房必须带对口令（批6，断线自动重连也带记忆的口令） |
| `leave` | — | **新增**：返回主页，把自己移出房间（旧客户端不发，行为不变） |
| `ready` | — | 回合结束后的下一局确认 |
| `dir` | `x, y` | 转向（服务端做反向与队列校验） |
| `atk` | — | 发射子弹（冷却 `ATK_COOL=800ms`） |
| `ult` | — | **批2 新增**：释放大招（蓄力满 `ULT_MAX=100`、冷却 `ULT_COOL=3s`，否则服务端静默忽略）；8 方向环形弹幕 |
| `speed` | `ms` | 速度档，服务端夹到 80–300，**立即生效** |
| `skin` | `i` | 换皮肤（0–4） |
| `persist` | `room` | **批6 新增（新#11）**：把房间标记为常驻（仅创建者可标，成功后广播刷新列表；写盘 `data/persist_rooms.json`，重启重建、永不回收） |
| `chat` | `text` | **批5 新增**：房间聊天（≤80 字，空白不发，1s 限速超限静默丢弃）；观战者也可发，走快照 `ev` 通道 |
| `respawn` | — | 死亡后重生 |

### 5.2 服务端 → 客户端

| `t` | 关键字段 | 说明 |
|---|---|---|
| `welcome` | `rooms[]` | 连接建立，带完整房间列表 |
| `rooms` | `list[]` | 房间列表（加入/离开/创建时主动广播） |
| `created` | `room, name` | 创建成功 |
| `room-ok` | `room, spectate, user, id` | 进房成功，`id` 即 `myId`；**批5**：命中断线恢复时带 `resumed:true`（原 id/身体/分数保留，不重新出生） |
| `left` | `room` | 离开房间回执 |
| `error` | `err` | **批6 新增**：服务端拒绝（口令错误/非法口令/非创建者保存等）；客户端浮层提示，入局中被拒则退回主页 |
| `auth` | `ok, user, token, stats, err` | 认证结果（`auth_payload`）；`authtoken` 失效时客户端自动清理本地态 |
| `leaderboard` | `list[]` | `[{name,best,wins,kills,games}]` |
| `snap` | 见下 | **50ms 一次的全量快照** |

**`snap` 字段**：`t, room, theme, cols, rows, walls, portals, rocks, items, food{id,x,y,score,color}, bonus, players[](含 bot), proj[], ev[], round, win, over, winMode, limit, respawn, remain`
> 批1 新增：`winMode('last'/'score')`、`limit`(秒，0=不限)、`respawn`(bool)、`remain`(限时剩余秒，int，无限制时 0)。

**`players[]` 字段**：`id, name, skin, cells[], dir, score, alive, tick, base_tick, inv, eff{shield,speed,ghost,magnet,double,rage,deflect}, user, cause, by, combo, ult, bot, off`（`off`=断线挂起中，批5）
> `ult` 为大招蓄力（0–100），满 100 可按 `ult` 消息/点 HUD 按钮释放。

**房间信息（`rooms` 列表项）**：`id, name, cols, rows, theme, themeFixed, rock, portal, players, alive, watchers, round, over, winMode, limit, respawn, bots, hasPass, persist`
> `players` 是**已连接人数**（含旁观），`alive` 是存活蛇数。

**事件 `snap.ev[]`**（由 `applyEvent()` 处理）：`join / eat / die / kill / fire / hit / bite / clash / star / rock / expire / round / win / respawn / ult`
> 顶层消息由 `onMsg` 的 switch 处理，`snap` 在 switch 之外单独分支；事件只随快照下发，不单独成帧。
> `bite{eater,victim,cut,score}`、`hit{x,y,by,victim,cut,score}` 是截断类事件。

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
| `BONUS_LIFE` | 8000 | 星星存活 ms（+50 分）；实际 = 基础 × `life_mult()`（批3，随地图放大） |
| `WIN_SCORE` | 200 | 达到该分数触发胜利判定 |
| `SPAWN_INV` | 2500 | 重生无敌 ms |
| `ITEM_LIFE` | 12000 | 道具在地上存活 ms；实际 = 基础 × `life_mult()`（批3，随地图放大） |
| `EFFECT_MS` | 6000 | 道具效果持续 ms |
| `MIN_LEN` | 2 | 被截断后蛇保留的最少格数 |
| `BULLET_CUT` | 1 | 子弹命中截断的格数（按需求"不要太大"） |
| `BITE_SCORE_PER_CELL` | 8 | 咬下对方每格得分 |
| `COMBO_MS` | 3000 | 连击窗口：两次吃果间隔超此值连击重置 |
| `COMBO_TIERS` | 15/10/5 → x2.5/x2/x1.5 | 连击倍率档位（1-4 连 x1） |
| `MAP_MIN / MAP_MAX` | 12 / **96** | 地图尺寸上下限 |
| `RESPAWN_MS` | 3000 | 无限复活模式下死亡到重生的等待 ms |
| `LIMIT_MAX` | 3600 | 限时模式上限（秒） |
| `ULT_MAX` | 100 | 大招蓄力上限（攒满才可释放） |
| `ULT_FRUIT / ULT_STAR / ULT_KILL` | 10 / 15 / 30 | 大招充能：吃水果 / 吃星星 / 咬蛇淘汰 |
| `ULT_COOL` | 3000 | 大招释放冷却 ms |
| `FRUITS` | 10/15/20/15/15 | 5 种水果分值 |
| `USAGE_MAX` | 8 MB | 用量日志轮转阈值 |

### 6.2 关键规则

- **咬蛇 = 截断并入；压到 2 格再被咬 → 淘汰**：接触点之后的对方身体被切走并接到自己身上；对方保留 `MIN_LEN=2` 格；**已是 2 格再被咬 → 整条淘汰**（`cause='bite'`，残躯归攻击者，事件 `bite` 带 `kill:true`）。
- **连击 Combo**：`COMBO_MS=3s` 窗口内连续吃果 `combo+1`，超时/死亡/新回合重置；只有**水果**计数（星星/道具/咬蛇不打断也不加）。倍率 `combo_mult()`：1-4→x1、5-9→x1.5、10-14→x2、15+→x2.5 封顶；`snap.players[]` 带 `combo`，`eat` 事件带 `combo/mult`。
- **道具 7 种**（`ITEM_TYPES`）：`shield 护盾 / speed 加速 / ghost 穿墙` + `magnet 磁铁`（食物/星星每 tick 朝自己拉 1 格、绕障碍、停在蛇头旁不落格）、`double 双倍`（一切得分 ×2，走 `score_gain()` 统一入口）、`rage 狂暴`（攻击 CD 减半 + 子弹速度 ×1.5，`proj[]` 带 `spd` 字段）、**`deflect 偏转`（批2：仅撞边界墙时折返不死；场内岩石照死、咬到 <2 照样淘汰）**。
- **护盾强化（批2）**：`shield` 除原被咬免疫外，**任何地形碰撞（边界墙/岩石墙块/自己身体）都折返不死**——折返方向取蛇头垂直两方向中空间最大的可走格（无路可走仍照死），折返时清空转向队列。
- **大招（批2，A6）**：`p.ult` 蓄力 0–100，吃水果 +10、吃星星 +15、咬蛇淘汰 +30（封顶 100）；满 100 发 `ult` 消息 → 从蛇头向 **8 方向**发射环形弹幕（对角线方向归一化、`spd=1.5`、命中仍只截断 `BULLET_CUT=1` 格），冷却 `ULT_COOL=3s`，死亡/重生清零。客户端 HUD 蓄力条（满时脉冲高亮），键 `K` 或点按钮释放。
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
- **AI 蛇（批4，A4）**：`create` 带 `bots`(0–7) 建房即生成；条目与普通玩家同结构但 `bot:true`、pid 为负数、名字 `AI-N`、`session=None`。**决策**：step 中该 AI 移动到期且转向队列空时 `_bot_think()`——候选不回头且界内可走，打分 `(是否绝路, 离目标距离, -前方开阔)`，目标优先级 星星 > 水果，无目标时以最开阔方向为准。AI **视为永远 ready**（只等真人 ready 触发新局）、常驻 `round_ids` 参与胜负计数、死亡/复活/新局逻辑与真人共用。**最后一个真人离开房间时 AI 全部清掉**（否则 AI 占位导致空房永不回收）。
- **单人练习（批4，新#5）**：主页「🐍 单人练习」→ 建房 `{size:24, bots:3}` → `created` 自动入局（断线重连 onopen 补建房）；建房面板「AI蛇」下拉 0/1/2/3/5/7；房间卡片 meta 显示 `🤖AI×N`。
- **断线恢复（批5，B2）**：断线时若房内**还有其他真人** → 原蛇置 `off_at` 挂起（原地冻结、不移动不参与转向）等待 `RESUME_MS=10s`；单人房/无其他真人则立即清房（保空房回收语义）。重连（同账号精确匹配；匿名仅当恰一个无账户挂起者）走原 `join` → `room-ok` 带 `resumed:true`，**原 id/身体/分数全保留不重新出生**；超 10s 未归 → drop（含清 AI）。客户端本有的自动重连（onDisconnect→2s→join）自动命中新路径。挂起者对 `maybe_start_round` 视为 ready。
- **房间聊天（批5，B3）**：`chat` 消息（≤80 字、空白不发、每连接 1s 限速超限静默丢弃）→ 快照 `ev` 通道广播 `{t:'chat',name,text}`；观战者可发（发件人=房内玩家名，否则账户名/'观众'）。客户端按 `/` 或点击输入框进入聊天（输入框早退方向键），左下角消息流 7s 淡出、上限 30 条、textContent 防注入，断线清空。
- **房间口令（批6，C3）**：建房可设口令 `pass`（6-20 位字母+数字混合、`WEAK_PASSES` 黑名单前后端同步校验），非法 `error` 拒绝创建；口令房 `join`/`watch` 必须带对口令（先校验再动状态，避免把自己踢出原房）。`info` 带 `hasPass`（口令本身不下发）。客户端：建房面板「口令」输入框（可选）、进房 `prompt` 要一次口令后内存记忆（页面生命周期免重输，含断线自动重连）、创建者免重输、口令错误清记忆并 toast 提示。
- **空房保留/保存（批6，新#11）**：自定义房间创建后 **24h 内不回收**（`ROOM_KEEP_SECS=86400`，之后仍按"没人+没观战+创建者不在线"才删）；创建者可在房间卡片点「⭐ 保存」→ `persist` 消息 → `persist=True` 写盘 `data/persist_rooms.json`，**常驻不回收 + 重启后重建**（`load_persist_rooms()` 于 `main()` 启动时调用）。`info` 带 `persist`，meta 显示「🔒口令」「⭐常驻」。
- **丝滑移动插值（批7，新#3）**：逻辑仍按格走（服务端不动）；客户端渲染在 `prev→next` 格间按 tick 进度**线性插值**——实体位移时记 `moveAt/moveDt`（按观测间隔自适应，夹 60–400ms），`syncBody` 按 `phase=(now-moveAt)/moveDt` 在两格间取插值目标再走脊柱平滑；头部大跳变（>6 格，传送门/跨图出生）不插值直接贴新位置。演示蛇同理按 `(now-lastTick)/180` 插值。
- **边缘提示图标（批7，新#9）**：屏外边缘提示不再一律 🍎——按水果实际颜色映射图标（红→🍎、樱桃红→🍒、粉→🍓、紫→🍇、橙→🍊，`FRUIT_EMOJI`），星星仍 ⭐；每帧 `updateEdgeHints` 同步。
- **白天主题 + 面板配色（批7，新#4/#10）**：主题池新增 `day`（见 §6.3）；客户端 `THEMES.day` 浅色天空 `0x9ecff2`、亮色棋盘格；建房面板主题下拉新增「白天」，且各主题选项文字着该主题原始配色（`wall` 色），与主页场景一致。桌面浏览器未连接时无法截图验收，视觉项以静态检查+单测+E2E 佐证。

### 6.3 主题（`THEME_CFG`）

| 主题 | 岩石倍率 | 传送门 | 固定墙块 |
|---|---|---|---|
| `default` | 1.0 | 有 | 0 |
| `lava` | 1.7 | 无 | 6 |
| `ice` | 0.5 | 无 | 0 |
| `space` | 0.6 | 有 | 4 |
| `day` | 0.8 | 有 | 0 |

房间未固定主题时**每局随机**（池含 5 种主题，批7 新增 `day` 白天：浅色天空、亮堂棋盘）；自定义房间的 `theme_fixed / rock_mult / portal_on` 覆盖主题默认值。传送门开启时按地图大小生成多对（见 §6.2 传送门扩容），快照 `portals` 为扁平坐标列表，客户端按索引两两配对、交替紫/蓝配色。

---

## 7. 房间系统

- **默认房间**：`a` 新手村 16×16、`b` 标准局 24×24、`c` 大神场 32×32 —— **永不回收**。
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
| `test_game.py` | 单元 ×67 | 幽灵穿墙/撞墙死亡/传送门/道具拾取/速度效果/护盾/咬蛇截断与**2格淘汰**与免疫/子弹截断/出生点/水果唯一 id/自定义房间/**apply_speed**/**free_cells 大地图**/usage 日志/**combo 链与超时重置**/**combo 档位倍率**/**双倍得分**/**磁铁吸附**/**狂暴 CD 与子弹加速** + 批1 ×7（战场自定义/限时/积分赛/死斗/复活×2）+ 批2 ×10（deflect/护盾折返/大招充能与释放）+ 批3 ×4（传送门对数随地图/多对互逆/出口朝开阔方向/资源有效期随地图）+ 批4 ×7（AI 配置/生成/追食转向/避墙/单人胜/AI ready/离房清 AI）+ 批5 ×10（聊天×2/挂起宽限与超时/挂起清AI/恢复匹配/状态保留/单人房立即清/多人房挂起/挂起蛇冻结）+ 批6 ×5（口令校验/口令不泄露/24h保留/persist不回收/持久化往返）+ 批7 ×1（白天主题进池/day 建房与地形） |
| `test_ws.py` | E2E | 连接、入局、移动、攻击、排行榜、房间列表、创建房间 |
| `test_ws2.py` | E2E | HTTP 三接口、注册登录（`user/pass` + token）、入局快照字段、第二连接观战、排行榜、创建房间 |
| `test_ws3.py` | E2E | 房间列表属性、自定义地图（40×熔岩/岩石/传送门）、非法参数回退、人数广播、空房回收 |
| `test_ws4.py` | E2E | 96×96 与 9999 夹紧、快照尺寸、速度 215/85 即时生效、`leave` 清房与回收、离开后可重新入局 |
| `test_p1.py` | 协议 | 连本地服：`snap.players[]` 带 `combo`、`proj[]` 带 `spd`、`ITEM_TYPES` 7 种（批2 同步：+deflect）（需先起 28000 测试服） |
| `test_bots_p4.py` | E2E | 批4 AI：create `bots=3` → 房间列表 `bots/players` 计数 → 快照 3 bot（负 id、AI- 名、存活有 cells）+ 1 人 → 3 秒内 AI 蛇头自主位移（连 28000） |
| `test_reconnect_p5.py` | E2E | 批5：双真人房断线 → 重连 `resumed:true` 同 id、身体长度不变且漂移≤2 格 → chat 首条随快照 ev 送达、1s 内第二条被限速（连 28000） |
| `test_pass_p6.py` | E2E | 批6：弱口令/黑名单口令建房被拒 → 合法口令建房 `hasPass` → 无口令/错口令 join 与 watch 被 `error` → 对口令进房 → persist 非创建者拒、创建者成且列表 `persist=true`（连 28000） |
| `verify_rooms.py` | 生产 | HTTP 200 + 创建/进房 + **批6 后：creator 断开后新房间 24h 内保留**（info 带 hasPass/persist） |
| `verify_prod.py` | 生产 | WS 冒烟：进房 `a`、快照字段、食物唯一 id、玩家 cells |

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
```

**前端静态检查清单**（无浏览器时的替代手段）：
1. `node --check` 抽出的 JS；
2. JS 里 `$('id')` 引用的 id 必须全部存在于 DOM（当前 52/52）；
3. `<div>` 开闭数量相等（当前 31/31）；
4. CSS 花括号配对（当前 579/579）。

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

### 11.2 发布流程（标准动作）

```bash
cd ~/snake-3d
TS=$(date +%Y%m%d-%H%M%S)
# 1) 远端备份
ssh tencent "cd /home/ubuntu/snake-3d && cp serve.py serve.py.bak-$TS && cp index.html index.html.bak-$TS"
# 2) 上传
scp serve.py index.html test_*.py tencent:/home/ubuntu/snake-3d/
# 3) 重启（只有 serve.py 需要；index.html 每请求读盘，可不重启但浏览器要强刷）
ssh tencent "sudo systemctl restart snake-3d"
# 4) 验证
ssh tencent "systemctl is-active snake-3d"
md5sum serve.py index.html          # 与 ssh tencent "md5sum ..." 比对
#   Windows PowerShell 的 PATH 里没有 md5sum，二选一：
#     C:\MyFile\Program\Git\usr\bin\md5sum.exe serve.py index.html
#     (Get-FileHash serve.py -Algorithm MD5).Hash.ToLower()
#   ⚠️ 本机 core.autocrlf=true 落盘是 CRLF，裸 md5 与服务器天然不等（差的全是行尾）。比内容先归一化：
#     python -c "import hashlib,io;print(hashlib.md5(io.open('serve.py','rb').read().replace(b'\r\n',b'\n')).hexdigest())"
curl -s -o /dev/null -w '%{http_code}\n' http://193.112.172.83:8090/
ssh tencent "cd /home/ubuntu/snake-3d && .venv/bin/python verify_rooms.py"
```

### 11.3 回滚

```bash
ssh tencent "cd /home/ubuntu/snake-3d && cp serve.py.bak-<时间戳> serve.py && cp index.html.bak-<时间戳> index.html && sudo systemctl restart snake-3d"
```

详细端口/1Panel 说明见 `DEPLOY.md`。

### 11.4 Git

- 分支 **`dev`**（全部开发提交），`main` 停在基线 `f583ce3`。
- **远端**：服务器裸仓库 **`tencent:/home/ubuntu/snake-3d.git`**（本地别名 `server`）。
  - **Termux 本机**：`dev`/`main` 已设上游跟踪，`git push` 不带参数即可同步。
  - **Windows 本机**：clone 得到的远端名叫 `origin`（`dev` 跟踪 `origin/dev`，`main` 只有 `origin/main`），已另补一个同址的 `server` 别名 —— 故 `git push server --all` 与 `git push` 都可用。
- 服务器上查看/克隆历史：`git --git-dir=/home/ubuntu/snake-3d.git log dev` 或 `git clone /home/ubuntu/snake-3d.git ~/repo`
- ⚠️ 生产目录 `/home/ubuntu/snake-3d/` **不是** git 仓库，它只是发布投放点（靠 `*.bak-*` 回滚），不要在里面执行 git 操作。
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
3. 跑单测 + E2E —— **Windows 本机直接跑**（`.venv\Scripts\python.exe`，见 §10；批7 后为 67 单测 + 7 套 E2E 全绿）；Termux 本机仍上传 `snake-test` 跑。
4. 通过后按 §11.2 发布生产，跑 `verify_rooms.py`。
5. `git add -A && git commit`（中文 feat/fix/style 提交说明）。
6. 通知使用者**强刷页面**（Ctrl/Cmd+Shift+R）确认新前端。

---

## 13. 已知限制与技术债（交接重点）

| # | 问题 | 影响 | 建议 |
|---|---|---|---|
| 1 | ~~咬到"仅剩 2 格"的蛇不会淘汰对方~~ **✅ 已实现（P1）** | — | 已加规则：已是 `MIN_LEN` 再被咬 → 该蛇淘汰，`cause='bite'` |
| 2 | 快照每 50ms **全量**广播（含 walls/portals/rocks/food/players） | 大地图 + 多人时带宽增长 | 静态地形改为进房时一次性下发，快照只发增量 |
| 3 | 仓库远端只有服务器本身（与本机各一份），未托管 GitHub/Gitee | 两处同时损坏才会丢历史 | 加第三方远端，或定期 `git bundle create snake.bundle --all` 归档到别处 |
| 4 | 无 CI、无浏览器自动化 | 前端只能靠静态检查 + 人工眼看 | 接入 Playwright 做冒烟 |
| 5 | 密码强制 6 位数字 | 弱口令 | 定位为小游戏可接受；如需加强要同步改前端校验 |
| 6 | `DEPLOY.md` 未随功能更新 | 部署章节仍准确，功能描述偏旧 | 以本文档为准 |
| 7 | 用量数据仅两天左右积累 | 趋势分析样本少 | 可加"每小时在线曲线/房间热度"（**已提过，未被要求**） |
| 8 | 本机（Termux）在运营商 CGNAT 后 | 无法从外网回调本机 | 需要对外暴露本机时走隧道/内网穿透 |
| 9 | `three.min.js` 为本地 vendor | 无安全更新 | 升级需回归渲染与光照 |

---

## 14. 常见坑（务必阅读）

1. **Termux 的 python3 没有 `websockets`** —— Termux 上一切测试都要 `ssh tencent` 用 `/home/ubuntu/snake-3d/.venv/bin/python` 跑。**Windows 本机例外**：仓库自带 `.venv`（`websockets==13.1`），单测与 7 套 E2E 可直接本地跑（见 §10）。
2. **`pkill -f <pattern>` 通过 SSH 执行会把自己杀掉**（pattern 匹配到 SSH 命令行本身，exit 255）。用 `fuser -k 28000/tcp`，或写成 `pkill -f 'serve[.]py'`。**Windows 本机没有 `fuser`**，本地停测试服用 `Get-NetTCPConnection -LocalPort 28000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }`。
3. **后台起测试服时 SSH 调用必然超时**，但进程其实已经起来了 —— 用 `ss -ltn | grep 28000` 确认，不要重复起（此坑仅限服务器端；Windows 本地后台起服无此问题）。
4. **Termux 没有 `/tmp`** —— 临时文件放 `$PREFIX/tmp/opencode`（即 `/data/data/com.termux/files/usr/tmp/opencode`）。Windows 本机用 `$env:TEMP`。
5. **`websockets` 不要升到 16.x** —— `process_request` API 已移除，HTTP 会全部 500（见 `DEPLOY.md`）。**已在 Windows 本机复现**：系统 Python 的 16.0 下 `GET /` 返回 500，`serve.py:1310 AttributeError: 'Request' object has no attribute 'keys'` —— 因此本机必须用仓库 `.venv`，别用系统解释器。
6. **改完前端必须强刷** —— 浏览器可能缓存旧 `index.html`；服务端本身是读盘的。
7. **改了 `serve.py` 必须 `systemctl restart snake-3d`**；只改 `index.html` 不用重启。
8. **`node --check` 不能用进程替换 `<(sed ...)`**（Node 读不了管道 fd）——先落地成临时文件再检查。
9. **房间回收的测试要区分"创建者在线/离线"** —— 否则会误判为 bug。

10. **`data/` 永不入库** —— 里面是账户 `store.json` 与用量 `usage.json`/`usage.log`，`.gitignore` 已加 `data/`。本地跑 E2E 会生成测试账号属正常，`git status` 不再显示 `?? data/`。

---

## 15. 后续可选方向

- 需求方可能追加：蛇压到 2 格再被咬即淘汰；用量报表加小时曲线/房间热度。
- 体验优化：小地图或雷达、移动端 UI 进一步压缩。（房间内聊天、断线重连"回到原房间原蛇"已随批5 完成）
- 工程化：git 远端 + CI、Playwright 冒烟、快照增量协议、配置外置（JSON/TOML）。

---

## 附：一页速查

```bash
# ── 本机（Windows）开发 ──
.venv\Scripts\python.exe test_game.py                      # 单测 18 项
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
