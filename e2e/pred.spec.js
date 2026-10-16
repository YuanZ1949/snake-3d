// 批28 C：自机预测探针（spec §7.1）
// 纪律：gate 开 → 注入 → 断言状态 → gate 关；断言状态而非帧时刻（真实 snap 流被 gate 隔离）
const { test, expect } = require('@playwright/test');

// 等 n 个 rAF（让帧钩子跑几拍；断言本身只依赖状态判据）
const rafN = (page, n) => page.evaluate(async k => {
  for (let i = 0; i < k; i++) await new Promise(r => requestAnimationFrame(r));
}, n);

// 轮询 __predState 直到谓词成立（状态判据；超时返回末次状态交给断言去红）
async function waitPred(page, pred, timeoutMs = 4000) {
  const t0 = Date.now();
  let st = await page.evaluate(() => window.__predState());
  while (Date.now() - t0 < timeoutMs && !pred(st)) {
    await page.waitForTimeout(50);
    st = await page.evaluate(() => window.__predState());
  }
  return st;
}

// 注入件公共壳：空世界字段保证预测空间确定（applyWorld 各字段均有 !==undefined 守卫 :2267-2344）
const snapShell = st0 => ({
  t: 'snap', round: st0.round, cols: st0.cols, rows: st0.rows,
  walls: [], portals: [], rocks: [], foods: [], bonus: null,   // bonus 必须是 null（[] 为 truthy 会造出 garbage bonus）
});

// 基准 snap：蛇 [[10,12],[9,12],[8,12]] 头朝东；q = 声明的服务器在途队列长
const baseSnap = (st0, q = 0, alive = true) => ({
  ...snapShell(st0),
  players: [{
    id: st0.id, name: 'P', skin: st0.skin, cells: [[10, 12], [9, 12], [8, 12]], dir: [1, 0], len: 3,
    q, tick: 150, alive, score: 0, eff: {}, off: false,
  }],
});

async function joinSolo(page) {
  await page.goto('/');
  await page.click('#btnSolo');
  await page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 15000 });
  // 固定视角才吃绝对方向键：跟随视角下 ArrowUp(x=0) 被 setDir:2129 丢弃（先例 smoke.spec.js:103-104）
  await page.click('#btnCam');
  await expect(page.locator('#btnCam')).toHaveText('🧭固定');
}

test('T1 本地预测激活与预览不回退', async ({ page }) => {
  await joinSolo(page);
  const st0 = await page.evaluate(() => window.__predState());
  expect(st0.id, '载具前置：已入局拿到自机 id').not.toBeNull();
  await page.evaluate(() => window.__predGate(true));
  await page.evaluate(s => window.__gachaDbg(s), baseSnap(st0, 0));
  // 基准 dir=E，↑ 非反向；须在首拍（注入 +150ms）前入 dirQ
  await page.keyboard.press('ArrowUp');
  const st1 = await waitPred(page, s => s.active && s.leadCells >= 1);
  expect(st1.active).toBe(true);
  expect(st1.leadCells).toBeGreaterThanOrEqual(1);
  // NEW-B2：预览/已消费方向不被基准 snap 撤销（q=1 = 服务器尚未确认的在途 ↑，重放可复现转向）
  await page.evaluate(s => window.__gachaDbg(s), baseSnap(st0, 1));
  const st2 = await page.evaluate(() => window.__predState());
  expect(st2.previewDir).toEqual({ x: 0, y: -1 });
  expect(st2.moveDir).toEqual({ x: 0, y: -1 });
  // Review Focus 3：seamless 分支必须还原四元组（proj.cells 不被 applyPlayers 覆盖回摆）
  await page.evaluate(s => window.__gachaDbg(s), baseSnap(st0, 1));
  const st3 = await page.evaluate(() => window.__predState());
  expect(st3.proj.cells).toEqual(st3.cells);
  await page.evaluate(() => window.__predGate(false));
});

