# PRE-REGISTRATION - NOISE #422 anatomy: which mechanism, not which size (scope rank 1; MANAGER #63 / #64)

Drafted 2026-10-05 evening by the NOISE lane, before any real bucket table was printed. The only output so far is the
null bands below (`--power` mode). Harness: `tools/noise_r422_anatomy.py`.

## What it is - and what it is not
A REPORT. It names the mechanism NOISE #422 earns on, so the habitat queue (IWM, QQQ, sector funds, TLT) knows what to
look for. Rules mined this way were regime artifacts (ledger 2.1), so:
- **No rule is mined.** No filter, size or setting on NQ changes.
- **No bar is passed or failed.**
- **The deliverable is one sentence:** "NOISE earns on ...". Plus a short list of which habitats share that day
  structure, which re-ranks the queue.

## The trades
- **Strategy:** #422 = NOISE_1_8_CT304H (60-minute compression gate 20 / 1.15, 1.75x) on the NQ 5m RTH no-adjust master,
  rebuilt by the engine. 2,797 trades with a signal date 2016-07-01 .. 2025-06-29 (the book's walk-forward).
- **Signal-bar tagging:** every trade is tagged at its SIGNAL bar, the bar whose close decided the entry (fill bar
  minus 1), never the fill bar.
- **Dollars at 1 NQ:**
  - UNIT = the #304 core trade, with the compression size divided out. This is the mechanism read.
  - SIZED = #422 as traded, shown beside it.
- **Every table prints:**
  - n, unit $, unit $/trade, PF, share of unit dollars and sized $;
  - the same columns for H1 (2016-07 .. 2021-12) and H2 (2022-01 .. 2025-06);
  - the null band.

## The tables (frozen)
- **B1 - hour.** The signal bar closes 09:40-10:25 (opening drive), 10:30-13:55 (midday) or 14:00-15:55 (late flow).
- **B2 - exit path.**
  - Exit kind: VWAP exit at the next open / stop inside the bar / end of day.
  - Holding time: <= 3 bars / 4-12 / > 12.
  - Median best and worst point (NQ points) for winners and losers.
  - These are descriptive of OUTCOMES, so they get no null.
  - **ROOM TO PAY (MANAGER #63's row):** the gap between the signal close and the session VWAP at that close, in % of
    price, split into terciles. A trade entered near VWAP has little room before its own exit fires.
- **B3 - day type and volatility state.**
  - Open gap |open / prior close - 1|: < 0.25% / 0.25-0.75% / >= 0.75%.
  - Ex-post day shape by close location (>= 0.8 trend up, <= 0.2 trend down, else range). DESCRIPTIVE ONLY: it is not
    knowable at entry and must never become a rule.
  - FOMC / CPI / NFP day (tools/data calendars; fomc_dates.txt is the canonical Fed list).
  - Prior-day range percentile vs 252 sessions, in terciles.
  - The 60-minute squeeze on or off at the signal bar.
- **B4 - side by market state.** Long / short x prior close above / below its 200-session average; and 2022 alone (no
  null - it is a year).
- **B5 - order within the session.** First break / second / third or later.

## Nulls = the power line of a report (printed BEFORE any real bucket)
- **Intraday tags** (hour, room to pay, squeeze, order) are shuffled among the trades of the SAME session. This keeps
  every day effect and tests only the within-day contrast.
- **Day-level tags** (gap, shape, event, range percentile, market state) are shuffled among the sessions of the SAME
  year. This keeps every year effect.
- 1,000 draws, seed 20261006. Each bucket's 5-95% band of UNIT $/trade is printed beside the real number.
- **Disclosed:** sessions with a single trade cannot be shuffled within the session, so the intraday bands are NOT
  blind. They still carry those trades' real values. The bands below were printed before the tables and read only as
  bands.

**Power output (--power, 2026-10-05 ~20:15 MST), unit $/trade null 5-95%:**

| Tag | Buckets |
|---|---|
| B1 hour | 09:40-10:25 162 .. 210; 10:30-13:55 50 .. 106; 14:00-15:55 -3 .. 76 |
| B2 room | near VWAP 52 .. 94; middle 82 .. 129; far 152 .. 200 |
| B3 squeeze | off 82 .. 93; on 224 .. 267 |
| B5 order | first 211 .. 260; second -44 .. 67; third+ -28 .. 23 |
| B3 gap | < 0.25% 58 .. 141; 0.25-0.75% 78 .. 165; >= 0.75% 71 .. 227 |
| B3 shape | range 66 .. 145; trend down 58 .. 227; trend up 75 .. 175 |
| B3 event | CPI -40 .. 302; FOMC -50 .. 324; NFP -40 .. 290; none 105 .. 131 |
| B3 range percentile | low 56 .. 143; mid 66 .. 170; high 89 .. 200 |
| B4 state | long/above 75 .. 125; long/below 113 .. 313; short/above 40 .. 156; short/below 20 .. 449 |

**How to read it:**
- The event and below-200 buckets are wide: few days, and a difference under about $150 a trade there cannot be told
  from chance.
- The hour, room, squeeze and order bands are narrow: about $30-50 wide.

## Deliverable and what follows
- One mechanism sentence, the tables, a NOISE.md section and a RUNBOARD research row (report). Nothing passes or fails.
- The sentence re-ranks the habitat queue only through the scope doc, with MANAGER's review.
- Then IWM (07:00 per MANAGER #64) and the QQQ calibration second.

## AMENDMENT 1 - MANAGER review (GO at 21:05 with two additions), 2026-10-05 ~20:35 MST, before any real table
1. **X - hour x break order, 3 x 3,** with the within-session null on the combined tag. The mechanism sentence is
   written FROM THIS TABLE, not from the B1 / B5 margins.
   - Null band (printed before the run), unit $/trade, 5-95%:

     | Hour | first | second | third+ |
     |---|---|---|---|
     | 09:40-10:25 | 201 .. 265 | -117 .. 104 | -329 .. 104 |
     | 10:30-13:55 | 218 .. 291 | -69 .. 93 | -39 .. 34 |
     | 14:00-15:55 | 163 .. 163 | -103 .. 166 | -31 .. 54 |

   - **Disclosed:** the late "first" cell's band is degenerate (163 .. 163). Every session in it has a single trade in that
     cell, so the null cannot move it. Read that cell without a null.
2. **Single-trade sessions:** their share of trades and of unit dollars (the intraday nulls cannot shuffle them).
3. **Room to pay in NQ points** beside the % of price: the median points per tercile.

## RESULT (run once, 2026-10-05 21:05 MST, after reading the inbox)
- **The sentence, from the hour x order cross-tab in unit dollars:** NOISE #422 earns on the one break of a trend day
  that never comes back through VWAP and is held to the close. The hour and the break order add nothing once that is
  known.
- **Why:** all nine cells are positive. Single-trade sessions are 29% of the trades and 97% of the unit dollars. The
  multi-break sessions net about $9k over 1,998 trades.
- **Tables:** `tools/r37_results/noise_r422_anatomy.txt`.
- **Habitat day-shape and cost table** (price bars only, written after the tables): `tools/noise_r422_habitats.py`,
  `tools/r37_results/noise_r422_habitats.txt`.
- **Write-up:** NOISE.md "#422 anatomy".
