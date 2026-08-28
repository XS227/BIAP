import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'biapDemoTradingWalletV1';
export const DEMO_INITIAL_CASH = 100_000_000;

type DemoHolding = { quantity: number; averageCost: number };
export type DemoTrade = { id: string; code: string; side: 'BUY' | 'SELL'; quantity: number; price: number; createdAt: string };
export type DemoWallet = { cash: number; holdings: Record<string, DemoHolding>; trades: DemoTrade[] };

const freshWallet = (): DemoWallet => ({ cash: DEMO_INITIAL_CASH, holdings: {}, trades: [] });

export async function getDemoWallet(): Promise<DemoWallet> {
  const raw = await AsyncStorage.getItem(KEY);
  if (!raw) {
    const wallet = freshWallet();
    await AsyncStorage.setItem(KEY, JSON.stringify(wallet));
    return wallet;
  }
  try {
    const parsed = JSON.parse(raw) as DemoWallet;
    if (!Number.isFinite(parsed.cash) || !parsed.holdings || !Array.isArray(parsed.trades)) throw new Error('bad wallet');
    return parsed;
  } catch {
    const wallet = freshWallet();
    await AsyncStorage.setItem(KEY, JSON.stringify(wallet));
    return wallet;
  }
}

async function save(wallet: DemoWallet): Promise<void> {
  await AsyncStorage.setItem(KEY, JSON.stringify(wallet));
}

export async function executeDemoTrade(params: { code: string; side: 'BUY' | 'SELL'; quantity: number; price: number }): Promise<{ ok: true; wallet: DemoWallet } | { ok: false; message: string }> {
  const { code, side, quantity, price } = params;
  if (!Number.isFinite(quantity) || quantity <= 0 || !Number.isFinite(price) || price <= 0) return { ok: false, message: 'قیمت یا تعداد برای معامله دمو معتبر نیست.' };
  const wallet = await getDemoWallet();
  const symbol = code.toUpperCase();
  const holding = wallet.holdings[symbol] ?? { quantity: 0, averageCost: 0 };
  const value = quantity * price;

  if (side === 'BUY') {
    if (wallet.cash < value) return { ok: false, message: 'موجودی دمو برای این خرید کافی نیست.' };
    const nextQty = holding.quantity + quantity;
    const nextAvg = ((holding.quantity * holding.averageCost) + value) / nextQty;
    wallet.cash -= value;
    wallet.holdings[symbol] = { quantity: nextQty, averageCost: nextAvg };
  } else {
    if (holding.quantity < quantity) return { ok: false, message: 'تعداد سهم دمو برای این فروش کافی نیست.' };
    wallet.cash += value;
    const nextQty = holding.quantity - quantity;
    if (nextQty === 0) delete wallet.holdings[symbol];
    else wallet.holdings[symbol] = { ...holding, quantity: nextQty };
  }

  wallet.trades.unshift({ id: `demo-${Date.now()}`, code: symbol, side, quantity, price, createdAt: new Date().toISOString() });
  wallet.trades = wallet.trades.slice(0, 200);
  await save(wallet);
  return { ok: true, wallet };
}

export async function resetDemoWallet(): Promise<void> {
  await save(freshWallet());
}
