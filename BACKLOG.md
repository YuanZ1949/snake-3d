# 候选池（批22 之后 · 批23 起）

> **批23 已全清（8/8，2026-10-15）**，批末收尾（push 双远端 + 部署生产 8090）亦完成。
> 本文件转为批23 归档；新需求请另起批24 段落或新建候选池。

## 批30（2026-10-17 · ①新手村配置 + ②在线人数 已交付 / ③公屏聊天/④管理员 待对齐）

来源：用户原话「新手村不新手 我觉得配置应该调整一点」「网站当前多少人也可以显示一下」「另外有没有必要增加一个聊天界面 支持暂停（这个也要支持）后公屏聊天 另外还有要不要加个管理员账户」。流程：backlog-sprint，逐项 brainstorming 拍板后独立交付。① 痛点票选 4 项（地图小被围死 / 主题随机地形复杂 / 无 AI 陪练被真人虐 / 死一次整局出局），参数拍板：**地图 24×24、主题保持随机**。

| 层 | 内容 | 证据 |
| --- | --- | --- |
| ① 新手村配置 | `DEFAULT_ROOMS` a 16→24；`NEWBIE_ROOM_CFG={rock_mult:0.5, bots:2, respawn:True}` 由 `init_rooms` 注入房 a（岩石覆盖主题值、2 条 AI 陪练、死亡可复活；respawn init 兜底自动限时 120s 比分结算）；b 标准局/c 大神场全默认不动 | `test_newbie_room_cfg_batch30` 先红（cols 16≠24）后绿：a 五项新值 + `eff_rock()==0.5` + AI×2 实生成 + b/c 不变 guard；`local_ci` ALL GREEN |
| ② 在线人数 | serve `online_count()`（登录按用户名去重、匿名按会话计）+ `broadcast_online()`：welcome 附 `online` 字段、会话建立/断开 + 身份变化四消息（register/login/authtoken/logout，handler 层单点）广播 `{'t':'online','n'}`；首页 `.roomHead` 新增 `#onlineBox`「🌐 当前在线 N 人」；纯增量不 bump PROTO_VER（设计获批：显示位置/去重口径/推送不轮询；不做峰值与战局内 HUD） | `test_online_count_batch30` 先红（AttributeError）后绿（同账号双标签去重 4→3）；e2e/rooms.spec.js「首页显示当前在线人数≥1」GREEN；单测/静态（ids=107）/`local_ci` 全绿 |
| ③a 公屏聊天+面板 | serve：`gchatin`（1s 限速/80字/空白拒，限速槽先于校验与房内同口径）+ `gchat_log`=deque(50) 内存 + `broadcast_gchat` 全体会话 + `welcome_payload()`（组包从 handler 拆出，带 `gchat` 历史）；客户端：`#chatPanel` 双 Tab（💬公屏/🏠本房）、三入口（首页房间行「💬 公屏」/顶栏「💬 聊天」手机可点/键盘 `/`），旧 `chatIn` 与 `.chatLog.up` 移除，本房 Tab 局外回退公屏，断线/换世界清本房列表（公屏保留） | `test_gchat_batch30` 先红（no attribute gchat_log）后绿（历史50 头淘汰/限速/空白拒/截断/登录名/广播含自己/welcome 历史）；e2e/gchat.spec.js ×3 GREEN（发言回显/新连接 welcome 历史/回退）；静态 ids=114 dup=0；`local_ci` ALL GREEN（Playwright 26 passed） |

待办（逐项对齐后补充行）：③ 公屏聊天 + 暂停交互（语义待澄清：现聊天仅房内、暂停仅主页演示）；④ 管理员账户（倾向轻量 admin 标记 + 踢人/禁言/公告）。

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

- 2026-10-16：**批26 收尾维护批（6 项拍板）→ 候选池 6/6 全清 + wrap-up 部署完成**：批25 报告 6 项建议用户逐项拍板（①顺手加缓存/②下批顺手删/③加 SIGTERM 优雅结算/④下批顺手补/⑤B 版本握手 reload/⑥先实测线上分布，开工时机=现在开工）→ backlog-sprint 排序 ⑥→⑤→③→①→②→④（解锁链：⑥取证解锁未来优化、⑤先于③避免新代码进 stale-tab 窗口），部署统一收口 wrap-up。交付：⑥  7e2955 spawn 薄 wrapper 计时 + [spawn] journal 行 + last_spawn_ms；⑤ 8b015cc PROTO_VER=26 三路 room-ok 握手 + 客户端不等即 reload + HANDOVER bump 规则；③ 1632eab shutdown_settle 并账落盘 + install_shutdown_handlers（Linux add_signal_handler/Windows signal.signal 降级）+ spec §5.1 回写（TDD：RED AttributeError→GREEN，密码=6 位数字 135790 卡过 2 次失败预算第 3 次换路成功）；① d5ec38e occupied() 果占用集 (id,len) key 缓存（变更路径全集摸底零原地改；微基准 1.74→0.79µs/call -55%；坑：fresh() 清空 foods 须自播果、注册缩进 11 空格、commit 尾字节 GBK 坏须 -F 文件 amend）；② 8aec385 删尾 2 行（y>+重复 </html>，批23 引入）；④ 191c9f HANDOVER gachainfo 补换号零值占位行。门禁终值：单测 140 / static js=658 ids=97 / local_ci ALL GREEN（wrap-up 终跑）。部署：漂移零→备份 predeploy-20261016-113444→投放+restart×2→active/200/生产 sha=aa83e215+f7a35604==191c9f blob/journal error=0/生产隔离单测 ALL PASSED；⑥ 核验 journal [spawn] 行（14–21ms@32x32）、③ 实证 [shutdown] settle ok: 0 players（首 restart 收 SIGTERM 者为新代码进程才打印）。push  e7c39e..b191c9f 三者一致，工作区干净。