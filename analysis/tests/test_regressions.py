from agents import fundamental_agent, run_team
import api_server
from audit_parser import (
    _extract_audit_opinion_section,
    classify_audit_opinion_from_text,
)
from codal_data import CodalFiling, CodalFundamentals, _parse_fundamentals, _row_values
import company_builder
from financial_scope import (
    CONSOLIDATED,
    STANDALONE,
    report_scope_from_title,
    select_scope_filings,
)
from kiasha import decide
from market_data import ExtendedMarketData, LiveQuote
from related_party import _related_party_flags_from_text
import symbol_universe as su
from symbol_universe import MarketSymbol, _parse_symbol


def test_exact_net_profit_row_matching():
    rows = [
        ["سود (زیان) خالص عملیات متوقف شده", "0", "0"],
        ["سود(زیان) خالص", "100", "80"],
    ]

    result = _row_values(
        rows,
        ("سود (زیان) خالص", "سود خالص", "زیان خالص"),
    )

    assert result == (100.0, 80.0)


def test_balance_sheet_totals_row_matching():
    rows = [
        ["جمع دارایی‌ها", "500", "400"],
        ["جمع بدهی‌ها", "300", "250"],
        ["جمع حقوق صاحبان سهام", "200", "150"],
    ]

    assert _row_values(rows, ("جمع دارایی‌ها", "جمع دارایی ها")) == (500.0, 400.0)
    assert _row_values(rows, ("جمع بدهی‌ها", "جمع بدهی ها")) == (300.0, 250.0)
    assert _row_values(rows, ("جمع حقوق صاحبان سهام",)) == (200.0, 150.0)


def test_parse_fundamentals_extracts_balance_sheet_alongside_income_statement():
    filing = CodalFiling(
        tracing_no="123",
        title="صورت‌های مالی سال مالی منتهی به ۱۴۰۴/۱۲/۲۹",
        sent_at=None,
        publish_at=None,
        letter_code=None,
        url=None,
        pdf_url=None,
        excel_url="https://excel.codal.ir/service/Excel/GetAll/xyz/0",
        attachment_url=None,
    )
    report_html = """
    <table>
      <tr><td>درآمدهای عملیاتی</td><td>120</td><td>100</td></tr>
      <tr><td>سود (زیان) ناخالص</td><td>40</td><td>30</td></tr>
      <tr><td>سود (زیان) خالص</td><td>15</td><td>10</td></tr>
      <tr><td>جمع دارایی‌ها</td><td>500</td><td>400</td></tr>
      <tr><td>جمع بدهی‌ها</td><td>300</td><td>250</td></tr>
      <tr><td>جمع حقوق صاحبان سهام</td><td>200</td><td>150</td></tr>
    </table>
    """

    result = _parse_fundamentals("فولاد", filing, report_html)

    assert result is not None
    assert result.total_assets_current == 500.0
    assert result.total_assets_prev == 400.0
    assert result.total_liabilities_current == 300.0
    assert result.total_liabilities_prev == 250.0
    assert result.total_equity_current == 200.0
    assert result.total_equity_prev == 150.0


def test_balance_sheet_equity_prefers_current_codal_template_label():
    # Verified live against فولاد's 1404 consolidated statement on
    # 2026-08-27: CODAL's current template labels the equity total
    # "جمع حقوق مالکانه", not the older "جمع حقوق صاحبان سهام".
    rows = [
        ["جمع حقوق مالکانه", "5,129,927,668", "4,146,581,655"],
        ["جمع حقوق صاحبان سهام", "999", "888"],
    ]

    result = _row_values(
        rows,
        ("جمع حقوق مالکانه", "جمع حقوق صاحبان سهام"),
    )

    assert result == (5129927668.0, 4146581655.0)


