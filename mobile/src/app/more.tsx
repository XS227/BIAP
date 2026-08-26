import { View, Text, StyleSheet, ScrollView, useColorScheme, SafeAreaView, Pressable, Alert } from 'react-native';
import { router } from 'expo-router';
import { Colors, Brand, Fonts, Spacing, Radius, BottomTabInset, MaxContentWidth, ThemeColors } from '@/constants/theme';
import { useLogout } from '@/lib/logout-context';
import AsyncStorage from '@react-native-async-storage/async-storage';

type MenuItem = { icon: string; title: string; sub: string; onPress: () => void; destructive?: boolean };

function MenuRow({ item, colors }: { item: MenuItem; colors: ThemeColors }) {
  return (
    <Pressable
      onPress={item.onPress}
      style={({ pressed }) => [rowStyles.row, { backgroundColor: colors.backgroundElement, opacity: pressed ? 0.8 : 1 }]}
    >
      <Text style={[rowStyles.chevron, { color: colors.textSecondary }]}>‹</Text>
      <View style={rowStyles.textWrap}>
        <Text style={[rowStyles.title, { color: item.destructive ? Brand.negative : colors.text }]}>{item.title}</Text>
        <Text style={[rowStyles.sub, { color: colors.textSecondary }]}>{item.sub}</Text>
      </View>
      <Text style={{ fontSize: 20 }}>{item.icon}</Text>
    </Pressable>
  );
}
const rowStyles = StyleSheet.create({
  row: { flexDirection: 'row-reverse', alignItems: 'center', gap: Spacing.three, borderRadius: Radius.md, padding: Spacing.three, marginBottom: Spacing.two },
  textWrap: { flex: 1, alignItems: 'flex-end', gap: 2 },
  title: { fontFamily: Fonts.sans, fontSize: 15, fontWeight: '600' },
  sub: { fontFamily: Fonts.sans, fontSize: 12 },
  chevron: { fontSize: 18 },
});

export default function MoreScreen() {
  const scheme = useColorScheme() ?? 'light';
  const colors = Colors[scheme];
  const logout = useLogout();

  const handleLogout = () => {
    Alert.alert('خروج از حساب', 'آیا مطمئن هستید که می‌خواهید خارج شوید؟', [
      { text: 'انصراف', style: 'cancel' },
      {
        text: 'خروج',
        style: 'destructive',
        onPress: async () => {
          await AsyncStorage.multiRemove(['accessToken', 'user']);
          logout();
        },
      },
    ]);
  };

  const items: MenuItem[] = [
    { icon: '💼', title: 'تحلیل کسب‌وکار', sub: 'خلاصه وضعیت بازار سرمایه', onPress: () => router.push('/bizdev') },
    { icon: '📊', title: 'تحلیل داده', sub: 'نمودار، آمار و خروجی CSV', onPress: () => router.push('/data') },
    { icon: '👤', title: 'حساب کاربری', sub: 'اطلاعات و تنظیمات حساب', onPress: () => router.push('/profile') },
  ];

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.four }]}>
        <View style={{ maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' }}>
          <View style={styles.header}>
            <Text style={[styles.headerTitle, { color: colors.text }]}>بیشتر</Text>
          </View>

          {items.map((item) => (
            <MenuRow key={item.title} item={item} colors={colors} />
          ))}

          <View style={{ height: Spacing.three }} />

          <MenuRow
            item={{ icon: '🚪', title: 'خروج از حساب', sub: 'خروج از حساب کاربری فعلی', onPress: handleLogout, destructive: true }}
            colors={colors}
          />
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { paddingHorizontal: Spacing.three },
  header: { paddingTop: Spacing.four, paddingBottom: Spacing.three },
  headerTitle: { fontSize: 22, fontFamily: Fonts.sans, textAlign: 'right', fontWeight: '700' },
});
