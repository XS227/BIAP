import { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { Brand, type ThemeColors } from '@/constants/theme';
import {
  fetchAccuracyStock, fetchPerformanceAssessment, fetchRiskAssessment, sessionGlobalStatus,
  type AgentResult, type GlobalAccuracyStock, type GlobalInstrument, type GlobalPerformanceAssessment, type GlobalRiskAssessment,
} from '@/lib/global-api';
import { tr, statusLabel, type Lang } from '@/lib/agent-i18n';
import { agentFlags, frac, isMarketWide, num, ohlsonProvisional, percentileText, performanceChip, riskChip, scopeLine, signedPct, toFa, type AgentFlags } from '@/lib/agent-format';
import { useAgentLang } from '@/lib/agent-lang';
import { AgentCard, Bullets, Expandable, LevelChip, Loading, Row, Tag, TONE_COLOR, Unavailable, rtl } from './agent-ui';

const PCT_METRICS = new Set(['roa', 'roe', 'operating_margin', 'accrual_ratio']);

type Load<T> = { state: 'idle' } | { state: 'loading' } | AgentResult<T>;

function useAgent<T>(enabled: boolean, start: boolean, fetcher: () => Promise<AgentResult<T>>, onDone?: () => void) {
  const [res, setRes] = useState<Load<T>>({ state: 'idle' });
  const run = useCallback(() => {
    setRes({ state: 'loading' });
    fetcher().then((r) => { setRes(r); onDone?.(); }).catch(() => { setRes({ state: 'unavailable' }); onDone?.(); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetcher]);
  useEffect(() => { if (enabled && start && res.state === 'idle') run(); }, [enabled, start, res.state, run]);
  return [res, run] as const;
}

function sevColor(sev: number) { return sev >= 3 ? TONE_COLOR.severe : sev === 2 ? TONE_COLOR.negative : sev === 1 ? TONE_COLOR.warning : TONE_COLOR.positive; }

export function RiskAgentSection({ instrument, colors, start, onDone }: { instrument: GlobalInstrument; colors: ThemeColors; start: boolean; onDone: () => void }) {
  const [lang, setLang] = useAgentLang();
  const fetcher = useCallback(() => fetchRiskAssessment(instrument), [instrument]);
  const [res, retry] = useAgent<GlobalRiskAssessment>(true, start, fetcher, onDone);
  if (res.state === 'idle' || (res.state === 'off')) return null;
  const a = res.state === 'ok' ? res.data : null;
  const chip = a ? riskChip(lang, a) : null;
  return <AgentCard title={tr(lang, 'riskTitle')} lang={lang} onLang={setLang} colors={colors} right={chip ? <LevelChip testID="risk-chip" text={chip.text} tone={chip.tone} /> : null}>
    <Text style={[styleBody(colors), rtl(lang)]}>{tr(lang, 'riskExplain')}</Text>
    {res.state === 'loading' ? <Loading lang={lang} colors={colors} /> : null}
    {res.state === 'unavailable' ? <Unavailable lang={lang} colors={colors} onRetry={retry} /> : null}
    {a ? <>
      <Text style={[styleSub(colors), rtl(lang)]}>{statusLabel(lang, a.status)}{ohlsonProvisional(a.signals) ? ` · ${tr(lang, 'provisional')}: Ohlson` : ''}</Text>
      <Bullets lines={a.reasons || []} colors={colors} lang={lang} />
      {lang === 'fa' ? <Text style={[styleSub(colors), rtl(lang)]}>{tr(lang, 'reasonsEnglish')}</Text> : null}
      <Expandable lang={lang} colors={colors} testID="risk-data">
        {(a.signals || []).map((sg) => {
          const unavailable = !sg.available;
          const isBeneish = sg.id === 'beneish';
          const value = unavailable ? (isBeneish ? tr(lang, 'beneishNA') : '—') : num(lang, sg.value, 3);
          const inputs = Object.entries(sg.inputs || {}).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${typeof v === 'number' ? num(lang, v, 3) : v}`).join(' · ');
          const needs = (sg.missing || []).length && !isBeneish ? `${tr(lang, 'needs')}: ${sg.missing.join(', ')}` : '';
          return <View key={sg.id}>
            <Row label={`${sg.name}${sg.id === 'ohlson' && sg.provisional ? ` (${tr(lang, 'provisional')})` : ''}`} value={sg.band ? `${value} · ${sg.band}` : value} colors={colors} lang={lang}
              dot={unavailable ? TONE_COLOR.muted : sevColor(sg.severity)} sub={[sg.reason, inputs, needs, sg.caveat || ''].filter(Boolean).join('\n')} />
          </View>;
        })}
        {a.unitScale?.status ? <Text style={[styleSub(colors), rtl(lang)]}>{tr(lang, 'unitScale')}: {a.unitScale.status}</Text> : null}
        {ohlsonProvisional(a.signals) ? <View style={{ marginTop: 6 }}><Tag text={tr(lang, 'provisionalOhlson')} /></View> : null}
        {a.leases?.applied && a.leases.lease_liabilities != null ? <Text style={[styleSub(colors), rtl(lang)]}>{tr(lang, 'leaseNote')} {num(lang, a.leases.lease_liabilities, 0)}</Text> : null}
        {a.asOf?.filingPeriodEnd ? <Text style={[styleSub(colors), rtl(lang)]}>{a.asOf.filingPeriodEnd}</Text> : null}
      </Expandable>
      {a.disclaimer ? <Text style={[styleSub(colors), rtl(lang)]}>{a.disclaimer}</Text> : null}
    </> : null}
  </AgentCard>;
}

export function PerformanceAgentSection({ instrument, colors, start, onDone }: { instrument: GlobalInstrument; colors: ThemeColors; start: boolean; onDone: () => void }) {
  const [lang, setLang] = useAgentLang();
  const fetcher = useCallback(() => fetchPerformanceAssessment(instrument), [instrument]);
  const [res, retry] = useAgent<GlobalPerformanceAssessment>(true, start, fetcher, onDone);
  if (res.state === 'idle' || (res.state === 'off')) return null;
  const a = res.state === 'ok' ? res.data : null;
  const rel = a?.relative || null;
  const abs = a ? performanceChip(lang, a.absoluteLevel, a.status) : null;
  const relChip = a && rel && rel.level ? performanceChip(lang, rel.level) : null;
  const m = a?.metrics;
  const D = m?.dupont;
  return <AgentCard title={tr(lang, 'performanceTitle')} lang={lang} onLang={setLang} colors={colors}>
    {res.state === 'loading' ? <Loading lang={lang} colors={colors} /> : null}
    {res.state === 'unavailable' ? <Unavailable lang={lang} colors={colors} onRetry={retry} /> : null}
    {a ? <>
      <View style={{ flexDirection: lang === 'fa' ? 'row-reverse' : 'row', gap: 14, marginTop: 8, flexWrap: 'wrap' }}>
        <View><Text style={[styleSub(colors), rtl(lang)]}>{tr(lang, 'absolute')}</Text><LevelChip testID="perf-abs-chip" text={abs!.text} tone={abs!.tone} arrowDown={abs!.arrowDown} /></View>
        <View><Text style={[styleSub(colors), rtl(lang)]}>{tr(lang, isMarketWide(rel?.scope) ? 'vsMarket' : 'vsSector')}</Text>
          {relChip ? <LevelChip testID="perf-rel-chip" text={relChip.text} tone={relChip.tone} arrowDown={relChip.arrowDown} /> : <LevelChip testID="perf-rel-chip" text={abs!.text} tone="muted" />}</View>
      </View>
      {rel?.level ? <Text style={[styleSub(colors), rtl(lang)]}>{scopeLine(lang, rel)}{rel.compositePercentile != null ? ` · ${percentileText(lang, rel.compositePercentile)}` : ''}</Text> : null}
      {isMarketWide(rel?.scope) ? <Text style={[styleSub(colors), rtl(lang), { color: Brand.warning }]}>{tr(lang, 'marketWide')}</Text> : null}
      <Bullets lines={[...(a.reasons || []), ...(rel?.reasons || [])]} colors={colors} lang={lang} />
      {rel && !rel.level ? <Text style={[styleSub(colors), rtl(lang)]}>{rel.status}</Text> : null}
      {lang === 'fa' ? <Text style={[styleSub(colors), rtl(lang)]}>{tr(lang, 'reasonsEnglish')}</Text> : null}
      <Expandable lang={lang} colors={colors} testID="perf-data">
        <Row label="ROA" value={frac(lang, m?.roa)} colors={colors} lang={lang} />
        <Row label="ROE" value={frac(lang, m?.roe)} colors={colors} lang={lang} />
        {D ? <Row label={tr(lang, 'dupont')} value={`${frac(lang, D.net_margin)} × ${num(lang, D.asset_turnover, 2)} × ${num(lang, D.equity_multiplier, 2)} = ${frac(lang, D.roe_from_parts)}`} colors={colors} lang={lang} /> : null}
        <Row label={`${tr(lang, 'margins')}: gross / operating / EBITDA / net`} value={[m?.margins?.gross, m?.margins?.operating, m?.margins?.ebitda, m?.margins?.net].map((x) => frac(lang, x)).join(' / ')} colors={colors} lang={lang} />
        <Row label={`${tr(lang, 'growth')}: revenue / net income`} value={`${frac(lang, m?.growth?.revenue_yoy)} / ${frac(lang, m?.growth?.net_income_yoy)}`} colors={colors} lang={lang} />
        <Row label={`${tr(lang, 'cashQuality')}: CFO/NI · accrual · FCF margin`} value={`${num(lang, m?.cash_quality?.cfo_to_net_income, 2)} · ${frac(lang, m?.cash_quality?.accrual_ratio)} · ${frac(lang, m?.cash_quality?.fcf_margin)}`} colors={colors} lang={lang} />
        {(rel?.metrics || []).map((mm) => <Row key={mm.id} label={`${mm.name} (${tr(lang, 'percentile')})`} value={`${PCT_METRICS.has(mm.id) ? frac(lang, mm.value) : num(lang, mm.value, 2)} · ${percentileText(lang, mm.percentile)}${mm.peers ? ` · ${num(lang, mm.peers, 0)} ${tr(lang, 'peers')}` : ''}`} colors={colors} lang={lang} />)}
        {(a.notes || []).map((n) => <Text key={n} style={[styleSub(colors), rtl(lang)]}>{n}</Text>)}
      </Expandable>
      {a.disclaimer ? <Text style={[styleSub(colors), rtl(lang)]}>{a.disclaimer}</Text> : null}
    </> : null}
  </AgentCard>;
}

export function StockRecordSection({ instrument, colors }: { instrument: GlobalInstrument; colors: ThemeColors }) {
  const [lang, setLang] = useAgentLang();
  const fetcher = useCallback(() => fetchAccuracyStock(instrument), [instrument]);
  const [res, retry] = useAgent<GlobalAccuracyStock>(true, true, fetcher);
  if (res.state === 'idle' || (res.state === 'off')) return null;
  const a = res.state === 'ok' ? res.data : null;
  if (a && !a.n) return null;                        // hidden when the stock has no decision record
  return <AgentCard title={tr(lang, 'trackTitle')} lang={lang} onLang={setLang} colors={colors}>
    {res.state === 'loading' ? <Loading lang={lang} colors={colors} /> : null}
    {res.state === 'unavailable' ? <Unavailable lang={lang} colors={colors} onRetry={retry} /> : null}
    {a ? <>
      {a.decisions.map((d) => <View key={d.cohortId} style={{ marginTop: 8 }}>
        <Text style={[styleBody(colors), rtl(lang), { fontWeight: '800' }]}>{d.cohortId} · {tr(lang, 'decisionDate')} {lang === 'fa' ? toFa(d.decisionDate) : d.decisionDate} · {d.side}</Text>
        {Object.entries(d.horizons).map(([h, hz]) => hz.status === 'MATURED'
          ? <Row key={h} label={`${lang === 'fa' ? toFa(h) : h}M · ${tr(lang, 'matured')} ${hz.exitDate || ''}`} colors={colors} lang={lang} dot={hz.hit ? Brand.positive : Brand.negative}
              value={`${signedPct(lang, hz.returnPct)} · ${hz.hit ? tr(lang, 'hit') : tr(lang, 'miss')}`}
              sub={`${tr(lang, 'benchmark')} ${signedPct(lang, hz.benchmarkPct)} · ${tr(lang, 'excess')} ${signedPct(lang, hz.excessPct)}`} />
          : <Row key={h} label={`${lang === 'fa' ? toFa(h) : h}M`} colors={colors} lang={lang} value={hz.status === 'PENDING' ? `${tr(lang, 'pending')}, ${tr(lang, 'due')} ${hz.matures}` : (hz.reason || hz.status)} />)}
      </View>)}
      <Text style={[styleSub(colors), rtl(lang)]}>{tr(lang, 'anecdote')}</Text>
    </> : null}
  </AgentCard>;
}

function styleBody(colors: ThemeColors) { return { color: colors.text, fontSize: 11.5, lineHeight: 18, marginTop: 6 } as const; }
function styleSub(colors: ThemeColors) { return { color: colors.textSecondary, fontSize: 10, lineHeight: 15, marginTop: 4 } as const; }

/** All three sections for one stock, below the decision block. Hidden unless the server flag is on; Risk then Performance load one at a time. */
export function AgentSections({ instrument, colors }: { instrument: GlobalInstrument; colors: ThemeColors }) {
  const [flags, setFlags] = useState<AgentFlags | null>(null);
  const [step, setStep] = useState(0);
  useEffect(() => { let alive = true; sessionGlobalStatus().then((s) => { if (alive) setFlags(agentFlags(s)); }); return () => { alive = false; }; }, []);
  useEffect(() => { setStep(0); }, [instrument.ticker, instrument.exchange, instrument.country]);
  useEffect(() => { if (flags && step === 0) setStep(flags.risk ? 1 : flags.performance ? 2 : 3); }, [flags, step]);
  if (!flags || (!flags.risk && !flags.performance && !flags.accuracy)) return null;
  const next = (from: number) => () => setStep((cur) => (cur === from ? (from === 1 ? (flags.performance ? 2 : 3) : 3) : cur));
  return <View>
    {flags.risk ? <RiskAgentSection instrument={instrument} colors={colors} start={step >= 1} onDone={next(1)} /> : null}
    {flags.performance ? <PerformanceAgentSection instrument={instrument} colors={colors} start={step >= 2} onDone={next(2)} /> : null}
    {flags.accuracy ? <StockRecordSection instrument={instrument} colors={colors} /> : null}
  </View>;
}
