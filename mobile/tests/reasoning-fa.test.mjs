import test from 'node:test';
import assert from 'node:assert/strict';
import { reasoningFa } from '../src/lib/reasoning-fa.ts';
test('stored English agent reasoning is rendered in Persian', () => {
  const samples = ['no CODAL fundamentals connected yet; only 16% off 52w high; high annualized volatility 2358.5%',
    'P/E 24.90 vs sector 9.15 (-172% premium)', '1w -4.8%; 1m -4.3%', 'net retail inflow; buy/sell per-capita 55.23x', 'no strong momentum signal'];
  for (const s of samples) assert.doesNotMatch(reasoningFa(s).replace(/P\/E/g, ''), /[A-Za-z]/, s);
  assert.match(reasoningFa('high annualized volatility 2358.5%'), /داده کافی نیست/);
  assert.match(reasoningFa('something never seen'), /جزئیات فنی/);
});
