# 候选池（批22 之后 · 批23 起）

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
| P6 | 常驻房修改权：owner 凭据下发+校验（匿名可恢复） | 中 | 用户拍板「匿名也能恢复」；myCreated 内存 Set + can_edit_room 只认 sid/账号 | 待做 |
| P4 | 卡顿动态自适应画质 | 大 | 用户拍板；帧耗时采样→pixelRatio/阴影/小地图频率降级与恢复 | 待做 |
| P7 | 修 `test_ult_fruit_and_star_charge` 随机 flaky（约 1.5%） | 小 | P5 的 local_ci 抓到：吃果后 `place_food()` 随机补粒恰落 (4,5)（蛇头下一步+星星同格）→ 一步双吃 10+15+10=35 ≠ 期望 25；既有问题与 P5 无关 | 待做（建议：测试里锁定补粮位置或断言改区间） |

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
