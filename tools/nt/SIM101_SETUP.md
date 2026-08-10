# PAPER Layer 1 — Sim101 auto-execution setup (owner checklist)

Two NinjaScript strategies port the crowned configs for automated paper trading on
Sim101. Fills flow into EDGELOG automatically through the existing AddOn →
`C:\EdgeLog\fills.csv` → runner sync, tagged `account: Sim101` (use the ACCOUNT
toggle in the app to see them separately from real trades).

Files (also copied to `Documents\NinjaTrader 8\bin\Custom\Strategies\`):

| Strategy | Port of | Config | Chart |
|---|---|---|---|
| `EdgeLogORB30` | ORB_3_0.py | #125: OR=1 bar · Both · stop 0.75×range · vol 1.25× · flat EOD | NQ · **5 Minute** · RTH session template |
| `EdgeLogENGUQ1m` | ENGUQ_1M_1_0.py | #149 + breakeven 1.5 (long only, trail 2.5R, holds overnight) | NQ · **1 Minute** · RTH session template · load ≥30 days |

## One-time setup (~10 min, owner does this — needs NT open)

1. **Compile:** NinjaTrader ▸ New ▸ NinjaScript Editor ▸ press **F5** (Compile).
   Both strategies were written against the standard NT8 API but have NOT been
   compiled yet — if the editor reports errors, paste them back to Claude.
2. **ORB chart:** open NQ (current contract) 5-Minute, session template
   *CME US Index Futures RTH*. Right-click ▸ Strategies ▸ add **EdgeLogORB30**,
   account **Sim101**, leave all inputs at defaults, ENABLE.
3. **ENGU-Q chart:** open NQ 1-Minute, same RTH session template, **Days to load: 30+**.
   Add **EdgeLogENGUQ1m**, account **Sim101**, defaults, ENABLE.
4. Leave NT running through the session (the OHLC AddOn already requires this anyway).

## What to expect

- ORB: at most one real trade/session, enters on a stop at the range edge within
  the first minutes, out by 16:00 ET. Occasional tiny "thin-vol" scratch trades
  are BY DESIGN (live can't know a bar's volume before it closes; the backtest
  can — the scratch is the honest live version of "skip that break").
- ENGU-Q: rarer (≈2-3/week), long-only, can hold overnight.
- If the strategy was enabled mid-session, ORB waits for the next session open.
- Both trade 1 contract. Sim101 fills appear in EDGELOG within ~20s of execution.

## Known model gaps (why Sim101 won't exactly match the shadow log — that's the point)

1. ENGU-Q enters at market on the bar close signal → ~1 tick of slip vs the
   engine's fill AT the close.
2. ENGU-Q's trailing stop updates at bar closes; the engine updates it with the
   same bar's high before checking that bar's low (idealized). Spike bars can
   exit at the previous stop level.
3. ORB's volume filter → thin-vol scratches (see above); the engine has none.
4. Stop-vs-target same-bar ties resolve by real intrabar sequence, not the
   engine's pessimistic stop-first rule.
5. Data: NT continuous contract vs the engine's Databento master — entry TIMES
   should line up; prices can differ by roll/adjustment.

The daily reconcile (shadow vs Sim101) quantifies exactly these gaps.
