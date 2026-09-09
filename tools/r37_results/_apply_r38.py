# one-shot (2026-09-08): round 38 rows 1382-1390 + docs + changelog + memory, applied on current main
import re, os
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); os.chdir(ROOT)
s = open('index.html', encoding='utf-8').read()
ns = [int(x) for x in re.findall(r"\bn:\s*(\d+)", s[s.find('const RESEARCH_STUDIES'):])]
assert max(ns) == 1381, max(ns)
STUDY = r"""      {key:'scalp38',title:'Round 38 - the 2-minute NOISE validate PASSES (run 334), the cost question answered, and the NOISE band is the trigger: four other triggers under the same exit all die',disc:'2026-09-08',isLbl:'PRE-LOCKBOX',fam:'NOISE',
       sub:'Three follow-ups to round 37. (1) The full-space NOISE Auto-Validate on the 2-minute master posted as run 334, PASS on all six gates, walk-forward 7 of 8, and its lockbox beats both 5-minute crowns on the same market days. (2) The owner asked whether the 0.533-point cost (10.66 dollars a round trip, about two ticks plus commissions) was too high: it is not high, and the cells that fail do so gross as well, but the 2m scalps ARE cost-sensitive, so every gate-passing 2m cell was re-scored at 15.66 and 20.66 dollars to find the cost-robust corner. (3) Round 37 four short-hold triggers were put on 2m bars under the NOISE VWAP-cross exit: 0 of 28 pass, so the band is the edge, not the exit. Selection window 2010-06-07 to 2025-06-29 for every local row.',
       notes:['RUN 334 (row 1382) IS THE FIRST NON-5-MINUTE NOISE VALIDATE AND IT PASSES. Verdict PASS 6 of 6, walk-forward 7 of 8 folds at efficiency 2.65, overfit probability 0.46 (some overfit risk), 7,885 trades, Sharpe 1.26. Its lockbox (2025-02-14 to 2026-07-16, 453 trades) earned 59,451 dollars at profit factor 1.28 with a 19,204 drawdown; on those same market days the 5-minute crowns earned 40,648 at 1.19 (run 243) and 24,553 at 1.12 (run 305). The runner picked a different corner from the round-37 search leader: narrow bands 0.5 and 1.0, VWAP exit, fixed stop 3.0, afternoon block; on the common window it is 7,427 trades, 335,478 dollars, profit factor 1.32, net over drawdown 12.2, R per year 104, median hold 8 minutes.',
              'THE COST IS NOT HIGH, BUT THE SCALP IS COST-SENSITIVE. 0.533 points is 10.66 dollars a round trip on the full NQ contract, roughly two ticks plus commissions, and every crown was graded on it. Re-run at zero cost the round-37 fixed-target cells still fail (best profit factor 1.11), so cost did not kill them. What cost DOES do is squeeze a 40-dollar trade: the R per year record cell (row 1321) goes from net over drawdown 25.9 at zero to 19.6 at 10.66, 11.4 at 15.66 and 5.4 at 20.66 (rows 1383). The crown 243 geometry on 2m holds better (31.6 to 24.8 to 19.8 to 11.0, row 1384). Of the 74 gate-passing 2m cells, 21 still clear the bar at 15.66 and 16 at 20.66.',
              'THE COST-ROBUST CORNER IS THE BAND EXIT IN THE AFTERNOON BLOCK. Row 1385 (band exit, ATR stop 0.75, three confirming closes, afternoon block, skip-short-after-weak-close, lookback 74, bands 1.0 and 1.75) is 3,621 trades, 247,998 dollars, profit factor 1.48, drawdown 13,438, net over drawdown 18.5 at the house cost, 16.2 at 15.66 and 14.2 at 20.66, 7 of 8 slices throughout, R per year 86, 64 dollars a trade, top-ten share 28 percent, median hold 16 minutes. It gives up the R per year record for a scalp that survives a second tick of slippage. Row 1386 (long only) is the most consistent cell: 8 of 8 slices at every cost.',
              'THE NOISE BAND IS THE TRIGGER, NOT JUST THE EXIT. Round 37 four short-hold triggers (micro opening range, open drive, prior-day high and low, range burst) were re-run on 2m bars with the NOISE VWAP-cross exit and with the ride exit: 0 of 28 pass (rows 1387 to 1390). The best is the 10-minute opening range with the VWAP exit at profit factor 1.18 and net over drawdown 5.3 with a 90 percent top-ten share. The band entry sizes itself to the day noise, which is what these fixed-level triggers cannot do.',
              'STATE OF PLAY: run 334 stands as the 2m card; the 1-minute twin (job RboN8x79sMiYCBgbOySp) is still running. Nothing is crowned or added to paper by this round. If a 2m NOISE leg is ever considered, the choice is between the runner champion (row 1382, most money, cost-fragile), the R per year record (row 1321, cost-fragile), and the cost-robust corner (row 1385), and it needs NinjaTrader parity on 2m bars first. Harnesses: tools/r38_scalp2m_triage.py, tools/r38_noise2m_cost_stress.py; outputs in tools/r37_results/.'],
       dashWhy:{wf:'Local harness rows carry no walk-forward; run 334 (row 1382) carries its own.',lb:'Local rows never load the lockbox; run 334 (row 1382) records its own lockbox.',tot:'Local rows: window 2010-06-07 to 2025-06-29.'},
       win:{from:'2010-06-07',to:'2025-06-29'},
       rows:[
        {n:1382,name:"RUN 334 - NOISE 1.0 full space on NQ 2-MINUTE bars (the round-37 queued validate)",what:"Auto-Validate of the parent NOISE file on the 2m master, 2010-06-07 to 2026-07-16, 8 walk-forward folds, 17-month lockbox from 2025-02-14. The board reads its window and trade count from the run itself. IS here is the run's own in-sample figure; the lockbox figure is the run's lockbox.",tone:'good',read:"PASS 6 OF 6. Walk-forward 7 of 8 folds (efficiency 2.65), overfit probability 0.46, 7,885 trades, Sharpe 1.26, whole-run drawdown 30,464. Lockbox 453 trades, plus 59,451 dollars, profit factor 1.28, drawdown 19,204 - better than either 5-minute crown on the same days. Runner champion on the common window: 7,427 trades, 335,478 dollars, profit factor 1.32, net over drawdown 12.2, R per year 104, hold 8 minutes; cost-fragile (net over drawdown 10.7 at 15.66, 7.5 at 20.66).",runs:[334],is:95437,lb:59451,dd:30464,pf:1.20,trd:7885,wr:33.1,sh:1.26,why:{wf:'The run records folds held (7 of 8), not a walk-forward dollar figure the board can read.'}},
        {n:1383,name:"COST SWEEP - the R per year record cell (row 1321) at 0 / 5.66 / 10.66 / 15.66 / 20.66 dollars a round trip",what:"Row 1321's parameters on NQ 2m RTH, same window, cost stepped from zero to four ticks. Figures on this row are the 15.66-dollar case (0.783 points).",tone:'frag',read:"COST-SENSITIVE. Net over drawdown 25.9 at zero, 22.5 at 5.66, 19.6 at 10.66 (the house cost), 11.4 at 15.66, 5.4 at 20.66; slices 8, 8, 6, 5, 4 of 8; dollars a trade 51, 45, 40, 35, 30. One extra tick of slippage each way halves the risk-adjusted return.",is:186849,tot:186849,dd:16438,pf:1.40,trd:5340,wr:15.6,evr:0.337},
        {n:1384,name:"COST SWEEP - the crown 243 configuration on 2m at the same five costs",what:"Row 1316's parameters (run 243, untouched) on NQ 2m RTH, cost stepped. Figures on this row are the 15.66-dollar case.",tone:'good',read:"HOLDS BETTER. Net over drawdown 31.6 at zero, 27.9, 24.8 at the house cost, 19.8 at 15.66, 11.0 at 20.66; 45 dollars a trade at 15.66. A 50-dollar average trade absorbs a tick the 40-dollar cells cannot.",is:287399,tot:287399,dd:14520,pf:1.30,trd:6431,wr:31.5,evr:0.21},
        {n:1385,name:"COST-ROBUST CORNER - band exit, ATR stop 0.75, 3 confirming closes, afternoon block, skip-short-after-weak-close (search rank 8)",what:"Every one of the 74 gate-passing 2m search cells re-scored at 10.66, 15.66 and 20.66 dollars and ranked by net over drawdown at 15.66 (tools/r38_noise2m_cost_stress.py). This is the best both-sides cell. Figures on this row are at the house cost.",tone:'good',read:"THE SCALP THAT SURVIVES A SECOND TICK. 3,621 trades, 247,998 dollars, profit factor 1.48, drawdown 13,438, net over drawdown 18.5 at the house cost, 16.2 at 15.66 and 14.2 at 20.66, 7 of 8 slices throughout, R per year 86 (79 and 71 under stress), 64 dollars a trade, top-ten share 28 percent, median hold 16 minutes. Trades the R per year record for cost robustness.",is:247998,tot:247998,dd:13438,pf:1.48,trd:3621,wr:26.0,evr:0.36},
        {n:1386,name:"COST-ROBUST CORNER - long only, afternoon block, band exit, 4 confirming closes (search rank 23)",what:"Same re-score, the most consistent cell. Figures at the house cost.",tone:'good',read:"8 OF 8 SLICES AT EVERY COST. 2,152 trades, 158,609 dollars, profit factor 1.55, drawdown 8,535, net over drawdown 18.6 at the house cost, 16.5 at 15.66, 14.6 at 20.66, R per year 58, 69 dollars a trade, top-ten share 31 percent. Fewer trades, the steadiest line on 2m.",is:158609,tot:158609,dd:8535,pf:1.55,trd:2152,wr:25.7,evr:0.41},
        {n:1387,fam:'SCALP',name:"r38 MICRO OPENING RANGE on 2m under the NOISE VWAP-cross exit (8 cells, shown: 10-minute range, VWAP exit)",what:"Round 38 harness (tools/r38_scalp2m_triage.py), NQ 2m RTH, 2010-06-07 to 2025-06-29, cost 0.533. First close beyond the first 3 or 5 two-minute bars in the first-candle direction; stop at the range's other side; exits: 1R target, 2R target, ride with breakeven, or exit at the next open after a close crosses the session VWAP against the trade.",tone:'fail',read:"DEAD UNDER EVERY EXIT. Best cell: 2,311 trades, 93,880 dollars, profit factor 1.18, drawdown 17,603, net over drawdown 5.3, 6 of 8, top-ten share 90 percent, median hold 30 minutes. The targets lose (profit factor 0.93 to 0.94); the ride exits hold three hours.",is:93880,tot:93880,dd:17603,pf:1.18,trd:2311,wr:29.4,evr:0.125},
        {n:1388,fam:'SCALP',name:"r38 OPEN DRIVE on 2m under the same four exits (shown: ride exit)",what:"Same harness. The 09:30 two-minute bar's direction at the 09:32 open, stop at that bar's other extreme.",tone:'fail',read:"DEAD. Ride: 3,725 trades, 78,277 dollars, profit factor 1.13, top-ten share 118 percent; VWAP exit 52,552 at 1.11 with 139 percent; both targets negative.",is:78277,tot:78277,dd:31473,pf:1.13,trd:3725,wr:10.3,evr:0.113},
        {n:1389,fam:'SCALP',name:"r38 PRIOR-DAY HIGH / LOW BREAK on 2m under the same four exits (shown: 0.20 daily-range stop, VWAP exit)",what:"Same harness. First 2m close beyond yesterday's session high or low, stop 0.10 or 0.20 of the 20-day average daily range, one per level per day.",tone:'fail',read:"DEAD. Best: 3,424 trades, 76,676 dollars, profit factor 1.11, drawdown 17,318, net over drawdown 4.4, 4 of 8, top-ten share 109 percent. The level break does not size itself to the day's noise the way the band does.",is:76676,tot:76676,dd:17318,pf:1.11,trd:3424,wr:30.9,evr:0.076},
        {n:1390,fam:'SCALP',name:"r38 RANGE BURST on 2m under the same four exits (shown: 3x average range, ride exit)",what:"Same harness. A bar with 3x or 4x its trailing 20-bar average range closing in the outer quarter, in the direction of the day so far; stop at the bar's other extreme; at most three a day.",tone:'fail',read:"DEAD, THE NEAREST MISS OF THE ROUND. 1,159 trades, 82,645 dollars, profit factor 1.36, drawdown 11,428, net over drawdown 7.2, 4 of 8 slices, top-ten share 112 percent: the ten best trades are the whole edge. The 4x cells are 360 trades with 200 percent top-ten shares.",is:82645,tot:82645,dd:11428,pf:1.36,trd:1159,wr:23.0,evr:0.277}
       ]},
"""
assert "{key:'scalp38'" not in s
i = s.find("{key:'scalp37'"); j = s.find("\n      ];", i); assert i > 0 and j > 0
s = s[:j + 1] + STUDY + s[j + 1:]
mv = re.search(r"const VERSION='([^']+)'", s).group(1); a_, b_ = mv.split('.'); nv = "%s.%d" % (a_, int(b_) + 1)
s = s.replace("const VERSION='%s';" % mv, "const VERSION='%s';" % nv, 1)
entry = ("{v:'%s',date:'2026-09-08',notes:['STUDIES BOARD: round 38 (rows 1382 to 1390). The 2-minute NOISE Auto-Validate posted as run 334: PASS 6 of 6, walk-forward 7 of 8, "
         "lockbox plus 59,451 dollars at profit factor 1.28 - better than either 5-minute crown on the same market days; its champion is a narrow-band VWAP-exit afternoon cell "
         "(R per year 104, median hold 8 minutes) and is cost-fragile.','The cost question: 0.533 points is 10.66 dollars a round trip (about two ticks plus commissions) and is not high; "
         "the round-37 scalp cells fail gross as well. But 2m scalps are cost-sensitive, so all 74 gate-passing 2m cells were re-scored at 15.66 and 20.66 dollars: 21 and 16 survive, and the "
         "cost-robust corner (band exit, afternoon block) keeps net over drawdown 16 to 14 under stress at 64 dollars a trade.','Four other short-hold triggers under the NOISE VWAP exit on 2m: 0 of 28 pass - the band is the trigger, not the exit.']},\n" % nv)
