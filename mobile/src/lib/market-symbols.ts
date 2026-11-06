import { normalizeSearch } from '@/lib/data-status';
import { KIASHA_API_BASE, MarketSymbolResult } from '@/lib/api';

const ORDINARY_SHARE_PAPER_TYPES = new Set(['300', '303', '307', '309', '313']);
type ClassifiedMarketSymbol = MarketSymbolResult & { paper_type?: string | null; source?: string | null };

function normalize(value: string | null | undefined): string {
  return String(value || '').trim().replace(/ي/g, 'ی').replace(/ك/g, 'ک').toLowerCase();
}

export function isVerifiedEquitySymbol(item: MarketSymbolResult): boolean {
  const classified = item as ClassifiedMarketSymbol;
  const source = normalize(classified.source);
  const paperType = String(classified.paper_type || '').trim();
  if (source === 'codal') return true;
  return ORDINARY_SHARE_PAPER_TYPES.has(paperType);
}

/** Persian instrument type from the TSETMC paper type (and name hints). Ordinary shares are what BIAP analyses. */
export function instrumentTypeFa(item: { paper_type?: string | null; name?: string | null; symbol?: string | null }): string {
  const t = String(item.paper_type ?? '').trim();
  const name = normalize(item.name);
  if (ORDINARY_SHARE_PAPER_TYPES.has(t)) return 'سهام';
  if (t === '301' || /حق\s*تقدم/.test(name)) return 'حق‌تقدم';
  if (t === '305' || /^صندوق/.test(name)) return 'صندوق';
  if (t === '306' || /^(اجاره|مرابحه|صکوک|اسناد)/.test(name)) return 'اوراق (اجاره/مرابحه)';
  if (/اختیار/.test(name)) return 'اختیار معامله';
  return 'ابزار دیگر';
}
export function isOrdinaryShare(item: { paper_type?: string | null }): boolean { return ORDINARY_SHARE_PAPER_TYPES.has(String(item.paper_type ?? '').trim()); }

export function rankMarketSymbols(items: MarketSymbolResult[], query?: string): MarketSymbolResult[] {
  const q = normalize(query);
  const shareFirst = (item: MarketSymbolResult): number => (isOrdinaryShare(item as ClassifiedMarketSymbol) ? 0 : 10);
  if (!q) return items;
  const rank = (item: MarketSymbolResult): number => {
    const symbol = normalize(item.symbol);
    const name = normalize(item.name);
    const code = normalize(item.code);
    if (symbol === q) return 0;
    if (name === q || code === q) return 1;
    if (symbol.startsWith(q)) return 2;
    if (name.startsWith(q)) return 3;
    return 4;
  };
  return [...items].sort((a, b) => {
    // The main stock always outranks bonds, funds, rights and options with a similar symbol («تابان» before «تابان25»).
    const diff = shareFirst(a) + rank(a) - (shareFirst(b) + rank(b));
    if (diff !== 0) return diff;
    return normalize(a.symbol).localeCompare(normalize(b.symbol), 'fa');
  });
}

export async function fetchMarketSymbols(
  params: { q?: string; market?: 'TSE' | 'IFB' | 'IFB_BASE'; limit?: number },
  timeoutMs = 12_000
): Promise<MarketSymbolResult[]> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const query = new URLSearchParams();
    if (params.q) query.set('q', normalizeSearch(params.q));
    if (params.market) query.set('market', params.market);
    if (params.limit) query.set('limit', String(params.limit));

    const res = await fetch(`${KIASHA_API_BASE}/stock/symbols?${query.toString()}`, {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) return [];
    const json = await res.json();
    const raw = Array.isArray(json?.items) ? (json.items as MarketSymbolResult[]) : [];
    return rankMarketSymbols(raw.filter(isVerifiedEquitySymbol), params.q);
  } catch {
    return [];
  } finally {
    clearTimeout(timer);
  }
}
