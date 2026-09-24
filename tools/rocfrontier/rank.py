# Moved from a session scratchpad 2026-09-24 (ROC frontier hunt); results in RESEARCH_LEDGER.md rows 1.15 / 2.12-2.19.
import json, os, datetime
CACHE = os.environ.get("EDGELOG_ROCFRONTIER", r"C:\EdgeLog\_anatomy_cache\rocfrontier")
R = json.load(open(os.path.join(CACHE, "runs_roc.json")))
def yrs(a, b):
    try: return (datetime.date.fromisoformat(str(b)[:10]) - datetime.date.fromisoformat(str(a)[:10])).days / 365.25
    except Exception: return None
rows = []
for r in R:
    v = r.get("validate") or {}
    w = v.get("wf_oos") or {}
    m = float(r.get("multiplier") or 1.0)
    lb = v.get("lockbox") or {}
    row = dict(id=r.get("id"), fam="%s-%s" % (r.get("famKey"), r.get("famSeq")), strat=str(r.get("strategy"))[:34],
               inst=r.get("instrument"), tf=r.get("timeframe"), m=m, verdict=v.get("verdict"))
    if w.get("trades"):
        y = w.get("years") or yrs(w.get("from"), w.get("to"))
        net = (w.get("net") or 0) * m
        dd = abs(w.get("max_drawdown") or 0) * m
        row.update(wf_net=net, wf_y=y, wf_roc=100 * net / y / 1e5 if y else None, wf_dd=dd,
                   wf_mar=(net / y / dd) if (y and dd) else None, wf_pf=w.get("pf"), wf_n=w.get("trades"),
                   wf_sort=w.get("sortino"))
    if lb:
        ly = yrs(lb.get("from"), lb.get("to"))
        lnet = (lb.get("pnl") or 0) * m
        ldd = abs(lb.get("max_drawdown") or lb.get("max_dd") or 0) * m
        row.update(lb_net=lnet, lb_y=ly, lb_roc=100 * lnet / ly / 1e5 if ly else None, lb_dd=ldd,
                   lb_pf=lb.get("profit_factor") or lb.get("pf"), lb_n=lb.get("num_trades") or lb.get("trades"))
    rows.append(row)
ok = [x for x in rows if x.get("wf_roc") is not None]
print(len(rows), "runs;", len(ok), "with a walk-forward test block")
print("%-5s %-12s %-34s %-4s %-4s %4s %-6s | %7s %8s %5s %5s %5s %5s | %7s %8s %5s %4s" % (
    "run", "family", "strategy", "inst", "tf", "mult", "verdct", "WFroc%", "WFdd$", "MAR", "PF", "SORT", "n",
    "LBroc%", "LBnet$", "LBpf", "LBn"))
for x in sorted(ok, key=lambda x: -x["wf_roc"])[:45]:
    print("%-5s %-12s %-34s %-4s %-4s %4.0f %-6s | %7.1f %8.0f %5.2f %5.2f %5.2f %5d | %7s %8s %5s %4s" % (
        x["id"], x["fam"][:12], x["strat"], x["inst"], x["tf"], x["m"], str(x["verdict"])[:6], x["wf_roc"], x["wf_dd"],
        x["wf_mar"] or 0, x["wf_pf"] or 0, x["wf_sort"] or 0, x["wf_n"],
        ("%.1f" % x["lb_roc"]) if x.get("lb_roc") is not None else "-",
        ("%.0f" % x["lb_net"]) if x.get("lb_net") is not None else "-",
        ("%.2f" % x["lb_pf"]) if x.get("lb_pf") else "-", x.get("lb_n") or "-"))
