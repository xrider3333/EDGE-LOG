# SEARCH SPACE AUDIT -- which knobs to stop searching

Built by `tools/knob_audit.py` from 270 cached run records. No Firestore reads. One verdict per knob per strategy family.

**Words used here.** A *knob* is one tunable input of a strategy -- a row of its Settings panel. Its *declared range* is the lowest and highest value the strategy file allows. The *crowned value* is the one the run's champion ended up carrying. A *finalist* is one of the ten configurations a validate run short-lists. The *lockbox* is the final months of data the search never saw. A knob is *on an edge* when its crowned value sits within 2% of the range width of the declared minimum or maximum. An *on/off switch* is a knob with only two settings; it is always on an edge by construction, so it is counted separately everywhere below. *Predictive power* is the 0-1 score each run stores per knob saying how much that knob's value explained the run's result; 0 means it explained nothing inside the space searched. *Spread* is how much the crowned value moved between runs, measured as a share of the declared range (0 = always the same setting, 1 = anywhere).

**Why this exists.** The candidate board found that picking between the ten finalists is a coin flip in the sealed year, that 71% of knobs carry no measurable predictive power, and that 58% of champions sit on a range edge. A separate walk-forward study found that re-picking parameters on ORB earned $166k over 11 forward years against $377k for leaving the file's defaults alone. Both say the same thing: the problem is the space we search, not the picker. This audits the space.

## Headline

- 108 knobs audited across 8 families (90 real ranges, 18 on/off switches).
- Edge rate **36% over real ranges**, 47% once switches are mixed in -- the second number is inflated and should not be quoted. This is lower than the candidate board's 58% because the board measured against the range each search actually swept after auto-widening, while this measures against the range the strategy file DECLARES, and drops runs whose file pinned the knob outright.
- Verdicts: **UNCLEAR** 88, **FREEZE** 8, **KEEP** 6, **WIDEN** 6.
- 3 FREEZE verdicts rest on knobs the ten finalists never actually varied -- flagged in the table, see the sanity check.

## FREEZE -- stop searching, pin at this value

Zero predictive power and a crown that barely moves, or crowns piling on the `0 = off` floor. Pinning these costs nothing measurable and shrinks the grid.

| family | knob | pin at | runs | spread | power | finalists varied it? |
|---|---|---:|---:|---:|---:|---|
| NOISE | Lower band width (x noise) (`band_mult_short`) | **1.5** | 14 | 0% | 0 | yes (100% of runs) |
| NOISE | Top close-position threshold (`daytype_hi`) | **0.9** | 5 | 0% | 0 | yes (56% of runs) |
| NOISE | Flat by session close - PINNED on (`flat_eod`) | **1** | 22 | 0% | n/a | yes (69% of runs) |
| NOISE | Skip holiday half-days - PINNED off (`skip_holidays`) | **0** | 22 | 0% | n/a | yes (69% of runs) |
| ORB | Breakout buffer (× range) (`breakout_buf`) | **0** | 10 | 40% | 0 | no in 72% of runs |
| ORB | Flat at the close — PINNED on (`flat_eod`) | **1** | 40 | 0% | n/a | yes (59% of runs) |
| TTIBS | 200-session regime filter (`ma200`) | **0** | 12 | 0% | n/a | no in 100% of runs |
| TTIBS | Monday drop threshold (fraction) (`mon_drop`) | **0.01** | 12 | 0% | 0 | no in 100% of runs |

## WIDEN -- the optimum is probably outside the range we drew

Half or more of the champions land on a declared end-stop, so the value we read off the champion is a limit we imposed rather than something the market chose. The proposed range extends past the busier end-stop by half the current width, snapped to the declared step. Where the crowns split across BOTH ends the knob is behaving as on-or-maxed rather than as a dial, and the widening is a probe, not a fix. The last column is the widest range any file in that family already allows: where it is wider than the proposal, the fix is to adopt that file's range rather than invent a new one.

