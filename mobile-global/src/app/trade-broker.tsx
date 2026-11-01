import { useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Alert, Linking, Pressable, ScrollView, Text, View, useColorScheme } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import { Colors, Brand } from '@/constants/theme';
import { getSelectedGlobalCompany } from '@/lib/global-company-selection';
import { BROKER_EXIT_NOTICE, brokersForMarket, brokerPreferenceKey, resolveBrokerPreference } from '@/lib/brokers';

export default function TradeBrokerScreen() {
  const params = useLocalSearchParams<{ country?: string; ticker?: string; isin?: string }>();
  const [selection, setSelection] = useState<{ country: string; ticker: string; isin?: string | null } | null>(null);
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [preference, setPreference] = useState<{ key: string; id: string | null; error: string | null } | null>(null);
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
  const preferenceKey = brokerPreferenceKey(country);
  const preferenceReady = !preferenceKey || preference?.key === preferenceKey;
  const selectedBrokerId = preferenceKey && preference?.key === preferenceKey ? preference.id : null;
  const preferenceError = preferenceKey && preference?.key === preferenceKey ? preference.error : null;
  useEffect(() => {
    let active = true;
    if (preferenceKey) {
      void AsyncStorage.getItem(preferenceKey).then(id => {
        if (active) setPreference({ key: preferenceKey, id: resolveBrokerPreference(country, id)?.id ?? null, error: null });
      }).catch(() => {
        if (active) setPreference({ key: preferenceKey, id: null, error: 'Saved preference could not be read on this device.' });
      });
    }
    return () => { active = false; };
  }, [country, preferenceKey]);

  const chooseBroker = async (id: string) => {
    if (!preferenceKey || !preferenceReady || !resolveBrokerPreference(country, id)) return;
    const next = selectedBrokerId === id ? null : id;
    try {
      if (next) await AsyncStorage.setItem(preferenceKey, next);
      else await AsyncStorage.removeItem(preferenceKey);
      setPreference({ key: preferenceKey, id: next, error: null });
    } catch {
      setPreference({ key: preferenceKey, id: selectedBrokerId, error: 'Could not save broker preference. No order was sent.' });
    }
  };
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
      <Text style={{ color: colors.textSecondary, fontSize: 12 }}>Choose a preferred broker for this market (saved only on this device). This does not connect an account, verify eligibility or enable trading.</Text>
      {preferenceError ? <Text accessibilityRole="alert" style={{ color: Brand.negative }}>{preferenceError}</Text> : null}
      {brokers.map(broker => <View key={broker.id}
        style={{ padding: 17, borderRadius: 12, backgroundColor: colors.backgroundElement, gap: 10 }}>
        <Text style={{ color: colors.text, fontWeight: '700' }}>{broker.name}{selectedBrokerId === broker.id ? ' • Preferred' : ''}</Text>
        <Pressable accessibilityRole="radio" accessibilityState={{ selected: selectedBrokerId === broker.id, disabled: !preferenceReady }}
          disabled={!preferenceReady} onPress={() => { void chooseBroker(broker.id); }}
          style={{ paddingVertical: 9, borderRadius: 8, borderWidth: 1, borderColor: Brand.primary, alignItems: 'center' }}>
          <Text style={{ color: Brand.primary }}>{selectedBrokerId === broker.id ? 'Clear preference' : 'Choose as preferred'}</Text>
        </Pressable>
        <Pressable accessibilityRole="link" onPress={() => launch(broker.name, broker.url)} style={{ paddingVertical: 7 }}>
          <Text style={{ color: colors.text }}>Open official broker website ↗</Text>
        </Pressable>
        <Text style={{ color: colors.textSecondary, fontSize: 11 }}>Instrument must be searched at broker. No account connection or orders.</Text>
      </View>)}
      {!country ? <Text style={{ color: colors.textSecondary }}>No company selected; choose a company to see market-relevant brokers.</Text> : brokers.length === 0 ? <Text style={{ color: colors.textSecondary }}>No supported external broker listed for this market.</Text> : null}
      <Text style={{ color: colors.textSecondary, fontSize: 11 }}>Market availability depends on your country of residence and broker account. BIAP does not verify trading eligibility.</Text>
    </ScrollView>
  </SafeAreaView>;
}
