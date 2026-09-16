import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router } from 'expo-router';
import { Brand, Colors, Fonts, Radius, Spacing } from '@/constants/theme';
import { fetchGlobalCountries, GlobalAnalysis, GlobalCountry, GlobalExchange, scanGlobalMarket } from '@/lib/global-api';
import { getGlobalMarketSelection, setGlobalMarketSelection } from '@/lib/global-market-selection';

const PRIORITY = ['US', 'GB', 'NO', 'SE', 'JP', 'AU', 'IR'];

function pct(value?: number) {
  if (value == null || Number.isNaN(value)) return '—';
  return `${Math.round(value * 100)}%`;
}

function ResultCard({ item, colors }: { item: GlobalAnalysis; colors: (typeof Colors)['light'] | (typeof Colors)['dark'] }) {
  const positive = item.call === 'BUY_CANDIDATE';
  const caution = item.call === 'HOLD_OR_WATCH';
  const callColor = positive ? Brand.positive : caution ? Brand.warning : item.call === 'NO_RECOMMENDATION' ? colors.textSecondary : Brand.negative;
  return (
    <View style={[styles.resultCard, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
      <View style={styles.rowBetween}>
        <View style={{ flex: 1 }}>
          <Text style={[styles.resultTicker, { color: colors.text }]}>{item.ticker || '—'}</Text>
          <Text numberOfLines={1} style={[styles.resultName, { color: colors.textSecondary }]}>{item.name || item.exchange || ''}</Text>
        </View>
        <View style={[styles.callPill, { borderColor: callColor }]}><Text style={[styles.callText, { color: callColor }]}>{item.call || 'UNRATED'}</Text></View>
      </View>
      <View style={styles.metricsRow}>
        <Text style={[styles.metric, { color: colors.textSecondary }]}>Score <Text style={{ color: colors.text }}>{item.score == null ? '—' : item.score.toFixed(3)}</Text></Text>
        <Text style={[styles.metric, { color: colors.textSecondary }]}>Confidence <Text style={{ color: colors.text }}>{pct(item.confidence)}</Text></Text>
        <Text style={[styles.metric, { color: colors.textSecondary }]}>Evidence <Text style={{ color: colors.text }}>{item.evidence?.status || '—'}</Text></Text>
      </View>
      {item.error ? <Text style={[styles.small, { color: Brand.negative }]}>{item.error}</Text> : null}
    </View>
  );
}

export default function GlobalScreen() {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  const [countries, setCountries] = useState<GlobalCountry[]>([]);
  const [catalogLive, setCatalogLive] = useState(false);
  const [countryCode, setCountryCode] = useState('US');
  const [exchangeCode, setExchangeCode] = useState('NASDAQ');
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState('');
  const [scanMeta, setScanMeta] = useState('');
  const [results, setResults] = useState<GlobalAnalysis[]>([]);

  useEffect(() => {
    Promise.all([fetchGlobalCountries(), getGlobalMarketSelection()]).then(([catalog, saved]) => {
      const rows = catalog.countries;
      setCountries(rows);
      setCatalogLive(catalog.live);
      const savedCountry = rows.find((item) => item.country === saved.country);
      const savedExchange = savedCountry?.exchanges.find((item) => item.code === saved.exchange);
      if (savedCountry && savedExchange) {
        setCountryCode(savedCountry.country);
        setExchangeCode(savedExchange.code);
      } else {
        const first = rows[0];
        if (first) {
          setCountryCode(first.country);
          setExchangeCode(first.exchanges[0]?.code || '');
        }
      }
    }).finally(() => setLoadingCatalog(false));
  }, []);

  const priorityCountries = useMemo(() => {
    const rank = new Map(PRIORITY.map((code, index) => [code, index]));
    return [...countries].sort((a, b) => (rank.get(a.country) ?? 99) - (rank.get(b.country) ?? 99));
  }, [countries]);
  const selectedCountry = countries.find((item) => item.country === countryCode) || priorityCountries[0];
  const selectedExchange = selectedCountry?.exchanges.find((item) => item.code === exchangeCode) || selectedCountry?.exchanges[0];

  const persist = async (country: GlobalCountry, exchange: GlobalExchange) => {
    await setGlobalMarketSelection({
      country: country.country,
      countryName: country.name,
      exchange: exchange.code,
      exchangeLabel: exchange.label,
      mic: exchange.mic,
      currency: exchange.currencies[0] || '',
    });
  };

  const chooseCountry = async (country: GlobalCountry) => {
    const exchange = country.exchanges[0];
    setCountryCode(country.country);
    setExchangeCode(exchange?.code || '');
    setResults([]);
    setScanError('');
    setScanMeta('');
    if (exchange) await persist(country, exchange);
  };

  const chooseExchange = async (exchange: GlobalExchange) => {
    setExchangeCode(exchange.code);
    setResults([]);
    setScanError('');
    setScanMeta('');
    if (selectedCountry) await persist(selectedCountry, exchange);
  };

  const useInBiap = async () => {
    if (!selectedCountry || !selectedExchange) return;
    await persist(selectedCountry, selectedExchange);
    router.replace('/market');
  };

  const runScan = async () => {
    if (!selectedCountry || !selectedExchange) return;
    await persist(selectedCountry, selectedExchange);
    setScanning(true); setScanError(''); setResults([]); setScanMeta('');
    try {
      const response = await scanGlobalMarket(selectedCountry.country, selectedExchange.code, 10);
      setResults(Array.isArray(response.recommendations) ? response.recommendations : []);
      setScanMeta(`${response.status} • ${response.recommendationCount ?? 0} qualified • ${response.deepAnalyzed ?? 0} deep analyses`);
      if (!response.recommendations?.length) setScanError('No stock passed all evidence and confidence gates. BIAP Global will not pad the list with weaker ideas.');
    } catch (error) {
      setScanError(`Live scan is unavailable for this market right now. ${error instanceof Error ? error.message.slice(0, 160) : ''}`.trim());
    } finally { setScanning(false); }
  };

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.hero}>
          <Text style={styles.kicker}>BIAP GLOBAL • MARKET CONTEXT</Text>
          <Text style={[styles.title, { color: colors.text }]}>Choose the market. Keep the BIAP engine.</Text>
          <Text style={[styles.subtitle, { color: colors.textSecondary }]}>This selector changes the data providers used by Market, Stock Analysis, Kiasha and Portfolio. The analysis modules remain the same across countries.</Text>
          <View style={styles.badges}>
            <View style={[styles.badge, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.badgeText, { color: colors.text }]}>Same BIAP modules</Text></View>
            <View style={[styles.badge, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.badgeText, { color: colors.text }]}>Country adapters</Text></View>
            <View style={[styles.badge, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.badgeText, { color: colors.text }]}>Evidence gated</Text></View>
          </View>
        </View>

        <View style={[styles.notice, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
          <Text style={[styles.noticeTitle, { color: colors.text }]}>{catalogLive ? '● Global API connected' : '○ Preview catalog'}</Text>
          <Text style={[styles.small, { color: colors.textSecondary }]}>{catalogLive ? 'Country and exchange metadata came from the BIAP Global backend.' : 'Catalog fallback is visible, but analysis remains unavailable until the relevant live providers are configured.'}</Text>
        </View>

        <Text style={[styles.sectionTitle, { color: colors.text }]}>1. Country</Text>
        {loadingCatalog ? <ActivityIndicator color={Brand.primary} /> : (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.horizontal}>
            {priorityCountries.map((country) => {
              const active = country.country === selectedCountry?.country;
              return <Pressable key={country.country} onPress={() => { void chooseCountry(country); }} style={[styles.countryChip, { backgroundColor: active ? Brand.primary : colors.backgroundElement, borderColor: active ? Brand.primary : colors.backgroundSelected }]}>
                <Text style={[styles.countryCode, { color: active ? '#fff' : colors.text }]}>{country.country}</Text>
                <Text style={[styles.countryName, { color: active ? '#fff' : colors.textSecondary }]}>{country.name}</Text>
              </Pressable>;
            })}
          </ScrollView>
        )}

        <Text style={[styles.sectionTitle, { color: colors.text }]}>2. Exchange</Text>
        <View style={styles.wrapRow}>
          {(selectedCountry?.exchanges || []).map((exchange) => {
            const active = exchange.code === selectedExchange?.code;
            return <Pressable key={exchange.code} onPress={() => { void chooseExchange(exchange); }} style={[styles.exchangeChip, { backgroundColor: active ? `${Brand.primary}22` : colors.backgroundElement, borderColor: active ? Brand.primary : colors.backgroundSelected }]}>
              <Text style={[styles.exchangeText, { color: colors.text }]}>{exchange.label}</Text>
              <Text style={[styles.micText, { color: colors.textSecondary }]}>{exchange.mic || exchange.code} • {exchange.currencies.join('/')}</Text>
            </Pressable>;
          })}
        </View>

        <View style={[styles.sourceCard, { backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]}>
          <Text style={[styles.sourceTitle, { color: colors.text }]}>Data adapter</Text>
          <Text style={[styles.sourceLine, { color: colors.textSecondary }]}>Market: {selectedCountry?.marketProvider || 'provider adapter'}</Text>
          <Text style={[styles.sourceLine, { color: colors.textSecondary }]}>Fundamentals: {selectedCountry?.fundamentalsProvider || 'official filings'}</Text>
          <Text style={[styles.sourceLine, { color: colors.textSecondary }]}>Official evidence: {selectedCountry?.officialEvidenceSource || 'issuer/regulator filings'}</Text>
        </View>

        <Pressable disabled={!selectedExchange} onPress={() => { void useInBiap(); }} style={[styles.useButton, { borderColor: Brand.primary }]}>
          <Text style={[styles.useButtonText, { color: Brand.primary }]}>Use {selectedExchange?.label || 'this market'} in BIAP</Text>
        </Pressable>
        <Pressable disabled={scanning || !selectedExchange} onPress={runScan} style={[styles.scanButton, { backgroundColor: Brand.primary, opacity: scanning ? .65 : 1 }]}>
          {scanning ? <ActivityIndicator color="#fff" /> : <Text style={styles.scanButtonText}>Quick evidence scan (diagnostic)</Text>}
        </Pressable>
        {scanMeta ? <Text style={[styles.scanMeta, { color: colors.textSecondary }]}>{scanMeta}</Text> : null}
        {scanError ? <View style={[styles.errorBox, { borderColor: Brand.warning }]}><Text style={[styles.small, { color: colors.text }]}>{scanError}</Text></View> : null}

        {results.length ? <Text style={[styles.sectionTitle, { color: colors.text }]}>Diagnostic qualified ideas</Text> : null}
        {results.map((item, index) => <ResultCard key={`${item.ticker || 'x'}-${index}`} item={item} colors={colors} />)}

        <Text style={[styles.disclaimer, { color: colors.textSecondary }]}>The quick scan is not the main app experience. Full analysis belongs in Market → Stock Detail → Kiasha → Portfolio, using the selected country/exchange context.</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { padding: Spacing.three, paddingBottom: 120 },
  hero: { paddingVertical: Spacing.three },
  kicker: { color: Brand.primary, fontFamily: Fonts.mono, fontSize: 10, fontWeight: '800', letterSpacing: 1.2 },
  title: { fontFamily: Fonts.sans, fontSize: 28, fontWeight: '800', lineHeight: 36, marginTop: 8 },
  subtitle: { fontFamily: Fonts.sans, fontSize: 13, lineHeight: 21, marginTop: 8 },
  badges: { flexDirection: 'row', gap: 8, marginTop: 14, flexWrap: 'wrap' },
  badge: { paddingHorizontal: 10, paddingVertical: 7, borderRadius: 20 },
  badgeText: { fontFamily: Fonts.sans, fontSize: 11, fontWeight: '700' },
  notice: { borderWidth: 1, borderRadius: Radius.md, padding: Spacing.three, marginVertical: Spacing.three },
  noticeTitle: { fontFamily: Fonts.sans, fontWeight: '800', fontSize: 13, marginBottom: 4 },
  sectionTitle: { fontFamily: Fonts.sans, fontWeight: '800', fontSize: 16, marginTop: 20, marginBottom: 10 },
  horizontal: { gap: 8, paddingRight: 8 },
  countryChip: { width: 122, borderWidth: 1, borderRadius: Radius.md, padding: 12 },
  countryCode: { fontFamily: Fonts.mono, fontWeight: '900', fontSize: 16 },
  countryName: { fontFamily: Fonts.sans, fontSize: 11, marginTop: 4 },
  wrapRow: { gap: 8 },
  exchangeChip: { borderWidth: 1, borderRadius: Radius.md, padding: 12 },
  exchangeText: { fontFamily: Fonts.sans, fontSize: 13, fontWeight: '800' },
  micText: { fontFamily: Fonts.mono, fontSize: 10, marginTop: 4 },
  sourceCard: { borderWidth: 1, borderRadius: Radius.md, padding: Spacing.three, marginTop: 16 },
  sourceTitle: { fontFamily: Fonts.sans, fontWeight: '800', fontSize: 13, marginBottom: 6 },
  sourceLine: { fontFamily: Fonts.sans, fontSize: 11, lineHeight: 19 },
  useButton: { borderWidth: 1, borderRadius: Radius.md, minHeight: 50, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 14, marginTop: 16 },
  useButtonText: { fontFamily: Fonts.sans, fontWeight: '800', fontSize: 13, textAlign: 'center' },
  scanButton: { borderRadius: Radius.md, minHeight: 50, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 14, marginTop: 10 },
  scanButtonText: { color: '#fff', fontFamily: Fonts.sans, fontWeight: '800', fontSize: 13, textAlign: 'center' },
  scanMeta: { fontFamily: Fonts.mono, fontSize: 10, marginTop: 8, textAlign: 'center' },
  errorBox: { borderWidth: 1, borderRadius: Radius.md, padding: 12, marginTop: 10 },
  resultCard: { borderWidth: 1, borderRadius: Radius.md, padding: Spacing.three, marginBottom: 10 },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  resultTicker: { fontFamily: Fonts.mono, fontSize: 17, fontWeight: '900' },
  resultName: { fontFamily: Fonts.sans, fontSize: 11, marginTop: 3 },
  callPill: { borderWidth: 1, borderRadius: 20, paddingHorizontal: 9, paddingVertical: 5 },
  callText: { fontFamily: Fonts.mono, fontSize: 9, fontWeight: '900' },
  metricsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 12 },
  metric: { fontFamily: Fonts.mono, fontSize: 10 },
  small: { fontFamily: Fonts.sans, fontSize: 11, lineHeight: 18 },
  disclaimer: { fontFamily: Fonts.sans, fontSize: 10, lineHeight: 16, textAlign: 'center', marginTop: 26 },
});