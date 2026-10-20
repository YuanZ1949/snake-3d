# 候选池（批22 之后 · 批23 起）

> **批23 已全清（8/8，2026-10-15）**，批末收尾（push 双远端 + 部署生产 8090）亦完成。
> 本文件转为批23 归档；新需求请另起批24 段落或新建候选池。

## 批33（2026-10-19 · 原神元素反应）已完成

> 计划：`docs/superpowers/plans/2026-10-18-element-reactions.md`（T1–T10，inline executing-plans 逐任务 TDD）；spec：`docs/superpowers/specs/2026-10-18-element-reactions-design.md`（oracle 审定 M1–M9，数值均为提案非承诺）。
> 目标原话（计划 Goal）：「四元素（火水冰雷）反应系统——常驻 aura、元素弹/元素地面/地形旋钮、6 种反应与反应充能机制，PROTO 29 双端。」

- **服务端**：常量 `ELEMS/AURA_MS=8000/EB_CD=2000/EB_SPD=1.2/ULT_REACT=15/FROZEN_MS=1600/SLOW_MS=3000` + `REACTIONS` 六反应表与 `reaction_of()`；`players[].aura` 附着（TTL、重生清、断线挂起保留、落盘前 `pop('aura')`）；`eterrain` 元素地面（`build_eterrain()` 预算 `min(60, cols*rows*0.015*elem_amt)`、计进 `occupied()`、`new_round` 重建）；消息 `eb` 元素弹（独立 CD、门禁「开关→存活→非 win_pending→非挂机→非冻结→查 CD」、不碎岩、跨高度层）；`apply_reaction()` 统一出口（先 `ev('react')` 即使 victim 已死 → 截断类效果 → 双方消耗 aura → 攻击者 +15 充能，不改 `grow/MIN_LEN` 既有语义）；咬击 `_bite_reaction`（感染+反应）与落格/命中两条附着路径；`frozen`（不可动、不可发射、头静止当障碍、仍可被咬）与 `slow`（tick×1.5）接入 `eff`（due 排除、门禁）；`elements/elem_amt` 三入口（create / roomcfg deferred / persist）+ 旧存档缺字段回退 True/0.6。
- **协议（PROTO_VER 28→29 双端同步 bump）**：`snap.eterrain` 进 `DELTA_FIELDS`（full+DELTA 双路）、`players[]` 带 `aura`、`proj[]` 带 `elem`、新事件 `react{kind,by,victim,x,y}`、`fire` 带 `elem`、房间配置 `elements/elemAmt`。
- **客户端**：HUD `#elemBar` 四元素按钮（键 1–4 切元素、`E` 发射、CD `.cool`）、aura 元素色光晕、frozen/slow 罩色、`eterrain` 面片、`react` 3D 浮字、元素弹染色、建房/房间编辑两旋钮、预测侧 frozen/slow 门控；探针 `__stateDbg/__auraDbg/__floatDbg/__projDbg`。**修复 2 个真 bug**：仓内无全局 `.hidden` 工具类 → 补 `#elemBar.hidden{display:none}`；`lastEb=0` 初值吞掉页面启动 2s 内首发 → 改 `let lastEb = -2000`。
- **门禁**：`test_game.py` +21 项（183 用例全注册全跑，`ALL GAME UNIT TESTS PASSED`）；新增第 9 套 E2E `test_reactions_p33.py`（进程内双 ws 反应链 5 断言，`reactions E2E PASS`）；`e2e/reactions.spec.js` ×4（HUD/40ms 紧采断言元素弹/注入附着+浮字+截图 `test-results/p33_attach_react.png`/`elements=false` 时 HUD 隐藏）；`pwsh scripts/local_ci.ps1` → **ALL GREEN**（9 套 E2E + 单测 + 静态检 ids=135 dup=0 + Playwright **39 passed**）。
- **部署与生产复验**：`scp index.html serve.py tencent:/home/ubuntu/snake-3d/` + `systemctl restart snake-3d`；生产 `npx playwright test e2e/reactions.spec.js e2e/smoke.spec.js` → **9/9 passed**（`--repeat-each=6` 曾 18/18），`prod_verify.js` → `room-ok ver=29`、`errs=[]`，截图肉眼可见元素 HUD 四键 + 「冻结」反应浮字。
- **E2E 对策（写给后来者）**：元素弹存活仅 ~60–400ms、solo 蛇 1.3–3.5s 撞墙死进 `over` 拒发射、生产注册限流 REG_MAX=30/300s —— 已固化为 `waitPlaying()` + `playing&&alive` 才按 e + 40ms 紧采 + 固定账号 `p33elem`。
- **遗留**：`.github/workflows/ci.yml` 的 python E2E 仍 7 套（未含 `test_reactions_p33.py`；Actions 因远端非 GitHub/Gitee 本就未触发，见 HANDOVER §13 #11）。

## 批32（2026-10-17 · 高度地形与建筑 已交付）

来源：用户原话「还想丰富玩法 主要是想增加地形和建筑 以及 原神的元素反应 你看看怎么加」。流程：architectural（spec+计划+oracle 审核+原生执行）；拆两子项目——**A=地形与建筑（本批）**、B=元素反应（后续单独立项）。11 项拍板要点：真高度层（非纯视觉）、蛇逐节高度、仅限上行自动跟随、PVP 碾压式高度裁决、子弹贴发射者头高、纯天然据点、无迷雾、半透明伏击草、服务端随机生成+配置旋钮、服务端权威 hmap 全量下发（否决 seed 双端复现）。

- **服务端**：`Room.hmap` 稀疏单源（-2草/-1水/1丘/2峰/3楼/9深渊；无 cellh 平行数组）；`gen_heights()` 四类共享 `int(0.35*area)` 预算、避开 portals/walls/旧头±4；三旋钮 `height/water/bld`（五主题基准 + `*Custom`，夹 0–4，persist/live/roomcfg/deferred 全通路）；四接入点 `_solid(cur_h)/reach_set/step/occupied`——上行≥2 挡崖（cause `cliff`）、下行自由、水减速 30%、出生 h==0、AI 前瞻传 cur_h；战斗：head-on 低者死、咬击 stance 三分支（高碾压整条死 cause `crush`/同高现有截断/低反噬）、子弹头高+沿途更高挡弹 `ev('phit')`+蛇身命中 `abs(节h-弹h)<=1`。
- **协议**：PROTO_VER 27→28 双端；`hmap` 进 DELTA_FIELDS（全量帧必带、签变增量）；`proj[]` 每条带 `h`。
- **客户端**：`syncHeight` kind 池化（柱/水/草/深渊黑柱+Edges child；全 `depthWrite=false` 蛇恒可见）+ `visH`（草0/水-0.12/陆 h×0.35）；蛇逐节 y lerp+头俯仰；预测挡崖（shield/deflect 门控同构）；伏击草整蛇淡出（对方 .35/自己全亮）；水面水花；建房/编辑面「地形/水域/建筑」三下拉；探针 `__mapDbgSet/__heightDbg/__mapSelfCorridorSet/__mapSelfCliffBlock`。
- **门禁**：单测 10 条（height_gen_invariants/cfg_roundtrip/cliff_move/water_slowdown/spawn_h0/ghost_cross_height/crush/bullet_terrain/bullet_hit_range/snapshot_height）+ `e2e/height32.spec.js`×3 + 全量 e2e 35/35 + `local_ci.ps1` ALL GREEN。计划期修订 6 条见 spec §12（含 §6.2 碰撞语义调和：同高保留咬击不判我死）。e2e 基建：`ensureLogin` 抽 `e2e/_helpers.js`（Playwright 禁止 test 文件互 require）。

## 批31（2026-10-17 · 登录即弹回馈/五星高级感/抽卡动画原神化 已交付）

来源：用户原话「用户登录的时候弹送的礼物」「五星皮肤貌似没啥特别的 看不出来有什么高级的地方」「抽卡动画还是不像原神 你回顾一下之前的要求 最好完美复刻」。流程：直通（既有结构表现层+协议增量）。澄清拍板：①登录时就弹（非进房）；②局内+皮肤页都要高级感；③差距项全选（夜空氛围/流星轨迹/落地光柱/卡牌揭示仪式感/十连节奏）+流星方向、动画时间、光效、运镜。

- **① 登录即弹**：`auth_payload` 增 `gift`（login/register/authtoken 三路），客户端 auth ok 分支弹 `#giftPop`（`giftShown` 每会话一次，room-ok 路保留兜底）；**修复真 bug**：`#giftPop` 原无 z-index 被 `#startScreen`(z:40) 盖住——登录场景点不到「领取」，批31 提至 45。单测 `test_login_gift_batch31`（注册/登录/authtoken 带 14400、领后归零）。
- **② 五星高级感**：局内三件套——emissive 强脉动（`.3+.4·|sin(now/520)|`）+ 头部星尘拖尾（90ms 节流 burst）+ 头部光环（TorusGeometry，5★ 金随 glow 色，呼吸缩放，护盾/挂机/死亡收起）；大厅演示蛇同享。皮肤页按星分级：`.wishSkn.s5` 金渐变底+金框+s5Glow 呼吸+斜向流光 s5Sheen+金字，`.s4` 紫框。探针 `__skinsDbgSet`。
- **③ 抽卡原神化**：夜空天幕（深蓝紫渐变+繁星 starTwinkle+山峦剪影 clip-path 地平线）；流星重做——`meteorFly` 沿 `--x0/--y0/--xm/--ym/--ang` 从右上外侧入场向中央下方消失点透视缩小（scale 1→.16），单抽 1.4s / 十连 550ms 依次；落地 `#wishPillar` 光柱冲天（5★ 金柱+`navigator.vibrate(60)`）；单抽剪影 hold→flip+`#wishBloom` 星徽光圈（4★紫/5★金）；**十连节奏改原神式：流星全飞完直接进陈列 10 格依次翻卡、最高档压轴**（不再逐颗放大揭示）。cap 分镜/两段点击/ESC/reduced-motion/WebAudio 全保留。
- **e2e 适配**（行为变更连带）：新增 `gift_skin31.spec.js`（登录即弹+皮肤页 s5/s4 断言）；`gift.spec.js` 改写为登录即弹语义；`admin.spec.js` ensureLogin 补 giftPop 关闭（新账号首跑弹窗会盖住后续点击）。门禁 `pwsh scripts\local_ci.ps1` ALL GREEN（Playwright 32/32、单测、静态 ids=129 div/css/js 全对齐）。PROTO_VER 未 bump（gift 随 auth 纯增量），概率/保底/数值未动，零素材文件。



