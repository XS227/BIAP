// Pure helpers for rendering the backend's module envelope (no React / network imports -> unit-testable).

export type ModuleStatus = 'ok' | 'partial' | 'blocked' | 'needs_private_data';
export type Block =
  | { type: 'metrics'; title?: string; scopeKind?: 'company' | 'market'; items: { label: string; value: unknown; unit?: string }[] }
  | { type: 'kpi_table'; items: KpiItem[] }
  | { type: 'table'; title?: string; scopeKind?: 'company' | 'market'; columns: string[]; rows: Record<string, unknown>[] }
  | { type: 'histogram'; title?: string; unit?: string; markerInRange?: boolean; bins: { from: number; to: number; count: number }[]; clipped?: number; n?: number; marker?: number | null; note?: string }
  | { type: 'bars'; title?: string; items: { label: string; value: number }[] }
  | { type: 'line'; title?: string; scopeKind?: 'company' | 'market'; points: { x: string; y: number }[]; forecast?: { x: string; y: number; low: number; high: number }[] }
  | { type: 'swot'; strengths: string[]; weaknesses: string[]; opportunities: string[]; threats: string[] }
  | { type: 'bullets'; title?: string; items: string[] }
  | { type: 'notice'; tone?: string; scopeKind?: 'company' | 'market'; text: string; missing?: string[] };
export type KpiItem = { group: string; key: string; label: string; value: number | null; unit: string; formula: string; inputs: string[]; source: string; period: string | null; status: string; missing: string[]; kind?: string; requiresPrivateData?: boolean };
export type ModuleEnvelope = {
  module: string; title?: string; status: ModuleStatus; summary?: string; blocks: Block[]; missing: string[]; note?: string | null;
  tier?: string; provenance?: Record<string, unknown>; quality?: { missing?: string[]; warnings?: string[] }; dataStatus?: { codes?: string[]; hasCurrentPrice?: boolean; hasHistory?: boolean; historyObservations?: number }; company?: { code?: string; symbol?: string; name?: string } | null;
  pipeline?: unknown; schema?: Record<string, { name: string; type: string }[]>; examples?: { title: string; sql: string; params: unknown[] }[];
};

const STATUSES: ModuleStatus[] = ['ok', 'partial', 'blocked', 'needs_private_data'];

/** Defensive parse: unknown shapes degrade to a blocked envelope, never to fabricated content. */
export function normalizeEnvelope(raw: unknown, moduleKey: string): ModuleEnvelope {
  const r = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const status = STATUSES.includes(r.status as ModuleStatus) ? (r.status as ModuleStatus) : 'blocked';
  const blocks = Array.isArray(r.blocks) ? (r.blocks.filter((b) => b && typeof b === 'object' && typeof (b as { type?: unknown }).type === 'string') as Block[]) : [];
  const missing = Array.isArray(r.missing) ? r.missing.map(String) : [];
  const valid = r && Object.keys(r).length > 0;
  return {
    ...(r as object), module: String(r.module ?? moduleKey), status: valid ? status : 'blocked',
    summary: valid ? String(r.summary ?? '') : 'پاسخ معتبر از سرور دریافت نشد.', blocks, missing,
  } as ModuleEnvelope;
}

export const STATUS_LABEL: Record<ModuleStatus, string> = {
  ok: 'محاسبه شد', partial: 'بخشی از داده موجود است', blocked: 'داده‌ی لازم موجود نیست', needs_private_data: 'نیازمند داده‌ی داخلی شما',
};
export function statusTone(status: ModuleStatus): 'positive' | 'warning' | 'negative' | 'info' {
  return status === 'ok' ? 'positive' : status === 'partial' ? 'warning' : status === 'blocked' ? 'negative' : 'info';
}
export const TIER_LABEL: Record<string, string> = {
  full: 'مالی کامل + بازار', partial_financials: 'مالی ناقص', market_only: 'فقط بازار', registered_only: 'فقط ثبت‌شده', private: 'داده‌ی داخلی',
};

