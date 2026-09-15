# -*- coding: utf-8 -*-
"""NOISE ROUND 59 - CAPITAL BOARD: which NOISE row makes the most money per year for the drawdown it costs.

Owner, 2026-09-15: "what do YOU think the best NOISE config (ML or not) is to run" - judged on walk-forward
ROC / YR, "the most bang for our buck while keeping DD/risk in check".

Every NOISE run's saved RAW / TILT / KEEL / HYBRID / HYBRID-recycled blocks, on the WF and LB stretches.
  ROC %/yr  on a $100k account, sized exactly as COMPARE > EXPLORE sizes it (recycled hybrid = ungated trades /
            hybrid trades of the SAME stretch; LB also shown at the multiplier known BEFORE the lockbox).
  MAR       ($/yr) / max drawdown - "is the bigger drawdown paid for by the bigger PnL". Any row can be traded
            at any size; size moves ROC and drawdown together and leaves MAR and Sortino unchanged.
  SORTINO   the engine's annualised Sortino (time-aware, unchanged by any size multiplier).
Runs #202/#203 predate the 2026-08-10 ML look-ahead fix; their GATE/TILT/HYBRID rows are optimistic.

  python tools/r59_noise_capital_board.py --pull   # one Firestore read of the NOISE runs (not a loop)
  python tools/r59_noise_capital_board.py          # rebuild the board from the saved read
The read is saved OUTSIDE the repo (C:\\EdgeLog\\r59_noise_gv.json, ~1.5 MB). Result: r37_results/r59_capital_board.txt
"""
import datetime, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("EDGELOG_R59_DATA", r"C:\EdgeLog\r59_noise_gv.json")
M, ACCT = 20.0, 100000.0


