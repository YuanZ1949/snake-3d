// 批29⑥：道具效果条中文名——gate 冻真实 snap 后注入带 eff/inv 的 snap，
// 断言 #effects 每个 chip 含 emoji + 中文效果名（护盾/加速/穿墙/磁铁/双倍/狂暴/偏转/无敌）
const { test, expect } = require('@playwright/test');

const snapShell = st0 => ({
  t: 'snap', round: st0.round, cols: st0.cols, rows: st0.rows,
  walls: [], portals: [], rocks: [], foods: [], bonus: null,
});

test('效果条 chip 显示中文名', async ({ page }) => {
  await page.goto('/');
  await page.click('#btnSolo');
  await page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 15000 });
  const st0 = await page.evaluate(() => window.__predState());
  expect(st0.id, '载具前置：已入局拿到自机 id').not.toBeNull();

  // gate 开 = 隔离真实 snap 流（注入件带 __dbg 标记放行，pred.spec §7.1 同款纪律）
  await page.evaluate(() => window.__predGate(true));
  await page.evaluate(s => window.__gachaDbg(s), {
    ...snapShell(st0),
    players: [{
      id: st0.id, name: 'P', skin: st0.skin, cells: [[10, 12], [9, 12], [8, 12]], dir: [1, 0], len: 3,
      q: 0, tick: 150, alive: true, score: 0, off: false,
      inv: 2000,
      // 服务端快照 eff = 剩余 ms（serve.py 序列化处），注入全七种 + inv 触发 8 个 chip
      eff: { shield: 5000, speed: 4000, ghost: 3000, magnet: 3500, double: 2500, rage: 2000, deflect: 1500 },
    }],
  });
  await page.waitForFunction(() => document.querySelectorAll('#effects .eff').length === 8, null, { timeout: 4000 });

  const box = page.locator('#effects');
  for (const label of ['护盾', '加速', '穿墙', '磁铁', '双倍', '狂暴', '偏转', '无敌']) {
    await expect(box, 'chip 应含中文名 ' + label).toContainText(label);
  }
  // emoji 仍在（中文是补充不是替换）
  await expect(box).toContainText('🛡');
  await expect(box).toContainText('⚡');
  await page.evaluate(() => window.__predGate(false));
});
