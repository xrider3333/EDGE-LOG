"""ENGU-Q <-> NOISE CROSS-FAMILY STATE FILTERS r1 - GATE G0 ONLY (the power screen).

Pre-registered in C:\\EdgeLog\\manager\\prereg\\PREREG_enguq_crossfamily_state_2026-11-03.md, whose
LF sha256 is pinned below and checked at start. This script computes G0 and NOTHING ELSE: how many
of each family's entries fall in each state of the other family, the gross-versus-cost reading per
cell, and the trades needed for 80% power at the measured per-trade difference. G0 can end the round
in either direction, and the number is published whichever way it falls.

It does not size, veto, re-time or re-price a single trade. No arm is run here.

    python tools/enguq_crossfamily_state_r1.py selftest    # no data, proves the rules
    python tools/enguq_crossfamily_state_r1.py             # G0
"""
import hashlib
import json
import os
import sys

PREREG = r"C:\EdgeLog\manager\prereg\PREREG_enguq_crossfamily_state_2026-11-03.md"
PREREG_SHA = "36510b301bfc0833db43dbe9d440347ad97dddbb294df5ba3e7a4ad9068ea39a"
REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
OUT = r"C:\EdgeLog\_anatomy_cache\enguq_crossfamily_r1"

# Both legs exactly as BOOK #463 carries them (api.book_shadow.BOOK463_LEGS).
ENGUQ = dict(strategy="ENGUQ_1M_ETH_R2_1_0.py", instrument="NQ", timeframe="1m",
             session="eth", source="db_adj_eth", cost_pts=0.783)
NOISE = dict(strategy="NOISE_1_8_CT304H.py", instrument="NQ", timeframe="5m",
             session="rth", source="db_noadj_rth", cost_pts=0.533)
WIN = ("2010-06-07", "2026-06-30")        # loaded; every READ below is walk-forward only
WF = ("2016-10-12", "2025-06-27")         # #335's own 8 folds (PREREG_enguq_executor_r1)
POINT_USD = 20.0

# A state is AVAILABLE only if the other family's own bar closed within this many minutes of the
# signal bar's close. One bar of the coarser tape (NOISE 5m) plus nothing. Outside regular hours the
# nearest closed NOISE bar can be hours old, and a stale state is not a state - it reads
# "unavailable", and an unavailable state means the signal is TAKEN UNCHANGED, never dropped.
MAX_STALE_MIN = 5.0


