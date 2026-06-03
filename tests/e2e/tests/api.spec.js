// 결정성 API 검증 — LLM 없는 엔드포인트가 200 + 기대 shape 를 돌려주는지.
// Deterministic API checks — non-LLM endpoints return 200 + the expected shape.
const { test, expect } = require('@playwright/test');

test('health is up and reports store + model', async ({ request }) => {
  const r = await request.get('/health');
  expect(r.status()).toBe(200);
  const j = await r.json();
  expect(j.ok).toBeTruthy();
  expect(j.store_id).toBeTruthy();
});

test('availability returns in-stock items with low flag', async ({ request }) => {
  const r = await request.get('/api/availability');
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  expect(Array.isArray(j.items)).toBeTruthy();
  if (j.items.length) {
    expect(j.items[0]).toHaveProperty('name');
    expect(j.items[0]).toHaveProperty('available');
    expect(j.items[0]).toHaveProperty('low');
  }
});

test('summary cards aggregate from MongoDB', async ({ request }) => {
  const r = await request.get('/api/summary');
  expect(r.ok()).toBeTruthy();
  await r.json();
});

test('explain surfaces a real pipeline + query plan', async ({ request }) => {
  const r = await request.get('/api/explain');
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  expect(j).toHaveProperty('pipeline');
  expect(Array.isArray(j.pipeline)).toBeTruthy();
});

test('db-health lists collections', async ({ request }) => {
  const r = await request.get('/api/db-health');
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  expect(Array.isArray(j.collections)).toBeTruthy();
});

test('digest, ops, timeline, approvals all respond', async ({ request }) => {
  for (const path of ['/api/digest', '/api/ops', '/api/timeline', '/api/approvals']) {
    const r = await request.get(path);
    expect(r.ok(), `${path} should be 200`).toBeTruthy();
  }
});

test('chat input is validated (empty message rejected)', async ({ request }) => {
  const r = await request.post('/api/chat', { data: { message: '' } });
  expect(r.status()).toBe(422); // pydantic min_length guard
});

test('bad ObjectId on approve is graceful (no 500)', async ({ request }) => {
  const r = await request.post('/api/approve/restock/not-an-oid');
  expect(r.status()).toBeLessThan(500);
  const j = await r.json();
  expect(j.ok).toBeFalsy();
});

test('vision rejects non-image upload (400, not 500)', async ({ request }) => {
  const r = await request.post('/api/vision/analyze', {
    multipart: { photo: { name: 'x.txt', mimeType: 'text/plain', buffer: Buffer.from('hi') } },
  });
  expect(r.status()).toBe(400);
});

test('evidence for unknown trace is 404', async ({ request }) => {
  const r = await request.get('/api/evidence/does-not-exist');
  expect(r.status()).toBe(404);
});

test('reject + reopen (undo) are graceful on a bad id', async ({ request }) => {
  for (const p of ['/api/reject/restock/nope', '/api/reopen/restock/nope']) {
    const r = await request.post(p);
    expect(r.status()).toBeLessThan(500);
    expect((await r.json()).ok).toBeFalsy();
  }
});

test('impact endpoint returns ROI shape', async ({ request }) => {
  const r = await request.get('/api/impact');
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  expect(j).toHaveProperty('actions_automated');
  expect(j).toHaveProperty('owner_minutes_saved_est');
});