test('T2 矛盾 snap 回滚收敛', async ({ page }) => {
  await joinSolo(page);
  const st0 = await page.evaluate(() => window.__predState());
  await page.evaluate(() => window.__predGate(true));
  await page.evaluate(s => window.__gachaDbg(s), baseSnap(st0, 0));
  await page.keyboard.press('ArrowUp');
  const st = await waitPred(page, s => s.active && s.leadCells >= 1);
  // 追赶 snap：服务器到达 pred 位置（RED 期 pred 未推进 → 退回基准形状）
  const cells = st.cells ? st.cells.map(c => [c.x, c.y]) : [[10, 12], [9, 12], [8, 12]];
  const mdir = st.moveDir || { x: 0, y: -1 };
  await page.evaluate(s => window.__gachaDbg(s), {
    ...snapShell(st0),
    players: [{
      id: st0.id, name: 'P', skin: st0.skin, cells, dir: [mdir.x, mdir.y], len: 3,
      q: 0, tick: 150, alive: true, score: 0, eff: {}, off: false,
    }],
  });
  // 矛盾 snap：位置与 pred 无关且回放无法对齐 → rollback 等于该 snap
  await page.evaluate(s => window.__gachaDbg(s), {
    ...snapShell(st0),
    players: [{
      id: st0.id, name: 'P', skin: st0.skin, cells: [[3, 3], [2, 3], [1, 3]], dir: [1, 0], len: 3,
      q: 0, tick: 150, alive: true, score: 0, eff: {}, off: false,
    }],
  });
  await rafN(page, 2);
  const st2 = await page.evaluate(() => window.__predState());
  const got = st2.cells ? st2.cells.map(c => [c.x, c.y]) : null;
  expect(got).toEqual([[3, 3], [2, 3], [1, 3]]);
  await page.evaluate(() => window.__predGate(false));
});

test('T3 alive:false 停用预测', async ({ page }) => {
  await joinSolo(page);
  const st0 = await page.evaluate(() => window.__predState());
  await page.evaluate(() => window.__predGate(true));
  await page.evaluate(s => window.__gachaDbg(s), baseSnap(st0, 0));
  await rafN(page, 6);
  await page.evaluate(s => window.__gachaDbg(s), baseSnap(st0, 0, false));
  await rafN(page, 3);
  const st = await page.evaluate(() => window.__predState());
  expect(st.active).toBe(false);
  await page.evaluate(() => window.__predGate(false));
});

