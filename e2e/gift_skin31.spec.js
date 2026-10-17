// 批31 探针：① 登录即弹更新回馈（authres 带 gift → #giftPop 立即可见，不再等进房）
//            ② 皮肤页按星级分级（5★ 卡 .s5 金框流光 / 4★ 卡 .s4 紫框）
// 注：e2e 环境账号首跑注册、后续跑登录；新账号 update_ver_claimed=0 → 登录必弹（每账号每版本一次性）
const { test, expect } = require('@playwright/test');

let _seq = 0;
const uniq = (base) => `${base}${(++_seq).toString(36)}${Date.now().toString(36).slice(-3)}`;

test('登录即弹更新回馈（不进房也弹）', async ({ page }) => {
  const name = uniq('gift');
  await page.goto('/');
  await page.waitForFunction(() => typeof window.__gachaDbg === 'function');
  await page.fill('#userIn', name);
  await page.fill('#passIn', '123456');
  await page.click('#btnRegister');
  // authres 一到即弹 —— 全程没有点加入房间
  await expect(page.locator('#giftPop')).toBeVisible({ timeout: 5000 });
  await expect(page.locator('#giftAmt')).toHaveText('14,400');
  await page.locator('#btnGiftClaim').click();
  await expect(page.locator('#giftPop')).toBeHidden({ timeout: 5000 });
});

test('皮肤页：5★ 金框流光卡（.s5）、4★ 紫框（.s4）', async ({ page }) => {
  const name = uniq('skin');
  await page.goto('/');
  await page.waitForFunction(() => typeof window.__gachaDbg === 'function');
  await page.fill('#userIn', name);
  await page.fill('#passIn', '123456');
  await page.click('#btnRegister');
  await expect(page.locator('#acctBadge')).toContainText(name, { timeout: 5000 });
  await page.locator('#btnGiftClaim').click();          // 顺手领掉回馈（不领也不影响本用例）
  // openWish 会发 gachainfo（回包 ownedSkins 空集覆盖注入）→ 先开面板等回包落地，再注入
  await page.locator('#btnWishLobby').click();
  await page.waitForTimeout(500);                      // 本地回包毫秒级，留 500ms 足够落地
  // 注入拥有集：0-4 免费 + 11(4★) + 15(5★ UP)；直接驱动 renderWishSkins
  await page.evaluate(() => {
    window.__skinsDbgSet([0, 1, 2, 3, 4, 11, 15]);
  });
  await page.locator('#tabSkins').click();
  await expect(page.locator('#wishSkins .wishSkn.s5')).toHaveCount(1);
  await expect(page.locator('#wishSkins .wishSkn.s4')).toHaveCount(1);
  await expect(page.locator('#wishSkins .wishSkn.s5')).toContainText('辉夜');
});