def lf_sha(path):
    return hashlib.sha256(open(path, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def check_prereg():
    got = lf_sha(PREREG)
    print("prereg %s\n  LF sha256 %s" % (PREREG, got))
    if got != PREREG_SHA:
        sys.exit("PREREG SHA MISMATCH - expected %s. The frozen document changed; stop and write an "
                 "addendum rather than running on a moved target." % PREREG_SHA)
    print("  matches the pinned sha")
    print("harness %s\n  LF sha256 %s" % (__file__, lf_sha(os.path.abspath(__file__))))


# ---------------------------------------------------------------- pure pieces (selftested)

def position_state(trades, n_bars, long_only):
    """State of a leg per BAR INDEX: 0 flat, +1 long, -1 short.

    A trade (entry_i, exit_i, ...) is held on bars entry_i .. exit_i inclusive. `long_only` asserts
    that every trade reads long, which is ENGU-Q's contract.
    """
    import numpy as np
    st = np.zeros(n_bars, dtype=np.int8)
    for t in trades:
        i0, i1 = int(t[0]), int(t[1])
        side = 1 if long_only else int(t[3])
        if long_only and len(t) > 3 and int(t[3]) != 1:
            raise AssertionError("long-only leg returned a short trade at bar %d" % i0)
        if side not in (1, -1):
            raise AssertionError("unreadable side %r at bar %d" % (side, i0))
        st[max(i0, 0):min(i1 + 1, n_bars)] = side
    return st


def state_at(signal_ts, other_ts, other_state, max_stale_min=MAX_STALE_MIN):
    """Read the other family's state on the last of ITS bars that CLOSED AT OR BEFORE this signal
    bar's close, and only if that bar is no more than `max_stale_min` minutes old.

    Returns 'flat' / 'long' / 'short' / 'unavailable'. Causal by construction: never a forming bar,
    never a bar that closes after the signal bar.
    """
    import numpy as np
    sig = np.asarray(signal_ts, dtype="datetime64[s]")
    oth = np.asarray(other_ts, dtype="datetime64[s]")
    k = np.searchsorted(oth, sig, side="right") - 1          # last bar with close <= signal close
    out = np.full(len(sig), "unavailable", dtype=object)
    ok = k >= 0
    if ok.any():
        age_min = (sig[ok] - oth[k[ok]]).astype("timedelta64[s]").astype(float) / 60.0
        fresh = age_min <= max_stale_min
        idx = np.flatnonzero(ok)[fresh]
        s = other_state[k[idx]]
        words = np.where(s > 0, "long", np.where(s < 0, "short", "flat"))
        out[idx] = words
    return out


def power_n(sd, delta, per_group=True):
    """Trades needed for 80% power at a two-sided 5% level on a per-trade difference `delta`
    (same units as `sd`). Two-sample: n per group = 15.7 sd^2 / delta^2. One-sample: 7.85.
    Returns None when delta is zero - an effect of exactly zero needs infinite trades, and saying
    so is more honest than printing a huge number.
    """
    if not delta:
        return None
    k = 15.7 if per_group else 7.85
    return int(round(k * (float(sd) ** 2) / (float(delta) ** 2)))


def selftest():
    import numpy as np
    # position_state: inclusive of the exit bar, sides read from the tuple
    st = position_state([(2, 4, 1.0, 1, 0.0), (7, 8, -1.0, -1, 0.0)], 10, long_only=False)
    assert list(st) == [0, 0, 1, 1, 1, 0, 0, -1, -1, 0], list(st)
    # a long-only leg must refuse a short
    try:
        position_state([(1, 2, 1.0, -1, 0.0)], 5, long_only=True)
        raise SystemExit("selftest FAILED: long-only leg accepted a short trade")
    except AssertionError:
        pass

    # state_at: the lag, the staleness rule and the unavailable word
    oth_ts = np.array(["2020-01-02T09:35", "2020-01-02T09:40", "2020-01-02T09:45"],
                      dtype="datetime64[s]")
    oth_st = np.array([0, 1, -1], dtype=np.int8)
    sig = np.array(["2020-01-02T09:40",   # the 09:40 bar has just closed -> its state, not 09:45's
                    "2020-01-02T09:44",   # 4 min after 09:40, still fresh
                    "2020-01-02T09:52",   # 7 min after 09:45 -> stale -> unavailable
                    "2020-01-02T03:00"],  # before the first bar -> unavailable
                   dtype="datetime64[s]")
    got = list(state_at(sig, oth_ts, oth_st))
    assert got == ["long", "long", "unavailable", "unavailable"], got
    # NEVER the forming bar: a signal at 09:44 must not see the 09:45 state (short)
    assert got[1] != "short"

    # power_n
    assert power_n(1.0, 0.5) == 63, power_n(1.0, 0.5)
    assert power_n(2.0, 0.5) == 251, power_n(2.0, 0.5)
    assert power_n(1.0, 0.0) is None
    print("selftest PASS - state lag, staleness, unavailable, long-only guard, power line")


# ---------------------------------------------------------------- G0

def leg_run(cfg, name):
    import numpy as np
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    from api.book_shadow import BOOK463_LEGS
    leg = [l for l in BOOK463_LEGS if l["strategy"] == cfg["strategy"]][0]
    m = find_master(cfg["instrument"], cfg["timeframe"], cfg["session"], cfg["source"])
    arr = load_master_arrays(m, date_from=WIN[0], date_to=WIN[1])
    res = run_backtest(cfg["strategy"], arrays=arr, params=leg["params"],
                       cost_pts=float(cfg["cost_pts"]), return_trades=True)
    tr = sorted(tuple(t) for t in res["trades"])
    ix = np.asarray(arr["index"], dtype="datetime64[s]")
    print("%-6s %-26s master %s rows %d bars %d trades %d"
          % (name, cfg["strategy"], m["filename"], m.get("rows", -1), len(ix), len(tr)))
    return arr, ix, tr, leg


def g0():
    import numpy as np
    sys.path.insert(0, REPO)
    os.chdir(REPO)
    os.makedirs(OUT, exist_ok=True)
    check_prereg()
    print()

    e_arr, e_ix, e_tr, _ = leg_run(ENGUQ, "ENGU-Q")
    n_arr, n_ix, n_tr, _ = leg_run(NOISE, "NOISE")
    e_state = position_state(e_tr, len(e_ix), long_only=True)
    n_state = position_state(n_tr, len(n_ix), long_only=False)

    wf0 = np.datetime64(WF[0] + "T00:00:00")
    wf1 = np.datetime64(WF[1] + "T23:59:59")
    rows = {}

    def screen(label, trades, sig_ix, other_ix, other_state, cost_pts):
        ent = np.array([int(t[0]) for t in trades])
        pnl = np.array([float(t[2]) for t in trades])
        ts = sig_ix[np.clip(ent, 0, len(sig_ix) - 1)]
        keep = (ts >= wf0) & (ts <= wf1)
        ts, pnl = ts[keep], pnl[keep]
        st = state_at(ts, other_ix, other_state)
        yrs = (np.datetime64(WF[1]) - np.datetime64(WF[0])).astype(float) / 365.25
        print("\n%s - %d walk-forward trades, %.2f years" % (label, len(ts), yrs))
        print("  %-13s %7s %8s %11s %11s %11s %9s" %
              ("state", "trades", "tr/yr", "net pts/tr", "gross/tr", "cost/tr", "power n"))
        out = []
        for s in ("flat", "long", "short", "unavailable"):
            sel = np.array([x == s for x in st])
            k = int(sel.sum())
            if not k:
                print("  %-13s %7d  (no trades)" % (s, 0))
                out.append({"state": s, "trades": 0})
                continue
            inn, outn = pnl[sel], pnl[~sel]
            net = float(inn.mean())
            gross = net + cost_pts
            delta = net - (float(outn.mean()) if len(outn) else 0.0)
            sd = float(np.std(np.concatenate([inn, outn]), ddof=1)) if len(outn) > 1 else float(np.std(inn, ddof=1))
            need = power_n(sd, delta)
            print("  %-13s %7d %8.1f %11.3f %11.3f %11.3f %9s"
                  % (s, k, k / yrs, net, gross, cost_pts,
                     "-" if need is None else format(need, ",d")))
            out.append({"state": s, "trades": k, "per_yr": k / yrs, "net_pts_tr": net,
                        "gross_pts_tr": gross, "cost_pts_tr": cost_pts, "delta_pts_tr": delta,
                        "sd": sd, "power_n_80": need,
                        "powered": bool(need is not None and k >= need),
                        "over_50_yr": bool(k / yrs >= 50.0)})
        rows[label] = out
        return out

    a = screen("A1 direction - NOISE state read at ENGU-Q entry bars", e_tr, e_ix, n_ix, n_state,
               float(ENGUQ["cost_pts"]))
    b = screen("A2/A3 direction - ENGU-Q state read at NOISE entry bars", n_tr, n_ix, e_ix, e_state,
               float(NOISE["cost_pts"]))

    print("\nG0 VERDICT, by the bar written in the prereg before this ran:")
    print("  a direction PASSES G0 only if some addressable state cell holds BOTH at least its own")
    print("  80%% power line AND at least 50 trades a year. Otherwise that direction closes at draft")
    print("  with one ledger row and no trial spent.")
    for label, out in (("A1 (NOISE state -> ENGU-Q size tilt)", a),
                       ("A2/A3 (ENGU-Q state -> NOISE veto / tilt)", b)):
        live = [r for r in out if r.get("trades") and r["state"] != "unavailable"
                and r.get("powered") and r.get("over_50_yr")]
        print("  %-42s %s" % (label, "PASS: " + ", ".join(r["state"] for r in live) if live
                              else "CLOSES AT DRAFT - no state cell is both powered and >= 50/yr"))

    p = os.path.join(OUT, "g0.json")
    json.dump({"rows": rows, "wf": list(WF), "window": list(WIN),
               "max_stale_min": MAX_STALE_MIN, "prereg_sha": PREREG_SHA},
              open(p, "w"), indent=1, default=str)
    print("\nwrote %s" % p)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        selftest()
    else:
        g0()
