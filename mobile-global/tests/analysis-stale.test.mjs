import test from 'node:test';
import assert from 'node:assert/strict';

const { investmentBadge, ANALYSIS_STALE } = await import('../src/lib/decision-tier.ts');

test('stale analysis is labelled and the call is unchanged', () => {
  const b = investmentBadge({ mode: 'investment', tier: 'ACCUMULATE', analysisStale: true, analysisStaleDays: 3 });
  assert.equal(b.tier, 'ACCUMULATE');
  assert.equal(b.notice, `${ANALYSIS_STALE} (3 d)`);
});

test('fresh analysis has no stale label; weak evidence text is kept next to it', () => {
  assert.equal(investmentBadge({ mode: 'investment', tier: 'HOLD' }).notice, '');
  const both = investmentBadge({ mode: 'investment', tier: 'HOLD', insufficientEvidence: true, analysisStale: true });
  assert.match(both.notice, /·/);
});
