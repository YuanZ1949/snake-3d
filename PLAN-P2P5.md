# 全量开发计划（backlog-sprint 候选池，23 项 → 11 批）

---

# 第二轮计划（批13-19，待子代理审阅）

总纲（m0221）：考察全部候选 → 列入计划 → 子代理审阅 → 直接执行 → 回归 → 上线（部署生产 8090）；决策自主按推荐。

## 候选池与考察结论（两个 explore 子代理报告 + 已确认）

| 项 | 症状 | 已考察根因（关键行号） |
|---|---|---|
| D 方向失控 | 某些时刻按键无效但视角可调，蛇沿旧方向撞墙 | ① dirQ 出队只比队头 `index.html:2134-2136`，服务端丢弃/改向（win_pending serve.py:1756、deflect 清队列 958、portal 改向 905、队满 1761、send 未发出 index.html:1486）造成队头永久失步 → `dirQ.length<4` 上限锁死；② 回合切换不清 dirQ（handleRound 2148→2177 先置 playing，2155 复位块被跳过；'round' 2286 也不清）+ onWin else 保持 playing（2362-2364）；③ send 异常只置 sess.room=None（serve.py:1313-1314）不摘 subs/pid → dir 永远走 1746 静默丢但快照照发 |
| C AI 吃不到水果 | AI 绕水果转、水果不消失 | ① place_food 无可达性检查（serve.py:640-670）→ 水果落蛇圈/岩石口袋永不可达；② _bot_think 无绕行搜索（serve.py:835-863，单步曼哈顿+固定次序 → 沿障碍绕圈）；③ bonus 优先压过 food（844-847，星星约 40% 时间常驻 → AI 无视水果）；④ spawn 可压在水果上（_solid serve.py:558 不含 food）；次要：head_on 冻结抖拍、快照帧丢失（1296 先更新 sig 后发送，异常被 1469 吞） |
| F 碰撞卡叠 | 蛇互相穿插/卡住不分离 | ① spawn_player 兜底分支零占用检查（serve.py:629-638）→ 两蛇同格同向 → head_on 每 tick force_right 永久死锁（914-935 + 1024 不移动）；② _protected 只拦咬不拦进入（974 continue vs 1027 插头）→ 无敌/护盾期穿身；③ 尸体不清且不阻挡（1015 只置 alive=False）；④ off_at 挂起蛇静止 10s 仍参与碰撞/挡 AI（869 vs 926/970/984）；⑤ portal 出口无占用预检 + 出口朝向恒东（902 因 561 把传送门算实心，_open_ahead 恒 0）；⑥ spawn 可压 food（同 C）；⑦ 双重 force_right 同帧右转两次反向自杀（914-935 互不检查 head_on） |
| B 下拉栏 | 建房面板 select 原生白底下拉（m0193） | 未考察细节：Chrome 原生下拉不吃 option 背景色 → 需 `color-scheme: dark` 或 appearance 自绘；小改动 |
| E 房间参数编辑 | 局中/房间改 win_mode/limit/respawn/bots 等（m0198） | 已有 create 解析全套参数（批1）；需新消息 `roomcfg` + 房主鉴权 + 重开局语义；client 复用建房面板控件 |
| G 死亡后直接观赛 | 死亡屏加「观战」按钮（m0209） | onMyDeath/overScreen 已在 index.html:2311-2335；spectate() 1637-1653 已存在；只差按钮+状态衔接 |
| H 碰外墙偏转项 | 新增房间选项：撞边界墙自动偏转（不用 deflect 道具）；石头/场内岩石照死、被别人咬到 <2 照死（m0222） | _deflect_dir + 折返机制批2 已有（serve.py:952-960、1072-1089）；只差 Room 参数 `walldeflect` + 判死处 947 分支 + 建房控件 + info/snapshot 下发 |
| A2 本地 CI 等价脚本 | 一键回归（单测+8 E2E+静态+Playwright） | 命令套路已固化（见 HANDOVER）；写 scripts/local_ci.ps1 |
| A3 服务器清理 | /tmp 探测脚本 + 部署目录 6 个 .bak + index.html.bak-* | 部署时已识别；上线时顺手清（保留 predeploy tar 备份） |

