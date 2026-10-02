"""TTM round 20a/20b - order flow behind the fire (tools/TTM_R20_PREREG.txt, 5f5a0948).

Executes the pre-registration as written, on the in-hand 10-second capture (DESCRIPTIVE ONLY):
  - the frozen #299 crown (TTMSQZ_3_0.py, clean ATR engine) on ES/NQ x 5m/15m/30m RTH, NO-ADJUST
    masters (db_noadj_rth), one contract, costs ES 0.363 / NQ 0.533 pts;
  - each fire's order-flow imbalance = sum(delta) / sum(buy_vol + sell_vol) over the 10s rows inside the
    FIRE bar (the signal bar; entry is the next bar's open). NT stamps a 10s row at its END, so a row
    stamped e belongs to the bar starting s when s < e <= s + bar length;
  - coverage < 0.8 or a 10s close more than 2 ticks off the master's bar close = "no data";
  - agree = sign(imbalance) == trade side (0 = disagree); R = net points / (1.5 x ATR at the fire bar).
20a: gated fires, agree vs disagree, and the agree-only 6-cell book vs the all-fires book.
20b: the same cells UNGATED (gate_mode "none"); ungated fires the gate would have blocked, split by
     agreement, against the gated fires' mean R.
Reported, no verdict: the coil's imbalance (squeeze-on bars before the fire).

The screen written in the prereg: the forward shadow starts only if gated agree mean R > disagree mean R.

Log: tools/data/ttmsqz_r20a_orderflow.txt ; per-fire rows: tools/data/ttmsqz_r20a_orderflow_fires.csv
"""
import os
import sys
import importlib.util

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.chdir(SHARED)
sys.path.insert(0, SHARED)
from augur_engine.data import find_master, load_master_arrays   # noqa: E402

CROWN = dict(length=20, bb_mult=2.0, kc_mult=1.5, min_sq_bars=1, entry_fill="open",
             exit_mode="fade", fade_bars=1, stop_atr=1.5, eod_cutoff=1, gate_tf_min=60,
             gate_mode="sq_on", gate_len=20, gate_bars=2, gate_ratio=1.0, gate_fired_k=3,
             direction="both")
CELLS = [(i, tf) for i in ("ES", "NQ") for tf in ("5m", "15m", "30m")]
COST = {"ES": 0.363, "NQ": 0.533}
MULT = {"ES": 50.0, "NQ": 20.0}
TICK = 0.25
CAP_FROM = pd.Timestamp(os.environ.get("TTM_R20_FROM", "2026-06-23"), tz="US/Eastern")
LOAD_FROM = "2025-06-01"          # warm-up for the 20-bar squeeze and the hourly gate
# Last session to read (inclusive). The engine treats the last bar it is given as a session close, so a
# master refreshed mid-session would force-close a live trade at an intraday price; the shadow sets this
# to the last COMPLETED session (review 2026-09-30). None = everything in the master (the in-hand read).
LOAD_TO = os.environ.get("TTM_R20_TO") or None
OUT = os.path.join(HERE, "tools", "data", "ttmsqz_r20a_orderflow.txt")
FIRES_CSV = os.path.join(HERE, "tools", "data", "ttmsqz_r20a_orderflow_fires.csv")
L = []


def emit(x=""):
    L.append(x)
    print(x, flush=True)


def _load_mod():
    sp = importlib.util.spec_from_file_location("TTMSQZ_3_0_r20", os.path.join(SHARED, "augur_strategies", "TTMSQZ_3_0.py"))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


MOD = _load_mod()


def load_10s(root):
    d = pd.read_csv(r"C:\EdgeLog\ohlc\%s_10s.csv" % root)
    d = d.drop_duplicates("time", keep="last").sort_values("time")
    d["flow"] = d["buy_vol"].astype(float) + d["sell_vol"].astype(float)
    # PAPER-NT8 rule (inbox #31, 2026-10-02): rt=3 rows (volume but no trade ticks - NT back-filled after the
    # PC slept) and any row with volume but buy+sell = 0 carry NO order flow: they are MISSING, never zero
    # delta. Zero-flow rows already add nothing and do not count toward coverage; rt=3 is dropped by name.
    if "rt" in d.columns:
        d = d[d["rt"] != 3]
    return d[["time", "close", "delta", "flow"]].reset_index(drop=True)


def window_flow(tens, s_utc, e_utc, tf_sec):
    """Imbalance, coverage and last close over the 10s rows stamped in (s, e]."""
    t = tens["time"].values
    a = np.searchsorted(t, s_utc, side="right")
    b = np.searchsorted(t, e_utc, side="right")
    seg = tens.iloc[a:b]
    rows = int((seg["flow"] > 0).sum())
    cov = rows / (tf_sec / 10.0)
    fl = float(seg["flow"].sum())
    imb = float(seg["delta"].sum()) / fl if fl > 0 else np.nan
    last = float(seg["close"].iloc[-1]) if len(seg) else np.nan
    return imb, cov, last


