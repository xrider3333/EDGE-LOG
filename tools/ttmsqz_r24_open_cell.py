"""TTM round 24 - the 10:00-ET first-fillable-bar cell and its matched control (tools/TTM_R24_PREREG.txt).

O1 = TTM #459 (TTMSQZ_3_0_ES30SSOF2.py) restricted to orders decided on the session's first bar (filled at 10:00
ET), the leg's own exits and sizes. Checked two ways: the #459 trades whose fill bar is ordinal 1, and a run whose
trade loop only accepts first-bar orders - they must agree to the trade.
M1 / M0 = one mechanical rule on every session, the label being whether the 09:30 bar FIRED: enter at 10:00 in the
squeeze momentum's sign when #459's hourly gate allows that side, exit on 2 fading bars or the close, no stop,
size 1. Same code path for both arms (the structural-stop loop with an infinitely far stop).
Only 2010-06-07 .. 2025-06-30 is loaded: the lockbox year is never read.
Log: tools/data/ttmsqz_r24_open_cell.txt
"""
import importlib.util
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.chdir(SHARED)
sys.path.insert(0, SHARED)
from augur_engine.data import find_master, load_master_arrays   # noqa: E402


def _imp(name, path):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


L459 = _imp("TTMSQZ_3_0_ES30SSOF2_r24", os.path.join(SHARED, "augur_strategies", "TTMSQZ_3_0_ES30SSOF2.py"))
SO = L459._so
SS = SO._ss                           # the structural-stop module THIS chain uses
ORIG = SS._simulate
R19 = _imp("r19a", os.path.join(HERE, "tools", "ttmsqz_r19a_multicell_sleeve.py"))
PARAMS = dict(kc_mult=1.5, eod_cutoff=1, gate_len=20)
COST, MULT = 0.363, 50.0
D0, LOAD_TO = "2010-06-07", "2025-06-30"
WF0, WF1 = "2016-06-30", "2025-06-29"
TB0, TB1 = "2010-06-07", "2016-06-29"
HALVES = [("2016-06-30", "2021-12-31"), ("2022-01-01", "2025-06-29")]
NO2020 = ("2020-02-01", "2020-04-30")
DDWIN = ("2020-03-02", "2020-03-27")      # #463's worst WF drawdown window (MDL r1)
OUT = os.path.join(HERE, "tools", "data", "ttmsqz_r24_open_cell.txt")
L = []


def emit(x=""):
    L.append(x)
    print(x, flush=True)


def fmt(x):
    return "{:,.0f}".format(x)


def stats_line(label, td, cal, d0, d1):
    s = R19.stretch_stats(td, cal, d0, d1)
    emit("  %-34s n %4d  net $%9s  DD $%8s  ROC@30k %6.1f  Sortino %5.2f  PF %5.2f  ex-big $%9s" % (
        label, s["n"], fmt(s["net"]), fmt(s["dd"]), s["roc"], min(s["sortino"], 99), min(s["pf"], 99),
        fmt(s["net_ex_biggest"])))
    return s


def in_window(day, d0, d1):
    return pd.Timestamp(d0) <= day <= pd.Timestamp(d1)


