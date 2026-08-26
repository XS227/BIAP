import { View, Text, StyleSheet, ScrollView, useColorScheme, SafeAreaView, Pressable } from 'react-native';
import { router } from 'expo-router';
import { Colors, Brand, Fonts, Spacing, Radius, BottomTabInset, MaxContentWidth } from '@/constants/theme';

// There is no real brokerage/positions API behind this app yet -- BIAP is
// an analysis + Paper-mode simulation tool today (see XS227/BIAP's
// PROJECT_STATUS.md). Showing a portfolio value or holdings here would mean
// inventing numbers, so this screen says plainly what it is instead.

export default function PortfolioScreen() {
  const scheme = useColorScheme() ?? 'light';
  const colors = Colors[scheme];

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.four }]}>
        <View style={{ maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' }}>
          <View style={styles.header}>
            <Text style={[styles.headerTitle, { color: colors.text }]}>پرتفوی</Text>
          </View>

          <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
            <Text style={{ fontSize: 40 }}>💼</Text>
            <Text style={[styles.title, { color: colors.text }]}>پرتفوی هنوز متصل نیست</Text>
            <Text style={[styles.body, { color: colors.textSecondary }]}>
              این بخش نیازمند اتصال به یک حساب کارگزاری واقعی است. در حال حاضر BIAP فقط تحلیل هوش مصنوعی و
              شبیه‌سازی سفارش در حالت Paper ارائه می‌دهد — هیچ پوزیشن یا دارایی واقعی‌ای اینجا ثبت نشده و
              نخواهد شد تا این اتصال به‌صورت واقعی، امن و قانونی برقرار شود.
            </Text>

            <View style={styles.actions}>
              <Pressable onPress={() => router.push('/orders')} style={[styles.btn, { backgroundColor: Brand.primary }]}>
                <Text style={styles.btnText}>مشاهده شبیه‌سازی‌های Paper</Text>
              </Pressable>
              <Pressable onPress={() => router.push('/market')} style={[styles.btnOutline, { borderColor: colors.backgroundSelected }]}>
                <Text style={[styles.btnOutlineText, { color: colors.text }]}>رفتن به بازار</Text>
              </Pressable>
            </View>
          </View>
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
  card: { borderRadius: Radius.lg, padding: Spacing.four, alignItems: 'center', gap: Spacing.two, marginTop: Spacing.four },
  title: { fontFamily: Fonts.sans, fontSize: 17, fontWeight: '700' },
  body: { fontFamily: Fonts.sans, fontSize: 13, textAlign: 'center', lineHeight: 22 },
  actions: { width: '100%', gap: Spacing.two, marginTop: Spacing.three },
  btn: { borderRadius: Radius.sm, paddingVertical: Spacing.three, alignItems: 'center' },
  btnText: { color: '#fff', fontFamily: Fonts.sans, fontSize: 14, fontWeight: '700' },
  btnOutline: { borderRadius: Radius.sm, paddingVertical: Spacing.three, alignItems: 'center', borderWidth: 1 },
  btnOutlineText: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '600' },
});