def test_parse_fundamentals_leaves_balance_sheet_none_when_rows_absent():
    filing = CodalFiling(
        tracing_no="124",
        title="صورت‌های مالی سال مالی منتهی به ۱۴۰۴/۱۲/۲۹",
        sent_at=None,
        publish_at=None,
        letter_code=None,
        url=None,
        pdf_url=None,
        excel_url="https://excel.codal.ir/service/Excel/GetAll/xyz/0",
        attachment_url=None,
    )
    report_html = """
    <table>
      <tr><td>درآمدهای عملیاتی</td><td>120</td><td>100</td></tr>
      <tr><td>سود (زیان) خالص</td><td>15</td><td>10</td></tr>
    </table>
    """

    result = _parse_fundamentals("فولاد", filing, report_html)

    assert result is not None
    assert result.total_assets_current is None
    assert result.total_liabilities_current is None
    assert result.total_equity_current is None


def test_negative_margin_is_penalized_even_if_improving():
    company = {
        "codal": {
            "revenue_yoy_pct": 56.8,
            "net_margin_pct": -0.9,
            "net_margin_prev_pct": -1.7,
            "audit_opinion": None,
            "related_party_flags": None,
        },
        "market": {},
    }

    result = fundamental_agent(company)

    assert result.vote == 0.1
    assert "net margin negative" in result.reasoning
    assert "loss margin improving" in result.reasoning


def test_bounded_audit_parser_ignores_exception_outside_opinion_section():
    text = """
    اظهارنظر
    به نظر این سازمان، صورتهای مالی یادشده، وضعیت مالی گروه و شرکت را
    از تمام جنبه های با اهمیت، طبق استانداردهای حسابداری،
    به نحو منصفانه نشان می دهد.
    مبنای اظهارنظر
    شواهد حسابرسی کافی و مناسب کسب شده است.
    سایر اطلاعات
    موجودی مواد و کالا به استثنای موجودی کالای در راه بررسی شده است.
    """

    section = _extract_audit_opinion_section(text)
    assert section is not None
    assert "موجودی مواد و کالا" not in section
    assert classify_audit_opinion_from_text(text) == "unqualified"


def test_bounded_audit_parser_detects_qualified_opinion_inside_section():
    text = """
    اظهارنظر
    به نظر این سازمان، به استثنای آثار موضوع شرح داده شده در بند مبنای
    اظهارنظر مشروط، صورتهای مالی از تمام جنبه های با اهمیت به نحو
    منصفانه نشان می دهد.
    مبنای اظهارنظر
    موضوع محدودیت رسیدگی در این بخش تشریح شده است.
    """

    assert classify_audit_opinion_from_text(text) == "qualified"


def test_bounded_audit_parser_requires_reliable_opinion_anchor():
    text = """
    یادداشت موجودی کالا شامل عبارت به استثنای کالای در راه است.
    اطلاعات دیگری نیز در صورتهای مالی ارائه شده است.
    """

    assert classify_audit_opinion_from_text(text) is None


def test_bounded_audit_parser_detects_disclaimer_of_opinion():
    text = """
    اظهارنظر
    با توجه به عدم دسترسی به شواهد حسابرسی کافی و مناسب در خصوص موجودی
    کالا، این سازمان قادر به اظهارنظر نسبت به صورتهای مالی نیست. بر این
    اساس، عدم اظهارنظر نسبت به صورتهای مالی ارائه می شود.
    مبنای عدم اظهارنظر
    محدودیت رسیدگی در این بخش تشریح شده است.
    """

    # "مبنای عدم اظهارنظر" must not itself be picked as the opinion heading
    # (it contains "اظهارنظر" as a substring); the section should start at
    # the real "اظهارنظر" heading above it.
    section = _extract_audit_opinion_section(text)
    assert section is not None
    assert section.startswith("اظهارنظر")
    assert classify_audit_opinion_from_text(text) == "disclaimer"


