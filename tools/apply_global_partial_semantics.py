from pathlib import Path

def replace_once(path: str, old: str, new: str) -> None:
    p=Path(path)
    text=p.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"anchor missing in {path}: {old[:220]!r}")
    p.write_text(text.replace(old,new,1),encoding="utf-8")

# Backend: make partial global scope explicit even when zero BUY candidates exist.
replace_once(
    "analysis/global_markets/scan_service.py",
    '''def scan_global_top10(
''',
    '''def _global_scan_status(*, eligible_markets: int, total_markets: int, recommendation_count: int) -> str:
    """Describe global scope without overstating incomplete market coverage."""
    if eligible_markets <= 0:
        return "GLOBAL_DATA_INCOMPLETE"
    if eligible_markets < total_markets:
        return "PARTIAL_GLOBAL_SCAN" if recommendation_count > 0 else "PARTIAL_GLOBAL_NO_RECOMMENDATION"
    return "GLOBAL_TOP10" if recommendation_count > 0 else "NO_RECOMMENDATION"


def scan_global_top10(
''',
)

replace_once(
    "analysis/global_markets/scan_service.py",
    '''    if eligible_markets == 0:
        status = "GLOBAL_DATA_INCOMPLETE"
        recommendations = []
    elif not recommendations:
        status = "NO_RECOMMENDATION"
    elif eligible_markets < len(markets):
        status = "PARTIAL_GLOBAL_SCAN"
    else:
        status = "GLOBAL_TOP10"
''',
    '''    status = _global_scan_status(
        eligible_markets=eligible_markets,
        total_markets=len(markets),
        recommendation_count=len(recommendations),
    )
    if eligible_markets == 0:
        recommendations = []
''',
)

# Backend regression tests.
p=Path("analysis/tests/test_global_top_markets.py")
text=p.read_text(encoding="utf-8")
text=text.replace(
    "from global_markets.scan_service import _global_top_markets\n",
    "from global_markets.scan_service import _global_scan_status, _global_top_markets\n",
    1,
)
addition='''

def test_global_status_never_calls_partial_zero_result_global_no_recommendation():
    assert _global_scan_status(
        eligible_markets=11, total_markets=18, recommendation_count=0
    ) == "PARTIAL_GLOBAL_NO_RECOMMENDATION"


def test_global_status_marks_partial_scope_when_candidates_exist():
    assert _global_scan_status(
        eligible_markets=11, total_markets=18, recommendation_count=3
    ) == "PARTIAL_GLOBAL_SCAN"


def test_global_status_uses_full_scope_labels_only_when_all_markets_ready():
    assert _global_scan_status(
        eligible_markets=18, total_markets=18, recommendation_count=0
    ) == "NO_RECOMMENDATION"
    assert _global_scan_status(
        eligible_markets=18, total_markets=18, recommendation_count=2
    ) == "GLOBAL_TOP10"
'''
if addition.strip() not in text:
    text += addition
p.write_text(text,encoding="utf-8")

# Mobile: distinguish partial ready-market scope from a true Global Top 10.
replace_once(
    "mobile/src/app/market.tsx",
    '''      const globallyReady = (result.marketsEligible ?? 0) > 0 && result.status !== 'GLOBAL_DATA_INCOMPLETE';
      setScan(globallyReady ? (result.recommendations || []) : []);
      setScanMode(globallyReady ? 'global' : 'cached');
      const coverage = result.globalCoveragePct == null ? '—' : `${Number(result.globalCoveragePct).toFixed(1)}%`;
      if (!globallyReady) {
        setScanStatus(`Global ranking blocked • ${result.marketsEligible ?? 0}/${result.marketsScanned ?? 0} markets ready • ${result.marketsExcluded ?? result.marketsScanned ?? 0} excluded`);
      } else {
        setScanStatus(`Global Top 10 • ${result.recommendationCount ?? 0} qualified • ${result.marketsEligible ?? 0}/${result.marketsScanned ?? 0} markets ready • ${result.screenedEquities ?? 0}/${result.eligibleEquities ?? 0} equities screened • ${coverage} coverage`);
      }
''',
    '''      const readyMarkets = result.marketsEligible ?? 0;
      const scannedMarkets = result.marketsScanned ?? 0;
      const globallyReady = readyMarkets > 0 && result.status !== 'GLOBAL_DATA_INCOMPLETE';
      const completeGlobalScope = scannedMarkets > 0 && readyMarkets === scannedMarkets;
      setScan(globallyReady ? (result.recommendations || []) : []);
      setScanMode(globallyReady ? 'global' : 'cached');
      const coverage = result.globalCoveragePct == null ? '—' : `${Number(result.globalCoveragePct).toFixed(1)}%`;
      if (!globallyReady) {
        setScanStatus(`Global ranking blocked • ${readyMarkets}/${scannedMarkets} markets ready • ${result.marketsExcluded ?? scannedMarkets} excluded`);
      } else if (!completeGlobalScope) {
        setScanStatus(`Partial global scan • ${readyMarkets}/${scannedMarkets} markets ready • ${result.recommendationCount ?? 0} qualified in ready markets • ${result.screenedEquities ?? 0}/${result.eligibleEquities ?? 0} equities screened • ${coverage} ready-market coverage`);
      } else {
        setScanStatus(`Global Top 10 • ${result.recommendationCount ?? 0} qualified • all ${scannedMarkets} markets ready • ${result.screenedEquities ?? 0}/${result.eligibleEquities ?? 0} equities screened • ${coverage} coverage`);
      }
''',
)
