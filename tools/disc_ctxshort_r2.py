"""CTXSHORT r2 harness (DISC, MANAGER #115 / #116, 2026-10-18) - see docs/PREREG_disc_ctxshort_r2_2026-10-18.md.

A DISCRETIONARY-AID read, never a book candidate. r1 (ledger 2.190) found the owner's CBD / ENGD context shorts make
their money on NOISE #382 short days and lose elsewhere. r2 asks the trader's question: take the setup ONLY while
NOISE #382 is already short at the entry minute - under two context readings, frozen as arms:
  A  completed-bar context (r1's CTX; MANAGER #116, the latest spec)   + the NOISE-short-open gate   (cell named first: A / E2)
  B  bar-so-far context (the 5m / 30m bar holding the signal minute,   + the NOISE-short-open gate
     read through the signal close; MANAGER #115 / the deep dive)
  B0 bar-so-far context, no gate (report only, no verdict)
Triggers, entries and exits are r1's frozen code (tools/disc_ctxshort_r1.py, imported unchanged; its LF sha256 is asserted).

    python tools/disc_ctxshort_r2.py [--out C:\\EdgeLog\\_anatomy_cache\\ctxshort_r2] [--selftest-only]
Writes only under --out, plus one run-record line per arm x exit (B0 marked report only) to
C:\\EdgeLog\\run_records\\DISC_<YYYYMM of the run>.jsonl, written right after Stage 1 (before the answer key).
"""
import argparse
import datetime as _dt
import hashlib
import json
import os
import socket
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import disc_ctxshort_r1 as R1                    # noqa: E402  (frozen r1 code; also sets the data registry path)

PREREG = os.path.join(ROOT, "docs", "PREREG_disc_ctxshort_r2_2026-10-18.md")
EXPECT_PREREG_SHA = "37e848b4b52d9c55368544f4f1e1a67035c890e75af241eaa3cb203026b74575"      # frozen 2026-10-18; the run stops if the prereg's LF sha256 differs
R1_SHA = "640fe08a602f767ba6084fdd8199af4bae0a7181daa3f1929e1b9868ba7382a4"     # r1 harness as frozen and run (2.190)
ET = R1.ET
NOISE_RUN = 382
ARMS = ("A", "B", "B0")
GATED = {"A": True, "B": True, "B0": False}
FIRST_CELL = ("A", "E2")
MIN_TRADES_AID = 30
KEY_CROWN_FROM = "2024-06-01"                  # >= 300 sessions of NOISE warm-up before the first answer-key date
RUN_RECORDS_DIR = r"C:\EdgeLog\run_records"


