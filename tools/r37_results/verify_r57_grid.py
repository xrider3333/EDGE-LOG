# -*- coding: utf-8 -*-
"""INDEPENDENT VERIFIER for ENGU-Q round 57, order-of-work items 1-3 (grid + S1-S9).

Written by a verifier session that did not trust tools/r57_grid.py or tools/r57_sel_parity_gates.py.
It re-uses only the ENGINE (augur_engine.engine.run_backtest) and the sibling strategy file
(augur_strategies/ENGUQ_1M_ETH_SEL_1_0.py). Metrics, the spec features and the clauses are computed
here from the pre-registration text (ENGUQ_R57_PREREG.md, a7f0811), NOT from measure().

PART 1  control + all 12 cells at R2 settings (params typed from prereg section 1, every one explicit),
        cost 0.533, $20/pt, one continuous backtest each; trades with entry bar >= the first bar at or after
        2025-06-30 00:00 ET are dropped unread. Own n / win / PF / net / E1-E2 top-10 share; S1-S3 on the
        centres; S9 on every neighbour; compared with r57_grid.json.
PART 2  spec re-implementation of the four rule features (brute force per bar, only bars <= i read),
        checked against the file's full-frame features and masks on every selection candidate bar
        (control signal bars for H-A/B/C, vol_mult=0 signal bars for H-D, plus each centre cell's own
        signal bars), and the file's helper mask fed back through _mask_override == the knob-on trades.
PART 3  look-ahead audit: 50 random selection candidate bars per rule (+10 extra rejected bars), arrays
        truncated at i (length i+1), file feature and mask recomputed with the memo cleared, compared with
        the full-frame value at i and with the spec value on the truncated arrays. Plus perturbation tests
        on 10 bars per rule: bars the rule must NOT read (current session before i for the daily /
        reference aggregates, sessions outside the lookback) are randomised and the value at i must not move.
PART 4  LB audit: stored selection trade lists / JSON rows carry no LB entry; prereg diff is append-only.

Run from the shared checkout:
    cd C:\\Users\\xride\\OneDrive\\Desktop\\EDGE-LOG
    python C:\\Users\\xride\\AppData\\Local\\EdgeLog-worktrees\\enguq57\\tools\\r37_results\\verify_r57_grid.py
One process (free RAM allows one). No commits, no queue, no Firestore writes unless --beacon.
"""
import argparse
import json
import math
import os
import subprocess
import sys
import time

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.environ["EDGELOG_REPO_ROOT"] = ROOT
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.pop("EDGELOG_NO_FASTLOOP", None)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import numpy as np                                                      # noqa: E402
import pandas as pd                                                     # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
WT = os.path.dirname(os.path.dirname(HERE))
SEL = os.path.join(WT, "augur_strategies", "ENGUQ_1M_ETH_SEL_1_0.py")
GRID_JSON = os.path.join(HERE, "r57_grid.json")
TRADES_CACHE = r"C:\EdgeLog\_anatomy_cache\r57\r57_grid_selection_trades.json"
OUT_TXT = os.path.join(HERE, "verify_r57_grid.txt")
OUT_JSON = os.path.join(HERE, "verify_r57_grid.json")

WIN = ("2010-06-07", "2026-06-30")
SPLIT = "2025-06-30"
ERA2 = "2020-01-01"
COST, MULT = 0.533, 20.0
SEED = 570914

# prereg section 1, typed by hand (not resolved from any file)
R2 = dict(tl_len=206, ema_len=220, atr_len=52, buf_atr=0.3, min_brk=1.6, vol_mult=1.1, stop_mult=1.0, act_R=1.5,
          trail_frac=2.5, breakeven_R=2.0, limit_atr=0.55, regime_len=10, er_len=100, er_th=0.0, max_hold_bars=0)
KOFF = dict(quiet_pct=0.0, stretch_max=0.0, rec_min=0.0, vol_clock=0.0)
HYP = {"H-A": ("quiet_pct", [10.0, 20.0, 30.0], 20.0),
       "H-B": ("stretch_max", [2.0, 1.5, 1.0], 1.5),
       "H-C": ("rec_min", [0.35, 0.45, 0.55], 0.45),
       "H-D": ("vol_clock", [1.0, 1.25, 1.5], 1.25)}

_FH = None
LOG = []


def say(s=""):
    print(s, flush=True)
    LOG.append(s)
    if _FH is not None:
        _FH.write(s + "\n")
        _FH.flush()


def cid(h=None, v=None):
    return "CTRL" if h is None else "%s %s=%g" % (h, HYP[h][0], v)


