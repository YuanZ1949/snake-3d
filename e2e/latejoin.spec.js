// 批29-③：进房不该先见「平局」（上一局结算对刚进房者）
// 链路：A 建积分赛房（score 模式只在全员阵亡时结算）独自进局撞死（joined<2 不提前结算）
//       → B 进房撞死 → alive=0 结算（ev win 到达 A/B，参与者见具体结果）
//       → 20s 结算窗口内 C 进房：A、B 均未点准备 → win_pending 未消化 → C 首拍
//         over=true + state='joining' → 批23 P5③ 补屏 → 修前 title='平局'/'🏆XX'（C 没参与）
// 修法：handleRound P5③ 分支只对 win===myId（resume 赢家本人）保留🏆，其余中性「上一局已结束」。
// 注意：check_win 有 len(joined)<2 守卫（serve.py:1060），单人房永不结算——故须 B 加入。
const { test, expect } = require('@playwright/test');

let _seq = 0;
const uniq = (base) => `${base}${(++_seq).toString(36)}${Date.now().toString(36).slice(-3)}`;

async function createScoreRoom(page, name) {
  await page.locator('#btnRoomCreate').click();
  await page.locator('#cName').fill(name);
  await page.locator('#cWin').selectOption('score');       // 积分·全员阵亡结算（先后死不提前判胜）
  await page.locator('#btnCreateGo').click();
  await expect(page.locator('#roomList').getByText(name, { exact: true })).toHaveCount(1);
}

async function joinRoom(page, roomName) {
  await page.locator('#roomList').getByText(roomName, { exact: true }).click();
  await page.click('#btnStart');
  await page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 15000 });
}

async function joinCurrentRoom(page) {                     // A：建房回执已顶 curRoom，直点开始
  await page.click('#btnStart');
  await page.waitForFunction(() => document.getElementById('startScreen').classList.contains('hidden'), null, { timeout: 15000 });
}

const overShown = (page) => page.locator('#overScreen').evaluate(el => !el.classList.contains('hidden'));
const overTitle = (page) => page.locator('#overTitle').textContent();

// 固定视角下循环按左把蛇钉死向西直到撞墙（smoke.spec.js:102-110 先例）
async function suicideByWall(page) {
  await page.click('#btnCam');
  await expect(page.locator('#btnCam')).toHaveText('🧭固定');
  for (let i = 0; i < 40 && !(await overShown(page)); i++) {
    await page.keyboard.press('ArrowLeft');
    await page.waitForTimeout(500);
  }
  await page.waitForFunction(() => !document.getElementById('overScreen').classList.contains('hidden'), null, { timeout: 15000 });
}

test('第三者进 over 房只见中性文案，参与者仍见具体结果', async ({ page, browser }) => {
  test.setTimeout(180000);
  const roomName = uniq('终局房');

  // ---- A：建积分赛房独自进局撞死 ----
  await page.goto('/');
  await createScoreRoom(page, roomName);
  await joinCurrentRoom(page);
  await suicideByWall(page);
  expect(await overTitle(page)).toBe('你被淘汰了');          // 死亡屏（joined<2 不结算）

  // ---- B：进同房撞死 → alive=0 → 结算 ev 到达 A ----
  const ctx2 = await browser.newContext();
  const p2 = await ctx2.newPage();
  await p2.goto('/');
  await joinRoom(p2, roomName);
  await suicideByWall(p2);
  // 结算到达 A：title 从死亡文案被 onWin 覆盖为具体结果（平局 or 🏆胜者，取决于谁吃到果）
  await page.waitForFunction(
    () => document.getElementById('overTitle').textContent !== '你被淘汰了',
    null, { timeout: 10000 });
  const aTitle = await overTitle(page);
  console.log('A settle title =', aTitle);
  expect(aTitle).not.toBe('上一局已结束');                   // 参与者见具体结果（护栏：中性文案不得污染）

  // ---- C：20s 结算窗口内进房 → P5③ 补屏必须中性（RED：修前为 '平局' 或 '🏆XX'）----
  const ctx3 = await browser.newContext();
  const p3 = await ctx3.newPage();
  await p3.goto('/');
  await joinRoom(p3, roomName);
  await p3.waitForFunction(() => !document.getElementById('overScreen').classList.contains('hidden'), null, { timeout: 10000 });
  expect(await overTitle(p3)).toBe('上一局已结束');
  await expect(p3.locator('#overSub')).toContainText('准备');  // 功能屏保留（准备指引不丢）

  await ctx3.close();
  await ctx2.close();
});