export const DATA_STATUS_LABEL: Record<string, string> = {
  REGISTERED_ONLY: 'شرکت در رجیستری هست، اما هنوز داده‌ی بازار یا کدال برایش دریافت نشده است.',
  MISSING_MARKET: 'قیمت بازار فعلی موجود نیست.',
  MISSING_CODAL: 'صورت مالی کدال برای این شرکت هنوز دریافت نشده است.',
  SOURCE_RATE_LIMITED: 'منبع داده موقتاً محدودیت نرخ اعمال کرده؛ دریافت در اجرای بعدی تکرار می‌شود.',
};
/** Why a module is empty, in words. Distinguishes a missing current price from stored historical observations. */
export function dataStatusText(ds?: ModuleEnvelope['dataStatus']): string[] {
  if (!ds || !Array.isArray(ds.codes)) return [];
  const out = ds.codes.filter((c) => c in DATA_STATUS_LABEL).map((c) => DATA_STATUS_LABEL[c]);
  if (ds.codes.includes('MISSING_MARKET') && ds.hasHistory) out.push(`${ds.historyObservations ?? 0} مشاهده‌ی تاریخی قیمت ذخیره شده است (قیمت فعلی نیست).`);
  return out;
}

const FA = '۰۱۲۳۴۵۶۷۸۹';
export function faDigits(s: string): string { return s.replace(/[0-9]/g, (d) => FA[Number(d)]); }

/** Number -> compact Persian text. Never invents a value: null/NaN/non-finite -> '—'. */
export function formatValue(v: unknown, opts: { unit?: string; digits?: number } = {}): string {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'number') {
    if (!Number.isFinite(v)) return '—';
    const abs = Math.abs(v);
    const digits = opts.digits ?? (abs >= 1000 ? 0 : abs >= 10 ? 1 : 3);
    const text = faDigits(v.toLocaleString('en-US', { maximumFractionDigits: digits })).replace('.', '٫');
    return opts.unit === '%' ? `${text}٪` : text;
  }
  return String(v);
}
/** Compact rial amounts: 19,950,000,000,000 -> «۱۹٫۹۵ هزار میلیارد». Never rounds a small value to zero. */
export function formatMoney(v: number): string {
  if (!Number.isFinite(v)) return '—';
  const a = Math.abs(v);
  const sign = v < 0 ? '-' : '';
  const f = (x: number, unit: string) => `${sign}${faDigits(x.toLocaleString('en-US', { maximumFractionDigits: 2 }).replace('.', '٫'))} ${unit}`;
  if (a >= 1e12) return f(a / 1e12, 'هزار میلیارد');
  if (a >= 1e9) return f(a / 1e9, 'میلیارد');
  if (a >= 1e6) return f(a / 1e6, 'میلیون');
  return formatValue(v);
}
/** Render a number by the unit the backend declares for its column. */
export function formatByUnit(v: unknown, unit?: string): string {
  if (typeof v !== 'number' || !Number.isFinite(v)) return v === null || v === undefined ? '—' : String(v);
  if (unit === 'fraction') return `${faDigits((v * 100).toLocaleString('en-US', { maximumFractionDigits: 1 }).replace('.', '٫'))}٪`;
  if (unit === 'percent') return `${faDigits(v.toLocaleString('en-US', { maximumFractionDigits: 2 }).replace('.', '٫'))}٪`;
  if (unit === 'times') return `${faDigits(v.toLocaleString('en-US', { maximumFractionDigits: 2 }).replace('.', '٫'))}×`;
  if (unit === 'rial') return formatMoney(v);
  return formatValue(v);
}
export const COLUMN_LABEL: Record<string, string> = {
  column: 'شاخص', value: 'مقدار', source: 'منبع', peerMedian: 'میانه نمونه', percentile: 'صدک', sampleN: 'اندازه نمونه', scope: 'دامنه', reason: 'توضیح',
  n: 'تعداد', mean: 'میانگین', median: 'میانه', std: 'انحراف معیار', min: 'کمینه', q1: 'چارک ۱', q3: 'چارک ۳', max: 'بیشینه', skew: 'چولگی',
  outlier: 'پرت', a: 'شاخص اول', b: 'شاخص دوم', r: 'همبستگی', present: 'موجود', missingPct: 'گمشده ٪', metric: 'شاخص', sectorMedian: 'میانه گروه',
  marketMedian: 'میانه بازار', company: 'این شرکت', date: 'تاریخ', return: 'بازده', robustZ: 'z مقاوم', step: 'گام', forecast: 'پیش‌بینی', low: 'کف', high: 'سقف',
};
export function columnLabel(c: string): string { return COLUMN_LABEL[c] ?? c; }
const PCT_COLUMNS = new Set(['percentile', 'missingPct']);
/** Table cell: value-like columns use the row's own unit, percentile columns get ٪, text stays text. */
export function tableCell(row: Record<string, unknown>, col: string): string {
  const v = row[col];
  if (v === null || v === undefined) return col === 'value' || col === 'peerMedian' || col === 'company' ? '—' : '';
  if (typeof v === 'number') {
    if (PCT_COLUMNS.has(col)) return `${formatValue(v, { digits: 1 })}٪`;
    const unitCols = new Set(['value', 'peerMedian', 'mean', 'median', 'std', 'min', 'q1', 'q3', 'max', 'sectorMedian', 'marketMedian', 'company']);
    if (unitCols.has(col) && typeof row.unit === 'string') return formatByUnit(v, row.unit);
  }
  if (col === 'outlier') return v === 'high' ? 'بالا' : v === 'low' ? 'پایین' : '';
  return cellText(v);
}
export function columnWidth(rows: Record<string, unknown>[], col: string): number {
  const longest = Math.max(columnLabel(col).length, ...rows.map((r) => tableCell(r, col).length));
  return Math.max(64, Math.min(220, 14 + longest * 7.2));
}
export function scopeBadge(kind?: string): string | null { return kind === 'company' ? 'این شرکت' : kind === 'market' ? 'کل بازار / نمونه' : null; }
export function verificationText(prov?: Record<string, unknown>): string | null {
  const v = prov?.verification as { status?: string; reasons?: string[] } | undefined;
  if (!v) return null;
  if (v.status === 'unverified') return `صورت مالی تأییدنشده: ${(v.reasons ?? []).join('؛ ')}. نسبت‌های مبتنی بر ترازنامه نمایش داده نمی‌شوند.`;
  if (v.status === 'incomplete') return `صورت مالی ناقص: ${(v.reasons ?? []).join('؛ ')}`;
  return null;
}

