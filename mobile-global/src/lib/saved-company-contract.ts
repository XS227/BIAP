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
  if (!record(payload) || payload.mode !== 'SAVED_READ_ONLY' ||
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
  if (!record(ledger) || !record(evidence) || !record(financials) ||
      !record(quality) || !record(audit) || !Array.isArray(agents) ||
      !record(kiasha) || !record(ai)) fail();

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
      !audit.checks.every(c => record(c) && typeof c.key === 'string' &&
        (c.passed === true || c.passed === false || c.passed === null))) fail();

  if (agents.length > 12 || !agents.every(a => record(a) &&
      textOrNull(a.name) && numberOrNull(a.vote) && numberOrNull(a.confidence) &&
      textOrNull(a.reason) && textOrNull(a.dataStatus)) ||
      !textOrNull(kiasha.call) || !numberOrNull(kiasha.confidence) ||
      !textOrNull(kiasha.evidence)) fail();

  if (ai.status !== 'NOT_REQUESTED' || ai.proxyCalled !== false ||
      ai.route !== 'biap-ai-proxy') fail();
  return payload as SavedGlobalCompanyView;
}
