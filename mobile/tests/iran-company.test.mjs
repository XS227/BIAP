// Run: node --experimental-strip-types --no-warnings --test tests/iran-company.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';

const status = await import('../src/lib/data-status.ts');

test('price statuses never show unknown-age or stale data as verified', () => {
  assert.equal(status.priceStatus('VERIFIED'), 'verified');
  assert.equal(status.priceStatus('STALE'), 'stale');
  assert.equal(status.priceStatus('UNKNOWN_AGE'), 'stale');
  assert.equal(status.priceStatus('MISSING'), 'missing');
  assert.equal(status.priceStatus(undefined), 'stale');
});

test('Persian status vocabulary covers verified / stale / missing / failed', () => {
  assert.equal(status.DATA_STATUS_FA.verified, 'تأییدشده');
  assert.equal(status.DATA_STATUS_FA.stale, 'کهنه');
  assert.equal(status.DATA_STATUS_FA.missing, 'ناموجود');
  assert.equal(status.DATA_STATUS_FA.failed, 'ناموفق');
});

test('agent and audit labels: zero-confidence agent is "no valid data", insufficient is explicit', () => {
  assert.equal(status.agentStatusFa('NO_DATA'), 'داده معتبر ندارد');
  assert.equal(status.agentStatusFa('MISSING'), 'ناموجود');
  assert.equal(status.auditStatusFa('INSUFFICIENT_DATA'), 'داده کافی نیست');
  assert.equal(status.auditStatusFa('RED_FLAG'), 'پرچم قرمز');
});

test('missing numbers render as a dash, never as zero', () => {
  assert.equal(status.faNumber(null), '—');
  assert.equal(status.faNumber(undefined), '—');
  assert.notEqual(status.faNumber(0), '—');
  assert.equal(status.faDate(null), 'ثبت نشده');
});

test('describeIranError: missing endpoint vs missing company vs rate limit', async () => {
  const m = status;
  assert.match(m.describeIranError({ status: 404, message: 'Not Found' }), /هنوز این قابلیت را ندارد/);
  assert.match(m.describeIranError({ status: 404, message: 'شرکتی با این نماد پیدا نشد' }), /پیدا نشد/);
  assert.match(m.describeIranError({ status: 429, message: 'سقف' }), /سقف/);
  assert.match(m.describeIranError({ status: 401, message: 'x' }), /وارد شوید/);
});


test('stale Pekerman BUY is explicitly non-actionable when financials and agent evidence are missing', () => {
  const view = {
    price: { status: 'STALE', conflictsWithKiasha: true },
    financials: { available: false },
    agents: Array.from({ length: 7 }, (_, i) => ({ dataStatus: i === 0 ? 'NO_DATA' : 'OK', confidence: i === 0 ? null : 0.7 })),
    kiasha: { call: 'BUY' },
  };
  const result = status.assessIranStoredDecisionReadiness(view);
  assert.equal(result.evidenceComplete, false);
  assert.equal(result.tradeEnabled, false);
  assert.ok(result.reasons.length >= 3);
  const complete = status.assessIranStoredDecisionReadiness({
    ...view, price: { status: 'VERIFIED', conflictsWithKiasha: false },
    financials: { available: true },
    agents: Array.from({ length: 7 }, () => ({ dataStatus: 'OK', confidence: 0.7 })),
  });
  assert.equal(complete.evidenceComplete, true);
  assert.equal(complete.tradeEnabled, false);
});
