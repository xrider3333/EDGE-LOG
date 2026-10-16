"""TTM QL_GAMMA_ORB (idea 20261015-1301-shelf30) - STAGE 2 supplementary look-ahead probe (complements ttm_trace's
within-session flatten probe). For EVERY arm-A trade (signal bar k = entry-1, fill bar e):
  P1 (cross-session): cut the arrays at the end of the trade's session -> the trade must be identical (entry, exit, side,
     entry px, pts): nothing after the session is read.
  P2 (at the signal): keep bars <= k real, keep only bar e's OPEN, replace bar e's high/low/close and every later bar of the
     session with seeded noise, cut after the session -> the entry (bar, side, price) must be identical: the signal and the
     fill read nothing past bar k except the fill open.
  P3 (stop): the stop the plugin uses must equal entry - side*0.5*range where range uses only the session's first 6 bars
     (checked from the realised stop-outs: every stop exit not at a gap open books exactly that level).
Runs the plugin's own run_backtest directly (same function the engine calls). Writes ttm_lookahead_probe.json here only."""
import hashlib
import importlib.util
import json
import os
import types

import numpy as np

HERE = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261015-1301-shelf30"
spec = importlib.util.spec_from_file_location("v", HERE + "/ttm_verify_20261015-1301-shelf30.py")
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)              # sets AUGUR_TRIAL_CACHE=0 before augur_engine is imported
assert os.environ.get("AUGUR_TRIAL_CACHE") == "0"


def main():
    row, A, idxn, days, o, h, l, c, day_id = V.load()
    assert V.lf_sha(V.PLUGIN) == V.PIN_PREREG_FULL, "plugin pin"
    m = types.ModuleType("ttm_probe_gamma_orb")
    m.__file__ = V.PLUGIN
    exec(compile(open(V.PLUGIN, encoding="utf-8").read(), V.PLUGIN, "exec"), m.__dict__)
    r = V.run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in r["trades"]]
    assert V.trades_sha(Ta) == "d5d59e7e36c2456a85c3294bbff31a5200b0b4deaa203dc3e29058e63e74a5a7", "arm A = stage 1"
    # the plugin called directly on the raw arrays must give arm A (the engine's difference-adjusted signals change nothing)
    rd = m.run_backtest(o, h, l, c, None, day_id=day_id, return_trades=True)
    Td = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in rd["trades"]]
    direct_eq = Td == Ta
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], len(c)]
    rng = np.random.default_rng(20261016)
    p1_ok = p2_ok = p3_ok = p3_n = 0
    p1_bad, p2_bad, p3_bad = [], [], []
    for t in Ta:
        e = t[0]
        si = int(np.searchsorted(starts, e, side="right") - 1)
        s_, e_ = int(starts[si]), int(ends[si])
        # P1
        r1 = m.run_backtest(o[:e_], h[:e_], l[:e_], c[:e_], None, day_id=day_id[:e_], return_trades=True)
        last = r1["trades"][-1] if r1 and r1.get("trades") else None
        if last is not None and (int(last[0]), int(last[1]), int(last[3]), float(last[4]), float(last[2])) == t:
            p1_ok += 1
        else:
            p1_bad.append(str(idxn[e]))
        # P2
        o2, h2, l2, c2 = o[:e_].copy(), h[:e_].copy(), l[:e_].copy(), c[:e_].copy()
        nz = e_ - e
        walk = o[e] + np.cumsum(rng.normal(0.0, 8.0, nz))
        c2[e:e_] = walk
        o2[e + 1:e_] = walk[:-1]
        h2[e:e_] = np.maximum(np.r_[o[e], walk[:-1]], walk) + np.abs(rng.normal(0.0, 3.0, nz))
        l2[e:e_] = np.minimum(np.r_[o[e], walk[:-1]], walk) - np.abs(rng.normal(0.0, 3.0, nz))
        r2 = m.run_backtest(o2, h2, l2, c2, None, day_id=day_id[:e_], return_trades=True)
        last2 = r2["trades"][-1] if r2 and r2.get("trades") else None
        if last2 is not None and (int(last2[0]), int(last2[3]), float(last2[4])) == (t[0], t[2], t[3]):
            p2_ok += 1
        else:
            p2_bad.append(str(idxn[e]))
        # P3: realised stop level
        rg = float(h[s_:s_ + 6].max() - l[s_:s_ + 6].min())
        stop = t[3] - t[2] * 0.5 * rg
        xb = t[1]
        exit_px = t[3] + t[2] * t[4]
        if xb != e_ - 1 or abs(exit_px - float(c[e_ - 1])) > 1e-9:      # not the session-close exit -> a stop exit
            p3_n += 1
            gap = (o[xb] < stop) if t[2] > 0 else (o[xb] > stop)
            want = float(o[xb]) if gap else stop
            if abs(exit_px - want) < 1e-9:
                p3_ok += 1
            else:
                p3_bad.append(str(idxn[e]))
    res = {"plugin_lf_sha256": V.lf_sha(V.PLUGIN), "probe_src_lf_sha256": V.lf_sha(__file__), "A_trades": len(Ta),
           "plugin_direct_raw_arrays_eq_engine_arm_A": bool(direct_eq),
           "P1_cut_after_session_identical": {"ok": p1_ok, "bad": p1_bad[:10], "pass": p1_ok == len(Ta)},
           "P2_noise_after_signal_entry_identical": {"ok": p2_ok, "bad": p2_bad[:10], "pass": p2_ok == len(Ta)},
           "P3_stop_exits_book_formula_level_or_gap_open": {"stop_exits": p3_n, "ok": p3_ok, "bad": p3_bad[:10],
                                                            "pass": p3_ok == p3_n}}
    s = json.dumps(res, indent=1, sort_keys=True)
    b = (s + "\n").encode("utf-8")
    with open(HERE + "/ttm_lookahead_probe.json", "wb") as f:
        f.write(b)
    print(s)
    print("probe output sha256", hashlib.sha256(b).hexdigest())


if __name__ == "__main__":
    main()
