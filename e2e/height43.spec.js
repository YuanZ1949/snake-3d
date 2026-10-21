// 批43：宏大起伏——cHeight「宏伟」(2.6) 档建房 → 服务端脊线山脉（h≥3 峰 + 逐级爬升链 + 连通脊）
const { test, expect } = require('@playwright/test');
const { ensureLogin } = require('./_helpers');

let _seq = 0;
const uniq = (base) => `${base}${(++_seq).toString(36)}${Date.now().toString(36).slice(-4)}`;

test('宏伟档 2.6 建房 → hmap 脊线山脉（h≥3 + 逐级爬升链 + 连通块≥6）', async ({ page }) => {
  await ensureLogin(page, 'yuan', '123456');
  const name = uniq('宏伟房');
  await page.locator('#btnRoomCreate').click();                 // 展开创建面板
  await page.locator('#cName').fill(name);
  await page.selectOption('#cHeight', '2.6');
  await page.locator('#btnCreateGo').click();
  // 进房：房间列表项选中（selectRoom）→ 「开始」按钮进局（btnStart → start → doJoin）
  const item = page.locator('#roomList .roomItem').filter({ has: page.getByText(name, { exact: true }) });
  await item.click();
  await page.locator('#btnStart').click();
  await page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 15000 });
  await page.waitForTimeout(500);                               // 等 full 帧 hmap 下发同步
  const hm = await page.evaluate(() => window.__hmapDump());
  const vals = new Set(hm.map(t => t[2]));
  expect(vals.has(3), '宏伟档必须出 h=3 脊峰').toBe(true);
  expect(vals.has(2) && vals.has(1), 'h=2 脊身 / h=1 缓坡必须存在').toBe(true);
  const map = new Map(hm.map(t => [t[0] + ',' + t[1], t[2]]));
  const at = (x, y) => map.get(x + ',' + y) ?? 0;
  const nb = (x, y) => [[x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]];
  // 逐级爬升链：h=3 相邻 h=2、h=2 相邻 h=1（与单测同款存在性断言）
  expect(hm.some(([x, y, h]) => h === 3 && nb(x, y).some(([a, b]) => at(a, b) === 2)),
    'h=3 峰必须与 h=2 相邻（可爬升）').toBe(true);
  expect(hm.some(([x, y, h]) => h === 2 && nb(x, y).some(([a, b]) => at(a, b) === 1)),
    'h=2 脊必须与 h=1 缓坡相邻').toBe(true);
  // 连绵性：h≥2 存在大小 ≥6 的连通块（非散点山包）
  const hi = new Set(hm.filter(t => t[2] >= 2).map(t => t[0] + ',' + t[1]));
  const seen = new Set();
  let big = 0;
  for (const s of hi) {
    if (seen.has(s)) continue;
    let size = 0;
    const comp = [s];
    seen.add(s);
    while (comp.length) {
      const [cx, cy] = comp.pop().split(',').map(Number);
      size++;
      for (const [a, b] of nb(cx, cy)) {
        const k = a + ',' + b;
        if (hi.has(k) && !seen.has(k)) { seen.add(k); comp.push(k); }
      }
    }
    big = Math.max(big, size);
  }
  expect(big, '脊必须连绵（最大连通块 ≥6）').toBeGreaterThanOrEqual(6);
});
