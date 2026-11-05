// Pure helpers for rendering the backend's module envelope (no React / network imports -> unit-testable).

export type ModuleStatus = 'ok' | 'partial' | 'blocked' | 'needs_private_data';
export type Block =
  | { type: 'metrics'; items: { label: string; value: unknown; unit?: string }[] }
  | { type: 'kpi_table'; items: KpiItem[] }
  | { type: 'table'; title?: string; columns: string[]; rows: Record<string, unknown>[] }
  | { type: 'histogram'; title?: string; bins: { from: number; to: number; count: number }[]; clipped?: number; n?: number; marker?: number | null; note?: string }
  | { type: 'bars'; title?: string; items: { label: string; value: number }[] }
  | { type: 'line'; title?: string; points: { x: string; y: number }[]; forecast?: { x: string; y: number; low: number; high: number }[] }
  | { type: 'swot'; strengths: string[]; weaknesses: string[]; opportunities: string[]; threats: string[] }
  | { type: 'bullets'; title?: string; items: string[] }
  | { type: 'notice'; tone?: string; text: string; missing?: string[] };
export type KpiItem = { group: string; key: string; label: string; value: number | null; unit: string; formula: string; inputs: string[]; source: string; period: string | null; status: string; missing: string[] };
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
    const text = faDigits(v.toLocaleString('en-US', { maximumFractionDigits: digits }));
    return opts.unit === '%' ? `${text}٪` : text;
  }
  return String(v);
}
export function formatKpi(item: KpiItem): string {
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
