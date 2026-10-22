// 批46 迁移：批41 橙红警戒栅栏已随真垂直物理退役（红色警示突兀/假深渊美学批评的直接回应）。
// 本 spec 断言：(a) 场景中无任何 0xff5a2e 橙红警戒材质残留；(b) 深渊 -9 渲染为漏斗井（ab mesh + 口沿/雾 children）；
// (c) 批39 撤除回归保持（c2/c3 不挂整格描边 child）。
const { test, expect } = require('@playwright/test');
const { ensureLogin } = require('./_helpers');

async function solo(page) {
  await ensureLogin(page, 'yuan', '123456');
  await page.click('#btnSolo');
  await page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 15000 });
}

test('批46: 深渊 -9 渲染为漏斗井（ab mesh，口沿+雾 children），无栅栏', async ({ page }) => {
  await solo(page);
  await page.evaluate(() => window.__mapDbgSet([[5, 5, -9]]));
  await page.waitForTimeout(200);
  const dw = await page.evaluate(() => window.__heightMeshDump());
  const ab = dw.find(m => m.kind === 'ab');
  expect(ab, 'h=-9 必须存在 kind=ab 井 mesh').toBeTruthy();
  expect(ab.inScene, '井 mesh 在场景中').toBe(true);
  expect(ab.kids, '井挂口沿青边+井底黑雾两个 children').toBe(2);
  // 全场景无 0xff5a2e 橙红警戒材质（批41 栅栏彻底退役）
  const n = await page.evaluate(() => window.__fenceScanDbg());
  expect(n, '场景中无橙红警戒材质残留').toBe(0);
});

test('批46: 原批41 警戒形态（裸峰 0→2 致死交界）不再产生任何栅栏', async ({ page }) => {
  await solo(page);
  // 批41 会在此形态画 4 条致死交界栅栏；批46 退役后全场景橙红扫描恒 0
  await page.evaluate(() => window.__mapDbgSet([[5, 5, 2]]));
  await page.waitForTimeout(200);
  const n1 = await page.evaluate(() => window.__fenceScanDbg());
  expect(n1).toBe(0);
  // 批39 曾整格误报的「h=1 环抱峰」形态同样恒 0
  await page.evaluate(() => window.__mapDbgSet([[5, 5, 2], [6, 5, 1], [4, 5, 1], [5, 6, 1], [5, 4, 1]]));
  await page.waitForTimeout(200);
  const n2 = await page.evaluate(() => window.__fenceScanDbg());
  expect(n2).toBe(0);
});

test('批46: c2/c3 不挂整格描边（批39 撤除回归），深渊 -9 井 children=2', async ({ page }) => {
  await solo(page);
  await page.evaluate(() => window.__mapDbgSet([[5, 5, 2], [5, 6, 3], [5, 7, -9]]));
  await page.waitForTimeout(200);
  const dw = await page.evaluate(() => window.__heightMeshDump());
  const byKind = k => dw.find(m => m.kind === k);
  expect(byKind('c2').kids, '峰不挂整格描边 child（批39 撤除回归）').toBe(0);
  expect(byKind('c3').kids, '楼不挂整格描边 child（批39 撤除回归）').toBe(0);
  expect(byKind('ab').kids, '井挂口沿青边+井底黑雾（批46 漏斗井）').toBe(2);
});
