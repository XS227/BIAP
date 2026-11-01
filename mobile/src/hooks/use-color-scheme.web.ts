import { useSyncExternalStore } from 'react';
import { useColorScheme as useRNColorScheme } from 'react-native';

// React uses the server snapshot for SSR and the client snapshot after hydration.
const subscribe = () => () => {};
const getClientSnapshot = () => true;
const getServerSnapshot = () => false;

export function useColorScheme() {
  const hydrated = useSyncExternalStore(subscribe, getClientSnapshot, getServerSnapshot);
  const colorScheme = useRNColorScheme();
  return hydrated ? colorScheme : 'light';
}
