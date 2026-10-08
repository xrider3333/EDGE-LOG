// EdgeLogHistFetch - headless NinjaTrader history fetcher (PAPER-NT8, 2026-10-08).
//
// WHY. The 10-second capture loses its buy/sell split for every hour NinjaTrader is not running (PC sleep,
// and from 10-08 the nightly "NT night mode"). The only refill was Tick Replay on the chart, and since
// 10-04 no market-day start loads any Tick Replay history ("replay sidecar: no historical bars"), although
// the ticks sit in NinjaTrader's own cache and on its data server. This add-on asks for the ticks directly
// (BarsRequest, 1-tick, no chart), rebuilds the 10-second rows with a bid/ask classification, and writes
// them where tools/repair_10s_from_replay.py already merges replay files. It also serves plain history
// pulls (e.g. two 2020 ES minute sessions for the TBIS lane).
//
// HOW. A Python job drops request files into C:\EdgeLog\nt_hist\queue\*.req (key=value lines). While a
// connection is up, a 30-second timer takes ONE request at a time:
//   instrument=NQ 12-26           NinjaTrader instrument name
//   kind=ticks10s | bars          ticks10s = 1-tick request rebuilt into 10 s END-stamped rows (rt=4)
//                                 bars     = plain bars at period/value, written as they come
//   period=Minute|Second|Tick     (bars only)   value=1
//   from=2026-10-07T04:38:00Z     UTC, ISO, inclusive        to=2026-10-07T12:51:00Z   UTC, exclusive
//   out=C:\EdgeLog\ohlc\replay\NQ_10s_backfill_20261007.csv
// The request file is renamed .running while it works, then .done (with the row count appended) or
// .failed (with the reason appended). It never writes outside the path it is given, never places an
// order, never touches a chart, an account or a strategy. Read-only history.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;

namespace NinjaTrader.NinjaScript.AddOns
{
    public class EdgeLogHistFetch : NinjaTrader.NinjaScript.AddOnBase
    {
        private const string QueueDir = @"C:\EdgeLog\nt_hist\queue";
        private const string LogPath = @"C:\EdgeLog\nt_hist\_histfetch.log";
        private static readonly DateTime Epoch = new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc);

