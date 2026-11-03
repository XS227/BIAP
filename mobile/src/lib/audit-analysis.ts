/**
 * «تحلیل حسابرسی» — deterministic checks on the CODAL statements BIAP has stored for one company.
 * No model, no invented numbers. Only what the importer actually stores is used (current and
 * previous year revenue, net profit, assets, liabilities, equity, audit opinion text).
 * Checks that need other inputs (cash flow, receivables, working capital…) are reported as
 * INSUFFICIENT_DATA instead of being guessed. The output is a "risk score", never a credit rating.
 */
export type CheckStatus = 'OK' | 'WATCH' | 'FLAG' | 'INSUFFICIENT_DATA';
export type AuditCheck = {
  id: string; title: string; status: CheckStatus; summary: string;
  inputs: { label: string; value: number | string | null }[]; period: string | null; source: string | null;
  /** counts toward the risk score (data-quality checks do not) */
  scored: boolean;
};
export type AuditReport = { checks: AuditCheck[]; evaluated: number; riskScore: number | null; note: string };
export type IranFundamentals = {
  revenue_current?: number | null; revenue_prev?: number | null;
  net_profit_current?: number | null; net_profit_prev?: number | null;
  total_assets_current?: number | null; total_assets_prev?: number | null;
  total_liabilities_current?: number | null; total_liabilities_prev?: number | null;
  total_equity_current?: number | null; total_equity_prev?: number | null;
  audit_opinion?: string | null; report_title?: string | null; report_scope?: string | null; source?: string | null;
  tracing_no?: string | null;
};

export const AUDIT_NOTE = 'امتیاز ریسک یک غربالگری ساده است؛ رتبه‌ی اعتباری یا نظر حسابرس نیست.';
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const r2 = (v: number) => Math.round(v * 100) / 100;

