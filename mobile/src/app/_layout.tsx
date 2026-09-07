import { DarkTheme, DefaultTheme, ThemeProvider } from 'expo-router/react-navigation';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect, useState } from 'react';
import { useColorScheme } from 'react-native';
import { useFonts, Vazirmatn_400Regular, Vazirmatn_700Bold } from '@expo-google-fonts/vazirmatn';

import { AnimatedSplashOverlay } from '@/components/animated-icon';
import AppTabs from '@/components/app-tabs';
import LoginScreen from '@/components/login-screen';
import RegisterScreen from '@/app/register';
import { getValidAccessToken } from '@/lib/auth-session';
import { trackAppOpen } from '@/lib/activity';

SplashScreen.preventAutoHideAsync();

type AuthScreen = 'login' | 'register';

export default function RootLayout() {
  const colorScheme = useColorScheme();
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [authScreen, setAuthScreen] = useState<AuthScreen>('login');
  const [checking, setChecking] = useState(true);
  const [fontsLoaded] = useFonts({ Vazirmatn_400Regular, Vazirmatn_700Bold });

  useEffect(() => {
    void trackAppOpen();
    getValidAccessToken().then((token) => {
      setIsLoggedIn(Boolean(token));
      setChecking(false);
    });
  }, []);

  if (checking || !fontsLoaded) return null;

  const handleLoggedIn = () => {
    setAuthScreen('login');
    setIsLoggedIn(true);
  };

  const handleLogout = () => {
    setAuthScreen('login');
    setIsLoggedIn(false);
  };

  return (
    <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      <AnimatedSplashOverlay />
      {isLoggedIn ? (
        <AppTabs onLogout={handleLogout} />
      ) : authScreen === 'register' ? (
        <RegisterScreen onLogin={handleLoggedIn} onBack={() => setAuthScreen('login')} />
      ) : (
        <LoginScreen onLogin={handleLoggedIn} onRegister={() => setAuthScreen('register')} />
      )}
    </ThemeProvider>
  );
}
