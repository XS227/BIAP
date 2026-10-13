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

// --- Market Top 10 vs Qualified BUY (phase 2) ---
import { marketListRows, gateLines } from '../src/lib/scan-summary.ts';
test('market list uses marketTop10 (any call) and never shows rows when ranking is not released', () => {
  const top = [{ ticker: 'A', call: 'HOLD_OR_WATCH' }];
  assert.deepEqual(marketListRows({ rankingEligible: true, marketTop10: top, recommendations: [] }), top);
  assert.deepEqual(marketListRows({ rankingEligible: false, marketTop10: top, recommendations: top }), []);
  assert.deepEqual(marketListRows({ rankingEligible: true, recommendations: top }), top);
});
test('gate lines list only gates that rejected companies, with reasons', () => {
  const lines = gateLines({ rankingGates: [
    { gate: 'evidence_pass', entered: 146, passed: 136, rejected: 10, byEvidenceStatus: { BLOCK: 10 } },
    { gate: 'buy_threshold', entered: 136, passed: 0, rejected: 136, reasons: { 'call=NO_RECOMMENDATION': 135, 'call=HOLD_OR_WATCH': 1 } },
    { gate: 'one_security_per_issuer', entered: 0, passed: 0, rejected: 0 },
  ] });
  assert.equal(lines.length, 2);
  assert.match(lines[0], /Evidence PASS: 10 of 146 rejected \(BLOCK 10\)/);
  assert.match(lines[1], /call=NO_RECOMMENDATION 135/);
});
