import { ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Colors } from '@/constants/theme';
import { GLOBAL_CHECKPOINT_DEMO, auditCheckpointDemo } from '@/lib/checkpoint-demo';

const demo = GLOBAL_CHECKPOINT_DEMO;
const audit = auditCheckpointDemo(demo);
const format = (n: number | null) => n === null ? '—' : n.toLocaleString('en-US');

export default function CheckpointDemoScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  if (!__DEV__) return <SafeAreaView style={{ flex: 1, backgroundColor: colors.background, padding: 20 }}><Text style={{ color: colors.text }}>Development preview unavailable.</Text></SafeAreaView>;
  const f = demo.financials;
  return <SafeAreaView style={{ flex: 1, backgroundColor: colors.background }}>
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={[styles.title, { color: colors.text }]}>BIAP Global • Checkpoint 1 Preview</Text>
      <View style={styles.warning}><Text style={styles.warningText}>SYNTHETIC DEMO ONLY — no real prices, agent decisions or investment advice.</Text></View>
      <Text style={[styles.subtitle, { color: colors.textSecondary }]}>{demo.company} • {demo.symbol}</Text>
      <Text style={[styles.subtitle, { color: colors.textSecondary }]}>Live data must come from verified sources via the approved proxy.</Text>
      <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
        <Text style={[styles.heading, { color: colors.text }]}>Illustrative financial statements</Text>
        {([
          ['Revenue', f.revenue], ['Net income', f.netIncome],
          ['Assets', f.assets], ['Liabilities', f.liabilities],
        ] as [string, number | null][]).map(([label, value]) =>
          <View key={label} style={styles.line}><Text style={{ color: colors.textSecondary }}>{label}</Text><Text style={{ color: colors.text }}>{format(value)} {f.currency}</Text></View>)}
        <Text style={[styles.caption, { color: colors.textSecondary }]}>{f.period}</Text>
      </View>
      <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
        <Text style={[styles.heading, { color: colors.text }]}>Agents & Kiasha</Text>
        {[...demo.agents, demo.kiasha].map(agent =>
          <View key={agent.name} style={styles.agent}>
            <Text style={[styles.agentName, { color: colors.text }]}>{agent.name}</Text>
            <Text style={styles.noTrade}>NO RECOMMENDATION</Text>
            <Text style={[styles.caption, { color: colors.textSecondary }]}>{agent.reason}</Text>
          </View>)}
      </View>
      <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
        <Text style={[styles.heading, { color: colors.text }]}>Data quality & deterministic audit</Text>
        <Text style={[styles.caption, { color: colors.textSecondary }]}>Source: {demo.provenance} • Status: {audit.status}</Text>
        {audit.checks.map(c => <View key={c.key} style={styles.line}><Text style={{ color: colors.text }}>{c.key}</Text><Text style={{ color: c.passed ? '#16a34a' : '#dc2626' }}>{c.passed ? '✓' : '✕'}</Text></View>)}
        <Text style={[styles.caption, { color: colors.textSecondary }]}>Eligible for investment decision: NO</Text>
      </View>
      <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
        <Text style={[styles.heading, { color: colors.text }]}>AI Company Analysis (preview)</Text>
        <Text style={[styles.caption, { color: colors.textSecondary }]}>{demo.ai.summary}</Text>
        <Text style={[styles.caption, { color: colors.textSecondary }]}>Route reserved: {demo.ai.route} • {demo.ai.status}</Text>
      </View>
      <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
        <Text style={[styles.heading, { color: colors.text }]}>Broker selection preview</Text>
        {demo.brokerChoices.map(b => <View key={b.name} style={styles.line}><Text style={{ color: colors.text }}>{b.name}</Text><Text style={{ color: colors.textSecondary }}>Preview only • disabled</Text></View>)}
        <Text style={[styles.caption, { color: colors.textSecondary }]}>No trading API, credentials, or order submission is connected.</Text>
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
