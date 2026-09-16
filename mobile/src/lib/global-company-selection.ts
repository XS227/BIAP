import AsyncStorage from '@react-native-async-storage/async-storage';
import type { GlobalInstrument } from '@/lib/global-api';

const STORAGE_KEY = 'biap-global:selected-company:v1';
let memoryValue: GlobalInstrument | null | undefined;
const listeners = new Set<(value: GlobalInstrument | null) => void>();

function normalize(input: GlobalInstrument): GlobalInstrument {
  return {
    country: String(input.country || '').trim().toUpperCase(),
    exchange: String(input.exchange || '').trim().toUpperCase(),
    mic_code: input.mic_code ? String(input.mic_code).trim().toUpperCase() : null,
    currency: String(input.currency || '').trim().toUpperCase(),
    ticker: String(input.ticker || '').trim(),
    name: String(input.name || input.ticker || '').trim(),
    isin: input.isin ? String(input.isin).trim().toUpperCase() : null,
    lei: input.lei ? String(input.lei).trim().toUpperCase() : null,
    sector: input.sector ? String(input.sector).trim() : null,
    industry: input.industry ? String(input.industry).trim() : null,
    lot_size: input.lot_size == null ? null : Number(input.lot_size),
  };
}

function valid(value: GlobalInstrument | null | undefined): value is GlobalInstrument {
  return Boolean(
    value &&
    /^[A-Z]{2}$/.test(String(value.country || '').toUpperCase()) &&
    String(value.exchange || '').trim() &&
    String(value.ticker || '').trim() &&
    /^[A-Z]{3}$/.test(String(value.currency || '').toUpperCase())
  );
}

export async function getSelectedGlobalCompany(): Promise<GlobalInstrument | null> {
  if (memoryValue !== undefined) return memoryValue;
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (!raw) {
      memoryValue = null;
      return null;
    }
    const parsed = normalize(JSON.parse(raw) as GlobalInstrument);
    memoryValue = valid(parsed) ? parsed : null;
    return memoryValue;
  } catch {
    memoryValue = null;
    return null;
  }
}

export async function setSelectedGlobalCompany(value: GlobalInstrument | null): Promise<void> {
  if (!value) {
    memoryValue = null;
    await AsyncStorage.removeItem(STORAGE_KEY);
    listeners.forEach((listener) => listener(null));
    return;
  }
  const next = normalize(value);
  if (!valid(next)) throw new Error('Invalid global company selection');
  memoryValue = next;
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  listeners.forEach((listener) => listener(next));
}

export function subscribeSelectedGlobalCompany(listener: (value: GlobalInstrument | null) => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