def test_bounded_audit_parser_detects_adverse_opinion():
    text = """
    اظهارنظر
    به نظر این سازمان، به علت اهمیت موضوعات مندرج در بند مبنای اظهارنظر
    مردود، صورتهای مالی وضعیت مالی شرکت را به نحو مطلوب نشان نمی دهد.
    مبنای اظهارنظر مردود
    آثار موضوعات مورد اشاره در این بخش تشریح شده است.
    """

    assert classify_audit_opinion_from_text(text) == "adverse"


def test_bounded_audit_parser_prefers_real_section_over_table_of_contents():
    # Without a canonical fairness clause to anchor on (real for a disclaimer,
    # which never confirms the statements are fairly presented), a naive
    # "first heading wins" rule would grab the table-of-contents entry instead
    # of the actual opinion section further down the document.
    text = """
    فهرست مطالب
    اظهارنظر
    سایر مطالب
    این بخش صرفا فهرست گزارش است و شامل هیچ اظهارنظری نیست.

    گزارش حسابرس مستقل
    اظهارنظر
    با توجه به عدم دسترسی به شواهد حسابرسی کافی و مناسب، این سازمان
    قادر به اظهارنظر نسبت به صورتهای مالی نیست. عدم اظهارنظر نسبت به
    صورتهای مالی ارائه می شود.
    """

    section = _extract_audit_opinion_section(text)
    assert section is not None
    assert "فهرست" not in section
    assert classify_audit_opinion_from_text(text) == "disclaimer"


def test_bounded_audit_parser_does_not_mistake_basis_heading_for_opinion_heading():
    # "مبنای اظهارنظر" ("Basis for Opinion") contains "اظهارنظر" as a
    # substring and must never itself be picked as the opinion heading.
    text = """
    مبنای اظهارنظر
    شواهد حسابرسی کافی و مناسب کسب شده است.
    اظهارنظر
    به نظر این سازمان، صورتهای مالی یادشده، وضعیت مالی گروه و شرکت را
    از تمام جنبه های با اهمیت، طبق استانداردهای حسابداری،
    به نحو منصفانه نشان می دهد.
    """

    section = _extract_audit_opinion_section(text)
    assert section is not None
    assert "شواهد حسابرسی کافی" not in section
    assert classify_audit_opinion_from_text(text) == "unqualified"


def test_bounded_audit_parser_prefers_canonical_sentence_over_a_corrupt_heading():
    # Observed on a real, live CODAL filing (فولاد مبارکه اصفهان, fetched
    # through the newly-connected relay): pdftotext's handling of a numbered
    # paragraph in a bidi Persian PDF dropped "مبنای" from what should have
    # been the "مبنای اظهارنظر" heading, leaving a bare "اظهار نظر" line
    # that matches the heading pattern and sits *before* the real, reliable
    # canonical opinion sentence. Anchoring on that corrupted heading instead
    # of the canonical sentence produced a false None instead of the correct
    # "unqualified" classification. The canonical sentence must win.
    text = """
    مسئولیت‌های حسابرس در بخش قبل شرح داده شده است.
    اظهار نظر
    .4 حسابرسی این سازمان طبق استانداردهای حسابرسی انجام شده است. این سازمان
    اعتقاد دارد که شواهد حسابرسی کسب شده به عنوان مبنای اظهارنظر، کافی و
    مناسب است.
    به نظر این سازمان، صورتهای مالی یادشده وضعیت مالی شرکت را از تمام
    جنبه های با اهمیت، طبق استانداردهای حسابداری، به نحو منصفانه نشان می دهد.
    """

    section = _extract_audit_opinion_section(text)
    assert section is not None
    assert section.startswith("به نظر این سازمان")
    assert classify_audit_opinion_from_text(text) == "unqualified"


def test_related_party_parser_returns_none_without_context():
    text = "صورتهای مالی طبق استانداردهای حسابداری تهیه شده است."

    assert _related_party_flags_from_text(text) is None


def test_related_party_routine_disclosure_is_not_a_flag():
    text = """
    معاملات با اشخاص وابسته در یادداشت های توضیحی صورتهای مالی افشا شده است.
    مانده حسابهای اشخاص وابسته نیز در صورتهای مالی ارائه شده است.
    """

    assert _related_party_flags_from_text(text) == 0


