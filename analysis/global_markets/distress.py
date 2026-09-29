"""Independent financial-distress and credit-risk sidecar for BIAP Global.

This module is deliberately not a directional investment agent. It reports
published/transparent solvency diagnostics and may block a new positive
recommendation when severe distress evidence contradicts the scoring agents.
It never creates BUY/SELL calls on its own.
"""
from __future__ import annotations

from math import exp
from typing import Optional

from .models import DistressAssessment, GlobalCompany


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


def _synthetic_credit_band(interest_coverage: float) -> str:
    """Coarse internal band, intentionally not presented as an agency rating."""
    if interest_coverage >= 8.0:
        return "STRONG"
    if interest_coverage >= 4.0:
        return "INVESTMENT_GRADE_LIKE"
    if interest_coverage >= 2.0:
        return "ADEQUATE"
    if interest_coverage >= 1.5:
        return "SPECULATIVE"
    if interest_coverage >= 1.0:
        return "WEAK"
    return "DISTRESSED"


def distress_agent(company: GlobalCompany) -> DistressAssessment:
    """Compute independent distress diagnostics without inventing inputs.

    Zmijewski uses the published index and reports a logistic transform as an
    applied probability-like diagnostic; the original model was estimated with
    a probit link. Altman Z'' is only computed when all required accounting
    inputs exist. Financial-sector issuers are marked not-applicable for these
    generic corporate distress models.
    """

    hard_reasons: list[str] = []
    if company.total_equity is not None and company.total_equity < 0:
        hard_reasons.append("negative total equity")

    event_text = " ".join(
        [company.audit_opinion or "", *[str(item) for item in company.material_event_flags]]
    ).lower()
    if "going concern" in event_text:
        hard_reasons.append("going-concern warning")

    if _is_financial(company):
        return DistressAssessment(
            status="NOT_APPLICABLE",
            positive_block=bool(hard_reasons),
            missing_inputs=(),
            reasoning=(
                "; ".join(hard_reasons + ["generic corporate distress models suppressed for financial-sector issuer"])
            ),
        )

    missing: list[str] = []
    available_models: list[str] = []
    reasons: list[str] = list(hard_reasons)

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
        reasons.append(f"Zmijewski logistic diagnostic={distress_probability:.3f}")
    else:
        for field_name, value in (
            ("net_income", company.net_income),
            ("total_assets", company.total_assets),
            ("total_liabilities", company.total_liabilities),
            ("current_assets", company.current_assets),
            ("current_liabilities", company.current_liabilities),
        ):
            if value in (None, 0) if field_name in {"total_assets", "current_liabilities"} else value is None:
                missing.append(f"zmijewski:{field_name}")

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
        working_capital = float(company.current_assets) - float(company.current_liabilities)
        assets = float(company.total_assets)
        liabilities = float(company.total_liabilities)
        altman_score = (
            6.56 * (working_capital / assets)
            + 3.26 * (float(company.retained_earnings) / assets)
            + 6.72 * (float(ebit) / assets)
            + 1.05 * (float(company.total_equity) / liabilities)
        )
        altman_zone = "SAFE" if altman_score > 2.6 else "GREY" if altman_score >= 1.1 else "DISTRESS"
        available_models.append("altman_z_double_prime")
        reasons.append(f"Altman Z''={altman_score:.3f} ({altman_zone})")
    else:
        for field_name, value in (
            ("current_assets", company.current_assets),
            ("current_liabilities", company.current_liabilities),
            ("retained_earnings", company.retained_earnings),
            ("operating_income", ebit),
            ("total_assets", company.total_assets),
            ("total_equity", company.total_equity),
            ("total_liabilities", company.total_liabilities),
        ):
            if value in (None, 0) if field_name in {"total_assets", "total_liabilities"} else value is None:
                missing.append(f"altman:{field_name}")

    interest_coverage: Optional[float] = None
    credit_band: Optional[str] = None
    if ebit is not None and company.interest_expense not in (None, 0):
        interest = abs(float(company.interest_expense))
        if interest > 0:
            interest_coverage = float(ebit) / interest
            credit_band = _synthetic_credit_band(interest_coverage)
            available_models.append("interest_coverage")
            reasons.append(f"interest coverage={interest_coverage:.2f}x ({credit_band})")
    else:
        if ebit is None:
            missing.append("interest_coverage:operating_income")
        if company.interest_expense in (None, 0):
            missing.append("interest_coverage:interest_expense")

    severe = bool(hard_reasons)
    elevated = False
    if distress_probability is not None:
        if distress_probability >= 0.75:
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
        synthetic_credit_band=credit_band,
        available_models=tuple(available_models),
        missing_inputs=tuple(dict.fromkeys(missing)),
        reasoning="; ".join(reasons) or "insufficient verified inputs for distress models",
    )
