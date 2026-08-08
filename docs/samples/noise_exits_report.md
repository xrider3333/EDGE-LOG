# NOISE 1.0 — does a stop loss (or alternative exit) help?

Engine: `scratchpad/noise_exits.py` (forked from `tools/noise_research.py`, entry/band math
byte-identical — sanity gate reproduced the frozen baseline exactly: n=3147, net
$254,382.98, PF 1.3110, DD -$31,239.80, MAR 8.1429, before any variant ran).
All rows below are **pre-lockbox only** (`date_to="2025-06-29"`), NQ 5m RTH,
`source=db_noadj_rth`, cost_pts=0.533, $20/pt. Full data: `noise_exits_results.json`.

---

## Exec summary

**YES, a stop helps — but only a specific kind.** A protective stop set at
`k=1.0 × (that trade's own entry-band excursion)` (variant B, k=1.0) is the standout:
it *raises* net to $268,371 (+5.5% vs baseline) while cutting max drawdown 30.7%
($31,240→$21,660), cutting the worst single trade 69.6% ($15,466→$4,707), and lifting
MAR from 8.14→12.39 — it beats baseline on every axis simultaneously, not a
risk/return trade-off. Nine variants are ADOPTABLE overall (all of group B, all of
group D, A_k1.0, and the composed I); **best ADOPTABLE = B (band-width stop, k=1.0)**.
The naked-tail problem IS fixable, cheaply: the disaster trade (2025-04-07
tariff-crash session, -772.75 pts / -$15,466) gets caught and clipped by every
meaningfully-tight stop tested — it is not a stubborn artifact. **Best RISK-ONLY**
(fails the net/MAR bar but cuts the tail) = H (20-bar prior-extreme trail), but it's
a weak trade: -47.8% net and a negative 2010-17 subtotal for a 77.5% smaller worst
trade — dominated by the B-group stops on every axis, not a real alternative.
Time stops (E) and full exit-mechanism replacements (F EMA-cross, G chandelier) are
uniformly worse than doing nothing.

---

## Full results table

n=25 variants + baseline. C1–C4 = the four pre-registered conditions (worst trade
reduced ≥40%, net ≥85% of baseline, MAR ≥ baseline 8.1429, 2010-17 subtotal ≥ $0).
"REFERENCE" = baseline itself, not scored against its own rule.

