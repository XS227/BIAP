import { useCallback, useMemo, useState } from 'react';
import {
  ActivityIndicator, Linking, Pressable, RefreshControl, SafeAreaView,
  ScrollView, StyleSheet, Text, TextInput, View, useColorScheme,
} from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { analyzeGlobalInstrument, type GlobalAnalysis, type GlobalInstrument } from '@/lib/global-api';
import { getGlobalMarketSelection } from '@/lib/global-market-selection';
import { getSelectedGlobalCompany } from '@/lib/global-company-selection';
import {
  answerIntelligenceQuestion, buildIntelligenceMetrics, formatIntelligenceMetric,
  type IntelligenceAnswer,
} from '@/lib/intelligence-summary';

const PROMPTS = [
  { fa: 'درآمد شرکت', en: 'Revenue', question: 'درآمد شرکت چقدر است؟' },
  { fa: 'سودآوری', en: 'Profit', question: 'سود خالص چقدر است؟' },
  { fa: 'بدهی', en: 'Debt', question: 'بدهی شرکت چقدر است؟' },
  { fa: 'ریسک', en: 'Risk', question: 'ریسک شرکت چقدر است؟' },
  { fa: 'منابع', en: 'Sources', question: 'منابع گزارش چیست؟' },
];

export default function IntelligenceScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [selected, setSelected] = useState<GlobalInstrument | null>(null);
  const [analysis, setAnalysis] = useState<GlobalAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<IntelligenceAnswer | null>(null);
  const [language, setLanguage] = useState<'fa' | 'en'>('fa');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    setAnswer(null);
    try {
      const market = await getGlobalMarketSelection();
      const stock = await getSelectedGlobalCompany();
      if (!stock || stock.country !== market.country || stock.exchange !== market.exchange) {
        setSelected(null);
        setAnalysis(null);
        return;
      }
      setSelected(stock);
      const result = await analyzeGlobalInstrument(stock);
      setAnalysis(result);
    } catch (err) {
      setAnalysis(null);
      setError(err instanceof Error ? err.message.slice(0, 240) : 'Global analysis is unavailable.');
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => {
    void load();
    return () => {};
  }, [load]));

  const metrics = useMemo(() => analysis ? buildIntelligenceMetrics(analysis) : [], [analysis]);
  const evidence = analysis?.evidence;
  const filing = analysis?.fundamentalEvidence;
  const rawSource = filing?.sourceUrl || analysis?.company?.sources?.find((s) => s.source_url)?.source_url;
  const sourceUrl = rawSource && /^https:\/\//i.test(rawSource) ? rawSource : null;

  const ask = (value?: string) => {
    if (!analysis) return;
    const q = String(value ?? question).trim().slice(0, 500);
    if (q.length < 3) return;
    setQuestion(q);
    setAnswer(answerIntelligenceQuestion(analysis, q, language));
  };

  const evidenceTone = evidence?.status === 'PASS' ? Brand.positive
    : evidence?.status === 'BLOCK' ? Brand.negative : Brand.warning;

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView contentContainerStyle={styles.content} refreshControl={
        <RefreshControl refreshing={loading} onRefresh={() => { void load(); }} tintColor={Brand.primary} />
      }>
        <View style={styles.max}>
          <View style={styles.header}>
            <Text style={styles.kicker}>BIAP / COMPANY INTELLIGENCE</Text>
            <Text style={[styles.title, { color: colors.text }]}>داشبورد هوشمند شرکت</Text>
            <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
              تحلیل مستند با همان موتور BIAP Global — بدون تغییر در تصمیم‌های سرمایه‌گذاری
            </Text>
          </View>

          <View style={[styles.hero, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
            <View style={styles.heroTop}>
              <Text style={[styles.heroTitle, { color: colors.text }]}>{selected?.name || 'هنوز شرکتی انتخاب نشده'}</Text>
              {selected ? <Text style={styles.ticker}>{selected.ticker}</Text> : null}
            </View>
            <Text style={[styles.muted, { color: colors.textSecondary }]}>
              {selected ? `${selected.country} • ${selected.exchange} • ${selected.currency}` : 'برای شروع، یک سهم از بخش Market انتخاب کنید.'}
            </Text>
            <View style={styles.actions}>
              <Pressable onPress={() => router.push('/market')} style={[styles.button, { backgroundColor: Brand.primary }]}>
                <Text style={styles.buttonText}>{selected ? 'تغییر شرکت' : 'انتخاب شرکت'}</Text>
              </Pressable>
              {selected ? <Pressable onPress={() => { void load(); }} disabled={loading} style={[styles.button, { borderColor: Brand.primary, borderWidth: 1 }]}>
                <Text style={[styles.buttonText, { color: Brand.primary }]}>بروزرسانی تحلیل</Text>
              </Pressable> : null}
            </View>
          </View>

          {loading ? <View style={styles.loading}><ActivityIndicator color={Brand.primary} size="large" />
            <Text style={[styles.muted, { color: colors.textSecondary }]}>در حال بررسی داده‌ها و عوامل تحلیل BIAP…</Text>
          </View> : null}
          {error ? <View style={[styles.notice, { borderColor: Brand.negative }]}><Text style={{ color: Brand.negative, fontFamily: Fonts.sans }}>خطا در دریافت داده واقعی: {error}</Text></View> : null}

          {analysis && !loading ? <>
            <View style={styles.statusRow}>
              <View style={[styles.status, { backgroundColor: colors.backgroundElement, borderColor: evidenceTone }]}>
                <Text style={[styles.tiny, { color: colors.textSecondary }]}>EVIDENCE</Text>
                <Text style={[styles.statusValue, { color: evidenceTone }]}>{evidence?.status || 'UNKNOWN'}</Text>
              </View>
              <View style={[styles.status, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
                <Text style={[styles.tiny, { color: colors.textSecondary }]}>EXISTING KIASHA CALL</Text>
                <Text style={[styles.statusValue, { color: colors.text }]} numberOfLines={2}>{analysis.call || 'NO_RECOMMENDATION'}</Text>
              </View>
            </View>

            <Text style={[styles.heading, { color: colors.text }]}>عملکرد مالی و بازار</Text>
            <View style={styles.grid}>
              {metrics.map((metric) => (
                <View key={metric.key} style={[styles.metric, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
                  <Text style={[styles.metricLabel, { color: colors.textSecondary }]}>{language === 'fa' ? metric.fa : metric.en}</Text>
                  <Text style={[styles.metricValue, { color: metric.value === null ? colors.textSecondary : colors.text }]} adjustsFontSizeToFit numberOfLines={2}>
                    {formatIntelligenceMetric(metric)}
                  </Text>
                  <Text style={[styles.tiny, { color: colors.textSecondary }]}>
                    {metric.category === 'filing' ? 'FILING' : 'MARKET'} • {metric.asOf?.slice(0, 10) || 'date unavailable'}
                  </Text>
                </View>
              ))}
            </View>

            <View style={[styles.notice, { borderColor: Brand.warning }]}>
              <Text style={[styles.noticeTitle, { color: Brand.warning }]}>توجه به کیفیت ارقام</Text>
              <Text style={[styles.noticeText, { color: colors.textSecondary }]}>
                وجود یک گزارش رسمی، صحت مستقل تک‌تک فیلدها را ثابت نمی‌کند. داده‌های نرمال‌شده ممکن است شامل اطلاعات مکمل فروشنده باشند. خط تیره یعنی داده موجود نیست؛ صفر فرض نمی‌شود.
              </Text>
            </View>

            <Text style={[styles.heading, { color: colors.text }]}>اعتبار داده و منابع</Text>
            <View style={[styles.panel, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
              <Info label="وضعیت گزارش" value={filing?.officialStatus || 'UNKNOWN'} colors={colors} />
              <Info label="پایان دوره مالی" value={filing?.reportPeriod || 'نامشخص'} colors={colors} />
              <Info label="زمان ثبت قیمت" value={analysis.company?.price_observed_at || 'نامشخص'} colors={colors} />
              <Info label="تازگی گزارش" value={filing?.freshnessTier || 'نامشخص'} colors={colors} />
              <Info label="منبع" value={filing?.sourceProvider || 'نامشخص'} colors={colors} />
              <Info label="کمبود داده" value={evidence?.missing_critical?.join('، ') || '—'} colors={colors} />
              {sourceUrl ? <Pressable onPress={() => { void Linking.openURL(sourceUrl); }} style={styles.sourceButton}>
                <Text style={[styles.sourceText, { color: Brand.primary }]}>مشاهده سند منبع ↗</Text>
              </Pressable> : null}
              {(filing?.limitations || []).slice(0, 3).map((text, index) =>
                <Text key={index} style={[styles.limitation, { color: colors.textSecondary }]}>• {text}</Text>
              )}
            </View>

            <Text style={[styles.heading, { color: colors.text }]}>Kiasha + Multi-Agent</Text>
            <View style={[styles.panel, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
              {(analysis.signals || []).map((signal, index) => (
                <View key={`${signal.agent}-${index}`} style={[styles.agent, { borderBottomColor: colors.backgroundSelected }]}>
                  <View style={styles.agentLine}>
                    <Text style={[styles.agentLabel, { color: colors.text }]}>{signal.agent}</Text>
                    <Text style={[styles.agentLabel, { color: colors.textSecondary }]}>
                      {Number.isFinite(signal.vote) ? signal.vote.toFixed(3) : '—'} • {Number.isFinite(signal.confidence) ? Math.round(signal.confidence * 100) + '%' : '—'}
                    </Text>
                  </View>
                  <Text style={[styles.muted, { color: colors.textSecondary }]}>{signal.reasoning || 'No verified signal explanation'}</Text>
                </View>
              ))}
              {!(analysis.signals || []).length ? <Text style={{ color: colors.textSecondary }}>سیگنال قابل نمایش موجود نیست.</Text> : null}
            </View>

            <View style={[styles.panel, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected, marginTop: 16 }]}>
              <Text style={styles.kicker}>BIAP ANALYST · GROUNDED PREVIEW</Text>
              <Text style={[styles.heading, { color: colors.text, marginTop: 5 }]}>از اطلاعات همین شرکت بپرسید</Text>
              <Text style={[styles.muted, { color: colors.textSecondary }]}>نسخه اولیه مبتنی بر قواعد است؛ هنوز گفت‌وگوی آزاد LLM نیست.</Text>
              <View style={styles.languageRow}>
                <Pressable onPress={() => { setLanguage('fa'); setAnswer(null); }} style={[styles.langPill, { backgroundColor: language === 'fa' ? Brand.primary : colors.backgroundSelected }]}><Text style={styles.langText}>فارسی</Text></Pressable>
                <Pressable onPress={() => { setLanguage('en'); setAnswer(null); }} style={[styles.langPill, { backgroundColor: language === 'en' ? Brand.primary : colors.backgroundSelected }]}><Text style={styles.langText}>English</Text></Pressable>
              </View>
              <View style={styles.prompts}>
                {PROMPTS.map((p) => <Pressable key={p.en} onPress={() => ask(language === 'en' ? p.en : p.question)} style={[styles.prompt, { borderColor: colors.backgroundSelected }]}>
                  <Text style={[styles.promptText, { color: colors.textSecondary }]}>{language === 'fa' ? p.fa : p.en}</Text>
                </Pressable>)}
              </View>
              <TextInput
                value={question} onChangeText={setQuestion}
                placeholder={language === 'fa' ? 'مثلاً: درآمد شرکت چقدر است؟' : 'e.g. What is the revenue?'}
                placeholderTextColor={colors.textSecondary}
                textAlign={language === 'fa' ? 'right' : 'left'} maxLength={500}
                style={[styles.input, { color: colors.text, borderColor: colors.backgroundSelected, backgroundColor: colors.background }]}
                onSubmitEditing={() => ask()} returnKeyType="send"
              />
              <Pressable onPress={() => ask()} disabled={question.trim().length < 3} style={[styles.button, { backgroundColor: Brand.primary, marginTop: 10, opacity: question.trim().length < 3 ? .5 : 1 }]}>
                <Text style={styles.buttonText}>تحلیل پرسش</Text>
              </Pressable>
              {answer ? <View style={[styles.answer, { backgroundColor: colors.background, borderColor: colors.backgroundSelected }]}>
                <Text style={[styles.answerText, { color: colors.text, textAlign: language === 'fa' ? 'right' : 'left' }]}>{answer.answer}</Text>
              </View> : null}
            </View>
            <Text style={[styles.footer, { color: colors.textSecondary }]}>
              READ-ONLY RESEARCH • no trade execution • no changes to archived decisions or frozen portfolios.
            </Text>
          </> : null}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function Info({ label, value, colors }: { label: string; value: string; colors: typeof Colors.light | typeof Colors.dark }) {
  return <View style={[styles.infoRow, { borderBottomColor: colors.backgroundSelected }]}>
    <Text style={[styles.infoKey, { color: colors.textSecondary }]}>{label}</Text>
    <Text style={[styles.infoValue, { color: colors.text }]} selectable>{value}</Text>
  </View>;
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { paddingHorizontal: Spacing.three, paddingBottom: BottomTabInset + Spacing.four },
  max: { maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' },
  header: { paddingTop: Spacing.four, paddingBottom: Spacing.three },
  kicker: { fontFamily: Fonts.mono, fontSize: 10, color: Brand.primary, fontWeight: '900', letterSpacing: 1 },
  title: { fontFamily: Fonts.sans, fontSize: 24, fontWeight: '900', marginTop: 8 },
  subtitle: { fontFamily: Fonts.sans, fontSize: 12, marginTop: 6, lineHeight: 22 },
  hero: { padding: 18, borderWidth: 1, borderRadius: Radius.lg },
  heroTop: { flexDirection: 'row', justifyContent: 'space-between', gap: 12, alignItems: 'center' },
  heroTitle: { fontFamily: Fonts.sans, fontSize: 18, fontWeight: '800', flex: 1 },
  ticker: { color: Brand.primary, fontFamily: Fonts.mono, fontSize: 16, fontWeight: '900' },
  muted: { fontFamily: Fonts.sans, fontSize: 11, marginTop: 5, lineHeight: 18 },
  actions: { flexDirection: 'row', gap: 10, marginTop: 15 },
  button: { paddingHorizontal: 18, minHeight: 45, borderRadius: Radius.md, alignItems: 'center', justifyContent: 'center', flex: 1 },
  buttonText: { color: '#fff', fontFamily: Fonts.sans, fontSize: 12, fontWeight: '900' },
  loading: { alignItems: 'center', gap: 15, marginVertical: 30 },
  statusRow: { flexDirection: 'row', gap: 10, marginTop: 16 },
  status: { flex: 1, borderWidth: 1, borderRadius: Radius.md, padding: 13 },
  tiny: { fontFamily: Fonts.mono, fontSize: 9, marginTop: 5 },
  statusValue: { fontFamily: Fonts.mono, fontSize: 12, fontWeight: '900', marginTop: 8 },
  heading: { fontFamily: Fonts.sans, fontSize: 17, fontWeight: '900', marginTop: 24, marginBottom: 12 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  metric: { width: '48.5%', padding: 13, minHeight: 128, borderRadius: Radius.md, borderWidth: 1 },
  metricLabel: { fontFamily: Fonts.sans, fontSize: 12 },
  metricValue: { fontFamily: Fonts.mono, fontSize: 18, fontWeight: '800', marginTop: 10 },
  notice: { padding: 16, borderRadius: Radius.md, borderWidth: 1, marginTop: 15 },
  noticeTitle: { fontFamily: Fonts.sans, fontSize: 13, fontWeight: '900' },
  noticeText: { fontFamily: Fonts.sans, fontSize: 11, lineHeight: 18, marginTop: 5 },
  panel: { borderRadius: Radius.md, padding: 16, borderWidth: 1 },
  infoRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10, paddingVertical: 10, borderBottomWidth: 1 },
  infoKey: { fontFamily: Fonts.sans, fontSize: 11, flex: 1 },
  infoValue: { fontFamily: Fonts.mono, fontSize: 10, maxWidth: '65%', textAlign: 'right' },
  sourceButton: { borderWidth: 1, borderColor: Brand.primary, padding: 11, borderRadius: Radius.sm, marginTop: 13 },
  sourceText: { fontFamily: Fonts.sans, fontSize: 11, fontWeight: '800', textAlign: 'center' },
  limitation: { fontFamily: Fonts.sans, fontSize: 10, lineHeight: 17, marginTop: 10 },
  agent: { borderBottomWidth: 1, paddingVertical: 12 },
  agentLine: { flexDirection: 'row', justifyContent: 'space-between', gap: 10 },
  agentLabel: { fontFamily: Fonts.mono, fontSize: 12, fontWeight: '800' },
  languageRow: { flexDirection: 'row', gap: 8, marginTop: 13 },
  langPill: { borderRadius: 30, paddingVertical: 7, paddingHorizontal: 14 },
  langText: { fontFamily: Fonts.sans, fontSize: 11, fontWeight: '900', color: '#fff' },
  prompts: { flexDirection: 'row', flexWrap: 'wrap', gap: 7, marginTop: 14 },
  prompt: { borderRadius: 30, borderWidth: 1, paddingVertical: 8, paddingHorizontal: 11 },
  promptText: { fontFamily: Fonts.sans, fontSize: 11 },
  input: { borderWidth: 1, borderRadius: Radius.md, padding: 12, fontFamily: Fonts.sans, fontSize: 12, marginTop: 13 },
  answer: { borderRadius: Radius.md, borderWidth: 1, padding: 14, marginTop: 14 },
  answerText: { fontFamily: Fonts.sans, fontSize: 12, lineHeight: 22 },
  footer: { fontFamily: Fonts.mono, fontSize: 9, lineHeight: 16, textAlign: 'center', marginTop: 18 },
});
