import * as XLSX from 'xlsx';
import type { BusinessDataset } from '@/lib/business-data';

export function parseExcelArrayBuffer(buffer: ArrayBuffer, name = 'Excel data'): BusinessDataset {
  const workbook = XLSX.read(buffer, { type: 'array' });
  const firstSheetName = workbook.SheetNames[0];
  if (!firstSheetName) throw new Error('فایل Excel هیچ شیتی ندارد');
  const sheet = workbook.Sheets[firstSheetName];
  const rawRows = XLSX.utils.sheet_to_json<Record<string, unknown>>(sheet, { defval: '' });
  if (!rawRows.length) throw new Error('شیت Excel داده‌ای برای وارد کردن ندارد');
  const columns = Array.from(new Set(rawRows.flatMap((row) => Object.keys(row))));
  if (!columns.length) throw new Error('ستون معتبری در فایل Excel پیدا نشد');
  const rows = rawRows.map((row) => Object.fromEntries(columns.map((column) => [column, row[column] == null ? '' : String(row[column])])) as Record<string, string>);
  return {
    name,
    columns,
    rows,
    importedAt: new Date().toISOString(),
    source: 'xlsx-file',
  };
}
