import AsyncStorage from '@react-native-async-storage/async-storage';
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

const VERIFIED_DISCOVERY_SEEDS = [
  'فولاد', 'فملی', 'فخوز', 'ذوب', 'کگل', 'کچاد', 'شستا', 'فارس',
  'شپنا', 'شبندر', 'شتران', 'نوری', 'بوعلی', 'پارسان', 'تاپیکو', 'وغدیر',
  'وبملت', 'وتجارت', 'وبصادر', 'وپاسار', 'خودرو', 'خساپا', 'خگستر', 'خزامیا',
  'حکشتی', 'رمپنا', 'اخابر', 'همراه', 'مبین', 'جم', 'زاگرس', 'مارون',
  'شپدیس', 'کرماشا', 'شیراز', 'خراسان', 'دماوند', 'بترانس',
] as const;

const TARGET_PICK_COUNT = 10;
const CACHE_TTL_MS = 15 * 60_000;
const RECOMMENDATION_CACHE_TTL_MS = 15 * 60_000;
const RECOMMENDATION_TIMEOUT_MS = 55_000;
const SCAN_WAVE_SIZE = 6;
const cache = new Map<InvestmentHorizon, { at: number; value: KiashaPicksResult }>();
const recommendationCache = new Map<string, { at: number; value: Recommendation | null }>();
const recommendationInflight = new Map<string, Promise<Recommendation | null>>();
const STORAGE_PREFIX = 'kiasha:picks:v4:';

function storageKey(horizon: InvestmentHorizon): string { return `${STORAGE_PREFIX}${horizon}`; }
function normalizedKey(value: string): string { return value.replace(/ي/g, 'ی').replace(/ك/g, 'ک').replace(/\s+/g, '').trim(); }

function sameTehranDay(iso: string): boolean {
  try {
    const formatter = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Tehran', year: 'numeric', month: '2-digit', day: '2-digit' });
    return formatter.format(new Date(iso)) === formatter.format(new Date());
  } catch {
    return Date.now() - new Date(iso).getTime() < 12 * 60 * 60_000;
  }
}

async function readPersisted(horizon: InvestmentHorizon): Promise<KiashaPicksResult | null> {
  try {
    const raw = await AsyncStorage.getItem(storageKey(horizon));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as KiashaPicksResult;
    if (!parsed || parsed.horizon !== horizon || !Array.isArray(parsed.picks) || !sameTehranDay(parsed.generatedAt)) return null;
    return parsed;
  } catch { return null; }
}

async function writePersisted(result: KiashaPicksResult): Promise<void> {
  try { await AsyncStorage.setItem(storageKey(result.horizon), JSON.stringify(result)); } catch { /* best effort */ }
}

async function fetchCachedRecommendation(code: string, force = false): Promise<Recommendation | null> {
  const key = normalizedKey(code);
  const cached = recommendationCache.get(key);
  if (!force && cached && Date.now() - cached.at < RECOMMENDATION_CACHE_TTL_MS) return cached.value;
  const inflight = recommendationInflight.get(key);
  if (!force && inflight) return inflight;
  const request = fetchRecommendation(code, RECOMMENDATION_TIMEOUT_MS)
    .then((value) => { recommendationCache.set(key, { at: Date.now(), value }); return value; })
    .finally(() => recommendationInflight.delete(key));
  recommendationInflight.set(key, request);
  return request;
}

