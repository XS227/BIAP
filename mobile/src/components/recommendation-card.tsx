import { useEffect, useMemo, useState } from 'react';
import { View, Text, Pressable, StyleSheet, ActivityIndicator, TextInput } from 'react-native';
import { Brand, Fonts, Spacing, ThemeColors } from '@/constants/theme';
import { Recommendation } from '@/lib/api';
import { getDemoMode } from '@/lib/demo-mode';
import { executeDemoTrade, getDemoWallet } from '@/lib/demo-trading';
import { confirmManualBuy, confirmManualSell, findOpenManualInvestment, ManualInvestment } from '@/lib/manual-investments';

const CALL_LABEL: Record<string, string> = { BUY: 'خرید', SELL: 'فروش', HOLD: 'نگهداری' };
const AGENT_LABEL: Record<string, string> = { fundamental: 'بنیادی', risk: 'ریسک', forecast: 'پیش‌بینی', comparison: 'مقایسه' };
function callColor(c: string) { return c === 'BUY' ? Brand.stockGreen : c === 'SELL' ? Brand.negative : Brand.dataViolet; }
type SimState = { status: 'idle' } | { status: 'loading' } | { status: 'filled'; note: string } | { status: 'error'; message: string };

function FundamentalChart({ rec, colors }: { rec: Recommendation; colors: ThemeColors }) {
  const f = rec.codalFundamentals;
  const vals = useMemo(() => {
    if (!f) return [];
    const rows: [string, number][] = [];
    if (typeof f.revenue_yoy_pct === 'number') rows.push(['رشد درآمد', f.revenue_yoy_pct]);
    if (typeof f.net_margin_pct === 'number') rows.push(['حاشیه سود', f.net_margin_pct]);
    if (typeof f.net_margin_prev_pct === 'number') rows.push(['حاشیه قبلی', f.net_margin_prev_pct]);
    return rows;
  }, [f]);
  if (!vals.length) return null;
  const max = Math.max(1, ...vals.map(([, v]) => Math.abs(v)));
  return <View style={[styles.chart, { backgroundColor: colors.backgroundSelected }]}><Text style={[styles.fundTitle, { color: colors.text }]}>نمودار واقعی بنیادی CODAL</Text>{vals.map(([label, v]) => <View key={label} style={styles.chartRow}><Text style={[styles.chartValue, { color: v >= 0 ? Brand.stockGreen : Brand.negative }]}>{v.toFixed(1)}٪</Text><View style={[styles.chartTrack, { backgroundColor: colors.backgroundElement }]}><View style={[styles.chartFill, { width: `${Math.max(6, Math.abs(v) / max * 100)}%`, backgroundColor: v >= 0 ? Brand.stockGreen : Brand.negative }]} /></View><Text style={[styles.chartLabel, { color: colors.textSecondary }]}>{label}</Text></View>)}</View>;
}