export function runIranAudit(f: IranFundamentals | null | undefined): AuditReport {
  const period = f?.report_title ?? null;
  const source = f ? [f.source, f.report_scope, f.tracing_no ? `کد رهگیری ${f.tracing_no}` : null].filter(Boolean).join(' · ') || null : null;
  const rev = num(f?.revenue_current), revP = num(f?.revenue_prev), ni = num(f?.net_profit_current), niP = num(f?.net_profit_prev);
  const ta = num(f?.total_assets_current), tl = num(f?.total_liabilities_current), eq = num(f?.total_equity_current), eqP = num(f?.total_equity_prev);
  const mk = (id: string, title: string, scored: boolean, status: CheckStatus, summary: string, inputs: AuditCheck['inputs']): AuditCheck =>
    ({ id, title, status, summary, inputs, period, source, scored });
  const missing = (id: string, title: string, need: string) => mk(id, title, true, 'INSUFFICIENT_DATA', `داده کافی نیست: ${need} در صورت‌های ذخیره‌شده وجود ندارد.`, []);
  const checks: AuditCheck[] = [];

  // data quality: balance-sheet identity (not scored)
  if (ta != null && tl != null && eq != null && ta > 0) {
    const gap = Math.abs(ta - (tl + eq)) / ta;
    checks.push(mk('identity', 'سازگاری ترازنامه (دارایی = بدهی + حقوق صاحبان سهام)', false, gap <= 0.01 ? 'OK' : 'FLAG',
      gap <= 0.01 ? 'ارقام ترازنامه سازگارند.' : `ارقام ترازنامه با هم نمی‌خوانند (اختلاف ${r2(gap * 100)}٪)؛ به اعداد دارایی/بدهی اعتماد نکنید تا منبع بازبینی شود.`,
      [{ label: 'جمع دارایی', value: ta }, { label: 'جمع بدهی', value: tl }, { label: 'حقوق صاحبان سهام', value: eq }, { label: 'اختلاف نسبی', value: r2(gap * 100) }]));
  } else checks.push(missing('identity', 'سازگاری ترازنامه', 'جمع دارایی، بدهی یا حقوق صاحبان سهام'));

  // net margin change
  if (rev && revP && ni != null && niP != null) {
    const m = (ni / rev) * 100, mp = (niP / revP) * 100, d = m - mp;
    checks.push(mk('margin', 'تغییر حاشیه‌ی سود خالص', true, d <= -10 ? 'FLAG' : d <= -4 ? 'WATCH' : 'OK',
      `حاشیه‌ی سود خالص از ${r2(mp)}٪ به ${r2(m)}٪ رسیده است (${d >= 0 ? '+' : ''}${r2(d)} واحد درصد).`,
      [{ label: 'درآمد (جاری)', value: rev }, { label: 'درآمد (قبل)', value: revP }, { label: 'سود خالص (جاری)', value: ni }, { label: 'سود خالص (قبل)', value: niP }]));
  } else checks.push(missing('margin', 'تغییر حاشیه‌ی سود خالص', 'درآمد و سود خالص دو سال'));

  // leverage
  if (ta != null && tl != null && ta > 0 && eq != null && tl + eq > 0) {
    const lev = tl / (tl + eq);
    checks.push(mk('leverage', 'اهرم مالی (بدهی به کل منابع)', true, lev >= 0.85 ? 'FLAG' : lev >= 0.7 ? 'WATCH' : 'OK',
      `بدهی ${r2(lev * 100)}٪ از کل منابع تأمین مالی است.`, [{ label: 'جمع بدهی', value: tl }, { label: 'حقوق صاحبان سهام', value: eq }, { label: 'نسبت', value: r2(lev * 100) }]));
  } else checks.push(missing('leverage', 'اهرم مالی', 'جمع بدهی و حقوق صاحبان سهام'));

  // equity trend
  if (eq != null && eqP != null && eqP > 0) {
    const ch = ((eq - eqP) / eqP) * 100;
    checks.push(mk('equity', 'روند حقوق صاحبان سهام', true, ch <= -25 ? 'FLAG' : ch <= -10 ? 'WATCH' : 'OK',
      `حقوق صاحبان سهام ${ch >= 0 ? '+' : ''}${r2(ch)}٪ نسبت به سال قبل تغییر کرده است.`, [{ label: 'جاری', value: eq }, { label: 'قبل', value: eqP }]));
  } else checks.push(missing('equity', 'روند حقوق صاحبان سهام', 'حقوق صاحبان سهام دو سال'));

  // checks the stored statements cannot support
  checks.push(missing('accruals', 'کیفیت سود (اقلام تعهدی)', 'جریان نقدی عملیاتی'));
  checks.push(missing('cfo', 'اختلاف سود و جریان نقدی عملیاتی', 'جریان نقدی عملیاتی'));
  checks.push(missing('beneish', 'امتیاز بنیش (Beneish M-Score)', 'حساب‌های دریافتنی، دارایی ثابت و هزینه‌ی استهلاک دو سال'));
  checks.push(missing('altman', 'امتیاز آلتمن (Z″)', 'سرمایه در گردش و سود انباشته'));
  checks.push(missing('zmijewski', 'امتیاز زمیجفسکی', 'دارایی/بدهی جاری'));
  const op = (f?.audit_opinion ?? '').trim();
  checks.push(op
    ? mk('opinion', 'نظر حسابرس', true, /مردود|عدم اظهار|مشروط/.test(op) ? 'FLAG' : /مقبول/.test(op) ? 'OK' : 'WATCH', `نظر حسابرس: ${op.slice(0, 160)}`, [{ label: 'متن', value: op.slice(0, 160) }])
    : missing('opinion', 'نظر حسابرس', 'متن نظر حسابرس'));

  const scored = checks.filter((c) => c.scored && c.status !== 'INSUFFICIENT_DATA');
  const pts = { OK: 0, WATCH: 50, FLAG: 100, INSUFFICIENT_DATA: 0 } as const;
  const riskScore = scored.length >= 2 ? Math.round(scored.reduce((a, c) => a + pts[c.status], 0) / scored.length) : null;
  return { checks, evaluated: checks.filter((c) => c.status !== 'INSUFFICIENT_DATA').length, riskScore, note: AUDIT_NOTE };
}