A1 ✅ 已完成（commit a0283e9，broadcast list 副本 + 确定性证明）。

## Oracle 审阅（ses_ec42f5645ffe…）：需修改后执行 → 已按必改项修订（采纳）

**必改项（已并入各批方案）**：
1. 批13① dirQ 校准不闭环 → players 快照加 `q=len(p['queue'])` 对账：客户端队头规则之外，按 q 截断/校正 dirQ，显式覆盖 955-959/723/1761 清队路径。
2. 批13③ send 失败（serve.py:1312-1314）改调 `leave_room(sess, hard=False)`，禁止手写 pid 清理（否则绕过 off_at/resumable → 重连变新蛇、幽灵实体、房间永不回收）。
3. 批14② protected 进入拦截否决裸 force_right → 本帧 skip_move（复刻 1024 模式；改 dir 本帧照样 1027 插头，且 723 清队反噬批13）。
4. 批14 加破僵局机制：同格同向 ≥2 tick 判死或确定性 tie-break（head_on 每 tick 重建 908，「跳过已 head_on」和 spawn 修复都破不了永久死锁）。
5. 批14④ off_at 排除精确限定在 970-978（咬）+ 926-929（顶头）；`_solid`/`free_cells`/`check_win(728)` 不动；`resume`(549-554) 加位置复核，冲突则 fresh spawn。
6. 批15① 可达性改「静态地形可达集 + 失效缓存」（失效点：build_terrain/maybe_rocks/岩石摧毁1196），按 MAP_MAX=96（9216格）估成本，删「重掷 N 次」，加 <5ms 计时断言。
7. 批18 放弃「立即 new_round」→ **live 生效**（check_win/快照 1260-1261 现读现发，零协议改动）+ `set_bots()` 显式增减；鉴权用 `sess.user`（owner==sid 重连即失效，1611/1711）。
8. 批13/14 补自动化验证：批14 ≥7 例先红后绿 + 小图 6-8 bot 30s 活性压力（断言无同格 ≥3 tick）；批13 服务端单测（monkeypatch ws.send 抛异常 → 断言 off_at → 重连 resume 命中）。

**建议采纳**：A2 local_ci.ps1 **前移为批13 前置**（批19 只留清理+部署+回滚）；「spawn 避开 food」划归批14；批15 bonus 用 `min(dist)` 目标选取；批17 补「折返遇岩石照死」第4用例；批19 补回滚预案；批16 color-scheme 限定作用域。
**已知限制（记录不修）**：1296/1469 增量帧丢失靠重连全量自愈；persist 的 owner-sid 既有缺陷；磁铁1151 可拉入不可达口袋。
**修正断言**：portal「恒东」真因是 900-905 `o>bo` 严格大于+方向序首项+cap=24 平局（非 561 恒0）→ 批14⑤ 先写复现用例再改。

## 批次划分与排序（理由）

| # | 批 | 覆盖 | 排序理由 |
|---|---|---|---|
| 12.5 | A2 本地 CI 脚本 | local_ci.ps1（前置，oracle 建议） | 批13-18 共 6 轮回归全靠它，先建工具 |
| 13 | D 方向失控 | 客户端 dirQ 校准 + 回合复位 + 服务端 ghost 订阅清理 | 最高频痛点；解锁「方向输入可靠」这一基础，后面批次的 E2E 手动验证都依赖它 |
| 14 | F 碰撞卡叠 | spawn 兜底检查 + protected 进入拦截 + 同格死锁解 + portal 出口修正 + off_at 障碍语义 | 与 D 同属核心手感；根因已全部定位，服务端集中改 step/spawn |
| 15 | C AI 吃水果 | place_food 可达性 + bot 简单绕行 + spawn 不压 food + bonus 优先级调权 | 依赖 14 的 spawn 修正（同一函数），故排其后 |
| 16 | B + G 小前端 | select 下拉暗色 + 死亡屏观战按钮 | 两项都小且互不相干，合一批省一轮回归 |
| 17 | H 外墙偏转选项 | Room walldeflect 参数 + 判死分支 + 建房控件 + 单测 | 新功能，依赖批14 的碰撞语义稳定 |
| 18 | E 房间参数编辑 | roomcfg 消息 + 房主鉴权 + 面板复用 | 最大新功能，放功能批最后 |
| 19 | A2 + A3 + 上线 | local_ci.ps1 + 服务器清理 + 全量回归 + git archive 部署 8090 + 生产验证 | 收尾批；上线必须在全部功能回归后 |

