// =============================================================================
//  EDGELOG · NOISE #545.1 keel — run #545 champion set 1 (augur_strategies/NOISE_1_8_CT304H_KFX.py,
//  gate_len 16 / gate_ratio 1.15 / tilt_mult 2.75 / fri_mult 2.0) x KEEL v12, on MNQ, Sim101 ONLY. Paper leg api/paper.py NOISE_545_K12.
//  Copied 2026-11-22 from EdgeLogNOISE422.cs (the #422 leg, N4), which keeps running beside it.
//  Same core as EdgeLogNOISE422 (NOISE_1_8_CT304H.py _FROZEN, py 62-68). Differences, all from the run:
//   • Hourly squeeze length 16 (not 20), ratio 1.15, tilt x2.75 (run #545 best_params; CT304H py 154-167).
//   • KEEL v12 SIZE: at the decision bar's close, ask api/gate_live.py /keel?leg=NOISE_545_K12 for the
//     multiplier = the file's Friday tilt (NOISE_1_8_CT304H_KFX.py py 92-93: fri_mult 2.0 when the FILL bar is a Friday)
//     x the KEEL v12 walk size over the paper leg's own closed trades. Contracts =
//     round(Qty x squeeze tilt x multiplier), at least 1 -- the paper row's size is the same product
//     (api/paper.py unfold_gate_sizes). FAIL-OPEN: no / bad / slow answer -> multiplier 1.0 (the
//     squeeze tilt alone). Same bar interlock as the ML gate (bar + own OHLCV sent).
//   • Signals N6 / N6exit / N6stop. Own files noise545k_state.json, noise545k_decisions.csv,
//     noise545k_warmup.txt. The other KEEL leg is EdgeLogNOISE555K (N5, run #555).
//   • Shared 40-contract ACCOUNT rail with EdgeLogNOISE / EdgeLogNOISE422 (RailClamp, identical).
//   • Flat at the session close (IsExitOnSessionCloseStrategy), like the others.
//  Historical / Analyzer bars never ask /keel (the service only knows "now"): they size on the
//  squeeze tilt alone, so an Analyzer blotter is the KEEL-free file, not the paper leg.
//  ---- original EdgeLogNOISE header follows ----
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
//  THE DECISION LEDGER (2026-08-26) — C:\EdgeLog\gate_decisions.csv
//  Nothing used to join a gate answer to a fill. The gate service logged its own
//  reply, this strategy Print()ed to an output window nobody keeps, and the fills
//  carry neither the probability nor the intended size. So when this leg was
//  enabled on 2026-08-24 and simply never asked the gate anything, there was no
//  way afterwards to tell that apart from "the gate was asked and said no" or
//  from "the market never gave a signal" — three completely different situations
//  that all look like an empty day. Every entry opportunity now appends one row,
//  INCLUDING the branches where the gate is never consulted; those are exactly
//  the ones that were invisible. See the Ledger() block for the column meanings.
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
    public class EdgeLogNOISE545K : Strategy
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

        // ── resume after a restart (2026-10-09, owner: "pick up where they left off") ──
        // On 10-08 a feed flap disabled NOISE with a 10 MNQ short on; the GTC stop held at the
        // broker but nothing ran the VWAP exit or the session-close exit, and the short sat
        // open overnight. What dies with an instance is its memory of the trade: the stop
        // level it computed once at entry. This file keeps it, written only in real time, so
        // a restart started with StartBehavior=AdoptAccountPosition can take the SAME trade
        // back. Anything that does not match -- side, size, contract, a missing or flat file --
        // is not adopted and is left strictly alone (no stop, no exit, no entry), exactly the
        // ENGU-Q rule (EdgeLogENGUQ1m.RestoreState): managing a position with the wrong stop is
        // worse than not managing it, and the watchdog holds such a position for a person.
        private const string StateFile = @"C:\EdgeLog\noise545k_state.json";
        private bool   stateChecked;                 // restore runs once, on the first live bar
        private bool   adopted;                      // this instance took the trade over from a saved file
        private bool   foreign;                      // the account holds a position that is not ours: hands off
        private bool   savedInPos;                   // what the file last said, so flat bars do not rewrite it
        private Order  adoptStop;                                        // our stop placed on adopt
        private List<Order> staleStops;                                  // the dead instance's stops

        // ── decision ledger state ────────────────────────────────────────────
        // The date of the last "nothing can happen today" row, so that state is
        // recorded once per session instead of once per bar.
        private DateTime ledgerSessionDay = DateTime.MinValue;

        // ── ML gate (the "bouncer", owner-approved 2026-08-16) ───────────────
        // Just before entering, ask the local gate service (api/gate_live.py on this
        // same PC) "take this trade, and how big?". FAIL-OPEN by design: any error,
        // timeout, or the service simply not running -> trade exactly as before, at
        // Qty. The bouncer can only ever SKIP or RESIZE an entry the strategy already
        // wanted; it can never invent an order, and exits/stops are untouched.

        /// <summary>One gate answer, in enough detail to write a full ledger row.
        ///
        /// WHY A CLASS AND NOT AN int: the old GateQty() returned only the quantity, so
        /// the probability, the threshold, the served size, the latency and the reason a
        /// call failed all died inside the method. That is half of why a gate decision
        /// could not be joined to a fill afterwards.
        ///
        /// Unknown numbers stay NaN / -1 and the ledger writes them EMPTY. A probability
        /// of zero and a probability nobody ever measured must never look the same.</summary>
        private class GateAnswer
        {
            public int    Q;                        // contracts to order (0 = do not enter)
            public string Outcome = "NOT_ASKED";    // ORDERED|SKIPPED_BY_GATE|FAIL_OPEN|NOT_ASKED
            public string Reason  = "";             // why, for NOT_ASKED / FAIL_OPEN
            public double Prob      = double.NaN;
            public double Threshold = double.NaN;
            public double Size      = double.NaN;   // the served size multiplier
            public int    Bars       = -1;          // bars the service scored on
            public int    BarMinutes = -1;          // ...and their step, the G2 interlock's evidence
            public int    ServedMax  = -1;          // max_contracts as served, -1 = the field was absent
            public int    Cap        = -1;          // the cap this strategy actually enforced
            public int    QIntended  = -1;          // contracts the model asked for, BEFORE the cap
            public int    HttpStatus = -1;
            public int    LatencyMs  = -1;
            public int    TakeFlag     = -1;        // -1 unknown, 0 false, 1 true
            public int    FallbackFlag = -1;        // the service's own ungated_fallback
            public string BarCheck     = null;      // ok | absent | unparseable | mismatch
        }

        /// <summary>An answer for a branch that never reaches the gate. `q` is what the
        /// strategy will order anyway (Qty when the gate is simply switched off, 0 when
        /// something upstream cancelled the entry).</summary>
        private GateAnswer NotAsked(string reason, int q)
        {
            GateAnswer a = new GateAnswer();
            a.Q = q;
            a.Outcome = "NOT_ASKED";
            a.Reason  = reason;
            return a;
        }

        /// <summary>Whole contracts for a fractional size: round(size x Qty), at least 1. Banker's
        /// rounding on purpose -- tools/nt_fill_reconcile.py prices the book side with Python's
        /// round(size * 3), which is the same rule, so a .5 lands on the same contract count.</summary>
        private int BaseQ(double size)
        {
            int q = (int)Math.Round(size * Qty, MidpointRounding.ToEven);
            return q < 1 ? 1 : q;
        }

        /// <summary>Ask /keel for the KEEL v12 multiplier, and bring back everything the ledger
        /// needs. Never throws: every failure path sizes on the squeeze tilt alone (x1.0).</summary>
        private GateAnswer AskKeel(DateTime barTime, double ctTilt)
        {
            GateAnswer a = new GateAnswer();
            a.Size = ctTilt;
            a.Q = BaseQ(ctTilt);                        // the answer if anything at all goes wrong
            DateTime t0 = DateTime.UtcNow;
            string body = "";
            try
            {
                // BAR INTERLOCK (2026-08-26). For three days every NOISE and ORB decision
                // was scored on ENGU-Q's overnight 1-minute bars because the service's bar
                // cache was keyed only on the date, and nothing in either process compared
                // notes -- the probabilities looked perfectly plausible. Telling the service
                // which bar this chart is acting on lets it refuse to answer for a series it
                // is not actually holding.
                //
                // The stamp sent is the bar's OPEN, in ISO-8601 WITH the offset. NinjaTrader
                // stamps a bar at its CLOSE and shows it in the PC's zone (Arizona, no DST);
                // the AUGUR engine stamps at the OPEN in ET. Sending the open stamp puts both
                // sides on the engine's convention, and the offset lets the service do the
                // zone conversion instead of guessing -- otherwise the two clocks disagree by
                // a full bar plus three hours and the interlock would cry mismatch on every
                // single request.
                //
                // OWN FINISHED-BAR PRICES (owner-approved 2026-09-28). We ask the instant
                // this bar closes (Calculate.OnBarClose), so Open[0]/High[0]/Low[0]/Close[0]
                // /Volume[0] right here ARE that same just-closed bar -- the one `barTime`
                // (its open) names. The service's own 10-second capture rebuilds the same bar
                // from a separate file and can still be a few seconds behind at the exact
                // moment we ask (2026-09-28 11:00 ET: "capture covers through 1790607590,
                // short of bar-end 1790607600" -> FAIL-OPEN, an ungated short). Sending our
                // own finished OHLCV lets the service score on THIS bar instead of waiting on
                // that capture; it validates and ignores these if they look wrong (see
                // api/gate_live.py _sane_ohlcv/_apply_nt_bar), so a bad read here degrades to
                // the pre-existing capture-only behaviour, never to a fabricated decision.
                string url = GateUrl + (GateUrl != null && GateUrl.IndexOf('?') >= 0 ? "&" : "?")
                           + "bar=" + Uri.EscapeDataString(Iso(barTime))
                           + "&o=" + Uri.EscapeDataString(F(Open[0], "0.##########"))
                           + "&h=" + Uri.EscapeDataString(F(High[0], "0.##########"))
                           + "&l=" + Uri.EscapeDataString(F(Low[0], "0.##########"))
                           + "&c=" + Uri.EscapeDataString(F(Close[0], "0.##########"))
                           + "&v=" + Uri.EscapeDataString(F(Volume[0], "0.##########"));
                var req = (System.Net.HttpWebRequest)System.Net.WebRequest.Create(url);
                req.Method  = "GET";
                req.Timeout = GateTimeoutMs;            // hard deadline; expired = fail-open
                req.ReadWriteTimeout = GateTimeoutMs;
                req.Proxy   = null;                     // localhost: skip proxy discovery
                using (var resp = (System.Net.HttpWebResponse)req.GetResponse())
                {
                    a.HttpStatus = (int)resp.StatusCode;
                    using (var sr = new System.IO.StreamReader(resp.GetResponseStream()))
                        body = sr.ReadToEnd();
                }
                a.LatencyMs = (int)(DateTime.UtcNow - t0).TotalMilliseconds;

                // /keel's answer: {"multiplier": x, "fallback": bool, "keel_size", "file_tilt", "bar_check",
                // "max_contracts", ...}. A body without a usable multiplier is a FAILURE -> 1.0.
                double d;
                if (!JsonNum(body, "multiplier", out d) || double.IsNaN(d) || d <= 0 || d > 10)
                {
                    a.Outcome = "FAIL_OPEN"; a.Reason = "parse_fail"; a.Size = ctTilt; a.Q = BaseQ(ctTilt);
                    Print("EdgeLogNOISE545K keel: PARSE FAIL (no usable \"multiplier\") -> x1.0 -> " + a.Q + " (" + body + ")");
                    return a;
                }
                a.Prob = d;                                // the ledger's prob column carries the KEEL multiplier
                if (JsonNum(body, "keel_size", out d))     a.Threshold = d;   // ...and threshold the KEEL walk size
                if (JsonNum(body, "bars", out d))          a.Bars       = (int)d;
                if (JsonNum(body, "bar_minutes", out d))   a.BarMinutes = (int)d;
                if (JsonNum(body, "max_contracts", out d)) a.ServedMax  = (int)d;
                string fb = JsonRaw(body, "fallback");
                if (fb == "true") a.FallbackFlag = 1; else if (fb == "false") a.FallbackFlag = 0;
                a.BarCheck = JsonRaw(body, "bar_check");
                a.TakeFlag = 1;                            // KEEL never refuses a trade
                if (a.FallbackFlag != 0)
                {
                    // The service answered but did not size (no state, bar mismatch, incomplete bar):
                    // its multiplier is 1.0 by contract, so trade the squeeze tilt alone.
                    string err = JsonRaw(body, "error");
                    a.Outcome = "FAIL_OPEN";
                    a.Reason  = (err != null && err.IndexOf("bar mismatch") >= 0) ? "bar_mismatch" : "service_fallback";
                    a.Size = ctTilt; a.Q = BaseQ(ctTilt);
                    Print("EdgeLogNOISE545K keel: SERVICE FAIL-OPEN -> x1.0 -> " + a.Q + " (" + body + ")");
                    return a;
                }
                double mult = a.Prob;
                double size = ctTilt * mult;
                int q = BaseQ(size);
                a.Size = size;
                a.QIntended = q;
                a.Q = q;
                a.Outcome = "ORDERED";
                if (a.BarCheck != null)
                {
                    string bc = a.BarCheck.Replace("\"", "");
                    if (bc.Length > 0 && bc != "ok") a.Reason = "interlock_" + bc;
                }
                Print("EdgeLogNOISE545K keel: squeeze x" + ctTilt.ToString("0.00") + " x keel x" + mult.ToString("0.000")
                      + " -> " + q + " (" + body + ")");
                return a;
            }
            catch (System.Net.WebException wex)
            {
                a.LatencyMs = (int)(DateTime.UtcNow - t0).TotalMilliseconds;
                var r = wex.Response as System.Net.HttpWebResponse;
                if (r != null)
                {
                    a.HttpStatus = (int)r.StatusCode;
                    try { r.Close(); } catch { }
                }
                a.Outcome = "FAIL_OPEN";
                a.Reason  = wex.Status == System.Net.WebExceptionStatus.Timeout ? "timeout" : "http_error";
                a.Size = ctTilt; a.Q = BaseQ(ctTilt);
                Print("EdgeLogNOISE545K keel: FAIL-OPEN (" + a.Reason + ": " + wex.Message + ") -> x1.0 -> " + a.Q);
                return a;
            }
            catch (Exception ex)
            {
                a.LatencyMs = (int)(DateTime.UtcNow - t0).TotalMilliseconds;
                a.Outcome = "FAIL_OPEN";
                a.Reason  = (ex is System.IO.IOException) ? "timeout" : "http_error";
                a.Size = ctTilt; a.Q = BaseQ(ctTilt);
                Print("EdgeLogNOISE545K keel: FAIL-OPEN (" + ex.Message + ") -> x1.0 -> " + a.Q);
                return a;
            }
        }

        /// <summary>Clamp an answer to the most contracts this leg may order right now.
        ///
        /// WHY THIS REPLACED `if (q > Qty * 3) q = Qty * 3` (2026-08-26): that line was the
        /// engine's per-trade 3x stretch applied a SECOND time, here, in the wrong place --
        /// the engine caps at 3x BEFORE the book's recycle factor, this capped AFTER it. At
        /// the live Qty=3 it also swallowed the size dial whole: every accepted NOISE_H_RF
        /// answer serves 3.52-3.75, which rounds to 11 contracts and came straight back down
        /// to 9, so the model's number could not change the order at all. The cap that
        /// belongs on this side is the RISK RAIL -- the most contracts the service will
        /// authorise, which it derives from bridge.json's max_position_contracts -- with the
        /// MaxContracts parameter as the fallback when an older service serves nothing, and
        /// the old 3x as the last resort so an un-set parameter changes today's behaviour by
        /// exactly nothing.
        ///
        /// Called on EVERY answer, gated or not, so no branch can slip past the rail.</summary>
        private void ApplyCap(GateAnswer a)
        {
            if (a == null) return;
            int cap = a.ServedMax > 0 ? a.ServedMax : (MaxContracts > 0 ? MaxContracts : Qty * 3);
            a.Cap = cap;
            if (a.Q > cap)
            {
                Print("EdgeLogNOISE545K gate: risk rail capped " + a.Q + " -> " + cap + " contracts");
                a.Q = cap;
            }
        }

        // ── SHARED ACCOUNT RAIL (2026-11-20) ─────────────────────────────────
        // EdgeLogNOISE (#243, NZ), EdgeLogNOISE422 (#422, N4), EdgeLogNOISE555K (N5) and
        // EdgeLogNOISE545K (N6) trade the SAME MNQ contract
        // in the same account. Each strategy's Position only sees its own fills, so neither
        // cap above can see the other leg. Before any entry, read the ACCOUNT's net position
        // on this instrument (both strategies' fills) and clamp so that
        // abs(account position) + qty <= AccountMaxContracts. Real time only: historical /
        // Analyzer fills are virtual and never reach the account. Same block in both files.
        // Known gap: two entries sent on the same bar both read the account before either
        // fills, so each is clamped against the pre-fill position only.
        private const int AccountMaxContracts = 40;

        /// <summary>The entry quantity after the shared rail; 0 = skip (reason printed).
        /// If the account cannot be read the entry is skipped: an unknown exposure never
        /// passes the rail.</summary>
        private int RailClamp(int q)
        {
            if (q <= 0) return q;
            int net = 0;
            try
            {
                string inst = Instrument != null ? Instrument.FullName : "";
                lock (Account.Positions)
                    foreach (Position p in Account.Positions)
                    {
                        if (p == null || p.Instrument == null || p.Instrument.FullName != inst) continue;
                        if (p.MarketPosition == MarketPosition.Long)       net += p.Quantity;
                        else if (p.MarketPosition == MarketPosition.Short) net -= p.Quantity;
                    }
            }
            catch (Exception ex)
            {
                Print(Name + " account rail: cannot read the account position (" + ex.Message
                      + ") -> entry of " + q + " SKIPPED");
                return 0;
            }
            int room = AccountMaxContracts - Math.Abs(net);
            if (room <= 0)
            {
                Print(Name + " account rail: account holds " + net + " on " + Instrument.FullName
                      + ", max " + AccountMaxContracts + " -> entry of " + q + " SKIPPED");
                return 0;
            }
            if (q > room)
            {
                Print(Name + " account rail: account holds " + net + ", max " + AccountMaxContracts
                      + " -> entry clamped " + q + " -> " + room);
                return room;
            }
            return q;
        }

        // ── ledger plumbing ──────────────────────────────────────────────────
        private const string LEDGER_PATH   = @"C:\EdgeLog\noise545k_decisions.csv";
        private const string LEDGER_HEADER = "ts_utc,strategy,leg,nt_bar_time,state,outcome,"
            + "http_status,prob,threshold,take,size,bars,bar_minutes,q_intended,q_ordered,"
            + "qty_base,max_contracts,latency_ms,fallback,reason";

        /// <summary>Append one row for one entry opportunity. Never throws — a ledger that
        /// cannot be written must not take down a live strategy; it complains to the output
        /// window and the trade goes on exactly as it would have.
        ///
        /// HOW TO READ A ROW. `outcome` describes what happened to the GATE, `q_ordered`
        /// what happened to the ORDER, and the two are deliberately independent:
        ///   ORDERED          asked, approved, entered at q_ordered
        ///   SKIPPED_BY_GATE  asked, refused, q_ordered 0
        ///   FAIL_OPEN        asked, no usable answer, entered ungated at q_ordered
        ///   NOT_ASKED        never asked — `reason` says why, and q_ordered says whether
        ///                    the strategy entered anyway (it does when the gate is simply
        ///                    switched off, it does not when a veto cancelled the entry)
        /// `nt_bar_time` is the OPEN stamp of the bar the decision was made on — the same
        /// string sent to the service as &amp;bar=, and the same convention the engine's own
        /// trade times use, so a ledger row joins to an engine trade without arithmetic.
        /// Empty cells mean NOT MEASURED. Never read one as a zero.</summary>
        private void Ledger(GateAnswer a, DateTime barTime, int qOrdered)
        {
            try
            {
                // The Strategy Analyzer is excluded on purpose: one optimize would run this
                // millions of times, and the contract is that Analyzer behaviour does not
                // change. A backtest's evidence is its blotter, not this file.
                if (IsInStrategyAnalyzer || a == null) return;
                // HISTORICAL BARS CARRY NO INFORMATION HERE and actively poison the audit.
                // A historical bar never asks the gate, so the row says only what the state
                // column already implies -- but there are thousands of them across a loaded
                // chart, they are rewritten on every enable / data reload / NT restart, and
                // a midday enable replays TODAY's bars with today's stamps, so they land in
                // today's audit rather than in backfill.
                if (State != State.Realtime) return;

                var inv = System.Globalization.CultureInfo.InvariantCulture;
                string dir = System.IO.Path.GetDirectoryName(LEDGER_PATH);
                if (!System.IO.Directory.Exists(dir)) System.IO.Directory.CreateDirectory(dir);

                var sb = new System.Text.StringBuilder();
                if (!System.IO.File.Exists(LEDGER_PATH)) sb.AppendLine(LEDGER_HEADER);
                sb.AppendLine(string.Join(",", new string[] {
                    IsoUtc(DateTime.UtcNow),
                    "EdgeLogNOISE545K",
                    Csv("NOISE_545_K12"),           // the paper leg key, fixed
                    Iso(barTime),
                    State.ToString(),
                    Csv(a.Outcome),
                    F(a.HttpStatus),
                    F(a.Prob, "0.####"),
                    F(a.Threshold, "0.####"),
                    Flag(a.TakeFlag),
                    F(a.Size, "0.###"),
                    F(a.Bars),
                    F(a.BarMinutes),
                    F(a.QIntended),
                    qOrdered.ToString(inv),
                    Qty.ToString(inv),
                    // The value the SERVICE served, empty when it served none -- not the
                    // cap this strategy went on to enforce. Writing the enforced cap made
                    // the audit's "did an order exceed the served ceiling" check impossible
                    // to fail, since ApplyCap has already guaranteed it cannot. The enforced
                    // cap is still recoverable from q_intended != q_ordered.
                    F(a.ServedMax > 0 ? a.ServedMax : -1),
                    F(a.LatencyMs),
                    Flag(a.FallbackFlag),
                    Csv(a.Reason)
                }));
                string row = sb.ToString();
                // Retried, not slept on: the ORB leg is meant to share this file, and two
                // processes appending in the same second is an IOException, not a bug. Three
                // immediate attempts costs microseconds and is the difference between a lost
                // row and a complete one. A live strategy never blocks on a log.
                for (int attempt = 0; attempt < 3; attempt++)
                {
                    try { System.IO.File.AppendAllText(LEDGER_PATH, row); return; }
                    catch (System.IO.IOException) { }
                }
                Print("EdgeLogNOISE545K ledger: row lost, file busy -> " + LEDGER_PATH);
            }
            catch (Exception ex)
            {
                Print("EdgeLogNOISE545K ledger: write failed: " + ex.Message);
            }
        }

        /// <summary>At most one row per session, for the days on which no entry check can
        /// happen at all. WHY IT EXISTS: a strategy that is not warm produces no bands, so
        /// no signal, so a per-opportunity ledger would record NOTHING on exactly the day
        /// the owner most needs a record — 2026-08-24, enabled and silent, which a chart
        /// loading too few days will reproduce every time. Realtime only: during historical
        /// warm-up "not warm" is the normal state and a row per replayed session is noise.</summary>
        private void LedgerSessionOnce(string reason, DateTime barTime)
        {
            if (State != State.Realtime) return;
            if (ledgerSessionDay == barTime.Date) return;
            ledgerSessionDay = barTime.Date;
            Ledger(NotAsked(reason, 0), barTime, 0);
        }

        /// <summary>The OPEN stamp of the bar that just closed. NinjaTrader hands us the
        /// close stamp; the engine and the gate service both index bars by their open, so
        /// everything that leaves this file is converted once, here.</summary>
        private DateTime BarOpenTime()
        {
            try
            {
                if (BarsPeriod != null && BarsPeriod.BarsPeriodType == BarsPeriodType.Minute
                    && BarsPeriod.Value > 0)
                    return Time[0].AddMinutes(-BarsPeriod.Value);
            }
            catch { }
            return Time[0];
        }

        /// <summary>The leg name out of the gate URL — the key the service and the audit
        /// both file this decision under. Empty rather than a guess if it is not there.</summary>
        private string LegKey()
        {
            try
            {
                string u = GateUrl == null ? "" : GateUrl;
                int i = u.IndexOf("leg=");
                if (i < 0) return "";
                int j = i + 4, k = j;
                while (k < u.Length && u[k] != '&') k++;
                return u.Substring(j, k - j);
            }
            catch { return ""; }
        }

        /// <summary>The raw token after "key": in a flat JSON body, or null when the key is
        /// not in the body AT ALL. Deliberately dumb — the service's JSON is flat and ours —
        /// but unlike the old inline search it can tell "absent" from "false", which is the
        /// whole difference between failing open and failing closed.</summary>
        private static string JsonRaw(string body, string key)
        {
            if (body == null) return null;
            int i = body.IndexOf("\"" + key + "\"");
            if (i < 0) return null;
            int c = body.IndexOf(':', i);
            if (c < 0) return null;
            int j = c + 1;
            while (j < body.Length && char.IsWhiteSpace(body[j])) j++;
            if (j < body.Length && body[j] == '"')
            {
                j++;
                int e = j;
                while (e < body.Length && body[e] != '"') e++;
                return body.Substring(j, e - j);
            }
            int k = j;
            while (k < body.Length && body[k] != ',' && body[k] != '}' && body[k] != ']'
                   && body[k] != '\r' && body[k] != '\n') k++;
            string s = body.Substring(j, k - j).Trim();
            if (s.Length == 0 || s == "null") return null;
            return s;
        }

        /// <summary>A number from the body. False = the field was absent or unreadable, and
        /// the caller leaves its slot NaN so the ledger writes it EMPTY.</summary>
        private static bool JsonNum(string body, string key, out double val)
        {
            val = double.NaN;
            string s = JsonRaw(body, key);
            if (s == null) return false;
            return double.TryParse(s, System.Globalization.NumberStyles.Float,
                                   System.Globalization.CultureInfo.InvariantCulture, out val);
        }

        /// <summary>ISO-8601 with NinjaTrader's own display offset, invariant. Never throws.
        /// NOT TimeZoneInfo.Local: bar times come back in the zone set under Tools > Options >
        /// General, which is independent of the OS zone. If those two diverge, every stamp
        /// here is off by a constant, the service's bar interlock mismatches on every single
        /// request, and the gate degrades to permanently ungated -- safely, but silently.</summary>
        private static string Iso(DateTime t)
        {
            try
            {
                var inv = System.Globalization.CultureInfo.InvariantCulture;
                TimeZoneInfo tz = null;
                try { tz = NinjaTrader.Core.Globals.GeneralOptions.TimeZoneInfo; }
                catch { }
                if (tz == null) tz = TimeZoneInfo.Local;
                TimeSpan off = tz.GetUtcOffset(
                                   DateTime.SpecifyKind(t, DateTimeKind.Unspecified));
                return t.ToString("yyyy-MM-dd'T'HH:mm:ss", inv)
                     + (off.Ticks < 0 ? "-" : "+")
                     + Math.Abs(off.Hours).ToString("00", inv) + ":"
                     + Math.Abs(off.Minutes).ToString("00", inv);
            }
            catch { return t.ToString("yyyy-MM-dd'T'HH:mm:ss"); }
        }

        private static string IsoUtc(DateTime t)
        {
            try
            {
                return t.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'",
                    System.Globalization.CultureInfo.InvariantCulture);
            }
            catch { return ""; }
        }

        /// <summary>NaN = nobody measured it = an EMPTY cell. Writing 0.0 instead would be
        /// a fabricated probability, and the audit cannot tell a fabricated one apart.</summary>
        private static string F(double v, string fmt)
        {
            if (double.IsNaN(v) || double.IsInfinity(v)) return "";
            return v.ToString(fmt, System.Globalization.CultureInfo.InvariantCulture);
        }

        /// <summary>Negative = never measured = an EMPTY cell, same rule.</summary>
        private static string F(int v)
        {
            return v < 0 ? "" : v.ToString(System.Globalization.CultureInfo.InvariantCulture);
        }

        /// <summary>Three states, not two: true, false, and nobody asked.</summary>
        private static string Flag(int f)
        {
            return f < 0 ? "" : (f == 1 ? "true" : "false");
        }

        /// <summary>Keep one field on one line in one cell. Substituting is enough here —
        /// none of these fields legitimately contains a comma — and it beats quoting rules
        /// that a hand-rolled reader on the other side would have to get right.</summary>
        private static string Csv(string s)
        {
            if (s == null) return "";
            return s.Replace(',', ';').Replace('"', '\'').Replace('\r', ' ').Replace('\n', ' ');
        }

        /// <summary>Exits must name no entry signal on an ADOPTED position: it has none, and
        /// NinjaTrader silently ignores an exit tied to one (ENGU-Q, live 2026-08-25).</summary>
        private string FromSig { get { return adopted ? "" : "N6"; } }

        /// <summary>Persist the open trade (or flat) so a restart can resume it. Real time
        /// only -- the historical pass rebuilds trades from scratch and must never overwrite
        /// a live trade's file (ENGU-Q lost one that way on 2026-08-19). Never throws.</summary>
        private void SaveState(bool inPos)
        {
            if (State != State.Realtime) return;
            try
            {
                var ci = System.Globalization.CultureInfo.InvariantCulture;
                string inst = Instrument != null ? Instrument.FullName : "";
                string json = "{"
                    + "\"inPos\":" + (inPos ? "true" : "false")
                    + ",\"dir\":" + (inPos ? lastDir : 0).ToString(ci)
                    + ",\"qty\":" + (inPos ? Position.Quantity : 0).ToString(ci)
                    + ",\"avg\":" + (inPos ? Position.AveragePrice : 0.0).ToString("R", ci)
                    + ",\"stop\":" + (inPos && !double.IsNaN(stopLevel) ? stopLevel : 0.0).ToString("R", ci)
                    + ",\"instrument\":\"" + inst + "\""
                    + ",\"saved_utc\":\"" + DateTime.UtcNow.ToString("yyyy-MM-dd HH:mm:ss", ci) + "\""
                    + "}";
                System.IO.File.WriteAllText(StateFile, json);
                savedInPos = inPos;
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
                return double.Parse(js.Substring(i, j - i), System.Globalization.CultureInfo.InvariantCulture);
            }
            catch { return dflt; }
        }

        private static bool JsonHas(string js, string key, string val)
        {
            return js.IndexOf("\"" + key + "\":" + val) >= 0
                || js.IndexOf("\"" + key + "\":\"" + val + "\"") >= 0;
        }

        /// <summary>On the first live bar: if the account holds a position, take it back only
        /// when it is this strategy's own saved trade (same contract, side and size, a stop on
        /// file); otherwise leave it alone. Starting flat clears a stale file. Never throws.</summary>
        private void RestoreState()
        {
            if (stateChecked) return;
            stateChecked = true;
            // Only an ADOPT start hands this strategy the account's position. Under WaitUntilFlat
            // Position is the historical pass's virtual trade, which must never get a real stop,
            // and says nothing about the account -- so the file is left exactly as it is.
            if (StartBehavior != StartBehavior.AdoptAccountPosition) return;
            try
            {
                string js = System.IO.File.Exists(StateFile) ? System.IO.File.ReadAllText(StateFile) : "";
                if (Position.MarketPosition == MarketPosition.Flat)
                {
                    stopPlaced = false; stopLevel = double.NaN;
                    if (JsonHas(js, "inPos", "true"))
                    { SaveState(false); Print("NOISE545K resume: starting flat, so the saved trade is stale - cleared"); }
                    else savedInPos = false;
                    return;
                }
                int dir = Position.MarketPosition == MarketPosition.Long ? 1 : -1;
                string inst = Instrument != null ? Instrument.FullName : "";
                double sDir = JsonNum(js, "dir", double.NaN), sQty = JsonNum(js, "qty", double.NaN);
                double sStop = JsonNum(js, "stop", double.NaN), sAvg = JsonNum(js, "avg", double.NaN);
                string why = js.Length == 0 ? "there is no saved trade"
                    : !JsonHas(js, "inPos", "true") ? "the saved trade says flat"
                    : !JsonHas(js, "instrument", inst) ? "the saved trade is for a different contract"
                    : (int)sDir != dir ? "the saved trade is on the other side"
                    : double.IsNaN(sQty) || (int)sQty != Position.Quantity
                        ? "the account holds " + Position.Quantity + " but the saved trade is " + (double.IsNaN(sQty) ? "unknown" : ((int)sQty).ToString())
                    : double.IsNaN(sAvg) || Math.Abs(sAvg - Position.AveragePrice) > TickSize / 2
                        ? "the account's average price " + Position.AveragePrice.ToString("F2") + " is not the saved trade's " + (double.IsNaN(sAvg) ? "unknown" : sAvg.ToString("F2"))
                    : double.IsNaN(sStop) || sStop <= 0 ? "the saved trade has no stop"
                    : null;
                if (why != null)
                {
                    foreign = true;
                    Print("NOISE545K resume: account is " + Position.MarketPosition + " " + Position.Quantity + " but " + why
                        + " - this position is not mine, NOT managing it (no stop, no exit, no entry)");
                    return;
                }
                adopted = true; lastDir = dir; stopLevel = sStop; stopPlaced = true; savedInPos = true;
                double px = Instrument.MasterInstrument.RoundToTickSize(stopLevel);
                Order mine = dir > 0 ? ExitLongStopMarket(0, true, Position.Quantity, px, "N6stop", "")
                                     : ExitShortStopMarket(0, true, Position.Quantity, px, "N6stop", "");
                Print("NOISE545K resume: adopted the open trade - " + Position.MarketPosition + " " + Position.Quantity
                    + " @ " + Position.AveragePrice.ToString("F2") + ", stop " + px.ToString("F2"));
                CancelStaleStops(mine, dir);
            }
            catch (Exception ex) { foreign = true; Print("NOISE545K resume failed, NOT managing the position: " + ex.Message); }
        }

        /// <summary>Remember the stops a dead instance left resting at the broker (its GTC
        /// NZstop survives a disable); they are cancelled in OnOrderUpdate only once our own
        /// stop is ACCEPTED, so the trade is never without one, and never with two (two stops
        /// for one position can fill twice and flip it). Never throws.</summary>
        private void CancelStaleStops(Order mine, int dir)
        {
            try
            {
                if (mine == null || Account == null) { Print("NOISE545K resume: own stop not confirmed - leaving any older stop in place"); return; }
                string inst = Instrument != null ? Instrument.FullName : "";
                OrderAction closing = dir > 0 ? OrderAction.Sell : OrderAction.BuyToCover;
                var stale = new List<Order>();
                lock (Account.Orders)
                    foreach (Order o in Account.Orders)
                    {
                        if (o == null || o == mine || Orders.Contains(o)) continue;
                        if (o.Instrument == null || o.Instrument.FullName != inst) continue;
                        if (o.OrderAction != closing && !(dir < 0 && o.OrderAction == OrderAction.Buy)) continue;
                        if (o.OrderType != OrderType.StopMarket && o.OrderType != OrderType.StopLimit) continue;
                        if (o.OrderState != OrderState.Working && o.OrderState != OrderState.Accepted
                            && o.OrderState != OrderState.TriggerPending) continue;
                        stale.Add(o);
                    }
                if (stale.Count == 0) return;
                foreach (Order o in stale)
                    Print("NOISE545K resume: stop left by the previous instance - " + o.Name + " qty " + o.Quantity
                        + " @ " + o.StopPrice.ToString("F2") + " - will cancel once our own stop is accepted");
                adoptStop = mine;
                staleStops = stale;
            }
            catch (Exception ex) { Print("NOISE545K resume: stale-stop cleanup failed: " + ex.Message); }
        }

        protected override void OnOrderUpdate(Order order, double limitPrice, double stopPrice,
            int quantity, int filled, double averageFillPrice, OrderState orderState,
            DateTime time, ErrorCode error, string comment)
        {
            try
            {
                if (staleStops == null || adoptStop == null || order == null) return;
                if (order != adoptStop && !(order.Name == "N6stop" && Orders.Contains(order))) return;
                if (orderState == OrderState.Accepted || orderState == OrderState.Working
                    || orderState == OrderState.TriggerPending)
                {
                    var cancel = new List<Order>();
                    foreach (Order o in staleStops)
                        if (o.OrderState == OrderState.Working || o.OrderState == OrderState.Accepted
                            || o.OrderState == OrderState.TriggerPending) cancel.Add(o);
                    staleStops = null; adoptStop = null;
                    if (cancel.Count == 0) return;
                    Print("NOISE545K resume: own stop accepted - cancelling " + cancel.Count + " stop(s) left by the previous instance");
                    Account.Cancel(cancel);
                }
                else if (orderState == OrderState.Rejected || orderState == OrderState.Cancelled)
                {
                    Print("NOISE545K resume: own stop " + orderState + " - KEEPING the previous instance's stop");
                    staleStops = null; adoptStop = null;
                }
            }
            catch (Exception ex) { Print("NOISE545K resume: OnOrderUpdate failed: " + ex.Message); }
        }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name        = "EdgeLogNOISE545K";
                Description = "EDGELOG NOISE 1.0 - intraday noise-band momentum, close signal / next-open fill";
                Calculate   = Calculate.OnBarClose;      // every decision is a bar-close decision
                EntriesPerDirection = 1;
                EntryHandling = EntryHandling.AllEntries;
                IsExitOnSessionCloseStrategy = true;     // engine is flat every session close
                ExitOnSessionCloseSeconds = 30;
                IsInstantiatedOnEachOptimizationIteration = false;
                StartBehavior = StartBehavior.WaitUntilFlat;
                // Lets the watchdog start NOISE with StartBehavior=AdoptAccountPosition when the
                // account holds NOISE's own saved trade (RestoreState). The default stays
                // WaitUntilFlat, so nothing changes until the watchdog chooses to adopt.
                IsAdoptAccountPositionAware = true;
                BarsRequiredToTrade = 20;

                // Defaults moved to the #231 crowned config on 2026-08-16 (three
                // consecutive auto-validates landed on this identical dict). The old
                // hand-built 14 / 1.5 / 1.5 / 1.0 stays available by typing it in.
                // NOISE_1_8_CT304H.py _FROZEN, py 62-68 (run #304 champion core, #422 leg).
                Lookback       = 40;                    // py 63 "lookback": 40
                BandMultLong   = 0.75;
                BandMultShort  = 1.5;
                StopK          = 1.75;
                UseStop        = true;
                // Short Veto (run #241, crowned 2026-08-21): default OFF so a rebuild
                // changes nothing until the knob is deliberately flipped on the
                // strategy row (bridge /strategy/check pre-flights it first).
                SkipBotShort   = true;                  // py 66 daytype_mode skip_bot_short
                DaytypeLo      = 0.20;                  // py 66 daytype_lo 0.2
                // Volatility skip (run #243, crowned 2026-08-23): default OFF for the
                // same reason -- a rebuild changes nothing until the knob is
                // deliberately flipped on the strategy row after an NT restart.
                VolSkipOn      = true;                  // py 67 vol_skip_pct 95.0 (always on)
                VolSkipPct     = 95.0;
                HistFills      = false;
                // 3 = tools/nt_fill_reconcile.py SPEC["NOISE"] contracts per book unit.
                Qty            = 3;
                // KEEL v12 sizing (api/gate_live.py /keel). On by default: this leg IS the KEEL leg.
                // Off = the squeeze tilt alone (the run's file without KEEL), never a skipped trade.
                GateEnabled    = true;
                GateUrl        = "http://127.0.0.1:8392/keel?leg=NOISE_545_K12";
                GateTimeoutMs  = 300;
                // 0 = "use 3 x Quantity", the cap this file has always applied. Default so
                // that a rebuild against a service that serves no max_contracts orders
                // exactly what it ordered yesterday.
                MaxContracts   = 0;
                // Hourly squeeze tilt, run #545 set 1 (api/paper.py NOISE_545_K12 params, from the run
                // doc's best_params); frame frozen at 60 min (NOISE_1_8_CT304H.py py 93 _GATE_TF_MIN = 60).
                SqueezeLen     = 16;                    // run #545 best_params gate_len 16 (CT304H py 154 comp)
                SqueezeRatio   = 1.15;                  // run #545 best_params gate_ratio 1.15
                TiltMult       = 2.75;                  // run #545 best_params tilt_mult 2.75 (KFX py 93: tilt_mult if on)
            }
            else if (State == State.DataLoaded)
            {
                adCurrent = new List<double>();
                history   = new List<double[]>();
                volHist   = new List<double>();
                sqH = new List<double>(); sqL = new List<double>(); sqC = new List<double>();
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
                                        "EdgeLogNOISE545K_" + stamp + ".csv");

                var sb = new System.Text.StringBuilder();
                // Header carries the run config. The reconcile side asserts on these
                // instead of trusting that the right thing was selected in the UI.
                sb.AppendLine("# strategy=EdgeLogNOISE545K");
                sb.AppendLine("# instrument=" + instrument);
                sb.AppendLine("# bars=" + period);
                sb.AppendLine("# trading_hours=" + hours);
                sb.AppendLine("# lookback=" + Lookback + " bandLong=" + BandMultLong
                              + " bandShort=" + BandMultShort + " useStop=" + UseStop
                              + " stopK=" + StopK + " qty=" + Qty
                              + " skipBotShort=" + SkipBotShort + " daytypeLo=" + DaytypeLo
                              + " volSkipOn=" + VolSkipOn + " volSkipPct=" + VolSkipPct
                              + " squeezeLen=" + SqueezeLen + " squeezeRatio=" + SqueezeRatio
                              + " tiltMult=" + TiltMult + " keel=" + (GateEnabled ? GateUrl : "off"));
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
                Print("EdgeLogNOISE545K: wrote " + n + " trades -> " + path);
            }
            catch (Exception ex)
            {
                Print("EdgeLogNOISE545K: blotter dump failed: " + ex.Message);
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
                    Print("EdgeLogNOISE545K short veto: prior close position "
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
                        Print("EdgeLogNOISE545K vol skip: prior session range percentile "
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
            sqSessStart = BarOpenTime();     // SQ py 131: buckets are offsets from the session's FIRST bar
            sqBucket = -1;                   // SQ py 148: a verification bar never spans two sessions
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
                System.IO.File.WriteAllText(@"C:\EdgeLog\noise545k_warmup.txt",
                    DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")
                    + "  sessions_banked=" + history.Count
                    + "  lookback=" + Lookback
                    + "  warm=" + (history.Count >= Lookback)
                    + "  bars_loaded=" + (Bars != null ? Bars.Count : 0)
                    + "  state=" + State);
            }
            catch { }
        }

        // ── hourly squeeze (the #422 size tilt) ─────────────────────────────
        // Built from THIS chart's 5-minute bars, not from an AddDataSeries hourly series, because
        // the engine's hourly bar is NOT a clock hour: NOISE_1_1_SBS_V90_SQ._compression buckets
        // base bars by minutes since the SESSION'S FIRST BAR // 60 (SQ py 131-133), keyed by day
        // so a bucket never spans sessions (SQ py 148) -- 09:30-10:30 ... 15:30-16:00 (a 30-min
        // last bucket). A secondary series would also update AFTER the primary on a shared close
        // stamp, i.e. one bar late on exactly the bars that complete an hour.
        private const int SqueezeTfMin = 60;          // NOISE_1_8_CT304H.py py 93 _GATE_TF_MIN
        private List<double> sqH, sqL, sqC;          // completed hourly bars (capped, see below)
        private int      sqDone;                     // completed hourly bars ever (the .py's j + 1)
        private DateTime sqSessStart;
        private int      sqBucket = -1;
        private bool     sqOpen;                     // a bucket is being built and not yet banked
        private double   sqHiCur, sqLoCur, sqCCur;
        private bool     sqCompressed;               // comp[] as of the last COMPLETE hourly bar
        private double   sqRatio = double.NaN;

        private void SqueezeBar(DateTime openT, bool lastOfSession)
        {
            int barMin = (BarsPeriod != null && BarsPeriod.BarsPeriodType == BarsPeriodType.Minute
                          && BarsPeriod.Value > 0) ? BarsPeriod.Value : 5;
            int off = (int)Math.Floor((openT - sqSessStart).TotalMinutes);
            if (off < 0) off = 0;
            int b = off / SqueezeTfMin;                                   // SQ py 133
            if (b != sqBucket)
            {
                // A data gap skipped the bar that would have closed the previous bucket: bank it now.
                // The .py marks it complete at its own last bar (SQ py 153, 170); here that is one
                // bar late, only ever on a gap.
                if (sqOpen) SqueezeBank();
                sqBucket = b; sqHiCur = High[0]; sqLoCur = Low[0]; sqOpen = true;
            }
            else
            {
                sqHiCur = Math.Max(sqHiCur, High[0]);                     // SQ py 154 max(highs)
                sqLoCur = Math.Min(sqLoCur, Low[0]);                      // SQ py 155 min(lows)
            }
            sqCCur = Close[0];                                            // SQ py 156 closes[ge]
            // SQ py 169-170: a verification bar is usable from its LAST base bar onward, so the
            // bar that completes an hour counts on that same bar's decision (no look-ahead: the
            // hour's last 5-min bar has closed). Last bar = next bar is another bucket or session.
            if (lastOfSession || (off + barMin) / SqueezeTfMin != b) SqueezeBank();
        }

        private void SqueezeBank()
        {
            sqOpen = false;
            sqH.Add(sqHiCur); sqL.Add(sqLoCur); sqC.Add(sqCCur);
            sqDone++;
            while (sqC.Count > 200) { sqH.RemoveAt(0); sqL.RemoveAt(0); sqC.RemoveAt(0); }
            int L = SqueezeLen;
            int n = sqC.Count;
            sqRatio = double.NaN;
            sqCompressed = false;
            // SQ py 167, 171: warm = L*2 + 5; usable only when j >= warm (j = sqDone - 1).
            if (sqDone - 1 < L * 2 + 5 || n < L + 1) return;
            // SQ py 160: dev = rolling(L).std(ddof=0) of the hourly closes.
            double mean = 0;
            for (int i = n - L; i < n; i++) mean += sqC[i];
            mean /= L;
            double v = 0;
            for (int i = n - L; i < n; i++) v += (sqC[i] - mean) * (sqC[i] - mean);
            double dev = Math.Sqrt(v / L);
            // SQ py 161-163: TR = max(h-l, |h-prevC|, |l-prevC|), prevC = the PRIOR hourly close
            // (across sessions too); atr = rolling(L).mean() -- a simple mean, not Wilder.
            double atr = 0;
            for (int i = n - L; i < n; i++)
            {
                double pc = sqC[i - 1];
                atr += Math.Max(sqH[i] - sqL[i], Math.Max(Math.Abs(sqH[i] - pc), Math.Abs(sqL[i] - pc)));
            }
            atr /= L;
            // SQ py 165: ratio = (2.0 * dev) / (1.5 * atr)  (Carter 2.0 BB / 1.5 KC).
            double ratio = atr > 0 ? (2.0 * dev) / (1.5 * atr) : double.NaN;
            sqRatio = ratio;
            // SQ py 175: compressed = ratio <= gate_ratio (NaN -> false).
            sqCompressed = !double.IsNaN(ratio) && ratio <= SqueezeRatio;
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
            if (State == State.Realtime) RestoreState();

            if (Bars.IsFirstBarOfSession)
            {
                RollSession();
                sessionValid = true;
            }
            if (!sessionValid)
            {
                // Enabled mid-session: no clean session open, so not one entry check will
                // happen today. Logged once, because "enabled and silent all day" is the
                // exact state that used to leave no trace at all (2026-08-24). The contract's
                // reason list has no token for a mid-session start; not_warm is the closest
                // true statement -- this instance is not in a state where it can evaluate an
                // entry -- and the row's own timestamp shows it started mid-session.
                LedgerSessionOnce("not_warm", BarOpenTime());
                prevSessionClose = Close[0]; return;   // enabled mid-session: wait for a clean open
            }

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
            SqueezeBar(BarOpenTime(), Bars.IsLastBarOfSession);   // before any entry decision on this bar

            double sig = Sigma(barOfDay);
            double ub = double.NaN, lb = double.NaN;
            if (!double.IsNaN(sig))
            {
                ub = refHi * (1.0 + BandMultLong * sig);
                lb = refLo * (1.0 - BandMultShort * sig);
            }

            bool warm = history.Count >= Lookback;
            bool lastBar = Bars.IsLastBarOfSession;
            bool bandsOk = warm && !double.IsNaN(ub) && !double.IsNaN(lb);
            DateTime barTime = BarOpenTime();

            // ── in a position ───────────────────────────────────────────────
            if (Position.MarketPosition != MarketPosition.Flat && foreign)
            {
                // Not our trade (RestoreState): no stop, no exit, no entry -- the watchdog holds it
                // for a person. Bookkeeping only, so the bands are right once the account is flat.
                barOfDay++;
                prevSessionClose = Close[0];
                return;
            }
            if (Position.MarketPosition != MarketPosition.Flat)
            {
                lastDir = Position.MarketPosition == MarketPosition.Long ? 1 : -1;
                // The contracts actually ON, which is NOT Qty: the gate sizes the entry, so
                // at the live Qty=3 an accepted trade is 9 micros. Every exit in this block
                // used to pass the literal Qty, which protected 3 of those 9 and left the
                // other 6 naked with no stop and no VWAP exit -- the position could only be
                // closed by the session-close flattener. Position.Quantity appeared nowhere
                // in this file before 2026-08-26.
                int posQty = Position.Quantity;

                // Protective stop, sized from THIS bar's band excursion, placed once.
                // It goes live for the next bar — the engine likewise never tests the
                // stop on the entry bar itself.
                if (UseStop && !stopPlaced && posQty > 0 && !double.IsNaN(ub) && !double.IsNaN(lb))
                {
                    double fill = Position.AveragePrice;      // anchor on the actual fill
                    stopLevel = lastDir > 0 ? fill - StopK * (ub - refHi)
                                            : fill + StopK * (refLo - lb);
                    if (!double.IsNaN(stopLevel))
                    {
                        double px = Instrument.MasterInstrument.RoundToTickSize(stopLevel);
                        if (lastDir > 0) ExitLongStopMarket(0, true, posQty, px, "N6stop", FromSig);
                        else             ExitShortStopMarket(0, true, posQty, px, "N6stop", FromSig);
                        stopPlaced = true;
                        SaveState(true);
                    }
                }

                // VWAP mean-reversion exit, decided at this close, filled next open.
                if (!double.IsNaN(vwap) && !lastBar && posQty > 0)
                {
                    bool trig = (lastDir > 0 && Close[0] < vwap) || (lastDir < 0 && Close[0] > vwap);
                    if (trig)
                    {
                        if (lastDir > 0) ExitLong(posQty, "N6exit", FromSig);
                        else             ExitShort(posQty, "N6exit", FromSig);
                        stopPlaced = false; stopLevel = double.NaN;
                    }
                }
                // A band break while already holding is still an entry opportunity that came
                // and went, and the ledger has to be able to say so -- otherwise the day's
                // signal count in this file does not match the day's signal count anywhere
                // else, and the difference looks like a missing call rather than a full book.
                if (bandsOk && (Close[0] > ub || Close[0] < lb))
                    Ledger(NotAsked("in_position", 0), barTime, 0);
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
            adopted = false; foreign = false;
            if (savedInPos) SaveState(false);

            // ── flat: look for a band-break entry at this bar's close ────────
            // Skipped on the session's first bar and on the session's LAST bar —
            // exactly the engine's `1 <= k <= m-2` rule (barOfDay>=1 covers the
            // low end, !lastBar the high end; session length is calendar
            // knowledge, not look-ahead). The old extra `Time[0] < sessionEnd
            // - 10min` guard blocked the final TWO signal bars the engine
            // allows (fills at 15:50/15:55): the 2026-08-24 crown parity run
            // showed every one of the engine's 5 unmatched late-day entries was
            // this guard, a systematic one-sided divergence — removed.
            //
            // The band-break test and the k-range test are now separate steps. Same
            // trades as before, in the same order, but a signal that arrives outside the
            // k range is now a ledger row instead of a silence.
            // ONE ROW A SESSION, UNCONDITIONALLY -- the heartbeat. Written on the first
            // real-time bar of every session whatever happens next, so an empty day is a
            // recorded fact rather than an empty file. Without it "the strategy ran and saw
            // nothing", "NinjaTrader was not running" and "the strategy was disabled" all
            // look identical from the audit's side, and that ambiguity is the whole reason
            // 2026-08-24 took a log grep to explain.
            LedgerSessionOnce(bandsOk ? "session_start" : "not_warm", barTime);
            if (!bandsOk)
            {
                // No noise estimate yet -> no bands -> not one signal all day. A chart loaded
                // with too few days reproduces this every day forever, so the reason matters.
            }
            else if (Close[0] > ub || Close[0] < lb)
            {
                bool longTrig  = Close[0] > ub;
                bool shortTrig = Close[0] < lb;
                if (barOfDay < 1 || lastBar)
                {
                    Ledger(NotAsked("entry_cutoff", 0), barTime, 0);
                }
                else
                {
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
                    if (!longTrig && !shortTrig)
                    {
                        // A veto ate the only side that fired. no_signal_side is the
                        // belt-and-braces third case: it can only be reached if the triggers
                        // stop agreeing with the test above them, which is worth seeing.
                        string why = blockAllToday ? "vetoed_volskip"
                                   : (blockShortToday ? "vetoed_daytype" : "no_signal_side");
                        Ledger(NotAsked(why, 0), barTime, 0);
                    }
                    else
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
                        // HOURLY SQUEEZE TILT (NOISE_1_8_CT304H.py py 163-165): the decision bar is THIS
                        // bar (py 163 dec = fill - 1); on = comp[dec] (py 164); s = tilt_mult if on else
                        // 1.0 (py 165). NOISE_1_8_CT304H_KFX.py keeps that size and multiplies on top (see header).
                        bool on = sqCompressed;
                        double ctTilt = on ? TiltMult : 1.0;
                        if (on) Print("EdgeLogNOISE545K squeeze tilt: hourly ratio " + sqRatio.ToString("0.000")
                                      + " <= " + SqueezeRatio + " -> x" + TiltMult);
                        GateAnswer ans;
                        if (State == State.Realtime)
                            ans = GateEnabled ? AskKeel(barTime, ctTilt) : NotAsked("keel_disabled", BaseQ(ctTilt));
                        else
                            ans = NotAsked("not_realtime", (IsInStrategyAnalyzer || HistFills) ? BaseQ(ctTilt) : 0);
                        if (ans.Outcome == "NOT_ASKED" && ans.Q > 0) { ans.Size = ctTilt; ans.QIntended = ans.Q; }
                        ApplyCap(ans);
                        int q = ans.Q;
                        if (q > 0 && State == State.Realtime)
                        {
                            int railed = RailClamp(q);
                            if (railed != q && ans.Reason.Length == 0) ans.Reason = "account_rail";
                            q = railed;
                        }
                        if (q > 0)
                        {
                            if (longTrig) EnterLong(q, "N6");
                            else          EnterShort(q, "N6");
                        }
                        // Exactly one row, on every branch above, ordered or not. This is the
                        // line that answers "was the gate even asked for this trade?".
                        Ledger(ans, barTime, q);
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

        // The hard ceiling on one entry, used only when the service serves no
        // max_contracts of its own (an older gate_live.py, or a fail-open answer). 0 keeps
        // the cap this file always had, 3 x Quantity, so leaving it alone changes nothing.
        // Range top is deliberately far above any rail the bridge would set: an
        // out-of-range value does not warn, it silently finalizes the strategy with a
        // popup nobody sees on a headless restart.
        [NinjaScriptProperty, Range(0, 100)]
        [Display(Name = "Max contracts per entry (0 = 3x Quantity)", Order = 16, GroupName = "ML GATE")]
        public int MaxContracts { get; set; }

        // ── #545 hourly squeeze size tilt (NOISE_1_8_CT304H.py, via NOISE_1_8_CT304H_KFX.py) ──
        [NinjaScriptProperty, Range(16, 24)]
        [Display(Name = "Squeeze length (hourly bars)", Order = 20, GroupName = "SQUEEZE TILT")]
        public int SqueezeLen { get; set; }

        [NinjaScriptProperty, Range(0.5, 2.0)]
        [Display(Name = "Compression threshold (BB width / KC width)", Order = 21, GroupName = "SQUEEZE TILT")]
        public double SqueezeRatio { get; set; }

        [NinjaScriptProperty, Range(1.0, 2.0)]
        [Display(Name = "Size on compressed-hour trades (x Quantity)", Order = 22, GroupName = "SQUEEZE TILT")]
        public double TiltMult { get; set; }
        #endregion
    }
}