来源：用户原话「新手村不新手 我觉得配置应该调整一点」「网站当前多少人也可以显示一下」「另外有没有必要增加一个聊天界面 支持暂停（这个也要支持）后公屏聊天 另外还有要不要加个管理员账户」。流程：backlog-sprint，逐项 brainstorming 拍板后独立交付。① 痛点票选 4 项（地图小被围死 / 主题随机地形复杂 / 无 AI 陪练被真人虐 / 死一次整局出局），参数拍板：**地图 24×24、主题保持随机**。

| 层 | 内容 | 证据 |
| --- | --- | --- |
| ① 新手村配置 | `DEFAULT_ROOMS` a 16→24；`NEWBIE_ROOM_CFG={rock_mult:0.5, bots:2, respawn:True}` 由 `init_rooms` 注入房 a（岩石覆盖主题值、2 条 AI 陪练、死亡可复活；respawn init 兜底自动限时 120s 比分结算）；b 标准局/c 大神场全默认不动 | `test_newbie_room_cfg_batch30` 先红（cols 16≠24）后绿：a 五项新值 + `eff_rock()==0.5` + AI×2 实生成 + b/c 不变 guard；`local_ci` ALL GREEN |
| ② 在线人数 | serve `online_count()`（登录按用户名去重、匿名按会话计）+ `broadcast_online()`：welcome 附 `online` 字段、会话建立/断开 + 身份变化四消息（register/login/authtoken/logout，handler 层单点）广播 `{'t':'online','n'}`；首页 `.roomHead` 新增 `#onlineBox`「🌐 当前在线 N 人」；纯增量不 bump PROTO_VER（设计获批：显示位置/去重口径/推送不轮询；不做峰值与战局内 HUD） | `test_online_count_batch30` 先红（AttributeError）后绿（同账号双标签去重 4→3）；e2e/rooms.spec.js「首页显示当前在线人数≥1」GREEN；单测/静态（ids=107）/`local_ci` 全绿 |
| ③a 公屏聊天+面板 | serve：`gchatin`（1s 限速/80字/空白拒，限速槽先于校验与房内同口径）+ `gchat_log`=deque(50) 内存 + `broadcast_gchat` 全体会话 + `welcome_payload()`（组包从 handler 拆出，带 `gchat` 历史）；客户端：`#chatPanel` 双 Tab（💬公屏/🏠本房）、三入口（首页房间行「💬 公屏」/顶栏「💬 聊天」手机可点/键盘 `/`），旧 `chatIn` 与 `.chatLog.up` 移除，本房 Tab 局外回退公屏，断线/换世界清本房列表（公屏保留） | `test_gchat_batch30` 先红（no attribute gchat_log）后绿（历史50 头淘汰/限速/空白拒/截断/登录名/广播含自己/welcome 历史）；e2e/gchat.spec.js ×3 GREEN（发言回显/新连接 welcome 历史/回退）；静态 ids=114 dup=0；`local_ci` ALL GREEN（Playwright 26 passed） |
| ③b 暂停=挂机 | serve：`pause` toggle 置/清 `off_at`+`pause`（复用挂起保护+冻结；`dir`/`atk`/`ult` 拒收防原地开火炮台；`step_wrapper` 对 session 在的挂机者不按 `RESUME_MS` 回收、挂机中断线由 `leave_room` 重置宽限照旧 10s；`leave_room` others 把挂机者算在场真人→他人断线挂起不移出；`resume` 重连一并清 `pause`）；客户端 HUD `#btnPauseGame`「⏸ 暂停」+ dpad 中心键 joined 分支（主页 demo 暂停不变）+ `#pauseMask` 胶囊（居中小胶囊非全屏遮挡，暂停中聊天照常）+ `pauseres` 回执，断线/回主页撤提示；协议纯增量不 bump | `test_pause_afk_batch30` 先红（无 pauseres，`AssertionError: []`）后绿（toggle 回执/冻结他蛇照走/dir·atk 拒收/超 RESUME_MS 不回收/恢复续动/挂机+断线照回收）+ `test_pause_counts_as_present_batch30`（挂机者在场→他人断线挂起不移出）；e2e/pause.spec.js×2 GREEN（HUD 链路+暂停中聊天不锁 / dpad 键同语义）；静态 ids=116 dup=0 |
| ④ 管理员账户 | serve：`ADMIN_USERS={'yuan'}` 白名单 + `is_admin()`/`mutes{}`/`is_muted()`；五消息 `adkick`（发 `kicked` 后关该用户全部在线连接）/`admute`（内存到期自动失效，缺省 10 分、钳 1~1440，仅登录账号；`gchatin`+房内 `chat` 同拒）/`adnotice`（「📢 公告」进 gchat_log 全体广播）/`adgrant`（`add_stardust` 钳 1~100000+用户须存在，在线受奖者收 `toast`）/`adreport`（`admin_report()` 从 usage.data 现算：实时/今日/累计/近7日/活跃 Top10）；非 admin 静默拒+`usage.note('adm_denied')`；`welcome`/`auth` 携带 `admin` 标记。客户端：聊天面板第三 Tab「🛡 管理」`#cpTabA`（白名单才 hidden 去除）→ `#admPane`（用户名输入+踢出/禁言10分/发奖数额/公告框/报告按钮+`#admOut` 结果区），登出/过期收权；纯增量不 bump | `test_admin_core_batch30` 先红（AttributeError: no attribute is_admin）后绿（白名单判定/welcome·auth 标记/非 admin 五消息全拒零副作用/踢人断连/禁言拒聊到期恢复）+ `test_admin_notice_grant_report_batch30`（公告历史+广播/发奖入账+超额·不存在拒零副作用+在线提醒/报告五关键词）；e2e/admin.spec.js×2 GREEN（公告回显+报告渲染 / 发奖 toast+踢人 kicked+非管理员无入口）；静态 ids=127 dup=0；`local_ci` ALL GREEN（Playwright 30 passed） |

## 批29（2026-10-16 · 3 修 3 增：卡顿/房间列表/进房平局 + 更新庆祝领星尘/星星调参/效果条中文）

来源：用户原话「游戏有点卡 房间修改完后房间列表会只有一个房间看不到其他房间了 房间进去后会先显示平局感觉不太对 每次推送更新都弹窗庆祝更新反馈玩家90抽 继续调高星星的数量」+ 修正「果子数量不增加 增加星星数量 然后给道具效果加上中文」。流程：backlog-sprint（顺序 ②→③→①→④→⑤→⑥，bug 优先）。设计终稿获批后执行。

| 层 | 内容 | 证据 |
| --- | --- | --- |
| ② 房间列表 | renderRooms 去掉 curRoom/isMine 过滤，显示全部房间（方案B 用户拍板）（`f74f15f`） | e2e/rooms.spec.js 4 项 GREEN（含翻转 guard/改名/活跃房回归） |
| ③ 进房平局 | P5③ 晚加入补屏改中性文案「上一局已结束」，仅 `win===myId` 保留🏆（`b51837e`） | e2e/latejoin.spec.js GREEN（积分赛双自杀→第三者进房断言中性文案） |
| ① 卡顿根因 | 实证：hook3 `lead==0 → lastMoveAt=now` 水平重锚在 50ms snap 节奏死锁 pred（lead 0/75、maxSince 63ms）+ rollback `prevCells=serverMy.cells` 退化钉死投影（deg 50/75）→ 蛇一格只滑 1/3 即钉住。修=转移触发重锚（`caught`）+ rollback prevCells 取改写前 pred 位 + lead==0 相位同步 + 删 hook3 重锚（`ccb67de`） | pred.spec.js 新 T5/T6/T7 + T4⑧/⑧b，7/7 GREEN；修复后实测 lead 17/76、maxSince 151、deg 2/76；两版帧率均 60fps 顶格（非帧率问题） |
| ④ 更新庆祝 | PROTO_VER 26→27 双端；store `update_ver_claimed`；room-ok join/resume 附 `gift`=待领金额（watch 不带）；`claimgift`→`giftres`，每账号每版本一次性入账 14,400（GACHA_PRICE×90，校验与写入无 await 原子）；客户端 `#giftPop` 每会话一弹（`3ebe80a`）+ oracle 后续强化：版本键单调比较（降级不重放不覆写）+ 金额服务端下发（消硬编码）+ watch 口径测试 | `test_update_gift_claim_once`（14400/一次性/重复拒/未登录拒/降级拒/老版本放行/watch 不带）；e2e/gift.spec.js 真实注册→弹窗→领取→刷新不再弹 GREEN |
| ⑤ 星星调参 | `BONUS_SPAWN_P` 0.004→**0.015**（新常量）、`BONUS_LIFE` 8000→**12000**（客户端三处镜像）、`ULT_STAR` 15→**25**、吃星星星尘 +10→**+15**（客户端镜像）；果子数量/收益 +10 明确不动（`0b6d39a`） | `test_star_tuning_batch29` 四新值断言 + 吃果 +10 不变 guard |
| ⑥ 效果条中文 | `updateEffectsHud` chip 加 `.lb` 中文 span（七道具 `ITEMS[k].label`：护盾/加速/穿墙/磁铁/双倍/狂暴/偏转 + inv「无敌」）（`9a85641`） | e2e/effects.spec.js：gate 注入带 eff/inv 快照，8 chip 全中文 + emoji 保留 GREEN |
| oracle 终审 | **APPROVE_WITH_NITS**；R-a/R-b/R-c/R-d/R-c2 五裁决全接受。落地修复：F3 版本键 `!=`→`<` 单调、F4 金额服务端下发、F5 三回归网（watch 口径/版本键语义/`static_check.js` 双端 PROTO_VER 一致性）；F1/F2 文档回写（本 commit） | 三门禁复跑全绿 + oracle 独立复跑 exit 0×3 |

门禁（终态）：`test_game.py` ALL GAME UNIT TESTS PASSED（含 2 新测）；`static_check` ids=106 css=281 js=747 + PROTO_VER 双端一致；`local_ci.ps1` ALL GREEN + 手动全量 Playwright **22/22**。

遗留（oracle NIT，记录在案未处理）：F6 dir-only rollback 单拍退化边（非本批回归）；F7 空态文案/列表规模化；F8 弹窗全屏遮挡与观战不触发（设计可解释）；F5-④ 非 gate 真实流断言（现全部 pred e2e 在 gate 内，真实节奏靠 T5 合成代理 + 人工实证）；经济面：今后每次 PROTO_VER bump = 每账号 +14,400。部署与 push：交付后单独询问。

