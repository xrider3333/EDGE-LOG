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

        /// <summary>Ask the bouncer, and bring back everything the ledger needs.
        /// Never throws: every failure path leaves Q = Qty (fail-open).</summary>
        private GateAnswer AskGate(DateTime barTime)
        {
            GateAnswer a = new GateAnswer();
            a.Q = Qty;                                  // the answer if anything at all goes wrong
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
                string url = GateUrl + (GateUrl != null && GateUrl.IndexOf('?') >= 0 ? "&" : "?")
                           + "bar=" + Uri.EscapeDataString(Iso(barTime));
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

                // THE PARSER MUST NOT FAIL CLOSED. The old one searched for the literal
                // "take": true and treated its absence as a refusal, so a renamed field, a
                // proxy error page or a truncated body would have silently stopped this leg
                // trading and looked exactly like a market with no signals. A body we cannot
                // read is a FAILURE, and every failure here trades ungated at Qty.
                string takeRaw = JsonRaw(body, "take");
                bool take = false;
                if (takeRaw == "true") take = true;
                else if (takeRaw != "false")
                {
                    a.Outcome = "FAIL_OPEN"; a.Reason = "parse_fail"; a.Q = Qty;
                    Print("EdgeLogNOISE gate: PARSE FAIL (no usable \"take\") -> ungated at "
                          + Qty + " (" + body + ")");
                    return a;
                }
                a.TakeFlag = take ? 1 : 0;

                double d;
                if (JsonNum(body, "prob", out d))          a.Prob      = d;
                if (JsonNum(body, "threshold", out d))     a.Threshold = d;
                if (JsonNum(body, "size", out d))          a.Size      = d;
                if (JsonNum(body, "bars", out d))          a.Bars       = (int)d;
                if (JsonNum(body, "bar_minutes", out d))   a.BarMinutes = (int)d;
                if (JsonNum(body, "max_contracts", out d)) a.ServedMax  = (int)d;
                string fb = JsonRaw(body, "ungated_fallback");
                if (fb == "true") a.FallbackFlag = 1; else if (fb == "false") a.FallbackFlag = 0;
                // Did the interlock actually run? "absent" and "unparseable" both mean it did
                // not, and the service says so only in its own log -- so without this the
                // ledger records a perfectly ordinary approved trade on a request where the
                // one check that catches a wrong bar series was switched off.
                a.BarCheck = JsonRaw(body, "bar_check");

                if (a.FallbackFlag == 1)
                {
                    // The service replied, but it did not decide anything -- it fell back to
                    // ungated on purpose (no artifact, too little data, or the bar interlock
                    // above refusing a series it does not hold). Recording that as an ordinary
                    // TAKE would put a fabricated "the model approved this" in the ledger.
                    string err = JsonRaw(body, "error");
                    a.Outcome = "FAIL_OPEN";
                    a.Reason  = (err != null && err.IndexOf("bar mismatch") >= 0)
                                ? "bar_mismatch" : "service_fallback";
                    a.Q = Qty;
                    Print("EdgeLogNOISE gate: SERVICE FAIL-OPEN -> ungated at " + Qty + " (" + body + ")");
                    return a;
                }

                if (!take)
                {
                    a.Outcome = "SKIPPED_BY_GATE"; a.Q = 0; a.QIntended = 0;
                    Print("EdgeLogNOISE gate: SKIP (" + body + ")");
                    return a;
                }

                // Size lands on whole contracts. At Qty=1 (full NQ) this rounds nearly
                // everything to 1 -- effectively keep/skip; run Qty=10 on micros (MNQ)
                // to give the size dial real resolution.
                double size = double.IsNaN(a.Size) ? 1.0 : a.Size;
                int q = (int)Math.Round(size * Qty);
                if (q < 1) q = 1;                       // take=true never rounds to zero
                a.QIntended = q;                        // the model's number, before any rail
                a.Q = q;
                a.Outcome = "ORDERED";
                // An approved trade whose interlock never ran is still approved, but the
                // ledger has to say the check was not armed -- otherwise a disarmed interlock
                // is indistinguishable from a passing one.
                if (a.BarCheck != null)
                {
                    string bc = a.BarCheck.Replace("\"", "");
                    if (bc.Length > 0 && bc != "ok") a.Reason = "interlock_" + bc;
                }
                Print("EdgeLogNOISE gate: TAKE x" + size.ToString("0.00") + " -> " + q + " (" + body + ")");
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
                a.Q = Qty;
                Print("EdgeLogNOISE gate: FAIL-OPEN (" + a.Reason + ": " + wex.Message + ") -> " + Qty);
                return a;
            }
            catch (Exception ex)
            {
                a.LatencyMs = (int)(DateTime.UtcNow - t0).TotalMilliseconds;
                a.Outcome = "FAIL_OPEN";
                a.Reason  = (ex is System.IO.IOException) ? "timeout" : "http_error";
                a.Q = Qty;
                Print("EdgeLogNOISE gate: FAIL-OPEN (" + ex.Message + ") -> " + Qty);
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
                Print("EdgeLogNOISE gate: risk rail capped " + a.Q + " -> " + cap + " contracts");
                a.Q = cap;
            }
        }

        // ── ledger plumbing ──────────────────────────────────────────────────
        private const string LEDGER_PATH   = @"C:\EdgeLog\gate_decisions.csv";
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
                    "EdgeLogNOISE",
                    Csv(LegKey()),
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
                Print("EdgeLogNOISE ledger: row lost, file busy -> " + LEDGER_PATH);
            }
            catch (Exception ex)
            {
                Print("EdgeLogNOISE ledger: write failed: " + ex.Message);
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
                // 0 = "use 3 x Quantity", the cap this file has always applied. Default so
                // that a rebuild against a service that serves no max_contracts orders
                // exactly what it ordered yesterday.
                MaxContracts   = 0;
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
                        if (lastDir > 0) ExitLongStopMarket(0, true, posQty, px, "NZstop", "NZ");
                        else             ExitShortStopMarket(0, true, posQty, px, "NZstop", "NZ");
                        stopPlaced = true;
                    }
                }

                // VWAP mean-reversion exit, decided at this close, filled next open.
                if (!double.IsNaN(vwap) && !lastBar && posQty > 0)
                {
                    bool trig = (lastDir > 0 && Close[0] < vwap) || (lastDir < 0 && Close[0] > vwap);
                    if (trig)
                    {
                        if (lastDir > 0) ExitLong(posQty, "NZexit", "NZ");
                        else             ExitShort(posQty, "NZexit", "NZ");
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
                        GateAnswer ans;
                        if (State == State.Realtime)
                            ans = GateEnabled ? AskGate(barTime) : NotAsked("gate_disabled", Qty);
                        else
                            ans = NotAsked("not_realtime", (IsInStrategyAnalyzer || HistFills) ? Qty : 0);
                        ApplyCap(ans);
                        int q = ans.Q;
                        if (q > 0)
                        {
                            if (longTrig) EnterLong(q, "NZ");
                            else          EnterShort(q, "NZ");
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
        #endregion
    }
}
