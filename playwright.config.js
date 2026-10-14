// 批9 C2：Playwright 冒烟配置（外部起服，与本地 7 套 E2E 同模式）
const BASE = process.env.BASE || 'http://127.0.0.1:8123';

module.exports = {
  testDir: './e2e',
  timeout: 60000,
  retries: 0,
  workers: 1,                 // 单人冒烟串行，避免互抢同一房间
  reporter: [['list']],
  use: {
    baseURL: BASE,
    headless: true,
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
};
