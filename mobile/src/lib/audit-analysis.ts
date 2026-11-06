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
  /** CODAL report link shown as a tappable row on the card */
  link?: string | null;
  /** counts toward the risk score (data-quality checks do not) */
  scored: boolean;
};
export type AuditReport = { checks: AuditCheck[]; evaluated: number; total: number; minCoverage: number; riskScore: number | null; note: string; stale: boolean; withheld: boolean };
/** A risk score is shown only when at least this many of the checks could actually be evaluated. */
export const MIN_AUDIT_COVERAGE = 6;
export type IranFundamentals = {
  revenue_current?: number | null; revenue_prev?: number | null;
  net_profit_current?: number | null; net_profit_prev?: number | null;
  total_assets_current?: number | null; total_assets_prev?: number | null;
  total_liabilities_current?: number | null; total_liabilities_prev?: number | null;
  total_equity_current?: number | null; total_equity_prev?: number | null;
  audit_opinion?: string | null; report_title?: string | null; report_scope?: string | null; source?: string | null;
  tracing_no?: string | null;
  /** auditor firm, the «مبنای اظهارنظر» paragraphs and the CODAL report link, when the importer captured them */
  auditor_name?: string | null; audit_basis?: string | null; report_url?: string | null;
  /** backend re-verification stamp (codal_reparse) when present */
  verification?: { status?: string | null; reason?: string | null } | null;
  operating_cash_flow_current?: number | null; operating_cash_flow_prev?: number | null;
  current_assets_current?: number | null; current_liabilities_current?: number | null;
  receivables_current?: number | null; retained_earnings_current?: number | null;
  current_assets_prev?: number | null; current_liabilities_prev?: number | null; receivables_prev?: number | null;
  fixed_assets_current?: number | null; fixed_assets_prev?: number | null;
  gross_profit_current?: number | null; gross_profit_prev?: number | null;
  operating_profit_current?: number | null; sga_expense_current?: number | null; sga_expense_prev?: number | null;
  depreciation_current?: number | null; depreciation_prev?: number | null;
};

/** CODAL titles carry «(حسابرسی نشده)» for unaudited statements: those have NO auditor opinion, whatever the importer stored. */
export function isUnaudited(title: string | null | undefined): boolean {
  return String(title ?? '').replace(/ي/g, 'ی').replace(/ك/g, 'ک').replace(/[\u200c\u00a0]/g, ' ').replace(/\s+/g, ' ').includes('حسابرسی نشده');
}

/** The importer stores English opinion codes; the audit screen shows Persian. */
export function auditOpinionFa(raw: string): string {
  const t = raw.trim().toLowerCase();
  if (t === 'unqualified' || t === 'clean') return 'مقبول';
  if (t === 'qualified') return 'مشروط';
  if (t === 'adverse') return 'مردود';
  if (t === 'disclaimer') return 'عدم اظهار نظر';
  return raw.trim();
}


/** Standard normal CDF (Abramowitz–Stegun 7.1.26, |error| < 1.5e-7). Zmijewski (1984) is a PROBIT model: P = Φ(x). */
export function normCdf(x: number): number {
  const t = 1 / (1 + 0.3275911 * Math.abs(x) / Math.SQRT2);
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-(x * x) / 2);
  return x >= 0 ? 0.5 * (1 + y) : 0.5 * (1 - y);
}
const FA_TO_EN = (s: string) => s.replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d))).replace(/[٠-٩]/g, (d) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)));
/** Jalali period end («منتهی به ۱۴۰۴/۱۲/۲۹») from the statement title. */
export function periodEndOf(title: string | null | undefined): { y: number; m: number; text: string } | null {
  const m = FA_TO_EN(String(title ?? '')).match(/(\d{4})\/(\d{2})\/(\d{2})/);
  return m ? { y: Number(m[1]), m: Number(m[2]), text: `${m[1]}/${m[2]}/${m[3]}` } : null;
}
export function jalaliYearMonth(now: Date): { y: number; m: number } {
  const parts = new Intl.DateTimeFormat('en-u-ca-persian-nu-latn', { year: 'numeric', month: 'numeric' }).formatToParts(now);
  return { y: Number(parts.find((p) => p.type === 'year')?.value), m: Number(parts.find((p) => p.type === 'month')?.value) };
}
export const STALE_AFTER_MONTHS = 18;
/** Same limits as the backend sanity guard: beyond them a ratio is a unit/parse error, shown as «داده نامعتبر» and never used. */
export const RATIO_LIMITS: Record<string, number> = { margin: 2, roa: 1.5, roe: 3 };
export function invalidRatios(f: { revenue_current?: number | null; net_profit_current?: number | null; total_assets_current?: number | null; total_equity_current?: number | null } | null | undefined): string[] {
  const out: string[] = [];
  if (!f) return out;
  const { revenue_current: rev, net_profit_current: ni, total_assets_current: ta, total_equity_current: eq } = f;
  if (rev && ni != null && Math.abs(ni / rev) > RATIO_LIMITS.margin) out.push('حاشیه سود خالص');
  if (ta && ta > 0 && ni != null && Math.abs(ni / ta) > RATIO_LIMITS.roa) out.push('ROA');
  if (eq && eq > 0 && ni != null && Math.abs(ni / eq) > RATIO_LIMITS.roe) out.push('ROE');
  return out;
}
/** Checks whose inputs come from the balance sheet: withheld when the balance sheet is not verified. */
export const BALANCE_SHEET_CHECKS = ['leverage', 'equity', 'accruals', 'zmijewski', 'altman', 'beneish'];

