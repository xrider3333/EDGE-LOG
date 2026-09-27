# DIP on ES (#432) as a book candidate — the case, pre-registered (2026-09-26)

Owner GO via MANAGER, 2026-09-26: re-argue DIP on ES as a book candidate after the roll fix, and have the
Frontier chat test it. **The owner decides adoption.** Everything in sections 1-3 was written BEFORE the
measurements in section 4 were run.

## 1. Where it stands

- **#432** = `NQDIP_1_2.py` on ES 5m RTH (true contract rolls), window 2010-06-07..2026-08-24, 12-month
  lockbox, 8 folds, warm 400, 900 trials. **WEAK 5/6.** Passes plateau (17/17 neighbours good), walk-forward
  efficiency (0.76), sample, consistency (**8 of 8** walk-forward stretches held), luck (deflated Sharpe
  0.997). Lockbox 74 trades, +$25,409, PF 2.06, 25.4 %/yr, Sortino 3.77. Whole-run drawdown $66,592.
- **Fails one gate: the overfit probability, 0.706** (refusal line 0.5).
- The pre-roll-fix run **#425** (same data, window, budget) scored **0.337 and PASSED**.
- **Both runs crowned the SAME config** (rsi 4/20/9, trend 300, N-day 4, pullback 5/15, capitulation
  1.0/0.30/7). The roll fix did not change what the search picked; it changed the prices of the other
  configs in the top 24 that the overfit number is built from.
- Pre-registered on 2026-09-26 (`tools/queue_dip_true_rolls.py`): below PASS, DIP on ES is no book
  candidate until re-argued. This file is that re-argument.

## 2. Why the overfit number misleads here (RESEARCH.md 3d)

The number is CSCV over the **top 24 in-sample configs**: over 252 half/half splits of the pre-lockbox
months, how often does the in-sample winner land below the out-of-sample median? RESEARCH.md 3d measured
that when the 24 are near-tied elites, **which 24 go in** moves the number from 0.16 to 0.91 on one
strategy, one file, one month range (NOISE, median 0.52, 58 % of draws at or above 0.5). A near-tie makes
"which elite wins out of sample" close to a coin flip, and the refusal line sits exactly on the coin.

DIP on ES shows the same signature before any new measurement: one champion, two runs, 0.337 and 0.706.
The only thing that moved is the set of 24 near-equal neighbours around a champion the search chose twice.

## 3. Pre-registered measurements and a fair bar

