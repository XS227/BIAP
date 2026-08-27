import { useCallback, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, RefreshControl, useColorScheme, SafeAreaView, Pressable } from 'react-native';
import { useFocusEffect, router } from 'expo-router';
import { Colors, Brand, Fonts, Spacing, Radius, BottomTabInset, MaxContentWidth, ThemeColors } from '@/constants/theme';
import { getLocalOrders, LocalOrderReceipt } from '@/lib/order-history';

const SIDE_LABEL: Record<string, string> = { BUY: 'خرید', SELL: 'فروش' };
const STATUS_LABEL: Record<string, string> = {
  PAPER_FILLED: 'اجرا شد (Paper)',
  PENDING_APPROVAL: 'در انتظار تأیید',
  SIMULATED: 'شبیه‌سازی شد',
};

function statusColor(status: string) {
  if (status === 'PAPER_FILLED') return Brand.positive;
  if (status === 'PENDING_APPROVAL') return Brand.warning;
  return Brand.secondary;
}

function OrderCard({ order, colors }: { order: LocalOrderReceipt; colors: ThemeColors }) {
  const sideColor = order.side === 'BUY' ? Brand.positive : Brand.negative;
  const date = new Date(order.submittedAt);
  const dateLabel = Number.isNaN(date.getTime()) ? '' : date.toLocaleString('fa-IR');

  return (
    <Pressable
      onPress={() => router.push(`/stock/${order.code}`)}
      style={({ pressed }) => [orderStyles.card, { backgroundColor: colors.backgroundElement, opacity: pressed ? 0.8 : 1 }]}
    >
      <View style={orderStyles.topRow}>
        <View style={[orderStyles.statusBadge, { backgroundColor: `${statusColor(order.status)}22` }]}>
          <Text style={[orderStyles.statusText, { color: statusColor(order.status) }]}>
            {STATUS_LABEL[order.status] ?? order.status}
          </Text>
        </View>
        <View style={[orderStyles.sideBadge, { backgroundColor: `${sideColor}22` }]}>
          <Text style={[orderStyles.sideText, { color: sideColor }]}>{SIDE_LABEL[order.side] ?? order.side}</Text>
        </View>
      </View>

      <Text style={[orderStyles.code, { color: colors.text }]}>{order.code}</Text>
      <Text style={[orderStyles.meta, { color: colors.textSecondary }]}>
        {order.quantity} سهم · Paper — بدون معامله واقعی
      </Text>
      {order.note ? <Text style={[orderStyles.note, { color: colors.textSecondary }]}>{order.note}</Text> : null}
      {dateLabel ? <Text style={[orderStyles.date, { color: colors.textSecondary }]}>{dateLabel}</Text> : null}
    </Pressable>
  );
}

const orderStyles = StyleSheet.create({
  card: { borderRadius: Radius.md, padding: Spacing.three, marginBottom: Spacing.two, alignItems: 'flex-end', gap: 4 },
  topRow: { flexDirection: 'row-reverse', gap: Spacing.one },
  statusBadge: { paddingHorizontal: Spacing.two, paddingVertical: 4, borderRadius: Radius.sm },
  statusText: { fontFamily: Fonts.sans, fontSize: 11, fontWeight: '700' },
  sideBadge: { paddingHorizontal: Spacing.two, paddingVertical: 4, borderRadius: Radius.sm },
  sideText: { fontFamily: Fonts.sans, fontSize: 11, fontWeight: '700' },
  code: { fontFamily: Fonts.mono, fontSize: 15, marginTop: 4 },
  meta: { fontFamily: Fonts.sans, fontSize: 12 },
  note: { fontFamily: Fonts.sans, fontSize: 12 },
  date: { fontFamily: Fonts.mono, fontSize: 11, marginTop: 2 },
});

function EmptyState({ colors }: { colors: ThemeColors }) {
  return (
    <View style={emptyStyles.wrap}>
      <Text style={{ fontSize: 40 }}>🧾</Text>
      <Text style={[emptyStyles.title, { color: colors.text }]}>هنوز سفارشی ثبت نشده</Text>
      <Text style={[emptyStyles.body, { color: colors.textSecondary }]}>
        از صفحه‌ی هر سهم می‌توانید توصیه‌ی هوش مصنوعی را ببینید و یک معامله را در حالت Paper شبیه‌سازی کنید — بدون
        اینکه معامله‌ی واقعی انجام شود.
      </Text>
      <Pressable onPress={() => router.push('/market')} style={[emptyStyles.btn, { backgroundColor: Brand.primary }]}>
        <Text style={emptyStyles.btnText}>برو به بازار</Text>
      </Pressable>
    </View>
  );
}
const emptyStyles = StyleSheet.create({
  wrap: { alignItems: 'center', gap: Spacing.two, paddingTop: Spacing.six, paddingHorizontal: Spacing.four },
  title: { fontFamily: Fonts.sans, fontSize: 17, fontWeight: '700' },
  body: { fontFamily: Fonts.sans, fontSize: 13, textAlign: 'center', lineHeight: 21 },
  btn: { marginTop: Spacing.two, borderRadius: Radius.sm, paddingHorizontal: Spacing.four, paddingVertical: Spacing.three },
  btnText: { color: '#fff', fontFamily: Fonts.sans, fontSize: 14, fontWeight: '700' },
});

export default function OrdersScreen() {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  const [orders, setOrders] = useState<LocalOrderReceipt[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    const items = await getLocalOrders();
    setOrders(items);
    setRefreshing(false);
  }, []);

  // Reload every time this tab gains focus -- e.g. after simulating an
  // order from a stock detail screen and navigating back here.
  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const onRefresh = () => {
    setRefreshing(true);
    load();
  };

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.four }]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={Brand.primary} />}
      >
        <View style={{ maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' }}>
          <View style={styles.header}>
            <Text style={[styles.headerTitle, { color: colors.text }]}>سفارش‌ها</Text>
            <Text style={[styles.headerSub, { color: colors.textSecondary }]}>
              شبیه‌سازی‌های Paper شما — فقط روی همین دستگاه ذخیره می‌شود
            </Text>
          </View>

          {orders.length === 0 ? (
            <EmptyState colors={colors} />
          ) : (
            orders.map((o) => <OrderCard key={o.id} order={o} colors={colors} />)
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { paddingHorizontal: Spacing.three },
  header: { paddingTop: Spacing.four, paddingBottom: Spacing.three },
  headerTitle: { fontSize: 22, fontFamily: Fonts.sans, textAlign: 'right', fontWeight: '700' },
  headerSub: { fontSize: 13, fontFamily: Fonts.sans, textAlign: 'right', marginTop: 4 },
});
