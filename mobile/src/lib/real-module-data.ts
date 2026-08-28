import { fetchKiashaPerformanceSummary, fetchWatchlist, parsePct } from '@/lib/api';
import { fetchMarketSymbols } from '@/lib/market-symbols';
import type { DemoMetric } from '@/demo/demo-data';

export type RealModulePayload = {
  available: boolean;
  sourceLabel: string;
  summary: string;
  metrics: DemoMetric[];
  bullets: string[];
  note?: string;
};

type ModuleInputs = Awaited<ReturnType<typeof loadInputs>>;

function fa(n: number, digits = 0) {
  return n.toLocaleString('fa-IR', { maximumFractionDigits: digits });
}

async function loadInputs() {
  const [watchlistResult, universeResult, perfResult] = await Promise.allSettled([
    fetchWatchlist(),
    fetchMarketSymbols({ limit: 5000 }),
    fetchKiashaPerformanceSummary(),
  ]);
  return {
    watchlist: watchlistResult.status === 'fulfilled' ? watchlistResult.value : [],
    universe: universeResult.status === 'fulfilled' ? universeResult.value : [],
    performance: perfResult.status === 'fulfilled' ? perfResult.value : null,
  };
}

let cache: { at: number; data: ModuleInputs } | null = null;
async function inputs(): Promise<ModuleInputs> {
  if (cache && Date.now() - cache.at < 30_000) return cache.data;
  const data = await loadInputs();
  cache = { at: Date.now(), data };
  return data;
}

function marketMetrics(data: ModuleInputs): RealModulePayload {
  const priced = data.watchlist.filter((x) => Number.isFinite(x.closingPrice ?? x.lastPrice));
  const pcts = priced.map((x) => parsePct(x.changePercent));
  const avg = pcts.length ? pcts.reduce((a, b) => a + b, 0) / pcts.length : 0;
  const positive = pcts.filter((x) => x > 0).length;
  return {
    available: data.universe.length > 0 || priced.length > 0,
    sourceLabel: 'BIAP Market + FIN',
    summary: 'نمای واقعی از داده‌های متصل BIAP؛ universe بازار از FIN و قیمت‌های قابل‌دسترس از سرویس بازار حساب خوانده می‌شوند.',
    metrics: [
      { label: 'نمادهای بازار', value: fa(data.universe.length) },
      { label: 'قیمت معتبر', value: fa(priced.length) },
      { label: 'میانگین تغییر', value: `${avg >= 0 ? '+' : ''}${fa(avg, 2)}٪`, tone: avg >= 0 ? 'positive' : 'negative' },
    ],
    bullets: [
      `${fa(positive)} نماد از داده قیمت متصل امروز مثبت هستند.`,
      `فهرست بازار شامل ${fa(data.universe.length)} رکورد قابل جستجو است.`,
      'مقادیر ناموجود عمداً خالی می‌مانند و با عدد نمونه جایگزین نمی‌شوند.',
    ],
  };
}

function anomalyMetrics(data: ModuleInputs): RealModulePayload {
  const rows = data.watchlist.filter((x) => Number.isFinite(Number(x.changePercent)));
  const flagged = rows.filter((x) => Math.abs(parsePct(x.changePercent)) >= 3);
  const max = rows.length ? Math.max(...rows.map((x) => Math.abs(parsePct(x.changePercent)))) : 0;
  return {
    available: rows.length > 0,
    sourceLabel: 'BIAP Market',
    summary: 'پایش واقعی تغییرات روزانه روی قیمت‌های متصل. فعلاً آستانه ساده ±۳٪ برای علامت‌گذاری ناهنجاری استفاده می‌شود؛ مدل آماری مستقل هنوز به feed تاریخی سرور نیاز دارد.',
    metrics: [
      { label: 'ردیف‌های پایش‌شده', value: fa(rows.length) },
      { label: 'هشدار ±۳٪', value: fa(flagged.length), tone: flagged.length ? 'negative' : 'positive' },
      { label: 'بیشترین حرکت', value: `${fa(max, 2)}٪` },
    ],
    bullets: flagged.length
      ? flagged.slice(0, 3).map((x) => `${x.name}: ${parsePct(x.changePercent) >= 0 ? '+' : ''}${fa(parsePct(x.changePercent), 2)}٪`)
      : ['در داده فعلی حرکت بزرگ‌تر از ±۳٪ ثبت نشده است.'],
  };
}

function performanceMetrics(data: ModuleInputs): RealModulePayload {
  const p = data.performance;
  if (!p) return { available: false, sourceLabel: 'Kiasha Performance', summary: '', metrics: [], bullets: [] };
  const ready = p.agents.filter((a) => a.trustReady).length;
  const evaluated = p.agents.reduce((m, a) => Math.max(m, a.evaluatedCalls), 0);
  const withAccuracy = p.agents.filter((a) => a.directionalAccuracy !== null);
  const avgAcc = withAccuracy.length
    ? withAccuracy.reduce((s, a) => s + (a.directionalAccuracy ?? 0), 0) / withAccuracy.length
    : null;
  return {
    available: true,
    sourceLabel: 'Kiasha Observed Performance',
    summary: 'خلاصه واقعی عملکرد ثبت‌شده عامل‌های Kiasha. وزن مشاهده‌شده فقط بعد از عبور هر عامل از حداقل نمونه فعال می‌شود.',
    metrics: [
      { label: 'عامل آماده وزن واقعی', value: fa(ready) },
      { label: 'حداقل ارزیابی ثبت‌شده', value: fa(evaluated) },
      { label: 'میانگین دقت ثبت‌شده', value: avgAcc === null ? '—' : `${fa(avgAcc * 100, 1)}٪` },
    ],
    bullets: p.agents.map((a) => `${a.agent}: ${fa(a.evaluatedCalls)} ارزیابی${a.directionalAccuracy === null ? '' : `، دقت ${fa(a.directionalAccuracy * 100, 1)}٪`}`),
  };
}

export async function fetchRealModuleData(key: string): Promise<RealModulePayload> {
  const data = await inputs();
  if (key === 'eda' || key === 'dashboard' || key === 'kpi-extract' || key === 'report') return marketMetrics(data);
  if (key === 'anomaly') return anomalyMetrics(data);
  if (key === 'governance' || key === 'mbr') return performanceMetrics(data);
  if (key === 'forecast') {
    const perf = performanceMetrics(data);
    return {
      ...perf,
      summary: perf.available
        ? 'داده واقعی عملکرد عامل پیش‌بینی متصل است، اما پیش‌بینی قیمت آینده بدون تاریخچه معتبر ساخته نمی‌شود.'
        : '',
      note: 'برای Forecast عدد آینده، feed تاریخچه قیمت سمت سرور لازم است.',
    };
  }
  return {
    available: false,
    sourceLabel: 'ورودی واقعی لازم است',
    summary: '',
    metrics: [],
    bullets: [],
    note: 'این ماژول برای خروجی واقعی به داده اختصاصی کسب‌وکار/CRM/SQL/مالی کاربر نیاز دارد و BIAP فعلاً چنین ورودی‌ای برای این حساب دریافت نکرده است.',
  };
}