        private System.Threading.Timer timer;
        private readonly object gate = new object();
        private bool busy;
        private bool connected;
        private BarsRequest req;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
                Name = "EdgeLogHistFetch";
            else if (State == State.Configure)
            {
                try { Directory.CreateDirectory(QueueDir); } catch { }
                Connection.ConnectionStatusUpdate += OnConn;
                timer = new System.Threading.Timer(delegate { Tick(); }, null, 45000, 30000);
                Log("loaded");
            }
            else if (State == State.Terminated)
            {
                try { Connection.ConnectionStatusUpdate -= OnConn; } catch { }
                try { if (timer != null) timer.Dispose(); } catch { }
                try { if (req != null) req.Dispose(); } catch { }
            }
        }

        private void OnConn(object sender, ConnectionStatusEventArgs e)
        {
            if (e.Status == ConnectionStatus.Connected) connected = true;
        }

        private void Log(string msg)
        {
            try
            {
                File.AppendAllText(LogPath, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture)
                                            + "  " + msg + Environment.NewLine);
            }
            catch { }
        }

        private void Tick()
        {
            string file = null;
            lock (gate)
            {
                if (busy || !connected) return;
                try
                {
                    string[] reqs = Directory.GetFiles(QueueDir, "*.req");
                    if (reqs.Length == 0) return;
                    Array.Sort(reqs, StringComparer.OrdinalIgnoreCase);
                    file = reqs[0] + ".running";
                    File.Move(reqs[0], file);
                    busy = true;
                }
                catch (Exception ex) { Log("queue read failed: " + ex.Message); return; }
            }
            try { Run(file); }
            catch (Exception ex) { Finish(file, false, "exception: " + ex.Message); }
        }

        private static Dictionary<string, string> ReadReq(string path)
        {
            var d = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (string raw in File.ReadAllLines(path))
            {
                string line = raw.Trim();
                if (line.Length == 0 || line.StartsWith("#")) continue;
                int i = line.IndexOf('=');
                if (i <= 0) continue;
                d[line.Substring(0, i).Trim()] = line.Substring(i + 1).Trim();
            }
            return d;
        }

        private static string Get(Dictionary<string, string> d, string k, string dflt)
        {
            string v;
            return d.TryGetValue(k, out v) && v.Length > 0 ? v : dflt;
        }

        private void Run(string file)
        {
            var d = ReadReq(file);
            string name = Get(d, "instrument", "");
            string kind = Get(d, "kind", "bars").ToLowerInvariant();
            string outPath = Get(d, "out", "");
            DateTime fromUtc, toUtc;
            if (name.Length == 0 || outPath.Length == 0
                || !DateTime.TryParse(Get(d, "from", ""), CultureInfo.InvariantCulture,
                                      DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out fromUtc)
                || !DateTime.TryParse(Get(d, "to", ""), CultureInfo.InvariantCulture,
                                      DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out toUtc)
                || toUtc <= fromUtc)
            {
                Finish(file, false, "bad request (need instrument, out, from < to)");
                return;
            }
            Instrument instr = Instrument.GetInstrument(name);
            if (instr == null) { Finish(file, false, "unknown instrument " + name); return; }

            BarsPeriod bp;
            if (kind == "ticks10s")
                bp = new BarsPeriod { BarsPeriodType = BarsPeriodType.Tick, Value = 1 };
            else
            {
                BarsPeriodType t;
                string per = Get(d, "period", "Minute");
                if (per.Equals("Second", StringComparison.OrdinalIgnoreCase)) t = BarsPeriodType.Second;
                else if (per.Equals("Tick", StringComparison.OrdinalIgnoreCase)) t = BarsPeriodType.Tick;
                else t = BarsPeriodType.Minute;
                int v;
                if (!int.TryParse(Get(d, "value", "1"), out v) || v <= 0) v = 1;
                bp = new BarsPeriod { BarsPeriodType = t, Value = v };
            }
            DateTime fromLocal = TimeZoneInfo.ConvertTimeFromUtc(fromUtc, TimeZoneInfo.Local);
            DateTime toLocal = TimeZoneInfo.ConvertTimeFromUtc(toUtc, TimeZoneInfo.Local);
            Log("request " + Path.GetFileName(file) + ": " + name + " " + kind + " " + fromUtc.ToString("s") + "Z.." + toUtc.ToString("s") + "Z");

            req = new BarsRequest(instr, fromLocal, toLocal);
            req.BarsPeriod = bp;
            req.Request(delegate(BarsRequest rq, ErrorCode ec, string em)
            {
                try
                {
                    if (ec != ErrorCode.NoError || rq == null || rq.Bars == null)
                    {
                        Finish(file, false, "BarsRequest " + ec + ": " + em);
                        return;
                    }
                    string extra = "";
                    int n;
                    if (kind == "ticks10s")
                    {
                        long byQuote, total;
                        n = WriteTicks10s(rq.Bars, fromUtc, toUtc, outPath, out byQuote, out total);
                        extra = ", " + byQuote + " of " + total + " trades classified by bid/ask (rest by tick rule)";
                    }
                    else n = WriteBars(rq.Bars, fromUtc, toUtc, outPath);
                    Finish(file, true, n + " rows -> " + outPath + " (" + rq.Bars.Count + " source bars" + extra + ")");
                }
                catch (Exception ex) { Finish(file, false, "write failed: " + ex.Message); }
                finally { try { rq.Dispose(); } catch { } }
            });
        }

        private void Finish(string running, bool ok, string note)
        {
            Log((ok ? "done   " : "FAILED ") + Path.GetFileName(running) + ": " + note);
            try
            {
                string final = running.Substring(0, running.Length - ".running".Length) + (ok ? ".done" : ".failed");
                File.AppendAllText(running, "# result=" + (ok ? "done" : "failed") + " " + note + Environment.NewLine);
                if (File.Exists(final)) File.Delete(final);
                File.Move(running, final);
            }
            catch { }
            lock (gate) busy = false;
        }

        private static long ToUnix(DateTime local)
        {
            DateTime utc = TimeZoneInfo.ConvertTimeToUtc(DateTime.SpecifyKind(local, DateTimeKind.Unspecified), TimeZoneInfo.Local);
            return (long)Math.Floor((utc - Epoch).TotalSeconds);
        }

        private static double ToUnixExact(DateTime local)
        {
            DateTime utc = TimeZoneInfo.ConvertTimeToUtc(DateTime.SpecifyKind(local, DateTimeKind.Unspecified), TimeZoneInfo.Local);
            return (utc - Epoch).TotalSeconds;
        }

        private static string F(double x) { return x.ToString("0.#########", CultureInfo.InvariantCulture); }

        private static void WriteAtomic(string outPath, StringBuilder sb)
        {
            string dir = Path.GetDirectoryName(outPath);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            string tmp = outPath + ".tmp";
            File.WriteAllText(tmp, sb.ToString());
            if (File.Exists(outPath)) File.Delete(outPath);
            File.Move(tmp, outPath);
        }

        // Plain bars: one row per source bar inside [from, to), time = the bar's own stamp (NinjaTrader stamps
        // time-based bars at their END), as unix seconds UTC.
        private static int WriteBars(Bars bars, DateTime fromUtc, DateTime toUtc, string outPath)
        {
            long lo = (long)(fromUtc - Epoch).TotalSeconds, hi = (long)(toUtc - Epoch).TotalSeconds;
            var sb = new StringBuilder("time,open,high,low,close,volume\n");
            int n = 0;
            for (int i = 0; i < bars.Count; i++)
            {
                long t = ToUnix(bars.GetTime(i));
                if (t < lo || t >= hi) continue;
                sb.Append(t.ToString(CultureInfo.InvariantCulture)).Append(',')
                  .Append(F(bars.GetOpen(i))).Append(',').Append(F(bars.GetHigh(i))).Append(',')
                  .Append(F(bars.GetLow(i))).Append(',').Append(F(bars.GetClose(i))).Append(',')
                  .Append(bars.GetVolume(i).ToString(CultureInfo.InvariantCulture)).Append('\n');
                n++;
            }
            WriteAtomic(outPath, sb);
            return n;
        }

        // 1-tick bars -> 10-second rows in the capture's own format, END-stamped like NinjaTrader's 10 s bars
        // (a trade at 09:30:03.2 belongs to the row stamped 09:30:10; one exactly on 09:30:10.000 also does).
        // Each trade is a BUY at or above the ask, a SELL at or below the bid, otherwise by the tick rule.
        // rt = 4 (rebuilt from history), the code tools/repair_10s_from_replay.py merges.
        private static int WriteTicks10s(Bars bars, DateTime fromUtc, DateTime toUtc, string outPath, out long byQuote, out long total)
        {
            double lo = (fromUtc - Epoch).TotalSeconds, hi = (toUtc - Epoch).TotalSeconds;
            var sb = new StringBuilder("time,open,high,low,close,volume,delta,buy_vol,sell_vol,tick_count,rt\n");
            long cur = -1; double o = 0, h = 0, l = 0, c = 0, buy = 0, sell = 0, lastPx = double.NaN; long vol = 0, ticks = 0;
            int n = 0; byQuote = 0; total = 0;
            for (int i = 0; i < bars.Count; i++)
            {
                double ts = ToUnixExact(bars.GetTime(i));
                if (ts < lo || ts >= hi) continue;
                long end = (long)Math.Ceiling(ts / 10.0) * 10;
                double px = bars.GetClose(i), bid = bars.GetBid(i), ask = bars.GetAsk(i);
                long v = bars.GetVolume(i);
                if (end != cur)
                {
                    if (cur >= 0) { AppendRow(sb, cur, o, h, l, c, vol, buy, sell, ticks); n++; }
                    cur = end; o = h = l = px; vol = 0; buy = 0; sell = 0; ticks = 0;
                }
                if (px > h) h = px;
                if (px < l) l = px;
                c = px; vol += v; ticks++;
                bool isBuy;
                total++;
                if (ask > 0 && px >= ask) { isBuy = true; byQuote++; }
                else if (bid > 0 && px <= bid) { isBuy = false; byQuote++; }
                else if (!double.IsNaN(lastPx) && px != lastPx) isBuy = px > lastPx;
                else isBuy = buy >= sell;   // unchanged price, no quote: lean with the bar so far
                if (isBuy) buy += v; else sell += v;
                lastPx = px;
            }
            if (cur >= 0) { AppendRow(sb, cur, o, h, l, c, vol, buy, sell, ticks); n++; }
            WriteAtomic(outPath, sb);
            return n;
        }

        private static void AppendRow(StringBuilder sb, long t, double o, double h, double l, double c,
                                      long vol, double buy, double sell, long ticks)
        {
            sb.Append(t.ToString(CultureInfo.InvariantCulture)).Append(',')
              .Append(F(o)).Append(',').Append(F(h)).Append(',').Append(F(l)).Append(',').Append(F(c)).Append(',')
              .Append(vol.ToString(CultureInfo.InvariantCulture)).Append(',')
              .Append((buy - sell).ToString("0.###", CultureInfo.InvariantCulture)).Append(',')
              .Append(buy.ToString("0.###", CultureInfo.InvariantCulture)).Append(',')
              .Append(sell.ToString("0.###", CultureInfo.InvariantCulture)).Append(',')
              .Append(ticks.ToString(CultureInfo.InvariantCulture)).Append(",4\n");
        }
    }
}
