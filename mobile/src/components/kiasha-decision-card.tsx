import { useEffect, useMemo, useState } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Brand, Fonts, Spacing, ThemeColors } from '@/constants/theme';
import { Recommendation } from '@/lib/api';
import { getDemoWallet } from '@/lib/demo-trading';
import { fetchServerPaperAccount } from '@/lib/paper-account';

function clamp(value: number, low: number, high: number) {
  return Math.max(low, Math.min(high, value));
}

export function KiashaDecisionCard({ rec, colors, demo }: { rec: Recommendation; colors: ThemeColors; demo: boolean }) {
  const [cash, setCash] = useState<number | null>(null);
  const [sizingCapital, setSizingCapital] = useState<number | null>(null);
  const [balanceSource, setBalanceSource] = useState<'demo' | 'paper' | 'none'>('none');

  useEffect(() => {
    let active = true;
    (async () => {
      if (demo) {
        const wallet = await getDemoWallet();
        if (!active) return;
        setCash(wallet.cash);
        setSizingCapital(wallet.cash);
        setBalanceSource('demo');
        return;
      }
      const paper = await fetchServerPaperAccount();
      if (!active) return;
      if (paper?.account) {
        setCash(Number(paper.account.cashBalance));
        setSizingCapital(Number(paper.sizingCapital || paper.account.initialCash));
        setBalanceSource('paper');
      } else {
        setCash(null);
        setSizingCapital(null);
        setBalanceSource('none');
      }
    })();
    return () => { active = false; };
  }, [demo, rec.code]);

  const decision = rec.call === 'BUY'
    ? { title: 'کیاشا: خرید قابل بررسی است', action: 'GO', color: Brand.stockGreen, detail: 'سیگنال فعلی BUY است؛ اندازه موقعیت باید با موجودی و کنترل ریسک محدود شود.' }
    : rec.call === 'SELL'
      ? { title: 'کیاشا: فعلاً نخر', action: 'NO-GO', color: Brand.negative, detail: 'سیگنال فعلی SELL است. برای موقعیت جدید خرید پیشنهاد نمی‌شود؛ اگر سهم را دارید، تحلیل فروش را بررسی کنید.' }
      : { title: 'کیاشا: فعلاً صبر کن', action: 'WAIT', color: Brand.dataViolet, detail: 'سیگنال فعلی HOLD است و ورود جدید پیشنهاد نمی‌شود.' };

  const sizing = useMemo(() => {
    if (rec.call !== 'BUY' || cash === null || sizingCapital === null || cash <= 0 || sizingCapital <= 0) return null;
    // Keep the UI aligned with BIAP's conservative Paper controls: max 5% per
    // symbol and preserve at least a 30% cash reserve. Stronger BUY scores can
    // use more of that ceiling, but the deterministic server risk gate remains authoritative.
    const strength = clamp((rec.score - 0.25) / 0.75, 0, 1);
    const targetFraction = 0.02 + 0.03 * strength;
    const symbolCap = sizingCapital * 0.05;
    const reserveCap = Math.max(0, cash - sizingCapital * 0.30);
    const suggested = Math.floor(Math.min(sizingCapital * targetFraction, symbolCap, reserveCap, cash));
    return suggested > 0 ? suggested : null;
  }, [rec.call, rec.score, cash, sizingCapital]);

  return <View style={[styles.card, { backgroundColor: colors.backgroundElement, borderColor: `${decision.color}55` }]}>
    <View style={styles.head}>
      <View style={[styles.badge, { backgroundColor: `${decision.color}22` }]}><Text style={[styles.badgeText, { color: decision.color }]}>{decision.action}</Text></View>
      <Text style={[styles.title, { color: decision.color }]}>{decision.title}</Text>
    </View>
    <Text style={[styles.score, { color: colors.textSecondary }]}>امتیاز کیا‌شا: {rec.score >= 0 ? '+' : ''}{rec.score.toFixed(3)}</Text>
    <Text style={[styles.detail, { color: colors.text }]}>{decision.detail}</Text>
    {rec.call === 'BUY' ? <View style={[styles.sizingBox, { backgroundColor: colors.backgroundSelected }]}>
      {sizing ? <>
        <Text style={[styles.sizingTitle, { color: colors.text }]}>حد پیشنهادی کیا‌شا برای این موقعیت</Text>
        <Text style={[styles.amount, { color: Brand.stockGreen }]}>{sizing.toLocaleString('fa-IR')} ریال</Text>
        <Text style={[styles.meta, { color: colors.textSecondary }]}>مبنای محاسبه: {balanceSource === 'demo' ? 'موجودی Demo' : 'حساب Paper سرور'} • سقف هر نماد ۵٪ سرمایه • حداقل ۳۰٪ ذخیره نقد</Text>
      </> : <Text style={[styles.meta, { color: colors.textSecondary }]}>برای پیشنهاد مبلغ، موجودی معتبر Paper/Demo لازم است. موجودی کارگزاری واقعی از داخل BIAP حدس زده نمی‌شود.</Text>}
    </View> : null}
    <Text style={[styles.note, { color: colors.textSecondary }]}>این «GO / WAIT / NO-GO» نتیجه تحلیل فعلی است، نه اجرای سفارش. کنترل ریسک سرور می‌تواند مبلغ را کمتر یا معامله را رد کند.</Text>
  </View>;
}

const styles = StyleSheet.create({
  card: { borderRadius: Spacing.three, borderWidth: 1, padding: Spacing.four, marginTop: Spacing.three, gap: Spacing.two, alignItems: 'flex-end' },
  head: { width: '100%', flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'center', gap: Spacing.two },
  title: { fontFamily: Fonts.sans, fontSize: 18, fontWeight: '900', flex: 1, textAlign: 'right' },
  badge: { borderRadius: 14, paddingHorizontal: 10, paddingVertical: 5 },
  badgeText: { fontFamily: Fonts.mono, fontSize: 11, fontWeight: '900' },
  score: { fontFamily: Fonts.mono, fontSize: 12 },
  detail: { fontFamily: Fonts.sans, fontSize: 13, lineHeight: 22, textAlign: 'right' },
  sizingBox: { width: '100%', borderRadius: Spacing.two, padding: Spacing.three, alignItems: 'flex-end', gap: 5 },
  sizingTitle: { fontFamily: Fonts.sans, fontSize: 12, fontWeight: '800' },
  amount: { fontFamily: Fonts.mono, fontSize: 21, fontWeight: '900' },
  meta: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 18, textAlign: 'right' },
  note: { fontFamily: Fonts.sans, fontSize: 10, lineHeight: 17, textAlign: 'right' },
});
