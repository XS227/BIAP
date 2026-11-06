/** Non-share listings (rental bonds «تابان25», funds, rights, options) are recognised from the name; the main stock must come first. */
export function isNonShareListing(item: { name?: string | null; symbol?: string | null; paper_type?: string | null }): boolean {
  const t = String(item.paper_type ?? '').trim();
  if (t) return !['300', '303', '307', '309', '313'].includes(t);
  const n = String(item.name ?? '').replace(/ي/g, 'ی').replace(/ك/g, 'ک').trim();
  return /^(اجاره|مرابحه|صکوک|اسناد|صندوق|اختیار|حق\s*تقدم|سلف|گواهی|مشارکت|منفعت)/.test(n) || /حق\s*تقدم/.test(n);
}
export function listingTypeFa(item: { name?: string | null; paper_type?: string | null }): string {
  if (!isNonShareListing(item)) return 'سهام';
  const n = String(item.name ?? '');
  if (/حق\s*تقدم/.test(n)) return 'حق‌تقدم';
  if (/^صندوق/.test(n)) return 'صندوق';
  if (/^اختیار/.test(n)) return 'اختیار معامله';
  return 'اوراق (اجاره/مرابحه)';
}
export function rankListedCompanies<T extends { symbol: string; name?: string | null; code: string }>(items: T[], q = ''): T[] {
  const nq = q.trim().replace(/ي/g, 'ی').replace(/ك/g, 'ک').toLowerCase();
  const rel = (i: T) => { const s = i.symbol.replace(/ي/g, 'ی').replace(/ك/g, 'ک').toLowerCase(); return !nq ? 2 : s === nq ? 0 : s.startsWith(nq) ? 1 : 2; };
  return [...items].sort((a, b) => (isNonShareListing(a) ? 10 : 0) + rel(a) - ((isNonShareListing(b) ? 10 : 0) + rel(b)));
}

/** Module/analysis entry points work on ordinary shares only: bonds, funds, rights and options have no CODAL statements. */
export function splitShares<T extends { name?: string | null; symbol?: string | null; paper_type?: string | null }>(items: T[]): { shares: T[]; others: T[] } {
  const shares: T[] = []; const others: T[] = [];
  for (const i of items) (isNonShareListing(i) ? others : shares).push(i);
  return { shares, others };
}
export const NON_SHARE_NOTE = 'این نتیجه سهام نیست (اوراق، صندوق، حق‌تقدم یا اختیار) و صورت مالی کدال ندارد؛ نماد سهام شرکت را جست‌وجو کنید.';
