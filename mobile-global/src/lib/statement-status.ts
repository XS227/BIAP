/** One honest line above the fundamentals table: which statement period, who filed it, when we stored it. */
export type StatementEvidence = {
  reportPeriod?: string | null; filingDate?: string | null; retrievedAt?: string | null;
  sourceProvider?: string | null; isOfficial?: boolean | null; fundamentalPeriodAgeDays?: number | null;
  values?: Record<string, unknown> | null;
} | null | undefined;

const KEY = ['revenue', 'net_income', 'total_assets', 'total_equity', 'operating_cash_flow'];
const day = (v?: string | null) => (v ? String(v).slice(0, 10) : null);

export function statementStatus(fe: StatementEvidence, reportingCurrency?: string | null): { status: 'OK' | 'INSUFFICIENT_DATA'; line: string } {
  const have = KEY.filter((k) => typeof fe?.values?.[k] === 'number').length;
  if (!fe || have === 0) return { status: 'INSUFFICIENT_DATA', line: 'INSUFFICIENT_DATA — no stored financial statement for this company. Nothing below is estimated.' };
  const parts = [
    `Statement period ${day(fe.reportPeriod) || 'unknown'}`,
    fe.filingDate ? `filed ${day(fe.filingDate)}` : null,
    fe.retrievedAt ? `stored ${day(fe.retrievedAt)}` : null,
    fe.fundamentalPeriodAgeDays != null ? `${fe.fundamentalPeriodAgeDays} days old` : null,
    reportingCurrency ? `reported in ${reportingCurrency}` : null,
    fe.sourceProvider ? `source ${fe.sourceProvider}${fe.isOfficial ? ' (official)' : ''}` : 'source unknown',
    have < KEY.length ? `partial: ${have}/${KEY.length} key lines present` : null,
  ].filter(Boolean);
  return { status: 'OK', line: parts.join(' • ') };
}
