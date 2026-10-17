// e2e 共享助手（非 .spec.js，不会被 Playwright 收集）
// 批32：ensureLogin 从 admin.spec 抽出——Playwright 禁止 test 文件 require 另一个 test 文件。
let _gseq = 0;
const uniqName = (base) => `${base}${(++_gseq).toString(36)}${Date.now().toString(36).slice(-3)}`;

async function ensureLogin(page, name, pass) {
  await page.goto('/');
  await page.waitForFunction(() => typeof window.__gachaDbg === 'function');
  await page.fill('#userIn', name);
  await page.fill('#passIn', pass);
  await page.click('#btnRegister');
  try {
    await page.locator('#acctBadge').waitFor({ state: 'visible', timeout: 3000 });
    const txt = await page.locator('#acctBadge').textContent();
    if (!txt.includes(name)) throw new Error('not logged in');
  } catch {
    await page.click('#btnLogin');       // 账号已存在（跨 run 复用）→ 改登录
    await page.locator('#acctBadge').waitFor({ state: 'visible', timeout: 5000 });
  }
  // 批31：登录即弹更新回馈（新账号未领 → 弹窗盖住 startScreen z-index:45）→ 关掉不挡后续点击
  const pop = page.locator('#giftPop');
  try {
    await pop.waitFor({ state: 'visible', timeout: 2000 });
    await page.click('#btnGiftClose');
    await pop.waitFor({ state: 'hidden', timeout: 3000 });
  } catch { /* 已领过（跨 run 复用账号）不弹，直接继续 */ }
}

module.exports = { ensureLogin, uniqName };
