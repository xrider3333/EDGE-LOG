// =============================================================================
//  EDGELOG · ORB 230 — NinjaTrader 8 port of augur_strategies/ORB_3_4_C221.py
//  (run #230 / ORB-40, the grail-hunt champion). PAPER/DEMO use.
//
//  WHY THIS FILE EXISTS (2026-08-17, owner: "fix them"). EdgeLogORBV2 could NOT be
//  made to match this config by changing parameters: V2 chases price INTRABAR on a
//  volume trigger, while #230 enters only when a bar CLOSES beyond the level, then
//  scales out and trails. Those are different mechanisms, so this is a new port and
//  V2 stays retired.
//
//  THE RULE, in the engine's own order (ORB_3_4.py):
//   • Opening range = the first `OrBars` bars of the session: or_hi / or_lo, rng.
//   • Direction gate ("first-candle dir"): or_dir = +1 if the OR's LAST close >= the
//     session OPEN, else -1. Longs only when +1, shorts only when -1.
//   • Levels: up = or_hi + buf, dn = or_lo - buf, where buf = BreakoutBuf * rng.
//   • SESSION filters, both checked before any entry:
//       - ATR / vol-regime: skip the whole session when the mean range of the last 5
//         sessions < AtrFilter x the median range of the last 60. Trailing only.
//       - V-pace: skip an entry bar unless the session's average volume PER BAR SO FAR
//         (bars strictly before this one) >= VpaceFilter x the same-length prefix
//         averaged over the prior 20 sessions.
//   • ENTRY: the bar CLOSES beyond the level -> market order. No intrabar touch, which
//     is exactly what made the retired #125 family illegal.
//   • risk = StopFrac x rng. Stop = entry -/+ risk. Target = entry +/- TargetR x risk.
//   • PARTIAL at PartialExitR x risk: book HALF the position, then
//   • TRAIL the runner on the extremes of the prior TrailBars bars (never the current
//     bar), moving one way only.
//   • Flat at the session close; holidays skipped.
//
//  TWO-LOT MODEL. The engine trades one notional unit and books half at the partial
//  (pnl = half x partial + half x runner). NinjaTrader cannot sell half a contract, so
//  Qty is contracts PER LOT and the strategy enters 2 x Qty: one lot leaves at the
//  partial, one is trailed. Qty 1 = 2 contracts working.
//
//  ORDER MODEL vs THE ENGINE. The engine tests stops on each COMPLETED bar and fills a
//  gap-through at the open. Live, a resting stop does the same thing but can also fill
//  intrabar, which is strictly more realistic and never worse than the backtest. Targets
//  and the partial are resting limits for the same reason.
//
//  Chart: NQ ##-## · 5 Minute · session template "EDGELOG RTH 0930-1600".
//  Load at least 70 days so the 60-session vol-regime median is warm on enable.
// =============================================================================
#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class EdgeLogORB230 : Strategy
    {
        // ── session state ────────────────────────────────────────────────────
        private int      barOfDay;
        private double   sessionOpen;
        private double   orHi, orLo, rng, upLvl, dnLvl;
        private int      orDir;
        private bool     sessionValid;      // saw this session's open (not a mid-session start)
        private bool     sessionSkipped;    // vol-regime filter refused this session
        private bool     tradedThisSession; // engine takes at most one entry per session
        private DateTime sessionEnd = DateTime.MaxValue;

        // ── history for the two session filters ──────────────────────────────
        private List<double>   sessionRanges = new List<double>();   // last 60 session ranges
        private double         curHi, curLo;                          // this session's running range
        private List<double[]> volPrefix = new List<double[]>();      // prior sessions' avg-volume-per-bar prefix
        private List<double>   curVolCum = new List<double>();        // this session's cumulative volume

        // ── position state ───────────────────────────────────────────────────
        private double entryPx, stopPx, tgtPx, ptgtPx, riskPts;
        private bool   partialDone;
        private bool   beArmed;             // breakeven armed on a finished close (ORB_3_6)
        private int    entryBar = -1;
        private int    dir;                 // +1 long / -1 short, 0 flat

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name        = "EdgeLogORB230";
                Description = "EDGELOG ORB 3.4 run #230 - close-confirmed opening-range break, partial + trailed runner";
                Calculate   = Calculate.OnBarClose;      // entry is a bar-CLOSE decision
                EntriesPerDirection = 1;
                EntryHandling = EntryHandling.AllEntries;
                IsExitOnSessionCloseStrategy = true;     // engine is flat every session close
                ExitOnSessionCloseSeconds = 30;
                IsInstantiatedOnEachOptimizationIteration = false;
                StartBehavior = StartBehavior.WaitUntilFlat;
                BarsRequiredToTrade = 20;

                // Run #230's pinned config.
                OrBars        = 2;
                StopFrac      = 2.0;
                BreakoutBuf   = 0.25;
                PartialExitR  = 3.0;
                TrailBars     = 3;
                TargetR       = 5.5;
                AtrFilter     = 0.7;
                VpaceFilter   = 0.7;
                SkipHolidays  = true;
                Qty           = 1;           // contracts PER LOT; 2 x this is entered
            }
            else if (State == State.DataLoaded)
            {
                sessionRanges = new List<double>();
                volPrefix     = new List<double[]>();
                curVolCum     = new List<double>();
            }
            else if (State == State.Terminated)
            {
                DumpBlotter();
            }
        }

        /// <summary>Write this run's trade blotter to the nt_backtest folder so
        /// tools/reconcile_nt_dump.py can read it without anyone driving the Strategy
        /// Analyzer's export UI.
        ///
        /// WHY (copied deliberately from EdgeLogNOISE, 2026-08-26): exporting by hand
        /// through Display > Trades > right-click > Export produced the WRONG FILE twice
        /// in one morning on 2026-08-13, and neither miss was visible until the CSV was
        /// parsed. The grid export carries no record of what was run; this writes the
        /// run's actual configuration into the header, so a mismatched run cannot be
        /// mistaken for a matching one.
        ///
        /// Times are UTC. NinjaTrader displays in the PC's local zone (Arizona, no DST)
        /// and stamps a bar at its CLOSE while the AUGUR engine stamps at its OPEN - two
        /// independent offsets. UTC removes the first; the reader handles the second.
        ///
        /// Never throws: a failed dump must not take down a backtest.</summary>
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
                                        "EdgeLogORB230_" + stamp + ".csv");

                var sb = new System.Text.StringBuilder();
                sb.AppendLine("# strategy=EdgeLogORB230");
                sb.AppendLine("# instrument=" + instrument);
                sb.AppendLine("# bars=" + period);
                sb.AppendLine("# trading_hours=" + hours);
                sb.AppendLine("# orBars=" + OrBars + " stopFrac=" + StopFrac
                              + " breakoutBuf=" + BreakoutBuf + " partialExitR=" + PartialExitR
                              + " trailBars=" + TrailBars + " targetR=" + TargetR
                              + " atrFilter=" + AtrFilter + " vpaceFilter=" + VpaceFilter
                              + " breakevenR=" + BreakevenR + " skipHolidays=" + SkipHolidays
                              + " histFills=" + HistFills + " qty=" + Qty);
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
                Print("EdgeLogORB230: wrote " + n + " trades -> " + path);
            }
            catch (Exception ex)
            {
                Print("EdgeLogORB230: blotter dump failed: " + ex.Message);
            }
        }

        /// <summary>Mean of the last `n` completed session ranges (most recent first-ish).</summary>
        private double MeanLast(List<double> xs, int n)
        {
            int c = Math.Min(n, xs.Count);
            if (c <= 0) return double.NaN;
            double s = 0;
            for (int i = xs.Count - c; i < xs.Count; i++) s += xs[i];
            return s / c;
        }

        private double MedianLast(List<double> xs, int n)
        {
            int c = Math.Min(n, xs.Count);
            if (c <= 0) return double.NaN;
            var slice = xs.GetRange(xs.Count - c, c).ToList();
            slice.Sort();
            return (c % 2 == 1) ? slice[c / 2] : 0.5 * (slice[c / 2 - 1] + slice[c / 2]);
        }

        /// <summary>Bank the finished session and reset for the new one.</summary>
        private void RollSession()
        {
            if (sessionValid && curHi > curLo)
            {
                sessionRanges.Add(curHi - curLo);
                while (sessionRanges.Count > 80) sessionRanges.RemoveAt(0);
            }
            if (sessionValid && curVolCum.Count > 0)
            {
                // avg volume per bar at each bar index k (1-based), the engine's _pref row
                var pref = new double[curVolCum.Count];
                for (int k = 0; k < curVolCum.Count; k++) pref[k] = curVolCum[k] / (k + 1);
                volPrefix.Add(pref);
                while (volPrefix.Count > 20) volPrefix.RemoveAt(0);
            }

            barOfDay = 0;
            sessionOpen = Open[0];
            curHi = High[0]; curLo = Low[0];
            curVolCum = new List<double>();
            orHi = double.MinValue; orLo = double.MaxValue; rng = 0;
            orDir = 0; upLvl = double.NaN; dnLvl = double.NaN;
            sessionSkipped = false; tradedThisSession = false;
            dir = 0; partialDone = false; entryBar = -1;

            // ── vol-regime gate, decided ONCE at the session open from prior sessions only
            if (AtrFilter > 0 && sessionRanges.Count >= 6)
            {
                double recent = MeanLast(sessionRanges, 5);
                double refMed = MedianLast(sessionRanges, 60);
                if (refMed > 0 && recent < AtrFilter * refMed) sessionSkipped = true;
            }
            if (SkipHolidays && IsHalfDay()) sessionSkipped = true;

            try
            {
                var si = new SessionIterator(Bars);
                si.GetNextSession(Time[0], true);
                sessionEnd = si.ActualSessionEnd;
            }
            catch { sessionEnd = DateTime.MaxValue; }
        }

        /// <summary>US market half-days the engine's skip_holidays drops. Calendar knowledge,
        /// known years ahead, so using it is not look-ahead.</summary>
        private bool IsHalfDay()
        {
            DateTime d = Time[0].Date;
            // day after Thanksgiving, Christmas Eve, July 3rd, and the eves NT half-sessions
            if (d.Month == 11 && d.DayOfWeek == DayOfWeek.Friday && d.Day >= 23 && d.Day <= 29) return true;
            if (d.Month == 12 && d.Day == 24) return true;
            if (d.Month == 7  && d.Day == 3)  return true;
            return false;
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0) return;
            if (CurrentBar < BarsRequiredToTrade) return;

            if (Bars.IsFirstBarOfSession)
            {
                RollSession();
                sessionValid = true;
            }
            if (!sessionValid) return;         // enabled mid-session: wait for a clean open

            // running session extremes + volume, for NEXT session's filters
            if (High[0] > curHi) curHi = High[0];
            if (Low[0]  < curLo) curLo = Low[0];
            double prevCum = curVolCum.Count > 0 ? curVolCum[curVolCum.Count - 1] : 0.0;
            curVolCum.Add(prevCum + Volume[0]);

            bool lastBar = Bars.IsLastBarOfSession;

            // ── build the opening range ──────────────────────────────────────
            if (barOfDay < OrBars)
            {
                if (High[0] > orHi || orHi == double.MinValue) orHi = Math.Max(orHi, High[0]);
                if (Low[0]  < orLo || orLo == double.MaxValue) orLo = Math.Min(orLo, Low[0]);
                if (barOfDay == OrBars - 1)
                {
                    rng = orHi - orLo;
                    orDir = Close[0] >= sessionOpen ? 1 : -1;   // FIRST-CANDLE DIRECTION
                    if (rng > 0)
                    {
                        double buf = BreakoutBuf * rng;
                        upLvl = orHi + buf;
                        dnLvl = orLo - buf;
                    }
                }
                barOfDay++;
                return;                                   // never trade inside the OR
            }

            // ── manage an open position ──────────────────────────────────────
            if (dir != 0 && Position.MarketPosition != MarketPosition.Flat)
            {
                // BREAKEVEN (engine ORB_3_6 semantics, the run #234 exit): once a
                // FINISHED bar closes BreakevenR x risk in favor of the trade, the stop
                // moves to ENTRY and never back. Armed on the close and submitted now,
                // so it can only act from the NEXT bar - identical to the engine's
                // "armed on close, acts next bar" rule, which is what makes it
                // live-legal. Arms off the ORIGINAL entry/risk, independent of the
                // partial; the trail (when active) still ratchets on top. 0 = off,
                // which is also what an older saved row's missing XML element
                // deserializes to, so adding this knob changes nothing until set.
                bool beNow = false;
                if (BreakevenR > 0)
                {
                    if (!beArmed && (dir > 0 ? Close[0] >= entryPx + BreakevenR * riskPts
                                             : Close[0] <= entryPx - BreakevenR * riskPts))
                        beArmed = true;
                    if (beArmed)
                    {
                        if (dir > 0 && entryPx > stopPx) { stopPx = entryPx; beNow = true; }
                        else if (dir < 0 && entryPx < stopPx) { stopPx = entryPx; beNow = true; }
                    }
                }
                // Trail the runner AFTER the partial has filled, off the PRIOR bars'
                // extremes (never this bar) -- the engine's sl[ts:k] / sh[ts:k].
                if (TrailBars > 0 && (PartialExitR == 0 || partialDone))
                {
                    int look = Math.Min(TrailBars, Math.Max(1, CurrentBar - entryBar));
                    if (dir > 0)
                    {
                        double lo = double.MaxValue;
                        for (int b = 1; b <= look; b++) lo = Math.Min(lo, Low[b]);
                        if (lo > stopPx) stopPx = lo;                  // only moves up
                    }
                    else
                    {
                        double hi = double.MinValue;
                        for (int b = 1; b <= look; b++) hi = Math.Max(hi, High[b]);
                        if (hi < stopPx) stopPx = hi;                  // only moves down
                    }
                    double sp = Instrument.MasterInstrument.RoundToTickSize(stopPx);
                    if (dir > 0) ExitLongStopMarket (0, true, Position.Quantity, sp, "ORBstop", "ORB");
                    else         ExitShortStopMarket(0, true, Position.Quantity, sp, "ORBstop", "ORB");
                }
                else if (beNow)
                {
                    // no trail active - the breakeven move still has to reach the broker
                    double sp = Instrument.MasterInstrument.RoundToTickSize(stopPx);
                    if (dir > 0) ExitLongStopMarket (0, true, Position.Quantity, sp, "ORBstop", "ORB");
                    else         ExitShortStopMarket(0, true, Position.Quantity, sp, "ORBstop", "ORB");
                }
                if (!lastBar) { barOfDay++; return; }
            }
            if (dir != 0 && Position.MarketPosition == MarketPosition.Flat)
                dir = 0;                                   // stop/target took us out

            // ── look for the close-confirmed break ───────────────────────────
            // REAL-MONEY RULE (2026-08-19): never OPEN on replayed history when live.
            // On 2026-08-19 this strategy replayed the morning session at startup, took
            // the opening-range short, and came up claiming Short 2 while the account was
            // flat -- blocked from trading for the rest of the day. Strategy Analyzer runs
            // are exempt: they are historical BY DEFINITION, and blocking them would dump
            // an empty blotter and break the engine reconcile.
            if (dir == 0 && (State == State.Realtime || IsInStrategyAnalyzer || HistFills)
                && !tradedThisSession && !sessionSkipped && !lastBar
                && rng > 0 && !double.IsNaN(upLvl)
                && Time[0] < sessionEnd.AddMinutes(-10))
            {
                bool up = Close[0] >= upLvl;               // CLOSE-confirmed, not a touch
                bool dn = Close[0] <= dnLvl;
                bool longOk  = orDir > 0;                  // first-candle direction
                bool shortOk = orDir < 0;

                if ((up && longOk) || (dn && shortOk))
                {
                    // ── V-PACE gate: this session's average volume per bar SO FAR (bars
                    //    strictly before this one) against the same-length prefix averaged
                    //    over the prior 20 sessions. Every input closed before this bar.
                    if (VpaceFilter > 0 && volPrefix.Count >= 20 && barOfDay > 0)
                    {
                        int k = barOfDay;                          // bars closed before this one
                        double soFar = (curVolCum.Count >= k + 1 && k > 0)
                                     ? (curVolCum[k - 1] / k) : double.NaN;
                        double refSum = 0; int refN = 0;
                        foreach (var pref in volPrefix)
                            if (k - 1 < pref.Length) { refSum += pref[k - 1]; refN++; }
                        double refAvg = refN > 0 ? refSum / refN : double.NaN;
                        if (!double.IsNaN(soFar) && !double.IsNaN(refAvg) && refAvg > 0
                            && soFar < VpaceFilter * refAvg)
                        { barOfDay++; return; }                    // too quiet - skip
                    }

                    entryPx  = Close[0];                   // engine fills at the confirming close
                    riskPts  = StopFrac * rng;
                    dir      = up ? 1 : -1;
                    stopPx   = dir > 0 ? entryPx - riskPts : entryPx + riskPts;
                    tgtPx    = TargetR      > 0 ? (dir > 0 ? entryPx + TargetR      * riskPts : entryPx - TargetR      * riskPts) : double.NaN;
                    ptgtPx   = PartialExitR > 0 ? (dir > 0 ? entryPx + PartialExitR * riskPts : entryPx - PartialExitR * riskPts) : double.NaN;
                    partialDone = false;
                    beArmed  = false;
                    entryBar = CurrentBar;
                    tradedThisSession = true;              // engine takes one entry per session

                    int total = 2 * Qty;                   // two lots: one partials, one trails
                    if (dir > 0) EnterLong (total, "ORB");
                    else         EnterShort(total, "ORB");

                    double sp = Instrument.MasterInstrument.RoundToTickSize(stopPx);
                    if (dir > 0) ExitLongStopMarket (0, true, total, sp, "ORBstop", "ORB");
                    else         ExitShortStopMarket(0, true, total, sp, "ORBstop", "ORB");

                    if (PartialExitR > 0)
                    {
                        double pp = Instrument.MasterInstrument.RoundToTickSize(ptgtPx);
                        if (dir > 0) ExitLongLimit (0, true, Qty, pp, "ORBpartial", "ORB");
                        else         ExitShortLimit(0, true, Qty, pp, "ORBpartial", "ORB");
                    }
                    if (TargetR > 0)
                    {
                        double tp = Instrument.MasterInstrument.RoundToTickSize(tgtPx);
                        // With the partial OFF the engine exits the WHOLE position at the
                        // target; the one-lot limit only makes sense as half of the
                        // partial+trail scale-out. The live row runs PartialExitR=3, so
                        // its behaviour is untouched by this branch.
                        int tq = PartialExitR > 0 ? Qty : total;
                        if (dir > 0) ExitLongLimit (0, true, tq, tp, "ORBtarget", "ORB");
                        else         ExitShortLimit(0, true, tq, tp, "ORBtarget", "ORB");
                    }
                    Print(String.Format("EdgeLogORB230 {0} entry {1} @ {2} risk {3:0.00} stop {4:0.00} partial {5:0.00} target {6:0.00}",
                        Time[0], dir > 0 ? "LONG" : "SHORT", entryPx, riskPts, stopPx, ptgtPx, tgtPx));
                }
            }
            barOfDay++;
        }

        protected override void OnExecutionUpdate(Execution execution, string executionId, double price,
                                                  int quantity, MarketPosition marketPosition,
                                                  string orderId, DateTime time)
        {
            if (execution.Order == null) return;
            if (execution.Order.Name == "ORBpartial" && execution.Order.OrderState == OrderState.Filled)
            {
                partialDone = true;                        // trailing activates from here
                Print("EdgeLogORB230: partial filled @ " + price + " - runner now trails");
            }
        }

        #region Properties
        [NinjaScriptProperty, Range(1, 12)]
        [Display(Name = "Opening range (bars)", Order = 1, GroupName = "ORB 230")]
        public int OrBars { get; set; }

        [NinjaScriptProperty, Range(0.1, 5.0)]
        [Display(Name = "Stop (x range width)", Order = 2, GroupName = "ORB 230")]
        public double StopFrac { get; set; }

        [NinjaScriptProperty, Range(0.0, 2.0)]
        [Display(Name = "Breakout buffer (x range)", Order = 3, GroupName = "ORB 230")]
        public double BreakoutBuf { get; set; }

        [NinjaScriptProperty, Range(0.0, 10.0)]
        [Display(Name = "Partial exit (x risk, 0=off)", Order = 4, GroupName = "ORB 230")]
        public double PartialExitR { get; set; }

        [NinjaScriptProperty, Range(0, 50)]
        [Display(Name = "Trail (bars, 0=off)", Order = 5, GroupName = "ORB 230")]
        public int TrailBars { get; set; }

        [NinjaScriptProperty, Range(0.0, 20.0)]
        [Display(Name = "Target (x risk, 0=off)", Order = 6, GroupName = "ORB 230")]
        public double TargetR { get; set; }

        [NinjaScriptProperty, Range(0.0, 3.0)]
        [Display(Name = "Vol-regime filter (x 60-session median, 0=off)", Order = 7, GroupName = "ORB 230")]
        public double AtrFilter { get; set; }

        [NinjaScriptProperty, Range(0.0, 3.0)]
        [Display(Name = "Volume-pace gate (x prior-20 norm, 0=off)", Order = 8, GroupName = "ORB 230")]
        public double VpaceFilter { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Skip half-days / holidays", Order = 9, GroupName = "ORB 230")]
        public bool SkipHolidays { get; set; }

        // Both declared LAST on purpose: XmlSerializer writes elements in declaration
        // order, and the live row's saved XML predates them - a missing element
        // deserializes to the CLR default (0.0 / false), both in range, so the live
        // row keeps trading exactly as before until somebody sets them.
        [NinjaScriptProperty, Range(0.0, 10.0)]
        [Display(Name = "Breakeven (R, 0=off) - the run #234 exit lever", Order = 98, GroupName = "ORB")]
        public double BreakevenR { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Historical fills ON (parity backtest only)", Order = 99, GroupName = "ORB")]
        public bool HistFills { get; set; }

        [NinjaScriptProperty, Range(1, 10)]
        [Display(Name = "Quantity PER LOT (2x is entered)", Order = 10, GroupName = "ORB 230")]
        public int Qty { get; set; }
        #endregion
    }
}
