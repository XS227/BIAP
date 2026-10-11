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


def test_truncated_stale_detail_with_untagged_reports_is_not_pipeline_failure():
    payload = {'evidence': {'status': 'BLOCK', 'missing_critical': ['fundamental_source'],
        'official_fundamental_status': 'OFFICIAL_STALE',
        'official_fundamental_detail': 'latest official period 2022-12-31 is 1380 days old; newer period only from non-official source; newer official source unavailable: official OAM ESEF package unusable: FSMA-STORI:653d9062-d0fa-463c-b9dd-e7b91a44ef5b: official ESEF report carries no inline XBRL tags (untagged report); FSMA-STORI:8490ee7f-eafb-40a9-9259-6fe3d69acab2: official ESEF repo'}}
    assert audit._classify(payload)['classification'] != 'PIPELINE_FAILURE'


def test_greenland_issuer_without_cvr_is_coverage_gap():
    detail = ("primary fundamentals unavailable (no Danish CVR number verifiable for LEI 549300EQF6IH6OIAYL40 (GLEIF registeredAs); "
              "Nasdaq Nordic announcements list no ESEF annual report for 'GRØNLANDSBANKEN, AKTIESELSKAB'); fallback unavailable "
              "(primary fundamentals unavailable (no ESEF filing found for LEI 549300EQF6IH6OIAYL40); fallback unavailable "
              "(primary fundamentals unavailable (SEC CIK not found for ticker GRLA); fallback unavailable (SEC CIK not found for ticker GRLA)))")
    assert audit._leaf_class(detail) == 'COVERAGE_GAP'


def test_canadian_ticker_owned_by_other_sec_filer_is_coverage_gap():
    detail = ("primary fundamentals unavailable (SEC ticker identity does not match selected issuer 'Elysee Development Corp.'; "
              "entityName='ENTERGY LOUISIANA, LLC'; jseIssuer=''; secAlias=''; cik=1348952); fallback unavailable "
              "(SEC returned no standard US-GAAP company facts for US:XTSX:ELC)")
    assert audit._leaf_class(detail) == 'COVERAGE_GAP'


def test_value_sanity_flags_thousand_scaled_eps_and_untied_balance_sheet():
    payload = {'currency': 'EUR', 'evidence': {'status': 'PASS', 'missing_critical': []},
        'company': {'price': 11.1},
        'fundamentalEvidence': {'isOfficial': True, 'values': {'reporting_currency': 'EUR', 'revenue': 1.0e8, 'eps': 655.0,
            'total_assets': 12.7e9, 'total_liabilities': 5.99e9, 'total_equity': -0.23e9}}}
    flags = audit._value_flags(payload)
    assert any('EPS' in f for f in flags) and any('balance sheet' in f for f in flags)
    assert audit._classify(payload)['classification'] == 'SUSPECT_VALUES'


def test_value_sanity_accepts_consistent_official_payload():
    payload = {'currency': 'NOK', 'evidence': {'status': 'PASS', 'missing_critical': []},
        'company': {'price': 417.9},
        'fundamentalEvidence': {'isOfficial': True, 'reportPeriod': '2025-12-31', 'filingDate': '2026-03-19',
            'values': {'reporting_currency': 'USD', 'revenue': 1.06e11, 'net_income': 5.1e9, 'eps': 1.94,
            'total_assets': 131.7e9, 'total_liabilities': 91.2e9, 'total_equity': 40.5e9}}}
    assert audit._value_flags(payload) == []
