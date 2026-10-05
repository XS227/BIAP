import AsyncStorage from '@react-native-async-storage/async-storage';
import { Recommendation, type MarketSymbolResult } from '@/lib/api';
import { fetchKiashaMarketScan, KiashaMarketScanItem } from '@/lib/kiasha-market-scan';
import { fetchTsetmcQuote } from '@/lib/market-quote';

export type InvestmentHorizon = 'short' | 'long';

export type KiashaPick = {
  symbol: string;
  name: string;
  code: string;
  horizon: InvestmentHorizon;
  score: number;
  rank: number;
  activeAgents: number;
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
  eligible: number;
  verified: number;
  generatedAt: string;
  error?: string;
  httpStatus?: number;
};

const CACHE_TTL_MS = 15 * 60_000;
const cache = new Map<InvestmentHorizon, { at: number; value: KiashaPicksResult }>();
const STORAGE_PREFIX = 'kiasha:picks:v6:';

function storageKey(horizon: InvestmentHorizon): string { return `${STORAGE_PREFIX}${horizon}`; }

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

function countActiveAgents(row: KiashaMarketScanItem): number {
  const breakdown = Array.isArray(row.agentBreakdown) ? row.agentBreakdown : [];
  return breakdown.filter((entry) => entry.agent !== 'scenario' && Number(entry.confidence || 0) > 0).length;
}

function pickFromScan(row: KiashaMarketScanItem, horizon: InvestmentHorizon, rank: number): KiashaPick {
  const breakdown = Array.isArray(row.agentBreakdown) ? row.agentBreakdown : [];
  const recommendation: Recommendation = {
    code: row.code,
    name: row.name,
    call: row.kiashaCall,
    score: Number(row.kiashaScore || 0),
    generatedAt: new Date().toISOString(),
    dataSource: 'live',
    dataAvailability: {
      codal: Boolean(row.dataAvailability?.codal),
      codal_metadata: Boolean(row.dataAvailability?.codal_metadata),
      market_extended: Boolean(row.dataAvailability?.market_extended),
    },
    codalMetadata: null,
    codalFundamentals: null,
    livePrice: { lastPrice: null, closingPrice: null, yesterdayPrice: null, changePercent: row.changePercent ?? null },
    breakdown,
  };
  return {
    symbol: row.symbol,
    name: row.name,
    code: row.code,
    horizon,
    score: Number(row.kiashaScore || 0),
    rank,
    activeAgents: countActiveAgents(row),
    source: 'live',
    price: null,
    changePercent: row.changePercent ?? null,
    rationale: row.explanation || 'رتبه‌بندی از اسکن واحد و تأییدشدهٔ کیا‌شا در سرور ساخته شده است.',
    recommendation,
  };
}

async function enrichPickPrice(pick: KiashaPick): Promise<KiashaPick> {
  const symbol: MarketSymbolResult = { code: pick.code, symbol: pick.symbol, name: pick.name };
  const quote = await fetchTsetmcQuote(symbol, 6_500, true);
  if (quote.error) return pick;
  const price = quote.lastPrice ?? quote.closingPrice ?? null;
  const changePercent = Number.isFinite(Number(quote.changePercent)) ? Number(quote.changePercent) : pick.changePercent;
  return {
    ...pick,
    price,
    changePercent,
    recommendation: {
      ...pick.recommendation,
      livePrice: {
        lastPrice: quote.lastPrice ?? null,
        closingPrice: quote.closingPrice ?? null,
        yesterdayPrice: quote.yesterdayPrice ?? null,
        changePercent,
      },
    },
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

  const scan = await fetchKiashaMarketScan(Boolean(options.force));
  const rows = scan.top10 ?? [];
  const rankedRows = rows
    .filter((x) => x.kiashaCall === 'BUY' && Number(x.kiashaScore) > 0)
    .sort((a, b) => Number(b.kiashaScore || 0) - Number(a.kiashaScore || 0))
    .slice(0, 10);
  const basePicks = rankedRows.map((x, index) => pickFromScan(x, horizon, index + 1));
  const ranked = await Promise.all(basePicks.map(enrichPickPrice));

  const result: KiashaPicksResult = {
    horizon,
    picks: ranked,
    scanned: Number(scan.marketRowsScanned ?? 0),
    eligible: Number(scan.ordinaryEquityCount ?? 0),
    verified: Number(scan.deepAnalyzedCount ?? 0),
    generatedAt: scan.createdAt ?? new Date().toISOString(),
    error: scan.error,
    httpStatus: scan.httpStatus,
  };
  cache.set(horizon, { at: Date.now(), value: result });
  if (!result.error) await writePersisted(result);
  return result;
}
