import test from 'node:test';
import assert from 'node:assert/strict';
import { isPaperDraft, paperTicketLabel, validatePaperTicket } from '../src/lib/global-paper-order.ts';

const valid = {
  brokerId: 'ibkr', side: 'BUY', country: 'NO', exchange: 'OSE',
  micCode: 'XOSL', currency: 'NOK', ticker: 'AZT', quantity: '10', limitPrice: '25.50',
};

test('validates market, currency and indicative notional without placing an order', () => {
  const result = validatePaperTicket(valid);
  assert.equal(result.ok, true);
  assert.equal(result.value.indicativeNotional, 255);
  assert.equal(result.value.micCode, 'XOSL');
  assert.match(paperTicketLabel(result.value), /NOK 255/);
});

test('reject non-US Alpaca, malformed symbols, fractional shares and invalid prices', () => {
  for (const patch of [
    { brokerId: 'alpaca' }, { ticker: '../AZT' }, { quantity: '-1' },
    { quantity: '0.5' }, { quantity: '0' }, { quantity: '100001' },
    { limitPrice: 'NaN' }, { limitPrice: '1e4' }, { limitPrice: '0' },
    { limitPrice: '1.0000001' }, { currency: 'NOK/USD' },
  ]) assert.equal(validatePaperTicket({ ...valid, ...patch }).ok, false, JSON.stringify(patch));
});

test('respects known lot sizes when available', () => {
  assert.equal(validatePaperTicket({ ...valid, lotSize: 5, quantity: '3' }).ok, false);
  assert.equal(validatePaperTicket({ ...valid, lotSize: 5, quantity: '10' }).ok, true);
});

test('only explicitly unsent local drafts can display as drafts', () => {
  const result = validatePaperTicket(valid);
  assert.equal(result.ok, true);
  const draft = { ...result.value, id: 'draft-1', createdAt: '2026-11-04T00:00:00Z', status: 'DRAFT_ONLY', note: 'NOT_SUBMITTED' };
  assert.equal(isPaperDraft(draft), true);
  assert.equal(isPaperDraft({ ...draft, status: 'FILLED' }), false);
  assert.equal(isPaperDraft({ ...draft, note: 'SENT' }), false);
});
