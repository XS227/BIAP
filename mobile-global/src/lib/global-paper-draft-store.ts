import AsyncStorage from '@react-native-async-storage/async-storage';
import { isPaperDraft, type PaperDraft, type PaperDraftFields } from './global-paper-order';

const STORE_KEY = 'biap-global:paper-order-drafts:v1';
const MAX_DRAFTS = 30;

/** Device-only research drafts. Not broker paper trading or executed holdings. */
export async function listGlobalPaperDrafts(): Promise<PaperDraft[]> {
  try {
    const raw = await AsyncStorage.getItem(STORE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(isPaperDraft).slice(0, MAX_DRAFTS) : [];
  } catch {
    return [];
  }
}

export async function saveGlobalPaperDraft(input: PaperDraftFields): Promise<PaperDraft> {
  const order: PaperDraft = {
    ...input,
    id: 'draft-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10),
    createdAt: new Date().toISOString(),
    status: 'DRAFT_ONLY',
    note: 'NOT_SUBMITTED',
  };
  const previous = await listGlobalPaperDrafts();
  await AsyncStorage.setItem(STORE_KEY, JSON.stringify([order, ...previous].slice(0, MAX_DRAFTS)));
  return order;
}

export async function clearGlobalPaperDrafts(): Promise<void> {
  await AsyncStorage.removeItem(STORE_KEY);
}
