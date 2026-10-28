import test from 'node:test';
import assert from 'node:assert/strict';

const { buildIntelligenceMetrics, formatIntelligenceMetric, answerIntelligenceQuestion } =
  await import('../src/lib/intelligence-summary.ts');

const payload = () => ({
  ticker: 'TEST', country: 'US', exchange: 'NASDAQ', currency: 'USD',
  call: 'NO_RECOMMENDATION', evidence: {status:'WARN', missing_critical:['fresh_price']},
  fundamentalEvidence: {officialStatus:'OFFICIAL_CURRENT', reportPeriod:'2025-12-31',
    sourceProvider:'sec-edgar', sourceUrl:'https://www.sec.gov/example'},
  distress: {status:'INSUFFICIENT_DATA'},
  company: {currency:'USD', reporting_currency:'USD', price: 43.2, price_observed_at:'2026-10-27T14:00:00Z',
    revenue: 120_000_000, revenue_yoy_pct: 20, net_income: 9_000_000, total_debt:null,
    sources: [{provider:'sec-edgar',source_type:'official_regulatory_xbrl',source_url:'https://www.sec.gov/example'}]},
});

test('read-only intelligence dashboard preserves null and separate dates', () => {
  const a=payload();
  const metrics=buildIntelligenceMetrics(a);
  const byKey=Object.fromEntries(metrics.map(m=>[m.key,m]));
  assert.equal(byKey.price.asOf,'2026-10-27T14:00:00Z');
  assert.equal(byKey.revenue.asOf,'2025-12-31');
  assert.equal(byKey.total_debt.value,null);
  assert.equal(byKey.revenue.fieldVerified,false);
  assert.equal(formatIntelligenceMetric(byKey.revenue),'120,000,000 USD');
  assert.equal(formatIntelligenceMetric(byKey.total_debt),'—');
  assert.equal(a.call,'NO_RECOMMENDATION');
});

test('Persian questions use existing data, no invented debt', () => {
  const result=answerIntelligenceQuestion(payload(),'بدهی شرکت چقدر است؟');
  assert.equal(result.supported,true);
  assert.ok(result.answer.includes('بدهی مالی: —'));
  assert.ok(result.answer.includes('2025-12-31'));
  assert.equal(result.decisionUnchanged,true);
});

test('English revenue and original decision are surfaced without new score', () => {
  const result=answerIntelligenceQuestion(payload(),'What is the revenue and recommendation?','en');
  assert.ok(result.answer.includes('120,000,000 USD'));
  assert.ok(result.answer.includes('NO_RECOMMENDATION'));
  assert.equal(result.method,'grounded_rules_no_llm');
});

test('unsupported forecasting question returns safe non-answer', () => {
  const result=answerIntelligenceQuestion(payload(),'What will happen in 10 years?','en');
  assert.equal(result.supported,false);
  assert.ok(result.answer.includes('does not generate unsupported forecasts'));
});

test('NaN, Infinity, strings and boolean financial values are unavailable', () => {
  assert.equal(buildIntelligenceMetrics({...payload(),company:{...payload().company, price:NaN, revenue:Infinity}})
    .find(m=>m.key==='revenue')?.value,null);
  assert.equal(buildIntelligenceMetrics({...payload(),company:{...payload().company, revenue:'120000000'}})
    .find(m=>m.key==='revenue')?.value,null);
  assert.equal(buildIntelligenceMetrics({...payload(),company:{...payload().company, revenue:true}})
    .find(m=>m.key==='revenue')?.value,null);
});
