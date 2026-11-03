/** Persian wording for the backend's CODAL evidence review (status + reasons). The server sends English codes. */
const STATUS_FA: Record<string, string> = { PASS: 'تأییدشده', WARN: 'ناقص', BLOCK: 'مسدود', MISSING: 'موجود نیست' };
const REASON_FA: Array<[RegExp, string]> = [
  [/Verified CODAL fundamentals unavailable/i, 'صورت مالی تأییدشده‌ی کدال موجود نیست'],
  [/Filing provenance.*incomplete/i, 'منبع گزارش (عنوان، شماره پیگیری و لینک) کامل نیست'],
  [/Revenue.*net profit.*missing or invalid/i, 'درآمد یا سود خالص موجود نیست یا نامعتبر است'],
  [/Both periods balance/i, 'ترازنامه‌ی هر دو دوره تطبیق دارد؛ منبع کدال و سود و زیان اصلی موجود است'],
  [/assets\/liabilities\/equity incomplete/i, 'دارایی، بدهی یا حقوق صاحبان سهام ناقص است'],
  [/assets non-positive/i, 'جمع دارایی‌ها صفر یا منفی است'],
  [/balance-sheet identity mismatch/i, 'ترازنامه تطبیق ندارد (دارایی ≠ بدهی + حقوق)'],
  [/balance sheet ties/i, 'ترازنامه تطبیق دارد'],
];
export function evidenceStatusFa(status?: string | null): string { return STATUS_FA[String(status ?? '').toUpperCase()] ?? 'نامشخص'; }
export function evidenceReasonFa(reason: string): string {
  const periodFa = /current/i.test(reason) ? 'دوره‌ی جاری: ' : /prev|compar/i.test(reason) ? 'دوره‌ی قبل: ' : '';
  const hit = REASON_FA.find(([re]) => re.test(reason));
  return hit ? periodFa + hit[1] : 'جزئیات فنی بررسی شواهد در دسترس نیست';
}
export function evidenceReasonsFa(reasons?: string[] | null): string { return (reasons ?? []).map(evidenceReasonFa).join('؛ '); }
