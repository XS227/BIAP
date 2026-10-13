// Run: node --experimental-strip-types --no-warnings --test tests/scan-summary.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';

const { evidenceCounts, topRanked, rankCriterionLabel } = await import('../src/lib/scan-summary.ts');

const sample150 = Array.from({ length: 150 }, (_, i) => ({ ticker: `T${i}`, evidence: { status: 'PASS' } }));

test('evidence counts come from ledger totals, not the 150-row payload sample', () => {
  const c = evidenceCounts({ deepResults: sample150, evidenceSummary: { denominator: 3001, pass: 2806, warn: 0, block: 195 } });
  assert.deepEqual([c.pass, c.warn, c.block, c.denominator, c.basis], [2806, 0, 195, 3001, 'ledger']);
  assert.equal(c.pass + c.warn + c.block, c.denominator);
});

test('legacy servers without evidenceSummary fall back to the sample and say so', () => {
  const c = evidenceCounts({ deepResults: sample150 });
  assert.equal(c.basis, 'payload_sample');
  assert.equal(c.denominator, 150);
});

test('analysisLedger.evidenceSummary is accepted', () => {
  const c = evidenceCounts({ analysisLedger: { evidenceSummary: { denominator: 815, pass: 458, warn: 0, block: 357 } } });
  assert.equal(c.basis, 'ledger');
  assert.equal(c.block, 357);
});

test('highest-ranked follows server rank (score x confidence), not raw score', () => {
  const recs = [
    { ticker: 'GOOGL', score: 0.4176, confidence: 0.6961, rank: 1 },
    { ticker: 'MSFT', score: 0.3954, confidence: 0.6961, rank: 2 },
    { ticker: 'ASML', score: 0.4307, confidence: 0.6306, rank: 3 },
  ];
  assert.equal(topRanked({ recommendations: recs }).ticker, 'GOOGL');
  assert.equal(topRanked({ recommendations: [...recs].reverse() }).ticker, 'GOOGL');
});

test('legacy payload without rank keeps server order', () => {
  assert.equal(topRanked({ recommendations: [{ ticker: 'A' }, { ticker: 'B' }] }).ticker, 'A');
});

test('criterion label', () => {
  assert.equal(rankCriterionLabel({ rankingBasis: { criterion: 'score_x_confidence' } }), 'score × confidence');
});
