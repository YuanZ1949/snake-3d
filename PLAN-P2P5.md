# 全量开发计划（backlog-sprint 候选池，23 项 → 11 批）

用户指令：原 11 项 + 新提 12 项「一次性都开发完，最后统一验收；歧义按推荐拍板」。
每批 TDD（先红后绿）+ 批后回归：test_game.py 全绿 + 4 套 E2E Exit 0 + 前端静态检查。
协议字段变更的批次排在 C1 之前；C4 依赖 C2 冒烟；C1 快照增量压轴。
不部署、不 push，统一验收通过后另行执行。

## 歧义拍板记录（推荐方案）
- 战场自定义（#12）取代原 P2 设计中的 team/timed/survival 独立模式 → 简化为
  `win_mode: last(死斗)/score(积分)` + `limit: 秒(0=无限)` + `respawn: bool(无限复活)`。
  respawn 且 limit=0 时强制 limit=120（否则局永不结束）。限时到 → 一律按当前比分取最高者胜。
- #1 碰墙偏转项：新道具 deflect；仅**边界墙**偏转（垂直开阔方向折返），场内岩石照死、咬到 <2 照样淘汰。
- #7 护盾：任何地形碰撞（边界/岩石/自身身体）都偏转不死（比 deflect 道具更强）；被咬免疫维持现状。
- #2 传送门数量 = clamp(size/16, 1, 4) 对；出口朝向取出口处最开阔方向（不贴最近墙）。
- #6 资源有效期 = base × clamp((cols*rows)/(24*24), 1, 4)。
- #5 单人模式 = 建房 `bots` 参数 + 首页「单人练习」快捷入口；多人房间列表默认展开。
- #11 空房保留 24h 再删；「保存」按钮 → 房间写入 persist 标记（重启后重建，常驻不回收）。
- #9 边缘提示按实际资源类型显示对应图标（不再全是苹果）。
- #3 渲染插值：逻辑仍按格移动，客户端按 tick 进度在 prev→next 格间线性插值。
- #4 新增白天主题（bright/day 类，天空浅色），主题池照旧随机。
- C3 口令：6-20 位、字母+数字混合、弱口令黑名单（前后端同步校验）。
- C4：查当前 three.min.js 版本→升级到最新 r16x 兼容写法，渲染回归靠 C2 冒烟。
- C2：Playwright 冒烟（加载/入局/snap/canvas 无报错）+ GitHub Actions workflow。
- C1：walls/portals/rocks/food/bonus/items 改 dirty 才下发，players/proj 每帧；客户端字段缺失沿用旧值。

## 批次表

| # | 批 | 覆盖项 | 状态 | 批后验证 |
|---|---|---|---|---|
| 1 | 战场自定义 | A3 + 新#12 | ✅ | 单测 31/31 先红后绿；静态检查 ALL PASSED；4 E2E Exit 0；create 解析端到端 OK；起服 / 200 |
| 2 | 大招+偏转+护盾 | A6 + 新#1 + 新#7 | ✅ | 单测 40/40 先红后绿；静态检查 ALL PASSED；4 E2E Exit 0；ult 冒烟 OK |
| 3 | 传送门+资源有效期 | 新#2 + 新#6 | ✅ | 单测 44/44 先红后绿；静态检查 ALL PASSED；4 E2E Exit 0（40×40 房 3 对传送门） |
| 4 | AI蛇+单人模式 | A4 + 新#5 | ✅ | 单测 51/51 先红后绿；静态检查 ALL PASSED；4+1 E2E Exit 0（BOTS E2E：info/快照/AI 自主移动） |
| 5 | 重连+聊天 | B2 + B3 | ✅ | 单测 61/61 先红后绿（含挂起蛇冻结）；静态检查 ALL PASSED (65ids/div32/css141)；6 E2E Exit 0（RECONNECT+CHAT：resumed 同 id/漂移1.0格/聊天送达+限速） |
| 6 | 弱口令+房间保留/保存 | C3 + 新#11 | ✅ | 单测 66/66 先红后绿；静态检查 ALL PASSED (70ids/div33/css145)；7 E2E Exit 0（PASS+PERSIST 全 9 步；verify_rooms 证实断开后 r1 保留） |
| 7 | 客户端视觉 | 新#3 丝滑移动 + 新#4 白天主题 + 新#9 边缘图标 + 新#10 面板风格 | ✅ | 单测 67/67 先红后绿（day 主题池）；静态检查 ALL PASSED (70ids/div33)；7 E2E Exit 0（顺带实证 default 房随机到 day 主题）；浏览器截图 BLOCKED（桌面浏览器未连接，视觉项以静态+单测+E2E 佐证） |
| 8 | 小地图+观战切换+移动端 | B1 + 新#8 + B4 | ✅ | 纯前端批（无服务端改动）：单测 67/67 全绿维持；静态检查 ALL PASSED (68ids/div33/css156/js528)；7 E2E Exit 0；起服 / 200 |
| 9 | CI/Playwright | C2 | ✅ | Playwright 3/3 passed（7.3s，首页/单人入局/观战；BASE=8123 外部起服）；单测 67/67 全绿；静态 ALL PASSED (71ids/dup0/div33/css159/js528)；7 套 E2E 全 Exit 0；YAML 校验 15 steps。附带修复 720p 底部 ⚔ 裁切 |
| 10 | three.min.js 升级 | C4 | ⬜ | |
| 11 | 快照增量协议 | C1（压轴） | ⬜ | |

