"""BIAP adapter for the canonical DMA Decision Agent 9.

The formulas, Altman zones and Damodaran-style synthetic rating bands are kept
aligned with XS227/dma-agent/decision_pipeline_ext.py. BIAP adds only one
application-specific behavior: a severe distress result may block a NEW
positive investment call; Agent 9 still never creates BUY/SELL by itself.
"""
from __future__ import annotations

from math import exp
from typing import Optional

from .models import DistressAssessment, GlobalCompany


_SYNTHETIC_RATING_TABLE = [
    (8.5, "AAA", 0.005),
    (6.5, "AA", 0.007),
    (5.5, "A+", 0.009),
    (4.25, "A", 0.011),
    (3.0, "A-", 0.013),
    (2.5, "BBB", 0.017),
    (2.25, "BB+", 0.025),
    (2.0, "BB", 0.032),
    (1.75, "B+", 0.045),
    (1.5, "B", 0.060),
    (1.25, "B-", 0.080),
    (0.8, "CCC", 0.120),
    (0.5, "CC", 0.180),
    (0.2, "C", 0.250),
    (float("-inf"), "D", 0.350),
]


def _is_financial(company: GlobalCompany) -> bool:
    text = " ".join(filter(None, (company.sector, company.industry))).lower()
    tokens = (
        "bank", "banking", "insurance", "financial", "capital markets",
        "broker", "asset management", "credit services", "mortgage",
    )
    return any(token in text for token in tokens)


def _logistic(value: float) -> float:
    value = max(-60.0, min(60.0, float(value)))
    return 1.0 / (1.0 + exp(-value))


def synthetic_credit_rating(icr: float) -> tuple[str, float]:
    """Canonical rounded illustrative bands from dma-agent Agent 9."""
    for minimum, rating, spread in _SYNTHETIC_RATING_TABLE:
        if icr >= minimum:
            return rating, spread
    return "D", 0.350