test('T4 predictor 固件对账（用例固件对账（用例①④②③⑤ + 悬停 + 上限 + interval + 相位守卫）', async ({ page }) => {
  await page.goto('/');   // 无需入局：纯函数直测
  const r = await page.evaluate(() => {
    const D = window.__predDbg;
    const E = { x: 1, y: 0 };
    const mk = () => [{ x: 5, y: 5 }, { x: 4, y: 5 }, { x: 3, y: 5 }];
    const world = w => ({ walls: new Set(w), rocks: new Set(), portals: new Set(), cols: 24, rows: 24 });
    const foods = new Set();
    const out = {};
    // ①④ 直线空队列：本地推进一步、服务器未动 → 回放直行 == pred → seamless 且保持领先 1
    const p1 = D.mkPred(mk(), E, 150, 0);
    D.predAdvance(p1, [], world([]), foods, {});
    out.r14 = D.predReconcile(p1, { cells: mk(), dir: { x: 1, y: 0 } }, [], world([]), foods, {});
    out.lead14 = p1.leadCells;
    // ② 被追平：server.cells == pred.cells → 位置等式递减 → seamless 且 leadCells == 0
    const p2 = D.mkPred(mk(), E, 150, 0);
    D.predAdvance(p2, [], world([]), foods, {});
    out.r2 = D.predReconcile(p2, { cells: p2.cells.map(c => ({ ...c })), dir: { ...p2.moveDir } }, [], world([]), foods, {});
    out.lead2 = p2.leadCells;
    // ③⑤ syncApplied clamp：游标差分不越界
    const pa = D.mkPred(mk(), E, 150, 0);
    pa.appliedInputs = 2; D.syncApplied(pa, 5); out.clamp5 = pa.appliedInputs;
    pa.appliedInputs = 2; D.syncApplied(pa, 1); out.clamp1 = pa.appliedInputs;
    // 悬停（§5.4）：[6,5] 为墙 → 不改 cells、lastMoveAt += interval、leadCells 不增、不消费输入
    const ph = D.mkPred(mk(), E, 150, 0);
    D.predAdvance(ph, [], world(['6,5']), foods, {});
    out.hover = {
      cells: ph.cells.map(c => [c.x, c.y]),
      lastMoveAt: ph.lastMoveAt,
      lead: ph.leadCells,
      applied: ph.appliedInputs,
    };
    // 上限（MINOR-c2）：连调两次 → leadCells ≤ 1，第二次按悬停处理不吃格
    const pc = D.mkPred(mk(), E, 150, 0);
    D.predAdvance(pc, [], world([]), foods, {});
    const after1 = JSON.stringify(pc.cells.map(c => [c.x, c.y]));
    D.predAdvance(pc, [], world([]), foods, {});
    out.cap = {
      lead: pc.leadCells,
      same: JSON.stringify(pc.cells.map(c => [c.x, c.y])) === after1,
    };
    // interval：speed 道具不改 tick，×0.6 下限 60 → floor(150*0.6)=90
    out.interval = D.predInterval(150, { speed: 2000 });
    // ⑧ 相位守卫（spec v5 :80 + 批29① 收紧：仅"等式递减转移"当拍允许重锚）
    const pp = D.mkPred(mk(), E, 150, 150);                       // lastMoveAt=150
    D.predAdvance(pp, [{ x: 0, y: -1 }], world([]), foods, {});   // 消费 ↑ → lead=1、lastMoveAt=300、moveDir=N
    out.rLead = D.predReconcile(pp, { cells: mk(), dir: { x: 1, y: 0 }, at: 1000 }, [{ x: 0, y: -1 }], world([]), foods, {});
    out.lmLead = pp.lastMoveAt;
    // 初态/等待态（lead==0 从未推进）+ at：不得重锚——水平触发即死锁（T5 回归网）
    const p0 = D.mkPred(mk(), E, 150, 150);
    out.rZero = D.predReconcile(p0, { cells: mk(), dir: { x: 1, y: 0 }, at: 1000 }, [], world([]), foods, {});
    out.lmZero = p0.lastMoveAt;
    // ⑧b 等式递减转移（lead 1→0）+ at：超过阈值重锚、阈值内不动（服务器刚追平的唯一合法重锚窗口）
    const pa2 = D.mkPred(mk(), E, 150, 150);
    D.predAdvance(pa2, [], world([]), foods, {});   // lead=1、lastMoveAt=300、cells=[6,5]…
    out.rCatch = D.predReconcile(pa2, {
      cells: pa2.cells.map(c => ({ ...c })), dir: { ...pa2.moveDir }, at: 1000,
    }, [], world([]), foods, {});
    out.lmCatch = pa2.lastMoveAt;
    const pa3 = D.mkPred(mk(), E, 150, 150);
    D.predAdvance(pa3, [], world([]), foods, {});
    out.rCatchNear = D.predReconcile(pa3, {
      cells: pa3.cells.map(c => ({ ...c })), dir: { ...pa3.moveDir }, at: 310,
    }, [], world([]), foods, {});
    out.lmCatchNear = pa3.lastMoveAt;
    return out;
  });
  expect(r.r14).toBe('seamless');
  expect(r.lead14).toBe(1);
  expect(r.r2).toBe('seamless');
  expect(r.lead2).toBe(0);
  expect(r.clamp5).toBe(0);
  expect(r.clamp1).toBe(1);
  expect(r.hover.cells).toEqual([[5, 5], [4, 5], [3, 5]]);
  expect(r.hover.lastMoveAt).toBe(150);   // mkPred(now=0) 悬停拍 → 0+150：证明 lastMoveAt += interval（§5.4），不动才是 bug
  expect(r.hover.lead).toBe(0);
  expect(r.hover.applied).toBe(0);
  expect(r.cap.lead).toBe(1);
  expect(r.cap.same).toBe(true);
  expect(r.interval).toBe(90);
  // 用例⑧：lead>0 时 at 不得重锚（oracle 终审 Critical 回归网）；批29①：等待态（lead==0 未转移）同样不重锚
  expect(r.rLead).toBe('seamless');
  expect(r.lmLead).toBe(300);
  expect(r.rZero).toBe('seamless');
  expect(r.lmZero).toBe(150);
  // ⑧b：仅等式递减转移当拍——阈值外重锚到 at、阈值内保持推进相位
  expect(r.rCatch).toBe('reanchor');
  expect(r.lmCatch).toBe(1000);
  expect(r.rCatchNear).toBe('seamless');
  expect(r.lmCatchNear).toBe(300);
});

// ===== 批29 ① 卡顿根因回归（真实 50ms snap 节奏；本地实证 lead 0/75、lastMoveAt 每 snap 被拉回、投影退化 50/75）=====

// 单 snap 构建 + 等 pred 自身时钟推进（gate 隔离真实流 → 无连注干扰）
async function buildAndAdvance(page, st0) {
  await page.evaluate(() => window.__predGate(true));
  await page.evaluate(s => window.__gachaDbg(s), baseSnap(st0, 0));
  const st = await waitPred(page, s => s.active && s.leadCells >= 1, 3000);
  expect(st.leadCells, '单 snap 后 pred 应按 150ms 自身时钟推进').toBeGreaterThanOrEqual(1);
  return st;
}

const playerOf = (st0, cells, dir) => ({
  ...snapShell(st0),
  players: [{
    id: st0.id, name: 'P', skin: st0.skin, cells, dir, len: 3,
    q: 0, tick: 150, alive: true, score: 0, eff: {}, off: false,
  }],
});

