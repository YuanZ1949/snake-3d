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
  // 点「🐍 单人练习」：自动建 48×48 + 3 AI 房并入局（批4；批41 尺寸 24→48）
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

// 批16 B：建房面板 select 强制暗色下拉，且作用域不外溢到全站
test('建房面板下拉暗色且不波及全站', async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto('/');
  await page.waitForFunction(() => document.querySelectorAll('#roomList .roomItem').length >= 1, null, { timeout: 10000 });
  await page.click('#btnRoomCreate');
  await expect(page.locator('#cSize')).toBeVisible();
  const panelCs = await page.evaluate(() => getComputedStyle(document.getElementById('cSize')).colorScheme);
  expect(panelCs).toBe('dark');
  const bodyCs = await page.evaluate(() => getComputedStyle(document.body).colorScheme);
  expect(bodyCs).not.toBe('dark');   // 限定作用域：body 不得被连带强制暗色
  expect(errors, errors.join('\n')).toEqual([]);
});

// 批16 G：死亡结算屏 →「观战」按钮衔接 spectate()（真实撞墙死亡驱动，无调试钩子）
test('死亡后点观战进入观战态无报错', async ({ page }) => {
  const errors = watchErrors(page);
  const snap = watchFrames(page, /"t":\s*"snap"/);
  await page.goto('/');
  await page.click('#btnSolo');
  await page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 15000 });
  await expect.poll(() => snap.got, { timeout: 15000 }).toBe(true);
  // 固定视角下方向键是绝对方向：循环按左把蛇钉死向西直到撞墙（护盾偏转也被重新钉回），任何死因都进结算屏
  await page.click('#btnCam');
  await expect(page.locator('#btnCam')).toHaveText('🧭固定');
  const overShown = () => page.locator('#overScreen').evaluate(el => !el.classList.contains('hidden'));
  for (let i = 0; i < 40 && !(await overShown()); i++) {
    await page.keyboard.press('ArrowLeft');
    await page.waitForTimeout(700);
  }
  await page.waitForFunction(() => !document.getElementById('overScreen').classList.contains('hidden'), null, { timeout: 5000 });
  // 死亡 500ms 后结算屏弹出且含观战按钮
  await expect(page.locator('#overScreen')).toBeVisible();
  await expect(page.locator('#btnOverSpectate')).toBeVisible();
  await page.click('#btnOverSpectate');
  // 衔接判据：结算屏收起 + 出现「加入对战」（spectate 前置动作），后续快照继续到达且无报错
  await page.waitForFunction(() => document.getElementById('overScreen').classList.contains('hidden'), null, { timeout: 5000 });
  await expect(page.locator('#btnJoinIn')).toBeVisible();
  await page.waitForTimeout(1200);
  expect(errors, errors.join('\n')).toEqual([]);
});
