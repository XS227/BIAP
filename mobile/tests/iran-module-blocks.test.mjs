import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeEnvelope, formatValue, formatKpi, scaleBars, scaleLine, markerBin, groupKpis, statusTone, readinessText, cellText, faDigits, dataStatusText } from '../src/lib/iran-module-blocks.ts';

test('garbage / empty responses degrade to a blocked envelope, never to content', () => {
  for (const raw of [null, undefined, 42, 'x', {}, []]) {
    const e = normalizeEnvelope(raw, 'kpi-extract');
    assert.equal(e.status, 'blocked');
    assert.deepEqual(e.blocks, []);
  }
});

test('envelope keeps valid blocks, drops malformed ones, validates status', () => {
  const e = normalizeEnvelope({ module: 'eda', status: 'ok', summary: 's', blocks: [{ type: 'metrics', items: [] }, { nope: 1 }, null, 'x'], missing: [1, 'a'] }, 'eda');
  assert.equal(e.status, 'ok'); assert.equal(e.blocks.length, 1); assert.deepEqual(e.missing, ['1', 'a']);
  assert.equal(normalizeEnvelope({ status: 'weird', blocks: [] }, 'x').status, 'blocked');
  assert.equal(normalizeEnvelope({ status: 'needs_private_data', blocks: [] }, 'crm').status, 'needs_private_data');
});

test('formatValue never shows NaN/Infinity/undefined', () => {
  for (const v of [null, undefined, '', NaN, Infinity, -Infinity]) assert.equal(formatValue(v), '—');
  assert.equal(formatValue(0), '۰');
  assert.equal(formatValue(1234567), '۱,۲۳۴,۵۶۷');
  assert.equal(formatValue(0.5, { unit: '%' }), '۰٫۵٪');
  assert.equal(cellText(null), '—');
  assert.equal(faDigits('2026'), '۲۰۲۶');
});

test('KPI formatting: ratios as percent, units kept, missing as dash', () => {
  const base = { group: 'g', key: 'k', label: 'l', formula: 'f', inputs: [], source: 's', period: null, status: 'ok', missing: [] };
  assert.equal(formatKpi({ ...base, value: 0.125, unit: 'نسبت' }), '۱۲٫۵٪');
  assert.equal(formatKpi({ ...base, value: null, unit: 'نسبت' }), '—');
  assert.equal(formatKpi({ ...base, value: NaN, unit: '×' }), '—');
  assert.match(formatKpi({ ...base, value: 1.8, unit: '×' }), /×$/);
});

test('bars and line scale safely (constant, empty, negative)', () => {
  assert.deepEqual(scaleBars([0, 0], 100), [0, 0]);
  assert.deepEqual(scaleBars([], 100), []);
  const b = scaleBars([10, 5, -10], 100); assert.equal(b[0], 100); assert.equal(b[1], 50); assert.equal(b[2], 100);
  assert.deepEqual(scaleLine([], 100, 50), []);
  assert.deepEqual(scaleLine([7, 7, 7], 100, 50).map((p) => p.y), [25, 25, 25]);
  const l = scaleLine([1, 3], 100, 50); assert.deepEqual(l, [{ x: 0, y: 50 }, { x: 100, y: 0 }]);
  assert.ok(scaleLine([1, NaN, 3], 10, 10).length === 3);
});

test('histogram marker lands in the right bin and out-of-range is ignored', () => {
  const bins = [{ from: 0, to: 1 }, { from: 1, to: 2 }, { from: 2, to: 3 }];
  assert.equal(markerBin(bins, 1.5), 1); assert.equal(markerBin(bins, 3), 2);
  assert.equal(markerBin(bins, 9), -1); assert.equal(markerBin(bins, null), -1); assert.equal(markerBin([], 1), -1);
});

test('groupKpis keeps order; status helpers', () => {
  const g = groupKpis([{ group: 'b', key: '1' }, { group: 'a', key: '2' }, { group: 'b', key: '3' }]);
  assert.deepEqual(g.map((x) => [x.group, x.items.length]), [['b', 2], ['a', 1]]);
  assert.equal(statusTone('ok'), 'positive'); assert.equal(statusTone('blocked'), 'negative');
  assert.equal(readinessText('ready'), 'آماده'); assert.equal(readinessText('x'), 'نامشخص');
});

