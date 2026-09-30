import { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View, useColorScheme } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import {
  analyzeGlobalInstrument,
  GlobalAnalysis,
  GlobalInstrument,
  IndividualCreditScoringResponse,
  scoreIndividualCredit,
} from '@/lib/global-api';
import { getSelectedGlobalCompany } from '@/lib/global-company-selection';

type Mode = 'company' | 'personal';

function valueOf(text: string) {
  const n = Number(text.replace(',', '.'));
  return Number.isFinite(n) ? n : 0;
}

function payment(principal: number, aprPct: number, months: number) {
  if (principal <= 0 || months <= 0) return 0;
  const r = Math.max(0, aprPct) / 100 / 12;
  if (!r) return principal / months;
  const f = Math.pow(1 + r, months);
  return principal * r * f / (f - 1);
}

function fmt(v: number | null | undefined, digits = 1) {
  if (v == null || !Number.isFinite(Number(v))) return '—';
  return Number(v).toLocaleString('en-US', { maximumFractionDigits: digits });
}

function pct(v: number | null | undefined, digits = 1) {
  if (v == null || !Number.isFinite(Number(v))) return '—';
  return `${(Number(v) * 100).toFixed(digits)}%`;
}

function friendly(value: string | null | undefined) {
  if (!value) return '—';
  return value.toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export default function CreditLabScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [mode, setMode] = useState<Mode>('company');

  // Company / legal-entity mode
  const [selected, setSelected] = useState<GlobalInstrument | null>(null);
  const [analysis, setAnalysis] = useState<GlobalAnalysis | null>(null);
  const [companyLoading, setCompanyLoading] = useState(false);
  const [companyError, setCompanyError] = useState('');

  const loadCompany = useCallback(async () => {
    const instrument = await getSelectedGlobalCompany();
    setSelected(instrument);
    if (!instrument) {
      setAnalysis(null);
      setCompanyError('');
      return;
    }
    setCompanyLoading(true);
    setCompanyError('');
    try {
      setAnalysis(await analyzeGlobalInstrument(instrument));
    } catch (err) {
      setAnalysis(null);
      setCompanyError(err instanceof Error ? err.message.slice(0, 320) : 'Company credit analysis is unavailable.');
    } finally {
      setCompanyLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => {
    void loadCompany();
  }, [loadCompany]));

  const company = analysis?.company;
  const distress = analysis?.distress;
  const credit = analysis?.creditScoring;
  const factors = credit?.factors ? Object.entries(credit.factors) : [];
  const missing = credit?.factors_missing ? Object.entries(credit.factors_missing) : [];

  // Personal / natural-person mode
  const [income, setIncome] = useState('5000');
  const [living, setLiving] = useState('2200');
  const [existing, setExisting] = useState('300');
  const [amount, setAmount] = useState('30000');
  const [months, setMonths] = useState('60');
  const [apr, setApr] = useState('6');
  const [asset, setAsset] = useState('40000');
  const [bureau, setBureau] = useState(false);
  const [arrears, setArrears] = useState(false);
  const [bankVerified, setBankVerified] = useState(false);

  const [paymentHistory, setPaymentHistory] = useState('97');
  const [utilization, setUtilization] = useState('30');
  const [historyYears, setHistoryYears] = useState('5');
  const [dti, setDti] = useState('36');
  const [activeAccounts, setActiveAccounts] = useState('4');
  const [bouncedChecks, setBouncedChecks] = useState('0');
  const [pastDefaults, setPastDefaults] = useState('0');
  const [agent10, setAgent10] = useState<IndividualCreditScoringResponse | null>(null);
  const [agent10Busy, setAgent10Busy] = useState(false);
  const [agent10Error, setAgent10Error] = useState('');

  const calc = useMemo(() => {
    const inc = valueOf(income);
    const liv = valueOf(living);
    const old = valueOf(existing);
    const principal = valueOf(amount);
    const term = Math.max(1, Math.round(valueOf(months)));
    const rate = valueOf(apr);
    const assetValue = valueOf(asset);
    const p = payment(principal, rate, term);
    const stress = payment(principal, rate + 3, term);
    return {
      p,
      residual: inc - liv - old - p,
      stressResidual: inc - liv - old - stress,
      pti: inc > 0 ? p / inc * 100 : 0,
      dsr: inc > 0 ? (old + p) / inc * 100 : 0,
      ltv: assetValue > 0 ? principal / assetValue * 100 : null,
    };
  }, [income, living, existing, amount, months, apr, asset]);

  const runAgent10 = async () => {
    try {
      setAgent10Busy(true);
      setAgent10Error('');
      const response = await scoreIndividualCredit({
        paymentOnTimeRatio: valueOf(paymentHistory) / 100,
        creditUtilization: valueOf(utilization) / 100,
        creditHistoryYears: valueOf(historyYears),
        debtToIncome: valueOf(dti) / 100,
        activeAccounts: valueOf(activeAccounts),
        bouncedChecks: valueOf(bouncedChecks),
        pastDefaults: valueOf(pastDefaults),
      });
      setAgent10(response);
    } catch (err) {
      setAgent10(null);
      setAgent10Error(err instanceof Error ? err.message.slice(0, 220) : 'Agent 10 is unavailable.');
    } finally {
      setAgent10Busy(false);
    }
  };

  const scenarioFields = [
    ['Monthly net income', income, setIncome],
    ['Essential / fixed living expenses', living, setLiving],
    ['Existing monthly debt payments', existing, setExisting],
    ['Requested credit', amount, setAmount],
    ['Term (months)', months, setMonths],
    ['APR %', apr, setApr],
    ['Vehicle / asset value', asset, setAsset],
  ] as const;

  const scorecardFields = [
    ['Payments on time %', paymentHistory, setPaymentHistory],
    ['Credit utilization %', utilization, setUtilization],
    ['Credit history years', historyYears, setHistoryYears],
    ['Debt-to-income %', dti, setDti],
    ['Active accounts', activeAccounts, setActiveAccounts],
    ['Bounced checks', bouncedChecks, setBouncedChecks],
    ['Past defaults', pastDefaults, setPastDefaults],
  ] as const;

  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
    <ScrollView contentContainerStyle={styles.content}>
      <View style={styles.max}>
        <View style={styles.header}>
          <Pressable onPress={() => router.back()} style={[styles.back, { backgroundColor: colors.backgroundElement }]}>
            <Text style={[styles.backText, { color: colors.text }]}>← Back</Text>
          </Pressable>
          <View style={{ flex: 1 }}>
            <Text style={[styles.title, { color: colors.text }]}>Credit Analysis</Text>
            <Text style={[styles.sub, { color: colors.textSecondary }]}>Agent 9 + Agent 10 for companies, and a separate Agent 10 model for natural persons.</Text>
          </View>
        </View>

        <View style={[styles.tabs, { backgroundColor: colors.backgroundElement }]}>
          <Pressable onPress={() => setMode('company')} style={[styles.tab, mode === 'company' && { backgroundColor: Brand.primary }]}>
            <Text style={[styles.tabText, { color: mode === 'company' ? '#fff' : colors.textSecondary }]}>🏢 Company</Text>
          </Pressable>
          <Pressable onPress={() => setMode('personal')} style={[styles.tab, mode === 'personal' && { backgroundColor: Brand.primary }]}>
            <Text style={[styles.tabText, { color: mode === 'personal' ? '#fff' : colors.textSecondary }]}>👤 Personal</Text>
          </Pressable>
        </View>

        {mode === 'company' ? <>
          {!selected ? <View style={[styles.emptyCard, { backgroundColor: colors.backgroundElement, borderColor: Brand.warning }]}>
            <Text style={[styles.cardTitle, { color: colors.text }]}>Select a company first</Text>
            <Text style={[styles.body, { color: colors.textSecondary }]}>Choose any supported listed company in Market. Credit Analysis will then load the same verified company data and automatically run Agent 9 and Agent 10.</Text>
            <Pressable onPress={() => router.push('/market')} style={[styles.action, { backgroundColor: Brand.primary }]}>
              <Text style={styles.actionText}>Open Market</Text>
            </Pressable>
          </View> : <>
            <View style={[styles.companyHero, { backgroundColor: colors.backgroundElement }]}>
              <View style={{ flex: 1 }}>
                <Text style={[styles.companyTicker, { color: colors.text }]}>{selected.ticker}</Text>
                <Text style={[styles.companyName, { color: colors.textSecondary }]}>{analysis?.name || selected.name}</Text>
                <Text style={[styles.meta, { color: colors.textSecondary }]}>{selected.country} • {selected.exchange} • {analysis?.currency || selected.currency}</Text>
              </View>
              <Pressable onPress={() => router.push('/market')} style={[styles.outlineAction, { borderColor: Brand.primary }]}>
                <Text style={[styles.outlineActionText, { color: Brand.primary }]}>Change</Text>
              </Pressable>
            </View>

            {companyLoading ? <View style={styles.loadingBox}><ActivityIndicator color={Brand.primary} /><Text style={[styles.body, { color: colors.textSecondary }]}>Running Agent 9 + Agent 10 on {selected.ticker}…</Text></View> : null}
            {companyError ? <View style={[styles.notice, { borderColor: Brand.negative }]}><Text style={[styles.body, { color: Brand.negative }]}>{companyError}</Text><Pressable onPress={() => void loadCompany()} style={[styles.action, { backgroundColor: Brand.primary }]}><Text style={styles.actionText}>Retry</Text></Pressable></View> : null}

            {!companyLoading && analysis ? <>
              <Text style={[styles.section, { color: colors.text }]}>Corporate credit rating</Text>
              <View style={[styles.ratingCard, { backgroundColor: colors.backgroundElement, borderColor: credit?.indicated_rating_sp ? Brand.positive : Brand.warning }]}>
                <Text style={[styles.agentLabel, { color: Brand.primary }]}>AGENT 10 · LEGAL ENTITY</Text>
                {credit?.indicated_rating_sp ? <>
                  <View style={styles.ratingRow}>
                    <View><Text style={[styles.ratingValue, { color: colors.text }]}>{credit.indicated_rating_sp}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>S&P equivalent</Text></View>
                    <View><Text style={[styles.ratingValue, { color: colors.text }]}>{credit.indicated_rating_moodys || '—'}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>Moody's grid</Text></View>
                  </View>
                  <View style={styles.ratingRow}>
                    <View style={{ flex: 1 }}><Text style={[styles.metricValue, { color: colors.text }]}>{credit.pd_1y == null ? '—' : pct(credit.pd_1y, 2)}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>1-year historical PD mapping</Text></View>
                    <View style={{ flex: 1 }}><Text style={[styles.metricValue, { color: colors.text }]}>{credit.weight_coverage == null ? '—' : pct(credit.weight_coverage, 0)}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>Grid coverage</Text></View>
                  </View>
                  <Text style={[styles.body, { color: credit.investment_grade ? Brand.positive : Brand.warning }]}>{credit.investment_grade ? 'Indicated investment-grade band' : 'Indicated non-investment-grade band'}</Text>
                </> : <>
                  <Text style={[styles.cardTitle, { color: Brand.warning }]}>Rating not produced yet</Text>
                  <Text style={[styles.body, { color: colors.textSecondary }]}>{credit?.status || 'Agent 10 does not have enough verified company inputs to produce a rating.'}</Text>
                  {credit?.weight_coverage != null ? <Text style={[styles.body, { color: colors.textSecondary }]}>Available grid coverage: {pct(credit.weight_coverage, 0)}</Text> : null}
                </>}
                <Text style={[styles.disclaimerInline, { color: colors.textSecondary }]}>Report-only synthetic credit scoring from canonical Agent 10. It is not an agency-issued rating and does not alter the stock decision. The investment Evidence gate is separate from this credit calculation.</Text>
              </View>

              <Text style={[styles.section, { color: colors.text }]}>Agent 9 cross-check</Text>
              <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
                <View style={styles.dataRow}><Text style={[styles.dataLabel, { color: colors.textSecondary }]}>Distress status</Text><Text style={[styles.dataValue, { color: colors.text }]}>{friendly(distress?.status)}</Text></View>
                <View style={styles.dataRow}><Text style={[styles.dataLabel, { color: colors.textSecondary }]}>Synthetic credit band</Text><Text style={[styles.dataValue, { color: colors.text }]}>{distress?.synthetic_credit_band || '—'}</Text></View>
                <View style={styles.dataRow}><Text style={[styles.dataLabel, { color: colors.textSecondary }]}>Zmijewski P(distress)</Text><Text style={[styles.dataValue, { color: colors.text }]}>{distress?.distress_probability == null ? '—' : pct(distress.distress_probability, 1)}</Text></View>
                <View style={styles.dataRow}><Text style={[styles.dataLabel, { color: colors.textSecondary }]}>Altman Z''</Text><Text style={[styles.dataValue, { color: colors.text }]}>{fmt(distress?.altman_z_double_prime, 2)}</Text></View>
                <View style={styles.dataRow}><Text style={[styles.dataLabel, { color: colors.textSecondary }]}>Interest coverage</Text><Text style={[styles.dataValue, { color: colors.text }]}>{distress?.interest_coverage == null ? '—' : `${fmt(distress.interest_coverage, 2)}x`}</Text></View>
              </View>

              <Text style={[styles.section, { color: colors.text }]}>Agent 10 factor grid</Text>
              <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
                {factors.length ? factors.map(([key, factor]) => <View key={key} style={styles.factorRow}>
                  <View style={{ flex: 1 }}><Text style={[styles.dataLabel, { color: colors.text }]}>{friendly(key)}</Text><Text style={[styles.factorMeta, { color: colors.textSecondary }]}>{factor.note || `weight ${Math.round(Number(factor.weight || 0) * 100)}%`}</Text></View>
                  <View style={{ alignItems: 'flex-end' }}><Text style={[styles.dataValue, { color: colors.text }]}>{factor.value == null ? '—' : typeof factor.value === 'number' ? fmt(factor.value, 2) : String(factor.value)}</Text><Text style={[styles.factorCategory, { color: Brand.primary }]}>{factor.category || '—'}</Text></View>
                </View>) : <Text style={[styles.body, { color: colors.textSecondary }]}>No Agent 10 factors could be scored from the currently available company data.</Text>}
                {missing.length ? <View style={[styles.missingBox, { borderColor: Brand.warning }]}>
                  <Text style={[styles.cardTitle, { color: Brand.warning }]}>Missing — not guessed</Text>
                  {missing.map(([key, why]) => <Text key={key} style={[styles.body, { color: colors.textSecondary }]}>• {friendly(key)}: {why}</Text>)}
                </View> : null}
              </View>

              <Text style={[styles.section, { color: colors.text }]}>Company data used</Text>
              <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
                {[
                  ['Price', company?.price == null ? '—' : `${fmt(company.price, 2)} ${analysis.currency || ''}`],
                  ['Sector', company?.sector || '—'],
                  ['Revenue', fmt(company?.revenue, 0)],
                  ['EBITDA', fmt(company?.ebitda, 0)],
                  ['Total debt', fmt(company?.total_debt, 0)],
                  ['Interest expense', fmt(company?.interest_expense, 0)],
                  ['Free cash flow', fmt(company?.free_cash_flow, 0)],
                  ['Current assets', fmt(company?.current_assets, 0)],
                  ['Current liabilities', fmt(company?.current_liabilities, 0)],
                  ['Investment evidence gate', analysis.evidence?.status || '—'],
                ].map(([label, value]) => <View key={String(label)} style={styles.dataRow}><Text style={[styles.dataLabel, { color: colors.textSecondary }]}>{label}</Text><Text style={[styles.dataValue, { color: colors.text }]}>{value}</Text></View>)}
              </View>

              <Pressable onPress={() => router.push({ pathname: '/stock/[code]', params: { code: selected.ticker, country: selected.country, exchange: selected.exchange, currency: selected.currency, name: selected.name, isin: selected.isin || '', lei: selected.lei || '' } } as never)} style={[styles.action, { backgroundColor: Brand.primary }]}>
                <Text style={styles.actionText}>Open full company analysis</Text>
              </Pressable>
            </> : null}
          </>}
        </> : <>
          <View style={[styles.notice, { borderColor: Brand.warning }]}>
            <Text style={[styles.noticeTitle, { color: Brand.warning }]}>Personal / natural person</Text>
            <Text style={[styles.body, { color: colors.textSecondary }]}>Separate hypothetical training mode. Agent 10 returns a score, illustrative PD and reason codes; it never returns an approve/decline credit decision.</Text>
          </View>

          <Text style={[styles.section, { color: colors.text }]}>Agent 10 scorecard inputs</Text>
          {scorecardFields.map(([label, v, setter]) => <View key={label} style={styles.field}><Text style={[styles.label, { color: colors.textSecondary }]}>{label}</Text><TextInput value={v} onChangeText={setter} keyboardType="decimal-pad" style={[styles.input, { color: colors.text, backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]} /></View>)}
          <Pressable onPress={() => void runAgent10()} disabled={agent10Busy} style={[styles.action, { backgroundColor: Brand.primary, opacity: agent10Busy ? .65 : 1 }]}>
            <Text style={styles.actionText}>{agent10Busy ? 'Running Agent 10…' : 'Calculate Agent 10'}</Text>
          </Pressable>
          {agent10Error ? <Text style={[styles.flag, { color: Brand.negative }]}>{agent10Error}</Text> : null}
          {agent10?.creditScoring ? <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
            <View style={styles.ratingRow}><View><Text style={[styles.ratingValue, { color: colors.text }]}>{agent10.creditScoring.score ?? '—'}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>Credit score</Text></View><View><Text style={[styles.ratingValue, { color: colors.text }]}>{agent10.creditScoring.pd == null ? '—' : pct(agent10.creditScoring.pd, 2)}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>Illustrative PD</Text></View></View>
            <Text style={[styles.body, { color: colors.textSecondary }]}>Risk band: {agent10.creditScoring.risk_band || '—'}</Text>
            {agent10.creditScoring.reason_codes?.length ? <Text style={[styles.flag, { color: Brand.warning }]}>Reason codes: {agent10.creditScoring.reason_codes.join(' • ')}</Text> : null}
          </View> : null}

          <Text style={[styles.section, { color: colors.text }]}>Affordability scenario</Text>
          {scenarioFields.map(([label, v, setter]) => <View key={label} style={styles.field}><Text style={[styles.label, { color: colors.textSecondary }]}>{label}</Text><TextInput value={v} onChangeText={setter} keyboardType="decimal-pad" style={[styles.input, { color: colors.text, backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]} /></View>)}

          <Text style={[styles.section, { color: colors.text }]}>Evidence checklist</Text>
          {[
            ['Credit bureau / BKR checked', bureau, setBureau],
            ['Bureau shows arrears', arrears, setArrears],
            ['Bank statement / open-banking evidence verified', bankVerified, setBankVerified],
          ].map(([label, v, setter]: any) => <Pressable key={label} onPress={() => setter(!v)} style={[styles.toggle, { backgroundColor: colors.backgroundElement, borderColor: v ? Brand.positive : colors.backgroundSelected }]}><Text style={[styles.toggleText, { color: colors.text }]}>{label}</Text><Text style={[styles.toggleState, { color: v ? Brand.positive : colors.textSecondary }]}>{v ? 'YES' : 'NO'}</Text></Pressable>)}

          <Text style={[styles.section, { color: colors.text }]}>Calculated underwriting indicators</Text>
          <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
            {[
              ['Estimated monthly payment', fmt(calc.p, 2)],
              ['Payment / income (PTI)', `${fmt(calc.pti)}%`],
              ['Total debt service / income', `${fmt(calc.dsr)}%`],
              ['Residual income', fmt(calc.residual, 2)],
              ['Residual at APR +3pp stress', fmt(calc.stressResidual, 2)],
              ['Loan-to-value (LTV)', calc.ltv == null ? '—' : `${fmt(calc.ltv)}%`],
            ].map(([label, value]) => <View key={String(label)} style={styles.metric}><Text style={[styles.metricValue, { color: colors.text }]}>{value}</Text><Text style={[styles.metricLabel, { color: colors.textSecondary }]}>{label}</Text></View>)}
          </View>
        </>}
      </View>
    </ScrollView>
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { paddingHorizontal: Spacing.three, paddingBottom: BottomTabInset + Spacing.six },
  max: { width: '100%', maxWidth: MaxContentWidth, alignSelf: 'center' },
  header: { flexDirection: 'row', gap: 12, paddingVertical: Spacing.three, alignItems: 'flex-start' },
  back: { paddingHorizontal: 11, paddingVertical: 8, borderRadius: 18 },
  backText: { fontFamily: Fonts.sans, fontSize: 10, fontWeight: '800' },
  title: { fontFamily: Fonts.sans, fontSize: 22, fontWeight: '900' },
  sub: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 16, marginTop: 4 },
  tabs: { flexDirection: 'row', borderRadius: Radius.md, padding: 4, marginBottom: 12 },
  tab: { flex: 1, minHeight: 42, borderRadius: Radius.sm, alignItems: 'center', justifyContent: 'center' },
  tabText: { fontFamily: Fonts.sans, fontSize: 11, fontWeight: '900' },
  companyHero: { borderRadius: Radius.lg, padding: Spacing.three, flexDirection: 'row', alignItems: 'center', gap: 12 },
  companyTicker: { fontFamily: Fonts.mono, fontSize: 24, fontWeight: '900' },
  companyName: { fontFamily: Fonts.sans, fontSize: 11.5, marginTop: 3 },
  meta: { fontFamily: Fonts.mono, fontSize: 9, marginTop: 5 },
  outlineAction: { borderWidth: 1, borderRadius: 18, paddingHorizontal: 12, paddingVertical: 8 },
  outlineActionText: { fontFamily: Fonts.sans, fontSize: 10, fontWeight: '900' },
  emptyCard: { borderWidth: 1, borderRadius: Radius.lg, padding: Spacing.four },
  loadingBox: { alignItems: 'center', paddingVertical: 24, gap: 8 },
  notice: { borderWidth: 1, borderRadius: Radius.md, padding: Spacing.three, marginBottom: 10 },
  noticeTitle: { fontFamily: Fonts.sans, fontSize: 12, fontWeight: '900' },
  section: { fontFamily: Fonts.sans, fontSize: 16, fontWeight: '900', marginTop: 20, marginBottom: 8 },
  ratingCard: { borderWidth: 1, borderRadius: Radius.lg, padding: Spacing.four },
  agentLabel: { fontFamily: Fonts.mono, fontSize: 9, fontWeight: '900', marginBottom: 10 },
  ratingRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 20, marginBottom: 12 },
  ratingValue: { fontFamily: Fonts.mono, fontSize: 28, fontWeight: '900' },
  card: { borderRadius: Radius.lg, padding: Spacing.three, marginBottom: 10 },
  cardTitle: { fontFamily: Fonts.sans, fontSize: 13, fontWeight: '900' },
  body: { fontFamily: Fonts.sans, fontSize: 10.5, lineHeight: 17, marginTop: 5 },
  disclaimerInline: { fontFamily: Fonts.sans, fontSize: 9, lineHeight: 14, marginTop: 10 },
  dataRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 12, paddingVertical: 9, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#ffffff18' },
  dataLabel: { fontFamily: Fonts.sans, fontSize: 10, flex: 1 },
  dataValue: { fontFamily: Fonts.mono, fontSize: 10, fontWeight: '800', flex: 1, textAlign: 'right' },
  factorRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 12, paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#ffffff18' },
  factorMeta: { fontFamily: Fonts.sans, fontSize: 8.5, lineHeight: 13, marginTop: 2 },
  factorCategory: { fontFamily: Fonts.mono, fontSize: 10, fontWeight: '900', marginTop: 2 },
  missingBox: { borderWidth: 1, borderRadius: Radius.md, padding: 10, marginTop: 12 },
  field: { marginBottom: 8 },
  label: { fontFamily: Fonts.sans, fontSize: 9.5, marginBottom: 5 },
  input: { borderWidth: 1, borderRadius: Radius.md, minHeight: 46, paddingHorizontal: 12, fontFamily: Fonts.mono, fontSize: 13 },
  toggle: { borderWidth: 1, borderRadius: Radius.md, minHeight: 46, paddingHorizontal: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 },
  toggleText: { fontFamily: Fonts.sans, fontSize: 10.5, fontWeight: '700', flex: 1 },
  toggleState: { fontFamily: Fonts.mono, fontSize: 10, fontWeight: '900' },
  metric: { paddingVertical: 9, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#ffffff22' },
  metricValue: { fontFamily: Fonts.mono, fontSize: 14, fontWeight: '900' },
  metricLabel: { fontFamily: Fonts.sans, fontSize: 9, marginTop: 3 },
  flag: { fontFamily: Fonts.sans, fontSize: 10, lineHeight: 17, marginTop: 8 },
  action: { minHeight: 46, borderRadius: Radius.md, alignItems: 'center', justifyContent: 'center', marginTop: 12 },
  actionText: { color: '#fff', fontFamily: Fonts.sans, fontSize: 11, fontWeight: '900' },
});