function uniqCandidates(items: MarketSymbolResult[]): MarketSymbolResult[] {
  const seen = new Set<string>();
  const out: MarketSymbolResult[] = [];
  for (const item of items) {
    const key = normalizedKey(item.symbol || item.code);
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
function contribution(rec: Recommendation, agent: string): number {
  const item = entry(rec, agent);
  return (item?.vote ?? 0) * (item?.confidence ?? 0);
}

function rank(rec: Recommendation, horizon: InvestmentHorizon): number {
  const weighted = Number.isFinite(rec.score) ? rec.score : 0;
  if (horizon === 'short') {
    return weighted * 0.34
      + contribution(rec, 'forecast') * 0.18
      + contribution(rec, 'risk') * 0.14
      + contribution(rec, 'technical') * 0.20
      + contribution(rec, 'flow') * 0.14;
  }
  return weighted * 0.34
    + contribution(rec, 'fundamental') * 0.32
    + contribution(rec, 'comparison') * 0.18
    + contribution(rec, 'technical') * 0.10
    + contribution(rec, 'flow') * 0.06;
}

function isVerifiedForHorizon(rec: Recommendation, horizon: InvestmentHorizon): boolean {
  if (rec.dataSource === 'mock') return false;
  if (horizon === 'short') {
    // A verified live quote is enough to enter the short-horizon candidate pool.
    // Individual agents stay neutral when their own extended inputs are absent,
    // instead of excluding an otherwise real symbol from Kiasha entirely.
    return rec.dataSource === 'live'
      && Boolean(rec.livePrice?.lastPrice || rec.livePrice?.closingPrice);
  }
  return rec.dataSource === 'live' || (rec.dataSource === 'codal' && Boolean(rec.codalFundamentals));
}

function rationale(rec: Recommendation, horizon: InvestmentHorizon): string {
  const names = horizon === 'short'
    ? ['technical', 'flow', 'forecast', 'risk']
    : ['fundamental', 'comparison', 'technical', 'flow'];
  return names.map((name) => entry(rec, name)).filter(Boolean).map((x) => x!.reasoning).filter(Boolean).slice(0, 2).join(' • ')
    || 'رتبه‌بندی فقط از داده‌های واقعی قابل‌دسترسی کیا‌شا انجام شده است.';
}

function toPick(candidate: MarketSymbolResult, rec: Recommendation, horizon: InvestmentHorizon): KiashaPick {
  const price = rec.livePrice?.lastPrice ?? rec.livePrice?.closingPrice ?? null;
  return {
    symbol: candidate.symbol || rec.code,
    name: rec.name && rec.name !== rec.code ? rec.name : (candidate.name || candidate.symbol),
    code: rec.code || candidate.code,
    horizon,
    score: rank(rec, horizon),
    source: rec.dataSource === 'live' ? 'live' : 'codal',
    price,
    changePercent: rec.livePrice?.changePercent ?? null,
    rationale: rationale(rec, horizon),
    recommendation: rec,
  };
}

export async function fetchKiashaTopPicks(
  horizon: InvestmentHorizon,
  options: { force?: boolean; scanLimit?: number } = {}
): Promise<KiashaPicksResult> {
  const cached = cache.get(horizon);
  if (!options.force && cached && Date.now() - cached.at < CACHE_TTL_MS) return cached.value;

  if (!options.force) {
    const persisted = await readPersisted(horizon);
    if (persisted) {
      cache.set(horizon, { at: Date.now(), value: persisted });
      return persisted;
    }
  }

  const [watchlist, universe] = await Promise.all([
    fetchWatchlist(4_000).catch(() => []),
    fetchMarketSymbols({ limit: 1800 }).catch(() => []),
  ]);

  const seedCandidates: MarketSymbolResult[] = VERIFIED_DISCOVERY_SEEDS.map((symbol) => ({ code: symbol, symbol, name: symbol, market: null }));
  const watchCandidates: MarketSymbolResult[] = watchlist.map((x) => ({ code: x.code, symbol: x.name || x.code, name: x.name || x.code, market: null }));
  const dynamicCandidates = prioritizeCandidates(uniqCandidates(universe));
  const scanLimit = Math.max(48, Math.min(options.scanLimit ?? 72, 120));
  const candidates = uniqCandidates([...seedCandidates, ...watchCandidates, ...dynamicCandidates]).slice(0, scanLimit);

  const verified: Array<{ candidate: MarketSymbolResult; rec: Recommendation }> = [];
  let scanned = 0;

  for (let i = 0; i < candidates.length; i += SCAN_WAVE_SIZE) {
    const chunk = candidates.slice(i, i + SCAN_WAVE_SIZE);
    const batch = await Promise.all(chunk.map(async (candidate) => {
      const rec = await fetchCachedRecommendation(candidate.symbol || candidate.code, Boolean(options.force));
      return rec ? { candidate, rec } : null;
    }));
    scanned += chunk.length;
    for (const item of batch) {
      if (item && isVerifiedForHorizon(item.rec, horizon)) verified.push(item);
    }
    const validBuyCount = verified.reduce((count, item) => {
      const pick = toPick(item.candidate, item.rec, horizon);
      return count + (pick.recommendation.call === 'BUY' && pick.score > 0 ? 1 : 0);
    }, 0);
    if (validBuyCount >= TARGET_PICK_COUNT) break;
  }

  const ranked = verified
    .map(({ candidate, rec }) => toPick(candidate, rec, horizon))
    .filter((x) => x.recommendation.call === 'BUY' && x.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, TARGET_PICK_COUNT);

  const result: KiashaPicksResult = { horizon, picks: ranked, scanned, verified: verified.length, generatedAt: new Date().toISOString() };
  cache.set(horizon, { at: Date.now(), value: result });
  await writePersisted(result);
  return result;
}
