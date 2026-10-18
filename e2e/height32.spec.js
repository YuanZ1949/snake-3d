// 批32：高度地形（hmap）——客户端渲染 + 房间编辑面三旋钮 + 探针
// 协议：full 帧带 "hmap": [[x,y,h],...]（PROTO 28）；探针 __mapDbgSet/__heightDbg 不走服务端。
const { test, expect } = require('@playwright/test');
const { ensureLogin } = require('./_helpers');

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

test('蛇节按 hmap 抬升 + 预测挡崖', async ({ page }) => {
  await ensureLogin(page, 'yuan', '123456');
  await page.click('#btnSolo');
  await page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 15000 });
  const base = await page.evaluate(() => window.__heightDbg());   // 平地基准（headY≈SEG_H/2）
  // 1) 走廊抬升：头格起沿 dir 6 格全 h=2（蛇移动也保持在高台上）
  await page.evaluate(() => window.__mapSelfCorridorSet(2));
  await page.waitForTimeout(400);
  const d = await page.evaluate(() => window.__heightDbg());
  expect(d.headY).toBeGreaterThan(base.headY + 0.5);              // visH(2)=0.7 → 抬升 ≥0.5
  // 2) 预测挡崖：头前一格注入 h=4（相对头格上行 ≥2）→ advanceStep 悬停
  await page.evaluate(() => window.__mapSelfCliffBlock());
  const d2 = await page.evaluate(() => window.__heightDbg());
  expect(d2.blocked).toBe(true);
});

test('批34 地形遮挡：实体地形 depthWrite=true，水/草/元素面片 depthWrite=false', async ({ page }) => {
  await ensureLogin(page, 'yuan', '123456');
  await page.click('#btnSolo');
  await page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 15000 });
  // 一次注入全部 6 类：丘1/峰2/楼3/深渊9/水-1/草-2
  await page.evaluate(() => window.__mapDbgSet([[5, 5, 1], [5, 6, 2], [5, 7, 3], [5, 8, 9], [5, 9, -1], [5, 10, -2]]));
  await page.waitForTimeout(300);
  const dw = await page.evaluate(() => window.__heightMeshDump());
  const byKind = k => dw.filter(m => m.kind === k);
  for (const k of ['c1', 'c2', 'c3', 'ab']) {
    expect(byKind(k).length, `kind=${k} 应有 mesh`).toBe(1);
    expect(byKind(k)[0].dw, `kind=${k} 必须写深度（真遮挡，山后之蛇被挡住）`).toBe(true);   // 批34：丘/峰/楼/深渊 挡视线
  }
  for (const k of ['w', 'g']) {
    expect(byKind(k).length, `kind=${k} 应有 mesh`).toBe(1);
    expect(byKind(k)[0].dw, `kind=${k} 是地板贴层不得写深度（否则会挡住地板上的蛇）`).toBe(false);
  }
  // 元素面片（批33）同理：贴层不遮挡
  await page.evaluate(() => window.__elemDbgSet([[6, 5, 'pyro'], [6, 6, 'cryo']]));
  await page.waitForTimeout(200);
  const ed = await page.evaluate(() => window.__elemMeshDump());
  expect(ed.length).toBe(2);
  for (const e of ed) expect(e.dw, `元素面片 ${e.elem} 不得写深度`).toBe(false);
});
