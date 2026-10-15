# 候选池（批22 之后 · 批23 起）

> **批23 已全清（8/8，2026-10-15）**，批末收尾（push 双远端 + 部署生产 8090）亦完成。
> 本文件转为批23 归档；新需求请另起批24 段落或新建候选池。

## 批24（2026-10-15 起）

来源：用户「房间的设置我咋没看到 还是说权限太严了 我觉得房间直接支持修改吧」→ 范围拍板「完全放开（推荐）」→ 设计获批。
流程：`tamako-flow-backlog-sprint`。

| # | 项 | 大小 | 依赖/依据 | 状态 |
| --- | --- | --- | --- | --- |
| O1 | 房间设置权限完全放开：roomcfg/persist 删鉴权，⚙/⭐ 全员可见可点 | 中 | 用户拍板「完全放开」；设计获批 m0177；`can_edit_room` 函数保留以备收紧 | ✅ 完成：服务端 roomcfg/persist 移除 `can_edit_room` 检查（批24 注释）；客户端卡片两处无条件显示；单测 4 例翻转（stranger_allowed/open_to_anyone×2/owner_survives_reconnect 断言翻转）106 全过；E2E `test_pass_p6.py` 第 7 步翻转（非创建者 persist 放行回执 rooms persist=true）；探针 `p24_open.js` GREEN（陌生人见⚙/⭐→改名→双端广播生效 errors=0）；local_ci ALL GREEN |

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
