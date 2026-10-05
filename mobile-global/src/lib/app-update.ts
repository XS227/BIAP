import { Alert, Linking } from 'react-native';
import Constants from 'expo-constants';
import { GLOBAL_API_BASE } from '@/lib/global-api';

type GlobalRelease = {
  version: string;
  versionCode?: number | null;
  changes?: string[];
  apkUrl?: string;
  apkAvailable?: boolean;
};

const installedVersion = (): string => Constants.expoConfig?.version || '0.0.0';
const installedVersionCode = (): number | null => {
  const code = Constants.expoConfig?.android?.versionCode;
  return typeof code === 'number' ? code : null;
};

function isNewer(latest: string, current: string): boolean {
  const a = latest.split('.').map((p) => Number.parseInt(p, 10) || 0);
  const b = current.split('.').map((p) => Number.parseInt(p, 10) || 0);
  for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
    if ((a[i] || 0) !== (b[i] || 0)) return (a[i] || 0) > (b[i] || 0);
  }
  return false;
}

function updateAvailable(release: GlobalRelease): boolean {
  const code = installedVersionCode();
  if (typeof release.versionCode === 'number' && code !== null) return release.versionCode > code;
  return isNewer(release.version, installedVersion());
}

async function fetchRelease(): Promise<GlobalRelease> {
  const response = await fetch(`${GLOBAL_API_BASE}/app/release`, { headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const release = (await response.json()) as GlobalRelease;
  if (!release?.version) throw new Error('invalid release manifest');
  return release;
}

function promptDownload(release: GlobalRelease) {
  const notes = release.changes?.length ? `\n\nWhat's new:\n• ${release.changes.slice(0, 5).join('\n• ')}` : '';
  Alert.alert(
    'Update available',
    `Installed: ${installedVersion()}\nNew version: ${release.version}${notes}`,
    [
      { text: 'Later', style: 'cancel' },
      { text: 'Download & install', onPress: () => { void Linking.openURL(release.apkUrl || 'https://biap.dadashi.no/global/download/BIAP-Global-latest.apk'); } },
    ],
  );
}

/** Startup check: prompts only when a newer, already published APK exists. */
export async function checkForUpdateSilently(): Promise<void> {
  try {
    const release = await fetchRelease();
    if (release.apkAvailable !== false && updateAvailable(release)) promptDownload(release);
  } catch {
    // Offline or server unavailable: stay quiet on startup.
  }
}

/** Manual check from the More screen: always reports the result. */
export async function checkForUpdateInteractive(): Promise<void> {
  try {
    const release = await fetchRelease();
    if (!updateAvailable(release)) {
      Alert.alert('BIAP Global is up to date', `Installed: ${installedVersion()}\nLatest: ${release.version}`);
      return;
    }
    if (release.apkAvailable === false) {
      Alert.alert('Update coming', `Version ${release.version} is being published. Please check again in a few minutes.`);
      return;
    }
    promptDownload(release);
  } catch {
    Alert.alert('Update check', 'Could not reach the update server. Please try again later.');
  }
}
