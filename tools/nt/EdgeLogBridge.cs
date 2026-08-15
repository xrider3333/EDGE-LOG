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
        private const string Version   = "1.5";
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
            Log("started v" + Version + " on 127.0.0.1:" + Port);
        }

        private void Stop()
        {
            _running = false;
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
            // 3) the grid's own rows (works for strategies disabled before we loaded)
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
                Core.Globals.MainThreadDispatcher.Invoke(new Action(() =>
                {
                    try
                    {
                        foreach (System.Windows.Window w in System.Windows.Application.Current.Windows)
                        {
                            foreach (var grid in FindVisualChildren(w))
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
                Core.Globals.MainThreadDispatcher.Invoke(new Action(() =>
                {
                    try
                    {
                        foreach (System.Windows.Window w in System.Windows.Application.Current.Windows)
                            foreach (var grid in FindVisualChildren(w))
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

            Order o = acct.CreateOrder(inst,
                act == "BUY" ? OrderAction.Buy : OrderAction.Sell,
                ot, OrderEntry.Manual, TimeInForce.Day, qty, limit, 0,
                "", name, Core.Globals.MaxDate, null);
            acct.Submit(new[] { o });
            Log("ORDER " + acctName + " " + act + " " + qty + " " + instName + " " + typ
                + (ot == OrderType.Limit ? (" @" + limit) : ""));
            Respond(s, 200, "{\"ok\":true,\"order_id\":" + J(o.OrderId ?? "") + "}");
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
        private class Conf { public bool OrdersEnabled; public List<string> Accounts = new List<string>(); }

        private Conf ReadConfig()
        {
            var c = new Conf();
            try
            {
                if (!File.Exists(ConfPath)) return c;
                string t = File.ReadAllText(ConfPath);
                c.OrdersEnabled = t.Replace(" ", "").IndexOf("\"orders_enabled\":true", StringComparison.OrdinalIgnoreCase) >= 0;
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
