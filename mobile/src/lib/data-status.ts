/** One Persian vocabulary for data states, so a badge never claims more than the data supports. */
export type DataStatus = 'verified' | 'stale' | 'missing' | 'failed' | 'demo' | 'selected';

export const DATA_STATUS_FA: Record<DataStatus, string> = {
  verified: 'تأییدشده',
  stale: 'کهنه',
  missing: 'ناموجود',
  failed: 'ناموفق',
  demo: 'نمونه (ساختگی)',
  selected: 'انتخاب‌شده؛ داده بررسی نشده',
};

/** Price status from the backend (VERIFIED | STALE | MISSING | UNKNOWN_AGE) to the shared vocabulary. */
export function priceStatus(status: string | null | undefined): DataStatus {
  switch (status) {
    case 'VERIFIED': return 'verified';
    case 'STALE': return 'stale';
    case 'MISSING': return 'missing';
    default: return 'stale'; // unknown age is never shown as verified
  }
}

/** Agent data status to Persian. NO_DATA = the agent ran but had no verified input (its vote is not evidence). */
export function agentStatusFa(status: string | null | undefined): string {
  switch (status) {
    case 'OK': return 'داده معتبر';
    case 'LOW_CONFIDENCE': return 'اطمینان پایین';
    case 'NO_DATA': return 'داده معتبر ندارد';
    case 'MISSING': return 'ناموجود';
    default: return 'نامشخص';
  }
}

export function auditStatusFa(status: string | null | undefined): string {
  switch (status) {
    case 'PASS': return 'قبول';
    case 'WATCH': return 'نیازمند توجه';
    case 'RED_FLAG': return 'پرچم قرمز';
    case 'INSUFFICIENT_DATA': return 'داده کافی نیست';
    case 'NOT_APPLICABLE': return 'قابل اعمال نیست';
    default: return String(status ?? '');
  }
}

export function faNumber(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(Number(value))) return '—';
  return Number(value).toLocaleString('fa-IR', { maximumFractionDigits: digits });
}

export function faDate(value: string | null | undefined): string {
  if (!value) return 'ثبت نشده';
  const t = Date.parse(value);
  if (!Number.isFinite(t)) return String(value).slice(0, 19);
  return new Date(t).toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
}

/** Persian message for a failed call on the new endpoints. */
export function describeIranError(err: unknown): string {
  const e = err as { status?: number | null; message?: string } | null;
  if (!e) return 'خطای ناشناخته.';
  if ((e.status === 404 || e.status === 405) && /^(not found|method not allowed)$/i.test((e.message || '').trim())) return 'این نسخه‌ی سرور هنوز این قابلیت را ندارد.';
  if (e.status === 401 || e.status === 403) return 'نشست شما منقضی شده است؛ دوباره وارد شوید.';
  if (e.status === 404) return e.message || 'داده‌ی ذخیره‌شده‌ای برای این شرکت پیدا نشد.';
  if (e.status === 429) return e.message || 'سقف روزانه‌ی گزارش پر شده است.';
  if (e.status === 503) return `سرویس در دسترس نیست: ${e.message || 'بعداً دوباره تلاش کنید'}`;
  return e.message || 'درخواست ناموفق بود.';
}


/** Presentation-only guard: a stored BUY call is not an actionable recommendation. */
export function assessIranStoredDecisionReadiness(view: {
  price: { status: string; conflictsWithKiasha?: boolean };
  financials: { available: boolean };
  agents: { dataStatus: string; confidence: number | null }[];
  kiasha: { call: string } | null;
}) {
  const reasons: string[] = [];
  if (view.price.status !== 'VERIFIED') reasons.push('قیمت ذخیره‌شده به‌روز و تأییدشده نیست.');
  if (view.price.conflictsWithKiasha) reasons.push('قیمت ذخیره‌شده با قیمت مرجع کیاشا اختلاف دارد.');
  if (!view.financials.available) reasons.push('صورت‌های مالی قابل بررسی موجود نیست.');
  if (!view.kiasha) reasons.push('نتیجه ذخیره‌شده کیاشا موجود نیست.');
  if (view.agents.length < 7 || view.agents.some(a => a.dataStatus !== 'OK' || a.confidence == null)) {
    reasons.push('شواهد معتبر هر هفت عامل کامل نیست.');
  }
  return { evidenceComplete: reasons.length === 0, reasons, tradeEnabled: false as const };
}
