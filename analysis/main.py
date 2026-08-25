"""
BIAP pipeline prototype (local, mock data):

  CODAL + TSETMC (mock) -> BIAP backend (in-memory dict, no persistence yet)
    -> BIAP agent team -> Kiasha decision layer -> console "dashboard"

Real gaps this stands in for, per the architecture discussion:
  - CODAL/TSETMC ingestion is unresolved (scrape vs official API, unknown)
  - No real backend/persistence yet
  - No broker execution API confirmed for Iranian markets -> this only
    ever prints a recommendation, it never places an order
"""

import json

from data_sample import SAMPLE_COMPANY
from kiasha import decide


def render(company: dict) -> None:
    decision = decide(company)

    print(f"\n=== BIAP / Kiasha — {company['name_en']} ({company['ticker']}) ===")
    print(f"[MOCK DATA — not live CODAL/TSETMC]\n")

    print(f"Call: {decision.call}   (blended score {decision.weighted_score:+.2f})")
    print(f"{decision.explanation}\n")

    print("Team breakdown:")
    for e in decision.breakdown:
        print(
            f"  - {e['agent']:<12} vote={e['vote']:+.2f}  "
            f"conf={e['confidence']:.2f}  trust={e['trust_score']:.2f}  "
            f"maturity={e['maturity']:<10}  weight={e['weight_normalized']:.0%}"
        )
        print(f"      -> {e['reasoning']}")

    print("\nRaw JSON (would feed the BIAP dashboard widget):")
    print(json.dumps({
        "ticker": company["ticker"],
        "call": decision.call,
        "score": decision.weighted_score,
        "breakdown": decision.breakdown,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    render(SAMPLE_COMPANY)
