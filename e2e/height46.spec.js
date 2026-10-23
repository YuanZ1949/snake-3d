// 批46 §4.1/§11：客户端坠落动画 + 死亡呈现延迟（H6 时序）e2e。
// 坠落注入：__fallScenarioSet() 把头格起沿 dir 6 格走廊抬到 h=3 且落点格(i=6)压到 h=0（原子注入，h1 定值；服务端平地不受影响，蛇照常移动），
// 蛇走出走廊末端（h3→h0 落差 3≥2）即触发真实坠落步：__fallDbg 可观测 fx 起跳→落地完成；
// 坠落中合成 die 事件（__dieDbg 走真实 handleDie 路径）→ 爆散必须延迟一个 step 间隔（H6：坠落帧先于死亡爆散）。
const { test, expect } = require('@playwright/test');
const { ensureLogin } = require('./_helpers');

async function solo(page) {
  await ensureLogin(page, 'yuan', '123456');
  await page.click('#btnSolo');
  await page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 15000 });
}

test('批46: 走出高台触发坠落步（__fallDbg：h3→h0 落差3，fx 起跳→落地完成）', async ({ page }) => {
  await solo(page);
  await page.waitForFunction(() => window.__fallDbg && window.__fallDbg().cell, null, { timeout: 8000 });
  await page.evaluate(() => window.__fallScenarioSet());
  const fx = await page.waitForFunction(() => {
    const d = window.__fallDbg();
    return d && d.fx ? { h0: d.fx.h0, h1: d.fx.h1, drop: d.fx.h0 - d.fx.h1 } : false;
  }, null, { timeout: 12000, polling: 60 });
  const v = await fx.jsonValue();
  expect(v.h0, '坠落起点 h=3').toBe(3);
  expect(v.h1, '坠落终点 h=0').toBe(0);
  expect(v.drop, '落差 3 ≥2').toBeGreaterThanOrEqual(2);
  // 落地帧：fx.landed 置 true（尘土/顿挫/微震触发点，§4.1）
  await page.waitForFunction(() => { const d = window.__fallDbg(); return d && d.fx && d.fx.landed === true; }, null, { timeout: 8000, polling: 60 });
});

test('批46 H6: 坠落帧先于死亡爆散（die 呈现延迟一个 step 间隔，结算文案 fall）', async ({ page }) => {
  await solo(page);
  await page.waitForFunction(() => window.__fallDbg && window.__fallDbg().cell, null, { timeout: 8000 });
  await page.evaluate(() => window.__fallScenarioSet());
  // 等坠落进行中（fx 起跳且未落地：此刻 cells 稳定、drop≥2 保证成立）
  await page.waitForFunction(() => { const d = window.__fallDbg(); return d && d.fx && !d.fx.landed && d.drop >= 2; }, null, { timeout: 12000, polling: 40 });
  const tFallPage = await page.evaluate(() => performance.now());   // 坠落帧观测时刻（页内时钟）
  await page.evaluate(() => window.__dieDbg());                      // 合成 die（myId, cause='fall'）走真实 handleDie
  await page.waitForTimeout(60);
  const b1 = await page.evaluate(() => window.__dieBurstAt || 0);
  expect(b1, '60ms 后爆散仍被挂起（延迟一个 step 间隔才呈现）').toBe(0);
  await page.waitForFunction(() => (window.__dieBurstAt || 0) > 0, null, { timeout: 3000, polling: 50 });
  const burstAt = await page.evaluate(() => window.__dieBurstAt);
  expect(burstAt, '坠落帧先于死亡爆散出现（H6 时序）').toBeGreaterThan(tFallPage);
  // 死亡结算文案：CAUSE_TEXT['fall']（overSub 在 onMyDeath 内同步写入，不依赖结算屏显隐时序）
  await page.waitForTimeout(200);
  const sub = await page.evaluate(() => document.getElementById('overSub').textContent);
  expect(sub, '结算副标题含坠落死因').toContain('坠落身亡');
});
