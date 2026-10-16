// 批28-A 探针：自己创建的空联机房在建第二个房（/去打单人练习）后仍留在房间列表
// 根因：renderRooms 只显示 players>0 活跃房 + 当前 curRoom 空房；
// created handler 把 curRoom 顶到新房后，前一个等朋友的空房从列表消失（误以为被覆盖/只能建一个房）。
const { test, expect } = require('@playwright/test');

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await page.waitForFunction(() => typeof window.__gachaDbg === 'function');
});

async function createRoom(page, name) {
  await page.locator('#btnRoomCreate').click();          // 展开创建面板
  await page.locator('#cName').fill(name);
  await page.locator('#btnCreateGo').click();
  await expect(page.locator('#roomList .roomItem .nm', { hasText: name })).toHaveCount(1);
}

test('自己创建的空房在建第二个房后仍显示', async ({ page }) => {
  await createRoom(page, '联机房A');
  await createRoom(page, '联机房B');                      // curRoom 被顶到 B
  // 两个自己建的空房都应留在列表（RED：A 消失）
  await expect(page.locator('#roomList .roomItem .nm', { hasText: '联机房A' })).toHaveCount(1);
  await expect(page.locator('#roomList .roomItem .nm', { hasText: '联机房B' })).toHaveCount(1);
});

test('无关的空房（非我的、非选中）不挤入列表', async ({ page }) => {
  await createRoom(page, '我的房');
  // 默认房 a/b/c 初始 0 人且非我所建、非当前选中 → 不应全挤进列表
  const shown = await page.locator('#roomList .roomItem .nm').allTextContents();
  expect(shown).toContain('我的房');                      // 我的空房在
  // 至少一个默认空房被过滤（列表精简，不是把所有空房都塞进来）
  expect(shown.length).toBeLessThanOrEqual(2);            // 我的房 + 最多一个选中空房
});
