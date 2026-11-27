// English + Persian labels for the three advisory agent sections and the Track record screen.
// Pure module (no React Native imports) so it can be unit tested with node --experimental-strip-types.
// Agent `reasons[]`, `caveats[]` and `disclaimer` are returned by the API and shown verbatim (English); only UI labels are translated here.

export type Lang = 'en' | 'fa';

export const STR = {
  advisory: { en: 'Research aid. Does not change the recommendation.', fa: 'ابزار پژوهشی. توصیهٔ نهایی را تغییر نمی‌دهد.' },
  reasonsEnglish: { en: '', fa: 'دلایل و توضیحات را موتور تحلیل به انگلیسی برمی‌گرداند و بدون تغییر نمایش داده می‌شود.' },
  riskTitle: { en: 'Risk Agent', fa: 'عامل ریسک' },
  riskExplain: { en: 'Model-based solvency and earnings-quality check. Different from the engine\'s "Risk level" row above.', fa: 'بررسی مبتنی بر مدل برای توان پرداخت بدهی و کیفیت سود. با ردیف «سطح ریسک» موتور در بالا متفاوت است.' },
  performanceTitle: { en: 'Performance Agent', fa: 'عامل عملکرد' },
  trackTitle: { en: 'BIAP\'s record on this stock', fa: 'سابقهٔ BIAP روی این سهم' },
  trackScreenTitle: { en: 'Track record', fa: 'سابقهٔ تصمیم‌ها' },
  trackScreenSub: { en: 'Past decisions measured against the market. Not a forecast.', fa: 'تصمیم‌های گذشته در مقایسه با بازار. پیش‌بینی نیست.' },
  trackCardTitle: { en: 'Track record', fa: 'سابقهٔ تصمیم‌ها' },
  trackCardSub: { en: 'How BUY and SELL decisions performed after one month.', fa: 'عملکرد تصمیم‌های خرید و فروش پس از یک ماه.' },
  absolute: { en: 'Absolute', fa: 'مطلق' },
  vsSector: { en: 'vs sector', fa: 'نسبت به صنعت' },
  vsMarket: { en: 'vs market', fa: 'نسبت به بازار' },
  notEnoughData: { en: 'Not enough data', fa: 'داده کافی نیست' },
  notApplicable: { en: 'Not applicable: financial institution', fa: 'قابل اعمال نیست: نهاد مالی' },
  provisional: { en: 'Provisional', fa: 'موقت' },
  provisionalOhlson: { en: 'Provisional (asset unit awaiting confirmation)', fa: 'موقت (واحد دارایی هنوز تأیید نشده است)' },
  dataBehind: { en: 'Data behind this', fa: 'داده‌های پشت این نتیجه' },
  hide: { en: 'Hide', fa: 'بستن' },
  loading: { en: 'Loading…', fa: 'در حال بارگذاری…' },
  unavailable: { en: 'Temporarily unavailable', fa: 'موقتاً در دسترس نیست' },
  retry: { en: 'Retry', fa: 'تلاش دوباره' },
  needs: { en: 'needs', fa: 'نیاز به' },
  value: { en: 'Value', fa: 'مقدار' },
  band: { en: 'Band', fa: 'محدوده' },
  percentile: { en: 'Percentile', fa: 'صدک' },
  peers: { en: 'peers', fa: 'همتا' },
  scope: { en: 'Scope', fa: 'دامنه' },
  sector: { en: 'Sector', fa: 'صنعت' },
  sectorNote: { en: 'current sector, not point-in-time', fa: 'صنعت فعلی، نه در زمان تصمیم' },
  marketWide: { en: 'market-wide fallback (too few sector peers or sector unknown)', fa: 'مقایسه با کل بازار (همتای صنعتی کم است یا صنعت نامشخص است)' },
  beneishNA: { en: 'not available (needs two years of statements)', fa: 'در دسترس نیست (به صورت‌های مالی دو سال نیاز دارد)' },
  unitScale: { en: 'Statement unit scale', fa: 'مقیاس واحد صورت‌های مالی' },
  leaseNote: { en: 'Debt includes lease liabilities of', fa: 'بدهی شامل بدهی اجاره به مبلغ' },
  dupont: { en: 'DuPont: net margin × asset turnover × equity multiplier', fa: 'دوپونت: حاشیه سود خالص × گردش دارایی × ضریب اهرمی' },
  margins: { en: 'Margins', fa: 'حاشیه‌ها' },
  growth: { en: 'Growth', fa: 'رشد' },
  cashQuality: { en: 'Cash-flow quality', fa: 'کیفیت جریان نقدی' },
  pending: { en: 'Pending', fa: 'در انتظار' },
  due: { en: 'due', fa: 'سررسید' },
  matured: { en: 'Matured', fa: 'رسیده' },
  return: { en: 'Return', fa: 'بازده' },
  benchmark: { en: 'Benchmark', fa: 'شاخص مرجع' },
  excess: { en: 'Excess', fa: 'بازده مازاد' },
  hit: { en: 'Hit', fa: 'موفق' },
  miss: { en: 'Miss', fa: 'ناموفق' },
  decisionDate: { en: 'Decision date', fa: 'تاریخ تصمیم' },
  anecdote: { en: 'One cohort is one observation per stock; per-stock results are anecdotes, not a track record.', fa: 'هر دسته تنها یک مشاهده برای هر سهم است؛ نتیجهٔ تک‌سهم حکایت است، نه سابقهٔ آماری.' },
  frozenCohort: { en: 'frozen v1 cohort', fa: 'دستهٔ ثابت‌شدهٔ v1' },
  returnBasis: { en: 'Stock returns include dividends; benchmarks are price indices.', fa: 'بازده سهم‌ها شامل سود نقدی است؛ شاخص‌های مرجع شاخص قیمتی‌اند.' },
  pastNotForecast: { en: 'Past decisions, not a forecast', fa: 'تصمیم‌های گذشته، نه پیش‌بینی' },
  horizon1m: { en: '1M', fa: '۱ ماه' },
  horizon3m: { en: '3M', fa: '۳ ماه' },
  horizon6m: { en: '6M', fa: '۶ ماه' },
  horizon12m: { en: '12M', fa: '۱۲ ماه' },
  pendingCard: { en: 'Not matured yet. Results appear after', fa: 'هنوز به سررسید نرسیده است. نتایج پس از این تاریخ نمایش داده می‌شود:' },
  venueEqual: { en: 'Venue-equal (each of the 12 venues counts once)', fa: 'برابر بر اساس بورس (هر یک از ۱۲ بورس یک بار شمرده می‌شود)' },
  stockWeighted: { en: 'Stock-weighted (all holdings pooled, dominated by the largest venues)', fa: 'وزن‌دار بر اساس سهم (همهٔ سهم‌ها یکجا، با غلبهٔ بورس‌های بزرگ)' },
  buyMean: { en: 'BUY mean', fa: 'میانگین خرید' },
  sellMean: { en: 'SELL mean', fa: 'میانگین فروش' },
  spread: { en: 'BUY-SELL spread', fa: 'اختلاف خرید و فروش' },
  ci95: { en: '95% interval', fa: 'بازهٔ ۹۵٪' },
  hitRate: { en: 'Hit rate', fa: 'نرخ موفقیت' },
  readingLine: { en: 'Positive BUY-SELL ranking spread over one month; absolute returns were negative in a falling market; longer horizons pending.', fa: 'اختلاف رتبه‌بندی خرید و فروش در یک ماه مثبت بود؛ بازده مطلق در بازار نزولی منفی بود؛ افق‌های بلندتر هنوز نرسیده‌اند.' },
  readingLineNegative: { en: 'Negative BUY-SELL ranking spread over one month; read the data warning; longer horizons pending.', fa: 'اختلاف رتبه‌بندی خرید و فروش در این یک ماه منفی بود؛ هشدار داده را بخوانید؛ افق‌های بلندتر هنوز نرسیده‌اند.' },
  perMarket: { en: 'Per market', fa: 'به تفکیک بازار' },
  tooSmall: { en: 'too small to interpret', fa: 'برای تفسیر بسیار کوچک است' },
  perStock: { en: 'Per stock', fa: 'به تفکیک سهم' },
  best10: { en: 'Best and worst calls (excess return in the direction of the call)', fa: 'بهترین و بدترین تصمیم‌ها (بازده مازاد در جهت تصمیم)' },
  worstCalls: { en: 'Worst calls', fa: 'بدترین تصمیم‌ها' },
  search: { en: 'Search ticker or name', fa: 'جستجوی نماد یا نام' },
  loadMore: { en: 'Load more', fa: 'نمایش بیشتر' },
  allMarkets: { en: 'All markets', fa: 'همهٔ بازارها' },
  noRows: { en: 'No rows.', fa: 'ردیفی وجود ندارد.' },
  caveats: { en: 'Caveats', fa: 'محدودیت‌ها' },
  source: { en: 'Source', fa: 'منبع' },
  language: { en: 'فارسی', fa: 'English' },
} as const;

