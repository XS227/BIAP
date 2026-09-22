import { useCallback, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  useColorScheme,
} from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import {
  buildGlobalPortfolio,
  fetchGlobalCountries,
  GlobalAnalysis,
  GlobalCountry,
  GlobalInstrument,
  GlobalPortfolioResponse,
  scanGlobalMarket,
} from '@/lib/global-api';
import { getGlobalMarketSelection, GlobalMarketSelection } from '@/lib/global-market-selection';

type Risk = 'low' | 'medium' | 'high';
type Objective = 'growth' | 'income' | 'value' | 'capital_preservation';
type LiquidityNeed = 'low' | 'medium' | 'high';
type Scope = {
  country: string;
  countryName: string;
  exchange: string;
  exchangeLabel: string;
  currency: string;
  mic?: string | null;
};
type MarketMode = 'LIVE' | 'CACHED' | 'CATALOG' | 'ERROR';
type MarketStat = {
  key: string;
  country: string;
  label: string;
  mode: MarketMode;
  status: string;
  qualified: number;
  deep: number;
  coverage: number;
  pass: number;
  warn: number;
  block: number;
  avgScore: number | null;
  avgConfidence: number | null;
  top: string;
};
type ScanWithMode = Awaited<ReturnType<typeof scanGlobalMarket>> & {
  catalogOnly?: boolean;
  cachedMarketData?: boolean;
};

const PRIORITY = ['US', 'NO', 'SE', 'GB', 'JP', 'AU', 'DE', 'FR', 'NL', 'FI', 'DK', 'KR', 'IR'];
const AGENTS = ['fundamental', 'risk', 'forecast', 'comparison', 'quality', 'liquidity'] as const;
const MAX_INPUTS = 50;

const n = (v: number | null | undefined, d = 2) =>
  v == null || !Number.isFinite(Number(v)) ? '—' : Number(v).toLocaleString('en-US', { maximumFractionDigits: d });
const pc = (v: number | null | undefined) =>
  v == null || !Number.isFinite(Number(v)) ? '—' : `${Math.round(Number(v) * 100)}%`;
const scopeKey = (m: Scope) => `${m.country}:${m.exchange}`;
const analysisKey = (a: GlobalAnalysis) => `${a.country || ''}:${a.exchange || ''}:${a.ticker || ''}`;
const fromSelection = (s: GlobalMarketSelection): Scope => ({
  country: s.country,
  countryName: s.countryName,
  exchange: s.exchange,
  exchangeLabel: s.exchangeLabel,
  currency: s.currency,
  mic: s.mic,
});
const signal = (a: GlobalAnalysis | undefined, name: string) => a?.signals?.find((x) => x.agent === name);

function scanMode(r: ScanWithMode): MarketMode {
  if (r.catalogOnly || r.status === 'MARKET_DATA_REQUIRED') return 'CATALOG';
  if (r.cachedMarketData || r.status.startsWith('CACHED_')) return 'CACHED';
  return 'LIVE';
}

function modeLabel(mode: MarketMode) {
  if (mode === 'LIVE') return 'Live';
  if (mode === 'CACHED') return 'Cached';
  if (mode === 'CATALOG') return 'Catalog only';
  return 'Unavailable';
}

function statusLabel(stat: MarketStat) {
  if (stat.mode === 'CATALOG') return 'Instrument catalog is available; verified price/history is still pending.';
  if (stat.mode === 'ERROR') return 'This market could not be scanned.';
  if (stat.mode === 'CACHED') return 'Using a verified saved market snapshot.';
  return 'Using current verified market data.';
}

function factorText(a: GlobalAnalysis | undefined) {
  const list = a?.signals || [];
  const positives = [...list]
    .filter((x) => x.vote > 0.08 && x.confidence > 0)
    .sort((x, y) => y.vote * y.confidence - x.vote * x.confidence)
    .slice(0, 3);
  const negatives = [...list]
    .filter((x) => x.vote < -0.08 && x.confidence > 0)
    .sort((x, y) => x.vote * x.confidence - y.vote * y.confidence)
    .slice(0, 2);
  return {
    why: positives.length
      ? positives.map((x) => `${x.agent} ${x.vote >= 0 ? '+' : ''}${x.vote.toFixed(2)}`).join(' • ')
      : 'No strong positive factor',
    caution: negatives.length
      ? negatives.map((x) => `${x.agent} ${x.vote.toFixed(2)}`).join(' • ')
      : 'No material negative agent vote',
  };
}