| family | knob | declared now | crowns on an end-stop (bottom / top) | declare instead | widest a file already allows | runs |
|---|---|---|---:|---|---|---:|
| NOISE | Entry confirmation (closes outside band) (`confirm_bars`) | 1 to 4 | 50% (12% / 38%) | **1 to 6** | same | 8 |
| ORB | Lot B trail (bars) (`trail_bars`) | 2 to 12 | 67% (5% / 62%) | **2 to 17** | 0 to 20 | 21 |
| TTIBS | IBS entry threshold (`ibs_entry`) | 0.05 to 0.4 | 92% (0% / 92%) | **0.05 to 0.6** | same | 12 |
| TTMSQZ | Verification squeeze length (`gate_len`) | 16 to 24 | 62% (62% / 0%) | **12 to 24** | 14 to 24 | 8 |
| TTMSQZ | Squeeze length (BB / Keltner / momentum) (`length`) | 10 to 40 | 50% (50% / 0%) | **4 to 40** | same | 8 |
| TTMSQZ | Protective stop, ATR multiples (`stop_atr`) | 0.5 to 4 | 70% (30% / 40%) | **0.5 to 5.75** | same | 10 |

## KEEP -- real power, champions land in the interior

| family | knob | power | spread | edge rate | drift | runs |
|---|---|---:|---:|---:|---:|---:|
| ENGU-Q | Efficiency Lookback (min) (`er_len`) | 0.02 | 30% | 0% | 0.1 | 5 |
| ENGU-Q | Trail Width (x risk) (`trail_frac`) | 0.14 | 32% | 40% | 0.48 | 20 |
| ENGU-Q | Volume Spike (x avg) (`vol_mult`) | 0.19 | 17% | 32% | -0.45 | 19 |
| NOISE | Skip entries above prior-day vol percentile (0=off) (`vol_skip_pct`) | 0.21 | 9% | 43% | 0.81 | 7 |
| TTIBS | Max hold (trading days) (`hold_cap`) | 0.03 | 11% | 0% | 0.54 | 12 |
| TTMSQZ | Keltner ATR multiplier (`kc_mult`) | 0.28 | 50% | 46% | -0.51 | 13 |

## Drift -- does the winning setting move with the calendar?

Rank correlation between the crowned value and the run's date, -1 to +1. **These cached records cannot tell a regime-sensitive knob from a noisy one.** A drifting knob may be tracking a changing market or may simply be re-rolled each time; distinguishing them needs a fixed-window re-run of the same knob across eras, which is not in this data. Listed for follow-up only, never as a finding.

| family | knob | drift | runs | verdict |
|---|---|---:|---:|---|
| NQDIP | RSI exit SMA (days) (`rsi_exit`) | -1 | 3 | UNCLEAR |
| ENGU-Q | Shallow Limit Depth (x ATR) (`limit_atr`) | -0.9 | 5 | UNCLEAR |
| NQDIP | RSI length (days) (`rsi_len`) | -0.87 | 3 | UNCLEAR |
| ORB | Volume filter (× session avg, 0=off) (`vol_filter`) | -0.87 | 3 | UNCLEAR |
| TTMSQZ | Protective stop, ATR multiples (`stop_atr`) | -0.81 | 10 | WIDEN |
| TTMSQZ | No entries inside the last N bars of the session (`eod_cutoff`) | -0.78 | 10 | UNCLEAR |
| ORB | Lot B trail (bars) (`trail_bars`) | -0.72 | 21 | WIDEN |
| ENGU-Q | Regime SMA (days, 0=off) (`regime_len`) | -0.55 | 14 | UNCLEAR |

## Sanity check -- was the knob ever really searched?

For each FREEZE knob: inside a single run, did the ten short-listed finalists carry different values for it? If they all carried the same value, the search never explored it there and the zero-power reading is partly an artifact of our own grid, not evidence about the market. Reported per knob rather than buried.

