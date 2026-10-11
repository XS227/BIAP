import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('audit_global_evidence', Path(__file__).parents[1] / 'audit_global_evidence.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_untagged_official_oam_with_known_fallback_absences():
    detail = ('primary fundamentals unavailable (no verified local filing record at /data/EU/COH.json); '
              'fallback unavailable (primary fundamentals unavailable (official OAM ESEF package unusable: '
              'AMF-INFOFI:ACT/2026/06/file.xhtml: official ESEF report carries no inline XBRL tags (untagged report)); '
              'fallback unavailable (no ESEF filing found for LEI 9695007OBW30ATMM1668); '
              'fallback unavailable (SEC CIK not found for ticker COH)))')
    assert audit._leaf_class(detail) == 'LEGIT_OFFICIAL_UNAVAILABLE'


def test_unknown_parser_error_remains_pipeline_failure():
    assert audit._leaf_class('official OAM ESEF package unusable: parser raised ValueError') == 'PIPELINE_FAILURE'


def test_missing_newer_oam_is_index_lag_not_pipeline_failure():
    payload = {'evidence': {'status': 'BLOCK', 'missing_critical': ['fresh_fundamentals'],
        'official_fundamental_status': 'OFFICIAL_STALE',
        'official_fundamental_detail': 'latest official period 2024-12-31 is 642 days old; newer period only from non-official source; newer official source unavailable: Newsweb lists no annual ESEF package for ODFB'}}
    assert audit._classify(payload)['classification'] == 'INDEX_LAG'


def test_discovery_queued_note_is_coverage_gap():
    detail = ('primary fundamentals unavailable (no verified HK issuer parser for 0001); fallback unavailable '
              '(no verified local filing record at /var/lib/biap-global/filings/HK/0001.json; official-source discovery queued)')
    assert audit._leaf_class(detail) == 'COVERAGE_GAP'


def test_untagged_oam_with_sec_ifrs_absence_is_legit_unavailable():
    detail = ('primary fundamentals unavailable (official OAM ESEF package unusable: FI-FINANSCENTRALEN:61691: '
              'official ESEF report carries no inline XBRL tags (untagged report)); '
              'fallback unavailable (SEC returned no standard IFRS company facts for SE:XSTO:ABB)')
    assert audit._leaf_class(detail) == 'LEGIT_OFFICIAL_UNAVAILABLE'


def test_unresolved_cnmv_identity_stays_pipeline_failure():
    payload = {'evidence': {'status': 'BLOCK', 'missing_critical': ['fundamental_source'],
        'official_fundamental_status': 'OFFICIAL_STALE',
        'official_fundamental_detail': 'latest official period 2024-12-31 is 649 days old; newer period only from non-official source; '
                                       'newer official source unavailable: no CNMV NIF verifiable for LEI 95980079E2NBJT967T79 (GLEIF RegisteredAs / CNMV ISIN register)'}}
    assert audit._classify(payload)['classification'] == 'PIPELINE_FAILURE'


def test_nse_twelve_month_wording_is_one_coverage_leaf():
    assert audit._leaf_class('NSE integrated filings contain no annual (12-month) results for LALITHAA') == 'COVERAGE_GAP'


def test_stale_frankfurt_key_data_without_esef_obligation_is_legit_unavailable():
    detail = ('primary fundamentals unavailable (primary fundamentals unavailable (listing is in Deutsche Boerse FRAB Open Market/Scale: '
              'no ESEF annual financial report obligation); fallback unavailable (primary fundamentals unavailable '
              '(no reviewed German annual-report snapshot for DE0005760029); fallback unavailable (Börse Frankfurt latest annual key data FY2024 is too old)))')
    assert audit._leaf_class(detail) == 'LEGIT_OFFICIAL_UNAVAILABLE'
