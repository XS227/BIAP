import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing, ThemeColors } from '@/constants/theme';
import { IranCompanyPicker, useInitialPickedCompany, type PickedCompany } from '@/components/iran-company-picker';
import { describeIranError, fetchIranAudit, type IranAuditCheck, type IranAuditView } from '@/lib/iran-company';
import { auditStatusFa, faDate, faNumber } from '@/lib/data-status';

const tone = (s: string) => (s === 'RED_FLAG' ? Brand.negative : s === 'WATCH' ? Brand.warning : s === 'PASS' ? Brand.positive : undefined);

function CheckCard({ check, colors }: { check: IranAuditCheck; colors: ThemeColors }) {
  const color = tone(check.status) || colors.textSecondary;
  return <View style={[styles.card, { backgroundColor: colors.backgroundElement, borderColor: color }]}>
    <View style={styles.rowBetween}><Text style={[styles.badge, { color }]}>{auditStatusFa(check.status)}</Text><Text style={[styles.cardTitle, { color: colors.text }]}>{check.title}</Text></View>
    {check.value != null ? <Text style={[styles.body, { color: colors.text }]}>نتیجه: {typeof check.value === 'number' ? faNumber(check.value, 3) : check.value}</Text> : null}
    {check.detail ? <Text style={[styles.meta, { color: colors.textSecondary }]}>{check.detail}</Text> : null}
    <Text style={[styles.label, { color: colors.textSecondary }]}>ورودی‌ها</Text>
    {Object.entries(check.inputs || {}).map(([k, v]) => <View key={k} style={styles.rowBetween}>
      <Text style={[styles.body, { color: v == null ? Brand.warning : colors.text }]}>{v == null ? 'ناموجود' : typeof v === 'number' ? faNumber(v, 3) : String(v)}</Text>
      <Text style={[styles.body, { color: colors.textSecondary }]}>{k.replace(/_/g, ' ')}</Text></View>)}
    {check.missing?.length ? <Text style={[styles.meta, { color: Brand.warning }]}>ورودی ناموجود: {check.missing.join('، ')}</Text> : null}
    <Text style={[styles.meta, { color: colors.textSecondary }]}>دوره: {check.period || 'ثبت نشده'} · منبع: {check.source || 'ثبت نشده'}</Text>
  </View>;
}

export default function AuditAnalysisScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [company, setCompany] = useState<PickedCompany | null>(null);
  const [response, setResponse] = useState<{ code: string; audit: IranAuditView | null; error: string }>({
    code: '', audit: null, error: '',
  });
  useInitialPickedCompany(useCallback((c: PickedCompany | null) => setCompany((prev) => prev ?? c), []));
  useEffect(() => {
    if (!company) return;
    let cancelled = false;
    fetchIranAudit(company.code)
      .then((audit) => { if (!cancelled) setResponse({ code: company.code, audit, error: '' }); })
      .catch((e) => { if (!cancelled) setResponse({ code: company.code, audit: null, error: describeIranError(e) }); });
    return () => { cancelled = true; };
  }, [company]);
  const loading = Boolean(company && response.code !== company.code);
  const audit = loading ? null : response.audit;
  const error = loading ? '' : response.error;
  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}><ScrollView contentContainerStyle={styles.content}><View style={styles.max}>
    <Pressable onPress={() => router.back()}><Text style={[styles.back, { color: Brand.primary }]}>بازگشت ›</Text></Pressable>
    <Text style={[styles.title, { color: colors.text }]}>تحلیل حسابرسی</Text>
    <Text style={[styles.sub, { color: colors.textSecondary }]}>غربالگری قطعی پرچم‌های قرمز از صورت‌های مالی ذخیره‌شده. هر بررسی ورودی‌ها، دوره و منبع را نشان می‌دهد؛ اگر ورودی نباشد «داده کافی نیست» می‌آید. این اظهارنظر حسابرسی نیست.</Text>
    <IranCompanyPicker colors={colors} selected={company} onSelect={setCompany} />
    {loading ? <ActivityIndicator color={Brand.primary} style={{ marginTop: 16 }} /> : null}
    {error ? <View style={[styles.card, { backgroundColor: colors.backgroundElement, borderColor: Brand.negative }]}><Text style={[styles.cardTitle, { color: Brand.negative }]}>بررسی‌ها در دسترس نیست</Text><Text style={[styles.body, { color: colors.textSecondary }]}>{error}</Text></View> : null}
    {audit ? <>
      <View style={[styles.card, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
        <Text style={[styles.cardTitle, { color: colors.text }]}>{audit.identity?.symbol} · {audit.identity?.nameFa}</Text>
        <Text style={[styles.meta, { color: colors.textSecondary }]}>دوره‌ی گزارش: {audit.reportPeriod || 'ثبت نشده'} · منبع: {audit.provider || 'ثبت نشده'} · آخرین به‌روزرسانی: {faDate(audit.lastUpdate)}</Text>
        {!audit.financialsAvailable ? <Text style={[styles.body, { color: Brand.warning }]}>صورت مالی برای این شرکت ذخیره نشده است؛ همه‌ی بررسی‌ها «داده کافی نیست» هستند.</Text> : null}
        <Text style={[styles.body, { color: audit.summary.redFlags.length ? Brand.negative : colors.textSecondary }]}>پرچم قرمز: {audit.summary.redFlags.length ? audit.summary.redFlags.join('، ') : 'در بررسی‌های قابل محاسبه نیست'}</Text>
      </View>
      {audit.checks.map((c) => <CheckCard key={c.id} check={c} colors={colors} />)}
      <Text style={[styles.meta, { color: colors.textSecondary, marginTop: 10 }]}>{audit.summary.note}</Text>
    </> : null}
  </View></ScrollView></SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { paddingHorizontal: Spacing.three, paddingBottom: BottomTabInset + Spacing.four },
  max: { maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center', alignItems: 'stretch' },
  back: { fontFamily: Fonts.sans, fontSize: 13, fontWeight: '800', paddingTop: Spacing.three, textAlign: 'right' },
  title: { fontFamily: Fonts.sans, fontSize: 22, fontWeight: '900', marginTop: 6, textAlign: 'right' },
  sub: { fontFamily: Fonts.sans, fontSize: 12, lineHeight: 18, marginTop: 4, marginBottom: Spacing.three, textAlign: 'right' },
  card: { borderRadius: Radius.lg, borderWidth: 1, padding: Spacing.three, marginTop: Spacing.three, alignItems: 'flex-end' },
  rowBetween: { alignSelf: 'stretch', flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginTop: 3 },
  cardTitle: { fontFamily: Fonts.sans, fontSize: 13, fontWeight: '900', flexShrink: 1, textAlign: 'right' },
  badge: { fontFamily: Fonts.sans, fontSize: 11, fontWeight: '900' },
  label: { fontFamily: Fonts.sans, fontSize: 11, fontWeight: '900', marginTop: 8, textAlign: 'right' },
  meta: { fontFamily: Fonts.sans, fontSize: 11, lineHeight: 16, marginTop: 4, textAlign: 'right' },
  body: { fontFamily: Fonts.sans, fontSize: 12, lineHeight: 18, marginTop: 3, textAlign: 'right' },
});
