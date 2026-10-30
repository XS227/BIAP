import { ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Colors } from '@/constants/theme';
import { IRAN_CHECKPOINT_DEMO, auditCheckpointDemo, demoFinancialRatios } from '@/lib/checkpoint-demo';

const demo = IRAN_CHECKPOINT_DEMO;
const audit = auditCheckpointDemo(demo);
const ratios = demoFinancialRatios(demo);
const format = (n: number | null) => n === null ? '—' : n.toLocaleString('fa-IR');

export default function CheckpointDemoScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  if (!__DEV__) return <SafeAreaView style={{ flex: 1, backgroundColor: colors.background, padding: 20 }}><Text style={{ color: colors.text }}>Development preview unavailable.</Text></SafeAreaView>;
  const f = demo.financials;
  return <SafeAreaView style={{ flex: 1, backgroundColor: colors.background }}>
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={[styles.title, { color: colors.text }]}>پیش‌نمایش مرحله اول BIAP ایران</Text>
      <View style={styles.warning}><Text style={styles.warningText}>فقط داده نمونه ساختگی — هیچ قیمت، سیگنال خرید یا تحلیل واقعی نمایش داده نمی‌شود.</Text></View>
      <Text style={[styles.subtitle, { color: colors.textSecondary }]}>{demo.company} • {demo.symbol}</Text>
      <Text style={[styles.subtitle, { color: colors.textSecondary }]}>داده واقعی باید از مسیر امن و با منبع معتبر دریافت شود.</Text>
      <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
        <Text style={[styles.heading, { color: colors.text }]}>صورت‌های مالی نمونه</Text>
        {([
          ['درآمد', f.revenue], ['سود خالص', f.netIncome],
          ['دارایی‌ها', f.assets], ['بدهی‌ها', f.liabilities],
        ] as [string, number | null][]).map(([label, value]) =>
          <View key={label} style={styles.line}><Text style={{ color: colors.textSecondary }}>{label}</Text><Text style={{ color: colors.text }}>{format(value)} {f.currency}</Text></View>)}
        <Text style={[styles.caption, { color: colors.textSecondary }]}>{f.period} • منبع: ساختگی • تاریخ تأیید: ناموجود</Text>
        <Text style={[styles.caption, { color: colors.textSecondary }]}>حاشیه سود نمونه: {ratios.netMarginPct ?? '—'}٪ • بدهی به دارایی: {ratios.debtToAssetsPct ?? '—'}٪</Text>
      </View>
      <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
        <Text style={[styles.heading, { color: colors.text }]}>ایجنت‌ها و کیا‌شا</Text>
        {[...demo.agents, demo.kiasha].map(agent =>
          <View key={agent.name} style={styles.agent}>
            <Text style={[styles.agentName, { color: colors.text }]}>{agent.name}</Text>
            <Text style={styles.noTrade}>بدون توصیه معاملاتی</Text>
            <Text style={[styles.caption, { color: colors.textSecondary }]}>اطمینان: ناموجود • وضعیت داده: ساختگی</Text>
            <Text style={[styles.caption, { color: colors.textSecondary }]}>{agent.reason}</Text>
          </View>)}
      </View>
      <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
        <Text style={[styles.heading, { color: colors.text }]}>کیفیت داده و حسابرسی قطعی</Text>
        <Text style={[styles.caption, { color: colors.textSecondary }]}>Source: {demo.provenance} • Status: {audit.status}</Text>
        {audit.checks.map(c => <View key={c.key} style={styles.line}><Text style={{ color: colors.text }}>{c.key}</Text><Text style={{ color: c.passed ? '#16a34a' : '#dc2626' }}>{c.passed ? '✓' : '✕'}</Text></View>)}
        <Text style={[styles.caption, { color: colors.textSecondary }]}>Eligible for investment decision: NO</Text>
      </View>
      <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
        <Text style={[styles.heading, { color: colors.text }]}>تحلیل AI شرکت (نمایش آزمایشی)</Text>
        <Text style={[styles.caption, { color: colors.textSecondary }]}>{demo.ai.summary}</Text>
        <Text style={[styles.caption, { color: colors.textSecondary }]}>Route reserved: {demo.ai.route} • {demo.ai.status}</Text>
      </View>
      
    </ScrollView>
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  content: { padding: 18, paddingBottom: 48, gap: 12 },
  title: { fontSize: 23, fontWeight: '800' },
  subtitle: { fontSize: 12, lineHeight: 20 },
  warning: { padding: 14, borderRadius: 12, backgroundColor: '#fef3c7', borderWidth: 1, borderColor: '#f59e0b' },
  warningText: { color: '#78350f', fontSize: 13, fontWeight: '800' },
  card: { padding: 16, borderRadius: 14, gap: 10 },
  heading: { fontSize: 17, fontWeight: '800' },
  line: { flexDirection: 'row', justifyContent: 'space-between', gap: 12, paddingVertical: 5 },
  caption: { fontSize: 12, lineHeight: 19 },
  agent: { paddingVertical: 7, gap: 4, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: '#64748b55' },
  agentName: { fontSize: 14, fontWeight: '700' },
  noTrade: { color: '#b45309', fontSize: 11, fontWeight: '700' },
});