def test_related_party_explicit_noncompliance_is_flagged():
    text = """
    در بررسی معاملات با اشخاص وابسته مشخص شد ماده 129 قانون تجارت رعایت نشده
    و بخشی از معاملات اشخاص وابسته افشا نشده است.
    """

    assert _related_party_flags_from_text(text) == 2


def test_related_party_parser_ignores_cross_window_false_adjacency():
    # Two unrelated related-party mentions, ~900 characters apart. Neither
    # fragment alone describes a real violation. Each mention gets its own
    # bounded window; joining those windows with a bare space would let the
    # tail of one ("...ماده 129 قانون تجارت") sit directly next to the head
    # of the other ("رعایت نشده...") and read as one sentence that never
    # actually appears in the source document.
    pad_a = "س" * 5
    pad_b = "ز" * 900
    head = pad_a + "رعایت نشده است ماده ۱۲۹ بی ربط به موضوع دیگری دارد"
    tail = "شرکت با اشخاص وابسته معامله کرده است و ماده 129 قانون تجارت"
    text = head + pad_b + tail

    assert _related_party_flags_from_text(text) == 0


def _filing(title: str) -> CodalFiling:
    return CodalFiling(
        tracing_no=None,
        title=title,
        sent_at=None,
        publish_at=None,
        letter_code=None,
        url=None,
        pdf_url=None,
        excel_url=None,
        attachment_url=None,
    )


def test_report_scope_classifies_consolidated_and_standalone():
    assert report_scope_from_title("صورت های مالی تلفیقی سال مالی منتهی به 1404/12/29") == CONSOLIDATED
    assert report_scope_from_title("صورت های مالی سال مالی منتهی به 1404/12/29") == STANDALONE
    assert report_scope_from_title("تصمیمات مجمع عمومی عادی سالیانه") is None


def test_report_scope_prefers_consolidated_when_both_exist():
    standalone = _filing("صورت های مالی سال مالی منتهی به 1404/12/29")
    consolidated = _filing("صورت های مالی تلفیقی سال مالی منتهی به 1404/12/29")

    scope, filings = select_scope_filings([standalone, consolidated])

    assert scope == CONSOLIDATED
    assert filings == [consolidated]


def test_report_scope_falls_back_to_standalone():
    standalone = _filing("صورت های مالی سال مالی منتهی به 1404/12/29")

    scope, filings = select_scope_filings([standalone])

    assert scope == STANDALONE
    assert filings == [standalone]


def test_symbol_snapshot_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / "symbols.json"
    monkeypatch.setenv("BIAP_SYMBOL_SNAPSHOT", str(path))
    items = [
        MarketSymbol(
            code="123",
            symbol="فولاد",
            name="فولاد مبارکه اصفهان",
            market="TSE",
            flow=1,
            industry_code="27",
            paper_type="300",
            source="tsetmc",
        )
    ]

    su._save_snapshot(items)
    loaded = su._load_snapshot()

    assert loaded == items


def test_symbol_universe_uses_verified_snapshot_when_upstreams_fail(tmp_path, monkeypatch):
    path = tmp_path / "symbols.json"
    monkeypatch.setenv("BIAP_SYMBOL_SNAPSHOT", str(path))
    cached = [
        MarketSymbol(
            code="123",
            symbol="فولاد",
            name="فولاد مبارکه اصفهان",
            market="TSE",
            flow=1,
            industry_code="27",
            paper_type="300",
            source="tsetmc",
        )
    ]
    su._save_snapshot(cached)
    su._cache = None
    monkeypatch.setattr(su, "_fetch_json_universe", lambda **kwargs: [])
    monkeypatch.setattr(su, "_fetch_legacy_universe", lambda **kwargs: [])
    monkeypatch.setattr(su, "_fetch_codal_universe", lambda: [])

    result = su.fetch_symbol_universe(use_cache=False)

    assert result == cached