## 执行状态（第二轮）

| 批 | 状态 | commit | 回归证据 |
|---|---|---|---|
| 12.5 A2 本地 CI | ✅ | db83653 | local_ci.ps1 基线全绿 |
| 13 D 方向失控 | ✅ | b5e9759 | 单测 69 + 8 E2E + 静态 + Playwright 全绿 |
| 14 F 碰撞卡叠 | ✅ | 本 commit | 单测 79（+10 新例，旧码 9 红）+ local_ci ALL GREEN（8 E2E/静态/Playwright 3/3） |
| 15 C AI 吃水果 | ⬜ 下一批 | | |
| 16 B+G 下拉暗色+死亡观战 | ⬜ | | |
| 17 H 外墙偏转选项 | ⬜ | | |
| 18 E 房间参数编辑 | ⬜ | | |
| 19 A3+部署上线 | ⬜ | | |

> 批14 踩坑记录：spawn 主路径 `_solid`→`occupied` 替换引入 OOB 回归（`occupied()` 无界检查，贴边出界 spawn 被 `_open_ahead` 高分开选中）→ P5 E2E 抓出（resume 位置复核 `RCONF oob` 插桩定位）→ 修法为 `occupied()` 顶部补「出界即占用」（其余 3 个调用点坐标恒界内，零行为变化）。诊断插桩已全部移除（grep RCONF clean）。

## 各批技术方案（要点）

- **批12.5（A2 前移）**：`scripts/local_ci.ps1`——停服清库→起双服(28000/8090)→8 E2E→单测→停服清库→静态检查→起 8123→Playwright 3/3→汇总 Exit code。批13-18 每批跑它。
- **批13**：① dirQ 精确重同步——players 快照加 `q=len(p['queue'])`，客户端 applyPlayers 对账：队头===myEnt.dir 或反向则 shift（保留现有规则），然后 `if (dirQ.length > q) dirQ = dirQ.slice(0, max(q,0))`... （**按必改1 修订**：以服务端 q 为权威长度校正本地镜像，覆盖 955-959 清队/723 clash 清队/1761 队满丢新项——队满丢的是队尾新项，故截尾；955-959 整队清空 → q=0 全清；clash 同理）；② `handleRound`/`'round'`/onWin else 分支强制 `dirQ=[]`；③ serve.py:1312-1314 send 失败改调 `leave_room(sess, hard=False)`（**必改2**：保留 off_at/resumable 语义，禁手写 pid 清理）；④ setDir 前置门控 wsOpen（send 返回 void 无法回滚，改为不 push 未发出的项）。
  - 验证（必改8）：服务端单测 monkeypatch ws.send 抛异常 → 断言 sess 进 off_at → 重连 resume 命中同 id；客户端 dirQ 收敛用单测级断言（test_game.py 无法覆盖 JS → 用 Playwright 或静态审查 + E2E 实玩）。
