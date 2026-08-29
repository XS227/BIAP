import AsyncStorage from '@react-native-async-storage/async-storage';

export const AUTH_API_BASE = 'https://biap.dadashi.no/api';

export type AuthPayload = {
  accessToken: string;
  refreshToken?: string;
  accessTokenExpiresAt?: number;
  refreshTokenTtlDays?: number;
  user?: Record<string, unknown>;
};

let refreshInFlight: Promise<string | null> | null = null;

export async function storeAuthPayload(payload: AuthPayload): Promise<void> {
  const entries: [string, string][] = [['accessToken', payload.accessToken]];
  if (payload.refreshToken) entries.push(['refreshToken', payload.refreshToken]);
  if (payload.accessTokenExpiresAt) entries.push(['accessTokenExpiresAt', String(payload.accessTokenExpiresAt)]);
  if (payload.user) entries.push(['user', JSON.stringify(payload.user)]);
  await AsyncStorage.multiSet(entries);
}

export async function clearAuthSession(): Promise<void> {
  await AsyncStorage.multiRemove(['accessToken', 'refreshToken', 'accessTokenExpiresAt', 'user']);
}

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = await AsyncStorage.getItem('refreshToken');
  if (!refreshToken) return null;
  try {
    const res = await fetch(`${AUTH_API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refreshToken }),
    });
    if (!res.ok) {
      await clearAuthSession();
      return null;
    }
    const payload = (await res.json()) as AuthPayload;
    if (!payload.accessToken) {
      await clearAuthSession();
      return null;
    }
    await storeAuthPayload(payload);
    return payload.accessToken;
  } catch {
    return null;
  }
}

export async function getValidAccessToken(): Promise<string | null> {
  const token = await AsyncStorage.getItem('accessToken');
  const expRaw = await AsyncStorage.getItem('accessTokenExpiresAt');
  const exp = expRaw ? Number(expRaw) : NaN;
  const now = Math.floor(Date.now() / 1000);
  if (token && (!Number.isFinite(exp) || exp - now > 60)) return token;
  if (!refreshInFlight) refreshInFlight = refreshAccessToken().finally(() => { refreshInFlight = null; });
  return refreshInFlight;
}

export async function authHeaders(extra?: Record<string, string>): Promise<Record<string, string>> {
  const token = await getValidAccessToken();
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(extra ?? {}),
  };
}

export async function authFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const firstHeaders = { ...(init.headers as Record<string, string> | undefined), ...(await authHeaders()) };
  let response = await fetch(input, { ...init, headers: firstHeaders });
  if (response.status !== 401 && response.status !== 403) return response;

  if (!refreshInFlight) refreshInFlight = refreshAccessToken().finally(() => { refreshInFlight = null; });
  const refreshed = await refreshInFlight;
  if (!refreshed) return response;

  const retryHeaders = {
    ...(init.headers as Record<string, string> | undefined),
    'Content-Type': 'application/json',
    Authorization: `Bearer ${refreshed}`,
  };
  response = await fetch(input, { ...init, headers: retryHeaders });
  return response;
}
