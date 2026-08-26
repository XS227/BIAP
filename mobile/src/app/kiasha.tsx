import { View, Text, StyleSheet, ScrollView, useColorScheme, SafeAreaView, Pressable } from 'react-native';
import { router } from 'expo-router';
import { Colors, Brand, Fonts, Spacing, Radius, BottomTabInset, MaxContentWidth, ThemeColors } from '@/constants/theme';

// Grounded in the real backend (XS227/BIAP: analysis/agents.py + kiasha.py),
// not invented. Explicitly does NOT show a performance/return chart --
// kiasha.py's own TRACK_RECORDS are seeded placeholders, not real logged
// outcomes yet, and "auto invest" is explicitly not enabled (execution.py
// blocks AUTO regardless of risk settings).

type FeatureItem = { icon: string; title: string; body: string; disabled?: boolean };

const FEATURES: FeatureItem[] = [
  { icon: '💡', title: 'پیشنهاد خرید/فروش', body: 'برای هر نماد، توصیه‌ای با امتیاز و دلیل روشن.' },
  { icon: '🛡️', title: 'مدیریت ریسک', body: 'سقف حجم، ارزش سفارش، انحراف قیمت و kill switch پیش از هر شبیه‌سازی بررسی می‌شود.' },
  { icon: '👥', title: 'گزارش تیم عامل‌ها', body: 'سهم هرکدام از چهار عامل (بنیادی، ریسک، پیش‌بینی، مقایسه) در تصمیم نهایی، شفاف نمایش داده می‌شود.' },
  { icon: '⚙️', title: 'سرمایه‌گذاری خودکار', body: 'به‌زودی — فقط پس از اتصال کارگزار واقعی و تأیید امنیتی/قانونی فعال می‌شود.', disabled: true },
];

function FeatureCard({ item, colors }: { item: FeatureItem; colors: ThemeColors }) {
  return (
    <View style={[fStyles.card, { backgroundColor: colors.backgroundElement, opacity: item.disabled ? 0.6 : 1 }]}>
      <Text style={{ fontSize: 22 }}>{item.icon}</Text>
      <Text style={[fStyles.title, { color: colors.text }]}>{item.title}</Text>
      <Text style={[fStyles.body, { color: colors.textSecondary }]}>{item.body}</Text>
      {item.disabled ? (
        <View style={[fStyles.badge, { backgroundColor: `${Brand.warning}22` }]}>
          <Text style={[fStyles.badgeText, { color: Brand.warning }]}>غیرفعال</Text>
        </View>
      ) : null}
    </View>
  );
}
const fStyles = StyleSheet.create({
  card: { flexBasis: '47%', borderRadius: Radius.md, padding: Spacing.three, alignItems: 'flex-end', gap: 4 },
  title: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '700', marginTop: 2 },
  body: { fontFamily: Fonts.sans, fontSize: 11.5, lineHeight: 17 },
  badge: { alignSelf: 'flex-end', borderRadius: Radius.sm, paddingHorizontal: 8, paddingVertical: 3, marginTop: 4 },
  badgeText: { fontFamily: Fonts.sans, fontSize: 10, fontWeight: '700' },
});

const AGENTS = [
  { name: 'بنیادی', desc: 'رشد درآمد، حاشیه سود و صورت‌های مالی CODAL' },
  { name: 'ریسک', desc: 'نقدشوندگی، نوسان و کیفیت داده' },
  { name: 'پیش‌بینی', desc: 'مومنتوم قیمت و حجم' },
  { name: 'مقایسه', desc: 'مقایسه با صنعت و سهام مشابه' },
];

