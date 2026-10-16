# DE peer rebuild E4: option E issuer by issuer (2026-10-16)

Official filings were read transiently (downloaded to scratch, text-extracted, deleted); nothing but metadata is stored
(`DE_PEER_EVIDENCE_E4_2026-10-16.json`: ISIN, URL, period end, sha256, match flags). 15 % threshold unchanged. No ledger, ESEF archive,
DMA agent or backup touched; all gate runs are dry-runs against an isolated sqlite copy. Nothing merged, deployed or restarted.

## Gate results (dry run, offline quotes, evidence E + E2 + E3 + E4)

| Gate | Start of day | After E3 | After E4 | Filing-dimension limit | Other gate checks | Result |
|---|---|---|---|---|---|---|
| DE:XETRA | 78.9 % excluded (105/133) | 39.8 % (53) | **12.8 % (17/133)** | <=15 % PASS | coverage 87.2 %, P/E ret. 89.0 %, P/B ret. 85.95 % (>=85) | **DRY_RUN_OK (PASS)** |
| DE:FRANKFURT | 73.9 % (85/115) | 42.6 % (49) | **13.9 % (16/115)** | <=15 % PASS | P/B retention **82.1 % < 85 %** | **REJECTED (FAIL)** |

XETRA passes every dry-run check. This is a dry run only: `replaced=false`, no cache or live benchmark was written, and no BUY decision was changed. Production still serves the old benchmark until an approved deploy + reprice.
FRANKFURT clears the 15 % filing gate but still fails closed on **P/B row retention (82.1 %, needs 85 %)**: 16 excluded peers include P/B-bearing rows.