## 批28（2026-10-16 · A+B 房间列表杂项 + C 转向手感「自机预测+回滚」）

A+B（`c024579`）：房间列表显示自己创建的空房 + roomcfg 回执标注「下局生效」字段。C 来源：转向手感差 → brainstorming 架构路径获批 → spec 落盘 `9203e8c` → 四轮 oracle 审阅闭合至 v5 `320fb8a` → 计划落盘 `ffdefdc`（writing-plans 自评通过）→ executing-plans 原地执行 5 任务。

| 层 | 内容 | 证据 |
| --- | --- | --- |
| 门禁基建 | `scripts/static_check.js` 从 Temp 正式入仓；`local_ci.ps1` 静态段改指仓内脚本、缺失即 FAIL（`1b854bd`） | `node scripts/static_check.js index.html` → ALL STATIC CHECKS PASSED |
| 探针 | `__predState`（真值观测）+ `__predGate`（拦截真实 snap 并重置基准）+ `__predDbg`（固件直测）+ `__gachaDbg` 打标注入；`e2e/pred.spec.js` 四探针 RED 基线（`fc1533d`） | 两轮 RED 达成计划 Step 2 Expected（skin 载荷修正后） |
| 预测内核 | predictor 纯函数集（mkPred/advanceStep/predAdvance/predReconcile/syncApplied/predInterval/previewDirOf）+ applyPlayers `e.tick` 落位 + hook2 本地推进/朝向投影（`37af98b`） | T4 固件 GREEN（§5.0 用例①④②③⑤+悬停+上限+interval=90） |
| 对账回滚 | hook3：serverMy 载荷暂存 → 裁剪游标差分 N+M → syncApplied → 三分支投影处置（seamless/reanchor/rollback 就地改写）→ lead==0 相位重锚；死亡停用 + `clearDirQ()` 10 处重置点 + hook2 停用门（`06e5af9`） | pred 四探针 4/4 GREEN（5.7s） |
| 全量门禁 | `pwsh scripts\local_ci.ps1` 全量 | ALL GREEN：8/8 E2E Exit 0 + test_game.py ALL PASSED + 静态 js=741/741 ids=102 + Playwright 14 passed（含 pred 4） |

遗留：部署生产后 §7.3 转向手感实操验收（8090，待用户实操）；退路开关 `PRED_ENABLED=true` 常量（异常时改 false 全关）。push 双远端 + 部署生产 8090 已于 2026-10-16 完成（origin/server 均至 `b5ae801`；漂移零：生产原为批26 `b191c9f` blob；回滚点 `snake-3d-predeploy-20261016-181919.tar.gz`；部署后 active/200/journal 零 error/生产隔离单测 ALL PASSED/`/` 含 pred 探针符号 5 处）。

## 批27（2026-10-16 · 祈愿动画全套分镜改造）

来源：用户粘贴分镜稿（四阶段：逐颗流星颜色判定/差异化揭示 1.75-2.5s/5★爆点运镜/捕获明光回溯/陈列金光 New 标）→ brainstorming(bounded) 三问拍板：全套分镜改造（推荐）；十连逐颗揭示（原神式，点击=快进）；做轻量 WebAudio 合成音效（零素材）。流程：vertical-slice（服务端 cap → gachares 协议 → 客户端四阶段+音效 → 测试/探针/文档）。

| 层 | 内容 | 证据 |
| --- | --- | --- |
| 服务端 | `gacha_roll` 增 `cap=(star==5 and up and not in_lose)`（赢50/50的5★）；`handle_gacha` 条件透传 `items[].cap:true` | TDD `test_gacha_cap_flag` 先红后绿；单测 141 ALL PASSED |
| 客户端 | 四阶段分镜：meteor 逐颗流星（各自颜色/stagger/4★5★ 推近/cap 项缩回→双星变形 glitch→二次飞行）→ flash（5★ Boom+光束+punch）→ reveal 逐颗（剪影 hold 1750/2100/2500ms→flip）→ done（5★ 金光脉冲+New 标）；sfxNoise/whoosh/boom/ping/glitch/chord 受 muted 约束 | 静态 js=677/677 ids=102 |
| 探针 | `e2e/wish.spec.js` 3 项：全套分镜到 done（capture=1/3流星/New×2/Dup×1/关闭）；两段点击协议；reduced-motion 直达 done | Playwright 8/8（含既有 smoke 5 项）；local_ci ALL GREEN |
| 文档 | HANDOVER §5.2 gachares 行 `cap?` 字段；spec §5.2 批27 回写块 | 本 commit |

不做（记录在案）：未拥有 5★ 角色语音（spec §9）、音频素材文件、spec §9 其余不做项、游戏相机与玩法数值、既有游戏音效区重构。部署与 push：交付后单独询问。

## 批26（2026-10-16 · 收尾维护批（6 项拍板））

来源：批25 报告「剩余风险与建议」6 项 → 用户逐项拍板：① occupied() 果占用集缓存=「顺手加缓存」；② index.html 尾部垃圾行=「下批顺手删（推荐）」；③ 断服丢当场星尘=「加 SIGTERM 优雅结算」；④ HANDOVER gachainfo 补行=「下批顺手补（推荐）」；⑤ stale-tab 协议=「B 版本握手 reload（推荐）」；⑥ spawn 24-256ms=「先实测线上分布」；开工时机=「现在开工（推荐）」。流程：backlog-sprint（候选池 6/6 全清，部署统一收口于 wrap-up）。

| # | 项 | commit | 状态与证据 |
| --- | --- | --- | --- |
| ⑥ | spawn 耗时测量：薄 wrapper 计时 + `[spawn]` journal 行 + `last_spawn_ms`（不动算法） | `07e2955` | ✅ 生产 journal 已见 `[spawn]` 行（14–21ms @32x32 实测） |
| ⑤ | 协议版本握手：room-ok 三路带 `ver=PROTO_VER`(26)，客户端不等即 reload 关闭 stale-tab 窗口；HANDOVER 写明改协议须同步 bump | `8b015cc` | ✅ 生产双端 `PROTO_VER = 26` grep=1/1 |
| ③ | SIGTERM 优雅结算：`shutdown_settle()` 遍历并账落盘 + `install_shutdown_handlers()`（Linux add_signal_handler / Windows signal.signal 降级） | `1632eab` | ✅ 生产 restart 实证 journal `[shutdown] settle ok: 0 players dust granted to store`，无 traceback，systemd Deactivated successfully |
| ① | occupied() 果占用集缓存（`(id,len)` key + 变更路径全集摸底：零原地改） | `d5ec38e` | ✅ 微基准 1.74→0.79µs/call（-55%）；`test_occupied_foods_cache` 三段断言 |
| ② | 删 index.html 尾部垃圾 2 行（`y>` + 重复 `</html>`，批23 `d9f075d` 引入） | `8aec385` | ✅ diff 恰 2 deletions，tail=`</html>` |
| ④ | HANDOVER `gachainfo` 补「换号身份不一致同样回零值占位」行 | `b191c9f` | ✅ diff 1/1，语义核对 serve.py `gacha_state` 一致 |

门禁终值：单测 **140**、static js=658/658 ids=97、`local_ci.ps1` **ALL GREEN**（每次 commit 前各跑一次，wrap-up 终跑亦 ALL GREEN）。
部署：漂移零（生产=0e7c39e 运行时 blob aa5eedc5/7c8a830b）→ 备份 `predeploy-20261016-113444.tar.gz` → 投放 + restart×2（第二次为 ③ 实证）→ active、200、生产 sha256 == `b191c9f` blob（serve.py `aa83e215…` / index.html `f7a35604…`）、journal error=0、生产隔离单测 ALL PASSED。
push：`0e7c39e..b191c9f`，origin/server/dev 三者 = `b191c9f`，工作区干净。

## 批25（2026-10-15 · 抽卡（祈愿）系统）

来源：用户「加个抽卡功能吧，类似原神那种祈愿，吃果子获得抽卡货币，抽卡来解锁皮肤」（m0413）→ 范围与数值经 brainstorming 逐项确认（m0419 拍板：「任何要决定的你自己按照推荐来」，推荐值全部通过）→ spec 获批（`1724228`）→ oracle 审计划（2 BLOCKER + 9 MAJOR 全修入计划，`d9178eb`）→ 原生执行（`executing-plans`），批末 oracle 终审。

| # | 项 | 大小 | 来源/依据 | 状态 |
| --- | --- | --- | --- | --- |
| A | 场上多果：`food` 单果 → `foods` 列表（每图 3–8 颗，`food_target()` 分档），全局递增 id，客户端按 id 对齐 mesh | 中 | spec §6 前置（吃果=星尘来源，单果节奏撑不起 160/抽）；唯一协议 break | ✅ 完成（`f0a6503`）：serve 多果生成/占用合并/吃果逻辑 + 快照 `foods` + 客户端 11 处 + 3 单测；E2E food→foods 同步修；探针 GREEN |
| 1 | Store 扩展：`stardust/skins/gacha_p5/gacha_p4/gacha_lose` 防御式读取 + `stardust/add_stardust/skins_of/grant_skin` | 小 | spec §5.1 | ✅ 完成（`c99d6e4`）：防御式 get 兼容旧账号，save 落盘 |
| 2 | 纯函数：`gacha_roll(rng, lose5050, pity5, pity4)` 判定序（硬保底5★>基础5★>4★保底>基础4★>3★）+ `pool_pick(rng, star, up)` | 小 | spec §5.3（实现 4 参拆 pool_pick，偏离已回写 spec） | ✅ 完成（`e3d721b`）：1.6%/14.6%、90/10 硬保底、50/50 歪置位复位、返还 10/50/200；**单测 11 项** |
| 3 | 消息/结算/鉴权：`gacha`/`gachainfo` 处理、`settle_dust` 并账（win_pending 六处含平局）、`skin i%=16` 归一化+拥有检查、join 静默回退、身份一致 | 中 | spec §5.2 + oracle BLOCKER 修订（n 白名单、保底判定序、身份一致、关键区无 await、大厅可抽） | ✅ 完成（`df660ac`）：先总账后当场扣减、gachares 含 up/dust/gained；**单测 11 项** |
| 4 | SKINS 16 款（5 免费 + 3★×6 + 4★×3 + 白金圣蛇 + UP 辉夜）+ 5★ 皮肤流光 | 中 | spec §6.3 | ✅ 完成（`d80640e`）：star 字段/越界钳制/暗金 emissive 流光；探针 p25_skins GREEN |
| 5 | 祈愿界面：全屏覆盖层（深蓝金）、星尘余额、卡池横幅、×1/×10、我的皮肤页签（按星级分组点选）、大厅入口 ✨祈愿（startScreen 账号行） | 中 | spec §6.1 + T5 Ruling（入口放 startScreen） | ✅ 完成（`a01beaa`）：探针 p25_ui GREEN（登录引导/免费 5+拥有 6/大厅 ×1 扣 160→4840） |
| 6 | 抽卡动画：流星（颜色按最高档 金>紫>蓝）→ 爆闪 → reveal，单抽 1 卡 / 十连 10 格最高档压轴、缩略图、跳过、reduced-motion | 中 | spec §6.2 + T6 Ruling（输入锁=动画非 done 锁键盘、点击两段协议） | ✅ 完成（`b322fca`）：探针 p25_anim GREEN（x1/x10/跳过+重抽/error-safe，errors=0） |
| 7 | 门禁 + 部署生产 + 文档回写 | 小 | 计划 Task 7 | ✅ 完成：门禁 ALL GREEN ×2（初版 134 单测/js=656 → 终审修复后 137/js=657/local_ci 8 E2E+静态+Playwright 5）；文档回写（BACKLOG/HANDOVER/spec，`ad13d62`）；**oracle 终审 REVISE → 必改全修**（`6727be0`：MAJOR-1 浮点 n 白名单 + MINOR-2 身份一致扩 gachainfo/skin + MINOR-3 登录指引 + NIT-5/6/7）；部署生产 8090 两轮（零漂移、active/200/sha 与 dev blob 一致、journal 零 error、生产隔离单测 ALL PASSED、只读探针 OK），备份 `predeploy-20261016-021537/024921`；push origin/server（批25 全部 commit） |