def lf_sha256(path):
    return hashlib.sha256(open(path, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


# ---------------------------------------------------------------- the bar-so-far context
def context_so_far(eth, rth, regular):
    """Per RTH 1m bar t: C1-C4 with the 5m / 30m bar that HOLDS minute t read through t's close (its open = the first
    ETH minute of that bar; its close = t's close) and the bars before it completed. Algebra (alpha = 2/21):
      EMA_so_far = EMA_last + alpha (c - EMA_last), so 'EMA falling and close below it' == c < EMA_last;
      SMA200_so_far = (sum of the last 199 completed closes + c) / 200, so 'close below it' == c < mean of those 199;
      three red 30m = the bar so far is red (c < its open) AND the two completed bars before it are red.
    Column age_30 = minutes since the holding 30m bar opened (0 = the signal candle IS the bar so far)."""
    out = pd.DataFrame(index=rth.index)
    c = rth.c.to_numpy()
    for tf in (5, 30):
        b = R1.bars_tf(eth, tf)
        b["ema20"] = b.c.ewm(span=20, adjust=False).mean()
        b["mean199"] = b.c.rolling(199, min_periods=199).mean()
        b["red"] = (b.c < b.o)
        key = rth.index.tz_convert("UTC").floor("%dmin" % tf).tz_convert(ET)
        j = b.index.get_indexer(key)
        if (j < 1).any():
            raise ValueError("context_so_far: a 1m bar has no %dm bar or no completed bar before it" % tf)
        out["o_f_%d" % tf] = b.o.to_numpy()[j]
        out["ema_last_%d" % tf] = b.ema20.to_numpy()[j - 1]
        out["mean199_%d" % tf] = b.mean199.to_numpy()[j - 1]
        if tf == 30:
            red = b.red.to_numpy()
            out["red_prev2_30"] = red[j - 1] & red[np.maximum(j - 2, 0)] & (j >= 2)
            out["age_30"] = ((rth.index - key).total_seconds() // 60).astype(int)
    base = R1.context(eth, rth, regular)          # C1 and 'regular' are the same in both readings
    out["C1"] = base.C1.to_numpy()
    out["regular"] = base.regular.to_numpy()
    out["C2"] = (c < out.mean199_5) & (c < out.mean199_30)
    out["C3"] = (c < out.ema_last_5) & (c < out.ema_last_30)
    out["C4"] = (c < out.o_f_30) & out.red_prev2_30
    out["CTX"] = out.C1 & out.C2 & out.C3 & out.C4 & out.regular
    return out, base


# ---------------------------------------------------------------- the NOISE-short-open gate
def noise_short_open_at(times, crown):
    """True where a NOISE #382 SHORT is already open at time T: its fill (the open of its entry bar, ix[t0]; the plugin
    decides on the bar before the fill) is STRICTLY before T, and its exit bar has not yet opened (T < ix[t1])."""
    s = crown[crown.side < 0]
    if s.empty:
        return np.zeros(len(times), bool)
    ti = pd.DatetimeIndex(s.t_in).asi8; to = pd.DatetimeIndex(s.t_exit_open).asi8
    order = np.argsort(ti); ti, to = ti[order], to[order]
    run_max = np.maximum.accumulate(to)
    T = pd.DatetimeIndex(times).asi8
    p = np.searchsorted(ti, T, side="left") - 1                # fills strictly before T
    return (p >= 0) & (run_max[np.maximum(p, 0)] > T)


def _exit_open(ct, minutes=5):
    ct["t_exit_open"] = ct.t_out - pd.Timedelta(minutes=minutes)   # R1 stamps t_out = ix[t1] + tf; the exit bar OPENS at ix[t1]
    return ct


def crown_382(date_from, date_to):
    ct, info = R1.crown_trades(NOISE_RUN, date_from, date_to)
    return _exit_open(ct), info


def entry_times(rth):
    """For each RTH bar i: the entry time if it signals = the open of bar i+1 (the next bar's start)."""
    nxt = np.r_[rth.index.asi8[1:], rth.index.asi8[-1]]
    return pd.DatetimeIndex(nxt, tz="UTC").tz_convert(ET)


def _floatify(tr):
    for col in ("entry", "stop", "R_pts", "exit", "gross_pts", "R"):
        tr[col] = tr[col].astype(float)
    return tr


# ---------------------------------------------------------------- verdicts
def verdict(blk, power_label):
    b = blk["NQ cost"]
    gross_ok = (b["gross_pts_per_trade"] if b["gross_pts_per_trade"] is not None else -1e9) >= R1.COST_NQ
    roc_ok = (b["roc30"] if b["roc30"] is not None else -1e9) > 0
    epi_ok = b["one_episode"] is False
    mdl_ok = (b["trades_yr"] or 0) >= R1.AV_TRADES_YR and (b["roc30"] or 0) >= R1.AV_ROC
    halves = [k for k in blk if k.startswith("half ")]
    halves_ok = len(halves) == len(R1.HALVES) and all(blk[k]["net_usd"] > 0 for k in halves)
    n_ok = b["trades"] >= MIN_TRADES_AID
    house = "PASS" if (gross_ok and roc_ok and epi_ok and mdl_ok) else "FAIL"
    aid = "SUPPORTED" if (gross_ok and roc_ok and epi_ok and halves_ok and n_ok) else "NOT SUPPORTED"
    return {"house_bar": house, "aid_read": aid, "gross_ge_cost": gross_ok, "roc_above_0": roc_ok, "not_one_episode": epi_ok,
            "mdl_path": mdl_ok, "both_halves_positive": halves_ok, "trades_ge_30": n_ok, "t_R": b["boot_t_R"],
            "power": power_label, "note": "never a book candidate (MANAGER #115)"}


def summary(arms):
    cells = [(k, r) for k in ("A", "B") for r in ("E1", "E2", "E3")]
    cells.sort(key=lambda x: x != FIRST_CELL)
    rows = [{"arm": k, "exit": r, "aid_read": arms[k][r]["verdict"]["aid_read"], "house_bar": arms[k][r]["verdict"]["house_bar"],
             "trades": arms[k][r]["reads"]["NQ cost"]["trades"], "t_R": arms[k][r]["reads"]["NQ cost"]["boot_t_R"]} for k, r in cells]
    return {"supported": "%d of 6 gated cells" % sum(x["aid_read"] == "SUPPORTED" for x in rows),
            "house_bar_passes": "%d of 6" % sum(x["house_bar"] == "PASS" for x in rows), "cells_first_named_first": rows}


# ---------------------------------------------------------------- run records (house rule 10-18)
def run_record(arm, rule, b, v, harness_sha, prereg_sha):
    now = _dt.datetime.now().astimezone()
    return {"ts": now.isoformat(timespec="seconds"), "lane": "DISC", "host": socket.gethostname(), "where": "lane",
            "strategy": "CTXSHORT r2 arm %s %s" % (arm, rule), "family": "CBU-Q", "instrument": "NQ", "timeframe": "1m",
            "stage": "WF", "roc30k": b["roc30"], "dd5": b["dd5"], "ddpct": b["dd_pct_peak"], "sortino": b["sortino"],
            "trades": b["trades"], "gross_pt": b["gross_pts_per_trade"], "cost_pt": R1.COST_NQ,
            "one_episode": (bool(b["one_episode"]) if b["one_episode"] is not None else None), "ledger_row": None,
            "run_id": "CTXSHORT-r2-%s-%s-%s" % (arm, rule, harness_sha[:8]), "sha": harness_sha,
            "note": ("report only (ungated base)" if v is None else "house bar %s; aid read %s; discretionary aid only" % (
                v["house_bar"], v["aid_read"])) + "; prereg %s" % prereg_sha[:8]}


def write_records(recs):
    if not recs:
        return None
    month = recs[0]["ts"][:7].replace("-", "")
    path = os.path.join(RUN_RECORDS_DIR, "DISC_%s.jsonl" % month)
    os.makedirs(RUN_RECORDS_DIR, exist_ok=True)
    have = set()
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            try:
                have.add(json.loads(line).get("run_id"))
            except ValueError:
                pass
    new = [r for r in recs if r["run_id"] not in have]
    with open(path, "a", encoding="utf-8") as f:
        for r in new:
            f.write(json.dumps(r, default=str) + "\n")
    return path, len(new)


# ---------------------------------------------------------------- selftest (synthetic bars only)
def selftest():
    days = pd.bdate_range("2015-03-02", periods=8)
    idx = pd.DatetimeIndex([pd.Timestamp(d.date().isoformat() + " 00:00", tz=ET) + pd.Timedelta(minutes=m)
                            for d in days for m in range(0, 1440) if not (17 * 60 <= m < 18 * 60)])
    rng = np.random.default_rng(11)
    c = 100.0 + np.cumsum(rng.normal(0, 0.3, len(idx)))
    o = np.r_[c[0], c[:-1]] + rng.normal(0, 0.05, len(idx))
    eth = pd.DataFrame({"o": o, "h": np.maximum(o, c) + 0.1, "l": np.minimum(o, c) - 0.1, "c": c, "v": 100.0}, index=idx)
    mn = R1._minute(eth.index); rth = eth[(mn >= R1.RTH0) & (mn <= R1.RTH1)].copy(); rth["day"] = rth.index.date
    reg = set(rth.day)
    dl = days[-1].date().isoformat()
    full, _ = context_so_far(eth, rth, reg)
    cols = [x for x in full.columns if x != "regular"]
    assert full.loc[dl + " 10:06", "mean199_30"] == full.loc[dl + " 10:06", "mean199_30"], "selftest needs a finite 30m mean199"
    for t in ("09:30", "09:45", "10:00", "10:04", "10:05", "10:06", "10:29", "10:30", "10:59", "11:00", "11:29"):
        T = pd.Timestamp(dl + " " + t, tz=ET)
        e2 = eth[eth.index <= T].copy(); r2 = rth[rth.index <= T].copy()
        part, _ = context_so_far(e2, r2, reg)
        e3 = eth.copy(); later = e3.index > T
        e3.loc[later, ["o", "h", "l", "c"]] = e3.loc[later, ["o", "h", "l", "c"]] * rng.uniform(0.5, 1.5, (later.sum(), 1))
        mn3 = R1._minute(e3.index); r3 = e3[(mn3 >= R1.RTH0) & (mn3 <= R1.RTH1)].copy(); r3["day"] = r3.index.date
        pert, _ = context_so_far(e3, r3, reg)
        for col in cols:
            a, b_, p = full.loc[T, col], part.loc[T, col], pert.loc[T, col]
            same = lambda x, y: (x == y) or (pd.isna(x) and pd.isna(y))
            assert same(a, b_) and same(a, p), (t, col, a, b_, p)
    T = pd.Timestamp(dl + " 10:06", tz=ET)
    assert full.loc[T, "o_f_30"] == eth.loc[pd.Timestamp(dl + " 10:00", tz=ET), "o"], "forming 30m open = its first minute's open"
    assert full.loc[T, "age_30"] == 6 and full.loc[pd.Timestamp(dl + " 10:30", tz=ET), "age_30"] == 0
    # entry times = the next bar's open
    et = entry_times(rth)
    assert (et[:-1] == rth.index[1:]).all()
    # crown mapping: R1 stamps t_out = ix[t1] + 5m; the gate closes at ix[t1]
    stub = _exit_open(pd.DataFrame({"t_in": [pd.Timestamp(dl + " 10:00", tz=ET)],
                                    "t_out": [pd.Timestamp(dl + " 10:30", tz=ET) + pd.Timedelta(minutes=5)], "side": [-1]}))
    assert stub.t_exit_open.iloc[0] == pd.Timestamp(dl + " 10:30", tz=ET)
    Ts = pd.DatetimeIndex([pd.Timestamp(dl + " " + x, tz=ET) for x in ("09:59", "10:00", "10:01", "10:29", "10:30")])
    assert list(noise_short_open_at(Ts, stub)) == [False, False, True, True, False], noise_short_open_at(Ts, stub)
    stub.loc[0, "side"] = 1
    assert not noise_short_open_at(Ts, stub).any(), "a NOISE long never opens the gate"
    # zero-trade arm reads without crashing
    empty = _floatify(R1.simulate(rth, np.zeros(len(rth), bool), np.zeros(len(rth), bool), np.zeros(len(rth), bool),
                                  np.full(len(rth), np.nan), "E2"))
    sess = pd.DatetimeIndex(pd.to_datetime(sorted(str(d) for d in reg)))
    empty.drop(empty.nlargest(3, "gross_pts").index)
    # verdict edges on a synthetic block
    def blk(gross, roc, epi, halves, n):
        base = {"gross_pts_per_trade": gross, "roc30": roc, "one_episode": epi, "trades": n, "trades_yr": n / 9, "boot_t_R": None}
        d = {"NQ cost": base}
        for i, h in enumerate(halves):
            d["half %d" % i] = {"net_usd": h}
        return d
    ok = blk(0.783, 0.1, False, [1, 1], 30)
    assert verdict(ok, "x")["aid_read"] == "SUPPORTED"
    for bad in (blk(0.782, 0.1, False, [1, 1], 30), blk(0.783, 0.0, False, [1, 1], 30), blk(0.783, 0.1, None, [1, 1], 30),
                blk(0.783, 0.1, True, [1, 1], 30), blk(0.783, 0.1, False, [1, 0], 30), blk(0.783, 0.1, False, [1], 30),
                blk(0.783, 0.1, False, [1, 1], 29)):
        assert verdict(bad, "x")["aid_read"] == "NOT SUPPORTED", bad
    json.dumps(run_record("A", "E2", {"roc30": None, "dd5": 1.0, "dd_pct_peak": 2.0, "sortino": None, "trades": 0,
                                      "gross_pts_per_trade": None, "one_episode": None}, None, "0" * 64, "1" * 64))
    print("r2 selftest OK (bar-so-far truncation + perturbation on all columns, forming open/age, entry times, crown mapping,"
          " strict gate edges, long ignored, zero-trade arm, verdict edges, run-record JSON)")


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=r"C:\EdgeLog\_anatomy_cache\ctxshort_r2")
    ap.add_argument("--selftest-only", action="store_true")
    a = ap.parse_args(argv)
    r1sha = lf_sha256(os.path.join(HERE, "disc_ctxshort_r1.py"))
    if r1sha != R1_SHA:
        sys.exit("R1 CODE CHANGED (%s) - stopping" % r1sha)
    R1.selftest(); selftest()
    if a.selftest_only:
        return
    sha = lf_sha256(PREREG); hsha = lf_sha256(os.path.abspath(__file__))
    print("prereg LF sha256", sha, "| harness LF sha256", hsha, "| r1 code LF sha256", r1sha)
    if EXPECT_PREREG_SHA is None or sha != EXPECT_PREREG_SHA:
        sys.exit("PREREG HASH MISMATCH (or not frozen) - stopping")
    os.makedirs(a.out, exist_ok=True)
    res = {"prereg_sha256": sha, "harness_sha256": hsha, "r1_sha256": r1sha}
    # ---------- Stage 0 ----------
    eth, rth, info = R1.load_1m("NQ", R1.WARM0, R1.WF1)
    res["master"] = info; print("master", info)
    regular = R1.regular_days(rth)
    so_far, base = context_so_far(eth, rth, regular)
    trg = R1.triggers(rth)
    crown, cinfo = crown_382("2015-01-01", R1.WF1)
    crown = crown[(crown.day >= R1.WF0) & (crown.day <= R1.WF1)]
    res["crown"] = cinfo; print("crown", cinfo)
    gate = noise_short_open_at(entry_times(rth), crown)
    ctx = {"A": base.CTX.to_numpy(), "B": so_far.CTX.to_numpy(), "B0": so_far.CTX.to_numpy()}
    cbd = {k: ctx[k] & trg.CBD.to_numpy() & (gate if GATED[k] else True) for k in ARMS}
    engd = {k: ctx[k] & trg.ENGD.to_numpy() & (gate if GATED[k] else True) for k in ARMS}
    sig = {k: cbd[k] | engd[k] for k in ARMS}
    wf = np.asarray((rth.index >= pd.Timestamp(R1.WF0, tz=ET)) & (rth.index < pd.Timestamp(R1.WF1, tz=ET) + pd.Timedelta(days=1)))
    mn = R1._minute(rth.index); inw = (mn >= R1.WIN0) & (mn <= R1.WIN1)
    yrs = (pd.Timestamp(R1.WF1) - pd.Timestamp(R1.WF0)).days / 365.25
    print("\nSTAGE 0 CENSUS (WF; no outcomes). Context window bars: A (completed) %d, B (so far) %d; gate-open window minutes %d of %d" % (
        (ctx["A"] & wf & inw).sum(), (ctx["B"] & wf & inw).sum(), (gate & wf & inw).sum(), (wf & inw).sum()))
    power = {}
    day = rth["day"].values
    for k in ARMS:
        s = pd.Series(sig[k][wf]).groupby(day[wf]).sum()
        n_cap = int(s.clip(upper=R1.MAX_PER_DAY).sum())
        by_yr = s.clip(upper=R1.MAX_PER_DAY).groupby(pd.DatetimeIndex(pd.to_datetime(s.index)).year).sum().to_dict()
        power[k] = {"signals": int(sig[k][wf].sum()), "both": int((cbd[k] & engd[k])[wf].sum()), "n_capped": n_cap,
                    "per_year_cap": n_cap / yrs, "by_year": {int(y): int(v) for y, v in by_yr.items()}}
        if k != "A":
            ages = so_far.age_30.to_numpy()[sig[k] & wf]
            power[k]["age_30_minute0"] = int((ages == 0).sum())
            power[k]["age_30_hist"] = {"0": int((ages == 0).sum()), "1-9": int(((ages >= 1) & (ages <= 9)).sum()),
                                       "10-19": int(((ages >= 10) & (ages <= 19)).sum()), "20-29": int((ages >= 20).sum())}
        for rule, sd in R1.SD_ASSUMED.items():
            mde = 2.8 * sd / np.sqrt(max(n_cap, 1))
            power[k][rule] = {"mde_R_80pct": float(mde), "label": "powered" if R1.PRIOR_R >= mde else "UNDERPOWERED"}
        print("arm %-2s signals %d (BOTH %d), capped %d = %.1f/yr, by year %s | MDE E1 %.2f E2 %.2f E3 %.2f R vs prior %.2f %s" % (
            k, power[k]["signals"], power[k]["both"], n_cap, n_cap / yrs, power[k]["by_year"], power[k]["E1"]["mde_R_80pct"],
            power[k]["E2"]["mde_R_80pct"], power[k]["E3"]["mde_R_80pct"], R1.PRIOR_R,
            ("| 30m-bar age of signals %s" % power[k]["age_30_hist"]) if k != "A" else ""))
    res["power"] = power
    # ---------- Stage 1 ----------
    sessions = pd.DatetimeIndex(pd.to_datetime([str(d) for d in sorted(set(rth["day"]) & regular)]))
    trail5 = R1.five_min_high_trail(eth, rth)
    orb = R1.crown_trades(314, "2015-01-01", R1.WF1)[0]
    orb = orb[(orb.day >= R1.WF0) & (orb.day <= R1.WF1)]
    res["arms"] = {}; recs = []
    for k in ARMS:
        res["arms"][k] = {}
        for rule in ("E1", "E2", "E3"):
            tr = _floatify(R1.simulate(rth, sig[k], cbd[k], engd[k], trail5, rule))
            tr.to_csv(os.path.join(a.out, "trades_%s_%s.csv" % (k, rule)), index=False)
            t_wf = tr[(tr.day >= R1.WF0) & (tr.day <= R1.WF1)]
            blk = {"NQ cost": R1.read(t_wf, sessions, R1.COST_NQ),
                   "NQ cost +1 tick a side": R1.read(t_wf, sessions, R1.COST_NQ + 2 * R1.TICK),
                   "MNQ cost": R1.read(t_wf, sessions, R1.COST_MNQ)}
            for lo, hi in R1.HALVES:
                blk["half %s..%s" % (lo, hi)] = R1.read(t_wf, sessions, R1.COST_NQ, lo, hi)
            blk["ex Feb-Apr 2020"] = R1.read(t_wf[~((t_wf.day >= "2020-02-01") & (t_wf.day <= "2020-04-30"))], sessions, R1.COST_NQ)
            blk["ex top 3 trades"] = R1.read(t_wf.drop(t_wf.nlargest(3, "gross_pts").index), sessions, R1.COST_NQ)
            if k == "B0":
                g_on = noise_short_open_at(pd.DatetimeIndex(t_wf.entry_t), crown) if len(t_wf) else np.zeros(0, bool)
                blk["NOISE short open at entry"] = R1.read(t_wf[g_on], sessions, R1.COST_NQ)
                blk["NOISE short NOT open at entry"] = R1.read(t_wf[~g_on], sessions, R1.COST_NQ)
            sh = R1.shadow_block(t_wf, sessions, {314: orb})
            blk["ORB #314 flat days"] = sh["crowns"][314]["read_flat_days"]
            orb_share = sh["crowns"][314]["flat_share_of_own"]
            v = verdict(blk, power[k][rule]["label"]) if GATED[k] else None
            res["arms"][k][rule] = {"reads": blk, "verdict": v, "orb314_flat_share_of_own": orb_share}
            b = blk["NQ cost"]
            print("\n== arm %s %s%s  trades %d (%.1f/yr)  net $%.0f  ROC@30k %s  DD5 $%s  DD%% %s  Sortino %s  one-episode %s" % (
                k, rule, "  [FIRST-NAMED CELL]" if (k, rule) == FIRST_CELL else "", b["trades"], b["trades_yr"] or 0, b["net_usd"],
                R1._f(b["roc30"]), R1._f(b["dd5"], 0), R1._f(b["dd_pct_peak"], 2), R1._f(b["sortino"], 2), b["one_episode"]))
            print("   gross %s pts/trade vs cost %.3f | win %s%% | mean R net %s | boot t R %s | %s | ORB #314 flat-day share of own net %s" % (
                R1._f(b["gross_pts_per_trade"], 2), R1.COST_NQ, R1._f(100 * b["win_rate"] if b["win_rate"] is not None else None, 0),
                R1._f(b["mean_R_net"], 3), R1._f(b["boot_t_R"], 2),
                ("house bar %s | aid read %s" % (v["house_bar"], v["aid_read"])) if v else "report only (no verdict)", R1._f(orb_share, 2)))
            for lab in [x for x in blk if isinstance(blk[x], dict)]:
                print(R1._line(lab, blk[lab]))
            recs.append(run_record(k, rule, b, v, hsha, sha))
    res["summary"] = summary(res["arms"])
    print("\nSUMMARY:", json.dumps(res["summary"], indent=1, default=str))
    out_json = os.path.join(a.out, "ctxshort_r2_result.json")
    json.dump(res, open(out_json, "w"), indent=1, default=str)
    w = write_records(recs)
    print("run records:", w)
    # ---------- Stage 2: answer key (flags only) ----------
    try:
        res["answer_key"] = answer_key()
    except Exception as e:                       # Stage 1 is already saved; a key failure loses nothing
        res["answer_key"] = {"error": repr(e)}
        print("ANSWER KEY FAILED:", repr(e))
    json.dump(res, open(out_json, "w"), indent=1, default=str)


def answer_key():
    print("\nSTAGE 2 ANSWER KEY (frozen rules, 2026 bars, flags only, AFTER the WF read). Gate = NOISE #382 re-run on NQ 5m"
          " from %s (warm), applied to the ES / MES rows too:" % KEY_CROWN_FROM)
    rows = []
    crown, _ = crown_382(KEY_CROWN_FROM, "2026-10-16")
    for root in ("NQ", "ES"):
        keys = [k for k in R1.answer_key_list() if k[0] == root]
        if not keys:
            continue
        eth, rth, _ = R1.load_1m(root, "2025-11-01", "2026-10-16")
        regular = R1.regular_days(rth)
        so_far, base = context_so_far(eth, rth, regular)
        trg = R1.triggers(rth)
        gate = noise_short_open_at(entry_times(rth), crown)
        for _, d, t, lab in keys:
            hh, mm = (int(x) for x in str(t).split(":"))
            day = rth[rth["day"].astype(str) == d]
            at = day.index[R1._minute(day.index) == hh * 60 + mm]
            if not len(at):
                rows.append({"root": root, "date": d, "label": lab, "note": "no bar"}); continue
            i = rth.index.get_loc(at[0])
            T0 = at[0]
            near = [j for j in range(max(0, i - 10), min(len(rth), i + 11))
                    if abs((rth.index[j] - T0).total_seconds()) <= 300]
            trig = [j for j in near if (trg.CBD.iloc[j] or trg.ENGD.iloc[j])]
            ctx_of = {"A": base.CTX.to_numpy(), "B": so_far.CTX.to_numpy(), "B0": so_far.CTX.to_numpy()}
            fired = {arm: [rth.index[j].strftime("%H:%M") for j in trig if ctx_of[arm][j] and (gate[j] or not GATED[arm])]
                     for arm in ARMS}
            row = {"root": root, "date": d, "label": lab, "owner_candle": t, "reachable": R1.WIN0 <= hh * 60 + mm <= R1.WIN1,
                   "fired_within_5min": fired, "trigger_only_within_5min": [rth.index[j].strftime("%H:%M") for j in trig],
                   "noise_short_open_at_entry": bool(gate[i]),
                   "flags_completed": {c: bool(base[c].iloc[i]) for c in ("C1", "C2", "C3", "C4", "CTX")},
                   "flags_so_far": {c: bool(so_far[c].iloc[i]) for c in ("C1", "C2", "C3", "C4", "CTX")}}
            rows.append(row)
            print(root, d, lab, t, "| reachable" if row["reachable"] else "| NOT reachable", "| fired:", fired,
                  "| trigger fires:", row["trigger_only_within_5min"], "| NOISE short open at entry:", row["noise_short_open_at_entry"],
                  "| completed", row["flags_completed"], "| so far", row["flags_so_far"])
    return rows


if __name__ == "__main__":
    main()