k = s.find("const CHANGELOG=[\n") + len("const CHANGELOG=[\n"); s = s[:k] + entry + s[k:]
open('index.html', 'w', encoding='utf-8').write(s)

# NOISE.md: round-38 subsection appended to the round-37 section (before the closing '---')
t = open('NOISE.md', encoding='utf-8').read()
anchor = "Files: `tools/r37_scalp_triage.py`, `tools/queue_noise_shortbar_validates.py`, results in\n`tools/r37_results/` (search CSVs, neighbourhood CSV, reference/concentration JSON, logs).\n"
assert anchor in t
R38 = anchor + """
### ROUND 38 (same day) — run #334 PASSES, the cost question, and the band is the trigger (rows 1382–1390, web v%s)

**Run #334 — `NOISE_1_0.py` full space on NQ 2m RTH, 2010-06-07 → 2026-07-16, 8 folds, 17-month lockbox
(2025-02-14 →).** Verdict **PASS 6/6**, WF **7/8** folds, wfe 2.654, PBO 0.46 ("some overfit risk"),
7,885 trades, Sharpe 1.26, whole-run DD 1,523 pts ($30,464). Champion: band 0.5 / 1.0 · VWAP exit ·
fixed stop 3.0 · confirm 4 · lookback 104 · afternoon block · skip-bot-short 0.3/0.95 · vol-skip 96.
**Lockbox 453 trades / +$59,451 / PF 1.283 / DD $19,204 — on the same market days #243 made +$40,648
at PF 1.19 and #305 +$24,553 at PF 1.12** (spent lockbox, confirmatory only). Champion on the common
2010-06-07..2025-06-29 window: n 7,427 / $335,478 / PF 1.315 / DD $27,517 / MAR 12.2 / EV R 0.21 /
R/YR 104 / top-10 24% / median hold 8 min. Cost-fragile: MAR 10.65 at 0.783, 7.49 at 1.033 (4/8 slices).
Note: the doc's header `best_*` fields (5,505 trades / $95,437 / PF 1.20 / DD $10,929) are the run's own
IS-stage figures, not the whole optimize window; the engine reproduces the champion at 7,282 trades /
$337,659 on the optimize window. `tools/r37_results/run334_champion_read.json`.

**The cost question (owner: "$10 seems high round trip but idk").** 0.533 pts = $10.66 on NQ = about
two ticks plus commissions, the same number every crown was graded on. It is not what killed the 1m
cells — rerun at ZERO cost the 25 fixed-target cells still fail (best PF 1.11, MAR 3.6;
`r37_scalp_triage_GROSS.csv`). What cost does is squeeze a $40 trade:

| config | $0 | $5.66 | $10.66 (house) | $15.66 | $20.66 |
|---|---|---|---|---|---|
| R/YR record (row 1321), MAR | 25.9 (8/8) | 22.5 (8/8) | 19.6 (6/8) | 11.4 (5/8) | 5.4 (4/8) |
| daytype-off neighbour (row 1322), MAR | 34.7 | 29.8 | 23.8 (7/8) | 9.3 (4/8) | 4.7 |
| #243 crown config on 2m (row 1316), MAR | 31.6 | 27.9 | 24.8 (7/8) | 19.8 (5/8) | 11.0 |
| run #334 champion, MAR | — | — | 12.2 (7/8) | 10.7 (4/8) | 7.5 (4/8) |

`tools/r38_noise2m_cost_stress.py` re-scored all 74 gate-passing 2m cells at 0.533 / 0.783 / 1.033:
**21 still clear the bar at 0.783, 16 at 1.033.** The cost-robust corner is the **band exit in the
afternoon block**: search rank 8 (row 1385: band exit · ATR stop 0.75 · confirm 3 · afternoon block ·
skip-bot-short · lookback 74 · bands 1.0/1.75 · vol-skip 93) = n 3,621 / $247,998 / PF 1.483 / DD $13,438
/ **MAR 18.5 → 16.2 → 14.2** / 7/8 at every cost / R/YR 86 → 79 → 71 / $64 a trade / top-10 28% / hold
16 min; rank 23 (row 1386, long only) = MAR 18.6 → 16.5 → 14.6 with **8/8 at every cost**, $69 a trade.
`tools/r37_results/noise2m_cost_stress.csv`, `noise2m_cost_sensitivity.json`.

**The band is the trigger, not the exit (`tools/r38_scalp2m_triage.py`, 0 of 28).** Round 37's four
triggers (micro OR 3/5 bars, open drive, PDH/PDL 0.10/0.20, range burst 3x/4x) on 2m bars under four
exits (1R, 2R, ride-BE, and NOISE's own VWAP-cross exit): best cell micro-OR 10-min / VWAP exit at
PF 1.18 / MAR 5.3 / top-10 90%; range-burst 3x / ride PF 1.36 / MAR 7.2 / top-10 112%. The band entry
sizes itself to the day's realized noise; a fixed level cannot, and the VWAP exit does not rescue it.

**Three 2m NOISE candidates now exist, none crowned:** the runner's #334 champion (most money,
cost-fragile), the R/YR record (row 1321, cost-fragile), and the cost-robust corner (row 1385). A
2m leg would need NT parity on 2m bars first; the 1m validate (job `RboN8x79sMiYCBgbOySp`) is running.
""" % nv
t = t.replace(anchor, R38); open('NOISE.md', 'w', encoding='utf-8').write(t)

