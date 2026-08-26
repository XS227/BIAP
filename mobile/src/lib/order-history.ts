import AsyncStorage from '@react-native-async-storage/async-storage';
import { OrderIntent } from './api';

// The XS227/BIAP backend has no per-user auth/ownership yet (see its
// PROJECT_STATUS.md "Open blockers"), so /audit/orders returns every order
// intent ever created, not "your" orders -- it can't be used to show a
// personal order history without misattributing other people's simulations.
// Until real auth exists, this app tracks its own paper-order receipts
// locally instead.

const KEY = 'biap_local_orders_v1';
const MAX_STORED = 200;

export type LocalOrderReceipt = OrderIntent & {
  submittedAt: string;
  broker: string | null;
  brokerOrderId: string | null;
};

export async function recordLocalOrder(receipt: LocalOrderReceipt): Promise<void> {
  const existing = await getLocalOrders();
  const next = [receipt, ...existing.filter((o) => o.id !== receipt.id)].slice(0, MAX_STORED);
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // best-effort; losing local history isn't worth crashing the sim flow
  }
}

export async function getLocalOrders(): Promise<LocalOrderReceipt[]> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export async function clearLocalOrders(): Promise<void> {
  try {
    await AsyncStorage.removeItem(KEY);
  } catch {
    // ignore
  }
}
