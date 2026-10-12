"""tests/_keel_live_world.py -- a small synthetic world for the LIVE KEEL tests (owner call 10-12,
MANAGER #143): api/cloud_signal's live scorer and entry records, api/qqq_exec's close hook,
tools/keel_intraday.py's handler, tools/keel_live_state.py's drift check.

Not a test module (no test_ prefix): the test files import LiveWorld from here.

LiveWorld(root) writes, all under `root` (never the real EDGELOG_HOME):
  * an NQ 5m RTH master (<root>/nq/NOADJ_NQ_5m_RTH.csv) and a QQQ 5m cache (<home>/ohlc/QQQ_5m.csv)
    over the same full sessions (Jan-Feb 2024: no half day);
  * the NIGHTLY reference: keel_build_state on the NQ arrays through `nightly_day` (the third-last
    session) and non-overlapping synthetic NQ trades, installed under NOISE_382's keel_paths with
    its summary (built_at, data_through, n_trades);
  * LIVE trades on the QQQ arrays of the last two sessions (`live_trades`, entry / exit bars,
    shares, pnl, the plugin size), one same-bar reversal among them.
"""
import csv
import datetime as _dt
import json
import os
import sys

import numpy as np
import pandas as pd

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import cloud_signal as cs  # noqa: E402
from api import market_calendar as mc  # noqa: E402
from augur_engine import ml_keel as K  # noqa: E402
import tools.keel_intraday as KI  # noqa: E402
import tools.keel_live_state as L  # noqa: E402

LEG = "NOISE_382"
VERSION = "v12"                 # the file names (CROWN_LEGS' version)
BARS = 78
QUIET = lambda *a, **k: None  # noqa: E731
BUILT_AT = "2024-02-01T23:30:00+00:00"
TS_FMT = "%Y-%m-%d %H:%M:%S"

# v12 with its trust lines moved into reach (trust = (t + 3) / 6, fast cut likewise), so on a short
# synthetic history the learned part already leans and every new ledger trade moves the size. On the
# real v12 lines a short world stays in its fixed-tilt-only stretch, where any ledger gives the same
# size and a test could not tell one ledger from another. The state carries its own cfg.
TRUSTING = "v12_trusting_test"
TRUSTING_CFG = dict(K.CFG["v12"], t_lo=-3.0, t_hi=3.0, fast={"W": 50, "lo": -3.0, "hi": 3.0})


def full_sessions(start, n):
    d = _dt.date.fromisoformat(start)
    out = []
    while len(out) < n:
        if mc.is_session(d):
            assert mc.session_close_et(d) == "16:00", "the synthetic range must hold no half day"
            out.append(d)
        d += _dt.timedelta(days=1)
    return out


def price_frame(days, seed, p0, step, tick):
    rng = np.random.RandomState(seed)
    q = lambda x: round(x / tick) * tick  # noqa: E731
    rows, price = [], p0
    for d in days:
        t0 = pd.Timestamp(f"{d.isoformat()} 09:30", tz="US/Eastern")
        vol = rng.uniform(0.6, 1.6)
        for b in range(BARS):
            ts = t0 + pd.Timedelta(minutes=5 * b)
            o = q(price)
            c = q(o + rng.normal(0, step * vol))
            h = q(max(o, c) + abs(rng.normal(0, step * vol / 3)))
            lo = q(min(o, c) - abs(rng.normal(0, step * vol / 3)))
            rows.append((int(ts.timestamp()), o, h, lo, c, int(rng.randint(100, 5000))))
            price = c
        price += rng.normal(0, step * 2)
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])


def nq_trades(arrays, seed=11):
    """Non-overlapping trades inside each session (entry bar, exit bar, pnl in points)."""
    rng = np.random.RandomState(seed)
    day_id = np.asarray(arrays["day_id"])
    out = []
    for d in np.unique(day_id):
        bars = np.flatnonzero(day_id == d)
        first, last = int(bars[0]), int(bars[-1])
        pos = first + int(rng.randint(1, 6))
        while pos < last - 1:
            x = min(pos + int(rng.randint(1, 16)), last)
            win = rng.rand() < 0.38
            pnl = float(rng.gamma(2.0, 15.0)) if win else -float(rng.gamma(2.0, 8.0))
            out.append((pos, x, round(pnl, 3)))
            pos = x + int(rng.randint(1, 9))
    return out


