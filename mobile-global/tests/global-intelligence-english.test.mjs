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

test('Global More description and web navigation never offer Persian-language UI', () => {
  const more = readFileSync(new URL('../src/app/more.tsx', import.meta.url), 'utf8');
  const webNav = readFileSync(new URL('../src/components/app-tabs.web.tsx', import.meta.url), 'utf8');
  assert.match(more, /English-language analyst for the selected stock/);
  assert.equal(more.includes('FA/EN'), false);
  assert.equal([...webNav].some(ch => ch.charCodeAt(0) >= 0x0600 && ch.charCodeAt(0) <= 0x06FF), false);
  for (const label of ['Home', 'Market', 'Orders', 'Portfolio', 'Kiasha', 'More']) {
    assert.ok(webNav.includes('>' + label + '</TabButton>'), 'Missing English tab ' + label);
  }
});
