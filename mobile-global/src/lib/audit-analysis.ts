/**
 * Deterministic audit checks on STORED BIAP data only (no model, no network, no invented figures).
 * Every check returns its inputs, period and source, or INSUFFICIENT_DATA with what is missing.
 * Output is a "risk score" of audit flags, never a credit rating.
 */
export type CheckStatus = 'OK' | 'WATCH' | 'FLAG' | 'INSUFFICIENT_DATA';

export type AuditInput = {
  values: Record<string, number | null | undefined>;
  reportPeriod?: string | null;
  source?: string | null;
  auditOpinion?: string | null;
  distress?: { altman_z_double_prime?: number | null; altman_zone?: string | null; zmijewski_index?: number | null; distress_probability?: number | null; status?: string | null } | null;
  beneish?: Record<string, number | null | undefined> | null; // two-year inputs; not stored today
  /** Banks/insurers: accruals, Altman and Beneish are not meaningful (balance sheet is the business). */
  financialSector?: boolean | null;
};

export type AuditCheck = {
  id: 'accruals' | 'cfo_divergence' | 'beneish' | 'altman' | 'zmijewski' | 'auditor_opinion';
  title: string;
  status: CheckStatus;
  summary: string;
  inputs: { label: string; value: number | string | null }[];
  period: string | null;
  source: string | null;
  missing: string[];
};

export type AuditReport = {
  checks: AuditCheck[];
  riskScore: number | null; // 0-100, share of weighted flags among evaluable checks
  evaluated: number;
  status: 'OK' | 'INSUFFICIENT_DATA';
  note: string;
};

export const AUDIT_NOTE = 'Risk score of audit-relevant flags from stored data. It is not a credit rating or investment advice.';
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const missing = (obj: Record<string, unknown>, keys: string[]) => keys.filter((k) => num(obj[k]) == null);
const mk = (partial: Omit<AuditCheck, 'missing'> & { missing?: string[] }): AuditCheck => ({ missing: [], ...partial });

function insufficient(id: AuditCheck['id'], title: string, miss: string[], inp: AuditInput, inputs: AuditCheck['inputs'] = []): AuditCheck {
  return mk({ id, title, status: 'INSUFFICIENT_DATA', summary: `Not enough stored data: ${miss.join(', ')}.`, inputs, period: inp.reportPeriod ?? null, source: inp.source ?? null, missing: miss });
}

export function accrualsCheck(inp: AuditInput): AuditCheck {
  const t = 'Accruals / earnings quality';
  const v = inp.values;
  const miss = missing(v, ['net_income', 'operating_cash_flow', 'total_assets']);
  if (miss.length || !num(v.total_assets)) return insufficient('accruals', t, miss.length ? miss : ['total_assets'], inp);
  const ni = num(v.net_income)!, cfo = num(v.operating_cash_flow)!, ta = num(v.total_assets)!;
  const ratio = (ni - cfo) / ta; // Sloan-style accruals on ending assets (average assets not stored)
  const status: CheckStatus = ratio > 0.1 ? 'FLAG' : ratio > 0.05 ? 'WATCH' : 'OK';
  return mk({ id: 'accruals', title: t, status, summary: `(Net income − operating cash flow) / total assets = ${(ratio * 100).toFixed(1)}%. Heuristic bands: >10% flag, 5–10% watch. Uses ending assets.`,
    inputs: [{ label: 'Net income', value: ni }, { label: 'Operating cash flow', value: cfo }, { label: 'Total assets', value: ta }], period: inp.reportPeriod ?? null, source: inp.source ?? null });
}

export function cfoDivergenceCheck(inp: AuditInput): AuditCheck {
  const t = 'Profit vs operating cash flow';
  const v = inp.values;
  const miss = missing(v, ['net_income', 'operating_cash_flow']);
  if (miss.length) return insufficient('cfo_divergence', t, miss, inp);
  const ni = num(v.net_income)!, cfo = num(v.operating_cash_flow)!;
  const inputs = [{ label: 'Net income', value: ni }, { label: 'Operating cash flow', value: cfo }];
  let status: CheckStatus = 'OK', summary: string;
  if (ni > 0 && cfo <= 0) { status = 'FLAG'; summary = 'Profit reported while operating cash flow is not positive.'; }
  else if (ni > 0 && cfo / ni < 0.5) { status = 'WATCH'; summary = `Operating cash flow is ${(cfo / ni * 100).toFixed(0)}% of net income (<50%).`; }
  else if (ni > 0) summary = `Operating cash flow is ${(cfo / ni * 100).toFixed(0)}% of net income.`;
  else summary = 'Net income is not positive; the cash-conversion test does not apply.';
  return mk({ id: 'cfo_divergence', title: t, status, summary, inputs, period: inp.reportPeriod ?? null, source: inp.source ?? null });
}

const BENEISH_KEYS = ['receivables', 'receivables_prev', 'revenue', 'revenue_prev', 'gross_profit', 'gross_profit_prev', 'ppe', 'ppe_prev', 'depreciation', 'depreciation_prev', 'sga', 'sga_prev', 'total_assets', 'total_assets_prev', 'total_debt', 'total_debt_prev', 'net_income', 'operating_cash_flow'];

