import test from 'node:test';
import assert from 'node:assert/strict';
import { isFinancialSector, runAudit, accrualsCheck, cfoDivergenceCheck, beneishCheck, auditorOpinionCheck } from '../src/lib/audit-analysis.ts';

const base = { values: { net_income: 100, operating_cash_flow: 120, total_assets: 1000 }, reportPeriod: '2025-12-31', source: 'test' };

test('accruals: low ratio OK, high FLAG, uses inputs/period/source', () => {
  const ok = accrualsCheck(base);
  assert.equal(ok.status, 'OK'); assert.equal(ok.period, '2025-12-31'); assert.equal(ok.inputs.length, 3);
  assert.equal(accrualsCheck({ ...base, values: { net_income: 300, operating_cash_flow: 100, total_assets: 1000 } }).status, 'FLAG');
  assert.equal(accrualsCheck({ ...base, values: { net_income: 160, operating_cash_flow: 100, total_assets: 1000 } }).status, 'WATCH');
});
test('missing data is INSUFFICIENT_DATA, never zero-filled', () => {
  const c = accrualsCheck({ values: { net_income: 100 } });
  assert.equal(c.status, 'INSUFFICIENT_DATA'); assert.deepEqual(c.missing.sort(), ['operating_cash_flow', 'total_assets']);
  assert.equal(accrualsCheck({ values: { net_income: 1, operating_cash_flow: 1, total_assets: 0 } }).status, 'INSUFFICIENT_DATA');
});
test('profit vs cash flow divergence', () => {
  assert.equal(cfoDivergenceCheck({ values: { net_income: 100, operating_cash_flow: -5 } }).status, 'FLAG');
  assert.equal(cfoDivergenceCheck({ values: { net_income: 100, operating_cash_flow: 30 } }).status, 'WATCH');
  assert.equal(cfoDivergenceCheck({ values: { net_income: -10, operating_cash_flow: 30 } }).status, 'OK');
});
test('Beneish needs two-year inputs: not stored today -> INSUFFICIENT_DATA listing them', () => {
  const c = beneishCheck(base);
  assert.equal(c.status, 'INSUFFICIENT_DATA'); assert.ok(c.missing.includes('receivables_prev'));
});
test('Beneish computes with full inputs (unchanged year stays below flag)', () => {
  const y = { receivables: 100, revenue: 1000, gross_profit: 400, ppe: 300, depreciation: 30, sga: 100, total_assets: 1000, total_debt: 200 };
  const b = { ...y, ...Object.fromEntries(Object.entries(y).map(([k, v]) => [k + '_prev', v])), net_income: 100, operating_cash_flow: 110 };
  const c = beneishCheck({ values: {}, beneish: b });
  assert.notEqual(c.status, 'INSUFFICIENT_DATA'); assert.match(c.summary, /M-Score -?\d/);
});
test('auditor opinion: absent -> INSUFFICIENT_DATA, adverse -> FLAG, unqualified -> OK', () => {
  assert.equal(auditorOpinionCheck({ values: {} }).status, 'INSUFFICIENT_DATA');
  assert.equal(auditorOpinionCheck({ values: {}, auditOpinion: 'Adverse opinion' }).status, 'FLAG');
  assert.equal(auditorOpinionCheck({ values: {}, auditOpinion: 'Unqualified' }).status, 'OK');
});
test('overall: <2 evaluable checks -> INSUFFICIENT_DATA with no score; otherwise a 0-100 risk score, no rating wording', () => {
  const none = runAudit({ values: {} });
  assert.equal(none.status, 'INSUFFICIENT_DATA'); assert.equal(none.riskScore, null);
  const r = runAudit({ ...base, distress: { altman_z_double_prime: 3.2, distress_probability: 0.01 } });
  assert.equal(r.status, 'OK'); assert.ok(r.riskScore >= 0 && r.riskScore <= 100);
  assert.doesNotMatch(JSON.stringify(r), /credit rating(?! or)/i);
});

test('financial-sector issuers: accruals/Altman/Beneish are not evaluated', () => {
  const r = runAudit({ ...base, financialSector: true, distress: { altman_z_double_prime: 0.5, distress_probability: 0.01 } });
  for (const id of ['accruals', 'altman', 'beneish']) assert.equal(r.checks.find((c) => c.id === id).status, 'INSUFFICIENT_DATA');
  assert.equal(r.checks.find((c) => c.id === 'cfo_divergence').status, 'OK');
});

test('isFinancialSector: flag wins, else sector text', () => {
  assert.equal(isFinancialSector(null, 'Financials', 'Banks'), true);
  assert.equal(isFinancialSector(false, 'Financials', 'Banks'), false);
  assert.equal(isFinancialSector(undefined, 'Technology', 'Software'), false);
});

import { beneishInputs, zmijewskiBand, isCapitalIntensive, runAudit as _runAudit } from '../src/lib/audit-analysis.ts';
test('Beneish lists only truly missing fields (total_assets, net_income, operating_cash_flow are present)', () => {
  const inp = { values: { total_assets: 100, net_income: 5, operating_cash_flow: 7 } };
  const b = beneishInputs(inp);
  assert.equal(b.total_assets, 100); assert.equal(b.net_income, 5); assert.equal(b.operating_cash_flow, 7);
  const c = _runAudit({ ...inp, auditOpinion: null, distress: null }).checks.find((x) => x.id === 'beneish');
  assert.equal(c.status, 'INSUFFICIENT_DATA');
  for (const k of ['total_assets', 'net_income', 'operating_cash_flow']) assert.ok(!c.missing.includes(k), k);
  assert.ok(c.missing.includes('receivables_prev'));
});
test('one Zmijewski band function: 48.8% is the watch band, never "distress unlikely"', () => {
  assert.equal(zmijewskiBand(0.488).status, 'WATCH'); assert.ok(zmijewskiBand(0.488).label.includes('watch band'));
  assert.equal(zmijewskiBand(0.1).status, 'OK'); assert.equal(zmijewskiBand(0.5).status, 'FLAG');
  const r = _runAudit({ values: { net_income: 1, operating_cash_flow: 1, total_assets: 10 }, distress: { distress_probability: 0.488, altman_z_double_prime: 3 } });
  assert.ok(r.checks.find((x) => x.id === 'zmijewski').summary.includes('watch band'));
});
test('Altman Z″ counts at half weight for capital-intensive sectors and the note says so', () => {
  assert.equal(isCapitalIntensive('Energy', ''), true); assert.equal(isCapitalIntensive('Industrials', 'Marine Shipping'), true); assert.equal(isCapitalIntensive('Technology', 'Software'), false);
  const base = { values: { net_income: 10, operating_cash_flow: 10, total_assets: 100 }, distress: { altman_z_double_prime: 0.5, distress_probability: 0.05 } };
  const plain = _runAudit({ ...base, sector: 'Technology' }), oil = _runAudit({ ...base, sector: 'Energy' });
  assert.ok(oil.riskScore < plain.riskScore); assert.ok(oil.note.includes('half weight')); assert.ok(!plain.note.includes('half weight'));
});
