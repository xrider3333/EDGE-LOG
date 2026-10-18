"""TTM SLEEVE5 r2 - the TTM 4-cell sleeve as a fifth book component, round 2 (docs/PREREG_TTM_SLEEVE5_R2_2026-10-18.txt).

Usage: python tools/ttm_verify/ttm_sleeve5_r2.py --expect-prereg <LF sha256> --expect-harness <LF sha256> [--no-records]
RUN-BEFORE-MAIN: both hashes were posted to MANAGER before the run; the harness stops on a mismatch.
Reads the #463 fixture (tests/fixtures/four_numbers/book463_wf_lb_daily.csv) and runs only the sleeve's four cells through
augur_engine.book._leg_trades. Writes C:/EdgeLog/_anatomy_cache/ttm_sleeve5_r2/results.json and, unless --no-records, the JSONL
lines of prereg section 8 into C:/EdgeLog/run_records/TTM_202610.jsonl."""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import socket
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools", "rocfrontier"))
os.chdir(REPO)
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from augur_engine import book  # noqa: E402
from augur_engine.drawdowns import episodes, four_numbers  # noqa: E402
import r12_mdl as R12  # noqa: E402

PREREG = os.path.join(REPO, "docs", "PREREG_TTM_SLEEVE5_R2_2026-10-18.txt")
FIX = os.path.join(REPO, "tests", "fixtures", "four_numbers", "book463_wf_lb_daily.csv")
DEPS = ["augur_engine/drawdowns.py", "augur_engine/book.py", "augur_strategies/TTMSQZ_3_0.py", "tools/rocfrontier/r12_mdl.py",
        "tools/rocfrontier/r11_risk.py"]
OUT = "C:/EdgeLog/_anatomy_cache/ttm_sleeve5_r2"
REC = "C:/EdgeLog/run_records/TTM_202610.jsonl"
W0, W1 = "2010-06-07", "2026-06-30"
STRETCHES = {"pre": (pd.Timestamp("2010-06-07"), pd.Timestamp("2016-06-30")),
             "wf": (pd.Timestamp("2016-07-01"), pd.Timestamp("2025-06-29")),
             "lb": (pd.Timestamp("2025-06-30"), pd.Timestamp("2026-06-30"))}
STAGE = {"pre": "preWF", "wf": "WF", "lb": "LB"}
CROWN = dict(length=20, bb_mult=2.0, kc_mult=1.5, min_sq_bars=1, entry_fill="open", exit_mode="fade", fade_bars=1, stop_atr=1.5,
             eod_cutoff=1, gate_tf_min=60, gate_mode="sq_on", gate_len=20, gate_bars=2, gate_ratio=1.0, gate_fired_k=3, direction="both")
CELLS = (("ES", "30m"), ("ES", "15m"), ("NQ", "30m"), ("NQ", "15m"))
MULT = {"ES": 50, "NQ": 20}
COSTS = {"G": {"ES": 0.0, "NQ": 0.0}, "L0": {"ES": 0.363, "NQ": 0.533}, "L1": {"ES": 0.613, "NQ": 0.7825},
         "L2": {"ES": 1.113, "NQ": 1.2825}, "L3": {"ES": 1.613, "NQ": 1.7825}}
LEVELS = ("L0", "L1", "L2", "L3")
REF_WF = (93.81, 36095, 13.09, 3.816, False)
REF_LB = (155.54, 35034, 18.33, 4.150, True)
R1_SLEEVE_WF_NET_L0 = 1398629.8307546282 - 1246751.0882546285        # round 1 ADD WF net - #463 WF net (sleeve_results.json)


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def pub(f):
    return (round(f["roc30"], 2) if f["roc30"] is not None else None, round(f["dd5_usd"]), round(f["dd_pct_peak"], 2),
            round(f["sortino"], 3) if f["sortino"] is not None else None, bool(f["one_episode"]))


def fn(series):
    f = four_numbers(series)
    ep = [e for e in episodes(series.to_numpy(float), dates=list(series.index)) if e["depth"] > 0]
    w = max(ep, key=lambda e: e["depth"]) if ep else None
    f["worst_episode"] = {"peak": w["peak"], "trough": w["trough"], "recovered": w["recovered"], "depth": round(w["depth"], 2)} if w else None
    return f


