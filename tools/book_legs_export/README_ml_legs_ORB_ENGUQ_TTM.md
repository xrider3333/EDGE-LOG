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

## Round 2: ENGU-Q paper-leg cell, TTM #455

**ENGUQ335paper (ENGUQ_1M_ETH_R2_1_0.py at FILE DEFAULTS, cost 0.783, db_adj_eth, #335's own
WF 2016-10-12..2025-06-30 / LB 2025-06-30..2026-06-30):** no stored gate_validate to reproduce
against (this is the live paper cell, not an archived validate). Roll guard
(`rolls.guard_masks('NQ',60,block_estimated=True)`) dropped 0 of 2053 trades — the one estimated
2026-06-15 NQ switch inside the window landed on a bar no ENGU-Q trade entered on; the second
estimated switch (2026-09-14) is outside this window. HYBRID DD rf @0.45, DD factor from its own
WF (0.8933) frozen at the lockbox boundary exactly as #335's leg was.
| Leg | WF net | WF DD | WF MAR | WF Sortino | LB net | LB DD | LB MAR | LB Sortino |
|---|---|---|---|---|---|---|---|---|
| ENGUQ335paper raw | $380,348 | $38,872 | 1.12 | 3.68 | $74,869 | $44,205 | 1.69 | 3.38 |
| ENGUQ335paper HYBRID DD rf | $318,466 | $38,872 | 0.94 | 3.46 | -$17,067 | $53,479 | -0.32 | -0.75 |
ML at raw's WF drawdown is trivial ($318,466, already matched); at raw's LB drawdown, ML would
have read -$14,107 (scale 0.827) — **the rf gate makes this cell materially worse in its own
lockbox**, unlike ORB/ENGU-Q's champion cells. Say so plainly: HYBRID DD does not help here.

**TTM #455 (TTMSQZ_3_0_ES30SSOF2R347.py) — BLOCKED, nothing exported.** Raw twin reproduced
trade counts exactly (246/234/144/12) but net points ran ~40% BELOW the stored
`gate_validate.ungated_*` blocks at every stretch (e.g. full 4,254 vs stored 7,172 pts) and KEEL
likewise (e.g. lockbox stored $176,250 vs my online reproduction $68,335). Root cause found, not
guessed: the strategy's shared base file `TTMSQZ_3_0_ES30SS.py` (and its `SSOF2R`/`SSOF2R347`
children) was edited TODAY, file-modified 14:51-14:57, fixing a real bug ("entry-bar stop no
longer books an exit at a price the bar never traded when the open gaps past the stop" —
comment cites a same-day MANAGER audit). Run #455 was validated at 14:08, before that fix, so
its stored numbers are pre-fix and my reproduction (post-fix code) correctly disagrees — same
bars, different exit price on the affected trades, amplified by this file's 3/4/7-contract
ladder. Per rule (a) this stops here: TTM455_raw/TTM455_keel are NOT written. Re-validating
run #455 on the current (fixed) code, then re-running this export, would resolve it.

## Round 3: TTM #458 (the fixed-code re-validation of #455)

Reproduces exactly (git-pulled to d4b3bc1f first, cache off): trade counts and net $ match
`gate_validate.ungated_*` and `.keel.*` to the cent at full/pre/WF/lockbox (whole-run raw net
$212,710, matching the lane's own figure). Files written: `TTM458_raw`/`TTM458_keel`
`_{daily,trades}.csv`, same KEEL v12 freeze as #368 (state built on the 234 pre-lockbox trades,
each of the 12 lockbox trades scored from that frozen state). Daily sums tie to trade sums.
| Leg | WF net | WF DD (daily) | ROC%/yr@$30k | WF Sortino | LB net | LB DD (daily) | ROC%/yr@$30k | LB Sortino |
|---|---|---|---|---|---|---|---|---|
| TTM458 raw | $142,510 | $16,307 | 29.1 | 2.40 | $29,278 | $3,761 | 233.3 | 8.96 |
| TTM458 KEEL v12 | $347,262 | $35,141 | 32.9 | 2.73 | $69,263 | $7,963 | 260.7 | 11.61 |
KEEL beats raw on both ROC%/yr and Sortino, both stretches. WF trades = 144 (clears the
owner's 100-trade floor). **LB trades = 12 — fails the 50-trade floor**, so the LB column above
is a thin read, not a judgement. LB stays profitable without its single biggest trade either
way: raw $16,050 of $29,278 net ex the $13,227 trade; KEEL $41,063 of $69,263 net ex the
$28,200 trade. Note: the lane's own WF Sortino (1.96) doesn't match this WF-window reading
(2.40) — likely the separate "walk-forward TEST" (re-tuned blind folds) vs this doc's
`gate_validate.wf_range` replay; flagging rather than guessing which one the lane wants.
