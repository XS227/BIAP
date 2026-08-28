import { fetchRecommendation, fetchWatchlist, MarketSymbolResult, Recommendation } from '@/lib/api';
import { fetchMarketSymbols } from '@/lib/market-symbols';

export type InvestmentHorizon = 'short' | 'long';

export type KiashaPick = {
  symbol: string;
  name: string;
  code: string;
  horizon: InvestmentHorizon;
  score: number;
  source: 'live' | 'codal';
  price: number | null;
  changePercent: number | null;
  rationale: string;
  recommendation: Recommendation;
};

export type KiashaPicksResult = {
  horizon: InvestmentHorizon;
  picks: KiashaPick[];
  scanned: number;
  verified: number;
  generatedAt: string;
};

// These are discovery seeds only: real Iranian ticker labels, never prices,
// scores or recommendations. Each one must still resolve through BIAP and pass
// the same live/CODAL verification below before it can appear as a pick. This
// keeps discovery useful when the VPS can only obtain CODAL's issuer directory.
const VERIFIED_DISCOVERY_SEEDS = [
  'فولاد', 'فملی', 'فخوز', 'ذوب', 'کگل', 'کچاد', 'شستا', 'فارس',
  'شپنا', 'شبندر', 'شتران', 'نوری', 'بوعلی', 'پارسان', 'تاپیکو', 'وغدیر',
  'وبملت', 'وتجارت', 'وبصادر', 'وپاسار', 'خودرو', 'خساپا', 'خگستر', 'خزامیا',
  'حکشتی', 'رمپنا', 'اخابر', 'همراه', 'مبین', 'جم', 'زاگرس', 'مارون',
  'شپدیس', 'کرماشا', 'شیراز', 'خراسان', 'دماوند', 'بترانس',
] as const;

const CACHE_TTL_MS = 15 * 60_000;
const cache = new Map<InvestmentHorizon, { at: number; value: KiashaPicksResult }>();

