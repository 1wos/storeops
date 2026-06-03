// Customer Counter — 주문 화면이 로드되고 핵심 요소가 보이는지(LLM 무관).
// Customer Counter — the ordering screen loads with its core elements (no LLM needed).
const { test, expect } = require('@playwright/test');

test.beforeEach(async ({ page }) => {
  await page.goto('/counter');
});

test('counter loads with a greeting bubble', async ({ page }) => {
  await expect(page).toHaveTitle(/Counter/i);
  await expect(page.locator('.b.bot').first()).toContainText(/Off-Duty/i);
});

test('live availability strip renders in-stock items', async ({ page }) => {
  await expect(page.locator('#avail')).toBeVisible();
  await expect(page.getByText('Available now', { exact: false })).toBeVisible();
  // 가용 칩이 하나라도 떠야(재고가 있으면) / at least one availability chip when stock exists
  await expect.poll(async () => (await page.locator('.av-chip').count()), { timeout: 15_000 })
    .toBeGreaterThan(0);
});

test('suggestion chips and composer are usable', async ({ page }) => {
  await expect(page.locator('.chip').first()).toBeVisible();
  await expect(page.locator('#in')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Send' })).toBeVisible();
});

test('mobile input font is >=16px (no iOS zoom)', async ({ page }) => {
  const fs = await page.locator('#in').evaluate(el => getComputedStyle(el).fontSize);
  expect(parseFloat(fs)).toBeGreaterThanOrEqual(16);
});