function stat(scope: Scope, r: ScanWithMode): MarketStat {
  const deep = r.deepResults || [];
  const scored = deep.filter((x) => x.score != null && Number.isFinite(Number(x.score)));
  const confident = deep.filter((x) => x.confidence != null && Number.isFinite(Number(x.confidence)));
  const top = [...(r.recommendations || [])].sort((a, b) => Number(b.score || 0) - Number(a.score || 0))[0];
  return {
    key: scopeKey(scope),
    country: scope.country,
    label: scope.exchangeLabel,
    mode: scanMode(r),
    status: r.status || 'UNKNOWN',
    qualified: Number(r.recommendationCount || r.recommendations?.length || 0),
    deep: Number(r.deepAnalyzed || deep.length || 0),
    coverage: Number(r.screeningCoveragePct || 0),
    pass: deep.filter((x) => x.evidence?.status === 'PASS').length,
    warn: deep.filter((x) => x.evidence?.status === 'WARN').length,
    block: deep.filter((x) => x.evidence?.status === 'BLOCK').length,
    avgScore: scored.length ? scored.reduce((sum, x) => sum + Number(x.score), 0) / scored.length : null,
    avgConfidence: confident.length ? confident.reduce((sum, x) => sum + Number(x.confidence), 0) / confident.length : null,
    top: top?.ticker || '—',
  };
}

