// External, non-affiliate broker destinations. Market eligibility is indicative only;
// residency, instrument availability and account permissions must be checked at the broker.
export type Broker = { id: string; name: string; url: string; countries: readonly string[]; affiliateUrl?: string };
export const BROKER_EXIT_NOTICE = 'You will leave BIAP and go to the broker\'s official platform. BIAP has no trading API with this broker and never receives your orders, passwords or funds.';
export const BROKERS: readonly Broker[] = [
  { id: 'ibkr', name: 'Interactive Brokers', url: 'https://www.interactivebrokers.com/', countries: ['US','GB','DE','FR','NL','IT','ES','NO','SE','FI','DK'] },
  { id: 'nordnet', name: 'Nordnet', url: 'https://www.nordnet.no/', countries: ['NO','SE','DK','FI'] },
  { id: 'saxo', name: 'Saxo', url: 'https://www.home.saxo/', countries: ['US','GB','DE','FR','NL','IT','ES','NO','SE','FI','DK'] },
  { id: 'degiro', name: 'DEGIRO', url: 'https://www.degiro.com/', countries: ['US','GB','DE','FR','NL','IT','ES','FI','SE','DK'] },
  { id: 'trading212', name: 'Trading 212', url: 'https://www.trading212.com/', countries: ['US','GB','DE','FR','NL','ES'] },
];
// Local preference only. Never implies KYC, execution permission or an order.
export function brokerPreferenceKey(country: string): string | null {
  const code = String(country || '').trim().toUpperCase();
  return /^[A-Z]{2}$/.test(code) && brokersForMarket(code).length
    ? `biap-global:broker-preference:v1:${code}` : null;
}

export function resolveBrokerPreference(country: string, id: string | null | undefined): Broker | null {
  return brokersForMarket(country).find(broker => broker.id === id) ?? null;
}

export function brokersForMarket(country: string): Broker[] {
  const code = String(country || '').trim().toUpperCase();
  return BROKERS.filter(broker => broker.countries.includes(code));
}