def main():
    emit("TTM round 24 - the 10:00-ET first-fillable-bar cell + matched control (prereg tools/TTM_R24_PREREG.txt)")
    arr = load_master_arrays(find_master("ES", "30m", "rth", "db_adj_rth"), date_from=D0, date_to=LOAD_TO)
    o, h, l, c = (np.asarray(arr[k], float) for k in ("open", "high", "low", "close"))
    did = np.asarray(arr["day_id"])
    idx_tz = pd.DatetimeIndex(arr["index"])
    idx = idx_tz.tz_localize(None)
    day = idx.normalize()
    cal = R19.full_calendar([idx], D0, LOAD_TO)
    ordn = SO._session_ordinal(did)
    first_hm = pd.Series(idx[ordn == 0].strftime("%H:%M")).value_counts()
    emit("Loaded ES 30m db_adj_rth %s .. %s: %d bars, %d sessions; first-bar stamps: %s" % (
        idx[0].date(), idx[-1].date(), len(idx), int((ordn == 0).sum()),
        ", ".join("%s x%d" % (k, v) for k, v in first_hm.items())))

    # ---- parity: #459 unchanged, then the first-bar-only loop ----
    twin = L459.run_backtest(arr["open"], arr["high"], arr["low"], arr["close"], day_id=arr["day_id"],
                             index=arr["index"], return_trades=True, **PARAMS)["trades"]
    o1 = [t for t in twin if ordn[int(t[0])] == 1]

    def first_bar_only(o_, h_, l_, c_, n, warm, mom, atr, fire, *rest):
        return ORIG(o_, h_, l_, c_, n, warm, mom, atr, np.asarray(fire) & (ordn == 0), *rest)

    SS._simulate = first_bar_only
    try:
        o1b = L459.run_backtest(arr["open"], arr["high"], arr["low"], arr["close"], day_id=arr["day_id"],
                                index=arr["index"], return_trades=True, **PARAMS)["trades"]
    finally:
        SS._simulate = ORIG
    usd = lambda tr: [(day[int(t[1])], (float(t[2]) - COST) * MULT) for t in tr]   # noqa: E731
    same = len(o1) == len(o1b) and all(tuple(a) == tuple(b) for a, b in zip(o1, o1b))
    emit("PARITY: #459 %d trades $%s at x1 (expect 340); ordinal-1 fills %d $%s (expect 81 / $42,983); "
         "first-bar-only loop identical to the trade: %s" % (
             len(twin), fmt(sum(u for _, u in usd(twin))), len(o1), fmt(sum(u for _, u in usd(o1))),
             "YES" if same else "NO - STOP"))
    if not same:
        return finish()

    # ---- the matched control: one rule, every session, labelled by the 09:30 fire ----
    A = SS._build_arrays(o, h, l, c, did, arr["index"], PARAMS["kc_mult"], PARAMS["gate_len"])
    sq_on = SS._t3.squeeze_indicators(h, l, c, SS._FROZEN["length"], SS._FROZEN["bb_mult"], PARAMS["kc_mult"])[0]
    n = A["n"]
    inf_hi, inf_lo = np.full(n, np.inf), np.full(n, -np.inf)
    first = ordn == 0

    def matched(gl, gs):
        return ORIG(o, h, l, c, n, A["warm"], A["mom"], A["atr"], first, inf_hi, inf_lo, gl, gs,
                    A["last_bar"], 2, PARAMS["eod_cutoff"], 0.0, "both")

    M = matched(A["gate_long"], A["gate_short"])
    MNG = matched(np.ones(n, bool), np.ones(n, bool))
    fired = lambda t: bool(A["fire"][int(t[0]) - 1])                                # noqa: E731
    M1 = [t for t in M if fired(t)]
    M0 = [t for t in M if not fired(t)]
    o1_keys = {(int(t[0]), int(t[3])) for t in o1}
    m1_keys = {(int(t[0]), int(t[3])) for t in M1}
    emit("CONTROL: %d gated 10:00 entries = %d fire days (M1) + %d no-fire days (M0); M1 entries == O1 entries "
         "(bar and side): %s" % (len(M), len(M1), len(M0), "YES" if o1_keys == m1_keys else "NO (%d vs %d, overlap %d)" % (
             len(m1_keys), len(o1_keys), len(m1_keys & o1_keys))))
    unit = lambda tr: [(day[int(t[1])], (float(t[2]) - COST) * MULT) for t in tr]    # noqa: E731

    def arr_in(tr, d0, d1):
        return np.array([u for d, u in unit(tr) if in_window(d, d0, d1)])

    # ---- classification (WF) - power line first ----
    emit("")
    emit("CLASSIFICATION (WF %s .. %s, size 1, $ per trade net of 0.363 pts)" % (WF0, WF1))
    x1, x0 = arr_in(M1, WF0, WF1), arr_in(M0, WF0, WF1)
    pooled = np.concatenate([x1, x0])
    sd = float(pooled.std(ddof=1))
    mde = 2.8 * sd * np.sqrt(1.0 / len(x1) + 1.0 / len(x0))
    emit("  POWER LINE: n1 %d, n0 %d, pooled sd $%s -> minimum detectable m1 - m0 = $%s a trade" % (
        len(x1), len(x0), fmt(sd), fmt(mde)))

    def classify(x1, x0, tag):
        m1, m0 = float(x1.mean()), float(x0.mean())
        rng = np.random.default_rng(7)
        pool = np.concatenate([x1, x0]); k = len(x1); obs = m1 - m0
        cnt = 0
        for _ in range(10000):
            p = rng.permutation(pool)
            cnt += (p[:k].mean() - p[k:].mean()) >= obs
        p_perm = (cnt + 1) / 10001.0
        rng = np.random.default_rng(7)
        bs = np.array([rng.choice(x0, len(x0)).mean() for _ in range(10000)])
        p0 = float((bs <= 0).mean())
        sq = p_perm <= 0.05 and m0 <= 0.5 * m1
        op = p0 <= 0.05 and m0 >= 0.5 * m1
        lab = "SQUEEZE EFFECT" if sq else "OPENING EFFECT" if op else "UNDECIDED"
        emit("  %-28s m1 $%6s (n %3d)  m0 $%6s (n %4d)  m1-m0 $%6s  p_perm %.4f  p0 %.4f  m0/m1 %5.2f -> %s" % (
            tag, fmt(m1), len(x1), fmt(m0), len(x0), fmt(m1 - m0), p_perm, p0, m0 / m1 if m1 else float("nan"), lab))
        return lab, m1 - m0

    lab, diff = classify(x1, x0, "WF (THE LABEL)")
    checks = []
    lab_tb, _ = classify(arr_in(M1, TB0, TB1), arr_in(M0, TB0, TB1), "tuning block 2010-16")
    checks.append(("tuning block same label", lab_tb == lab))
    for a, b in HALVES:
        _, d = classify(arr_in(M1, a, b), arr_in(M0, a, b), "half %s .. %s" % (a[:4], b[:4]))
        checks.append(("half %s-%s keeps sign of m1-m0" % (a[:4], b[:4]), np.sign(d) == np.sign(diff)))
    keep = lambda tr: [t for t in tr if not in_window(day[int(t[1])], *NO2020)]   # noqa: E731
    _, d = classify(arr_in(keep(M1), WF0, WF1), arr_in(keep(M0), WF0, WF1), "WF without Feb-Apr 2020")
    checks.append(("without Feb-Apr 2020 keeps sign", np.sign(d) == np.sign(diff)))
    emit("  LABEL: %s; checks: %s%s" % (lab, "; ".join("%s %s" % (k, "yes" if v else "NO") for k, v in checks),
                                       "" if all(v for _, v in checks) else " -> FRAGILE"))

    # ---- O1 standalone: the map placement ----
    emit("")
    emit("O1 STANDALONE (sized as #459 sizes, x1) - WF %s .. %s; tuning block reported below" % (WF0, WF1))
    rest = [t for t in twin if ordn[int(t[0])] != 1]
    s459 = stats_line("#459 entire", usd(twin), cal, WF0, WF1)
    so1 = stats_line("O1 = 10:00 fills only", usd(o1), cal, WF0, WF1)
    stats_line("#459 without its 10:00 fills", usd(rest), cal, WF0, WF1)
    stats_line("M1 (control rule, fire days)", unit(M1), cal, WF0, WF1)
    stats_line("M0 (control rule, no-fire days)", unit(M0), cal, WF0, WF1)
    emit("  tuning block %s .. %s:" % (TB0, TB1))
    for lab_, td in (("#459 entire", usd(twin)), ("O1", usd(o1)), ("M1", unit(M1)), ("M0", unit(M0))):
        stats_line(lab_, td, cal, TB0, TB1)
    yrs = so1["yrs"]
    scale = 30000.0 / so1["dd"] if so1["dd"] > 0 else float("nan")
    per_yr30 = so1["net"] / yrs * scale
    in_dd = sum(u for d, u in usd(o1) if in_window(d, *DDWIN)) * scale
    rule = "gains there" if in_dd >= 0 else "%s a year per $1,000 lost (rule: > $3,127)" % fmt(per_yr30 / (-in_dd / 1000.0))
    emit("  MAP: O1 earns $%s a year at a $30k own drawdown (MDL line $15,000); inside #463's worst WF drawdown "
         "(%s .. %s) it made $%s at that scale -> %s" % (fmt(per_yr30), DDWIN[0], DDWIN[1], fmt(in_dd), rule))
    av = [("WF trades >= 100", so1["n"] >= 100), ("ROC@30k >= #459 (%.1f)" % s459["roc"], so1["roc"] >= s459["roc"]),
          ("ROC@30k >= 15", so1["roc"] >= 15), ("Sortino >= #459 (%.2f)" % s459["sortino"], so1["sortino"] >= s459["sortino"]),
          ("WF net ex-biggest > 0", so1["net_ex_biggest"] > 0)]
    emit("  AUTO-VALIDATE BARS: %s -> %s" % ("; ".join("%s %s" % (k, "yes" if v else "NO") for k, v in av),
                                           "AUTO-VALIDATE" if all(v for _, v in av) else "RESEARCH ROW (TTM-R24), never a leg"))

    # ---- diagnostics ----
    emit("")
    emit("DIAGNOSTICS (no verdict)")
    deep = SS._deep_state(arr["high"], arr["low"], arr["close"], arr["day_id"], arr["index"])

    def size_of(t):
        eb = int(t[0])
        s = float(SS._TILT_MULT) if bool(deep[max(eb - 1, 0)]) else 1.0
        return s * (float(SO._OPEN_MULT) if ordn[eb] == 1 else 1.0)

    raw_o1 = [t for t in ORIG(o, h, l, c, n, A["warm"], A["mom"], A["atr"], A["fire"] & first, A["rng_hi"],
                              A["rng_lo"], A["gate_long"], A["gate_short"], A["last_bar"], 2, PARAMS["eod_cutoff"],
                              SS._STRUCT_BUF, "both")]
    chk = all(abs(size_of(r) * (float(r[2]) - COST) * MULT - (float(t[2]) - COST) * MULT) < 1e-6
              for r, t in zip(raw_o1, o1)) and len(raw_o1) == len(o1)
    emit("  re-pricing check (raw loop x size == #459's sized O1 trades): %s" % ("YES" if chk else "NO"))

    def path(tr, sized):
        P = np.full((len(tr), 12), np.nan)
        for i, t in enumerate(tr):
            eb, xb, sd_, ep = int(t[0]), int(t[1]), int(t[3]), float(t[4])
            s = size_of(t) if sized else 1.0
            fin = s * (float(t[2]) - COST) * MULT
            for k in range(12):
                b = eb + k
                P[i, k] = fin if b >= xb else s * (sd_ * (c[b] - ep) - COST) * MULT
        return np.nanmean(P, axis=0)

    for lab_, tr, sz in (("O1", [r for r in raw_o1 if in_window(day[int(r[1])], WF0, WF1)], True),
                         ("M1", [t for t in M1 if in_window(day[int(t[1])], WF0, WF1)], False),
                         ("M0", [t for t in M0 if in_window(day[int(t[1])], WF0, WF1)], False)):
        emit("  event path %-3s mean cum $ by bar 0-11: %s" % (lab_, " ".join("%+.0f" % v for v in path(tr, sz))))
    emit("  per WF year (06-30 blocks), O1 net / M1 mean / M0 mean:")
    for k in range(9):
        a = pd.Timestamp(WF0) + pd.DateOffset(years=k)
        b = a + pd.DateOffset(years=1) - pd.Timedelta(days=1)
        y1 = [u for d, u in usd(o1) if a <= d <= b]
        ym1 = [u for d, u in unit(M1) if a <= d <= b]
        ym0 = [u for d, u in unit(M0) if a <= d <= b]
        emit("    %s: O1 n %2d $%8s | M1 n %2d mean $%6s | M0 n %3d mean $%6s" % (
            a.year, len(y1), fmt(sum(y1)), len(ym1), fmt(np.mean(ym1)) if ym1 else "-", len(ym0),
            fmt(np.mean(ym0)) if ym0 else "-"))
    for lab_, tr, pr in (("O1", o1, usd), ("M1", M1, unit), ("M0", M0, unit)):
        for side, nm in ((1, "long"), (-1, "short")):
            v = [u for (d, u), t in zip(pr(tr), tr) if int(t[3]) == side and in_window(d, WF0, WF1)]
            emit("  %s %-5s n %4d net $%9s mean $%6s" % (lab_, nm, len(v), fmt(sum(v)), fmt(np.mean(v)) if v else "-"))
    emit("  cost curve, WF net at 0 / 5 / 10 / 20 bps of the entry price per round trip:")
    for lab_, tr, sized in (("O1", raw_o1, True), ("M1", M1, False), ("M0", M0, False)):
        row = []
        for bps in (0, 5, 10, 20):
            tot = 0.0
            for t in tr:
                if not in_window(day[int(t[1])], WF0, WF1):
                    continue
                s = size_of(t) if sized else 1.0
                tot += s * (float(t[2]) - bps / 1e4 * float(t[4])) * MULT
            row.append("$%s" % fmt(tot))
        emit("    %s: %s" % (lab_, " / ".join(row)))
    for lab_, keep_on in (("M0, 09:30 bar still IN a squeeze", True), ("M0, 09:30 bar NOT in a squeeze", False)):
        v = [u for (d, u), t in zip(unit(M0), M0) if bool(sq_on[int(t[0]) - 1]) == keep_on and in_window(d, WF0, WF1)]
        emit("  %-34s n %4d mean $%6s" % (lab_, len(v), fmt(np.mean(v)) if v else "-"))
    ng1 = [u for (d, u), t in zip(unit(MNG), MNG) if fired(t) and in_window(d, WF0, WF1)]
    ng0 = [u for (d, u), t in zip(unit(MNG), MNG) if not fired(t) and in_window(d, WF0, WF1)]
    emit("  no hourly gate (all sessions): fire days n %d mean $%s | no-fire days n %d mean $%s" % (
        len(ng1), fmt(np.mean(ng1)), len(ng0), fmt(np.mean(ng0))))
    return finish()


def finish():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