export function beneishCheck(inp: AuditInput): AuditCheck {
  const t = 'Beneish M-Score';
  const b = inp.beneish ?? {};
  const miss = missing(b, BENEISH_KEYS);
  if (miss.length) return insufficient('beneish', t, miss, inp);
  const g = (k: string) => num(b[k])!;
  const dsri = (g('receivables') / g('revenue')) / (g('receivables_prev') / g('revenue_prev'));
  const gmi = ((g('gross_profit_prev') / g('revenue_prev')) / (g('gross_profit') / g('revenue')));
  const aqi = (1 - (g('ppe')) / g('total_assets')) / (1 - g('ppe_prev') / g('total_assets_prev'));
  const sgi = g('revenue') / g('revenue_prev');
  const depi = (g('depreciation_prev') / (g('depreciation_prev') + g('ppe_prev'))) / (g('depreciation') / (g('depreciation') + g('ppe')));
  const sgai = (g('sga') / g('revenue')) / (g('sga_prev') / g('revenue_prev'));
  const lvgi = (g('total_debt') / g('total_assets')) / (g('total_debt_prev') / g('total_assets_prev'));
  const tata = (g('net_income') - g('operating_cash_flow')) / g('total_assets');
  const m = -4.84 + 0.92 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi + 0.115 * depi - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi;
  const status: CheckStatus = m > -1.78 ? 'FLAG' : m > -2.22 ? 'WATCH' : 'OK';
  return mk({ id: 'beneish', title: t, status, summary: `M-Score ${m.toFixed(2)} (8-variable model; > −1.78 flag, > −2.22 watch).`, inputs: BENEISH_KEYS.map((k) => ({ label: k, value: g(k) })), period: inp.reportPeriod ?? null, source: inp.source ?? null });
}

export function altmanCheck(inp: AuditInput): AuditCheck {
  const t = 'Altman Z″ (stored distress model)';
  const d = inp.distress, z = num(d?.altman_z_double_prime);
  if (z == null) return insufficient('altman', t, ['altman_z_double_prime'], inp);
  const status: CheckStatus = z < 1.1 ? 'FLAG' : z < 2.6 ? 'WATCH' : 'OK';
  return mk({ id: 'altman', title: t, status, summary: `Z″ ${z.toFixed(2)}${d?.altman_zone ? ` (${d.altman_zone})` : ''}. Bands: <1.1 distress, 1.1–2.6 grey, >2.6 safe. Not reliable for capital-intensive or financial sectors.`,
    inputs: [{ label: 'Altman Z″', value: z }], period: inp.reportPeriod ?? null, source: 'BIAP Agent 9 (stored)', });
}

export function zmijewskiCheck(inp: AuditInput): AuditCheck {
  const t = 'Zmijewski distress probability (stored)';
  const d = inp.distress, p = num(d?.distress_probability);
  if (p == null) return insufficient('zmijewski', t, ['distress_probability'], inp);
  const status: CheckStatus = p >= 0.5 ? 'FLAG' : p >= 0.2 ? 'WATCH' : 'OK';
  return mk({ id: 'zmijewski', title: t, status, summary: `Distress probability ${(p * 100).toFixed(1)}% (>=50% flag, 20–50% watch).`,
    inputs: [{ label: 'Distress probability', value: p }, { label: 'Zmijewski index', value: num(d?.zmijewski_index) }], period: inp.reportPeriod ?? null, source: 'BIAP Agent 9 (stored)' });
}

export function auditorOpinionCheck(inp: AuditInput): AuditCheck {
  const t = 'Auditor opinion';
  const o = (inp.auditOpinion || '').trim();
  if (!o) return insufficient('auditor_opinion', t, ['audit_opinion'], inp);
  const low = o.toLowerCase();
  const status: CheckStatus = /(adverse|disclaimer|going concern)/.test(low) ? 'FLAG' : /(qualified|emphasis)/.test(low) && !/unqualified/.test(low) ? 'WATCH' : 'OK';
  return mk({ id: 'auditor_opinion', title: t, status, summary: `Reported opinion: ${o}.`, inputs: [{ label: 'Opinion', value: o }], period: inp.reportPeriod ?? null, source: inp.source ?? null });
}

const WEIGHTS: Record<CheckStatus, number> = { OK: 0, WATCH: 0.5, FLAG: 1, INSUFFICIENT_DATA: 0 };

const NOT_FOR_FINANCIALS = new Set<AuditCheck['id']>(['accruals', 'altman', 'beneish']);

export function runAudit(inp: AuditInput): AuditReport {
  const raw = [accrualsCheck(inp), cfoDivergenceCheck(inp), beneishCheck(inp), altmanCheck(inp), zmijewskiCheck(inp), auditorOpinionCheck(inp)];
  const checks = inp.financialSector
    ? raw.map((c) => NOT_FOR_FINANCIALS.has(c.id)
        ? { ...c, status: 'INSUFFICIENT_DATA' as CheckStatus, summary: 'Not meaningful for banks and insurers (financial-sector issuer); not evaluated.', missing: ['non-financial issuer'] }
        : c)
    : raw;
  const done = checks.filter((c) => c.status !== 'INSUFFICIENT_DATA');
  if (done.length < 2) return { checks, riskScore: null, evaluated: done.length, status: 'INSUFFICIENT_DATA', note: AUDIT_NOTE };
  const score = Math.round((done.reduce((s, c) => s + WEIGHTS[c.status], 0) / done.length) * 100);
  return { checks, riskScore: score, evaluated: done.length, status: 'OK', note: AUDIT_NOTE };
}

/** API flag when present, else the sector/industry text (HSBC comes with sector "Financials", flag null). */
export function isFinancialSector(flag: boolean | null | undefined, sector?: string | null, industry?: string | null): boolean {
  if (typeof flag === 'boolean') return flag;
  return /financial|bank|insur/i.test(`${sector || ''} ${industry || ''}`);
}
