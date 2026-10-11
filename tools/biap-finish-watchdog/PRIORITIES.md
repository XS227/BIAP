# BIAP Global finish job — priority order (updated 2026-10-11 by user request)

Work markets in this order. Do not start a lower tier before the higher tiers are
fixed or documented as blocked with evidence:

1. Germany (DE) filing coverage: official ESEF/annual-report filings
   (de_issuer_esef.json registry, issuer sites, filings.xbrl.org; never scrape Unternehmensregister).
2. Italy (IT) filing coverage.
3. Nordic filing coverage: Norway (NO), Sweden (SE), Denmark (DK), Finland (FI), Iceland (IS).
4. UK, USA.
5. Lower-priority markets: Australia, Turkey, then everything else (still excluding Iran and Japan).

Exit criteria, recorded in CHECKPOINT.md: for each market, per-sample PASS/WARN/BLOCK counts, sources and commits.
When EVERYTHING is finished and verified (report pushed, CI green, prod health on the
deployed commit, APK built if triggered), add this exact line to
/home/ubuntu/biap-global/session-1011-final/CHECKPOINT.md:
WATCHDOG_STATUS: COMPLETE
If the job is finished but blocked (needs user action), add instead:
WATCHDOG_STATUS: BLOCKED <reason>