test('dataStatusText explains empties and separates missing price from stored history', () => {
  assert.deepEqual(dataStatusText(undefined), []);
  assert.deepEqual(dataStatusText({ codes: [] }), []);
  const reg = dataStatusText({ codes: ['REGISTERED_ONLY'] });
  assert.equal(reg.length, 1); assert.match(reg[0], /رجیستری/);
  const hist = dataStatusText({ codes: ['MISSING_MARKET', 'MISSING_CODAL'], hasHistory: true, historyObservations: 5 });
  assert.equal(hist.length, 3); assert.match(hist[2], /5/);
  assert.match(dataStatusText({ codes: ['SOURCE_RATE_LIMITED'] })[0], /محدودیت نرخ/);
  assert.deepEqual(dataStatusText({ codes: ['UNKNOWN_X'] }), []);
});

import { formatMoney, formatByUnit, tableCell, columnLabel, columnWidth, verificationText, scopeBadge, formatKpi as formatKpi2 } from '../src/lib/iran-module-blocks.ts';

test('money is compact, never rounds to zero, keeps sign', () => {
  assert.equal(formatMoney(19950000000000), '۱۹٫۹۵ هزار میلیارد');
  assert.equal(formatMoney(2999475220), '۳ میلیارد');
  assert.equal(formatMoney(-1500000), '-۱٫۵ میلیون');
  assert.equal(formatMoney(NaN), '—');
});
test('values render by the unit the backend declares', () => {
  assert.equal(formatByUnit(0.0682, 'fraction'), '۶٫۸٪');
  assert.equal(formatByUnit(2.78, 'percent'), '۲٫۷۸٪');
  assert.equal(formatByUnit(0.815, 'times'), '۰٫۸۲×');
  assert.equal(formatByUnit(null, 'fraction'), '—');
});
test('table cells use the row unit, percentile gets ٪, outlier is Persian, missing value is a dash', () => {
  const row = { column: 'ROE', unit: 'fraction', value: 0.1915, peerMedian: 0.12, percentile: 29.5, outlier: 'high' };
  assert.equal(tableCell(row, 'value'), '۱۹٫۲٪');
  assert.equal(tableCell(row, 'peerMedian'), '۱۲٪');
  assert.equal(tableCell(row, 'percentile'), '۲۹٫۵٪');
  assert.equal(tableCell(row, 'outlier'), 'بالا');
  assert.equal(tableCell({ column: 'P/E', unit: 'times', value: null }, 'value'), '—');
});
test('table headers are Persian, never raw JSON keys, and long text widens the column', () => {
  for (const k of ['column', 'value', 'source', 'percentile', 'sampleN', 'reason', 'sectorMedian']) assert.notEqual(columnLabel(k), k);
  const rows = [{ column: 'x', reason: 'ورودی‌های ناموجود: net_profit، total_assets و ورودی‌های دیگر' }];
  assert.ok(columnWidth(rows, 'reason') > columnWidth(rows, 'column'));
  assert.ok(columnWidth(rows, 'reason') <= 220);
});
test('verification banner only for unverified/incomplete statements; scope badges', () => {
  assert.equal(verificationText({ verification: { status: 'verified', reasons: [] } }), null);
  assert.match(verificationText({ verification: { status: 'unverified', reasons: ['ترازنامه تراز نیست'] } }), /تأییدنشده/);
  assert.match(verificationText({ verification: { status: 'incomplete', reasons: ['ناقص'] } }), /ناقص/);
  assert.equal(scopeBadge('company'), 'این شرکت');
  assert.equal(scopeBadge('market'), 'کل بازار / نمونه');
  assert.equal(scopeBadge(undefined), null);
});
test('an unverified KPI is shown as unverified, not as a number or a dash', () => {
  assert.equal(formatKpi2({ group: 'g', key: 'roa', label: 'ROA', value: null, unit: 'نسبت', formula: '', inputs: [], source: 'CODAL', period: null, status: 'unverified', missing: ['x'] }), 'تأییدنشده');
});
