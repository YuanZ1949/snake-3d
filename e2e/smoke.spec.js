// 批9 C2：前端冒烟 —— 加载 / 房间列表 / 单人入局 / 快照到达 / canvas 有内容 / 全程无 JS 报错
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const SHOT_DIR = path.join(__dirname, '..', 'test-results');

function watchErrors(page) {
  const errors = [];
  page.on('pageerror', err => errors.push('pageerror: ' + err.message));
  page.on('console', msg => {
    if (msg.type() !== 'error') return;
    const t = msg.text();
    if (t.includes('favicon')) return;                 // 浏览器默认请求，非代码问题
    errors.push('console.error: ' + t);
  });
  return errors;
}

function watchFrames(page, re) {
  const flag = { got: false };
  page.on('websocket', ws => {
    ws.on('framereceived', f => {
      if (re.test(String(f.payload))) flag.got = true;
    });
  });
  return flag;
}

test('首页加载干净且房间列表有内容', async ({ page }) => {
  const errors = watchErrors(page);
  const rooms = watchFrames(page, /"t":\s*"rooms"/);   // json.dumps 分隔符带空格
  await page.goto('/');
  await expect(page.locator('h1')).toHaveText('贪吃蛇 3D');
  await expect(page.locator('#startScreen')).toBeVisible();
  // 首屏自动拉房间列表：至少渲染出 1 个房间卡片（默认房间常驻）
  await page.waitForFunction(() => document.querySelectorAll('#roomList .roomItem').length >= 1, null, { timeout: 10000 });
  // rooms 帧必须经 ws 到达
  await expect.poll(() => rooms.got, { timeout: 10000 }).toBe(true);
  await page.waitForTimeout(800);
  fs.mkdirSync(SHOT_DIR, { recursive: true });
  await page.screenshot({ path: path.join(SHOT_DIR, 'smoke-home.png'), fullPage: false });
  expect(errors, errors.join('\n')).toEqual([]);
});

test('单人练习入局：收到快照、蛇动起来、canvas 非空、无报错', async ({ page }) => {
  const errors = watchErrors(page);
  const snap = watchFrames(page, /"t":\s*"snap"/);
  await page.goto('/');
  // 点「🐍 单人练习」：自动建 24×24 + 3 AI 房并入局（批4）
  await page.click('#btnSolo');
  await page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 15000 });
  // 等服务端快照到达（入局成功判据）
  await expect.poll(() => snap.got, { timeout: 15000 }).toBe(true);
  // 让蛇跑 1.5s，观察帧率内无 JS 异常
  await page.waitForTimeout(1500);
  // canvas 必须有实际绘制内容（toDataURL 非空白）
  const shotLen = await page.evaluate(() => document.getElementById('game').toDataURL('image/png').length);
  expect(shotLen).toBeGreaterThan(2000);
  // HUD 显示分数（入局态 DOM 判据）
  await expect(page.locator('#score')).toBeVisible();
  fs.mkdirSync(SHOT_DIR, { recursive: true });
  await page.screenshot({ path: path.join(SHOT_DIR, 'smoke-ingame.png'), fullPage: false });
  expect(errors, errors.join('\n')).toEqual([]);
});

test('观战进入与返回主页无报错', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await page.waitForFunction(() => document.querySelectorAll('#roomList .roomItem').length >= 1, null, { timeout: 10000 });
  await page.click('#btnSpectate');
  // 观战态：主页隐藏 + 连接提示「观战中」
  await page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 10000 });
  await page.waitForTimeout(1200);
  await page.click('#btnHome');
  await page.waitForFunction(() => !document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 10000 });
  expect(errors, errors.join('\n')).toEqual([]);
});
