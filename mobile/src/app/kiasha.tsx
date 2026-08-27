import { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, useColorScheme, SafeAreaView, Pressable, ActivityIndicator } from 'react-native';
import { router } from 'expo-router';
import { Colors, Brand, Fonts, Spacing, Radius, BottomTabInset, MaxContentWidth, ThemeColors } from '@/constants/theme';
import { AgentPerformance, fetchKiashaPerformanceSummary, KiashaPerformanceSummary } from '@/lib/api';

// Grounded in the real backend (XS227/BIAP: analysis/agents.py + kiasha.py).
// Performance values below are fetched from the observed-performance API.
// The UI deliberately renders unavailable measurements as "—" rather than
// inventing a return/accuracy number before enough outcomes have been observed.

type FeatureItem = { icon: string; title: string; body: string; disabled?: boolean };

const FEATURES: FeatureItem[] = [
  { icon: '💡', title: 'پیشنهاد خرید/فروش', body: 'برای هر نماد، توصیه‌ای با امتیاز و دلیل روشن.' },
  { icon: '🛡️', title: 'مدیریت ریسک', body: 'سقف حجم، ارزش سفارش، انحراف قیمت و kill switch پیش از هر شبیه‌سازی بررسی می‌شود.' },
  { icon: '👥', title: 'گزارش تیم عامل‌ها', body: 'سهم هرکدام از چهار عامل (بنیادی، ریسک، پیش‌بینی، مقایسه) در تصمیم نهایی، شفاف نمایش داده می‌شود.' },
  { icon: '⚙️', title: 'سرمایه‌گذاری خودکار', body: 'به‌زودی — فقط پس از اتصال کارگزار واقعی و تأیید امنیتی/قانونی فعال می‌شود.', disabled: true },
];

const AGENT_LABELS: Record<string, { name: string; desc: string }> = {
  fundamental: { name: 'بنیادی', desc: 'رشد درآمد، حاشیه سود و صورت‌های مالی CODAL' },
  risk: { name: 'ریسک', desc: 'نقدشوندگی، نوسان و کیفیت داده' },
  forecast: { name: 'پیش‌بینی', desc: 'مومنتوم قیمت و حجم' },
  comparison: { name: 'مقایسه', desc: 'مقایسه با صنعت و سهام مشابه' },
};

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

function pct(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—';
  return `${(value * 100).toLocaleString('fa-IR', { maximumFractionDigits: 1 })}٪`;
}

function signedReturn(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—';
  const percent = value * 100;
  const sign = percent > 0 ? '+' : '';
  return `${sign}${percent.toLocaleString('fa-IR', { maximumFractionDigits: 2 })}٪`;
}

