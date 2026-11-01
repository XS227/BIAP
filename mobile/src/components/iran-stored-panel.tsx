import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { Brand, Fonts, Radius, Spacing, ThemeColors } from '@/constants/theme';
import { describeIranError, fetchIranCompany, type IranCompanyView } from '@/lib/iran-company';
import { agentStatusFa, assessIranStoredDecisionReadiness, DATA_STATUS_FA, faDate, faNumber, priceStatus } from '@/lib/data-status';

const AGENT_FA: Record<string, string> = {
  fundamental: 'بنیادی', risk: 'ریسک', forecast: 'پیش‌بینی', technical: 'تکنیکال', comparison: 'مقایسه‌ای', flow: 'جریان معاملات', scenario: 'سناریو',
};
const KEY_RATIOS = ['net_margin', 'gross_margin', 'roa', 'roe', 'liabilities_to_equity', 'liabilities_to_assets', 'current_ratio', 'revenue_growth'];

/** نتیجه‌ی ذخیره‌شده: هفت عامل، آخرین اجرای کیاشا (با زمان)، قیمت با منشأ، صورت‌های مالی و نسبت‌ها. */
export function IranStoredPanel({ symbol, colors }: { symbol: string; colors: ThemeColors }) {
  const [response, setResponse] = useState<{ symbol: string; view: IranCompanyView | null; error: string }>({
    symbol: '', view: null, error: '',
  });
  useEffect(() => {
    let cancelled = false;
    fetchIranCompany(symbol)
      .then((view) => { if (!cancelled) setResponse({ symbol, view, error: '' }); })
      .catch((e) => { if (!cancelled) setResponse({ symbol, view: null, error: describeIranError(e) }); });
    return () => { cancelled = true; };
  }, [symbol]);
  const loading = response.symbol !== symbol;
  const view = loading ? null : response.view;
  const error = loading ? '' : response.error;

  const card = [styles.card, { backgroundColor: colors.backgroundElement }];
  if (loading) return <View style={card}><ActivityIndicator color={Brand.primary} /><Text style={[styles.meta, { color: colors.textSecondary }]}>در حال خواندن نتیجه‌ی ذخیره‌شده…</Text></View>;
  if (error || !view) return <View style={[styles.card, { backgroundColor: colors.backgroundElement, borderColor: Brand.warning, borderWidth: 1 }]}>
    <Text style={[styles.title, { color: colors.text }]}>نتیجه‌ی ذخیره‌شده و صورت‌های مالی</Text><Text style={[styles.body, { color: Brand.warning }]}>در دسترس نیست: {error || 'داده‌ای برگردانده نشد'}</Text></View>;

  const p = view.price; const fin = view.financials; const k = view.kiasha;
  const ps = priceStatus(p.status);
  const readiness = assessIranStoredDecisionReadiness(view);
  const warnColor = ps === 'verified' ? Brand.positive : Brand.warning;
  const lines = fin.statements.filter((s) => s.value != null);
  return <View>
    {view.dataQualityWarnings.length ? <View style={[styles.card, { backgroundColor: colors.backgroundElement, borderColor: Brand.warning, borderWidth: 1 }]}>
      <Text style={[styles.title, { color: Brand.warning }]}>هشدار کیفیت داده</Text>
      {view.dataQualityWarnings.map((w) => <Text key={w} style={[styles.body, { color: colors.textSecondary }]}>• {w}</Text>)}
    </View> : null}
    <View style={card}>
      <Text style={[styles.title, { color: colors.text }]}>قیمت ذخیره‌شده در رکورد شرکت</Text>
      <Text style={[styles.body, { color: warnColor }]}>{p.price == null ? 'ناموجود' : `${faNumber(p.price, 0)} ریال`} · {DATA_STATUS_FA[ps]}</Text>
      <Text style={[styles.meta, { color: colors.textSecondary }]}>زمان مشاهده: {faDate(p.observedAt)}{p.ageDays != null ? ` (${faNumber(p.ageDays, 1)} روز پیش)` : ''} · منبع: {p.source || 'نامشخص'}</Text>
      {p.kiashaReferencePrice != null ? <Text style={[styles.meta, { color: colors.textSecondary }]}>قیمت مرجع آخرین تحلیل کیاشا: {faNumber(p.kiashaReferencePrice, 0)} ریال ({faDate(p.kiashaReferenceAt)})</Text> : null}
    </View>
    <View style={card}>
      <Text style={[styles.title, { color: colors.text }]}>نتیجه‌ی کیاشا</Text>
      {k ? <>
        <Text style={[styles.body, { color: colors.text }]}>{k.call} · امتیاز {faNumber(k.score, 3)}</Text>
        <Text style={[styles.meta, { color: colors.textSecondary }]}>زمان تحلیل: {faDate(k.generatedAt)}</Text>
        {!readiness.evidenceComplete ? <Text style={[styles.body, { color: Brand.warning }]}>نتیجه ذخیره‌شده کیاشا صرفاً برای بررسی است؛ با داده فعلی توصیه قابل اجرا نیست.</Text> : null}

      </> : <Text style={[styles.body, { color: Brand.warning }]}>نتیجه‌ی ذخیره‌شده‌ای وجود ندارد.</Text>}
    </View>
    {!readiness.evidenceComplete ? <View style={[styles.card, { backgroundColor: colors.backgroundElement, borderColor: Brand.warning, borderWidth: 1 }]}>
      <Text style={[styles.title, { color: Brand.warning }]}>عدم تأیید برای تصمیم معاملاتی</Text>
      {readiness.reasons.map(reason => <Text key={reason} style={[styles.body, { color: colors.textSecondary }]}>• {reason}</Text>)}
    </View> : null}
    <View style={card}>
      <Text style={[styles.title, { color: colors.text }]}>هفت عامل تحلیل (نتیجه‌ی ذخیره‌شده)</Text>
      {view.agents.map((a) => <View key={a.agent} style={styles.agent}>
        <View style={styles.rowBetween}>
          <Text style={[styles.name, { color: a.vote == null || a.dataStatus === 'NO_DATA' ? Brand.warning : colors.text }]}>{a.vote == null ? 'بدون رأی' : `${a.vote > 0 ? '+' : ''}${faNumber(a.vote, 2)}`}</Text>
          <Text style={[styles.name, { color: colors.text }]}>{AGENT_FA[a.agent] || a.agent}</Text>
        </View>
        <Text style={[styles.meta, { color: a.dataStatus === 'OK' ? colors.textSecondary : Brand.warning }]}>اطمینان {a.confidence == null ? '—' : `${faNumber(Math.round(a.confidence * 100), 0)}٪`} · {agentStatusFa(a.dataStatus)}</Text>
        {a.reasoning ? <Text style={[styles.meta, { color: colors.textSecondary }]}>{a.reasoning}</Text> : null}
      </View>)}
    </View>
    <View style={card}>
      <Text style={[styles.title, { color: colors.text }]}>صورت‌های مالی (کدال، ذخیره‌شده)</Text>
      {!fin.available ? <Text style={[styles.body, { color: Brand.warning }]}>داده کافی نیست؛ صورت مالی برای این شرکت ذخیره نشده است. {fin.missingReason ? `(${fin.missingReason})` : ''}</Text> : <>
        <Text style={[styles.meta, { color: colors.textSecondary }]}>دوره: {fin.reportPeriod || 'ثبت نشده'} · منبع: {fin.source || 'کدال'} · آخرین به‌روزرسانی: {faDate(fin.lastUpdate)}</Text>
        {lines.map((s) => <View key={s.key} style={styles.rowBetween}><Text style={[styles.body, { color: colors.text }]}>{faNumber(s.value, 0)}</Text><Text style={[styles.body, { color: colors.textSecondary }]}>{s.label}</Text></View>)}
        {KEY_RATIOS.map((id) => fin.ratios[id]).filter(Boolean).map((r) => <View key={r.label} style={styles.rowBetween}>
          <Text style={[styles.body, { color: r.value == null ? Brand.warning : colors.text }]}>{r.value == null ? 'داده کافی نیست' : `${faNumber(r.value)}${r.unit === '%' ? '٪' : ''}`}</Text>
          <Text style={[styles.body, { color: colors.textSecondary }]}>{r.label}</Text></View>)}
      </>}
    </View>
  </View>;
}

const styles = StyleSheet.create({
  card: { borderRadius: Radius.lg, padding: Spacing.three, marginTop: Spacing.three, alignItems: 'flex-end' },
  title: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '900', textAlign: 'right' },
  name: { fontFamily: Fonts.sans, fontSize: 12, fontWeight: '800' },
  agent: { alignSelf: 'stretch', marginTop: 8 },
  rowBetween: { alignSelf: 'stretch', flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginTop: 3 },
  meta: { fontFamily: Fonts.sans, fontSize: 11, lineHeight: 16, marginTop: 3, textAlign: 'right' },
  body: { fontFamily: Fonts.sans, fontSize: 12, lineHeight: 18, marginTop: 3, textAlign: 'right' },
});
