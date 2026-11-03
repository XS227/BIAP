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
  assert.ok(r.riskScore != null && r.riskScore > 0);
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
