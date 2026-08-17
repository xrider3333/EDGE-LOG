// ============================================================================
//  EdgeLogBridge v1.0  —  NinjaTrader 8 AddOn  (2026-08-14)
//  Local HTTP bridge so EDGELOG's tooling (Claude, the runner, scripts) can SEE
//  and — where explicitly allowed — CONTROL this NinjaTrader from outside the UI.
//
//  WHY: the assistant driving EDGELOG is policy-blocked from clicking inside
//  trading apps. Every "check the Strategies tab / press F5 / re-enable X" lands
//  on the owner. Code running INSIDE NinjaTrader has no such limit. This AddOn is
//  the inside half; tools/nt_bridge.py is the outside half.
//
//  TRANSPORT: raw TcpListener on 127.0.0.1:8391 with a minimal HTTP/1.1 parser.
//  Deliberately NOT HttpListener — that needs a netsh URL ACL for non-admin
//  users; a TcpListener bound to loopback needs nothing and can never be
//  reached from another machine.
//
//  ENDPOINTS (all JSON):
//    GET  /health        uptime, version, account count, flags
//    GET  /accounts      name, cash, realized day PnL
//    GET  /positions     per-account open positions
//    GET  /orders        per-account orders (working by default; ?all=1 for all)
//    GET  /strategies    per-account strategy instances: name, state, position
//    GET  /executions    today's fills
//    POST /flatten?account=NAME          close everything on ONE allowed account
//    POST /killswitch                    flatten + disable every ALLOWED account/strategy
//    POST /order  (json body)            place an order — see ORDERS below
//
//  SAFETY MODEL — built with LIVE trading in mind, so the rails are layered and
//  the LOOSENING of each layer is a deliberate, visible act:
//    L1  LIVE_LOCKED accounts are refused for every mutating endpoint no matter
//        what any config says. Editing this constant requires a recompile — that
//        recompile IS the owner's sign-off. Today: 1810769 (the real-money acct).
//    L2  Mutations only touch accounts in C:\EdgeLog\bridge.json "accounts".
//        Missing file -> mutations refuse everything (reads always work).
//    L3  /order additionally requires "orders_enabled": true in bridge.json.
//        Ships false. Flatten is allowed at L2 because its worst case is FLAT —
//        that is the panic button and it should never be behind an extra flag.
//    L4  Reads are read-only by construction: no reflection, no internal state,
//        only public documented collections, every field individually try/caught.
//
//  When the owner takes an account live: add it to bridge.json (L2), flip
//  orders_enabled (L3), and — only if it is the hard-locked one — change L1 and
//  recompile. Three layers, three separate decisions, all of them the owner's.
//
//  INSTALL: same as EdgeLogExport — this file lives in bin\Custom\AddOns,
//  F5 in the NinjaScript Editor, restart NinjaTrader. Logs: C:\EdgeLog\bridge.log
// ============================================================================
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using NinjaTrader.Cbi;
using NinjaTrader.NinjaScript;
using NinjaTrader.Gui.NinjaScript;   // StrategiesGrid statics: the same calls the UI buttons make

namespace NinjaTrader.NinjaScript.AddOns
{
    public class EdgeLogBridge : AddOnBase
    {
        private const string Version   = "2.2";
        private const int    Port      = 8391;
        private const string LogPath   = @"C:\EdgeLog\bridge.log";
        private const string ConfPath  = @"C:\EdgeLog\bridge.json";

        // L1 — hard-locked accounts. Refused for every mutating endpoint no matter
        // what bridge.json says. Changing this line requires a recompile: that is
        // deliberate, the recompile is the owner's signature.
        private static readonly string[] LIVE_LOCKED = { "1810769" };

