import test from 'node:test';
import assert from 'node:assert/strict';
import { parseIranFinancialInboxAudit } from '../src/lib/iran-financial-inbox.ts';

const valid = () => ({
  source: 'verified_liara_codal_inbox_only', verifiedExports: 9, newestExport: '2026-11-02',
  rejectedExports: 0,
  company: { symbol: 'پكرمان', issuer: 'گروه صنعتی بارز', financial_filings: 1,
    financial_ai_eligible: false, audit_status: 'BLOCKED_PENDING_ISSUER_AND_STATEMENT_VALIDATION',
    market_price_reconciliation: 'NOT_POSSIBLE_FROM_CODAL_INBOX_ALONE',
    filing_evidence: [{ tracing_no: '42', financial_ai_eligible: false,
      quality_gate: 'BLOCKED_ISSUER_SCOPE_AND_ACCOUNTING_NOT_RECONCILED' }] },
});
test('accepts verified Liara metadata and Persian/Arabic symbol variants', () => {
  assert.equal(parseIranFinancialInboxAudit(valid(), 'پکرمان').company.financial_ai_eligible, false);
});
test('rejects other data sources and mismatched symbols', () => {
  assert.throws(() => parseIranFinancialInboxAudit({ ...valid(), source: 'codal_live' }, 'پکرمان'));
  assert.throws(() => parseIranFinancialInboxAudit(valid(), 'خودرو'));
});
test('rejects financial approval or unblocked filings without reconciliation', () => {
  const x = valid(); x.company.financial_ai_eligible = true;
  assert.throws(() => parseIranFinancialInboxAudit(x, 'پکرمان'));
  const y = valid(); y.company.filing_evidence[0].quality_gate = 'PASS';
  assert.throws(() => parseIranFinancialInboxAudit(y, 'پکرمان'));
});
test('rejects missing exports or unproven price reconciliation', () => {
  assert.throws(() => parseIranFinancialInboxAudit({ ...valid(), verifiedExports: 0 }, 'پکرمان'));
  const x = valid(); x.company.market_price_reconciliation = 'MATCHED';
  assert.throws(() => parseIranFinancialInboxAudit(x, 'پکرمان'));
});
