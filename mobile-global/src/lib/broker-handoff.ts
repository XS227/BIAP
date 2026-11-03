import { BROKERS, type BrokerConfig } from '../config/brokers.ts';

export const LEAVE_NOTICE =
  'You will leave BIAP and go to the broker’s official platform. BIAP has no trading API with this broker and never receives your orders, passwords or funds.';

export type HandoffInstrument = { country?: string | null; ticker?: string | null; isin?: string | null };

export function normalizeCountry(country: string | null | undefined): string {
  const c = String(country || '').trim().toUpperCase();
  return c === 'UK' ? 'GB' : c;
}

/** Only brokers whose configured coverage includes the instrument's country. */
export function brokersForMarket(country: string | null | undefined, list: readonly BrokerConfig[] = BROKERS): BrokerConfig[] {
  const c = normalizeCountry(country);
  if (!c) return [];
  return list.filter((b) => b.markets.includes(c));
}

export type Handoff = { url: string; prefilled: boolean };

/** Public https URL to open externally. Pre-fills the instrument only when a deep link is configured. */
export function buildHandoff(broker: BrokerConfig, instrument: HandoffInstrument): Handoff {
  const c = normalizeCountry(instrument.country);
  const base = broker.homeByCountry?.[c] || broker.home;
  if (broker.deepLink && (instrument.isin || instrument.ticker)) {
    const url = broker.deepLink
      .replace('{isin}', encodeURIComponent(String(instrument.isin || '')))
      .replace('{ticker}', encodeURIComponent(String(instrument.ticker || '')));
    if (/^https:\/\//.test(url) && !/\{[a-z]+\}/.test(url)) return { url, prefilled: true };
  }
  return { url: base, prefilled: false };
}
