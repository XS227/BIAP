import { useState } from 'react';
import { View, Text, Pressable, StyleSheet, ActivityIndicator } from 'react-native';
import { Brand, Fonts, Spacing, ThemeColors } from '@/constants/theme';
import { Recommendation, previewPaperOrder, submitPaperOrder } from '@/lib/api';
import { recordLocalOrder } from '@/lib/order-history';

const CALL_LABEL: Record<string, string> = { BUY: 'خرید', SELL: 'فروش', HOLD: 'نگهداری' };

function callColor(call: string) {
  if (call === 'BUY') return Brand.stockGreen;
  if (call === 'SELL') return Brand.negative;
  return Brand.dataViolet;
}

type SimState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'filled'; note: string }
  | { status: 'pending'; note: string }
  | { status: 'rejected'; reasons: string[] }
  | { status: 'error'; message: string };

export function RecommendationCard({ rec, colors }: { rec: Recommendation; colors: ThemeColors }) {
  const [sim, setSim] = useState<SimState>({ status: 'idle' });
  const [expanded, setExpanded] = useState(false);
  const accent = callColor(rec.call);
  const directional = rec.call === 'BUY' || rec.call === 'SELL';
  const top = [...rec.breakdown].sort((a, b) => b.weight_normalized - a.weight_normalized)[0];
  const isLimited = !rec.dataAvailability.codal || !rec.dataAvailability.market_extended;

  const runPaperSim = async () => {
    if (!directional) return;
    setSim({ status: 'loading' });
    const preview = await previewPaperOrder({ code: rec.code, side: rec.call as 'BUY' | 'SELL', quantity: 10 });
    if (!preview.ok) {
      if (preview.riskRejected) {
        setSim({ status: 'rejected', reasons: preview.risk.reasons });
      } else {
        setSim({ status: 'error', message: preview.message });
      }
      return;
    }
    const submitted = await submitPaperOrder(preview.intent.id);
    if (!submitted.ok) {
      setSim({ status: 'error', message: submitted.message });
      return;
    }
    recordLocalOrder(submitted.receipt);
    if (submitted.receipt.status === 'PAPER_FILLED') {
      setSim({ status: 'filled', note: submitted.receipt.note ?? 'شبیه‌سازی انجام شد' });
    } else {
      setSim({ status: 'pending', note: submitted.receipt.note ?? 'در انتظار تأیید' });
    }
  };

  return (
    <View style={[styles.wrap, { backgroundColor: colors.backgroundElement }]}>
      <View style={styles.header}>
        <View style={[styles.badge, { backgroundColor: `${accent}22` }]}>
          <Text style={[styles.badgeText, { color: accent }]}>{CALL_LABEL[rec.call] ?? rec.call}</Text>
        </View>
        <Text style={[styles.title, { color: colors.text }]}>توصیه هوش مصنوعی</Text>
      </View>

      <Text style={[styles.score, { color: colors.textSecondary }]}>
        امتیاز: {rec.score >= 0 ? '+' : ''}
        {rec.score.toFixed(2)}
      </Text>

      {top ? (
        <Text
          style={[styles.reasoning, { color: colors.textSecondary }]}
          numberOfLines={expanded ? undefined : 2}
        >
          {top.reasoning}
        </Text>
      ) : null}

      {rec.breakdown.length > 0 ? (
        <Pressable onPress={() => setExpanded((e) => !e)}>
          <Text style={[styles.toggle, { color: accent }]}>
            {expanded ? 'بستن جزئیات تیم' : 'مشاهده جزئیات تیم'}
          </Text>
        </Pressable>
      ) : null}

      {expanded ? (
        <View style={styles.breakdown}>
          {rec.breakdown.map((b) => (
            <View key={b.agent} style={styles.breakdownRow}>
              <Text style={[styles.breakdownAgent, { color: colors.text }]}>{b.agent}</Text>
              <Text style={[styles.breakdownDetail, { color: colors.textSecondary }]}>
                {(b.weight_normalized * 100).toFixed(0)}٪ · {b.reasoning}
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      {isLimited ? (
        <Text style={[styles.disclaimer, { color: colors.textSecondary }]}>
          فقط بر اساس قیمت لحظه‌ای — داده‌های بنیادی CODAL هنوز متصل نشده‌اند
        </Text>
      ) : null}

      <View style={styles.simSection}>
        <Text style={[styles.simLabel, { color: colors.textSecondary }]}>
          Paper — فقط شبیه‌سازی، بدون معامله واقعی
        </Text>
        <Pressable
          disabled={!directional || sim.status === 'loading'}
          onPress={runPaperSim}
          style={({ pressed }) => [
            styles.simBtn,
            {
              backgroundColor: directional ? accent : colors.backgroundSelected,
              opacity: pressed ? 0.8 : directional ? 1 : 0.7,
            },
          ]}
        >
          {sim.status === 'loading' ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={[styles.simBtnText, { color: directional ? '#fff' : colors.textSecondary }]}>
              {directional ? `شبیه‌سازی ${CALL_LABEL[rec.call]} (۱۰ سهم)` : 'بدون سیگنال جهت‌دار'}
            </Text>
          )}
        </Pressable>

        {sim.status === 'filled' ? (
          <Text style={[styles.simResult, { color: Brand.stockGreen }]}>✓ {sim.note}</Text>
        ) : null}
        {sim.status === 'pending' ? (
          <Text style={[styles.simResult, { color: colors.textSecondary }]}>{sim.note}</Text>
        ) : null}
        {sim.status === 'rejected' ? (
          <Text style={[styles.simResult, { color: Brand.negative }]}>
            رد شد توسط ریسک: {sim.reasons.join('؛ ')}
          </Text>
        ) : null}
        {sim.status === 'error' ? (
          <Text style={[styles.simResult, { color: Brand.negative }]}>{sim.message}</Text>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    borderRadius: Spacing.three,
    padding: Spacing.four,
    marginTop: Spacing.three,
    gap: Spacing.two,
    alignItems: 'flex-end',
  },
  header: { flexDirection: 'row-reverse', alignItems: 'center', gap: Spacing.two },
  badge: { paddingHorizontal: Spacing.three, paddingVertical: Spacing.one, borderRadius: Spacing.five },
  badgeText: { fontFamily: Fonts.sans, fontSize: 13, fontWeight: '700' },
  title: { fontFamily: Fonts.sans, fontSize: 13 },
  score: { fontFamily: Fonts.mono, fontSize: 13, alignSelf: 'flex-end' },
  reasoning: { fontFamily: Fonts.sans, fontSize: 13, textAlign: 'right', lineHeight: 20, alignSelf: 'flex-end' },
  toggle: { fontFamily: Fonts.sans, fontSize: 12, fontWeight: '600' },
  breakdown: { width: '100%', gap: Spacing.one, marginTop: Spacing.one },
  breakdownRow: { alignItems: 'flex-end' },
  breakdownAgent: { fontFamily: Fonts.sans, fontSize: 12, fontWeight: '700' },
  breakdownDetail: { fontFamily: Fonts.sans, fontSize: 11, textAlign: 'right' },
  disclaimer: { fontFamily: Fonts.sans, fontSize: 11, textAlign: 'right', lineHeight: 17, alignSelf: 'flex-end' },
  simSection: { width: '100%', marginTop: Spacing.two, gap: Spacing.two, alignItems: 'flex-end' },
  simLabel: { fontFamily: Fonts.sans, fontSize: 11 },
  simBtn: {
    width: '100%',
    paddingVertical: Spacing.three,
    borderRadius: Spacing.two,
    alignItems: 'center',
    justifyContent: 'center',
  },
  simBtnText: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '700' },
  simResult: { fontFamily: Fonts.sans, fontSize: 12, textAlign: 'right', lineHeight: 18, alignSelf: 'flex-end' },
});