# BOOKMARKS: status update on B26 + a B28 row + round-38 line
b = open('BOOKMARKS.md', encoding='utf-8').read()
old = "| **Auto-Validate QUEUED — `NOISE_1_0.py` FULL space on the NQ 2m master, job `qsSDwagxJsahDSmAwx1r`** (spent-lockbox caveat on the card) |"
assert old in b
b = b.replace(old, "| **VALIDATED — run #334 PASS 6/6, WF 7/8, LB +$59,451 / PF 1.28 (beats both 5m crowns on the same days); the runner's champion is a different corner (row 1382, MAR 12.2, R/YR 104, cost-fragile).** Round 38: the R/YR record itself is cost-fragile (MAR 19.6 → 11.4 at 0.783) |")
b += """
### Round 38 addendum (2026-09-08) — run #334, the cost question, the band is the trigger (rows 1382-1390, v%s)

| # | What | Numbers | Where | Status |
|---|---|---|---|---|
| **B28** | **Cost-robust 2m NOISE corner** — band exit · ATR stop 0.75 · confirm 3 · afternoon block · skip-bot-short · lookback 74 · bands 1.0/1.75 · vol-skip 93 | n=3,621 · $247,998 · PF 1.48 · DD $13,438 · **MAR 18.5 / 16.2 / 14.2 at $10.66 / $15.66 / $20.66** · 7/8 at every cost · R/YR 86 · $64/trade · top-10 28% · hold 16 min | STUDIES row 1385; `tools/r38_noise2m_cost_stress.py` | candidate — inside run #334's own search space, not separately validated |
| B29 | Run #334's champion (narrow bands 0.5/1.0, VWAP exit, afternoon block) | common window n=7,427 · $335,478 · PF 1.32 · MAR 12.2 · R/YR 104 · hold 8 min; LB +$59,451 / PF 1.28 | Past Runs #334; row 1382 | PASS 6/6 but cost-fragile (MAR 7.5 at $20.66) |

- **TIER 3:** the house cost (0.533 pts = $10.66) is two ticks plus commissions, not high; the round-37 scalp cells fail at ZERO cost too. A $40-a-trade scalp loses half its MAR to one extra tick each way; a $60+ trade does not. Judge any sub-5m cell at 0.783 as well as 0.533.
- **TIER 3:** the NOISE band is the trigger. Four other 2m momentum triggers under NOISE's own VWAP exit: 0 of 28 (`tools/r38_scalp2m_triage.py`).
""" % nv
open('BOOKMARKS.md', 'w', encoding='utf-8').write(b)

