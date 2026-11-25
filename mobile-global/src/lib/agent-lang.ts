import { useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import type { Lang } from './agent-i18n';

const KEY = 'biap.global.agentLang';
let current: Lang = 'en';
let loaded = false;
const listeners = new Set<(l: Lang) => void>();

export function setAgentLang(lang: Lang) {
  current = lang;
  listeners.forEach((fn) => fn(lang));
  AsyncStorage.setItem(KEY, lang).catch(() => {});
}

/** English by default; the choice (EN / فارسی) is remembered and shared by every agent section and the Track record screen. */
export function useAgentLang(): [Lang, (l: Lang) => void] {
  const [lang, setLang] = useState<Lang>(current);
  useEffect(() => {
    listeners.add(setLang);
    if (!loaded) {
      loaded = true;
      AsyncStorage.getItem(KEY).then((v) => { if (v === 'fa' || v === 'en') { current = v; listeners.forEach((fn) => fn(v)); } }).catch(() => {});
    } else setLang(current);
    return () => { listeners.delete(setLang); };
  }, []);
  return [lang, setAgentLang];
}
