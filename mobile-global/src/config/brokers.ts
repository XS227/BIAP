/**
 * Licensed brokers BIAP can hand a user off to. THIS FILE IS THE ONLY PLACE for broker names,
 * URLs and market coverage. BIAP has no trading API with any of them: it only opens the
 * broker's official public website/app in the external browser.
 *
 * Rules:
 *  - `home` must be the broker's official public site. No affiliate or tracking parameters.
 *  - `deepLink` stays null unless the broker documents a PUBLIC instrument deep link. None is
 *    verified today, so no instrument is pre-filled; the user searches the ticker/ISIN there.
 *  - `markets` = ISO country codes whose coverage was CHECKED on the broker's own official page
 *    (2026-11-03); the page is in `coverageSource`. A market that could not be confirmed there is
 *    NOT listed, so the app does not offer that broker for it. Availability still depends on
 *    the user's residence and account type, hence AVAILABILITY_NOTE.
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
  /** Official page the `markets` list was checked against. */
  coverageSource: string;
  /** What was and was not confirmed. */
  coverageNote: string;
};

export const AVAILABILITY_NOTE = "Availability may vary; check the broker's site." as const;

export const BROKER_ASSET_CLASSES = 'Stocks and ETFs only' as const;

export const BROKERS: readonly BrokerConfig[] = [
  {
    id: 'ibkr', name: 'Interactive Brokers', home: 'https://www.interactivebrokers.com/', deepLink: null,
    markets: ['FR'],
    coverageSource: 'https://www.interactivebrokers.com/en/accounts/trading-and-market-data.php',
    coverageNote: 'Official pages returned HTTP 403 to automated fetch; only France was seen named in an official result. Other markets NOT confirmed, so not offered. Owner to verify in a browser.',
  },
  {
    id: 'nordnet', name: 'Nordnet', home: 'https://www.nordnet.no/', deepLink: null,
    homeByCountry: { NO: 'https://www.nordnet.no/', SE: 'https://www.nordnet.se/', DK: 'https://www.nordnet.dk/', FI: 'https://www.nordnet.fi/' },
    markets: ['NO', 'SE', 'DK', 'FI'],
    coverageSource: 'https://www.nordnet.no/faq/handel/handelsplassene-vare/handelsplassene-vare',
    coverageNote: 'Nasdaq Stockholm/Copenhagen/Helsinki and Euronext Oslo (plus First North/Growth) listed by Nordnet.',
  },
  {
    id: 'saxo', name: 'Saxo', home: 'https://www.home.saxo/', deepLink: null,
    markets: ['US', 'FR', 'NL', 'PT'],
    coverageSource: 'https://www.home.saxo/products/equities',
    coverageNote: 'Page names main US exchanges and Euronext Amsterdam, Lisbon, Paris; says "over 25 countries" without a list. Others NOT confirmed.',
  },
  {
    id: 'degiro', name: 'DEGIRO', home: 'https://www.degiro.com/', deepLink: null,
    markets: ['US', 'GB', 'DE', 'FR', 'IT', 'NL', 'ES', 'PT', 'SE', 'NO', 'DK', 'FI'],
    coverageSource: 'https://www.degiro.com/uk/products-and-markets',
    coverageNote: 'Lists NASDAQ/NYSE, LSE, Xetra, Euronext Paris/Amsterdam/Lisbon/Milan, Madrid, Oslo, Nasdaq Stockholm/Copenhagen/Helsinki.',
  },
  {
    id: 'trading212', name: 'Trading 212', home: 'https://www.trading212.com/', deepLink: null,
    markets: ['US', 'GB', 'DE', 'FR', 'IT', 'NL', 'ES', 'PT'],
    coverageSource: 'https://helpcentre.trading212.com/hc/en-us/articles/360008818178-What-are-the-markets-opening-and-closing-times',
    coverageNote: 'Help-centre hours article lists LSE, NYSE/NASDAQ, Xetra, Euronext Amsterdam/Paris/Lisbon/Milan, Madrid. Varies by account type, country and Trading 212 entity.',
  },
];
