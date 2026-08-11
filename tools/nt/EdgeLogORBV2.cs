// =============================================================================
//  EDGELOG · ORB V2 — "volume-confirmed chase" — the live-legal ORB
//
//  WHY THIS FILE EXISTS
//  The crowned ORB #125 cannot be executed as backtested: it fills at the range
//  edge the moment price touches it (intrabar), but only keeps the trade if that
//  bar's FINISHED volume clears the gate (vol_filter × mean of the session's
//  prior bar volumes). At fill time that volume total does not exist yet.
//  Measured on real 10s data (tools/orb_volarm_10s.py): in 0 of 32 engine trades
//  had the volume arrived before the touch. The information always comes second.
//
//  V2 RULE (nothing here uses the future):
//  Volume only accumulates. So watch the FORMING 5-minute bar in real time:
//    • gate for this bar = VolFilter × mean volume of the session's CLOSED bars
//      (fully known when the bar opens)
//    • the moment the forming bar's volume-so-far ≥ gate AND price has touched
//      the range edge (either order), enter AT MARKET in the touch direction.
//  Same trade selection as the engine. The fill is honest: at the level if
//  volume confirmed first, a chased price if the touch came first. Measured
//  chase cost over 34 sessions: mean −1.0 pt, median −2.6 (worst +177).
//
//  Chart: NQ ##-## · 5 Minute · session template "CME US Index Futures RTH".
//  Account: the broker DEMO account (paper). Calculate is forced OnEachTick —
//  the whole point is watching volume DURING the bar.
//
//  Notes:
//  • Trades only in REAL TIME. Historical bars carry no intrabar sequencing, so
//    a historical simulation of V2 would be exactly the look-ahead we're
//    eliminating. On enable it waits for the next live session.
//  • One real trade per session, stop = StopFrac × range from the fill,
//    ride to session close (flatten ~20s before), long+short (TradeMode).
//  • No thin-vol ejections exist here — V2 never enters unconfirmed.
// =============================================================================
#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class EdgeLogORBV2 : Strategy
    {
        // session state (closed-bar bookkeeping)
        private int      barsClosed;          // closed bars in this session
        private double   orHi, orLo, sessOpen, orClose, rng, upLvl, dnLvl;
        private double   cumVolClosed;        // summed volume of closed session bars
        private double   gate;                // volume gate for the CURRENT forming bar
        private int      orDir;
        private bool     orDone, tradedThisSession;
        private int      touchSide;           // forming bar: +1/-1 once an edge is touched
        private DateTime sessionEnd = DateTime.MaxValue;
        private double   entryFill;
        private bool     stopPlaced;
        private bool     catchupDone;   // mid-session enable: one-time replay of today's closed bars

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name        = "EdgeLogORBV2";
                Description = "EDGELOG ORB V2 - volume-confirmed chase (live-legal, no look-ahead)";
                Calculate   = Calculate.OnEachTick;      // required: we watch volume DURING the bar
                EntriesPerDirection = 1;
                EntryHandling = EntryHandling.AllEntries;
                IsExitOnSessionCloseStrategy = true;     // belt: NT's own flattener as backstop
                ExitOnSessionCloseSeconds = 10;
                IsInstantiatedOnEachOptimizationIteration = false;
                StartBehavior = StartBehavior.WaitUntilFlat;
                BarsRequiredToTrade = 1;

                OrBars    = 1;
                TradeMode = "Both";
                StopFrac  = 0.75;
                VolFilter = 1.25;
                Qty       = 1;
            }
        }

        private void ResetSession()
        {
            barsClosed = 0; orHi = double.MinValue; orLo = double.MaxValue;
            sessOpen = Open[0]; orClose = double.NaN; rng = 0;
            cumVolClosed = 0; gate = double.MaxValue; orDir = 0;
            orDone = false; tradedThisSession = false; touchSide = 0;
            entryFill = 0; stopPlaced = false;
            try
            {
                var si = new SessionIterator(Bars);
                si.GetNextSession(Time[0], true);
                sessionEnd = si.ActualSessionEnd;
            }
            catch { sessionEnd = DateTime.MaxValue; }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0) return;

            // ── new-bar bookkeeping (first tick of every bar) ────────────────────
            if (IsFirstTickOfBar)
            {
                if (Bars.IsFirstBarOfSession)
                {
                    ResetSession();
                }
                else if (CurrentBar > 0)
                {
                    // the bar at index 1 just CLOSED — fold it into session stats
                    if (barsClosed < OrBars)
                    {
                        orHi = Math.Max(orHi, High[1]);
                        orLo = Math.Min(orLo, Low[1]);
                        if (barsClosed == OrBars - 1) orClose = Close[1];
                    }
                    cumVolClosed += Volume[1];
                    barsClosed++;
                    if (!orDone && barsClosed >= OrBars)
                    {
                        rng = orHi - orLo;
                        if (rng > 0)
                        {
                            upLvl = Instrument.MasterInstrument.RoundToTickSize(orHi);
                            dnLvl = Instrument.MasterInstrument.RoundToTickSize(orLo);
                            orDir = (!double.IsNaN(orClose)) ? (orClose >= sessOpen ? 1 : -1) : 0;
                            orDone = true;
                        }
                    }
                    // volume gate for the NEW forming bar: engine's sv[:k].mean() × filter
                    gate = (VolFilter > 0 && barsClosed > 0)
                         ? VolFilter * (cumVolClosed / barsClosed)
                         : 0;
                }
                touchSide = 0;   // touches are per forming bar, like the engine's per-bar test
            }

            // V2 is a REAL-TIME rule; historical bars have no intrabar sequencing.
            if (State != State.Realtime) return;

            // ── one-time catch-up when enabled mid-session ───────────────────────
            // The historical pass above already rebuilt today's opening range and
            // volume stats from the chart's bars. What it could NOT do is trade —
            // so if the engine's one trade for today ALREADY fired on a closed bar
            // (touch + that bar's volume ≥ its gate — all in the past now, so
            // reading those finished volumes is not look-ahead), we sit out the
            // rest of the day rather than take a stale, late entry.
            if (!catchupDone)
            {
                catchupDone = true;
                if (orDone && !tradedThisSession && barsClosed > OrBars)
                {
                    double cv = 0;
                    for (int n = barsClosed; n >= 1; n--)   // today's closed bars, oldest first
                    {
                        int off = n;                        // barsAgo: barsClosed..1
                        int barInSess = barsClosed - n;     // 0-based index within session
                        if (barInSess >= OrBars)
                        {
                            double g = (VolFilter > 0 && barInSess > 0) ? VolFilter * (cv / barInSess) : 0;
                            bool touched = High[off] >= upLvl || Low[off] <= dnLvl;
                            if (touched && (VolFilter <= 0 || Volume[off] >= g))
                            {
                                tradedThisSession = true;   // engine already had its trade today
                                Print("[EdgeLogORBV2] mid-session enable: today's signal already fired on a closed bar - standing down until tomorrow");
                                break;
                            }
                        }
                        cv += Volume[off];
                    }
                    if (!tradedThisSession)
                        Print("[EdgeLogORBV2] mid-session enable: no signal yet today - live for the remainder of the session");
                }
            }

            // ── manage an open position ──────────────────────────────────────────
            // EOD flat is handled ONLY by NT's IsExitOnSessionCloseStrategy (10s before
            // the chart session's close, on NT's own clock). A manual Time[0] check here
            // is a trap: under OnEachTick, Time[0] is the FORMING BAR'S END time for every
            // tick in it, so `Time[0] >= sessionEnd-20s` fires on the FIRST tick of the
            // session's last bar — 5 minutes early (observed live 2026-08-11: the first
            // V2 trade flattened at 16:55:00 on a 17:00 session).
            if (Position.MarketPosition == MarketPosition.Long)
            {
                if (!stopPlaced && entryFill > 0)
                {
                    ExitLongStopMarket(0, true, Qty,
                        Instrument.MasterInstrument.RoundToTickSize(entryFill - StopFrac * rng),
                        "V2x", "V2");
                    stopPlaced = true;
                }
                return;
            }
            if (Position.MarketPosition == MarketPosition.Short)
            {
                if (!stopPlaced && entryFill > 0)
                {
                    ExitShortStopMarket(0, true, Qty,
                        Instrument.MasterInstrument.RoundToTickSize(entryFill + StopFrac * rng),
                        "V2x", "V2");
                    stopPlaced = true;
                }
                return;
            }

            // ── flat: look for a V2 entry on the forming bar ─────────────────────
            if (!orDone || tradedThisSession || rng <= 0) return;
            if (Time[0] >= sessionEnd.AddMinutes(-5)) return;   // no fresh entry into the close

            // which edge has the forming bar touched? (first side wins, engine-style)
            if (touchSide == 0)
            {
                bool upT = High[0] >= upLvl;
                bool dnT = Low[0] <= dnLvl;
                if (upT && dnT) touchSide = Close[0] >= (upLvl + dnLvl) / 2 ? 1 : -1;
                else if (upT)   touchSide = 1;
                else if (dnT)   touchSide = -1;
            }
            if (touchSide == 0) return;

            bool longOk  = TradeMode == "Both" || TradeMode == "Long Only"  || (TradeMode == "First-candle dir" && orDir > 0);
            bool shortOk = TradeMode == "Both" || TradeMode == "Short Only" || (TradeMode == "First-candle dir" && orDir < 0);
            if (touchSide > 0 && !longOk) return;
            if (touchSide < 0 && !shortOk) return;

            // the confirmation: forming bar volume-so-far has reached the gate.
            // Volume[0] under OnEachTick = the developing bar's cumulative volume.
            if (VolFilter > 0 && Volume[0] < gate) return;

            if (touchSide > 0) EnterLong(Qty, "V2");
            else               EnterShort(Qty, "V2");
            tradedThisSession = true;      // one confirmed trade per session
        }

        protected override void OnExecutionUpdate(Execution execution, string executionId,
            double price, int quantity, MarketPosition marketPosition, string orderId, DateTime time)
        {
            if (execution.Order == null || execution.Order.OrderState != OrderState.Filled) return;
            if (execution.Order.Name == "V2")
            {
                entryFill = price;         // stop anchors on the ACTUAL fill
                stopPlaced = false;
                Print(string.Format("[EdgeLogORBV2] {0} filled {1} @ {2}", time,
                    execution.Order.IsLong ? "LONG" : "SHORT", price));
            }
        }

        #region Properties
        [NinjaScriptProperty, Range(1, 12)]
        [Display(Name = "Opening range (bars)", Order = 1, GroupName = "ORB V2")]
        public int OrBars { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Direction (Both / First-candle dir / Long Only / Short Only)", Order = 2, GroupName = "ORB V2")]
        public string TradeMode { get; set; }

        [NinjaScriptProperty, Range(0.5, 2.0)]
        [Display(Name = "Stop (x range width)", Order = 3, GroupName = "ORB V2")]
        public double StopFrac { get; set; }

        [NinjaScriptProperty, Range(0.0, 3.0)]
        [Display(Name = "Volume gate (x session avg, 0=off)", Order = 4, GroupName = "ORB V2")]
        public double VolFilter { get; set; }

        [NinjaScriptProperty, Range(1, 10)]
        [Display(Name = "Quantity", Order = 5, GroupName = "ORB V2")]
        public int Qty { get; set; }
        #endregion
    }
}
