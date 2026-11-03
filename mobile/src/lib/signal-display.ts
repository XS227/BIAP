/** Honest display rules for the Iranian app: never show Buy/Sell on missing evidence, weights add to 100, queue badge. */
export type EvidenceReviewLike = { actionable?: boolean | null } | null | undefined;

/** Fail closed: anything but an explicit actionable review means the call must not be shown as a trade signal. */
export function evidenceHeld(review: EvidenceReviewLike): boolean {
  return review?.actionable !== true;
}

export const DATA_HOLD_LABEL = 'داده کافی نیست';

const CALL_LABEL: Record<string, string> = { BUY: 'خرید', SELL: 'فروش', HOLD: 'نگهداری' };

export function callBadge(call: string, review: EvidenceReviewLike): { label: string; neutral: boolean } {
  if (evidenceHeld(review)) return { label: DATA_HOLD_LABEL, neutral: true };
  return { label: CALL_LABEL[call] ?? call, neutral: false };
}

/** Portfolio-tracking button: neutral wording; "bought" wording only when a live, actionable BUY exists. */
export function trackButtonLabel(call: string, review: EvidenceReviewLike, alreadyTracked: boolean): { label: string; neutral: boolean } {
  const strongBuy = call === 'BUY' && !evidenceHeld(review);
  if (strongBuy) return { label: alreadyTracked ? 'خریدم بیشتر — ثبت' : 'خریدم — شروع پیگیری', neutral: false };
  return { label: alreadyTracked ? 'ثبت در پرتفوی من (افزودن)' : 'ثبت در پرتفوی من', neutral: true };
}

/** Whole-percent weights that always sum to exactly 100 (largest remainder), so the display never shows 99% or 101%. */
export function normalizedWeightPercents(weights: (number | null | undefined)[]): number[] {
  const w = weights.map((x) => (typeof x === 'number' && Number.isFinite(x) && x > 0 ? x : 0));
  const total = w.reduce((a, b) => a + b, 0);
  if (total <= 0) return w.map(() => 0);
  const raw = w.map((x) => (x / total) * 100);
  const floor = raw.map(Math.floor);
  let left = 100 - floor.reduce((a, b) => a + b, 0);
  const order = raw.map((r, i) => ({ i, f: r - Math.floor(r) })).sort((a, b) => b.f - a.f || a.i - b.i);
  for (const { i } of order) { if (left <= 0) break; floor[i] += 1; left -= 1; }
  return floor;
}

export const QUEUE_LABEL = 'تک‌قیمت در حد مجاز نوسان — احتمال صف خرید/فروش';

/** Single traded price all day with volume, sitting at a daily limit band (3% / 5%). A heuristic: the exact limit is not in the API. */
export function queueBadge(m: { dayLow?: number | null; dayHigh?: number | null; changePercent?: number | null; volumeToday?: number | null } | null | undefined): { side: 'BUY' | 'SELL'; label: string } | null {
  if (!m || m.dayLow == null || m.dayHigh == null || m.changePercent == null) return null;
  if (m.dayLow !== m.dayHigh) return null;
  if (!(Number(m.volumeToday) > 0)) return null;
  const c = m.changePercent;
  const atBand = [3, 5].some((band) => Math.abs(c) >= band - 0.2 && Math.abs(c) <= band + 0.05);
  if (!atBand) return null;
  return { side: c > 0 ? 'BUY' : 'SELL', label: c > 0 ? 'صف خرید (احتمالی)' : 'صف فروش (احتمالی)' };
}

/** An agent's confidence is its own estimate; show how many graded past calls back it so a high % on a tiny record is not read as proven. */
export function confidenceNote(samples?: number | null, maturity?: string | null): string {
  if (samples == null) return '';
  if (samples <= 0) return ' (بدون سابقه‌ی ارزیابی‌شده)';
  if (samples < 10) return ` (سابقه‌ی کم: ${samples} نمونه${maturity ? ` • ${maturity}` : ''})`;
  return ` (${samples} نمونه‌ی ارزیابی‌شده)`;
}
