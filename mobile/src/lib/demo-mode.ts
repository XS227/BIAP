import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'biapDemoMode';
const DEMO_EMAIL = 'demo@biap.app';

type StoredUser = { email?: string | null };

async function currentUserEmail(): Promise<string | null> {
  const raw = await AsyncStorage.getItem('user');
  if (!raw) return null;
  try {
    const user = JSON.parse(raw) as StoredUser;
    return typeof user?.email === 'string' ? user.email.trim().toLowerCase() : null;
  } catch {
    return null;
  }
}

export async function getDemoMode(): Promise<boolean> {
  const enabled = (await AsyncStorage.getItem(KEY)) === 'true';
  if (!enabled) return false;

  // Demo mode is account-scoped. A stale flag left behind after logging out of
  // the demo account must never make a normal authenticated account use the
  // local demo wallet or hide server-owned Paper/Auto Invest.
  const email = await currentUserEmail();
  if (email !== DEMO_EMAIL) {
    await AsyncStorage.setItem(KEY, 'false');
    return false;
  }
  return true;
}

export async function setDemoMode(enabled: boolean): Promise<void> {
  if (enabled) {
    const email = await currentUserEmail();
    if (email !== DEMO_EMAIL) {
      await AsyncStorage.setItem(KEY, 'false');
      return;
    }
  }
  await AsyncStorage.setItem(KEY, enabled ? 'true' : 'false');
}
