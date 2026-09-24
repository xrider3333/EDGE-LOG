"""TTM SQUEEZE ROUND 16a - the fade-exit DOSE-RESPONSE curve.

Run #364 validated waiting for a SECOND momentum-fading bar before the squeeze exits (fade_bars=2)
against fade_bars=1: more money, lower drawdown, a bigger lockbox, a slightly lower whole-run profit
factor. Nobody has asked what 3, 4 or 6 fading bars do, or the limit case of never fading at all and
simply holding every open trade to the session close. If 2 is a genuine peak with 3 falling away,
that is a real optimum - one extra bar of patience and no more. If the curve keeps climbing to the
limit, the fade exit is not doing any work at all and the leg should just hold to the close.

BASE: the combined book leg - structural stop + 1.5x deep-squeeze tilt + 1.5x open-bar tilt -
augur_strategies/TTMSQZ_3_0_ES30SSOF2.py, on ES 30m RTH. Everything else frozen at the crowned cell
(kc_mult 1.5, eod_cutoff 1, gate_len 20 - the last forced internally by the SSO/SSOF2 wrappers
regardless of what is passed in).

THE FROZEN TRAP (see TTMSQZ_3_0_ES30SSF2.py's docstring): the structural-stop engine
(TTMSQZ_3_0_ES30SS.py) reads fade_bars out of its OWN module-level `_FROZEN` dict and silently
IGNORES a `fade_bars=` kwarg passed into run_backtest. This has already discarded a change twice in
this family. So this driver loads TTMSQZ_3_0_ES30SSOF2.py through its own private
importlib.util.spec_from_file_location (never the shared module cache) and, for each sweep value,
rebinds `mod._so._ss._FROZEN` exactly the way TTMSQZ_3_0_ES30SSOF2.py itself does at import time.
Because every wrapper in this family loads its parent through its OWN spec, this rebinding reaches
only this driver's private copy of the module chain.

THE "HOLD TO THE CLOSE" LIMIT CASE, STATED PLAINLY: the structural-stop engine's trade loop
(`_simulate` in TTMSQZ_3_0_ES30SS.py) never reads `exit_mode` at all - it is carried in `_FROZEN` as
a vestigial key ('fade') but the loop has exactly one exit mechanism besides the protective stop and
the end-of-session close: `fade_cnt >= fade_bars`. There is no separate switch to ask for "no fade
exit" directly. But an ES 30m RTH session is at most 13 bars, so setting fade_bars to a sentinel far
above any possible in-session fade streak (this driver uses 9999) makes `fade_cnt >= fade_bars` false
for the rest of eternity - the condition can mathematically never fire. That is not an approximation
of "hold to the close", it IS "hold to the close": the only two ways a trade can end are then the
stop and the session close. This driver verifies computationally (see the exit-mix columns) that zero
trades exit by fade under the sentinel before trusting the row.

EXIT-MIX ATTRIBUTION: run_backtest's own trade tuples carry no exit-reason tag, and this driver does
not edit augur_strategies/ to add one. Instead it runs a second, LOCAL copy of the same engine's bar
loop (`_simulate` in TTMSQZ_3_0_ES30SS.py, copied verbatim into this file with one addition: a reason
string logged at each `_book` call site: "fade" / "stop" / "close"), built from the SAME arrays
(`_build_arrays`, same kc_mult/eod_cutoff/gate_len/fade_bars/struct_buf/direction) the real engine
uses. The two trade lists are then joined by entry_bar (unique per trade, since only one position is
ever open at a time, and unchanged by every wrapper's re-pricing) and the counts are asserted to
reconcile exactly with the real, priced trade count before any row is trusted.

DISCIPLINE: window 2010-06-07..2026-06-30, lockbox from 2025-07-01, ES 0.363 points a round trip at
50 dollars a point, 16.06 years. Pre-lockbox trades are split 60/40 BY TIME (by position in the
already-time-ordered trade list, the same convention tools/ttmsqz_r15e_open_bar_tilt.py uses) into a
discovery half and a holdout half. Judged on annualised MAR on the leg's own drawdown, lockbox net and
lockbox profit factor - never on whole-run profit factor, which is not a clause in any bar this family
crowns on (see TTMSQZ_3_0_ES30SSF2.py's docstring for why that screen is a triage heuristic, not the
bar). MANDATORY PARITY GATE before any number is trusted: fade_bars=2 must reproduce run #369's
354 / $135,884 / PF 3.12 / lockbox $22,739 / lockbox PF 9.89 / lockbox DD $1,978 / whole-run DD $4,634
/ MAR 1.826, and fade_bars=1 must reproduce run #368's 357 / $136,043 / PF 3.28 / lockbox $22,321 /
lockbox PF 8.52 / lockbox DD $2,003 / whole-run DD $5,330 / MAR 1.589, to the numbers published in
TTMSQZ_3_0_ES30SSOF2.py's own docstring.

SCAN ONLY. Nothing here is crowned, queued for Auto-Validate, or written to index.html.
Log: tools/data/ttmsqz_r16a_fade_dose.txt
"""
import os
import sys
import importlib.util