# ─────────────────────────────────────────────────────────── own metrics (prereg section 3)
def own_metrics(sel, idx):
    e = np.array([int(t[0]) for t in sel], np.int64)
    usd = np.array([float(t[2]) for t in sel]) * MULT
    ent = idx[e]
    e2 = np.asarray(ent >= pd.Timestamp(ERA2, tz=idx.tz))

    def blk(u):
        gw, gl = float(u[u > 0].sum()), float(-u[u < 0].sum())
        net = float(u.sum())
        top = float(np.sort(u)[::-1][:10].sum())
        return dict(n=int(len(u)), win=100.0 * float((u > 0).mean()) if len(u) else float("nan"),
                    pf=gw / gl if gl > 0 else float("nan"), net=net,
                    top10=100.0 * top / net if net > 0 else float("nan"), ex10=net - top)
    out = blk(usd)
    out["E1"] = blk(usd[~e2])
    out["E2"] = blk(usd[e2])
    return out


# ─────────────────────────────────────────────────────────── spec features (prereg section 5), bars <= i only
class Spec(object):
    """Built on ONE frame (full or truncated). Session ids are a running count of changes in the
    (ET wall clock + 6 h) day number, so the id of bar k depends only on bars <= k."""

    def __init__(self, o, h, l, c, v, ix):
        self.h, self.l, self.c = h, l, c
        self.v = None if v is None else np.asarray(v, float)
        wall = ix.tz_localize(None).asi8
        day = (wall + 6 * 3600 * 10 ** 9) // (86400 * 10 ** 9)
        if np.any(np.diff(day) < 0):
            raise SystemExit("index day numbers not monotone")
        chg = np.r_[True, day[1:] != day[:-1]]
        self.sess = np.cumsum(chg) - 1
        self.starts = np.flatnonzero(chg)
        self.minute = (wall // (60 * 10 ** 9)) % 1440
        n = len(c)
        tr = np.empty(n)
        tr[0] = h[0] - l[0]
        cp = c[:-1]
        tr[1:] = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - cp), np.abs(l[1:] - cp)))
        self.tr = tr

    def _atr14(self, xs):
        xs = np.asarray(xs, np.int64)
        good = xs >= 13
        out = np.full(len(xs), np.nan)
        if good.any():
            w = xs[good][:, None] - np.arange(14)[None, :]
            out[good] = self.tr[w].mean(axis=1)
        return out

    def q(self, i):
        s = int(self.sess[i])
        if s < 60:
            return float("nan")
        a = self._atr14([i])[0]
        xs = np.concatenate([np.arange(self.starts[t], self.starts[t + 1], 23) for t in range(max(0, s - 252), s)])
        assert xs.max() < self.starts[s] <= i
        ref = self._atr14(xs)
        ref = ref[np.isfinite(ref)]
        if len(ref) < 100 or not np.isfinite(a):
            return float("nan")
        return 100.0 * float(np.count_nonzero(ref <= a)) / float(len(ref))

    def stretch(self, i):
        s = int(self.sess[i])
        t = s - 1
        if t < 19:
            return float("nan")
        st = self.starts

        def HLC(u):
            a, b = st[u], st[u + 1]
            assert b <= st[s] <= i
            return self.h[a:b].max(), self.l[a:b].min(), self.c[b - 1]
        agg = {u: HLC(u) for u in range(max(0, t - 20), t + 1)}
        trd = []
        for u in range(t - 13, t + 1):
            H, L, C = agg[u]
            if u == 0:
                trd.append(H - L)
            else:
                Cp = agg[u - 1][2]
                trd.append(max(H - L, abs(H - Cp), abs(L - Cp)))
        atrd = float(np.mean(trd))
        sma = float(np.mean([agg[u][2] for u in range(t - 19, t + 1)]))
        if not atrd > 0:
            return float("nan")
        return (float(self.c[i]) - sma) / atrd

    def rec(self, i, tl=206):
        wh = float(self.h[i - tl:i].max())
        sl = float(self.l[i - tl:i + 1].min())
        return (float(self.c[i]) - sl) / (wh - sl) if wh > sl else float("nan")

    def clock(self, i):
        """(baseline B, ratio V/B, nonfinite volume prints in the pool)."""
        s = int(self.sess[i])
        if self.v is None or s < 21:
            return float("nan"), float("nan"), 0
        lo, hi = self.starts[s - 20], self.starts[s]
        assert hi <= i
        m = self.minute[i]
        pick = self.minute[lo:hi] == m
        vals = self.v[lo:hi][pick]
        nonfin = int((~np.isfinite(vals)).sum())
        vals = vals[np.isfinite(vals)]
        if len(vals) < 10:
            return float("nan"), float("nan"), nonfin
        B = float(vals.mean())
        return B, float(self.v[i]) / B, nonfin


def spec_pass(rule, val, knob):
    if rule == "H-A":
        return not (math.isfinite(val) and val < knob)
    if rule == "H-B":
        return not (math.isfinite(val) and val > knob)
    if rule == "H-C":
        return not (math.isfinite(val) and val < knob)
    raise ValueError(rule)


