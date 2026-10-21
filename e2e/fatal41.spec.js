// 批41：警戒面对焦——真实致死面（相邻两格 |Δh|≥2 的交界面）栅栏渲染
// 旧批39 的 c2/c3 整格橙红描边已撤（治警戒脱敏）；h=1 台阶不产生警戒色。
const { test, expect } = require('@playwright/test');
const { ensureLogin } = require('./_helpers');

async function solo(page) {
  await ensureLogin(page, 'yuan', '123456');
  await page.click('#btnSolo');
  await page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 15000 });
}

test('批41: -2 深坑出口（遥测 4/4 死因）有栅栏，h=1 台阶无警戒', async ({ page }) => {
  await solo(page);
  // 1) 坑口形态：h=-2 格 + 周围全平地（0，稀疏不存）→ |-2-0|=2 致死交界
  await page.evaluate(() => window.__mapDbgSet([[5, 5, -2]]));
  await page.waitForTimeout(200);
  const d = await page.evaluate(() => window.__fatalDbg());
  expect(d.edges.length).toBe(4);            // 四邻全是平地，四个坑口边全标
  expect(d.seg).toBeGreaterThan(0);          // 轮廓线存在
  expect(d.fill).toBeGreaterThan(0);         // 地面警示条+立面填充存在
  expect(d.fill % 6).toBe(0);                // 每个面片 6 顶点（两三角）
  expect(d.inScene).toBe(true);
  // 2) h=1 丘（上行 1，安全台阶）→ 无任何警戒
  await page.evaluate(() => window.__mapDbgSet([[6, 6, 1]]));
  await page.waitForTimeout(200);
  const d2 = await page.evaluate(() => window.__fatalDbg());
  expect(d2.edges.length).toBe(0);
  expect(d2.seg).toBe(0);
  expect(d2.fill).toBe(0);
});

test('批41: h=2 峰——无阶立面(0→2)标警戒，h=1 环面(1→2)不标', async ({ page }) => {
  await solo(page);
  // 裸峰：2 + 四邻平地 → 4 条致死交界
  await page.evaluate(() => window.__mapDbgSet([[5, 5, 2]]));
  await page.waitForTimeout(200);
  const bare = await page.evaluate(() => window.__fatalDbg());
  expect(bare.edges.length).toBe(4);
  // 带 h=1 环的峰（批39 曾整格误报的形态）：环侧 1→2 高差仅 1 → 不标
  await page.evaluate(() => window.__mapDbgSet([[5, 5, 2], [6, 5, 1], [4, 5, 1], [5, 6, 1], [5, 4, 1]]));
  await page.waitForTimeout(200);
  const ring = await page.evaluate(() => window.__fatalDbg());
  // 环上 h=1 格的外侧邻（平地 0）高差 1 也不标；环与峰之间高差 1 不标
  expect(ring.edges.length).toBe(0);
  expect(ring.seg).toBe(0);
});

test('批41: c2/c3 整格橙红描边已撤，深渊青描边保留', async ({ page }) => {
  await solo(page);
  await page.evaluate(() => window.__mapDbgSet([[5, 5, 2], [5, 6, 3], [5, 7, 9]]));
  await page.waitForTimeout(200);
  const dw = await page.evaluate(() => window.__heightMeshDump());
  const byKind = k => dw.find(m => m.kind === k);
  expect(byKind('c2').kids, '峰不再挂整格描边 child（批39 撤除）').toBe(0);
  expect(byKind('c3').kids, '楼不再挂整格描边 child（批39 撤除）').toBe(0);
  expect(byKind('ab').kids, '深渊青描边保留').toBe(1);
});
