import AsyncStorage from '@react-native-async-storage/async-storage';
import type { MarketSymbolResult } from '@/lib/api';

const KEY = 'biap:favorites:v1';

export type FavoriteSymbol = Pick<MarketSymbolResult, 'code' | 'symbol' | 'name' | 'market'> & { addedAt: string };

async function read(): Promise<FavoriteSymbol[]> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

async function write(items: FavoriteSymbol[]): Promise<void> {
  await AsyncStorage.setItem(KEY, JSON.stringify(items));
}

export async function listFavorites(): Promise<FavoriteSymbol[]> {
  return read();
}

export async function isFavorite(code: string): Promise<boolean> {
  const key = code.trim().toUpperCase();
  return (await read()).some((item) => item.code.trim().toUpperCase() === key);
}

export async function toggleFavorite(symbol: MarketSymbolResult): Promise<boolean> {
  const items = await read();
  const key = symbol.code.trim().toUpperCase();
  const index = items.findIndex((item) => item.code.trim().toUpperCase() === key);
  if (index >= 0) {
    items.splice(index, 1);
    await write(items);
    return false;
  }
  items.unshift({ code: symbol.code, symbol: symbol.symbol, name: symbol.name, market: symbol.market, addedAt: new Date().toISOString() });
  await write(items.slice(0, 300));
  return true;
}
