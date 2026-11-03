import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { getSelectedListedCompany } from '@/lib/listed-company-selection';
import { AI_STATUS_FA, fetchAiCompanyAnalysis, type AiAnalysis } from '@/lib/ai-analysis-api';

const SECTIONS: { key: 'strengths' | 'weaknesses' | 'risks' | 'missingData'; title: string; tone: string }[] = [
  { key: 'strengths', title: 'نقاط قوت', tone: Brand.positive }, { key: 'weaknesses', title: 'نقاط ضعف', tone: Brand.warning },
  { key: 'risks', title: 'ریسک‌ها', tone: Brand.negative }, { key: 'missingData', title: 'داده‌های ناقص', tone: '#64748b' },
];

/** «تحلیل شرکت با هوش مصنوعی» — narrative built by the server from stored BIAP results only. */
export default function AiAnalysisScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [title, setTitle] = useState(''); const [busy, setBusy] = useState(false);
  const [state, setState] = useState<AiAnalysis | { error: string } | null>(null);

  useFocusEffect(useCallback(() => {
    let active = true;
    (async () => {
      setBusy(true);
      const c = await getSelectedListedCompany();
      if (!c) { if (active) { setState({ error: 'ابتدا از بخش بازار یک شرکت را انتخاب کنید.' }); setBusy(false); } return; }
      if (active) setTitle(`${c.name || c.symbol} (${c.symbol})`);
      const res = await fetchAiCompanyAnalysis(c.symbol);
      if (active) { setState(res); setBusy(false); }
    })();
    return () => { active = false; };
  }, []));

  const ok = state && 'status' in state && state.status === 'OK' ? state : null;
  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.max}>
          <Pressable onPress={() => router.back()} style={[styles.back, { backgroundColor: colors.backgroundElement }]}><Text style={{ color: colors.text, fontFamily: Fonts.sans, fontSize: 12, fontWeight: '800' }}>بازگشت ›</Text></Pressable>
          <Text style={[styles.title, { color: colors.text }]}>تحلیل شرکت با هوش مصنوعی</Text>
          <Text style={[styles.body, { color: colors.textSecondary }]}>این متن فقط از نتایج ذخیره‌شده‌ی BIAP (عامل‌ها، کیاشا، صورت‌های مالی) ساخته می‌شود؛ هر روز برای هر شرکت یک‌بار تولید و نگهداری می‌شود.</Text>
          {title ? <Text style={[styles.sub, { color: colors.text }]}>{title}</Text> : null}
          {busy ? <ActivityIndicator style={{ marginTop: 20 }} color={Brand.primary} /> : null}
          {state && 'error' in state ? <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.body, { color: Brand.negative, marginTop: 0 }]}>{state.error}</Text></View> : null}
          {state && 'status' in state && state.status !== 'OK' ? <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.body, { color: colors.text, marginTop: 0 }]}>{AI_STATUS_FA[state.status]}</Text></View> : null}
          {ok?.report ? (
            <>
              <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
                <Text style={[styles.body, { color: colors.text, marginTop: 0 }]}>{ok.report.summary}</Text>
                <Text style={[styles.meta, { color: colors.textSecondary }]}>{ok.cached ? 'نسخه‌ی ذخیره‌شده‌ی امروز' : 'تازه تولید شد'} · {ok.date}</Text>
              </View>
              {SECTIONS.map((s) => ok.report && ok.report[s.key].length ? (
                <View key={s.key} style={[styles.card, { backgroundColor: colors.backgroundElement, borderRightWidth: 3, borderRightColor: s.tone }]}>
                  <Text style={[styles.cardTitle, { color: colors.text }]}>{s.title}</Text>
                  {ok.report[s.key].map((line, i) => <Text key={i} style={[styles.body, { color: colors.textSecondary }]}>• {line}</Text>)}
                </View>
              ) : null)}
            </>
          ) : null}
          <Text style={[styles.disclaimer, { color: colors.textSecondary }]}>تولیدشده با هوش مصنوعی؛ توصیه‌ی سرمایه‌گذاری نیست</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 }, content: { paddingHorizontal: Spacing.three, paddingBottom: BottomTabInset + Spacing.six },
  max: { maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center', paddingTop: Spacing.four },
  back: { alignSelf: 'flex-end', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 18 },
  title: { fontFamily: Fonts.sans, fontSize: 22, fontWeight: '900', marginTop: 12, textAlign: 'right' },
  sub: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '800', marginTop: 10, textAlign: 'right' },
  body: { fontFamily: Fonts.sans, fontSize: 12, lineHeight: 20, marginTop: 6, textAlign: 'right' },
  card: { borderRadius: Radius.lg, padding: Spacing.four, marginTop: 12 },
  cardTitle: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '900', textAlign: 'right' },
  meta: { fontFamily: Fonts.sans, fontSize: 10, marginTop: 8, textAlign: 'right' },
  disclaimer: { fontFamily: Fonts.sans, fontSize: 11, lineHeight: 16, textAlign: 'center', marginTop: 18, fontWeight: '700' },
});
