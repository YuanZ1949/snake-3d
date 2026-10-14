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
| 2 | 大招+偏转+护盾 | A6 + 新#1 + 新#7 | ⬜ | |
| 3 | 传送门+资源有效期 | 新#2 + 新#6 | ⬜ | |
| 4 | AI蛇+单人模式 | A4 + 新#5 | ⬜ | |
| 5 | 重连+聊天 | B2 + B3 | ⬜ | |
| 6 | 弱口令+房间保留/保存 | C3 + 新#11 | ⬜ | |
| 7 | 客户端视觉 | 新#3 丝滑移动 + 新#4 白天主题 + 新#9 边缘图标 + 新#10 面板风格 | ⬜ | |
| 8 | 小地图+观战切换+移动端 | B1 + 新#8 + B4 | ⬜ | |
| 9 | CI/Playwright | C2 | ⬜ | |
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
