// 批30③b：对局暂停=挂机（设计拍板：单人/联机都支持，暂停者原地冻结+现有保护，其他人正常）
// 链路：自建房进局 → HUD「⏸ 暂停」→ 服务端 toggle off_at+pause → pauseres on
//       → 提示胶囊「已挂机 · 点按恢复」出现 + 按钮变「▶ 恢复」
//       暂停中聊天照常可用（设计硬要求：挂机不锁交互）
//       点胶囊 → pauseres off → 胶囊消失 + 按钮回「⏸ 暂停」
// 第二入口：dpad 中心「暂停」键（手机主入口，对局中同语义；主页 demo 暂停行为不变）
// 服务端语义（单测 test_pause_afk_batch30 / test_pause_counts_as_present_batch30 钉住）：
//   冻结+不被咬/不顶头（复用 off_at）、dir/atk/ult 拒收、session 在则超 RESUME_MS 不回收、
//   挂机者算在场真人（他人断线挂起不移出）。
const { test, expect } = require('@playwright/test');

let _seq = 0;
const uniq = (base) => `${base}${(++_seq).toString(36)}${Date.now().toString(36).slice(-3)}`;

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await page.waitForFunction(() => typeof window.__gachaDbg === 'function');
});

async function joinFreshRoom(page, name) {
  await page.locator('#btnRoomCreate').click();
  await page.locator('#cName').fill(name);
  await page.locator('#btnCreateGo').click();
  await expect(page.locator('#roomList').getByText(name, { exact: true })).toHaveCount(1);
  await page.locator('#roomList').getByText(name, { exact: true }).click();
  await page.click('#btnStart');
  await page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 15000 });
}

test('HUD 暂停键 → 挂机胶囊，聊天不受锁，点按恢复', async ({ page }) => {
  test.setTimeout(60000);
  await joinFreshRoom(page, uniq('挂机房'));

  // 暂停前：胶囊隐藏
  await expect(page.locator('#pauseMask')).toBeHidden();

  // HUD「⏸ 暂停」→ pauseres on → 胶囊 + 按钮变「恢复」
  await page.locator('#btnPauseGame').click();
  await expect(page.locator('#pauseMask')).toBeVisible();
  await expect(page.locator('#pauseMask')).toContainText('已挂机');
  await expect(page.locator('#btnPauseGame')).toHaveText('▶ 恢复');

  // 暂停中聊天照常可用（不锁交互）：面板开、发言、回显
  await page.locator('#btnChat').click();
  await expect(page.locator('#chatPanel')).toBeVisible();
  const msg = '挂机聊天' + Date.now().toString(36);
  await page.locator('#cpIn').fill(msg);
  await page.locator('#cpIn').press('Enter');
  await expect(page.locator('#cpLog')).toContainText(msg);
  await page.locator('#cpClose').click();
  await expect(page.locator('#chatPanel')).toBeHidden();

  // 点胶囊恢复 → pauseres off → 胶囊消失、按钮回「暂停」
  await page.locator('#pauseMask').click();
  await expect(page.locator('#pauseMask')).toBeHidden();
  await expect(page.locator('#btnPauseGame')).toHaveText('⏸ 暂停');
});

test('dpad 中心暂停键同语义（手机主入口）', async ({ page }) => {
  test.setTimeout(60000);
  await joinFreshRoom(page, uniq('挂机房2'));

  await expect(page.locator('#pauseMask')).toBeHidden();
  await page.locator('#btnPause').click();          // dpad 中心键（对局中=挂机）
  await expect(page.locator('#pauseMask')).toBeVisible();
  await expect(page.locator('#btnPause')).toHaveText('继续');
  await page.locator('#pauseMask').click();
  await expect(page.locator('#pauseMask')).toBeHidden();
  await expect(page.locator('#btnPause')).toHaveText('暂停');
});