test('T5 50ms snap 节奏下 pred 按自身时钟推进（相位重锚死锁回归）', async ({ page }) => {
  await joinSolo(page);
  const st0 = await page.evaluate(() => window.__predState());
  await page.evaluate(() => window.__predGate(true));
  await page.evaluate(s => window.__gachaDbg(s), baseSnap(st0, 0));   // 首注 = 建基准
  // 断言窗口 = 连注期内（实证 trace：死锁期 lead 恒 0；停注后因不再重锚会自然推进，
  // 所以宽限必须在窗口外拿不到判别力 → 每拍注入前采样 lead）
  let maxLeadInCadence = 0;
  let lastCellsInCadence = null;
  for (let i = 0; i < 8; i++) {
    const before = await page.evaluate(() => window.__predState());
    maxLeadInCadence = Math.max(maxLeadInCadence, before.leadCells);
    if (before.cells) lastCellsInCadence = before.cells.map(c => [c.x, c.y]);
    await page.evaluate(s => window.__gachaDbg(s), baseSnap(st0, 0));
    await page.waitForTimeout(50);
  }
  expect(maxLeadInCadence, '连注期间（>150ms 到期线）pred 必须推进过——重锚不得水平拉回相位').toBeGreaterThanOrEqual(1);
  expect(lastCellsInCadence[0], '基准头 E → 本地推进一格').toEqual([11, 12]);
  await page.evaluate(() => window.__predGate(false));
});

test('T6 追赶后空闲 snap 不拉相位（等式递减转移才允许重锚）', async ({ page }) => {
  await joinSolo(page);
  const st0 = await page.evaluate(() => window.__predState());
  const st = await buildAndAdvance(page, st0);
  const predCells = st.cells.map(c => [c.x, c.y]);
  const md = st.moveDir;
  // 追赶 snap：服务器到达 pred 位置 → 等式递减 1→0 转移
  await page.evaluate(s => window.__gachaDbg(s), playerOf(st0, predCells, [md.x, md.y]));
  const afterCatch = await page.evaluate(() => window.__predState());
  expect(afterCatch.leadCells).toBe(0);
  // 空闲 snap：服务器未动 → 写回不得改 moveAt、不得退化为钉死段
  await page.evaluate(s => window.__gachaDbg(s), playerOf(st0, predCells, [md.x, md.y]));
  await rafN(page, 2);
  const idle = await page.evaluate(() => window.__predState());
  const p = idle.proj;
  const deg = p.lastCells.every((c, i) => c.x === p.cells[i].x && c.y === p.cells[i].y);
  expect(deg, '空闲 snap 投影不得退化为 lastCells==cells 钉死段').toBe(false);
  expect(p.moveAt, '空闲 snap 不得拉动相位（重锚仅等式递减转移触发）').toBe(afterCatch.proj.moveAt);
  expect(p.cells.map(c => [c.x, c.y])).toEqual(predCells);
  await page.evaluate(() => window.__predGate(false));
});

test('T7 回滚后空闲 snap 写回保持非退化且相位不动', async ({ page }) => {
  await joinSolo(page);
  const st0 = await page.evaluate(() => window.__predState());
  const st = await buildAndAdvance(page, st0);
  const predCells = st.cells.map(c => [c.x, c.y]);
  const md = st.moveDir;
  // 追赶（lead→0）后注入矛盾 snap → rollback（steps=0 → pred 收敛到服务器位）
  await page.evaluate(s => window.__gachaDbg(s), playerOf(st0, predCells, [md.x, md.y]));
  await page.evaluate(s => window.__gachaDbg(s), playerOf(st0, [[3, 3], [2, 3], [1, 3]], [1, 0]));
  const afterC = await page.evaluate(() => window.__predState());
  expect(afterC.cells.map(c => [c.x, c.y])).toEqual([[3, 3], [2, 3], [1, 3]]);
  const moveAt0 = afterC.proj.moveAt;   // rollback 不写投影 → 此值 = applyPlayers 锚点（矛盾拍到达时刻）
  // 空闲 snap：eq 成立 → seamless 写回 → prevCells 必须非退化、moveAt 必须与锚点一致
  await page.evaluate(s => window.__gachaDbg(s), playerOf(st0, [[3, 3], [2, 3], [1, 3]], [1, 0]));
  await rafN(page, 2);
  const idle = await page.evaluate(() => window.__predState());
  const p = idle.proj;
  const deg = p.lastCells.every((c, i) => c.x === p.cells[i].x && c.y === p.cells[i].y);
  expect(deg, 'rollback 后空闲写回不得退化（prevCells 须为回滚前 pred 位）').toBe(false);
  expect(p.lastCells.map(c => [c.x, c.y])).toEqual(predCells);
  expect(p.moveAt, '空闲写回 moveAt 须与 applyPlayers 锚点同源（回滚拍相位同步）').toBe(moveAt0);
  await page.evaluate(() => window.__predGate(false));
});
