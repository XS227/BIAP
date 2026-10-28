import test from 'node:test';
import assert from 'node:assert/strict';
const { iranCompanyKpis, answerIranIntelligence, formatIranKpi, finiteNumber } =
  await import('../src/lib/iran-intelligence.ts');

const sample=()=>({
  code:'1234', name:'نمونه', call:'HOLD', score:0.1, generatedAt:'2026-10-28T13:00:00Z',
  dataSource:'live', dataAvailability:{codal:true,codal_metadata:true,market_extended:true},
  livePrice:{lastPrice:5000}, extendedMarket:{pe:8.2, marketCap:25000000,volumeToday:5000},
  codalFundamentals:{revenue_yoy_pct:13.5,net_margin_pct:9.6,total_liabilities_current:null,report_title:'صورت‌های مالی حسابرسی‌شده',audit_opinion:'نامشخص'},
  breakdown:[{agent:'risk',vote:0.1,confidence:0.5,weight_normalized:1,reasoning:'ریسک متوسط'}],
});

test('safe financial KPI formatting, independent field not certified',()=>{
  const list=iranCompanyKpis(sample());
  const find=key=>list.find(x=>x.key===key);
  assert.equal(find('revenueGrowth').value,13.5);
  assert.equal(find('marketCap').value,25000000);
  assert.equal(find('liabilities').value,null);
  assert.equal(formatIranKpi(find('liabilities')),'داده موجود نیست');
  assert.equal(find('revenueGrowth').sourceVerifiedPerField,false);
});

test('questions preserve existing call and report unavailable liabilities',()=>{
  const x=sample();
  const d=answerIranIntelligence(x,'بدهی شرکت چقدر است؟');
  assert.equal(d.supported,true);
  assert.match(d.answer,/داده موجود نیست/);
  const decision=answerIranIntelligence(x,'سیگنال خرید کیاشا چیست؟');
  assert.match(decision.answer,/HOLD/);
  assert.equal(x.call,'HOLD');
});

test('no mock financial values or invented unsupported answers',()=>{
  const x=sample();x.dataSource='mock';
  assert.ok(iranCompanyKpis(x).every(r=>r.value===null));
  const q=answerIranIntelligence(x,'ده سال آینده را پیش‌بینی کن');
  assert.equal(q.supported,false);
});

test('reject nonfinite, numerical strings and booleans',()=>{
  assert.equal(finiteNumber(NaN),null);
  assert.equal(finiteNumber(Infinity),null);
  assert.equal(finiteNumber('1,000'),null);
  assert.equal(finiteNumber(true),null);
});
