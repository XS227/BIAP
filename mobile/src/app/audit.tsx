import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { fetchRecommendation } from '@/lib/api';
import { getSelectedListedCompany } from '@/lib/listed-company-selection';
import { runIranAudit, type AuditReport, type CheckStatus, type IranFundamentals } from '@/lib/audit-analysis';

const TONE: Record<CheckStatus, string> = { OK: Brand.positive, WATCH: Brand.warning, FLAG: Brand.negative, INSUFFICIENT_DATA: '#64748b' };
const LABEL: Record<CheckStatus, string> = { OK: 'مناسب', WATCH: 'نیازمند توجه', FLAG: 'هشدار', INSUFFICIENT_DATA: 'داده کافی نیست' };
const fmt = (v: number | string | null) => (v == null ? '—' : typeof v === 'string' ? v : v.toLocaleString('fa-IR', { maximumFractionDigits: 2 }));

/** «تحلیل حسابرسی» — deterministic checks over the stored CODAL statements. */
export default function AuditScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [state, setState] = useState<{ title: string; report: AuditReport } | { error: string } | null>(null); const [busy, setBusy] = useState(false);
  useFocusEffect(useCallback(() => {
    let active = true;
    (async () => {
      setBusy(true);
      const c = await getSelectedListedCompany();
      if (!c) { if (active) { setState({ error: 'ابتدا از بخش بازار یک شرکت را انتخاب کنید.' }); setBusy(false); } return; }
      const rec = await fetchRecommendation(c.symbol);
      if (active) {
        setState(rec ? { title: `${rec.name || c.name || c.symbol} (${c.symbol})`, report: runIranAudit(rec.codalFundamentals as IranFundamentals | null) } : { error: 'پاسخ سرویس تحلیل دریافت نشد.' });
        setBusy(false);
      }
    })();
    return () => { active = false; };
  }, []));
  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.max}>
          <Pressable onPress={() => router.back()} style={[styles.back, { backgroundColor: colors.backgroundElement }]}><Text style={{ color: colors.text, fontFamily: Fonts.sans, fontSize: 12, fontWeight: '800' }}>بازگشت ›</Text></Pressable>
          <Text style={[styles.title, { color: colors.text }]}>تحلیل حسابرسی</Text>
          <Text style={[styles.body, { color: colors.textSecondary }]}>بررسی‌های قطعی روی صورت‌های مالی ذخیره‌شده. هر بررسی ورودی، دوره و منبع خود را نشان می‌دهد؛ اگر داده نباشد «داده کافی نیست» نمایش داده می‌شود و عددی حدس زده نمی‌شود.</Text>
          {busy ? <ActivityIndicator style={{ marginTop: 20 }} color={Brand.primary} /> : null}
          {state && 'error' in state ? <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.body, { color: Brand.negative, marginTop: 0 }]}>{state.error}</Text></View> : null}
          {state && 'report' in state ? (
            <>
              <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
                <Text style={[styles.cardTitle, { color: colors.text }]}>{state.title}</Text>
                <Text style={[styles.score, { color: state.report.riskScore == null ? '#64748b' : state.report.riskScore >= 50 ? Brand.negative : state.report.riskScore >= 25 ? Brand.warning : Brand.positive }]}>
                  {state.report.riskScore == null ? 'داده کافی نیست' : `امتیاز ریسک ${state.report.riskScore.toLocaleString('fa-IR')} از ۱۰۰`}
                </Text>
                <Text style={[styles.body, { color: colors.textSecondary }]}>{state.report.evaluated.toLocaleString('fa-IR')} بررسی از {state.report.checks.length.toLocaleString('fa-IR')} بررسی قابل انجام بود. {state.report.note}</Text>
              </View>
              {state.report.checks.map((c) => (
                <View key={c.id} style={[styles.card, { backgroundColor: colors.backgroundElement, borderRightWidth: 3, borderRightColor: TONE[c.status] }]}>
                  <View style={styles.rowBetween}><Text style={[styles.status, { color: TONE[c.status] }]}>{LABEL[c.status]}</Text><Text style={[styles.cardTitle, { color: colors.text, flex: 1 }]}>{c.title}</Text></View>
                  <Text style={[styles.body, { color: colors.textSecondary }]}>{c.summary}</Text>
                  {c.inputs.map((i) => <Text key={i.label} style={[styles.meta, { color: colors.textSecondary }]}>{i.label}: {fmt(i.value)}</Text>)}
                  {c.status !== 'INSUFFICIENT_DATA' ? <Text style={[styles.meta, { color: colors.textSecondary }]}>دوره: {c.period || '—'} · منبع: {c.source || '—'}</Text> : null}
                </View>
              ))}
            </>
          ) : null}
          <Text style={[styles.disclaimer, { color: colors.textSecondary }]}>غربالگری ساده است؛ نظر حسابرس، رتبه‌ی اعتباری یا توصیه‌ی سرمایه‌گذاری نیست.</Text>
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
  body: { fontFamily: Fonts.sans, fontSize: 12, lineHeight: 20, marginTop: 6, textAlign: 'right' },
  card: { borderRadius: Radius.lg, padding: Spacing.four, marginTop: 12 },
  cardTitle: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '900', textAlign: 'right' },
  score: { fontFamily: Fonts.mono, fontSize: 18, fontWeight: '900', marginTop: 8, textAlign: 'right' },
  rowBetween: { flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  status: { fontFamily: Fonts.sans, fontSize: 11, fontWeight: '900' },
  meta: { fontFamily: Fonts.sans, fontSize: 10.5, marginTop: 3, textAlign: 'right' },
  disclaimer: { fontFamily: Fonts.sans, fontSize: 11, lineHeight: 16, textAlign: 'center', marginTop: 18 },
});
