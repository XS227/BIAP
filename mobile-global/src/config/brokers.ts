/**
 * Licensed brokers BIAP can hand a user off to. THIS FILE IS THE ONLY PLACE for broker names,
 * URLs and market coverage. BIAP has no trading API with any of them: it only opens the
 * broker's official public website/app in the external browser.
 *
 * Rules:
 *  - `home` must be the broker's official public site. No affiliate or tracking parameters.
 *  - `deepLink` stays null unless the broker documents a PUBLIC instrument deep link. None is
 *    verified today, so no instrument is pre-filled; the user searches the ticker/ISIN there.
 *  - `markets` = ISO country codes of the listings the broker is expected to cover. The owner
 *    must verify these against each broker's current market list before release (see
 *    docs/mobile/BROKER_COVERAGE_TO_VERIFY.md); the app trusts this file as written.
 */
export type BrokerConfig = {
  id: string;
  name: string;
  /** Official site; per-country override when the broker runs country sites. */
  home: string;
  homeByCountry?: Record<string, string>;
  /** `{isin}` / `{ticker}` placeholders; only set when a public deep link is documented. */
  deepLink: string | null;
  markets: readonly string[];
};

export const BROKER_ASSET_CLASSES = 'Stocks and ETFs only' as const;

export const BROKERS: readonly BrokerConfig[] = [
  {
    id: 'ibkr', name: 'Interactive Brokers', home: 'https://www.interactivebrokers.com/', deepLink: null,
    markets: ['US', 'GB', 'DE', 'FR', 'IT', 'NL', 'ES', 'PT', 'SE', 'NO', 'DK', 'FI'],
  },
  {
    id: 'nordnet', name: 'Nordnet', home: 'https://www.nordnet.no/', deepLink: null,
    homeByCountry: { NO: 'https://www.nordnet.no/', SE: 'https://www.nordnet.se/', DK: 'https://www.nordnet.dk/', FI: 'https://www.nordnet.fi/' },
    markets: ['NO', 'SE', 'DK', 'FI'],
  },
  {
    id: 'saxo', name: 'Saxo', home: 'https://www.home.saxo/', deepLink: null,
    markets: ['US', 'GB', 'DE', 'FR', 'IT', 'NL', 'ES', 'PT', 'SE', 'NO', 'DK', 'FI'],
  },
  {
    id: 'degiro', name: 'DEGIRO', home: 'https://www.degiro.com/', deepLink: null,
    markets: ['US', 'GB', 'DE', 'FR', 'IT', 'NL', 'ES', 'PT', 'SE', 'NO', 'DK', 'FI'],
  },
  {
    id: 'trading212', name: 'Trading 212', home: 'https://www.trading212.com/', deepLink: null,
    markets: ['US', 'GB', 'DE', 'FR', 'IT', 'NL', 'ES'],
  },
];
