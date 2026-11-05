// Independent validation of the audit formulas: expected values were computed separately (textbook formulas, Python math.erf)
// from the stored CODAL statement of tracing no. 1505427 (consolidated, FY ending 1404/09/30).
import test from 'node:test';
import assert from 'node:assert/strict';
import { runIranAudit, normCdf, periodEndOf, jalaliYearMonth } from '../src/lib/audit-analysis.ts';

const F = { audit_opinion: 'disclaimer', current_assets_current: 1195359, current_assets_prev: 930136, current_liabilities_current: 439009, current_liabilities_prev: 368265,
  depreciation_current: -1896, depreciation_prev: -823, fixed_assets_current: 110968, fixed_assets_prev: 64147, gross_profit_current: 718656, gross_profit_prev: 606174,
  net_profit_current: 306836, net_profit_prev: 465842, operating_cash_flow_current: -97658, operating_cash_flow_prev: 322969, operating_profit_current: 414169,
  receivables_current: 1020606, receivables_prev: 909693, retained_earnings_current: 691965, revenue_current: 663672, revenue_prev: 603015,
  sga_expense_current: -66783, sga_expense_prev: -37898, total_assets_current: 2233170, total_assets_prev: 1905054, total_equity_current: 1791965,
  total_equity_prev: 1532129, total_liabilities_current: 441205, total_liabilities_prev: 372925, tracing_no: '1505427', source: 'codal_financial_statement_html_v2',
  report_scope: 'consolidated', report_title: 'صورت‌های مالی تلفیقی سال مالی منتهی به ۱۴۰۴/۰۹/۳۰ (حسابرسی شده)' };
const NOW = new Date('2026-11-05T12:00:00Z');
const by = (r, id) => r.checks.find((c) => c.id === id);
const val = (c, label) => c.inputs.find((i) => i.label === label)?.value;

test('Φ matches reference values', () => {
  assert.ok(Math.abs(normCdf(0) - 0.5) < 1e-7);
  assert.ok(Math.abs(normCdf(1.96) - 0.9750021) < 1e-6);
  assert.ok(Math.abs(normCdf(-3.823197686344193) - 6.6e-5) < 2e-6);
});
test('Altman Z″ equals the independently computed 8.74 and is in the safe zone', () => {
  const c = by(runIranAudit(F, NOW), 'altman');
  assert.match(c.summary, /Z″ = 8\.74/);
  assert.equal(c.status, 'OK');
});
test('Zmijewski uses the probit CDF (0.01%), not the logistic (2.14%)', () => {
  const c = by(runIranAudit(F, NOW), 'zmijewski');
  assert.equal(val(c, 'احتمال'), 0.01);
  assert.equal(c.status, 'OK');
});
test('accruals ratio equals (NI − CFO) / TA = 18.11% and Beneish M = −1.75', () => {
  const r = runIranAudit(F, NOW);
  assert.equal(val(by(r, 'accruals'), 'نسبت'), 18.11);
  assert.equal(by(r, 'accruals').status, 'WATCH');
  assert.match(by(r, 'beneish').summary, /M = -1\.75/);
  assert.equal(by(r, 'beneish').status, 'FLAG'); // -1.75 > -1.78 cut-off
  assert.equal(by(r, 'identity').status, 'OK');
});
test('a statement whose balance sheet does not reconcile never produces Altman / Zmijewski / Beneish / leverage and no risk score', () => {
  const r = runIranAudit({ ...F, total_assets_current: 843393 }, NOW);
  assert.equal(by(r, 'identity').status, 'FLAG');
  for (const id of ['leverage', 'equity', 'accruals', 'zmijewski', 'altman', 'beneish']) {
    assert.equal(by(r, id).status, 'INSUFFICIENT_DATA', id);
    assert.match(by(r, id).summary, /شماره رهگیری کدال 1505427/);
  }
  assert.equal(r.riskScore, null);
  assert.equal(r.withheld, true);
  assert.equal(by(r, 'margin').status !== 'INSUFFICIENT_DATA', true); // income-statement checks are not hidden
});
test('a backend UNVERIFIED stamp withholds balance-sheet checks even if the numbers happen to balance', () => {
  const r = runIranAudit({ ...F, verification: { status: 'unverified', reason: 'صورت مالی اصلی در صندوق ورودی نیست' } }, NOW);
  assert.equal(by(r, 'altman').status, 'INSUFFICIENT_DATA');
  assert.match(by(r, 'altman').summary, /صندوق ورودی/);
  assert.equal(r.riskScore, null);
});
test('an old statement is flagged as not current and gets no risk score', () => {
  const r = runIranAudit({ ...F, report_title: 'صورت‌های مالی سال مالی منتهی به ۱۳۹۶/۰۸/۳۰' }, NOW);
  assert.equal(r.stale, true);
  assert.equal(by(r, 'freshness').status, 'WATCH');
  assert.equal(r.riskScore, null);
  assert.equal(runIranAudit(F, NOW).stale, false);
});
test('Jalali period parsing and current Jalali month', () => {
  assert.deepEqual(periodEndOf('منتهی به ۱۴۰۴/۱۲/۲۹'), { y: 1404, m: 12, text: '1404/12/29' });
  assert.equal(periodEndOf('بدون تاریخ'), null);
  assert.deepEqual(jalaliYearMonth(NOW), { y: 1405, m: 8 });
});
