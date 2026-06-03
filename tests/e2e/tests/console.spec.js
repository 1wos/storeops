// Owner Ops Console — 데모에 필요한 패널들이 실제로 렌더되는지(LLM 무관).
// Owner Ops Console — the demo-critical panels actually render (no LLM needed).
const { test, expect } = require('@playwright/test');

test.beforeEach(async ({ page }) => {
  await page.goto('/');
});

test('console loads with the Off-Duty brand', async ({ page }) => {
  await expect(page).toHaveTitle(/Off-Duty/i);
  await expect(page.getByText('Off-Duty').first()).toBeVisible();
});

test('summary cards render with numbers from the API', async ({ page }) => {
  const cards = page.locator('#cards');
  await expect(cards).toBeVisible();
  // 카운트업 카드가 최소 1개는 채워져야 / at least one card materializes
  await expect.poll(async () => (await cards.locator('> *').count())).toBeGreaterThan(0);
});

test('"Needs you" approval inbox is present at the top', async ({ page }) => {
  await expect(page.getByText('Needs you', { exact: false }).first()).toBeVisible();
  await expect(page.locator('#approvals')).toBeAttached();
});

test('MongoDB engine panel (explain + collections) renders', async ({ page }) => {
  await expect(page.getByText('MongoDB engine', { exact: false })).toBeVisible();
  const body = page.locator('#mdbBody');
  await expect.poll(async () => (await body.textContent()) || '', { timeout: 15_000 })
    .not.toContain('Loading');
});

test('MongoDB MCP panel + live-call button are present', async ({ page }) => {
  await expect(page.locator('#mcpBox > summary')).toContainText('MongoDB MCP');
  await page.locator('#mcpBox > summary').click(); // 펼쳐서 버튼 노출 / expand to reveal button
  await expect(page.locator('.mcp-btn')).toBeVisible();
  await expect(page.locator('.mcp-btn')).toHaveText(/Run live MCP call/i);
});

test('approval rows offer both Approve and Reject (HITL)', async ({ page }) => {
  const inbox = page.locator('#approvals');
  await expect(inbox).toBeVisible();
  // 승인 항목이 있으면 Approve+Reject 둘 다 있어야 / if any pending, both buttons exist
  const rows = inbox.locator('.appr');
  if (await rows.count()) {
    await expect(rows.first().locator('.bn-app')).toHaveText(/Approve/);
    await expect(rows.first().locator('.bn-rej')).toHaveText(/Reject/);
  }
});

test('impact stat shows in the digest', async ({ page }) => {
  await expect.poll(async () => (await page.locator('#digest').textContent()) || '', { timeout: 15_000 })
    .toMatch(/saved|min/i);
});

test('vision photo-upload card is visible (not hidden)', async ({ page }) => {
  await expect(page.getByText('Store-State', { exact: false })).toBeVisible();
  await expect(page.locator('#vphoto')).toBeAttached();
});

test('agent activity timeline section exists', async ({ page }) => {
  await expect(page.locator('#timeline')).toBeAttached();
});

test('ask box is present for owner questions', async ({ page }) => {
  await expect(page.locator('#askIn')).toBeVisible();
});
