# ML-sized book legs: ORB #314, ENGU-Q #335, TTM #368

## Windows / sources (rule d: unadjusted masters, no ADJ_/FADJ_ used)
- ORB #314: ORB_3_6_R6.py, NQ 5m RTH, master NOADJ_NQ_5m_RTH.csv (db_noadj_rth), cost 0.533 pts, mult $20.
  Window 2010-06-07..2026-08-13. WF 2016-07-13..2025-08-13. LB 2025-08-13..2026-08-13.
- ENGU-Q #335: ENGUQ_1M_ETH_R2_1_0.py, NQ 1m ETH, master NOADJ_NQ_1m_ETH.csv (db_noadj_eth), cost 0.533 pts, mult $20.
  Window 2010-06-07..2026-06-30. WF 2016-10-12..2025-06-30. LB 2025-06-30..2026-06-30.
- TTM #368: TTMSQZ_3_0_ES30SSO.py, ES 30m RTH, master NOADJ_ES_30m_RTH.csv (db_noadj_rth), cost 0.363 pts, mult $50.
  Window 2010-06-18..2026-06-30. WF 2016-06-24..2025-06-30. LB 2025-06-30..2026-06-30.
Roll-corrected ADJ_/FADJ_ masters exist for these instruments but were NOT used, per rule d.

## Reproduction check (rule a) — raw twin vs stored gate_validate.ungated_*
All three legs reproduce trade-for-trade at full/pre-lockbox/lockbox; net $ matches to the cent.
- ORB #314: full/pre/lockbox trades and net EXACT; WF split off by 1 boundary trade (1290 vs
  stored 1289, net $2.22 / 0.01% — lands exactly on the IS/WF date, not a data error).
- ENGU-Q #335 and TTM #368: full/pre/WF/lockbox EXACT (trades and net, no mismatch).
Chosen gate reproduced exactly: #314 et@0.45 (pre net $15,748.24); #335 rf@0.45 (pre net
$18,517.80), both identical to the cent. Hybrid[tree]/#314 and Hybrid[rf]/#335 stat blocks
reproduce to the cent except the one WF boundary trade above. TTM KEEL v12 (the version the run
doc itself carries) reproduces within 0.04%-0.4% per stretch (sklearn float-order noise) —
inside the 1% bar.

## How each leg was frozen (rule b)
- **HYBRID DD (ORB tree, ENGU-Q rf):** kept the causal online walk for IS+WF (gate model refit
  every 25 trades on trades whose exit precedes the entry — never sees the future). For the
  LOCKBOX, that walk was replaced: ONE model fit ONCE on every pre-lockbox trade only
  (`ml_gate._make_model` + the same |pnl|-weighted fit gate_trades uses), then used unchanged to
  score every lockbox trade — no lockbox-time refits. Floor threshold pinned to the crowned
  gate's own cutoff (0.45 both legs, read from the stored `chosen` block). HYBRID DD's size
  factor = |ungated WF drawdown| / |hybrid WF drawdown| (WF-only, pre-lockbox-knowable), then
  applied uniformly to every trade including lockbox — never a factor re-derived from lockbox
  results. Factors: ORB #314 tree 1.2785x; ENGU-Q #335 rf 2.3715x.
  Freeze cost vs the stored (leaky) numbers, same DD factor applied: ORB LB net moved from
  $119,844 (unfrozen) to $119,268 (frozen) = -0.5%. ENGU-Q LB net moved from $145,541 (unfrozen)
  to $110,209 (frozen) = **-24.3%** — the stored HYBRID row materially overstates what a truly
  pre-lockbox-frozen rf gate would have earned in ENGU-Q's lockbox.
- **KEEL (TTM v12):** `ml_keel.keel_build_state` built on the 341 pre-lockbox trades only; each
  of the 16 lockbox trades scored with `ml_keel.keel_score_from_state(..., cross_series=False)`
  against that one frozen state — no lockbox-time refit. Pre/WF sizes come from the normal
  `keel_walk` (already causal, unaffected by the freeze). Freeze effect was negligible here:
  frozen LB net $61,194 vs online $61,157 (+0.06%).

## Daily valuation (rule c)
Multi-day holds (ENGU-Q, TTM) marked to each session's last close via
`augur_engine.book._mtm_increments` (the house book.mtm helper; UTC-truncated day-stamp, the
same convention book.py uses — an ET-session-day alternative exists but was not used). Neither
strategy file declares `PNL_UNITS`/`mark_open_trades`, so the generic side×(close−entry)×mult×
size mark applied. Daily sums equal per-trade totals for every leg (exact for ORB/ENGU-Q,
within $0.19 rounding noise for TTM across 357/16 independently-rounded cent entries).

## Summary (WF = 2016→lockbox, LB = the sealed year; $ = net; DD = max drawdown $; MAR = (net/yrs)/DD)
| Leg | WF net | WF DD | WF MAR | WF Sortino | LB net | LB DD | LB MAR | LB Sortino |
|---|---|---|---|---|---|---|---|---|
| ORB314 raw | $308,124 | $28,857 | 1.18 | 2.22 | $87,132 | $22,925 | 3.80 | 3.09 |
| ORB314 HYBRID DD tree | $369,081 | $28,857 | 1.41 | 2.31 | $119,268 | $26,783 | 4.45 | 4.19 |
| ENGUQ335 raw | $447,548 | $66,569 | 0.77 | 3.93 | $49,812 | $47,779 | 1.04 | 2.44 |
| ENGUQ335 HYBRID DD rf | $911,961 | $66,569 | 1.57 | 4.19 | $110,209 | $104,528 | 1.05 | 2.68 |
| TTM368 raw | $89,481 | $5,330 | 1.86 | 4.00 | $22,321 | $2,003 | 11.13 | 15.52 |
| TTM368 KEEL v12 | $227,858 | $10,898 | 2.32 | 5.14 | $61,194 | $3,268 | 18.70 | 28.42 |

**ML at matched drawdown** (scale each stretch's ML $ by that stretch's own raw-DD/ML-DD ratio):
- ORB tree: WF trivial ($369,081, factor already WF-matched); LB $102,087 vs raw $87,132 (scale 0.856) — the ML leg still beats raw even after re-matching the lockbox's own drawdown.
- ENGUQ rf: WF trivial ($911,961); LB $50,375 vs raw $49,812 (scale 0.457) — roughly a wash once the lockbox's own (much larger) ML drawdown is priced in.
- TTM keel (never DD-matched at export): WF $111,437 vs raw $89,481 (scale 0.489); LB $37,509 vs raw $22,321 (scale 0.613) — KEEL still ahead of raw at matched risk on both stretches.

**Honest caveat:** the WF "equal-drawdown" promise did not fully travel to the lockbox for either
hybrid — ML lockbox drawdown ran 17% above raw on ORB and 119% above raw on ENGU-Q despite being
DD-matched on WF alone (per rule b, no lockbox-derived re-matching was allowed).

Files: `C:\EdgeLog\book_legs\{ORB314_raw,ORB314_hybdd_tree,ENGUQ335_raw,ENGUQ335_hybdd_rf,TTM368_raw,TTM368_keel}_{daily,trades}.csv` and `_summary_*.json` per ML leg.