export function formatKpi(item: KpiItem): string {
  if (item.status === 'unverified') return 'تأییدنشده';
  if (item.value === null || !Number.isFinite(item.value)) return '—';
  if (item.unit === 'نسبت' && Math.abs(item.value) < 5) return `${formatValue(item.value * 100, { digits: 1 })}٪`;
  return `${formatValue(item.value)}${item.unit && item.unit !== 'نسبت' ? ` ${item.unit}` : ''}`;
}

export function scaleBars(values: number[], maxPx: number): number[] {
  const finite = values.filter((v) => Number.isFinite(v));
  const max = Math.max(0, ...finite.map(Math.abs));
  if (max === 0) return values.map(() => 0);
  return values.map((v) => (Number.isFinite(v) ? Math.max(2, Math.round((Math.abs(v) / max) * maxPx)) : 0));
}

/** Points scaled into a w x h box (y inverted). Constant series sit on the middle line. */
export function scaleLine(ys: number[], w: number, h: number): { x: number; y: number }[] {
  const finite = ys.filter((v) => Number.isFinite(v));
  if (finite.length === 0) return [];
  const lo = Math.min(...finite), hi = Math.max(...finite);
  const span = hi - lo;
  return ys.map((v, i) => ({ x: ys.length === 1 ? w / 2 : (i / (ys.length - 1)) * w, y: span === 0 ? h / 2 : h - ((v - lo) / span) * h }));
}

export function markerBin(bins: { from: number; to: number }[], marker: number | null | undefined): number {
  if (marker === null || marker === undefined || !Number.isFinite(marker) || bins.length === 0) return -1;
  if (marker < bins[0].from || marker > bins[bins.length - 1].to) return -1;
  const i = bins.findIndex((b) => marker >= b.from && marker <= b.to);
  return i;
}

export function cellText(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'number') return formatValue(v);
  return String(v);
}

/** Group KPI items by their `group`, preserving first-seen order. */
export function groupKpis(items: KpiItem[]): { group: string; items: KpiItem[] }[] {
  const order: string[] = [];
  const map = new Map<string, KpiItem[]>();
  for (const it of items) {
    if (!map.has(it.group)) { map.set(it.group, []); order.push(it.group); }
    map.get(it.group)!.push(it);
  }
  return order.map((g) => ({ group: g, items: map.get(g)! }));
}

export const SQL_ROW_LIMITS = [50, 200, 1000];
export function csvFileName(prefix = 'biap-query'): string { return `${prefix}-${new Date().toISOString().slice(0, 10)}.csv`; }

export function readinessText(status: string): string {
  return status === 'ready' ? 'آماده' : status === 'partial' ? 'ناقص' : status === 'blocked' ? 'داده ناکافی' : status === 'needs_private_data' ? 'نیازمند داده داخلی' : 'نامشخص';
}