import numpy as np
import pandas as pd

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"


def _mod(path, name):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


# ---- the same tagged trade loop as TTMSQZ_3_0_ES30SS.py's _simulate, with a reason logged at
# ---- each _book() call site. Copied, not imported, because the real function does not tag exits
# ---- and augur_strategies/ is not to be touched. Every branch and ordering below is identical to
# ---- the source; only the extra `reason` argument to _book and its 7th tuple field are new.
def _simulate_tagged(o, h, l, c, n, warm, mom, atr, fire, rng_hi, rng_lo, gate_long, gate_short,
                      last_bar, fade_bars, eod_cutoff, struct_buf, direction):
    pos = 0
    entry_px = 0.0
    entry_bar = -1
    side = 0
    stop_px = None
    fade_cnt = 0
    pending = None
    trade_log = []  # (entry_bar, exit_bar, pnl_pts, side, entry_px, exit_px, reason)

    def _book(exit_i, px, sd, ep, eb, reason):
        p = (px - ep) if sd > 0 else (ep - px)
        trade_log.append((int(eb), int(exit_i), float(p), int(sd), float(ep), float(px), reason))

    for u in range(warm, n):
        eod = u == last_bar[u]

        if pending is not None:
            kind = pending[0]
            if kind == "exit":
                if pos != 0:
                    _book(u, o[u], pos, entry_px, entry_bar, "fade")
                    pos = 0
                    stop_px = None
                pending = None
            else:  # "mkt"
                if pos == 0:
                    side = pending[1]
                    rh, rl = pending[2], pending[3]
                    pos = side
                    entry_px = o[u]
                    entry_bar = u
                    fade_cnt = 0
                    stop_px = (rl - struct_buf) if side > 0 else (rh + struct_buf)
                    if stop_px is not None and ((side > 0 and l[u] <= stop_px) or
                                                 (side < 0 and h[u] >= stop_px)):
                        _book(u, stop_px, pos, entry_px, entry_bar, "stop")
                        pos = 0
                        stop_px = None
                pending = None

        if pos != 0 and u > entry_bar and stop_px is not None:
            if (pos > 0 and l[u] <= stop_px) or (pos < 0 and h[u] >= stop_px):
                px = min(o[u], stop_px) if pos > 0 else max(o[u], stop_px)
                _book(u, px, pos, entry_px, entry_bar, "stop")
                pos = 0
                stop_px = None

        if eod:
            if pos != 0:
                _book(u, c[u], pos, entry_px, entry_bar, "close")
                pos = 0
                stop_px = None
            pending = None
            continue

        m, m1 = mom[u], mom[u - 1]
        if not (np.isfinite(m) and np.isfinite(m1)):
            continue

        if pos != 0:
            fading = (m < m1) if pos > 0 else (m > m1)
            fade_cnt = fade_cnt + 1 if fading else 0
            if fade_cnt >= fade_bars:
                pending = ("exit",)
                continue

        if pos == 0 and pending is None and fire[u] and m != 0:
            sd = 1 if m > 0 else -1
            if direction == "long" and sd < 0:
                continue
            if direction == "short" and sd > 0:
                continue
            if sd > 0 and not gate_long[u]:
                continue
            if sd < 0 and not gate_short[u]:
                continue
            if last_bar[u] - u <= eod_cutoff:
                continue
            pending = ("mkt", sd, rng_hi[u], rng_lo[u])

    return trade_log