| family | knob | runs checked | finalists all identical | best vs worst finalist differ | reading |
|---|---|---:|---:|---:|---|
| NOISE | Lower band width (x noise) (`band_mult_short`) | 13 | 0% | 80% | genuine -- it was searched and did not matter |
| NOISE | Top close-position threshold (`daytype_hi`) | 9 | 44% | 56% | genuine -- it was searched and did not matter |
| NOISE | Flat by session close - PINNED on (`flat_eod`) | 13 | 31% | 0% | genuine -- it was searched and did not matter |
| NOISE | Skip holiday half-days - PINNED off (`skip_holidays`) | 13 | 31% | 20% | genuine -- it was searched and did not matter |
| ORB | Breakout buffer (× range) (`breakout_buf`) | 29 | 72% | 20% | ARTIFACT -- never searched |
| ORB | Flat at the close — PINNED on (`flat_eod`) | 17 | 41% | 40% | genuine -- it was searched and did not matter |
| TTIBS | 200-session regime filter (`ma200`) | 7 | 100% | 0% | ARTIFACT -- never searched |
| TTIBS | Monday drop threshold (fraction) (`mon_drop`) | 7 | 100% | 0% | ARTIFACT -- never searched |

**What this changes:** 3 of 8 FREEZE verdicts are artifacts of a grid that never varied the knob. Freezing those is still the right *action* -- the search was not using them anyway -- but it is **not** evidence the knob is useless, so none of them should be written off permanently. The remaining 5 were genuinely varied and genuinely did not move the result.

## Budget impact -- the same trial budget over a smaller space

*Settings* here is every combination the declared ranges allow, multiplied together -- the haystack, not a list the search ever walks. Freezing a knob deletes its multiplier outright. The trial budget does not change; each trial simply covers more of what is left. The reference file for each family is the one declaring the most of that family's audited knobs, not the most-run variant.

| family | reference file | runs | knobs now | knobs kept | settings now | settings after | smaller by |
|---|---|---:|---:|---:|---:|---:|---:|
| ENGU-Q | `ENGUQ_1M_ETH_ER_1_0.py` | 34 | 14 | 14 | 1,226,991,910,248,476,064 | 1,226,991,910,248,476,064 | unchanged |
| NQDIP | `NQDIP_1_1.py` | 3 | 24 | 24 | 9,468,090,777,600,000 | 9,468,090,777,600,000 | unchanged |
| NOISE | `NOISE_1_0.py` | 29 | 15 | 11 | 10,521,114,624,000 | 32,472,576,000 | 324x |
| RSIDIV | `RSIDIV_1_0.py` | 1 | 11 | 11 | 6,379,220,016,000 | 6,379,220,016,000 | unchanged |
| ORB | `ORB_3_5.py` | 55 | 13 | 12 | 638,435,685,888 | 91,205,097,984 | 7x |
| TTMSQZ | `TTMSQZ_2_0.py` | 14 | 14 | 14 | 76,082,872,320 | 76,082,872,320 | unchanged |
| TTIBS | `TTIBS_1_3.py` | 12 | 8 | 6 | 725,760 | 17,280 | 42x |
| GAPGO | `GAPGO_TRAVEL_1_0.py` | 2 | 3 | 3 | 32 | 32 | unchanged |

## How to act on this

1. Pin every FREEZE knob at the value in that table and take it out of the search.
2. Re-declare the WIDEN ranges before the next sweep -- a champion on an end-stop is an unfinished search, and its value is a floor or ceiling we imposed, not a finding.
3. Leave the KEEP knobs alone and let the same trial budget cover the smaller space.
4. Nothing here says a frozen knob is worthless. It says the search, as run, could not tell -- and for the artifact-flagged ones it never even asked.

Row-level numbers for every knob, including every UNCLEAR one: `docs/candidates/knob_audit.csv` (and the same rows as `knob_audit.json`, because the repo does not track CSV files).
