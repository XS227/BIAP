import test from 'node:test';
import assert from 'node:assert/strict';
import { callBadge, evidenceHeld, normalizedWeightPercents, queueBadge, trackButtonLabel, DATA_HOLD_LABEL } from '../src/lib/signal-display.ts';

test('missing/blocked evidence never shows خرید/فروش', () => {
  for (const review of [undefined, null, {}, { actionable: false }]) {
    assert.equal(evidenceHeld(review), true);
    for (const call of ['BUY', 'SELL', 'HOLD']) assert.deepEqual(callBadge(call, review), { label: DATA_HOLD_LABEL, neutral: true });
  }
  assert.deepEqual(callBadge('BUY', { actionable: true }), { label: 'خرید', neutral: false });
});
test('portfolio button is neutral unless an actionable BUY', () => {
  assert.equal(trackButtonLabel('SELL', { actionable: true }, false).neutral, true);
  assert.equal(trackButtonLabel('SELL', { actionable: true }, false).label, 'ثبت در پرتفوی من');
  assert.equal(trackButtonLabel('BUY', { actionable: false }, false).neutral, true);
  assert.equal(trackButtonLabel('BUY', { actionable: true }, false).label, 'خریدم — شروع پیگیری');
});
test('weights always sum to exactly 100', () => {
  for (const ws of [[0.105, 0.263, 0.184, 0.447], [1 / 3, 1 / 3, 1 / 3], [0.505, 0.495], [0, 0, 0], [0.2, 0.5, 0.35, 0.15, 0.1]]) {
    const out = normalizedWeightPercents(ws);
    const total = ws.reduce((a, b) => a + b, 0);
    assert.equal(out.reduce((a, b) => a + b, 0), total > 0 ? 100 : 0, JSON.stringify(ws));
  }
  assert.deepEqual(normalizedWeightPercents([null, undefined, 1]), [0, 0, 100]);
});
test('queue badge: single price at the 3% limit with volume -> buy queue; normal days -> none', () => {
  assert.equal(queueBadge({ dayLow: 10270, dayHigh: 10270, changePercent: 2.9058, volumeToday: 45139154 }).side, 'BUY');
  assert.equal(queueBadge({ dayLow: 4000, dayHigh: 4000, changePercent: -4.96, volumeToday: 10 }).side, 'SELL');
  assert.equal(queueBadge({ dayLow: 10000, dayHigh: 10270, changePercent: 2.9, volumeToday: 5 }), null);
  assert.equal(queueBadge({ dayLow: 10270, dayHigh: 10270, changePercent: 1.2, volumeToday: 5 }), null);
  assert.equal(queueBadge({ dayLow: 10270, dayHigh: 10270, changePercent: 2.9, volumeToday: 0 }), null);
  assert.equal(queueBadge(null), null);
});

import { confidenceNote } from '../src/lib/signal-display.ts';
test('confidence note flags thin track records', () => {
  assert.match(confidenceNote(0), /بدون سابقه/);
  assert.match(confidenceNote(3), /سابقه‌ی کم/);
  assert.equal(confidenceNote(null), '');
  assert.match(confidenceNote(50), /50|۵۰/);
});

import { previewRowBadge, previewExplanation, NO_CODAL_LABEL } from '../src/lib/signal-display.ts';
test('home preview: stock without CODAL or with held evidence carries «بدون تأیید کدال»; verified stock none; unloaded none', () => {
  assert.equal(NO_CODAL_LABEL, 'بدون تأیید کدال');
  assert.equal(previewRowBadge(undefined), null);
  assert.deepEqual(previewRowBadge(null), { label: NO_CODAL_LABEL, held: true });
  assert.equal(previewRowBadge({ dataAvailability: { codal: false }, evidenceReview: { actionable: true } }).held, true);
  assert.equal(previewRowBadge({ dataAvailability: { codal: true }, evidenceReview: { actionable: false } }).held, true);
  assert.equal(previewRowBadge({ dataAvailability: { codal: true }, evidenceReview: { actionable: true } }), null);
});
test('home preview explanation says why only one stock shows and counts held ones', () => {
  const t = previewExplanation(1, 1, false);
  assert.ok(t.includes('بازار بسته') && t.includes('تنها یک نماد') && t.includes(NO_CODAL_LABEL) && t.includes('توصیهٔ Kiasha'));
  assert.ok(!previewExplanation(5, 0, true).includes('تنها یک نماد'));
});

import { normalizeSearch } from '../src/lib/data-status.ts';
import { columnLabel } from '../src/lib/iran-module-blocks.ts';
test('search folds Arabic ي/ك and digits so a keyboard variant finds the stored symbol', () => {
  assert.equal(normalizeSearch('فولاد خوزستان'), 'فولاد خوزستان');
  assert.equal(normalizeSearch('كيان'), 'کیان');
  assert.equal(normalizeSearch('مبين٣'), 'مبین3');
  assert.equal(normalizeSearch('  وبملت‌ '), 'وبملت');
});
test('SWOT competitor columns have Persian headers', () => {
  assert.equal(columnLabel('pe'), 'P/E'); assert.equal(columnLabel('debt_ratio'), 'نسبت بدهی');
  assert.equal(columnLabel('roe'), 'ROE'); assert.equal(columnLabel('net_margin'), 'حاشیه سود خالص'); assert.equal(columnLabel('name'), 'نام شرکت');
});

import { splitShares, NON_SHARE_NOTE, isNonShareListing } from '../src/lib/listed-company-rank.ts';
import { fieldStateText } from '../src/lib/module-data-requirements.ts';
import { formatByUnit, tableCell } from '../src/lib/iran-module-blocks.ts';
test('analysis entry points hide bonds/funds (e.g. «مرابحه تندیس08») and keep the main stock', () => {
  const { shares, others } = splitShares([
    { symbol: 'تندیس08', name: 'مرابحه تندیس08', paper_type: '306' }, { symbol: 'پارسان', name: 'گسترش نفت و گاز پارسیان', paper_type: '300' },
    { symbol: 'اهرم', name: 'صندوق س. اهرمی' }, { symbol: 'فولاد', name: 'فولاد مبارکه اصفهان' }]);
  assert.deepEqual(shares.map((x) => x.symbol), ['پارسان', 'فولاد']); assert.equal(others.length, 2);
  assert.ok(NON_SHARE_NOTE.includes('سهام نیست')); assert.equal(isNonShareListing({ name: 'مرابحه تندیس08' }), true);
});
test('listed symbol never shows «✓ موجود» from a private dataset: CODAL fields are automatic, customer fields come from the user', () => {
  assert.equal(fieldStateText({ required: true, autoSources: ['codal'] }, 'listed', true), 'خودکار از کدال');
  assert.equal(fieldStateText({ required: true }, 'listed', true), 'از شما (آپلود)');
  assert.equal(fieldStateText({ required: false }, 'listed', true), 'اختیاری (داده‌ی خودتان)');
  assert.equal(fieldStateText({ required: true }, 'private', true), '✓ موجود');
});
test('CODAL KPI table formats million-rial amounts and fractions with the previous-period column', () => {
  assert.ok(formatByUnit(1234, 'million_rial').endsWith('م.ر'));
  assert.ok(tableCell({ metric: 'درآمد', value: 1000, prev: 800, unit: 'million_rial' }, 'prev').includes('م.ر'));
  assert.ok(tableCell({ metric: 'حاشیه', value: 0.2, prev: 0.15, unit: 'fraction' }, 'prev').includes('٪'));
});