export type StrKey = keyof typeof STR;

export function tr(lang: Lang, key: StrKey): string {
  const e = STR[key];
  return (lang === 'fa' ? e.fa : e.en) || e.en;
}

const RISK_LEVELS: Record<string, { en: string; fa: string }> = {
  LOW: { en: 'LOW', fa: 'کم' }, MEDIUM: { en: 'MEDIUM', fa: 'متوسط' }, HIGH: { en: 'HIGH', fa: 'بالا' }, CRITICAL: { en: 'CRITICAL', fa: 'بحرانی' },
};
const PERF_LEVELS: Record<string, { en: string; fa: string }> = {
  STRONG: { en: 'STRONG', fa: 'قوی' }, STABLE: { en: 'STABLE', fa: 'پایدار' }, WEAK: { en: 'WEAK', fa: 'ضعیف' }, DETERIORATING: { en: 'DETERIORATING', fa: 'رو به وخامت' },
};
const STATUSES: Record<string, { en: string; fa: string }> = {
  OK: { en: 'OK', fa: 'کامل' }, PARTIAL: { en: 'PARTIAL', fa: 'ناقص' }, INSUFFICIENT_DATA: { en: 'INSUFFICIENT DATA', fa: 'داده ناکافی' },
  NOT_APPLICABLE: { en: 'NOT APPLICABLE', fa: 'قابل اعمال نیست' },
};
const SCOPES: Record<string, { en: string; fa: string }> = {
  'sector+market': { en: 'sector in this market', fa: 'صنعت در همین بازار' },
  sector: { en: 'sector, all markets', fa: 'صنعت در همهٔ بازارها' },
  'market-wide': { en: 'market-wide fallback', fa: 'مقایسه با کل بازار' },
};

export function levelLabel(lang: Lang, kind: 'risk' | 'performance', level: string | null | undefined): string | null {
  if (!level) return null;
  const e = (kind === 'risk' ? RISK_LEVELS : PERF_LEVELS)[level];
  return e ? (lang === 'fa' ? e.fa : e.en) : level;
}
export function statusLabel(lang: Lang, status: string | null | undefined): string {
  if (!status) return '';
  const e = STATUSES[status];
  return e ? (lang === 'fa' ? e.fa : e.en) : status;
}
export function scopeLabel(lang: Lang, scope: string | null | undefined): string {
  if (!scope) return '';
  const e = SCOPES[scope.startsWith('market-wide') ? 'market-wide' : scope];
  return e ? (lang === 'fa' ? e.fa : e.en) : scope;
}
