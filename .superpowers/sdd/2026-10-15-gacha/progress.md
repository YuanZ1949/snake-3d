# SDD ledger — plan: docs/superpowers/plans/2026-10-15-gacha.md

Pre-flight: shared interfaces T1→T2/T3 (store.* / gacha_roll/pool_pick/GACHA_POOL), T3→T4/T5/T6 (消息协议) — 计划 Interfaces 块互相一致，无冲突。
Ruling: 直接在 dev 分支执行（非 worktree）— 批23/24 既定工作流，用户授权「开工」，部署流程与 dev 直推绑定 — cost if wrong: 与既有五批相同的既受风险。

Task 0: 结论（用户拍板 m0419）— 1 果 = 10 星尘、场上多果并存（果数随地图放大 3-8 个）。bonus 星星同 +10（对等）。重估：活跃一局 300s ≈ 600-1800 星尘 ≈ 4-11 抽/局，最坏保底 14400 ≈ 8-24 局。定价 160/1600 不动。
Task 3: Ruling: 多果 = 服务端 self.food → self.foods 列表（snapshot 字段 food→foods，客户端同批改渲染/吃除名），部署同文件无滚动兼容负担 — spec §4.1 同步改写。

Task 3: Ruling 修订 — 多果改动从 T3 拆出，作为独立 Task A（先于 T1 执行）：serve.py food→foods 列表 + place_food 满员 + snapshot 'foods' + index.html 渲染/吃除名，独立 TDD；T3 回归纯抽卡协议（dust +10 两点保留）。理由：正交改动分开可测，T3 不膨胀。
