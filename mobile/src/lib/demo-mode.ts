import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'biapDemoMode';

export async function getDemoMode(): Promise<boolean> {
  return (await AsyncStorage.getItem(KEY)) === 'true';
}

export async function setDemoMode(enabled: boolean): Promise<void> {
  await AsyncStorage.setItem(KEY, enabled ? 'true' : 'false');
}
