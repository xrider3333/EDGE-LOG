"""TTM QL_GAMMA_ORB (idea 20261015-1301-shelf30) - STAGE 2 COMPARE + TRACE. Written AFTER the stage-1 output sha f4ab6bfe...
was posted to MANAGER (#1266); the lab's numbers_pre_wf.json / pre_wf_trades.csv / sandbox_pre_wf_out.json and the plugin are
read here for the first time as numbers (disclosed).

(1) Arm A (plugin via the engine, TTM booking) vs the lab's numbers_pre_wf.json field by field, and vs the lab's two trade lists
    (pre_wf_trades.csv, sandbox_pre_wf_out.json) trade for trade; the lab's CSV is also re-booked through TTM's scorer.
(2) TTM's own rule with each slip as a switch: 'plugin' (the plugin's way) or 'literal' (TTM's stage-1 reading of the prereg).
    All switches 'plugin' must match the plugin 752/752 trade for trade; all 'literal' must reproduce the frozen Arm B
    (trade sha abff2221...). Each slip is then flipped ALONE to its literal reading (others plugin-way) and scored.
(3) Look-ahead probe: flatten every bar from each trade's fill bar to its session end (keep the fill bar's OPEN); every
    entry (bar, side, price) must survive.
Writes ttm_trace.json in this folder only.  Usage: python ttm_trace_20261015-1301-shelf30.py"""
import csv
import hashlib
import importlib.util
import json
import os
import types

import numpy as np
import pandas as pd

HERE = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261015-1301-shelf30"
spec = importlib.util.spec_from_file_location("v", HERE + "/ttm_verify_20261015-1301-shelf30.py")
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)              # sets AUGUR_TRIAL_CACHE=0 before augur_engine is imported
assert os.environ.get("AUGUR_TRIAL_CACHE") == "0"
LAB_NUM = V.IDEA + "/numbers_pre_wf.json"
LAB_CSV = V.IDEA + "/pre_wf_trades.csv"
LAB_SBX = V.IDEA + "/sandbox_pre_wf_out.json"
RB, LB, SF = 6, 20, 0.5
PLUGIN_WAY = {"warmup": "plugin", "zeros": "plugin", "scan_end": "plugin", "short": "plugin", "stop": "formula"}


def rule(o, h, l, c, day_id, sw):
    """TTM's own rule; each slip is a switch. Returns [(entry_bar, exit_bar, side, entry_px, exit_px, gross_pts)]."""
    n = len(c)
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    hist, out = [], []
    for s, e in zip(starts, ends):
        nb = e - s
        # range sample: plugin -> every session is a sample, <= RB bars = 0.0; literal -> only sessions with >= RB bars
        if sw["zeros"] == "plugin":
            rg_s = 0.0 if nb <= RB else float(h[s:s + RB].max() - l[s:s + RB].min())
        else:
            if nb < RB:
                continue
            rg_s = float(h[s:s + RB].max() - l[s:s + RB].min())
        prior = np.array(hist[-LB:], float)
        hist.append(rg_s)
        # short session: plugin skips <= RB+2 bars, literal (TTM) skips < RB+2
        if (nb <= RB + 2) if sw["short"] == "plugin" else (nb < RB + 2):
            continue
        hi, lo = float(h[s:s + RB].max()), float(l[s:s + RB].min())
        rg = hi - lo
        if rg <= 0:
            continue
        # warm-up: literal needs a full LB prior samples; plugin takes what there is (>= 3 after the zero filter)
        if sw["warmup"] == "literal" and len(prior) < LB:
            continue
        if sw["zeros"] == "plugin":
            prior = prior[prior > 0]                 # plugin drops zero ranges from the median window
        if len(prior) < (3 if sw["warmup"] == "plugin" else 1):
            continue
        if rg < float(np.median(prior)):
            continue
        last_k = e - 3 if sw["scan_end"] == "plugin" else e - 2   # plugin range(a+rb, b-2); literal: k+1 in session
        side, k = 0, -1
        for kk in range(s + RB, last_k + 1):
            if c[kk] > hi:
                side, k = 1, kk
                break
            if c[kk] < lo:
                side, k = -1, kk
                break
        if side == 0:
            continue
        ent = k + 1
        ep = float(o[ent])
        stop = ep - side * SF * rg if sw["stop"] == "formula" else 0.5 * (hi + lo)
        xb, xp = e - 1, float(c[e - 1])
        for j in range(ent, e):
            if j > ent or sw["stop"] != "formula":
                if side * (o[j] - stop) <= 0:            # opens at/past the stop -> books the open
                    xb, xp = j, float(o[j])
                    break
            if (l[j] <= stop) if side > 0 else (h[j] >= stop):
                xb, xp = j, float(stop)
                break
        out.append((int(ent), int(xb), int(side), ep, xp, float(side * (xp - ep))))
    return out


