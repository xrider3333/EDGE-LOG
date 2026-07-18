// ============================================================================
//  EdgeLogExport v2.0  —  NinjaTrader 8 AddOn
//  Streams every account execution (fill) to C:\EdgeLog\fills.csv in real time.
//  EDGELOG's local runner watches that file, pairs fills into round-trip trades,
//  and pushes them to your EDGELOG journal automatically.
//
//  WHY AN AddOn (not a Strategy):  an AddOn subscribes to the *account's*
//  ExecutionUpdate, so it captures EVERY fill on the account — manual/discretionary
//  trades AND automated strategy fills. A Strategy only sees its own orders.
//
//  v2.0 (2026-07-11) — self-healing rewrite. v1 subscribed once at startup and
//  swallowed every exception; after a broker (Tradovate) reconnect the
//  subscription went stale and a morning of fills was silently lost. Changes:
//    • RESUBSCRIBE — OnConnectionStatusUpdate re-hooks ExecutionUpdate on every
//      account whenever any connection transitions to Connected.
//    • SWEEP — every 60s each account's current-session Executions collection is
//      scanned; any fill whose ExecutionId isn't recorded yet is appended exactly
//      as a live event would be (the broker replays the current session on
//      connect, so a stale subscription now heals within a minute).
//    • HEARTBEAT — every sweep overwrites C:\EdgeLog\addon_heartbeat.json with
//      {"ts_utc","accounts","seen","version"} so the EDGELOG pipeline/UI can flag
//      a dead capture even when no fills are expected.
//    • v2.1 (2026-07-17) — the heartbeat now also carries each account's cash
//      balance and realized day P&L (accts:{name:{cash,realized}}), so the web
//      app can reconcile NinjaTrader web/mobile fills that never reach this
//      desktop AddOn.
//    • LOGGING — startup/shutdown, connection changes, (re)subscribes, sweep
//      additions and EVERY exception append to C:\EdgeLog\addon.log (UTC
//      timestamps). No silent catches. Routine no-op sweeps are not logged.
//
//  INSTALL (one time):
//    1. Copy this file to
//         Documents\NinjaTrader 8\bin\Custom\AddOns\EdgeLogExport.cs
//       (or paste it into a New AddOn in the NinjaScript Editor).
//    2. In NinjaTrader 8 → NinjaScript Editor → press F5 (Compile).
//       You should see "Compile succeeded".
//    3. Restart NinjaTrader 8. The AddOn loads automatically on every launch and
//       runs in the background — there is nothing to enable on a chart.
//    4. Place/close a trade → C:\EdgeLog\fills.csv gets a new row.
//
//  The file is append-only and self-healing: each fill carries a unique
//  ExecutionId (deduped in-memory, reloaded from the CSV at startup), so replays
//  and sweeps never double-count. New accounts are picked up on reconnect or by
//  the next sweep — no NinjaTrader restart needed (v1 required one).
// ============================================================================
using System;
using System.IO;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using NinjaTrader.Cbi;
using NinjaTrader.NinjaScript;

namespace NinjaTrader.NinjaScript.AddOns
{
    public class EdgeLogExport : NinjaTrader.NinjaScript.AddOnBase
    {
        private const string Version = "2.1";

        // Change this path if you keep EdgeLog elsewhere — keep it in sync with the
        // runner's --nt-fills argument (default C:\EdgeLog\fills.csv).
        private const string Dir           = @"C:\EdgeLog";
        private const string FilePath      = @"C:\EdgeLog\fills.csv";
        private const string LogPath       = @"C:\EdgeLog\addon.log";
        private const string HeartbeatPath = @"C:\EdgeLog\addon_heartbeat.json";
        private const string Header =
            "ExecutionId,Time,Account,Instrument,Action,Qty,Price,Commission,OrderId\n";

        private const int SweepMs = 60000;    // sweep + heartbeat cadence (60s)