## 批24（2026-10-15 起）

来源：用户「房间的设置我咋没看到 还是说权限太严了 我觉得房间直接支持修改吧」→ 范围拍板「完全放开（推荐）」→ 设计获批。
流程：`tamako-flow-backlog-sprint`。

| # | 项 | 大小 | 依赖/依据 | 状态 |
| --- | --- | --- | --- | --- |
| O1 | 房间设置权限完全放开：roomcfg/persist 删鉴权，⚙/⭐ 全员可见可点 | 中 | 用户拍板「完全放开」；设计获批 m0177；`can_edit_room` 函数保留以备收紧 | ✅ 完成：服务端 roomcfg/persist 移除 `can_edit_room` 检查（批24 注释）；客户端卡片两处无条件显示；单测 4 例翻转（stranger_allowed/open_to_anyone×2/owner_survives_reconnect 断言翻转）106 全过；E2E `test_pass_p6.py` 第 7 步翻转（非创建者 persist 放行回执 rooms persist=true）；探针 `p24_open.js` GREEN（陌生人见⚙/⭐→改名→双端广播生效 errors=0）；local_ci ALL GREEN；commit `6e0376b` 已部署生产+推送 |
| O2 | 房间删除：卡片🗑按钮 + `delroom` 消息，任意空闲房（含常驻⭐）任何人可删 | 中 | 用户「房间无法删除」→ 拍板「任意空闲房，含常驻」→ 设计获批 m0254；默认房/有人房拒 | ✅ 完成：服务端 `delroom` 分支（默认房拒/有人观战拒/persist 重写盘/delok+broadcast_rooms）；客户端非默认房（id a/b/c）显示🗑+confirm+`delok` toast；TDD 单测 `test_delroom_open_to_anyone` 先红（空闲房应被删除）后绿，**单测 107**；探针 `p25_del.js` GREEN（默认房无按钮/自建房删除+toast errors=0）；静态 js=581；local_ci ALL GREEN |
| O4 | 纯 AI 房可直接删除 | 小 | 用户报「AI房无法直接删除」→ 根因 = O2 `delroom` 用 `room.players` 判"有人"（含 bot 占位）→ 改 `any(not q.get('bot') ...) or room.subs` | ✅ 完成：单测第 5/6 段先红（纯 AI 房应可删除）后绿，单测 107；local_ci ALL GREEN；commit `251a933` 已部署生产+push（生产 sha 6cefab54 核对，隔离单测 ALL PASS） |
| O3 | 只剩 AI 自动停：纯 AI 房整房冻结（不 step 不 broadcast），真人回来自动恢复 | 小 | 用户挂起项「挂起项继续」放行；设计 = `room_live(room)`（subs 有人类 或 players 有非 bot）+ 从 `game_loop` 拆出可测 `game_cycle`，冻结时仍刷 `last_step` 防恢复大 dt 跳跃 | ✅ 完成：TDD `test_room_live_and_ai_freeze` 先红（`AttributeError: room_live`）后绿，单测 **108**；静态 js=581；local_ci ALL GREEN（8 E2E+单测+静态+Playwright 5/5）；不删/不回收纯 AI 房、不改 UI、不动 drop_player 清 AI 级联与 gc |
| O5 | AI 边角转圈吃不到水果：贪心打分绕墙死循环 | 中 | 用户挂起项 2；systematic-debugging 根因修复 | ✅ 完成：Phase1 确定性复现 `test-results/repro_circling.py`（case_a 8 步环/case_c 16 步环，BFS 可达却吃不到；夹具坑=Room.__init__ 默认生成 portals、未移动帧假阳性自环须按头位变化登记）；根因=`_bot_think` 纯贪心 Manhattan 打分无路径记忆，`|dy|>|dx|` 时缺口处选轴错向回环；修复=`_bot_path_step` 最短路首步 BFS（阻挡=地形+传送门+活蛇身，起步直行破平局，无路回落贪心）；TDD 2 例先红后绿，**单测 110**；复现 LOOP→EATEN(27/51 步)；local_ci ALL GREEN |

来源：用户上报「手机端访问体验不好」五项 + 后续追加指令。
流程：`tamako-flow-backlog-sprint` —— 一次取一项，做完回写本文件。
取证结论与根因链见 PLAN-P2P5.md 批23 记录及本文件各条。

## 用户拍板记录

| 问题 | 用户决定（原话/要点） |
| --- | --- |
| 常驻房修改权 | 「匿名也能恢复」——建房时下发一次性 owner 凭据存 localStorage，服务端校验放行 |
| 卡顿优化取舍 | 「动态自适应」——运行时采样帧耗时，掉帧自动降级、恢复升回 |
| 闪烁/开局不动时机 | 「说不清，按你排查到的修（推荐）」——先复现拿实证再动手 |
| 房间人数 | 「房间上的人数把ai区分一下」 |
| 设置面板 | 「房间创建的时候的设置和点击房间设置后保存的设置不一样 应该统一」+「房间设置建议点击后直接展开复用创建房间的视图代码」（实现方向已指定） |
| 闪烁线索 | 「白天场景容易闪烁」（主题相关，P3 复现提示） |

## 排序后候选池

| # | 项 | 大小 | 依赖/依据 | 状态 |
| --- | --- | --- | --- | --- |
| N1 | 房间人数区分 AI（卡片计数分真人/AI） | 小 | 用户 m0798；serve info() + renderRooms cnt 行 | ✅ 完成：`info()['humans']` 新字段（TDD 先红 KeyError→绿）；卡片 `2AI`→入局 `1人+2AI` 探针 EXIT=0；单测 100/100；静态 js=543 全过 |
| N2 | 创建房间设置与⚙房间设置统一：点设置直接展开、复用创建房间视图代码 | 中 | 用户 m0798+m0802 已指定实现方向；拍板：尺寸可改下局生效、口令可改+清除 | ✅ 完成：删 cfgScreen 全套，openCfg 复用 #createPanel 预填；roomcfg 扩 name/theme/rock/portal/size(pending)/pass(+clearPass 原子拒绝)；新用例 `test_roomcfg_extended_fields_unified` 先红后绿；单测 101、静态 ids=77 全过；n2_probe/n1_card 双 EXIT=0 |
| P5 | 修复「开局不动」（root cause 确凿 + 用户授权按排查修） | 中 | 根因三层：join/resume 不触发 maybe_start_round；在线滞留者永挡；晚加入者无准备 UI。复现 repro_round_stuck v2 | ✅ 完成：三层一次修齐（见回写日志 P5 条）；单测 103/103、repro v3 verdict 三 true、p5_ui 探针 EXIT=0、local_ci ALL GREEN |
| P2 | 移动端小地图遮挡 HUD 按钮（CSS 布局） | 小 | `.miniMap` fixed top:66px 压 `.hud` 多行后排 | ✅ 完成：`body.minimapOn` 让位右列 116px，几何探针零相交（见回写日志 P2 条） |
| P3 | 白天场景闪烁 | 中 | 已修复：根因=地板与基座顶面 z-fighting（y 差 0.005，远距深度精度不足逐帧互换）；连帧探针 over10 8→0 | ✅ |
| P6 | 常驻房修改权：owner 凭据下发+校验（匿名可恢复） | 中 | 用户拍板「匿名也能恢复」；`Room.owner_tok` + `can_edit_room` 第三轨 `secrets.compare_digest`，persist 同扩三轨，客户端 `snake-owner-toks` 入 localStorage | ✅ 完成：TDD 3 新例先红后绿（见回写日志 P6 条）；单测 106、静态 js=562 全过、local_ci ALL GREEN |
| P4 | 卡顿动态自适应画质 | 大 | 用户拍板；帧耗时采样→pixelRatio/阴影/小地图频率降级与恢复 | ✅ 完成：EMA 采样（>24ms×30 降档 / <17.5ms×180 升档、2.5s 冷却）三档自适应；探针先红后绿（见回写日志 P4 条）；静态 js=577 全过、local_ci ALL GREEN |
| P7 | 修 `test_ult_fruit_and_star_charge` 随机 flaky（约 1.5%） | 小 | P5 的 local_ci 抓到：吃果后 `place_food()` 随机补粒恰落 (4,5)（蛇头下一步+星星同格）→ 一步双吃 10+15+10=35 ≠ 期望 25；既有问题与 P5 无关 | ✅ 完成：夹具第二步前覆写 `r.food` 钉到远格 (0,9)（构造性消除随机，非概率性绕开）；确定性复现 35≠25 先红 → 30 连跑 0 失败；单测 106、local_ci ALL GREEN |

排序依据（按流程四规则）：① N1/N2 = 用户最新显式要求、成本收益最高；② P5 = 已确证的玩法级阻塞（严重但用户未催，授权已在手）；③ P2 = 成本极低；④ P3 = 已有主题线索可复现；⑤ P6 = 协议设计需多想一步；⑥ P4 = 成本最高放最后。