## Verified issuers (E4: 46 by the automatic matcher + LEG by manual reconciliation = 47)
| ISIN | Issuer (ledger name) | Markets | Period end | Source host | sha256 (first 12) |
|---|---|---|---|---|---|
| DE000A1PHFF7 | HUGO BOSS AG NA O.N. | XETRA/FRANKFURT | 2025-12-31 | annualreport.hugoboss.com | bbb7392e91fd |
| DE0006458003 | LECHWERKE AG | FRANKFURT | 2025-12-31 | www.hauptversammlung.de | 9e1a975e86a6 |
| DE0006916604 | PFEIFFER VACUUM TECH.O.N. | XETRA/FRANKFURT | 2025-12-31 | s1.q4cdn.com | 2157a5da90b8 |
| DE0006083405 | HORNBACH HOLD.ST O.N. | XETRA/FRANKFURT | 2026-02-28 | www.hauptversammlung.de | a2151d481da6 |
| DE000A2YN900 | TEAMVIEWER SE  INH O.N. | XETRA | 2025-12-31 | ir-api.eqs.com | 687515905579 |
| DE0006200108 | INDUS HOLDING AG | XETRA/FRANKFURT | 2025-12-31 | www.hauptversammlung.de | a17a3893dc86 |
| DE0006052830 | MASCH.BERT.HER. O.N. VZO | FRANKFURT | 2025-12-31 | www.hermle.de | 4fb6123a90c0 |
| DE0005653604 | MEDNATION AG INH O.N. | XETRA | 2025-12-31 | mednation.de | 01ff7cf0131f |
| DE000A0LBFE4 | MEVIS MEDICAL SOL.NA O.N. | XETRA/FRANKFURT | 2025-09-30 | www.mevis.de | a9d9d8739a2b |
| DE000A40ZW88 | THE PLATFORM GROUP NA ON | XETRA/FRANKFURT | 2025-12-31 | www.hauptversammlung.de | e42a167a25d8 |
| DE0007857476 | KLASSIK RADIO AG NA O.N. | XETRA/FRANKFURT | 2025-12-31 | assets.ctfassets.net | 703c9e20c34a |
| DE0005580005 | DIERIG HOLDING AG O.N. | FRANKFURT | 2025-12-31 | www.dierig.de | f70c23fb5d15 |
| DE000A168205 | SHAREHOLD.VAL.BET.NA O.N. | XETRA/FRANKFURT | 2025-12-31 | svb-ag.de | c89c03bc32e2 |
| DE0006627201 | MUEHLBAUER HOLD.AG O.N. | XETRA/FRANKFURT | 2025-12-31 | www.muehlbauer.de | 015ce386df12 |
| DE000A1TNWJ4 | MPC OCEANIC GROUP AG | XETRA/FRANKFURT | 2025-12-31 | www.mpc-oceanic.com | c51b2e2e7caf |
| DE000A0S9QZ8 | STOCK3 AG  NA O.N. | XETRA/FRANKFURT | 2025-12-31 | inside.stock3.com | 82454827a0f0 |
| DE000A2E4SV8 | CYAN AG  INH O.N. | XETRA/FRANKFURT | 2025-12-31 | ir.cyansecurity.com | e070bd67deec |
| DE0005403901 | CEWE STIFT.KGAA  O.N. | XETRA/FRANKFURT | 2025-12-31 | ir-api.eqs.com | a80dad2102c0 |
| DE0005659700 | ECKERT+ZIEGLER  INH O.N. | XETRA | 2025-12-31 | ir-api.eqs.com | 83a1f460e960 |
| DE000PAT1AG3 | PATRIZIA SE NA O.N. | XETRA | 2025-12-31 | ir-api.eqs.com | 621d9ea166a2 |
| DE000A42FR12 | SMAG MOB.ANT.MASTS INH ON | XETRA | 2025-12-31 | www.smag.de | 925fc2dcf54c |
| DE000A0HL8N9 | 2G ENERGY AG | XETRA | 2025-12-31 | 2-g.com | aca0072b1f6b |
| DE000A3E5C24 | MHP HOTEL AG INH O.N. | XETRA/FRANKFURT | 2025-12-31 | www.mhphotels.com | 67203582e10b |
| DE0007229007 | SCHLOSS WACHENHEIM AG O.N | XETRA/FRANKFURT | 2026-06-30 | www.schloss-wachenheim.com | 877918f8f194 |
| DE000A420ZL4 | ELECTROVAC AG | XETRA/FRANKFURT | 2026-03-31 | www.electrovac.com | a6102ec87aae |
| DE0007600108 | VALORA EFFEK.HAND.O.N. | FRANKFURT | 2025-12-31 | veh.de | 0932afcfa3ec |
| DE000ZEAL241 | ZEAL NETWORK SE NA O.N. | XETRA/FRANKFURT | 2025-12-31 | www.lobbyregister.bundestag.de | c79f2700aa3f |
| DE000A2DAM03 | AUMANN AG  INH O.N. | XETRA/FRANKFURT | 2025-12-31 | ir-api.eqs.com | 9f7ea81cf124 |
| DE0005492938 | MASTERFLEX O.N. | FRANKFURT | 2025-12-31 | ir-api.eqs.com | f408a7524040 |
| DE000A0JM2M1 | BLUE CAP             O.N. | XETRA/FRANKFURT | 2025-12-31 | www.hauptversammlung.de | e341c865c603 |
| DE0005405104 | INNOTEC TSS AG | FRANKFURT | 2025-12-31 | www.hauptversammlung.de | 8384dc6fd47a |
| DE0008055021 | DT.REAL ESTATE AG O.N. | FRANKFURT | 2025-12-31 | www.hauptversammlung.de | 0690553d3ead |
| DE0005408686 | OEKOWORLD AG VZNA O.N. | XETRA/FRANKFURT | 2025-12-31 | www.hauptversammlung.de | 4e74a362a0cb |
| DE000A13SUL5 | DEFAMA AG | FRANKFURT | 2025-12-31 | www.hauptversammlung.de | 73d99357e88e |
| DE000A255F11 | FR.VORWERK GRP SE INH ON | XETRA | 2025-12-31 | www.friedrich-vorwerk-group.de | 009fe5bbfaca |
| DE000A0Z23Q5 | ADESSO SE  INH O.N. | XETRA | 2025-12-31 | www.adesso-group.de | 1d8dcd653cb8 |
| DE0006569403 | ALBIS LEASING AG O.N. | XETRA | 2025-12-31 | xozalbisassets.blob.core.windows.net | ac1a31d739a4 |
| DE000A40ET13 | AUDIUS SE  NA O.N. | XETRA | 2025-12-31 | www.audius.de | cccd4e47a328 |
| DE000A0MZ4B0 | DELIGNIT AG      INH.O.N. | XETRA | 2025-12-31 | ir-api.eqs.com | 65fec57230e9 |
| DE0006069008 | FROSTA AG AKT. O.N. | FRANKFURT | 2025-12-31 | www.frosta-ag.com | 60c398bfd957 |
| DE000A3DRAE2 | SMT SCHARF AG NA O.N. | XETRA | 2025-12-31 | www.hauptversammlung.de | 8bb47cd53a00 |
| DE0005754402 | LS TELCOM AG | XETRA/FRANKFURT | 2025-09-30 | ir-api.eqs.com | c6ad5d8066a5 |
| DE000A3ENQ51 | SCHOTT PHARMA INH O.N. | XETRA/FRANKFURT | 2025-09-30 | ir.schott-pharma.com | e85f9e640f80 |
| DE0006201403 | PEH WERTPAPIER AG | FRANKFURT | 2025-12-31 | www.peh.de | c265ef961667 |
| DE0007448508 | IVU TRAFFIC TECHN.AG O.N. | XETRA/FRANKFURT | 2025-12-31 | www.ivu.com | e77b32347e42 |
| DE000A3E5E55 | RINGMETALL SE  NA O.N. | XETRA/FRANKFURT | 2025-12-31 | ringmetall.de | 82c3096dc1e0 |
| DE000LEG1110 | LEG IMMOBILIEN SE NA O.N. | XETRA | 2025-12-31 | ir.leg-se.com | cf3d3e4fae3f |

