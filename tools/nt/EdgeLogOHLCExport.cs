// ============================================================================
//  EdgeLogOHLCExport  —  NinjaTrader 8 Indicator        (v2 + replay sidecar, 2026-10-02)
//  Streams every CLOSED bar of the chart it is applied to (designed for a
//  10-SECOND chart of the ES / NQ front-month OUTRIGHT) to a CSV that EDGELOG's
//  watch-folder ingest turns into a master — OHLCV PLUS order-flow (delta /
//  buy / sell volume / tick count).
//
//  Companion to EdgeLogExport.cs (the fills AddOn): same C:\EdgeLog staging idea,
//  same append-only, resume-safe, fail-quiet design. An INDICATOR (not an AddOn)
//  because it needs the chart's bar series AND tick-by-tick market data for the
//  exact instrument + period it is dropped on.
//
//  WHAT IT WRITES  (one row per CLOSED bar):
//     time,open,high,low,close,volume,delta,buy_vol,sell_vol,tick_count,rt
//       time       = Unix seconds, UTC   (matches your TV / Yahoo / Databento masters)
//       open..close= the bar's OHLC
//       volume     = REAL contract volume of the bar (unlike Yahoo's intraday volume)
//       buy_vol    = volume classified as aggressive buying
//       sell_vol   = volume classified as aggressive selling
//       delta      = buy_vol - sell_vol   (net buy/sell PRESSURE for the bar)
//       tick_count = number of trades in the bar (intensity, not direction)
//       rt         = HOW THE ROW WAS BUILT  (v2 — was a 0/1 flag, old readers only ever
//                    tested 0 vs non-0, and nothing in EDGE-LOG filters on rt == 1):
//                      0 = HISTORICAL bar (OHLCV good; delta only with Tick Replay, and
//                          then by the TICK RULE only — history carries no bid/ask)
//                      1 = LIVE, every trade classified against a fresh bid/ask
//                      2 = LIVE, but >10% of the bar's volume had to use the tick rule
//                          (bid/ask missing/stale or trade inside the spread)
//                      3 = LIVE bar with volume but ZERO ticks seen by this indicator:
//                          delta/buy/sell = 0 are UNKNOWN, not a real zero.  This is the
//                          "dropout" state — before v2 it was indistinguishable from a
//                          quiet bar.
//     ( cumulative delta is intentionally NOT stored — derive it downstream as a
//       running sum of `delta`, so you control session resets. )
//
//  v2 CHANGES (see C:\EdgeLog\_nt_staging\EdgeLogOHLCExport.diff)
//    * WHY: the chart's OnMarketData subscription silently dies (bars keep closing with
//      real volume, tick_count = 0) after a provider resubscribe — the AddOn watchdog's
//      Restart() and NT feed reconnects both trigger it — and never comes back until NT
//      restarts.  A second subscription made directly on Instrument.MarketData.Update
//      (the path the headless AddOn uses, which never dropped out) now takes over when
//      the primary goes silent, and is re-subscribed by a 5 s watchdog.
//    * Quotes older than QuoteFreshSec are no longer trusted (stale bid/ask biased every
//      bar one-sided); trades at an unchanged price take the previous side instead of
//      being dropped (Tick Replay history classified only 67% of NQ / 10% of ES volume).
//    * Health lines go to C:\EdgeLog\ohlc\_export_<ROOT>.log.
//
//  REPLAY SIDECAR (v2.1, 2026-10-02 - additive, live rows are untouched):
//    When the hosting chart has TICK REPLAY on, the historical pass also collects one row per
//    historical bar, classified by EXACTLY the same Feed() code as live bars (same quote rule /
//    tick rule), with rt = 4 ("rebuilt from tick replay"), and writes them once - at the
//    Historical -> Realtime hand-over - to
//         C:\EdgeLog\ohlc\replay\<ROOT>_<PERIOD>_replay.csv      (same 11 columns)
//    The file is rewritten from scratch on every load (temp file, then an atomic move/replace).
//    The main <ROOT>_<PERIOD>.csv is NOT changed by this; tools/repair_10s_from_replay.py merges
//    the sidecar into it (rt=3 / zero-delta rows are rewritten, missing bars inserted).
//    History is classified with the bid/ask that Tick Replay attaches to every Last tick (e.Bid / e.Ask),
//    falling back to the tick rule exactly as live does (HistUseEventQuotes = false restores the old
//    tick-rule-only history, which also changes the rt=0 rows the historical pass writes to the main file).
//    A sidecar with no tick at all is NOT written (it would clobber a good one); the outcome and the
//    share of volume classified by quote vs tick rule go to _export_<ROOT>.log ("replay sidecar ...").
//
//  INSTALL (one time):
//    1. This file is already at
//         Documents\NinjaTrader 8\bin\Custom\Indicators\EdgeLogOHLCExport.cs
//    2. NinjaScript Editor → press F5 (Compile) → expect "Compile succeeded".
//    3. Open a chart of the FRONT-MONTH OUTRIGHT (e.g. "ES 09-26", NOT the
//       "ES ##-##" continuous). Outright = non-adjusted, so it carries roll gaps
//       overnight and lines up with your db_noadj / Yahoo =F masters at the seam.
//    4. Set the data series to 10 Second (right-click chart → Data Series →
//       Type = Second, Value = 10).
//    5. Right-click chart → Indicators → add "EdgeLogOHLCExport" → OK.
//    6. (Optional, for accurate HISTORICAL delta) in Data Series, tick
//       "Tick Replay". Without it, only live bars carry delta; backfilled bars
//       still get correct OHLCV.
//    Repeat 3-5 on an NQ 10s chart. Park both charts in a workspace that loads
//    when NinjaTrader starts → capture is hands-free.
//
//  OUTPUT:  C:\EdgeLog\ohlc\<ROOT>_<PERIOD>.csv   e.g. ES_10s.csv, NQ_10s.csv
//  EDGELOG then ingests these into 10s masters tagged 'nt_noadj', kept separate
//  from your tv / yahoo / db_noadj masters (instrument + timeframe + source key).
// ============================================================================
using System;
using System.IO;
using System.Text;
using System.Collections.Generic;
using System.Globalization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;

