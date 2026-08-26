import { Tabs } from 'expo-router';
import { Text, useColorScheme } from 'react-native';
import { Colors, Brand } from '@/constants/theme';
import { LogoutContext } from '@/lib/logout-context';

function TabIcon({ symbol, size }: { symbol: string; size: number }) {
  return <Text style={{ fontSize: size - 2, lineHeight: size }}>{symbol}</Text>;
}

type Props = { onLogout: () => void };

export default function AppTabs({ onLogout }: Props) {
  const scheme = useColorScheme() ?? 'light';
  const colors = Colors[scheme];
  return (
    <LogoutContext.Provider value={onLogout}>
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarStyle: { backgroundColor: colors.background, borderTopColor: colors.backgroundSelected },
          tabBarLabelStyle: { fontFamily: 'Vazirmatn_400Regular', fontSize: 10.5 },
        }}
      >
        <Tabs.Screen
          name="index"
          options={{
            title: 'خانه',
            tabBarActiveTintColor: Brand.primary,
            tabBarIcon: ({ size }) => <TabIcon symbol="🏠" size={size} />,
          }}
        />
        <Tabs.Screen
          name="market"
          options={{
            title: 'بازار',
            tabBarActiveTintColor: Brand.positive,
            tabBarIcon: ({ size }) => <TabIcon symbol="📈" size={size} />,
          }}
        />
        <Tabs.Screen
          name="orders"
          options={{
            title: 'سفارش‌ها',
            tabBarActiveTintColor: Brand.warning,
            tabBarIcon: ({ size }) => <TabIcon symbol="🧾" size={size} />,
          }}
        />
        <Tabs.Screen
          name="portfolio"
          options={{
            title: 'پرتفوی',
            tabBarActiveTintColor: Brand.secondary,
            tabBarIcon: ({ size }) => <TabIcon symbol="💼" size={size} />,
          }}
        />
        <Tabs.Screen
          name="kiasha"
          options={{
            title: 'کیاشا',
            tabBarActiveTintColor: Brand.primary,
            tabBarIcon: ({ size }) => <TabIcon symbol="🤖" size={size} />,
          }}
        />
        <Tabs.Screen
          name="more"
          options={{
            title: 'بیشتر',
            tabBarActiveTintColor: colors.text,
            tabBarIcon: ({ size }) => <TabIcon symbol="☰" size={size} />,
          }}
        />

        {/* Reachable by navigation, hidden from the tab bar */}
        <Tabs.Screen name="stock/[code]" options={{ href: null }} />
        <Tabs.Screen name="register" options={{ href: null }} />
        <Tabs.Screen name="bizdev" options={{ href: null }} />
        <Tabs.Screen name="data" options={{ href: null }} />
        <Tabs.Screen name="profile" options={{ href: null }} />
      </Tabs>
    </LogoutContext.Provider>
  );
}
