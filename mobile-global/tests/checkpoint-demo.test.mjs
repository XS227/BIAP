import { createCheckpointRequestGuard } from '../src/lib/checkpoint-request-guard.ts';
import test from 'node:test';
import { validateSavedGlobalCompany, validateSavedGlobalAiReport, assertIsolatedCheckpointStagingBase, assessSavedGlobalCoverage, summarizeSavedGlobalCompany } from '../src/lib/saved-company-contract.ts';
import assert from 'node:assert/strict';
import { GLOBAL_CHECKPOINT_DEMO, auditCheckpointDemo, demoFinancialRatios, createCheckpointScenario, explainDemoCompany, selectDemoBroker } from '../src/lib/checkpoint-demo.ts';

test('Global checkpoint preview is explicitly synthetic and never recommends trades', () => {
  const d = GLOBAL_CHECKPOINT_DEMO;
  assert.equal(d.mode, 'DEMO');
  assert.equal(d.provenance, 'SYNTHETIC_NOT_MARKET_DATA');
  assert.equal(d.agents.length, 6);
  assert.equal(d.kiasha.verdict, 'NO_RECOMMENDATION');
  assert.ok(d.agents.every(a => a.verdict === 'NO_RECOMMENDATION'));
  assert.equal(d.ai.status, 'DEMO_ONLY');
  assert.equal(d.ai.route, 'biap-ai-proxy');
  assert.ok(d.brokerChoices.length >= 3);
  assert.ok(d.brokerChoices.every(b => b.enabled === false));
  assert.equal(auditCheckpointDemo(d).eligibleForInvestmentDecision, false);
});

test('Global audit reports missing financial fields deterministically', () => {
  const d = structuredClone(GLOBAL_CHECKPOINT_DEMO);
  d.financials.revenue = null;
  const audit = auditCheckpointDemo(d);
  assert.deepEqual(audit.missing, ['revenue']);
  assert.equal(audit.checks.find(c => c.key === 'financial_lines')?.passed, false);
});

test('Global preview never invents agent confidence or verified financial sources', () => {
  const d = GLOBAL_CHECKPOINT_DEMO;
  assert.equal(d.financials.source, 'SYNTHETIC');
  assert.equal(d.financials.lastUpdatedAt, null);
  assert.ok(d.agents.every(a => a.confidence === null && a.dataStatus === 'SYNTHETIC'));
  assert.equal(d.kiasha.confidence, null);
  assert.deepEqual(demoFinancialRatios(d), { netMarginPct: 7, debtToAssetsPct: 40.91 });
  assert.equal(auditCheckpointDemo(d).checks.find(c => c.key === 'verified_source_and_date')?.passed, false);
});

test('Global demo scenarios exercise missing and invalid figures without mutating the fixture', () => {
  const base = GLOBAL_CHECKPOINT_DEMO;
  const original = structuredClone(base.financials);
  const missing = createCheckpointScenario(base, 'missing');
  const invalid = createCheckpointScenario(base, 'invalid');
  assert.deepEqual(base.financials, original);
  assert.equal(missing.financials.netIncome, null);
  assert.deepEqual(auditCheckpointDemo(missing).missing, ['netIncome']);
  assert.equal(demoFinancialRatios(missing).netMarginPct, null);
  assert.equal(auditCheckpointDemo(invalid).checks.find(c => c.key === 'liabilities_lte_assets')?.passed, false);
  assert.equal(auditCheckpointDemo(invalid).eligibleForInvestmentDecision, false);
  assert.equal(auditCheckpointDemo(missing).eligibleForInvestmentDecision, false);
});

test('local snapshot explanation reacts to invalid/missing figures and never calls the AI proxy', () => {
  const complete = explainDemoCompany(GLOBAL_CHECKPOINT_DEMO);
  const missing = explainDemoCompany(createCheckpointScenario(GLOBAL_CHECKPOINT_DEMO, 'missing'));
  const invalid = explainDemoCompany(createCheckpointScenario(GLOBAL_CHECKPOINT_DEMO, 'invalid'));
  for (const result of [complete, missing, invalid]) {
    assert.equal(result.proxyCalled, false);
    assert.equal(result.routeReserved, 'biap-ai-proxy');
    assert.equal(result.generatedBy, 'DETERMINISTIC_FIXTURE');
    assert.equal(result.eligibleForInvestmentDecision, false);
  }
  assert.notDeepEqual(complete.findings, missing.findings);
  assert.notDeepEqual(complete.findings, invalid.findings);
  assert.ok(missing.findings.some(f => /netIncome/.test(f)));
  assert.ok(invalid.findings.some(f => /Balance-sheet inconsistency/.test(f)));
});