export default function GlobalPortfolioScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [current, setCurrent] = useState<GlobalMarketSelection | null>(null);
  const [countries, setCountries] = useState<GlobalCountry[]>([]);
  const [scopes, setScopes] = useState<Scope[]>([]);
  const [capital, setCapital] = useState('50000');
  const [baseCurrency, setBaseCurrency] = useState('EUR');
  const [risk, setRisk] = useState<Risk>('medium');
  const [horizon, setHorizon] = useState('5y+');
  const [objectives, setObjectives] = useState<Objective[]>(['growth', 'value']);
  const [liquidityNeed, setLiquidityNeed] = useState<LiquidityNeed>('medium');
  const [drawdownComfort, setDrawdownComfort] = useState('25');
  const [maxPositions, setMaxPositions] = useState('10');
  const [cashReserve, setCashReserve] = useState('15');
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [notes, setNotes] = useState<string[]>([]);
  const [stats, setStats] = useState<MarketStat[]>([]);
  const [result, setResult] = useState<GlobalPortfolioResponse | null>(null);
  const [candidateCount, setCandidateCount] = useState(0);

  useFocusEffect(
    useCallback(() => {
      Promise.all([getGlobalMarketSelection(), fetchGlobalCountries()]).then(([selection, catalog]) => {
        setCurrent(selection);
        setCountries(catalog.countries);
        setScopes((previous) => (previous.length ? previous : [fromSelection(selection)]));
      });
    }, []),
  );

  const options = useMemo(() => {
    const rows: Scope[] = [];
    for (const country of countries) {
      for (const exchange of country.exchanges) {
        rows.push({
          country: country.country,
          countryName: country.name,
          exchange: exchange.code,
          exchangeLabel: exchange.label,
          currency: exchange.currencies[0] || '',
          mic: exchange.mic,
        });
      }
    }
    const rank = new Map(PRIORITY.map((value, index) => [value, index]));
    const currentKey = current ? `${current.country}:${current.exchange}` : '';
    return rows.sort(
      (a, b) =>
        (scopeKey(a) === currentKey ? -1 : scopeKey(b) === currentKey ? 1 : 0) ||
        (rank.get(a.country) ?? 99) - (rank.get(b.country) ?? 99) ||
        a.exchangeLabel.localeCompare(b.exchangeLabel),
    );
  }, [countries, current]);

  const toggle = (market: Scope) =>
    setScopes((previous) => {
      const exists = previous.some((x) => scopeKey(x) === scopeKey(market));
      if (exists) return previous.length === 1 ? previous : previous.filter((x) => scopeKey(x) !== scopeKey(market));
      return previous.length >= 4 ? previous : [...previous, market];
    });

  const toggleObjective = (objective: Objective) =>
    setObjectives((previous) =>
      previous.includes(objective)
        ? previous.length === 1 ? previous : previous.filter((item) => item !== objective)
        : [...previous, objective],
    );

  const build = async () => {
    const amount = Number(capital.replace(/,/g, ''));
    const positions = Math.max(1, Math.min(30, Number(maxPositions) || 10));
    const reserve = Math.max(0, Math.min(80, Number(cashReserve) || 0));
    const drawdown = Math.max(0, Math.min(100, Number(drawdownComfort) || 0));
    if (!Number.isFinite(amount) || amount <= 0) {
      setError('Enter a positive capital amount.');
      return;
    }
    if (!/^[A-Za-z]{3}$/.test(baseCurrency.trim())) {
      setError('Base currency must be a 3-letter code such as EUR, USD or NOK.');
      return;
    }

    setLoading(true);
    setError('');
    setResult(null);
    setNotes([]);
    setStats([]);
    setCandidateCount(0);

    try {
      const perMarket = Math.min(
        50,
        Math.max(1, Math.floor(MAX_INPUTS / scopes.length)),
        Math.max(5, Math.ceil(positions * 1.5)),
      );
      const scans = await Promise.allSettled(scopes.map((scope) => scanGlobalMarket(scope.country, scope.exchange, perMarket)));
      const instruments: GlobalInstrument[] = [];
      const nextStats: MarketStat[] = [];
      const nextNotes: string[] = [];
      let usableMarkets = 0;
      let catalogOnlyMarkets = 0;
      let limitedCoverageMarkets = 0;

      scans.forEach((scanResult, index) => {
        const scope = scopes[index];
        if (scanResult.status === 'rejected') {
          nextNotes.push(`${scope.country}/${scope.exchange}: scan request failed`);
          nextStats.push({
            key: scopeKey(scope), country: scope.country, label: scope.exchangeLabel, mode: 'ERROR', status: 'SCAN_ERROR',
            qualified: 0, deep: 0, coverage: 0, pass: 0, warn: 0, block: 0, avgScore: null, avgConfidence: null, top: '—',
          });
          return;
        }

        const scan = scanResult.value as ScanWithMode;
        const marketStat = stat(scope, scan);
        nextStats.push(marketStat);

        if (marketStat.mode === 'CATALOG') {
          catalogOnlyMarkets += 1;
          nextNotes.push(`${scope.country}/${scope.exchange}: Catalog ready — verified price/history data pending`);
          return;
        }

        usableMarkets += 1;
        if (marketStat.coverage < 80) limitedCoverageMarkets += 1;
        const sourceLabel = marketStat.mode === 'CACHED' ? 'cached verified market data' : 'live market data';
        const coverageLabel = `${n(marketStat.coverage, 1)}% screening coverage`;
        const limitedLabel = marketStat.coverage < 80 ? ' • LIMITED COVERAGE' : '';
        nextNotes.push(
          `${scope.country}/${scope.exchange}: ${sourceLabel} • ${coverageLabel}${limitedLabel} • ${scan.recommendationCount ?? 0} qualified from ${scan.deepAnalyzed ?? 0} deep analyses`,
        );

        for (const item of scan.recommendations || []) {
          if (!item.ticker) continue;
          instruments.push({
            country: item.country || scope.country,
            exchange: item.exchange || scope.exchange,
            currency: item.currency || scope.currency,
            ticker: item.ticker,
            name: item.name || item.ticker,
            isin: item.isin || null,
            lei: item.lei || null,
            sector: item.company?.sector || null,
            industry: item.company?.industry || null,
            lot_size: item.company?.lot_size || null,
          });
        }
      });

      setStats(nextStats);
      setNotes(nextNotes);
      const unique = [...new Map(instruments.map((item) => [`${item.country}:${item.exchange}:${item.ticker}`, item])).values()].slice(0, MAX_INPUTS);
      setCandidateCount(unique.length);

      if (!unique.length) {
        if (usableMarkets === 0 && catalogOnlyMarkets > 0) {
          setError('Portfolio not generated yet: the selected market catalogs are available, but verified price/history snapshots have not been seeded.');
        } else if (usableMarkets > 0 && catalogOnlyMarkets > 0) {
          setError('No evidence-qualified BUY candidates were found in the currently verified market-data coverage. Catalog-only markets were excluded, and partial cached coverage is not a full-exchange scan.');
        } else if (limitedCoverageMarkets > 0) {
          setError('No evidence-qualified BUY candidates were found in the currently verified snapshots. Coverage is limited; this result is not a full-exchange scan.');
        } else {
          setError('No evidence-qualified BUY candidates were found across the selected markets with verified market data.');
        }
        return;
      }

      const countryCap = scopes.length <= 1 ? 100 : Math.max(30, Math.min(60, Math.ceil(140 / scopes.length)));
      setResult(
        await buildGlobalPortfolio(
          {
            capital: amount,
            baseCurrency: baseCurrency.trim().toUpperCase(),
            riskTolerance: risk,
            horizon: horizon.trim() || '5y',
            allowedCountries: [...new Set(scopes.map((x) => x.country))],
            allowedExchanges: [...new Set(scopes.map((x) => x.exchange))],
            maxPositionPct: Math.min(25, Math.max(3, 150 / positions)),
            maxCountryPct: countryCap,
            maxSectorPct: 35,
            minCashReservePct: reserve,
            maxPositions: positions,
            objectives,
            liquidityNeed,
            maxDrawdownComfortPct: drawdown,
          },
          unique,
        ),
      );
    } catch (exception) {
      setError(exception instanceof Error ? exception.message.slice(0, 360) : 'Portfolio Agent is unavailable.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const proposal = result?.proposal;
  const allocations = proposal?.allocations || [];
  const analysisMap = useMemo(() => new Map((result?.analyses || []).map((analysis) => [analysisKey(analysis), analysis])), [result]);
  const noRecommendationReason = useMemo(() => {
    if (!proposal || proposal.status !== 'NO_RECOMMENDATION') return '';
    if (!candidateCount) return 'No stock cleared the current Evidence/Verification and candidate filters.';
    const limited = stats.filter((market) => market.mode === 'CACHED' && market.coverage < 80);
    const blocked = stats.reduce((sum, market) => sum + market.block, 0);
    const warned = stats.reduce((sum, market) => sum + market.warn, 0);
    if (limited.length) return `The selected market coverage is still limited (${limited.map((market) => `${market.country} ${n(market.coverage, 1)}%`).join(' • ')}). The ${candidateCount} qualified scan inputs were not sufficient to create an allocation under the current profile and evidence rules.`;
    if (blocked || warned) return `${candidateCount} candidate inputs reached portfolio review, but evidence/risk checks still excluded the final allocation (${blocked} blocked • ${warned} review).`;
    return 'The qualified candidates did not satisfy the portfolio constraints together (risk, concentration, cash reserve, FX and evidence).';
  }, [candidateCount, proposal, stats]);

  const modeColor = (mode: MarketMode) => {
    if (mode === 'LIVE') return Brand.positive;
    if (mode === 'CACHED') return Brand.warning;
    if (mode === 'ERROR') return Brand.negative;
    return colors.textSecondary;
  };

  return (
    <SafeAreaView style={[s.safe, { backgroundColor: colors.background }]}>
      <ScrollView
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); void build(); }} tintColor={Brand.primary} />}
        contentContainerStyle={s.content}
      >
        <View style={s.max}>
          <View style={s.header}>
            <View style={{ flex: 1 }}>
              <Text style={[s.title, { color: colors.text }]}>Global Portfolio Agent</Text>
              <Text style={[s.sub, { color: colors.textSecondary }]}>Compare up to four exchanges, then build one evidence-gated cross-market portfolio.</Text>
            </View>
            <Pressable onPress={() => router.push('/global')} style={[s.outline, { borderColor: Brand.primary }]}>
              <Text style={s.outlineText}>Market selector</Text>
            </Pressable>
          </View>

          <View style={[s.card, { backgroundColor: colors.backgroundElement }]}>
            <Text style={s.eyebrow}>MULTI-MARKET SCOPE • MAX 4</Text>
            <Text style={[s.cardTitle, { color: colors.text }]}>Choose exchanges</Text>
            <Text style={[s.body, { color: colors.textSecondary }]}>Every selected exchange is screened with the same six scoring agents. Evidence/Verification must PASS before a stock can enter the allocation stage.</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} snapToInterval={149} decelerationRate="fast" contentContainerStyle={s.chips}>
              {options.map((market) => {
                const active = scopes.some((x) => scopeKey(x) === scopeKey(market));
                return (
                  <Pressable key={scopeKey(market)} onPress={() => toggle(market)} style={[s.chip, { backgroundColor: active ? Brand.primary : colors.backgroundSelected }]}>
                    <Text style={[s.chipCode, { color: active ? '#fff' : colors.text }]}>{market.country}</Text>
                    <Text numberOfLines={2} style={[s.chipName, { color: active ? '#fff' : colors.textSecondary }]}>{market.exchangeLabel}</Text>
                  </Pressable>
                );
              })}
            </ScrollView>
            <Text style={[s.tiny, { color: colors.textSecondary }]}>Selected {scopes.length}/4: {scopes.map((x) => `${x.country} · ${x.exchangeLabel}`).join(' • ')}</Text>
          </View>

          <Text style={[s.section, { color: colors.text }]}>Investor profile</Text>
          <View style={[s.card, { backgroundColor: colors.backgroundElement }]}>
            <View style={s.two}><Field label="Capital" value={capital} onChange={setCapital} colors={colors} /><Field label="Base currency" value={baseCurrency} onChange={setBaseCurrency} colors={colors} /></View>

            <Text style={[s.label, { color: colors.textSecondary }]}>Risk tolerance</Text>
            <View style={s.segment}>
              {(['low', 'medium', 'high'] as Risk[]).map((value) => (
                <Pressable key={value} onPress={() => setRisk(value)} style={[s.segmentBtn, { backgroundColor: risk === value ? Brand.primary : colors.backgroundSelected }]}>
                  <Text style={{ color: risk === value ? '#fff' : colors.text, fontFamily: Fonts.sans, fontWeight: '800' }}>{value}</Text>
                </Pressable>
              ))}
            </View>

            <Text style={[s.label, { color: colors.textSecondary }]}>Investment horizon</Text>
            <View style={s.optionWrap}>
              {['3m', '1y', '3y', '5y+'].map((value) => (
                <Pressable key={value} onPress={() => setHorizon(value)} style={[s.optionChip, { backgroundColor: horizon === value ? Brand.primary : colors.backgroundSelected }]}>
                  <Text style={[s.optionText, { color: horizon === value ? '#fff' : colors.text }]}>{value}</Text>
                </Pressable>
              ))}
            </View>

            <Text style={[s.label, { color: colors.textSecondary }]}>What matters most? Select one or more</Text>
            <View style={s.optionWrap}>
              {([
                ['growth', 'Growth'],
                ['income', 'Dividend income'],
                ['value', 'Value'],
                ['capital_preservation', 'Capital preservation'],
              ] as Array<[Objective, string]>).map(([value, label]) => {
                const active = objectives.includes(value);
                return (
                  <Pressable key={value} onPress={() => toggleObjective(value)} style={[s.optionChip, { backgroundColor: active ? Brand.primary : colors.backgroundSelected }]}>
                    <Text style={[s.optionText, { color: active ? '#fff' : colors.text }]}>{active ? '✓ ' : ''}{label}</Text>
                  </Pressable>
                );
              })}
            </View>

            <Text style={[s.label, { color: colors.textSecondary }]}>Need quick access to the money?</Text>
            <View style={s.segment}>
              {(['low', 'medium', 'high'] as LiquidityNeed[]).map((value) => (
                <Pressable key={value} onPress={() => setLiquidityNeed(value)} style={[s.segmentBtn, { backgroundColor: liquidityNeed === value ? Brand.primary : colors.backgroundSelected }]}>
                  <Text style={{ color: liquidityNeed === value ? '#fff' : colors.text, fontFamily: Fonts.sans, fontWeight: '800' }}>{value}</Text>
                </Pressable>
              ))}
            </View>

            <View style={s.two}>
              <Field label="Max drawdown you can tolerate (%)" value={drawdownComfort} onChange={setDrawdownComfort} colors={colors} />
              <Field label="Max positions" value={maxPositions} onChange={setMaxPositions} colors={colors} />
            </View>
            <Field label="Minimum cash reserve (%)" value={cashReserve} onChange={setCashReserve} colors={colors} />
            <Text style={[s.body, { color: colors.textSecondary }]}>These answers do not change a stock's objective Kiasha score. They only change whether that stock fits your portfolio.</Text>
          </View>

          <Pressable disabled={loading || !scopes.length} onPress={() => { void build(); }} style={[s.primary, { backgroundColor: Brand.primary, opacity: loading ? 0.65 : 1 }]}>
            {loading ? <ActivityIndicator color="#fff" /> : <Text style={s.primaryText}>Compare markets and build global portfolio</Text>}
          </Pressable>

          {result?.profileAssessment ? <View style={[s.card, { backgroundColor: colors.backgroundElement, marginTop: 10 }]}>
            <Text style={s.eyebrow}>INVESTOR FIT PROFILE</Text>
            <Text style={[s.cardTitle, { color: colors.text }]}>{String(result.profileAssessment.label || 'BALANCED').replace(/_/g, ' ')}</Text>
            <Text style={[s.body, { color: colors.textSecondary }]}>Horizon {result.profileAssessment.horizon || horizon} • Liquidity need {result.profileAssessment.liquidityNeed || liquidityNeed} • Drawdown comfort {result.profileAssessment.maxDrawdownComfortPct ?? drawdownComfort}%</Text>
            <Text style={[s.body, { color: colors.textSecondary }]}>Priorities: {(result.profileAssessment.objectives || objectives).join(' • ') || 'general'}</Text>
          </View> : null}
          {notes.length ? <View style={[s.card, { backgroundColor: colors.backgroundElement, marginTop: 8 }]}>{notes.map((note) => <Text key={note} style={[s.tiny, { color: colors.textSecondary }]}>• {note}</Text>)}</View> : null}
          {error ? <Text style={[s.error, { color: Brand.warning }]}>{error}</Text> : null}

          {stats.length ? <>
            <Text style={[s.section, { color: colors.text }]}>Market comparison</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.chips}>
              {stats.map((market) => (
                <View key={market.key} style={[s.marketCard, { backgroundColor: colors.backgroundElement }]}>
                  <View style={s.between}><Text style={s.eyebrow}>{market.country}</Text><Text style={[s.mode, { color: modeColor(market.mode) }]}>{modeLabel(market.mode)}</Text></View>
                  <Text style={[s.marketName, { color: colors.text }]}>{market.label}</Text>
                  <Text style={[s.marketLine, { color: colors.textSecondary }]}>{statusLabel(market)}</Text>
                  {market.mode === 'CATALOG' ? <Text style={[s.marketLine, { color: Brand.warning }]}>Price/history pending — excluded from portfolio</Text> : <>
                    <Text style={[s.marketLine, { color: market.coverage < 80 ? Brand.warning : colors.textSecondary }]}>Screened coverage {n(market.coverage, 1)}%{market.coverage < 80 ? ' • limited sample' : ''}</Text>
                    <Text style={[s.marketLine, { color: colors.textSecondary }]}>Qualified ideas {market.qualified} • Deep analyses {market.deep}</Text>
                    <Text style={[s.marketLine, { color: colors.textSecondary }]}>Average score {n(market.avgScore, 3)} • confidence {pc(market.avgConfidence)}</Text>
                    <Text style={[s.marketLine, { color: colors.textSecondary }]}>Evidence {market.pass} pass • {market.warn} review • {market.block} blocked</Text>
                    <Text style={[s.marketTop, { color: colors.text }]}>Highest-ranked in this scan: {market.top}</Text>
                  </>}
                </View>
              ))}
            </ScrollView>
          </> : null}

          {proposal ? <>
            <View style={[s.card, { backgroundColor: colors.backgroundElement, marginTop: 18 }]}>
              <View style={s.between}>
                <View><Text style={[s.label, { color: colors.textSecondary }]}>PROPOSAL STATUS</Text><Text style={[s.status, { color: proposal.status === 'NO_RECOMMENDATION' ? Brand.warning : Brand.positive }]}>{proposal.status ? String(proposal.status).toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()) : '—'}</Text></View>
                <View style={{ alignItems: 'flex-end' }}><Text style={[s.label, { color: colors.textSecondary }]}>PORTFOLIO INPUTS</Text><Text style={[s.big, { color: colors.text }]}>{candidateCount}</Text></View>
              </View>
              <Text style={[s.body, { color: colors.textSecondary }]}>Invested {n(proposal.invested_pct, 1)}% • Cash {n(proposal.cash_pct, 1)}% • Positions {allocations.length}</Text>
            </View>

            {proposal.status === 'NO_RECOMMENDATION' ? <View style={[s.card, { backgroundColor: colors.backgroundElement, marginTop: 10, borderWidth: 1, borderColor: Brand.warning }]}>
              <Text style={[s.cardTitle, { color: colors.text }]}>Why no portfolio was created</Text>
              <Text style={[s.body, { color: colors.textSecondary }]}>{noRecommendationReason}</Text>
              <Text style={[s.body, { color: colors.textSecondary, marginTop: 6 }]}>Try selecting 2–4 markets for broader comparison, or refresh later when verified coverage is larger. BIAP will not force an allocation just to fill the table.</Text>
            </View> : null}

            <Text style={[s.section, { color: colors.text }]}>Proposed allocations</Text>
            {!allocations.length ? <View style={[s.card, { backgroundColor: colors.backgroundElement }]}>
              <Text style={[s.cardTitle, { color: colors.text }]}>No allocation rows</Text>
              <Text style={[s.body, { color: colors.textSecondary }]}>There are no evidence-qualified positions under the current market coverage and investor constraints. This is a valid result, not an empty-screen error.</Text>
            </View> : null}
            {allocations.map((allocation, index) => {
              const analysis = analysisMap.get(`${allocation.country || ''}:${allocation.exchange || ''}:${allocation.ticker || ''}`);
              const factors = factorText(analysis);
              return (
                <View key={`${allocation.identity}-${index}`} style={[s.card, { backgroundColor: colors.backgroundElement, marginBottom: 8 }]}>
                  <View style={s.between}>
                    <View><Text style={[s.allocTicker, { color: colors.text }]}>#{index + 1} {allocation.ticker}</Text><Text style={[s.tiny, { color: colors.textSecondary }]}>{allocation.country} • {allocation.exchange} • {allocation.currency}</Text></View>
                    <Text style={[s.weight, { color: Brand.primary }]}>{n(allocation.weight_pct, 1)}%</Text>
                  </View>
                  <Text style={[s.tiny, { color: colors.textSecondary }]}>Amount {n(allocation.amount_base_currency)} {baseCurrency.toUpperCase()} • Score {n(allocation.score, 3)} • Confidence {pc(allocation.confidence)}</Text>
                  <Text style={[s.why, { color: Brand.positive }]}>Why selected: {factors.why}</Text>
                  <Text style={[s.caution, { color: factors.caution.startsWith('No material') ? colors.textSecondary : Brand.warning }]}>Remaining cautions: {factors.caution}</Text>
                </View>
              );
            })}

            {allocations.length ? <>
              <Text style={[s.section, { color: colors.text }]}>Final analytical summary</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                <View>
                  <View style={[s.row, s.rowHead, { backgroundColor: colors.backgroundSelected }]}>
                    <Cell w={145}>Stock / Market</Cell><Cell>Weight</Cell><Cell>Score</Cell><Cell>Conf.</Cell><Cell w={74}>Evidence</Cell>{AGENTS.map((agent) => <Cell key={agent} w={82}>{agent}</Cell>)}
                  </View>
                  {allocations.map((allocation, index) => {
                    const analysis = analysisMap.get(`${allocation.country || ''}:${allocation.exchange || ''}:${allocation.ticker || ''}`);
                    return (
                      <View key={`r-${index}`} style={[s.row, { backgroundColor: index % 2 ? colors.backgroundElement : colors.background }]}>
                        <View style={{ width: 145 }}><Text style={[s.rowTicker, { color: colors.text }]}>{allocation.ticker}</Text><Text style={[s.rowMeta, { color: colors.textSecondary }]}>{allocation.country}/{allocation.exchange}</Text></View>
                        <Cell>{n(allocation.weight_pct, 1)}%</Cell><Cell>{n(allocation.score, 2)}</Cell><Cell>{pc(allocation.confidence)}</Cell>
                        <Cell w={74} color={analysis?.evidence?.status === 'PASS' ? Brand.positive : Brand.warning}>{analysis?.evidence?.status || '—'}</Cell>
                        {AGENTS.map((agent) => { const value = signal(analysis, agent); return <Cell key={agent} w={82} color={value && value.vote >= 0.2 ? Brand.positive : value && value.vote <= -0.2 ? Brand.negative : colors.textSecondary}>{value ? `${value.vote >= 0 ? '+' : ''}${value.vote.toFixed(2)}` : '—'}</Cell>; })}
                      </View>
                    );
                  })}
                </View>
              </ScrollView>
            </> : null}

            {result?.fxErrors && Object.keys(result.fxErrors).length ? <Text style={[s.error, { color: Brand.warning }]}>FX unavailable: {Object.entries(result.fxErrors).map(([key, value]) => `${key}: ${value}`).join(' • ')}</Text> : null}
          </> : null}

          <View style={[s.card, { backgroundColor: colors.backgroundElement, marginTop: 18 }]}>
            <Text style={[s.cardTitle, { color: colors.text }]}>Decision support, paper first</Text>
            <Text style={[s.body, { color: colors.textSecondary }]}>Live and cached verified data are labelled separately. Cached scans may cover only a subset of an exchange, and the exact screening coverage is shown above. Catalog-only markets are never treated as investable evidence. Missing, stale or conflicting evidence can remove a stock entirely, and this build never submits live broker orders.</Text>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function Field({ label, value, onChange, colors }: { label: string; value: string; onChange: (v: string) => void; colors: typeof Colors.light | typeof Colors.dark }) {
  return <View style={{ flex: 1 }}><Text style={[s.label, { color: colors.textSecondary }]}>{label}</Text><TextInput value={value} onChangeText={onChange} autoCapitalize="characters" style={[s.input, { color: colors.text, borderColor: colors.backgroundSelected }]} /></View>;
}
function Cell({ children, w = 62, color }: { children: React.ReactNode; w?: number; color?: string }) {
  return <Text style={[s.cell, { width: w, color: color || '#9aa4b2' }]}>{children}</Text>;
}

