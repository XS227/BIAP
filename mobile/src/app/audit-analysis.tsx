import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { fetchIranFinancialInboxAudit, type IranFinancialInboxAudit } from '@/lib/api';

const SYMBOLS = ['پکرمان', 'فولاد', 'خودرو'] as const;

export default function AuditAnalysisScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [symbol, setSymbol] = useState<string>('پکرمان');
  const [refresh, setRefresh] = useState(0);
  const [result, setResult] = useState<IranFinancialInboxAudit | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    void fetchIranFinancialInboxAudit(symbol)
      .then(data => { if (active) setResult(data); })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : 'اطلاعات قابل تأیید نیست.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [symbol, refresh]);

  const selectSymbol = (next: string) => {
    if (next === symbol) return;
    setLoading(true);
    setResult(null);
    setError('');
    setSymbol(next);
  };
  const reload = () => {
    setLoading(true);
    setResult(null);
    setError('');
    setRefresh(n => n + 1);
  };
  const company = result?.company;
  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
    <ScrollView contentContainerStyle={styles.content}><View style={styles.max}>
      <Pressable onPress={() => router.back()}><Text style={[styles.back, { color: colors.textSecondary }]}>← بازگشت</Text></Pressable>
      <Text style={[styles.title, { color: colors.text }]}>Audit Analysis · ایران</Text>
      <Text style={[styles.notice, { color: colors.textSecondary }]}>
        فقط خروجی‌های دارای manifest و SHA-256 معتبر از Liara inbox. هیچ درخواست مستقیم CODAL، تحلیل AI جدید، تغییر قیمت یا سفارش معاملاتی انجام نمی‌شود.
      </Text>
      <View style={styles.picker}>{SYMBOLS.map(item =>
        <Pressable key={item} onPress={() => selectSymbol(item)}
          style={[styles.choice, { backgroundColor: item === symbol ? Brand.primary : colors.backgroundElement }]}>
          <Text style={{ color: item === symbol ? '#fff' : colors.text, fontWeight: '800' }}>{item}</Text>
        </Pressable>)}</View>
      <Pressable onPress={reload} style={[styles.refresh, { backgroundColor: colors.backgroundElement }]}>
        <Text style={{ color: colors.text }}>بررسی دوباره داده ذخیره‌شده</Text>
      </Pressable>
      {loading ? <ActivityIndicator color={Brand.primary} /> : null}
      {error ? <Text style={[styles.error, { color: Brand.negative }]}>{error} داده مالی تأییدنشده نمایش داده نمی‌شود.</Text> : null}
      {result && company ? <>
        <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
          <Text style={[styles.company, { color: colors.text }]}>{company.issuer || symbol}</Text>
          <Text style={[styles.meta, { color: colors.textSecondary }]}>آخرین بسته تأییدشده: {result.newestExport || 'نامشخص'} · بسته‌ها: {result.verifiedExports}</Text>
          <Text style={[styles.meta, { color: colors.textSecondary }]}>پرونده‌های مالی: {company.financial_filings} · HTML موجود: {company.html_available} · HTML ناموجود: {company.html_missing}</Text>
          <Text style={[styles.meta, { color: Brand.warning }]}>نیازمند بررسی صادرکننده: {company.explicit_issuer_review} · وضعیت حسابرسی: {company.audit_status}</Text>
          <Text style={[styles.meta, { color: Brand.negative }]}>صورت مالی برای AI تأیید نشده است؛ اختلاف قیمت پکرمان از inbox مالی قابل اثبات نیست.</Text>
        </View>
        {company.filing_evidence.slice(0, 12).map((filing, i) =>
          <View key={filing.tracing_no + '-' + i} style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
            <Text style={[styles.meta, { color: colors.text }]}>شناسه گزارش: {filing.tracing_no || 'ناموجود'} · دوره: {filing.period_end_jalali || 'نامشخص'}</Text>
            <Text style={[styles.meta, { color: colors.textSecondary }]}>دامنه: {filing.scope_claim} · حسابرسی: {filing.assurance_claim}</Text>
            <Text style={[styles.meta, { color: colors.textSecondary }]}>صادرکننده: {filing.issuer_evidence} · HTML: {filing.html_available ? 'موجود، تأیید حسابداری نشده' : 'ناموجود'}</Text>
            <Text style={[styles.meta, { color: Brand.warning }]}>{filing.quality_gate}</Text>
          </View>)}
      </> : null}
    </View></ScrollView>
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { paddingHorizontal: Spacing.three, paddingTop: Spacing.three, paddingBottom: BottomTabInset + Spacing.four },
  max: { maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' },
  back: { fontFamily: Fonts.sans, fontSize: 13, marginBottom: Spacing.three },
  title: { fontFamily: Fonts.sans, fontSize: 23, fontWeight: '900', textAlign: 'right' },
  notice: { fontFamily: Fonts.sans, fontSize: 12, lineHeight: 21, textAlign: 'right', marginVertical: Spacing.three },
  picker: { flexDirection: 'row-reverse', gap: Spacing.two },
  choice: { flex: 1, paddingVertical: Spacing.three, alignItems: 'center', borderRadius: Radius.md },
  refresh: { padding: Spacing.three, borderRadius: Radius.md, marginVertical: Spacing.three, alignItems: 'center' },
  error: { fontFamily: Fonts.sans, fontSize: 12, textAlign: 'right', lineHeight: 20 },
  card: { padding: Spacing.three, borderRadius: Radius.md, marginBottom: Spacing.two },
  company: { fontFamily: Fonts.sans, fontSize: 16, fontWeight: '900', textAlign: 'right' },
  meta: { fontFamily: Fonts.sans, fontSize: 11, lineHeight: 19, marginTop: Spacing.two, textAlign: 'right' },
});
