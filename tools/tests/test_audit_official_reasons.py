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
