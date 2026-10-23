// 批46 §4.1/§11：客户端坠落动画 + 死亡呈现延迟（H6 时序）e2e。
// 坠落注入：__fallScenarioSet() 把头格 h=3 且前一格 h=0（原子注入，h1 定值；服务端平地不受影响，蛇照常移动），
// 蛇下一步走出头格（h3→h0 落差 3≥2）即触发真实坠落步：__fallDbg 可观测 fx 起跳→落地完成；
// 坠落中合成 die 事件（__dieDbg 走真实 handleDie 路径）→ 爆散必须延迟一个 step 间隔（H6：坠落帧先于死亡爆散）。
// 防 flaky（T12 收尾）：solo 无输入蛇会撞墙/被 3 AI 咬死 → 回合落 over，要等 AI 分出胜负出 win 才能 btnRestart 重开；
// 服务端 hmap 重下发也会抹掉注入 → 每次尝试先恢复回合态、再按当前头格重注入（expect.toPass 重试环，60s 预算）。
const { test, expect } = require('@playwright/test');
const { ensureLogin } = require('./_helpers');

async function solo(page) {
  await ensureLogin(page, 'yuan', '123456');
  await page.click('#btnSolo');
  await page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 15000 });
}

// 恢复+注入（toPass 单步）：win→btnRestart 开新回合；非 playing→等终局流转；playing+alive→按当前头格重注入。
// 就绪断言失败/后续 fx 等待超时都会抛错 → toPass 自动重试，直到注入后真实坠落步出现。
async function recoverAndInject(page) {
  const st = await page.evaluate(() => window.__stateDbg());
  if (st.state === 'win') {
    // DOM click 而非 page.click：overScreen 可能带 .hidden（批36 同法）；winRound→sendReady 开新回合
    await page.evaluate(() => document.getElementById('btnRestart').click());
    await page.waitForFunction(() => window.__stateDbg().state === 'playing', null, { timeout: 8000 });
  } else if (st.state !== 'playing') {
    await page.waitForTimeout(300);   // over：轮询等 AI 分出胜负 → win 再重开（批36 恢复路径）
  }
  const ok = await page.evaluate(() => {
    const s = window.__stateDbg(), d = window.__fallDbg && window.__fallDbg();
    return !!(s.state === 'playing' && s.alive && d && d.cell && window.__fallScenarioSet());
  });
  expect(ok, '重试：回合未就绪（state/alive/myEnt）或注入失败').toBe(true);
}

test('批46: 走出高台触发坠落步（__fallDbg：h3→h0 落差3，fx 起跳→落地完成）', async ({ page }) => {
  await solo(page);
  let v = null;
  await expect(async () => {
    await recoverAndInject(page);
    v = await page.waitForFunction(() => {
      const d = window.__fallDbg();
      return d && d.fx && d.fx.h0 === 3 && d.fx.h1 === 0
        ? { h0: d.fx.h0, h1: d.fx.h1, drop: d.fx.h0 - d.fx.h1 } : false;
    }, null, { timeout: 6000, polling: 60 }).then(h => h.jsonValue());
  }).toPass({ timeout: 60000 });
  expect(v.h0, '坠落起点 h=3').toBe(3);
  expect(v.h1, '坠落终点 h=0').toBe(0);
  expect(v.drop, '落差 3 ≥2').toBeGreaterThanOrEqual(2);
  // 落地帧：fx.landed 置 true（尘土/顿挫/微震触发点，§4.1）
  await page.waitForFunction(() => { const d = window.__fallDbg(); return d && d.fx && d.fx.landed === true; }, null, { timeout: 8000, polling: 60 });
});

test('批46 H6: 坠落帧先于死亡爆散（die 呈现延迟一个 step 间隔，结算文案 fall）', async ({ page }) => {
  await solo(page);
  await expect(async () => {
    await recoverAndInject(page);
    // 等坠落进行中（fx 起跳且未落地、live drop≥2 → handleDie 必走延迟路径），并在同一谓词里原子合成 die：
    // 谓词命中与合成同 tick，消掉「等 fx 退出→再 evaluate」跨步后 drop<2 的竞态窗口
    await page.waitForFunction(() => {
      const d = window.__fallDbg();
      if (d && d.fx && !d.fx.landed && d.fx.h0 === 3 && d.fx.h1 === 0 && d.drop >= 2 && !window.__h6DieAt) {
        window.__h6DieAt = performance.now();   // 坠落帧观测时刻（页内时钟）
        window.__dieDbg();                      // 合成 die（myId, cause='fall'）走真实 handleDie
        return true;
      }
      return false;
    }, null, { timeout: 6000, polling: 40 });
  }).toPass({ timeout: 60000 });
  const tFallPage = await page.evaluate(() => window.__h6DieAt);
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
