// =============================================================================
//  EDGELOG · ORB 3.0 — NinjaTrader 8 port of augur_strategies/ORB_3_0.py
//  For AUTOMATED PAPER TRADING on Sim101 (PAPER system Layer 1).
//
//  Defaults = the crowned #125 config the runner shadow-trades (api/paper.py):
//    or_bars=1 · Both · stop_frac=0.75 · vol_filter=1.25 · buf=0 · target=0 · flat EOD
//
//  Chart: NQ ##-## · 5 Minute · session template "CME US Index Futures RTH".
//
//  Execution model (vs the Python engine — engine is authoritative on fills):
//  • Entries are REAL resting stop orders at the range edges (both sides armed
//    via unmanaged OCO — NT's managed mode cancels the opposite-direction entry,
//    so this strategy uses the unmanaged API). Fills at the level, or at the
//    gap price if price gaps through — same intent as the engine's
//    max(level, open) fill, but with true intrabar realism.
//  • VOLUME FILTER: the engine checks the breakout bar's FULL volume before
//    entering (an intrabar look-ahead no live trader has). Live we can't know a
//    bar's volume until it closes, so this port enters on the stop order and
//    EJECTS at that bar's close if the bar was thin (vol < filter × session
//    mean-so-far), then RE-ARMS for a later break (the engine also retries).
//    These "thin-vol" scratch trades are an honest live cost the engine can't
//    see — reconcile flags them, don't panic over them.
//  • ONE real trade per session (a thin-vol scratch does not count).
//  • Protective stop is placed when the entry bar closes (the engine also only
//    begins checking the stop on the bar AFTER entry).
//  • Flat on the last bar of the session (manual close at that bar's close —
//    unmanaged strategies don't get NT's auto exit-on-session-close).
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
    public class EdgeLogORB30 : Strategy
    {
        // session state
        private int    bis;            // bar index within session (0-based, counts CLOSED bars)
        private double orHi, orLo, sessOpen, orClose, rng, upLvl, dnLvl;
        private double cumVol;         // session volume of closed bars (for the filter mean)
        private double volMeanAtArm;   // mean bar volume of session-so-far when orders were armed
        private bool   tradedThisSession;   // a REAL (non-scratch) trade completed
        private bool   armed;
        private int    orDir;

        // order state (unmanaged)
        private Order  longEntry, shortEntry, exitStop;
        private double entryPx;
        private int    dir;            // +1 long, -1 short, 0 flat
        private bool   pendingVolCheck;
        private bool   ejecting;       // thin-vol market exit in flight
        private bool   sessionValid;   // only trade sessions we saw open (not a mid-day start)

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name        = "EdgeLogORB30";
                Description = "EDGELOG ORB 3.0 #125 — opening range breakout, Sim101 paper port";
                Calculate   = Calculate.OnBarClose;
                IsUnmanaged = true;
                IsInstantiatedOnEachOptimizationIteration = false;
                BarsRequiredToTrade = 1;
                StartBehavior = StartBehavior.WaitUntilFlat;

                OrBars      = 1;
                TradeMode   = "Both";
                StopFrac    = 0.75;
                VolFilter   = 1.25;
                BreakoutBuf = 0.0;
                TargetR     = 0.0;
                Qty         = 1;
            }
            else if (State == State.Configure)
            {
            }
        }

        private void ResetSession()
        {
            bis = 0; orHi = double.MinValue; orLo = double.MaxValue;
            sessOpen = Open[0]; orClose = double.NaN; rng = 0;
            cumVol = 0; tradedThisSession = false; armed = false; orDir = 0;
            CancelEntries();
        }

        private void CancelEntries()
        {
            if (longEntry  != null && (longEntry.OrderState  == OrderState.Working || longEntry.OrderState  == OrderState.Accepted)) CancelOrder(longEntry);
            if (shortEntry != null && (shortEntry.OrderState == OrderState.Working || shortEntry.OrderState == OrderState.Accepted)) CancelOrder(shortEntry);
            armed = false;
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0) return;

            if (Bars.IsFirstBarOfSession)
            {
                ResetSession();
                sessionValid = true;
            }
            if (!sessionValid) return;   // started mid-session — wait for the next open

            // ── build the opening range over the first OrBars closed bars ────────
            if (bis < OrBars)
            {
                orHi = Math.Max(orHi, High[0]);
                orLo = Math.Min(orLo, Low[0]);
                if (bis == OrBars - 1) orClose = Close[0];
            }

            // ── thin-vol check: the entry bar just closed ────────────────────────
            if (pendingVolCheck && dir != 0)
            {
                pendingVolCheck = false;
                if (VolFilter > 0 && volMeanAtArm > 0 && Volume[0] < VolFilter * volMeanAtArm)
                {
                    // engine would have skipped this break — eject and re-arm later
                    ejecting = true;
                    if (exitStop != null && exitStop.OrderState == OrderState.Working) CancelOrder(exitStop);
                    SubmitOrderUnmanaged(0, dir > 0 ? OrderAction.Sell : OrderAction.BuyToCover,
                                         OrderType.Market, Qty, 0, 0, "", "thin-vol");
                }
            }

            // ── flat by session close (engine: exit at last bar's close) ─────────
            if (Bars.IsLastBarOfSession)
            {
                CancelEntries();
                if (dir != 0 && !ejecting)
                {
                    if (exitStop != null && exitStop.OrderState == OrderState.Working) CancelOrder(exitStop);
                    SubmitOrderUnmanaged(0, dir > 0 ? OrderAction.Sell : OrderAction.BuyToCover,
                                         OrderType.Market, Qty, 0, 0, "", "eod");
                }
                bis++; cumVol += Volume[0];
                return;
            }

            // ── arm resting stop entries once the range is complete ──────────────
            if (bis >= OrBars - 1 && dir == 0 && !tradedThisSession && !armed && !ejecting)
            {
                rng = orHi - orLo;
                if (rng > 0 && bis >= OrBars - 1)
                {
                    upLvl = Instrument.MasterInstrument.RoundToTickSize(orHi + BreakoutBuf * rng);
                    dnLvl = Instrument.MasterInstrument.RoundToTickSize(orLo - BreakoutBuf * rng);
                    orDir = (!double.IsNaN(orClose)) ? (orClose >= sessOpen ? 1 : -1) : 0;

                    bool longOk  = TradeMode == "Both" || TradeMode == "Long Only"  || (TradeMode == "First-candle dir" && orDir > 0);
                    bool shortOk = TradeMode == "Both" || TradeMode == "Short Only" || (TradeMode == "First-candle dir" && orDir < 0);

                    // engine: sv[:k].mean() = mean of session bars BEFORE the breakout bar.
                    // We arm at the close of bar `bis`; the earliest fill bar is bis+1, so
                    // the reference mean is over bars 0..bis inclusive (bis+1 closed bars).
                    volMeanAtArm = (cumVol + Volume[0]) / (bis + 1);

                    string oco = "ORBent_" + CurrentBar;   // unique per arming; pairs the two entry stops
                    if (longOk)
                        longEntry = SubmitOrderUnmanaged(0, OrderAction.Buy, OrderType.StopMarket,
                                                         Qty, 0, upLvl, oco, "L");
                    if (shortOk)
                        shortEntry = SubmitOrderUnmanaged(0, OrderAction.SellShort, OrderType.StopMarket,
                                                          Qty, 0, dnLvl, oco, "S");
                    armed = longOk || shortOk;
                }
            }

            bis++;
            cumVol += Volume[0];
        }

        protected override void OnExecutionUpdate(Execution execution, string executionId,
            double price, int quantity, MarketPosition marketPosition, string orderId, DateTime time)
        {
            if (execution.Order == null || execution.Order.OrderState != OrderState.Filled) return;
            string sig = execution.Order.Name;

            if (sig == "L" || sig == "S")
            {
                dir = sig == "L" ? 1 : -1;
                entryPx = price;
                armed = false;
                pendingVolCheck = VolFilter > 0;    // verify the breakout bar's volume at its close

                // protective stop (engine checks the stop from the NEXT bar; the order
                // rests from now, which is only safer). Optional target at TargetR × risk,
                // OCO-paired with the stop (engine: risk = stop distance = StopFrac × range).
                double risk   = StopFrac * rng;
                double stopPx = Instrument.MasterInstrument.RoundToTickSize(
                    dir > 0 ? entryPx - risk : entryPx + risk);
                string exitOco = TargetR > 0 ? "ORBexit_" + CurrentBar + "_" + executionId : "";
                exitStop = SubmitOrderUnmanaged(0, dir > 0 ? OrderAction.Sell : OrderAction.BuyToCover,
                                                OrderType.StopMarket, Qty, 0, stopPx, exitOco, dir > 0 ? "Lx" : "Sx");
                if (TargetR > 0)
                {
                    double tgtPx = Instrument.MasterInstrument.RoundToTickSize(
                        dir > 0 ? entryPx + TargetR * risk : entryPx - TargetR * risk);
                    SubmitOrderUnmanaged(0, dir > 0 ? OrderAction.Sell : OrderAction.BuyToCover,
                                         OrderType.Limit, Qty, tgtPx, 0, exitOco, dir > 0 ? "Lt" : "St");
                }
            }
            else if (sig == "Lx" || sig == "Sx" || sig == "Lt" || sig == "St" || sig == "eod")
            {
                dir = 0; tradedThisSession = true; pendingVolCheck = false;
            }
            else if (sig == "thin-vol")
            {
                dir = 0; ejecting = false;          // scratch — does NOT consume the session's trade
            }
        }

        #region Properties
        [NinjaScriptProperty, Range(1, 12)]
        [Display(Name = "Opening range (bars)", Order = 1, GroupName = "ORB")]
        public int OrBars { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Direction (Both / First-candle dir / Long Only / Short Only)", Order = 2, GroupName = "ORB")]
        public string TradeMode { get; set; }

        [NinjaScriptProperty, Range(0.5, 2.0)]
        [Display(Name = "Stop (x range width)", Order = 3, GroupName = "ORB")]
        public double StopFrac { get; set; }

        [NinjaScriptProperty, Range(0.0, 3.0)]
        [Display(Name = "Volume filter (x session avg, 0=off)", Order = 4, GroupName = "ORB")]
        public double VolFilter { get; set; }

        [NinjaScriptProperty, Range(0.0, 0.5)]
        [Display(Name = "Breakout buffer (x range)", Order = 5, GroupName = "ORB")]
        public double BreakoutBuf { get; set; }

        [NinjaScriptProperty, Range(0.0, 6.0)]
        [Display(Name = "Target (x risk, 0=EOD only)", Order = 6, GroupName = "ORB")]
        public double TargetR { get; set; }

        [NinjaScriptProperty, Range(1, 10)]
        [Display(Name = "Quantity", Order = 7, GroupName = "ORB")]
        public int Qty { get; set; }
        #endregion
    }
}
