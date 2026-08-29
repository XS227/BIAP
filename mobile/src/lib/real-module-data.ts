import { fetchKiashaPerformanceSummary, fetchWatchlist, parsePct } from '@/lib/api';
import { fetchMarketSymbols } from '@/lib/market-symbols';
import { getBusinessDataset, summarizeBusinessDataset, type BusinessDataset } from '@/lib/business-data';
import type { DemoMetric } from '@/demo/demo-data';

export type RealModulePayload = { available: boolean; sourceLabel: string; summary: string; metrics: DemoMetric[]; bullets: string[]; note?: string };
type ModuleInputs = Awaited<ReturnType<typeof loadInputs>>;

function fa(n: number, digits = 0) { return n.toLocaleString('fa-IR', { maximumFractionDigits: digits }); }
function fmt(n: number) { return Math.abs(n) >= 1_000_000 ? `${fa(n / 1_000_000, 2)}M` : fa(n, 2); }

async function loadInputs() {
  const [watchlistResult, universeResult, perfResult] = await Promise.allSettled([fetchWatchlist(), fetchMarketSymbols({ limit: 5000 }), fetchKiashaPerformanceSummary()]);
  return { watchlist: watchlistResult.status === 'fulfilled' ? watchlistResult.value : [], universe: universeResult.status === 'fulfilled' ? universeResult.value : [], performance: perfResult.status === 'fulfilled' ? perfResult.value : null };
}
let cache: { at: number; data: ModuleInputs } | null = null;
async function inputs(): Promise<ModuleInputs> { if (cache && Date.now() - cache.at < 30_000) return cache.data; const data = await loadInputs(); cache = { at: Date.now(), data }; return data; }

const TITLES: Record<string, string> = {
  eda:'EDA', sql:'SQL / Data Query', anomaly:'Anomaly', forecast:'Forecast', 'kpi-extract':'KPI', dashboard:'Dashboard', governance:'Governance', report:'Report', swot:'SWOT', journey:'Journey', crm:'CRM / Pipeline', campaign:'Campaign', pricing:'Pricing', plan:'Business Plan', 'financial-model':'Financial Model', scenario:'Scenario', unit:'Unit Economics', mbr:'MBR'
};

function datasetPayload(key: string, dataset: BusinessDataset): RealModulePayload {
  const s = summarizeBusinessDataset(dataset);
  const first = s.numeric[0];
  const second = s.numeric[1];
  const baseMetrics: DemoMetric[] = [
    { label:'ردیف واقعی', value:fa(s.rows) },
    { label:'ستون', value:fa(s.columns) },
    { label:'کامل بودن', value:`${fa(s.completeness * 100, 1)}٪`, tone:s.completeness >= 0.9 ? 'positive' : 'negative' },
  ];
  const numericBullets = s.numeric.slice(0, 3).map((x) => `${x.column}: میانگین ${fmt(x.avg)} • بازه ${fmt(x.min)} تا ${fmt(x.max)}`);
  const common = [`منبع: ${dataset.name} — واردشده ${new Date(dataset.importedAt).toLocaleDateString('fa-IR')}.`, `${fa(s.numericColumns.length)} ستون عددی قابل محاسبه شناسایی شد.`, s.missing ? `${fa(s.missing)} مقدار خالی در داده وجود دارد.` : 'مقدار خالی در داده ثبت نشده است.'];

  if (key === 'anomaly') {
    const spreads = s.numeric.map((x) => ({ ...x, spread: x.max - x.min })).sort((a,b) => b.spread - a.spread);
    return { available:true, sourceLabel:'Company Dataset • LIVE', summary:'پایش ساختاری داده واقعی شرکت برای دامنه‌های عددی بزرگ و کیفیت داده. این مرحله بدون ساختن هشدار جعلی انجام می‌شود.', metrics:[...baseMetrics.slice(0,2), { label:'بیشترین دامنه', value:spreads[0] ? fmt(spreads[0].spread) : '—' }], bullets:spreads.slice(0,3).map(x => `${x.column}: دامنه ${fmt(x.spread)}`), note:'برای تشخیص آماری زمانی، ستون تاریخ/زمان و تاریخچه کافی لازم است.' };
  }
  if (key === 'forecast') {
    let trend: number | null = null;
    if (first) {
      const vals = dataset.rows.map(r => Number(String(r[first.column] ?? '').replace(/,/g,''))).filter(Number.isFinite);
      const mid = Math.floor(vals.length / 2);
      if (mid > 0) { const a = vals.slice(0,mid).reduce((x,y)=>x+y,0)/mid; const bvals=vals.slice(mid); const b=bvals.reduce((x,y)=>x+y,0)/Math.max(1,bvals.length); trend = a !== 0 ? (b-a)/Math.abs(a) : null; }
    }
    return { available:true, sourceLabel:'Company Dataset • LIVE', summary:'Forecast به داده واقعی شرکت متصل است. فعلاً روند مشاهده‌شده را گزارش می‌کند و بدون سری زمانی معتبر عدد آینده اختراع نمی‌کند.', metrics:[...baseMetrics.slice(0,2), { label:'روند مشاهده‌شده', value:trend === null ? '—' : `${trend>=0?'+':''}${fa(trend*100,1)}٪`, tone:trend === null ? 'neutral' : trend>=0 ? 'positive':'negative' }], bullets:[...numericBullets.slice(0,2), 'برای پیش‌بینی آینده باید ستون زمانی و تعداد مشاهده کافی وجود داشته باشد.'] };
  }
  if (key === 'sql') return { available:true, sourceLabel:'Company Dataset • LIVE', summary:'داده شرکت به موتور تحلیل محلی متصل است و ساختار جدول برای Query/فیلتر آماده است.', metrics:baseMetrics, bullets:[`ستون‌ها: ${dataset.columns.slice(0,8).join('، ')}${dataset.columns.length>8?'…':''}`, ...numericBullets.slice(0,2)], note:'اتصال SQL Server/Postgres/MySQL خارجی هنوز به credential سازمان و کانکتور read-only سمت سرور نیاز دارد.' };
  if (key === 'financial-model' || key === 'scenario' || key === 'unit' || key === 'pricing') {
    return { available:true, sourceLabel:'Company Dataset • LIVE', summary:`${TITLES[key]} به داده واقعی شرکت متصل است. BIAP فقط شاخص‌هایی را محاسبه می‌کند که از ستون‌های موجود قابل استخراج باشند.`, metrics:[...baseMetrics.slice(0,2), { label:first?.column ?? 'شاخص عددی', value:first ? fmt(first.avg) : '—' }], bullets:[...numericBullets, second ? `ستون دوم قابل تحلیل: ${second.column}` : 'برای مدل دقیق‌تر ستون‌های مالی/فروش بیشتری وارد کنید.'], note:'نام‌گذاری درست ستون‌های revenue/cost/customer/date دقت مدل را بیشتر می‌کند.' };
  }
  if (key === 'crm' || key === 'journey' || key === 'campaign' || key === 'swot' || key === 'plan') {
    return { available:true, sourceLabel:'Company Dataset • LIVE', summary:`${TITLES[key]} اکنون ورودی واقعی شرکت را می‌خواند. نتیجه فقط بر اساس فیلدهای موجود ساخته می‌شود؛ ادعای کسب‌وکاری بدون داده ایجاد نمی‌شود.`, metrics:baseMetrics, bullets:[...common.slice(1), `فیلدهای ورودی: ${dataset.columns.slice(0,6).join('، ')}${dataset.columns.length>6?'…':''}`], note:'برای insight تخصصی این ماژول، ستون‌های مرتبط با مشتری/فروش/کانال/رقیب را وارد کنید.' };
  }
  return { available:true, sourceLabel:'Company Dataset • LIVE', summary:`${TITLES[key] ?? 'تحلیل'} روی داده واقعی متصل شرکت اجرا می‌شود.`, metrics:baseMetrics, bullets:[...common, ...numericBullets.slice(0,2)] };
}