export const AUDIT_NOTE = 'امتیاز ریسک یک غربالگری ساده است؛ رتبه‌ی اعتباری یا نظر حسابرس نیست.';
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const r2 = (v: number) => Math.round(v * 100) / 100;

export function runIranAudit(f: IranFundamentals | null | undefined, now: Date = new Date()): AuditReport {
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

  // earnings quality / cash-flow divergence (needs operating cash flow)
  const cfo = num(f?.operating_cash_flow_current);
  if (cfo != null && ni != null && ta != null && ta > 0) {
    const acc = (ni - cfo) / ta;
    checks.push(mk('accruals', 'کیفیت سود (اقلام تعهدی)', true, acc >= 0.2 ? 'FLAG' : acc >= 0.1 ? 'WATCH' : 'OK',
      `اقلام تعهدی به کل دارایی‌ها ${r2(acc * 100)}٪ است (سود خالص − جریان نقدی عملیاتی).`,
      [{ label: 'سود خالص', value: ni }, { label: 'جریان نقدی عملیاتی', value: cfo }, { label: 'جمع دارایی', value: ta }, { label: 'نسبت', value: r2(acc * 100) }]));
  } else checks.push(missing('accruals', 'کیفیت سود (اقلام تعهدی)', 'جریان نقدی عملیاتی'));
  if (cfo != null && ni != null) {
    const bad = ni > 0 && (cfo < 0 || cfo < 0.5 * ni);
    checks.push(mk('cfo', 'اختلاف سود و جریان نقدی عملیاتی', true, ni > 0 && cfo < 0 ? 'FLAG' : bad ? 'WATCH' : 'OK',
      ni > 0 ? `جریان نقدی عملیاتی ${r2((cfo / ni) * 100)}٪ سود خالص است.` : 'سود خالص مثبت نیست؛ نسبت جریان نقدی به سود معنادار نیست.',
      [{ label: 'سود خالص', value: ni }, { label: 'جریان نقدی عملیاتی', value: cfo }]));
  } else checks.push(missing('cfo', 'اختلاف سود و جریان نقدی عملیاتی', 'جریان نقدی عملیاتی'));
  const ca = num(f?.current_assets_current), cl = num(f?.current_liabilities_current);
  if (ni != null && ta != null && ta > 0 && tl != null && ca != null && cl != null && cl > 0) {
    const x = -4.336 - 4.513 * (ni / ta) + 5.679 * (tl / ta) + 0.004 * (ca / cl);
    const p = normCdf(x);
    checks.push(mk('zmijewski', 'امتیاز زمیجفسکی (احتمال درماندگی)', true, p >= 0.5 ? 'FLAG' : p >= 0.2 ? 'WATCH' : 'OK',
      `احتمال برآوردی درماندگی مالی ${r2(p * 100)}٪ (مدل پروبیت زمیجفسکی؛ پیش‌بینی قطعی نیست).`,
      [{ label: 'ROA', value: r2((ni / ta) * 100) }, { label: 'بدهی/دارایی', value: r2((tl / ta) * 100) }, { label: 'نسبت جاری', value: r2(ca / cl) }, { label: 'احتمال', value: r2(p * 100) }]));
  } else checks.push(missing('zmijewski', 'امتیاز زمیجفسکی', 'دارایی‌های جاری و بدهی‌های جاری (نسبت جاری)'));
  // Altman Z'' (non-manufacturing/emerging-market form): needs working capital, retained earnings, EBIT.
  const ebit = num(f?.operating_profit_current), re = num(f?.retained_earnings_current);
  if (ca != null && cl != null && re != null && ebit != null && ta != null && ta > 0 && tl != null && tl > 0 && eq != null) {
    const z = 6.56 * ((ca - cl) / ta) + 3.26 * (re / ta) + 6.72 * (ebit / ta) + 1.05 * (eq / tl);
    checks.push(mk('altman', 'امتیاز آلتمن (Z″)', true, z < 1.1 ? 'FLAG' : z < 2.6 ? 'WATCH' : 'OK',
      `Z″ = ${r2(z)} (زیر ۱٫۱ ناحیه‌ی خطر، ۱٫۱ تا ۲٫۶ ناحیه‌ی خاکستری، بالای ۲٫۶ امن). مدل عمومی است و برای صنایع سرمایه‌بر محتاطانه تفسیر شود.`,
      [{ label: 'سرمایه در گردش/دارایی', value: r2((ca - cl) / ta) }, { label: 'سود انباشته/دارایی', value: r2(re / ta) }, { label: 'سود عملیاتی/دارایی', value: r2(ebit / ta) }, { label: 'حقوق صاحبان سهام/بدهی', value: r2(eq / tl) }]));
  } else checks.push(missing('altman', 'امتیاز آلتمن (Z″)', 'سرمایه در گردش، سود انباشته و سود عملیاتی'));

  // Beneish M-Score (8 variables). Every input for both years is required; otherwise INSUFFICIENT_DATA.
  const g = (k: keyof IranFundamentals) => num(f?.[k]);
  const B = { rec: g('receivables_current'), recP: g('receivables_prev'), gp: g('gross_profit_current'), gpP: g('gross_profit_prev'), ca, caP: g('current_assets_prev'),
    ppe: g('fixed_assets_current'), ppeP: g('fixed_assets_prev'), dep: g('depreciation_current'), depP: g('depreciation_prev'), sga: g('sga_expense_current'), sgaP: g('sga_expense_prev'),
    taP: num(f?.total_assets_prev), tlP: num(f?.total_liabilities_prev) };
  const all = [rev, revP, ta, B.taP, tl, B.tlP, ni, cfo, B.rec, B.recP, B.gp, B.gpP, B.ca, B.caP, B.ppe, B.ppeP, B.dep, B.depP, B.sga, B.sgaP];
  if (all.every((v) => v != null) && rev! > 0 && revP! > 0 && B.recP! > 0 && B.taP! > 0 && ta! > 0 && B.gp! > 0 && B.gpP! > 0 && (B.dep! + B.ppe!) > 0 && (B.depP! + B.ppeP!) > 0) {
    const a = (v: number | null) => Math.abs(v as number);
    const dsri = (B.rec! / rev!) / (B.recP! / revP!);
    const gmi = (B.gpP! / revP!) / (B.gp! / rev!);
    const aqi = (1 - (B.ca! + B.ppe!) / ta!) / (1 - (B.caP! + B.ppeP!) / B.taP!);
    const sgi = rev! / revP!;
    const depi = (a(B.depP) / (a(B.depP) + B.ppeP!)) / (a(B.dep) / (a(B.dep) + B.ppe!));
    const sgai = (a(B.sga) / rev!) / (a(B.sgaP) / revP!);
    const lvgi = (tl! / ta!) / (B.tlP! / B.taP!);
    const tata = (ni! - cfo!) / ta!;
    const m = -4.84 + 0.92 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi + 0.115 * depi - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi;
    // Complete source fields do not guarantee valid ratios. Zero denominators
    // (e.g. zero depreciation or a prior-period asset-quality index of zero)
    // must never yield NaN/Infinity and a green "OK" audit.
    if ([dsri, gmi, aqi, sgi, depi, sgai, lvgi, tata, m].every(Number.isFinite)) {
      checks.push(mk('beneish', 'امتیاز بنیش (Beneish M-Score)', true, m > -1.78 ? 'FLAG' : m > -2.22 ? 'WATCH' : 'OK',
        `M = ${r2(m)} (بالاتر از ‎−۱٫۷۸ احتمال دستکاری سود بیشتر است). غربالگری آماری است، نه اثبات تقلب.`,
        [{ label: 'DSRI', value: r2(dsri) }, { label: 'GMI', value: r2(gmi) }, { label: 'AQI', value: r2(aqi) }, { label: 'SGI', value: r2(sgi) }, { label: 'DEPI', value: r2(depi) }, { label: 'SGAI', value: r2(sgai) }, { label: 'LVGI', value: r2(lvgi) }, { label: 'TATA', value: r2(tata) }]));
    } else {
      checks.push(missing('beneish', 'امتیاز بنیش (Beneish M-Score)', 'مخرج یکی از نسبت‌ها صفر یا یکی از شاخص‌های محاسبه‌شده نامعتبر است'));
    }
  } else checks.push(missing('beneish', 'امتیاز بنیش (Beneish M-Score)', 'حساب‌های دریافتنی، دارایی ثابت، هزینه‌ی استهلاک و هزینه‌های فروش/اداری برای دو سال'));

  const link = f?.report_url ?? null;
  const tracing = f?.tracing_no ? `شماره رهگیری کدال ${f.tracing_no}` : null;
  if (isUnaudited(f?.report_title)) {
    const c = mk('opinion', 'نظر حسابرس', false, 'INSUFFICIENT_DATA', `حسابرسی نشده: این صورت مالی حسابرسی نشده و نظر حسابرس ندارد.${tracing ? ` • ${tracing}` : ''}`, [{ label: 'وضعیت', value: 'حسابرسی نشده' }]);
    checks.push({ ...c, link });
  } else {
    const op = auditOpinionFa(f?.audit_opinion ?? '');
    if (op) {
      const c = mk('opinion', 'نظر حسابرس', true, /مردود|عدم اظهار|مشروط/.test(op) ? 'FLAG' : /مقبول/.test(op) ? 'OK' : 'WATCH', `نظر حسابرس: ${op.slice(0, 160)}${tracing ? ` • ${tracing}` : ''}`, [
        { label: 'نظر', value: op.slice(0, 160) },
        { label: 'مؤسسهٔ حسابرسی', value: f?.auditor_name?.trim() || 'در داده‌ی ذخیره‌شده موجود نیست' },
        { label: 'مبنای اظهارنظر', value: f?.audit_basis?.trim() ? f.audit_basis.trim().slice(0, 1200) : 'متن بند مبانی هنوز از گزارش کدال استخراج نشده است' },
      ]);
      checks.push({ ...c, link });
    } else checks.push({ ...missing('opinion', 'نظر حسابرس', 'متن نظر حسابرس'), link });
  }

  // Verification gate: balance-sheet based checks are never computed on a statement that does not reconcile or was not confirmed.
  const idCheck = checks.find((c) => c.id === 'identity');
  const stampedBad = f?.verification?.status === 'unverified';
  const badRatios = invalidRatios(f);
  const withheld = Boolean(f) && ((idCheck?.status === 'FLAG') || stampedBad || badRatios.length > 0);
  if (withheld) {
    const why = badRatios.length ? `داده نامعتبر: ${badRatios.join('، ')} خارج از دامنه‌ی معتبر است (احتمال خطای واحد یا استخراج)؛ محاسبه نشد${f?.tracing_no ? ` • شماره رهگیری کدال ${f.tracing_no}` : ''}` : `تأییدنشده: ${stampedBad && f?.verification?.reason ? f.verification.reason : 'ترازنامه‌ی ذخیره‌شده با خودش تراز نیست'}${f?.tracing_no ? ` • شماره رهگیری کدال ${f.tracing_no}` : ''}`;
    for (let i = 0; i < checks.length; i++) if (BALANCE_SHEET_CHECKS.includes(checks[i].id)) checks[i] = mk(checks[i].id, checks[i].title, true, 'INSUFFICIENT_DATA', why, []);
  }
  const end = periodEndOf(f?.report_title);
  const cur = jalaliYearMonth(now);
  const age = end ? (cur.y * 12 + cur.m) - (end.y * 12 + end.m) : null;
  const stale = age !== null && age > STALE_AFTER_MONTHS;
  if (stale) checks.push(mk('freshness', 'تازگی صورت مالی', false, 'WATCH', `صورت مالی مربوط به دوره‌ی منتهی به ${end!.text} است (${age} ماه پیش)؛ امتیاز ریسک برای آن محاسبه نمی‌شود.`, [{ label: 'پایان دوره', value: end!.text }]));

  const scored = checks.filter((c) => c.scored && c.status !== 'INSUFFICIENT_DATA');
  const pts = { OK: 0, WATCH: 50, FLAG: 100, INSUFFICIENT_DATA: 0 } as const;
  const evaluated = checks.filter((c) => c.status !== 'INSUFFICIENT_DATA').length;
  const riskScore = !stale && !withheld && evaluated >= MIN_AUDIT_COVERAGE && scored.length >= 2 ? Math.round(scored.reduce((a, c) => a + pts[c.status], 0) / scored.length) : null;
  return { checks, evaluated, total: checks.length, minCoverage: MIN_AUDIT_COVERAGE, riskScore, note: AUDIT_NOTE, stale, withheld };
}