## 批次日志
（每批回写：验证证据、暴露的新工作、顺序调整）

### 批1 战场自定义（A3 + 新#12）✅
- **serve.py**：`Room()` 新参 `win_mode('last'/'score') / limit(0..3600) / respawn(bool)`；limit==0 兜底 score→300、respawn→120。`check_win` 四级：限时到→比分最高胜（并列平局）；respawn→不按淘汰结算；score→全员死亡才按比分；默认死斗。`RESPAWN_MS=3000`、`LIMIT_MAX=3600`；死亡置位处记 `died_at`，`step_wrapper` 到点 `spawn_player` 并发 `ev('respawn')`；`new_round` 重置 `round_started`。`snapshot` 加 winMode/limit/respawn/remain，`info` 加前三个，`create` 消息解析透传。
- **index.html**：HUD `timeChip` 倒计时；建房面板 3 控件（#cWin/#cLimit/#cRespawn）；`roomCfg`/`roomMeta()` 显示积分赛/无限复活/限时；`fmtDur`；死亡提示按 respawn 分支；applyEvent `case 'respawn'`。
- **test_game.py**：+7 用例（battle_mode_config / time_limit×2 / score_mode / last_mode / respawn×2），先红（TypeError: unexpected keyword 'win_mode'）后绿，31/31。
- **验证**：静态检查 ALL STATIC CHECKS PASSED（JS OK / 59 id refs / div 31-31 / css 130-130）；test_ws / test_ws2 / verify_rooms / test_p1 全 Exit 0；HTTP / 与 three.min.js 200；create 端到端（8090）respawn→('last',120,True)、score→('score',300,False)、非法值→('last',0,False)。
- **暴露的新工作**：无；**顺序调整**：无。

### 批2 大招+偏转+护盾（A6 + 新#1 + 新#7）✅
- **A6 拍板（原 backlog 无细节，按推荐实现）**：蓄力大招——吃果 +10 / 星星 +15 / 咬杀 +30 封顶 100；`ult` 消息释放 8 方向环形弹幕（对角归一化、spd 1.5、命中截断不变），冷却 `ULT_COOL=3000`；死亡/重生清零；客户端 HUD 蓄力条 + 键 K + 点击按钮。
- **serve.py**：`ITEM_TYPES` + `deflect`；新常量 `ULT_MAX/ULT_FRUIT/ULT_STAR/ULT_KILL/ULT_COOL`；`make_player`/`spawn_player` 增 `ult`；`_deflect_dir()`（垂直两方向取空间最大可走格，界内/非阻挡/非传送门/非己身）；step 第 4 节分级——shield 全地形折返、deflect 仅边界墙折返、折返时清转向队列并重算 tent、无路可走照死（cause 按 wall/rock/self 原序）；`try_ult()`；snapshot players 加 `ult`；消息 `ult`。
- **index.html**：`ITEMS.deflect`（↩️ #74c0fc）+ `.eff.deflect` CSS；HUD `ultBtn`（蓄力 %、满 100 脉冲 `ultPulse`、点按释放）；键 `K`；`fireUlt()`（客户端预校验 100）；eff 显示列表 + deflect；applyEvent `case 'ult'`（爆裂+floater+beep）。
- **test_game.py**：+10 用例（deflect×2、shield 折返×3、ult 充能/击杀/蓄力门槛/弹幕冷却/重生清零×5）。先红（deflect 撞墙仍死）后绿，**40/40**。
- **test_p1.py**：P1 期望 `ITEM_TYPES` 6→7 同步（批2 预期变更，非删测）。
- **验证**：静态检查 ALL PASSED（61 ids / div 31 / css 135）；test_ws / test_ws2 / verify_rooms / test_p1 全 Exit 0；HTTP /、three.min.js、leaderboard 全 200；`ult` 未蓄满消息冒烟被静默忽略、服务端快照正常（ULT SMOKE OK）。
- **暴露的新工作**：无；**顺序调整**：无。

