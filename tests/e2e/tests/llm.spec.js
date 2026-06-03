// LLM 의존 흐름(@llm) — Gemini/MCP 콜드스타트·무료티어로 느리거나 rate-limit 가능.
// 따라서 '성공 OR 우아한 에러' 둘 다 통과로 본다(데모 안정성 = graceful degradation).
// LLM-dependent flows (@llm) — Gemini/MCP can be slow or rate-limited, so we accept
// EITHER a real result OR a graceful error. The point is: it must never hard-crash.
const { test, expect } = require('@playwright/test');

test.describe('@llm slow paths', () => {
  test.describe.configure({ timeout: 150_000 });

  test('counter chat returns a reply or a graceful message', async ({ page }) => {
    await page.goto('/counter');
    await page.locator('#in').fill("What's available right now?");
    await page.getByRole('button', { name: 'Send' }).click();
    // 사용자 버블 즉시, 봇 버블은 응답 후 / user bubble immediately, bot bubble after the run
    await expect(page.locator('.b.user').last()).toContainText("available", { timeout: 5_000 });
    await expect(page.locator('.b.bot')).toHaveCount(2, { timeout: 140_000 }); // greet + reply
    const reply = await page.locator('.b.bot').last().textContent();
    expect((reply || '').trim().length).toBeGreaterThan(0);
  });

  test('console MCP button yields tool_calls or a graceful error', async ({ page }) => {
    await page.goto('/');
    // 패널 펼치고 버튼 클릭 / open the panel, click the live-call button
    await page.locator('#mcpBox > summary').click();
    await page.locator('.mcp-btn').click();
    const out = page.locator('#mcpOut');
    // 성공(via ...) 또는 graceful 에러 문구 중 하나가 떠야 / either outcome, never a blank hang
    await expect(out).toContainText(/via MongoDB MCP server|MCP call|timed out|failed|retry/i, {
      timeout: 140_000,
    });
  });
});
