import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  useColorScheme,
  SafeAreaView,
  Pressable,
  Alert,
  Platform,
} from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import { Colors, Brand, Fonts, Spacing, BottomTabInset, MaxContentWidth, ThemeColors } from '@/constants/theme';
import { fetchWatchlist, formatPrice, parsePct, StockItem } from '@/lib/api';

function BarChart({
  items,
  colors,
}: {
  items: StockItem[];
  colors: ThemeColors;
}) {
  if (items.length === 0) return null;

  const prices = items.map((s) => s.closingPrice ?? 0);
  const maxPrice = Math.max(...prices);

  return (
    <View style={[barStyles.wrap, { backgroundColor: colors.backgroundElement }]}>
      <Text style={[barStyles.title, { color: colors.text }]}>مقایسه قیمت پایانی (ریال)</Text>
      <View style={barStyles.chart}>
        {items.map((item) => {
          const price = item.closingPrice ?? 0;
          const heightPct = maxPrice > 0 ? (price / maxPrice) * 100 : 0;
          const pct = parsePct(item.changePercent);
          const up = pct >= 0;

          return (
            <View key={item.code} style={barStyles.barCol}>
              <Text style={[barStyles.barValue, { color: colors.textSecondary }]}>
                {(price / 1000).toFixed(0)}K
              </Text>
              <View style={barStyles.barTrack}>
                <View
                  style={[
                    barStyles.bar,
                    {
                      height: `${Math.max(heightPct, 4)}%`,
                      backgroundColor: up ? Brand.stockGreen : Brand.negative,
                    },
                  ]}
                />
              </View>
              <Text style={[barStyles.barLabel, { color: colors.text }]}>{item.name}</Text>
            </View>
          );
        })}
      </View>
    </View>
  );
}

const barStyles = StyleSheet.create({
  wrap: { borderRadius: Spacing.two, padding: Spacing.three, marginBottom: Spacing.three },
  title: { fontFamily: Fonts.sans, fontSize: 15, textAlign: 'right', marginBottom: Spacing.three },
  chart: { flexDirection: 'row-reverse', alignItems: 'flex-end', height: 160, gap: Spacing.two },
  barCol: { flex: 1, alignItems: 'center', height: '100%' },
  barTrack: { flex: 1, width: '100%', justifyContent: 'flex-end', alignItems: 'center' },
  bar: { width: '70%', borderRadius: 4, minHeight: 4 },
  barValue: { fontFamily: Fonts.mono, fontSize: 10, marginBottom: 4 },
  barLabel: { fontFamily: Fonts.sans, fontSize: 11, marginTop: 6, textAlign: 'center' },
});

function PctChart({ items, colors }: { items: StockItem[]; colors: ThemeColors }) {
  if (items.length === 0) return null;

  const pcts = items.map((s) => parsePct(s.changePercent));
  const absMax = Math.max(...pcts.map(Math.abs), 0.01);

  return (
    <View style={[pctStyles.wrap, { backgroundColor: colors.backgroundElement }]}>
      <Text style={[pctStyles.title, { color: colors.text }]}>تغییر درصدی امروز</Text>
      {items.map((item) => {
        const pct = parsePct(item.changePercent);
        const up = pct >= 0;
        const barWidth = (Math.abs(pct) / absMax) * 100;
        const color = up ? Brand.stockGreen : Brand.negative;

        return (
          <View key={item.code} style={pctStyles.row}>
            <Text style={[pctStyles.name, { color: colors.text }]}>{item.name}</Text>
            <View style={pctStyles.barWrap}>
              <View style={pctStyles.centerLine}>
                {up ? (
                  <View style={{ flex: 1 }} />
                ) : null}
                <View
                  style={[
                    pctStyles.bar,
                    {
                      width: `${barWidth}%`,
                      backgroundColor: color,
                      alignSelf: up ? 'flex-end' : 'flex-start',
                    },
                  ]}
                />
                {!up ? (
                  <View style={{ flex: 1 }} />
                ) : null}
              </View>
            </View>
            <Text style={[pctStyles.pct, { color }]}>
              {up ? '+' : ''}{pct.toFixed(2)}٪
            </Text>
          </View>
        );
      })}
    </View>
  );
}

const pctStyles = StyleSheet.create({
  wrap: { borderRadius: Spacing.two, padding: Spacing.three, marginBottom: Spacing.three },
  title: { fontFamily: Fonts.sans, fontSize: 15, textAlign: 'right', marginBottom: Spacing.three },
  row: {
    flexDirection: 'row-reverse',
    alignItems: 'center',
    marginBottom: Spacing.two,
    gap: Spacing.two,
  },
  name: { fontFamily: Fonts.sans, fontSize: 13, width: 52, textAlign: 'right' },
  barWrap: { flex: 1, height: 18 },
  centerLine: { flex: 1, flexDirection: 'row', height: '100%', alignItems: 'center' },
  bar: { height: 12, borderRadius: 6, minWidth: 4 },
  pct: { fontFamily: Fonts.mono, fontSize: 13, width: 64, textAlign: 'left' },
});

