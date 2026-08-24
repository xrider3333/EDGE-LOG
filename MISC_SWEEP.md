# MISC_SWEEP.md — round 16: six classic mechanisms, first look (2026-08-24)

Owner directive: *"find others we may have not tried either in TV or otherplaces."*
This round tested mechanism FAMILIES, not TradingView scripts — the 2026-08-24
inventory of `augur_strategies/` (119 files) plus the round-13 TV sweep (12 dead),
web rounds 1/2/15 and the TTM study left exactly six classic families untouched.

Harness: `tools/r16_misc_triage.py` (committed). Cell-by-cell results:
`tools/r16_results/r16_triage.csv`. Studies-board rows: **487–517, fam MISC**
(web v73.246).

## Pre-registration (fixed before any result was computed)

- **Window:** 2010-06-07 → 2025-06-29 hard cutoff. The lockbox year was never loaded.
- **Data/costs:** NQ 5m RTH, 0.533 pts/RT (SESSBRK: NQ 1m ETH, 0.783; PAIRS adds the
  ES leg at 0.363 — both legs costed, $28.81/RT per pair).
- **Fills:** close-confirmed signals → next bar's open; resting stop-entries fill at
  the level with gap-through at the open; stop-first pessimism inside a bar; OOPS
  skips roll-seam days (GAPFADE-calibrated detector).
- **Gates (triage, all must pass):** PF ≥ 1.25, MAR ≥ 8, n ≥ 300.
- **The 30-cell grid below is the whole grid.** No cell added after results existed.

## Verdict: 0 of 30 cells pass. Family banked DEAD.

| Concept | Cells | Best cell | n | Net$ | PF | DD$ | MAR |
|---|---|---|---|---|---|---|---|
| OOPS gap-reversal | 4 | stop 0.5×ATR / hold-to-close | 786 | 49,543 | 1.139 | 23,733 | 2.09 |
| NR7/NR4/inside breakout | 6 | NR4 / 2R target | 989 | 106,952 | 1.225 | 33,256 | 3.22 |
| Floor pivots | 4 | breakout / stop 1.0×band | 3,040 | 208,952 | 1.156 | 34,639 | 6.03 |
| Last-hour drift (MOC) | 8 | 60m / momentum / 0.3-ATR filter | 2,238 | 117,153 | **1.246** | 23,121 | 5.07 |
| Session-range break (ETH) | 4 | london / half-range stop | 3,814 | 161,730 | 1.112 | 43,069 | 3.76 |
| ES/NQ spread | 4 | z2.5 / w1170 | 206 | 6,308 | 1.029 | 44,134 | 0.14 |
| B0 drift yardstick | 1 | always-long RTH | 3,868 | 97,767 | 1.040 | 90,626 | 1.08 |

Readings:

- **The house pattern held exactly:** every breakout-direction cell is positive,
  every fade is negative (pivot fade −$89k/−$110k, MOC fade −$60k to −$199k,
  asia-range fade-side included). NQ intraday pays breakout, kills fades — same
  verdict as REVERT/GAPFADE/VWAP_FADE/ORB_FADE.
- **Nearest miss:** MOC 60m momentum + 0.3-ATR filter, PF 1.246 vs the 1.25 bar,
  MAR 5.07 vs 8. A near miss is not a re-tune license; it also conceptually overlaps
  the DRIVE first-hour-momentum family already measured. Banked dead, not parked.
- **PAIRS answers a standing question:** ES/NQ log-ratio mean reversion at 1 contract
  a leg loses its whole edge to the doubled cost — best cell +$6.3k over 15 years.
- **PIVOT breakout ≈ a worse ORB:** the mechanism (break of a prior-day-derived level,
  with trend) earns PF 1.16–1.19 where the ORB crown's opening-range level earns 1.31.
  The opening range is simply the better level; nothing to fuse.
- **The lockbox was never opened for any row.**

Round tally now: rounds 13 (TV 0/12), 14/15 (web, empty), 16 (classics 0/30). The
next genuinely new edge still looks like it comes from new instruments/order-flow
data or an owner idea — not from public mechanism recipes.

---

# Round 17 — the hold-for-days playbook (2026-08-24, same session)

Harness: `tools/r17_misc_triage.py`. Results: `tools/r16_results/r17_triage.csv`.
Board rows **518–533, fam MISC** (web v73.247). Same window, same costs, same bar
(multi-day cells: 150-trade floor instead of 300, pre-registered in the harness).

Six more never-tested families, on daily bars built from the 5m day session. Multi-day
holds are honest: contract-roll days book no fake jump (seam detector + 0.25-pt roll
cost), and no overnight stop is pretended (the ENGU-Q $178k lesson).

## Verdict: 0 of 16 pass.

| Concept | Best cell | n | Net$ | PF | DD$ | MAR |
|---|---|---|---|---|---|---|
| Pullback to 20-day avg (long) | ema20/long | 168 | 150,654 | **1.879** | 32,856 | 4.59 |
| 7-day low buy (long) | 7d/long | 132 | 119,768 | 1.703 | 31,611 | 3.79 |
| Turtle breakout | 20/10 | 97 | 99,516 | 1.362 | 31,488 | 3.16 |
| 2-day dip buy (long) | thr10/long | 109 | 47,708 | 1.402 | 33,286 | 1.43 |
| Gap continuation | gap0.5% | 758 | −27,990 | 0.957 | 78,484 | neg |
| 10 o'clock fade | best of 4 | 1,067 | −110,254 | 0.775 | 118,204 | neg |

- **PB20 long = best cell of the whole hunt.** Independently rebuilt, reproduces to the
  dollar; post-2021 share only 26%. Still fails: MAR 4.59 vs 8, profit concentrated in
  2020/2021/2024, and one 2022 trade lost $23,361 (10-day hold, no stop). Banked dead.
- **MOC recheck (owner ask):** the round-16 near miss (PF 1.246) reproduces exactly in an
  independent clock-time rebuild — but 2010–2017 is eight flat years and 73% of profit is
  post-2021, which fails the year-concentration check. Dead twice over. Row 503 updated.
- **Gap pair complete:** fading gaps failed (round 13-era), riding them fails too.
- Buying weakness in an uptrend (dip/pullback/7-day-low) is the one shape that keeps
  showing a real edge fingerprint (PF 1.4–1.9, 70%+ winners) — it just doesn't earn
  enough per unit of its worst stretch to clear a futures bar built for MAR 8.
