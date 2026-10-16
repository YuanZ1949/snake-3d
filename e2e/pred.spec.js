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
    // ⑧ 相位守卫（spec v5 :80 仅 lead==0 重锚）：lead>0 时 at 注入不得拉平相位；lead==0 才按阈值重锚
    const pp = D.mkPred(mk(), E, 150, 150);                       // lastMoveAt=150
    D.predAdvance(pp, [{ x: 0, y: -1 }], world([]), foods, {});   // 消费 ↑ → lead=1、lastMoveAt=300、moveDir=N
    out.rLead = D.predReconcile(pp, { cells: mk(), dir: { x: 1, y: 0 }, at: 1000 }, [{ x: 0, y: -1 }], world([]), foods, {});
    out.lmLead = pp.lastMoveAt;
    const p0 = D.mkPred(mk(), E, 150, 150);
    out.rZero = D.predReconcile(p0, { cells: mk(), dir: { x: 1, y: 0 }, at: 1000 }, [], world([]), foods, {});
    out.lmZero = p0.lastMoveAt;
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
  // 用例⑧：lead>0 时 at 不得重锚（oracle 终审 Critical 回归网）；lead==0 才重锚
  expect(r.rLead).toBe('seamless');
  expect(r.lmLead).toBe(300);
  expect(r.rZero).toBe('reanchor');
  expect(r.lmZero).toBe(1000);
});
