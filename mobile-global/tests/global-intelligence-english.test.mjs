import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('BIAP Global new Intelligence UI contains no Persian/Arabic text', () => {
  const ui = readFileSync(new URL('../src/app/intelligence.tsx', import.meta.url), 'utf8');
  const stock = readFileSync(new URL('../src/app/stock/[code].tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(ui, /[\u0600-\u06FF]/u,
    'Global Intelligence must be English-only; Persian belongs to the separate Iran app');
  const cta = stock.match(/🔎 Open Company Intelligence[^<]*/u)?.[0] || '';
  assert.equal(cta, '🔎 Open Company Intelligence');
  assert.doesNotMatch(cta, /[\u0600-\u06FF]/u);
});
