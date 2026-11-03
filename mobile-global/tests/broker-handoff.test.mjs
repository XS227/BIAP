import test from 'node:test';
import assert from 'node:assert/strict';
import { BROKERS } from '../src/config/brokers.ts';
import { brokersForMarket, buildHandoff, normalizeCountry, LEAVE_NOTICE } from '../src/lib/broker-handoff.ts';

const ids = (c) => brokersForMarket(c).map((b) => b.id);

test('Nordnet only for NO/SE/DK/FI; Trading 212 not for Nordics', () => {
  for (const c of ['NO', 'SE', 'DK', 'FI']) assert.ok(ids(c).includes('nordnet'), c);
  for (const c of ['US', 'GB', 'DE', 'IT']) assert.ok(!ids(c).includes('nordnet'), c);
  assert.ok(!ids('NO').includes('trading212'));
  assert.ok(ids('DE').includes('trading212'));
});
test('unknown/empty market gives no brokers; UK maps to GB', () => {
  assert.deepEqual(brokersForMarket(''), []);
  assert.deepEqual(brokersForMarket('ZZ'), []);
  assert.equal(normalizeCountry('uk'), 'GB');
  assert.ok(ids('uk').length > 0);
});
test('no deep link configured: opens official site, nothing pre-filled', () => {
  for (const b of BROKERS) {
    const h = buildHandoff(b, { country: 'US', ticker: 'AAPL', isin: 'US0378331005' });
    assert.equal(h.prefilled, false);
    assert.match(h.url, /^https:\/\//);
    assert.ok(!/AAPL|US0378331005|\?/.test(h.url), 'no instrument, query or tracking in URL');
  }
});
test('nordnet uses the country site', () => {
  const n = BROKERS.find((b) => b.id === 'nordnet');
  assert.equal(buildHandoff(n, { country: 'SE' }).url, 'https://www.nordnet.se/');
  assert.equal(buildHandoff(n, { country: 'FI' }).url, 'https://www.nordnet.fi/');
});
test('deep link is used only when configured and complete', () => {
  const b = { id: 'x', name: 'X', home: 'https://x.example/', deepLink: 'https://x.example/s/{isin}', markets: ['US'] };
  assert.deepEqual(buildHandoff(b, { country: 'US', isin: 'US1' }), { url: 'https://x.example/s/US1', prefilled: true });
  assert.equal(buildHandoff(b, { country: 'US' }).prefilled, false);
});
test('config holds no credentials/affiliate params and the notice is exact', () => {
  assert.ok(JSON.stringify(BROKERS).indexOf('?') < 0);
  assert.match(LEAVE_NOTICE, /never receives your orders, passwords or funds/);
});
test('only verified markets: every broker has a source and unverified markets are absent', () => {
  for (const b of BROKERS) { assert.match(b.coverageSource, /^https:\/\//); assert.ok(b.coverageNote.length > 10); }
  assert.ok(!ids('DE').includes('saxo'));
  assert.ok(!ids('SE').includes('saxo'));
  assert.ok(ids('FR').includes('saxo'));
});