function uniqCandidates(items: MarketSymbolResult[]): MarketSymbolResult[] {
  const seen = new Set<string>();
  const out: MarketSymbolResult[] = [];
  for (const item of items) {
    const key = (item.symbol || item.code).trim();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}

function tickerPriority(item: MarketSymbolResult): number {
  const value = (item.symbol || item.code || '').trim().replace(/\s+/g, ' ');
  if (!value) return -100;
  const spaces = (value.match(/ /g) || []).length;
  const hasPersian = /[\u0600-\u06FF]/.test(value);
  const hasLatin = /[A-Za-z]/.test(value);
  let score = 0;
  if (spaces === 0) score += 8;
  else if (spaces === 1) score += 3;
  else score -= spaces * 3;
  if (value.length <= 8) score += 6;
  else if (value.length <= 12) score += 3;
  else if (value.length > 18) score -= 8;
  if (hasPersian) score += 3;
  if (hasLatin) score -= 2;
  if (item.market) score += 10;
  return score;
}

function prioritizeCandidates(items: MarketSymbolResult[]): MarketSymbolResult[] {
  return [...items].sort((a, b) => tickerPriority(b) - tickerPriority(a));
}

function entry(rec: Recommendation, agent: string) { return rec.breakdown.find((x) => x.agent === agent); }

function rank(rec: Recommendation, horizon: InvestmentHorizon): number {
  const fundamental = entry(rec, 'fundamental');
  const risk = entry(rec, 'risk');
  const forecast = entry(rec, 'forecast');
  const comparison = entry(rec, 'comparison');
  const weighted = Number.isFinite(rec.score) ? rec.score : 0;
  return horizon === 'short'
    ? weighted * 0.42 + (forecast?.vote ?? 0) * (forecast?.confidence ?? 0) * 0.38 + (risk?.vote ?? 0) * (risk?.confidence ?? 0) * 0.20
    : weighted * 0.36 + (fundamental?.vote ?? 0) * (fundamental?.confidence ?? 0) * 0.44 + (comparison?.vote ?? 0) * (comparison?.confidence ?? 0) * 0.20;
}

function isVerifiedForHorizon(rec: Recommendation, horizon: InvestmentHorizon): boolean {
  if (rec.dataSource === 'mock') return false;
  if (horizon === 'short') {
    return rec.dataSource === 'live'
      && Boolean(rec.livePrice?.lastPrice || rec.livePrice?.closingPrice)
      && rec.dataAvailability.market_extended;
  }
  return rec.dataSource === 'live' || (rec.dataSource === 'codal' && Boolean(rec.codalFundamentals));
}

function rationale(rec: Recommendation, horizon: InvestmentHorizon): string {
  const names = horizon === 'short' ? ['forecast', 'risk'] : ['fundamental', 'comparison'];
  return names.map((name) => entry(rec, name)).filter(Boolean).map((x) => x!.reasoning).filter(Boolean).slice(0, 2).join(' • ')
    || 'رتبه‌بندی فقط از داده‌های واقعی قابل‌دسترسی کیا‌شا انجام شده است.';
}

export async function fetchKiashaTopPicks(
  horizon: InvestmentHorizon,
  options: { force?: boolean; scanLimit?: number } = {}
): Promise<KiashaPicksResult> {
  const cached = cache.get(horizon);
  if (!options.force && cached && Date.now() - cached.at < CACHE_TTL_MS) return cached.value;

  const [watchlist, universe] = await Promise.all([
    fetchWatchlist(4_000).catch(() => []),
    fetchMarketSymbols({ limit: 1200 }).catch(() => []),
  ]);

  const seedCandidates: MarketSymbolResult[] = VERIFIED_DISCOVERY_SEEDS.map((symbol) => ({
    code: symbol,
    symbol,
    name: symbol,
    market: null,
  }));
  const watchCandidates: MarketSymbolResult[] = watchlist.map((x) => ({ code: x.code, symbol: x.name || x.code, name: x.name || x.code, market: null }));
  const dynamicCandidates = prioritizeCandidates(uniqCandidates(universe));
  const scanLimit = Math.max(48, Math.min(options.scanLimit ?? 64, 96));
  const candidates = uniqCandidates([...seedCandidates, ...watchCandidates, ...dynamicCandidates]).slice(0, scanLimit);

  const recs: Array<{ candidate: MarketSymbolResult; rec: Recommendation } | null> = [];
  for (let i = 0; i < candidates.length; i += 8) {
    const chunk = candidates.slice(i, i + 8);
    const batch = await Promise.all(chunk.map(async (candidate) => {
      const rec = await fetchRecommendation(candidate.symbol || candidate.code, 6_000);
      return rec ? { candidate, rec } : null;
    }));
    recs.push(...batch);
  }

  const verified = recs.filter((x): x is NonNullable<typeof x> => Boolean(x) && isVerifiedForHorizon(x!.rec, horizon));
  const ranked = verified.map(({ candidate, rec }) => {
    const price = rec.livePrice?.lastPrice ?? rec.livePrice?.closingPrice ?? null;
    return {
      symbol: candidate.symbol || rec.code,
      name: rec.name && rec.name !== rec.code ? rec.name : (candidate.name || candidate.symbol),
      code: rec.code || candidate.code,
      horizon,
      score: rank(rec, horizon),
      source: rec.dataSource === 'live' ? 'live' as const : 'codal' as const,
      price,
      changePercent: rec.livePrice?.changePercent ?? null,
      rationale: rationale(rec, horizon),
      recommendation: rec,
    };
  }).filter((x) => x.recommendation.call === 'BUY' && x.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 3);

  const result: KiashaPicksResult = { horizon, picks: ranked, scanned: candidates.length, verified: verified.length, generatedAt: new Date().toISOString() };
  cache.set(horizon, { at: Date.now(), value: result });
  return result;
}
