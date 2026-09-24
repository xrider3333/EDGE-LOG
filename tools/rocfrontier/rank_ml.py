# Moved from a session scratchpad 2026-09-24 (ROC frontier hunt); results in RESEARCH_LEDGER.md rows 1.15 / 2.12-2.19.
# ML-row frontier, same arithmetic as tools/r59_noise_capital_board.py (EXPLORE's sizing), all families.
import json, os, datetime
CACHE = os.environ.get("EDGELOG_ROCFRONTIER", r"C:\EdgeLog\_anatomy_cache\rocfrontier")
ACCT = 1e5
def yrs(a, b):
    return (datetime.date.fromisoformat(str(b)[:10]) - datetime.date.fromisoformat(str(a)[:10])).days / 365.25
rows = []
for r in json.load(open(os.path.join(CACHE, "runs_ml.json"))):
    gv = r.get("gate_validate") or {}
    wr = gv.get("wf_range")
    if not (isinstance(wr, list) and len(wr) == 2 and gv.get("ungated_wf") and gv.get("ungated_lockbox")):
        continue
    M = float(r.get("multiplier") or 1)
    wfy = yrs(wr[0], wr[1])
    end = (gv.get("span") or [None, r.get("date_to")])[1] or r.get("date_to")
    lby = yrs(gv.get("lockbox_from") or wr[1], end)
    uw, ul = gv["ungated_wf"], gv["ungated_lockbox"]
    tag = "#%s %s-%s" % (r.get("id"), r.get("famKey"), r.get("famSeq"))
    def add(kind, wf, lb, fwf=1.0, flb=1.0):
        if not wf or not lb or not wf.get("num_trades") or lby <= 0.2 or wfy <= 0.2:
            return
        nw, dw = wf["total_pnl"] * M * fwf / wfy, abs(wf["max_drawdown"]) * M * fwf
        nl, dl = lb["total_pnl"] * M * flb / lby, abs(lb["max_drawdown"]) * M * flb
        rows.append(dict(tag=tag, strat=str(r.get("strategy"))[:26], kind=kind, v=(r.get("validate") or {}).get("verdict"),
                         roc_wf=100 * nw / ACCT, dd_wf=dw, mar_wf=nw / dw if dw else 0, so_wf=wf.get("sortino") or 0,
                         n_wf=wf.get("num_trades"), roc_lb=100 * nl / ACCT, dd_lb=dl, mar_lb=nl / dl if dl else 0))
    add("RAW", uw, ul)
    for t in gv.get("tilts") or []:
        add("TILT %s %s" % (t.get("model"), t.get("scheme")), t.get("wf_rng"), t.get("lockbox"))
    if isinstance(gv.get("keel"), dict):
        add("KEEL %s" % gv["keel"].get("version"), gv["keel"].get("wf_rng"), gv["keel"].get("lockbox"))
    for h in gv.get("hybrids") or []:
        wf, lb = h.get("wf_rng"), h.get("lockbox")
        if not wf or not lb or not wf.get("num_trades") or not lb.get("num_trades"):
            continue
        add("HYBRID %s" % h["model"], wf, lb)
        add("HYBRID-R %s" % h["model"], wf, lb, uw["num_trades"] / wf["num_trades"], ul["num_trades"] / lb["num_trades"])
print(len(rows), "rows from", len({x["tag"] for x in rows}), "runs  (WF here = champion replayed over WF years, the 1E WF column)")
hdr = "%-16s %-26s %-18s %-5s %6s %7s %5s %5s %5s | %6s %7s %5s" % ("run", "file", "row", "verd", "ROCwf", "DDwf", "MAR", "SORT", "n", "ROClb", "DDlb", "MARlb")
def show(title, key, n=25, filt=lambda x: True):
    print("\n" + title + "\n" + hdr)
    for x in sorted(filter(filt, rows), key=key, reverse=True)[:n]:
        print("%-16s %-26s %-18s %-5s %6.1f %7.0f %5.2f %5.2f %5s | %6.1f %7.0f %5.2f" % (x["tag"][:16], x["strat"], x["kind"][:18], str(x["v"])[:5],
              x["roc_wf"], x["dd_wf"], x["mar_wf"], x["so_wf"], x["n_wf"], x["roc_lb"], x["dd_lb"], x["mar_lb"]))
show("TOP BY WF ROC %/YR - any row", lambda x: x["roc_wf"])
show("TOP BY WF ROC %/YR - RAW only", lambda x: x["roc_wf"], filt=lambda x: x["kind"] == "RAW")
show("TOP BY WF MAR - RAW only, >=200 WF trades", lambda x: x["mar_wf"], filt=lambda x: x["kind"] == "RAW" and (x["n_wf"] or 0) >= 200)
