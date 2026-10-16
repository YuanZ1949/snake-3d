// 批27 探针：祈愿四阶段分镜（逐颗流星判定 → 爆点 → 逐颗揭示 → 陈列）
// 用 __gachaDbg 注入 gachares（不依赖登录/服务端抽卡），断言相位机/捕获标记/New 标/快进协议/reduced-motion 直达 done
const { test, expect } = require('@playwright/test');

const MIXED = {
  t: 'gachares',
  items: [
    { star: 3, skin: 5, dup: true, refund: 10 },
    { star: 4, skin: 11, dup: false },
    { star: 5, skin: 15, dup: false, cap: true },   // 赢50/50 → 捕获明光
  ],
  balance: 1600, dust: 0,
};

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await page.waitForFunction(() => typeof window.__gachaDbg === 'function');
  // 真实流程 openWish() 会先隐藏 startScreen（L3737 顶替策略），探针直喂 gachares 需手动对齐层级
  await page.evaluate(() => document.getElementById('startScreen').classList.add('hidden'));
});

test('全套分镜：逐颗揭示到 done，捕获标记与 New/5★ 陈列', async ({ page }) => {
  await page.evaluate(m => window.__gachaDbg(m), MIXED);
  const layer = page.locator('#wishAnim');
  await expect(layer).toHaveAttribute('data-phase', 'meteor');
  await expect(layer).toHaveAttribute('data-capture', '1');          // 含 cap 的批次打标
  await expect(page.locator('#wishSky .meteor')).toHaveCount(3);     // 逐颗流星 3 条
  await page.waitForFunction(() => document.getElementById('wishAnim').dataset.phase === 'done', null, { timeout: 20000 });
  await expect(page.locator('#wishGrid .wishCard')).toHaveCount(3);
  await expect(page.locator('#wishGrid .wishCard[data-star="5"]')).toHaveCount(1);
  await expect(page.locator('#wishGrid .wishNew')).toHaveCount(2);   // 两个未重复 = New
  await expect(page.locator('#wishGrid .wishDup')).toHaveCount(1);   // 一个重复 +10
  await layer.click();                                               // done 上点击 = 关闭（中心点冒泡到 overlay）
  await expect(layer).toHaveAttribute('data-phase', 'hidden');
});

test('两段点击协议：演出中点=快进到陈列，再点=关闭', async ({ page }) => {
  await page.evaluate(m => window.__gachaDbg(m), MIXED);
  const layer = page.locator('#wishAnim');
  await page.waitForFunction(() => ['meteor', 'flash', 'reveal'].includes(document.getElementById('wishAnim').dataset.phase));
  await layer.click();
  await expect(layer).toHaveAttribute('data-phase', 'done');         // 快进到陈列
  await layer.click();
  await expect(layer).toHaveAttribute('data-phase', 'hidden');       // 关闭
});

test('reduced-motion：喂 gachares 后直达 done（演出跳过）', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.evaluate(m => window.__gachaDbg(m), MIXED);
  const layer = page.locator('#wishAnim');
  await expect(layer).toHaveAttribute('data-phase', 'done');
  await expect(page.locator('#wishGrid .wishCard')).toHaveCount(3);
});
