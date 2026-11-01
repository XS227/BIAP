// Fail-closed validation for the development-only saved Global ledger view.
// A TypeScript cast is not a runtime check: staging responses may be partial or stale.
import type { SavedGlobalCompanyView, SavedGlobalAiReport } from './global-api';

const record = (v: unknown): v is Record<string, unknown> =>
  v !== null && typeof v === 'object' && !Array.isArray(v);
const textOrNull = (v: unknown): v is string | null => v === null || typeof v === 'string';
const numberOrNull = (v: unknown): v is number | null =>
  v === null || (typeof v === 'number' && Number.isFinite(v));
const fail = (): never => { throw new Error('Stored analysis response failed read-only provenance/schema validation.'); };

export function validateSavedGlobalCompany(
  payload: unknown, country: string, exchange: string, ticker: string,
): SavedGlobalCompanyView {
  if (!record(payload)) return fail();
  if (payload.mode !== 'SAVED_READ_ONLY' ||
      payload.proxyCalled !== false || payload.eligibleForInvestmentDecision !== false ||
      payload.country !== country.trim().toUpperCase() ||
      payload.exchange !== exchange.trim().toUpperCase() ||
      payload.ticker !== ticker.trim().toUpperCase()) fail();

  const ledger = payload.ledger;
  const evidence = payload.evidence;
  const financials = payload.financials;
  const quality = payload.financialQuality;
  const audit = payload.audit;
  const agents = payload.agents;
  const kiasha = payload.kiasha;
  const ai = payload.ai;
  if (!record(ledger)) return fail();
  if (!record(evidence)) return fail();
  if (!record(financials)) return fail();
  if (!record(quality)) return fail();
  if (!record(audit)) return fail();
  if (!Array.isArray(agents)) return fail();
  if (!record(kiasha)) return fail();
  if (!record(ai)) return fail();

  if (!textOrNull(payload.name) || !textOrNull(payload.currency) ||
      !['status', 'reason', 'source', 'analyzedAt'].every(k => textOrNull(ledger[k])) ||
      !['status', 'sourceProvider', 'reportPeriod'].every(k => textOrNull(evidence[k])) ||
      !Object.keys(financials).length || Object.keys(financials).length > 32 ||
      !Object.values(financials).every(numberOrNull) ||
      typeof quality.coreComplete !== 'boolean' ||
      !(quality.coveragePct === undefined || numberOrNull(quality.coveragePct))) fail();

  if (audit.method !== 'DETERMINISTIC_STORED_CONSISTENCY' ||
      !['UNVERIFIED', 'INCOMPLETE', 'INCONSISTENT'].includes(String(audit.status)) ||
      audit.externallyVerified !== false ||
      audit.eligibleForInvestmentDecision !== false ||
      !Array.isArray(audit.checks) || audit.checks.length < 3 || audit.checks.length > 30 ||
      !audit.checks.every((c: unknown) => record(c) && typeof c.key === 'string' &&
        (c.passed === true || c.passed === false || c.passed === null))) fail();

  if (agents.length > 12 || !agents.every((a: unknown) => record(a) &&
      textOrNull(a.name) && numberOrNull(a.vote) && numberOrNull(a.confidence) &&
      textOrNull(a.reason) && textOrNull(a.dataStatus)) ||
      !textOrNull(kiasha.call) || !numberOrNull(kiasha.confidence) ||
      !textOrNull(kiasha.evidence)) fail();

  if (ai.status !== 'NOT_REQUESTED' || ai.proxyCalled !== false ||
      ai.route !== 'biap-ai-proxy') fail();
  return payload as unknown as SavedGlobalCompanyView;
}

/** The checkpoint must never accidentally query the default production API. */
export function assertIsolatedCheckpointStagingBase(configured: string | undefined): string {
  if (!configured || !/^https:\/\//i.test(configured)) {
    throw new Error('Set an explicit HTTPS staging API base for saved checkpoint reads.');
  }
  const url = new URL(configured);
  const host = url.hostname.toLowerCase().replace(/\.$/, '');
  // Never send saved financial records to a direct server IP, loopback,
  // private hostname, or a subdomain of the known production API.
  // URL canonicalizes alternate IPv4 spellings (e.g. 0x7f000001).
  const directIp = /^\d+\.\d+\.\d+\.\d+$/.test(host) || host.startsWith('[');
  const forbiddenHost = host === 'localhost' || host.endsWith('.localhost') ||
    host.endsWith('.local') || host === 'setai.no' || host === 'www.setai.no' ||
    host === 'biap.dadashi.no' || host.endsWith('.biap.dadashi.no');
  // An arbitrary HTTPS domain is not evidence of isolation. Require an
  // explicit staging/dev/sandbox DNS label, as the read-only API sampler does.
  // This is a naming guard, not a substitute for verifying deployment isolation.
  const labels = host.split('.');
  const hasStagingLabel = labels.length >= 3 && labels.slice(0, -2).some(label =>
    ['staging', 'dev', 'sandbox'].includes(label) ||
    ['staging-', 'dev-', 'sandbox-'].some(prefix => label.startsWith(prefix)) ||
    ['-staging', '-dev', '-sandbox'].some(suffix => label.endsWith(suffix))
  );
  if (!host || url.username || url.password || directIp || forbiddenHost ||
      !hasStagingLabel || url.hash || url.search) {
    throw new Error('Saved checkpoint reads require an isolated staging host, not production.');
  }
  return configured.replace(/\/$/, '');
}