### 批3 传送门+资源有效期（新#2 + 新#6）✅
- **拍板细节**：传送门对数按**列数就近取整**（`cols/16+0.5` 夹 1..4），故 24×24 起成 2 对（原需求"按地图大小适当增加"落地口径）；资源有效期倍率 `clamp((cols*rows)/576, 1, 4)`。
- **serve.py**：`portal_pairs()`；`portals` 改扁平 `[a,b,a2,b2,...]` 存储、`portal_map()` 两两配对互逆；`build_terrain()` 循环生成 npairs 对（两口不同、曼哈顿>6、去重不与障碍重叠）；step 传送后在出口处取 `_open_ahead` 最大方向设 `p['dir']`（不改转向队列）；新 `life_mult()/item_life()/bonus_life()`，`step_wrapper` 过期判断改用放大值。
- **index.html**：无需改动（syncPortals 按 i%2 交替配色天然多对兼容；`ITEM_LIFE` 常量无引用）。
- **test_game.py**：+4 用例（传送门对数随地图 / 32×32 多对互逆 / 出口朝开阔方向 / 资源有效期随地图），先红（24×24 仅 1 对）后绿，**44/44**。
- **验证**：静态检查 ALL PASSED（61 ids / div 31 / css 135）；4 E2E Exit 0（test_ws + test_ws2 / verify_rooms + test_p1 两串），verify_rooms 创建 40×40 房快照 `portals` 6 格 = 3 对，符合预期。
- **暴露的新工作**：无；**顺序调整**：无。

### 批4 AI蛇+单人模式（A4 + 新#5）✅
- **A4 拍板（原 backlog 无细节，按推荐实现）**：AI 蛇 = 服务端驱动的普通玩家条目（`bot: true`、负数 pid 与真人不冲突、名字 `AI-N`）；**决策时机**：step 中移动到期且转向队列为空时 `_bot_think()` 一次；**打分**（优先级键）：`是否绝路(0/1) → 离目标(星星>水果)曼哈顿距离 → -前方开阔格数`，候选不走回头路、须界内可走；无目标时以开阔空间为准。AI 视为**永远 ready**（maybe_start_round 特判），只等真人 ready 开局；常驻 round_ids 参与胜负计数（joined 含 AI）。`bots` 建房参数夹 0–7（`BOTS_MAX`），非法回退 0；`info()`/`create`/快照 players 均带 bot 信息。
- **单人模式（#5）**：主页「🐍 单人练习」按钮 → create `{size:24, bots:3}` → `created` 后自动 start() 入局（`soloPending` 标志，断线重连时 onopen 补建房）；建房面板新增「AI蛇」下拉（0/1/2/3/5/7）。房间列表默认即展开（原实现无折叠，#5 的"直接展开"天然满足），房间 meta 显示 `🤖AI×N`。
- **关键防泄漏**：`drop_player` 里最后一个真人离开 → 清掉全部 AI（否则 AI 占位导致空房永不回收，`players` 非空让 gc 跳过）；断线 finally → leave_room → drop_player 链路复用同一清理。
- **serve.py**：常量 `BOTS_MAX=7`、`DIRS4`；`make_player(..., bot=False)`（`sess` 可为 None）；`Room.__init__(..., bots=0)` + `add_bots()`；`_bot_think()`；step 第 0 节 bot 决策 hook；`maybe_start_round` AI 视为 ready；`drop_player` 清 AI；`info()` 加 `bots`；snapshot players 加 `bot`；create 解析 `bots`。
- **index.html**：#cBots 下拉 + createRoom 发送；btnSolo 按钮 + soloCreate() + soloPending 流程；roomMeta `🤖AI×N`；blur 列表加 btnSolo。
- **test_game.py**：+7 用例（配置夹取/创建即生成/追食物转向/避墙不死/单人击杀 AI 获胜/AI ready 开局/最后真人离开清 AI），先红（TypeError: unexpected keyword 'bots'）后绿，**51/51**。新增 **test_bots_p4.py** E2E（连 28000：create bots=3 → info.bots=3 且 players=3 → 快照 3 bot+1 人、负 id/AI- 名/存活 → 3 秒内 AI 蛇头位移）。
- **验证**：静态检查 ALL PASSED（**63** ids / div 31 / css 135）；test_ws / test_ws2 / verify_rooms / test_p1 / **test_bots_p4** 全 Exit 0（BOTS E2E OK）。
- **暴露的新工作**：新增 test_bots_p4.py 为第 5 套常驻 E2E（计划外新增测试文件，属加非改）；**顺序调整**：无。