const s = StyleSheet.create({
  safe: { flex: 1 },
  content: { paddingHorizontal: Spacing.three, paddingBottom: BottomTabInset + Spacing.six },
  max: { maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingTop: Spacing.four, paddingBottom: Spacing.three },
  title: { fontFamily: Fonts.sans, fontSize: 24, fontWeight: '900' },
  sub: { fontFamily: Fonts.sans, fontSize: 10, lineHeight: 15, marginTop: 3 },
  outline: { borderWidth: 1, borderRadius: 20, paddingHorizontal: 10, paddingVertical: 8 },
  outlineText: { color: Brand.primary, fontFamily: Fonts.sans, fontSize: 9, fontWeight: '900' },
  card: { borderRadius: Radius.lg, padding: Spacing.three },
  eyebrow: { color: Brand.primary, fontFamily: Fonts.mono, fontSize: 8, fontWeight: '900' },
  cardTitle: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '900', marginTop: 4 },
  body: { fontFamily: Fonts.sans, fontSize: 9.5, lineHeight: 15, marginTop: 5 },
  chips: { gap: 7, paddingVertical: 10, paddingRight: 6 },
  chip: { width: 142, minHeight: 74, borderRadius: Radius.md, padding: 10, justifyContent: 'center' },
  chipCode: { fontFamily: Fonts.mono, fontSize: 11, fontWeight: '900' },
  chipName: { fontFamily: Fonts.sans, fontSize: 8, lineHeight: 11, marginTop: 3 },
  tiny: { fontFamily: Fonts.mono, fontSize: 8, lineHeight: 13 },
  section: { fontFamily: Fonts.sans, fontSize: 15, fontWeight: '900', marginTop: 19, marginBottom: 8 },
  two: { flexDirection: 'row', gap: 8 },
  label: { fontFamily: Fonts.sans, fontSize: 8.5, marginTop: 7, marginBottom: 4 },
  input: { borderWidth: 1, borderRadius: Radius.md, paddingHorizontal: 10, paddingVertical: 9, fontFamily: Fonts.mono, fontSize: 11 },
  segment: { flexDirection: 'row', gap: 6 },
  segmentBtn: { flex: 1, minHeight: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  optionWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  optionChip: { minHeight: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 11 },
  optionText: { fontFamily: Fonts.sans, fontSize: 9.5, fontWeight: '800' },
  primary: { minHeight: 49, borderRadius: Radius.md, alignItems: 'center', justifyContent: 'center', marginTop: 12 },
  primaryText: { color: '#fff', fontFamily: Fonts.sans, fontSize: 11, fontWeight: '900' },
  error: { fontFamily: Fonts.sans, fontSize: 9.5, lineHeight: 15, marginTop: 9 },
  marketCard: { width: 250, minHeight: 220, borderRadius: Radius.lg, padding: Spacing.three },
  marketName: { fontFamily: Fonts.sans, fontSize: 11, fontWeight: '900', marginTop: 3, minHeight: 28 },
  marketLine: { fontFamily: Fonts.mono, fontSize: 7.8, marginTop: 5 },
  marketTop: { fontFamily: Fonts.mono, fontSize: 8.5, fontWeight: '800', marginTop: 7 },
  mode: { fontFamily: Fonts.mono, fontSize: 8, fontWeight: '900' },
  between: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  status: { fontFamily: Fonts.mono, fontSize: 11, fontWeight: '900', marginTop: 3 },
  big: { fontFamily: Fonts.mono, fontSize: 16, fontWeight: '900' },
  allocTicker: { fontFamily: Fonts.mono, fontSize: 13, fontWeight: '900' },
  weight: { fontFamily: Fonts.mono, fontSize: 15, fontWeight: '900' },
  why: { fontFamily: Fonts.sans, fontSize: 8.8, lineHeight: 14, marginTop: 10, fontWeight: '700' },
  caution: { fontFamily: Fonts.sans, fontSize: 8.5, lineHeight: 14, marginTop: 4 },
  row: { minWidth: 920, flexDirection: 'row', alignItems: 'center', minHeight: 46, paddingHorizontal: 7, marginBottom: 2 },
  rowHead: { minHeight: 36 },
  cell: { fontFamily: Fonts.mono, fontSize: 7.6, textAlign: 'center' },
  rowTicker: { fontFamily: Fonts.mono, fontSize: 9.5, fontWeight: '900' },
  rowMeta: { fontFamily: Fonts.mono, fontSize: 6.8, marginTop: 2 },
});