**3a. The band (tool `tools/pbo_band.py`).** For a run, take the top **48** configs of its saved in-sample
search, re-run each over the pre-lockbox window (2010-06-07..2025-08-23, the run's own tuning window),
bin trade net into calendar months, then draw **300** random sets of 24 of the 48 (seed 42) and compute
the overfit probability for each. Also recompute the stored top-24 number as a reproduction check.
Runs: **#432** (`NQDIP_1_2.py`) and, as the control, **#425** (`NQDIP_1_0.py`).

**3b. Fair bar for the overfit gate** (replacing one draw against a hard 0.5, per RESEARCH item 14):
- band **median < 0.5** → the overfit gate counts as **PASSED**;
- band **10th percentile ≥ 0.5** (nine draws in ten say overfit) → **FAILED**, the case is dropped;
- otherwise → **UNINFORMATIVE**: the gate carries no weight and the verdict rests on the other five gates,
  which #432 passes.
- If the recomputed top-24 number misses the stored 0.706 by more than 0.05, the band is not trusted
  and the case goes back to the owner as-is.
- The #425 control is context only: it cannot rescue #432, it only shows whether the two runs' numbers
  sit in one band.

**3c. The book test (for the Frontier chat; the verdict above only makes it eligible).**
Legs on roll-corrected settings (the Frontier chat's current #396 reproduction), DIP on ES = #432's
champion, `NQDIP_1_2.py`, frozen, whole MES-style sizing from the file ($100k notional). Two sizes only,
fixed now so there is no weight fishing: **full ($100k) and half ($50k)**. Two shapes:
- **Seat:** #396 + DIP on ES. Adoptable only if, against #396 on the same window: calendar years won ≥
  years lost AND whole-run net higher; lockbox drawdown within +5 % (house clause); whole-run drawdown not
  worse than +10 %. History warns: on 2026-09-09 DIP on NQ as a 5th seat was rejected because its own
  drawdown exceeded the whole book's; DIP on ES's $66.6k is also above #396's $36.6k, so the half size is
  the likelier pass.
- **Own book:** DIP on ES + DIP on NQ (#433 champion, `NQDIP_1_2.py`) as a two-leg BOOK. Reported, not
  gated: it answers "is DIP a separate account", and is compared to #396 on ROC %/yr, Sortino and
  drawdown at matched drawdown.
Either result goes to the owner; nothing is adopted by this file.

## 4. Results

Run 2026-09-26 with `tools/pbo_band.py` (sections 1-3 unchanged; pre-registration commit d491b177).

| Run | Stored | Top-24 recomputed | Band over 300 draws of 24 from the top 48 (min / 10 % / median / 90 % / max) | Draws ≥ 0.5 | Bar |
|---|---|---|---|---|---|
| **#432** (true rolls) | 0.706 | 0.817 | 0.321 / 0.448 / **0.651** / 0.865 / 0.980 | 83 % | UNINFORMATIVE |
| #425 (control, old rolls) | 0.337 | 0.639 | 0.369 / 0.504 / **0.623** / 0.770 / 0.944 | 92 % | FAILED |

**The reproduction check failed on both runs** (off by 0.11 and 0.30), so under 3b **the band is not trusted
and the case goes back to the owner as-is.** Cause: the validate builds its 24 from the search's full ranked
list (all ~860 valid trials, realism-gated, then by profit), and a run saves only a 150-point sample of the
search, so this tool cannot rebuild the exact 24. Fixing that means saving the validate's 24 config ids on
the run (engine change, not done here).

**What the untrusted band suggests, stated as context only:** the two versions of DIP on ES land in one
band (medians 0.65 and 0.62, wide spread), so #425's 0.337 PASS looks like the low end of a draw, not the
roll fix breaking a sound strategy. That cuts **against** the re-argument, not for it: the overfit concern is
not shown to be pure measurement here. It also does not show real overfitting - the band is wide (0.32 to
0.98) and, unlike NOISE in RESEARCH.md 3d, sits mostly above the line, which a near-tie alone would not do.

**Standing facts for the owner:** five of six gates pass; 8 of 8 walk-forward stretches held; lockbox +25.4 %
a year, Sortino 3.77; the search chose the same champion before and after the roll fix. Adoption, and
whether a book test is still worth running, is the owner's call. The book test in 3c was handed to the
Frontier chat as information for that call, marked not eligible under 3b.

## 5. New data for the next strategy search (scoped 2026-09-26, prices as found on vendor pages that day)

| Option | What it unlocks | Cost | Effort |
|---|---|---|---|
| **Alpaca stock/ETF 1m-5m bars (free tier)** | Intraday search on single stocks and ETFs, not just NQ/ES | Free; needs an owner-created API key | Near zero: `tools/import_alpaca_stocks.py` is already written |
| **Databento CME Globex OHLCV-1m for YM, RTY, CL, GC, ZN/ZB, 6E** | New, less-correlated futures for the ORB / NOISE / DIP recipes on the same pipeline | Usage-based, "from $0.50/GB" (databento.com/catalog/GLBX.MDP3); $125 free credit for a new team (databento.com/pricing). 1-minute bars for one root over 16 years are small, so likely inside the credit - confirm with Databento's cost estimate before buying | About 0.5-1 day per root: add the root to `tools/stitch_databento.py`, build its roll table with `tools/rollaudit/ground_truth.py`, register masters (YM/RTY/CL/GC specs already exist in `optimizer.py`) |
| VIX futures (CFE) | A new asset class | Databento offers raw feed only ($750/month); normalized bars "in development". FirstRate / Kibot sell minute bundles (Kibot top-10 futures $400 one-time, kibot.com); FirstRate price not readable on the page | Medium-high: new importer and vendor format |
| Order flow (CME trades / top of book) | Per-bar buy/sell delta on NQ/ES | Not verified (ROADMAP.md #23 quotes $28/GB, unconfirmed) | Medium-high: new schema and features |

Recommendation: the free Alpaca pull first, then a small Databento pull for YM, RTY, CL and GC. Both need an
account only the owner can create (this chat never creates accounts or handles keys).
