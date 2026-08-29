import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'biap:business-dataset:v1';

export type BusinessDataset = {
  name: string;
  columns: string[];
  rows: Record<string, string>[];
  importedAt: string;
  source: 'csv-paste' | 'json-paste';
};

function splitCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = '';
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (ch === '"') {
      if (quoted && line[i + 1] === '"') { cur += '"'; i += 1; }
      else quoted = !quoted;
    } else if (ch === ',' && !quoted) { out.push(cur.trim()); cur = ''; }
    else cur += ch;
  }
  out.push(cur.trim());
  return out;
}

export function parseBusinessData(input: string, name = 'Company data'): BusinessDataset {
  const text = input.trim();
  if (!text) throw new Error('داده خالی است');
  if (text.startsWith('[') || text.startsWith('{')) {
    const parsed = JSON.parse(text);
    const arr = Array.isArray(parsed) ? parsed : Array.isArray(parsed?.rows) ? parsed.rows : [];
    if (!arr.length || typeof arr[0] !== 'object') throw new Error('JSON باید شامل آرایه‌ای از رکوردها باشد');
    const columns = Array.from(new Set(arr.flatMap((row: Record<string, unknown>) => Object.keys(row))));
    const rows = arr.map((row: Record<string, unknown>) => Object.fromEntries(columns.map((c) => [c, row[c] == null ? '' : String(row[c])])));
    return { name, columns, rows, importedAt: new Date().toISOString(), source: 'json-paste' };
  }
  const lines = text.split(/\r?\n/).filter((x) => x.trim());
  if (lines.length < 2) throw new Error('CSV باید حداقل یک ردیف عنوان و یک ردیف داده داشته باشد');
  const columns = splitCsvLine(lines[0]);
  const rows = lines.slice(1).map((line) => {
    const values = splitCsvLine(line);
    return Object.fromEntries(columns.map((c, i) => [c, values[i] ?? '']));
  });
  return { name, columns, rows, importedAt: new Date().toISOString(), source: 'csv-paste' };
}

export async function saveBusinessDataset(dataset: BusinessDataset): Promise<void> {
  await AsyncStorage.setItem(KEY, JSON.stringify(dataset));
}

export async function getBusinessDataset(): Promise<BusinessDataset | null> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    return raw ? JSON.parse(raw) as BusinessDataset : null;
  } catch { return null; }
}

export async function clearBusinessDataset(): Promise<void> {
  await AsyncStorage.removeItem(KEY);
}

export function summarizeBusinessDataset(dataset: BusinessDataset) {
  const total = dataset.rows.length * dataset.columns.length;
  const missing = dataset.rows.reduce((sum, row) => sum + dataset.columns.filter((c) => !String(row[c] ?? '').trim()).length, 0);
  const numericColumns = dataset.columns.filter((c) => {
    const vals = dataset.rows.map((r) => Number(String(r[c] ?? '').replace(/,/g, ''))).filter(Number.isFinite);
    return vals.length >= Math.max(2, Math.ceil(dataset.rows.length * 0.6));
  });
  const numeric = numericColumns.map((c) => {
    const vals = dataset.rows.map((r) => Number(String(r[c] ?? '').replace(/,/g, ''))).filter(Number.isFinite);
    const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
    const min = vals.length ? Math.min(...vals) : 0;
    const max = vals.length ? Math.max(...vals) : 0;
    return { column: c, count: vals.length, avg, min, max };
  });
  return { rows: dataset.rows.length, columns: dataset.columns.length, missing, completeness: total ? 1 - missing / total : 0, numericColumns, numeric };
}
