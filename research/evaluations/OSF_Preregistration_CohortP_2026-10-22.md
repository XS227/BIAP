# BIAP Global — Cohort P OSF preregistration tracking

**Recorded:** 2026-10-22  
**Status (last user-visible OSF screenshot):** Submitted; **pending approval**. Do not mark as approved or archived without a subsequent OSF confirmation.  
**OSF registration page:** https://osf.io/6p8y7/overview  
**Visibility requested at submission:** Embargo, scheduled to end **2027-04-27** (subject to OSF approval and any later authorized change).

## Scope of the preregistered study

- **Title:** Prospective evaluation of an evidence-gated multi-agent equity screening system (BIAP Global): BUY versus SELL baskets across ten national markets.
- **Frozen cohort:** Cohort P, 2026-10-20. Original decisions: **964** (445 BUY, 519 SELL). Priced initial positions reported: **941** (442 BUY, 499 SELL); **23** initially unpriced.
- **German cross-listing rule:** ISIN deduplication; **43** overlapping German issuer decisions counted once, on Xetra in the frozen cohort, yielding **921 issuer-level decisions** (429 BUY, 492 SELL).
- **Primary endpoint:** One-month (20 November 2026) local-currency total-return BUY-minus-SELL spread; unweighted mean of eligible venue-level spreads across **12 prespecified trading venues**, with US NASDAQ and NYSE separate and DE Xetra and Frankfurt separate. Venues need priced BUY and SELL holdings to contribute. Run after the horizon close is final, on or after **2026-11-21**.
- **Secondary horizons:** Three and six months; reporting and sensitivity methods are detailed in the OSF form and attached protocol.
- **Study category:** Observational, non-randomized, paper portfolio; no actual trades.

## Provenance and safeguards

- Registration was submitted on **2026-10-22**, *after* the 20 October cohort freeze and *before* the prespecified one-month outcome evaluation. Prior access to frozen decisions and decision-time summaries is disclosed in the preregistration.
- The OSF submission included a protocol PDF titled `BIAP_CohortP_Prospective_Protocol...`. The user-provided reviewed corrected protocol copy from 2026-10-22 has SHA-256 `47a9d62ded32a6b535ac0149eacbe6ec914b34829d6ecdced51bc2ac931e3d77`; the exact hash of the OSF-hosted attachment has **not** been independently verified.
- Source provenance referenced in the protocol: portfolio tag `paper-portfolio-2026-10-20`; evaluation code `research/paper_portfolio_returns.py` at commit `5f60385e5b46d251ee2180cfcdc160c3b721dbc6`. These are historical references, not new modifications.
- **This file is only an internal BIAP research-tracking pointer**, not a replacement for the OSF registration or a change to its archived protocol. The frozen portfolio, decision labels, research datasets, production, and evaluation rules must not be modified as part of this note.
- Until the OSF state changes from **Pending approval** to approved/embargoed, do not describe the preregistration as fully approved, DOI-issued, or publicly readable. The planned embargo should be respected in journal communications.
- Any future new-market expansion (starting with **Switzerland and Denmark**) must use a separate cohort/experiment; **do not retroactively insert them into Cohort P or alter its preregistered 10-country/12-venue scope**.