def cell_fires(inst, tf, gate_mode, tens):
    arr = load_master_arrays(find_master(inst, tf, "rth", "db_noadj_rth"), date_from=LOAD_FROM, date_to=LOAD_TO)
    p = dict(CROWN, gate_mode=gate_mode)
    o, h, l, c = arr["open"], arr["high"], arr["low"], arr["close"]
    res = MOD.run_backtest(o, h, l, c, day_id=arr["day_id"], index=arr["index"], return_trades=True, **p)
    _, _, atr = MOD.squeeze_indicators(np.asarray(h, float), np.asarray(l, float), np.asarray(c, float),
                                       p["length"], p["bb_mult"], p["kc_mult"])
    sq_on, _, _ = MOD.squeeze_indicators(np.asarray(h, float), np.asarray(l, float), np.asarray(c, float),
                                         p["length"], p["bb_mult"], p["kc_mult"])
    idx = pd.DatetimeIndex(arr["index"])
    tfm = int(tf[:-1])
    tf_sec = tfm * 60
    rows = []
    for t in (res or {}).get("trades", []):
        eb, xb, pts, side = int(t[0]), int(t[1]), float(t[2]), int(t[3])
        fb = eb - 1
        if idx[fb] < CAP_FROM:
            continue
        net = pts - COST[inst]
        s_utc = int(idx[fb].tz_convert("UTC").timestamp())
        imb, cov, last = window_flow(tens, s_utc, s_utc + tf_sec, tf_sec)
        # the coil: consecutive squeeze-on bars ending the bar before the fire
        k = fb - 1
        while k >= 0 and sq_on[k]:
            k -= 1
        c0 = k + 1
        if c0 <= fb - 1:
            cs = int(idx[c0].tz_convert("UTC").timestamp())
            cimb, ccov, _ = window_flow(tens, cs, s_utc, s_utc - cs)
        else:
            cimb, ccov = np.nan, 0.0
        price_ok = np.isfinite(last) and abs(last - float(c[fb])) <= 2 * TICK + 1e-9
        ok = bool(cov >= 0.8 and price_ok and np.isfinite(imb))
        stop_dist = 1.5 * float(atr[fb])
        rows.append(dict(inst=inst, tf=tf, gate=gate_mode, fire_bar=str(idx[fb]), entry_bar=str(idx[eb]),
                         exit_date=idx[xb].tz_localize(None).normalize(), side=side, net_pts=net,
                         usd=net * MULT[inst], R=net / stop_dist if stop_dist > 0 else np.nan,
                         imb=imb, cov=cov, price_gap=(last - float(c[fb])) if np.isfinite(last) else np.nan,
                         ok=ok, agree=bool(ok and np.sign(imb) == side and imb != 0),
                         coil_imb=cimb, coil_cov=ccov,
                         coil_agree=bool(np.isfinite(cimb) and np.sign(cimb) == side and cimb != 0),
                         candle=bool(np.sign(float(c[fb]) - float(o[fb])) == side)))
    return rows


def book(df, cal):
    s = df.groupby("exit_date")["usd"].sum().reindex(cal, fill_value=0.0)
    cum = np.concatenate([[0.0], s.cumsum().values])
    dd = float((np.maximum.accumulate(cum) - cum).max())
    yrs = ((cal[-1] - cal[0]).days + 1) / 365.25
    net = float(s.sum())
    mar = (net / yrs) / dd if dd > 1e-9 else float("inf")
    dn = np.minimum(s.values, 0.0)
    ddv = float(np.sqrt(np.mean(dn ** 2)))
    sor = float(s.mean()) / ddv * np.sqrt(252.0) if ddv > 1e-9 else float("inf")
    return dict(n=len(df), net=net, dd=dd, roc=30.0 * mar, sortino=sor)


def perm_p(a, b, n=10000, seed=7):
    """One-sided p that mean(a) - mean(b) is this large by label shuffling."""
    if len(a) == 0 or len(b) == 0:
        return np.nan
    rng = np.random.default_rng(seed)
    x = np.concatenate([a, b]); k = len(a)
    obs = a.mean() - b.mean()
    hits = 0
    for _ in range(n):
        rng.shuffle(x)
        hits += (x[:k].mean() - x[k:].mean()) >= obs - 1e-12
    return (hits + 1) / (n + 1)


def split_line(label, df):
    a, d = df[df.agree], df[~df.agree]
    emit("  %-34s agree %3d  mean R %+.3f  $%9s | disagree %3d  mean R %+.3f  $%9s | p %.3f" % (
        label, len(a), a.R.mean() if len(a) else np.nan, "{:,.0f}".format(a.usd.sum()),
        len(d), d.R.mean() if len(d) else np.nan, "{:,.0f}".format(d.usd.sum()),
        perm_p(a.R.values, d.R.values)))


