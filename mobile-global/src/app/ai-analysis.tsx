import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useFocusEffect } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { getSelectedGlobalCompany } from '@/lib/global-company-selection';
import { AI_STATUS_EN, fetchAiCompanyAnalysis, type AiAnalysis } from '@/lib/ai-analysis-api';

const SECTIONS = [
  { key: 'strengths', title: 'Strengths', tone: Brand.positive }, { key: 'weaknesses', title: 'Weaknesses', tone: Brand.warning },
  { key: 'risks', title: 'Risks', tone: Brand.negative }, { key: 'missingData', title: 'Missing data', tone: '#64748b' },
] as const;

/** AI Company Analysis: a narrative the server builds from stored BIAP results only. */
export default function AiAnalysisScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [title, setTitle] = useState(''); const [busy, setBusy] = useState(false);
  const [state, setState] = useState<AiAnalysis | { error: string } | null>(null);
  useFocusEffect(useCallback(() => {
    let active = true;
    (async () => {
      setBusy(true);
      const c = await getSelectedGlobalCompany();
      if (!c) { if (active) { setState({ error: 'No company selected. Open a company in Market first.' }); setBusy(false); } return; }
      if (active) setTitle(`${c.name} (${c.ticker})`);
      const res = await fetchAiCompanyAnalysis(c);
      if (active) { setState(res); setBusy(false); }
    })();
    return () => { active = false; };
  }, []));
  const ok = state && 'status' in state && state.status === 'OK' ? state : null;
  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.max}>
          <Pressable onPress={() => router.back()} style={[styles.back, { backgroundColor: colors.backgroundElement }]}><Text style={{ color: colors.text, fontFamily: Fonts.sans, fontSize: 11, fontWeight: '800' }}>‹ Back</Text></Pressable>
          <Text style={[styles.title, { color: colors.text }]}>AI Company Analysis</Text>
          <Text style={[styles.body, { color: colors.textSecondary }]}>Written from stored BIAP results only (agents, Kiasha, statements, distress). One report per company per day.</Text>
          {title ? <Text style={[styles.cardTitle, { color: colors.text, marginTop: 10 }]}>{title}</Text> : null}
          {busy ? <ActivityIndicator style={{ marginTop: 20 }} color={Brand.primary} /> : null}
          {state && 'error' in state ? <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.body, { color: Brand.negative, marginTop: 0 }]}>{state.error}</Text></View> : null}
          {state && 'status' in state && state.status !== 'OK' ? <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.body, { color: colors.text, marginTop: 0 }]}>{AI_STATUS_EN[state.status]}</Text></View> : null}
          {ok?.report ? (
            <>
              <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
                <Text style={[styles.body, { color: colors.text, marginTop: 0 }]}>{ok.report.summary}</Text>
                <Text style={[styles.meta, { color: colors.textSecondary }]}>{ok.cached ? 'Cached for today' : 'Freshly generated'} • {ok.date}</Text>
              </View>
              {SECTIONS.map((s) => ok.report && ok.report[s.key].length ? (
                <View key={s.key} style={[styles.card, { backgroundColor: colors.backgroundElement, borderLeftWidth: 3, borderLeftColor: s.tone }]}>
                  <Text style={[styles.cardTitle, { color: colors.text }]}>{s.title}</Text>
                  {ok.report[s.key].map((line, i) => <Text key={i} style={[styles.body, { color: colors.textSecondary }]}>• {line}</Text>)}
                </View>
              ) : null)}
            </>
          ) : null}
          <Text style={[styles.disclaimer, { color: colors.textSecondary }]}>AI-generated, not investment advice</Text>
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
