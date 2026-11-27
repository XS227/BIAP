// Run: node --experimental-strip-types --no-warnings --test tests/tab-routes.test.mjs
// Every route file must be registered in BOTH tab layouts: native (a missing Tabs.Screen becomes an unwanted extra tab) and web
// (expo-router/ui renders only routes that have a TabTrigger, so an unregistered route shows the home screen instead).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

function routes(dir = 'src/app', prefix = '') {
  const out = [];
  for (const f of readdirSync(dir)) {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) { out.push(...routes(p, prefix + f + '/')); continue; }
    const m = f.match(/^(.*)\.tsx$/);
    if (!m || m[1].startsWith('_') || m[1].startsWith('+')) continue;
    out.push(m[1] === 'index' && !prefix ? 'index' : prefix + m[1]);
  }
  return out;
}
const native = readFileSync('src/components/app-tabs.tsx', 'utf8');
const web = readFileSync('src/components/app-tabs.web.tsx', 'utf8');

test('every route file is registered in the native tab layout', () => {
  for (const r of routes()) assert.ok(native.includes(`name="${r}"`), `native tabs miss route ${r}`);
});

test('every route file has a TabTrigger in the web tab layout', () => {
  for (const r of routes()) {
    const web_name = r === 'index' ? 'home' : r;
    assert.ok(web.includes(`name="${web_name}"`), `web tabs miss route ${r}`);
  }
});
