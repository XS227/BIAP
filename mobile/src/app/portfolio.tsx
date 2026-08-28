import { useCallback, useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, useColorScheme, SafeAreaView, Pressable, RefreshControl } from 'react-native';
import { router } from 'expo-router';
import { Colors, Brand, Fonts, Spacing, Radius, BottomTabInset, MaxContentWidth, ThemeColors } from '@/constants/theme';
import { fetchPaperPortfolio, PaperPortfolio, PaperPosition } from '@/lib/paper-portfolio';

function money(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—';
  return Math.round(value).toLocaleString('fa-IR');
}

function pct(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—';
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}٪`;
}

function PositionCard({ position, colors }: { position: PaperPosition; colors: ThemeColors }) {
  const positive = (position.unrealizedPnL ?? 0) >= 0;
  return (
    <Pressable
      onPress={() => router.push(`/stock/${position.code}`)}
      style={({ pressed }) => [styles.positionCard, { backgroundColor: colors.backgroundElement, opacity: pressed ? 0.78 : 1 }]}
    >
      <View style={styles.positionHead}>
        <View style={[styles.weightBadge, { backgroundColor: colors.backgroundSelected }]}>
          <Text style={[styles.weightText, { color: colors.textSecondary }]}>{position.weightPct === null ? '—' : `${position.weightPct.toFixed(1)}٪`}</Text>
        </View>
        <View style={styles.positionTitleWrap}>
          <Text style={[styles.positionCode, { color: colors.text }]}>{position.code}</Text>
          <Text style={[styles.positionQty, { color: colors.textSecondary }]}>{position.quantity.toLocaleString('fa-IR')} سهم</Text>
        </View>
      </View>

      <View style={styles.metricsRow}>
        <View style={styles.metric}><Text style={[styles.metricValue, { color: colors.text }]}>{money(position.currentPrice)}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>قیمت روز</Text></View>
        <View style={styles.metric}><Text style={[styles.metricValue, { color: colors.text }]}>{money(position.averageCost)}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>میانگین خرید</Text></View>
        <View style={styles.metric}><Text style={[styles.metricValue, { color: colors.text }]}>{money(position.marketValue)}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>ارزش</Text></View>
      </View>

      <View style={styles.pnlRow}>
        <Text style={[styles.pnlValue, { color: positive ? Brand.positive : Brand.negative }]}>{pct(position.unrealizedPnLPct)}</Text>
        <Text style={[styles.pnlLabel, { color: colors.textSecondary }]}>سود/زیان تحقق‌نیافته: {money(position.unrealizedPnL)} ریال</Text>
      </View>
    </Pressable>
  );
}

export default function PortfolioScreen() {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  const [portfolio, setPortfolio] = useState<PaperPortfolio | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    const result = await fetchPaperPortfolio();
    if (result === null) {
      setError(true);
    } else {
      setError(false);
      setPortfolio(result);
    }
    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.four }]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={Brand.primary} />}
      >
        <View style={{ maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' }}>
          <View style={styles.header}>
            <View style={styles.headerLine}>
              <View style={styles.paperBadge}><Text style={styles.paperBadgeText}>PAPER</Text></View>
              <Text style={[styles.headerTitle, { color: colors.text }]}>پرتفوی من</Text>
            </View>
            <Text style={[styles.headerSub, { color: colors.textSecondary }]}>برگرفته از سفارش‌های Paper واقعی حساب شما؛ حساب کارگزاری واقعی هنوز متصل نیست.</Text>
          </View>

          {loading ? <Text style={[styles.stateText, { color: colors.textSecondary }]}>در حال محاسبه پرتفوی...</Text> : null}

          {error ? (
            <View style={[styles.stateCard, { backgroundColor: colors.backgroundElement }]}>
              <Text style={[styles.stateTitle, { color: colors.text }]}>دریافت پرتفوی ممکن نشد</Text>
              <Text style={[styles.stateText, { color: colors.textSecondary }]}>احراز هویت یا سرویس سفارش‌ها را بررسی کنید و دوباره پایین بکشید.</Text>
            </View>
          ) : null}

          {!loading && !error && portfolio ? (
            <>
              <View style={[styles.summary, { backgroundColor: colors.backgroundElement }]}>
                <Text style={[styles.summaryLabel, { color: colors.textSecondary }]}>ارزش کل پرتفوی Paper</Text>
                <Text style={[styles.summaryValue, { color: colors.text }]}>{money(portfolio.totalMarketValue)} <Text style={styles.rial}>ریال</Text></Text>
                <Text style={[styles.summaryPnl, { color: (portfolio.totalUnrealizedPnL ?? 0) >= 0 ? Brand.positive : Brand.negative }]}>
                  {pct(portfolio.totalUnrealizedPnLPct)}  •  {money(portfolio.totalUnrealizedPnL)} ریال
                </Text>
                <View style={styles.summaryMeta}>
                  <Text style={[styles.metaText, { color: colors.textSecondary }]}>{portfolio.pricedPositions}/{portfolio.totalPositions} پوزیشن با قیمت روز</Text>
                  <Text style={[styles.metaText, { color: colors.textSecondary }]}>{portfolio.totalPositions} دارایی باز</Text>
                </View>
              </View>

              {portfolio.positions.length === 0 ? (
                <View style={[styles.stateCard, { backgroundColor: colors.backgroundElement }]}>
                  <Text style={{ fontSize: 36 }}>💼</Text>
                  <Text style={[styles.stateTitle, { color: colors.text }]}>هنوز پوزیشن Paper باز ندارید</Text>
                  <Text style={[styles.stateText, { color: colors.textSecondary }]}>از تحلیل یک نماد، سفارش Paper ثبت کنید تا بعد از Fill اینجا وارد پرتفوی شود.</Text>
                  <Pressable onPress={() => router.push('/market')} style={[styles.primaryBtn, { backgroundColor: Brand.primary }]}><Text style={styles.primaryBtnText}>رفتن به بازار</Text></Pressable>
                </View>
              ) : (
                <>
                  <View style={styles.sectionHead}>
                    <Pressable onPress={() => router.push('/orders')}><Text style={{ color: Brand.primary, fontFamily: Fonts.sans, fontSize: 12 }}>تاریخچه سفارش‌ها ←</Text></Pressable>
                    <Text style={[styles.sectionTitle, { color: colors.text }]}>دارایی‌ها</Text>
                  </View>
                  {portfolio.positions.map((position) => <PositionCard key={position.code} position={position} colors={colors} />)}
                </>
              )}

              <View style={[styles.notice, { backgroundColor: colors.backgroundElement }]}>
                <Text style={[styles.noticeTitle, { color: colors.text }]}>اتصال کارگزاری واقعی</Text>
                <Text style={[styles.noticeBody, { color: colors.textSecondary }]}>این صفحه فعلاً فقط Paper Portfolio است. وقتی API و مجوز کارگزاری واقعی آماده شود، provider پرتفوی به داده کارگزاری تغییر می‌کند و رابط کاربری حفظ می‌شود.</Text>
              </View>
            </>
          ) : null}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { paddingHorizontal: Spacing.three },
  header: { paddingTop: Spacing.four, paddingBottom: Spacing.three, alignItems: 'flex-end' },
  headerLine: { flexDirection: 'row-reverse', alignItems: 'center', gap: Spacing.two },
  headerTitle: { fontSize: 22, fontFamily: Fonts.sans, textAlign: 'right', fontWeight: '800' },
  headerSub: { fontSize: 11.5, lineHeight: 19, fontFamily: Fonts.sans, textAlign: 'right', marginTop: 5 },
  paperBadge: { backgroundColor: '#7048e8', borderRadius: 12, paddingHorizontal: 8, paddingVertical: 3 },
  paperBadgeText: { color: '#fff', fontFamily: Fonts.mono, fontSize: 9, fontWeight: '800' },
  summary: { borderRadius: Radius.lg, padding: Spacing.four, alignItems: 'flex-end', marginBottom: Spacing.four },
  summaryLabel: { fontFamily: Fonts.sans, fontSize: 12 },
  summaryValue: { fontFamily: Fonts.mono, fontSize: 25, fontWeight: '800', marginTop: 5 },
  rial: { fontFamily: Fonts.sans, fontSize: 11, fontWeight: '400' },
  summaryPnl: { fontFamily: Fonts.mono, fontSize: 14, fontWeight: '800', marginTop: 5 },
  summaryMeta: { flexDirection: 'row-reverse', gap: Spacing.three, marginTop: Spacing.three },
  metaText: { fontFamily: Fonts.sans, fontSize: 10.5 },
  sectionHead: { flexDirection: 'row-reverse', alignItems: 'center', justifyContent: 'space-between', marginBottom: Spacing.two },
  sectionTitle: { fontFamily: Fonts.sans, fontSize: 16, fontWeight: '800' },
  positionCard: { borderRadius: Radius.md, padding: Spacing.three, marginBottom: Spacing.two },
  positionHead: { flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'center', marginBottom: Spacing.three },
  positionTitleWrap: { alignItems: 'flex-end' },
  positionCode: { fontFamily: Fonts.sans, fontSize: 16, fontWeight: '800' },
  positionQty: { fontFamily: Fonts.sans, fontSize: 10.5, marginTop: 2 },
  weightBadge: { borderRadius: 15, paddingHorizontal: 9, paddingVertical: 5 },
  weightText: { fontFamily: Fonts.mono, fontSize: 10, fontWeight: '700' },
  metricsRow: { flexDirection: 'row-reverse', gap: Spacing.two },
  metric: { flex: 1, alignItems: 'flex-end' },
  metricValue: { fontFamily: Fonts.mono, fontSize: 12, fontWeight: '700' },
  metricLabel: { fontFamily: Fonts.sans, fontSize: 9.5, marginTop: 3 },
  pnlRow: { flexDirection: 'row-reverse', justifyContent: 'space-between', alignItems: 'center', marginTop: Spacing.three },
  pnlValue: { fontFamily: Fonts.mono, fontSize: 13, fontWeight: '800' },
  pnlLabel: { fontFamily: Fonts.sans, fontSize: 10.5 },
  stateCard: { borderRadius: Radius.lg, padding: Spacing.four, alignItems: 'center', gap: Spacing.two, marginTop: Spacing.three },
  stateTitle: { fontFamily: Fonts.sans, fontSize: 16, fontWeight: '800', textAlign: 'center' },
  stateText: { fontFamily: Fonts.sans, fontSize: 12, lineHeight: 20, textAlign: 'center' },
  primaryBtn: { width: '100%', borderRadius: Radius.sm, paddingVertical: Spacing.three, alignItems: 'center', marginTop: Spacing.two },
  primaryBtnText: { color: '#fff', fontFamily: Fonts.sans, fontSize: 13, fontWeight: '800' },
  notice: { borderRadius: Radius.md, padding: Spacing.three, marginTop: Spacing.four, alignItems: 'flex-end' },
  noticeTitle: { fontFamily: Fonts.sans, fontSize: 13, fontWeight: '800' },
  noticeBody: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 18, textAlign: 'right', marginTop: 4 },
});
