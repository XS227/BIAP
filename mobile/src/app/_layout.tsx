import { DarkTheme, DefaultTheme, ThemeProvider } from 'expo-router/react-navigation';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect, useState } from 'react';
import { useColorScheme } from 'react-native';
import { useFonts, Vazirmatn_400Regular, Vazirmatn_700Bold } from '@expo-google-fonts/vazirmatn';

import { AnimatedSplashOverlay } from '@/components/animated-icon';
import AppTabs from '@/components/app-tabs';
import LoginScreen from '@/components/login-screen';
import { getValidAccessToken } from '@/lib/auth-session';

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const colorScheme = useColorScheme();
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [checking, setChecking] = useState(true);
  const [fontsLoaded] = useFonts({ Vazirmatn_400Regular, Vazirmatn_700Bold });

  useEffect(() => {
    getValidAccessToken().then((token) => {
      setIsLoggedIn(Boolean(token));
      setChecking(false);
    });
  }, []);

  if (checking || !fontsLoaded) return null;
  return (
    <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      <AnimatedSplashOverlay />
      {isLoggedIn ? <AppTabs onLogout={() => setIsLoggedIn(false)} /> : <LoginScreen onLogin={() => setIsLoggedIn(true)} />}
    </ThemeProvider>
  );
}