### 批5 重连+聊天（B2 + B3）✅
- **B2 拍板**：`RESUME_MS=10s` 宽限。断线 finally → `leave_room(hard=False)`：**仅当房内还有其他真人玩家**（非 bot、非已挂起）→ 原蛇 `off_at=now` 挂起、`session=None`；否则照旧 `drop_player` 立即清（此修正因 verify_rooms 断言「creator 断开后房间立即回收」失败而加，TDD 先红后绿）。挂起蛇在 `step` 的 `due` 过滤中排除（**原地冻结**——否则宽限期内无人控制必然撞死，恢复失去意义；E2E 曾断言 cells 完全相等失败，诊断为采样时点在断线前+逐段求和度量过严，改为「长度不变 + 每段平均漂移≤2 格」）。`step_wrapper` 扫 `off_at` 超 10s → drop（含清 AI）。重连：`join` 先 `leave_room` 再 `room.resumable(user)`——有账户精确匹配挂起者，匿名仅当恰一个无账户挂起者；命中 `room.resume()` → `room-ok` 带 `resumed:true` 原 id，身体/分数全保留不重生；`maybe_start_round` 挂起者视为 ready；snapshot players 加 `off`（客户端暂未消费，灰化渲染砍为建议项）。客户端既有自动重连链路（onDisconnect→2s→join）自动走恢复路径。
- **B3 拍板**：`CHAT_COOL=1000ms`、`CHAT_MAX=80`；`chat_throttle(src,now)` + `Room.chat(name,text)`（截断去空白，空不发）→ `ev('chat',name,text)` 走快照 ev 通道；`chat` 消息在「需已在房间中」校验**之前**处理（观战者可发），限速超限静默丢弃；发件人=房内玩家名，否则账户名/'观众'。
- **index.html**：chatLog（左下消息流，7s 淡出、上限 30 条、textContent 防注入）+ chatIn 输入框（`/` 或点击进入，Enter 发送、Esc 关闭，输入态早退方向键——顺带修主页输入框误触发 setDir）；onDisconnect 清消息流；room-ok resumed 提示「已恢复原蛇」。
- **serve.py**：`step` due 过滤加 `not p.get('off_at')`（挂起冻结）；`leave_room` hard 分支；`RESUME_MS`；step_wrapper 挂起超时清理；`resumable/resume`；chat 常量+模块函数+`Room.chat`+消息处理；`Session.chat_at`。
- **test_game.py**：+10 用例（聊天发送与截断/限速、挂起宽限内存活、超时移除、最后真人离开清AI、resumable 匹配规则、resume 保留状态、单人房断线立即清、多人房挂起、**挂起蛇冻结不动**），先红后绿 **61/61**。新增 **test_reconnect_p5.py** 第 6 套 E2E（双真人房断线→恢复同 id/漂移 1.0 格、聊天首条送达+1s 内第二条被限速）。
- **验证**：静态检查 ALL PASSED（**65** ids / div 32 / css 141）；test_ws / test_ws2 / test_reconnect_p5 / verify_rooms / test_p1 / test_bots_p4 全 **Exit 0**（6/6）。
- **暴露的新工作**：off 灰化渲染（砍为建议项）；**顺序调整**：无（E2E 期间两次踩 background 120s 杀服 + 端口 10048 残留，处置=先清理端口再起双服在 120s 窗口跑完）。