namespace NinjaTrader.NinjaScript.Indicators
{
    public class EdgeLogOHLCExport : Indicator
    {
        // Change this if you keep EdgeLog elsewhere. Mirrors C:\EdgeLog\fills.csv.
        private const string OutDir = @"C:\EdgeLog\ohlc";
        private const string Header =
            "time,open,high,low,close,volume,delta,buy_vol,sell_vol,tick_count,rt\n";

        // v2 tunables
        private const double QuoteFreshSec = 15.0;   // bid/ask older than this is not trusted
        private const double FeedStaleSec  = 20.0;   // no trade tick this long while bars still close = L1 path dead
        private const double ResubGapSec   = 30.0;   // never re-subscribe more often than this
        private const bool   HistUseEventQuotes = true;   // v2.1: classify Tick Replay history with the bid/ask carried on each Last event
        private const double TickRuleShare = 0.10;   // rt=2 when tick-rule volume exceeds this share of the bar

        private static readonly DateTime Epoch =
            new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc);

        private readonly object _lock = new object();
        private string _file;
        private long   _lastWritten;     // unix-sec of the last bar already on disk (resume)

        // per-bar order-flow accumulators (filled by the market-data handlers between closes)
        private double _bestBid, _bestAsk, _lastTrade;
        private double _buyVol,  _sellVol;
        private double _quoteVol, _tickVol;      // volume classified by quote rule / tick rule this bar
        private long   _tickCount;
        private double _side;                    // tick-rule carry: +1 last classified buyer, -1 seller, 0 none yet
        private DateTime _quoteUtc = DateTime.MinValue;   // wall-clock of the last Bid/Ask event