def distress_agent(company: GlobalCompany) -> DistressAssessment:
    """Run the canonical Agent-9 diagnostics without guessing missing inputs."""

    hard_reasons: list[str] = []
    if company.total_equity is not None and company.total_equity < 0:
        hard_reasons.append("negative total equity")

    event_text = " ".join(
        [company.audit_opinion or "", *[str(item) for item in company.material_event_flags]]
    ).lower()
    if "going concern" in event_text:
        hard_reasons.append("going-concern warning")

    # The canonical models are corporate distress models. BIAP keeps its
    # sector guard for banks/insurers rather than pretending those ratios are
    # directly comparable.
    if _is_financial(company):
        return DistressAssessment(
            status="NOT_APPLICABLE",
            positive_block=bool(hard_reasons),
            reasoning="; ".join(
                hard_reasons
                + ["generic corporate distress models suppressed for financial-sector issuer"]
            ),
        )

    missing: list[str] = []
    available_models: list[str] = []
    reasons: list[str] = list(hard_reasons)

    # Zmijewski (1984): exact canonical formula.
    zmijewski_index: Optional[float] = None
    distress_probability: Optional[float] = None
    if (
        company.net_income is not None
        and company.total_assets not in (None, 0)
        and company.total_liabilities is not None
        and company.current_assets is not None
        and company.current_liabilities not in (None, 0)
    ):
        ni_ta = float(company.net_income) / float(company.total_assets)
        tl_ta = float(company.total_liabilities) / float(company.total_assets)
        ca_cl = float(company.current_assets) / float(company.current_liabilities)
        zmijewski_index = -4.3 - 4.5 * ni_ta + 5.7 * tl_ta - 0.004 * ca_cl
        distress_probability = _logistic(zmijewski_index)
        available_models.append("zmijewski")
        reasons.append(
            f"Zmijewski P(distress)={distress_probability:.3f} "
            f"({'distress-likely' if distress_probability >= 0.5 else 'distress-unlikely'})"
        )
    else:
        for field_name, value in (
            ("net_income", company.net_income),
            ("total_assets", company.total_assets),
            ("total_liabilities", company.total_liabilities),
            ("current_assets", company.current_assets),
            ("current_liabilities", company.current_liabilities),
        ):
            required_nonzero = field_name in {"total_assets", "current_liabilities"}
            if value is None or (required_nonzero and value == 0):
                missing.append(f"zmijewski:{field_name}")

    # Altman Z'' (1995/2000): exact canonical formula/zones.
    altman_score: Optional[float] = None
    altman_zone: Optional[str] = None
    ebit = company.operating_income
    if (
        company.current_assets is not None
        and company.current_liabilities is not None
        and company.retained_earnings is not None
        and ebit is not None
        and company.total_assets not in (None, 0)
        and company.total_equity is not None
        and company.total_liabilities not in (None, 0)
    ):
        wc = float(company.current_assets) - float(company.current_liabilities)
        assets = float(company.total_assets)
        liabilities = float(company.total_liabilities)
        altman_score = (
            6.56 * (wc / assets)
            + 3.26 * (float(company.retained_earnings) / assets)
            + 6.72 * (float(ebit) / assets)
            + 1.05 * (float(company.total_equity) / liabilities)
        )
        altman_zone = "SAFE" if altman_score > 2.6 else "GREY" if altman_score >= 1.1 else "DISTRESS"
        available_models.append("altman_z_double_prime")
        reasons.append(f"Altman Z''={altman_score:.3f} ({altman_zone.lower()})")
    else:
        for field_name, value in (
            ("retained_earnings", company.retained_earnings),
            ("operating_income", ebit),
            ("total_assets", company.total_assets),
            ("total_liabilities", company.total_liabilities),
            ("total_equity", company.total_equity),
            ("current_assets", company.current_assets),
            ("current_liabilities", company.current_liabilities),
        ):
            required_nonzero = field_name in {"total_assets", "total_liabilities"}
            if value is None or (required_nonzero and value == 0):
                missing.append(f"altman:{field_name}")

    # ICR + canonical rounded Damodaran synthetic rating table.
    interest_coverage: Optional[float] = None
    rating: Optional[str] = None
    default_spread: Optional[float] = None
    if ebit is not None and company.interest_expense not in (None, 0):
        interest_coverage = float(ebit) / float(company.interest_expense)
        rating, default_spread = synthetic_credit_rating(interest_coverage)
        available_models.append("interest_coverage")
        reasons.append(
            f"synthetic credit rating≈{rating} "
            f"(ICR={interest_coverage:.2f}x, default spread≈{default_spread:.3f})"
        )
    else:
        if ebit is None:
            missing.append("interest_coverage:operating_income")
        if company.interest_expense in (None, 0):
            missing.append("interest_coverage:interest_expense")

    # Canonical Agent 9 calls p>=0.5 distress-likely and Altman <1.1 distress.
    # BIAP uses those same published/canonical boundaries for the safety gate.
    severe = bool(hard_reasons)
    elevated = False
    if distress_probability is not None:
        if distress_probability >= 0.5:
            severe = True
        elif distress_probability >= 0.35:
            elevated = True
    if altman_zone == "DISTRESS":
        severe = True
    elif altman_zone == "GREY":
        elevated = True
    if interest_coverage is not None:
        if interest_coverage < 1.0:
            severe = True
        elif interest_coverage < 1.5:
            elevated = True

    if severe:
        status = "HIGH_RISK"
    elif elevated:
        status = "ELEVATED_RISK"
    elif available_models:
        status = "LOW_RISK"
    else:
        status = "INSUFFICIENT_DATA"

    return DistressAssessment(
        status=status,
        positive_block=severe,
        zmijewski_index=zmijewski_index,
        distress_probability=distress_probability,
        altman_z_double_prime=altman_score,
        altman_zone=altman_zone,
        interest_coverage=interest_coverage,
        synthetic_credit_band=rating,
        approx_default_spread=default_spread,
        available_models=tuple(available_models),
        missing_inputs=tuple(dict.fromkeys(missing)),
        reasoning="; ".join(reasons) or "insufficient verified inputs for distress models",
    )
