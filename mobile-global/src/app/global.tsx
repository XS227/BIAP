import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router } from 'expo-router';
import { Brand, Colors, Fonts, Radius, Spacing } from '@/constants/theme';
import { fetchGlobalCountries, GlobalCountry, GlobalExchange } from '@/lib/global-api';
import { getGlobalMarketSelection, setGlobalMarketSelection } from '@/lib/global-market-selection';

const PRIORITY = ['US', 'GB', 'NO', 'SE', 'JP', 'AU', 'IR'];

export default function GlobalScreen() {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  const [countries, setCountries] = useState<GlobalCountry[]>([]);
  const [countryCode, setCountryCode] = useState('US');
  const [exchangeCode, setExchangeCode] = useState('NASDAQ');
  const [loading, setLoading] = useState(true);
  const [catalogLive, setCatalogLive] = useState(false);

  useEffect(() => {
    Promise.all([fetchGlobalCountries(), getGlobalMarketSelection()])
      .then(([catalog, saved]) => {
        setCountries(catalog.countries);
        setCatalogLive(catalog.live);
        const savedCountry = catalog.countries.find((item) => item.country === saved.country);
        const savedExchange = savedCountry?.exchanges.find((item) => item.code === saved.exchange);
        if (savedCountry && savedExchange) {
          setCountryCode(savedCountry.country);
          setExchangeCode(savedExchange.code);
          return;
        }
        const first = catalog.countries[0];
        if (first) {
          setCountryCode(first.country);
          setExchangeCode(first.exchanges.length === 1 ? first.exchanges[0]?.code || '' : '');
        }
      })
      .finally(() => setLoading(false));
  }, []);

  const priorityCountries = useMemo(() => {
    const rank = new Map(PRIORITY.map((code, index) => [code, index]));
    return [...countries].sort((a, b) => (rank.get(a.country) ?? 99) - (rank.get(b.country) ?? 99));
  }, [countries]);

  const selectedCountry = countries.find((item) => item.country === countryCode) || priorityCountries[0];
  const selectedExchange = selectedCountry
    ? selectedCountry.exchanges.find((item) => item.code === exchangeCode)
      || (selectedCountry.exchanges.length === 1 ? selectedCountry.exchanges[0] : undefined)
    : undefined;

  const persistAndOpen = async (country: GlobalCountry, exchange: GlobalExchange) => {
    await setGlobalMarketSelection({
      country: country.country,
      countryName: country.name,
      exchange: exchange.code,
      exchangeLabel: exchange.label,
      mic: exchange.mic,
      currency: exchange.currencies[0] || '',
    });
    router.replace('/market');
  };

  const chooseCountry = async (country: GlobalCountry) => {
    setCountryCode(country.country);
    if (country.exchanges.length === 1 && country.exchanges[0]) {
      const onlyExchange = country.exchanges[0];
      setExchangeCode(onlyExchange.code);
      await persistAndOpen(country, onlyExchange);
      return;
    }
    // Multi-exchange countries require an explicit exchange choice.
    setExchangeCode('');
  };

  const chooseExchange = async (exchange: GlobalExchange) => {
    if (!selectedCountry) return;
    setExchangeCode(exchange.code);
    await persistAndOpen(selectedCountry, exchange);
  };

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.kicker}>BIAP GLOBAL</Text>
        <Text style={[styles.title, { color: colors.text }]}>Choose a market</Text>
        <Text style={[styles.subtitle, { color: colors.textSecondary }]}>This step only selects the country and exchange data source. After selection, the full English BIAP opens with the same Market, Stock Analysis, Kiasha, Portfolio and Modules.</Text>

        <View style={[styles.statusCard, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
          <Text style={[styles.statusTitle, { color: colors.text }]}>{catalogLive ? '● Global data catalog connected' : '○ Market catalog preview'}</Text>
          <Text style={[styles.statusText, { color: colors.textSecondary }]}>The BIAP engine does not change by country. Only the market and filing adapters change.</Text>
        </View>

        {selectedCountry?.exchanges.length && selectedCountry.exchanges.length > 1 ? (
          <>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>Exchange</Text>
            <Text style={[styles.exchangePrompt, { color: colors.textSecondary }]}>Choose which {selectedCountry.name} exchange to open.</Text>
            <View style={styles.exchangeList}>
              {selectedCountry.exchanges.map((exchange) => {
                const active = exchange.code === exchangeCode;
                return (
                  <Pressable key={exchange.code} onPress={() => { void chooseExchange(exchange); }} style={[styles.exchangeCard, { backgroundColor: active ? Brand.primary : colors.backgroundElement, borderColor: active ? Brand.primary : colors.backgroundSelected }]}>
                    <View style={{ flex: 1 }}>
                      <Text style={[styles.exchangeTitle, { color: active ? '#fff' : colors.text }]}>{exchange.label}</Text>
                      <Text style={[styles.exchangeMeta, { color: active ? '#EAF2FF' : colors.textSecondary }]}>{exchange.mic || exchange.code} • {exchange.currencies.join('/')}</Text>
                    </View>
                    <Text style={[styles.chevron, { color: active ? '#fff' : Brand.primary }]}>›</Text>
                  </Pressable>
                );
              })}
            </View>
          </>
        ) : null}

        <Text style={[styles.sectionTitle, { color: colors.text }]}>Country</Text>
        {loading ? <ActivityIndicator color={Brand.primary} /> : (
          <View style={styles.countryGrid}>
            {priorityCountries.map((country) => {
              const active = country.country === selectedCountry?.country;
              return (
                <Pressable key={country.country} onPress={() => { void chooseCountry(country); }} style={[styles.countryCard, { backgroundColor: active ? Brand.primary : colors.backgroundElement, borderColor: active ? Brand.primary : colors.backgroundSelected }]}>
                  <Text style={[styles.countryCode, { color: active ? '#fff' : colors.text }]}>{country.country}</Text>
                  <Text numberOfLines={1} style={[styles.countryName, { color: active ? '#fff' : colors.textSecondary }]}>{country.name}</Text>
                  <Text style={[styles.countryMeta, { color: active ? '#EAF2FF' : colors.textSecondary }]}>{country.exchanges.length} exchange{country.exchanges.length === 1 ? '' : 's'}</Text>
                </Pressable>
              );
            })}
          </View>
        )}

        {selectedCountry && selectedExchange ? (
          <View style={[styles.adapterCard, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
            <Text style={[styles.adapterTitle, { color: colors.text }]}>Selected data sources</Text>
            <Text style={[styles.adapterLine, { color: colors.textSecondary }]}>Market: {selectedCountry.marketProvider || 'market adapter'}</Text>
            <Text style={[styles.adapterLine, { color: colors.textSecondary }]}>Fundamentals: {selectedCountry.fundamentalsProvider || 'official filings'}</Text>
            <Text style={[styles.adapterLine, { color: colors.textSecondary }]}>Evidence: {selectedCountry.officialEvidenceSource || 'issuer/regulator filings'}</Text>
          </View>
        ) : null}

        {selectedCountry && selectedExchange ? (
          <Pressable onPress={() => { void persistAndOpen(selectedCountry, selectedExchange); }} style={[styles.continueButton, { backgroundColor: Brand.primary }]}>
            <Text style={styles.continueText}>Open full BIAP for {selectedCountry.name}</Text>
          </Pressable>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { padding: Spacing.three, paddingBottom: 80 },
  kicker: { color: Brand.primary, fontFamily: Fonts.mono, fontSize: 10, fontWeight: '900', letterSpacing: 1.2, marginTop: Spacing.three },
  title: { fontFamily: Fonts.sans, fontSize: 30, fontWeight: '900', marginTop: 8 },
  subtitle: { fontFamily: Fonts.sans, fontSize: 13, lineHeight: 21, marginTop: 8 },
  statusCard: { borderWidth: 1, borderRadius: Radius.md, padding: Spacing.three, marginTop: Spacing.four },
  statusTitle: { fontFamily: Fonts.sans, fontSize: 12, fontWeight: '800' },
  statusText: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 17, marginTop: 5 },
  sectionTitle: { fontFamily: Fonts.sans, fontSize: 16, fontWeight: '900', marginTop: Spacing.four, marginBottom: 10 },
  countryGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 9 },
  countryCard: { width: '48%', borderWidth: 1, borderRadius: Radius.md, padding: 13 },
  countryCode: { fontFamily: Fonts.mono, fontSize: 17, fontWeight: '900' },
  countryName: { fontFamily: Fonts.sans, fontSize: 12, fontWeight: '700', marginTop: 4 },
  countryMeta: { fontFamily: Fonts.mono, fontSize: 9, marginTop: 5 },
  exchangePrompt: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 16, marginTop: -4, marginBottom: 9 },
  exchangeList: { gap: 8 },
  exchangeCard: { borderWidth: 1, borderRadius: Radius.md, padding: 13, flexDirection: 'row', alignItems: 'center' },
  exchangeTitle: { fontFamily: Fonts.sans, fontSize: 13, fontWeight: '900' },
  exchangeMeta: { fontFamily: Fonts.mono, fontSize: 9.5, marginTop: 4 },
  chevron: { fontSize: 28, marginLeft: 10 },
  adapterCard: { borderWidth: 1, borderRadius: Radius.md, padding: Spacing.three, marginTop: Spacing.four },
  adapterTitle: { fontFamily: Fonts.sans, fontSize: 12, fontWeight: '900', marginBottom: 6 },
  adapterLine: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 18 },
  continueButton: { minHeight: 52, borderRadius: Radius.md, alignItems: 'center', justifyContent: 'center', marginTop: 14, paddingHorizontal: 16 },
  continueText: { color: '#fff', fontFamily: Fonts.sans, fontSize: 13, fontWeight: '900', textAlign: 'center' },
});