def csv_closes(path):
    """{epoch: close} read with the csv module (exact float text, like the handler)."""
    out = {}
    with open(path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            out[int(float(r["time"]))] = float(r["close"])
    return out


class LiveWorld:
    def __init__(self, root, n_days=24, version=VERSION, seed=7):
        self.root = str(root)
        self.home = os.path.join(self.root, "home")
        self.days = full_sessions("2024-01-02", n_days)
        self.version = version
        # -- price files ------------------------------------------------------------------------
        self.nq_master = os.path.join(self.root, "nq", KI.MASTER_NAME)
        os.makedirs(os.path.dirname(self.nq_master), exist_ok=True)
        price_frame(self.days, seed, 15000.0, 6.0, 0.25).to_csv(self.nq_master, index=False)
        self.cs_paths = cs._paths(home=self.home)
        os.makedirs(self.cs_paths["ohlc_dir"], exist_ok=True)
        self.qqq_csv = cs._cache_path("5m", self.cs_paths)
        price_frame(self.days, seed + 2, 400.0, 0.16, 0.01).to_csv(self.qqq_csv, index=False)
        self.nq_arrays, _ = L.load_nq_arrays(self.nq_master, drop_incomplete=False, log=QUIET)
        self.q_arrays, _ = L.load_nq_arrays(self.qqq_csv, drop_incomplete=False, log=QUIET)
        self.q_idx = pd.DatetimeIndex(self.q_arrays["index"])
        self.q_day = np.array([ts.date() for ts in self.q_idx])
        self.q_feats = K.keel_features(self.q_arrays)
        # -- the nightly reference --------------------------------------------------------------
        self.nightly_day = self.days[-3]
        self.live_days = self.days[-2:]
        arr, _ = L.load_nq_arrays(self.nq_master, date_to=str(self.nightly_day), log=QUIET)
        self.nightly = K.keel_build_state(arr, nq_trades(arr, seed + 4), version=version)
        self.files = KI.leg_files(self.home, LEG, VERSION)
        self.paths = KI.inbox_paths(self.home)
        os.makedirs(self.files["dir"], exist_ok=True)
        os.makedirs(self.paths["inbox"], exist_ok=True)
        self.install_nightly(self.nightly)
        self.live_trades = self._make_live_trades(seed + 9)

    def clone(self, dst):
        """A copy of this world's files under `dst` (a fresh dir per test, the slow build once)."""
        import copy
        import shutil
        shutil.copytree(self.root, str(dst))
        w = copy.copy(self)
        w.root = str(dst)
        w.home = os.path.join(w.root, "home")
        w.nq_master = os.path.join(w.root, "nq", KI.MASTER_NAME)
        w.cs_paths = cs._paths(home=w.home)
        w.qqq_csv = cs._cache_path("5m", w.cs_paths)
        w.files = KI.leg_files(w.home, LEG, VERSION)
        w.paths = KI.inbox_paths(w.home)
        w.live_trades = [dict(t) for t in self.live_trades]
        cs._KEEL_STATE_CACHE.clear()
        return w

    # -- nightly ---------------------------------------------------------------------------------
    def install_nightly(self, state, through=None, built_at=BUILT_AT):
        import joblib
        joblib.dump(state, self.files["state_path"])
        summary = {"leg": LEG, "version": state["version"], "n_trades": int(state["n"]),
                   "built_at": built_at, "data_through": str(through or self.nightly_day),
                   "last_nq_session": str(through or self.nightly_day),
                   "feature_names": list(state["feature_names"])}
        with open(self.files["summary_path"], "w", encoding="utf-8") as f:
            json.dump(summary, f)
        return summary

    # -- live trades -------------------------------------------------------------------------------
    def _make_live_trades(self, seed):
        """Non-overlapping QQQ trades on the live days; trade 1 of day 1 is a same-bar REVERSAL
        (it enters on the bar trade 0 exits)."""
        rng = np.random.RandomState(seed)
        out = []
        for di, d in enumerate(self.live_days):
            bars = np.flatnonzero(self.q_day == d)
            first, last = int(bars[0]), int(bars[-1])
            pos = first + 3
            k = 0
            while pos < last - 6 and k < 4:
                x = min(pos + int(rng.randint(2, 9)), last)
                plugin = 2.0 if rng.rand() < 0.5 else 1.0
                out.append({"e": pos, "x": x, "plugin": plugin, "shares": int(rng.randint(8, 40)),
                            "side": "long" if rng.rand() < 0.6 else "short",
                            "reversal": bool(out and di == 0 and k == 1)})
                k += 1
                pos = x if (di == 0 and k == 1) else x + int(rng.randint(2, 6))
        for i, t in enumerate(out):
            t["k"] = i
            t["entry_time"] = self.q_idx[t["e"]]
            t["trade_id"] = f"{LEG}-{t['entry_time'].tz_convert('UTC').strftime('%Y%m%dT%H%M%SZ')}-" \
                            f"{'L' if t['side'] == 'long' else 'S'}"
            t["entry_px"] = float(self.q_arrays["open"][t["e"]])
            t["exit_px"] = float(self.q_arrays["open"][t["x"]])
            # the executor's wall-clock stamps: two seconds into the fill bar
            t["entry_ts"] = (self.q_idx[t["e"]] + pd.Timedelta(seconds=2)).strftime(TS_FMT)
            t["exit_ts"] = (self.q_idx[t["x"]] + pd.Timedelta(seconds=2)).strftime(TS_FMT)
        for a, b in zip(out, out[1:]):
            if b["reversal"]:
                assert b["e"] == a["x"]
                b["entry_ts"] = a["exit_ts"]          # one executor tick: close, then open
        return out

    def keel_cfg(self, version=None):
        return dict(version=version or self.version, **cs.keel_paths(LEG, VERSION, home=self.home))

    def x_row(self, e):
        return self.q_feats[0][e:e + 1]

    def xrow_record(self, t, keel_size, state_source="live", state_n=None):
        """The entry record api/cloud_signal writes for live trade `t` sized `keel_size`."""
        trade = {"entry_time": t["entry_time"].isoformat(), "entry_bar": t["e"], "side": t["side"]}
        rec = cs._keel_xrow_record(LEG, t["trade_id"], trade, self.q_arrays, self.keel_cfg(),
                                   keel_size, {"z": 0.0}, t["plugin"], t["plugin"] * keel_size,
                                   {"state_source": state_source, "ledger_n": state_n,
                                    "feats": self.q_feats})
        assert rec is not None
        return rec

    def write_xrow(self, rec):
        return cs._append_keel_xrow(self.files["xrows_path"], rec)

    def inbox_trade(self, t, pnl_usd=None, **over):
        pnl = pnl_usd if pnl_usd is not None else round(
            (t["exit_px"] - t["entry_px"]) * (1 if t["side"] == "long" else -1) * t["shares"], 2)
        tr = {"leg": LEG, "trade_id": t["trade_id"], "entry_ts": t["entry_ts"],
              "exit_ts": t["exit_ts"], "side": t["side"], "shares": t["shares"], "pnl_usd": pnl,
              "entry_px": t["entry_px"], "exit_px": t["exit_px"], "pnl_source": "book"}
        tr.update(over)
        return tr

    def drop(self, tr, name=None):
        path = os.path.join(self.paths["inbox"], name or f"{tr['trade_id']}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(tr, f)
        return path

    def run(self, **kw):
        """The handler on this world; the CUT is this world's own (live trades from its first live
        day, a nightly through the session before it -- KI.LIVE_FROM_DAY is the box's 2026 date)."""
        kw.setdefault("live_from", str(self.live_days[0]))
        return KI.process_inbox(self.home, self.nq_master, LEG, log=QUIET, **kw)

    def inbox(self):
        return sorted(os.listdir(self.paths["inbox"]))

    def load(self, key):
        import joblib
        p = self.files[key]
        return joblib.load(p) if os.path.exists(p) else None

    def ack(self):
        with open(self.files["live_ack_path"], encoding="utf-8") as f:
            return json.load(f)

    # -- the ratio, computed here independently of the handler -----------------------------------
    def ratio_for(self, entry_day):
        prior = KI._sessions_before(entry_day, 1)[0]
        nq, qq = csv_closes(self.nq_master), csv_closes(self.qqq_csv)
        hh, mm = (int(x) for x in mc.session_close_et(prior).split(":"))
        last = int(pd.Timestamp(f"{prior.isoformat()} {hh:02d}:{mm:02d}",
                                tz="US/Eastern").timestamp()) - 300
        return nq[last] / qq[last]