test('Global broker selection is interactive but cannot trade or request credentials', () => {
  const d = GLOBAL_CHECKPOINT_DEMO;
  const initial = selectDemoBroker(d, null);
  const chosen = selectDemoBroker(d, d.brokerChoices[0].name);
  const unknown = selectDemoBroker(d, 'Unknown Broker');
  assert.equal(initial.selectedBroker, null);
  assert.equal(chosen.selectedBroker, d.brokerChoices[0].name);
  assert.equal(chosen.status, 'DEMO_SELECTION_ONLY');
  assert.equal(chosen.executionEnabled, false);
  assert.equal(chosen.credentialsRequested, false);
  assert.equal(chosen.orderSubmitted, false);
  assert.equal(chosen.countryEligibilityVerified, false);
  assert.equal(unknown.selectedBroker, null);
  assert.ok(d.brokerChoices.every(b => b.enabled === false));
});

test('Global financial quality rejects NaN, Infinity and negative assets while allowing genuine losses', () => {
  const base = GLOBAL_CHECKPOINT_DEMO;
  for (const [field, value] of [['revenue', Number.NaN], ['assets', -1], ['liabilities', Infinity]]) {
    const sample = structuredClone(base);
    sample.financials[field] = value;
    const audit = auditCheckpointDemo(sample);
    assert.deepEqual(audit.invalidValues, [field]);
    assert.equal(audit.checks.find(c => c.key === 'financial_values_valid')?.passed, false);
    assert.equal(audit.eligibleForInvestmentDecision, false);
  }
  const loss = structuredClone(base);
  loss.financials.netIncome = -500;
  assert.deepEqual(auditCheckpointDemo(loss).invalidValues, []);
  assert.ok(demoFinancialRatios(loss).netMarginPct < 0);
  const impossible = createCheckpointScenario(base, 'invalid');
  assert.equal(demoFinancialRatios(impossible).debtToAssetsPct, null);
});

test('invalid numeric snapshots never receive a plausible-financial summary', () => {
  for (const [field, value] of [['revenue', Number.NaN], ['assets', -1], ['liabilities', Infinity]]) {
    const sample = structuredClone(GLOBAL_CHECKPOINT_DEMO);
    sample.financials[field] = value;
    const result = explainDemoCompany(sample);
    assert.ok(result.findings.some(f => f.includes('Invalid numeric financial fields')));
    assert.ok(!result.findings.some(f => f.includes('plausible balance-sheet relationship')));
    assert.equal(result.proxyCalled, false);
    assert.equal(result.eligibleForInvestmentDecision, false);
  }
});

test('stored Global company API is accepted only with safe provenance and a valid bounded schema', () => {
  const good = {
    mode: 'SAVED_READ_ONLY', proxyCalled: false, eligibleForInvestmentDecision: false,
    ticker: 'ABC', country: 'US', exchange: 'NASDAQ', name: 'Example', currency: 'USD',
    ledger: { status: 'done', reason: null, source: 'LEDGER', analyzedAt: '2026-10-30' },
    evidence: { status: 'WARN', sourceProvider: null, reportPeriod: null },
    financials: { revenue: 100, net_income: null, total_assets: 200, total_liabilities: 70 },
    financialQuality: { coreComplete: false, coveragePct: 60 },
    audit: { method: 'DETERMINISTIC_STORED_CONSISTENCY', status: 'INCOMPLETE',
      externallyVerified: false, eligibleForInvestmentDecision: false,
      checks: [{ key: 'core', passed: false }, { key: 'balance', passed: null }, { key: 'source', passed: true }] },
    agents: [{ name: 'Fundamental', vote: null, confidence: null, reason: null, dataStatus: 'WARN' }],
    kiasha: { call: null, confidence: null, evidence: null },
    ai: { status: 'NOT_REQUESTED', proxyCalled: false, route: 'biap-ai-proxy' },
  };
  assert.equal(validateSavedGlobalCompany(good, 'US', 'NASDAQ', 'ABC').mode, 'SAVED_READ_ONLY');
  const mutate = (path, value) => {
    const copy = structuredClone(good);
    const keys = path.split('.');
    let node = copy;
    for (const key of keys.slice(0, -1)) node = node[key];
    node[keys.at(-1)] = value;
    return copy;
  };
  for (const [path, value] of [
    ['mode', 'DEMO'], ['proxyCalled', true], ['eligibleForInvestmentDecision', true],
    ['ticker', 'WRONG'], ['audit.externallyVerified', true],
    ['audit.eligibleForInvestmentDecision', true], ['ai.proxyCalled', true],
    ['financials.revenue', Infinity], ['financials.revenue', '100'],
    ['kiasha.confidence', NaN], ['agents', [{}]], ['audit.checks', []],
  ]) {
    assert.throws(() => validateSavedGlobalCompany(mutate(path, value), 'US', 'NASDAQ', 'ABC'), /provenance\/schema/, path);
  }
});