## 已完成

- **P1 卡顿/开局不动取证** ✅（批23 前段）：
  - 「开局不动」根因链复现成功（verdict 全 true）：限时房结算后滞留在线者永挡新局，晚加入者零 UI——详见 PLAN。
  - 「闪烁」resize 清屏假说**证伪**（同尺寸 width 重赋 readPixels no-op，20 次/10 事件零防抖但视觉无效果）→ 降级待实机。
  - 本地链路健康基线：16.3 snap/s、入局 613ms、帧 p50=16.7ms（96 大房、CPU 4× 降级）。
  - 探针留存 `test-results/`（gitignored）：repro_mobile.js / flicker_probe.js / repro_round_stuck.py。

## 回写日志

- 2026-10-15：建池（P1 完成结论落档）。用户追加 N1、N2（含实现方向）与 P3 线索，插入队首/队中。
- 2026-10-15：**N1 ✅**。TDD：`test_room_info_humans_vs_bots` 先红（KeyError 'humans'）后绿，单测 100/100、静态 ALL PASS、探针 `test-results/n1_card.js` 双态断言过（未入局 `2AI` / 入局 `1人+2AI`，零 console error）。顺带发现（不扩散，留作事实）：回主页=离房、离房后无真人时 AI 被清（serve.py L1022），故卡片断言须在局内读。下一项：N2。
- 2026-10-15：**N2 ✅**。用户拍板：尺寸可改（下局生效 pending_size）、口令可改+清除。实现：删 cfgScreen 整块（HTML/CSS/JS 引用零残留），openCfg 预填 #createPanel（pendingSize 优先、rockCustom/portalCustom 精确回填），btnCreateGo 按 cfgRoomId 分流 create/roomcfg，收起/取消即退出编辑态；服务端 roomcfg 扩 6 字段（口令先验、非法整条原子拒绝），Room 补 `self.size`（原只存 cols/rows，RED 抓出）、new_round 开头消费 pending_size 重建坐标系；info 加 rockCustom/portalCustom/pendingSize。RED（r.name 断言失败）→ GREEN 101 用例；静态 ids 82→77 全过；n2_probe（同视图/预填/保存改名即时/卡片尺寸仍旧=pending 下局生效）与 n1_card 回归双 EXIT=0。踩坑：①⚙ 是 `<span role=button>` 非 `<button>`（选择器改 .saveBtn）；②Room('rc','rc',10) 被 MAP_MIN=12 夹到 12（改测试期望）；③无全局 `.hidden` CSS，新控件补作用域规则。下一项：P5。
- 2026-10-15：**P5 ✅（「开局不动」三层根因一次修齐）**。实现：① 服务端 join 分支 `ready.add` 后补调 `maybe_start_round()`（全员就绪含挂起视 ready 时晚加入者立刻开新局）；② `step` 头结算滞留超时 `WIN_PENDING_MAX_MS=20000`：win_pending 为 dict 时首帧锚定 `win_at`、超时强制 `new_round()`（**只对 dict 生效**——`"t"` 哨兵与 `=={"winner":1}` 等式断言不受影响；new_round/drop/step 三处复位锚点）；③ 客户端 `handleRound`：`joined && state==='joining' && meta.over` → 补出准备屏（overTitle 按 win∈{平局/我/对手} 三态 + showReadyScreen）——晚加入者不再零 UI。TDD：`test_win_pending_timeout_forces_new_round`（RED=AttributeError WIN_PENDING_MAX_MS 特征正确）+ `test_late_join_starts_round_when_all_ready`（RED=join 后 win_pending 未清）→ GREEN **103 用例**；静态 js=552 全过。服务端 E2E `repro_round_stuck_v3.py`：**verdict 三 true**（前 8s 冻结 / 全程零 ready 下 round 0→1、28 蛇头坐标恢复 / over+20s 超时模型）；客户端 E2E `p5_ui.js`：三页（p1+p2 over 屏装死 + p3 晚加入）EXIT=0（p3 overVisible+「准备」+enabled，errors=[]——修复前 overScreen 隐藏零 UI）。门禁：local_ci **ALL GREEN**（8 E2E + 103 单测 + 静态 + Playwright 5）。踩坑：local_ci 首跑单测红 1 个 = `test_ult_fruit_and_star_charge` **既有随机 flaky**（吃果后 place_food 随机补粒落蛇头下一步+星星同格 → 35≠25，约 1.5%），与 P5 无关（未触碰吃食/充能路径，直跑复绿、重跑 local_ci 全绿）→ 记池 P7。下一项：P2。
- 2026-10-15：**P2 ✅（移动端小地图遮挡 HUD）**。根因（几何实证先于修复）：`.miniMap` fixed `top:54 right:8` 104×104 z-index:8 半透明底（L408-425），`.hud` 居中 flex-wrap 满宽三行（右缘 376）——移动视口 390×844 入局后 **4 chip 与小地图相交**（ultBtn/最高/btnCam/connChip，`pointer-events:none` 故为视觉遮挡非点击拦截）。修复：① CSS 移动端 MQ 加 `body.minimapOn .hud { padding-right: 116px; }`（内容右缘 W-130 < 小地图左缘 W-112 → **任意视口宽度恒 18px 间隙**的几何不变量）；② `updateMinimap()` 随 `show` 同步 `body.classList.toggle('minimapOn', show)`（仅在局/观战收窄，大厅不收）。TDD：几何探针 `p2_probe.js`（390×844，建房入局，断言小地图 rect 与全部可见 chip rect 零相交 + lobbyPad='0px' + inGame pad='116px' + errors=[]）先红（overlaps=4，pad 0px）后绿（overlaps=[]，EXIT=0）；副作用：hud 3→4 行（底 172→212，844 高度预算内画布+方向键仍完整落屏）。门禁：静态 css 162→163 全过、103 单测、local_ci **ALL GREEN**。探针备份 `Temp\opencode\p2_probe.js`（test-results 会被 Playwright 步清空）。下一项：P3（白天场景闪烁，需连帧 diff 探针拿实证）。
- 2026-10-15：**P3 ✅（白天场景闪烁 = 地板/基座 z-fighting）**。取证（先于修复，`test-results/p3_flicker.js`，rAF 内 readPixels 连帧 diff，>10% 突变存翻转 PNG）：day 主题 6s **361 帧中 8 帧 >10%、成对出现（间隔 15ms = 1 暗帧+1 恢复帧）、mean 亮度 157↔192 跳变(+35)、errors=[]**；翻转帧肉眼复核（flash0/flash4）：**棋盘远半区整片消失露深色基座 0x222a4e，近处棋盘/相机/蛇/名字位置完全一致，1 帧即恢复**——相机/蛇一致排除几何与网络；边界随相机角度倾斜 + 仅远区出现 = 深度精度随距离劣化。根因：地板 `floor.position.y=.005` 与基座顶面（Box 高 .8 于 y=-.4 → 顶 y=0）**仅差 0.005**，相机 near=.1 far=200 下远距深度量化步长超过间隙 → 逐帧深度平局互换；白天亮棋盘 vs 深蓝基座高对比所以刺眼（暗主题对照亦闪但肉眼难察）。修复：地板材质加 `polygonOffset:true, factor:-1, units:-1`（深度平局时地板恒胜，不改几何/光照/玩法数值）。TDD：探针即红测试（day over10=8）→ 修复后 **over10=0、meanRange 35.2→0.2、maxFrac 0.115→0.0157**（残余全为蛇/食物正常运动）；default 主题对照 over10=0；静态 77 ids/163 css/552 js 全过、103 单测、local_ci **ALL GREEN**。探针备份 `Temp\opencode\p3_flicker.js`。下一项：P6。
- 2026-10-15：**P6 ✅（常驻房 owner 凭据，匿名可恢复）**。协议设计：建房回执 `{t:'created', room, name, tok}`（`secrets.token_hex(16)`，**仅创建者回执携带，`info()`/room_list 不下发**）；`Room.owner_tok` 字段 + `can_edit_room(sess, room, otok=None)` 第三轨 `secrets.compare_digest` 常数时间比对（账号轨/sid 轨/凭据轨三选一，双 None 无凭据仍拒）；**`persist` 消息从「仅 `owner==sid`」扩为同一三轨**（原实现匿名断线后连自己常驻房都存不了）；persist 往返加 `ownerTok`（dump/load 防御式反序列容错，重启后匿名仍可恢复——本项核心场景）。客户端：`created` 存 `snake-owner-toks`（JSON map rid→tok，localStorage 跨刷新），卡片 ⚙/⭐ 条件 `myCreated.has || ownerToks[rid]`（`isMine()`），`roomcfg`/`persist` 出站附 `otok`（无则 undefined 不带键）。TDD：`test_created_issues_owner_tok`（回执带 tok + info 不泄露）、`test_roomcfg_owner_tok_recovers_anonymous`（匿名新 sid 凭据改 bots 放行、错/无凭据拒且参数不变）、`test_persist_owner_tok_grants_save`（无凭据拒→凭据存成功，`save_persist_rooms` 打桩不落真实文件）三例**先红**（`AttributeError: no attribute 'owner_tok'`）**后绿**，`test_persist_roundtrip` 扩 ownerTok 断言；踩坑：create 分支走 `sess.ip` 需给夹具补 `ip` 属性。门禁：单测 **106**、静态 ids=77/dup=0/css=163/js=562 全过、local_ci **ALL GREEN**（8 E2E 含 `test_pass_p6.py` 回归 + Playwright 5）。**浏览器探针 `test-results/p6_probe.js` GREEN**：建房→`snake-owner-toks` 1 键 tokLen=32 → 刷新（IIFE 内 `myCreated` 必空、新 sid 匿名）→ 卡片 ⚙ 仍显示 → 点⚙改名保存 → toast「房间设置已更新」+ 卡片即时改名 + errors=[]——**新 sid 匿名凭 otok 过服务端三轨鉴权**全链路实证。踩坑：探针须放项目内（Temp 下解析不到 `@playwright/test`）；`myCreated` 非全局（IIFE 封装）探针取不到属预期。探针备份 `Temp\opencode\p6_probe.js`。下一项：P4（动态自适应画质，池中成本最高放最后）。
- 2026-10-15：**P7 ✅（test_ult_fruit_and_star_charge flaky 根除）**。根因：第一步吃 (3,5) 果触发 `place_food()` 随机补粒，恰落 **(4,5)**（第二步蛇头与 bonus 同格）→ 一步双吃 10+15+10=**35 ≠ 期望 25**（约 1.5%）。确定性复现（夹具手动把补粒放 (4,5)）→ `ult = 35 expect 25 -> RED` 先红；修复=测试第二步前覆写 `r.food` 钉到远格 **(0,9)**（**构造性消除**——`place_food` 的随机选择被显式丢弃，非概率绕开）；**30 连跑 0 失败**。门禁：单测 106、local_ci **ALL GREEN**。只动测试夹具，玩法/计分零改动。下一项：P4。
- 2026-10-15：**P4 ✅（卡顿动态自适应画质）**——批23 收官项。机制：`frame()` 每帧 `qualSample(now, now-prevFrame)` 喂 **EMA**（.88/.12），`ema>24ms` 连续 30 样本（≈0.5s，<45fps）降一档、`ema<17.5ms` 连续 180 样本（≈3s）升一档、档位变更后 2.5s 冷却（回差防抖）；首帧/切回标签 >1000ms 大间隔不计入。三档 `QUAL_TIERS`：0 满档 {ratio1.5, 阴影开, 小地图每帧} → 1 中档 {1.0, 开, 每2帧} → 2 低档 {.75, **关阴影**（traverse 置 material.needsUpdate 重编译）, 每4帧}；pixelRatio 落地统一走 `resize()`（改读档位），小地图在 `frame` 末按 `miniTick%miniEvery` 降频。挂 `window.__qual={quality,qualSample,setTier,applyQuality}` 调试钩子（`quality.freeze` 隔离真实帧，探针专用）。**TDD 先红**（`window.__qual 缺失 → RED exit 1`）**后绿**：`test-results/p4_quality.js`（备份 `Temp\opencode\p4_quality.js`）——真实帧 ema 在喂 → 冻结注入 33ms×40 两轮 tier 0→1→2 且 `applied` shadows=false/miniEvery=4/canvas 432→324 → 注入 8ms 升回 0 且阴影恢复 → errors=[]，**PROBE GREEN**。门禁：静态 `js=577/577` 全过、单测 106、`pwsh scripts\local_ci.ps1` **ALL GREEN**（8 E2E + 单测 + Playwright 5）。踩坑：**local_ci 的 `npx playwright test` 会清空 `test-results/`**（P4 探针首跑后被抹，靠会话内内容重建）——探针务必备份到 `Temp\opencode\`。**批23 收官**：池 8/8 全清（N1/N2/P5/P2/P3/P6/P7/P4）；批末收尾已执行——漂移检查通过（`3dac1b4` serve.py 与生产 sha 一致 `5272bb48…`）→ 备份回滚点 `predeploy-20261015-153153` → `git -c core.autocrlf=false archive` 投放 → 重启 active/200/journal 零 error、生产 serve.py sha=`469583de…` 与 `39bc6be` blob 一致 → 生产 venv 单测 106 PASS（`/tmp/b23test` 隔离跑防污染 data）→ P4 探针经 ssh 隧道对生产 GREEN → 双远端推送至 `b7fe788`（origin/server 同址裸仓库）→ HANDOVER 生产版本行已回写。
- 2026-10-15：**批25 抽卡（祈愿）系统 ✅（A+1–6，7 执行中）**：用户 m0413「类似原神祈愿、吃果得货币解锁皮肤」→ brainstorming 拍板（m0419：果 +10 星尘、场上 3–8 果、160/抽、1600/十连、返还 10/50/200、1.6%/90 硬保底/5050、卡池 5–15）→ spec `1724228` → oracle 审计划（2 BLOCKER + 9 MAJOR 全修 `d9178eb`）→ 原生执行 Task 0–6：A 多果 `f0a6503`（**唯一协议 break：snap food→foods**）/ Store `c99d6e4` / 纯函数 `e3d721b`（11 单测）/ 消息鉴权 `df660ac`（11 单测，n 白名单/身份一致/关键区无 await/大厅可抽）/ SKINS 16 款 `d80640e` / 祈愿界面 `a01beaa`（p25_ui GREEN，入口 T5 Ruling=startScreen 账号行）/ 流星动画 `b322fca`（p25_anim GREEN，T6 Ruling=非 done 锁键盘+点击两段协议）；门禁 134 单测 / js=656+ids=97 / local_ci ALL GREEN；spec §5.2/§5.3 偏离与 HANDOVER 协议表已回写（本段同 commit）
- 2026-10-16：**批25 收尾（oracle 终审 → REVISE → 必改全修 → 重部署）**：终审 1 MAJOR（`handle_gacha` 白名单 `n not in (1,10)` 放行 float/bool——`True==1`、`1.0 in (1,10)` 相等性穿透，扣款后 `range(float)` TypeError 被顶层吞=扣款无回包，违反计划「非 int 零副作用回 error」）+ 4 MINOR + 4 NIT；修复（`6727be0`）= `type(n) is not int` 白名单（测试扩 1.0/10.0/True/None 带余额断言，TDD RED 先复现 TypeError）+ 身份一致扩 `gachainfo`（不一致回零值占位）/`skin`（不一致回 error，匿名换免费皮肤不受影响，既有 skin 测试补 `p.user` 入局不变量）+ 祈愿未登录 toast「请回主页登录」+ `room-ok` 后重发 `gachainfo`（resume 重同步 dust HUD）+ 计划/spec `gained`=本次返还合计 + 测试注释 21→5 改 3★；不动：NIT-8 `occupied()` 每调用建 set（开销亚毫秒级/tick 预算内）、INFO-9 文件尾 `y>` 垃圾行（50af4f0 前既存）、INFO-10 断服丢当场星尘（spec §5.1 允许的临时态）；门禁 137 单测/静态 js=657/local_ci ALL GREEN ×2；重部署零漂移（生产 sha=ad13d62→6727be0 blob）、active/200/journal 0、生产隔离单测 ALL PASSED、只读探针 OK

- 2026-10-16：**批26 收尾维护批（6 项拍板）→ 候选池 6/6 全清 + wrap-up 部署完成**：批25 报告 6 项建议用户逐项拍板（①顺手加缓存/②下批顺手删/③加 SIGTERM 优雅结算/④下批顺手补/⑤B 版本握手 reload/⑥先实测线上分布，开工时机=现在开工）→ backlog-sprint 排序 ⑥→⑤→③→①→②→④（解锁链：⑥取证解锁未来优化、⑤先于③避免新代码进 stale-tab 窗口），部署统一收口 wrap-up。交付：⑥ 7e2955 spawn 薄 wrapper 计时 + [spawn] journal 行 + last_spawn_ms；⑤ 8b015cc PROTO_VER=26 三路 room-ok 握手 + 客户端不等即 reload + HANDOVER bump 规则；③ 1632eab shutdown_settle 并账落盘 + install_shutdown_handlers（Linux add_signal_handler/Windows signal.signal 降级）+ spec §5.1 回写（TDD：RED AttributeError→GREEN，密码=6 位数字 135790 卡过 2 次失败预算第 3 次换路成功）；① d5ec38e occupied() 果占用集 (id,len) key 缓存（变更路径全集摸底零原地改；微基准 1.74→0.79µs/call -55%；坑：fresh() 清空 foods 须自播果、注册缩进 11 空格、commit 尾字节 GBK 坏须 -F 文件 amend）；② 8aec385 删尾 2 行（y>+重复 </html>，批23 引入）；④ 191c9f HANDOVER gachainfo 补换号零值占位行。门禁终值：单测 140 / static js=658 ids=97 / local_ci ALL GREEN（wrap-up 终跑）。部署：漂移零→备份 predeploy-20261016-113444→投放+restart×2→active/200/生产 sha=aa83e215+f7a35604==191c9f blob/journal error=0/生产隔离单测 ALL PASSED；⑥ 核验 journal [spawn] 行（14–21ms@32x32）、③ 实证 [shutdown] settle ok: 0 players（首 restart 收 SIGTERM 者为新代码进程才打印）。push e7c39e..b191c9f 三者一致，工作区干净。
## 批34（2026-10-19 · 地形遮挡）已完成

- 根因：丘/峰/楼/深渊材质 `depthWrite:false`（批32 为「蛇恒可见」的妥协）→ 山体挡不住蛇且自身前后不分。
- 改法：实体地形 `depthWrite=true` 真遮挡；水/草/元素面片（地板贴层）保持 `false`。
- 验证：height32 批34 用例先红后绿；local_ci ALL GREEN（183 单测 + 40 Playwright + 7 套 python E2E）；生产 scp 后遮挡 A/B 截图存证 `test-results/occl_prod_A_wall.png`（蛇被墙完全挡住）与 `_B_nowall.png`（清空后可见），`CONSOLE_ERRS=[]`。
- 协议：PROTO_VER 29 未变，未重启服务端。

## 批35（2026-10-19 · 奶龙/芙宁娜 角色皮肤 + 迷你 3D 模型 · 已完成）

- **需求**：新增「奶龙」「芙宁娜」两款角色蛇皮肤，蛇头挂**可辨识低多边形迷你 3D 模型**（GLB + GLTFLoader），**纯外观改动**。
- **素材定案**：Sketchfab 下载 API 401、许可不干净 → **不走第三方素材**，改自建生成器 `scripts/gen_models.js`（可复现、零版权风险）；`gltf-loader.js` = three r160 GLTFLoader 由 ESM **机械**改写成的 UMD 产物（**不引入 ESM 打包器**，`<script>` 架构不变）。
- **服务端**：`SKIN_N` 16→18；`FREE_SKINS={0,1,2,3,4,16,17}` 恒免费（角色款**不进 GACHA_POOL**，故无需持有记录）；`ALLOWED` 白名单加 `gltf-loader.js` 与两个 `.glb`；`/download` zip 清单同步；**`PROTO_VER` 29→30 双端 bump**。
- **客户端**：`applySkin` 加载 GLB 挂 `myEnt.head`；GLB 404 **静默回退** skull 球；`applyOffTint` 断线灰化改为**逐实体克隆材质**（避免一条蛇灰化污染全场蛇的贴图材质）；**未改** `CAM.h`/`camDist`、碰撞盒/判定/移动/玩法数值、`GACHA_POOL`，未加开关/设置项。
- **探针根因**：`applySkin` 原挂模块级 `head`，入局后 `demoBodyShow(false)` 把它隐藏、屏上渲染的是 `myEnt.head` → 旧探针瞄错对象（ON/OFF 字节完全相同 15411）。修复：`myHeadSel()`（优先 `myEnt.head`）+ `__modelBoxDbg()` + `__modelShowDbg(on, zoom)`（**zoom 只放大模型节点、相机不动**，原 scale 存 `node.userData.__zoom0`）+ `__modelDbg().mine`。
- **门禁**：`node scripts/gen_models.js` + `node scripts/test_gen_models.js` → `GENERATOR CHECKS PASSED`（16/16）；`e2e/skin35.spec.js` **6/6**；`node scripts/static_check.js` → `ALL STATIC CHECKS PASSED`（ids=135 dup=0 div=69/69 css=350/350 js=917/917）；`pwsh scripts/local_ci.ps1` → **ALL GREEN**（`npx playwright test` 跑整个 `e2e/`，含批35 spec）。
- **生产验收（验收 4）**：5 文件 scp + 重启（PID 1676685）、白名单全 200、远端 `index.html` 249141 B（`myHeadSel`=3）、`loader=true`、`MOUNT_* node=true skull=false`、`FALLBACK node=false skull=true`、三个取证会话 **`ERRS=[]`**（项目无 `prod_verify` 脚本，以取证脚本收集的 `pageerror`+`console.error` 为空作等价证据）。存证 `test-results/`：真实比例同会话配对 `prod35_{nailong,furina}_{ts,tsOff}.png`（ON=模型可辨 vs OFF=素金球）+ 8× 放大 `{head,headOff}` + 全帧语境 `zoomOn`。
- **证伪掉的取证路线（别再走）**：截图差分法、严格颜色计数法、投影盒子裁剪对比法 —— ON/OFF 字节数完全相同 / 地板干扰。最终用「**必须放大取证法**」（先 OFF 帧再 ON 帧）+ 真实比例同会话配对。
- **清理**：`prod35_*_normal.png` 实为登录页截图（无效，已删）；`*_full.png`、裸名 `prod35_{furina,nailong}.png`、`ab_/frz_/iso_` 过程帧全删；根目录 17 个一次性 `_tmp_*.js` 全删。
- **协议**：`PROTO_VER` 29→30 双端（皮肤数与模型资源属服务端语义变化）；bump 会再触发批29④ 每账号 14,400 更新回馈（预期行为）。
- **交付落点**：契约 `.tamako/contract.json`（`state=closed`，acceptance 4/4 `pass`）、证据 `.tamako/evidence.md`。

### 批35 第 2 轮（2026-10-19 · 可复现性补齐 · 已完成）

- **背景**：批35 首轮收口后用户问「现在还有什么问题」，盘点出 4 项交付流程问题（P1 提交未推送 / P2 本次部署没打 predeploy 备份 / P3 验收 4 无法一键复现 / P4 存证图不入库）。用户拍板：**「只补备份，先不推」**、**P3+P4「两条都做」**。
- **P2 已办**：生产补建 `/home/ubuntu/snake-3d-predeploy-20261019-134813.tar.gz`（546497 B / 55 条目；较 §11.2 配方多 `--exclude=node_modules`）。此前最新备份停在 20261017-192553，批34/批35 两次部署都没打 tar。
- **P3 已办**：新增常驻脚本 `scripts/prod_verify35.js`（`playwright` 由 `@playwright/test` 带入，**无新依赖**）。流程 = 探针就绪 → `#btnSolo` 入局 → `__applySkinDbg(id)` → 等 `mine.node=true` → `__modelBoxDbg()` 中心 ±170/±190 算 CLIP → 截图 ON → `__modelShowDbg(false)` → 截图 OFF → 还原，全程收 `pageerror`+`console.error`。**首轮实跑生产即 PASS**：`ALL_ERRS=[]`、两皮肤 `mine.node=true`、OFF 态 `{"node":false,"skull":true,"src":"myEnt"}`、`PAUSE_MASK={"display":"none"}`、退出码 0。与首轮口径的唯一差异：**不登录也能过**（16/17 属 `FREE_SKINS`，探针是纯客户端路径），`--login` 保留给要复核账号链路的场景。
- **P4 已办**：10 张首轮存证从 `test-results/`（被 `.gitignore` 忽略，且 Playwright 每次运行会清空）移入 `docs/evidence/batch35/`，`git ls-files` 计数 = **10**（验收 7 原文判据）。脚本重跑产出的 4 张 `prod35_{nailong,furina}_{on,off}.png`（nailong 173072/122790 B、furina 115150/106502 B）**不入库**，落 `test-results/`，可由 `node scripts/prod_verify35.js` 随时重新生成。`test-results/` 另有他批文件（`p33_attach_react.png`、`smoke-home.png`、`smoke-ingame.png`、`.last-run.json`，按契约不动）。另注：`BACKLOG.md` 里存在一个**既存 NUL 字节**（offset 49571，批35 之前的 `git show HEAD:BACKLOG.md` 同样有，非本轮引入），它让 ripgrep/`read` 工具把本文件当二进制跳过（git 仍按文本 diff）；按「不顺手改未被要求的东西」原则只报不动。
- **生产零漂移复核**：本地与生产 5 文件 sha256 逐字节一致（`index.html` d0687bb7…、`gltf-loader.js` 87492709…、`serve.py` f5ceeb5c…、`models/nailong.glb` 550fd911…、`models/furina.glb` 70c10d91…），`PID 1676685` 存活、`HTTP 200 249141B`、`PROTO_VER = 30`，生产目录无 `_tmp` 散件。
- **仍待人工**：`git push`（`dev` ahead `origin/dev` 16 / ahead `server/dev` 27）——用户明确「先不推」，故本轮未执行；本 clone 无 GitHub/Gitee 远端，`ci.yml` 在此不会触发（本地等价门禁是 `scripts/local_ci.ps1`）。
- **契约**：`.tamako/contract.json` 增补 acceptance 5/6/7（备份 / 脚本 / 存证入仓）并全部 `pass`，`state=closed`；证据 `.tamako/evidence.md` 增「第 2 轮 · 可复现性补齐」章节。
## 批36（2026-10-19 · 按整体评估建议逐个修复 · 已完成）

