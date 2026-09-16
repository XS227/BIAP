import AsyncStorage from '@react-native-async-storage/async-storage';

export type GlobalMarketSelection = {
  country: string;
  countryName: string;
  exchange: string;
  exchangeLabel: string;
  mic?: string | null;
  currency: string;
};

const STORAGE_KEY = 'biap-global:market-selection:v1';

export const DEFAULT_GLOBAL_MARKET: GlobalMarketSelection = {
  country: 'US',
  countryName: 'United States',
  exchange: 'NASDAQ',
  exchangeLabel: 'Nasdaq',
  mic: 'XNAS',
  currency: 'USD',
};

const listeners = new Set<(selection: GlobalMarketSelection) => void>();
let memoryValue: GlobalMarketSelection | null = null;

function normalize(value: GlobalMarketSelection): GlobalMarketSelection {
  return {
    country: String(value.country || '').trim().toUpperCase(),
    countryName: String(value.countryName || value.country || '').trim(),
    exchange: String(value.exchange || '').trim().toUpperCase(),
    exchangeLabel: String(value.exchangeLabel || value.exchange || '').trim(),
    mic: value.mic ? String(value.mic).trim().toUpperCase() : null,
    currency: String(value.currency || '').trim().toUpperCase(),
  };
}

function valid(value: GlobalMarketSelection | null | undefined): value is GlobalMarketSelection {
  return Boolean(
    value &&
    /^[A-Z]{2}$/.test(String(value.country || '').toUpperCase()) &&
    String(value.exchange || '').trim() &&
    /^[A-Z]{3}$/.test(String(value.currency || '').toUpperCase())
  );
}

export async function getGlobalMarketSelection(): Promise<GlobalMarketSelection> {
  if (memoryValue) return memoryValue;
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = normalize(JSON.parse(raw) as GlobalMarketSelection);
      if (valid(parsed)) {
        memoryValue = parsed;
        return parsed;
      }
    }
  } catch {
    // Fall through to the explicit default; never fabricate market data.
  }
  memoryValue = DEFAULT_GLOBAL_MARKET;
  return DEFAULT_GLOBAL_MARKET;
}

export async function setGlobalMarketSelection(value: GlobalMarketSelection): Promise<GlobalMarketSelection> {
  const next = normalize(value);
  if (!valid(next)) throw new Error('Invalid country/exchange/currency selection');
  memoryValue = next;
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  listeners.forEach((listener) => listener(next));
  return next;
}

export function subscribeGlobalMarketSelection(listener: (selection: GlobalMarketSelection) => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
