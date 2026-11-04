import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { SymbolPicker, type PickedSymbol } from '@/components/symbol-picker';
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
  const params = useLocalSearchParams<{ code?: string; name?: string }>();
  const [picked, setPicked] = useState<PickedSymbol | null>(null);
  const run = useCallback(async (c: PickedSymbol) => {
    setBusy(true); setState(null);
    const rec = await fetchRecommendation(c.code);
    setState(rec ? { title: `${rec.name || c.name || c.symbol} (${c.symbol})`, report: runIranAudit(rec.codalFundamentals as IranFundamentals | null) } : { error: 'پاسخ سرویس تحلیل دریافت نشد.' });
    setBusy(false);
  }, []);
  useFocusEffect(useCallback(() => {
    (async () => {
      if (picked) return;
      if (typeof params.code === 'string' && params.code) { const c = { code: params.code, symbol: String(params.name || params.code), name: String(params.name || '') }; setPicked(c); run(c); return; }
      const c = await getSelectedListedCompany();
      if (!c) { setState({ error: 'یک نماد انتخاب کنید یا از صفحه‌ی نماد وارد شوید.' }); return; }
      const d = { code: c.code, symbol: c.symbol, name: c.name || c.symbol }; setPicked(d); run(d);
    })();
  }, [params.code, params.name, picked, run]));
  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.max}>
          <Pressable onPress={() => router.back()} style={[styles.back, { backgroundColor: colors.backgroundElement }]}><Text style={{ color: colors.text, fontFamily: Fonts.sans, fontSize: 12, fontWeight: '800' }}>بازگشت ›</Text></Pressable>
          <Text style={[styles.title, { color: colors.text }]}>تحلیل حسابرسی</Text>
          <Text style={[styles.body, { color: colors.textSecondary }]}>بررسی‌های قطعی روی صورت‌های مالی ذخیره‌شده. هر بررسی ورودی، دوره و منبع خود را نشان می‌دهد؛ اگر داده نباشد «داده کافی نیست» نمایش داده می‌شود و عددی حدس زده نمی‌شود.</Text>
          <SymbolPicker current={picked?.symbol} onPick={(c) => { setPicked(c); run(c); }} />
          {busy ? <ActivityIndicator style={{ marginTop: 20 }} color={Brand.primary} /> : null}
          {state && 'error' in state ? <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.body, { color: Brand.negative, marginTop: 0 }]}>{state.error}</Text></View> : null}
          {state && 'report' in state ? (
            <>
              <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
                <Text style={[styles.cardTitle, { color: colors.text }]}>{state.title}</Text>
                <Text style={[styles.score, { color: state.report.riskScore == null ? '#64748b' : state.report.riskScore >= 50 ? Brand.negative : state.report.riskScore >= 25 ? Brand.warning : Brand.positive }]}>
                  {state.report.riskScore == null ? `امتیاز ریسک محاسبه نشد: فقط ${state.report.evaluated.toLocaleString('fa-IR')} از ${state.report.total.toLocaleString('fa-IR')} بررسی انجام شد (حداقل ${state.report.minCoverage.toLocaleString('fa-IR')} لازم است)` : `امتیاز ریسک ${state.report.riskScore.toLocaleString('fa-IR')} از ۱۰۰`}
                </Text>
                <Text style={[styles.body, { color: colors.textSecondary }]}>پوشش بررسی‌ها: {state.report.evaluated.toLocaleString('fa-IR')} از {state.report.total.toLocaleString('fa-IR')}. {state.report.riskScore == null ? 'برای نمایش امتیاز حداقل ۶ بررسی لازم است؛ فقط بررسی‌های انجام‌شده زیر معتبرند.' : ''} {state.report.note}</Text>
              </View>
              {state.report.checks.filter((c) => c.status !== 'INSUFFICIENT_DATA').map((c) => (
                <View key={c.id} style={[styles.card, { backgroundColor: colors.backgroundElement, borderRightWidth: 3, borderRightColor: TONE[c.status] }]}>
                  <View style={styles.rowBetween}><Text style={[styles.status, { color: TONE[c.status] }]}>{LABEL[c.status]}</Text><Text style={[styles.cardTitle, { color: colors.text, flex: 1 }]}>{c.title}</Text></View>
                  <Text style={[styles.body, { color: colors.textSecondary }]}>{c.summary}</Text>
                  {c.inputs.map((i) => <Text key={i.label} style={[styles.meta, { color: colors.textSecondary }]}>{i.label}: {fmt(i.value)}</Text>)}
                  {c.status !== 'INSUFFICIENT_DATA' ? <Text style={[styles.meta, { color: colors.textSecondary }]}>دوره: {c.period || '—'} · منبع: {c.source || '—'}</Text> : null}
                </View>
              ))}
              {state.report.checks.some((c) => c.status === 'INSUFFICIENT_DATA') ? (
                <View style={[styles.card, { backgroundColor: colors.backgroundElement, borderRightWidth: 3, borderRightColor: '#64748b' }]}>
                  <Text style={[styles.cardTitle, { color: colors.text }]}>بررسی‌های انجام‌نشده (داده کافی نیست)</Text>
                  {state.report.checks.filter((c) => c.status === 'INSUFFICIENT_DATA').map((c) => <Text key={c.id} style={[styles.meta, { color: colors.textSecondary }]}>• {c.title}</Text>)}
                </View>
              ) : null}
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
