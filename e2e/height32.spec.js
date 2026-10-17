// 批32：高度地形（hmap）——客户端渲染 + 房间编辑面三旋钮 + 探针
// 协议：full 帧带 "hmap": [[x,y,h],...]（PROTO 28）；探针 __mapDbgSet/__heightDbg 不走服务端。
const { test, expect } = require('@playwright/test');
const { ensureLogin } = require('./admin.spec');

let _seq = 0;
const uniq = (base) => `${base}${(++_seq).toString(36)}${Date.now().toString(36).slice(-3)}`;

test('hmap 注入 → 高度地形 mesh 生成', async ({ page }) => {
  await ensureLogin(page, 'yuan', '123456');
  await page.click('#btnSolo');                          // 进单人房（服务端建房）
  await page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 15000 });
  await page.evaluate(() => window.__mapDbgSet([[5, 5, 2], [5, 6, -1], [5, 7, -1], [5, 8, 9], [5, 9, 1], [5, 10, 3]]));
  await page.waitForTimeout(300);
  const d = await page.evaluate(() => window.__heightDbg());
  expect(d.meshes).toBe(6);                              // 6 个非平格 → 6 个主 mesh（h=9 的 Edges 为 child 不计）
});

test('创建/编辑面三旋钮 height/water/bld 保存与回填', async ({ page }) => {
  await ensureLogin(page, 'yuan', '123456');
  const name = uniq('地形房');
  await page.locator('#btnRoomCreate').click();          // 展开创建面板
  await page.locator('#cName').fill(name);
  await page.selectOption('#cHeight', '0.5');
  await page.selectOption('#cWater', '1');
  await page.selectOption('#cBld', '1');
  await page.locator('#btnCreateGo').click();
  // ⚙ 设置 → 三值回填（回填数据即来自服务端 info()，与 spec §9.2-3 等价）
  const item = page.locator('#roomList .roomItem').filter({ has: page.getByText(name, { exact: true }) });
  await item.locator('span.saveBtn', { hasText: '⚙ 设置' }).click();
  await expect(page.locator('#cHeight')).toHaveValue('0.5');
  await expect(page.locator('#cWater')).toHaveValue('1');
  await expect(page.locator('#cBld')).toHaveValue('1');
});
