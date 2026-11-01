# 贪吃蛇 3D 多人对战（snake-3D）

基于 **Python websockets + 原生 JavaScript + Three.js** 的 3D 多人大厅对战贪吃蛇。
单进程同时提供 HTTP 静态站与 WebSocket 实时对局，前端零构建、零框架依赖。

## 特性

- **3D 垂直地形**：高度图地形（平原/水面/草丛/深渊 -9）、撞崖与坠亡物理、断尾求生；
  「宏伟」档高山巨图（最高山峰 h18、128×128 巨无霸地图）
- **多人大厅**：多房间、观战、断线重连、延迟 delta 增量同步、房间列表与自定义地图尺寸
- **道具与元素反应**：shield / speed / ghost / magnet / double / rage / deflect 七种道具
- **养成与外观**：通行证、祈愿抽卡、皮肤系统（模型皮肤、头环、站姿）
- **AI 对手**：Dijkstra 寻路 bot，可与真人同房混战
- **社交**：房间聊天、表情反应
- **可运维性**：死亡遥测落盘（usage.log）、systemd 部署、一键全量门禁 CI

## 快速开始

```bash
pip install websockets
python serve.py
# 浏览器打开 http://localhost:20000/
# 端口可用环境变量覆盖：PORT=8090 python serve.py
```

前端为单页 `index.html` + `three.module.min.js`（ES Module 直载），无需打包。

## 开发与测试

```bash
# 单元测试（约 200+ 用例）
python test_game.py

# 浏览器端 E2E（Playwright）
npm ci
npx playwright test

# 全量门禁（停服→双端口→12 套 WS E2E→单测→静态检查→Playwright）
pwsh -File scripts/local_ci.ps1
```

## 项目结构

| 路径 | 说明 |
|---|---|
| `serve.py` | 服务端：HTTP + WebSocket + 房间/回合/地形/物理（单文件） |
| `index.html` | 前端：Three.js 场景、UI、预测与同步（单文件） |
| `three.module.min.js` | Three.js 渲染库 |
| `e2e/` | Playwright 浏览器 E2E（19+ spec） |
| `test_*.py` | 服务端 WS/物理/地形回归测试 |
| `scripts/` | 全量 CI、静态检查、生产验收探针 |
| `docs/` | 设计 spec、实施计划、存证截图 |
| `BACKLOG.md` / `HANDOVER.md` / `DEPLOY.md` | 批次开发记录 / 交接与部署运维 |

## 部署

生产部署流程（备份 → `git archive` 投放 → 重启 → sha/握手核验）见 `HANDOVER.md` §11，
服务器要求见 `DEPLOY.md`。

## 许可

[MIT](LICENSE)