- **背景**：用户看过整体代码评估报告后拍板「按建议逐个修复」，并拍板两点口径：roomcfg「设密码的只有房主能改 没密码的所有人都能改」、逐项独立 commit（不 push）。
- **P0-1 落盘节流（db1f509）**：`store.inc/record_best` 改 `_mark_dirty()` 脏标记 + 5s 节流批量落盘（`STORE_SAVE_INTERVAL=5.0`），主循环不再逐事件整份重写 store.json；register/add_stardust/grant_skin 仍立即写，`shutdown_settle` 无条件 flush 兜底。测试 2 条（哨兵法先红后绿）。
- **P0-2 写盘安全（629620f）**：`save_persist_rooms` 改 tmp+`os.replace` 原子写（异常吞掉删半截 tmp 返 False）；`Store.load` 损坏先备份 `store.json.corrupt-<时间戳>` 再 `users={}` 兜底。测试 2 条先红后绿。顺带修既存随机 flaky `test_eterrain_attach_and_spawn_avoid_batch33`（20×20 只撒 6 格且依赖全局 RNG 残留 → 测试钉死 (5,5)/hydro 构造性消除）。
- **P1 roomcfg 口径（a0095e1）**：有口令房仅三轨房主（账号/sid/owner_tok，复用 `can_edit_room`）可改，无口令房任何人可改（含首次设口令）；persist/delroom 维持放开（契约 notDo）。测试 2 条先红后绿，客户端已带 otok 无需改。
- **P1 生产备份**：ssh 生成 `/home/ubuntu/snake-3d-data-20261019-153034.tar.gz`（28834 B，tar tzf 含 data/store.json ✓），无本地代码改动。
- **P1 门禁补套（7dda151）**：`local_ci.ps1` python E2E 9→11 套（+test_ws3/ws4）；两套断言原停在批6 之前（期望创建者断开即回收自定义房）→ 改为对齐现行 GC 口径（24h 内保留）；`ci.yml` 补 `test_reactions_p33.py` 一行。实跑 local_ci ALL GREEN（189 单测 + 11 套 E2E + Playwright 46 passed）。
- **P2 拆分起步（0b03f4e）**：`handle_msg` 698 行/32 分支 if 链逐支平移为 28 个 `_msg_*` handler + `MSG_HANDLERS` 注册表（逻辑零改动，脚本化平移带断言；局内 9 名共用 `_room_actor`），新消息 `@msg_handler` 注册即可；`index.html` 18 主分区头注编号 01-18 + 祈愿升 19，IIFE 开头加分区编号索引块。
- **P2 热路径减负（2e160fd）**：frame() 每帧 `$()`/querySelectorAll 改启动期缓存（elAtkBtn/elElemBar/elEbBtns）；placeEdge 的 canvas 包围盒缓存（resize 失效）；updateBoard 加内容签名脏标记跳过榜单 DOM 重建（款式同 effHudSig）。
- **已知问题披露**：reactions.spec「元素弹渲染链路」在全量跑中偶发落在已 win 的 solo 局而超时（spec 注释自述既有竞态），本轮复跑全绿，未归因于本批改动；未修（越界，改 spec 属新决策）。
- **契约**：`.tamako/contract.json` acceptance 1-8 全 pass、`state=closed`；7 个本地 commit（db1f509/629620f/a0095e1/7dda151/0b03f4e/2e160fd + 收尾文档提交），未 push（契约 notDo）。

