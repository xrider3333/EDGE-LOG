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

        // SHALLOW LIMIT entry state (LimitAtr > 0). The engine places a resting limit
        // LimitAtr x ATR below the signal close, scans the next 10 bars, and DROPS the
        // signal entirely if it never fills -- it is not carried forward. Mirrored here.
        private bool   limitPending;
        private int    limitBar;          // CurrentBar when the limit was submitted
        private double limitSwingLow;     // risk anchor, measured at the SIGNAL bar
        private const int LimitScanBars = 10;

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
                LimitAtr   = 0.0;
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
                limitPending = false;
            }
            else if (State == State.Terminated)
            {
                DumpBlotter();
            }
        }

        /// <summary>Write this run's trade blotter to the nt_backtest folder so the
        /// reconcile tooling reads it directly instead of anyone hand-exporting from the
        /// Strategy Analyzer grid. Same mechanism as EdgeLogNOISE - see that file for why
        /// (the manual export produced the wrong file twice on 2026-08-13, and the grid
        /// export records nothing about which strategy or timeframe actually ran).
        ///
        /// This matters MORE for ENGU-Q than for NOISE: TradingView serves only ~24 days of
        /// 1-minute history and our 1m masters have a hole across exactly that window, so
        /// NinjaTrader is currently the ONLY second engine ENGU-Q can be checked against.
        ///
        /// Times are UTC. NinjaTrader stamps a bar at its CLOSE and the AUGUR engine at its
        /// OPEN; the reader undoes that with --bar-min.
        ///
        /// KNOWN CONVENTION GAP - expect it in the diff, do not chase it: the engine enters
        /// AT the signal bar's close, while a market order placed here on bar close fills at
        /// the NEXT bar's open. NT entries should sit one bar later at a slightly different
        /// price. That is NinjaTrader being honest about a fill you cannot actually get.
        ///
        /// Never throws.</summary>
        private void DumpBlotter()
        {
            try
            {
                if (SystemPerformance == null || SystemPerformance.AllTrades == null) return;
                if (SystemPerformance.AllTrades.Count == 0) return;

                string dir = @"C:\EdgeLog\nt_backtest";
                if (!System.IO.Directory.Exists(dir)) System.IO.Directory.CreateDirectory(dir);

                string instrument = Instrument != null ? Instrument.FullName : "?";
                string period     = BarsPeriod != null
                                  ? BarsPeriod.BarsPeriodType + "-" + BarsPeriod.Value : "?";
                string hours      = (Bars != null && Bars.TradingHours != null)
                                  ? Bars.TradingHours.Name : "?";
                string stamp      = DateTime.Now.ToString("yyyyMMdd-HHmmss");
                string path       = System.IO.Path.Combine(dir,
                                        "EdgeLogENGUQ1m_" + stamp + ".csv");

                var sb = new System.Text.StringBuilder();
                sb.AppendLine("# strategy=EdgeLogENGUQ1m");
                sb.AppendLine("# instrument=" + instrument);
                sb.AppendLine("# bars=" + period);
                sb.AppendLine("# trading_hours=" + hours);
                sb.AppendLine("# tlLen=" + TlLen + " emaLen=" + EmaLen + " bufAtr=" + BufAtr
                              + " minBrk=" + MinBrk + " atrLen=" + AtrLen + " volMult=" + VolMult
                              + " stopMult=" + StopMult + " actR=" + ActR + " trailFrac=" + TrailFrac
                              + " breakevenR=" + BreakevenR + " qty=" + Qty);
                sb.AppendLine("# times=UTC bar_stamp=close");
                sb.AppendLine("trade,side,qty,entry_utc,exit_utc,entry_px,exit_px,entry_name,exit_name,pnl_usd");

                var inv = System.Globalization.CultureInfo.InvariantCulture;
                int n = 0;
                foreach (Trade t in SystemPerformance.AllTrades)
                {
                    n++;
                    sb.AppendLine(string.Join(",", new string[] {
                        n.ToString(inv),
                        t.Entry.MarketPosition == MarketPosition.Long ? "1" : "-1",
                        t.Quantity.ToString(inv),
                        t.Entry.Time.ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss", inv),
                        t.Exit.Time.ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss", inv),
                        t.Entry.Price.ToString(inv),
                        t.Exit.Price.ToString(inv),
                        t.Entry.Name,
                        t.Exit.Name,
                        t.ProfitCurrency.ToString(inv)
                    }));
                }
                System.IO.File.WriteAllText(path, sb.ToString());
                Print("EdgeLogENGUQ1m: wrote " + n + " trades -> " + path);
            }
            catch (Exception ex)
            {
                Print("EdgeLogENGUQ1m: blotter dump failed: " + ex.Message);
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

            // ── shallow-limit entry: did the resting limit fill, or has it expired? ──
            // The engine treats the FILL price as the entry and re-derives risk from it
            // (risk = fill - swingLow measured at the signal bar), so a better fill means
            // a proportionally smaller stop distance -- not the same stop from a better
            // price. Anchoring on the real fill here is therefore closer to the engine
            // than the market-entry path above, which anchors on the signal close.
            if (limitPending)
            {
                if (Position.MarketPosition == MarketPosition.Long)
                {
                    ep   = Position.AveragePrice;
                    risk = ep - limitSwingLow;
                    if (risk < 0.5)
                    {
                        // Degenerate after the fill: exit flat rather than run an
                        // un-stoppable position. Cannot happen with a BUY limit BELOW
                        // the signal close (a lower fill can only widen risk), but a
                        // partial or out-of-band fill must not be left unguarded.
                        ExitLong(Qty, "EQx", "EQ");
                        limitPending = false; inPos = false;
                        return;
                    }
                    sl = ep - StopMult * risk;
                    trailActive = false; inPos = true; limitPending = false;
                    ExitLongStopMarket(0, true, Qty,
                        Instrument.MasterInstrument.RoundToTickSize(sl), "EQx", "EQ");
                    return;   // engine never management-checks the ENTRY bar itself;
                              // trailing/breakeven start on the bar AFTER the fill.
                }
                else if (CurrentBar - limitBar >= LimitScanBars)
                {
                    // Window closed unfilled -> the engine DROPS this signal. Cancel so a
                    // stale resting order cannot fill hours later on an unrelated move.
                    foreach (Order o in Orders)
                        if (o.Name == "EQ" && (o.OrderState == OrderState.Working
                            || o.OrderState == OrderState.Accepted
                            || o.OrderState == OrderState.Submitted))
                            CancelOrder(o);
                    limitPending = false;
                }
                else
                {
                    return;   // still inside the scan window: wait, take no new signal
                }
            }

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

            // REAL-MONEY RULE: never OPEN a position on replayed history.
            // NinjaTrader replays bars through this method at every start, and this
            // strategy holds across sessions, so the replay routinely ends mid-trade --
            // leaving it managing a position the account never took. ImmediatelySubmit
            // then placed REAL protective orders for that ghost (the EQx stop that
            // re-armed after every cancel, 2026-08-17); WaitUntilFlat merely made it sit
            // out instead -- live on the board, unable to trade, potentially for days.
            // Every rolling computation above still runs on every historical bar, so the
            // ATR ring, EMA, volume average and swing low are fully warmed. Only the
            // ENTRY is withheld until the strategy is genuinely live: it goes real-time
            // FLAT and in sync with the account, and takes the first REAL signal.
            // Management above is deliberately NOT gated -- a genuine live position must
            // still be trailed and stopped after a restart.
            if (State != State.Realtime) return;

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

            if (LimitAtr > 0)
            {
                // ── SHALLOW LIMIT entry (run #249, adopted 2026-08-18) ───────────
                // Rest a BUY limit LimitAtr x ATR below the signal close and wait up to
                // 10 bars. No stop goes out yet: the stop is derived from the actual fill
                // once we have one (see the fill handler above). isLiveUntilCancelled is
                // true so the order survives bar boundaries; the expiry branch cancels it.
                double limitPx = Instrument.MasterInstrument.RoundToTickSize(
                                     Close[0] - LimitAtr * a);
                limitSwingLow = swingLow;
                limitBar      = CurrentBar;
                limitPending  = true;
                EnterLongLimit(0, true, Qty, limitPx, "EQ");
            }
            else
            {
                // ── enter: market at the close (engine enters AT the close) ──────
                ep = Close[0]; risk = r; sl = ep - StopMult * risk; trailActive = false; inPos = true;
                EnterLong(Qty, "EQ");
                ExitLongStopMarket(0, true, Qty,
                    Instrument.MasterInstrument.RoundToTickSize(sl), "EQx", "EQ");
            }
        }

        private bool PendingEntry()
        {
            foreach (Order o in Orders)
                if (o.Name == "EQ" && (o.OrderState == OrderState.Working || o.OrderState == OrderState.Accepted || o.OrderState == OrderState.Submitted))
                    return true;
            return false;
        }

        #region Properties
        // Ranges are wide enough for BOTH sessions: the RTH champion uses short lookbacks
        // (tl 48 / ema 200 / atr 14) while the ETH champion (#226) needs tl 170 / ema 1380 /
        // atr 106. A too-tight Range() here is fatal, not cosmetic — NinjaTrader refuses to
        // start the strategy and finalizes it with only a modal popup to say why.
        [NinjaScriptProperty, Range(15, 400)]
        [Display(Name = "Trendline length (bars)", Order = 1, GroupName = "ENGU-Q")]
        public int TlLen { get; set; }

        [NinjaScriptProperty, Range(20, 4000)]
        [Display(Name = "Trend EMA length", Order = 2, GroupName = "ENGU-Q")]
        public int EmaLen { get; set; }

        [NinjaScriptProperty, Range(0.0, 1.0)]
        [Display(Name = "Breakout buffer (x ATR)", Order = 3, GroupName = "ENGU-Q")]
        public double BufAtr { get; set; }

        [NinjaScriptProperty, Range(0.0, 3.0)]
        [Display(Name = "Breakout decisiveness (x ATR)", Order = 4, GroupName = "ENGU-Q")]
        public double MinBrk { get; set; }

        [NinjaScriptProperty, Range(5, 400)]
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
        [NinjaScriptProperty, Range(0.0, 1.0)]
        [Display(Name = "Shallow limit depth (x ATR, 0=market at close)", Order = 11, GroupName = "ENGU-Q")]
        public double LimitAtr { get; set; }

        [Display(Name = "Quantity", Order = 12, GroupName = "ENGU-Q")]
        public int Qty { get; set; }
        #endregion
    }
}
