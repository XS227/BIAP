type EquityLike = {
  ticker?: string | null;
  name?: string | null;
};

const STRUCTURED_PREFIXES = [
  'BULL',
  'BEAR',
  'MINI',
  'TURBO',
  'BEST',
  'FAKTOR',
  'TRACKER',
  'CERT',
  'WARRANT',
];

const STRUCTURED_NAME_MARKERS = [
  'KNOCK OUT',
  'LEVERAGE',
  'WARRANT',
  'CERTIFICATE',
  'MINI FUTURE',
  'TURBO',
];

function normalized(value: string | null | undefined) {
  return String(value || '').trim().toUpperCase().replace(/\s+/g, ' ');
}

export function isSupportedGlobalEquityInstrument(item: EquityLike) {
  const ticker = normalized(item.ticker);
  const name = normalized(item.name);
  if (!ticker) return false;

  if (ticker.includes('.AVA.') || ticker.endsWith('.AVA')) return false;

  const firstToken = ticker.split(/[.\s_-]+/, 1)[0];
  if (STRUCTURED_PREFIXES.includes(firstToken)) return false;

  if (STRUCTURED_NAME_MARKERS.some((marker) => name.includes(marker))) return false;

  return true;
}

export function unsupportedGlobalInstrumentMessage(item: EquityLike) {
  const ticker = normalized(item.ticker) || 'This instrument';
  return `${ticker} is not an ordinary listed equity. BIAP Stock Analysis currently supports company shares only, not leveraged certificates, mini futures, warrants or similar structured products.`;
}