        // v2: two trade-tick sources. Path 0 = the OnMarketData override (needed: it is the
        // only one that replays Tick Replay history). Path 1 = a direct subscription on
        // Instrument.MarketData.Update, made in State.Realtime. Only the PRIMARY path feeds
        // the accumulators; the other takes over once the primary has been silent FeedStaleSec.
        private int  _primary;
        private readonly DateTime[] _lastTickUtc = new DateTime[] { DateTime.UtcNow, DateTime.MinValue };
        private EventHandler<MarketDataEventArgs> _directHandler;
        private Instrument _instr;
        private System.Threading.Timer _wd;
        private bool _terminated;
        private DateTime _lastBarUtc = DateTime.MinValue;   // wall-clock of the last OnBarUpdate
        private DateTime _lastResubUtc = DateTime.MinValue;
        private int _resubCount;
        private string _root = "UNKNOWN";

        // v2.1: replay sidecar (historical bars rebuilt from Tick Replay, rt = 4)
        private bool _replayOn;                                       // hosting chart has Tick Replay
        private readonly List<string> _replayRows = new List<string>();
        private double _rpQuoteVol, _rpTickVol;                       // sidecar volume by classification path
        private int _rpTickBars;                                      // sidecar bars that saw >= 1 tick

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name                        = "EdgeLogOHLCExport";
                Description                 = "Streams closed bars (OHLCV + order-flow delta) to C:\\EdgeLog\\ohlc for EDGELOG.";
                Calculate                   = Calculate.OnBarClose;   // one write per CLOSED bar
                IsOverlay                   = true;
                DisplayInDataBox            = false;
                IsSuspendedWhileInactive    = false;                  // keep capturing even off-screen
            }
            else if (State == State.DataLoaded)
            {
                try
                {
                    if (!Directory.Exists(OutDir)) Directory.CreateDirectory(OutDir);

                    _instr = Instrument;
                    _root = (Instrument != null && Instrument.MasterInstrument != null)
                            ? Instrument.MasterInstrument.Name : "UNKNOWN";
                    _file = Path.Combine(OutDir, _root + "_" + PeriodTag() + ".csv");

                    if (!File.Exists(_file))
                        File.WriteAllText(_file, Header);
                    else
                        _lastWritten = ReadLastTime(_file);   // resume — never double-write
                }
                catch { /* disk not writable — fail quiet, never break NinjaTrader */ }

                try { _replayOn = (Bars != null && Bars.IsTickReplay); }
                catch { _replayOn = false; }
                Log("data loaded: tick replay " + (_replayOn ? "ON - replay sidecar armed" : "off - no sidecar")
                    + ", lastWritten " + _lastWritten);
            }
            else if (State == State.Realtime)
            {
                // Historical (Tick Replay) is over: write the replay sidecar, then add the second
                // trade-tick source and the watchdog.
                try { WriteReplaySidecar(); }
                catch (Exception ex) { Log("replay sidecar EXC: " + ex.Message); }
                try
                {
                    SubscribeDirect();
                    _wd = new System.Threading.Timer(_ => WatchdogTick(), null, 5000, 5000);
                    Log("realtime: direct L1 subscription + watchdog armed");
                }
                catch (Exception ex) { Log("realtime setup EXC: " + ex.Message); }
            }
            else if (State == State.Terminated)
            {
                _terminated = true;
                try { if (_wd != null) _wd.Dispose(); } catch { }
                try { UnsubscribeDirect(); } catch { }
            }
        }

        // --- tick-by-tick, path 0: classify each trade as aggressive buy / sell --------------
        protected override void OnMarketData(MarketDataEventArgs e)
        {
            Feed(0, e);
        }

        // --- tick-by-tick, path 1: direct Instrument.MarketData subscription (realtime only) -
        private void OnDirect(object sender, MarketDataEventArgs e)
        {
            Feed(1, e);
        }

        private void Feed(int path, MarketDataEventArgs e)
        {
            if (e == null || _terminated) return;
            DateTime now = DateTime.UtcNow;
            lock (_lock)
            {
                bool isLast = (e.MarketDataType == MarketDataType.Last);
                if (isLast) _lastTickUtc[path] = now;

                if (path != _primary)
                {
                    // the other path only takes over when the primary has gone silent
                    if (!isLast) return;
                    if ((now - _lastTickUtc[_primary]).TotalSeconds <= FeedStaleSec) return;
                    Log("primary tick path " + _primary + " silent " + (int)(now - _lastTickUtc[_primary]).TotalSeconds
                        + "s — switching to path " + path);
                    _primary = path;
                }

                switch (e.MarketDataType)
                {
                    case MarketDataType.Ask: _bestAsk = e.Price; _quoteUtc = now; break;
                    case MarketDataType.Bid: _bestBid = e.Price; _quoteUtc = now; break;
                    case MarketDataType.Last:
                        double p = e.Price;
                        double v = e.Volume;
                        // v2.1: Tick Replay replays ONLY Last events, but each one carries the best bid/ask at the
                        // moment of the trade (e.Bid / e.Ask). Without this the history was classified by the tick
                        // rule alone (the old "history carries no bid/ask" assumption was wrong). Historical only:
                        // realtime classification is untouched.
                        if (HistUseEventQuotes && State == State.Historical && e.Bid > 0 && e.Ask > 0)
                        { _bestBid = e.Bid; _bestAsk = e.Ask; }
                        // bid/ask are only trusted while fresh. In history (Tick Replay) there are no
                        // quotes at all, so the tick rule below is what classifies those bars.
                        bool quoteOk = _bestAsk > 0 && _bestBid > 0 &&
                                       (State != State.Realtime || (now - _quoteUtc).TotalSeconds <= QuoteFreshSec);
                        double side = 0; bool byQuote = false;
                        if (quoteOk && p >= _bestAsk)        { side = 1;  byQuote = true; }   // lifted the offer
                        else if (quoteOk && p <= _bestBid)   { side = -1; byQuote = true; }   // hit the bid
                        else if (_lastTrade > 0 && p > _lastTrade) side = 1;                  // uptick
                        else if (_lastTrade > 0 && p < _lastTrade) side = -1;                 // downtick
                        else side = _side;                                                    // unchanged: same side as last classified trade
                        if (side != 0) _side = side;
                        if (side > 0)      _buyVol  += v;
                        else if (side < 0) _sellVol += v;
                        if (byQuote) _quoteVol += v; else _tickVol += v;
                        _lastTrade = p;
                        _tickCount++;
                        break;
                }
            }
        }

        // --- bar close: write the row, then reset accumulators --------------------
        protected override void OnBarUpdate()
        {
            _lastBarUtc = DateTime.UtcNow;
            if (CurrentBar < 1 || _file == null) return;

            long t = ToUnixUtc(Time[0]);

            lock (_lock)
            {
                // v2.1: historical bar under Tick Replay -> sidecar row (rt = 4). Independent of
                // _lastWritten (the sidecar covers the whole replayed window) and of the live write below.
                if (_replayOn && State == State.Historical)
                {
                    try { _replayRows.Add(ReplayLine(t)); }
                    catch { /* fail quiet */ }
                }

                if (t > _lastWritten)
                {
                    double delta = _buyVol - _sellVol;
                    int    rt    = RowCode();

                    string line = string.Join(",", new string[] {
                        t.ToString(CultureInfo.InvariantCulture),
                        Open[0].ToString("0.#########",  CultureInfo.InvariantCulture),
                        High[0].ToString("0.#########",  CultureInfo.InvariantCulture),
                        Low[0].ToString("0.#########",   CultureInfo.InvariantCulture),
                        Close[0].ToString("0.#########", CultureInfo.InvariantCulture),
                        ((long)Volume[0]).ToString(CultureInfo.InvariantCulture),
                        delta.ToString("0.###",    CultureInfo.InvariantCulture),
                        _buyVol.ToString("0.###",  CultureInfo.InvariantCulture),
                        _sellVol.ToString("0.###", CultureInfo.InvariantCulture),
                        _tickCount.ToString(CultureInfo.InvariantCulture),
                        rt.ToString(CultureInfo.InvariantCulture)
                    }) + "\n";

                    try { File.AppendAllText(_file, line); _lastWritten = t; }
                    catch { /* fail quiet */ }
                }

                // reset for the next bar (whether or not we wrote this one)
                _buyVol = 0; _sellVol = 0; _tickCount = 0; _quoteVol = 0; _tickVol = 0;
            }
        }

        // caller holds _lock
        private int RowCode()
        {
            if (State != State.Realtime) return 0;
            if (_tickCount == 0 && Volume[0] > 0) return 3;           // bar traded, this indicator saw no ticks
            double seen = _quoteVol + _tickVol;
            if (seen > 0 && _tickVol / seen > TickRuleShare) return 2;
            return 1;
        }

        // v2.1: one sidecar row for the CLOSING bar; caller holds _lock. Same columns / formats as the live row.
        private string ReplayLine(long t)
        {
            double delta = _buyVol - _sellVol;
            if (_tickCount > 0) _rpTickBars++;
            _rpQuoteVol += _quoteVol;
            _rpTickVol  += _tickVol;
            return string.Join(",", new string[] {
                t.ToString(CultureInfo.InvariantCulture),
                Open[0].ToString("0.#########",  CultureInfo.InvariantCulture),
                High[0].ToString("0.#########",  CultureInfo.InvariantCulture),
                Low[0].ToString("0.#########",   CultureInfo.InvariantCulture),
                Close[0].ToString("0.#########", CultureInfo.InvariantCulture),
                ((long)Volume[0]).ToString(CultureInfo.InvariantCulture),
                delta.ToString("0.###",    CultureInfo.InvariantCulture),
                _buyVol.ToString("0.###",  CultureInfo.InvariantCulture),
                _sellVol.ToString("0.###", CultureInfo.InvariantCulture),
                _tickCount.ToString(CultureInfo.InvariantCulture),
                "4"
            }) + "\n";
        }

        // v2.1: called once at State.Realtime. Rewrites the sidecar from scratch: temp file -> move / replace.
        private void WriteReplaySidecar()
        {
            if (!_replayOn || _file == null) return;
            List<string> rows;
            int tickBars; double qv, tv;
            lock (_lock)
            {
                rows = new List<string>(_replayRows);
                tickBars = _rpTickBars; qv = _rpQuoteVol; tv = _rpTickVol;
                _replayRows.Clear();
            }
            if (rows.Count == 0) { Log("replay sidecar: no historical bars - not written"); return; }
            if (tickBars == 0)
            {
                Log("replay sidecar: " + rows.Count + " bars but ZERO ticks (provider served no tick history) - not written");
                return;
            }

            string dir = Path.Combine(OutDir, "replay");
            Directory.CreateDirectory(dir);
            string fin = Path.Combine(dir, _root + "_" + PeriodTag() + "_replay.csv");
            string tmp = fin + ".tmp";
            using (FileStream fs = new FileStream(tmp, FileMode.Create, FileAccess.Write, FileShare.None))
            using (StreamWriter sw = new StreamWriter(fs, new UTF8Encoding(false)))
            {
                sw.Write(Header);
                foreach (string r in rows) sw.Write(r);
                sw.Flush();
                fs.Flush(true);                               // fsync before the move
            }
            for (int attempt = 0; ; attempt++)
            {
                try
                {
                    if (File.Exists(fin)) File.Replace(tmp, fin, null);
                    else File.Move(tmp, fin);
                    break;
                }
                catch (IOException)
                {
                    if (attempt >= 5) throw;                  // a reader may hold it a moment (the repair tool)
                    System.Threading.Thread.Sleep(500);
                }
            }
            double seen = qv + tv;
            Log("replay sidecar written: " + rows.Count + " bars, " + tickBars + " with ticks, "
                + (seen > 0 ? (100.0 * qv / seen).ToString("0.#", CultureInfo.InvariantCulture) : "0")
                + "% of volume classified by bid/ask quote (rest by tick rule) -> " + fin);
        }

        // ----- v2 self-heal ------------------------------------------------------
        private void SubscribeDirect()
        {
            if (_instr == null || _instr.MarketData == null) return;
            if (_directHandler == null) _directHandler = OnDirect;
            _instr.MarketData.Update += _directHandler;
        }

        private void UnsubscribeDirect()
        {
            if (_instr == null || _instr.MarketData == null || _directHandler == null) return;
            _instr.MarketData.Update -= _directHandler;
        }

        // every 5 s: if bars are still closing but no trade tick has reached us for
        // FeedStaleSec, the L1 path is dead — drop and re-add the direct subscription.
        private void WatchdogTick()
        {
            try
            {
                if (_terminated || State != State.Realtime) return;
                DateTime now = DateTime.UtcNow;
                double barAge, tickAge;
                lock (_lock)
                {
                    barAge  = (now - _lastBarUtc).TotalSeconds;
                    DateTime newest = _lastTickUtc[0] > _lastTickUtc[1] ? _lastTickUtc[0] : _lastTickUtc[1];
                    tickAge = (now - newest).TotalSeconds;
                }
                if (barAge > 30 || tickAge <= FeedStaleSec) return;          // healthy, or the whole feed is quiet/closed
                if ((now - _lastResubUtc).TotalSeconds < ResubGapSec) return;
                _lastResubUtc = now;
                _resubCount++;
                Log("no trade tick for " + (int)tickAge + "s while bars still close — re-subscribing direct L1 (#" + _resubCount + ")");
                try { UnsubscribeDirect(); } catch { }
                SubscribeDirect();
            }
            catch (Exception ex) { Log("watchdog EXC: " + ex.Message); }
        }

        private void Log(string msg)
        {
            try
            {
                File.AppendAllText(Path.Combine(OutDir, "_export_" + _root + ".log"),
                    string.Format("{0:yyyy-MM-dd HH:mm:ss}  {1}\n", DateTime.Now, msg));
            }
            catch { }
        }

        // ----- helpers -----------------------------------------------------------

        // NinjaTrader bar times are in the time zone set under Tools > Options >
        // General. The DEFAULT is your PC's local zone, which this assumes. If your
        // NT zone differs, the first-run cross-check against TradingView will reveal
        // a constant offset — tell me and I'll pin the exact zone here.
        private static long ToUnixUtc(DateTime barTime)
        {
            DateTime utc = DateTime.SpecifyKind(barTime, DateTimeKind.Local).ToUniversalTime();
            return (long)(utc - Epoch).TotalSeconds;
        }

        private string PeriodTag()
        {
            int v = (BarsPeriod != null) ? BarsPeriod.Value : 0;
            if (BarsPeriod == null) return "bar";
            switch (BarsPeriod.BarsPeriodType)
            {
                case BarsPeriodType.Second: return v + "s";
                case BarsPeriodType.Minute: return v + "m";
                case BarsPeriodType.Day:    return v + "D";
                default:                    return v + "x";   // tick/range/etc — flag, don't crash
            }
        }

        private static long ReadLastTime(string path)
        {
            try
            {
                string[] lines = File.ReadAllLines(path);
                for (int i = lines.Length - 1; i >= 1; i--)
                {
                    if (string.IsNullOrWhiteSpace(lines[i])) continue;
                    int comma = lines[i].IndexOf(',');
                    string head = comma > 0 ? lines[i].Substring(0, comma) : lines[i];
                    long t;
                    if (long.TryParse(head, out t)) return t;
                }
            }
            catch { /* ignore — treat as fresh */ }
            return 0;
        }
    }
}
