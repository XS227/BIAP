import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';
import { Platform } from 'react-native';
import { API_BASE } from '@/lib/api';
import { getValidAccessToken } from '@/lib/auth-session';

const INSTALL_KEY = 'biap:installation-id:v1';

function randomPart() {
  return Math.random().toString(36).slice(2, 12);
}

async function getInstallation(): Promise<{ id: string; created: boolean }> {
  const existing = await AsyncStorage.getItem(INSTALL_KEY);
  if (existing) return { id: existing, created: false };
  const id = `biap-${Date.now().toString(36)}-${randomPart()}-${randomPart()}`;
  await AsyncStorage.setItem(INSTALL_KEY, id);
  return { id, created: true };
}

export async function getClientContext() {
  const { id } = await getInstallation();
  return {
    installationId: id,
    platform: Platform.OS,
    appVersion: Constants.expoConfig?.version ?? Constants.nativeAppVersion ?? 'unknown',
  };
}

async function postEvent(eventType: string, metadata?: Record<string, string | number | boolean | null>) {
  const context = await getClientContext();
  const token = await getValidAccessToken().catch(() => null);
  await fetch(`${API_BASE}/auth/activity/event`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ eventType, ...context, metadata: metadata ?? {} }),
  }).catch(() => undefined);
}

export async function trackActivity(eventType: string, metadata?: Record<string, string | number | boolean | null>) {
  await postEvent(eventType, metadata);
}

export async function trackAppOpen() {
  const installation = await getInstallation();
  if (installation.created) {
    await postEvent('install', { source: 'mobile' });
  }
  await postEvent('app_open');
}
