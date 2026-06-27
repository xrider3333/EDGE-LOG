// ============================================================================
//  EdgeLogExport  —  NinjaTrader 8 AddOn
//  Streams every account execution (fill) to C:\EdgeLog\fills.csv in real time.
//  EDGELOG's local runner watches that file, pairs fills into round-trip trades,
//  and pushes them to your EDGELOG journal automatically.
//
//  WHY AN AddOn (not a Strategy):  an AddOn subscribes to the *account's*
//  ExecutionUpdate, so it captures EVERY fill on the account — manual/discretionary
//  trades AND automated strategy fills. A Strategy only sees its own orders.
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
//  Accounts are bound once at startup; if you connect a NEW account later, restart
//  NinjaTrader so it is picked up. The file is append-only and self-healing: each
//  fill carries a unique ExecutionId so re-reads never double-count.
// ============================================================================
using System;
using System.IO;
using System.Collections.Generic;
using System.Globalization;
using NinjaTrader.Cbi;
using NinjaTrader.NinjaScript;

namespace NinjaTrader.NinjaScript.AddOns
{
    public class EdgeLogExport : NinjaTrader.NinjaScript.AddOnBase
    {
        // Change this path if you keep EdgeLog elsewhere — keep it in sync with the
        // runner's --nt-fills argument (default C:\EdgeLog\fills.csv).
        private const string Dir      = @"C:\EdgeLog";
        private const string FilePath = @"C:\EdgeLog\fills.csv";
        private const string Header =
            "ExecutionId,Time,Account,Instrument,Action,Qty,Price,Commission,OrderId\n";

        private readonly object _lock = new object();
        private readonly HashSet<string> _seen = new HashSet<string>();
        private bool _subscribed = false;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "EdgeLogExport";
            }
            else if (State == State.Configure)
            {
                try
                {
                    if (!Directory.Exists(Dir)) Directory.CreateDirectory(Dir);
                    if (!File.Exists(FilePath)) File.WriteAllText(FilePath, Header);
                }
                catch { /* disk not writable — fail quiet */ }

                // Bind to every account known at startup. (Canonical NT8 pattern.)
                lock (Account.All)
                {
                    foreach (Account a in Account.All)
                        a.ExecutionUpdate += OnExecutionUpdate;
                }
                _subscribed = true;
            }
            else if (State == State.Terminated)
            {
                if (_subscribed)
                {
                    lock (Account.All)
                    {
                        foreach (Account a in Account.All)
                            a.ExecutionUpdate -= OnExecutionUpdate;
                    }
                    _subscribed = false;
                }
            }
        }

        private void OnExecutionUpdate(object sender, ExecutionEventArgs e)
        {
            try
            {
                Execution ex = (e == null) ? null : e.Execution;
                if (ex == null || ex.Order == null) return;

                // Only count real fills.
                OrderState os = ex.Order.OrderState;
                if (os != OrderState.Filled && os != OrderState.PartFilled) return;

                string execId = ex.ExecutionId ?? "";
                if (execId.Length == 0) return;

                lock (_lock)
                {
                    if (_seen.Contains(execId)) return;   // NT can fire twice
                    _seen.Add(execId);

                    string action;
                    switch (ex.Order.OrderAction)
                    {
                        case OrderAction.Buy:
                        case OrderAction.BuyToCover: action = "BUY";  break;
                        default:                     action = "SELL"; break;  // Sell / SellShort
                    }

                    string line = string.Join(",", new string[] {
                        Csv(execId),
                        ex.Time.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture),
                        Csv(ex.Account != null ? ex.Account.Name : ""),
                        Csv(ex.Instrument != null ? ex.Instrument.FullName : ""),
                        action,
                        ex.Quantity.ToString(CultureInfo.InvariantCulture),
                        ex.Price.ToString("0.#########", CultureInfo.InvariantCulture),
                        ex.Commission.ToString("0.####", CultureInfo.InvariantCulture),
                        Csv(ex.Order.OrderId ?? "")
                    }) + "\n";

                    File.AppendAllText(FilePath, line);
                }
            }
            catch { /* never let logging break trading */ }
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