export function RecommendationCard({ rec, colors }: { rec: Recommendation; colors: ThemeColors }) {
  const [sim, setSim] = useState<SimState>({ status: 'idle' });
  const [expanded, setExpanded] = useState(false);
  const [demo, setDemo] = useState(false);
  const [demoCash, setDemoCash] = useState<number | null>(null);
  const [quantityText, setQuantityText] = useState('10');
  const [rialText, setRialText] = useState('');
  const [tracked, setTracked] = useState<ManualInvestment | null>(null);
  const accent = callColor(rec.call);
  const top = [...rec.breakdown].sort((a, b) => (b.weight_normalized ?? 0) - (a.weight_normalized ?? 0))[0];
  const sourceLabel = rec.dataSource === 'live' ? 'TSETMC + CODAL' : rec.dataSource === 'codal' ? 'CODAL' : 'نمونه';
  const price = Number(rec.livePrice?.lastPrice ?? rec.livePrice?.closingPrice ?? 0);
  const quantity = Math.max(0, Math.floor(Number(quantityText.replace(/,/g, '')) || 0));
  const notional = price > 0 && quantity > 0 ? price * quantity : 0;

  useEffect(() => {
    getDemoMode().then(async (e) => { setDemo(e); if (e) setDemoCash((await getDemoWallet()).cash); });
    findOpenManualInvestment(rec.code).then(setTracked);
  }, [rec.code]);

  const onQuantityChange = (value: string) => {
    const clean = value.replace(/[^0-9]/g, '');
    setQuantityText(clean);
    const q = Math.floor(Number(clean) || 0);
    if (price > 0 && q > 0) setRialText(String(Math.round(q * price)));
  };

  const onRialChange = (value: string) => {
    const clean = value.replace(/[^0-9]/g, '');
    setRialText(clean);
    const rial = Number(clean) || 0;
    if (price > 0 && rial > 0) setQuantityText(String(Math.floor(rial / price)));
  };

  const runDemoTrade = async (side: 'BUY' | 'SELL') => {
    if (!price) { setSim({ status: 'error', message: 'قیمت معتبر برای معامله دمو در دسترس نیست.' }); return; }
    const q = Math.max(1, quantity || 10);
    setSim({ status: 'loading' });
    const r = await executeDemoTrade({ code: rec.code, side, quantity: q, price });
    if (!r.ok) setSim({ status: 'error', message: r.message });
    else { setDemoCash(r.wallet.cash); setSim({ status: 'filled', note: `${side === 'BUY' ? 'خرید' : 'فروش'} دمو ${q.toLocaleString('fa-IR')} سهم ثبت شد.` }); }
  };

  const markBought = async () => {
    if (!price || quantity < 1) { setSim({ status: 'error', message: 'قیمت معتبر و تعداد سهم را وارد کنید.' }); return; }
    setSim({ status: 'loading' });
    try {
      const item = await confirmManualBuy({ code: rec.code, symbol: rec.name || rec.code, quantity, buyPrice: price });
      setTracked(item);
      const signalNote = rec.call === 'BUY' ? '' : ` سیگنال فعلی کیا‌شا ${CALL_LABEL[rec.call] ?? rec.call} است؛ این فقط ثبت معامله‌ای است که خودتان بیرون BIAP انجام داده‌اید.`;
      setSim({ status: 'filled', note: `ثبت شد: مجموع موقعیت ${item.quantity.toLocaleString('fa-IR')} سهم شد.${signalNote}` });
    } catch (e) { setSim({ status: 'error', message: e instanceof Error ? e.message : 'ثبت خرید دستی انجام نشد.' }); }
  };

  const markSold = async () => {
    if (!tracked || !price) { setSim({ status: 'error', message: 'برای ثبت فروش، قیمت معتبر لازم است.' }); return; }
    setSim({ status: 'loading' });
    try {
      await confirmManualSell(tracked.id, price);
      setTracked(null);
      setSim({ status: 'filled', note: 'فروش کل موقعیت دستی ثبت شد و پیگیری این موقعیت بسته شد.' });
    } catch (e) { setSim({ status: 'error', message: e instanceof Error ? e.message : 'ثبت فروش دستی انجام نشد.' }); }
  };

  return <View style={[styles.wrap, { backgroundColor: colors.backgroundElement }]}>
    <View style={styles.header}><View style={[styles.badge, { backgroundColor: `${accent}22` }]}><Text style={[styles.badgeText, { color: accent }]}>{CALL_LABEL[rec.call] ?? rec.call}</Text></View><View style={styles.titleWrap}><Text style={[styles.title, { color: colors.text }]}>تحلیل کیا‌شا</Text><Text style={[styles.source, { color: colors.textSecondary }]}>منبع: {sourceLabel}</Text></View></View>
    <Text style={[styles.score, { color: colors.textSecondary }]}>امتیاز نهایی: {rec.score >= 0 ? '+' : ''}{rec.score.toFixed(3)}</Text>
    {rec.breakdown.length ? <View style={styles.weights}><Text style={[styles.weightTitle, { color: colors.text }]}>وزن‌دهی فعال کیا‌شا</Text><View style={styles.weightGrid}>{rec.breakdown.map(b => <View key={b.agent} style={[styles.weightPill, { backgroundColor: colors.backgroundSelected }]}><Text style={[styles.weightName, { color: colors.textSecondary }]}>{AGENT_LABEL[b.agent] ?? b.agent}</Text><Text style={[styles.weightPct, { color: Brand.primary }]}>{Math.round((b.weight_normalized ?? 0) * 100)}٪</Text></View>)}</View></View> : null}
    {top ? <Text style={[styles.reasoning, { color: colors.textSecondary }]} numberOfLines={expanded ? undefined : 2}>{top.reasoning}</Text> : null}
    {rec.breakdown.length ? <Pressable onPress={() => setExpanded(e => !e)}><Text style={[styles.toggle, { color: accent }]}>{expanded ? 'بستن جزئیات' : 'جزئیات رأی عامل‌ها'}</Text></Pressable> : null}
    {expanded ? <View style={styles.breakdown}>{rec.breakdown.map(b => <View key={b.agent} style={styles.breakdownRow}><Text style={[styles.breakdownAgent, { color: colors.text }]}>{AGENT_LABEL[b.agent] ?? b.agent}</Text><Text style={[styles.breakdownDetail, { color: colors.textSecondary }]}>رأی {b.vote >= 0 ? '+' : ''}{b.vote.toFixed(2)} · اطمینان {(b.confidence * 100).toFixed(0)}٪ · وزن {((b.weight_normalized ?? 0) * 100).toFixed(0)}٪</Text><Text style={[styles.breakdownDetail, { color: colors.textSecondary }]}>{b.reasoning}</Text></View>)}</View> : null}
    <FundamentalChart rec={rec} colors={colors} />

    <View style={styles.manualSection}>
      <Text style={[styles.manualTitle, { color: colors.text }]}>اجرای دستی از طریق کارگزاری دلخواه</Text>
      <Text style={[styles.manualNote, { color: colors.textSecondary }]}>خرید و فروش واقعی خارج از BIAP انجام می‌شود. اینجا می‌توانید هر بار خرید جدید را به موقعیت اضافه کنید یا فروش کل موقعیت را ثبت کنید؛ سیگنال کیا‌شا جداگانه نمایش داده می‌شود.</Text>
      {tracked ? <View style={[styles.trackedBox, { backgroundColor: colors.backgroundSelected }]}><Text style={[styles.trackedTitle, { color: Brand.positive }]}>✓ در حال پیگیری توسط کیا‌شا</Text><Text style={[styles.trackedMeta, { color: colors.textSecondary }]}>{tracked.quantity.toLocaleString('fa-IR')} سهم • میانگین ثبت خرید {Math.round(tracked.buyPrice).toLocaleString('fa-IR')} ریال</Text><Text style={[styles.trackedSignal, { color: rec.call === 'SELL' ? Brand.negative : colors.text }]}>{`سیگنال فعلی: ${CALL_LABEL[rec.call] ?? rec.call}`}</Text></View> : null}
      <View style={styles.inputRow}><View style={styles.inputBox}><Text style={[styles.inputLabel, { color: colors.textSecondary }]}>مبلغ تقریبی (ریال)</Text><TextInput value={rialText} onChangeText={onRialChange} keyboardType="number-pad" placeholder="مثلاً 5000000" placeholderTextColor={colors.textSecondary} style={[styles.input, { color: colors.text, borderColor: colors.backgroundSelected }]} /></View><View style={styles.inputBox}><Text style={[styles.inputLabel, { color: colors.textSecondary }]}>تعداد سهم</Text><TextInput value={quantityText} onChangeText={onQuantityChange} keyboardType="number-pad" placeholder="10" placeholderTextColor={colors.textSecondary} style={[styles.input, { color: colors.text, borderColor: colors.backgroundSelected }]} /></View></View>
      <Text style={[styles.calc, { color: colors.textSecondary }]}>{price > 0 ? `قیمت مبنا ${Math.round(price).toLocaleString('fa-IR')} ریال • ارزش تقریبی ${Math.round(notional).toLocaleString('fa-IR')} ریال` : 'قیمت معتبر فعلاً دریافت نشده است.'}</Text>
      {demo ? <View style={styles.demoButtons}><Pressable disabled={sim.status === 'loading'} onPress={() => runDemoTrade('BUY')} style={[styles.demoBtn, { backgroundColor: Brand.stockGreen }]}><Text style={styles.simBtnText}>خرید دمو</Text></Pressable><Pressable disabled={sim.status === 'loading'} onPress={() => runDemoTrade('SELL')} style={[styles.demoBtn, { backgroundColor: Brand.negative }]}><Text style={styles.simBtnText}>فروش دمو</Text></Pressable></View> : <View style={styles.demoButtons}><Pressable disabled={sim.status === 'loading'} onPress={markBought} style={[styles.demoBtn, { backgroundColor: Brand.stockGreen }]}>{sim.status === 'loading' ? <ActivityIndicator color="#fff" /> : <Text style={styles.simBtnText}>{tracked ? 'خریدم بیشتر — ثبت' : 'خریدم — شروع پیگیری'}</Text>}</Pressable><Pressable disabled={sim.status === 'loading' || !tracked} onPress={markSold} style={[styles.demoBtn, { backgroundColor: tracked ? Brand.negative : colors.backgroundSelected, opacity: tracked ? 1 : .6 }]}><Text style={[styles.simBtnText, { color: tracked ? '#fff' : colors.textSecondary }]}>فروختم همه</Text></Pressable></View>}
      {demo ? <Text style={[styles.demoCash, { color: colors.textSecondary }]}>موجودی Demo: {demoCash === null ? '—' : Math.round(demoCash).toLocaleString('fa-IR')} ریال</Text> : null}
      {sim.status === 'filled' ? <Text style={[styles.simResult, { color: Brand.stockGreen }]}>✓ {sim.note}</Text> : null}
      {sim.status === 'error' ? <Text style={[styles.simResult, { color: Brand.negative }]}>{sim.message}</Text> : null}
    </View>
  </View>;
}

