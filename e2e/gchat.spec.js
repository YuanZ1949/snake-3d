// 公屏聊天回归（批30③ 引入）
// 设计：首页房间行「💬 公屏」按钮开面板 → Tab 公屏发言（gchatin，1s 限速）→
// 服务端广播 {'t':'gchat'} 回显全体；新连接 welcome 携带最近 50 条历史（内存不落盘）。
// 未进房点「本房」Tab 强制回退公屏（本房消息仅局内有效）。
const { test, expect } = require('@playwright/test');

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await page.waitForFunction(() => typeof window.__gachaDbg === 'function');
});

test('首页开公屏面板发言 → 自己看到回显', async ({ page }) => {
  const msg = '公屏测试' + Date.now().toString(36);
  await page.locator('#btnGchat').click();
  await expect(page.locator('#chatPanel')).toBeVisible();
  await page.locator('#cpIn').fill(msg);
  await page.locator('#cpIn').press('Enter');
  await expect(page.locator('#cpLog')).toContainText(msg);   // 广播回自己
  await page.locator('#cpClose').click();
  await expect(page.locator('#chatPanel')).toBeHidden();     // ✕ 关闭
});

test('新连接 welcome 携带公屏历史（未发言即可见）', async ({ page, browser }) => {
  const msg = '历史消息' + Date.now().toString(36);
  await page.locator('#btnGchat').click();
  await page.locator('#cpIn').fill(msg);
  await page.locator('#cpIn').press('Enter');
  await expect(page.locator('#cpLog')).toContainText(msg);
  // 第二个全新连接：历史只能来自 welcome
  const ctx = await browser.newContext();
  const p2 = await ctx.newPage();
  await p2.goto('/');
  await p2.waitForFunction(() => typeof window.__gachaDbg === 'function');
  await p2.locator('#btnGchat').click();
  await expect(p2.locator('#cpLog')).toContainText(msg);
  await ctx.close();
});

test('未进房点「本房」Tab → 强制回退公屏', async ({ page }) => {
  await page.locator('#btnGchat').click();
  await page.locator('#cpTabR').click();
  await expect(page.locator('#cpTabG')).toHaveClass(/on/);
  await expect(page.locator('#cpTabR')).not.toHaveClass(/on/);
  await expect(page.locator('#chatPanel')).toBeVisible();
});
