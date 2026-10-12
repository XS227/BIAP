# BIAP Global — session 8 audit (2026-10-12)

## Committed in this session
Persistent analysis queue replacing the hidden `deepLimit` cap: `analysis_ledger` (SQLite, per market,
audited status/reason/source per company), `analysis_worker` + systemd timer (drains every market,
one fresh interpreter per market), `GET /global/analysis-ledger`, interactive `/global/scan` bounded
by `batchLimit` / time budget (legacy `deepLimit` still accepted), OAM/ESEF scratch ZIP cleanup,
B3 official-source fixes. No verdict was relaxed; no WARN was converted to PASS.

## Verification
- `pytest -k global`: 706 passed.
- Isolated instance (port 8191, throw-away data dir): NO/EURONEXT_OSLO scan with batchLimit=3 returned in ~49 s,
  ledger registered 146 companies (143 PENDING, 3 COMPLETE), `/global/analysis-ledger` served counts and rows.
- Live prod API (b883fcc) `/global/analyze`, 12 representative issuers:

| Issuer | Call | Fundamentals | Gaps |
|---|---|---|---|
| NO EQNR | NO_RECOMMENDATION (conf 0.50 < 0.55) | official OAM, 16 fields | gross_profit, ebitda, current assets/liabs |
| NO DNB | NO_RECOMMENDATION (0.45) | official OAM, 12 | bank-type statement gaps |
| SE VOLV-B | HOLD_OR_WATCH, ACCEPT (0.63) | official OAM, 20 | none |
| SE ERIC-B | HOLD_OR_WATCH, ACCEPT (0.56) | official OAM, 19 | ebitda |
| GB SHEL / AZN | NO_RECOMMENDATION (0.46 / 0.51) | official OAM, 16 / 19 | SHEL: gross/operating/ebitda/FCF |
| US AAPL / JPM | NO_RECOMMENDATION (agent disagreement, distress) | SEC XBRL, 19 / 12 | JPM: bank-type gaps |
| FR MC, IT ENEL | NO_RECOMMENDATION | official, 17 / 16 | ebitda etc. |
| DE SAP / SIE | NO_RECOMMENDATION (ABSTAIN / REVIEW) | issuer press/IR figures, **7 fields only** | no balance sheet |

## Remaining issues (not fixed; need a legitimate source)
1. **Germany**: SAP and Siemens have no ESEF package in the reviewed registry (`de_issuer_esef.json`, 10 issuers).
   sap.com answers automated requests with HTTP 403; Unternehmensregister robots.txt forbids automation. The
   `biap-global-de-fundamentals` worker fails 20/20 per run (resolved 0). Not worked around.
2. EBITDA is never reported directly; deriving it needs D&A tagged evidence per issuer.
3. Governance ABSTAIN/REVIEW on large caps is confidence/disagreement driven, by design.
4. Disk 93% (3.8 GB free): `/var/log/journal` 1.8 GB needs `sudo journalctl --vacuum-size`; stale worktrees under
   `biap-global/wt-*` (two dirty) and `staging-1012` (in use by pid 728216) left untouched.
5. Real-device test of the APK is still pending.