def same(a, b, rel=1e-9):
    a, b = float(a), float(b)
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    return abs(a - b) <= rel * max(1.0, abs(a), abs(b))


# ─────────────────────────────────────────────────────────── main
def run(step):
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    from augur_engine.strategies import load_strategy, strategy_file_sha
    t_all = time.time()
    np.seterr(all="ignore")
    RES = dict(disagreements=[])

    say("=" * 140)
    say("INDEPENDENT VERIFIER -- ENGU-Q round 57 items 1-3   (run %s)" % time.strftime("%Y-%m-%d %H:%M"))
    say("file %s sha256 %s" % (SEL, strategy_file_sha(SEL)))
    m = find_master("NQ", "1m", "eth", "db_noadj_eth")
    A = load_master_arrays(m, date_from=WIN[0], date_to=WIN[1])
    ix = pd.DatetimeIndex(A["index"])
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    V = np.asarray(A["volume"], float)
    n = len(c)
    n_split = int(ix.searchsorted(pd.Timestamp(SPLIT, tz=ix.tz)))
    say("master %s id %s | %d bars %s .. %s | tz %s | first bar >= split %d (%s) | nonfinite volumes %d"
        % (m.get("filename"), m.get("id"), n, ix[0], ix[-1], ix.tz, n_split, ix[n_split], int((~np.isfinite(V)).sum())))
    mod = load_strategy(SEL)
    say("loaded module file: %s" % getattr(mod, "__file__", "?"))
    grid = json.load(open(GRID_JSON, encoding="utf-8"))

    # ================================================================= PART 1
    say("\n" + "=" * 140)
    say("PART 1 -- ENGINE RE-RUN, OWN METRICS (selection only; LB trades dropped unread)")
    cells = [(None, None)] + [(hh, v) for hh in HYP for v in HYP[hh][1]]
    M, SELT = {}, {}
    for hh, v in cells:
        k = cid(hh, v)
        P = dict(R2, **KOFF)
        if hh:
            P[HYP[hh][0]] = float(v)
        r = run_backtest(SEL, arrays=A, params=dict(P), cost_pts=COST, return_trades=True)
        sel = [tuple(z) for z in sorted(r["trades"], key=lambda z: z[0]) if int(z[0]) < n_split]
        del r
        SELT[k] = sel
        M[k] = own_metrics(sel, ix)
    step(1)
    C0 = M["CTRL"]
    say("  %-22s | %5s %8s %8s %12s | %8s %8s | vs r57_grid.json (max abs diff n / win / PF / net / E1t10 / E2t10)"
        % ("cell", "n", "win%", "PF", "net $", "E1 t10%", "E2 t10%"))
    p1 = {}
    for hh, v in cells:
        k = cid(hh, v)
        X = M[k]
        g = grid["rows"][k]
        d = dict(n=abs(X["n"] - g["sel"]["n"]), win=abs(X["win"] - g["sel"]["wr"]), pf=abs(X["pf"] - g["sel"]["pf"]),
                 net=abs(X["net"] - g["sel"]["net"]), e1=abs(X["E1"]["top10"] - g["era1"]["top10"]),
                 e2=abs(X["E2"]["top10"] - g["era2"]["top10"]))
        bad = d["n"] > 0 or d["win"] > 1e-6 or d["pf"] > 1e-6 or d["net"] > 0.01 or d["e1"] > 1e-6 or d["e2"] > 1e-6
        if bad:
            RES["disagreements"].append(dict(part=1, cell=k, diffs=d))
        say("  %-22s | %5d %8.4f %8.5f %12.2f | %8.4f %8.4f | %d / %.2g / %.2g / %.2g / %.2g / %.2g %s"
            % (k, X["n"], X["win"], X["pf"], X["net"], X["E1"]["top10"], X["E2"]["top10"], d["n"], d["win"], d["pf"],
               d["net"], d["e1"], d["e2"], "DISAGREE" if bad else "agree"))
        p1[k] = dict(n=X["n"], win=X["win"], pf=X["pf"], net=X["net"], E1_top10=X["E1"]["top10"],
                     E2_top10=X["E2"]["top10"], E1_pf=X["E1"]["pf"], E2_pf=X["E2"]["pf"], E1_win=X["E1"]["win"],
                     E2_win=X["E2"]["win"], diffs_vs_grid=d)
    # matches the prereg's published control row?
    ok_ctrl = (C0["n"] == 1831 and round(C0["win"], 1) == 29.4 and round(C0["pf"], 3) == 1.717
               and round(C0["net"]) == 524745 and round(C0["E1"]["top10"], 1) == 62.1 and round(C0["E2"]["top10"], 1) == 64.6)
    say("  control == prereg section-1 table (1,831 / 29.4%% / 1.717 / $524,745 / E1 62.1%% / E2 64.6%%): %s" % ok_ctrl)
    if not ok_ctrl:
        RES["disagreements"].append(dict(part=1, cell="CTRL", what="prereg control row"))
    say("\n  CLAUSES recomputed (own numbers; thresholds from the control's exact values)")
    cl = {}
    for hh in HYP:
        k = cid(hh, HYP[hh][2])
        X = M[k]
        s1 = X["win"] - C0["win"]
        cl[hh] = dict(S1_win=X["win"], S1_thr=C0["win"] + 1.0, S1_pass=X["win"] >= C0["win"] + 1.0,
                      S2_pf=X["pf"], S2_thr=C0["pf"] + 0.02, S2_pass=X["pf"] >= C0["pf"] + 0.02,
                      S3_net=X["net"], S3_thr=0.95 * C0["net"], S3_pass=X["net"] >= 0.95 * C0["net"],
                      S5a_E1=X["E1"]["top10"], S5a_E1_thr=C0["E1"]["top10"] + 2, S5a_E1_pass=X["E1"]["top10"] <= C0["E1"]["top10"] + 2,
                      S5a_E2=X["E2"]["top10"], S5a_E2_thr=C0["E2"]["top10"] + 2, S5a_E2_pass=X["E2"]["top10"] <= C0["E2"]["top10"] + 2,
                      A0=dict(win_lift=s1, pf_lift=X["pf"] - C0["pf"], net_ratio=X["net"] / C0["net"],
                              tripped=bool(s1 > 3.0 or X["pf"] - C0["pf"] > 0.30 or X["net"] / C0["net"] > 1.10)))
        gr = {c_["clause"]: c_["passed"] for c_ in grid["results"][hh]["centre_clauses"]}
        agree = (gr["S1"] == cl[hh]["S1_pass"] and gr["S2"] == cl[hh]["S2_pass"] and gr["S3"] == cl[hh]["S3_pass"]
                 and gr["S5a-E1"] == cl[hh]["S5a_E1_pass"] and gr["S5a-E2"] == cl[hh]["S5a_E2_pass"])
        if not agree:
            RES["disagreements"].append(dict(part=1, hyp=hh, what="centre clause verdicts"))
        say("  %s %-20s S1 win %.4f vs >= %.4f %s | S2 PF %.5f vs >= %.5f %s | S3 net %.2f vs >= %.2f %s | S5a E1 %.3f<=%.3f %s "
            "E2 %.3f<=%.3f %s | A0 win %+.3f PF %+.4f net %.2f%% tripped %s | same verdicts as grid: %s"
            % (hh, k, cl[hh]["S1_win"], cl[hh]["S1_thr"], "P" if cl[hh]["S1_pass"] else "F", cl[hh]["S2_pf"], cl[hh]["S2_thr"],
               "P" if cl[hh]["S2_pass"] else "F", cl[hh]["S3_net"], cl[hh]["S3_thr"], "P" if cl[hh]["S3_pass"] else "F",
               cl[hh]["S5a_E1"], cl[hh]["S5a_E1_thr"], "P" if cl[hh]["S5a_E1_pass"] else "F", cl[hh]["S5a_E2"],
               cl[hh]["S5a_E2_thr"], "P" if cl[hh]["S5a_E2_pass"] else "F", s1, X["pf"] - C0["pf"], 100 * X["net"] / C0["net"],
               cl[hh]["A0"]["tripped"], agree))
    s9 = {}
    for hh in HYP:
        knob, gridv, cen = HYP[hh]
        for v in gridv:
            if v == cen:
                continue
            k = cid(hh, v)
            X = M[k]
            s9[k] = dict(win_lift=X["win"] - C0["win"], win_pass=X["win"] - C0["win"] >= 0.5, pf=X["pf"],
                         pf_pass=X["pf"] >= C0["pf"] + 0.01, net=X["net"], net_pass=X["net"] >= 0.90 * C0["net"],
                         e2_pf_lift=X["E2"]["pf"] - C0["E2"]["pf"], e2_pass=X["E2"]["pf"] - C0["E2"]["pf"] >= 0)
            gs = {c_["clause"]: c_["passed"] for c_ in grid["results"][hh]["s9"] if c_["desc"].startswith(k + ":")}
            agree = (gs.get("S9-win") == s9[k]["win_pass"] and gs.get("S9-pf") == s9[k]["pf_pass"]
                     and gs.get("S9-net") == s9[k]["net_pass"] and gs.get("S9-E2pf") == s9[k]["e2_pass"])
            if not agree:
                RES["disagreements"].append(dict(part=1, cell=k, what="S9 verdicts", mine=s9[k], grid=gs))
            say("  S9 %-22s win lift %+.4f %s | PF %.5f (>= %.5f) %s | net %.2f (>= %.2f) %s | E2 PF lift %+.5f %s | same as grid %s"
                % (k, s9[k]["win_lift"], "P" if s9[k]["win_pass"] else "F", X["pf"], C0["pf"] + 0.01,
                   "P" if s9[k]["pf_pass"] else "F", X["net"], 0.9 * C0["net"], "P" if s9[k]["net_pass"] else "F",
                   s9[k]["e2_pf_lift"], "P" if s9[k]["e2_pass"] else "F", agree))
    RES["part1"] = dict(cells=p1, centre_clauses=cl, s9=s9, control_matches_prereg=ok_ctrl)

    # stored selection trade cache == my selection trades?
    try:
        tc = json.load(open(TRADES_CACHE, encoding="utf-8"))["cells"]
        cache_eq = {}
        for k, sel in SELT.items():
            mine = [(int(t[0]), int(t[1]), round(float(t[2]), 6), round(float(t[4]), 6)) for t in sel]
            theirs = [(int(t[0]), int(t[1]), round(float(t[2]), 6), round(float(t[4]), 6)) for t in tc[k]]
            cache_eq[k] = mine == theirs
        max_entry = max(int(t[0]) for v in tc.values() for t in v)
        say("  grid's cached selection trade lists == my selection trades, per cell: %s | max cached entry bar %d < split bar %d: %s"
            % (all(cache_eq.values()), max_entry, n_split, max_entry < n_split))
        RES["part1"]["trade_cache_equal"] = cache_eq
        RES["part1"]["trade_cache_max_entry_bar"] = max_entry
        if not all(cache_eq.values()) or max_entry >= n_split:
            RES["disagreements"].append(dict(part=1, what="trade cache", eq=cache_eq))
    except Exception as exc:
        say("  (trade cache not compared: %s)" % exc)

    # ================================================================= PART 2
    say("\n" + "=" * 140)
    say("PART 2 -- SPEC FEATURES vs THE FILE'S FEATURES AND MASKS")
    base = dict(R2, **KOFF)
    sp_base, sp_v0 = [], []
    mod.run_backtest(o, h, l, c, volumes=V, day_id=A["day_id"], index=A["index"], return_trades=False,
                     _signal_index_probe=sp_base, **base)
    mod.run_backtest(o, h, l, c, volumes=V, day_id=A["day_id"], index=A["index"], return_trades=False,
                     _signal_index_probe=sp_v0, **dict(base, vol_mult=0.0))
    cand = {"base": np.array(sorted(set(i for i in sp_base if i < n_split)), np.int64),
            "v0": np.array(sorted(set(i for i in sp_v0 if i < n_split)), np.int64)}
    cen_sig = {}
    for hh in HYP:
        pr = []
        mod.run_backtest(o, h, l, c, volumes=V, day_id=A["day_id"], index=A["index"], return_trades=False,
                         _signal_index_probe=pr, **dict(base, **{HYP[hh][0]: HYP[hh][2]}))
        cen_sig[hh] = np.array(sorted(set(i for i in pr if i < n_split)), np.int64)
    say("  selection candidate bars: control signals %d | vol_mult=0 signals %d | centre-cell own signals %s"
        % (len(cand["base"]), len(cand["v0"]), {k_: len(v_) for k_, v_ in cen_sig.items()}))
    step(2)

    mod._MEMO.clear()
    tr_file = mod._true_range(h, l, c)
    F = mod._rule_features(o, h, l, c, V, A["index"], tl_len=206)
    MK = {"H-A": mod._rule_mask(h, l, c, V, ix, tr_file, 206, 20.0, 0.0, 0.0, 0.0),
          "H-B": mod._rule_mask(h, l, c, V, ix, tr_file, 206, 0.0, 1.5, 0.0, 0.0),
          "H-C": mod._rule_mask(h, l, c, V, ix, tr_file, 206, 0.0, 0.0, 0.45, 0.0),
          "H-D": mod._rule_mask(h, l, c, V, ix, tr_file, 206, 0.0, 0.0, 0.0, 1.25)}
    SP = Spec(o, h, l, c, V, ix)
    say("  own TR == file TR on all bars: %s | own session ids == file session ids: %s | own minute == file minute: %s"
        % (bool(np.array_equal(SP.tr, tr_file)), bool(np.array_equal(SP.sess, mod._sessions(ix, n)[0])),
           bool(np.array_equal(SP.minute, mod._sessions(ix, n)[1]))))

    p2 = {}
    for hh in HYP:
        bars = np.union1d(cand["v0" if hh == "H-D" else "base"], cen_sig[hh])
        vmis, mmis, nonfin, rej = [], [], 0, 0
        for i in bars:
            i = int(i)
            if hh == "H-A":
                sv, fv = SP.q(i), F["q"][i]
                sm = spec_pass(hh, sv, 20.0)
            elif hh == "H-B":
                sv, fv = SP.stretch(i), F["stretch"][i]
                sm = spec_pass(hh, sv, 1.5)
            elif hh == "H-C":
                sv, fv = SP.rec(i), F["rec"][i]
                sm = spec_pass(hh, sv, 0.45)
            else:
                B, sv, nf = SP.clock(i)
                nonfin += nf
                fv = F["vol_vs_clock"][i]
                if not same(B, F["clock_base"][i]):
                    vmis.append((i, "B", B, float(F["clock_base"][i])))
                sm = bool(math.isfinite(B) and V[i] >= 1.25 * B)
            if not same(sv, fv):
                vmis.append((i, float(sv), float(fv)))
            if bool(sm) != bool(MK[hh][i]):
                mmis.append((i, float(sv), bool(sm), bool(MK[hh][i])))
            rej += (not sm)
        cen_ok = bool(np.all(MK[hh][cen_sig[hh]]))
        p2[hh] = dict(bars=int(len(bars)), rejected_by_spec=int(rej), value_mismatch=len(vmis), mask_mismatch=len(mmis),
                      examples=(vmis + mmis)[:5], centre_signals_all_pass_file_mask=cen_ok, nonfinite_volume_prints=nonfin)
        if vmis or mmis or not cen_ok:
            RES["disagreements"].append(dict(part=2, hyp=hh, **p2[hh]))
        say("  %s spec vs file on %d selection candidate bars: value mismatches %d, mask mismatches %d (spec rejects %d) | "
            "centre cell's own signal bars all pass the file mask: %s%s"
            % (hh, len(bars), len(vmis), len(mmis), rej, cen_ok, (" | e.g. %s" % (vmis + mmis)[:3]) if (vmis or mmis) else ""))
    # helper mask fed back == knob-on engine trades
    ov = {}
    for hh in HYP:
        knob, _g, cen = HYP[hh]
        P = dict(R2, **KOFF)
        P[knob] = cen
        r = run_backtest(SEL, arrays=A, params=dict(P, _mask_override=MK[hh]), cost_pts=COST, return_trades=True)
        sel = [tuple(z) for z in sorted(r["trades"], key=lambda z: z[0]) if int(z[0]) < n_split]
        del r
        ov[hh] = [(t[0], t[1], t[2], t[4]) for t in sel] == [(t[0], t[1], t[2], t[4]) for t in SELT[cid(hh, cen)]]
        if not ov[hh]:
            RES["disagreements"].append(dict(part=2, hyp=hh, what="override != knob-on"))
    say("  file mask fed back via _mask_override reproduces the knob-on selection trades: %s" % ov)
    p2["override_identity"] = ov
    RES["part2"] = p2
    step(3)

    # ================================================================= PART 3
    say("\n" + "=" * 140)
    say("PART 3 -- LOOK-AHEAD AUDIT: truncate at i (bars 0..i), recompute with the memo cleared (seed %d)" % SEED)
    rng = np.random.default_rng(SEED)
    knob_of = {"H-A": (20.0, 0.0, 0.0, 0.0), "H-B": (0.0, 1.5, 0.0, 0.0), "H-C": (0.0, 0.0, 0.45, 0.0),
               "H-D": (0.0, 0.0, 0.0, 1.25)}
    p3 = {}
    kstep = 3
    for hh in HYP:
        pool = cand["v0" if hh == "H-D" else "base"]
        pick = rng.choice(pool, size=50, replace=False)
        rej_pool = np.setdiff1d(pool[~MK[hh][pool]], pick)
        extra = rng.choice(rej_pool, size=min(10, len(rej_pool)), replace=False)
        bars = [(int(i), "random") for i in pick] + [(int(i), "extra-rejected") for i in extra]
        rows, bad = [], 0
        t0 = time.time()
        for i, why in bars:
            nt = i + 1
            ot, ht, lt, ct, vt = o[:nt], h[:nt], l[:nt], c[:nt], V[:nt]
            ixt = ix[:nt]
            mod._MEMO.clear()
            trt = mod._true_range(ht, lt, ct)
            fk = mod._frame_key(ht, lt, ct, vt, ixt)
            if hh == "H-C":
                ft = mod._feat_recovery(ht, lt, ct, 206, fk)
                fv_full, fv_tr = float(F["rec"][i]), float(ft[-1])
                pref_eq = True
            else:
                ses = mod._sessions(ixt, nt)
                if hh == "H-A":
                    ft = mod._feat_quiet(trt, ses, fk)
                    full = F["q"]
                elif hh == "H-B":
                    ft = mod._feat_stretch(ht, lt, ct, ses, fk)
                    full = F["stretch"]
                else:
                    ft = vt / mod._feat_clock_base(vt, ses, fk)
                    full = F["vol_vs_clock"]
                fv_full, fv_tr = float(full[i]), float(ft[-1])
                s0 = int(ses[2][ses[0][-1]])
                a_, b_ = full[s0:nt], ft[s0:nt]
                pref_eq = bool(np.array_equal(np.isnan(a_), np.isnan(b_)) and np.array_equal(a_[np.isfinite(a_)], b_[np.isfinite(b_)]))
            mod._MEMO.clear()
            mt = mod._rule_mask(ht, lt, ct, vt, ixt, trt, 206, *knob_of[hh])
            m_tr, m_full = bool(mt[-1]), bool(MK[hh][i])
            spt = Spec(ot, ht, lt, ct, vt, ixt)
            if hh == "H-A":
                sv = spt.q(i)
                smask = spec_pass(hh, sv, 20.0)
            elif hh == "H-B":
                sv = spt.stretch(i)
                smask = spec_pass(hh, sv, 1.5)
            elif hh == "H-C":
                sv = spt.rec(i)
                smask = spec_pass(hh, sv, 0.45)
            else:
                B, sv, _nf = spt.clock(i)
                smask = bool(math.isfinite(B) and V[i] >= 1.25 * B)
            ok = (fv_full == fv_tr or (math.isnan(fv_full) and math.isnan(fv_tr))) and same(sv, fv_tr) and \
                m_tr == m_full == smask and pref_eq
            bad += (not ok)
            rows.append(dict(i=i, why=why, ts=str(ix[i]), full=fv_full, trunc=fv_tr, spec=sv, mask_full=m_full,
                             mask_trunc=m_tr, mask_spec=bool(smask), session_prefix_equal=pref_eq, ok=bool(ok)))
            del spt
        nfalse = sum(1 for r_ in rows if not r_["mask_full"])
        nfalse_rand = sum(1 for r_ in rows if not r_["mask_full"] and r_["why"] == "random")
        p3[hh] = dict(n=len(rows), random=50, extra_rejected=len(extra), mask_false=nfalse, mask_false_in_random=nfalse_rand,
                      failures=bad, secs=time.time() - t0, rows=rows)
        if bad:
            RES["disagreements"].append(dict(part=3, hyp=hh, failures=[r_ for r_ in rows if not r_["ok"]][:5]))
        say("  %s %d bars (50 random, %d extra rejected; mask False on %d, of which %d in the random 50): truncated value == "
            "full value == spec, truncated mask == full mask == spec mask, current-session prefix equal -> failures %d  (%.0fs)"
            % (hh, len(rows), len(extra), nfalse, nfalse_rand, bad, time.time() - t0))
        kstep += 1
        step(kstep)

    # ---------------------------------------------------------------- perturbation tests
    say("\n  PERTURBATION (on the truncated frame, memo cleared): randomise bars the rule must not read -> value at i unchanged;"
        " randomise bars it must read -> value should move (sensitivity, reported)")
    pert = {}
    for hh in HYP:
        rows3 = p3[hh]["rows"][:10]
        res_rows = []
        for r_ in rows3:
            i = r_["i"]
            nt = i + 1
            ixt = ix[:nt]
            spt = Spec(o[:nt], h[:nt], l[:nt], c[:nt], V[:nt], ixt)
            s = int(spt.sess[i])
            st = spt.starts

            def val(hp, lp, cp, vp):
                mod._MEMO.clear()
                fk = mod._frame_key(hp, lp, cp, vp, ixt)
                if hh == "H-C":
                    return float(mod._feat_recovery(hp, lp, cp, 206, fk)[-1])
                ses = mod._sessions(ixt, nt)
                if hh == "H-A":
                    return float(mod._feat_quiet(mod._true_range(hp, lp, cp), ses, fk)[-1])
                if hh == "H-B":
                    return float(mod._feat_stretch(hp, lp, cp, ses, fk)[-1])
                return float(vp[-1] / mod._feat_clock_base(vp, ses, fk)[-1])

            v0 = val(h[:nt], l[:nt], c[:nt], V[:nt])
            tests = []
            if hh == "H-A":
                tests.append(("current session before i-14", (st[s], i - 14), "hlc", False))
                lo_ref = st[max(0, s - 252)]
                tests.append(("before the 252-session lookback (-15 bars)", (0, lo_ref - 15), "hlc", False))
                tests.append(("session s-1 (inside reference) x20 ranges", (st[s - 1], st[s]), "scale", True))
            elif hh == "H-B":
                tests.append(("current session before i", (st[s], i), "hlc", False))
                tests.append(("sessions before s-21", (0, st[max(0, s - 21)]), "hlc", False))
                tests.append(("session s-1 (inside SMA/ATRd)", (st[s - 1], st[s]), "hlc", True))
            elif hh == "H-C":
                tests.append(("bars before i-206", (0, i - 206), "hlc", False))
                tests.append(("bars i-206..i-1 highs", (i - 206, i), "hlc", True))
            else:
                tests.append(("current-session volume before i", (st[s], i), "vol", False))
                tests.append(("volume before session s-20", (0, st[max(0, s - 20)]), "vol", False))
                tests.append(("volume in session s-1", (st[s - 1], st[s]), "vol", True))
            out = []
            for name, (a, b), kind, expect_move in tests:
                if b <= a:
                    out.append(dict(test=name, skipped="empty range"))
                    continue
                hp, lp, cp, vp = h[:nt].copy(), l[:nt].copy(), c[:nt].copy(), V[:nt].copy()
                prng = np.random.default_rng(i)
                if kind == "hlc":
                    hp[a:b] += prng.uniform(0.5, 40.0, b - a)
                    lp[a:b] -= prng.uniform(0.5, 40.0, b - a)
                    cp[a:b] += prng.uniform(-20.0, 20.0, b - a)
                elif kind == "scale":
                    mid = (hp[a:b] + lp[a:b]) / 2.0
                    hp[a:b] = mid + 20.0 * (hp[a:b] - mid) + 5.0
                    lp[a:b] = mid - 20.0 * (mid - lp[a:b]) - 5.0
                else:
                    vp[a:b] = vp[a:b] * prng.uniform(0.05, 20.0, b - a) + 50.0
                v1 = val(hp, lp, cp, vp)
                moved = not (v1 == v0 or (math.isnan(v1) and math.isnan(v0)))
                out.append(dict(test=name, range=[int(a), int(b)], expect_move=expect_move, before=v0, after=v1, moved=moved,
                                ok=(moved if expect_move else not moved)))
                del hp, lp, cp, vp
            res_rows.append(dict(i=i, tests=out))
        must_not = [t for rr in res_rows for t in rr["tests"] if "moved" in t and not t["expect_move"]]
        should = [t for rr in res_rows for t in rr["tests"] if "moved" in t and t["expect_move"]]
        nbad = sum(1 for t in must_not if t["moved"])
        pert[hh] = dict(rows=res_rows, must_not_move=len(must_not), moved_wrongly=nbad, sensitivity_tests=len(should),
                        sensitivity_moved=sum(1 for t in should if t["moved"]),
                        skipped=sum(1 for rr in res_rows for t in rr["tests"] if "skipped" in t))
        if nbad:
            RES["disagreements"].append(dict(part=3, hyp=hh, what="perturbation moved a value it must not read",
                                             rows=[t for t in must_not if t["moved"]][:5]))
        say("  %s: 'must not read' perturbations %d, value moved on %d | sensitivity perturbations %d, moved on %d | skipped %d"
            % (hh, len(must_not), nbad, len(should), pert[hh]["sensitivity_moved"], pert[hh]["skipped"]))
    RES["part3"] = dict(truncation=p3, perturbation=pert)
    kstep += 1
    step(kstep)

    # ================================================================= PART 4
    say("\n" + "=" * 140)
    say("PART 4 -- LB AUDIT")
    lb_rows = {k: grid["rows"][k]["lb"]["n"] for k in grid["rows"]}
    whole_eq_sel = {k: grid["rows"][k]["whole"]["n"] == grid["rows"][k]["sel"]["n"] for k in grid["rows"]}
    say("  r57_grid.json lb.n per cell (must all be 0): %s | whole n == sel n in every cell: %s"
        % (sorted(set(lb_rows.values())), all(whole_eq_sel.values())))
    diff = subprocess.run(["git", "-C", WT, "diff", "--numstat", "a7f0811", "--", "ENGUQ_R57_PREREG.md"], capture_output=True,
                          text=True).stdout.strip()
    say("  prereg diff vs a7f0811 (added / deleted lines): %s" % diff)
    RES["part4"] = dict(grid_lb_n=lb_rows, whole_eq_sel=whole_eq_sel, prereg_numstat=diff)
    if set(lb_rows.values()) != {0} or not all(whole_eq_sel.values()):
        RES["disagreements"].append(dict(part=4, what="LB rows present in grid json"))

    say("\n" + "=" * 140)
    say("VERIFIER RESULT: disagreements %d   (runtime %.0fs)" % (len(RES["disagreements"]), time.time() - t_all))
    for d_ in RES["disagreements"]:
        say("  %s" % json.dumps(d_, default=str)[:600])
    return RES


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, np.integer, np.bool_)):
        return clean(o.item())
    if isinstance(o, float) and not math.isfinite(o):
        return None if math.isnan(o) else ("inf" if o > 0 else "-inf")
    return o


def main():
    global _FH
    ap = argparse.ArgumentParser()
    ap.add_argument("--beacon", action="store_true")
    a = ap.parse_args()
    _FH = open(OUT_TXT, "w", encoding="utf-8")
    try:
        if a.beacon:
            from research_beacon import beacon
            with beacon("r57 ENGU-Q independent verifier", total=8) as b:
                out = run(lambda i: b.step(i))
        else:
            out = run(lambda i: None)
    finally:
        _FH.close()
        _FH = None
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(clean(out), fh, indent=1, default=str)
    print("wrote", OUT_TXT, OUT_JSON)


if __name__ == "__main__":
    main()
