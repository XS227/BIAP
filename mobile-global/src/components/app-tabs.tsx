import { Tabs } from 'expo-router';
import { Text, useColorScheme } from 'react-native';
import { Colors, Brand } from '@/constants/theme';
import { LogoutContext } from '@/lib/logout-context';

function TabIcon({ symbol, size }: { symbol: string; size: number }) {
  return <Text style={{ fontSize: size - 2, lineHeight: size }}>{symbol}</Text>;
}

type Props = { onLogout: () => void };

export default function AppTabs({ onLogout }: Props) {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  return (
    <LogoutContext.Provider value={onLogout}>
      <Tabs screenOptions={{
        headerShown: false,
        tabBarStyle: { backgroundColor: colors.background, borderTopColor: colors.backgroundSelected },
        tabBarLabelStyle: { fontFamily: 'Vazirmatn_400Regular', fontSize: 10.5 },
        tabBarActiveTintColor: Brand.primary,
      }}>
        <Tabs.Screen name="index" options={{ title: 'Home', tabBarIcon: ({ size }) => <TabIcon symbol="🏠" size={size} /> }} />
        <Tabs.Screen name="market" options={{ title: 'Market', tabBarIcon: ({ size }) => <TabIcon symbol="📈" size={size} /> }} />
        <Tabs.Screen name="portfolio" options={{ title: 'Portfolio', tabBarIcon: ({ size }) => <TabIcon symbol="💼" size={size} /> }} />
        <Tabs.Screen name="kiasha" options={{ title: 'Kiasha', tabBarIcon: ({ size }) => <TabIcon symbol="🧠" size={size} /> }} />
        <Tabs.Screen name="more" options={{ title: 'More', tabBarIcon: ({ size }) => <TabIcon symbol="•••" size={size} /> }} />

        {/* Country/exchange selection is a shared flow, not a replacement for
            the normal BIAP modules. The route stays accessible from Home/Market. */}
        <Tabs.Screen name="global" options={{ href: null }} />
        <Tabs.Screen name="orders" options={{ href: null }} />
        <Tabs.Screen name="favorites" options={{ href: null }} />
        <Tabs.Screen name="data-connect" options={{ href: null }} />
        <Tabs.Screen name="how-to" options={{ href: null }} />
        <Tabs.Screen name="kiasha-profile" options={{ href: null }} />
        <Tabs.Screen name="stock/[code]" options={{ href: null }} />
        <Tabs.Screen name="register" options={{ href: null }} />
        <Tabs.Screen name="bizdev" options={{ href: null }} />
        <Tabs.Screen name="data" options={{ href: null }} />
        <Tabs.Screen name="modules" options={{ href: null }} />
        <Tabs.Screen name="module" options={{ href: null }} />
        <Tabs.Screen name="profile" options={{ href: null }} />
        <Tabs.Screen name="search" options={{ href: null }} />
      </Tabs>
    </LogoutContext.Provider>
  );
}
