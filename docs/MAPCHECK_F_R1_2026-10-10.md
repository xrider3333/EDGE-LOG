# MAPCHECK-F r1 - the house futures / book power-first check, first pass over the parked ideas (Custom ML, 2026-10-10)

MANAGER #91 (3): build MAPCHECK-F on MDL r1's generator (FRONTIER OK #92), then run it over the ideas parked in
RESEARCH.md / the candidate board and send the top 3 that clear it. Tool: `tools/mapcheck_f.py`. Output:
`C:\EdgeLog\custom_ml\mapcheck_f\MAPCHECK_F.txt` / `.csv`.

## What it does
- An idea becomes a PRIOR: trades a year, yearly Sharpe (mid +- sd, from the ledger evidence, decayed / halved for
  selection), its correlation with #463 on #463's drawdown days and elsewhere, tails, volatility shape.
- 2,000 synthetic daily legs per prior from MDL r1's `gen_leg` (r12_mdl imported, never edited; seed [20261010, k],
  printed). Each leg is read on its own (WF ROC @ $30k) and added to #463 at the c that MDL r1 freezes on the WF ROC.
- #463 is loaded from r11's cache and refused unless WF 93.81 / Sortino 3.816 reproduce. The S1 line
  (file e204dd53, 121.06) is read through seat_pipeline's `line_L`, parity-checked.
- WALK-FORWARD only. #463's lockbox is spent (BOOK LOOKS r1): no LB lift is printed. Synthetic priors are not book looks.

## Rules (frozen before the pass)
1. Fewer than 50 trades a year = GREYED: cannot be a seat on its own (no 50 sealed-year trades).
2. Median own ROC < ~8 AND P(own >= 15) < ~10% (MANAGER #84) = close at draft, unless the leg earns while the book falls.
3. P(book lift on #463, WF) under 30% = close at draft.
CLEARS = passes all three = worth a prereg.

## Result
| Idea (ledger) | Trades/yr | Own ROC median | P(own >= 15) | P(lift #463) | P(lift S1) | Verdict |
|---|---|---|---|---|---|---|
| EVENT-SLEEVE (TLT pre-auction short + ES month-end + NQ 08:30 fade as ONE leg) | 55 | 11.6 | 39% | 56% | 41% | CLEARS |
| - same, the 08:30 fade worth nothing | 55 | 7.3 | 26% | 42% | 27% | CLEARS |
| - same, every part halved again | 55 | 4.2 | 16% | 31% | 20% | CLEARS (at the bar) |
| MONTHEND-ES (2.18) | 8 | 8.4 | 33% | 46% | 32% | GREYED |
| AUCTION-K5 (2.70) | 24 | 4.7 | 20% | 36% | 24% | GREYED |
| MACRO830-FADE (2.95) | 23 | 3.7 | 15% | 25% | 11% | GREYED |
| OVERNIGHT-DOWNDAY (2.13) | 100 | 1.5 | 4% | 14% | 6% | CLOSE |
| GEX-MOMENTUM (literature) | 250 | 3.9 | 9% | 1% | 0% | CLOSE |
| TRANSFER-CME (2.29) | 400 | 2.0 | 7% | 4% | 1% | CLOSE |
| XLK-NOISE (2.108, calibration only) | 314 | 36.5 | 98% | 34% | 2% | calibration |

- **One idea clears: the EVENT SLEEVE.** Its three parts each lift the book in a third to a half of draws but are too
  rare to be seats alone; pooled they reach 55 trades a year on unrelated calendars. Even with the weakest part set
  to zero it clears; with every part halved again it sits on the 30% bar.
- **Closed at draft:** OVERNIGHT-DOWNDAY (too thin), GEX-MOMENTUM (moves with the book; GAMMA r1 2.135-2.137 has
  since closed GEX as a filter on real data), TRANSFER-CME (moves with the book, thin per trade).
- **Calibration:** the measured XLK book add was 98.6 (2.108); the tool's median for a leg built to XLK's measured
  strength is 94.9 (lift 34%). **Correction 10-14 (FRONTIER #111):** 98.6 sits at the 63rd percentile of that
  prior's 2,000 draws (p25 86.4, p75 101.8) - one draw inside the middle half, so no bias is shown; it was also read
  after XLK was chosen. The generator stays frozen; where a measured book add exists, print it beside the map.
- The S1 bar is harder (P(lift) 0-41%): S1 already holds the residual-momentum leg, so any new leg competes with it.

## Next - and the catch on the sleeve
- **All three parts have already been run on the walk-forward years** (2.18 month-end, 2.70 AUCTION K5, 2.95 the
  08:30 fade mirror), and 2.18's scan printed its lockbox columns. A real-data Stage A of the sleeve on those years
  would re-add numbers we have seen, picked as the near-misses of 36 + 6 + 8 cells - it cannot be a fresh test.
  The map prior already halves each part for that selection; the history can only check the pooling arithmetic.
- **A fair test is forward only:** freeze the three calendars, sizes and the bar now, then judge on trades after the
  freeze (a paper shadow; ~55 trades a year means ~1 year to 50 trades). MANAGER advised against a forward shadow
  of AUCTION alone (2.70: the seat moves with K) - the sleeve freezes K = 5 before any forward trade.
- Any pilot daily series of the sleeve added to #463 = ONE book look (FRONTIER #92): MANAGER's line first.
