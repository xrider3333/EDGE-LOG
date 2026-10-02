# PRE-REGISTRATION — NOISE round 68: breakeven at +1R on a CLOSE, then ride (2026-10-02)

Owner idea via MANAGER (inbox #21, from the CBU review): once a trade is up 1R, move the stop to entry and let it run
to the strategy's normal exit. Written and committed before any breakeven trade was computed.

Prior evidence, stated up front: round 52 (2026-09-09) tested a breakeven at 0.5 / 1.0 / 1.5 R on the #304 crown with
the trigger on the previous bar's finished EXTREME, ranked on profit factor: a wash (1.0R bought ~5% of drawdown for a
hair less money; every variant slightly worse 2010-23, slightly better since 2024). Its fenced Auto-Validate, run #374,
came back WEAK and the runner's own search chose NO breakeven. What is new here: the trigger is a bar CLOSE at +1R (the
owner's rule), the bases are the two sized legs the owner trades or shadows (NOISE #382 and #422), and the judge is
the owner yardstick in dollars, not profit factor or R.

Rule, fixed now: R = the distance from the fill price to the trade's own initial protective stop (the crown's bandwidth
stop). When a bar CLOSES with the open trade at least 1.0 R in profit (the fill bar's own close counts), the stop moves
to the fill price for every later bar; it never moves again. The stop is checked exactly as the crown checks it (a bar
that opens through it exits at that open, otherwise at the stop), so a breakeven exit costs the round-trip cost and any
gap. Everything else unchanged; re-simulated inside the strategy (NOISE_1_0.py patched in memory), so a slot freed by a
breakeven exit can take a later break the same day. Each trade keeps its leg's size rule: #382 = 2.0x when the 30-minute
compression gate (16 bars, ratio 1.15) is on at the decision bar, else 1x; #422 = 1.75x on the 60-minute gate (20 bars,
ratio 1.15). The rebuilt legs must reproduce the leg strategy files trade for trade before any breakeven is run.
Neighbours reported, never picked from: 0.5 R and 1.5 R. Descriptive only: #304 unsized, share of trades that reach the
move, share that then exit at breakeven.

Data, cost and stretches as rounds 63-67: NQ 5-minute RTH no-adjust master to 2026-09-16, cost 0.533 per contract, $20
per point, $100k account, WF 2016-06-30 .. 2025-07-16, LB .. 2026-07-16. RAW TWIN = the same leg with the crown's exit
unchanged. OWNER YARDSTICK on BOTH legs: ROC %/yr at a $30k worst drawdown (drawdown valued daily) AND Sortino beat the
twin in BOTH stretches; >= 100 WF / 50 LB trades; LB profitable without its biggest trade; both neighbours beat the
twin's WF ROC at $30k. Judged in dollars, never on R statistics (a breakeven shrinks the average loss and flatters
anything in R). BOOK #463 reference for scale: WF 93.8 / LB 155.5. A survivor gets a fenced house Auto-Validate (pinned
date_from/date_to, 900 trials) then the RUNBOARD watch list; a failure is recorded dead.