def test_parse_symbol_maps_all_three_market_flows():
    for flow, expected_market in ((1, "TSE"), (2, "IFB"), (4, "IFB_BASE")):
        raw = {
            "insCode": "1000",
            "lVal18AFC": "SYM",
            "lVal30": "Sample Co",
            "flow": flow,
            "cs": "27",
            "yVal": "300",
        }
        parsed = _parse_symbol(raw)
        assert parsed is not None
        assert parsed.market == expected_market


def test_parse_symbol_rejects_unrecognized_flow():
    # Flow 3 isn't one of the three markets BIAP resolves symbols for. A row
    # like this must be excluded, never silently mapped to the wrong market.
    raw = {"insCode": "1000", "lVal18AFC": "SYM", "lVal30": "Sample Co", "flow": 3}

    assert _parse_symbol(raw) is None


def _legacy_row(code: str, symbol: str, name: str, flow: int) -> str:
    cols = [""] * 23
    cols[0], cols[2], cols[3], cols[17] = code, symbol, name, str(flow)
    cols[18], cols[22] = "27", "300"
    return ",".join(cols)


def test_legacy_universe_parser_handles_all_three_markets(monkeypatch):
    # A second, independent parsing path (the plain-text TSETMC fallback used
    # when the JSON API is unreachable) -- covering flow mapping there too so
    # a bug in one parser can't hide behind the other's test coverage.
    rows = [
        _legacy_row("1", "TSE1", "TSE Co", 1),
        _legacy_row("2", "IFB1", "IFB Co", 2),
        _legacy_row("3", "BASE1", "Base Co", 4),
        _legacy_row("4", "UNKNOWN1", "Unknown Flow Co", 3),  # must be dropped
    ]
    legacy_text = "header1@header2@" + ";".join(rows)
    monkeypatch.setattr(su, "_read_url", lambda url, timeout: legacy_text.encode("utf-8"))

    items = su._fetch_legacy_universe(timeout=1)

    by_symbol = {item.symbol: item for item in items}
    assert by_symbol["TSE1"].market == "TSE"
    assert by_symbol["IFB1"].market == "IFB"
    assert by_symbol["BASE1"].market == "IFB_BASE"
    assert "UNKNOWN1" not in by_symbol


def test_query_symbols_filters_by_market_across_all_three_markets(monkeypatch):
    universe = [
        MarketSymbol(code="1", symbol="TSE1", name="TSE Co", market="TSE", flow=1,
                     industry_code="27", paper_type="300"),
        MarketSymbol(code="2", symbol="IFB1", name="IFB Co", market="IFB", flow=2,
                     industry_code="27", paper_type="300"),
        MarketSymbol(code="3", symbol="BASE1", name="Base Co", market="IFB_BASE", flow=4,
                     industry_code="27", paper_type="300"),
    ]
    monkeypatch.setattr(su, "fetch_symbol_universe", lambda: universe)

    for market, expected_symbol in (("TSE", "TSE1"), ("IFB", "IFB1"), ("IFB_BASE", "BASE1")):
        result = su.query_symbols(market=market)
        assert [item.symbol for item in result] == [expected_symbol]


def _synthetic_fundamentals(**overrides) -> CodalFundamentals:
    defaults = dict(
        symbol="SYM",
        revenue_current=120.0,
        revenue_prev=100.0,
        net_profit_current=15.0,
        net_profit_prev=10.0,
        revenue_yoy_pct=20.0,
        net_margin_pct=12.5,
        net_margin_prev_pct=10.0,
        audit_opinion="unqualified",
        related_party_flags=0,
    )
    defaults.update(overrides)
    return CodalFundamentals(**defaults)


