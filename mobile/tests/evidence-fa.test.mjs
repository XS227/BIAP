import test from 'node:test';
import assert from 'node:assert/strict';
import { evidenceReasonsFa, evidenceStatusFa } from '../src/lib/evidence-fa.ts';
test('statuses and reasons are Persian, never raw English', () => {
  assert.equal(evidenceStatusFa('BLOCK'), 'مسدود');
  assert.equal(evidenceStatusFa('PASS'), 'تأییدشده');
  assert.equal(evidenceReasonsFa(['Verified CODAL fundamentals unavailable']), 'صورت مالی تأییدشده‌ی کدال موجود نیست');
  assert.doesNotMatch(evidenceReasonsFa(['Current balance-sheet identity mismatch (3.0% of assets)', 'something new']), /[A-Za-z]/);
});
