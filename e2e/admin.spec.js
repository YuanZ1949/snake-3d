// 批30④：管理员账户（ADMIN_USERS 白名单）——登录见「🛡 管理」Tab；
// 公告全体回显公屏；报告渲染字段；发奖在线提醒；踢人收 kicked 提示；非管理员无入口。
// 注：e2e 环境 yuan 账号首跑注册、后续跑登录（同一密码）；服务端二次校验白名单，前端隐藏仅易用性。
const { test, expect } = require('@playwright/test');

let _seq = 0;
const uniq = (base) => `${base}${(++_seq).toString(36)}${Date.now().toString(36).slice(-3)}`;

async function ensureLogin(page, name, pass) {
  await page.goto('/');
  await page.waitForFunction(() => typeof window.__gachaDbg === 'function');
  await page.fill('#userIn', name);
  await page.fill('#passIn', pass);
  await page.click('#btnRegister');
  try {
    await expect(page.locator('#acctBadge')).toContainText(name, { timeout: 3000 });
  } catch {
    await page.click('#btnLogin');       // 账号已存在（跨 run 复用）→ 改登录
    await expect(page.locator('#acctBadge')).toContainText(name, { timeout: 5000 });
  }
  // 批31：登录即弹更新回馈（新账号未领 → 弹窗盖住 startScreen z-index:45）→ 关掉不挡后续点击
  const pop = page.locator('#giftPop');
  try {
    await pop.waitFor({ state: 'visible', timeout: 2000 });
    await page.click('#btnGiftClose');
    await expect(pop).toBeHidden({ timeout: 3000 });
  } catch { /* 已领过（跨 run 复用账号）不弹，直接继续 */ }
}

test('管理员：公告全体回显、报告渲染、发奖在线提醒', async ({ page, browser }) => {
  const notice = '公告' + Date.now().toString(36);
  // 受众（匿名也收公屏）先上线，等着收公告与发奖提醒
  const ctx2 = await browser.newContext();
  const p2 = await ctx2.newPage();
  await p2.goto('/');
  await p2.waitForFunction(() => typeof window.__gachaDbg === 'function');

  // 管理员登录 → 管理 Tab 可见 → 发公告 → 回执 ✅
  await ensureLogin(page, 'yuan', '123456');
  await page.locator('#btnGchat').click();
  const tabA = page.locator('#cpTabA');
  await expect(tabA).toBeVisible();
  await tabA.click();
  await expect(page.locator('#admPane')).toBeVisible();
  await page.locator('#admNotice').fill(notice);
  await page.locator('#admSend').click();
  await expect(page.locator('#admOut')).toContainText('公告已发布');

  // 受众公屏回显（📢 公告 身份）
  await p2.locator('#btnGchat').click();
  await expect(p2.locator('#cpLog')).toContainText(notice);

  // 报告渲染（含在线/今日/累计关键词）
  await page.locator('#admReport').click();
  await expect(page.locator('#admOut')).toContainText('在线', { timeout: 5000 });
  await expect(page.locator('#admOut')).toContainText('累计');

  await ctx2.close();
});

test('管理员：发奖到账提醒 + 踢人收提示；非管理员无管理入口', async ({ page, browser }) => {
  const victim = uniq('配角');
  // 受害者注册登录（在线以收 toast / kicked）
  const ctx2 = await browser.newContext();
  const p2 = await ctx2.newPage();
  await ensureLogin(p2, victim, '123456');

  // 管理员：发奖 5 → 受害者收 toast 提醒；adminres ✅
  await ensureLogin(page, 'yuan', '123456');
  await page.locator('#btnGchat').click();
  await page.locator('#cpTabA').click();
  await page.locator('#admName').fill(victim);
  await page.locator('#admAmt').fill('5');
  await page.locator('#admGrant').click();
  await expect(page.locator('#admOut')).toContainText('已发 5');
  await expect(p2.locator('#toast')).toContainText('管理员发放 5', { timeout: 5000 });

  // 踢人 → 受害者收 kicked 提示（随后服务端断连）
  await page.locator('#admKick').click();
  await expect(page.locator('#admOut')).toContainText('已踢出');
  await expect(p2.locator('#toast')).toContainText('你已被管理员移出', { timeout: 5000 });

  // 非管理员：管理 Tab 永不可见
  await expect(p2.locator('#cpTabA')).toBeHidden();

  await ctx2.close();
});

// 批32：导出登录助手供其他 spec 复用
module.exports = { ensureLogin };