# BACKTESTING_STACK changelog bullet
c = open('BACKTESTING_STACK.md', encoding='utf-8').read()
h = "## Changelog\n"; k = c.find(h) + len(h)
line = ("- **2026-09-08 (round 38 — run #334 PASSES, the cost question, the band is the trigger; STUDIES rows 1382-1390, web v%s).** "
        "**Run #334 = `NOISE_1_0.py` full space on NQ 2m RTH (2010-06-07..2026-07-16, 8 folds, 17-mo LB): PASS 6/6, WF 7/8 (wfe 2.65), PBO 0.46, 7,885 trades, Sharpe 1.26; LB 453 tr / +$59,451 / PF 1.28 / DD $19,204 — beats #243 (+$40,648 / 1.19) and #305 (+$24,553 / 1.12) on the same market days (spent LB, confirmatory).** "
        "Champion (bands 0.5/1.0, VWAP exit, fixed stop 3.0, afternoon block) on the common window: n 7,427 / $335,478 / PF 1.315 / MAR 12.2 / R/YR 104 / hold 8 min; cost-fragile (MAR 10.7 at 0.783). "
        "Cost: 0.533 pts = $10.66 = ~2 ticks + commissions; the r37 fixed-target cells fail at zero cost too (best PF 1.11). All 74 gate-passing 2m cells re-scored at 0.533/0.783/1.033 (`tools/r38_noise2m_cost_stress.py`): 21 / 16 survive; the R/YR record (row 1321) drops MAR 19.6 → 11.4 → 5.4, the crown-#243 geometry holds 24.8 → 19.8 → 11.0, and the cost-robust corner (row 1385: band exit, ATR stop 0.75, confirm 3, afternoon block) holds 18.5 → 16.2 → 14.2 with 7/8 at every cost, $64/trade. "
        "`tools/r38_scalp2m_triage.py`: round-37's four triggers on 2m under NOISE's VWAP exit = 0/28 — the band is the trigger. 1m validate (job RboN8x79sMiYCBgbOySp) still running. Full doc: `NOISE.md` round 38.\n" % nv)
