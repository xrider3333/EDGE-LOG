// =============================================================================
//  EDGELOG · NOISE 1.0 — NinjaTrader 8 port of augur_strategies/NOISE_1_0.py
//  For PAPER TRADING on the broker demo account (PAPER system Layer 1).
//
//  WHY THIS ONE IS THE EASY PORT
//  NOISE uses the honest convention end to end: every decision is made at a bar's
//  CLOSE and every fill is a plain market order at the NEXT bar's OPEN. There is
//  no resting entry order, no intrabar trigger, and nothing that needs to know a
//  bar's outcome before the bar ends. So unlike ORB, the engine and the platform
//  can agree trade-for-trade; the only expected difference is real slippage on
//  the market orders.
//
//  Defaults = the #231 crowned core (moved 2026-08-16): lookback 44 · bands
//    0.75 / 1.5 · exit VWAP · both sides · all day · bandwidth stop k 1.75.
//  SHORT VETO (2026-08-21): the run-#241 filter is ported as SkipBotShort +
//    DaytypeLo (engine daytype_mode='skip_bot_short'), DEFAULT OFF.
//  VOLATILITY SKIP (2026-08-23): the run-#243 crown adds VolSkipOn + VolSkipPct
//    (engine vol_skip_pct=90), DEFAULT OFF: skip ALL entries on any session whose
//    PRIOR session's (H-L)/C ranks at or above the 90th percentile of the 252
//    sessions before it (60 reference sessions minimum before it activates).
//    Fully causal, exits and stops untouched. Flipping BOTH knobs on via the
//    strategy row makes this the crowned run-#243 config (Short Veto + Wild10).
//
//  Chart: NQ ##-## · 5 Minute · session template "CME US Index Futures RTH".
//  Load at least 25 days so the 14-session noise estimate is warm on enable.
//
//  THE RULE
//   • Reference levels for the day: refHi = max(today's open, yesterday's close),
//     refLo = min(same). Fixed at the open, never revised.
//   • Noise estimate sigma[k]: for bar-of-day k, the average of
//     |close - session open| / session open over the PRIOR `lookback` sessions at
//     that SAME bar-of-day. Prior sessions only, so it is known before the bar.
//   • Bands: UB = refHi × (1 + 1.5 × sigma[k]) · LB = refLo × (1 − 1.5 × sigma[k])
//   • ENTRY: a bar CLOSES outside its band -> market order, fills next bar's open.
//   • EXIT: a bar CLOSES back across the session VWAP -> market order, next open.
//   • PROTECTIVE STOP: at entry, k × how far the entry bar's band sat outside the
//     reference. Resting stop, live from the bar AFTER entry (the engine also
//     never checks it on the entry bar).
//   • Flat at the session close. Re-entry allowed later the same session.
//
//  KNOWN GAPS vs the engine (documented, small by design):
//   • The engine exits EOD exactly at the last bar's close; NT's session-close
//     flattener fires ~30s earlier. Immaterial, but it is a real difference.
//   • VWAP is computed here from (H+L+C)/3 × volume, reset each session — the
//     same formula the engine uses, not NinjaTrader's Order Flow VWAP.
//   • Market orders fill at the next tick after the bar closes, which is the
//     honest version of "next bar's open".
// =============================================================================
#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class EdgeLogNOISE : Strategy
    {
        // ── session state ────────────────────────────────────────────────────
        private double        sessionOpen;
        private double        prevSessionClose = double.NaN;
        // Short Veto (2026-08-21, the crowned run-#241 filter; knob default OFF).
        // sessHi/sessLo accumulate THIS session's extremes bar by bar; at the next
        // session roll they are the PRIOR session's range, and together with
        // prevSessionClose give the prior close's position in its own range,
        // (C-L)/(H-L) -- exactly the engine's _daytype_pos. Fully causal: everything
        // is known before the new session's first bar.
        private double        sessHi = double.NaN, sessLo = double.NaN;
        private bool          blockShortToday;
        // Volatility skip (2026-08-23, the crowned run-#243 filter; knob default OFF).
        // volHist banks each completed session's (H-L)/C, capped at the engine's 252
        // reference window. At a session roll the session that JUST finished is ranked
        // against the (up to 252) sessions strictly before it -- exactly the engine's
        // _vol_percentile: pct = 100 * count(ref < prior) / len(ref), inactive until
        // 60 reference sessions exist. At or above VolSkipPct -> no ENTRIES today
        // (exits and stops untouched). Fully causal: everything is known at the open.
        private List<double>  volHist;
        private bool          blockAllToday;
        private int           barOfDay;
        private double        refHi, refLo;
        private List<double>  adCurrent;             // |close-open|/open per bar-of-day, this session
        private List<double[]> history;              // last `Lookback` completed sessions
        private double        cumTPV, cumVol;        // session VWAP accumulators
        private DateTime      sessionEnd = DateTime.MaxValue;
        private bool          sessionValid;          // saw this session's open (not a mid-session start)

        // ── position state ───────────────────────────────────────────────────
        private double stopLevel = double.NaN;
        private bool   stopPlaced;
        private int    lastDir;                      // +1/-1 of the position we believe we hold

        // ── ML gate (the "bouncer", owner-approved 2026-08-16) ───────────────
        // Just before entering, ask the local gate service (api/gate_live.py on this
        // same PC) "take this trade, and how big?". FAIL-OPEN by design: any error,
        // timeout, or the service simply not running -> trade exactly as before, at
        // Qty. The bouncer can only ever SKIP or RESIZE an entry the strategy already
        // wanted; it can never invent an order, and exits/stops are untouched.
        /// <summary>Contracts to enter, per the gate. Qty on ANY failure (fail-open).</summary>
        private int GateQty()
        {
            if (!GateEnabled) return Qty;
            try
            {
                var req = (System.Net.HttpWebRequest)System.Net.WebRequest.Create(GateUrl);
                req.Method  = "GET";
                req.Timeout = GateTimeoutMs;            // hard deadline; expired = fail-open
                req.ReadWriteTimeout = GateTimeoutMs;
                req.Proxy   = null;                     // localhost: skip proxy discovery
                string body;
                using (var resp = (System.Net.HttpWebResponse)req.GetResponse())
                using (var sr = new System.IO.StreamReader(resp.GetResponseStream()))
                    body = sr.ReadToEnd();

                // tiny hand parse -- the service's JSON is flat and ours
                bool take = body.IndexOf("\"take\": true") >= 0 || body.IndexOf("\"take\":true") >= 0;
                double size = 1.0;
                int i = body.IndexOf("\"size\":");
                if (i >= 0)
                {
                    int j = i + 7; int k2 = j;
                    while (k2 < body.Length && (char.IsDigit(body[k2]) || body[k2] == '.' || body[k2] == ' ')) k2++;
                    double.TryParse(body.Substring(j, k2 - j).Trim(),
                        System.Globalization.NumberStyles.Float,
                        System.Globalization.CultureInfo.InvariantCulture, out size);
                }
                if (!take)
                {
                    Print("EdgeLogNOISE gate: SKIP (" + body + ")");
                    return 0;
                }
                // Size lands on whole contracts. At Qty=1 (full NQ) this rounds nearly
                // everything to 1 -- effectively keep/skip; run Qty=10 on micros (MNQ)
                // to give the size dial real resolution.
                int q = (int)Math.Round(size * Qty);
                if (q < 1) q = 1;                       // take=true never rounds to zero
                if (q > Qty * 3) q = Qty * 3;           // engine's own 3x cap, belt+braces
                Print("EdgeLogNOISE gate: TAKE x" + size.ToString("0.00") + " -> " + q + " (" + body + ")");
                return q;
            }
            catch (Exception ex)
            {
                Print("EdgeLogNOISE gate: FAIL-OPEN (" + ex.Message + ") -> " + Qty);
                return Qty;
            }
        }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name        = "EdgeLogNOISE";
                Description = "EDGELOG NOISE 1.0 - intraday noise-band momentum, close signal / next-open fill";
                Calculate   = Calculate.OnBarClose;      // every decision is a bar-close decision
                EntriesPerDirection = 1;
                EntryHandling = EntryHandling.AllEntries;
                IsExitOnSessionCloseStrategy = true;     // engine is flat every session close
                ExitOnSessionCloseSeconds = 30;
                IsInstantiatedOnEachOptimizationIteration = false;
                StartBehavior = StartBehavior.WaitUntilFlat;
                BarsRequiredToTrade = 20;

                // Defaults moved to the #231 crowned config on 2026-08-16 (three
                // consecutive auto-validates landed on this identical dict). The old
                // hand-built 14 / 1.5 / 1.5 / 1.0 stays available by typing it in.
                Lookback       = 44;
                BandMultLong   = 0.75;
                BandMultShort  = 1.5;
                StopK          = 1.75;
                UseStop        = true;
                // Short Veto (run #241, crowned 2026-08-21): default OFF so a rebuild
                // changes nothing until the knob is deliberately flipped on the
                // strategy row (bridge /strategy/check pre-flights it first).
                SkipBotShort   = false;
                DaytypeLo      = 0.20;
                // Volatility skip (run #243, crowned 2026-08-23): default OFF for the
                // same reason -- a rebuild changes nothing until the knob is
                // deliberately flipped on the strategy row after an NT restart.
                VolSkipOn      = false;
                VolSkipPct     = 90.0;
                HistFills      = false;
                Qty            = 1;
                GateEnabled    = true;
                GateUrl        = "http://127.0.0.1:8392/gate/check?leg=NOISE_H_RF";
                GateTimeoutMs  = 300;
            }
            else if (State == State.DataLoaded)
            {
                adCurrent = new List<double>();
                history   = new List<double[]>();
                volHist   = new List<double>();
            }
            else if (State == State.Terminated)
            {
                DumpBlotter();
            }
        }

        /// <summary>Write this run's trade blotter to the nt_backtest folder so the
        /// reconcile tooling can read it without anyone driving the Strategy Analyzer UI.
        ///
        /// WHY: exporting by hand through Display > Trades > right-click > Export is the
        /// step that silently produced the wrong file twice on 2026-08-13 - once the wrong
        /// strategy, once the wrong timeframe - and neither was visible until the CSV was
        /// parsed. This writes itself, and it stamps the run's actual configuration into
        /// the header so a mismatched run can never be mistaken for a matching one.
        ///
        /// Times are written in UTC. NinjaTrader displays in the PC's local zone (Arizona
        /// here, which does not observe DST) and stamps a bar at its CLOSE while the AUGUR
        /// engine stamps at its OPEN - two independent offsets that have to be undone
        /// before any comparison. UTC removes the first; the reader handles the second.
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
                                        "EdgeLogNOISE_" + stamp + ".csv");

                var sb = new System.Text.StringBuilder();
                // Header carries the run config. The reconcile side asserts on these
                // instead of trusting that the right thing was selected in the UI.
                sb.AppendLine("# strategy=EdgeLogNOISE");
                sb.AppendLine("# instrument=" + instrument);
                sb.AppendLine("# bars=" + period);
                sb.AppendLine("# trading_hours=" + hours);
                sb.AppendLine("# lookback=" + Lookback + " bandLong=" + BandMultLong
                              + " bandShort=" + BandMultShort + " useStop=" + UseStop
                              + " stopK=" + StopK + " qty=" + Qty
                              + " skipBotShort=" + SkipBotShort + " daytypeLo=" + DaytypeLo
                              + " volSkipOn=" + VolSkipOn + " volSkipPct=" + VolSkipPct);
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
                Print("EdgeLogNOISE: wrote " + n + " trades -> " + path);
            }
            catch (Exception ex)
            {
                Print("EdgeLogNOISE: blotter dump failed: " + ex.Message);
            }
        }

        private void RollSession()
        {
            // Short Veto (run #241, engine daytype_mode='skip_bot_short'): decided ONCE
            // per session, from the session that JUST finished. If its close sat in the
            // bottom DaytypeLo of its own high-to-low range, no short ENTRIES today
            // (longs and all exits untouched). First session / zero range / a partial
            // mid-session start -> filter inactive, same as the engine's NaN.
            blockShortToday = false;
            if (SkipBotShort && !double.IsNaN(prevSessionClose)
                && !double.IsNaN(sessHi) && !double.IsNaN(sessLo) && sessHi > sessLo)
            {
                double cp = (prevSessionClose - sessLo) / (sessHi - sessLo);
                blockShortToday = cp <= DaytypeLo;
                if (blockShortToday)
                    Print("EdgeLogNOISE short veto: prior close position "
                          + cp.ToString("0.000") + " <= " + DaytypeLo + " -> no shorts today");
            }
            // Volatility skip (run #243, engine vol_skip_pct): decided ONCE per session.
            // Rank the session that JUST finished against the (up to 252) sessions
            // strictly before it, THEN bank it -- so the reference window can never
            // contain the session being ranked, exactly like the engine. A partial
            // mid-session start banks nothing and blocks nothing (engine NaN).
            blockAllToday = false;
            if (!double.IsNaN(sessHi) && !double.IsNaN(sessLo)
                && !double.IsNaN(prevSessionClose) && prevSessionClose > 0)
            {
                double priorVol = (sessHi - sessLo) / prevSessionClose;
                if (VolSkipOn && volHist.Count >= 60)
                {
                    int below = 0;
                    for (int i = 0; i < volHist.Count; i++) if (volHist[i] < priorVol) below++;
                    double pct = 100.0 * below / volHist.Count;
                    blockAllToday = pct >= VolSkipPct;
                    if (blockAllToday)
                        Print("EdgeLogNOISE vol skip: prior session range percentile "
                              + pct.ToString("0.0") + " >= " + VolSkipPct + " -> no entries today");
                }
                volHist.Add(priorVol);
                while (volHist.Count > 252) volHist.RemoveAt(0);
            }
            sessHi = double.NaN; sessLo = double.NaN;

            // bank the session that just finished, keep only the last `Lookback`
            if (adCurrent != null && adCurrent.Count > 0)
            {
                history.Add(adCurrent.ToArray());
                while (history.Count > Lookback) history.RemoveAt(0);
            }
            adCurrent = new List<double>();
            barOfDay = 0;
            cumTPV = 0; cumVol = 0;
            sessionOpen = Open[0];
            refHi = double.IsNaN(prevSessionClose) ? sessionOpen : Math.Max(sessionOpen, prevSessionClose);
            refLo = double.IsNaN(prevSessionClose) ? sessionOpen : Math.Min(sessionOpen, prevSessionClose);
            stopLevel = double.NaN; stopPlaced = false;
            try
            {
                var si = new SessionIterator(Bars);
                si.GetNextSession(Time[0], true);
                sessionEnd = si.ActualSessionEnd;
            }
            catch { sessionEnd = DateTime.MaxValue; }

            // Warm-up self-report (2026-08-16). Lookback 44 needs 44 banked sessions
            // before the FIRST trade is even possible, and a chart that loads fewer
            // days fails SILENTLY -- the strategy just never trades and nothing says
            // why. This one line, rewritten each session roll, makes the warm-up state
            // checkable from outside NinjaTrader. Never throws.
            try
            {
                System.IO.File.WriteAllText(@"C:\EdgeLog\noise_warmup.txt",
                    DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")
                    + "  sessions_banked=" + history.Count
                    + "  lookback=" + Lookback
                    + "  warm=" + (history.Count >= Lookback)
                    + "  bars_loaded=" + (Bars != null ? Bars.Count : 0)
                    + "  state=" + State);
            }
            catch { }
        }

        /// <summary>Mean of the prior sessions' noise at this bar-of-day. Sessions that
        /// were shorter simply do not contribute at that index (the engine's nanmean).</summary>
        private double Sigma(int k)
        {
            double sum = 0; int n = 0;
            for (int i = 0; i < history.Count; i++)
            {
                double[] a = history[i];
                if (k < a.Length && !double.IsNaN(a[k])) { sum += a[k]; n++; }
            }
            return n > 0 ? sum / n : double.NaN;
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0) return;

            if (Bars.IsFirstBarOfSession)
            {
                RollSession();
                sessionValid = true;
            }
            if (!sessionValid) { prevSessionClose = Close[0]; return; }   // enabled mid-session: wait for a clean open

            // ── this bar's own bookkeeping (all knowable at its close) ───────
            // Session extremes for the Short Veto's prior-close-position read. Only
            // clean sessions accumulate (the mid-session-start return above already
            // skipped invalid bars), so a partial session can never fake a range.
            sessHi = double.IsNaN(sessHi) ? High[0] : Math.Max(sessHi, High[0]);
            sessLo = double.IsNaN(sessLo) ? Low[0]  : Math.Min(sessLo, Low[0]);
            double ad = sessionOpen > 0 ? Math.Abs(Close[0] - sessionOpen) / sessionOpen : double.NaN;
            while (adCurrent.Count <= barOfDay) adCurrent.Add(double.NaN);
            adCurrent[barOfDay] = ad;

            double tp = (High[0] + Low[0] + Close[0]) / 3.0;
            cumTPV += tp * Volume[0];
            cumVol += Volume[0];
            double vwap = cumVol > 0 ? cumTPV / cumVol : double.NaN;

            double sig = Sigma(barOfDay);
            double ub = double.NaN, lb = double.NaN;
            if (!double.IsNaN(sig))
            {
                ub = refHi * (1.0 + BandMultLong * sig);
                lb = refLo * (1.0 - BandMultShort * sig);
            }

            bool warm = history.Count >= Lookback;
            bool lastBar = Bars.IsLastBarOfSession;

            // ── in a position ───────────────────────────────────────────────
            if (Position.MarketPosition != MarketPosition.Flat)
            {
                lastDir = Position.MarketPosition == MarketPosition.Long ? 1 : -1;

                // Protective stop, sized from THIS bar's band excursion, placed once.
                // It goes live for the next bar — the engine likewise never tests the
                // stop on the entry bar itself.
                if (UseStop && !stopPlaced && !double.IsNaN(ub) && !double.IsNaN(lb))
                {
                    double fill = Position.AveragePrice;      // anchor on the actual fill
                    stopLevel = lastDir > 0 ? fill - StopK * (ub - refHi)
                                            : fill + StopK * (refLo - lb);
                    if (!double.IsNaN(stopLevel))
                    {
                        double px = Instrument.MasterInstrument.RoundToTickSize(stopLevel);
                        if (lastDir > 0) ExitLongStopMarket(0, true, Qty, px, "NZstop", "NZ");
                        else             ExitShortStopMarket(0, true, Qty, px, "NZstop", "NZ");
                        stopPlaced = true;
                    }
                }

                // VWAP mean-reversion exit, decided at this close, filled next open.
                if (!double.IsNaN(vwap) && !lastBar)
                {
                    bool trig = (lastDir > 0 && Close[0] < vwap) || (lastDir < 0 && Close[0] > vwap);
                    if (trig)
                    {
                        if (lastDir > 0) ExitLong(Qty, "NZexit", "NZ");
                        else             ExitShort(Qty, "NZexit", "NZ");
                        stopPlaced = false; stopLevel = double.NaN;
                    }
                }
                // barOfDay MUST advance here too. It did not until 2026-08-13, and the
                // early return meant bar-of-day froze for the whole life of every trade:
                // adCurrent[barOfDay] was overwritten at the same index bar after bar, and
                // Sigma(barOfDay) was then read at a stale, too-early index for the REST of
                // the session. Noise is smallest right after the open and grows through the
                // day, so a stale index means a noise estimate that is too small, bands that
                // are too narrow, and far too many entries. Measured against the engine on
                // identical bars: 322 trades vs 191, and trades on 151 days vs 108.
                barOfDay++;
                prevSessionClose = Close[0];
                return;                                  // never signal an entry while holding
            }

            stopPlaced = false; stopLevel = double.NaN;

            // ── flat: look for a band-break entry at this bar's close ────────
            // Skipped on the session's first bar and on the session's LAST bar —
            // exactly the engine's `1 <= k <= m-2` rule (barOfDay>=1 covers the
            // low end, !lastBar the high end; session length is calendar
            // knowledge, not look-ahead). The old extra `Time[0] < sessionEnd
            // - 10min` guard blocked the final TWO signal bars the engine
            // allows (fills at 15:50/15:55): the 2026-08-24 crown parity run
            // showed every one of the engine's 5 unmatched late-day entries was
            // this guard, a systematic one-sided divergence — removed.
            if (warm && barOfDay >= 1 && !lastBar
                && !double.IsNaN(ub) && !double.IsNaN(lb))
            {
                bool longTrig  = Close[0] > ub;
                bool shortTrig = Close[0] < lb;
                // Volatility skip: a session-level entry gate, applied before everything
                // else exactly like the engine's sess_block_entries (exits, stops and the
                // EOD flattener are untouched -- it only stops NEW positions today).
                if (blockAllToday) { longTrig = false; shortTrig = false; }
                // Short Veto: applied BEFORE the both-trigger tie-break, exactly like the
                // engine (block_short falses short_trig first, so a both-trigger bar on a
                // vetoed day takes the LONG side rather than no trade).
                if (blockShortToday) shortTrig = false;
                if (longTrig && shortTrig)               // both: take the bigger excursion
                {
                    if ((Close[0] - ub) >= (lb - Close[0])) shortTrig = false; else longTrig = false;
                }
                if (longTrig || shortTrig)
                {
                    // Historical bars (chart warm-up / backtest) never call the gate:
                    // the service only knows "now", so an answer for an old bar would be
                    // nonsense -- and the blotter must stay comparable to the engine.
                    // Live warm-up must not open a position: a ghost inherited from replay
                    // blocks the strategy from trading (ENGU-Q 08-17, ORB230 08-19).
                    // Strategy Analyzer stays full-size so backtests remain comparable.
                    // HistFills (2026-08-24, parity tooling): a chart-hosted instance
                    // normally takes NO historical fills (the ghost-position rule above),
                    // which also means DumpBlotter has nothing to write. The engine-vs-NT
                    // parity run needs a full historical blotter WITHOUT the Strategy
                    // Analyzer (which cannot be driven headlessly), so this knob — default
                    // OFF, never enabled on a live leg — restores Analyzer-style full-size
                    // historical fills on a chart. Realtime behaviour is untouched.
                    int q = State == State.Realtime ? GateQty()
                          : ((IsInStrategyAnalyzer || HistFills) ? Qty : 0);
                    if (q > 0)
                    {
                        if (longTrig) EnterLong(q, "NZ");
                        else          EnterShort(q, "NZ");
                    }
                }
            }

            barOfDay++;
            prevSessionClose = Close[0];
        }

        #region Properties
        [NinjaScriptProperty, Range(5, 120)]
        [Display(Name = "Noise lookback (sessions)", Order = 1, GroupName = "NOISE")]
        public int Lookback { get; set; }

        [NinjaScriptProperty, Range(0.5, 2.5)]
        [Display(Name = "Upper band width (x noise)", Order = 2, GroupName = "NOISE")]
        public double BandMultLong { get; set; }

        [NinjaScriptProperty, Range(0.5, 2.5)]
        [Display(Name = "Lower band width (x noise)", Order = 3, GroupName = "NOISE")]
        public double BandMultShort { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Protective stop ON (bandwidth mode)", Order = 4, GroupName = "NOISE")]
        public bool UseStop { get; set; }

        [NinjaScriptProperty, Range(0.25, 4.0)]
        [Display(Name = "Stop size (x band excursion)", Order = 5, GroupName = "NOISE")]
        public double StopK { get; set; }

        [NinjaScriptProperty, Range(1, 10)]
        [Display(Name = "Quantity", Order = 6, GroupName = "NOISE")]
        public int Qty { get; set; }

        // ── Short Veto (run #241, the crowned NOISE filter, 2026-08-21) ──────
        // Engine equivalent: daytype_mode='skip_bot_short' with daytype_lo. When ON,
        // no short ENTRIES on any session whose PRIOR session closed in the bottom
        // DaytypeLo of that prior session's own high-to-low range. Longs, exits and
        // stops untouched. Default OFF -- enable it on the strategy row to run the
        // crowned config.
        [NinjaScriptProperty]
        [Display(Name = "Short veto ON (skip shorts after a weak close)", Order = 10, GroupName = "NOISE")]
        public bool SkipBotShort { get; set; }

        [NinjaScriptProperty, Range(0.05, 0.5)]
        [Display(Name = "Weak-close threshold (fraction of prior range)", Order = 11, GroupName = "NOISE")]
        public double DaytypeLo { get; set; }

        // ── Volatility skip (run #243, the crowned NOISE filter, 2026-08-23) ─
        // Engine equivalent: vol_skip_pct. When ON, no ENTRIES at all on any session
        // whose PRIOR session's (H-L)/C ranks at or above VolSkipPct among the 252
        // sessions before it (needs 60 banked reference sessions to activate; exits,
        // stops and the EOD flattener untouched). Default OFF -- enable BOTH this and
        // the Short Veto on the strategy row to run the crowned run-#243 config.
        [NinjaScriptProperty]
        [Display(Name = "Volatility skip ON (no entries after a wildest-decile day)", Order = 12, GroupName = "NOISE")]
        public bool VolSkipOn { get; set; }

        [NinjaScriptProperty, Range(50.0, 100.0)]
        [Display(Name = "Volatility percentile threshold (skip at/above)", Order = 13, GroupName = "NOISE")]
        public double VolSkipPct { get; set; }

        // Parity tooling only (2026-08-24): full-size HISTORICAL fills on a chart, so a
        // chart-hosted instance can produce a complete backtest blotter for reconcile.
        // NEVER turn this on for a live leg — historical fills recreate the ghost-position
        // problem the q=0 rule exists to prevent. Default OFF.
        [NinjaScriptProperty]
        [Display(Name = "Historical fills ON (parity backtest only)", Order = 14, GroupName = "NOISE")]
        public bool HistFills { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ML gate ON (ask the local bouncer before entering)", Order = 7, GroupName = "ML GATE")]
        public bool GateEnabled { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Gate URL (local service)", Order = 8, GroupName = "ML GATE")]
        public string GateUrl { get; set; }

        [NinjaScriptProperty, Range(50, 2000)]
        [Display(Name = "Gate timeout ms (expired = trade ungated)", Order = 9, GroupName = "ML GATE")]
        public int GateTimeoutMs { get; set; }
        #endregion
    }
}
