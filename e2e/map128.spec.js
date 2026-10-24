// 批47 §Task7：128×128 巨图建房 → 进图快照尺寸回归。
// 建房走大厅创建面板（#cSize 选 128 档，#cName 唯一房名防跨 run 同名误配，同 rooms.spec 纪律）；
// 进图后读 __predState().cols/rows（既有 e2e 的尺寸口径，源自真实 snap 的 ensureBoard）。
const { test, expect } = require('@playwright/test');
const { ensureLogin, uniqName } = require('./_helpers');

test('批47: 128×128 建房进图快照尺寸', async ({ page }) => {
  await ensureLogin(page, 'yuan', '123456');
  const name = uniqName('巨图128');

  await page.click('#btnRoomCreate');                       // 展开创建面板
  await page.selectOption('#cSize', '128');
  await page.fill('#cName', name);
  await page.click('#btnCreateGo');
  // created 回执：唯一房名全等出现在列表（renderRooms 已刷新）
  await expect(page.locator('#roomList').getByText(name, { exact: true })).toHaveCount(1);

  await page.click('#btnStart');                            // 入局 curRoom（刚创建并自动选中的 128 房）
  await page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 20000 });

  const st = await page.evaluate(() => window.__predState());
  expect(st.cols, '128 档列数').toBe(128);
  expect(st.rows, '128 档行数').toBe(128);
});