c = c[:k] + line + c[k:]; open('BACKTESTING_STACK.md', 'w', encoding='utf-8').write(c)

# memory
mem = r"C:\Users\xride\.claude\projects\C--Users-xride-OneDrive-Desktop-EDGE-LOG\memory\edgelog-round37-scalp-hunt.md"
m = open(mem, encoding='utf-8').read()
m = m.replace("- Board: STUDIES rows 1315–1336", """- **Round 38 (same day):** run **#334** = the 2m validate, PASS 6/6, WF 7/8, LB +$59,451 / PF 1.28
  (beats both 5m crowns on the same days); champion = narrow-band VWAP-exit afternoon cell, MAR 12.2,
  R/YR 104, cost-fragile. Cost 0.533 pts = $10.66 = ~2 ticks + commissions, NOT high; r37 cells fail
  at zero cost too. 2m scalps ARE cost-sensitive: R/YR record MAR 19.6 → 11.4 at 0.783; cost-robust
  corner = band exit + afternoon block (row 1385, MAR 18.5 → 16.2 → 14.2, $64/trade). Four other 2m
  triggers under the NOISE VWAP exit: 0/28 — the band is the trigger. Rows 1382–1390.
- Board: STUDIES rows 1315–1336""")
open(mem, 'w', encoding='utf-8').write(m)
print("applied: rows 1382-1390, VERSION", mv, "->", nv)