def stats_slice(usd, yrs=None):
    if len(usd) == 0:
        return dict(n=0, net=0.0, pf=float("nan"), dd=0.0, mar=float("nan"))
    gw, gl = usd[usd > 0].sum(), -usd[usd < 0].sum()
    cum = np.concatenate([[0.0], np.cumsum(usd)])
    dd = -float((cum - np.maximum.accumulate(cum)).min())
    pf = float(gw / gl) if gl > 1e-9 else 99.0
    net = float(usd.sum())
    mar = (net / yrs) / dd if (yrs and dd > 1e-9) else float("nan")
    return dict(n=len(usd), net=net, pf=pf, dd=dd, mar=mar)


def main():
    os.chdir(ROOT)
    sys.path.insert(0, ROOT)

    r6 = _mod(os.path.join(ROOT, "tools", "ttmsqz_round6_parts.py"), "r16a_r6")
    COST, MULT, YRS = r6.COST["ES"], r6.MULT["ES"], 16.06

    df = r6.load("ES", "30m", "RTH")
    o = np.asarray(df["open"].values, float)
    h = np.asarray(df["high"].values, float)
    l = np.asarray(df["low"].values, float)
    c = np.asarray(df["close"].values, float)
    did = np.asarray(df["day_id"].values)
    idx = df["_dt"]

    A = dict(opens=o, highs=h, lows=l, closes=c, day_id=did, index=idx)

    # THE BASE - loaded through its OWN private spec, never the shared module cache, so rebinding
    # its frozen fade_bars cannot reach any other leg (SS20, SSF2, SSO...) even if they are loaded
    # elsewhere in the same process.
    base_path = os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0_ES30SSOF2.py")
    mod = _mod(base_path, "r16a_ssof2")
    ss = mod._so._ss          # the structural-stop engine module, private to this driver
    t3 = ss._t3               # the base TTM engine (squeeze_indicators, _htf_gate, _session_last_bar)

    KW = {k: v["default"] for k, v in mod.DEFAULT_PARAMS.items()}   # kc_mult 1.5, eod_cutoff 1
    GATE_LEN = mod._so._GATE_LEN                                     # forced to 20 internally
    STRUCT_BUF = ss._STRUCT_BUF                                      # 0.0, frozen
    DIRECTION = ss._FROZEN["direction"]                              # "both"

    NO_FADE = 9999   # sentinel far above any possible in-session fade streak (RTH session <= 13 bars)

    def set_fade(fb):
        ss._FROZEN = dict(ss._FROZEN, fade_bars=fb)

    L = []

    def emit(x=""):
        L.append(x)
        print(x, flush=True)

    emit("TTM SQUEEZE r16a - the fade-exit DOSE-RESPONSE curve")
    emit("base = the combined book leg (structural stop + deep-squeeze tilt + open-bar tilt), "
         "augur_strategies/TTMSQZ_3_0_ES30SSOF2.py, ES 30m RTH")
    emit("window %s..%s, lockbox from %s, 0.363 pts a round trip, 50 dollars a point, %.2f years"
         % (r6.DATE_FROM, r6.DATE_TO, r6.LB_FROM, YRS))
    emit("crown cell held: kc_mult %.2f, eod_cutoff %d, gate_len %d (forced internally by SSO/SSOF2)"
         % (KW["kc_mult"], KW["eod_cutoff"], GATE_LEN))
    emit("")
    emit("exit_mode is DEAD in this engine: TTMSQZ_3_0_ES30SS.py's _simulate never reads it - it is a")
    emit("vestigial key in _FROZEN, carried but unused. The only exit lever besides the structural stop")
    emit("and the session close is fade_bars. So the limit case 'no fade exit, hold to the close' is")
    emit("realised exactly (not approximated) as fade_bars -> a sentinel (%d) no in-session fade streak" % NO_FADE)
    emit("can ever reach (RTH sessions run <= 13 bars); the exit-mix columns below confirm zero fade")
    emit("exits under that sentinel before any number from that row is trusted.")
    emit("")

    def load_arrays():
        return ss._build_arrays(o, h, l, c, did, idx, KW["kc_mult"], GATE_LEN)

    def cell(fb_value):
        """Run one sweep cell: the real (priced) trades via the module's own run_backtest, plus a
        shadow tagged simulation for the exit-reason breakdown, cross-checked against each other."""
        set_fade(fb_value)
        r = mod.run_backtest(return_trades=True, **A, **KW)
        real_trades = r["trades"] if (r and r.get("trades")) else []

        arrs = load_arrays()
        raw = _simulate_tagged(o, h, l, c, arrs["n"], arrs["warm"], arrs["mom"], arrs["atr"],
                                arrs["fire"], arrs["rng_hi"], arrs["rng_lo"], arrs["gate_long"],
                                arrs["gate_short"], arrs["last_bar"], fb_value, KW["eod_cutoff"],
                                STRUCT_BUF, DIRECTION)
        reason_by_eb = {t[0]: t[6] for t in raw}

        real_ebs = sorted(int(t[0]) for t in real_trades)
        raw_ebs = sorted(reason_by_eb.keys())
        if real_ebs != raw_ebs:
            raise RuntimeError(
                "fade_bars=%r: shadow simulation disagrees with the priced engine on WHICH trades "
                "fire (real %d, shadow %d) - harness bug, not a finding." % (
                    fb_value, len(real_ebs), len(raw_ebs)))

        t = pd.DataFrame([(int(x[0]), int(x[1]), float(x[2])) for x in real_trades],
                          columns=["eb", "xb", "pts"])
        t["reason"] = t["eb"].map(reason_by_eb)
        usd = (t["pts"].values - COST) * MULT
        dates = pd.DatetimeIndex(idx)[t["xb"].values]
        lb = np.asarray(dates >= pd.Timestamp(r6.LB_FROM, tz="US/Eastern"))

        whole = stats_slice(usd, YRS)
        lockbox = stats_slice(usd[lb], YRS)

        pre = np.flatnonzero(~lb)
        if len(pre):
            cut = pre[int(len(pre) * 0.6)]
            disc_mask = np.zeros(len(t), bool)
            disc_mask[pre[pre < cut]] = True
            hold_mask = np.zeros(len(t), bool)
            hold_mask[pre[pre >= cut]] = True
        else:
            disc_mask = np.zeros(len(t), bool)
            hold_mask = np.zeros(len(t), bool)
        discovery = stats_slice(usd[disc_mask], YRS)
        holdout = stats_slice(usd[hold_mask], YRS)

        mix = t["reason"].value_counts().to_dict()
        exit_mix = dict(fade=int(mix.get("fade", 0)), stop=int(mix.get("stop", 0)),
                         close=int(mix.get("close", 0)))
        assert exit_mix["fade"] + exit_mix["stop"] + exit_mix["close"] == len(t), \
            "fade_bars=%r: exit-reason counts do not sum to the trade count - harness bug" % (fb_value,)

        return dict(whole=whole, lockbox=lockbox, discovery=discovery, holdout=holdout,
                    exit_mix=exit_mix, n=len(t))

    # ============================= MANDATORY PARITY GATE =============================
    emit("=" * 100)
    emit("PARITY GATE - fade_bars 1 and 2 must reproduce runs #368 and #369 to the dollar before any")
    emit("other number in this log is trusted.")
    emit("=" * 100)

    PARITY = {
        1: dict(n=357, net=136043, pf=3.28, dd=5330, mar=1.589, lb_net=22321, lb_pf=8.52, lb_dd=2003),
        2: dict(n=354, net=135884, pf=3.12, dd=4634, mar=1.826, lb_net=22739, lb_pf=9.89, lb_dd=1978),
    }
    parity_cells = {}
    parity_ok = True
    for fb in (1, 2):
        res = cell(fb)
        parity_cells[fb] = res
        w, lb = res["whole"], res["lockbox"]
        want = PARITY[fb]
        checks = [
            ("n", res["n"], want["n"], 0),
            ("net $", w["net"], want["net"], 1.0),
            ("PF", w["pf"], want["pf"], 0.01),
            ("whole-run DD $", w["dd"], want["dd"], 1.0),
            ("MAR", w["mar"], want["mar"], 0.002),
            ("lockbox net $", lb["net"], want["lb_net"], 1.0),
            ("lockbox PF", lb["pf"], want["lb_pf"], 0.01),
            ("lockbox DD $", lb["dd"], want["lb_dd"], 1.0),
        ]
        emit("")
        emit("fade_bars=%d  (run #%s)" % (fb, "368" if fb == 1 else "369"))
        for name, got, ref, tol in checks:
            ok = abs(got - ref) <= tol
            parity_ok = parity_ok and ok
            emit("  %-16s got %10s   published %10s   %s" % (
                name, ("%.3f" % got if isinstance(got, float) else got),
                ("%.3f" % ref if isinstance(ref, float) else ref),
                "OK" if ok else "MISMATCH"))
    emit("")
    if not parity_ok:
        emit("PARITY GATE FAILED - harness numbers below the gate would not be trustworthy. Stopping.")
        out = os.path.join(ROOT, "tools", "data", "ttmsqz_r16a_fade_dose.txt")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("\n".join(L) + "\n")
        raise SystemExit(1)
    emit("PARITY GATE PASSED. Continuing to the dose-response sweep.")
    emit("")

    # ================================ THE SWEEP =================================
    SWEEP = [1, 2, 3, 4, 6, "limit"]
    results = {}
    for fb in SWEEP:
        fb_value = NO_FADE if fb == "limit" else fb
        results[fb] = parity_cells[fb] if fb in parity_cells else cell(fb_value)

    def lbl(fb):
        return "no fade / hold to close" if fb == "limit" else ("fade after %d" % fb)

    emit("=" * 100)
    emit("WHOLE-RUN AND LOCKBOX, the metrics this family judges on")
    emit("=" * 100)
    emit("%-26s %4s %6s %10s %8s %6s | %10s %6s %8s" % (
        "fade rule", "n", "PF", "net $", "DD $", "MAR", "LB net $", "LB PF", "LB DD $"))
    for fb in SWEEP:
        res = results[fb]
        w, lb = res["whole"], res["lockbox"]
        emit("%-26s %4d %6.2f %10s %8s %6.3f | %10s %6.2f %8s" % (
            lbl(fb), res["n"], w["pf"], "{:,.0f}".format(w["net"]), "{:,.0f}".format(w["dd"]),
            w["mar"], "{:,.0f}".format(lb["net"]), min(lb["pf"], 99), "{:,.0f}".format(lb["dd"])))

    emit("")
    emit("=" * 100)
    emit("DISCOVERY / HOLDOUT / LOCKBOX split (pre-lockbox trades split 60/40 by time)")
    emit("=" * 100)
    H = ("%-26s %s" % ("", "-------- discovery --------   -------- holdout --------   -------- lockbox --------"))
    emit(H)
    emit("%-26s %4s %6s %10s %8s   %4s %6s %10s %8s   %4s %6s %10s %8s" % (
        "fade rule", "n", "PF", "net $", "DD $", "n", "PF", "net $", "DD $", "n", "PF", "net $", "DD $"))
    for fb in SWEEP:
        res = results[fb]
        d, hld, lb = res["discovery"], res["holdout"], res["lockbox"]
        emit("%-26s %4d %6.2f %10s %8s   %4d %6.2f %10s %8s   %4d %6.2f %10s %8s" % (
            lbl(fb), d["n"], min(d["pf"], 99), "{:,.0f}".format(d["net"]), "{:,.0f}".format(d["dd"]),
            hld["n"], min(hld["pf"], 99), "{:,.0f}".format(hld["net"]), "{:,.0f}".format(hld["dd"]),
            lb["n"], min(lb["pf"], 99), "{:,.0f}".format(lb["net"]), "{:,.0f}".format(lb["dd"])))

    emit("")
    emit("=" * 100)
    emit("EXIT MIX (whole run) - how each trade actually left")
    emit("=" * 100)
    emit("%-26s %4s %8s %8s %8s" % ("fade rule", "n", "fade", "stopped", "held->close"))
    for fb in SWEEP:
        mix = results[fb]["exit_mix"]
        n = results[fb]["n"]
        emit("%-26s %4d %8d %8d %8d" % (lbl(fb), n, mix["fade"], mix["stop"], mix["close"]))
        if fb == "limit" and mix["fade"] != 0:
            emit("  *** sentinel fade_bars=%d still produced %d fade exits - the limit case is NOT "
                 "clean, investigate before trusting this row ***" % (NO_FADE, mix["fade"]))

    # ================================ VERDICT =================================
    emit("")
    emit("=" * 100)
    emit("VERDICT - does any cell beat fade_bars=2 (the incumbent, run #364/#369) on BOTH annualised")
    emit("MAR and lockbox net, at a lockbox drawdown no worse?")
    emit("=" * 100)
    incumbent = results[2]
    inc_w, inc_lb = incumbent["whole"], incumbent["lockbox"]
    emit("incumbent (fade after 2): MAR %.3f, lockbox net $%s, lockbox DD $%s" % (
        inc_w["mar"], "{:,.0f}".format(inc_lb["net"]), "{:,.0f}".format(inc_lb["dd"])))
    any_beats = False
    for fb in SWEEP:
        if fb == 2:
            continue
        res = results[fb]
        w, lb = res["whole"], res["lockbox"]
        beats_mar = w["mar"] > inc_w["mar"]
        beats_lbnet = lb["net"] > inc_lb["net"]
        no_worse_dd = lb["dd"] <= inc_lb["dd"] + 1e-6
        beats = beats_mar and beats_lbnet and no_worse_dd
        any_beats = any_beats or beats
        emit("  %-26s MAR %s%.3f  lockbox net %s$%s  lockbox DD %s$%s  -> %s" % (
            lbl(fb), "+" if beats_mar else " ", w["mar"],
            "+" if beats_lbnet else " ", "{:,.0f}".format(lb["net"]),
            "<=" if no_worse_dd else "> ", "{:,.0f}".format(lb["dd"]),
            "BEATS incumbent on all three" if beats else "does not clear all three"))
    emit("")
    if any_beats:
        emit("At least one cell clears MAR, lockbox net and lockbox drawdown against fade-after-2 - see")
        emit("above for which. That is a scan result, not a validation; nothing here is crowned or")
        emit("queued.")
    else:
        emit("No cell clears all three against fade-after-2. On this reading, fade-after-2 remains the")
        emit("peak of the cells swept here; nothing to do.")

    out = os.path.join(ROOT, "tools", "data", "ttmsqz_r16a_fade_dose.txt")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("\nlog -> tools/data/ttmsqz_r16a_fade_dose.txt")


if __name__ == "__main__":
    main()
