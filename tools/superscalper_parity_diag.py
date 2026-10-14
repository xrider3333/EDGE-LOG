# SUPERSCALPER parity DIAGNOSTICS (prereg Amendment 1: match statistics only - no port P&L, totals or win rate are printed).
# Where do the port and TradingView's published trades disagree? Unmatched TV trades by side / hour / nearest same-side port
# entry; matched pairs' exit-time gaps; and which port entry PATHS the unmatched port trades came from.
import collections, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import superscalper_parity as SP

TV = r"C:\EdgeLog\_research_cache\tv_scalp\superscalper\superscalper_tv_trades_published.csv"
ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
params = {"intrabar": "tv"}
for kv in sys.argv[1:]:
    k, v = kv.split("=", 1); params[k] = v
tv = SP.read_tv(TV, "America/Chicago")
first = min(t["entry_ts"] for t in tv).tz_convert("America/New_York")
rows, idx, _ = SP.run_port("2026-02-27", "2026-04-22", SP._parse_params(["%s=%s" % kv for kv in params.items()]), ROOT)
epoch = idx.tz_convert("UTC").as_unit("ns").asi8 // 10 ** 9
port = [{"side": r["side"], "entry_epoch": int(epoch[r["entry_bar"]]), "exit_epoch": int(epoch[r["exit_bar"]]),
         "entry_price": r["entry_price"], "exit_price": r["exit_price"], "reason": r["exit_reason"], "pnl": r["pnl_pts"],
         "path": r.get("path", "?"), "x_sl": r.get("exit_order_sl", float("nan")), "x_tp": r.get("exit_order_tp", float("nan"))} for r in rows]
t_lo = min(t["entry_ts"] for t in tv).value // 10 ** 9 - 60
t_hi = max(t["entry_ts"] for t in tv).value // 10 ** 9 + 60
port = [p for p in port if t_lo <= p["entry_epoch"] <= t_hi]
pairs = SP.match(tv, port)
mt = {a for a, _ in pairs}; mp = {b for _, b in pairs}
print("params", params, "| TV", len(tv), "port", len(port), "matched", len(pairs))
un_tv = [t for i, t in enumerate(tv) if i not in mt]
print("unmatched TV by side:", dict(collections.Counter("L" if t["side"] > 0 else "S" for t in un_tv)),
      "| all TV by side:", dict(collections.Counter("L" if t["side"] > 0 else "S" for t in tv)))
hrs = collections.Counter(t["entry_ts"].tz_convert("America/New_York").hour for t in un_tv)
print("unmatched TV by NY hour:", dict(sorted(hrs.items())))
d = []
for t in un_tv:
    e = t["entry_ts"].value // 10 ** 9
    same = [abs(p["entry_epoch"] - e) / 60 for p in port if p["side"] == t["side"]]
    d.append(min(same) if same else np.inf)
d = np.array(d)
print("unmatched TV: nearest same-side port entry (min): <=5 %d, 5-30 %d, 30-120 %d, >120 %d" % (
    (d <= 5).sum(), ((d > 5) & (d <= 30)).sum(), ((d > 30) & (d <= 120)).sum(), (d > 120).sum()))
gap = np.array([(port[b]["exit_epoch"] - (tv[a]["exit_ts"].value // 10 ** 9)) / 60 for a, b in pairs])
print("matched pairs: port exit minus TV exit (min): median %.1f, |gap|<=1 %d, 1-15 %d, >15 %d" % (
    np.median(gap), (abs(gap) <= 1).sum(), ((abs(gap) > 1) & (abs(gap) <= 15)).sum(), (abs(gap) > 15).sum()))
print("unmatched PORT trades by entry path:", dict(collections.Counter(p["path"] for j, p in enumerate(port) if j not in mp)))
print("matched PORT trades by entry path:", dict(collections.Counter(port[b]["path"] for _, b in pairs)))
