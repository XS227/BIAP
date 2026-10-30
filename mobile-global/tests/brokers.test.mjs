import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const ts = require('typescript');
const source = readFileSync(new URL('../src/lib/brokers.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { BROKERS, BROKER_EXIT_NOTICE, brokersForMarket } = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));
test('market filtering excludes Nordnet outside Nordic markets', () => {
  assert.ok(brokersForMarket('NO').some(b => b.id === 'nordnet'));
  assert.ok(!brokersForMarket('US').some(b => b.id === 'nordnet'));
  assert.deepEqual(brokersForMarket('IR'), []);
});
test('official external URLs and warning, no affiliate URLs', () => {
  assert.equal(BROKERS.length, 5);
  for (const broker of BROKERS) {
    assert.ok(broker.url.startsWith('https://'));
    assert.ok(!broker.affiliateUrl);
    assert.ok(!broker.url.includes('?'));
  }
  assert.match(BROKER_EXIT_NOTICE, /never receives your orders, passwords or funds/);
});
