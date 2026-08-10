// =============================================================================
//  EDGELOG · ENGU-Q 1m — NinjaTrader 8 port of augur_strategies/ENGUQ_1M_1_0.py
//  For AUTOMATED PAPER TRADING on Sim101 (PAPER system Layer 1).
//
//  Defaults = the certified NQ champion NQ_DEPLOY_PARAMS_149 (+ breakeven 1.5),
//  the same config the runner shadow-trades (api/paper.py):
//    tl_len=48 · ema_len=390 · buf_atr=0.9 · min_brk=1.3 · atr_len=30 ·
//    vol_mult=0.8 · stop_mult=1.0 · act_R=2.5 · trail_frac=2.5 · breakeven_R=1.5
//    (regime_len=0 = off, not implemented)
//
//  Chart: NQ ##-## · 1 Minute · session template "CME US Index Futures RTH".
//  Load AT LEAST 30 days of chart history — the 390-bar EMA and the trendline
//  need warm-up; with a short chart the first days' signals are wrong.
//
//  Entry (long only, evaluated at bar close, mirrors the engine bar-for-bar):
//    green candle (close>open) · close > EMA(390) · volume ≥ 0.8 × SMA20(vol) ·
//    descending trendline (linear fit of the last 48 PRIOR highs, slope<0) ·
//    close > trendline + 0.9×ATR and > prior high · decisive break
//    ((close−trendline)/max(ATR,0.25) ≥ 1.3) · risk = close − lowest low of the
//    last 49 bars ≥ 0.5 pts.  Market entry at the close (fills next tick).
//
//  Exit: initial stop = signalClose − 1.0×risk. Once the bar HIGH is ≥1.5R above
//  the signal close the stop rises to breakeven; once ≥2.5R the stop trails
//  2.5×risk below the highest high since. Stop maintained as a REAL resting stop
//  order, updated at each bar close. No end-of-day flat — like the engine, a
//  position can carry across sessions (RTH-only bars).
//
//  Known engine gaps (documented, measured later by reconcile):
//  • Engine enters AT the signal close; this sends a market order at that close, so
//    live on Sim101 it fills at the next tick (usually a tick or two of slip).
//  • Engine raises the trail with the CURRENT bar's high before checking that
//    same bar's low; live the stop order updates after the bar closes, so a
//    same-bar spike-up-then-down exits at the PREVIOUS stop level.
//  • Stops anchor on the SIGNAL CLOSE (engine's entry px), not the actual fill,
//    so the logic stays aligned to the engine and slippage shows only in PnL.
//  • ATR here = simple mean of True Range over 30 (the engine's), NOT NT's
//    Wilder-smoothed ATR indicator.
// =============================================================================
#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Indicators;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class EdgeLogENGUQ1m : Strategy
    {
        private EMA ema;
        private SMA volAvg;
        private NinjaTrader.NinjaScript.Indicators.MIN lowMin;

        // rolling simple-mean ATR of the engine (SMA of True Range)
        private double trSum;
        private double[] trBuf;
        private int trCount;

        // trendline regression constants (x = 0..TlLen-1)
        private double xm, xss;

        // position state (engine semantics — anchored on the SIGNAL close)
        private bool   inPos;
        private double ep, risk, sl;
        private bool   trailActive;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name        = "EdgeLogENGUQ1m";
                Description = "EDGELOG ENGU-Q 1m #149 — trendline break long, Sim101 paper port";
                Calculate   = Calculate.OnBarClose;
                EntriesPerDirection = 1;
                EntryHandling = EntryHandling.AllEntries;
                IsExitOnSessionCloseStrategy = false;   // engine holds across sessions
                IsInstantiatedOnEachOptimizationIteration = false;
                StartBehavior = StartBehavior.WaitUntilFlat;
                BarsRequiredToTrade = 60;

                TlLen      = 48;
                EmaLen     = 390;
                BufAtr     = 0.9;
                MinBrk     = 1.3;
                AtrLen     = 30;
                VolMult    = 0.8;
                StopMult   = 1.0;
                ActR       = 2.5;
                TrailFrac  = 2.5;
                BreakevenR = 1.5;
                Qty        = 1;
            }
            else if (State == State.DataLoaded)
            {
                ema    = EMA(Close, EmaLen);
                volAvg = SMA(Volume, 20);
                lowMin = MIN(Low, TlLen + 1);
                trBuf  = new double[AtrLen];
                trSum  = 0; trCount = 0;
                xm  = (TlLen - 1) / 2.0;
                xss = 0;
                for (int j = 0; j < TlLen; j++) xss += (j - xm) * (j - xm);
                inPos = false;
            }
        }

        private double TrueRange()
        {
            if (CurrentBar == 0) return High[0] - Low[0];
            return Math.Max(High[0] - Low[0],
                   Math.Max(Math.Abs(High[0] - Close[1]), Math.Abs(Low[0] - Close[1])));
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0) return;

            // ── rolling simple-mean ATR (engine: SMA of TR; before warm-up use TR) ─
            double tr = TrueRange();
            int slot = CurrentBar % AtrLen;
            if (trCount >= AtrLen) trSum -= trBuf[slot];
            trBuf[slot] = tr; trSum += tr;
            if (trCount < AtrLen) trCount++;
            double atr = trCount >= AtrLen ? trSum / AtrLen : tr;

            // re-sync flat state if the position closed via the resting stop
            if (inPos && Position.MarketPosition == MarketPosition.Flat && !PendingEntry())
                inPos = false;

            // ── manage an open position (engine order: activate → trail → BE → stop) ─
            if (inPos && Position.MarketPosition == MarketPosition.Long)
            {
                if (!trailActive && High[0] - ep >= ActR * risk) trailActive = true;
                if (trailActive) sl = Math.Max(sl, High[0] - TrailFrac * risk);
                if (BreakevenR > 0 && High[0] - ep >= BreakevenR * risk) sl = Math.Max(sl, ep);
                ExitLongStopMarket(0, true, Qty,
                    Instrument.MasterInstrument.RoundToTickSize(sl), "EQx", "EQ");
                return;                                     // engine: no new signal while in a trade
            }
            if (Position.MarketPosition != MarketPosition.Flat || PendingEntry()) return;

            if (CurrentBar < TlLen + 1) return;

            // ── entry signal (all conditions on the just-closed bar) ─────────────
            if (Close[0] <= Open[0]) return;                            // green candle
            if (!(Close[0] > ema[0])) return;                           // uptrend
            if (VolMult > 0)
            {
                if (CurrentBar < 19) return;
                if (!(Volume[0] >= VolMult * volAvg[0])) return;        // volume spike
            }

            // descending trendline: linear fit of the PRIOR TlLen highs (excl. current)
            double mean = 0;
            for (int j = 0; j < TlLen; j++) mean += High[TlLen - j];    // hw[j]: oldest→newest
            mean /= TlLen;
            double slope = 0;
            for (int j = 0; j < TlLen; j++) slope += (j - xm) * (High[TlLen - j] - mean);
            slope /= xss;
            if (slope >= 0) return;                                     // must slope down
            double tlNow = mean + slope * (TlLen - xm);                 // projected to current bar

            double a = atr;
            if (!(Close[0] > tlNow + BufAtr * a && Close[0] > High[1])) return;
            if ((Close[0] - tlNow) / Math.Max(a, 0.25) < MinBrk) return;  // decisive break

            double swingLow = lowMin[0];                                // lowest low, last TlLen+1 bars
            double r = Close[0] - swingLow;
            if (r < 0.5) return;                                        // risk floor

            // ── enter: market at the close (engine enters AT the close) ──────────
            ep = Close[0]; risk = r; sl = ep - StopMult * risk; trailActive = false; inPos = true;
            EnterLong(Qty, "EQ");
            ExitLongStopMarket(0, true, Qty,
                Instrument.MasterInstrument.RoundToTickSize(sl), "EQx", "EQ");
        }

        private bool PendingEntry()
        {
            foreach (Order o in Orders)
                if (o.Name == "EQ" && (o.OrderState == OrderState.Working || o.OrderState == OrderState.Accepted || o.OrderState == OrderState.Submitted))
                    return true;
            return false;
        }

        #region Properties
        [NinjaScriptProperty, Range(15, 80)]
        [Display(Name = "Trendline length (bars)", Order = 1, GroupName = "ENGU-Q")]
        public int TlLen { get; set; }

        [NinjaScriptProperty, Range(20, 400)]
        [Display(Name = "Trend EMA length", Order = 2, GroupName = "ENGU-Q")]
        public int EmaLen { get; set; }

        [NinjaScriptProperty, Range(0.0, 1.0)]
        [Display(Name = "Breakout buffer (x ATR)", Order = 3, GroupName = "ENGU-Q")]
        public double BufAtr { get; set; }

        [NinjaScriptProperty, Range(0.0, 3.0)]
        [Display(Name = "Breakout decisiveness (x ATR)", Order = 4, GroupName = "ENGU-Q")]
        public double MinBrk { get; set; }

        [NinjaScriptProperty, Range(5, 50)]
        [Display(Name = "ATR length (simple mean of TR)", Order = 5, GroupName = "ENGU-Q")]
        public int AtrLen { get; set; }

        [NinjaScriptProperty, Range(0.0, 5.0)]
        [Display(Name = "Volume spike (x 20-bar avg, 0=off)", Order = 6, GroupName = "ENGU-Q")]
        public double VolMult { get; set; }

        [NinjaScriptProperty, Range(0.3, 2.0)]
        [Display(Name = "Stop (x risk-to-swing-low)", Order = 7, GroupName = "ENGU-Q")]
        public double StopMult { get; set; }

        [NinjaScriptProperty, Range(0.0, 3.0)]
        [Display(Name = "Trail activation (R)", Order = 8, GroupName = "ENGU-Q")]
        public double ActR { get; set; }

        [NinjaScriptProperty, Range(0.5, 4.0)]
        [Display(Name = "Trail width (x risk)", Order = 9, GroupName = "ENGU-Q")]
        public double TrailFrac { get; set; }

        [NinjaScriptProperty, Range(0.0, 3.0)]
        [Display(Name = "Breakeven (R, 0=off)", Order = 10, GroupName = "ENGU-Q")]
        public double BreakevenR { get; set; }

        [NinjaScriptProperty, Range(1, 10)]
        [Display(Name = "Quantity", Order = 11, GroupName = "ENGU-Q")]
        public int Qty { get; set; }
        #endregion
    }
}
