// Run: node --experimental-strip-types --no-warnings --test tests/engine-labels.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';

const { engineScoreLines, ENGINE_LABEL, PORTFOLIO_ENGINE_NOTE, KIASHA_PICKS_ENGINE_NOTE } = await import('../src/lib/decision-tier.ts');

test('SAP: each engine line carries its own decision, 3-decimal score and confidence', () => {
  const lines = engineScoreLines({
    displayed: 'investment',
    investment: { tier: 'ACCUMULATE', score: 0.212994, confidence: 0.67237, rank: 39 },
    conservative: { call: 'NO_RECOMMENDATION', score: 0.191, confidence: 0.606933 },
  });
  assert.deepEqual(lines, [
    'Investment ranking: ACCUMULATE · score 0.213 · confidence 67% · rank 39',
    'Conservative check: No Recommendation · score 0.191 · confidence 61% (fresh analysis)',
  ]);
});

test('without a ranking only the conservative line is shown', () => {
  const lines = engineScoreLines({ displayed: 'conservative', investment: null, conservative: { call: 'HOLD_OR_WATCH', score: -0.000401, confidence: 0.567667 } });
  assert.equal(lines.length, 1);
  assert.match(lines[0], /^Conservative check: Hold Or Watch · score -0\.000 · confidence 57%/);
});

test('missing numbers render as a dash and old servers without engines give no lines', () => {
  assert.deepEqual(engineScoreLines(undefined), []);
  assert.deepEqual(engineScoreLines(null), []);
  assert.match(engineScoreLines({ conservative: { call: null, score: null, confidence: null } })[0], /: — · score — · confidence —/);
});

test('portfolio and Kiasha-picks notes name the conservative engine', () => {
  assert.ok(PORTFOLIO_ENGINE_NOTE.includes(ENGINE_LABEL.conservative));
  assert.ok(PORTFOLIO_ENGINE_NOTE.includes('not built from the investment ranking'));
  assert.ok(KIASHA_PICKS_ENGINE_NOTE.startsWith(ENGINE_LABEL.conservative));
});