function AgentPerformanceRow({ agent, colors }: { agent: AgentPerformance; colors: ThemeColors }) {
  const label = AGENT_LABELS[agent.agent] ?? { name: agent.agent, desc: 'عامل کیاشا' };
  return (
    <View style={[styles.performanceRow, { borderBottomColor: colors.backgroundSelected }]}>
      <View style={styles.performanceHead}>
        <View style={[styles.trustBadge, { backgroundColor: agent.trustReady ? `${Brand.positive}22` : colors.backgroundSelected }]}>
          <Text style={[styles.trustBadgeText, { color: agent.trustReady ? Brand.positive : colors.textSecondary }]}>
            {agent.trustReady ? 'اعتماد فعال' : 'در حال جمع‌آوری داده'}
          </Text>
        </View>
        <Text style={[styles.agentName, { color: colors.text }]}>{label.name}</Text>
      </View>
      <Text style={[styles.agentDesc, { color: colors.textSecondary }]}>{label.desc}</Text>
      <View style={styles.metricsRow}>
        <View style={styles.metric}>
          <Text style={[styles.metricValue, { color: colors.text }]}>{agent.evaluatedCalls.toLocaleString('fa-IR')}</Text>
          <Text style={[styles.metricLabel, { color: colors.textSecondary }]}>ارزیابی‌شده</Text>
        </View>
        <View style={styles.metric}>
          <Text style={[styles.metricValue, { color: colors.text }]}>{pct(agent.directionalAccuracy)}</Text>
          <Text style={[styles.metricLabel, { color: colors.textSecondary }]}>دقت جهت</Text>
        </View>
        <View style={styles.metric}>
          <Text style={[styles.metricValue, { color: colors.text }]}>{signedReturn(agent.averageSignedReturn)}</Text>
          <Text style={[styles.metricLabel, { color: colors.textSecondary }]}>بازده امضاشده</Text>
        </View>
      </View>
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

export default function KiashaScreen() {
  const scheme = useColorScheme();
  const colors = scheme === 'dark' ? Colors.dark : Colors.light;
  const [performance, setPerformance] = useState<KiashaPerformanceSummary | null>(null);
  const [loadingPerformance, setLoadingPerformance] = useState(true);
  const [performanceUnavailable, setPerformanceUnavailable] = useState(false);

  useEffect(() => {
    let mounted = true;
    fetchKiashaPerformanceSummary()
      .then((data) => {
        if (!mounted) return;
        setPerformance(data);
        setPerformanceUnavailable(data === null);
      })
      .finally(() => {
        if (mounted) setLoadingPerformance(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

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
            {Object.entries(AGENT_LABELS).map(([key, a], i, all) => (
              <View
                key={key}
                style={[styles.agentRow, i < all.length - 1 && { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.backgroundSelected }]}
              >
                <Text style={[styles.agentName, { color: colors.text }]}>{a.name}</Text>
                <Text style={[styles.agentDesc, { color: colors.textSecondary }]}>{a.desc}</Text>
              </View>
            ))}
          </View>

          <Text style={[styles.sectionTitle, { color: colors.text }]}>عملکرد واقعی عامل‌ها</Text>
          <View style={[styles.performanceCard, { backgroundColor: colors.backgroundElement }]}>
            {loadingPerformance ? (
              <View style={styles.loadingRow}>
                <ActivityIndicator />
                <Text style={[styles.noteBody, { color: colors.textSecondary }]}>در حال دریافت گزارش عملکرد…</Text>
              </View>
            ) : performanceUnavailable || !performance ? (
              <Text style={[styles.noteBody, { color: colors.textSecondary }]}>گزارش عملکرد فعلاً از سرور در دسترس نیست.</Text>
            ) : (
              <>
                <View style={styles.summaryRow}>
                  <View style={styles.summaryItem}>
                    <Text style={[styles.summaryValue, { color: colors.text }]}>{performance.pendingRecommendations.toLocaleString('fa-IR')}</Text>
                    <Text style={[styles.summaryLabel, { color: colors.textSecondary }]}>منتظر ارزیابی</Text>
                  </View>
                  <View style={styles.summaryItem}>
                    <Text style={[styles.summaryValue, { color: colors.text }]}>{performance.evaluatedRecommendationsLowerBound.toLocaleString('fa-IR')}</Text>
                    <Text style={[styles.summaryLabel, { color: colors.textSecondary }]}>حداقل ارزیابی‌شده</Text>
                  </View>
                  <View style={styles.summaryItem}>
                    <Text style={[styles.summaryValue, { color: colors.text }]}>{performance.minimumObservedSamples.toLocaleString('fa-IR')}</Text>
                    <Text style={[styles.summaryLabel, { color: colors.textSecondary }]}>حداقل نمونه اعتماد</Text>
                  </View>
                </View>

                <View style={[styles.observedBadge, { backgroundColor: performance.observedTrustActive ? `${Brand.positive}22` : `${Brand.warning}18` }]}>
                  <Text style={[styles.observedBadgeText, { color: performance.observedTrustActive ? Brand.positive : Brand.warning }]}>
                    {performance.observedTrustActive ? 'وزن‌دهی بر اساس عملکرد مشاهده‌شده فعال است' : 'وزن‌دهی مشاهده‌شده هنوز فعال نشده'}
                  </Text>
                </View>

                {performance.agents.map((agent, i) => (
                  <View key={agent.agent}>
                    <AgentPerformanceRow agent={agent} colors={colors} />
                    {i === performance.agents.length - 1 ? null : <View style={{ height: StyleSheet.hairlineWidth, backgroundColor: colors.backgroundSelected }} />}
                  </View>
                ))}
              </>
            )}
          </View>

          <View style={[styles.noteCard, { backgroundColor: colors.backgroundElement }]}>
            <Text style={[styles.noteTitle, { color: colors.text }]}>درباره این گزارش</Text>
            <Text style={[styles.noteBody, { color: colors.textSecondary }]}>
              فقط نتیجه‌هایی نمایش داده می‌شوند که واقعاً توسط ارزیاب کیاشا ثبت شده‌اند. تا وقتی برای یک عامل نمونه کافی وجود نداشته باشد، دقت و بازده آن به‌صورت «—» نمایش داده می‌شود و در وزن‌دهی اعتماد استفاده نمی‌شود.
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
  agentDesc: { fontFamily: Fonts.sans, fontSize: 12, textAlign: 'right' },
  performanceCard: { borderRadius: Radius.md, padding: Spacing.three, marginBottom: Spacing.four },
  loadingRow: { flexDirection: 'row-reverse', gap: Spacing.two, alignItems: 'center', justifyContent: 'center', paddingVertical: Spacing.four },
  summaryRow: { flexDirection: 'row-reverse', justifyContent: 'space-between', gap: Spacing.two, marginBottom: Spacing.three },
  summaryItem: { flex: 1, alignItems: 'center' },
  summaryValue: { fontFamily: Fonts.sans, fontSize: 18, fontWeight: '800' },
  summaryLabel: { fontFamily: Fonts.sans, fontSize: 10.5, textAlign: 'center', marginTop: 2 },
  observedBadge: { borderRadius: Radius.sm, paddingHorizontal: Spacing.three, paddingVertical: Spacing.two, marginBottom: Spacing.two, alignItems: 'center' },
  observedBadgeText: { fontFamily: Fonts.sans, fontSize: 11, fontWeight: '700', textAlign: 'center' },
  performanceRow: { paddingVertical: Spacing.three },
  performanceHead: { width: '100%', flexDirection: 'row-reverse', alignItems: 'center', justifyContent: 'space-between', gap: Spacing.two },
  trustBadge: { borderRadius: Radius.sm, paddingHorizontal: 8, paddingVertical: 4 },
  trustBadgeText: { fontFamily: Fonts.sans, fontSize: 9.5, fontWeight: '700' },
  metricsRow: { flexDirection: 'row-reverse', justifyContent: 'space-between', marginTop: Spacing.two },
  metric: { flex: 1, alignItems: 'center' },
  metricValue: { fontFamily: Fonts.sans, fontSize: 13, fontWeight: '700' },
  metricLabel: { fontFamily: Fonts.sans, fontSize: 9.5, marginTop: 2 },
  noteCard: { borderRadius: Radius.md, padding: Spacing.three, alignItems: 'flex-end', gap: 6 },
  noteTitle: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '700' },
  noteBody: { fontFamily: Fonts.sans, fontSize: 12.5, textAlign: 'right', lineHeight: 20 },
});