test('saved checkpoint reads require explicit non-production HTTPS staging host', () => {
  for (const base of [undefined, '', 'http://staging.example.org', 'https://biap.dadashi.no/global-api',
    'https://setai.no/global-api', 'https://localhost:3000', 'https://user:pass@staging.example.org',
    'https://5.249.252.88/global-api', 'https://127.0.0.2:443', 'https://[::1]/global-api',
    'https://0x7f000001/global-api', 'https://api.biap.dadashi.no/global-api',
    'https://localhost./global-api', 'https://dev.local/global-api',
    'https://example.org/global-api', 'https://api.example.org/global-api',
    'https://staging.example.org/global-api?redirect=prod',
    'https://staging.example.org/global-api#fragment']) {
    assert.throws(() => assertIsolatedCheckpointStagingBase(base), /staging|production/);
  }
  assert.equal(assertIsolatedCheckpointStagingBase('https://biap-staging.example.org/global-api/'),
    'https://biap-staging.example.org/global-api');
  assert.equal(assertIsolatedCheckpointStagingBase('https://api.dev.example.org/global-api'),
    'https://api.dev.example.org/global-api');
});


test('saved Global coverage is fail-closed, distinct from audit and trading eligibility', () => {
  const incomplete = {
    mode: 'SAVED_READ_ONLY', proxyCalled: false, eligibleForInvestmentDecision: false,
    ticker: 'ABC', country: 'US', exchange: 'NASDAQ', name: 'Example', currency: 'USD',
    ledger: { status: 'COMPLETE', reason: null, source: 'SAVED_LEDGER', analyzedAt: '2026-10-30' },
    evidence: { status: 'WARN', sourceProvider: null, reportPeriod: null },
    financials: { revenue: 100, net_income: null, total_assets: 200, total_liabilities: 70, total_equity: null },
    financialQuality: { coreComplete: false, coveragePct: 60 },
    audit: { method: 'DETERMINISTIC_STORED_CONSISTENCY', status: 'INCOMPLETE',
      externallyVerified: false, eligibleForInvestmentDecision: false,
      checks: [{ key: 'core', passed: false }, { key: 'balance', passed: null }, { key: 'source', passed: true }] },
    agents: [{ name: 'Fundamental', vote: null, confidence: null, reason: null, dataStatus: 'WARN' }],
    kiasha: { call: null, confidence: null, evidence: null },
    ai: { status: 'NOT_REQUESTED', proxyCalled: false, route: 'biap-ai-proxy' },
  };
  const partial = assessSavedGlobalCoverage(validateSavedGlobalCompany(incomplete, 'US', 'NASDAQ', 'ABC'));
  assert.equal(partial.complete, false);
  assert.deepEqual(partial.missing, ['financialStatements', 'sourceAndDate', 'evidencePass',
    'sixAgentVotes', 'kiasha', 'deterministicConsistency']);
  assert.equal(partial.eligibleForInvestmentDecision, false);
  const full = structuredClone(incomplete);
  full.financials.net_income = -1;
  full.financials.total_equity = 130;
  full.financialQuality.coreComplete = true;
  full.evidence.status = 'PASS';
  full.evidence.sourceProvider = 'OFFICIAL';
  full.evidence.reportPeriod = 'FY2025';
  full.audit.status = 'UNVERIFIED';
  full.audit.checks = full.audit.checks.map(c => ({ ...c, passed: true }));
  full.agents = Array.from({ length: 6 }, (_, i) => ({
    name: 'Agent' + i, vote: 0, confidence: 0.5, reason: 'Stored', dataStatus: 'PASS',
  }));
  full.kiasha = { call: 'HOLD', confidence: 0.6, evidence: 'Stored' };
  const covered = assessSavedGlobalCoverage(validateSavedGlobalCompany(full, 'US', 'NASDAQ', 'ABC'));
  assert.equal(covered.complete, true);
  assert.deepEqual(covered.missing, []);
  assert.equal(covered.eligibleForInvestmentDecision, false);
  full.agents[5].name = 'Agent0';
  assert.equal(assessSavedGlobalCoverage(full).checks.sixAgentVotes, false);
  full.agents[5].name = 'Agent5';
  full.audit.checks[0].passed = null;
  assert.equal(assessSavedGlobalCoverage(full).checks.deterministicConsistency, false);
});