| # | Variant | n | Net $ | PF | WR% | MaxDD $ | MAR | Worst trade $ | p99 loss $ | Avg loss pts | 2010-17 subtotal $ | C1 | C2 | C3 | C4 | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | baseline (no stop) | 3147 | $254,383 | 1.311 | 37.5 | -$31,240 | 8.14 | -$15,465.66 | $2,926.16 | 20.80 | $15,845.04 | ref | ref | ref | ref | REFERENCE |
| 1 | A: ATR20d stop k=1.0 | 3148 | $260,173 | 1.320 | 37.5 | -$28,908 | 9.00 | -$8,127.91 | $2,925.86 | 20.65 | $15,845.04 | PASS | PASS | PASS | PASS | **ADOPTABLE** |
| 2 | A: ATR20d stop k=1.5 | 3147 | $257,662 | 1.316 | 37.5 | -$27,961 | 9.22 | -$12,186.54 | $2,926.16 | 20.72 | $15,845.04 | FAIL | PASS | PASS | PASS | fail |
| 3 | A: ATR20d stop k=2.0 | 3147 | $254,383 | 1.311 | 37.5 | -$31,240 | 8.14 | -$15,465.66 | $2,926.16 | 20.80 | $15,845.04 | FAIL | PASS | PASS | PASS | fail (never fires) |
| 4 | A: ATR20d stop k=3.0 | 3147 | $254,383 | 1.311 | 37.5 | -$31,240 | 8.14 | -$15,465.66 | $2,926.16 | 20.80 | $15,845.04 | FAIL | PASS | PASS | PASS | fail (never fires) |
| 5 | A: ATR20d stop k=4.0 | 3147 | $254,383 | 1.311 | 37.5 | -$31,240 | 8.14 | -$15,465.66 | $2,926.16 | 20.80 | $15,845.04 | FAIL | PASS | PASS | PASS | fail (never fires) |
| 6 | B: band-width stop k=0.5 | 3479 | $249,340 | 1.311 | 33.6 | -$20,873 | 11.95 | -$3,460.66 | $1,938.73 | 17.35 | $10,089.81 | PASS | PASS | PASS | PASS | **ADOPTABLE** |
| 7 | B: band-width stop k=1.0 | 3185 | $268,371 | 1.334 | 37.0 | -$21,660 | 12.39 | -$4,707.10 | $2,699.16 | 20.05 | $15,263.93 | PASS | PASS | PASS | PASS | **ADOPTABLE — best (MAR)** |
| 8 | B: band-width stop k=2.0 | 3148 | $265,070 | 1.328 | 37.5 | -$25,122 | 10.55 | -$6,748.47 | $2,816.73 | 20.52 | $16,251.45 | PASS | PASS | PASS | PASS | **ADOPTABLE** |
| 9 | C: opposite-band stop | 3148 | $252,421 | 1.308 | 37.5 | -$31,240 | 8.08 | -$15,465.66 | $2,909.06 | 20.84 | $15,845.04 | FAIL | PASS | FAIL | PASS | fail |
| 10 | D: fixed stop P=50pt | 3264 | $239,001 | 1.295 | 35.9 | -$27,519 | 8.68 | -$3,460.66 | $1,463.06 | 19.34 | $15,560.04 | PASS | PASS | PASS | PASS | **ADOPTABLE** |
| 11 | D: fixed stop P=100pt | 3160 | $254,644 | 1.316 | 37.3 | -$22,420 | 11.36 | -$3,460.66 | $2,010.66 | 20.34 | $15,845.04 | PASS | PASS | PASS | PASS | **ADOPTABLE** |
| 12 | D: fixed stop P=150pt | 3153 | $244,819 | 1.299 | 37.4 | -$28,382 | 8.63 | -$3,460.66 | $3,010.66 | 20.78 | $15,845.04 | PASS | PASS | PASS | PASS | **ADOPTABLE** |
| 13 | D: fixed stop P=250pt | 3148 | $253,362 | 1.311 | 37.5 | -$27,279 | 9.29 | -$5,010.66 | $2,952.46 | 20.68 | $15,845.04 | PASS | PASS | PASS | PASS | **ADOPTABLE** |
| 14 | E: time stop N=6 bars | 3963 | $218,389 | 1.275 | 28.0 | -$36,034 | 6.06 | -$15,465.66 | $2,285.26 | 13.89 | $9,848.32 | FAIL | PASS | FAIL | PASS | fail |
| 15 | E: time stop N=12 bars | 3541 | $242,663 | 1.307 | 31.6 | -$36,557 | 6.64 | -$15,465.66 | $2,568.66 | 16.31 | $12,234.18 | FAIL | PASS | FAIL | PASS | fail |
| 16 | E: time stop N=24 bars | 3275 | $246,354 | 1.307 | 34.7 | -$34,665 | 7.11 | -$15,465.66 | $2,871.76 | 18.74 | $13,855.16 | FAIL | PASS | FAIL | PASS | fail |
| 17 | F: EMA(9) cross exit (replaces vwap) | 9410 | $90,114 | 1.074 | 35.2 | -$54,953 | 1.64 | -$9,940.66 | $1,660.66 | 10.03 | -$22,151.48 | FAIL | FAIL | FAIL | FAIL | fail |
| 18 | F: EMA(20) cross exit (replaces vwap) | 5752 | $152,674 | 1.144 | 37.2 | -$62,942 | 2.43 | -$22,230.66 | $2,428.41 | 14.67 | -$5,201.70 | FAIL | FAIL | FAIL | FAIL | fail |
| 19 | F: EMA(50) cross exit (replaces vwap) | 2912 | $191,048 | 1.203 | 41.6 | -$48,911 | 3.91 | -$22,230.66 | $3,905.66 | 27.65 | $4,949.24 | FAIL | FAIL | FAIL | PASS | fail |
| 20 | G: chandelier trail k=2.0×ATR20d (replaces vwap) | 2005 | $188,033 | 1.180 | 52.6 | -$43,565 | 4.32 | -$17,631.66 | $8,342.91 | 55.01 | $22,453.92 | FAIL | FAIL | FAIL | PASS | fail |
| 21 | G: chandelier trail k=3.0×ATR20d (replaces vwap) | 1977 | $179,712 | 1.171 | 52.7 | -$61,050 | 2.94 | -$26,804.66 | $8,823.76 | 56.12 | $23,519.70 | FAIL | FAIL | FAIL | PASS | fail |
| 22 | H: 5-bar prior-extreme trail (replaces vwap) | 13886 | $32,190 | 1.026 | 30.3 | -$72,250 | 0.45 | -$3,475.66 | $996.81 | 6.38 | -$55,525.28 | PASS | FAIL | FAIL | FAIL | RISK-ONLY |
| 23 | H: 10-bar prior-extreme trail (replaces vwap) | 10386 | $87,825 | 1.085 | 26.5 | -$36,478 | 2.41 | -$3,475.66 | $1,054.26 | 6.76 | -$30,314.26 | PASS | FAIL | FAIL | FAIL | RISK-ONLY |
| 24 | H: 20-bar prior-extreme trail (replaces vwap) | 7808 | $132,792 | 1.152 | 21.5 | -$32,241 | 4.12 | -$3,475.66 | $1,109.26 | 7.14 | -$21,346.92 | PASS | FAIL | FAIL | FAIL | **RISK-ONLY — best (MAR)** |
| 25 | I: best-of-A (k=1.0) + best-of-E (N=24, fallback) | 3276 | $252,144 | 1.317 | 34.6 | -$27,634 | 9.12 | -$8,127.91 | $2,871.66 | 18.59 | $13,855.16 | PASS | PASS | PASS | PASS | **ADOPTABLE** |

