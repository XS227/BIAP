/** Read-only verified Liara inbox evidence; not validated financials or prices. */
export type IranFilingEvidence = {
  tracing_no: string;
  issuer_evidence: string;
  html_available: boolean;
  scope_claim: string;
  assurance_claim: string;
  period_end_jalali: string | null;
  financial_ai_eligible: false;
  quality_gate: string;
};
export type IranFinancialInboxAudit = {
  source: 'verified_liara_codal_inbox_only';
  verifiedExports: number;
  newestExport: string | null;
  rejectedExports: number;
  company: {
    symbol: string;
    issuer: string;
    inbox_status: string;
    financial_filings: number;
    explicit_issuer_review: number;
    html_available: number;
    html_missing: number;
    financial_ai_eligible: false;
    audit_status: string;
    market_price_reconciliation: 'NOT_POSSIBLE_FROM_CODAL_INBOX_ALONE';
    filing_evidence: IranFilingEvidence[];
  };
};
function normalizeSymbol(symbol: string): string {
  return symbol.replace(/ي/g, 'ی').replace(/ك/g, 'ک').replace(/[\s\u200c\u200d\u200e\u200f]/g, '');
}
/** Fail closed on other sources, missing evidence, or unverified approval. */
export function parseIranFinancialInboxAudit(payload: unknown, expectedSymbol: string): IranFinancialInboxAudit {
  if (!payload || typeof payload !== 'object') throw new Error('Invalid Liara audit response');
  const data = payload as Partial<IranFinancialInboxAudit>;
  const c = data.company;
  if (data.source !== 'verified_liara_codal_inbox_only' ||
      !Number.isInteger(data.verifiedExports) || (data.verifiedExports ?? 0) < 1 ||
      !c || normalizeSymbol(String(c.symbol || '')) !== normalizeSymbol(expectedSymbol) ||
      !Array.isArray(c.filing_evidence) ||
      c.financial_ai_eligible !== false ||
      c.market_price_reconciliation !== 'NOT_POSSIBLE_FROM_CODAL_INBOX_ALONE' ||
      !String(c.audit_status || '').startsWith('BLOCKED') ||
      c.filing_evidence.some(f => f.financial_ai_eligible !== false || !String(f.quality_gate).startsWith('BLOCKED'))) {
    throw new Error('Unverified or mismatched Liara audit evidence');
  }
  return data as IranFinancialInboxAudit;
}
