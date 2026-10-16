// 房间列表回归（批28-A 引入 → 批29-② 修正）
// 批28-A 规则：active(players>0) + 空房(curRoom||isMine) → 生产无活跃对局时列表只剩自己那间
// （用户报「修改完后房间列表只剩一个房间看不到其他房间」，根因即此过滤，与修改动作无关）。
// 批29-② 方案 B（已拍板）：显示全部房间；空闲垃圾房由服务端 gc 兜底（非持久空房 24h 回收）。
// 注意：全量显示后房名匹配必须全等 + 每轮唯一（server 房间跨测试共享，同名累积会让子串匹配爆炸）。
const { test, expect } = require('@playwright/test');

// 每个房名唯一（server 房间跨测试共享且不自动回收，同名会让全等断言 count>1）
let _seq = 0;
function uniq(base) {
  return `${base}${(_seq++).toString(36)}${Date.now().toString(36).slice(-3)}`;
}

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await page.waitForFunction(() => typeof window.__gachaDbg === 'function');
});

// 房名全等定位（避免 hasText 子串误配，如 '房A' 命中 '联机房A'）
function nm(page, name) {
  return page.locator('#roomList').getByText(name, { exact: true });
}

async function createRoom(page, name) {
  await page.locator('#btnRoomCreate').click();          // 展开创建面板
  await page.locator('#cName').fill(name);
  await page.locator('#btnCreateGo').click();
  await expect(nm(page, name)).toHaveCount(1);
}

async function renameRoom(page, oldName, newName) {
  const item = page.locator('#roomList .roomItem').filter({ has: page.getByText(oldName, { exact: true }) });
  await item.locator('span.saveBtn', { hasText: '⚙ 设置' }).click();
  await page.locator('#cName').fill(newName);
  await page.locator('#btnCreateGo').click();            // 💾 保存设置
}

test('自己创建的空房在建第二个房后仍显示', async ({ page }) => {
  const a = uniq('联机房A'), b = uniq('联机房B');
  await createRoom(page, a);
  await createRoom(page, b);                             // curRoom 被顶到 B
  // 两个自己建的空房都应留在列表（批28-A 回归）
  await expect(nm(page, a)).toHaveCount(1);
  await expect(nm(page, b)).toHaveCount(1);
});

test('空闲的默认房与别人的空房也全部显示', async ({ page }) => {
  const mine = uniq('我的房');
  await createRoom(page, mine);
  const shown = await page.locator('#roomList .roomItem .nm').allTextContents();
  expect(shown).toContain(mine);
  // 批29-② 方案 B：默认房 a/b/c 无论空闲恒显示（RED：批28-A 旧规则会过滤掉）
  expect(shown).toContain('新手村');
  expect(shown).toContain('标准局');
  expect(shown).toContain('大神场');
  expect(shown.length).toBeGreaterThanOrEqual(4);
});

test('建两房后改名 → 两房仍可见', async ({ page }) => {
  const a = uniq('房A'), b = uniq('房B'), b2 = b + '改';
  await createRoom(page, a);
  await createRoom(page, b);
  await renameRoom(page, b, b2);
  await page.waitForTimeout(500);                         // 等 broadcast 回执
  const shown = await page.locator('#roomList .roomItem .nm').allTextContents();
  expect(shown).toContain(a);
  expect(shown).toContain(b2);
});

test('有活跃房时改名 → 两房仍可见', async ({ page, browser }) => {
  const a = uniq('房A'), b = uniq('房B'), b2 = b + '改';
  await createRoom(page, a);
  await createRoom(page, b);
  // 第二页选中并进入房A → A 变活跃
  const ctx2 = await browser.newContext();
  const p2 = await ctx2.newPage();
  await p2.goto('/');
  await p2.waitForFunction(() => typeof window.__gachaDbg === 'function');
  await p2.locator('#roomList .roomItem').filter({ has: p2.getByText(a, { exact: true }) }).click();
  await p2.locator('#btnSolo').click();                   // 单人练习（载具，进局）
  await p2.waitForTimeout(800);
  await renameRoom(page, b, b2);
  await page.waitForTimeout(500);
  const shown = await page.locator('#roomList .roomItem .nm').allTextContents();
  expect(shown).toContain(a);
  expect(shown).toContain(b2);
  await ctx2.close();
});

test('首页显示当前在线人数（≥1，去重口径）', async ({ page }) => {
  // 批30②：welcome/online 推送渲染；toHaveText 自带重试等首帧推送落地
  const box = page.locator('#onlineBox');
  await expect(box).toHaveText(/当前在线\s*\d+\s*人/);
  const n = parseInt((await box.textContent()).match(/\d+/)[0], 10);
  expect(n).toBeGreaterThanOrEqual(1);
});
