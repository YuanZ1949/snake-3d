// 批29④+批31：版本更新庆祝弹窗——真实注册 → 登录即弹（authres 带 gift，不再等进房）
// → 领取 14,400 入账 toast → 刷新会话再登录不再弹（服务端每版本一次性兜底）
const { test, expect } = require('@playwright/test');

let _seq = 0;
const uniq = (base) => `${base}${(++_seq).toString(36)}${Date.now().toString(36).slice(-3)}`;

test('更新弹窗：登录即弹、领取入账 14400，二次登录不再弹', async ({ page }) => {
  const name = uniq('庆');
  const pass = '123456';
  await page.goto('/');

  // 注册 → authres 带 gift → 庆祝弹窗即刻可见（全程不点入房）
  await page.fill('#userIn', name);
  await page.fill('#passIn', pass);
  await page.click('#btnRegister');
  const pop = page.locator('#giftPop');
  await expect(pop).toBeVisible({ timeout: 8000 });
  await expect(page.locator('#giftAmt')).toHaveText('14,400');

  // 领取 → giftres 关窗 + 到账 toast
  await page.click('#btnGiftClaim');
  await expect(pop).toBeHidden({ timeout: 5000 });
  await expect(page.locator('#toast')).toContainText('14,400');   // F4 后 toast 走服务端金额+千分位

  // 新会话（刷新拿新 giftShown）再登录：服务端已记版本 → 不带 gift → 不弹
  await page.reload();
  await page.waitForFunction(() => typeof window.__predState === 'function');
  await expect(page.locator('#acctBadge')).toContainText(name, { timeout: 5000 }); // token 自动登录
  await expect(pop).toBeHidden();
});
