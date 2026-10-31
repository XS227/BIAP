// Fail-closed validation for the development-only saved Global ledger view.
// A TypeScript cast is not a runtime check: staging responses may be partial or stale.
import type { SavedGlobalCompanyView } from './global-api';

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
  if (!url.hostname || url.username || url.password ||
      ['biap.dadashi.no', 'setai.no', 'www.setai.no', 'localhost', '127.0.0.1'].includes(url.hostname.toLowerCase())) {
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
