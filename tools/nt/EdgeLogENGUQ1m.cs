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
using System.Globalization;
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

        // CARRY A TRADE ACROSS A RESTART. This strategy holds positions across sessions
        // and the machine is powered down overnight, so a live trade routinely outlives
        // the process that opened it. The protective stop is GTC and rests at the broker,
        // so the position is never unprotected. What dies with the process is the
        // strategy's own memory of the trade: entry price, risk, and where the stop had
        // trailed to. Without that it cannot resume, which forced an ugly choice between
        // closing a trade the rules never closed, or leaving one unmanaged. Persisting a
        // handful of numbers removes the choice.
        private const string StateFile = @"C:\EdgeLog\enguq_state.json";
        private bool stateChecked;      // restore is attempted once, on the first live bar

        /// <summary>Persist the open trade so a restart can resume it. Called whenever the
        /// trade state changes. Never throws.</summary>
        private void SaveState()
        {
            // Replayed bars must never touch the file. The historical pass reconstructs the
            // trade from scratch and finishes flat, so letting it write would erase the very
            // trade this exists to remember -- which is exactly what happened on 2026-08-19.
            if (State != State.Realtime) return;
            try
            {
                var ci = CultureInfo.InvariantCulture;
                string inst = Instrument != null ? Instrument.FullName : "";
                string json = "{"
                    + "\"inPos\":" + (inPos ? "true" : "false")
                    + ",\"ep\":" + ep.ToString("R", ci)
                    + ",\"risk\":" + risk.ToString("R", ci)
                    + ",\"sl\":" + sl.ToString("R", ci)
                    + ",\"trailActive\":" + (trailActive ? "true" : "false")
                    + ",\"qty\":" + Qty.ToString(ci)
                    + ",\"instrument\":\"" + inst + "\""
                    + ",\"saved_utc\":\"" + DateTime.UtcNow.ToString("yyyy-MM-dd HH:mm:ss", ci) + "\""
                    + "}";
                System.IO.File.WriteAllText(StateFile, json);
            }
            catch { }
        }

        private static double JsonNum(string js, string key, double dflt)
        {
            try
            {
                int i = js.IndexOf("\"" + key + "\":");
                if (i < 0) return dflt;
                i += key.Length + 3;
                int j = i;
                while (j < js.Length && (char.IsDigit(js[j]) || js[j] == '.' || js[j] == '-'
                       || js[j] == '+' || js[j] == 'E' || js[j] == 'e')) j++;
                return double.Parse(js.Substring(i, j - i), CultureInfo.InvariantCulture);
            }
            catch { return dflt; }
        }

        private static bool JsonHas(string js, string key, string val)
        {
            return js.IndexOf("\"" + key + "\":" + val) >= 0
                || js.IndexOf("\"" + key + "\":\"" + val + "\"") >= 0;
        }

        /// <summary>On the first live bar, if the ACCOUNT holds a position this strategy has
        /// no memory of, adopt the saved trade instead of ignoring it. Refuses on any
        /// mismatch -- wrong instrument, saved state says flat, numbers missing -- because
        /// managing a position with the wrong entry and stop is worse than not managing it.
        /// Never throws.</summary>
        private void RestoreState()
        {
            if (stateChecked) return;
            stateChecked = true;
            try
            {
                if (inPos) return;
                if (Position.MarketPosition != MarketPosition.Long)
                {
                    // STARTING FLAT: throw away any saved trade. A position can be closed by
                    // something OTHER than this strategy -- on 2026-08-19 the risk killswitch
                    // flattened the account and disabled the roster in the same second, so the
                    // strategy never got another bar in which to notice, and its file went on
                    // claiming an open trade for the rest of the day. Left there, the next
                    // restart could hand those stale numbers -- an entry price and a stop from
                    // a trade that no longer exists -- to a position that is not the same one.
                    try
                    {
                        if (System.IO.File.Exists(StateFile)
                            && JsonHas(System.IO.File.ReadAllText(StateFile), "inPos", "true"))
                        {
                            inPos = false; ep = 0; risk = 0; sl = 0; trailActive = false;
                            SaveState();
                            Print("ENGUQ resume: starting flat, so the saved trade is stale - cleared");
                        }
                    }
                    catch { }
                    return;
                }
                if (!System.IO.File.Exists(StateFile))
                { Print("ENGUQ resume: account is long but there is no saved trade - NOT managing it"); return; }
                string js = System.IO.File.ReadAllText(StateFile);
                if (!JsonHas(js, "inPos", "true"))
                { Print("ENGUQ resume: saved trade says flat - refusing to adopt"); return; }
                string inst = Instrument != null ? Instrument.FullName : "";
                if (!JsonHas(js, "instrument", inst))
                { Print("ENGUQ resume: saved trade is for a different instrument - refusing"); return; }
                double sEp = JsonNum(js, "ep", double.NaN);
                double sRisk = JsonNum(js, "risk", double.NaN);
                double sSl = JsonNum(js, "sl", double.NaN);
                if (double.IsNaN(sEp) || double.IsNaN(sRisk) || double.IsNaN(sSl) || sRisk <= 0)
                { Print("ENGUQ resume: saved trade is incomplete - refusing"); return; }
                // The account can hold a position that is NOT this trade. ORB230 trades the
                // same contract on the same account, so what NinjaTrader hands over on start
                // is the NET of every strategy. Adopting that blindly would have this strategy
                // trailing somebody else stop. Size has to agree before the saved numbers are
                // allowed to describe it.
                double sQty = JsonNum(js, "qty", double.NaN);
                if (double.IsNaN(sQty) || (int)sQty != Position.Quantity)
                {
                    Print("ENGUQ resume: account holds " + Position.Quantity + " but the saved trade is "
                        + (double.IsNaN(sQty) ? "unknown" : ((int)sQty).ToString())
                        + " - this position is not mine, refusing to manage it");
                    return;
                }
                ep = sEp; risk = sRisk; sl = sSl;
                trailActive = JsonHas(js, "trailActive", "true");
                inPos = true;
                SaveState();
                Print("ENGUQ resume: adopted the open trade - entry " + ep.ToString("F2")
                    + ", risk " + risk.ToString("F2") + ", stop " + sl.ToString("F2")
                    + ", trailing=" + trailActive);
                ExitLongStopMarket(0, true, Position.Quantity,
                    Instrument.MasterInstrument.RoundToTickSize(sl), "EQx", "");   // "" = any entry: an ADOPTED position has no entry signal, and NT silently ignores exits tied to one (live 2026-08-25)
            }
            catch (Exception ex) { Print("ENGUQ resume failed: " + ex.Message); }
        }

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
                // ADOPT, do not abandon. This strategy holds across sessions and the machine
                // is powered down overnight, so a live trade regularly outlives the process.
                // Adopting lets it pick that trade back up (see RestoreState). NinjaScript
                // rejects the setting outright unless the strategy declares it is aware of it,
                // and the rejection arrives as a runtime error that terminates the strategy.
                IsAdoptAccountPositionAware = true;
                StartBehavior = StartBehavior.AdoptAccountPosition;
                BarsRequiredToTrade = 60;

                // v2026-08-26 (owner: "adjust ENGUq on paper trade and any subsequent gates").
                // These defaults were the RTH-scaled #149 numbers with the efficiency gate OFF,
                // while the PAPER leg this strategy is mapped to (ENGUQ_ER) is run #265 on the
                // 24-hour ETH tape. An ETH day is ~1380 one-minute bars against RTH's ~390, so
                // every bar-count lookback is ~3.54x longer; the old defaults ran hour-scale
                // windows on a 24-hour tape with no efficiency filter. Measured on the same tape
                // and window (tools/enguq_nt_default_gap.py): the old defaults trade 9,276 times
                // for $227,670 at PF 1.09, against run #265's 1,336 trades for $486,413 at
                // PF 1.60 - twice the money on a seventh of the trades. Nobody ever attached the
                // strategy, so this never cost anything; it is fixed so attaching it just works.
                TlLen      = 170;   // was 48  (RTH)
                EmaLen     = 1380;  // was 390 (RTH)
                BufAtr     = 0.9;
                MinBrk     = 1.3;
                AtrLen     = 106;   // was 30  (RTH)
                VolMult    = 0.8;
                StopMult   = 1.0;
                ActR       = 2.5;
                TrailFrac  = 2.5;
                BreakevenR = 1.5;
                ErLen      = 60;
                ErTh       = 0.25;  // was 0.0 (gate OFF). 0.25 = the run #265 efficiency floor,
                                    // the ONLY thing separating #265 from the retired #226 leg.
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
                inPos = false; SaveState();
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
                        ExitLong(Qty, "EQx", "");   // "" = any entry: an ADOPTED position has no entry signal, and NT silently ignores exits tied to one (live 2026-08-25)
                        limitPending = false; inPos = false;
                        return;
                    }
                    sl = ep - StopMult * risk;
                    trailActive = false; inPos = true; limitPending = false;
                    SaveState();
                    ExitLongStopMarket(0, true, Qty,
                        Instrument.MasterInstrument.RoundToTickSize(sl), "EQx", "");   // "" = any entry: an ADOPTED position has no entry signal, and NT silently ignores exits tied to one (live 2026-08-25)
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

            if (State == State.Realtime) RestoreState();

            // ── manage an open position (engine order: activate → trail → BE → stop) ─
            if (inPos && Position.MarketPosition == MarketPosition.Long)
            {
                if (!trailActive && High[0] - ep >= ActR * risk) trailActive = true;
                if (trailActive) sl = Math.Max(sl, High[0] - TrailFrac * risk);
                if (BreakevenR > 0 && High[0] - ep >= BreakevenR * risk) sl = Math.Max(sl, ep);
                ExitLongStopMarket(0, true, Qty,
                    Instrument.MasterInstrument.RoundToTickSize(sl), "EQx", "");   // "" = any entry: an ADOPTED position has no entry signal, and NT silently ignores exits tied to one (live 2026-08-25)
                SaveState();
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
            // HistFills (2026-08-25, parity tooling - same knob EdgeLogNOISE grew a day
            // earlier): a chart-hosted instance normally takes NO historical fills (the
            // ghost-position rule), which also means DumpBlotter has nothing to write.
            // The engine-vs-NT parity run needs a full historical blotter WITHOUT the
            // Strategy Analyzer (which cannot be driven headlessly), so this knob -
            // default OFF, never enabled on the live leg - restores Analyzer-style
            // historical fills on a chart. Realtime behaviour is untouched, and the
            // SaveState guard already refuses to persist non-Realtime trades.
            if (State != State.Realtime && !IsInStrategyAnalyzer && !HistFills) return;

            // WARM-UP (fixed 2026-08-26 alongside the ETH defaults). The old guard was
            // TlLen+1 only -- fine when EmaLen was 390, wrong now it is 1380. NinjaTrader's
            // EMA() seeds from the FIRST bar on the chart and converges exponentially, so a
            // 1380-period EMA is badly wrong for thousands of bars after load, while the
            // engine computes it over the whole history. Trading before it settles is not a
            // small difference: the uptrend test (Close > ema) is this strategy's primary
            // filter, so a wrong EMA means entries the engine would never take.
            // EmaLen+TlLen is the MINIMUM for the maths to be defined. Convergence wants
            // several multiples of EmaLen, so LOAD PLENTY OF HISTORY: on NQ 1-minute ETH,
            // 1380 bars is one 24-hour day, so give the chart weeks, not days.
            if (CurrentBar < EmaLen + TlLen + 1) return;

            // ── entry signal (all conditions on the just-closed bar) ─────────────
            if (Close[0] <= Open[0]) return;                            // green candle
            if (!(Close[0] > ema[0])) return;                           // uptrend
            if (VolMult > 0)
            {
                if (CurrentBar < 19) return;
                if (!(Volume[0] >= VolMult * volAvg[0])) return;        // volume spike
            }

            // ── efficiency-ratio gate (engine ENGUQ_1M_ETH_ER_1_0, the #265 leg) ──
            // Kaufman ER of the last ErLen closes: |net move| / sum(|bar-to-bar moves|),
            // evaluated on the signal bar's own close - 1.0 is a straight line, 0 is
            // churn. Enter only when er >= ErTh. ErTh=0 = gate OFF = the #226 parity
            // anchor, and 0 is also what the live row's older XML deserializes to, so
            // this knob changes nothing until somebody sets it after an NT restart.
            if (ErTh > 0)
            {
                int erL = Math.Max(2, ErLen);
                if (CurrentBar < erL) return;
                double chg = Math.Abs(Close[0] - Close[erL]);
                double path = 0;
                for (int b = 0; b < erL; b++) path += Math.Abs(Close[b] - Close[b + 1]);
                double er = path > 0 ? chg / path : 0.0;   // engine: no path = fail
                if (er < ErTh) return;
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
                SaveState();
                EnterLong(Qty, "EQ");
                ExitLongStopMarket(0, true, Qty,
                    Instrument.MasterInstrument.RoundToTickSize(sl), "EQx", "");   // "" = any entry: an ADOPTED position has no entry signal, and NT silently ignores exits tied to one (live 2026-08-25)
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

        [NinjaScriptProperty, Range(0.0, 1.0)]
        [Display(Name = "Shallow limit depth (x ATR, 0=market at close)", Order = 11, GroupName = "ENGU-Q")]
        public double LimitAtr { get; set; }

        // Declared LAST on purpose: XmlSerializer writes elements in declaration
        // order, and every existing saved row predates these knobs - a missing element
        // deserializes to the CLR default, so old rows keep trading unchanged.
        //
        // ErLen carries NO [Range] attribute DELIBERATELY: a missing int deserializes
        // to 0, and NinjaTrader enforces [Range] at STARTUP with only a popup (the
        // silent-finalize trap this project already paid for once, NT_RUNBOOK.md).
        // The entry code clamps it to >= 2 instead.
        [NinjaScriptProperty]
        [Display(Name = "Efficiency-ratio window (bars)", Order = 97, GroupName = "ENGU-Q")]
        public int ErLen { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Efficiency-ratio floor (0=off) - the run #265 gate", Order = 98, GroupName = "ENGU-Q")]
        public double ErTh { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Historical fills ON (parity backtest only)", Order = 99, GroupName = "ENGU-Q")]
        public bool HistFills { get; set; }

        [NinjaScriptProperty, Range(1, 10)]
        [Display(Name = "Quantity", Order = 12, GroupName = "ENGU-Q")]
        public int Qty { get; set; }
        #endregion
    }
}
