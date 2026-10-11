# SCOPE_DISC addendum A (2026-10-08): DIXSTATE and FIXREV fail the map check - no prereg (MANAGER #58 items 2-3)

Both are map checks in RELFADE's form: counts plus a SYNTHETIC effect. No strategy return was read. Scripts and output:
`C:\EdgeLog\_anatomy_cache\dixstate\map_check.py` and this lane's notes.

## DIXSTATE - SqueezeMetrics DIX (dark-pool short-volume index) -> long 1 ES the next RTH session
- **Data:** TV's photograph `C:\EdgeLog\_research_cache\squeezemetrics\DIX.csv` (sha 64910ffb...), cut at 2025-06-29.
  The state uses the latest DIX dated strictly before the session, ranked in its trailing 252.
- **Counts (WF):**
  - Top tercile: 847 days, 94 a year (2020-21: 39; 2023-24: 43).
  - Top quintile: 60 a year.
  - Top decile: 34 a year, under the count line.
- **Synthetic map:** 1 ES on the state days, holding RTH open -> close. Returns are drawn at random from ALL WF sessions
  (mean 1.6 bps, SD 86.9 bps), de-meaned, plus an assumed edge mu; 2,000 paths.
  - Top tercile: mu 2 bps gives median ROC@$30k 2.6; 5 bps gives 7.7; **10 bps gives 20.4**.
  - Top decile: 10 bps gives 10.4.
- **Read:** ROC 15 needs about 9 bps of excess on every state session. That is 5-6x ES's whole unconditional session
  drift, about 23% a year from one public daily number. The vendor's own claim is a 60-day forward return, which implies
  about 1-3 bps a day, a median ROC of about 1-4. Costs (about 1 bp a round trip) make it worse. **Fails the map; not
  drafted.**

## FIXREV - the London 4pm FX fix on FXE (short the 30 min before, long the 30 min after)
- **Effect (literature):** Krohn, Mueller & Whelan (2024 JF; BoC SWP 2021-48). Around each fix the dollar appreciates
  about 2.5 bps before and gives it back after. Their Sharpe ratios are negative at full transaction costs, even in
  interbank FX. Break-even cost is about 2.5 bps a leg.
- **FXE costs from the bars held:**
  - Abdi-Ranaldo spread on 10:00-12:00 ET 5m bars: 1.06 bps pooled (0.4-2.0 by year), about one 1-cent tick (0.94
    bps at $106).
  - 30% of those bars have high = low.
  - The fix falls at 11:00 ET on 2,106 WF sessions and at 12:00 ET on 154 (the DST-mismatch weeks).
- **First test passes narrowly:** break-even 2.5 bps against a spread of about 1 bp.
- **Capacity kills it:**
  - 30-minute window SD: 11.3 bps pre-fix, 8.8 post-fix. At a net 0.5-1.0 bp a leg, a $30k drawdown needs $0.9-1.3M of
    notional a leg, which is **134-204% of FXE's entire median 30-minute dollar volume** (the 10:30-11:30 median is
    $1.28M).
  - At 10% participation ($64k a leg) the leg earns about $1.6-3.2k a year, against the map's $15k a year line.
  - It needs 6E futures data, which the house does not hold (paid). **Fails the map; no quotes pull, not drafted.**

## This lane's position after addendum A
The scoped ground is closed: PMFAIL / RUNNER2 / BALANCE dead; ranks 4 and 6-9 are gapper siblings (no variants); GEXREV
sits inside TTM's GAMMA r1 (owner gate); DIXSTATE and FIXREV fail the map. The lane works MANAGER's cross-lane
queue (audits, second reviews) until a new habitat is argued.
