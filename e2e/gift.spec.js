// 批29④：版本更新庆祝弹窗——真实注册 → 单人入局 room-ok 带 gift → 弹窗领取 14,400
// → 到账 toast → 刷新会话（新 giftShown）再入局不再弹（服务端每版本一次性兜底）
const { test, expect } = require('@playwright/test');

let _seq = 0;
const uniq = (base) => `${base}${(++_seq).toString(36)}${Date.now().toString(36).slice(-3)}`;

test('更新弹窗：领取入账 14400，同账号二次进房不再弹', async ({ page }) => {
  const name = uniq('庆');
  const pass = '123456';
  await page.goto('/');

  // 注册并等待登录态（register 成功回 auth.ok → acctBadge 显示账号）
  await page.fill('#userIn', name);
  await page.fill('#passIn', pass);
  await page.click('#btnRegister');
  await expect(page.locator('#acctBadge')).toContainText(name, { timeout: 5000 });

  // 单人入局 → room-ok 带 gift:1 → 庆祝弹窗可见
  await page.click('#btnSolo');
  const pop = page.locator('#giftPop');
  await expect(pop).toBeVisible({ timeout: 8000 });
  await expect(page.locator('#giftAmt')).toHaveText('14,400');

  // 领取 → giftres 关窗 + 到账 toast
  await page.click('#btnGiftClaim');
  await expect(pop).toBeHidden({ timeout: 5000 });
  await expect(page.locator('#toast')).toContainText('14400');

  // 新会话（刷新拿新 giftShown）再入局：服务端已记版本 → 不再带 gift → 不弹
  await page.reload();
  await page.waitForFunction(() => typeof window.__predState === 'function');
  await expect(page.locator('#acctBadge')).toContainText(name, { timeout: 5000 }); // token 自动登录
  await page.click('#btnSolo');
  await page.waitForSelector('#startScreen.hidden', { state: 'hidden', timeout: 8000 });
  await expect(pop).toBeHidden();
});
