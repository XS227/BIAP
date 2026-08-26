import { createContext, useContext } from 'react';

export const LogoutContext = createContext<() => void>(() => {});

export function useLogout() {
  return useContext(LogoutContext);
}
