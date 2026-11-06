/**
 * Persian data-status wording and symbol display. Pure (no imports) so it is unit-tested with node.
 * A status is only "verified" when the server says so; "AUTO"/"LIVE" never imply data is present.
 */
export type DataStatus = 'verified' | 'stale' | 'missing' | 'failed';
export const DATA_STATUS_FA: Record<DataStatus, string> = {
  verified: 'تأییدشده', stale: 'قدیمی', missing: 'موجود نیست', failed: 'خطا در دریافت',
};
export const STALE_AFTER_HOURS = 36;

export function dataStatus(opts: { present: boolean; failed?: boolean; ageHours?: number | null }): DataStatus {
  if (opts.failed) return 'failed';
  if (!opts.present) return 'missing';
  if (opts.ageHours != null && (opts.ageHours > STALE_AFTER_HOURS || opts.ageHours < 0)) return 'stale';
  return 'verified';
}

/** A bare TSETMC instrument id is not a symbol: fall back to the name, never show the number. */
export function displaySymbol(symbol?: string | null, name?: string | null): string {
  const s = (symbol ?? '').trim(); const n = (name ?? '').trim();
  if (s && !/^\d{5,}$/.test(s)) return s;
  if (n && !/^\d{5,}$/.test(n)) return n;
  return 'نماد نامشخص';
}

/** Labels that used to say LIVE/AUTO even when nothing was fetched. */
export function realSourceBadge(sourceLabel: string): string {
  if (/LIVE FALLBACK/i.test(sourceLabel)) return 'دریافت مستقیم (پایگاه ذخیره‌شده موجود نبود)';
  if (/Company Dataset/i.test(sourceLabel)) return 'داده‌ی خود شرکت شما';
  return 'داده‌ی ذخیره‌شده‌ی BIAP';
}

/** Persian/Arabic letter forms differ between keyboards and TSETMC/CODAL: fold ي/ك (and ى/ة/ۀ, Arabic-Indic digits) so a search finds the stored symbol. */
export function normalizeSearch(q: string): string {
  return String(q ?? '')
    .replace(/[يىئ]/g, (c) => (c === 'ئ' ? 'ئ' : 'ی')).replace(/ك/g, 'ک').replace(/[ۀة]/g, 'ه')
    .replace(/[٠-٩]/g, (d) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d))).replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
    .replace(/[\u200c\u200f\u200e\u00a0]/g, ' ').replace(/\s+/g, ' ').trim();
}
