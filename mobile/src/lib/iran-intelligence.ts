import type { Recommendation } from './api';

export type IranKpi = {
  key: string;
  fa: string;
  value: number | null;
  unit: string;
  source: 'TSETMC / بازار' | 'CODAL / اطلاعات مالی';
  sourceVerifiedPerField: false;
};

const METRICS = [
  ['marketCap', 'ارزش بازار', 'ریال', 'market'],
  ['pe', 'نسبت قیمت به سود (P/E)', 'برابر', 'market'],
  ['eps', 'سود هر سهم (EPS)', 'ریال', 'market'],
  ['volumeToday', 'حجم معاملات', 'سهم', 'market'],
  ['avgVolume30d', 'میانگین حجم ۳۰ روز', 'سهم', 'market'],
  ['dayLow', 'کمترین قیمت امروز', 'ریال', 'market'],
  ['dayHigh', 'بیشترین قیمت امروز', 'ریال', 'market'],
  ['revenueGrowth', 'رشد درآمد سالانه', 'درصد', 'codal'],
  ['netMargin', 'حاشیه سود خالص', 'درصد', 'codal'],
  ['prevNetMargin', 'حاشیه سود قبلی', 'درصد', 'codal'],
  ['assets', 'دارایی‌های جاری', 'ریال', 'codal'],
  ['liabilities', 'بدهی‌های جاری', 'ریال', 'codal'],
  ['equity', 'حقوق صاحبان سهام', 'ریال', 'codal'],
] as const;

export function finiteNumber(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

export function iranCompanyKpis(rec: Recommendation | null): IranKpi[] {
  const isReal = rec?.dataSource === 'live' || rec?.dataSource === 'codal';
  const m = isReal ? rec?.extendedMarket : null;
  const f = isReal && (rec?.dataAvailability?.codal || rec?.dataAvailability?.codal_metadata) ? rec?.codalFundamentals : null;
  const data: Record<string, unknown> = {
    marketCap: m?.marketCap, pe: m?.pe,
    eps: m?.epsValue ?? m?.estimatedEps, volumeToday: m?.volumeToday,
    avgVolume30d: m?.avgVolume30d, dayLow: m?.dayLow, dayHigh: m?.dayHigh,
    revenueGrowth: f?.revenue_yoy_pct, netMargin: f?.net_margin_pct,
    prevNetMargin: f?.net_margin_prev_pct, assets: f?.total_assets_current,
    liabilities: f?.total_liabilities_current, equity: f?.total_equity_current,
  };
  return METRICS.map(([key, fa, unit, family]) => ({
    key, fa, unit,
    value: finiteNumber(data[key]),
    source: (family === 'market' ? 'TSETMC / بازار' : 'CODAL / اطلاعات مالی') as IranKpi['source'],
    sourceVerifiedPerField: false as const,
  }));
}

export function formatIranKpi(k: IranKpi): string {
  return k.value === null ? 'داده موجود نیست'
    : k.value.toLocaleString('fa-IR', { maximumFractionDigits: 3 }) + ' ' + k.unit;
}

const TOPICS: readonly [string, readonly string[], readonly string[]][] = [
  ['source', ['منابع', 'منبع', 'اعتبار', 'مدرک', 'داده از کجا'], []],
  ['revenue', ['درآمد', 'فروش', 'رشد فروش'], ['revenueGrowth']],
  ['profit', ['سود', 'حاشیه', 'سودآوری'], ['eps', 'netMargin']],
  ['debt', ['بدهی', 'اهرم'], ['liabilities', 'equity']],
  ['valuation', ['ارزش', 'قیمت به سود', 'p/e'], ['marketCap', 'pe']],
  ['volume', ['حجم', 'معاملات'], ['volumeToday', 'avgVolume30d']],
  ['risk', ['ریسک', 'ورشکستگی'], []],
  ['decision', ['خرید', 'فروش سهم', 'پیشنهاد', 'سیگنال', 'تصمیم کیاشا'], []],
];

export function answerIranIntelligence(rec: Recommendation | null, rawQuestion: string) {
  const question = rawQuestion.trim().replace(/ي/g, 'ی').replace(/ك/g, 'ک').toLowerCase().replace(/\s+/g,' ');
  const selected = TOPICS.filter(([, words]) => words.some(w => question.includes(w))).slice(0,3);
  if (!rec || !selected.length) return { supported: false, answer: 'این نسخه درباره رشد درآمد، سود، بدهی، ارزش‌گذاری، حجم معاملات، منابع، ریسک و تصمیم ثبت‌شده کیاشا پاسخ می‌دهد. پیش‌بینی آزاد یا عدد ساختگی ارائه نمی‌شود.' };
  const kpis = iranCompanyKpis(rec), lines: string[] = [];
  for (const [topic, , keys] of selected) {
    if (keys.length) for (const key of keys) {
      const k = kpis.find(x => x.key === key);
      if (k) lines.push(`${k.fa}: ${formatIranKpi(k)}`);
    }
    else if (topic === 'source') {
      lines.push('منبع داده بازار: TSETMC (در صورت موجودبودن داده واقعی)');
      lines.push('اطلاعات مالی: CODAL (در صورت موجودبودن گزارش)');
      lines.push('عنوان گزارش: ' + (rec.codalFundamentals?.report_title || 'داده موجود نیست'));
    }
    else if (topic === 'risk') lines.push('وضعیت ریسک: ' + (rec.breakdown?.find(x => x.agent.toLowerCase().includes('risk'))?.reasoning || 'داده موجود نیست'));
    else if (topic === 'decision') lines.push('تصمیم اصلی کیاشا (بدون تغییر): ' + rec.call);
  }
  lines.push('منبع موتور: ' + rec.dataSource + '؛ زمان تحلیل: ' + (rec.generatedAt || 'نامشخص'));
  lines.push('توجه: تاریخ تحلیل با تاریخ دوره گزارش مالی یکسان نیست؛ اطلاعات مالی ممکن است ناقص باشد و صحت هر فیلد مستقلاً تأیید نشده است.');
  return { supported: true, answer: lines.join('\n') };
}
