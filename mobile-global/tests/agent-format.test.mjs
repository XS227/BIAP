// Run: node --experimental-strip-types --no-warnings --test tests/agent-format.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';

const f = await import('../src/lib/agent-format.ts');
const i = await import('../src/lib/agent-i18n.ts');

test('sections are hidden unless the server flag is true', () => {
  assert.deepEqual(f.agentFlags(null), { risk: false, performance: false, accuracy: false });
  assert.deepEqual(f.agentFlags({ riskAgentEnabled: true, performanceAgentEnabled: 'yes', decisionAccuracyEnabled: false }), { risk: true, performance: false, accuracy: false });
});

test('a null level is a grey "not enough data" chip, never LOW or blank', () => {
  const c = f.riskChip('en', { level: null, status: 'INSUFFICIENT_DATA' });
  assert.equal(c.tone, 'muted'); assert.equal(c.text, 'Not enough data');
  assert.equal(f.riskChip('en', { level: null, status: 'NOT_APPLICABLE' }).text, 'Not applicable: financial institution');
  assert.equal(f.riskChip('fa', { level: null, status: 'OK' }).text, 'داده کافی نیست');
  assert.equal(f.performanceChip('en', null).tone, 'muted');
});

test('risk and performance chip tones', () => {
  assert.equal(f.riskChip('en', { level: 'CRITICAL' }).tone, 'severe');
  assert.equal(f.riskChip('en', { level: 'LOW' }).tone, 'positive');
  assert.equal(f.performanceChip('en', 'DETERIORATING').arrowDown, true);
  assert.equal(f.performanceChip('en', 'WEAK').tone, 'warning');
  assert.equal(f.performanceChip('fa', 'STRONG').text, 'قوی');
});

test('every level has a Persian label and none is empty', () => {
  for (const l of ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']) assert.ok(i.levelLabel('fa', 'risk', l) && i.levelLabel('fa', 'risk', l) !== l);
  for (const l of ['STRONG', 'STABLE', 'WEAK', 'DETERIORATING']) assert.ok(i.levelLabel('fa', 'performance', l) && i.levelLabel('fa', 'performance', l) !== l);
  for (const k of Object.keys(i.STR)) { assert.ok(i.STR[k].en !== undefined && i.STR[k].fa, `fa missing for ${k}`); }
});

test('percentile and number formatting', () => {
  assert.equal(f.percentileText('en', 0.814), '81st percentile');
  assert.equal(f.percentileText('en', 0.12), '12th percentile');
  assert.equal(f.percentileText('en', 0.22), '22nd percentile');
  assert.equal(f.percentileText('fa', 0.81), 'صدک ۸۱');
  assert.equal(f.percentileText('en', null), '—');
  assert.equal(f.signedPct('en', -0.3544), '-0.35%');
  assert.equal(f.signedPct('en', 10.57), '+10.57%');
  assert.equal(f.pp('en', 10.5747), '10.57 pp');
  assert.equal(f.frac('en', 0.1041), '10.4%');
  assert.equal(f.num('fa', 12.5, 1), '۱۲.۵');
  assert.equal(f.num('en', -0.0001, 2), '0');
});

test('pending card text carries the due date', () => {
  assert.match(f.pendingLine('en', '2027-01-20'), /2027-01-20/);
  assert.match(f.pendingLine('fa', '2027-01-20'), /۲۰۲۷-۰۱-۲۰/);
});

test('scope line labels the sector source and fallback', () => {
  const line = f.scopeLine('en', { scope: 'sector+market', sector: 'Technology', sectorSource: 'supplement (current sector)', peerCount: 59 });
  assert.match(line, /current sector, not point-in-time/); assert.match(line, /59 peers/);
  assert.match(f.scopeLine('en', { scope: 'market-wide', sector: null, peerCount: 800 }), /market-wide fallback/);
  assert.doesNotMatch(f.scopeLine('en', { scope: 'sector', sector: 'Energy', sectorSource: 'official classification', peerCount: 40 }), /point-in-time/);
});

test('provisional Ohlson is detected only when the signal says so', () => {
  assert.equal(f.ohlsonProvisional([{ id: 'ohlson', provisional: true }]), true);
  assert.equal(f.ohlsonProvisional([{ id: 'ohlson', provisional: false }, { id: 'altman' }]), false);
  assert.equal(f.ohlsonProvisional(null), false);
});

test('markets sort by spread, missing spread last', () => {
  const out = f.sortMarkets({ A: { spreadMeanPp: 3 }, B: { spreadMeanPp: null }, C: { spreadMeanPp: 11 } }).map(([k]) => k);
  assert.deepEqual(out, ['C', 'A', 'B']);
});

test('market-wide fallback is recognised from the API label', () => {
  const api = 'market-wide fallback (too few sector peers; all-sector peers in this market)';
  assert.equal(f.isMarketWide(api), true); assert.equal(f.isMarketWide('sector+market'), false);
  assert.match(f.scopeLine('en', { scope: api, sector: null, peerCount: 800 }), /market-wide fallback/);
});

test('performance chip: financial institutions are "not applicable", other gaps "not enough data"', () => {
  assert.equal(f.performanceChip('en', null, 'NOT_APPLICABLE').text, 'Not applicable: financial institution');
  assert.equal(f.performanceChip('en', null, 'INSUFFICIENT_DATA').text, 'Not enough data');
});

test('risk status reads FULL or PARTIAL, missing statements and calibration are stated', () => {
  assert.equal(i.statusLabel('en', 'OK'), 'FULL');
  assert.equal(i.statusLabel('en', 'PARTIAL'), 'PARTIAL');
  assert.equal(f.riskChip('en', { level: null, status: 'INSUFFICIENT_DATA', dataNotYetAvailable: true }).text, 'Data not yet available');
  assert.equal(f.riskChip('en', { level: null, status: 'NOT_APPLICABLE', dataNotYetAvailable: true }).tone, 'muted');
  assert.equal(f.calibrationLabel('en', 'preliminary'), 'Preliminary calibration (US)');
  assert.equal(f.calibrationLabel('en', 'not_calibrated'), 'Not calibrated for this market');
  assert.equal(f.calibrationLabel('fa', 'unavailable'), '');
});

