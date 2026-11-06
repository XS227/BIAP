import test from 'node:test';
import assert from 'node:assert/strict';

const { reportingSuffix, reportingCurrencyNote } = await import('../src/lib/reporting-currency.ts');

test('USD reporter listed in NOK is labelled', () => {
  const co = { reporting_currency: 'usd', currency: 'NOK' };
  assert.equal(reportingSuffix(co), ' (USD)');
  assert.match(reportingCurrencyNote(co, 'NOK'), /in USD; the price is in NOK/);
});

test('same currency or unknown currency: suffix kept, no cross-currency note', () => {
  assert.equal(reportingCurrencyNote({ reporting_currency: 'EUR', currency: 'EUR' }, 'EUR'), '');
  assert.equal(reportingSuffix({ reporting_currency: 'EUR' }), ' (EUR)');
  assert.equal(reportingSuffix({}), '');
  assert.equal(reportingSuffix(null), '');
  assert.equal(reportingCurrencyNote({ reporting_currency: 'US$' }, 'NOK'), '');
});