def test_recommendation_pipeline_handles_a_representative_symbol_from_each_market(monkeypatch):
    # The recommendation pipeline (company_builder -> agents -> kiasha) takes
    # a resolved quote, not a market segment -- so this isn't testing market
    # *routing*, it's a regression net catching the case where someone adds
    # market-type-conditional logic later and it silently breaks for two of
    # the three segments. Exercises real TSE/IFB/IFB_BASE-representative
    # symbols end to end with no live network access.
    monkeypatch.setattr(company_builder, "metadata_for_symbol", lambda symbol: None)
    monkeypatch.setattr(
        company_builder, "scoped_fundamentals_for_symbol",
        lambda symbol: (_synthetic_fundamentals(symbol=symbol), "standalone"),
    )
    monkeypatch.setattr(
        company_builder, "fetch_extended_market_data",
        lambda code: ExtendedMarketData(
            day_low=900, day_high=1050, volume_today=500_000, trade_value_today=1.2e9,
            trade_count_today=1200, avg_volume_30d=400_000, price_52w_high=1200,
            price_52w_low=800, estimated_eps=95, eps_value=90, pe=11.1, sector_pe=13.4,
            shares_outstanding=1_000_000_000, market_cap=1.0e12, base_volume=350_000,
            sector_code="27", sector_name="Sample sector", market_flow=1, market_title="Sample",
        ),
    )

    representative_quotes = [
        LiveQuote(code="1", name="TSE1", last_price=1000, closing_price=990,
                   yesterday_price=980, change=20, change_percent=2.04),
        LiveQuote(code="2", name="IFB1", last_price=1000, closing_price=990,
                   yesterday_price=980, change=20, change_percent=2.04),
        LiveQuote(code="3", name="BASE1", last_price=1000, closing_price=990,
                   yesterday_price=980, change=20, change_percent=2.04),
    ]

    for quote in representative_quotes:
        company = company_builder.build_company_from_quote(quote)
        decision = decide(company)

        assert decision.call in {"BUY", "HOLD", "SELL"}
        assert -1.0 <= decision.weighted_score <= 1.0
        assert len(run_team(company)) == 6


# Found live on the same crash: /stock/recommendation/{code} is also called
# with a Persian company symbol (the CODAL-only fallback path is designed for
# exactly that), and find_quote() always tries the TSETMC numeric-code
# endpoint first regardless, which used to crash with an unhandled
# UnicodeEncodeError instead of failing gracefully into that fallback.
# Fixed with an explicit numeric-code guard (_is_tsetmc_instrument_code) in
# market_data.py; see test_market_data_identifiers.py for that regression
# coverage rather than duplicating it here.


def test_numeric_code_lookup_passes_persian_ticker_to_codal_enrichment(monkeypatch):
    # api_server._company_or_404 used to forward the raw numeric TSETMC code
    # (the URL path segment, e.g. "46348559193224090") straight through as the
    # CODAL search symbol instead of the resolved quote's Persian ticker name.
    # CODAL only indexes issuers by their Persian symbol, so every
    # numeric-code lookup -- the normal way /stock/recommendation/{code} is
    # called -- silently got codal_metadata/codal_fundamentals back as None
    # (dataAvailability.codal: false) even though live CODAL data existed.
    # Fixed by passing quote.name explicitly; this locks that in so it can't
    # silently regress back to passing the raw path code.
    quote = LiveQuote(
        code="46348559193224090", name="فولاد", last_price=2698.0,
        closing_price=2697.0, yesterday_price=2620.0, change=0.0, change_percent=2.94,
    )
    monkeypatch.setattr(api_server, "find_quote", lambda code: quote)

    captured = {}

    def fake_build_company_from_quote(q, *, codal_symbol=None):
        captured["codal_symbol"] = codal_symbol
        return {"ticker": q.code, "name_fa": q.name}

    monkeypatch.setattr(api_server, "build_company_from_quote", fake_build_company_from_quote)

    company, source = api_server._company_or_404(quote.code)

    assert source == "live"
    assert company == {"ticker": quote.code, "name_fa": quote.name}
    assert captured["codal_symbol"] == "فولاد"
    assert captured["codal_symbol"] != quote.code
