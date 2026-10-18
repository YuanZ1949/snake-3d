// 批33：元素弹前端——HUD 按钮组 + 键位切元素/发射 + CD 置灰 + 房间 elements 开关显隐
// 协议：snap players[].aura={e,t} / ev react / eterrain；本 spec 只验前端层，
//       反应语义由 test_reactions_p33.py（进程内双 ws E2E）覆盖。
const { test, expect } = require('@playwright/test');
const { ensureLogin } = require('./_helpers');

let _seq = 0;
const uniq = (base) => `${base}${(++_seq).toString(36)}${Date.now().toString(36).slice(-3)}`;

const startScreenHidden = (page) =>
  page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 15000 });

test('solo 进局 → elemBar 可见 4 元素；键 3 切冰、键 e 发射进 CD', async ({ page }) => {
  await ensureLogin(page, 'yuan', '123456');
  await page.click('#btnSolo');
  await startScreenHidden(page);
  // 默认显示（单人房 elements 默认开）：pyro 为当前选中
  const bar = page.locator('#elemBar');
  await expect(bar).toBeVisible();
  await expect(bar.locator('.ebtn')).toHaveCount(4);
  await expect(bar.locator('.ebtn[data-elem="pyro"]')).toHaveClass(/on/);
  // 键 3 → cryo 选中（键 1-4 只切元素，E 才发射）
  await page.keyboard.press('3');
  await expect(bar.locator('.ebtn[data-elem="cryo"]')).toHaveClass(/on/);
  await expect(bar.locator('.ebtn[data-elem="pyro"]')).not.toHaveClass(/on/);
  // 键 e 发射 → 本地 EB_CD 2s → 全组置灰（主循环 toggle .cool）
  await page.keyboard.press('e');
  await expect(bar.locator('.ebtn[data-elem="cryo"]')).toHaveClass(/cool/);
});

test('元素弹渲染链路：发射后服务端弹药 → projMeshes > 0', async ({ page }) => {
  await ensureLogin(page, 'yuan', '123456');
  await page.click('#btnSolo');
  await startScreenHidden(page);
  await page.keyboard.press('e');                            // 发射 pyro
  // snap → syncProjectiles 建 mesh（弹速慢，命中前有存活窗口）
  await page.waitForFunction(() => window.__projDbg() > 0, null, { timeout: 5000 });
});

test('建房 elements 关 → 进局 elemBar 隐藏', async ({ page }) => {
  await ensureLogin(page, 'yuan', '123456');
  const name = uniq('无元素房');
  await page.locator('#btnRoomCreate').click();
  await page.locator('#cName').fill(name);
  await page.selectOption('#cElements', '0');
  await page.locator('#btnCreateGo').click();
  await expect(page.locator('#roomList').getByText(name, { exact: true })).toHaveCount(1);
  await page.locator('#roomList').getByText(name, { exact: true }).click();
  await page.click('#btnStart');
  await startScreenHidden(page);
  // updateHud 按 roomList 里该房 elements===false → 隐藏
  await expect(page.locator('#elemBar')).toBeHidden();
});
