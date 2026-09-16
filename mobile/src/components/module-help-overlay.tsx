import { useMemo, useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { useGlobalSearchParams, usePathname } from 'expo-router';

import { BottomTabInset, Brand, Colors, Fonts, Radius, Spacing } from '@/constants/theme';

type Guide = {
  title: string;
  purpose: string;
  steps: string[];
  checks: string[];
  caution: string;
};

const MODULE_NAMES: Record<string, string> = {
  financial: 'Financial Model',
  kpi: 'KPI Analysis',
  swot: 'SWOT',
  pricing: 'Pricing',
  unitEconomics: 'Unit Economics',
  forecasting: 'Forecasting',
  anomalies: 'Anomaly Detection',
  query: 'Data Query',
  journey: 'Customer Journey',
  crm: 'CRM',
  bizdev: 'Business Development',
};

function guideFor(pathname: string, moduleKey?: string): Guide {
  if (pathname === '/' || pathname === '/index') {
    return {
      title: 'Home',
      purpose: 'Your BIAP Global starting point. The selected country and exchange become the shared market context for Market, Kiasha, stock analysis and the portfolio workflow.',
      steps: [
        'Use Change country when you want to switch the active market.',
        'Open Market to browse instruments or run a market scan.',
        'Open Kiasha to see evidence-gated ranked ideas.',
        'Open Portfolio to compare several exchanges and construct a global paper portfolio.',
      ],
      checks: ['Confirm the country, exchange and currency before interpreting results.', 'A selected company is reused by supported analysis modules.'],
      caution: 'BIAP Global is research and decision support. A market selection changes the data provider, not the core analysis engine.',
    };
  }
  if (pathname === '/global') {
    return {
      title: 'Market Selector',
      purpose: 'Choose the country and exchange whose data providers should feed the BIAP analysis engine.',
      steps: ['Choose a country.', 'Choose one of its supported exchanges.', 'Return to Market, Kiasha or Portfolio with that context saved.'],
      checks: ['Market data, filings and official evidence can come from different providers.', 'Provider availability is shown rather than silently replaced with invented data.'],
      caution: 'If a required official source is unavailable, BIAP may withhold a recommendation.',
    };
  }
  if (pathname === '/market') {
    return {
      title: 'Market',
      purpose: 'Browse the selected exchange, search securities and run the same BIAP screening pipeline across that market.',
      steps: ['Search by ticker, company name or ISIN.', 'Open a stock for deep analysis.', 'Use Run scan to screen the exchange through liquidity, six scoring agents and the evidence gate.'],
      checks: ['Check price freshness and volume.', 'Confirm the listing identity/MIC.', 'Review official filing coverage before relying on a score.'],
      caution: 'A missing instrument list or scan error means the provider connection needs attention; it is not a negative view on the market.',
    };
  }
  if (pathname === '/kiasha') {
    return {
      title: 'Kiasha Global',
      purpose: 'Kiasha combines the independent scoring agents and the Evidence/Verification gate into a ranked research view for the active market.',
      steps: ['Run the selected-market scan.', 'Review only candidates that pass evidence checks.', 'Open a candidate to inspect every agent vote before using it in a portfolio.'],
      checks: ['Fundamental', 'Risk', 'Forecast', 'Comparison', 'Quality', 'Liquidity', 'Evidence/Verification'],
      caution: 'A strong aggregate score is not enough by itself. Evidence can block promotion to a BUY candidate.',
    };
  }
  if (pathname === '/portfolio') {
    return {
      title: 'Global Portfolio Agent',
      purpose: 'Compare several exchanges and combine only evidence-qualified candidates into one paper portfolio.',
      steps: ['Select up to four exchanges.', 'Set capital, base currency, risk tolerance, horizon, position count and cash reserve.', 'Run market comparison and portfolio construction.', 'Review the final analytical table and the reason each position was selected.'],
      checks: ['Cross-market FX conversion', 'Country and position concentration', 'Evidence status', 'Agent agreement', 'Liquidity and tradability'],
      caution: 'Portfolio output is a research proposal. Live broker execution remains disabled until separate execution and compliance controls are implemented.',
    };
  }
  if (pathname.startsWith('/stock/')) {
    return {
      title: 'Stock Analysis',
      purpose: 'Deep analysis of one listed company using normalized market, valuation, financial and official-evidence data.',
      steps: ['Verify the company identity and listing.', 'Review price, valuation, fundamentals and risk metrics.', 'Compare all six scoring-agent signals.', 'Read Evidence/Verification before the Kiasha interpretation.'],
      checks: ['Data source and observation time', 'Fundamental quality', 'Risk flags', 'Forecast context', 'Peer comparison', 'Quality and liquidity'],
      caution: 'NO_RECOMMENDATION is a valid result when data is stale, incomplete, contradictory or insufficiently verified.',
    };
  }
  if (pathname === '/modules') {
    return {
      title: 'Analysis Modules',
      purpose: 'Use the selected listed company across reusable business and financial analysis modules.',
      steps: ['Select a company from Market or Kiasha first.', 'Open a module.', 'Review which fields came from public market/filing data and which require private company data.'],
      checks: ['Public issuer data should never be confused with private CRM/operational data.', 'Missing private inputs remain missing instead of being fabricated.'],
      caution: 'Not every module can be completed from stock-market disclosures alone.',
    };
  }
  if (pathname === '/module') {
    const name = MODULE_NAMES[moduleKey || ''] || 'Analysis Module';
    return {
      title: name,
      purpose: `Apply the ${name} workflow to the currently selected company using normalized BIAP Global data where appropriate.`,
      steps: ['Confirm the selected company.', 'Review source coverage.', 'Add private/internal data only when the module genuinely requires it.', 'Interpret the result together with the stock-level evidence and risk view.'],
      checks: ['Source provenance', 'Period alignment', 'Currency consistency', 'Public vs private data boundary'],
      caution: 'The module must not infer unavailable internal business data from share price alone.',
    };
  }
  if (pathname === '/data-connect') {
    return {
      title: 'Data Connections',
      purpose: 'Attach private company data such as CSV/Excel exports, CRM data, SQL sources or custom APIs to supported modules.',
      steps: ['Choose the private data source.', 'Map fields carefully.', 'Validate periods, units and currencies.', 'Use connected data only in modules that need it.'],
      checks: ['Field mapping', 'Date coverage', 'Duplicates', 'Currency/units', 'Access permissions'],
      caution: 'Private data is separate from official investment evidence and should not silently replace regulatory filings.',
    };
  }
  if (pathname === '/orders') {
    return {
      title: 'Execution',
      purpose: 'Shows the execution boundary between BIAP research, paper portfolios and future broker connections.',
      steps: ['Review the recommendation and portfolio first.', 'Keep execution in paper/human-approval mode.', 'Connect a supported broker only after execution and compliance gates are ready.'],
      checks: ['Broker status', 'Market/currency match', 'Risk limits', 'Human approval'],
      caution: 'Live global trading is intentionally disabled in this version.',
    };
  }
  return {
    title: 'BIAP Global Guide',
    purpose: 'Context-sensitive help for the current BIAP Global screen.',
    steps: ['Confirm the selected market.', 'Review source quality.', 'Use agent outputs together rather than in isolation.', 'Open the detailed view when a result needs interpretation.'],
    checks: ['Data freshness', 'Evidence coverage', 'Risk', 'Agent agreement'],
    caution: 'Research outputs can be uncertain. BIAP may withhold a recommendation when evidence is insufficient.',
  };
}

export function ModuleHelpOverlay() {
  const pathname = usePathname();
  const params = useGlobalSearchParams<{ key?: string }>();
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  const [visible, setVisible] = useState(false);
  const guide = useMemo(() => guideFor(pathname, typeof params.key === 'string' ? params.key : undefined), [pathname, params.key]);

  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Help for ${guide.title}`}
        onPress={() => setVisible(true)}
        style={({ pressed }) => [styles.helpButton, { opacity: pressed ? 0.78 : 1 }]}
      >
        <Text style={styles.helpButtonText}>? Help</Text>
      </Pressable>

      <Modal visible={visible} transparent animationType="slide" onRequestClose={() => setVisible(false)}>
        <View style={styles.modalRoot}>
          <Pressable style={StyleSheet.absoluteFill} onPress={() => setVisible(false)} />
          <View style={[styles.sheet, { backgroundColor: colors.backgroundElement }]}> 
            <View style={styles.sheetHeader}>
              <View style={styles.headerCopy}>
                <Text style={[styles.eyebrow, { color: Brand.primary }]}>BIAP GLOBAL GUIDE</Text>
                <Text style={[styles.title, { color: colors.text }]}>{guide.title}</Text>
              </View>
              <Pressable accessibilityLabel="Close help" onPress={() => setVisible(false)} style={[styles.closeButton, { backgroundColor: colors.backgroundSelected }]}> 
                <Text style={[styles.closeText, { color: colors.text }]}>×</Text>
              </Pressable>
            </View>

            <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
              <Section title="Purpose" colors={colors}>
                <Text style={[styles.body, { color: colors.textSecondary }]}>{guide.purpose}</Text>
              </Section>

              <Section title="How to use it" colors={colors}>
                {guide.steps.map((item, index) => <Bullet key={`${index}-${item}`} text={item} colors={colors} />)}
              </Section>

              <Section title="What to check" colors={colors}>
                {guide.checks.map((item, index) => <Bullet key={`${index}-${item}`} text={item} colors={colors} />)}
              </Section>

              <View style={[styles.caution, { borderColor: Brand.warning, backgroundColor: colors.background }]}> 
                <Text style={[styles.sectionTitle, { color: colors.text }]}>Important</Text>
                <Text style={[styles.body, { color: colors.textSecondary }]}>{guide.caution}</Text>
              </View>
            </ScrollView>
          </View>
        </View>
      </Modal>
    </>
  );
}

function Section({ title, colors, children }: { title: string; colors: (typeof Colors)['light'] | (typeof Colors)['dark']; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={[styles.sectionTitle, { color: colors.text }]}>{title}</Text>
      {children}
    </View>
  );
}

function Bullet({ text, colors }: { text: string; colors: (typeof Colors)['light'] | (typeof Colors)['dark'] }) {
  return (
    <View style={styles.bulletRow}>
      <Text style={[styles.bulletMark, { color: Brand.primary }]}>•</Text>
      <Text style={[styles.body, styles.bulletText, { color: colors.textSecondary }]}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  helpButton: {
    position: 'absolute',
    left: Spacing.three,
    bottom: BottomTabInset + Spacing.three,
    zIndex: 50,
    paddingHorizontal: Spacing.three,
    paddingVertical: 10,
    borderRadius: Radius.xl,
    backgroundColor: Brand.primary,
    shadowColor: '#000',
    shadowOpacity: 0.15,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
    elevation: 5,
  },
  helpButtonText: { color: '#FFFFFF', fontFamily: Fonts.sans, fontWeight: '700', fontSize: 14 },
  modalRoot: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(4, 8, 20, 0.38)' },
  sheet: { maxHeight: '82%', borderTopLeftRadius: Radius.xl, borderTopRightRadius: Radius.xl, paddingTop: Spacing.three },
  sheetHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.four, gap: Spacing.three },
  headerCopy: { flex: 1 },
  eyebrow: { fontFamily: Fonts.mono, fontSize: 12, fontWeight: '700', letterSpacing: 1.2 },
  title: { fontFamily: Fonts.sans, fontSize: 28, lineHeight: 34, fontWeight: '800', marginTop: Spacing.one },
  closeButton: { width: 42, height: 42, borderRadius: 21, alignItems: 'center', justifyContent: 'center' },
  closeText: { fontSize: 28, lineHeight: 30, fontWeight: '500' },
  scrollContent: { padding: Spacing.four, paddingBottom: BottomTabInset + Spacing.four },
  section: { marginBottom: Spacing.four },
  sectionTitle: { fontFamily: Fonts.sans, fontWeight: '800', fontSize: 17, marginBottom: Spacing.two },
  body: { fontFamily: Fonts.sans, fontSize: 15, lineHeight: 23 },
  bulletRow: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: Spacing.two },
  bulletMark: { fontSize: 18, lineHeight: 23, marginRight: Spacing.two },
  bulletText: { flex: 1 },
  caution: { borderWidth: 1, borderRadius: Radius.lg, padding: Spacing.three, marginBottom: Spacing.four },
});