function DataTable({ items, colors }: { items: StockItem[]; colors: ThemeColors }) {
  return (
    <View style={[tableStyles.wrap, { backgroundColor: colors.backgroundElement }]}>
      <Text style={[tableStyles.title, { color: colors.text }]}>جدول کامل داده‌ها</Text>

      {/* Header */}
      <View style={[tableStyles.row, tableStyles.headerRow, { borderBottomColor: colors.backgroundSelected }]}>
        <Text style={[tableStyles.cell, tableStyles.cellName, { color: colors.textSecondary }]}>نماد</Text>
        <Text style={[tableStyles.cell, { color: colors.textSecondary }]}>قیمت دیروز</Text>
        <Text style={[tableStyles.cell, { color: colors.textSecondary }]}>قیمت پایانی</Text>
        <Text style={[tableStyles.cell, { color: colors.textSecondary }]}>تغییر</Text>
      </View>

      {items.map((item, i) => {
        const pct = parsePct(item.changePercent);
        const up = pct >= 0;
        const diff = (item.closingPrice ?? 0) - (item.yesterdayPrice ?? 0);
        const isLast = i === items.length - 1;

        return (
          <View
            key={item.code}
            style={[
              tableStyles.row,
              !isLast && tableStyles.rowBorder,
              { borderBottomColor: colors.backgroundSelected },
            ]}
          >
            <Text style={[tableStyles.cell, tableStyles.cellName, { color: colors.text }]}>
              {item.name}
            </Text>
            <Text style={[tableStyles.cell, { color: colors.textSecondary }]}>
              {formatPrice(item.yesterdayPrice)}
            </Text>
            <Text style={[tableStyles.cell, { color: colors.text }]}>
              {formatPrice(item.closingPrice)}
            </Text>
            <Text style={[tableStyles.cell, { color: up ? Brand.stockGreen : Brand.negative }]}>
              {diff >= 0 ? '+' : ''}{formatPrice(diff)}
            </Text>
          </View>
        );
      })}
    </View>
  );
}

const tableStyles = StyleSheet.create({
  wrap: { borderRadius: Spacing.two, padding: Spacing.three, marginBottom: Spacing.three },
  title: { fontFamily: Fonts.sans, fontSize: 15, textAlign: 'right', marginBottom: Spacing.three },
  row: { flexDirection: 'row-reverse', paddingVertical: Spacing.two },
  headerRow: { borderBottomWidth: 1, marginBottom: 2 },
  rowBorder: { borderBottomWidth: StyleSheet.hairlineWidth },
  cell: { flex: 1, fontFamily: Fonts.mono, fontSize: 12, textAlign: 'center' },
  cellName: { fontFamily: Fonts.sans, fontSize: 13 },
});

function StatSummary({ items, colors }: { items: StockItem[]; colors: ThemeColors }) {
  if (items.length === 0) return null;

  const prices = items.map((s) => s.closingPrice ?? 0).filter(Boolean);
  const pcts = items.map((s) => parsePct(s.changePercent));

  const totalValue = prices.reduce((a, b) => a + b, 0);
  const avgPrice = prices.length ? totalValue / prices.length : 0;
  const maxPct = Math.max(...pcts);
  const minPct = Math.min(...pcts);
  const stdDev = Math.sqrt(
    pcts.reduce((sum, p) => sum + Math.pow(p - (pcts.reduce((a, b) => a + b, 0) / pcts.length), 2), 0) /
      pcts.length
  );

  const stats = [
    { label: 'میانگین قیمت', value: formatPrice(Math.round(avgPrice)) + ' ریال' },
    { label: 'بیشترین رشد', value: `+${maxPct.toFixed(2)}٪` },
    { label: 'بیشترین افت', value: `${minPct.toFixed(2)}٪` },
    { label: 'انحراف معیار', value: `${stdDev.toFixed(2)}٪` },
  ];

  return (
    <View style={[sumStyles.wrap, { backgroundColor: colors.backgroundElement }]}>
      <Text style={[sumStyles.title, { color: colors.text }]}>آمار کلی</Text>
      {stats.map((s) => (
        <View key={s.label} style={[sumStyles.row, { borderBottomColor: colors.backgroundSelected }]}>
          <Text style={[sumStyles.val, { color: Brand.dataViolet }]}>{s.value}</Text>
          <Text style={[sumStyles.lbl, { color: colors.textSecondary }]}>{s.label}</Text>
        </View>
      ))}
    </View>
  );
}