def main():
    emit("TTM round 20a/20b - order flow behind the fire (prereg tools/TTM_R20_PREREG.txt, 5f5a0948)")
    emit("frozen #299 crown, TTMSQZ_3_0.py, ES/NQ x 5m/15m/30m RTH db_noadj_rth, one contract; fires from %s" % CAP_FROM.date())
    tens = {r: load_10s(r) for r in ("ES", "NQ")}
    for r, d in tens.items():
        emit("  10s capture %s: %d rows, %s .. %s (UTC end stamps)" % (
            r, len(d), pd.to_datetime(d.time.iloc[0], unit="s"), pd.to_datetime(d.time.iloc[-1], unit="s")))
    allrows = []
    for inst, tf in CELLS:
        for g in ("sq_on", "none"):
            allrows += cell_fires(inst, tf, g, tens[inst])
    df = pd.DataFrame(allrows)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    df.to_csv(FIRES_CSV, index=False)
    last_day = df.exit_date.max()
    cal = pd.bdate_range(CAP_FROM.tz_localize(None).normalize(), last_day)

    emit("")
    emit("COVERAGE (fires on the capture stretch, by cell; ok = coverage >= 0.8 and price within 2 ticks)")
    for (inst, tf, g), x in df.groupby(["inst", "tf", "gate"], sort=False):
        emit("  %s %-3s gate %-5s fires %3d  ok %3d  (low coverage %d, price gap %d)" % (
            inst, tf, g, len(x), int(x.ok.sum()), int((x["cov"] < 0.8).sum()),
            int(((x["cov"] >= 0.8) & ~x.ok).sum())))

    G = df[(df.gate == "sq_on") & df.ok]
    U = df[(df.gate == "none") & df.ok]
    emit("")
    emit("20a - GATED fires with order-flow data, agree vs disagree (R = net pts / 1.5 ATR)")
    split_line("ALL six cells", G)
    for (inst, tf), x in G.groupby(["inst", "tf"], sort=False):
        split_line("%s %s" % (inst, tf), x)
    emit("")
    emit("20a - the six-cell book, capture stretch %s .. %s (daily P&L, one contract per cell)" % (cal[0].date(), cal[-1].date()))
    Gall = df[df.gate == "sq_on"]
    for lab, x in (("all gated fires (incl. no-data)", Gall), ("gated fires with data", G),
                   ("agree only", G[G.agree]), ("disagree only", G[~G.agree])):
        b = book(x, cal)
        emit("  %-34s n %3d  net $%9s  DD $%8s  ROC@30k %8.1f  Sortino %6.2f" % (
            lab, b["n"], "{:,.0f}".format(b["net"]), "{:,.0f}".format(b["dd"]), b["roc"], b["sortino"]))

    emit("")
    emit("20b - UNGATED fires the hourly gate would have BLOCKED, by agreement, vs the gated fires")
    gk = set(zip(G.inst, G.tf, G.entry_bar))
    B = U[[k not in gk for k in zip(U.inst, U.tf, U.entry_bar)]]
    emit("  gated fires with data: %d, mean R %+.3f" % (len(G), G.R.mean() if len(G) else np.nan))
    split_line("blocked-by-gate, ALL cells", B)
    for (inst, tf), x in B.groupby(["inst", "tf"], sort=False):
        split_line("blocked %s %s" % (inst, tf), x)
    emit("  blocked-agree adds %d trades to %d gated (+%.0f%%); blocked-agree mean R %+.3f vs gated %+.3f" % (
        int(B.agree.sum()), len(G), 100.0 * B.agree.sum() / max(len(G), 1),
        B[B.agree].R.mean() if B.agree.any() else np.nan, G.R.mean() if len(G) else np.nan))

    emit("")
    emit("REPORTED, NO VERDICT - the coil's order flow (squeeze-on bars before the fire), gated fires with data")
    C = G[G.coil_cov > 0]
    a, d = C[C.coil_agree], C[~C.coil_agree]
    emit("  coil agrees %d  mean R %+.3f | coil disagrees %d  mean R %+.3f | p %.3f" % (
        len(a), a.R.mean() if len(a) else np.nan, len(d), d.R.mean() if len(d) else np.nan,
        perm_p(a.R.values, d.R.values)))

    emit("")
    ga, gd = G[G.agree].R.mean(), G[~G.agree].R.mean()
    emit("SCREEN (prereg): gated agree mean R %+.3f vs disagree %+.3f -> forward shadow %s" % (
        ga, gd, "STARTS" if ga > gd else "does NOT start"))
    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("log ->", OUT)


if __name__ == "__main__":
    main()
