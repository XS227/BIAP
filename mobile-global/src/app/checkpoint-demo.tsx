import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View, useColorScheme } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Colors } from '@/constants/theme';
import { GLOBAL_CHECKPOINT_DEMO, auditCheckpointDemo, demoFinancialRatios, createCheckpointScenario, explainDemoCompany, selectDemoBroker, type CheckpointScenario } from '@/lib/checkpoint-demo';

import { fetchSavedGlobalCompanyPreview, type SavedGlobalCompanyView } from '@/lib/global-api';
import { assessSavedGlobalCoverage } from '@/lib/saved-company-contract';

const format = (n: number | null) => n === null ? '—' : n.toLocaleString('en-US');

export default function CheckpointDemoScreen() {
  const [scenario, setScenario] = useState<CheckpointScenario>('complete');
  const [selectedBroker, setSelectedBroker] = useState<string | null>(null);
  const [savedCountry, setSavedCountry] = useState('US');
  const [savedExchange, setSavedExchange] = useState('NASDAQ');
  const [savedTicker, setSavedTicker] = useState('AAPL');
  const [savedResult, setSavedResult] = useState<SavedGlobalCompanyView | null>(null);
  const [savedStatus, setSavedStatus] = useState('Not requested');
  const loadSaved = async () => {
    setSavedResult(null);
    setSavedStatus('Loading stored result (GET only)…');
    try {
      const value = await fetchSavedGlobalCompanyPreview(savedCountry, savedExchange, savedTicker);
      if (value.mode !== 'SAVED_READ_ONLY' || value.proxyCalled !== false) throw new Error('Unexpected provenance contract');
      setSavedResult(value);
      setSavedStatus('Stored result loaded; no AI proxy or trading call');
    } catch (error) {
      setSavedStatus(error instanceof Error ? error.message : 'Stored result unavailable');
    }
  };
  const demo = createCheckpointScenario(GLOBAL_CHECKPOINT_DEMO, scenario);
  const audit = auditCheckpointDemo(demo);
  const ratios = demoFinancialRatios(demo);
  const explanation = explainDemoCompany(demo);
  const brokerPreview = selectDemoBroker(demo, selectedBroker);
  const savedCoverage = savedResult ? assessSavedGlobalCoverage(savedResult) : null;
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  if (!__DEV__) return <SafeAreaView style={{ flex: 1, backgroundColor: colors.background, padding: 20 }}><Text style={{ color: colors.text }}>Development preview unavailable.</Text></SafeAreaView>;
  const f = demo.financials;
  return <SafeAreaView style={{ flex: 1, backgroundColor: colors.background }}>
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={[styles.title, { color: colors.text }]}>BIAP Global • Checkpoint 1 Preview</Text>
      <View style={styles.warning}><Text style={styles.warningText}>SYNTHETIC DEMO ONLY — no real prices, agent decisions or investment advice.</Text></View>
      <Text style={[styles.caption, { color: colors.textSecondary }]}>Try financial-data failure states</Text>
      <View style={styles.scenarioRow}>
        {([
          { key: 'complete', label: 'Complete sample' },
          { key: 'missing', label: 'Missing figures' },
          { key: 'invalid', label: 'Invalid balance' },
        ] as const).map(option =>
          <Pressable key={option.key} accessibilityRole="button" onPress={() => setScenario(option.key)}
            style={[styles.scenarioButton, { borderColor: scenario === option.key ? '#d97706' : '#64748b66' }]}>
            <Text style={[styles.scenarioLabel, { color: colors.text }]}>{option.label}</Text>
          </Pressable>)}
      </View>
      <Text style={[styles.subtitle, { color: colors.textSecondary }]}>{demo.company} • {demo.symbol}</Text>
      <Text style={[styles.subtitle, { color: colors.textSecondary }]}>Live data must come from verified sources via the approved proxy.</Text>
      <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
        <Text style={[styles.heading, { color: colors.text }]}>Illustrative financial statements</Text>
        {([
          ['Revenue', f.revenue], ['Net income', f.netIncome],
          ['Assets', f.assets], ['Liabilities', f.liabilities],
        ] as [string, number | null][]).map(([label, value]) =>
          <View key={label} style={styles.line}><Text style={{ color: colors.textSecondary }}>{label}</Text><Text style={{ color: colors.text }}>{format(value)} {f.currency}</Text></View>)}
        <Text style={[styles.caption, { color: colors.textSecondary }]}>{f.period} • Source: {f.source} • Last verified: unavailable</Text>
        <Text style={[styles.caption, { color: colors.textSecondary }]}>Synthetic net margin: {ratios.netMarginPct ?? '—'}% • Debt/assets: {ratios.debtToAssetsPct ?? '—'}%</Text>
      </View>
      <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
        <Text style={[styles.heading, { color: colors.text }]}>Agents & Kiasha</Text>
        {[...demo.agents, demo.kiasha].map(agent =>
          <View key={agent.name} style={styles.agent}>
            <Text style={[styles.agentName, { color: colors.text }]}>{agent.name}</Text>
            <Text style={styles.noTrade}>NO RECOMMENDATION</Text>
            <Text style={[styles.caption, { color: colors.textSecondary }]}>Confidence: unavailable • Data: {agent.dataStatus}</Text>
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
        <Text style={[styles.heading, { color: colors.text }]}>Local snapshot explanation (not AI output)</Text>
        {explanation.findings.map((finding, i) => <Text key={i} style={[styles.caption, { color: colors.textSecondary }]}>{finding}</Text>)}
        <Text style={[styles.caption, { color: colors.textSecondary }]}>Generated locally; proxy called: NO</Text>
        <Text style={[styles.heading, { color: colors.text }]}>AI Company Analysis (preview)</Text>
        <Text style={[styles.caption, { color: colors.textSecondary }]}>{demo.ai.summary}</Text>
        <Text style={[styles.caption, { color: colors.textSecondary }]}>Route reserved: {demo.ai.route} • {demo.ai.status}</Text>
      </View>
      <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
        <Text style={[styles.heading, { color: colors.text }]}>Saved Global analysis • staging GET only</Text>
        <Text style={[styles.caption, { color: colors.textSecondary }]}>Requires the off-by-default BIAP_CHECKPOINT_SAVED_READONLY=1 flag on an isolated development API. Never runs /global/analyze.</Text>
        <View style={styles.scenarioRow}>
          {([
            { value: savedCountry, setter: setSavedCountry, hint: 'Country' },
            { value: savedExchange, setter: setSavedExchange, hint: 'Exchange' },
            { value: savedTicker, setter: setSavedTicker, hint: 'Ticker' },
          ] as const).map(field => (
            <TextInput key={field.hint} accessibilityLabel={field.hint} value={field.value}
              onChangeText={field.setter} autoCapitalize="characters" autoCorrect={false}
              placeholder={field.hint} placeholderTextColor={colors.textSecondary}
              style={[styles.savedInput, { color: colors.text, borderColor: colors.textSecondary }]} />
          ))}
        </View>
        <Pressable accessibilityRole="button" onPress={() => { void loadSaved(); }} style={styles.savedButton}>
          <Text style={styles.savedButtonText}>Load saved result (read-only)</Text>
        </Pressable>
        <Text style={[styles.caption, { color: colors.textSecondary }]}>{savedStatus}</Text>
        {savedResult && <>
          <Text style={[styles.subtitle, { color: colors.text }]}>{savedResult.name ?? 'Unknown issuer'} • {savedResult.ticker} • {savedResult.ledger.status ?? 'Unknown status'}</Text>
          <Text style={[styles.caption, { color: colors.textSecondary }]}>Stored display coverage: {savedCoverage?.complete ? 'All required fields present' : 'PARTIAL — missing or unverified fields'} • Not trade eligible</Text>
          {savedCoverage && !savedCoverage.complete && <Text style={styles.noTrade}>Coverage gaps: {savedCoverage.missing.join(', ')}</Text>}
          <Text style={[styles.caption, { color: colors.textSecondary }]}>Source: {savedResult.ledger.source ?? 'Unknown'} • Analyzed: {savedResult.ledger.analyzedAt ?? 'Unknown'} • Evidence: {savedResult.evidence.status ?? 'Unknown'}</Text>
          <Text style={[styles.caption, { color: colors.textSecondary }]}>Report: {savedResult.evidence.reportPeriod ?? 'Unavailable'} • Provider: {savedResult.evidence.sourceProvider ?? 'Unavailable'}</Text>
          {Object.entries(savedResult.financials).map(([key, value]) => (
            <View key={key} style={styles.line}><Text style={{ color: colors.textSecondary }}>{key}</Text><Text style={{ color: colors.text }}>{format(value)}</Text></View>
          ))}
          <Text style={[styles.caption, { color: colors.textSecondary }]}>Core financial completeness: {savedResult.financialQuality.coreComplete ? 'Yes' : 'Unverified / missing'} • Coverage: {savedResult.financialQuality.coveragePct ?? '—'}</Text>
          <Text style={[styles.heading, { color: colors.text }]}>Saved financial consistency • deterministic</Text>
          <Text style={[styles.caption, { color: colors.textSecondary }]}>Status: {savedResult.audit?.status ?? 'Unavailable'} • Not an external audit; never authorizes investment.</Text>
          {savedResult.audit?.checks.map(check => (
            <View key={check.key} style={styles.line}>
              <Text style={{ color: colors.textSecondary, flex: 1 }}>{check.key}</Text>
              <Text style={{ color: check.passed === true ? '#16a34a' : check.passed === false ? '#dc2626' : colors.textSecondary }}>{check.passed === null ? 'Not checked' : check.passed ? 'Consistent' : 'Failed'}</Text>
            </View>
          ))}
          {savedResult.agents.map((agent, index) => (
            <Text key={index} style={[styles.caption, { color: colors.textSecondary }]}>{agent.name ?? 'Agent'}: vote {agent.vote ?? '—'} • confidence {agent.confidence ?? '—'} • {agent.dataStatus ?? 'Unverified'}</Text>
          ))}
          <Text style={[styles.caption, { color: colors.textSecondary }]}>Kiasha stored call: {savedResult.kiasha.call ?? 'Unavailable'} • Confidence: {savedResult.kiasha.confidence ?? '—'}</Text>
          <Text style={styles.noTrade}>Saved evidence only. Proxy called: NO. Trading eligibility: NO.</Text>
        </>}
      </View>
      <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
        <Text style={[styles.heading, { color: colors.text }]}>Broker selection preview</Text>
        {demo.brokerChoices.map(b =>
          <Pressable key={b.name} accessibilityRole="radio" accessibilityState={{ selected: brokerPreview.selectedBroker === b.name }}
            onPress={() => setSelectedBroker(b.name)}
            style={[styles.line, { borderWidth: 1, borderRadius: 8, borderColor: brokerPreview.selectedBroker === b.name ? '#d97706' : '#64748b55', paddingHorizontal: 10 }]}>
            <Text style={{ color: colors.text }}>{b.name}</Text>
            <Text style={{ color: colors.textSecondary }}>{brokerPreview.selectedBroker === b.name ? 'Selected (demo)' : 'Select'}</Text>
          </Pressable>)}
        <Text style={[styles.caption, { color: colors.textSecondary }]}>Selected: {brokerPreview.selectedBroker ?? 'None'} • Country eligibility not verified</Text>
        <Text style={[styles.caption, { color: colors.textSecondary }]}>Local preference only. No trading API, credentials, or order submission is connected.</Text>
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
  scenarioRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  scenarioButton: { borderWidth: 1, borderRadius: 8, paddingHorizontal: 9, paddingVertical: 7 },
  scenarioLabel: { fontSize: 11, fontWeight: '700' },
  noTrade: { color: '#b45309', fontSize: 11, fontWeight: '700' },
  savedInput: { borderWidth: 1, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6, minWidth: 78, flexGrow: 1 },
  savedButton: { backgroundColor: '#1d4ed8', padding: 10, borderRadius: 8, alignItems: 'center' },
  savedButtonText: { color: '#fff', fontSize: 12, fontWeight: '700' },
});