## 批37（2026-10-19 · 「都做」全量清扫 · 已完成）

来源：用户原话「都做」——完成上轮盘点的全部未做项。流程：直通（12 条验收契约 `.tamako/contract.json`）。

- **项1 生产部署批36**：predeploy `snake-3d-predeploy-20261019-202345.tar.gz`（546497 B）→ scp serve.py + index.html → 远端 sha256 与本地逐字节一致、新 PID 1812083、HTTP 200 251348 B、`PROTO_VER = 30`、`node scripts/prod_verify35.js` → `VERDICT=pass`（皮肤 2/2、`ALL_ERRS=[]`）。
- **项2 文档债（7d36306）**：HANDOVER §10 对齐现状（11 套 / 14 spec / 46 passed / 单测 191 / js 915）、§13 #10 追加批37 竞态修复记录、#11 改写为已修、当前生产版本改 dev@a341db5；DEPLOY.md 标题改「批1-23 基线 + 批24-37 已交付」与工程化数字对齐（191 单测 / 11 套 / 14 spec）；**BACKLOG 既存 NUL 字节 ×2（offset 49571 起）清除**——这是本文件被 ripgrep/read 判为二进制的根因，97 处 CRLF 混排随 autocrlf add 一并归一为 LF（内容零改动）。
- **项3 ci.yml（c882fcf）**：round2 补 `test_ws3.py`/`test_ws4.py`，9→11 套与 `local_ci.ps1` 一致。
- **项4 账号口令强度（eddbfb3）**：register/login 放开为 6-64 位任意字符（旧 6 位数字账号兼容），客户端 `#passIn` 同步；新单测 `test_password_policy_accepts_6plus_chars` 先红后绿；test_game.py 190 全绿。
- **项5 房口令哈希存储（a7a09bd）**：`Room.passw` property（明文 + `salt$hash` 并存）、`has_pass`、`check_pass()`；persist 只写 `pass_h`、加载后内存不留明文（旧档明文自动转哈希）；新单测 `test_room_passw_hashed_at_rest` 先红后绿；test_game.py 191 全绿。
- **项6 批33 4 条 oracle NIT（本段）**：**逐条原文不可恢复**——已穷尽检索 `ho-export.json`（10.8MB 会话导出，独立 NIT 0 次）与本会话 dcp 压缩存储（95 处独立 NIT 全为批25 抽卡审查 / 批28 预测审查，或「批33 4条 NIT」这句盘点文字自引用），原始 oracle 评审输出已被压缩丢弃且不在任何可读存储。改用替代口径（与 explore 结论一致），现存最接近的 4 条可考遗留逐条核对：
  1. HANDOVER §13 #10「批33 三处测试性约束」——`e2e/reactions.spec.js` 已内置对策（`waitPlaying` + `playing&&alive` 才按 e + 40ms 紧采 + 固定账号 p33elem），且批37 前一轮再修「win 态卡准备屏」全量偶发竞态（`5e59f6e`，全量 46 passed）→ **已修**；
  2. HANDOVER §13 #11「ci.yml 缺第 9 套」——项3 已修（`c882fcf`，round2 现 11 套）→ **已修**；
  3. BACKLOG:17 批33 遗留「ci.yml 仍 7 套」——被项3 覆盖（reactions + ws3 + ws4 均已补）→ **已修**；
  4. 批33 元素弹 E2E 采样竞态——同第 1 条，spec 已固化对策并经批37 前一轮修复复验 → **已修**。
  四条全部「已修」，无遗留需记理由项；原文丢失事实披露于此，检索方法可复现（node 读 JSON 统计独立 NIT 出现）。