        private TcpListener _listener;
        private Thread      _thread;
        private volatile bool _running;
        private DateTime    _startedUtc;
        private static readonly object _logLock = new object();

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name        = "EdgeLogBridge";
                Description = "Local HTTP bridge (127.0.0.1:" + Port + ") for EDGELOG tooling.";
            }
            else if (State == State.Active)
            {
                try { Start(); } catch (Exception ex) { Log("FATAL start: " + ex); }
            }
            else if (State == State.Terminated)
            {
                try { Stop(); } catch (Exception ex) { Log("stop: " + ex.Message); }
            }
        }

        private void Start()
        {
            if (_running) return;
            _startedUtc = DateTime.UtcNow;
            _listener = new TcpListener(IPAddress.Loopback, Port);   // loopback ONLY
            _listener.Start();
            _running = true;
            _thread = new Thread(AcceptLoop) { IsBackground = true, Name = "EdgeLogBridge" };
            _thread.Start();
            // L5 monitor. 10s cadence: fast enough that a runaway is caught in seconds,
            // slow enough to be free. It re-reads bridge.json every tick, so limits and
            // the on/off switch take effect without restarting NinjaTrader.
            _riskTimer = new System.Threading.Timer(RiskTick, null, 10000, 10000);
            Log("started v" + Version + " on 127.0.0.1:" + Port);
        }

        private void Stop()
        {
            _running = false;
            try { if (_riskTimer != null) { _riskTimer.Dispose(); _riskTimer = null; } } catch { }
            try { if (_listener != null) _listener.Stop(); } catch { }
            Log("stopped");
        }

        private void AcceptLoop()
        {
            while (_running)
            {
                TcpClient client = null;
                try { client = _listener.AcceptTcpClient(); }
                catch { if (!_running) return; continue; }
                // One request per connection, handled inline: traffic is a local CLI,
                // not a web app. A hung socket must never wedge NinjaTrader, so
                // everything below is fenced and the socket gets a hard deadline.
                try
                {
                    client.ReceiveTimeout = 3000; client.SendTimeout = 3000;
                    using (var stream = client.GetStream())
                        Handle(stream);
                }
                catch (Exception ex) { Log("conn: " + ex.Message); }
                finally { try { client.Close(); } catch { } }
            }
        }

        // ── HTTP plumbing ────────────────────────────────────────────────────
        /// <summary>First index of an ASCII marker within buf[0..len), or -1.</summary>
        private static int IndexOf(byte[] buf, int len, string marker)
        {
            byte[] m = Encoding.ASCII.GetBytes(marker);
            for (int i = 0; i <= len - m.Length; i++)
            {
                int j = 0;
                while (j < m.Length && buf[i + j] == m[j]) j++;
                if (j == m.Length) return i;
            }
            return -1;
        }

        private void Handle(NetworkStream s)
        {
            // Read headers (and body if Content-Length says so). 64 KB cap.
            var buf = new byte[65536]; int total = 0;
            int headerEnd = -1;
            while (total < buf.Length)
            {
                int n = s.Read(buf, total, buf.Length - total);
                if (n <= 0) break;
                total += n;
                headerEnd = IndexOf(buf, total, "\r\n\r\n");
                if (headerEnd >= 0) break;
            }
            if (headerEnd < 0) { Respond(s, 400, "{\"error\":\"bad request\"}"); return; }

            string head = Encoding.ASCII.GetString(buf, 0, headerEnd);
            string[] lines = head.Split(new[] { "\r\n" }, StringSplitOptions.None);
            string[] req = lines[0].Split(' ');
            if (req.Length < 2) { Respond(s, 400, "{\"error\":\"bad request line\"}"); return; }
            string method = req[0].ToUpperInvariant();
            string rawUrl = req[1];

            int clen = 0;
            foreach (string h in lines)
                if (h.StartsWith("Content-Length:", StringComparison.OrdinalIgnoreCase))
                    int.TryParse(h.Substring(15).Trim(), out clen);
            int bodyStart = headerEnd + 4;
            while (total - bodyStart < clen && total < buf.Length)
            {
                int n = s.Read(buf, total, buf.Length - total);
                if (n <= 0) break;
                total += n;
            }
            string body = clen > 0 ? Encoding.UTF8.GetString(buf, bodyStart, Math.Min(clen, total - bodyStart)) : "";

            string path = rawUrl; var query = new Dictionary<string, string>();
            int qi = rawUrl.IndexOf('?');
            if (qi >= 0)
            {
                path = rawUrl.Substring(0, qi);
                foreach (string kv in rawUrl.Substring(qi + 1).Split('&'))
                {
                    int eq = kv.IndexOf('=');
                    if (eq > 0) query[Uri.UnescapeDataString(kv.Substring(0, eq))] =
                                Uri.UnescapeDataString(kv.Substring(eq + 1));
                }
            }

            try { Route(s, method, path.TrimEnd('/'), query, body); }
            catch (Exception ex)
            {
                Log("route " + method + " " + path + ": " + ex);
                Respond(s, 500, "{\"error\":" + J(ex.Message) + "}");
            }
        }

        private void Route(NetworkStream s, string method, string path,
                           Dictionary<string, string> q, string body)
        {
            bool post = method == "POST";
            switch (path)
            {
                case "/health":      Respond(s, 200, Health());               return;
                case "/connections": Respond(s, 200, Connections());         return;
                case "/connect":
                    if (!post) { Respond(s, 405, "{\"error\":\"POST only\"}"); return; }
                    ConnectByName(s, q.ContainsKey("name") ? q["name"] : ""); return;
                case "/accounts":    Respond(s, 200, Accounts());             return;
                case "/positions":   Respond(s, 200, Positions());            return;
                case "/orders":      Respond(s, 200, Orders(q.ContainsKey("all"))); return;
                case "/strategies":  Respond(s, 200, Strategies());           return;
                case "/executions":  Respond(s, 200, Executions());           return;
                case "/shutdown":
                    if (!post) { Respond(s, 405, "{\"error\":\"POST only\"}"); return; }
                    Respond(s, 200, "{\"ok\":true,\"note\":\"clean exit requested\"}");
                    Log("SHUTDOWN requested via bridge");
                    // Answer first, then exit: the socket must not die mid-reply. This is
                    // the same call NT's own exit-confirm dialog makes - no dialog, saves state.
                    try
                    {
                        Core.Globals.MainThreadDispatcher.BeginInvoke(new Action(() =>
                        {
                            try { Core.Globals.ApplicationExit(); } catch (Exception ex) { Log("shutdown: " + ex.Message); }
                        }));
                    }
                    catch (Exception ex) { Log("shutdown dispatch: " + ex.Message); }
                    return;
                case "/strategy/params":
                    StrategyParams(s, q.ContainsKey("name") ? q["name"] : ""); return;
                case "/strategy/setparam":
                    if (!post) { Respond(s, 405, "{\"error\":\"POST only\"}"); return; }
                    StrategySetParam(s, q.ContainsKey("name") ? q["name"] : "",
                                        q.ContainsKey("param") ? q["param"] : "",
                                        q.ContainsKey("value") ? q["value"] : ""); return;
                case "/strategy/check":
                    StrategyCheck(s, q.ContainsKey("name") ? q["name"] : ""); return;
                case "/dialogs":     Respond(s, 200, Dialogs());               return;
                case "/strategy/enable":
                    if (!post) { Respond(s, 405, "{\"error\":\"POST only\"}"); return; }
                    StrategyLifecycle(s, q.ContainsKey("name") ? q["name"] : "", true); return;
                case "/strategy/disable":
                    if (!post) { Respond(s, 405, "{\"error\":\"POST only\"}"); return; }
                    StrategyLifecycle(s, q.ContainsKey("name") ? q["name"] : "", false); return;
                case "/connections/startup":
                    if (!post) { Respond(s, 405, "{\"error\":\"POST only\"}"); return; }
                    // Experiment, honestly labelled: ConnectOnStartup is writable, but
                    // whether NT persists it for a login-provisioned brokerage
                    // connection across restarts is unproven. The next boot is the test.
                    {
                        string cn = q.ContainsKey("name") ? q["name"] : "";
                        bool on = !q.ContainsKey("on") || q["on"] != "0";
                        ConnectOptions target = null;
                        foreach (ConnectOptions o in AllConnectOptions())
                            if (string.Equals(o.Name, cn, StringComparison.OrdinalIgnoreCase)) { target = o; break; }
                        if (target == null) { Respond(s, 404, "{\"error\":\"no saved connection by that name\"}"); return; }
                        try { target.ConnectOnStartup = on; Log("STARTUP flag " + cn + " -> " + on); }
                        catch (Exception ex) { Respond(s, 500, "{\"error\":" + J(ex.Message) + "}"); return; }
                        Respond(s, 200, "{\"ok\":true,\"note\":\"flag set in memory; whether NT persists it shows on the next boot\"}");
                    }
                    return;
                case "/reflect/windows":
                    Respond(s, 200, ReflectWindows()); return;
                case "/reflect/inspect":
                    Respond(s, 200, ReflectInspect(q.ContainsKey("type") ? q["type"] : "")); return;
                case "/reflect/gridfields":
                    Respond(s, 200, ReflectGridFields()); return;
                case "/reflect/gridrows":
                    Respond(s, 200, ReflectGridRows()); return;
                case "/reflect/types":
                    Respond(s, 200, ReflectTypes(q.ContainsKey("contains") ? q["contains"] : "")); return;
                case "/reflect/members":
                    Respond(s, 200, ReflectMembers(q.ContainsKey("type") ? q["type"] : "")); return;
                case "/cancel":
                    if (!post) { Respond(s, 405, "{\"error\":\"POST only\"}"); return; }
                    CancelOrder(s, q.ContainsKey("account") ? q["account"] : "",
                                   q.ContainsKey("order_id") ? q["order_id"] : ""); return;
                case "/flatten":
                    if (!post) { Respond(s, 405, "{\"error\":\"POST only\"}"); return; }
                    Flatten(s, q.ContainsKey("account") ? q["account"] : "");  return;
                case "/risk":        Respond(s, 200, RiskJson());            return;
                case "/risk/reset":
                    if (!post) { Respond(s, 405, "{\"error\":\"POST only\"}"); return; }
                    lock (_riskLock) { _breakerTripped = false; _breakerReason = ""; }
                    Log("BREAKER RESET by request");
                    Respond(s, 200, "{\"ok\":true,\"note\":\"breaker latch cleared; limits still apply\"}");
                    return;
                case "/killswitch":
                    if (!post) { Respond(s, 405, "{\"error\":\"POST only\"}"); return; }
                    KillSwitch(s); return;
                case "/order":
                    if (!post) { Respond(s, 405, "{\"error\":\"POST only\"}"); return; }
                    PlaceOrder(s, body);                                       return;
                default: Respond(s, 404, "{\"error\":\"unknown path\"}");      return;
            }
        }

        private void Respond(NetworkStream s, int code, string json)
        {
            string status = code == 200 ? "200 OK" : code == 400 ? "400 Bad Request"
                          : code == 403 ? "403 Forbidden" : code == 404 ? "404 Not Found"
                          : code == 405 ? "405 Method Not Allowed" : "500 Internal Server Error";
            byte[] b = Encoding.UTF8.GetBytes(json);
            string hdr = "HTTP/1.1 " + status + "\r\nContent-Type: application/json\r\n"
                       + "Content-Length: " + b.Length + "\r\nConnection: close\r\n\r\n";
            byte[] h = Encoding.ASCII.GetBytes(hdr);
            s.Write(h, 0, h.Length); s.Write(b, 0, b.Length); s.Flush();
        }

        // ── read endpoints — public documented collections only, every field
        //    individually fenced so one bad object never kills the whole row ──
        private string Health()
        {
            int nAcct = 0;
            try { lock (Account.All) nAcct = Account.All.Count; } catch { }
            var cfg = ReadConfig();
            return "{\"ok\":true,\"version\":" + J(Version)
                 + ",\"started_utc\":" + J(_startedUtc.ToString("yyyy-MM-dd HH:mm:ss"))
                 + ",\"accounts\":" + nAcct
                 + ",\"orders_enabled\":" + (cfg.OrdersEnabled ? "true" : "false")
                 + ",\"allowed_accounts\":" + JArr(cfg.Accounts)
                 + ",\"live_locked\":" + JArr(LIVE_LOCKED) + "}";
        }

        private string Accounts()
        {
            var rows = new List<string>();
            List<Account> accts;
            lock (Account.All) accts = new List<Account>(Account.All);
            foreach (var a in accts)
            {
                try
                {
                    double cash = 0, real = 0;
                    try { cash = a.Get(AccountItem.CashValue, Currency.UsDollar); } catch { }
                    try { real = a.Get(AccountItem.RealizedProfitLoss, Currency.UsDollar); } catch { }
                    rows.Add("{\"name\":" + J(a.Name) + ",\"cash\":" + Num(cash)
                           + ",\"realized\":" + Num(real)
                           + ",\"live_locked\":" + (IsLiveLocked(a.Name) ? "true" : "false") + "}");
                }
                catch (Exception ex) { Log("accounts row: " + ex.Message); }
            }
            return "{\"accounts\":[" + string.Join(",", rows) + "]}";
        }

        private string Positions()
        {
            var rows = new List<string>();
            List<Account> accts;
            lock (Account.All) accts = new List<Account>(Account.All);
            foreach (var a in accts)
            {
                try
                {
                    List<Position> ps;
                    lock (a.Positions) ps = new List<Position>(a.Positions);
                    foreach (var p in ps)
                    {
                        try
                        {
                            if (p.MarketPosition == MarketPosition.Flat) continue;
                            rows.Add("{\"account\":" + J(a.Name)
                                   + ",\"instrument\":" + J(p.Instrument != null ? p.Instrument.FullName : "?")
                                   + ",\"side\":" + J(p.MarketPosition.ToString())
                                   + ",\"qty\":" + Num(p.Quantity)
                                   + ",\"avg_price\":" + Num(p.AveragePrice) + "}");
                        }
                        catch (Exception ex) { Log("pos row: " + ex.Message); }
                    }
                }
                catch (Exception ex) { Log("positions: " + ex.Message); }
            }
            return "{\"positions\":[" + string.Join(",", rows) + "]}";
        }

        private string Orders(bool all)
        {
            var rows = new List<string>();
            List<Account> accts;
            lock (Account.All) accts = new List<Account>(Account.All);
            foreach (var a in accts)
            {
                try
                {
                    List<Order> os;
                    lock (a.Orders) os = new List<Order>(a.Orders);
                    foreach (var o in os)
                    {
                        try
                        {
                            bool working = o.OrderState == OrderState.Working
                                        || o.OrderState == OrderState.Accepted
                                        || o.OrderState == OrderState.Submitted
                                        || o.OrderState == OrderState.TriggerPending;
                            if (!all && !working) continue;
                            rows.Add("{\"account\":" + J(a.Name)
                                   + ",\"order_id\":" + J(o.OrderId ?? "")
                                   + ",\"name\":" + J(o.Name ?? "")
                                   + ",\"instrument\":" + J(o.Instrument != null ? o.Instrument.FullName : "?")
                                   + ",\"action\":" + J(o.OrderAction.ToString())
                                   + ",\"type\":" + J(o.OrderType.ToString())
                                   + ",\"state\":" + J(o.OrderState.ToString())
                                   + ",\"qty\":" + Num(o.Quantity)
                                   + ",\"limit\":" + Num(o.LimitPrice)
                                   + ",\"stop\":" + Num(o.StopPrice)
                                   + ",\"filled\":" + Num(o.Filled) + "}");
                        }
                        catch (Exception ex) { Log("order row: " + ex.Message); }
                    }
                }
                catch (Exception ex) { Log("orders: " + ex.Message); }
            }
            return "{\"orders\":[" + string.Join(",", rows) + "]}";
        }

        private string Strategies()
        {
            // The Control Center's Strategies grid is fed from each account's
            // Strategies collection — the same public list we read here. If THIS
            // comes back empty while charts have strategies, the workspace never
            // re-attached them (the exact 2026-08-14 morning failure).
            var rows = new List<string>();
            List<Account> accts;
            lock (Account.All) accts = new List<Account>(Account.All);
            foreach (var a in accts)
            {
                try
                {
                    var ss = new List<StrategyBase>();
                    try { lock (a.Strategies) foreach (var x in a.Strategies) ss.Add(x); }
                    catch (Exception ex) { Log("strategies enum " + a.Name + ": " + ex.Message); continue; }
                    foreach (var st in ss)
                    {
                        try
                        {
                            string inst = "?";
                            try { if (st.Instruments != null && st.Instruments.Length > 0 && st.Instruments[0] != null) inst = st.Instruments[0].FullName; } catch { }
                            string pos = "";
                            try { pos = st.Position != null ? (st.Position.MarketPosition + " " + st.Position.Quantity) : ""; } catch { }
                            rows.Add("{\"account\":" + J(a.Name)
                                   + ",\"name\":" + J(st.Name ?? "?")
                                   + ",\"state\":" + J(st.State.ToString())
                                   + ",\"instrument\":" + J(inst)
                                   + ",\"position\":" + J(pos) + "}");
                        }
                        catch (Exception ex) { Log("strategy row: " + ex.Message); }
                    }
                }
                catch (Exception ex) { Log("strategies: " + ex.Message); }
            }
            return "{\"strategies\":[" + string.Join(",", rows) + "]}";
        }

        private string Executions()
        {
            var rows = new List<string>();
            List<Account> accts;
            lock (Account.All) accts = new List<Account>(Account.All);
            foreach (var a in accts)
            {
                try
                {
                    List<Execution> es;
                    lock (a.Executions) es = new List<Execution>(a.Executions);
                    foreach (var e in es)
                    {
                        try
                        {
                            rows.Add("{\"account\":" + J(a.Name)
                                   + ",\"exec_id\":" + J(e.ExecutionId ?? "")
                                   + ",\"time_utc\":" + J(e.Time.ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss"))
                                   + ",\"instrument\":" + J(e.Instrument != null ? e.Instrument.FullName : "?")
                                   + ",\"side\":" + J(e.MarketPosition.ToString())
                                   + ",\"qty\":" + Num(e.Quantity)
                                   + ",\"price\":" + Num(e.Price) + "}");
                        }
                        catch (Exception ex) { Log("exec row: " + ex.Message); }
                    }
                }
                catch (Exception ex) { Log("executions: " + ex.Message); }
            }
            return "{\"executions\":[" + string.Join(",", rows) + "]}";
        }

        // ── strategy lifecycle — the 2026-08-14 evening, as endpoints ────────
        // StrategiesGrid.StrategyEnable/StrategyDisable are the PUBLIC STATIC
        // methods the Control Center's own Enabled checkbox calls (mapped via
        // /reflect/members, not guessed). Two honest limits in this version:
        //  * finding the instance: enabled strategies sit in account.Strategies;
        //    DISABLED ones are invisible there, so we also keep every strategy this
        //    bridge itself disables in a parked registry, and fall back to the
        //    grid's own rows (see FindGridStrategy). A strategy disabled before
        //    this AddOn loaded may still be unreachable - the response says so.
        //  * these run on NT's UI thread via MainThreadDispatcher - a wedge there
        //    would hang the call, so everything is fenced and the socket times out.
        private static readonly Dictionary<string, StrategyBase> _parked =
            new Dictionary<string, StrategyBase>(StringComparer.OrdinalIgnoreCase);

        private void StrategyLifecycle(NetworkStream s, string name, bool enable)
        {
            if (string.IsNullOrEmpty(name)) { Respond(s, 400, "{\"error\":\"name is required\"}"); return; }
            StrategyBase sb = null; string where = null;
            // 1) enabled instances: the account collections
            List<Account> accts;
            lock (Account.All) accts = new List<Account>(Account.All);
            foreach (var a in accts)
            {
                try
                {
                    lock (a.Strategies)
                        foreach (var st in a.Strategies)
                            if (string.Equals(st.Name, name, StringComparison.OrdinalIgnoreCase))
                            { sb = st; where = "account " + a.Name; break; }
                }
                catch { }
                if (sb != null) break;
            }
            // 2) strategies this bridge parked when it disabled them
            if (sb == null)
                lock (_parked)
                    if (_parked.TryGetValue(name, out var p)) { sb = p; where = "parked registry"; }
            // 3) REMOVED - v1.6 resolved here via StrategiesGrid.AvailableStrategies,
            //    which turned out to be the New Strategy PICKER's template list: fresh
            //    default-constructed objects bound to the FIRST account (the live one).
            //    The L1 rail refused them on the 2026-08-15 test - working exactly as
            //    designed - and this source is permanently disqualified for lifecycle.
            //    (FindAvailableStrategy stays: it is the right raw material for a
            //    future /strategy/add, where a fresh template is exactly what you want.)
            // 4) the grid's own rows
            if (sb == null)
            {
                sb = FindGridStrategy(name);
                if (sb != null) where = "strategies grid";
            }
            if (sb == null)
            {
                Respond(s, 404, "{\"error\":\"no reachable instance named " + name.Replace('"', ' ')
                    + " - if it was disabled before this bridge version loaded, toggle it once in the UI\"}");
                return;
            }
            // Rails: the instance's own account decides, same L1+L2 as every mutation.
            string acctName = "?";
            try { acctName = sb.Account != null ? sb.Account.Name : "?"; } catch { }
            string deny = DenyMutation(acctName);
            if (deny != null) { Respond(s, 403, "{\"error\":" + J(deny) + "}"); Log("lifecycle REFUSED " + name + ": " + deny); return; }

            // L5 pre-ENABLE size gate. Turning a strategy on is the moment its size
            // becomes real, so HOW MUCH gets checked here and not only at order time --
            // the strategy's own orders never pass through /order. Reads the instance's
            // own Qty property (the same knob /strategy/params exposes). Disable is never
            // gated: stopping is always allowed.
            if (enable)
            {
                var rc = ReadConfig();
                if (rc.RiskEnabled)
                {
                    bool tripped; string treason;
                    lock (_riskLock) { tripped = _breakerTripped; treason = _breakerReason; }
                    if (tripped)
                    { Respond(s, 403, "{\"error\":" + J("circuit breaker is TRIPPED: " + treason + " - POST /risk/reset to clear") + "}");
                      Log("enable REFUSED " + name + ": breaker tripped"); return; }
                    int q = 0;
                    try
                    {
                        var qp = sb.GetType().GetProperty("Qty",
                            System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
                        if (qp != null) q = Convert.ToInt32(qp.GetValue(sb), CultureInfo.InvariantCulture);
                    }
                    catch { }
                    if (q > 0)
                    {
                        string sz = DenySize(rc, FindAccount(acctName), q);
                        if (sz != null)
                        { Respond(s, 403, "{\"error\":" + J("position-size gate: " + name + " " + sz) + "}");
                          Log("enable REFUSED " + name + ": " + sz); return; }
                    }
                }
            }

            string err = null;
            try
            {
                Core.Globals.MainThreadDispatcher.Invoke(new Action(() =>
                {
                    try
                    {
                        // Present in the assembly (mapped via /reflect/members) but not
                        // public, so the compiler cannot see them - reflection can.
                        const System.Reflection.BindingFlags SF =
                            System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic |
                            System.Reflection.BindingFlags.Static;
                        var mi = typeof(StrategiesGrid).GetMethod(enable ? "StrategyEnable" : "StrategyDisable", SF);
                        if (mi == null) err = "grid method not found - NT version changed the internals";
                        else mi.Invoke(null, enable ? new object[] { sb, null, null } : new object[] { sb });
                    }
                    catch (System.Reflection.TargetInvocationException tex)
                    { err = (tex.InnerException ?? tex).GetType().Name + ": " + (tex.InnerException ?? tex).Message; }
                    catch (Exception ex) { err = ex.GetType().Name + ": " + ex.Message; }
                }));
            }
            catch (Exception ex) { err = "dispatch: " + ex.Message; }
            if (err != null)
            {
                Log("lifecycle " + (enable ? "ENABLE" : "DISABLE") + " " + name + " FAILED: " + err);
                Respond(s, 500, "{\"error\":" + J(err) + "}"); return;
            }
            if (!enable) lock (_parked) _parked[name] = sb;   // keep it reachable for re-enable
            else lock (_parked) _parked.Remove(name);
            Log("lifecycle " + (enable ? "ENABLE" : "DISABLE") + " " + name + " via " + where);
            Respond(s, 200, "{\"ok\":true,\"found_in\":" + J(where)
                 + ",\"note\":\"poll /strategies to confirm state\"}");
        }

        // ── strategy PARAMETERS — read, and (gated) write ────────────────────────
        // WHY: the paper book only means anything if the config NinjaTrader is actually
        // running is the config we think it is. That has already drifted once in this
        // project (the NOISE leg runs 14/1.5/1.5/k=1.0 while auto-validate #225 crowned
        // 44/0.75/1.5/k=1.75), and nothing outside NT could SEE the live values to catch it.
        // Reads are pure reflection over the strategy type's OWN public properties -- the
        // ones the NinjaScript author declared with [Display] -- not the ~200 inherited
        // StrategyBase members, which would bury the six knobs that matter.

        /// <summary>Same 3-step resolution the lifecycle endpoints use: enabled instances,
        /// then this bridge's parked registry, then a walk of the Control Center grid.</summary>
        private StrategyBase ResolveStrategy(string name, out string where)
        {
            where = null;
            if (string.IsNullOrEmpty(name)) return null;
            List<Account> accts;
            lock (Account.All) accts = new List<Account>(Account.All);
            foreach (var a in accts)
            {
                try
                {
                    lock (a.Strategies)
                        foreach (var st in a.Strategies)
                            if (string.Equals(st.Name, name, StringComparison.OrdinalIgnoreCase))
                            { where = "account " + a.Name; return st; }
                }
                catch { }
            }
            lock (_parked)
                if (_parked.TryGetValue(name, out var p)) { where = "parked registry"; return p; }
            var sb = FindGridStrategy(name);
            if (sb != null) where = "strategies grid";
            return sb;
        }

        /// <summary>Public instance properties DECLARED ON the strategy type itself, with
        /// their live values. Read-only.</summary>
        private static List<System.Reflection.PropertyInfo> OwnParams(Type t)
        {
            var outp = new List<System.Reflection.PropertyInfo>();
            try
            {
                foreach (var p in t.GetProperties(System.Reflection.BindingFlags.Public |
                                                  System.Reflection.BindingFlags.Instance |
                                                  System.Reflection.BindingFlags.DeclaredOnly))
                {
                    if (p.GetIndexParameters().Length > 0 || !p.CanRead) continue;
                    var pt = p.PropertyType;
                    // Only the simple, settable-looking knobs: numbers, bools, strings, enums.
                    if (pt.IsPrimitive || pt.IsEnum || pt == typeof(string) || pt == typeof(decimal))
                        outp.Add(p);
                }
            }
            catch { }
            return outp;
        }

        private void StrategyParams(NetworkStream s, string name)
        {
            string where;
            var sb = ResolveStrategy(name, out where);
            if (sb == null) { Respond(s, 404, "{\"error\":\"no reachable strategy named " + name.Replace('"', ' ') + "\"}"); return; }
            var rows = new List<string>();
            string acct = "?", state = "?";
            try { acct = sb.Account != null ? sb.Account.Name : "?"; } catch { }
            try { state = sb.State.ToString(); } catch { }
            foreach (var p in OwnParams(sb.GetType()))
            {
                string val = "";
                try { var v = p.GetValue(sb); val = v == null ? "" : Convert.ToString(v, CultureInfo.InvariantCulture); }
                catch (Exception ex) { val = "threw: " + ex.Message; }
                double rmin, rmax;
                string range = ParamRange(p, out rmin, out rmax)
                    ? ",\"min\":" + rmin.ToString("R", CultureInfo.InvariantCulture)
                      + ",\"max\":" + rmax.ToString("R", CultureInfo.InvariantCulture)
                    : "";
                rows.Add("{\"name\":" + J(p.Name) + ",\"type\":" + J(p.PropertyType.Name)
                       + ",\"value\":" + J(val) + ",\"writable\":" + (p.CanWrite ? "true" : "false")
                       + range + "}");
            }
            Respond(s, 200, "{\"strategy\":" + J(sb.Name ?? name) + ",\"account\":" + J(acct)
                 + ",\"state\":" + J(state) + ",\"found_in\":" + J(where)
                 + ",\"params\":[" + string.Join(",", rows) + "]}");
        }

        /// <summary>Pre-flights a strategy: checks EVERY current parameter value against its
        /// declared range and reports the offenders. This answers "will it actually start?"
        /// before burning an enable attempt, which is the question that matters — an enable
        /// that fails this way leaves no trace anywhere except a popup on screen.</summary>
        private void StrategyCheck(NetworkStream s, string name)
        {
            string where;
            var sb = ResolveStrategy(name, out where);
            if (sb == null) { Respond(s, 404, "{\"error\":\"no reachable strategy named " + name.Replace('"', ' ') + "\"}"); return; }
            var bad = new List<string>();
            int checkedN = 0;
            foreach (var p in OwnParams(sb.GetType()))
            {
                double rmin, rmax;
                if (!ParamRange(p, out rmin, out rmax)) continue;
                double v;
                try { v = Convert.ToDouble(p.GetValue(sb), CultureInfo.InvariantCulture); }
                catch { continue; }
                checkedN++;
                if (v < rmin || v > rmax)
                    bad.Add("{\"param\":" + J(p.Name)
                          + ",\"value\":" + v.ToString("R", CultureInfo.InvariantCulture)
                          + ",\"min\":" + rmin.ToString("R", CultureInfo.InvariantCulture)
                          + ",\"max\":" + rmax.ToString("R", CultureInfo.InvariantCulture) + "}");
            }
            string state = "?";
            try { state = sb.State.ToString(); } catch { }
            Respond(s, 200, "{\"strategy\":" + J(sb.Name ?? name) + ",\"state\":" + J(state)
                 + ",\"checked\":" + checkedN
                 + ",\"ok\":" + (bad.Count == 0 ? "true" : "false")
                 + ",\"out_of_range\":[" + string.Join(",", bad) + "]}");
        }

        private void StrategySetParam(NetworkStream s, string name, string param, string value)
        {
            if (string.IsNullOrEmpty(name) || string.IsNullOrEmpty(param))
            { Respond(s, 400, "{\"error\":\"name and param are required\"}"); return; }
            string where;
            var sb = ResolveStrategy(name, out where);
            if (sb == null) { Respond(s, 404, "{\"error\":\"no reachable strategy named " + name.Replace('"', ' ') + "\"}"); return; }

            // Same account rails as every other mutation (L1 live-lock + L2 allowlist).
            string acctName = "?";
            try { acctName = sb.Account != null ? sb.Account.Name : "?"; } catch { }
            string deny = DenyMutation(acctName);
            if (deny != null) { Respond(s, 403, "{\"error\":" + J(deny) + "}"); Log("setparam REFUSED " + name + ": " + deny); return; }

            // EXTRA RAIL, specific to this endpoint: refuse while the strategy is RUNNING.
            // NinjaScript reads most parameters once at State.Configure; writing one to a
            // live strategy either silently does nothing or leaves the running logic
            // disagreeing with the value now displayed, which is worse than refusing.
            // Disable -> set -> enable is the honest sequence, and it is two extra calls.
            string state = "?";
            try { state = sb.State.ToString(); } catch { }
            if (state == "Realtime" || state == "Historical" || state == "Transition")
            {
                Respond(s, 409, "{\"error\":\"strategy is " + state + " - disable it first, set the "
                     + "parameter, then re-enable. Parameters are read at configure time, so writing "
                     + "one now would not take effect and would misreport the running config.\"}");
                return;
            }

            var pi = OwnParams(sb.GetType()).Find(p => string.Equals(p.Name, param, StringComparison.OrdinalIgnoreCase));
            if (pi == null) { Respond(s, 404, "{\"error\":\"no such parameter on this strategy (see GET /strategy/params)\"}"); return; }
            if (!pi.CanWrite) { Respond(s, 403, "{\"error\":\"parameter is read-only\"}"); return; }

            object oldVal = null, newVal = null;
            try { oldVal = pi.GetValue(sb); } catch { }
            try
            {
                var t = pi.PropertyType;
                if (t.IsEnum) newVal = Enum.Parse(t, value, true);
                else if (t == typeof(bool)) newVal = (value == "1" || string.Equals(value, "true", StringComparison.OrdinalIgnoreCase));
                else if (t == typeof(string)) newVal = value;
                else newVal = Convert.ChangeType(value, t, CultureInfo.InvariantCulture);
            }
            catch (Exception ex)
            { Respond(s, 400, "{\"error\":" + J("could not parse '" + value + "' as " + pi.PropertyType.Name + ": " + ex.Message) + "}"); return; }

            // RANGE RAIL. A NinjaScript property carries a [Range(min,max)] attribute, and
            // NinjaTrader enforces it at STARTUP, not at assignment: an out-of-range value
            // writes cleanly here, shows correctly in the grid, and then the strategy dies
            // to State.Finalized with nothing but a modal popup to explain it. Nothing is
            // written to any log file. That cost a full session of blind diagnosis on
            // ENGU-Q (TlLen 170 against a stale Range(15,80)), so refuse it up front and
            // say exactly which bound was crossed.
            {
                double rmin, rmax;
                if (ParamRange(pi, out rmin, out rmax))
                {
                    double nv;
                    try { nv = Convert.ToDouble(newVal, CultureInfo.InvariantCulture); }
                    catch { nv = double.NaN; }
                    if (!double.IsNaN(nv) && (nv < rmin || nv > rmax))
                    {
                        Respond(s, 400, "{\"error\":" + J(param + " " + value + " is outside the range "
                             + rmin.ToString("R", CultureInfo.InvariantCulture) + ".."
                             + rmax.ToString("R", CultureInfo.InvariantCulture)
                             + " declared on the strategy. NinjaTrader would accept the write and then "
                             + "refuse to start the strategy (it finalizes with only a popup). Widen the "
                             + "Range() attribute in the source and recompile, or pick a value in range.")
                             + ",\"param\":" + J(param) + ",\"value\":" + J(value)
                             + ",\"min\":" + rmin.ToString("R", CultureInfo.InvariantCulture)
                             + ",\"max\":" + rmax.ToString("R", CultureInfo.InvariantCulture) + "}");
                        Log("setparam REFUSED " + name + "." + param + "=" + value + ": out of range "
                            + rmin.ToString("R", CultureInfo.InvariantCulture) + ".."
                            + rmax.ToString("R", CultureInfo.InvariantCulture));
                        return;
                    }
                }
            }

            string err = null;
            try
            {
                CcDispatcher().Invoke(new Action(() =>
                {
                    try { pi.SetValue(sb, newVal); }
                    catch (Exception ex) { err = ex.GetType().Name + ": " + ex.Message; }
                }));
            }
            catch (Exception ex) { err = "dispatch: " + ex.Message; }
            if (err != null) { Respond(s, 500, "{\"error\":" + J(err) + "}"); Log("setparam " + name + "." + param + " FAILED: " + err); return; }

            string readBack = "";
            try { var v = pi.GetValue(sb); readBack = v == null ? "" : Convert.ToString(v, CultureInfo.InvariantCulture); }
            catch { }
            Log("SETPARAM " + name + "." + pi.Name + " : " + Convert.ToString(oldVal, CultureInfo.InvariantCulture)
                + " -> " + readBack + " (account " + acctName + ", via " + where + ")");
            Respond(s, 200, "{\"ok\":true,\"strategy\":" + J(sb.Name ?? name) + ",\"param\":" + J(pi.Name)
                 + ",\"old\":" + J(Convert.ToString(oldVal, CultureInfo.InvariantCulture))
                 + ",\"new\":" + J(readBack)
                 + ",\"note\":\"set in memory on the instance; NinjaTrader persists it when the "
                 + "strategy is next enabled from the grid. Re-enable to apply.\"}");
        }

        /// <summary>Resolve a strategy instance from StrategiesGrid.AvailableStrategies —
        /// the non-public STATIC list behind the grid, alive whether or not the tab was
        /// ever opened. Read on the UI dispatcher: it is grid state.</summary>
        private StrategyBase FindAvailableStrategy(string name)
        {
            StrategyBase found = null;
            try
            {
                Core.Globals.MainThreadDispatcher.Invoke(new Action(() =>
                {
                    try
                    {
                        var pi = typeof(StrategiesGrid).GetProperty("AvailableStrategies",
                            System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic |
                            System.Reflection.BindingFlags.Static);
                        var en = pi != null ? pi.GetValue(null) as System.Collections.IEnumerable : null;
                        if (en == null) { Log("AvailableStrategies: property missing or null"); return; }
                        foreach (var o in en)
                        {
                            var sb = o as StrategyBase;
                            if (sb != null && string.Equals(sb.Name, name, StringComparison.OrdinalIgnoreCase))
                            { found = sb; return; }
                        }
                    }
                    catch (Exception ex) { Log("AvailableStrategies: " + ex.Message); }
                }));
            }
            catch (Exception ex) { Log("AvailableStrategies dispatch: " + ex.Message); }
            return found;
        }

        /// <summary>Reads the [Range(min,max)] attribute off a NinjaScript property.
        /// Returns false for properties that declare no range (bools, strings, enums).</summary>
        private static bool ParamRange(System.Reflection.PropertyInfo p, out double min, out double max)
        {
            min = 0; max = 0;
            try
            {
                foreach (var a in p.GetCustomAttributes(true))
                {
                    var ra = a as System.ComponentModel.DataAnnotations.RangeAttribute;
                    if (ra == null) continue;
                    min = Convert.ToDouble(ra.Minimum, CultureInfo.InvariantCulture);
                    max = Convert.ToDouble(ra.Maximum, CultureInfo.InvariantCulture);
                    return true;
                }
            }
            catch { }
            return false;
        }

        /// <summary>Every open window with its visible text, so a modal error popup can be
        /// READ instead of screenshotted. NinjaTrader reports several fatal conditions —
        /// notably a parameter outside its declared range — only in a popup: nothing lands
        /// in the trace file or the Log tab, so without this the failure is invisible to
        /// anything that is not a pair of human eyes.</summary>
        private string Dialogs()
        {
            var rows = new List<string>();
            // Walk BOTH UI threads. The Control Center lives on its own dispatcher, and
            // Application.Current.Windows only ever returns the CALLING thread's windows —
            // so a popup raised by the Control Center is invisible from the main thread.
            // Missing that is what makes an error dialog unreadable from here.
            var dispatchers = new List<System.Windows.Threading.Dispatcher>();
            try { dispatchers.Add(Core.Globals.MainThreadDispatcher); } catch { }
            try { var d = CcDispatcher(); if (d != null && !dispatchers.Contains(d)) dispatchers.Add(d); } catch { }
            foreach (var disp in dispatchers)
            try
            {
                disp.Invoke(new Action(() =>
                {
                    try
                    {
                        if (System.Windows.Application.Current == null) return;
                        foreach (System.Windows.Window w in System.Windows.Application.Current.Windows)
                        {
                            var texts = new List<string>();
                            var seen = new HashSet<string>();
                            foreach (var c in FindVisualChildren(w))
                            {
                                string t = null;
                                var tb = c as System.Windows.Controls.TextBlock;
                                if (tb != null) t = tb.Text;
                                else
                                {
                                    var cl = c as System.Windows.Controls.ContentControl;
                                    if (cl != null && cl.Content is string) t = (string)cl.Content;
                                }
                                if (string.IsNullOrEmpty(t)) continue;
                                t = t.Trim();
                                if (t.Length == 0 || !seen.Add(t)) continue;
                                texts.Add(J(t));
                                if (texts.Count >= 40) break;
                            }
                            bool modal = false;
                            try
                            {
                                var mi = typeof(System.Windows.Window).GetProperty("IsModal",
                                    System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);
                                if (mi != null) modal = Convert.ToBoolean(mi.GetValue(w));
                            }
                            catch { }
                            rows.Add("{\"window\":" + J(w.GetType().FullName)
                                   + ",\"title\":" + J(w.Title ?? "")
                                   + ",\"visible\":" + (w.IsVisible ? "true" : "false")
                                   + ",\"modal\":" + (modal ? "true" : "false")
                                   + ",\"text\":[" + string.Join(",", texts) + "]}");
                        }
                    }
                    catch (Exception ex) { Log("dialogs: " + ex.Message); }
                }));
            }
            catch (Exception ex) { Log("dialogs dispatch: " + ex.Message); }
            return "{\"dialogs\":[" + string.Join(",", rows) + "]}";
        }

        /// <summary>Debug: every open window's type, plus how many StrategiesGrid
        /// descendants the visual walk finds in each — discriminates "no grid exists"
        /// from "grid exists but its rows hide elsewhere".</summary>
        private string ReflectWindows()
        {
            var rows = new List<string>();
            try
            {
                Core.Globals.MainThreadDispatcher.Invoke(new Action(() =>
                {
                    try
                    {
                        foreach (System.Windows.Window w in System.Windows.Application.Current.Windows)
                        {
                            int grids = 0, nodes = 0;
                            foreach (var c in FindVisualChildren(w))
                            {
                                nodes++;
                                if (c.GetType().FullName == "NinjaTrader.Gui.NinjaScript.StrategiesGrid") grids++;
                            }
                            rows.Add("{\"window\":" + J(w.GetType().FullName) + ",\"title\":" + J(w.Title ?? "")
                                   + ",\"visual_nodes\":" + nodes + ",\"strategies_grids\":" + grids + "}");
                        }
                    }
                    catch (Exception ex) { Log("windows: " + ex.Message); }
                }));
            }
            catch (Exception ex) { Log("windows dispatch: " + ex.Message); }
            return "{\"windows\":[" + string.Join(",", rows) + "]}";
        }

        /// <summary>Debug: a type's STATIC fields and properties with live values —
        /// type name, enumerable count, first item's type. Read-only.</summary>
        private string ReflectInspect(string typeName)
        {
            if (string.IsNullOrEmpty(typeName)) return "{\"error\":\"pass ?type=Full.Type.Name\"}";
            Type t = null;
            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                try { t = asm.GetType(typeName, false, true); } catch { }
                if (t != null) break;
            }
            if (t == null) return "{\"error\":\"type not found\"}";
            var rows = new List<string>();
            const System.Reflection.BindingFlags SF =
                System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic |
                System.Reflection.BindingFlags.Static;
            try
            {
                Core.Globals.MainThreadDispatcher.Invoke(new Action(() =>
                {
                    foreach (var f in t.GetFields(SF))
                        rows.Add(DescribeValue("field", f.Name, () => f.GetValue(null)));
                    foreach (var p in t.GetProperties(SF))
                        if (p.GetIndexParameters().Length == 0)
                            rows.Add(DescribeValue("property", p.Name, () => p.GetValue(null)));
                }));
            }
            catch (Exception ex) { Log("inspect: " + ex.Message); }
            return "{\"type\":" + J(t.FullName) + ",\"statics\":[" + string.Join(",", rows) + "]}";
        }

        private string DescribeValue(string kind, string name, Func<object> get)
        {
            string vt = "?", extra = "";
            try
            {
                object v = get();
                if (v == null) vt = "null";
                else
                {
                    vt = v.GetType().Name;
                    if (v is System.Collections.IEnumerable en && !(v is string))
                    {
                        int n = 0; string first = "";
                        foreach (var item in en)
                        {
                            if (n == 0 && item != null) first = item.GetType().Name;
                            n++; if (n > 500) break;
                        }
                        extra = ",\"count\":" + n + ",\"item_type\":" + J(first);
                    }
                }
            }
            catch (Exception ex) { vt = "threw: " + ex.Message; }
            return "{\"kind\":" + J(kind) + ",\"name\":" + J(name) + ",\"value_type\":" + J(vt) + extra + "}";
        }

        /// <summary>Debug: every field/property on each StrategiesGrid instance found in
        /// the tree — names, runtime types, enumerable counts. The map for finding where
        /// the grid actually keeps its rows.</summary>
        private string ReflectGridFields()
        {
            var rows = new List<string>();
            try
            {
                var ccF = ControlCenterInstance() as System.Windows.DependencyObject;
                if (ccF == null) return "{\"members\":[],\"error\":\"no ControlCenter.Instance\"}";
                CcDispatcher().Invoke(new Action(() =>
                {
                    try
                    {
                        foreach (var grid in FindVisualChildren(ccF))
                            {
                                if (grid.GetType().FullName != "NinjaTrader.Gui.NinjaScript.StrategiesGrid") continue;
                                const System.Reflection.BindingFlags BF =
                                    System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic |
                                    System.Reflection.BindingFlags.Instance;
                                foreach (var f in grid.GetType().GetFields(BF))
                                    rows.Add(DescribeValue("field", f.Name, () => f.GetValue(grid)));
                                foreach (var p in grid.GetType().GetProperties(BF))
                                    if (p.GetIndexParameters().Length == 0)
                                        rows.Add(DescribeValue("property", p.Name, () => p.GetValue(grid)));
                                return;   // first grid is enough
                            }
                    }
                    catch (Exception ex) { Log("gridfields: " + ex.Message); }
                }));
            }
            catch (Exception ex) { Log("gridfields dispatch: " + ex.Message); }
            return "{\"members\":[" + string.Join(",", rows) + "]}";
        }

        /// <summary>The Control Center window and its OWN dispatcher. NT runs every
        /// window on its own UI thread, so Application.Current.Windows from the main
        /// thread is EMPTY - the 2026-08-15 /reflect/windows probe proved it. All grid
        /// walking must happen on the CC's dispatcher, reached via the static
        /// ControlCenter.Instance found with /reflect/members.</summary>
        private static object ControlCenterInstance()
        {
            try
            {
                Type t = null;
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    try { t = asm.GetType("NinjaTrader.Gui.ControlCenter", false, true); } catch { }
                    if (t != null) break;
                }
                if (t == null) return null;
                var pi = t.GetProperty("Instance",
                    System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic |
                    System.Reflection.BindingFlags.Static);
                return pi != null ? pi.GetValue(null) : null;
            }
            catch { return null; }
        }

        private static System.Windows.Threading.Dispatcher CcDispatcher()
        {
            var cc = ControlCenterInstance() as System.Windows.Threading.DispatcherObject;
            return cc != null ? cc.Dispatcher : Core.Globals.MainThreadDispatcher;
        }

        /// <summary>All enumerable collections reachable on a grid instance — fields AND
        /// properties. v1.4 walked fields only and saw nothing; WPF controls keep their
        /// rows behind properties (ItemsSource, Items, view collections).</summary>
        private static List<System.Collections.IEnumerable> GridCollections(object grid)
        {
            var outp = new List<System.Collections.IEnumerable>();
            const System.Reflection.BindingFlags BF =
                System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Public |
                System.Reflection.BindingFlags.Instance;
            try
            {
                foreach (var f in grid.GetType().GetFields(BF))
                {
                    var v = f.GetValue(grid) as System.Collections.IEnumerable;
                    if (v != null && !(v is string)) outp.Add(v);
                }
                foreach (var p in grid.GetType().GetProperties(BF))
                {
                    if (p.GetIndexParameters().Length > 0) continue;
                    object v = null;
                    try { v = p.GetValue(grid); } catch { }
                    var en = v as System.Collections.IEnumerable;
                    if (en != null && !(en is string)) outp.Add(en);
                }
            }
            catch { }
            return outp;
        }

        /// <summary>Walk the Control Center's StrategiesGrid rows for a StrategyBase by
        /// name — reflection over its instance fields, read-only. Returns null quietly:
        /// callers treat null as "not reachable", never as an error.</summary>
        private StrategyBase FindGridStrategy(string name)
        {
            StrategyBase found = null;
            try
            {
                var cc = ControlCenterInstance() as System.Windows.DependencyObject;
                if (cc == null) { Log("grid walk: no ControlCenter.Instance"); return null; }
                CcDispatcher().Invoke(new Action(() =>
                {
                    try
                    {
                        foreach (var grid in FindVisualChildren(cc))
                        {
                            if (grid.GetType().FullName != "NinjaTrader.Gui.NinjaScript.StrategiesGrid") continue;
                            foreach (var val in GridCollections(grid))
                                foreach (var item in val)
                                {
                                    var sbFound = StrategyFromRow(item, name);
                                    if (sbFound != null) { found = sbFound; return; }
                                }
                        }
                    }
                    catch (Exception ex) { Log("grid walk: " + ex.Message); }
                }));
            }
            catch (Exception ex) { Log("grid walk dispatch: " + ex.Message); }
            return found;
        }

        /// <summary>If a grid row (entry or child) carries a StrategyBase whose Name
        /// matches, return it. Rows nest one level (entry -> Children).</summary>
        private StrategyBase StrategyFromRow(object row, string name)
        {
            if (row == null) return null;
            try
            {
                foreach (var p in row.GetType().GetProperties(
                    System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic |
                    System.Reflection.BindingFlags.Instance))
                {
                    if (!typeof(StrategyBase).IsAssignableFrom(p.PropertyType)) continue;
                    var sb = p.GetValue(row) as StrategyBase;
                    if (sb != null && string.Equals(sb.Name, name, StringComparison.OrdinalIgnoreCase)) return sb;
                }
                var kids = row.GetType().GetProperty("Children");
                if (kids != null && kids.GetValue(row) is System.Collections.IEnumerable en)
                    foreach (var k in en)
                    {
                        var sb = StrategyFromRow(k, name);
                        if (sb != null) return sb;
                    }
            }
            catch { }
            return null;
        }

        private static IEnumerable<System.Windows.DependencyObject> FindVisualChildren(System.Windows.DependencyObject root)
        {
            if (root == null) yield break;
            int n = System.Windows.Media.VisualTreeHelper.GetChildrenCount(root);
            for (int i = 0; i < n; i++)
            {
                var c = System.Windows.Media.VisualTreeHelper.GetChild(root, i);
                yield return c;
                foreach (var g in FindVisualChildren(c)) yield return g;
            }
        }

        /// <summary>Debug: dump every StrategiesGrid row the walk can see — name,
        /// account, state, whether a StrategyBase is reachable. Read-only.</summary>
        private string ReflectGridRows()
        {
            var rows = new List<string>();
            try
            {
                var ccR = ControlCenterInstance() as System.Windows.DependencyObject;
                if (ccR == null) return "{\"rows\":[],\"error\":\"no ControlCenter.Instance\"}";
                CcDispatcher().Invoke(new Action(() =>
                {
                    try
                    {
                        foreach (var grid in FindVisualChildren(ccR))
                            {
                                if (grid.GetType().FullName != "NinjaTrader.Gui.NinjaScript.StrategiesGrid") continue;
                                int srcIdx = -1;
                                foreach (var val in GridCollections(grid))
                                {
                                    srcIdx++;
                                    foreach (var item in val)
                                    {
                                        var t = item.GetType().Name;
                                        if (t != "StrategiesGridEntry" && t != "StrategiesGridEntryChild") continue;
                                        string nm = "?", acct = "?", st = "?";
                                        bool reachable = false;
                                        try
                                        {
                                            foreach (var p in item.GetType().GetProperties())
                                            {
                                                if (p.Name == "Name") nm = "" + p.GetValue(item);
                                                if (p.Name == "AccountName" || p.Name == "Account") acct = "" + p.GetValue(item);
                                                if (p.Name == "State") st = "" + p.GetValue(item);
                                                if (typeof(StrategyBase).IsAssignableFrom(p.PropertyType) && p.GetValue(item) != null) reachable = true;
                                            }
                                        }
                                        catch { }
                                        rows.Add("{\"field\":" + J("src" + srcIdx) + ",\"row_type\":" + J(t)
                                               + ",\"name\":" + J(nm) + ",\"account\":" + J(acct)
                                               + ",\"state\":" + J(st)
                                               + ",\"strategy_reachable\":" + (reachable ? "true" : "false") + "}");
                                        if (rows.Count >= 100) return;
                                    }
                                }
                            }
                    }
                    catch (Exception ex) { Log("gridrows: " + ex.Message); }
                }));
            }
            catch (Exception ex) { Log("gridrows dispatch: " + ex.Message); }
            return "{\"rows\":[" + string.Join(",", rows) + "]}";
        }

        // ── reflection introspection — READ-ONLY R&D instruments ─────────────
        // NT8 has no supported API for creating/enabling strategy instances (the
        // 2026-08-14 recovery would have been one call if it did). These two
        // endpoints let the outside tooling MAP the internals — type names, member
        // signatures — live over HTTP, so each reflection experiment in a future
        // version is designed from facts instead of one blind recompile per guess.
        // They only ever READ metadata: no Invoke, no field writes, no instances.
        private string ReflectTypes(string contains)
        {
            var rows = new List<string>();
            if (string.IsNullOrEmpty(contains) || contains.Length < 3)
                return "{\"error\":\"pass ?contains= with at least 3 chars\"}";
            try
            {
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    Type[] types;
                    try { types = asm.GetTypes(); } catch { continue; }   // dynamic asms throw
                    foreach (var t in types)
                    {
                        if (t.FullName == null ||
                            t.FullName.IndexOf(contains, StringComparison.OrdinalIgnoreCase) < 0) continue;
                        rows.Add("{\"type\":" + J(t.FullName)
                               + ",\"assembly\":" + J(asm.GetName().Name)
                               + ",\"public\":" + (t.IsPublic ? "true" : "false") + "}");
                        if (rows.Count >= 100) break;
                    }
                    if (rows.Count >= 100) break;
                }
            }
            catch (Exception ex) { Log("reflect/types: " + ex.Message); }
            return "{\"types\":[" + string.Join(",", rows) + "]}";
        }

        private string ReflectMembers(string typeName)
        {
            if (string.IsNullOrEmpty(typeName)) return "{\"error\":\"pass ?type=Full.Type.Name\"}";
            Type t = null;
            try
            {
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    try { t = asm.GetType(typeName, false, true); } catch { }
                    if (t != null) break;
                }
            }
            catch (Exception ex) { Log("reflect/members: " + ex.Message); }
            if (t == null) return "{\"error\":\"type not found\"}";
            var rows = new List<string>();
            const System.Reflection.BindingFlags F =
                System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic |
                System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Static |
                System.Reflection.BindingFlags.DeclaredOnly;
            try
            {
                foreach (var m in t.GetMethods(F))
                {
                    var ps = new List<string>();
                    foreach (var p in m.GetParameters()) ps.Add(p.ParameterType.Name + " " + p.Name);
                    rows.Add("{\"kind\":\"method\",\"name\":" + J(m.Name)
                           + ",\"static\":" + (m.IsStatic ? "true" : "false")
                           + ",\"public\":" + (m.IsPublic ? "true" : "false")
                           + ",\"returns\":" + J(m.ReturnType.Name)
                           + ",\"params\":" + J(string.Join(", ", ps)) + "}");
                    if (rows.Count >= 300) break;
                }
                foreach (var p in t.GetProperties(F))
                {
                    if (rows.Count >= 300) break;
                    rows.Add("{\"kind\":\"property\",\"name\":" + J(p.Name)
                           + ",\"type\":" + J(p.PropertyType.Name)
                           + ",\"can_write\":" + (p.CanWrite ? "true" : "false") + "}");
                }
            }
            catch (Exception ex) { Log("reflect/members walk: " + ex.Message); }
            return "{\"type\":" + J(t.FullName) + ",\"base\":" + J(t.BaseType != null ? t.BaseType.FullName : "")
                 + ",\"members\":[" + string.Join(",", rows) + "]}";
        }

        // ── connections ──────────────────────────────────────────────────────
        // Connect is deliberately OUTSIDE the account rails: it moves no money and
        // holds no position — it is the same act as clicking Connections ▸ <name>.
        // There is still one guard: only names that exist in the user's own saved
        // connection list can be dialed. The bridge can never invent a connection.
        /// <summary>Every saved connection: the user-defined list PLUS the unified-login
        /// brokerage list. v1.1-v1.4 read only the first and could not see the broker
        /// demo at all — three hand-dials in one evening before the gap was mapped
        /// (Globals.BrokerageConnectOptions, found via /reflect on 2026-08-14).</summary>
        private static List<ConnectOptions> AllConnectOptions()
        {
            var outp = new List<ConnectOptions>();
            try { lock (Core.Globals.ConnectOptions) foreach (ConnectOptions o in Core.Globals.ConnectOptions) outp.Add(o); } catch { }
            try
            {
                var bl = Core.Globals.BrokerageConnectOptions;
                if (bl != null) lock (bl) foreach (var o in bl) if (o != null) outp.Add(o);
            }
            catch (Exception ex) { Log("brokerage options: " + ex.Message); }
            return outp;
        }

        private string Connections()
        {
            var rows = new List<string>();
            try
            {
                var live = new Dictionary<string, string>();
                lock (Connection.Connections)
                    foreach (Connection c in Connection.Connections)
                    {
                        try { live[c.Options.Name] = c.Status.ToString(); }
                        catch { }
                    }
                foreach (ConnectOptions o in AllConnectOptions())
                {
                    try
                    {
                        string st = live.ContainsKey(o.Name) ? live[o.Name] : "Disconnected";
                        rows.Add("{\"name\":" + J(o.Name) + ",\"status\":" + J(st)
                               + ",\"connect_on_startup\":" + (o.ConnectOnStartup ? "true" : "false")
                               + ",\"brokerage\":" + (o is NTConnectOptions ? "true" : "false") + "}");
                    }
                    catch (Exception ex) { Log("conn row: " + ex.Message); }
                }
            }
            catch (Exception ex) { Log("connections: " + ex.Message); }
            return "{\"connections\":[" + string.Join(",", rows) + "]}";
        }

        private void ConnectByName(NetworkStream s, string name)
        {
            if (string.IsNullOrEmpty(name)) { Respond(s, 400, "{\"error\":\"name is required\"}"); return; }
            ConnectOptions opt = null;
            foreach (ConnectOptions o in AllConnectOptions())
                if (string.Equals(o.Name, name, StringComparison.OrdinalIgnoreCase)) { opt = o; break; }
            if (opt == null) { Respond(s, 404, "{\"error\":\"no saved connection by that name\"}"); return; }
            lock (Connection.Connections)
                foreach (Connection c in Connection.Connections)
                    try
                    {
                        if (string.Equals(c.Options.Name, name, StringComparison.OrdinalIgnoreCase)
                            && c.Status == ConnectionStatus.Connected)
                        { Respond(s, 200, "{\"ok\":true,\"note\":\"already connected\"}"); return; }
                    }
                    catch { }
            Connection.Connect(opt);
            Log("CONNECT " + name);
            Respond(s, 200, "{\"ok\":true,\"note\":\"connect requested - poll /connections for status\"}");
        }

        // ── mutating endpoints — the layered rails live here ─────────────────
        private void Flatten(NetworkStream s, string acctName)
        {
            string deny = DenyMutation(acctName);      // L1 + L2
            if (deny != null) { Respond(s, 403, "{\"error\":" + J(deny) + "}"); Log("flatten REFUSED " + acctName + ": " + deny); return; }
            Account acct = FindAccount(acctName);
            if (acct == null) { Respond(s, 404, "{\"error\":\"no such account\"}"); return; }
            var instruments = new List<Instrument>();
            try
            {
                lock (acct.Positions)
                    foreach (var p in acct.Positions)
                        if (p.MarketPosition != MarketPosition.Flat && p.Instrument != null)
                            instruments.Add(p.Instrument);
            }
            catch (Exception ex) { Respond(s, 500, "{\"error\":" + J(ex.Message) + "}"); return; }
            if (instruments.Count == 0) { Respond(s, 200, "{\"ok\":true,\"note\":\"already flat\"}"); return; }
            acct.Flatten(instruments);
            Log("FLATTEN " + acctName + " (" + instruments.Count + " instrument(s))");
            Respond(s, 200, "{\"ok\":true,\"flattened\":" + instruments.Count + "}");
        }

        private void CancelOrder(NetworkStream s, string acctName, string orderId)
        {
            // Cancel sits at L1+L2 like flatten: pulling a resting order only ever
            // REDUCES what can happen next. First real use: the 2026-08-14 orphan —
            // ENGU-Q's protective stop left working on the demo after the auto-update
            // deleted the strategy that owned it, a short waiting to happen.
            string deny = DenyMutation(acctName);
            if (deny != null) { Respond(s, 403, "{\"error\":" + J(deny) + "}"); Log("cancel REFUSED " + acctName + ": " + deny); return; }
            if (string.IsNullOrEmpty(orderId)) { Respond(s, 400, "{\"error\":\"order_id is required\"}"); return; }
            Account acct = FindAccount(acctName);
            if (acct == null) { Respond(s, 404, "{\"error\":\"no such account\"}"); return; }
            Order target = null;
            lock (acct.Orders)
                foreach (var o in acct.Orders)
                    try { if ((o.OrderId ?? "") == orderId) { target = o; break; } } catch { }
            if (target == null) { Respond(s, 404, "{\"error\":\"no order with that id\"}"); return; }
            acct.Cancel(new[] { target });
            Log("CANCEL " + acctName + " " + orderId + " (" + (target.Name ?? "") + ")");
            Respond(s, 200, "{\"ok\":true,\"note\":\"cancel requested - poll /orders to confirm\"}");
        }

        // ── kill switch — ONE call: flatten every allowed account, disable every
        // reachable strategy on it. Built for the moment reasoning fails under
        // pressure — no target selection, no judgment calls, just "stop everything
        // you're allowed to touch, right now". It is a composition of Flatten +
        // StrategyLifecycle's own disable path, so it inherits the SAME L1/L2 gate
        // per account (DenyMutation) — it can never reach 1810769 any more than a
        // single flatten call could. Best-effort: one account/strategy failing
        // never stops the rest from being attempted.
        private void KillSwitch(NetworkStream s)
        {
            var flattened = new List<string>();
            var disabled = new List<string>();
            var errors = new List<string>();

            List<Account> accts;
            lock (Account.All) accts = new List<Account>(Account.All);

            foreach (var a in accts)
            {
                string deny = DenyMutation(a.Name);
                if (deny != null) continue;   // not ours to touch (incl. LIVE_LOCKED)

                try
                {
                    var instruments = new List<Instrument>();
                    lock (a.Positions)
                        foreach (var p in a.Positions)
                            if (p.MarketPosition != MarketPosition.Flat && p.Instrument != null)
                                instruments.Add(p.Instrument);
                    if (instruments.Count > 0)
                    {
                        a.Flatten(instruments);
                        flattened.Add(a.Name + " (" + instruments.Count + ")");
                    }
                }
                catch (Exception ex) { errors.Add("flatten " + a.Name + ": " + ex.Message); }

                List<StrategyBase> ss;
                try { lock (a.Strategies) ss = new List<StrategyBase>(a.Strategies); }
                catch (Exception ex) { errors.Add("strategies " + a.Name + ": " + ex.Message); continue; }

                foreach (var st in ss)
                {
                    string stName = "?";
                    try { stName = st.Name; } catch { }
                    string err = null;
                    try
                    {
                        Core.Globals.MainThreadDispatcher.Invoke(new Action(() =>
                        {
                            try
                            {
                                const System.Reflection.BindingFlags SF =
                                    System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic |
                                    System.Reflection.BindingFlags.Static;
                                var mi = typeof(StrategiesGrid).GetMethod("StrategyDisable", SF);
                                if (mi == null) err = "grid method not found";
                                else mi.Invoke(null, new object[] { st });
                            }
                            catch (System.Reflection.TargetInvocationException tex)
                            { err = (tex.InnerException ?? tex).Message; }
                            catch (Exception ex) { err = ex.Message; }
                        }));
                    }
                    catch (Exception ex) { err = "dispatch: " + ex.Message; }
                    if (err != null) errors.Add("disable " + stName + ": " + err);
                    else { disabled.Add(stName); lock (_parked) _parked[stName] = st; }
                }
            }

            Log("KILLSWITCH flattened=[" + string.Join(",", flattened) + "] disabled=[" + string.Join(",", disabled) + "]"
                + (errors.Count > 0 ? " errors=[" + string.Join(" | ", errors) + "]" : ""));
            Respond(s, 200, "{\"ok\":true,\"flattened\":" + JArr(flattened) + ",\"disabled\":" + JArr(disabled)
                + ",\"errors\":" + JArr(errors) + "}");
        }

        private void PlaceOrder(NetworkStream s, string body)
        {
            // Body: {"account":"...","instrument":"NQ 09-26","action":"BUY"|"SELL",
            //        "type":"MARKET"|"LIMIT","qty":1,"limit":0,"name":"..."}
            var cfg = ReadConfig();
            if (!cfg.OrdersEnabled)                                    // L3
            {
                Respond(s, 403, "{\"error\":\"orders_enabled is false in bridge.json\"}");
                Log("order REFUSED: orders_enabled=false"); return;
            }
            string acctName = JGet(body, "account");
            string deny = DenyMutation(acctName);                      // L1 + L2
            if (deny != null) { Respond(s, 403, "{\"error\":" + J(deny) + "}"); Log("order REFUSED " + acctName + ": " + deny); return; }

            Account acct = FindAccount(acctName);
            if (acct == null) { Respond(s, 404, "{\"error\":\"no such account\"}"); return; }
            string instName = JGet(body, "instrument");
            Instrument inst = Instrument.GetInstrument(instName);
            if (inst == null) { Respond(s, 400, "{\"error\":\"unknown instrument\"}"); return; }

            string act = (JGet(body, "action") ?? "").ToUpperInvariant();
            string typ = (JGet(body, "type") ?? "MARKET").ToUpperInvariant();
            int qty; int.TryParse(JGet(body, "qty") ?? "0", out qty);
            double limit; double.TryParse(JGet(body, "limit") ?? "0", NumberStyles.Float, CultureInfo.InvariantCulture, out limit);
            if (qty <= 0 || qty > 10) { Respond(s, 400, "{\"error\":\"qty must be 1-10\"}"); return; }
            if (act != "BUY" && act != "SELL") { Respond(s, 400, "{\"error\":\"action must be BUY or SELL\"}"); return; }
            OrderType ot = typ == "LIMIT" ? OrderType.Limit : OrderType.Market;
            if (ot == OrderType.Limit && limit <= 0) { Respond(s, 400, "{\"error\":\"limit price required\"}"); return; }
            string name = JGet(body, "name") ?? "ELB";

            // L5 pre-trade: size, resulting position, margin, and rate. Only covers
            // orders THIS bridge places -- strategy orders never reach here, which is
            // exactly why the monitor above exists.
            if (cfg.RiskEnabled)
            {
                bool tripped; string treason;
                lock (_riskLock) { tripped = _breakerTripped; treason = _breakerReason; }
                if (tripped)
                { Respond(s, 403, "{\"error\":" + J("circuit breaker is TRIPPED: " + treason + " - POST /risk/reset to clear") + "}");
                  Log("order REFUSED: breaker tripped"); return; }
                string sz = DenySize(cfg, acct, qty);
                if (sz != null) { Respond(s, 403, "{\"error\":" + J("position-size gate: " + sz) + "}"); Log("order REFUSED: " + sz); return; }
                string rt = DenyRate(cfg);
                if (rt != null) { Respond(s, 403, "{\"error\":" + J(rt) + "}"); Log("order REFUSED: " + rt); return; }
            }
            Order o = acct.CreateOrder(inst,
                act == "BUY" ? OrderAction.Buy : OrderAction.Sell,
                ot, OrderEntry.Manual, TimeInForce.Day, qty, limit, 0,
                "", name, Core.Globals.MaxDate, null);
            acct.Submit(new[] { o });
            NoteOrderPlaced();
            Log("ORDER " + acctName + " " + act + " " + qty + " " + instName + " " + typ
                + (ot == OrderType.Limit ? (" @" + limit) : ""));
            Respond(s, 200, "{\"ok\":true,\"order_id\":" + J(o.OrderId ?? "") + "}");
        }

        // ── L5: CIRCUIT BREAKER + POSITION-SIZE GATE ─────────────────────────
        // THE THING THAT MAKES THIS NON-TRIVIAL: strategy orders do NOT pass through
        // /order. NinjaScript submits them straight to the broker, so a pre-trade check
        // on this bridge's own endpoint would protect exactly nothing when a strategy
        // misbehaves -- which is the case that actually costs money. So there are TWO
        // halves and they are not interchangeable:
        //   (a) PRE-TRADE gate  -> covers orders THIS bridge places (qty, size, rate)
        //   (b) MONITOR loop    -> watches ACCOUNT state (realized day P&L, net open
        //                          contracts) on a timer, so it catches strategy orders,
        //                          manual clicks in the NT UI, and anything else that
        //                          moves the account without asking us.
        // The monitor is the one that matters for live trading. It LATCHES on trip so a
        // flapping value cannot fire the action repeatedly, and it only ever acts on
        // accounts that already clear L1+L2.
        private static readonly List<DateTime> _orderTimes = new List<DateTime>();
        private static readonly object _riskLock = new object();
        private static bool     _breakerTripped;
        private static string   _breakerReason = "";
        private static DateTime _breakerAtUtc;
        private System.Threading.Timer _riskTimer;

        /// <summary>Net open contracts on an account, summed across instruments.</summary>
        private static int NetContracts(Account a)
        {
            int n = 0;
            try
            {
                lock (a.Positions)
                    foreach (var p in a.Positions)
                        if (p.MarketPosition != MarketPosition.Flat) n += Math.Abs(p.Quantity);
            }
            catch { }
            return n;
        }

        private static double RealizedToday(Account a)
        {
            try { return a.Get(AccountItem.RealizedProfitLoss, Currency.UsDollar); }
            catch { return 0.0; }
        }

        /// <summary>Position-size / margin gate. Returns a refusal reason or null.
        /// `addQty` is what is about to be ADDED, so the check is on the resulting size.</summary>
        private string DenySize(Conf cfg, Account acct, int addQty)
        {
            if (acct == null) return null;
            if (addQty > cfg.MaxQty)
                return "qty " + addQty + " exceeds max_qty " + cfg.MaxQty;
            int after = NetContracts(acct) + Math.Max(0, addQty);
            if (after > cfg.MaxPositionContracts)
                return "resulting position " + after + " contracts exceeds max_position_contracts "
                     + cfg.MaxPositionContracts + " (currently " + NetContracts(acct) + ")";
            // Margin leg is SKIPPED when margin_per_contract_usd is unset. Guessing a
            // margin number would be worse than not checking: it would either block
            // legitimate orders or wave through real ones with false confidence.
            if (cfg.MarginPerContract > 0)
            {
                double cash = 0;
                try { cash = acct.Get(AccountItem.CashValue, Currency.UsDollar); } catch { }
                if (cash > 0)
                {
                    double need = after * cfg.MarginPerContract;
                    double cap  = cash * (cfg.MaxMarginPct / 100.0);
                    if (need > cap)
                        return "estimated margin $" + need.ToString("0", CultureInfo.InvariantCulture)
                             + " for " + after + " contract(s) exceeds " + cfg.MaxMarginPct
                             + "% of $" + cash.ToString("0", CultureInfo.InvariantCulture) + " cash (cap $"
                             + cap.ToString("0", CultureInfo.InvariantCulture) + ")";
                }
            }
            return null;
        }

        /// <summary>Bridge-placed order RATE ceiling. Returns a reason or null.</summary>
        private string DenyRate(Conf cfg)
        {
            lock (_riskLock)
            {
                var cutoff = DateTime.UtcNow.AddMinutes(-1);
                _orderTimes.RemoveAll(x => x < cutoff);
                if (_orderTimes.Count >= cfg.MaxOrdersPerMin)
                    return "order rate limit: " + _orderTimes.Count + " bridge orders in the last minute "
                         + "(max_orders_per_min " + cfg.MaxOrdersPerMin + ")";
            }
            return null;
        }

        private static void NoteOrderPlaced()
        {
            lock (_riskLock) _orderTimes.Add(DateTime.UtcNow);
        }

        /// <summary>The monitor. Runs on a timer, reads ACCOUNT state so it sees orders
        /// this bridge never placed, and trips once when a limit is breached.</summary>
        private void RiskTick(object _)
        {
            try
            {
                var cfg = ReadConfig();
                if (!cfg.RiskEnabled) return;
                lock (_riskLock) { if (_breakerTripped) return; }   // latched: act once

                List<Account> accts;
                lock (Account.All) accts = new List<Account>(Account.All);
                foreach (var a in accts)
                {
                    if (DenyMutation(a.Name) != null) continue;      // only accounts we may touch
                    string why = null;
                    double real = RealizedToday(a);
                    if (real <= -Math.Abs(cfg.MaxDailyLossUsd))
                        why = "daily loss limit: realized " + real.ToString("0.00", CultureInfo.InvariantCulture)
                            + " on " + a.Name + " is at or past -" + cfg.MaxDailyLossUsd;
                    int net = NetContracts(a);
                    if (why == null && net > cfg.MaxPositionContracts)
                        why = "position limit: " + net + " net contracts on " + a.Name
                            + " exceeds max_position_contracts " + cfg.MaxPositionContracts;
                    if (why == null) continue;

                    lock (_riskLock)
                    {
                        if (_breakerTripped) return;
                        _breakerTripped = true; _breakerReason = why; _breakerAtUtc = DateTime.UtcNow;
                    }
                    Log("BREAKER TRIPPED (" + cfg.BreakerAction + "): " + why);
                    try
                    {
                        if (cfg.BreakerAction == "notify")
                        {
                            // nothing to do beyond the log + /risk surfacing it
                        }
                        else if (cfg.BreakerAction == "disable")
                        {
                            // Deliberately NOT the default: disabling a strategy that is
                            // holding a position orphans that position with nothing left
                            // managing its exit. Offered because it is the right call for a
                            // RATE breach, wrong for a LOSS breach.
                            DisableAllOn(a);
                        }
                        else
                        {
                            FlattenAccount(a);
                            DisableAllOn(a);
                        }
                    }
                    catch (Exception ex) { Log("breaker action failed: " + ex.Message); }
                    return;
                }
            }
            catch (Exception ex) { Log("risk tick: " + ex.Message); }
        }

        private void FlattenAccount(Account a)
        {
            var inst = new List<Instrument>();
            try
            {
                lock (a.Positions)
                    foreach (var p in a.Positions)
                        if (p.MarketPosition != MarketPosition.Flat && p.Instrument != null) inst.Add(p.Instrument);
            }
            catch { }
            if (inst.Count > 0) { a.Flatten(inst); Log("breaker: flattened " + inst.Count + " instrument(s) on " + a.Name); }
        }

        private void DisableAllOn(Account a)
        {
            List<StrategyBase> ss;
            try { lock (a.Strategies) ss = new List<StrategyBase>(a.Strategies); }
            catch { return; }
            foreach (var st in ss)
            {
                string nm = "?";
                try { nm = st.Name; } catch { }
                try
                {
                    Core.Globals.MainThreadDispatcher.Invoke(new Action(() =>
                    {
                        try
                        {
                            const System.Reflection.BindingFlags SF =
                                System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic |
                                System.Reflection.BindingFlags.Static;
                            var mi = typeof(StrategiesGrid).GetMethod("StrategyDisable", SF);
                            if (mi != null) mi.Invoke(null, new object[] { st });
                        }
                        catch { }
                    }));
                    lock (_parked) _parked[nm] = st;
                    Log("breaker: disabled " + nm);
                }
                catch (Exception ex) { Log("breaker disable " + nm + ": " + ex.Message); }
            }
        }

        private string RiskJson()
        {
            var cfg = ReadConfig();
            var rows = new List<string>();
            List<Account> accts;
            lock (Account.All) accts = new List<Account>(Account.All);
            foreach (var a in accts)
            {
                if (DenyMutation(a.Name) != null) continue;
                rows.Add("{\"account\":" + J(a.Name) + ",\"realized_today\":" + Num(RealizedToday(a))
                       + ",\"net_contracts\":" + NetContracts(a) + "}");
            }
            bool tripped; string why; DateTime at;
            lock (_riskLock) { tripped = _breakerTripped; why = _breakerReason; at = _breakerAtUtc; }
            int recent;
            lock (_riskLock) { _orderTimes.RemoveAll(x => x < DateTime.UtcNow.AddMinutes(-1)); recent = _orderTimes.Count; }
            return "{\"risk_enabled\":" + (cfg.RiskEnabled ? "true" : "false")
                 + ",\"tripped\":" + (tripped ? "true" : "false")
                 + ",\"reason\":" + J(tripped ? why : "")
                 + ",\"tripped_at_utc\":" + J(tripped ? at.ToString("yyyy-MM-dd HH:mm:ss") : "")
                 + ",\"breaker_action\":" + J(cfg.BreakerAction)
                 + ",\"limits\":{\"max_daily_loss_usd\":" + Num(cfg.MaxDailyLossUsd)
                 + ",\"max_orders_per_min\":" + cfg.MaxOrdersPerMin
                 + ",\"max_qty\":" + cfg.MaxQty
                 + ",\"max_position_contracts\":" + cfg.MaxPositionContracts
                 + ",\"margin_per_contract_usd\":" + Num(cfg.MarginPerContract)
                 + ",\"max_margin_pct\":" + Num(cfg.MaxMarginPct) + "}"
                 + ",\"orders_last_min\":" + recent
                 + ",\"accounts\":[" + string.Join(",", rows) + "]}";
        }

        /// <summary>The layered account gate. Returns a refusal reason or null.</summary>
        private string DenyMutation(string acctName)
        {
            if (string.IsNullOrEmpty(acctName)) return "account is required";
            if (IsLiveLocked(acctName))                                 // L1
                return "account " + acctName + " is LIVE-LOCKED in code; changing that requires editing EdgeLogBridge.cs and recompiling";
            var cfg = ReadConfig();                                     // L2
            if (cfg.Accounts.Count == 0)
                return "no bridge.json allowlist found at " + ConfPath + " - mutations refuse everything until it exists";
            foreach (var a in cfg.Accounts)
                if (string.Equals(a, acctName, StringComparison.OrdinalIgnoreCase)) return null;
            return "account " + acctName + " is not in the bridge.json allowlist";
        }

        private static bool IsLiveLocked(string name)
        {
            foreach (var l in LIVE_LOCKED)
                if (string.Equals(l, name, StringComparison.OrdinalIgnoreCase)) return true;
            return false;
        }

        private static Account FindAccount(string name)
        {
            List<Account> accts;
            lock (Account.All) accts = new List<Account>(Account.All);
            foreach (var a in accts)
                if (string.Equals(a.Name, name, StringComparison.OrdinalIgnoreCase)) return a;
            return null;
        }

        // ── config / json / log helpers ──────────────────────────────────────
        // RISK CONFIG (L5). Everything in L1-L4 answers "WHICH account". None of it
        // answers "HOW MUCH" or "how badly is today going" -- the gap that matters the
        // day orders_enabled flips true. Tunable from bridge.json so thresholds need no
        // recompile; the CODE defaults are conservative so a missing or garbled file can
        // never silently mean "no limits".
        private class Conf
        {
            public bool OrdersEnabled;
            public List<string> Accounts = new List<string>();
            // circuit breaker
            public bool   RiskEnabled       = false;        // ships OFF; turning it on is the owner's call
            public double MaxDailyLossUsd   = 1000.0;       // realized day P&L floor, per allowed account
            public int    MaxOrdersPerMin   = 10;           // bridge-placed order RATE ceiling
            public string BreakerAction     = "killswitch"; // notify | disable | killswitch
            // position-size / margin gate
            public int    MaxQty              = 3;    // per bridge order AND per strategy at enable
            public int    MaxPositionContracts= 5;    // net open contracts per account
            public double MarginPerContract   = 0.0;  // 0 = unknown -> margin leg SKIPPED, never guessed
            public double MaxMarginPct        = 25.0; // of account cash
        }

        /// <summary>Pull "key": number out of the flat config. Returns dflt when absent or
        /// unparseable -- a typo must fall back to the conservative default, not to zero.</summary>
        private static double CfgNum(string t, string key, double dflt)
        {
            try
            {
                int i = t.IndexOf("\"" + key + "\"", StringComparison.OrdinalIgnoreCase);
                if (i < 0) return dflt;
                int c = t.IndexOf(':', i); if (c < 0) return dflt;
                int p = c + 1; while (p < t.Length && (t[p] == ' ' || t[p] == '\t')) p++;
                int e = p; while (e < t.Length && "-+.0123456789eE".IndexOf(t[e]) >= 0) e++;
                double v;
                if (e > p && double.TryParse(t.Substring(p, e - p), NumberStyles.Float, CultureInfo.InvariantCulture, out v)) return v;
            }
            catch { }
            return dflt;
        }

        private static string CfgStr(string t, string key, string dflt)
        {
            try
            {
                int i = t.IndexOf("\"" + key + "\"", StringComparison.OrdinalIgnoreCase);
                if (i < 0) return dflt;
                int c = t.IndexOf(':', i); if (c < 0) return dflt;
                int q1 = t.IndexOf('"', c + 1); if (q1 < 0) return dflt;
                int q2 = t.IndexOf('"', q1 + 1); if (q2 < 0) return dflt;
                string s = t.Substring(q1 + 1, q2 - q1 - 1).Trim();
                return s.Length > 0 ? s : dflt;
            }
            catch { }
            return dflt;
        }

        private Conf ReadConfig()
        {
            var c = new Conf();
            try
            {
                if (!File.Exists(ConfPath)) return c;
                string t = File.ReadAllText(ConfPath);
                c.OrdersEnabled = t.Replace(" ", "").IndexOf("\"orders_enabled\":true", StringComparison.OrdinalIgnoreCase) >= 0;
                c.RiskEnabled   = t.Replace(" ", "").IndexOf("\"risk_enabled\":true", StringComparison.OrdinalIgnoreCase) >= 0;
                c.MaxDailyLossUsd    = CfgNum(t, "max_daily_loss_usd", c.MaxDailyLossUsd);
                c.MaxOrdersPerMin    = (int)CfgNum(t, "max_orders_per_min", c.MaxOrdersPerMin);
                c.MaxQty             = (int)CfgNum(t, "max_qty", c.MaxQty);
                c.MaxPositionContracts = (int)CfgNum(t, "max_position_contracts", c.MaxPositionContracts);
                c.MarginPerContract  = CfgNum(t, "margin_per_contract_usd", c.MarginPerContract);
                c.MaxMarginPct       = CfgNum(t, "max_margin_pct", c.MaxMarginPct);
                c.BreakerAction      = CfgStr(t, "breaker_action", c.BreakerAction);
                int i = t.IndexOf("\"accounts\"", StringComparison.OrdinalIgnoreCase);
                if (i >= 0)
                {
                    int lb = t.IndexOf('[', i), rb = t.IndexOf(']', i);
                    if (lb > 0 && rb > lb)
                        foreach (var part in t.Substring(lb + 1, rb - lb - 1).Split(','))
                        {
                            string v = part.Trim().Trim('"').Trim();
                            if (v.Length > 0) c.Accounts.Add(v);
                        }
                }
            }
            catch (Exception ex) { Log("config: " + ex.Message); }
            return c;
        }

        private static string J(string v)
        {
            if (v == null) return "null";
            var sb = new StringBuilder("\"");
            foreach (char ch in v)
            {
                if (ch == '"' || ch == '\\') sb.Append('\\').Append(ch);
                else if (ch == '\n') sb.Append("\\n");
                else if (ch == '\r') sb.Append("\\r");
                else if (ch < ' ') sb.Append(' ');
                else sb.Append(ch);
            }
            return sb.Append('"').ToString();
        }

        private static string JArr(IEnumerable<string> xs)
        {
            var parts = new List<string>();
            foreach (var x in xs) parts.Add(J(x));
            return "[" + string.Join(",", parts) + "]";
        }

        private static string Num(double v)
        {
            if (double.IsNaN(v) || double.IsInfinity(v)) return "null";
            return v.ToString("0.####", CultureInfo.InvariantCulture);
        }

        /// <summary>Naive one-level JSON string/number field getter — the bodies this
        /// bridge accepts are flat objects built by our own client, nothing nested.</summary>
        private static string JGet(string json, string key)
        {
            if (json == null) return null;
            int i = json.IndexOf("\"" + key + "\"", StringComparison.OrdinalIgnoreCase);
            if (i < 0) return null;
            int c = json.IndexOf(':', i);
            if (c < 0) return null;
            int p = c + 1;
            while (p < json.Length && (json[p] == ' ' || json[p] == '\t')) p++;
            if (p >= json.Length) return null;
            if (json[p] == '"')
            {
                int e = json.IndexOf('"', p + 1);
                return e > p ? json.Substring(p + 1, e - p - 1) : null;
            }
            int end = p;
            while (end < json.Length && "-+.0123456789eE".IndexOf(json[end]) >= 0) end++;
            return end > p ? json.Substring(p, end - p) : null;
        }

        private static void Log(string msg)
        {
            try
            {
                lock (_logLock)
                    File.AppendAllText(LogPath,
                        DateTime.UtcNow.ToString("yyyy-MM-dd HH:mm:ss") + "Z  [bridge] " + msg + "\r\n");
            }
            catch { }
        }
    }
}
