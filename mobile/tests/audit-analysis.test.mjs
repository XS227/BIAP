import test from 'node:test';
import assert from 'node:assert/strict';
import { runIranAudit } from '../src/lib/audit-analysis.ts';

const PEK = { revenue_current: 269826442, revenue_prev: 194546655, net_profit_current: 2676167, net_profit_prev: 31089222,
  total_assets_current: 161431776, total_liabilities_current: 129035244, total_equity_current: 38832929, total_equity_prev: 53559887,
  audit_opinion: null, report_title: 'سال ۱۴۰۴', source: 'codal', tracing_no: '1550679' };
const by = (r, id) => r.checks.find((c) => c.id === id);

test('no statements: everything INSUFFICIENT_DATA, no score', () => {
  const r = runIranAudit(null);
  assert.equal(r.riskScore, null);
  assert.ok(r.checks.every((c) => c.status === 'INSUFFICIENT_DATA'));
});
test('Pekarman stored values: margin collapse flagged, inconsistent balance sheet flagged, no CFO invented', () => {
  const r = runIranAudit(PEK);
  assert.equal(by(r, 'margin').status, 'FLAG');
  assert.equal(by(r, 'identity').status, 'FLAG');
  for (const id of ['accruals', 'cfo', 'beneish', 'altman', 'zmijewski', 'opinion']) assert.equal(by(r, id).status, 'INSUFFICIENT_DATA', id);
  assert.equal(r.riskScore, null) // coverage below 6 checks: no score;
  assert.ok(!by(r, 'identity').scored);
});
test('consistent balance sheet passes identity', () => {
  const r = runIranAudit({ ...PEK, total_assets_current: 167868173 });
  assert.equal(by(r, 'identity').status, 'OK');
});
test('single scored check is not enough for a score', () => {
  const r = runIranAudit({ revenue_current: 10, revenue_prev: 9, net_profit_current: 1, net_profit_prev: 1 });
  assert.equal(r.riskScore, null);
});

import { MIN_AUDIT_COVERAGE } from '../src/lib/audit-analysis.ts';
test('no risk score when fewer than 6 checks could be evaluated', () => {
  const r = runIranAudit({ revenue_current: 100, revenue_prev: 90, net_profit_current: 10, net_profit_prev: 9, total_assets_current: 500, total_liabilities_current: 400, total_equity_current: 100, total_equity_prev: 90 });
  assert.ok(r.evaluated < MIN_AUDIT_COVERAGE);
  assert.equal(r.riskScore, null);
  assert.equal(r.total, r.checks.length);
});

import { auditOpinionFa } from '../src/lib/audit-analysis.ts';
test('audit opinion shown in Persian', () => {
  assert.equal(auditOpinionFa('qualified'), 'مشروط');
  assert.equal(auditOpinionFa('unqualified'), 'مقبول');
  const r = runIranAudit({ audit_opinion: 'qualified' });
  assert.equal(r.checks.find((c) => c.id === 'opinion').status, 'FLAG');
});

test('cash-flow inputs enable accruals, CFO divergence and Zmijewski; score appears at >=6 checks', () => {
  const r = runIranAudit({ revenue_current: 1200, revenue_prev: 1000, net_profit_current: 240, net_profit_prev: 150, total_assets_current: 1000, total_liabilities_current: 400, total_equity_current: 600, total_equity_prev: 550,
    operating_cash_flow_current: 180, current_assets_current: 600, current_liabilities_current: 300 });
  const st = (id) => r.checks.find((c) => c.id === id).status;
  assert.notEqual(st('accruals'), 'INSUFFICIENT_DATA'); assert.notEqual(st('cfo'), 'INSUFFICIENT_DATA'); assert.notEqual(st('zmijewski'), 'INSUFFICIENT_DATA');
  assert.equal(st('beneish'), 'INSUFFICIENT_DATA');
  assert.ok(r.evaluated >= 6 && r.riskScore != null);
});

test('Altman needs EBIT; Beneish needs depreciation and SG&A for both years', () => {
  const base = { revenue_current: 1200, revenue_prev: 1000, net_profit_current: 240, net_profit_prev: 150, total_assets_current: 1000, total_assets_prev: 900, total_liabilities_current: 400, total_liabilities_prev: 350, total_equity_current: 600, total_equity_prev: 550,
    operating_cash_flow_current: 180, current_assets_current: 600, current_assets_prev: 500, current_liabilities_current: 300, retained_earnings_current: 200, operating_profit_current: 300 };
  const st = (r, id) => r.checks.find((c) => c.id === id).status;
  const r1 = runIranAudit(base);
  assert.notEqual(st(r1, 'altman'), 'INSUFFICIENT_DATA');
  assert.equal(st(r1, 'beneish'), 'INSUFFICIENT_DATA');
  const r2 = runIranAudit({ ...base, receivables_current: 200, receivables_prev: 150, gross_profit_current: 500, gross_profit_prev: 400, fixed_assets_current: 300, fixed_assets_prev: 280, depreciation_current: 30, depreciation_prev: 28, sga_expense_current: -100, sga_expense_prev: -90 });
  assert.notEqual(st(r2, 'beneish'), 'INSUFFICIENT_DATA');
  assert.equal(runIranAudit({ ...base, operating_profit_current: null }).checks.find((c) => c.id === 'altman').status, 'INSUFFICIENT_DATA');
});