def cmp(Ta, B):
    ka = {(t[0], t[2]): t for t in Ta}
    kb = {(t[0], t[2]): t for t in B}
    both = set(ka) & set(kb)
    exact = sum(1 for k in both if ka[k][1] == kb[k][1] and abs(ka[k][3] - kb[k][3]) < 1e-9 and abs(ka[k][4] - kb[k][5]) < 1e-9)
    return {"A": len(Ta), "mine": len(B), "same_entry_side": len(both), "exact": exact,
            "only_A": len(set(ka) - set(kb)), "only_mine": len(set(kb) - set(ka)),
            "match_100pct": bool(exact == len(Ta) == len(B))}


def four_str(f):
    return ("ROC@30k %.2f | DD5 $%s | DD%% from peak %.1f%% | Sortino %.2f | trades %s (%d/yr) | $/yr %s"
            % (f["roc30"], format(round(f["dd5"]), ","), f["dd_pct_peak"], f["sortino"], format(f["trades"], ","),
               round(f["trades_per_yr"]), format(round(f["per_yr"]), ",")))


def slim(f):
    return {k: f[k] for k in ("trades", "trades_per_yr", "net_usd", "per_yr", "roc30", "dd5", "one_episode", "max_dd",
                              "dd_pct_peak", "sortino", "win_rate")} | {"four": four_str(f)}


