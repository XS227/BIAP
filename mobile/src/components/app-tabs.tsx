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
      }}>
        <Tabs.Screen name="index" options={{ title: 'Home', tabBarActiveTintColor: Brand.primary, tabBarIcon: ({ size }) => <TabIcon symbol="🏠" size={size} /> }} />
        <Tabs.Screen name="global" options={{ title: 'Global', tabBarActiveTintColor: Brand.positive, tabBarIcon: ({ size }) => <TabIcon symbol="🌍" size={size} /> }} />
        <Tabs.Screen name="kiasha" options={{ title: 'Kiasha', tabBarActiveTintColor: Brand.primary, tabBarIcon: ({ size }) => <TabIcon symbol="🤖" size={size} /> }} />
        <Tabs.Screen name="more" options={{ title: 'More', tabBarActiveTintColor: colors.text, tabBarIcon: ({ size }) => <TabIcon symbol="☰" size={size} /> }} />

        {/* Iran/current BIAP screens stay in the branch but are hidden from the Global footer. */}
        <Tabs.Screen name="market" options={{ href: null }} />
        <Tabs.Screen name="orders" options={{ href: null }} />
        <Tabs.Screen name="portfolio" options={{ href: null }} />
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
