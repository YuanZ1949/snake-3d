// 批33：元素弹前端——HUD 按钮组 + 键位切元素/发射 + CD 置灰 + 房间 elements 开关显隐
// 协议：snap players[].aura={e,t} / ev react / eterrain；本 spec 只验前端层，
//       反应语义由 test_reactions_p33.py（进程内双 ws E2E）覆盖。
const { test, expect } = require('@playwright/test');
const { ensureLogin } = require('./_helpers');

let _seq = 0;
const uniq = (base) => `${base}${(++_seq).toString(36)}${Date.now().toString(36).slice(-3)}`;
// 生产 yuan 账号密码非 123456（注册报已存在/登录报密码错）→ 本 spec 用专用固定账号 p33elem（已预建）：
// ensureLogin 先 register（账号已存在 → 不计注册配额）→ 失败兜底 login，天然免疫生产注册限流（REG_MAX=30/300s）。
const E2E_USER = 'p33elem';
const E2E_PASS = '123456';

const startScreenHidden = (page) =>
  page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 15000 });
// 等回合进入 playing（fireEb 需 state==='playing' 才发射；到达耗时实测 0-323ms）
const waitPlaying = (page) =>
  page.waitForFunction(() => window.__stateDbg && window.__stateDbg().state === 'playing', null, { timeout: 8000 });

test('solo 进局 → elemBar 可见 4 元素；键 3 切冰、键 e 发射进 CD', async ({ page }) => {
  await ensureLogin(page, E2E_USER, E2E_PASS);
  await page.click('#btnSolo');
  await startScreenHidden(page);
  // 默认显示（单人房 elements 默认开）：pyro 为当前选中
  const bar = page.locator('#elemBar');
  await expect(bar).toBeVisible();
  await expect(bar.locator('.ebtn')).toHaveCount(4);
  await expect(bar.locator('.ebtn[data-elem="pyro"]')).toHaveClass(/on/);
  // 键 3 → cryo 选中（键 1-4 只切元素，E 才发射）
  await page.keyboard.press('3');
  await expect(bar.locator('.ebtn[data-elem="cryo"]')).toHaveClass(/on/);
  await expect(bar.locator('.ebtn[data-elem="pyro"]')).not.toHaveClass(/on/);
  // 键 e 发射 → 本地 EB_CD 2s → 全组置灰（主循环 toggle .cool）
  await waitPlaying(page);          // fireEb 需 playing，否则不设 lastEb → 无 .cool（race 已实测）
  await page.keyboard.press('e');
  await expect(bar.locator('.ebtn[data-elem="cryo"]')).toHaveClass(/cool/);
});

test('元素弹渲染链路：发射后服务端弹药 → projMeshes > 0', async ({ page }) => {
  await ensureLogin(page, E2E_USER, E2E_PASS);
  await page.click('#btnSolo');
  await startScreenHidden(page);
  // proj 生命周期极短（fire 后 ~66ms 出现、<400ms 即消失），且 solo 蛇 1.3-3.5s 撞墙死后不可重开：
  // 必须等 playing&&alive 帧发射（否则 fireEb 被 state 拦），再 40ms 紧采（400ms 粗采样必错过瞬时弹药）
  await expect(async () => {
    const st = await page.evaluate(() => window.__stateDbg());
    expect(st.state).toBe('playing');   // 未进回合 → 断言失败触发 toPass 重试（到达耗时实测 0-323ms）
    expect(st.alive).toBe(true);
    await page.keyboard.press('e');
    const ok = await page.evaluate(async () => {   // 40ms 紧采 800ms，任一帧 projMeshes>0 即成
      const t = performance.now();
      while (performance.now() - t < 800) {
        if (window.__projDbg() > 0) return true;
        await new Promise(r => setTimeout(r, 40));
      }
      return false;
    });
    expect(ok).toBe(true);
  }).toPass({ timeout: 15000 });
});

test('附着光晕 + 反应浮字可见（注入 snap players[].aura + ev react）', async ({ page }) => {
  await ensureLogin(page, E2E_USER, E2E_PASS);
  await page.click('#btnSolo');
  await startScreenHidden(page);
  const st0 = await page.evaluate(() => window.__predState());
  expect(st0.id, '载具前置：已入局拿到自机 id').not.toBeNull();
  // 闸门隔离真实 snap 流（注入件带 __dbg 放行，pred.spec §7.1 同款纪律）
  await page.evaluate(() => window.__predGate(true));
  const f0 = await page.evaluate(() => window.__floatDbg());
  await page.evaluate(s => window.__gachaDbg(s), {
    t: 'snap', round: st0.round, cols: st0.cols, rows: st0.rows,
    walls: [], portals: [], rocks: [], foods: [], bonus: null,
    players: [{
      id: st0.id, name: 'P', skin: st0.skin, cells: [[10, 12], [9, 12], [8, 12]], dir: [1, 0], len: 3,
      q: 0, tick: 150, alive: true, score: 0, off: false,
      aura: { e: 'cryo', t: 5000 },   // 附着：自机冰元素光晕 5s（render 据 e.aura.t>0 画辉光）
    }],
    ev: [{ t: 'react', kind: 'frozen', victim: st0.id, x: 10, y: 12 }],  // 反应浮字（floater sprite 入场景）
  });
  // 附着断言：自机 aura 生效（render 循环据 e.aura.t>0 画元素色光晕 → 生产可见）
  const aura = await page.evaluate(() => window.__auraDbg());
  expect(aura && aura.e, '附着光晕元素=冰').toBe('cryo');
  // 反应浮字断言：3D 浮字 sprite 入场景（存活数 +1）
  await page.waitForFunction(f => window.__floatDbg() > f, f0, { timeout: 3000 });
  // 截图存证：附着光晕 + 反应浮字在真实渲染层可见（计划 T10 Step3「截图存证」）
  await page.screenshot({ path: 'test-results/p33_attach_react.png' });
  await page.evaluate(() => window.__predGate(false));
});

test('建房 elements 关 → 进局 elemBar 隐藏', async ({ page }) => {
  await ensureLogin(page, E2E_USER, E2E_PASS);
  const name = uniq('无元素房');
  await page.locator('#btnRoomCreate').click();
  await page.locator('#cName').fill(name);
  await page.selectOption('#cElements', '0');
  await page.locator('#btnCreateGo').click();
  await expect(page.locator('#roomList').getByText(name, { exact: true })).toHaveCount(1);
  await page.locator('#roomList').getByText(name, { exact: true }).click();
  await page.click('#btnStart');
  await startScreenHidden(page);
  // updateHud 按 roomList 里该房 elements===false → 隐藏
  await expect(page.locator('#elemBar')).toBeHidden();
});