Variant I selection: A's pool had one ADOPTABLE cell (A_k1.0, picked directly). E's
pool had **zero** ADOPTABLE cells, so E fell back to its best-MAR cell overall
(E_N24) per the pre-registered fallback. Composing them (ATR stop k=1.0 + time stop
N=24) gets MAR back up to 9.12 (from E_N24's standalone 7.11) — confirms the two
levers compose additively rather than fighting each other, but the ATR stop alone
(A_k1.0, MAR 9.00) already does almost all of that work; the time stop adds little.

---

## Tail comparison — top 5 by MAR vs baseline's 5 worst

**Baseline's 5 worst trades:**
| Date | PnL $ | Exit |
|---|---|---|
| 2025-04-07 10:15 | -$15,465.66 | primary (vwap) |
| 2022-03-08 12:35 | -$4,730.66 | primary (vwap) |
| 2025-04-07 14:00 | -$4,490.66 | eod |
| 2025-04-02 13:15 | -$4,440.66 | primary (vwap) |
| 2020-03-09 09:45 | -$4,150.66 | primary (vwap) |

**Top 5 variants by MAR** (all four are B/D-group protective stops):

| Rank | Variant | MAR | 5 worst trades |
|---|---|---|---|
| 1 | B k=1.0 | 12.39 | -$4,707 stop (2022-03-08) · -$4,656 stop (2025-04-07 14:00) · -$4,441 primary (2025-04-02) · -$3,461 primary (2022-08-26) · -$3,461 primary (2025-03-07) |
| 2 | B k=0.5 | 11.95 | -$3,461 primary (2022-08-26) · -$3,449 stop (2025-04-09) · -$3,266 primary (2020-03-12) · -$2,671 primary (2020-03-16) · -$2,500 stop (2025-04-07 14:20) |
| 3 | D P=100pt | 11.36 | -$3,461 primary (2022-08-26) · -$3,266 primary (2020-03-12) · -$2,671 primary (2020-03-16) · -$2,551 stop (2025-04-09) · -$2,406 primary (2015-08-24) |
| 4 | B k=2.0 | 10.55 | -$6,748 stop (2025-04-07 10:15) · -$4,731 primary (2022-03-08) · -$4,491 eod (2025-04-07 14:00) · -$4,441 primary (2025-04-02) · -$3,999 stop (2025-04-04) |
| 5 | D P=250pt | 9.29 | -$5,011 stop (2022-03-08) · -$5,011 stop (2025-04-07 10:15) · -$5,011 stop (2025-04-07 14:00) · -$5,011 stop (2025-04-09) · -$4,441 primary (2025-04-02) |

**Verdict: the stop catches the real disaster, and mostly leaves normal losers
alone.** The 2025-04-07 10:15 trade (the baseline's single worst, an entry that ran
772.75 points against the position over 5 bars during that session's shock move)
drops OUT of the top-5 entirely for B k=1.0 and D P=100pt — traced directly: baseline
holds it 5 bars for -772.75 pts; B k=1.0 exits it after 1 bar at -168.4 pts (a
~78% smaller loss, ~$3,380 vs $15,466). B k=2.0 and D P=250pt (looser stops) still
show it in their top-5 but sliced to -$6,748 and -$5,011 respectively — the stop
scales the damage down with its width, monotonically. Meanwhile the OTHER baseline
disasters (2022-03-08, 2025-04-02, 2022-08-26, 2020-03-xx) mostly survive unchanged
(`exit_kind: primary`) in every top-5 variant — these were "normal" bad trades that
never moved fast/far enough to touch even a fairly tight stop, so the stop isn't
just shaving routine variance, it's specifically cauterizing the outlier.

---

## Per-year table — best ADOPTABLE (B: band-width stop, k=1.0)

| Year | Baseline net $ | B k=1.0 net $ | Δ $ |
|---|---|---|---|
| 2010 | -$2,825 | -$2,770 | +$55 |
| 2011 | $237 | $9 | -$228 |
| 2012 | $1,421 | $2,252 | +$832 |
| 2013 | $372 | $798 | +$427 |
| 2014 | $4,345 | $4,075 | -$269 |
| 2015 | $6,189 | $5,922 | -$267 |
| 2016 | $6,443 | $7,052 | +$609 |
| 2017 | -$337 | -$2,075 | -$1,739 |
| 2018 | $36,071 | $38,396 | +$2,325 |
| 2019 | $6,595 | $6,684 | +$89 |
| 2020 | -$7,589 | $627 | **+$8,217** |
| 2021 | $42,538 | $39,434 | -$3,104 |
| 2022 | $67,713 | $65,039 | -$2,674 |
| 2023 | $19,429 | $19,558 | +$129 |
| 2024 | $58,085 | $55,688 | -$2,398 |
| 2025 (partial, thru 6/29) | $15,695 | $27,680 | **+$11,985** |
| **Total (pre-lockbox)** | **$254,383** | **$268,371** | **+$13,988** |

Notably, 2020 (NOISE 1.0's documented weak year — the VWAP exit whipsaws hardest in
COVID-crash volatility, per the plugin's own docstring) flips from -$7,589 to +$627 —
the stop directly addresses the plugin's own previously-banked weakness. 2025 also
improves sharply (the tariff-crash tail event lives there).

---

## Why: what is the stop actually doing to the trade population

**The core cost metric — % of stopped trades that would have recovered without the stop**
(shadow counterfactual: continue holding the same entry with the ordinary vwap exit,
ignoring the stop, and check if it eventually would have closed net-profitable):

| Variant | # trades stopped | # would've recovered | % (the "cost") |
|---|---|---|---|
| A k=1.0 | 5 | 0 | 0.0% |
| A k=1.5 | 1 | 0 | 0.0% |
| A k≥2.0 | 0 | — | never fires (baseline's worst trade only ran ~1.7×ATR20d) |
| **B k=0.5** | 1183 | 142 | 12.0% |
| **B k=1.0 (featured)** | **271** | **15** | **5.5%** |
| B k=2.0 | 21 | 0 | 0.0% |
| C (opposite-band) | 1 | 0 | 0.0% |
| D P=50pt | 379 | 67 | 17.7% |
| D P=100pt | 85 | 7 | 8.2% |
| D P=150pt | 31 | 3 | 9.7% |
| D P=250pt | 4 | 1 | 25.0% |
| E N=6 bars | 1671 | 420 | 25.1% |
| E N=12 bars | 948 | 222 | 23.4% |
| E N=24 bars | 425 | 103 | 24.2% |
| I (A k1.0 + E N24) | 430 | 103 | 24.0% |

**Mechanically:** the band-width stop (B) ties the stop distance to that specific
trade's own entry excursion — a trade that broke out further above the band gets
more room, one that barely broke out gets a tighter leash. At k=1.0, it intervenes
in 271 of 3185 trades (8.5%) and is wrong (would've recovered) only 5.5% of the
time — a favorable cost/benefit because it's discriminating on the same signal
(band excursion) that defines the entry itself, so it scales with the trade's own
character rather than applying a one-size-fits-all level. **Time stops (E) are the
blunt instrument**: they fire on ELAPSED TIME + sign only, blind to how far price
has actually moved, so 23-25% of everything they touch would have turned around —
roughly 4-5x costlier per intervention than the well-calibrated price stops. Very
tight stops (D P=50, B k=0.5) touch far more trades (379-1183) and pay for it with
higher false-positive rates (12-18%) — cutting DD further but bleeding real edge.
Very loose stops (A k≥2.0) essentially never fire (baseline's own worst trade only
ran to ~1.7×ATR20d, i.e. a k=2.0 ATR stop sits just outside where the real disaster
peaked) — so the ATR stop is "invisible insurance" until k drops to ~1.0-1.5, at
which point it earns its keep.

**Naked-tail problem — fixable, cheaply.** The single -$15,466 trade that defines
the whole tail-risk conversation is not an unstoppable artifact: it ran mechanically
through 5 bars of a real air-pocket move, and virtually any protective stop with a
meaningful width (B, D, even the composed I) catches it early with only modest
(single-digit-to-low-teens %) cost to the rest of the trade population.

---

## SPENT-YEAR OBSERVATION — one look, NOT evidence, does not change any verdict

Per the task's constraint, this is the **only** look at the sealed year
(2025-06-30 → 2026-06-30), taken **after** all pre-lockbox selection above was
frozen, using the single pre-lockbox-selected best-ADOPTABLE variant
(**B: band-width stop, k=1.0**) and nothing else. It is informational only.

| Metric | Pre-lockbox only (thru 2025-06-29) | Full window (incl. sealed year, thru 2026-06-30) |
|---|---|---|
| Trades | 3,185 | 3,429 |
| Net $ | $268,371 | $296,570 |
| PF | 1.334 | 1.307 |
| Win rate | 37.0% | 37.1% |
| Max DD | -$21,660 | -$21,660 (unchanged — no new peak-to-trough drawdown in the sealed year) |
| MAR | 12.39 | 13.69 |

The sealed year alone (2025-06-30 → 2026-06-30, i.e. full-window minus the
pre-lockbox partial-2025 net) contributed **+$11,621.50** net, on top of a max
drawdown that did not get any worse. Directionally consistent with the
pre-lockbox read — not used to select or re-rank anything above.