### 批6 弱口令+房间保留/保存（C3 + 新#11）✅
- **C3 拍板**：`valid_room_pass(p)` = 6-20 位、`isalnum` 且非纯数字非纯字母（必须混合）、`WEAK_PASSES` 黑名单（32 个常见弱口令，lower 比较）——**前后端同步**（前端仅输入 maxlength，服务端为准）。create 给了 `pass` 但非法 → `{'t':'error'}` 直接拒绝创建（**不静默回退**，口令静默失效是安全坑）。口令房 `join`/`watch` 校验放在 `leave_room` **之前**（避免口令错把自己踢出当前房）；断线自动重连也带记忆口令（恢复路径同样校验，语义统一）。`info` 只带 `hasPass` 不泄露口令。
- **新#11 拍板**：`ROOM_KEEP_SECS=86400`——自定义房间创建 24h 内 gc 不回收（之后仍按原条件：没人+没观战+创建者不在线）；`persist` 消息（仅 `owner==sess.sid` 可标）→ `r.persist=True` 写盘 `data/persist_rooms.json` → **常驻不回收 + `load_persist_rooms()` 启动重建**（`main()` 中 `init_rooms()` 后调用；单测不走 main 不受污染）。字段容错反序列化（size/rock/portal/winMode/limit/respawn/bots/pass 全部防御）。
- **serve.py**：常量 PASS_MIN/MAX、ROOM_KEEP_SECS、PERSIST_FILE、WEAK_PASSES；`valid_room_pass()`；`Room(..., passw=None)` + `self.persist`；`info()` 加 hasPass/persist；create 解析 pass；join/watch 校验；`persist` 消息；`gc_empty_rooms` 加 persist 常驻 + 24h 保留；`persist_rooms_dump/save/load`。
- **index.html**：建房面板 `#cPass` 输入框；`roomPasss{}` 内存口令表 + `askPassIfNeeded()`（start/spectate 前 prompt 一次）；doJoin/watch×2 带 `pass`；`pendingPass` 让创建者免重输；`myCreated` Set → 卡片「⭐ 保存」span（stopPropagation）→ `send persist`；roomMeta 加 🔒口令/⭐常驻；`.saveBtn` CSS；**新 `error` 消息通道**：`showToast()` 浮层 + 口令错清记忆 + state==='joining' 时退回主页（否则卡"入局中…"）；`#toast` DOM+CSS。
- **test_game.py**：+5（口令校验/口令不泄露/24h保留/persist不回收/save-load 往返 tmp 文件），先红（AttributeError valid_room_pass）后绿 **66/66**（中途修一处自相矛盾断言：abc123 既 True 又黑名单 False → 改 Game2024/room77x）。
- **E2E**：新 **test_pass_p6.py** 第 7 套（9 步：弱口令拒/黑名单拒/合法建房 hasPass/无口令 join 拒/错口令拒/对口令进/watch 拒/persist 非创建者拒/创建者成 persist=true；首跑踩 `broadcast rooms 先于 created 到达被 recv吞` → 改收集双消息后过）；**verify_rooms.py 同步**（计划内需求变化）：`rid not in ids` 立即回收断言 → `rid in ids` 24h 保留断言 + info 字段加 hasPass/persist。
- **验证**：静态 ALL PASSED（**70** ids / div 33 / css 145）；7 套 E2E 全 **Exit 0**；E2E 残留 `data/persist_rooms.json` 已清理（避免污染后续批次）。
- **暴露的新工作**：无；**顺序调整**：无。


### 批7 客户端视觉（新#3 + 新#4 + 新#9 + 新#10）✅
- **#3 丝滑移动拍板**：逻辑仍按格（服务端零改动）；渲染在 prev→next 格间按 tick 进度线性插值。实体位移时记 `moveAt/moveDt`（观测间隔自适应，夹 60–400ms），`syncBody` 新收 `opts.from/opts.phase`，插值目标 = `lerp(prev, next, phase)` 再走原脊柱平滑；头部大跳变（>6 格：传送门/出生）不插值直接贴位。演示蛇按 `(now-lastTick)/180` 同理；掉帧兜底 `lastTick=now` 处同步 `lastCells` 防回退。
- **#4 白天主题拍板**：服务端 `THEMES` + `day`、`THEME_CFG['day'] = {rock 0.8, portal True, walls 0, accent 0x4dabf7}`（随机池含 day）；客户端 `THEMES.day` 浅色天空 0x9ecff2 + 亮色棋盘格；`THEME_LABEL`/建房下拉加「白天」。
- **#9 边缘图标拍板**：`FRUIT_EMOJI` 按水果颜色映射（红苹果/樱桃/草莓/葡萄/柑橘），`updateEdgeHints` 每帧同步 foodEdge 文本，缺省回落 🍎；星星 ⭐ 不变。
- **#10 面板配色拍板**：建房主题下拉各 `<option>` 文字着该主题 `wall` 原始配色（`THEMES` 定义后立即批量设置），与主页场景一致。
- **serve.py**：L82 THEMES + 'day'；THEME_CFG + day 条目。
- **index.html**：THEME_LABEL/cTheme/THEMES.day/选项着色块；FRUIT_EMOJI + updateEdgeHints；makeEnt 加 moveAt/moveDt；applyPlayers 位移记录+跳变保护；syncBody 插值；syncEnt/syncSnake 传 from/phase；720ms 兜底同步 lastCells。
- **test_game.py**：+1（test_day_theme_in_pool：池含 day、THEME_CFG 齐备、建房/地形/随机不炸），先红（AssertionError: THEMES 无 day）后绿 **67/67**。
- **验证**：静态 ALL STATIC CHECKS PASSED (70ids/div33/css516)；停服清理后起双服，7 套 E2E 全 **Exit 0**（verify_rooms 实测 default 房随机到 theme=day）；E2E 残留 persist_rooms.json 已清理；HTTP / 200。
- **暴露的新工作**：桌面浏览器未连接 → 截图视觉验收 BLOCKED（已记入 HANDOVER 主题节），批9 Playwright 落地后可补自动化截图。**顺序调整**：无。

