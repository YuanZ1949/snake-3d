# CloudServer 验收证据

（本文件由 tamako 续跑插件的数据修复创建：原 `contract.json` 用的是自造字段 (`not_do` / `status` / `phase`，`acceptance[]` 是纯字符串数组)，插件读不了、续跑会空转。现已按 8 字段 schema 迁移，`verdict` 一律置 `pending`（原文没有任何通过证据，不代替模型判定）。原文件逐字保留在下方。证据请追加到本文件，不要写回契约文件。）

原进度：`status` = "in_progress"，`phase` = "T1 开工"

---

## 批33 结项证据（2026-10-19 记，契约 3/3 pass，state=closed）

> 注：按 schema 规则，`acceptance[]` 只保留 `id/text/verdict`，证据一律写在本文件（`contract.json` 里曾多出 `evidence` 字段导致续跑报 `acceptance[0] has unknown field(s): evidence`，已剥离）。下列 ①②③ 与契约三条验收一一对应。

**① `pwsh scripts/local_ci.ps1` → `ALL GREEN — 本地 CI 全部通过`（结项前复跑，EXIT=0）**
- 9 套 python E2E 全 Exit 0，含新增 `test_reactions_p33.py` → `reactions E2E PASS`（5 断言）
- 单测 `ALL GAME UNIT TESTS PASSED`（183 用例注册即跑，批33 +21 项 `*_batch33`）
- 静态检 `node scripts/static_check.js index.html` → `ids=135 dup=0 div=69/69 css=350/350 js=878/878` + `ALL STATIC CHECKS PASSED`
- Playwright `39 passed`（13 个 spec，含新增 `e2e/reactions.spec.js` ×4）

**② PROTO_VER=29 双端 + 生产复验 + 视觉判据**
- `serve.py:48` `PROTO_VER = 29`；`index.html:1128` `const PROTO_VER = 29`
- 部署：`scp index.html serve.py tencent:/home/ubuntu/snake-3d/`（静态每次读盘，仅 index 增量无需重启）+ `sudo systemctl restart snake-3d` → `systemctl is-active snake-3d` = `active`，`http://193.112.172.83:8090` 返回 200
- `BASE=http://193.112.172.83:8090 npx playwright test e2e/reactions.spec.js e2e/smoke.spec.js` → `9/9 passed`；`--repeat-each=6` → `18/18`
- `node prod_verify.js` → `PROTO_VER room-ok ver=29 (29 OK)` / `errs=[]`（console+pageerror+ws error 全空）/ `PROD VERIFY PASS`
- 视觉：`test-results/p33_attach_react.png`（279KB，生产运行产出）肉眼可见顶部元素 HUD 4 按钮（🔥/💧/❄/⚡）+ 棋盘「冻结」反应浮字 + P 名牌 + 小地图；用户另发生产截图同样可见 HUD 四键与「冻结」浮字（m0164 回「继续」=确认存证）。附着/浮字为 3D 无 DOM，断言走探针 `__auraDbg().e==='cryo'`、`__floatDbg()` 递增。

**③ 文档回写**
- `HANDOVER.md`（§1/§2/§5.1/§5.2/§6.1/§6.2/§10/§13 + 头部日期与基线）
- `BACKLOG.md` 新增「## 批33（2026-10-19 · 原神元素反应）已完成」（`git diff --stat` = 13 insertions 纯插入）

```json
{
  "goal": "批33 原神元素反应：按 docs/superpowers/plans/2026-10-18-element-reactions.md 完成 10 任务实现（T1-T10），PRO 双端，E2E+门禁+部署+生产复验+文档回写",
  "acceptance": [
    "pwsh scripts/local_ci.ps1 → ALL GREEN（含新单测先红后绿、E2E、静态检）",
    "PROTO_VER=29 双端一致；scp 部署后生产进局 errs=[] 且元素 HUD/附着/反应浮字可见",
    "HANDOVER.md / BACKLOG.md 回写批33 完成记录"
  ],
  "not_do": [
    "不改既有玩法数值（ULT_KILL/水减速/批32弹道）",
    "不做 spec 外重构与 Deferred 项",
    "不改 opencode 配置"
  ],
  "flow": "直通（writing-plans 已产出 10 任务计划，按 executing-plans 逐任务执行；任务间接口由计划锁定）",
  "status": "in_progress",
  "phase": "T1 开工"
}
```


---

## 批34 地形遮挡（2026-10-19）· flow=直通 · 3/3 PASS

### ① 先红后绿（height32.spec.js 新增「批34 地形遮挡」用例）
- 红：\\='http://127.0.0.1:20000'; npx playwright test height32 --grep '批34' → 失败 height32.spec.js:63「kind=c1 必须写深度」Received false（真红）
- 绿：改材质后 npx playwright test height32 → 4 passed（19.5s）

### ② 全量门禁
- node scripts/static_check.js index.html → ids=135 dup=0 div=69/69 css=350/350 js=879/879 + ALL STATIC CHECKS PASSED
- pwsh scripts/local_ci.ps1 → ALL GREEN：单测 183 ALL GAME UNIT TESTS PASSED、静态检 PASS、Playwright 40 passed、python E2E test_reactions_p33.py PASS

### ③ 生产部署
- scp -i C:\\Users\\yuan\\.ssh\\1.pem index.html ubuntu@193.112.172.83:/home/ubuntu/snake-3d/index.html → SCP_EXIT=0
- 远端 grep -c '批34' = 4；PROTO_VER = 29（未变 → 服务端无需重启）

### ④ 生产遮挡视觉存证（临时探针 _tmp_occl_shot.js：注册→单人局→暂停冻结→身后注入 h=12 高墙→截图 A→清空→截图 B）
- PAUSED=true；CAM={x:7.5,y:5.4,z:-3.51,snake:{x:8,y:8},dir:{x:-1,y:0}} → 相机 cell≈19、蛇 cell=8、墙 cells x=11..13 正好在视线中间
- WALLCELLS=21 meshesA=21 dwAllTrue=true
- CONSOLE_ERRS=[]（无新增 console 错误）
- 截图：test-results/occl_prod_A_wall.png（高墙充满视野、蛇完全不可见）／ occl_prod_B_nowall.png（清空地形后棋盘地板+绿色蛇身清晰可见）→ 山后之蛇被正确挡住