def main():
    row, A, idxn, days, o, h, l, c, day_id = V.load()
    assert V.lf_sha(V.PLUGIN) == V.PIN_PREREG_FULL, "plugin pin"
    m = types.ModuleType("ttm_trace_gamma_orb")
    m.__file__ = V.PLUGIN
    exec(compile(open(V.PLUGIN, encoding="utf-8").read(), V.PLUGIN, "exec"), m.__dict__)
    r = V.run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in r["trades"]]   # entry, exit, side, px, pts
    assert V.trades_sha(Ta) == "d5d59e7e36c2456a85c3294bbff31a5200b0b4deaa203dc3e29058e63e74a5a7", "arm A = stage 1"
    exA, ptA = [t[1] for t in Ta], [t[4] for t in Ta]
    res = {"plugin_lf_sha256": V.lf_sha(V.PLUGIN), "trace_src_lf_sha256": V.lf_sha(__file__),
           "stage1_output_sha256": hashlib.sha256(open(HERE + "/ttm_verify.json", "rb").read()).hexdigest()}
    Ah, Ar, As = (V.score(exA, ptA, idxn, days, cst) for cst in (V.COST, V.REAL_COST, V.STRESS_COST))
    res["arm_A"] = {"house": slim(Ah), "real": slim(Ar), "stress": slim(As),
                    "win_rate_gross_pct": 100.0 * float(np.mean(np.array(ptA) > 0)),
                    "win_rate_net_house_pct": 100.0 * Ah["win_rate"]}

    # ---- (1) lab numbers file, field by field ----
    L = json.load(open(LAB_NUM, encoding="utf-8"))["numbers"]
    tol = {"trades": ("trades", 0), "net_usd": ("net_usd", 1.0), "roc_30k": ("roc30", 0.005), "dd5_usd": ("dd5", 1.0),
           "max_dd_usd": ("max_dd", 1.0), "dd_pct_peak": ("dd_pct_peak", 0.01), "sortino": ("sortino", 0.001)}
    rows = []
    for lk, (mk, t) in tol.items():
        rows.append({"field": lk, "lab": L[lk], "mine": Ah[mk], "abs_diff": abs(float(L[lk]) - float(Ah[mk])),
                     "tol": t, "match": abs(float(L[lk]) - float(Ah[mk])) <= t})
    rows.append({"field": "one_episode", "lab": L["one_episode"], "mine": Ah["one_episode"], "tol": "equal",
                 "match": bool(L["one_episode"]) == Ah["one_episode"]})
    wr_l = float(L["win_rate"]) if float(L["win_rate"]) > 1 else 100.0 * float(L["win_rate"])
    rows.append({"field": "win_rate", "lab": L["win_rate"], "mine": 100.0 * Ah["win_rate"], "tol": 0.05,
                 "abs_diff": abs(wr_l - 100.0 * Ah["win_rate"]), "match": abs(wr_l - 100.0 * Ah["win_rate"]) <= 0.05})
    for lk, mk, t in (("trades_per_year", "trades_per_yr", 0.05), ("years", "years", 0.0005), ("sessions", None, 0)):
        mv = len(days) if mk is None else Ah[mk]
        rows.append({"field": lk + " (extra)", "lab": L[lk], "mine": mv, "tol": t, "match": abs(float(L[lk]) - mv) <= t})
    res["lab_numbers_vs_arm_A"] = rows

    # ---- (1b) lab trade lists, trade for trade ----
    def tl_cmp(lab):   # lab rows: (entry, exit, net_pts, side, entry_px)
        ka = {(t[0], t[2]): t for t in Ta}
        kl = {(int(x[0]), int(x[3])): x for x in lab}
        both = set(ka) & set(kl)
        ex = sum(1 for k in both if ka[k][1] == int(kl[k][1]) and abs(ka[k][3] - float(kl[k][4])) < 1e-9
                 and abs((ka[k][4] - V.COST) - float(kl[k][2])) < 5e-6)
        return {"lab_trades": len(lab), "A_trades": len(Ta), "same_entry_side": len(both), "exact_exit_px_netpts": ex,
                "only_A": len(set(ka) - set(kl)), "only_lab": len(set(kl) - set(ka)), "match_100pct": ex == len(Ta) == len(lab)}
    with open(LAB_CSV, newline="", encoding="utf-8") as f:
        cr = list(csv.DictReader(f))
    lab_csv = [(int(x["entry_bar"]), int(x["exit_bar"]), float(x["pnl_points_net"]), int(x["side"]), float(x["entry_price"]))
               for x in cr]
    res["lab_csv_vs_arm_A"] = tl_cmp(lab_csv)
    idx_tz = pd.DatetimeIndex(A["index"])
    res["lab_csv_vs_arm_A"]["timestamps_match"] = sum(
        1 for x in cr if pd.Timestamp(x["entry_time"]) == idx_tz[int(x["entry_bar"])]
        and pd.Timestamp(x["exit_time"]) == idx_tz[int(x["exit_bar"])])
    # re-book the lab's own CSV (net pts, exit_time ET date) through TTM's scorer
    usd = pd.Series([float(x["pnl_points_net"]) * V.MULT for x in cr],
                    index=pd.DatetimeIndex([pd.Timestamp(x["exit_time"]).tz_localize(None).normalize() for x in cr]))
    s = usd.groupby(level=0).sum().reindex(days, fill_value=0.0)
    res["lab_csv_rebooked_four"] = V.four(s.to_numpy(), days)
    sbx = json.load(open(LAB_SBX, encoding="utf-8"))
    res["lab_sandbox_trades_vs_arm_A"] = tl_cmp([tuple(t) for t in sbx["trades"]])
    res["lab_sandbox_meta"] = {k: sbx[k] for k in ("bars", "first", "last", "fingerprint", "master", "params")}

    # ---- (2) slips: plugin way vs literal ----
    B_plugin = rule(o, h, l, c, day_id, PLUGIN_WAY)
    res["plugin_way_vs_A"] = cmp(Ta, B_plugin)
    lit_all = {"warmup": "literal", "zeros": "literal", "scan_end": "literal", "short": "literal", "stop": "formula"}
    B_lit = rule(o, h, l, c, day_id, lit_all)
    res["all_literal_reproduces_frozen_arm_B"] = {"sha256": V.trades_sha(B_lit), "frozen": V.json.load(
        open(HERE + "/b_freeze.json"))["B_trades_sha256"], "trades": len(B_lit)}
    res["all_literal_reproduces_frozen_arm_B"]["equal"] = (res["all_literal_reproduces_frozen_arm_B"]["sha256"]
                                                           == res["all_literal_reproduces_frozen_arm_B"]["frozen"])
    slips = {}
    for nm, sw in (("S1_warmup_full20", {"warmup": "literal"}), ("S2_keep_zero_ranges", {"zeros": "literal"}),
                   ("S3_scan_to_second_last_bar", {"scan_end": "literal"}), ("S4_short_lt8", {"short": "literal"}),
                   ("S5_true_midpoint_stop", {"stop": "midpoint"}), ("ALL_literal_eq_arm_B", lit_all),
                   ("ALL_literal_plus_true_midpoint", lit_all | {"stop": "midpoint"})):
        T = rule(o, h, l, c, day_id, PLUGIN_WAY | sw)
        ex, pt = [t[1] for t in T], [t[5] for t in T]
        slips[nm] = {"switch": sw, "vs_A": cmp(Ta, T), "gross_pts": float(np.sum(pt)),
                     "house": slim(V.score(ex, pt, idxn, days, V.COST)), "real": slim(V.score(ex, pt, idxn, days, V.REAL_COST)),
                     "stress": slim(V.score(ex, pt, idxn, days, V.STRESS_COST))}
    res["slips"] = slips
    # diagnostics: how often each slip's condition occurs
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], len(c)]
    nbs = ends - starts
    ors = np.array([h[s_:s_ + RB].max() - l[s_:s_ + RB].min() if e_ - s_ >= RB else np.nan for s_, e_ in zip(starts, ends)])
    res["diagnostics"] = {"sessions": int(len(starts)), "min_bars": int(nbs.min()), "sessions_le_8_bars": int((nbs <= 8).sum()),
                          "sessions_eq_8_bars": int((nbs == 8).sum()), "sessions_le_6_bars": int((nbs <= 6).sum()),
                          "zero_opening_ranges": int(np.nansum(ors <= 0)),
                          "session_bar_counts": {str(k): int(v) for k, v in zip(*np.unique(nbs, return_counts=True))},
                          "A_trades_before_session_21": int(sum(1 for t in Ta if idxn[t[0]] <= days[LB])),
                          "session_20_date": str(days[LB - 1].date())}

    # ---- (3) look-ahead probe: flatten every bar from each fill bar to session end at the fill OPEN ----
    A2 = dict(A)
    o2, h2, l2, c2 = o.copy(), h.copy(), l.copy(), c.copy()
    sess_end = {int(b): int(e_) for s_, e_ in zip(starts, ends) for b in (s_,)}
    for t in Ta:
        s_ = starts[np.searchsorted(starts, t[0], side="right") - 1]
        e_ = sess_end[int(s_)]
        px = o[t[0]]
        o2[t[0] + 1:e_] = px
        h2[t[0]:e_] = px
        l2[t[0]:e_] = px
        c2[t[0]:e_] = px
    for k_, arr in (("open", o2), ("high", h2), ("low", l2), ("close", c2)):
        A2[k_] = arr
    r2 = V.run_backtest(m, instrument="NQ", arrays=A2, params=None, cost_pts=0.0, return_trades=True)
    T2 = {(int(t[0]), int(t[3])): float(t[4]) for t in r2["trades"]}
    keep = sum(1 for t in Ta if (t[0], t[2]) in T2 and abs(T2[(t[0], t[2])] - t[3]) < 1e-9)
    res["lookahead_probe_flatten_after_fill"] = {"A_entries": len(Ta), "entries_unchanged": keep, "probe_trades": len(T2),
                                                 "pass": keep == len(Ta) == len(T2)}
    s = json.dumps(res, indent=1, sort_keys=True, default=float)
    b = (s + "\n").encode("utf-8")
    with open(HERE + "/ttm_trace.json", "wb") as f:
        f.write(b)
    print(s)
    print("trace output sha256", hashlib.sha256(b).hexdigest())


if __name__ == "__main__":
    main()