### 批8 小地图+观战切换+移动端（B1 + 新#8 + B4）✅
- **纯前端批**（serve.py 零改动）：单测 67/67 维持全绿；静态 ALL STATIC CHECKS PASSED (68ids/div33/css156/js528)；7 套 E2E 全 Exit 0；起服 / 200；E2E 残留 persist_rooms.json 已清理、双服已停。
- **B1 小地图**：`#miniMap` canvas 150×150（@media 760px→104）固定右上，joined||spectating 才显示，每帧 updateMinimap 绘制：墙块/岩石/传送门（i%2 紫蓝）/水果实际色/星星金/道具类型色/玩家（自己绿大、他人红、尸体不画）/观战目标白圈；syncWalls/syncPortals 新增 wallCells/portalCells 几何缓存。
- **新#8 观战切换**：全局 `spectTarget`（null=跟随领先者）；keydown 观战时 ←/→/A/D → spectSwitch(±1) 循环（spectList=存活蛇按分数降序，与相机同序），toast「观战：名（i/N）」；触屏观战左右滑同效；相机优先 spectTarget、失效回退领先者；spectate/joinIn/goHome 重置。
- **B4 移动端**：`@media (max-width:760px)` 压缩 h1/HUD chip/开始页 sub/聊天宽度/小地图尺寸、开始页 overflow-y:auto；转向已有触屏滑动+dpad pointer 覆盖，无需新增。
- 浏览器截图仍 BLOCKED（批9 Playwright 落地后补视觉验收）。

### 批9 CI/Playwright（C2）✅ + 720p 裁切修复
- **拍板落地**：`e2e/smoke.spec.js` 3 用例（首页渲染 / 单人 guest 登录入局 / 观战切换），**外部起服模式**（无 webServer 自动化）：本地 `PORT=8123` 起服 → `BASE=http://127.0.0.1:8123 npx playwright test`。识别走带空格正则 `"t":\s*"snap"`，房间列表判据 `.roomItem`。截图落 `test-results/smoke-home.png` / `smoke-ingame.png`，供 observer 视觉验收。
- **CI**：`.github/workflows/ci.yml`（push dev/main + PR + 手动），ubuntu：pip `websockets<16` → 单测 → 起 28000/8090 双服 → 7 套 python E2E（两轮）→ 停服清 persist → setup-node 20 + `npm ci` + `playwright install --with-deps chromium` → 起 8123 → `npx playwright test` → upload-artifact test-results/playwright-report（失败另传 /tmp/serve_*.log）。YAML safe_load 校验 15 steps（step name 含冒号需引号，已修）。
- **附带修复（720p 底部 ⚔ 裁切）**：根因 `顶部102+画布(720×.68=490)+gap12+dpad120+底padding44=768>720`。修复①`resize()` 加 `vFactor = innerHeight<=760 ? .60 : .68`（画布 432px）；②`@media (max-height:720px)` 内 `body{padding-bottom:16px}`、`.dpad{grid-template-rows:repeat(3,46px);gap:6px}`、`body.follow .dpad{grid-template-rows:46px 46px}`。实测 1280×720：scrollH=720 零溢出、dpadBottom=644、atkVisible=true。
- **验证**：Playwright 3/3 passed (7.3s)；单测 67/67 ALL PASSED；静态 ALL STATIC CHECKS PASSED (ids=71 dup=0 div=33/33 css=159/159 js=528/528)；7 套 E2E ALL PASSED；observer 视觉验收通过（day 主题浅色+金框为预期非缺陷）。
- **暴露的新工作**：无；**顺序调整**：无。
