// 批35：角色皮肤「奶龙 / 芙宁娜」迷你模型（GLB + GLTFLoader 挂头）
// 断言：SKINS 扩到 18 款、16/17 带 model 字段、选中后挂载模型且球可见（批45 站姿：脚贴球顶/高≈0.65/光环避让）、加载失败静默回退。
const { test, expect } = require('@playwright/test');
const { ensureLogin } = require('./_helpers');

test('SKINS 含 18 款且 16/17 为角色模型款', async ({ page }) => {
  await ensureLogin(page, 'yuan', '123456');
  const d = await page.evaluate(() => window.__modelDbg());
  expect(d.skins.length).toBe(18);
  expect(d.skins[16]).toBe('nailong');
  expect(d.skins[17]).toBe('furina');
  expect(d.skins.slice(0, 16).every((m) => m === null)).toBe(true);  // 老款不受污染
});

test('GLTFLoader 就位（ESM 引入可用 · 批37 项9）', async ({ page }) => {
  await ensureLogin(page, 'yuan', '123456');
  const d = await page.evaluate(() => window.__modelDbg());
  expect(d.loader).toBe(true);
});

test('选中奶龙 → 蛇头挂载模型（批45 站姿：脚贴球顶、高≈0.65，球可见）', async ({ page }) => {
  await ensureLogin(page, 'yuan', '123456');
  await page.click('#btnSolo');
  await page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 15000 });
  await page.evaluate(() => { localStorage.setItem('snake-skin', '16'); window.__applySkinDbg(Number(localStorage.getItem('snake-skin'))); });
  // 模型是异步加载 → 等模板就绪 + 挂载完成
  await page.waitForFunction(() => {
    const d = window.__modelDbg();
    return d.loaded.includes('nailong') && d.mine.node === true;
  }, null, { timeout: 15000 });
  const d = await page.evaluate(() => window.__modelDbg());
  expect(d.mine.want).toBe('nailong');
  expect(d.mine.key).toBe('nailong');
  expect(d.mine.node).toBe(true);
  expect(d.mine.skull).toBe(true);              // 批45：球可见（模型站在球上）
  expect(Math.abs(d.mine.foot - 0.24)).toBeLessThan(0.01);   // 脚贴球顶
  expect(d.mine.h).toBeGreaterThanOrEqual(0.5); // 站姿高（0.65 或被宽度上限压低）
  expect(d.mine.h).toBeLessThanOrEqual(0.81);
  expect(d.mine.ringY).toBeGreaterThan(0.24 + d.mine.h);     // 光环在模型头顶上方
});

test('切换芙宁娜 → 换成 furina 模型；回切普通皮肤 → 卸载恢复 skull', async ({ page }) => {
  await ensureLogin(page, 'yuan', '123456');
  await page.click('#btnSolo');
  await page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 15000 });
  await page.evaluate(() => { localStorage.setItem('snake-skin', '17'); window.__applySkinDbg(Number(localStorage.getItem('snake-skin'))); });
  await page.waitForFunction(() => {
    const d = window.__modelDbg();
    return d.loaded.includes('furina') && d.mine.node === true;
  }, null, { timeout: 15000 });
  let d = await page.evaluate(() => window.__modelDbg());
  expect(d.mine.key).toBe('furina');
  expect(d.mine.skull).toBe(true);               // 批45：球可见（站姿设计）
  expect(Math.abs(d.mine.foot - 0.24)).toBeLessThan(0.01);
  // 回切 0 号（无 model）→ 必须卸掉模型，球保持可见，光环复位默认高度
  await page.evaluate(() => { localStorage.setItem('snake-skin', '0'); window.__applySkinDbg(Number(localStorage.getItem('snake-skin'))); });
  await page.waitForFunction(() => window.__modelDbg().mine.key === null, null, { timeout: 5000 });
  d = await page.evaluate(() => window.__modelDbg());
  expect(d.mine.node).toBe(false);
  expect(d.mine.skull).toBe(true);
  expect(Math.abs(d.mine.ringY - 0.34)).toBeLessThan(0.01);   // 光环复位
});

test('皮肤页可选到两款角色皮肤（渲染进祈愿面板且能点选）', async ({ page }) => {
  await ensureLogin(page, 'yuan', '123456');
  await page.click('#btnWishLobby');   // 大厅入口（startScreen 遮罩盖住顶栏 #btnWish）
  await page.click('#tabSkins');       // 面板默认停在抽卡页签，皮肤页需切过去才 renderWishSkins()
  await page.waitForSelector('#wishSkins .wishSkn', { timeout: 5000 });
  const nailong = page.locator('#wishSkins .wishSkn').filter({ hasText: '奶龙' });
  const furina = page.locator('#wishSkins .wishSkn').filter({ hasText: '芙宁娜' });
  await expect(nailong).toHaveCount(1);
  await expect(furina).toHaveCount(1);
  await nailong.first().click();
  const d = await page.evaluate(() => window.__modelDbg());
  expect(d.mine.want).toBe('nailong');
});

test('模型 404 → 静默回退 skull 球，不产生未捕获错误', async ({ page }) => {
  const errs = [];
  page.on('pageerror', (e) => errs.push(String(e)));
  // 拦掉所有 .glb 请求，模拟模型缺失/加载失败
  await page.route('**/*.glb', (r) => r.abort());
  await ensureLogin(page, 'yuan', '123456');
  await page.click('#btnSolo');
  await page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 15000 });
  await page.evaluate(() => { localStorage.setItem('snake-skin', '16'); window.__applySkinDbg(Number(localStorage.getItem('snake-skin'))); });
  await page.waitForTimeout(3000);   // 留足时间让失败的加载 settle
  const d = await page.evaluate(() => window.__modelDbg());
  expect(d.mine.key).toBe('nailong');   // 意图仍然记录（key 在请求前就写入）
  expect(d.mine.node).toBe(false);      // 没挂上模型
  expect(d.mine.skull).toBe(true);      // skull 球保持可见 → 不会出现无头蛇
  expect(errs).toEqual([]);             // 无未捕获异常（加载错误已 catch 静默 resolve）
});