function marketMetrics(data: ModuleInputs): RealModulePayload {
  const priced = data.watchlist.filter((x) => Number.isFinite(x.closingPrice ?? x.lastPrice)); const pcts = priced.map((x) => parsePct(x.changePercent)); const avg = pcts.length ? pcts.reduce((a,b)=>a+b,0)/pcts.length : 0; const positive=pcts.filter(x=>x>0).length;
  return { available:data.universe.length>0 || priced.length>0, sourceLabel:'BIAP Market + FIN', summary:'نمای واقعی از داده‌های متصل BIAP؛ مقدار ناموجود با عدد نمونه پر نمی‌شود.', metrics:[{label:'نمادهای بازار',value:fa(data.universe.length)},{label:'قیمت معتبر',value:fa(priced.length)},{label:'میانگین تغییر',value:`${avg>=0?'+':''}${fa(avg,2)}٪`,tone:avg>=0?'positive':'negative'}], bullets:[`${fa(positive)} نماد از داده قیمت متصل مثبت هستند.`,`فهرست بازار شامل ${fa(data.universe.length)} رکورد است.`,'مقادیر ناموجود عمداً خالی می‌مانند.'] };
}
function performanceMetrics(data: ModuleInputs): RealModulePayload {
  const p=data.performance; if(!p) return {available:false,sourceLabel:'Kiasha Performance',summary:'',metrics:[],bullets:[]}; const ready=p.agents.filter(a=>a.trustReady).length; const maxEvaluated=p.agents.reduce((m,a)=>Math.max(m,a.evaluatedCalls),0); const withAccuracy=p.agents.filter(a=>a.directionalAccuracy!==null); const avgAcc=withAccuracy.length?withAccuracy.reduce((s,a)=>s+(a.directionalAccuracy??0),0)/withAccuracy.length:null;
  return {available:true,sourceLabel:'Kiasha Observed Performance',summary:'خلاصه واقعی عملکرد ثبت‌شده عامل‌های Kiasha.',metrics:[{label:'عامل آماده وزن واقعی',value:fa(ready)},{label:'بیشترین ارزیابی',value:fa(maxEvaluated)},{label:'میانگین دقت',value:avgAcc===null?'—':`${fa(avgAcc*100,1)}٪`}],bullets:p.agents.map(a=>`${a.agent}: ${fa(a.evaluatedCalls)} ارزیابی`)};
}

export async function fetchRealModuleData(key: string): Promise<RealModulePayload> {
  const company = await getBusinessDataset();
  if (company && company.rows.length) return datasetPayload(key, company);
  const data = await inputs();
  if (key === 'eda' || key === 'dashboard' || key === 'kpi-extract' || key === 'report') return marketMetrics(data);
  if (key === 'governance' || key === 'mbr') return performanceMetrics(data);
  if (key === 'anomaly') return marketMetrics(data);
  if (key === 'forecast') { const perf=performanceMetrics(data); return {...perf, summary:perf.available?'داده واقعی عملکرد متصل است، اما بدون تاریخچه معتبر عدد آینده ساخته نمی‌شود.':'', note:'برای Forecast عدد آینده، تاریخچه معتبر لازم است.'}; }
  return { available:false, sourceLabel:'ورودی واقعی لازم است', summary:'', metrics:[], bullets:[], note:'از «اتصال داده» CSV/JSON واقعی شرکت را وارد کنید. SQL/CRM/API خارجی نیز بعد از ارائه مشخصات منبع از کانکتور امن سمت سرور فعال می‌شوند.' };
}
