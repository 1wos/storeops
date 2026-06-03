// 데모 평가용 스크린샷 — 콘솔/카운터를 데스크탑+모바일로 캡처. ad-hoc, not a test.
const { chromium } = require('@playwright/test');
const fs = require('fs');

(async () => {
  const dir = '/tmp/offduty_shots';
  fs.mkdirSync(dir, { recursive: true });
  const browser = await chromium.launch();
  const shots = [
    { name: 'console-desktop', url: '/', w: 1366, h: 1100 },
    { name: 'console-mobile', url: '/', w: 390, h: 1400 },
    { name: 'counter-desktop', url: '/counter', w: 1366, h: 900 },
    { name: 'counter-mobile', url: '/counter', w: 390, h: 844 },
  ];
  for (const s of shots) {
    const page = await browser.newPage({ viewport: { width: s.w, height: s.h } });
    await page.goto('http://127.0.0.1:8080' + s.url, { waitUntil: 'networkidle' });
    await page.waitForTimeout(2500); // count-up + availability render
    await page.screenshot({ path: `${dir}/${s.name}.png`, fullPage: true });
    console.log('shot', s.name);
    await page.close();
  }
  await browser.close();
})();