export default function KiashaScreen() {
  const scheme = useColorScheme() ?? 'light';
  const colors = Colors[scheme];

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.four }]}>
        <View style={{ maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' }}>
          <View style={styles.header}>
            <Text style={[styles.headerTitle, { color: colors.text }]}>عامل هوشمند</Text>
          </View>

          <View style={[styles.hero, { backgroundColor: Brand.primary }]}>
            <Text style={styles.heroBadge}>🤖 کیاشا</Text>
            <Text style={styles.heroTitle}>عامل هوشمند: کیاشا</Text>
            <Text style={styles.heroBody}>
              کیاشا تحلیل چهار عامل هوش مصنوعی را — با وزن‌دهی بر اساس سابقه و بلوغ هرکدام — ترکیب می‌کند و یک
              پیشنهاد خرید، نگهداری یا فروش همراه با دلیل روشن می‌سازد.
            </Text>
            <Pressable onPress={() => router.push('/market')} style={styles.heroBtn}>
              <Text style={styles.heroBtnText}>⚡ مشاهده تحلیل یک نماد</Text>
            </Pressable>
          </View>

          <Text style={[styles.sectionTitle, { color: colors.text }]}>قابلیت‌ها</Text>
          <View style={styles.grid}>
            {FEATURES.map((f) => (
              <FeatureCard key={f.title} item={f} colors={colors} />
            ))}
          </View>

          <Text style={[styles.sectionTitle, { color: colors.text }]}>تیم عامل‌ها</Text>
          <View style={[styles.agentsCard, { backgroundColor: colors.backgroundElement }]}>
            {AGENTS.map((a, i) => (
              <View
                key={a.name}
                style={[styles.agentRow, i < AGENTS.length - 1 && { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.backgroundSelected }]}
              >
                <Text style={[styles.agentName, { color: colors.text }]}>{a.name}</Text>
                <Text style={[styles.agentDesc, { color: colors.textSecondary }]}>{a.desc}</Text>
              </View>
            ))}
          </View>

          <View style={[styles.noteCard, { backgroundColor: colors.backgroundElement }]}>
            <Text style={[styles.noteTitle, { color: colors.text }]}>گزارش عملکرد</Text>
            <Text style={[styles.noteBody, { color: colors.textSecondary }]}>
              چون هنوز نتیجه‌ی واقعی معاملات ثبت و اندازه‌گیری نشده، گزارش بازدهی کیاشا فعلاً در دسترس نیست. این
              بخش بعد از ثبت واقعی نتایج شبیه‌سازی‌ها و معاملات تکمیل می‌شود.
            </Text>
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
  hero: { borderRadius: Radius.lg, padding: Spacing.four, alignItems: 'flex-end', gap: Spacing.two, marginBottom: Spacing.four },
  heroBadge: { fontSize: 13, color: 'rgba(255,255,255,0.85)', fontFamily: Fonts.sans },
  heroTitle: { fontSize: 20, color: '#fff', fontFamily: Fonts.sans, fontWeight: '700' },
  heroBody: { fontSize: 13, color: 'rgba(255,255,255,0.9)', fontFamily: Fonts.sans, textAlign: 'right', lineHeight: 21 },
  heroBtn: { backgroundColor: 'rgba(255,255,255,0.16)', borderRadius: Radius.sm, paddingHorizontal: Spacing.four, paddingVertical: Spacing.three, marginTop: Spacing.two },
  heroBtnText: { color: '#fff', fontFamily: Fonts.sans, fontSize: 14, fontWeight: '700' },
  sectionTitle: { fontFamily: Fonts.sans, fontSize: 16, fontWeight: '700', textAlign: 'right', marginBottom: Spacing.two },
  grid: { flexDirection: 'row-reverse', flexWrap: 'wrap', gap: Spacing.two, marginBottom: Spacing.four },
  agentsCard: { borderRadius: Radius.md, padding: Spacing.three, marginBottom: Spacing.four },
  agentRow: { alignItems: 'flex-end', paddingVertical: Spacing.two, gap: 2 },
  agentName: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '700' },
  agentDesc: { fontFamily: Fonts.sans, fontSize: 12 },
  noteCard: { borderRadius: Radius.md, padding: Spacing.three, alignItems: 'flex-end', gap: 6 },
  noteTitle: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '700' },
  noteBody: { fontFamily: Fonts.sans, fontSize: 12.5, textAlign: 'right', lineHeight: 20 },
});
