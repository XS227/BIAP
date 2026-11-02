import { useSyncExternalStore } from 'react';
import { useColorScheme as useRNColorScheme } from 'react-native';

// During static rendering and the first hydration pass, keep the server's
// light theme. useSyncExternalStore switches to the client value after
// hydration without setting React state synchronously in an effect.
const subscribe = () => () => {};
const clientSnapshot = () => true;
const serverSnapshot = () => false;

export function useColorScheme() {
  const hasHydrated = useSyncExternalStore(subscribe, clientSnapshot, serverSnapshot);
  const colorScheme = useRNColorScheme();
  return hasHydrated ? colorScheme : 'light';
}
