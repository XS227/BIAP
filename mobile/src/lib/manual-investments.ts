import AsyncStorage from '@react-native-async-storage/async-storage';

export type ManualInvestmentStatus = 'OPEN' | 'SOLD';

export type ManualInvestment = {
  id: string;
  code: string;
  symbol: string;
  quantity: number;
  buyPrice: number;
  buyNotional: number;
  boughtAt: string;
  status: ManualInvestmentStatus;
  soldAt?: string;
  sellPrice?: number;
  sellNotional?: number;
  source: 'MANUAL_BROKER';
};

const STORAGE_KEY = 'kiasha:manual-investments:v1';

async function readAll(): Promise<ManualInvestment[]> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

async function writeAll(items: ManualInvestment[]): Promise<void> {
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

export async function listManualInvestments(): Promise<ManualInvestment[]> {
  return readAll();
}

export async function findOpenManualInvestment(code: string): Promise<ManualInvestment | null> {
  const key = code.trim().toUpperCase();
  const items = await readAll();
  return items.find((x) => x.status === 'OPEN' && x.code.trim().toUpperCase() === key) ?? null;
}

export async function confirmManualBuy(input: {
  code: string;
  symbol: string;
  quantity: number;
  buyPrice: number;
}): Promise<ManualInvestment> {
  const quantity = Math.max(1, Math.floor(input.quantity));
  if (!Number.isFinite(input.buyPrice) || input.buyPrice <= 0) throw new Error('قیمت خرید معتبر نیست.');
  const items = await readAll();
  const existing = items.find((x) => x.status === 'OPEN' && x.code.trim().toUpperCase() === input.code.trim().toUpperCase());
  if (existing) return existing;
  const item: ManualInvestment = {
    id: `manual_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    code: input.code,
    symbol: input.symbol,
    quantity,
    buyPrice: input.buyPrice,
    buyNotional: quantity * input.buyPrice,
    boughtAt: new Date().toISOString(),
    status: 'OPEN',
    source: 'MANUAL_BROKER',
  };
  items.unshift(item);
  await writeAll(items);
  return item;
}

export async function confirmManualSell(id: string, sellPrice: number): Promise<ManualInvestment | null> {
  if (!Number.isFinite(sellPrice) || sellPrice <= 0) throw new Error('قیمت فروش معتبر نیست.');
  const items = await readAll();
  const index = items.findIndex((x) => x.id === id && x.status === 'OPEN');
  if (index < 0) return null;
  const current = items[index];
  const updated: ManualInvestment = {
    ...current,
    status: 'SOLD',
    soldAt: new Date().toISOString(),
    sellPrice,
    sellNotional: current.quantity * sellPrice,
  };
  items[index] = updated;
  await writeAll(items);
  return updated;
}