        private readonly object _ioLock  = new object();  // fills.csv / addon.log / heartbeat + _seen
        private readonly object _subLock = new object();  // _hooked + event (un)hooking
        private readonly HashSet<string>  _seen   = new HashSet<string>();
        private readonly HashSet<Account> _hooked = new HashSet<Account>();
        private System.Timers.Timer _sweepTimer;
        private int _sweeping;                // re-entrancy guard (timer vs reconnect sweep)

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "EdgeLogExport";
            }
            else if (State == State.Configure)
            {
                int loaded = 0;
                try
                {
                    if (!Directory.Exists(Dir)) Directory.CreateDirectory(Dir);
                    lock (_ioLock)
                    {
                        if (!File.Exists(FilePath)) File.WriteAllText(FilePath, Header);
                        loaded = LoadSeenFromCsv();
                    }
                }
                catch (Exception ex) { Log("ERROR startup init: " + ex.Message); }
                Log("startup: EdgeLogExport v" + Version + " — " + loaded +
                    " ExecutionId(s) loaded from fills.csv");

                SubscribeAll("startup");

                // Static connection hook (same pattern as tools/EdgeLogOHLCAddon.cs).
                // AddOnBase has NO OnConnectionStatusUpdate virtual — verified by
                // reflection against NinjaTrader.Core 8.1.7.2 — so the documented
                // static Connection.ConnectionStatusUpdate event is the AddOn API.
                Connection.ConnectionStatusUpdate += OnConnectionStatus;

                _sweepTimer = new System.Timers.Timer(SweepMs);
                _sweepTimer.AutoReset = true;
                _sweepTimer.Elapsed += (s, e) => Sweep("timer");
                _sweepTimer.Start();
            }
            else if (State == State.Terminated)
            {
                try { Connection.ConnectionStatusUpdate -= OnConnectionStatus; }
                catch (Exception ex) { Log("ERROR connection unhook: " + ex.Message); }
                try
                {
                    if (_sweepTimer != null)
                    { _sweepTimer.Stop(); _sweepTimer.Dispose(); _sweepTimer = null; }
                }
                catch (Exception ex) { Log("ERROR timer dispose: " + ex.Message); }
                UnsubscribeAll();
                Log("shutdown: terminated");
            }
        }

        // Fires on every connection status change (documented static NT8 AddOn API;
        // ConnectionStatusEventArgs carries Status / PreviousStatus — verified
        // against NinjaTrader.Core 8.1.7.2. PriceStatus-only updates are ignored).
        private void OnConnectionStatus(object sender, ConnectionStatusEventArgs e)
        {
            try
            {
                if (e == null || e.Status == e.PreviousStatus) return;
                Log("connection status: " + e.PreviousStatus + " -> " + e.Status);
                if (e.Status == ConnectionStatus.Connected)
                {
                    // A broker (Tradovate) reconnect orphans the old ExecutionUpdate
                    // subscriptions — THE v1 failure mode. Re-hook everything, then
                    // sweep immediately to capture whatever the broker replays.
                    SubscribeAll("reconnect");
                    Sweep("reconnect");
                }
            }
            catch (Exception ex) { Log("ERROR OnConnectionStatus: " + ex.Message); }
        }

        // ---- subscriptions ---------------------------------------------------

        private void SubscribeAll(string reason)
        {
            try
            {
                List<Account> accounts;
                lock (Account.All) accounts = new List<Account>(Account.All);
                lock (_subLock)
                {
                    foreach (Account a in accounts)
                    {
                        a.ExecutionUpdate -= OnExecutionUpdate;  // unhook first — never stack duplicates
                        a.ExecutionUpdate += OnExecutionUpdate;
                        _hooked.Add(a);
                    }
                }
                Log("subscribed ExecutionUpdate on " + accounts.Count + " account(s) [" + reason + "]"
                    + (accounts.Count > 0 ? ": " + Names(accounts) : ""));
            }
            catch (Exception ex) { Log("ERROR SubscribeAll [" + reason + "]: " + ex.Message); }
        }

        private void UnsubscribeAll()
        {
            try
            {
                lock (_subLock)
                {
                    foreach (Account a in _hooked) a.ExecutionUpdate -= OnExecutionUpdate;
                    _hooked.Clear();
                }
            }
            catch (Exception ex) { Log("ERROR UnsubscribeAll: " + ex.Message); }
        }

        // ---- live path -------------------------------------------------------

        private void OnExecutionUpdate(object sender, ExecutionEventArgs e)
        {
            try
            {
                Execution ex = (e == null) ? null : e.Execution;
                if (ex == null || ex.Order == null) return;

                // Only count real fills (same filter as v1). Any real fill this skips
                // is healed by the sweep — account.Executions only holds actual fills.
                OrderState os = ex.Order.OrderState;
                if (os != OrderState.Filled && os != OrderState.PartFilled) return;

                RecordExecution(ex);
            }
            catch (Exception ex2) { Log("ERROR OnExecutionUpdate: " + ex2.Message); }
        }

        // ---- self-heal sweep + heartbeat --------------------------------------

        private void Sweep(string reason)
        {
            if (System.Threading.Interlocked.CompareExchange(ref _sweeping, 1, 0) != 0)
                return;   // a sweep is already running (timer/reconnect overlap)
            try
            {
                List<Account> accounts;
                lock (Account.All) accounts = new List<Account>(Account.All);

                // Hook accounts that appeared after startup (e.g. created by a fresh
                // broker connection) — v1 needed a NinjaTrader restart for these.
                List<Account> fresh = null;
                lock (_subLock)
                {
                    foreach (Account a in accounts)
                    {
                        if (_hooked.Contains(a)) continue;
                        a.ExecutionUpdate -= OnExecutionUpdate;
                        a.ExecutionUpdate += OnExecutionUpdate;
                        _hooked.Add(a);
                        if (fresh == null) fresh = new List<Account>();
                        fresh.Add(a);
                    }
                }
                if (fresh != null)
                    Log("sweep: hooked " + fresh.Count + " new account(s): " + Names(fresh));

                int added = 0;
                foreach (Account a in accounts)
                {
                    try
                    {
                        // Account.Executions = the account's current-session executions
                        // (documented Account property; the broker replays the current
                        // session's fills into it on connect). Copy under the
                        // collection's own lock — canonical NT8 pattern.
                        List<Execution> execs;
                        lock (a.Executions) execs = new List<Execution>(a.Executions);
                        foreach (Execution ex in execs)
                            if (RecordExecution(ex)) added++;
                    }
                    catch (Exception exAcct)
                    { Log("ERROR sweep account '" + a.Name + "': " + exAcct.Message); }
                }
                if (added > 0)
                    Log("sweep[" + reason + "]: appended " + added + " missed execution(s)");
                // (no log line for a routine no-op sweep — keeps addon.log small)

                WriteHeartbeat(accounts);
            }
            catch (Exception ex) { Log("ERROR sweep [" + reason + "]: " + ex.Message); }
            finally { System.Threading.Interlocked.Exchange(ref _sweeping, 0); }
        }

        // Append one execution to fills.csv (idempotent by ExecutionId).
        // Returns true only when a new row was actually written. Used by BOTH the
        // live ExecutionUpdate path and the sweep, so rows are byte-identical.
        private bool RecordExecution(Execution ex)
        {
            if (ex == null) return false;
            string execId = ex.ExecutionId;
            if (string.IsNullOrEmpty(execId)) return false;

            string action;
            if (ex.Order != null)
            {
                switch (ex.Order.OrderAction)
                {
                    case OrderAction.Buy:
                    case OrderAction.BuyToCover: action = "BUY";  break;
                    default:                     action = "SELL"; break;  // Sell / SellShort
                }
            }
            else
            {
                // Replayed/session executions can arrive without an Order object —
                // fall back to the execution's side (documented Execution.MarketPosition:
                // Long = buy fill, Short = sell fill).
                action = ex.MarketPosition == MarketPosition.Long ? "BUY" : "SELL";
            }

            lock (_ioLock)
            {
                if (_seen.Contains(execId)) return false;   // live+sweep dedupe (NT can fire twice)

                string line = string.Join(",", new string[] {
                    Csv(execId),
                    // Log in UTC so the journal can convert to the market's local
                    // timezone deterministically (nt_sync.py -> America/New_York),
                    // independent of this PC's NinjaTrader time-zone setting.
                    ex.Time.ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture),
                    Csv(ex.Account != null ? ex.Account.Name : ""),
                    Csv(ex.Instrument != null ? ex.Instrument.FullName : ""),
                    action,
                    ex.Quantity.ToString(CultureInfo.InvariantCulture),
                    ex.Price.ToString("0.#########", CultureInfo.InvariantCulture),
                    ex.Commission.ToString("0.####", CultureInfo.InvariantCulture),
                    // Execution.OrderId is the documented fallback when the Order
                    // object isn't attached (e.g. broker-replayed executions).
                    Csv(ex.Order != null ? (ex.Order.OrderId ?? "") : (ex.OrderId ?? ""))
                }) + "\n";

                File.AppendAllText(FilePath, line);
                _seen.Add(execId);   // only after a successful append, so an IO error retries next sweep
            }
            return true;
        }

        // accounts: the same List<Account> Sweep() already collected this pass — reused here
        // (not re-queried) so the heartbeat's account count and per-account detail agree.
        private void WriteHeartbeat(List<Account> accounts)
        {
            try
            {
                int seen;
                lock (_ioLock) seen = _seen.Count;

                StringBuilder accts = new StringBuilder();
                foreach (Account a in accounts)
                {
                    try
                    {
                        double cash = a.Get(AccountItem.CashValue, Currency.UsDollar);
                        double realized = a.Get(AccountItem.RealizedProfitLoss, Currency.UsDollar);
                        if (accts.Length > 0) accts.Append(",");
                        accts.Append(string.Format(CultureInfo.InvariantCulture,
                            "\"{0}\":{{\"cash\":{1},\"realized\":{2}}}",
                            JsonStr(a.Name),
                            cash.ToString("0.##", CultureInfo.InvariantCulture),
                            realized.ToString("0.##", CultureInfo.InvariantCulture)));
                    }
                    catch (Exception exAcct)
                    { Log("ERROR heartbeat account '" + a.Name + "': " + exAcct.Message); }
                }

                string json = string.Format(CultureInfo.InvariantCulture,
                    "{{\"ts_utc\":\"{0}\",\"accounts\":{1},\"seen\":{2},\"version\":\"{3}\",\"accts\":{{{4}}}}}",
                    DateTime.UtcNow.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture),
                    accounts.Count, seen, Version, accts.ToString());
                lock (_ioLock) File.WriteAllText(HeartbeatPath, json);
            }
            catch (Exception ex) { Log("ERROR heartbeat write: " + ex.Message); }
        }

        // Minimal JSON string escaping for account names (normally alphanumeric).
        private static string JsonStr(string s)
        {
            if (s == null) return "";
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"");
        }

        // ---- plumbing ----------------------------------------------------------

        private void Log(string msg)
        {
            try
            {
                string line = DateTime.UtcNow.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture)
                              + "  " + msg + "\n";
                lock (_ioLock) File.AppendAllText(LogPath, line);
            }
            catch (Exception ex)
            {
                // The log file itself is unwritable — surface it in the NinjaScript
                // Output window (New > NinjaScript Output) rather than swallowing.
                try { NinjaTrader.Code.Output.Process("EdgeLogExport: log write failed: " + ex.Message, PrintTo.OutputTab1); }
                catch { /* nowhere left to report a logging failure */ }
            }
        }

        // Seed _seen from the existing fills.csv (small file) so sweeps never
        // re-append executions recorded in a previous NinjaTrader session.
        private int LoadSeenFromCsv()
        {
            int n = 0;
            if (!File.Exists(FilePath)) return 0;
            string[] lines = File.ReadAllLines(FilePath);
            for (int i = 1; i < lines.Length; i++)          // skip header row
            {
                string id = FirstCsvField(lines[i]);
                if (id.Length > 0 && _seen.Add(id)) n++;
            }
            return n;
        }

        // First CSV field of a line, honoring the quoting Csv() below produces.
        private static string FirstCsvField(string line)
        {
            if (string.IsNullOrEmpty(line)) return "";
            if (line[0] != '"')
            {
                int c = line.IndexOf(',');
                return (c < 0 ? line : line.Substring(0, c)).Trim();
            }
            StringBuilder sb = new StringBuilder();
            for (int i = 1; i < line.Length; i++)
            {
                if (line[i] == '"')
                {
                    if (i + 1 < line.Length && line[i + 1] == '"') { sb.Append('"'); i++; }
                    else break;                                   // closing quote
                }
                else sb.Append(line[i]);
            }
            return sb.ToString();
        }

        private static string Names(List<Account> accounts)
        {
            StringBuilder sb = new StringBuilder();
            foreach (Account a in accounts)
            {
                if (sb.Length > 0) sb.Append(", ");
                sb.Append(a != null ? a.Name : "?");
            }
            return sb.ToString();
        }

        // Minimal CSV escaping: quote a field only if it contains a comma/quote/newline.
        private static string Csv(string s)
        {
            if (s == null) return "";
            if (s.IndexOf(',') >= 0 || s.IndexOf('"') >= 0 || s.IndexOf('\n') >= 0)
                return "\"" + s.Replace("\"", "\"\"") + "\"";
            return s;
        }
    }
}
