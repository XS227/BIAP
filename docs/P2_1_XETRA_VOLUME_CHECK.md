# P2.1 — Xetra volume field check (2026-11-02)

Question (from P1.12): 30.6 % of DE names sit under 0.02 %/day turnover and 49 % under EUR 100k/day. Is the volume field wrong (venue-only or partial) or is that real?

## Method
- Source under test: `avg_volume_30d` x `price` in the DE:XETRA ledger (408 rows, scan of 30 Oct). It comes from the Yahoo public chart (30-bar mean).
- Reference: Deutsche Boerse's official MiFIR delayed post-trade file `DETR-posttrade-daily-2026-10-30.json.gz` (the source `xetra_delayed.py` already uses for stage-one liquidity), aggregated per ISIN with the existing `aggregate_xetra_posttrade` (modification/cancellation prints excluded). 407 of 408 ISINs found. Read-only public download.

## Result
- Per-name ratio (one-day official turnover / Yahoo 30-day mean turnover), 362 names with both: p10 0.14, **median 0.89**, p90 2.25. Day-to-day variation, no systematic scale error.
- Large caps match closely: SAP EUR 431M official vs 411M Yahoo; Siemens 263M vs 243M; Allianz 185M vs 208M; Siemens Energy 361M vs 259M.
- On the official file alone, 203 of 407 names traded under EUR 100k on the day (Yahoo-based: 201 of 408 under 100k/30-day mean). The two sources agree.
- Under-100k names are small: median market cap EUR 46M. The ten above EUR 500M are closely held (EnBW, MVV Energie, Nuernberger Beteiligungs, Hamburger Hafen, Rhoen-Klinikum, KSB ...), i.e. a small free float, not a data error.

## Conclusion
- The field is correct for what it measures: **volume on the Xetra venue**. It is not consolidated across Tradegate, Frankfurt floor, Lang & Schwarz, Gettex etc., so small-cap tradability across all German venues is higher than shown. For a Xetra-listed rating the venue figure is the defensible one; the app should say "Xetra volume".
- Gate enabled for DE (changelog 2026-11-02 P2.1 / P1.12), v2 only. Effect: Xetra BUY/ACCUMULATE names under USD 100k/day are capped at HOLD ("low liquidity").
- Optional follow-up for the owner: a consolidated-volume source (needs a licence, P2.6) would remove the venue caveat.
