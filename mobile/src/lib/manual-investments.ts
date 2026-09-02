import AsyncStorage from '@react-native-async-storage/async-storage';
import { KIASHA_API_BASE } from '@/lib/api';
import { authFetch } from '@/lib/auth-session';

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
  /** True when the server is authoritative for this record. */
  serverBacked?: boolean;
};

type ManualTradeResponse = {
  positions?: ManualInvestment[];
};

const STORAGE_KEY = 'kiasha:manual-investments:v1';
const REMOTE_PATH = '/performance/ai/manual-trades';

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

function syncKey(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`.slice(0, 128);
}

async function postRemoteTrade(input: {
  code: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  quantity: number;
  price: number;
  idempotencyKey: string;
}): Promise<boolean> {
  try {
    const res = await authFetch(`${KIASHA_API_BASE}${REMOTE_PATH}/${encodeURIComponent(input.code)}`, {
      method: 'POST',
      headers: { 'Idempotency-Key': input.idempotencyKey },
      body: JSON.stringify({
        side: input.side,
        quantity: input.quantity,
        price: input.price,
        symbol: input.symbol,
      }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

async function fetchRemotePositions(): Promise<ManualInvestment[] | null> {
  try {
    const res = await authFetch(`${KIASHA_API_BASE}${REMOTE_PATH}?limit=1000`, {
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) return null;
    const data = (await res.json()) as ManualTradeResponse;
    if (!Array.isArray(data?.positions)) return [];
    return data.positions.map((item) => ({ ...item, serverBacked: true }));
  } catch {
    return null;
  }
}

async function migrateLegacyLocal(items: ManualInvestment[]): Promise<void> {
  for (const item of items.filter((x) => !x.serverBacked)) {
    const code = item.code.trim().toUpperCase();
    if (!code || item.quantity < 1 || !Number.isFinite(item.buyPrice) || item.buyPrice <= 0) continue;
    const bought = await postRemoteTrade({
      code,
      symbol: item.symbol || code,
      side: 'BUY',
      quantity: item.quantity,
      price: item.buyPrice,
      idempotencyKey: `legacy-buy-${item.id}`.slice(0, 128),
    });
    if (!bought) continue;
    if (item.status === 'SOLD' && item.sellPrice && item.sellPrice > 0) {
      await postRemoteTrade({
        code,
        symbol: item.symbol || code,
        side: 'SELL',
        quantity: item.quantity,
        price: item.sellPrice,
        idempotencyKey: `legacy-sell-${item.id}`.slice(0, 128),
      });
    }
  }
}

export async function listManualInvestments(): Promise<ManualInvestment[]> {
  const local = await readAll();
  let remote = await fetchRemotePositions();
  if (remote === null) return local;

  // One-time migration path for purchases made with older builds. The
  // deterministic legacy idempotency key makes repeated app opens safe.
  if (local.some((item) => !item.serverBacked)) {
    await migrateLegacyLocal(local);
    remote = (await fetchRemotePositions()) ?? remote;
  }

  await writeAll(remote);
  return remote;
}

export async function findOpenManualInvestment(code: string): Promise<ManualInvestment | null> {
  const key = code.trim().toUpperCase();
  const items = await listManualInvestments();
  return items.find((x) => x.status === 'OPEN' && x.code.trim().toUpperCase() === key) ?? null;
}

async function localBuyFallback(input: {
  code: string;
  symbol: string;
  quantity: number;
  buyPrice: number;
}): Promise<ManualInvestment> {
  const items = await readAll();
  const index = items.findIndex((x) => x.status === 'OPEN' && x.code.trim().toUpperCase() === input.code.trim().toUpperCase());
  if (index >= 0) {
    const existing = items[index];
    const oldNotional = existing.buyPrice * existing.quantity;
    const addedNotional = input.buyPrice * input.quantity;
    const nextQuantity = existing.quantity + input.quantity;
    const updated: ManualInvestment = {
      ...existing,
      serverBacked: false,
      symbol: input.symbol || existing.symbol,
      quantity: nextQuantity,
      buyPrice: (oldNotional + addedNotional) / nextQuantity,
      buyNotional: oldNotional + addedNotional,
    };
    items[index] = updated;
    await writeAll(items);
    return updated;
  }
  const item: ManualInvestment = {
    id: `manual_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    code: input.code,
    symbol: input.symbol,
    quantity: input.quantity,
    buyPrice: input.buyPrice,
    buyNotional: input.quantity * input.buyPrice,
    boughtAt: new Date().toISOString(),
    status: 'OPEN',
    source: 'MANUAL_BROKER',
    serverBacked: false,
  };
  items.unshift(item);
  await writeAll(items);
  return item;
}

export async function confirmManualBuy(input: {
  code: string;
  symbol: string;
  quantity: number;
  buyPrice: number;
}): Promise<ManualInvestment> {
  const quantity = Math.max(1, Math.floor(input.quantity));
  if (!Number.isFinite(input.buyPrice) || input.buyPrice <= 0) throw new Error('قیمت خرید معتبر نیست.');
  const code = input.code.trim().toUpperCase();
  const symbol = input.symbol || code;

  const synced = await postRemoteTrade({
    code,
    symbol,
    side: 'BUY',
    quantity,
    price: input.buyPrice,
    idempotencyKey: syncKey(`mobile-buy-${code}`),
  });
  if (synced) {
    const remote = await fetchRemotePositions();
    if (remote !== null) {
      await writeAll(remote);
      const current = remote.find((x) => x.status === 'OPEN' && x.code.trim().toUpperCase() === code);
      if (current) return current;
    }
  }

  // Offline/server-unavailable fallback keeps the user's action visible. It is
  // migrated to the server automatically by listManualInvestments later.
  return localBuyFallback({ code, symbol, quantity, buyPrice: input.buyPrice });
}

export async function confirmManualSell(id: string, sellPrice: number): Promise<ManualInvestment | null> {
  if (!Number.isFinite(sellPrice) || sellPrice <= 0) throw new Error('قیمت فروش معتبر نیست.');
  const items = await listManualInvestments();
  const index = items.findIndex((x) => x.id === id && x.status === 'OPEN');
  if (index < 0) return null;
  const current = items[index];

  const synced = await postRemoteTrade({
    code: current.code,
    symbol: current.symbol,
    side: 'SELL',
    quantity: current.quantity,
    price: sellPrice,
    idempotencyKey: syncKey(`mobile-sell-${current.code}`),
  });
  if (synced) {
    const remote = await fetchRemotePositions();
    if (remote !== null) {
      await writeAll(remote);
      return remote.find((x) => x.code.trim().toUpperCase() === current.code.trim().toUpperCase()) ?? null;
    }
  }

  const cached = await readAll();
  const cachedIndex = cached.findIndex((x) => x.id === id && x.status === 'OPEN');
  if (cachedIndex < 0) return null;
  const updated: ManualInvestment = {
    ...cached[cachedIndex],
    serverBacked: false,
    status: 'SOLD',
    soldAt: new Date().toISOString(),
    sellPrice,
    sellNotional: cached[cachedIndex].quantity * sellPrice,
  };
  cached[cachedIndex] = updated;
  await writeAll(cached);
  return updated;
}