test('stored Global explanation uses saved figures only, fails closed on missing and inconsistent data', () => {
  const base = {
    financials: { revenue: 100, net_income: -5, total_assets: 200, total_liabilities: 80, total_equity: 120 },
    ledger: { source: 'SAVED_LEDGER', analyzedAt: '2026-10-30T12:00:00Z' },
    evidence: { status: 'WARN', sourceProvider: null, reportPeriod: null },
    financialQuality: { coreComplete: true },
    audit: { status: 'UNVERIFIED', checks: [{ key: 'balance', passed: true }, { key: 'core', passed: true }, { key: 'source', passed: true }] },
    agents: [], kiasha: { call: null, confidence: null },
  };
  const saved = summarizeSavedGlobalCompany(base);
  assert.equal(saved.status, 'DETERMINISTIC_SAVED_SUMMARY');
  assert.equal(saved.generatedBy, 'LOCAL_RULES_ON_STORED_DATA');
  assert.equal(saved.proxyCalled, false);
  assert.equal(saved.eligibleForInvestmentDecision, false);
  assert.ok(saved.findings.some(f => f.includes('Net margin from stored figures: -5.00%')));
  assert.ok(saved.findings.some(f => f.includes('Liabilities/assets from stored figures: 40.00%')));
  assert.ok(saved.findings.some(f => f.includes('Missing or unverified display coverage')));

  const incomplete = structuredClone(base);
  incomplete.financials.net_income = null;
  incomplete.financials.revenue = 0;
  incomplete.audit.status = 'INCOMPLETE';
  const missing = summarizeSavedGlobalCompany(incomplete);
  assert.ok(missing.findings.some(f => f.includes('Net margin unavailable')));
  assert.ok(!missing.findings.some(f => f.includes('Net margin from stored figures')));

  const inconsistent = structuredClone(base);
  inconsistent.financials.total_liabilities = 250;
  inconsistent.audit.status = 'INCONSISTENT';
  const invalid = summarizeSavedGlobalCompany(inconsistent);
  assert.ok(invalid.findings.some(f => f.includes('fail one or more')));
  assert.ok(invalid.findings.some(f => f.includes('Liabilities/assets unavailable or inconsistent')));
  assert.equal(invalid.proxyCalled, false);
  assert.equal(invalid.eligibleForInvestmentDecision, false);
});


test('Global AI explanation requires verified proxy provenance and never enables trading', () => {
  const good = {
    mode: 'SAVED_AI_EXPLANATION', route: 'biap-ai-proxy', proxyCalled: true,
    eligibleForInvestmentDecision: false, country: 'US', exchange: 'NASDAQ', ticker: 'ABC',
    dataAnalyzedAt: '2026-10-30T12:00:00Z', generatedAt: '2026-11-01T10:00:00Z',
    model: 'proxy-test', report: 'Missing financial evidence is explicit.',
    disclaimer: 'Not an audit or investment recommendation.',
  };
  assert.equal(validateSavedGlobalAiReport(good, 'US', 'NASDAQ', 'ABC').proxyCalled, true);
  for (const [key, value] of [
    ['mode', 'DEMO'], ['route', 'external-vendor'], ['proxyCalled', false],
    ['eligibleForInvestmentDecision', true], ['ticker', 'OTHER'],
    ['report', ''], ['report', 'x'.repeat(12001)], ['model', ''],
  ]) {
    assert.throws(() => validateSavedGlobalAiReport({ ...good, [key]: value }, 'US', 'NASDAQ', 'ABC'));
  }
});


test('Global saved-company and AI responses from prior selections cannot overwrite current data', async () => {
  const saved = createCheckpointRequestGuard();
  const ai = createCheckpointRequestGuard();
  let finishOld;
  let finishNew;
  const oldResponse = new Promise(resolve => { finishOld = resolve; });
  const newResponse = new Promise(resolve => { finishNew = resolve; });
  const applied = [];
  const apply = async (guard, promise) => {
    const version = guard.begin();
    const result = await promise;
    if (guard.isCurrent(version)) applied.push(result);
  };
  const oldPending = apply(saved, oldResponse);
  saved.invalidate(); // User changes the country, exchange or ticker.
  ai.invalidate(); // Any pending AI explanation must also be discarded.
  const newPending = apply(saved, newResponse);
  finishNew('new issuer');
  await newPending;
  finishOld('old issuer');
  await oldPending;
  assert.deepEqual(applied, ['new issuer']);
  let finishAi;
  const pendingAi = new Promise(resolve => { finishAi = resolve; });
  const aiPending = apply(ai, pendingAi);
  ai.invalidate(); // User changes issuer while the proxy is processing.
  finishAi('old issuer AI');
  await aiPending;
  assert.deepEqual(applied, ['new issuer']);
});
