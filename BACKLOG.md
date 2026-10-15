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
| P5 | 修复「开局不动」（root cause 确凿 + 用户授权按排查修） | 中 | 根因三层：join/resume 不触发 maybe_start_round；在线滞留者永挡；晚加入者无准备 UI。复现 repro_round_stuck v2 | 待做 |
| P2 | 移动端小地图遮挡 HUD 按钮（CSS 布局） | 小 | `.miniMap` fixed top:66px 压 `.hud` 多行后排 | 待做 |
| P3 | 白天场景闪烁 | 中 | 线索「白天易闪」；已证伪 resize 清屏假说（readPixels no-op）；剩余候选：真机 GPU/阴影/主题光照，需连帧 diff 探针复现 | 待做 |
| P6 | 常驻房修改权：owner 凭据下发+校验（匿名可恢复） | 中 | 用户拍板「匿名也能恢复」；myCreated 内存 Set + can_edit_room 只认 sid/账号 | 待做 |
| P4 | 卡顿动态自适应画质 | 大 | 用户拍板；帧耗时采样→pixelRatio/阴影/小地图频率降级与恢复 | 待做 |

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
