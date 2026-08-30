import AsyncStorage from '@react-native-async-storage/async-storage';
import { Recommendation } from '@/lib/api';
import { fetchKiashaMarketScan } from '@/lib/kiasha-market-scan';

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

const CACHE_TTL_MS = 15 * 60_000;
const cache = new Map<InvestmentHorizon, { at: number; value: KiashaPicksResult }>();
const STORAGE_PREFIX = 'kiasha:picks:v5:';

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

function pickFromScan(item: Awaited<ReturnType<typeof fetchKiashaMarketScan>> extends infer R ? R extends { top10: (infer I)[] } ? I : never : never, horizon: InvestmentHorizon): KiashaPick {
  const row = item as any;
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
    source: 'live',
    price: null,
    changePercent: row.changePercent ?? null,
    rationale: row.explanation || 'رتبه‌بندی از اسکن واحد و تأییدشدهٔ کیا‌شا در سرور ساخته شده است.',
    recommendation,
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
  const rows = scan?.top10 ?? [];
  const ranked = rows
    .filter((x) => x.kiashaCall === 'BUY' && Number(x.kiashaScore) > 0)
    .map((x) => pickFromScan(x as any, horizon))
    .sort((a, b) => b.score - a.score)
    .slice(0, 10);

  const result: KiashaPicksResult = {
    horizon,
    picks: ranked,
    scanned: Number(scan?.marketRowsScanned ?? 0),
    verified: Number(scan?.deepAnalyzedCount ?? 0),
    generatedAt: scan?.createdAt ?? new Date().toISOString(),
  };
  cache.set(horizon, { at: Date.now(), value: result });
  await writePersisted(result);
  return result;
}