def pull():
    import firebase_admin
    from firebase_admin import credentials, firestore
    from google.cloud.firestore_v1.base_query import FieldFilter
    cred = os.path.join(ROOT, "serviceAccount.json")
    if not os.path.exists(cred):
        cred = os.path.join(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG", "serviceAccount.json")
    firebase_admin.initialize_app(credentials.Certificate(cred))
    u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")
    G = ["ungated_is", "ungated_wf", "ungated_lockbox", "ungated_pre", "ungated_full", "hybrids", "tilts", "keel",
         "chosen", "wf_range", "lockbox_from", "span"]
    q = (u.collection("runs").where(filter=FieldFilter("strategy", ">=", "NOISE"))
         .where(filter=FieldFilter("strategy", "<", "NOISF"))
         .select(["id", "strategy", "famKey", "famSeq", "date_from", "date_to", "timeframe", "cost_pts"]
                 + ["gate_validate." + g for g in G] + ["validate.verdict", "validate.pbo"]))
    out = []
    for d in q.stream():
        r = d.to_dict() or {}
        gv = r.get("gate_validate") or {}
        for row in (gv.get("hybrids") or []) + (gv.get("tilts") or []) + [gv.get("keel") or {}]:
            row.pop("equity", None)
        out.append(r)
    json.dump(out, open(DATA, "w"), default=str)
    print(len(out), "NOISE runs saved to", DATA)


def yrs(a, b):
    return (datetime.date.fromisoformat(str(b)[:10]) - datetime.date.fromisoformat(str(a)[:10])).days / 365.25


def board():
    rows = []
    for r in json.load(open(DATA)):
        gv = r.get("gate_validate") or {}
        wr = gv.get("wf_range")
        if not (isinstance(wr, list) and len(wr) == 2 and gv.get("ungated_wf") and gv.get("ungated_lockbox")):
            continue
        wfy = yrs(wr[0], wr[1])
        end = (gv.get("span") or [None, r.get("date_to")])[1] or r.get("date_to")
        lby = yrs(gv.get("lockbox_from") or wr[1], end)
        uw, ul, up = gv["ungated_wf"], gv["ungated_lockbox"], gv.get("ungated_pre") or {}
        tag = "#%s %s-%s" % (r.get("id"), r.get("famKey") or "NOISE", r.get("famSeq") or "?")

        def add(kind, wf, lb, fwf=1.0, flb=1.0, flb_pre=None):
            if not wf or not lb or not wf.get("num_trades") or lby <= 0.2:
                return
            nw, dw = wf["total_pnl"] * M * fwf / wfy, abs(wf["max_drawdown"]) * M * fwf
            nl, dl = lb["total_pnl"] * M * flb / lby, abs(lb["max_drawdown"]) * M * flb
            rows.append(dict(tag=tag, strat=str(r.get("strategy"))[:-3], kind=kind, tf=r.get("timeframe"),
                             cost=r.get("cost_pts"), roc_wf=100 * nw / ACCT, dd_wf=dw, mar_wf=nw / dw if dw else 0,
                             so_wf=wf.get("sortino") or 0, pf_wf=wf.get("profit_factor") or 0,
                             roc_lb=100 * nl / ACCT, dd_lb=dl, mar_lb=nl / dl if dl else 0,
                             so_lb=lb.get("sortino") or 0, pf_lb=lb.get("profit_factor") or 0,
                             pre=(100 * lb["total_pnl"] * M * flb_pre / lby / ACCT) if flb_pre else None))

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
            add("HYBRID-R %s" % h["model"], wf, lb, uw["num_trades"] / wf["num_trades"],
                ul["num_trades"] / lb["num_trades"], (up.get("num_trades") or 0) / max(1, h.get("kept_pre") or 1))

    hdr = "%-17s %-22s %-18s %6s %7s %5s %5s %5s | %6s %7s %5s %5s %5s %6s %8s" % (
        "run", "file", "row", "ROC%wf", "DDwf$", "MAR", "SORT", "PF", "ROC%lb", "DDlb$", "MAR", "SORT", "PF",
        "lbPRE%", "@30kDD")

    def show(title, key, n=30, filt=lambda x: True):
        print("\n" + title + "\n" + hdr)
        for x in sorted(filter(filt, rows), key=key, reverse=True)[:n]:
            print("%-17s %-22s %-18s %6.1f %7.0f %5.2f %5.2f %5.2f | %6.1f %7.0f %5.2f %5.2f %5.2f %6s %4.0f/%-3.0f" % (
                x["tag"], x["strat"][:22], x["kind"][:18], x["roc_wf"], x["dd_wf"], x["mar_wf"], x["so_wf"],
                x["pf_wf"], x["roc_lb"], x["dd_lb"], x["mar_lb"], x["so_lb"], x["pf_lb"],
                ("%.1f" % x["pre"]) if x["pre"] is not None else "-", 30 * x["mar_wf"], 30 * x["mar_lb"]))

    clean = lambda x: x["tf"] == "5m" and abs(float(x["cost"] or 0) - 0.533) < 1e-6 and not x["tag"].startswith(("#202 ", "#203 "))
    print("%d rows from %d runs. @30kDD = ROC %%/yr (WF/LB) if sized so the stretch's worst drawdown is $30k." % (
        len(rows), len({x["tag"] for x in rows})))
    show("TOP BY WF ROC %/YR (EXPLORE's sort) - 5m, cost 0.533, post look-ahead fix", lambda x: x["roc_wf"], filt=clean)
    show("TOP BY WF MAR - same filter", lambda x: x["mar_wf"], filt=clean)
    show("TOP BY WF SORTINO - same filter", lambda x: x["so_wf"], filt=clean)
    show("HYBRID-R xgb ON EVERY RUN (walk-forward leader vs its lockbox)", lambda x: x["roc_wf"], 40,
         lambda x: clean(x) and x["kind"] == "HYBRID-R xgb")


if __name__ == "__main__":
    if "--pull" in sys.argv or not os.path.exists(DATA):
        pull()
    board()
