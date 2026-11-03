import { useCallback, useState } from 'react';
import { Alert, Linking, Pressable, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { AVAILABILITY_NOTE, BROKER_ASSET_CLASSES } from '@/config/brokers';
import { brokersForMarket, buildHandoff, LEAVE_NOTICE, type HandoffInstrument } from '@/lib/broker-handoff';
import { getSelectedGlobalCompany } from '@/lib/global-company-selection';
import { isSupportedGlobalEquityInstrument, unsupportedGlobalInstrumentMessage } from '@/lib/global-equity-filter';

type Target = HandoffInstrument & { name?: string | null };

/** "Trade at a Broker": hands the user to a licensed broker's official site. No orders, no credentials. */
export default function BrokerHandoffScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const params = useLocalSearchParams<{ country?: string; ticker?: string; name?: string; isin?: string }>();
  const [target, setTarget] = useState<Target | null>(null);
  const [loaded, setLoaded] = useState(false);

  useFocusEffect(useCallback(() => {
    let active = true;
    (async () => {
      if (params.ticker && params.country) {
        if (active) setTarget({ country: params.country, ticker: params.ticker, name: params.name, isin: params.isin || null });
      } else {
        const c = await getSelectedGlobalCompany();
        if (active) setTarget(c ? { country: c.country, ticker: c.ticker, name: c.name, isin: c.isin } : null);
      }
      if (active) setLoaded(true);
    })();
    return () => { active = false; };
  }, [params.country, params.ticker, params.name, params.isin]));

  const supported = target ? isSupportedGlobalEquityInstrument({ ticker: target.ticker || '', name: target.name || '' }) : false;
  const brokers = target && supported ? brokersForMarket(target.country) : [];

  const open = (brokerId: string) => {
    const broker = brokers.find((b) => b.id === brokerId);
    if (!broker || !target) return;
    const { url } = buildHandoff(broker, target);
    Alert.alert('Leaving BIAP', LEAVE_NOTICE, [
      { text: 'Cancel', style: 'cancel' },
      { text: `Open ${broker.name}`, onPress: () => { void Linking.openURL(url); } },
    ]);
  };

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.max}>
          <Pressable onPress={() => router.back()} style={[styles.back, { backgroundColor: colors.backgroundElement }]}><Text style={{ color: colors.text, fontFamily: Fonts.sans, fontSize: 11, fontWeight: '800' }}>‹ Back</Text></Pressable>
          <Text style={[styles.title, { color: colors.text }]}>Trade at a Broker</Text>
          <Text style={[styles.body, { color: colors.textSecondary }]}>{BROKER_ASSET_CLASSES}. BIAP only opens the broker’s official website or app; it does not place orders.</Text>

          <View style={[styles.notice, { borderColor: Brand.warning, backgroundColor: colors.backgroundElement }]}><Text style={[styles.body, { color: colors.textSecondary, marginTop: 0 }]}>{LEAVE_NOTICE}</Text></View>

          {!loaded ? null : !target ? (
            <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.body, { color: colors.textSecondary, marginTop: 0 }]}>No company selected. Open a company in Market first, then choose “Trade”.</Text></View>
          ) : (
            <>
              <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
                <Text style={[styles.cardTitle, { color: colors.text }]}>{target.name || target.ticker}</Text>
                <Text style={[styles.body, { color: colors.textSecondary }]}>{target.ticker} • {target.country}{target.isin ? ` • ${target.isin}` : ''}</Text>
                <Text style={[styles.body, { color: colors.textSecondary }]}>Search this ticker or ISIN on the broker’s platform; BIAP does not pre-fill it.</Text>
              </View>
              {!supported ? (
                <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.body, { color: Brand.warning, marginTop: 0 }]}>{unsupportedGlobalInstrumentMessage({ ticker: target.ticker || '', name: target.name || '' })}</Text></View>
              ) : brokers.length === 0 ? (
                <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.body, { color: colors.textSecondary, marginTop: 0 }]}>No configured broker covers this market ({target.country}).</Text></View>
              ) : brokers.map((b) => (
                <Pressable key={b.id} accessibilityRole="link" onPress={() => open(b.id)} style={({ pressed }) => [styles.broker, { backgroundColor: colors.backgroundElement, opacity: pressed ? 0.75 : 1 }]}>
                  <Text style={[styles.cardTitle, { color: colors.text }]}>{b.name}</Text>
                  <Text style={[styles.link, { color: Brand.primary }]}>Open official platform ↗</Text>
                </Pressable>
              ))}
            </>
          )}
          <Text style={[styles.disclaimer, { color: colors.textSecondary }]}>{AVAILABILITY_NOTE} Not investment advice.</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { paddingHorizontal: Spacing.three, paddingBottom: BottomTabInset + Spacing.six },
  max: { maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center', paddingTop: Spacing.four },
  back: { alignSelf: 'flex-start', paddingHorizontal: 11, paddingVertical: 8, borderRadius: 18 },
  title: { fontFamily: Fonts.sans, fontSize: 22, fontWeight: '900', marginTop: 12 },
  body: { fontFamily: Fonts.sans, fontSize: 11, lineHeight: 17, marginTop: 6 },
  notice: { borderWidth: 1, borderRadius: Radius.md, padding: 12, marginTop: 12 },
  card: { borderRadius: Radius.lg, padding: Spacing.four, marginTop: 12 },
  cardTitle: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '900' },
  broker: { borderRadius: Radius.lg, padding: Spacing.four, marginTop: 10 },
  link: { fontFamily: Fonts.sans, fontSize: 11, fontWeight: '800', marginTop: 6 },
  disclaimer: { fontFamily: Fonts.sans, fontSize: 9, lineHeight: 14, textAlign: 'center', marginTop: 18 },
});
