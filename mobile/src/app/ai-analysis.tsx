import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { IranCompanyPicker, useInitialPickedCompany, type PickedCompany } from '@/components/iran-company-picker';
import { describeIranError, requestIranAiReport, type IranAiReport } from '@/lib/iran-company';
import { faDate } from '@/lib/data-status';

export default function AiAnalysisScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [company, setCompany] = useState<PickedCompany | null>(null);
  const [report, setReport] = useState<IranAiReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  useInitialPickedCompany(useCallback((c: PickedCompany | null) => setCompany((prev) => prev ?? c), []));
  const choose = (c: PickedCompany) => { setCompany(c); setReport(null); setError(''); };
  const run = async () => {
    if (!company) return;
    setLoading(true); setError(''); setReport(null);
    try { setReport(await requestIranAiReport(company.code)); } catch (e) { setError(describeIranError(e)); } finally { setLoading(false); }
  };
  const lines = report ? report.report.split('\n') : [];
  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}><ScrollView contentContainerStyle={styles.content}><View style={styles.max}>
    <Pressable onPress={() => router.back()}><Text style={[styles.back, { color: Brand.primary }]}>بازگشت ›</Text></Pressable>
    <Text style={[styles.title, { color: colors.text }]}>تحلیل شرکت با هوش مصنوعی</Text>
    <Text style={[styles.sub, { color: colors.textSecondary }]}>گزارش کوتاه فقط از داده‌های ذخیره‌شده‌ی BIAP (عامل‌ها، کیاشا، صورت‌های مالی، نسبت‌ها) نوشته می‌شود. برای هر شرکت در روز یک گزارش ذخیره می‌شود.</Text>
    <IranCompanyPicker colors={colors} selected={company} onSelect={choose} />
    <Pressable disabled={!company || loading} onPress={run} style={[styles.button, { backgroundColor: Brand.primary, opacity: !company || loading ? 0.5 : 1 }]}><Text style={styles.buttonText}>{loading ? 'در حال تولید…' : 'تولید گزارش'}</Text></Pressable>
    {loading ? <ActivityIndicator color={Brand.primary} style={{ marginTop: 16 }} /> : null}
    {error ? <View style={[styles.card, { backgroundColor: colors.backgroundElement, borderColor: Brand.negative }]}><Text style={[styles.cardTitle, { color: Brand.negative }]}>گزارش در دسترس نیست</Text><Text style={[styles.body, { color: colors.textSecondary }]}>{error}</Text></View> : null}
    {report ? <View style={[styles.card, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
      <Text style={[styles.disclaimer, { color: Brand.warning }]}>تولیدشده با هوش مصنوعی؛ توصیه‌ی سرمایه‌گذاری نیست.</Text>
      <Text style={[styles.cardTitle, { color: colors.text }]}>{report.identity?.symbol} · {report.identity?.nameFa}</Text>
      <Text style={[styles.meta, { color: colors.textSecondary }]}>{report.cached ? 'گزارش ذخیره‌شده‌ی امروز' : 'گزارش جدید'} · تولید: {faDate(report.generatedAt)} · آخرین به‌روزرسانی داده: {faDate(report.dataLastUpdate)} · تحلیل کیاشا: {faDate(report.kiashaGeneratedAt)}</Text>
      {lines.map((line, i) => line.startsWith('## ')
        ? <Text key={i} style={[styles.h, { color: colors.text }]}>{line.replace(/^##\s*/, '')}</Text>
        : line.trim() ? <Text key={i} style={[styles.body, { color: colors.textSecondary }]}>{line.replace(/^\s*[-*]\s*/, '• ')}</Text> : null)}
    </View> : null}
  </View></ScrollView></SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { paddingHorizontal: Spacing.three, paddingBottom: BottomTabInset + Spacing.four },
  max: { maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center', alignItems: 'stretch' },
  back: { fontFamily: Fonts.sans, fontSize: 13, fontWeight: '800', paddingTop: Spacing.three, textAlign: 'right' },
  title: { fontFamily: Fonts.sans, fontSize: 22, fontWeight: '900', marginTop: 6, textAlign: 'right' },
  sub: { fontFamily: Fonts.sans, fontSize: 12, lineHeight: 18, marginTop: 4, marginBottom: Spacing.three, textAlign: 'right' },
  button: { borderRadius: Radius.md, paddingVertical: 12, alignItems: 'center' },
  buttonText: { color: '#fff', fontFamily: Fonts.sans, fontSize: 14, fontWeight: '900' },
  card: { borderRadius: Radius.lg, borderWidth: 1, padding: Spacing.three, marginTop: Spacing.three, alignItems: 'flex-end' },
  cardTitle: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '900', textAlign: 'right' },
  disclaimer: { fontFamily: Fonts.sans, fontSize: 12, fontWeight: '900', marginBottom: 6, textAlign: 'right' },
  meta: { fontFamily: Fonts.sans, fontSize: 11, lineHeight: 16, marginTop: 3, textAlign: 'right' },
  h: { fontFamily: Fonts.sans, fontSize: 13, fontWeight: '900', marginTop: 12, textAlign: 'right' },
  body: { fontFamily: Fonts.sans, fontSize: 12, lineHeight: 19, marginTop: 4, textAlign: 'right' },
});
