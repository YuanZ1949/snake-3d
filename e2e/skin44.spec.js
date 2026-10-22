// 批44：换肤 UI 改进 e2e —— 十连叠牌排 / 局内换肤浮层 / 大厅皮肤直入口
const { test, expect } = require('@playwright/test');
const { ensureLogin } = require('./_helpers');

// 10 项注入：9 个 3★（奇偶决定 dup/refund）+ 1 个 5★ 压轴（playWish 会把最高星排最右）
function tenItems() {
  const arr = [];
  for (let i = 0; i < 9; i++) arr.push(i % 2 === 0 ? { star: 3, skin: 5, dup: true, refund: 10 } : { star: 3, skin: 11, dup: false });
  arr.push({ star: 5, skin: 15, dup: false, cap: true });
  return arr;
}

test('十连结果：10 卡单排叠牌（不折行）+ 5★ 最右压轴 + 无底部缩略图', async ({ page }) => {
  await page.goto('/');
  await page.waitForFunction(() => typeof window.__gachaDbg === 'function');
  await page.evaluate(() => document.getElementById('startScreen').classList.add('hidden'));
  await page.evaluate(m => window.__gachaDbg(m), { t: 'gachares', items: tenItems(), balance: 1600, dust: 0 });
  const layer = page.locator('#wishAnim');
  // 两段点击协议：演出中点=快进到 done
  await page.waitForFunction(() => ['meteor', 'flash', 'reveal'].includes(document.getElementById('wishAnim').dataset.phase), null, { timeout: 15000 });
  await layer.click();
  await expect(layer).toHaveAttribute('data-phase', 'done');
  await expect(page.locator('#wishGrid .wishCard')).toHaveCount(10);
  const info = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('#wishGrid .wishCard')];
    return {
      rows: new Set(cards.map(c => c.offsetTop)).size,          // 单排 = 所有卡同 top
      wrap: getComputedStyle(document.getElementById('wishGrid')).flexWrap,
      thumbs: !!document.getElementById('wishThumbs'),          // 底部缩略图已删
      firstZ: cards[0].style.zIndex, lastZ: cards[9].style.zIndex,   // 右卡压左卡 z 序
      lastStar: cards[9].dataset.star,
    };
  });
  expect(info.rows).toBe(1);
  expect(info.wrap).toBe('nowrap');
  expect(info.thumbs).toBe(false);
  expect(info.lastStar).toBe('5');                              // 5★ 最右压轴
  expect(Number(info.lastZ)).toBeGreaterThan(Number(info.firstZ));
});

test('局内点皮肤按钮 → 弹浮层列表，点选即换肤并自动关闭', async ({ page }) => {
  await ensureLogin(page, 'yuan', '123456');
  await page.locator('#btnSolo').click();                       // 单人练习：建好自动开局
  await page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 15000 });
  await page.waitForTimeout(800);                               // 等 HUD 稳定
  const before = await page.evaluate(() => localStorage.getItem('snake-skin'));
  await page.locator('#btnSkin').click();
  await expect(page.locator('#skinDrawer')).toBeVisible();
  await expect(page.locator('#skinDrawerGrid .wishSkn')).not.toHaveCount(0);
  await expect(page.locator('#skinDrawerGrid .using')).toHaveCount(1);   // 当前款唯一「使用中」
  const other = page.locator('#skinDrawerGrid .wishSkn:not(.cur)').first();
  const nm = (await other.locator('.nm').textContent()).trim();
  await other.click();
  await expect(page.locator('#skinDrawer')).toBeHidden();        // 点选即关
  const after = await page.evaluate(() => localStorage.getItem('snake-skin'));
  expect(after).toBeTruthy();
  expect(after).not.toBe(before ?? '');
  await expect(page.locator('#btnSkin')).toContainText(nm);      // HUD 按钮即时刷新
});

test('大厅 🎨 皮肤入口 → wishLayer 直落皮肤 tab（使用中徽标可见）', async ({ page }) => {
  await ensureLogin(page, 'yuan', '123456');
  await page.locator('#btnSkinsLobby').click();
  await expect(page.locator('#wishLayer')).toBeVisible();
  await expect(page.locator('#tabSkins')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#wishSkinsPane')).toBeVisible();
  await expect(page.locator('#wishGachaPane')).toBeHidden();
  await expect(page.locator('#wishSkins .wishSkn')).not.toHaveCount(0);
  await expect(page.locator('#wishSkins .using')).toHaveCount(1);
});