/**
 * Display-coverage gate for already stored analysis only. This is NOT a
 * financial audit, AI verification, trading approval, or Checkpoint 1 signoff.
 * Partial saved records remain viewable, but their missing fields are explicit.
 */
export function assessSavedGlobalCoverage(view: SavedGlobalCompanyView) {
  const required = ['revenue', 'net_income', 'total_assets', 'total_liabilities', 'total_equity'];
  const agentNames = view.agents.map(agent => agent.name?.trim()).filter((name): name is string => Boolean(name));
  const checks = {
    financialStatements: view.financialQuality.coreComplete === true &&
      required.every(key => typeof view.financials[key] === 'number' && Number.isFinite(view.financials[key])),
    sourceAndDate: Boolean(view.ledger.source?.trim() && view.ledger.analyzedAt?.trim() &&
      view.evidence.sourceProvider?.trim() && view.evidence.reportPeriod?.trim()),
    evidencePass: view.evidence.status === 'PASS',
    sixAgentVotes: new Set(agentNames).size >= 6 &&
      view.agents.every(agent => Boolean(agent.name?.trim()) &&
        typeof agent.vote === 'number' && Number.isFinite(agent.vote) &&
        typeof agent.confidence === 'number' && Number.isFinite(agent.confidence)),
    kiasha: Boolean(view.kiasha.call?.trim()) &&
      typeof view.kiasha.confidence === 'number' && Number.isFinite(view.kiasha.confidence),
    deterministicConsistency: view.audit.status === 'UNVERIFIED' &&
      view.audit.checks.length >= 3 && view.audit.checks.every(check => check.passed === true),
  };
  const missing = Object.entries(checks).filter(([, passed]) => !passed).map(([key]) => key);
  return { complete: missing.length === 0, checks, missing, eligibleForInvestmentDecision: false as const };
}


/**
 * Explain an already stored Global snapshot using transparent arithmetic only.
 * This never invokes biap-ai-proxy, recomputes agent decisions or turns
 * incomplete evidence into a BUY/SELL recommendation.
 */
export function summarizeSavedGlobalCompany(view: SavedGlobalCompanyView) {
  const coverage = assessSavedGlobalCoverage(view);
  const findings: string[] = [];
  const f = view.financials;
  const revenue = f.revenue;
  const netIncome = f.net_income;
  const assets = f.total_assets;
  const liabilities = f.total_liabilities;

  if (view.audit.status === 'INCONSISTENT') {
    findings.push('Stored financial figures fail one or more deterministic consistency checks.');
  } else if (view.audit.status === 'INCOMPLETE') {
    findings.push('Stored financial statements are incomplete; missing amounts were not estimated.');
  } else {
    findings.push('Stored figures passed local consistency checks; this is not external verification.');
  }
  if (typeof revenue === 'number' && Number.isFinite(revenue) && revenue > 0 &&
      typeof netIncome === 'number' && Number.isFinite(netIncome)) {
    findings.push('Net margin from stored figures: ' + (100 * netIncome / revenue).toFixed(2) + '%.');
  } else {
    findings.push('Net margin unavailable: verified revenue and net income figures are required.');
  }
  if (typeof assets === 'number' && Number.isFinite(assets) && assets > 0 &&
      typeof liabilities === 'number' && Number.isFinite(liabilities) && liabilities >= 0 &&
      liabilities <= assets) {
    findings.push('Liabilities/assets from stored figures: ' + (100 * liabilities / assets).toFixed(2) + '%.');
  } else {
    findings.push('Liabilities/assets unavailable or inconsistent.');
  }
  findings.push('Stored source: ' + (view.ledger.source || 'unavailable') +
    '; analyzed: ' + (view.ledger.analyzedAt || 'unavailable') +
    '; evidence: ' + (view.evidence.status || 'unverified') + '.');
  if (!coverage.complete) {
    findings.push('Missing or unverified display coverage: ' + coverage.missing.join(', ') + '.');
  }
  findings.push('No new agent run, AI proxy call, market quote verification or trade authorization.');
  return {
    status: 'DETERMINISTIC_SAVED_SUMMARY' as const,
    generatedBy: 'LOCAL_RULES_ON_STORED_DATA' as const,
    proxyCalled: false as const,
    findings,
    eligibleForInvestmentDecision: false as const,
  };
}


/** An AI report is never an investment decision and cannot be confused with a fixture. */
export function validateSavedGlobalAiReport(
  payload: unknown, country: string, exchange: string, ticker: string,
): SavedGlobalAiReport {
  if (!record(payload) ||
      payload.mode !== 'SAVED_AI_EXPLANATION' || payload.route !== 'biap-ai-proxy' ||
      payload.proxyCalled !== true || payload.eligibleForInvestmentDecision !== false ||
      payload.country !== country.trim().toUpperCase() ||
      payload.exchange !== exchange.trim().toUpperCase() ||
      payload.ticker !== ticker.trim().toUpperCase() ||
      typeof payload.report !== 'string' || !payload.report.trim() || payload.report.length > 12000 ||
      typeof payload.model !== 'string' || !payload.model.trim() || payload.model.length > 120 ||
      typeof payload.generatedAt !== 'string' || !payload.generatedAt.trim() ||
      !textOrNull(payload.dataAnalyzedAt) ||
      typeof payload.disclaimer !== 'string' || !payload.disclaimer.trim()) {
    throw new Error('AI proxy explanation failed provenance/schema validation.');
  }
  return payload as unknown as SavedGlobalAiReport;
}
