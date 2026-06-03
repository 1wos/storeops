// @ts-check
const { defineConfig, devices } = require('@playwright/test');

// 데모 직전 'UI가 라이브에서 깨지지 않는다'를 자동 검증. 서버는 자동 기동(이미 떠있으면 재사용).
// Verifies the web UIs work end-to-end before a live demo. The app server is started
// automatically (or reused if already running on 8080).
const PORT = process.env.PORT || 8080;
const BASE = `http://127.0.0.1:${PORT}`;

module.exports = defineConfig({
  testDir: './tests',
  fullyParallel: false,            // 공유 DB 상태라 직렬 / shared DB state → run serial
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  timeout: 30_000,                 // 기본 테스트 타임아웃 / default per-test
  expect: { timeout: 10_000 },
  use: {
    baseURL: BASE,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  // 앱 서버 자동 기동: uvicorn 을 integration 루트에서 실행. health 200 이면 준비 완료.
  // Auto-start the app server from the integration root; ready when /health is 200.
  webServer: {
    command: 'python -m uvicorn app.main:app --port ' + PORT,
    cwd: '../..',
    url: `${BASE}/health`,
    timeout: 60_000,
    reuseExistingServer: true,
  },
});
