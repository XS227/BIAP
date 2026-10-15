// Run: node --experimental-strip-types --test tests/global-api.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';

const api = await import('../src/lib/global-api.ts');
const realFetch = globalThis.fetch;
const realSetTimeout = globalThis.setTimeout;

function jsonResponse(status, body) {
  return { ok: status >= 200 && status < 300, status, text: async () => JSON.stringify(body), json: async () => body };
}
function speedUpBackoff() {
  // Collapse retry sleeps so tests are instant; keep AbortController timers working.
  globalThis.setTimeout = (fn, ms, ...rest) => realSetTimeout(fn, ms >= 1000 && ms <= 15000 ? 0 : ms, ...rest);
}
test.afterEach(() => { globalThis.fetch = realFetch; globalThis.setTimeout = realSetTimeout; });

test('connection abort is retried and then succeeds', async () => {
  speedUpBackoff();
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    if (calls < 3) throw new TypeError('fetch failed: java.net.SocketException: Software caused connection abort');
    return jsonResponse(200, { status: 'COMPLETE_SCAN', universeDiscovered: 849 });
  };
  const result = await api.scanGlobalMarket('GB', 'LSE', 10);
  assert.equal(calls, 3);
  assert.equal(result.status, 'COMPLETE_SCAN');
});

test('persistent network abort surfaces a structured NETWORK_ERROR, never an empty result', async () => {
  speedUpBackoff();
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; throw new TypeError('Software caused connection abort'); };
  await assert.rejects(() => api.scanGlobalMarket('GB', 'LSE', 10), (err) => {
    assert.equal(err.name, 'GlobalApiError');
    assert.equal(err.code, 'NETWORK_ERROR');
    assert.equal(err.retryable, true);
    assert.match(err.message, /connection abort/i);
    return true;
  });
  assert.equal(calls, 3); // 1 try + 2 retries
});

test('structured 503 SCAN_BUSY is retried honouring retryAfterSec', async () => {
  speedUpBackoff();
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    if (calls === 1) return jsonResponse(503, { detail: { code: 'SCAN_BUSY', message: 'busy', retryable: true, retryAfterSec: 10 } });
    return jsonResponse(200, { status: 'COMPLETE_SCAN' });
  };
  const result = await api.scanGlobalMarket('US', 'NASDAQ', 10);
  assert.equal(calls, 2);
  assert.equal(result.status, 'COMPLETE_SCAN');
});

test('non-retryable server errors are not retried and keep their code', async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; return jsonResponse(500, { detail: { code: 'SCAN_INTERNAL_ERROR', message: 'boom', retryable: false } }); };
  await assert.rejects(() => api.scanGlobalMarket('GB', 'LSE', 10), (err) => err.code === 'SCAN_INTERNAL_ERROR' && err.retryable === false);
  assert.equal(calls, 1);
});

test('400 validation errors are not retried', async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; return jsonResponse(400, { detail: 'unknown exchange' }); };
  await assert.rejects(() => api.scanGlobalMarket('GB', 'XXX', 10), (err) => err.code === 'HTTP_400' && !err.retryable);
  assert.equal(calls, 1);
});

test('parseGlobalApiError tolerates non-JSON proxy bodies', () => {
  const err = api.parseGlobalApiError(504, '<html>Gateway Time-out</html>');
  assert.equal(err.code, 'HTTP_504');
  assert.equal(err.retryable, true);
});