const styles = StyleSheet.create({
  wrap: { borderRadius: Spacing.three, padding: Spacing.four, marginTop: Spacing.three, gap: Spacing.two, alignItems: 'flex-end' }, header: { flexDirection: 'row-reverse', alignItems: 'center', gap: Spacing.two, width: '100%', justifyContent: 'space-between' }, titleWrap: { alignItems: 'flex-end', flex: 1 }, badge: { paddingHorizontal: Spacing.three, paddingVertical: Spacing.one, borderRadius: Spacing.five }, badgeText: { fontFamily: Fonts.sans, fontSize: 13, fontWeight: '700' }, title: { fontFamily: Fonts.sans, fontSize: 15, fontWeight: '800' }, source: { fontFamily: Fonts.sans, fontSize: 10, marginTop: 2 }, score: { fontFamily: Fonts.mono, fontSize: 13 }, weights: { width: '100%', marginTop: 4 }, weightTitle: { fontFamily: Fonts.sans, fontSize: 12, fontWeight: '800', textAlign: 'right', marginBottom: 6 }, weightGrid: { flexDirection: 'row-reverse', gap: 6 }, weightPill: { flex: 1, borderRadius: 10, paddingVertical: 7, alignItems: 'center' }, weightName: { fontFamily: Fonts.sans, fontSize: 9 }, weightPct: { fontFamily: Fonts.mono, fontSize: 12, fontWeight: '900', marginTop: 2 }, reasoning: { fontFamily: Fonts.sans, fontSize: 13, textAlign: 'right', lineHeight: 20 }, toggle: { fontFamily: Fonts.sans, fontSize: 12, fontWeight: '700' }, breakdown: { width: '100%', gap: Spacing.two }, breakdownRow: { alignItems: 'flex-end' }, breakdownAgent: { fontFamily: Fonts.sans, fontSize: 12, fontWeight: '700' }, breakdownDetail: { fontFamily: Fonts.sans, fontSize: 11, textAlign: 'right', lineHeight: 17 }, chart: { width: '100%', borderRadius: 12, padding: 10, marginTop: 4 }, fundTitle: { fontFamily: Fonts.sans, fontSize: 12, fontWeight: '800', textAlign: 'right', marginBottom: 7 }, chartRow: { flexDirection: 'row', alignItems: 'center', gap: 7, marginVertical: 4 }, chartValue: { width: 48, fontFamily: Fonts.mono, fontSize: 10 }, chartTrack: { flex: 1, height: 7, borderRadius: 7, overflow: 'hidden' }, chartFill: { height: 7, borderRadius: 7 }, chartLabel: { width: 70, fontFamily: Fonts.sans, fontSize: 9, textAlign: 'right' },
  manualSection: { width: '100%', marginTop: Spacing.two, gap: Spacing.two, alignItems: 'flex-end' }, manualTitle: { fontFamily: Fonts.sans, fontSize: 13, fontWeight: '900' }, manualNote: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 18, textAlign: 'right' }, inputRow: { width: '100%', flexDirection: 'row-reverse', gap: Spacing.two }, inputBox: { flex: 1 }, inputLabel: { fontFamily: Fonts.sans, fontSize: 9.5, textAlign: 'right', marginBottom: 5 }, input: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 9, textAlign: 'right', fontFamily: Fonts.mono, fontSize: 12 }, calc: { fontFamily: Fonts.sans, fontSize: 10, textAlign: 'right' }, manualBtn: { width: '100%', paddingVertical: Spacing.three, borderRadius: Spacing.two, alignItems: 'center' }, trackedBox: { width: '100%', borderRadius: 12, padding: Spacing.three, gap: 7, alignItems: 'flex-end' }, trackedTitle: { fontFamily: Fonts.sans, fontSize: 12, fontWeight: '900' }, trackedMeta: { fontFamily: Fonts.mono, fontSize: 10.5 }, trackedSignal: { fontFamily: Fonts.sans, fontSize: 10.5, textAlign: 'right', lineHeight: 18 }, demoButtons: { width: '100%', flexDirection: 'row-reverse', gap: Spacing.two }, demoBtn: { flex: 1, paddingVertical: Spacing.three, borderRadius: Spacing.two, alignItems: 'center' }, simBtnText: { fontFamily: Fonts.sans, fontSize: 13, fontWeight: '700', color: '#fff' }, simResult: { fontFamily: Fonts.sans, fontSize: 12, textAlign: 'right', lineHeight: 18 }, demoCash: { fontFamily: Fonts.sans, fontSize: 10 },
});