def short(f):
    w = f.get("worst_episode") or {}
    return "ROC@30k %s | DD5 $%s%s | DD%% %.2f | Sortino %s | $/yr %s | worst $%s %s..%s (rec %s)" % (
        ("%.2f" % f["roc30"]) if f["roc30"] is not None else "None", "{:,.0f}".format(f["dd5_usd"]), " ONE-EP" if f["one_episode"] else "",
        f["dd_pct_peak"], ("%.3f" % f["sortino"]) if f["sortino"] is not None else "None", "{:,.0f}".format(f["net_per_year"]),
        "{:,.0f}".format(w.get("depth") or 0), w.get("peak"), w.get("trough"), w.get("recovered"))


def cut(s, key):
    lo, hi = STRETCHES[key]
    return s[(s.index >= lo) & (s.index <= hi)]


def on_cal(s, cal):
    extra = s.index.difference(cal)
    return s.reindex(cal.union(extra)).fillna(0.0), len(extra)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect-prereg", required=True)
    ap.add_argument("--expect-harness", required=True)
    ap.add_argument("--no-records", action="store_true")
    a = ap.parse_args()
    hp, hh = lf_sha(PREREG), lf_sha(os.path.abspath(__file__))
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print("P4 prereg  LF sha256 %s (expected %s)" % (hp, a.expect_prereg))
    print("P4 harness LF sha256 %s (expected %s)" % (hh, a.expect_harness))
    deps = {d: lf_sha(os.path.join(REPO, d)) for d in DEPS}
    print("P4 git HEAD %s; deps %s" % (head, json.dumps({k: v[:12] for k, v in deps.items()})))
    if hp != a.expect_prereg or hh != a.expect_harness:
        sys.exit("P4 STOP: hash mismatch")
    os.makedirs(OUT, exist_ok=True)
    res = {"hashes": {"prereg": hp, "harness": hh, "git_head": head, "deps": deps}}

    fx = pd.read_csv(FIX, index_col=0, parse_dates=True)["book"].astype(float).sort_index()
    ref = {"wf": fn(cut(fx, "wf")), "lb": fn(cut(fx, "lb"))}
    print("R1 #463 WF:", short(ref["wf"]))
    print("R1 #463 LB:", short(ref["lb"]))
    if pub(ref["wf"]) != REF_WF or pub(ref["lb"]) != REF_LB:
        sys.exit("P1 STOP: #463 fixture does not reproduce %s / %s (got %s / %s)" % (REF_WF, REF_LB, pub(ref["wf"]), pub(ref["lb"])))
    print("P1 OK")
    res["ref"] = ref

    # ---- the sleeve, cell by cell, at every cost level (G first: P3 on every stretch) -----------------------------------
    cells, cellinfo = {}, {}
    for lvl in ("G",) + LEVELS:
        for inst, tf in CELLS:
            leg = {"strategy": "TTMSQZ_3_0.py", "instrument": inst, "timeframe": tf, "session": "rth", "source": "db_adj_rth",
                   "params": dict(CROWN), "cost_pts": COSTS[lvl][inst], "mult": MULT[inst], "weight": 1}
            tr, inf = book._leg_trades(leg, W0, W1)
            if inf.get("session") != "rth" or inf.get("source") != "db_adj_rth" or "mtm_error" in inf:
                sys.exit("P3 STOP: %s %s %s ran on %s / %s (mtm_error %s)" % (lvl, inst, tf, inf.get("session"), inf.get("source"), inf.get("mtm_error")))
            m = inf.pop("_mtm_day", None)
            if m is None:
                sys.exit("P3 STOP: %s %s %s has no valued-daily series" % (lvl, inst, tf))
            d, v = book._daily(m)
            daily = pd.Series(v, index=pd.to_datetime(d)).groupby(level=0).sum()
            td = pd.Series([float(x[1]) for x in tr], index=pd.to_datetime([x[0] for x in tr]))
            cells[(lvl, inst, tf)] = {"daily": daily, "trades": td}
            if lvl == "G":
                cellinfo["%s %s" % (inst, tf)] = {"master": inf.get("master"), "roll_stamp": inf.get("roll_stamp"), "trades_total": len(td)}
                for k in STRETCHES:
                    if len(cut(td, k)) == 0:
                        sys.exit("P3 STOP: cell %s %s has no trades in %s" % (inst, tf, k))
        print("built %s: " % lvl + ", ".join("%s %s %d tr $%s" % (i, t, len(cells[(lvl, i, t)]["trades"]),
              "{:,.0f}".format(cells[(lvl, i, t)]["trades"].sum())) for i, t in CELLS), flush=True)
    for c, ci in cellinfo.items():
        print("P3 cell %s: master %s, roll stamp %s" % (c, ci["master"], json.dumps(ci["roll_stamp"], default=str)[:160]))
    res["cells_info"] = cellinfo

    def sleeve(lvl):
        return pd.concat([cells[(lvl, i, t)]["daily"] for i, t in CELLS]).groupby(level=0).sum().sort_index()

    add_cal = {k: cut(fx, k).index for k in ("wf", "lb")}
    sl_cal = {k: pd.bdate_range(*STRETCHES[k]) for k in STRETCHES}

    # P2
    s0, x0 = on_cal(cut(sleeve("L0"), "wf"), add_cal["wf"])
    p2 = float(s0.sum())
    p2d = (p2 - R1_SLEEVE_WF_NET_L0) / R1_SLEEVE_WF_NET_L0
    print("P2 sleeve WF net at L0 $%s vs round 1 $%s: %+.2f $ (%+.3f%%)" % ("{:,.2f}".format(p2), "{:,.2f}".format(R1_SLEEVE_WF_NET_L0),
          p2 - R1_SLEEVE_WF_NET_L0, 100 * p2d))
    res["p2"] = {"now": p2, "round1": R1_SLEEVE_WF_NET_L0, "diff": p2 - R1_SLEEVE_WF_NET_L0, "rel": p2d}
    if abs(p2d) > 0.02:
        sys.exit("P2 STOP: sleeve WF net moved more than 2% from round 1")

    # ---- R2 gross per trade ---------------------------------------------------------------------------------------------
    gross = {}
    for k in STRETCHES:
        yrs = ((STRETCHES[k][1] - STRETCHES[k][0]).days) / 365.25
        g_tr = {c: cut(cells[("G",) + c]["trades"], k) for c in CELLS}
        n = {c: len(g_tr[c]) for c in CELLS}
        row = {"%s %s" % c: {"trades": n[c], "trades_per_year": n[c] / yrs, "gross_pt_per_trade": float(g_tr[c].sum() / n[c] / MULT[c[0]]),
                             "cost_pt_L1": COSTS["L1"][c[0]]} for c in CELLS}
        tot_g = sum(float(g_tr[c].sum()) for c in CELLS)
        tot_c = sum(n[c] * COSTS["L1"][c[0]] * MULT[c[0]] for c in CELLS)
        ntr = sum(n.values())
        row["pooled"] = {"trades": ntr, "trades_per_year": ntr / yrs, "gross_usd_per_trade": tot_g / ntr, "cost_usd_per_trade_L1": tot_c / ntr,
                         "gross_ge_cost": tot_g / ntr >= tot_c / ntr}
        gross[k] = row
        print("R2 gross %s: " % k + " | ".join("%s %d tr (%.1f/yr) gross %.3f pt vs cost %.4g" % (c, r["trades"], r["trades_per_year"],
              r["gross_pt_per_trade"], r["cost_pt_L1"]) for c, r in row.items() if c != "pooled")
              + " || pooled gross $%.2f vs cost $%.2f per trade -> %s" % (row["pooled"]["gross_usd_per_trade"], row["pooled"]["cost_usd_per_trade_L1"],
                                                                         "gross >= cost" if row["pooled"]["gross_ge_cost"] else "gross < cost"))
    res["gross"] = gross

    # ---- R2 per cell at L1 ----------------------------------------------------------------------------------------------
    percell = {}
    for inst, tf in CELLS:
        c = "%s %s" % (inst, tf)
        percell[c] = {}
        for k in STRETCHES:
            x, _ = on_cal(cut(cells[("L1", inst, tf)]["daily"], k), sl_cal[k])
            percell[c][k] = fn(x)
            print("R2 cell %s %s L1: %s" % (c, k, short(percell[c][k])))
    res["percell_L1"] = percell

    # ---- R2 sleeve alone, R3 ADD + deltas, R6 ---------------------------------------------------------------------------
    res["sleeve"], res["add"], res["delta"] = {}, {}, {}
    for lvl in LEVELS:
        s = sleeve(lvl)
        sl = {}
        for k in STRETCHES:
            x, extra = on_cal(cut(s, k), sl_cal[k])
            sl[k] = fn(x)
            sl[k]["extra_days"] = extra
            sl[k]["trades"] = int(sum(len(cut(cells[(lvl,) + c]["trades"], k)) for c in CELLS))
            print("%s SLEEVE %-3s %s | trades %d | extra days %d" % (lvl, k, short(sl[k]), sl[k]["trades"], extra))
        res["sleeve"][lvl] = sl
        ad = {}
        for k in ("wf", "lb"):
            x, extra = on_cal(cut(s, k), add_cal[k])
            b = cut(fx, k).reindex(x.index).fillna(0.0)
            ad[k] = fn(b + x)
            ad[k]["extra_days"] = extra
            print("%s ADD    %-3s %s | extra days %d" % (lvl, k, short(ad[k]), extra))
        res["add"][lvl] = ad
        dl = {"roc30": ad["wf"]["roc30"] - ref["wf"]["roc30"], "dd5_usd": ad["wf"]["dd5_usd"] - ref["wf"]["dd5_usd"],
              "dd_pct_peak": ad["wf"]["dd_pct_peak"] - ref["wf"]["dd_pct_peak"], "sortino": ad["wf"]["sortino"] - ref["wf"]["sortino"],
              "net_per_year": ad["wf"]["net_per_year"] - ref["wf"]["net_per_year"]}
        res["delta"][lvl] = dl
        print("{} ADD - #463 on WF: ROC {:+.2f} | DD5 {:+,.0f} | DD% {:+.2f} | Sortino {:+.3f} | $/yr {:+,.0f}".format(
            lvl, dl["roc30"], dl["dd5_usd"], dl["dd_pct_peak"], dl["sortino"], dl["net_per_year"]), flush=True)

    # ---- R4 folds at L1 -------------------------------------------------------------------------------------------------
    s1, _ = on_cal(cut(sleeve("L1"), "wf"), add_cal["wf"])
    b1 = cut(fx, "wf").reindex(s1.index).fillna(0.0)
    L = (((STRETCHES["wf"][1] - STRETCHES["wf"][0]).days) + 1) / 8.0
    kf = np.floor(np.asarray((s1.index - STRETCHES["wf"][0]).days, float) / L).astype(int)
    assert kf.min() == 0 and kf.max() == 7, (kf.min(), kf.max())
    folds, up, ties, dd_ok = [], 0, 0, 0
    for i in range(8):
        mk = kf == i
        fb, fa = fn(b1[mk]), fn(b1[mk] + s1[mk])
        if fa["roc30"] is None and fb["roc30"] is None:
            lift, tie = False, True
        elif fa["roc30"] is None:
            lift, tie = True, False
        elif fb["roc30"] is None:
            lift, tie = False, False
        else:
            lift, tie = fa["roc30"] > fb["roc30"], False
        up += int(lift)
        ties += int(tie)
        dd_ok += int(fa["dd5_usd"] <= fb["dd5_usd"])
        folds.append({"fold": i + 1, "from": str(s1.index[mk][0].date()), "to": str(s1.index[mk][-1].date()), "rows": int(mk.sum()),
                      "book": fb, "add": fa, "sleeve_net": float(s1[mk].sum()), "roc_lift": lift, "tie": tie,
                      "dd5_no_worse": fa["dd5_usd"] <= fb["dd5_usd"]})
        print("fold %d %s..%s (%d rows) sleeve $%s%s\n   #463 %s\n   ADD  %s" % (i + 1, folds[-1]["from"], folds[-1]["to"], folds[-1]["rows"],
              "{:,.0f}".format(folds[-1]["sleeve_net"]), "  ROC LIFT" if lift else ("  TIE" if tie else ""), short(fb), short(fa)))
    nn = 8 - ties
    p_sign = sum(math.comb(nn, j) for j in range(nn + 1) if abs(j - nn / 2) >= abs(up - nn / 2)) / 2 ** nn if nn else None
    res["folds"] = {"rows": folds, "roc_lift_count": up, "ties": ties, "dd5_no_worse_count": dd_ok, "sign_test_p_two_sided": p_sign}
    print("R4 ADD beats #463 ROC@30k in %d of %d folds (%d ties; sign test p %s); DD5 no worse in %d of 8" % (up, nn, ties, p_sign, dd_ok))

    # ---- R5 years split -------------------------------------------------------------------------------------------------
    S1 = res["sleeve"]["L1"]
    for k in ("pre", "wf"):
        print("R5 sleeve L1 %s: ROC %.2f | $/yr %s | Sortino %.3f | gross/trade $%.2f | %.1f trades/yr" % (
            k, S1[k]["roc30"], "{:,.0f}".format(S1[k]["net_per_year"]), S1[k]["sortino"], gross[k]["pooled"]["gross_usd_per_trade"],
            gross[k]["pooled"]["trades_per_year"]))

    # ---- R7 rho_dd as MDL r1 measures it -----------------------------------------------------------------------------------
    St = R12.Stretch(b1.to_numpy(float), pd.DatetimeIndex(b1.index), None, STRETCHES["wf"][0], STRETCHES["wf"][1])
    rho_a, do_a = R12.realised(s1.to_numpy(float)[None, :], St)
    rho, do = float(rho_a[0]), float(do_a[0])
    res["rho_dd"] = {"rho": rho, "do": do, "dd_weeks": St.n_dd_weeks, "dd_days": St.n_dd_days, "qualifying_episodes": len(St.qual)}
    if not math.isfinite(rho):
        json.dump(res, open(os.path.join(OUT, "results_partial.json"), "w"), indent=1, default=str)
        sys.exit("R7 STOP: rho_dd undefined (%d DD weeks)" % St.n_dd_weeks)
    print("R7 rho_dd %.3f (MDL r1: %d qualifying episodes, %d DD days, %d DD weeks); DO %.3f" % (rho, len(St.qual), St.n_dd_days, St.n_dd_weeks, do))

    # ---- verdict (frozen section 5) -------------------------------------------------------------------------------------
    A1, A2 = res["add"]["L1"]["wf"], res["add"]["L2"]["wf"]
    lift_at = lambda A: round(A["roc30"], 2) > 93.81 and round(A["dd5_usd"]) <= 36095 and round(A["sortino"], 3) >= 3.816
    book_lift = lift_at(A1) and not A1["one_episode"] and lift_at(A2)
    band = 5 if rho < -0.45 else (15 if rho < 0.15 else (25 if rho < 0.45 else 40))
    pg = gross["wf"]["pooled"]["gross_ge_cost"]
    promising = (pg and S1["wf"]["roc30"] is not None and S1["wf"]["roc30"] > 0 and not S1["wf"]["one_episode"] and S1["wf"]["roc30"] >= band)
    veto = S1["lb"]["net"] < 0 or round(res["add"]["L1"]["lb"]["roc30"], 2) < 155.54
    verdict = "BOOK LIFT" if book_lift else ("PROMISING" if promising else "DEAD")
    if veto and verdict != "DEAD":
        verdict = "VETOED (LB)"
    dd_only = (A1["net_per_year"] > ref["wf"]["net_per_year"] and round(A1["sortino"], 3) >= 3.816 and not A1["one_episode"]
               and not (round(A1["roc30"], 2) > 93.81 and round(A1["dd5_usd"]) <= 36095))
    res["verdict"] = {"verdict": verdict, "book_lift": book_lift, "promising": promising, "mdl_band": band, "lb_veto": veto,
                      "fails_only_on_drawdown": dd_only,
                      "checks": {"add_L1_roc": round(A1["roc30"], 2) > 93.81, "add_L1_dd5": round(A1["dd5_usd"]) <= 36095,
                                 "add_L1_sortino": round(A1["sortino"], 3) >= 3.816, "add_L1_not_one_ep": not A1["one_episode"],
                                 "add_L2_lift": lift_at(A2), "gross_ge_cost": pg, "sleeve_roc_pos": (S1["wf"]["roc30"] or 0) > 0,
                                 "sleeve_not_one_ep": not S1["wf"]["one_episode"], "sleeve_roc_ge_band": (S1["wf"]["roc30"] or 0) >= band,
                                 "sleeve_lb_net_neg": S1["lb"]["net"] < 0, "add_lb_below_ref": round(res["add"]["L1"]["lb"]["roc30"], 2) < 155.54}}
    print("VERDICT:", json.dumps(res["verdict"]))
    out = os.path.join(OUT, "results.json")
    json.dump(res, open(out, "w"), indent=1, default=str)
    osha = hashlib.sha256(open(out, "rb").read()).hexdigest()
    print("results.json sha256", osha)

    if not a.no_records:
        ts = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        lines = []

        def rec(arm, stage, rid, f, trades, inst, tf, gross_pt, cost_pt, note):
            lines.append({"ts": ts, "lane": "TTM", "host": socket.gethostname(), "where": "lane", "strategy": arm, "family": "TTM",
                          "instrument": inst, "timeframe": tf, "stage": stage, "roc30k": f["roc30"], "dd5": f["dd5_usd"],
                          "ddpct": f["dd_pct_peak"], "sortino": f["sortino"], "trades": trades, "gross_pt": gross_pt, "cost_pt": cost_pt,
                          "one_episode": f["one_episode"], "ledger_row": None, "run_id": "ttm-sleeve5-r2:" + rid, "sha": hh[:12],
                          "note": ("results %s; " % osha[:12]) + note})
        for lvl in LEVELS:
            cst = "cost %s ES %.4f / NQ %.4f pt" % (lvl, COSTS[lvl]["ES"], COSTS[lvl]["NQ"])
            for k in STRETCHES:
                f = res["sleeve"][lvl][k]
                rec("TTM-SLEEVE 4-cell (TTMSQZ_3_0 #299 settings)", STAGE[k], "sleeve:%s:%s" % (k, lvl), f, f["trades"], "ES+NQ", "15m+30m",
                    None, None, "%s; pooled gross $%.2f/trade%s" % (cst, gross[k]["pooled"]["gross_usd_per_trade"], "; LB veto-only" if k == "lb" else ""))
            for k in ("wf", "lb"):
                rec("BOOK #463 + TTM-SLEEVE (ADD)", STAGE[k], "add:%s:%s" % (k, lvl), res["add"][lvl][k], None, "book", "mixed", None, None,
                    "sleeve %s; #463 legs at run costs; #463 %s = %s%s" % (cst, STAGE[k], REF_WF if k == "wf" else REF_LB, "; LB veto-only" if k == "lb" else ""))
        for inst, tf in CELLS:
            c = "%s %s" % (inst, tf)
            for k in STRETCHES:
                rec("TTMSQZ_3_0 #299 settings (sleeve cell)", STAGE[k], "cell:%s%s:%s:L1" % (inst, tf, k), percell[c][k], gross[k][c]["trades"],
                    inst, tf, round(gross[k][c]["gross_pt_per_trade"], 4), COSTS["L1"][inst], "sleeve cell at L1 real cost%s" % ("; LB veto-only" if k == "lb" else ""))
        os.makedirs(os.path.dirname(REC), exist_ok=True)
        with open(REC, "a", encoding="utf-8") as fh:
            for ln in lines:
                fh.write(json.dumps(ln, default=str) + "\n")
        print("records: %d lines appended to %s" % (len(lines), REC))


if __name__ == "__main__":
    main()