LEG (DE000LEG1110) is verified by **manual reconciliation**, not the automatic matcher: stored revenue 1,579.1m equals the revenue note components 1,377.3 (rental) + 187.8 (disposal of investment property) + 14.0 (other services); net income 1,458.2m is printed as attributable to shareholders. (The earlier "1,566m" is the sustainability-report revenue by value chain, a different scope.)

## Issuers examined and NOT verified (exact blocker, nothing substituted)
| Issuer | Finding / blocker |
|---|---|
| Vonovia (DE000A1ML7J1) | Filing prints revenue from property management 5,087.3m (letting 4,880.5m); stored 5,061.3m is not printed. Definition/line-item mismatch; correction needs owner choice of revenue definition. |
| Deutsche Beteiligungs AG (DE000A1TNUT7) | Stored NI 26.4m = Konzern-Gesamtergebnis (26,397 TEUR); Konzernergebnis is 24,698 TEUR; no revenue field exists for the investment company. Wrong line item mapped; stays excluded. |
| Berliner Effektengesellschaft (DE0005221303) | Group report: net income matches, stored revenue is None (financial company has no revenue line). Excluded until a revenue-less policy is decided; earlier HGB single-entity document did not match. |
| Scherzer & Co (DE0006942808) | Group report net income matches; stored revenue is 10,000 EUR, which is not in the filing. Provider data error. |
| Evonik (DE000EVNK013), Bilfinger (DE0005909006) | Official PDF found but issuer robots.txt disallows the path; not fetched (verifier policy). |
| thyssenkrupp nucera (DE000NCA0001) | Annual Report 2024/25 PDF not locatable on the IR site (only the sustainability extract). |
| Vincorion (DE000VNC0014) | ESEF zip contains single-entity statements only (VISE Abschluss), not the group; stored group figures not printed. |
| Hyrican (DE0006004500) | Jahresabschluss PDF found; neither period phrase nor stored figures match (stored row likely different basis). |
| B+S Banksysteme (DE0001262152) | FY 2024/25 report: stored revenue 13.24m vs reported 12.6m; no match. FY 2025/26 report due 2026-09-30, not located. |
| DN Group, Netfonds, ADM Hamburg, SM Wirtschaftsberatung, Helios Solar, Webac, Pittler, 029 Group, ARI Motors, GBS Software, Solutiance, others | No official 2025 filing URL found (or only HGB single-entity/press releases). Not attempted further. |
| Ceconomy, Nagarro, Commerzbank, Delivery Hero ("Z.VERK." lines), Pferdewetten, Energenta, Philion, A.I.S., Euwax | No fundamentals at all; the four "Z.VERK." lines are temporary tender-offer lines of existing issuers, not independent peers. Recommend excluding such lines from the peer set (a code change that alters the gate denominator, left for owner review). |

## Software fixes in this change
* `de_peer_doc_verify.py`: rounded-TEUR matcher (E3, earlier), plus ESEF-zip text extraction (xhtml and PDF members).
* Tests: `analysis/tests/test_de_peer_doc_verify_rounding.py` (6 tests).

## Open decisions / next steps
1. FRANKFURT needs P/B retention >= 85 %: about 3-4 more P/B-bearing excluded peers verified (candidates: Netfonds, ADM Hamburg, DN Group, Scherzer revenue correction, Berliner Effektengesellschaft revenue-less policy).
2. Owner policy: revenue-less financial/holding issuers (BFV, DBAG); excluding "Z.VERK." tender lines.
3. Production deploy + reprice of the XETRA benchmark remains an approval-gated step; this change does not touch it.
