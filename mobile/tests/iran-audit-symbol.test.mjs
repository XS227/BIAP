import test from 'node:test';
import assert from 'node:assert/strict';
import { validateIranAuditSymbol } from '../src/lib/iran-audit-symbol.ts';

test('allows arbitrary verified-inbox symbol lookups, not only three presets', () => {
  assert.equal(validateIranAuditSymbol('  شستا  '), 'شستا');
  assert.equal(validateIranAuditSymbol('پكرمان'), 'پكرمان');
});
test('rejects empty, oversized, control and path/query characters', () => {
  for (const input of ['', '  ', 'a'.repeat(65), 'foo/bar', 'foo?bar', 'foo#bar', 'foo\nbar']) {
    assert.equal(validateIranAuditSymbol(input), null);
  }
});