const sumStyles = StyleSheet.create({
  wrap: { borderRadius: Spacing.two, padding: Spacing.three, marginBottom: Spacing.three },
  title: { fontFamily: Fonts.sans, fontSize: 15, textAlign: 'right', marginBottom: Spacing.three },
  row: {
    flexDirection: 'row-reverse',
    justifyContent: 'space-between',
    paddingVertical: Spacing.two,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  lbl: { fontFamily: Fonts.sans, fontSize: 13 },
  val: { fontFamily: Fonts.mono, fontSize: 13, fontWeight: '700' },
});

async function exportCSV(stocks: StockItem[]) {
  const header = 'نام,کد,قیمت پایانی,آخرین قیمت,قیمت دیروز,تغییر,درصد تغییر\n';
  const rows = stocks
    .map((s) =>
      [s.name, s.code, s.closingPrice ?? '', s.lastPrice ?? '', s.yesterdayPrice ?? '', s.change ?? '', s.changePercent ?? ''].join(',')
    )
    .join('\n');
  const csv = header + rows;

  if (Platform.OS === 'web') {
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'biap-data.csv';
    a.click();
    URL.revokeObjectURL(url);
    return;
  }

  const uri = `${FileSystem.documentDirectory}biap-data.csv`;
  await FileSystem.writeAsStringAsync(uri, csv, { encoding: FileSystem.EncodingType.UTF8 });
  const canShare = await Sharing.isAvailableAsync();
  if (canShare) {
    await Sharing.shareAsync(uri, { mimeType: 'text/csv', dialogTitle: 'خروجی CSV داده‌های بازار' });
  } else {
    Alert.alert('ذخیره شد', `فایل CSV در مسیر زیر ذخیره شد:\n${uri}`);
  }
}

export default function DataScreen() {
  const scheme = useColorScheme() ?? 'light';
  const colors = Colors[scheme];

  const [stocks, setStocks] = useState<StockItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);
  const [exporting, setExporting] = useState(false);

  // Memoize to avoid recomputing on every render
  const sortedByPrice = useMemo(
    () => [...stocks].sort((a, b) => (b.closingPrice ?? 0) - (a.closingPrice ?? 0)),
    [stocks]
  );

  const load = useCallback(async () => {
    try {
      setError(false);
      const data = await fetchWatchlist();
      setStocks(data);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const onRefresh = () => {
    setRefreshing(true);
    load();
  };

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={[
          styles.content,
          { paddingBottom: BottomTabInset + Spacing.four },
        ]}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={Brand.dataViolet}
          />
        }
      >
        <View style={{ maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' }}>
          <View style={styles.header}>
            <Text style={[styles.headerTitle, { color: colors.text }]}>تحلیل داده</Text>
            <Text style={[styles.headerSub, { color: colors.textSecondary }]}>
              نمودارها و آمار بازار سرمایه
            </Text>
          </View>

          {error && (
            <View style={[styles.errorBox, { backgroundColor: colors.backgroundElement }]}>
              <Text style={{ color: colors.textSecondary, textAlign: 'right', fontFamily: Fonts.sans }}>
                خطا در دریافت داده. برای تلاش دوباره پایین بکشید.
              </Text>
            </View>
          )}

          {loading && (
            <View style={styles.loadingWrap}>
              <Text style={{ color: colors.textSecondary, fontFamily: Fonts.sans }}>
                در حال بارگذاری...
              </Text>
            </View>
          )}

          {!loading && stocks.length > 0 && (
            <>
              <Pressable
                style={({ pressed }) => [
                  exportStyles.btn,
                  { backgroundColor: Brand.dataViolet, opacity: pressed || exporting ? 0.7 : 1 },
                ]}
                disabled={exporting}
                onPress={async () => {
                  setExporting(true);
                  try { await exportCSV(stocks); } catch { Alert.alert('خطا', 'خروجی CSV ناموفق بود'); }
                  finally { setExporting(false); }
                }}
              >
                <Text style={exportStyles.btnText}>
                  {exporting ? 'در حال خروجی...' : '⬇ خروجی CSV'}
                </Text>
              </Pressable>
              <StatSummary items={stocks} colors={colors} />
              <BarChart items={stocks} colors={colors} />
              <PctChart items={stocks} colors={colors} />
              <DataTable items={sortedByPrice} colors={colors} />
            </>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { paddingHorizontal: Spacing.three },
  header: {
    paddingTop: Spacing.four,
    paddingBottom: Spacing.three,
  },
  headerTitle: { fontSize: 22, fontFamily: Fonts.sans, textAlign: 'right' },
  headerSub: { fontSize: 13, fontFamily: Fonts.sans, textAlign: 'right', marginTop: 2 },
  errorBox: { borderRadius: Spacing.two, padding: Spacing.three, marginBottom: Spacing.three },
  loadingWrap: { alignItems: 'center', marginTop: Spacing.six },
});

const exportStyles = StyleSheet.create({
  btn: { borderRadius: Spacing.two, paddingVertical: Spacing.two, paddingHorizontal: Spacing.three, alignItems: 'center', marginBottom: Spacing.three },
  btnText: { color: '#fff', fontFamily: Fonts.sans, fontSize: 14, fontWeight: '700' },
});