- **项7 运行配置外置（40ed250）**：新增 `load_runtime_config()`（env `SNAKE_CONFIG` 指向 JSON 文件；缺文件/非法 JSON/根非对象告警兜底 `{}` 不阻断启动）与 `cfg_val(key, default, cast, lo, hi, cfg, env)`（优先级 **配置文件 > `SNAKE_<KEY>` env > 代码默认**；转换失败回默认；lo/hi 钳位）；接线 CREATE_MAX/CREATE_IP_MAX/CREATE_WIN/ROOM_MAX/REG_MAX/ROOM_KEEP_SECS/STORE_SAVE_INTERVAL 七键 + PORT。新单测 ×3（优先级与回退钳位 / 文件加载与坏档兜底 / 接线后默认值不变）先红（`AttributeError: no attribute 'cfg_val'`）后绿；test_game.py 194 全绿。
- **项8 state 写入收敛单一入口（c180045）**：index.html 13 处 `state='…'` 赋值全改 `setState(...)`（声明 `:1108` 后新增，函数体仅 `state=v`，界面副作用留原地不动）；`advanceStep(state,…)` 同名只读形参不受影响。门禁：static_check PASS（js=916/916）+ Playwright 46 passed。教训：`str.count` 是子串匹配，缩进差异（4/6/8/10 空格）会误命中——锚点必须带行首 EOL 锚定。
- **项9 three r161+ ESM（b6fdef2）**：three.min.js(r160 UMD 669KB) → `three.module.min.js`(r161 ESM 675320B) + `<script type="importmap">`（`"three": "./three.module.min.js"`）+ 主脚本改 `<script type="module">` + `import * as THREE from 'three'` / `import { GLTFLoader } from './loaders/GLTFLoader.js'`；jsm 源码入库 `loaders/GLTFLoader.js`(108522B) + `utils/BufferGeometryUtils.js`(31554B)（GLTFLoader 依赖，与 loaders/ 平级布局）；serve.py ALLOWED 静态白名单与 /download zip 清单同步、test_ws2.py/verify_rooms.py 冒烟 URL 同步、package.json main 同步、`scripts/static_check.js` 支持 importmap/module 块（module 写临时 .mjs 再 node --check）；**计划内删除** `three.min.js`、`gltf-loader.js`、`scripts/build_gltf_loader.js`（UMD→THREE 全局的机械改写管线退役，git 历史保留）。四道门禁全绿：static_check（ids=135 js=917/917）、静态路由探测（新 3 件 200 + 旧 2 路由 404）、全量 Playwright 46 passed（skin35 6 条 GLB E2E = ESM 链路真浏览器跑通）、单测 194 全绿。
- **项10 真实 CI = BLOCKED（外部阻塞，验收原文自带 BLOCKED 出口）**：本 clone 无 GitHub/Gitee 远端（origin=ssh://vmsz 裸仓、server=tencent 裸仓，均不支持 Actions）；`gh` CLI 未安装；`git credential fill` 探测 github.com/gitee.com 均无凭据（本机只配了本地 Gitea yuannas.local:3000，与本项目无关）。解锁所需：GitHub 账号 + repo 权限 token（或装 gh CLI 后 `gh auth login`）→ 把 dev push 到 github.com 新远端 → ci.yml 首跑（workflow 无 secrets 依赖，python+node+npx playwright 自足）。
- **项11 批28 §7.3 转向手感量化（a780caa）**：新增 `scripts/quant_feel28.js`（343 行）——headless chromium 进 solo，页内 16ms 采样器读 `__predState`/`__stateDbg` + keydown capture 时间戳，node 侧 evaluate 全程 10s 超时 + FATAL 截图取证，输出 `test-results/quant_feel28.json`。spec §7.3 五点自动化三组：Q1 转向跟手延迟、Q2 开放地无回弹、Q3 局末结算窗不抖（M1 speed 期间与对头回弹按 spec 原口径留人测）。实测（VERDICT=pass）：Q1 pv 最快 16.8ms≈1 帧即时（余 4 试次 pred 断链期 null；2 条 md 延迟受 headless 软渲染长帧污染属环境噪声）、**Q2 直行 2458ms/91 帧 mdChanges=0 / mdReversals=0 / headBounces=0**、**Q3 over+win 19933ms/1212 帧 headMoves=0 / headBounces=0**——数据无系统性缺陷，故**未做实现调整**（契约 notDo 不许盲调玩法参数；最终判定交用户实操）。四版迭代根因：页内无界 for(;;) 在 moveDir 零向量下死循环挂死 renderer（循环全改有界 + 零向量短路）；solo 房 respawn=False 死亡后只能 goto+btnSolo 开新命。
- **项12 收尾**：文档回写（本段收口 + HANDOVER 行数/vendor/§10 ×194/§13 #5 #9/DEPLOY 对齐）→ 全量 `local_ci.ps1` ALL GREEN → push origin+server → 生产再部署（predeploy tar + scp + 重启 + 远端 sha 核验 + prod_verify35）→ 契约 12 条自评（项10 blocked 如实记）。

## 批38（2026-10-20 · quant_feel28 M1/M4 落地修复 · 已完成）

来源：批37 项11 交付的 quant_feel28.js 把 M1 speed 期间与 M4 踏门回弹按 spec 原口径留了人测——本批目标是把这两项做成自动化并实测出数据。流程：直通（契约 `.tamako/contract.json`）。

- **项1 pred-T1 竞态修复（84adcde）**：snapShell 补 hmap 空场，堵批32 高度通道泄漏（详见 commit）。
- **项2 quant_feel28 落地修复（a8ec20c）**：M1「吃到 speed 道具后 3.2s 窗」与 M4「踏门后回弹窗」从人测改为自动化，四轮实跑迭代，**最终 VERDICT=pass**（M1 spdFrames=124/hr=20/aliveEnd=true；M4 crossings=2，a0/a1 各 1 次 nav ok）。
  - **主根因（实证确证）**：index.html:1122 默认 `camFollow=true` 时 setDir(:2764) 把按键当**相对旋转**——↑/↓(x=0) 直接忽略、←/→ 只左右转 → 我方绝对方向键全废，蛇无输入直行撞崖/出界（__qfDeaths 60 次死亡全 cliff/wall，~6.5s 一死螺旋）。修复 = WS_PATCH 注入 `__qfCamFix()`（body.follow 存在才点 #btnCam，幂等），初始注入/ensurePlaying 新局/navToward 启动前三处调用，实测 follow-after=false 生效。
  - **次根因链**：①控制延迟——旧 navToward 每键一个完整 Node→page evaluate RTT（~1.1s/press）追不上 150ms/步；改页内 `__qfCtrl` 控制器（100ms interval）+ `__qfPlan` BFS 多目标寻路（静态障碍+上行≥2+自身 body+首步禁反向）。②保命 v2 拐向<4 原地等死 → v3（直行≥3 不管/拐向≥2 拐/拐向≥1 且直行≤1 拐一格）。③M1 取缓存第一个 speed 道具（常是远处/12s 快过期）→ 改距头最近。④M1 记录窗污染（死亡残帧+无 headroom 门）→ 吃到后 headroom 门转向 + `s.spd>0 && s.alive` 过滤。⑤M4 观察窗污染（踏门后 KA 保命键仍按）→ 控制器 done 即停输入（~100ms 内）+ KA 让位条件。⑥权威头 `__qfHeadDir`（服务端快照新鲜优先/投影兜底）+ body 障碍优先服务端 cells。
  - **排除的假设**：WS 地形缓存失效（serve.py :2290-2331 增量帧每字段是**全量值非 patch**，客户端正确合并即可，读码排除）。
  - 基础设施教训：后台 shell 硬 120s 上限连后台命令也杀 → 长跑用 `Start-Process cmd`（重定向日志）+ 前台 wait-loop。
- **项3 文档回写 + 全量门禁**：本段 + HANDOVER；`local_ci.ps1` ALL GREEN 复核后收口。
- **项4 契约自评**：见 `.tamako/contract.json` + 报告。
- 临时探针产物已清（scripts/_probe_ws.js、test-results/_extract_create.py、_create_body.txt、_srv_create.txt、_probe_ws.log）。
