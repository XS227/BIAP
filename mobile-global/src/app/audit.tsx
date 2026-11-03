import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useFocusEffect } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { analyzeGlobalInstrument } from '@/lib/global-api';
import { getSelectedGlobalCompany } from '@/lib/global-company-selection';
import { isFinancialSector, runAudit, type AuditInput, type AuditReport, type CheckStatus } from '@/lib/audit-analysis';

const TONE: Record<CheckStatus, string> = { OK: Brand.positive, WATCH: Brand.warning, FLAG: Brand.negative, INSUFFICIENT_DATA: '#64748b' };

function fmt(v: number | string | null) {
  if (v == null) return '—';
  if (typeof v === 'string') return v;
  return Math.abs(v) >= 1000 ? v.toLocaleString('en-US', { maximumFractionDigits: 0 }) : String(Math.round(v * 1000) / 1000);
}

/** Audit Analysis: deterministic checks on stored BIAP data. No model, no invented numbers. */
export default function AuditAnalysisScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [state, setState] = useState<{ title: string; report: AuditReport } | { error: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useFocusEffect(useCallback(() => {
    let active = true;
    (async () => {
      setBusy(true);
      try {
        const c = await getSelectedGlobalCompany();
        if (!c) { if (active) setState({ error: 'No company selected. Open a company in Market first.' }); return; }
        const a = await analyzeGlobalInstrument(c);
        const fe = (a as unknown as { fundamentalEvidence?: { financialSector?: boolean | null; values?: Record<string, number | null>; reportPeriod?: string | null; sourceProvider?: string | null } }).fundamentalEvidence;
        const co = (a as unknown as { company?: { audit_opinion?: string | null; sector?: string | null; industry?: string | null } }).company;
        const input: AuditInput = {
          values: fe?.values ?? {}, reportPeriod: fe?.reportPeriod ?? null, source: fe?.sourceProvider ?? null,
          auditOpinion: co?.audit_opinion ?? null, financialSector: isFinancialSector(fe?.financialSector, co?.sector, co?.industry), distress: (a as unknown as { distress?: AuditInput['distress'] }).distress ?? null,
        };
        if (active) setState({ title: `${a.name || c.name} (${a.ticker || c.ticker})`, report: runAudit(input) });
      } catch (e) {
        if (active) setState({ error: e instanceof Error ? e.message : 'The analysis service did not respond.' });
      } finally { if (active) setBusy(false); }
    })();
    return () => { active = false; };
  }, []));

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.max}>
          <Pressable onPress={() => router.back()} style={[styles.back, { backgroundColor: colors.backgroundElement }]}><Text style={{ color: colors.text, fontFamily: Fonts.sans, fontSize: 11, fontWeight: '800' }}>‹ Back</Text></Pressable>
          <Text style={[styles.title, { color: colors.text }]}>Audit Analysis</Text>
          <Text style={[styles.body, { color: colors.textSecondary }]}>Deterministic checks on stored BIAP data. Each check shows its inputs, period and source; missing data is shown as INSUFFICIENT_DATA, never guessed.</Text>
          {busy ? <ActivityIndicator style={{ marginTop: 20 }} color={Brand.primary} /> : null}
          {state && 'error' in state ? <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.body, { color: Brand.negative, marginTop: 0 }]}>{state.error}</Text></View> : null}
          {state && 'report' in state ? (
            <>
              <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
                <Text style={[styles.cardTitle, { color: colors.text }]}>{state.title}</Text>
                <Text style={[styles.score, { color: state.report.riskScore == null ? '#64748b' : state.report.riskScore >= 50 ? Brand.negative : state.report.riskScore >= 25 ? Brand.warning : Brand.positive }]}>
                  {state.report.riskScore == null ? 'INSUFFICIENT_DATA' : `Risk score ${state.report.riskScore}/100`}
                </Text>
                <Text style={[styles.body, { color: colors.textSecondary }]}>{state.report.evaluated} of {state.report.checks.length} checks could be evaluated. {state.report.note}</Text>
              </View>
              {state.report.checks.map((c) => (
                <View key={c.id} style={[styles.card, { backgroundColor: colors.backgroundElement, borderLeftWidth: 3, borderLeftColor: TONE[c.status] }]}>
                  <View style={styles.rowBetween}><Text style={[styles.cardTitle, { color: colors.text, flex: 1 }]}>{c.title}</Text><Text style={[styles.status, { color: TONE[c.status] }]}>{c.status}</Text></View>
                  <Text style={[styles.body, { color: colors.textSecondary }]}>{c.summary}</Text>
                  {c.inputs.filter((i) => c.status !== 'INSUFFICIENT_DATA' || i.value != null).slice(0, 12).map((i) => <Text key={i.label} style={[styles.meta, { color: colors.textSecondary }]}>{i.label}: {fmt(i.value)}</Text>)}
                  <Text style={[styles.meta, { color: colors.textSecondary }]}>Period: {c.period || '—'} • Source: {c.source || '—'}</Text>
                </View>
              ))}
            </>
          ) : null}
          <Text style={[styles.disclaimer, { color: colors.textSecondary }]}>Heuristic screening, not an audit opinion, credit rating or investment advice.</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { paddingHorizontal: Spacing.three, paddingBottom: BottomTabInset + Spacing.six },
  max: { maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center', paddingTop: Spacing.four },
  back: { alignSelf: 'flex-start', paddingHorizontal: 11, paddingVertical: 8, borderRadius: 18 },
  title: { fontFamily: Fonts.sans, fontSize: 22, fontWeight: '900', marginTop: 12 },
  body: { fontFamily: Fonts.sans, fontSize: 11, lineHeight: 17, marginTop: 6 },
  card: { borderRadius: Radius.lg, padding: Spacing.four, marginTop: 12 },
  cardTitle: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '900' },
  score: { fontFamily: Fonts.mono, fontSize: 20, fontWeight: '900', marginTop: 8 },
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  status: { fontFamily: Fonts.mono, fontSize: 10, fontWeight: '900' },
  meta: { fontFamily: Fonts.mono, fontSize: 9.5, marginTop: 3 },
  disclaimer: { fontFamily: Fonts.sans, fontSize: 9, lineHeight: 14, textAlign: 'center', marginTop: 18 },
});
