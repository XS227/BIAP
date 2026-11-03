import test from 'node:test';
import assert from 'node:assert/strict';
import { isNonShareListing, listingTypeFa, rankListedCompanies } from '../src/lib/listed-company-rank.ts';
test('bond ranks after the main stock', () => {
  const items = [{ code: '1', symbol: 'تابان25', name: 'اجاره تابان فردا زاگرس14070603' }, { code: '2', symbol: 'تابان', name: 'گروه پتروشيمي تابان فردا' }];
  assert.equal(rankListedCompanies(items, 'تابان')[0].symbol, 'تابان');
  assert.equal(isNonShareListing(items[0]), true);
  assert.equal(listingTypeFa(items[1]), 'سهام');
});
