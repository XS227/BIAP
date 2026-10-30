import { useEffect, useState } from 'react';
import { Alert, Linking, Pressable, ScrollView, Text, View, useColorScheme } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import { Colors, Brand } from '@/constants/theme';
import { getSelectedGlobalCompany } from '@/lib/global-company-selection';
import { BROKER_EXIT_NOTICE, brokersForMarket } from '@/lib/brokers';

export default function TradeBrokerScreen() {
  const params = useLocalSearchParams<{ country?: string; ticker?: string; isin?: string }>();
  const [selection, setSelection] = useState<{ country: string; ticker: string; isin?: string | null } | null>(null);
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  useEffect(() => {
    let active = true;
    void getSelectedGlobalCompany().then(company => {
      if (active) setSelection(company ? { country: company.country, ticker: company.ticker, isin: company.isin } : null);
    });
    return () => { active = false; };
  }, []);
  const country = String(params.country || selection?.country || '').toUpperCase();
  const ticker = String(params.ticker || selection?.ticker || '').trim();
  const brokers = brokersForMarket(country);
  const launch = (name: string, url: string) => Alert.alert(
    'Leaving BIAP', BROKER_EXIT_NOTICE,
    [{ text: 'Cancel', style: 'cancel' }, { text: 'Continue to ' + name, onPress: () => {
      void Linking.openURL(url).catch(() => Alert.alert('Link unavailable', 'Unable to open the broker website.'));
    } }],
  );
  return <SafeAreaView style={{ flex: 1, backgroundColor: colors.background }}>
    <ScrollView contentContainerStyle={{ padding: 20, gap: 14 }}>
      <Pressable onPress={() => router.back()}><Text style={{ color: Brand.primary }}>← Back</Text></Pressable>
      <Text style={{ color: colors.text, fontSize: 23, fontWeight: '800' }}>Trade at a Broker</Text>
      <Text style={{ color: colors.textSecondary }}>External broker websites only. Stocks and ETFs. No orders are placed inside BIAP.</Text>
      <Text style={{ color: colors.text, fontWeight: '700' }}>{ticker ? ticker + ' • ' + country : 'Select a company in Market first'}</Text>
      <Text style={{ color: colors.textSecondary, fontSize: 12 }}>{BROKER_EXIT_NOTICE}</Text>
      {brokers.map(broker => <Pressable key={broker.id} onPress={() => launch(broker.name, broker.url)}
        style={{ padding: 17, borderRadius: 12, backgroundColor: colors.backgroundElement }}>
        <Text style={{ color: colors.text, fontWeight: '700' }}>{broker.name} ↗</Text>
        <Text style={{ color: colors.textSecondary, fontSize: 11 }}>Official homepage • instrument must be searched at broker</Text>
      </Pressable>)}
      {!country ? <Text style={{ color: colors.textSecondary }}>No company selected; choose a company to see market-relevant brokers.</Text> : brokers.length === 0 ? <Text style={{ color: colors.textSecondary }}>No supported external broker listed for this market.</Text> : null}
      <Text style={{ color: colors.textSecondary, fontSize: 11 }}>Market availability depends on your country of residence and broker account. BIAP does not verify trading eligibility.</Text>
    </ScrollView>
  </SafeAreaView>;
}