- **批14**：① spawn 兜底分支改 free_cells 安全点（**含避开 food**，划归本批）；② protected 进入拦截 = 本帧 skip_move（复刻 1024 模式，**必改3**：禁裸 force_right）；③ head_on 跳过已 head_on 的蛇（防双重右转）；④ **破僵局（必改4）**：同格同向 ≥2 tick → 确定性 tie-break 判死（按 pid 序留一死一，或强制方改向）；⑤ off_at 排除精确限定 970-978 咬 + 926-929 顶头，_solid/free_cells/check_win 不动，**resume 549-554 加位置复核冲突则 fresh spawn**（必改5）；⑥ portal 出口：**先写复现用例**再改（真因候选 = 900-905 `o>bo` + cap=24 平局偏东，非 561）；出口格 occupied → skip_move 一帧（须防 1027 重复插格）；⑦ 尸体已全面过滤 → 不改。
  - 验证（必改8）：≥7 例先红后绿 + 小图 6-8 bot 30s 活性压力（断言无同格 ≥3 tick）。
- **批15**：① place_food 可达性 = **静态地形可达集 + 失效缓存**（必改6：失效点 build_terrain/maybe_rocks/1196 岩石摧毁；从活蛇头 flood-fill 到 food 格，MAP_MAX=96 → 9216 格 BFS，加 <5ms 计时断言；删除「重掷 N 次」）；② _bot_think 绕行：直路被挡选「与被挡方向最接近的开放方向」；③ bonus 优先改 `min(dist)` 目标选取（food/bonus 统一按 dist 排序）；④ spawn 避 food 不在本批（已划归批14）。TDD：围死格不放、BFS 计时、bot 绕障用例。
- **批16**：B=`select{color-scheme:dark}` **限定作用域**（仅建房/房间设置面板内 select）+ option 暗色兜底；G=overScreen 加「观战」→ spectate()，wantPlay=false 衔接。
- **批17**：`Room.walldeflect`（建房 `walldeflect:bool`，info/snapshot 下发）；947 wall 判死前若 walldeflect → 复用 _deflect_dir（无路照死）；岩石/自己/咬<2 不变；建房 checkbox「撞墙反弹」；单测 4 例：墙不死反弹/岩石照死/咬<2 照死/**折返遇岩石照死**（oracle 补充）。INFO：walldeflect 房 deflect 道具冗余（接受）；_deflect_dir 1082-1084 未排除他人身体（观察，坏则下批修）。
- **批18**：新消息 `roomcfg`，**live 生效（必改7）**——win_mode/limit/respawn/bots/walldeflect 即时生效（check_win/快照 1260-1261 现读现发零协议改动）；bots 变更用 `set_bots()` 显式增减（add_bots 仅构造时调用）；鉴权 `sess.user`（禁 owner==sid，重连失效）；**不 new_round**（避免重掷地形/清比分坑）；theme 不 live 改（记入已知限制：改主题下局生效）。边界拍板：limit 改小→到点即时结算（夹取 ≥1s）；score 模式改 win_mode 后按新规则结算。client 房间内「房间设置」复用建房控件。
- **批19**：A3 清 /tmp/*.py + 部署目录 .bak（保留 predeploy tar）；`git archive dev` 部署 + restart + 生产验证（200/delta 探针/journal 无 error）；**回滚预案（必补）**：生产验证失败 → `tar xzf snake-3d-predeploy-*.tar.gz -C /home/ubuntu/snake-3d` + restart。

## 回归与验收（每批）

每批跑 `scripts/local_ci.ps1`（批12.5 建）：单测 test_game.py 全绿（批17/18 先红后绿）+ 8 套 E2E Exit 0（停服清 persist_rooms.json）+ 静态检查 ALL PASSED + Playwright 3/3（8123）。批19 收尾 → 部署生产 8090 → curl/journal/delta 探针 → 失败走回滚预案。

## 不做

- 不 push（部署用本地 git archive，与前两轮一致——用户指令是"上线"即部署生产，push 未被要求）。
- 不重构渲染/协议大结构；不做 ESM 改造（已拍板维持 r160 UMD）。
- 方向失控的「服务端 dir 回执协议」（dir-rej 消息）不做——用快照 q 对账 + 客户端校准替代（改动面小，且 q 字段仅 1 字节不算消息协议）。
- 已知限制（记录不修）：增量帧 1296/1469 丢失靠重连全量自愈；persist owner-sid 既有缺陷；磁铁 1151 可拉入不可达口袋；theme live 修改（下局生效）。


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
  **（批10 实拍）**：r128→**r160**（0.160.0 是最后带 UMD `three.min.js` 的版本，0.161 起仅 cjs/module）；同主题 A/B 对比后**用户拍板采用 r160 新 sRGB 色彩管理默认观感**（棋盘亮度+24%/饱和−34%/格纹对比−40%，可交付），不锁旧观感、不改主题配色。
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
| 10 | three.min.js 升级 | C4 | ✅ | r128→r160（最后带 UMD 版本）；Playwright 3/3 passed (7.0s)；单测 67/67；静态 ALL PASSED (71ids/div33/css159/js528)；7 E2E ALL PASSED；同主题 A/B observer 对比无破损，观感按用户拍板采用 r160 新默认 |
| 11 | 快照增量协议 | C1（压轴） | ✅ | 新 test_delta_p1.py 一次通过：首帧 full(620B)/增量帧均 428B（−31%）/walls、portals 稳态 30/30 缺席/中途 watch 者首帧仍全量；单测 67/67；静态 ALL PASSED (71ids/dup0/div33/css159/js531)；8 套 E2E ALL PASSED（新增 delta 套件）；Playwright 3/3 passed (7.5s) |
| 12 | 计划外：灰化+报表+评估+文档 | 用户追加 4 项 | ✅ | 灰化 applyOffTint/off+💤；报表每小时峰值曲线+房间热度实测出数；ESM 评估=维持 r160；DEPLOY.md 补功能版本节。回归：单测+8 E2E+Playwright 3/3 (7.8s)+静态 (js533) |

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

### 批10 three.min.js 升级（C4）✅
- **版本核实**：jsdelivr flat API 探测——r160（npm `0.160.0`）是**最后一个带 UMD `three.min.js`** 的版本（0.161.0 起仅 `three.cjs`/`three.module*`）；最新 three 为 0.186.1。替换文件：下载 `three@0.160.0/build/three.min.js`（669,884 B，`REVISION="160"`，`node --check` 过），`<script src="three.min.js">` 引用方式不变。文件头自带 r150+ deprecation console.warn（仅 warning 不影响冒烟）。
- **API 面核查**：index.html 所用 three API 全为现代稳定类（BufferGeometry/MeshStandardMaterial/PlaneGeometry/CatmullRomCurve3/ExtrudeGeometry/Sprite/Points/Fog/PCFShadowMap），无 outputEncoding/physicallyCorrectLights 等已删 API；未显式设置色彩空间 → r160 新默认（sRGB 输出 + ColorManagement）接管。
- **渲染回归（同主题 A/B）**：临时脚本（`$env:TEMP\ab_shot.js`，不入库）固定 `theme=default`+3AI 建房入局截图 r160/r128 各一张。**关键坑**：手动建房只选中房间，须再点 `#btnStart` 才入局（单人练习才有 soloPending 自动 start）。observer 量化：色相零回归（上轮红↔teal 翻转系随机主题干扰）、UI 分区 diff=0、无过曝无破损；变化=棋盘亮度+24%/饱和−34%/格纹对比−40%（sRGB 色彩管理预期效应）。
- **拍板**：问用户三选一 → **采用 r160 新默认（零改动）**，不锁 ColorManagement 旧观感、不改 THEMES 配色。
- **验证**：Playwright 3/3 passed (7.0s)（含 canvas 非空断言+无 console.error）；单测 67/67 ALL PASSED；静态 ALL PASSED (ids=71 dup=0 div=33/33 css=159/159 js=528/528)；7 套 E2E ALL PASSED。
- **暴露的新工作**：r161+ 若再升级需 `<script type="module">` 改造（已记 HANDOVER 技术债 #9）；**顺序调整**：无。

### 批11 快照增量协议（C1，压轴）✅
- **方案（零插桩签名对比）**：不在每个修改点插 dirty 标志（改点多易漏），改为 `Room.snapshot(now, full=False)` 时对 6 个静态字段（food/bonus/rocks/walls/portals/items）做 `json.dumps` 签名与上次下发值对比，变了才带进增量帧并更新 `_field_sig` 缓存；players/proj/标量（round/cols/winMode/remain/ev…）每帧恒在。**per-订阅者全量**：`Session.full_sent` 标志，join/watch/resume 三处订阅点置 False，`broadcast()` 发现有未全量者时补组一份 `full=True` 帧（含 6 字段 + `full:1` 标志，且**先算增量再算全量**避免签名被提前刷新）。新加入者/重连恢复者首帧必全量 → 旧测试直接取 `snap["walls"]`/`snap["items"]` 的写法不破。
- **客户端（index.html applyWorld）**：6 个静态字段全部改 `s.X !== undefined` 才处理——缺失=沿用旧值（原来 `else if (food)` 等清空分支只在字段明确下发时执行）；proj 每帧恒在保持 `s.proj || []`。
- **新测试 test_delta_p1.py（第 8 套 E2E）**：join 'a' 首帧断言 6 字段齐全+full==1；连收 30 帧断言 walls/portals 缺席 ≥25/30（稳态 30/30）且 players/proj 每帧恒在；第二个 ws watch 后其首帧仍全量。CI round 2 步骤追加 `python test_delta_p1.py`（8 套）。
- **验证**：`PY_COMPILE OK`；test_delta 一次通过（first=full 620B / avg_delta=428B，−31%）；单测 67/67 ALL PASSED；8 套 E2E 全 Exit 0（含重连/口令/bots 关键路径在增量协议下正常）；静态 ALL STATIC CHECKS PASSED (ids=71 dup=0 div=33/33 css=159/159 js=531/531，js +3 系 applyWorld 新增 3 个字段守卫块)；Playwright 3/3 passed (7.5s)。
- **暴露的新工作**：无；**顺序调整**：无。**注意**：`broadcast()` 无订阅者时仍调增量 snapshot 以清 events/刷签名（与旧行为一致），新订阅者靠 full_sent 补全量，语义闭环。

### 批12 计划外追加（灰化 + 报表 + ESM 评估 + 文档）✅
- **① 挂起蛇灰化（批5 砍项回收）**：makeEnt 加 `off:false`；新 `applyOffTint(e)`——`bodyMat.color` 0x5a5a5a（贴图乘灰罩）+ skull 压灰，恢复白色；paintEnt 末尾统一重应用（皮肤切换不丢灰化）；applyPlayers 首建/更新两分支同步 `e.off = !!p.off`，变化才重涂；名字标签加 ` 💤` 后缀（syncEnt nameSprite 处）。验证：test_reconnect_p5 E2E（断线挂起→恢复）全绿。
- **② 用量报表增强（纯 report 端，serve.py 零改动）**：usage_report.py 从 usage.log(+.1) 明细聚合——conn/session(sid 配对) 重建并发连接数，按小时桶取峰值输出「每小时在线峰值」24 行柱状图（未闭合连接延续到现在）；join/win 聚合「房间热度」（进房/会话/胜局 TOP15）。本地实测出数（20:00 峰值 4、22:00-00:00 峰值 6；r3 进房 9）。
- **③ three r161+ ESM 评估（结论：维持 r160）**：已核实 index.html 无 inline onclick → ESM 改造技术可行（主脚本包 boot + module import THREE 后触发）；但新版本特性（WebGPU 等）本项目用不到，改造需 2130 行作用域包裹 + 全量视觉回归重做——收益低风险中。已写入 HANDOVER 技术债 #9。
- **④ DEPLOY.md 刷新**：文件位置树更新（data/、vendor r160 说明）+ 新增「当前功能版本」节（11 批功能清单 + 协议/CI/报表一段，指向 HANDOVER）。
- **验证**：单测 67/67 ALL PASSED；8 套 E2E 全 Exit 0（delta: first=full 680B/avg_delta 424B）；Playwright 3/3 passed (7.8s)；静态 ALL PASSED (71ids/dup0/div33/css159/**js533**，+2 系 applyOffTint)。
