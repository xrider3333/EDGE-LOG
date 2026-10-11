r"""PIN (2026-10-11, MANAGER #96 -- item 8 of Custom ML's
C:\EdgeLog\manager\KEEL_LIVE_VS_BACKTEST_2026-10-11.md: "a SEED position is never KEEL-scored").

No live effect, so no fix -- this pins why. A LIVE (order-placing) NOISE_382 leg that cold-starts
while its strategy holds a trade ABSORBS it (api/cloud_signal._diff_leg's COLD START: the
record is exit_emitted, no ENTRY now and no EXIT later -- an executor that never entered cannot
exit), so there is nothing to size. A process RESTART is not a cold start: leg_state (with the
ENTRY's size and keel_size) is reloaded from state.json, and the EXIT reuses those values -- KEEL
is never scored a second time. The executor closes a lot's OWN shares (api/qqq_exec._reduce_lot
via lot["nq_qty_total"]), never the EXIT row's size.
"""
import json
import os
import sys

import pandas as pd

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
for p in (ROOT, THIS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import api.cloud_signal as cs  # noqa: E402
from test_cloud_signal_keel import _arrays  # noqa: E402

QUIET = lambda *a, **k: None  # noqa: E731
KEEL = {"version": "v12", "state_path": "never-read.joblib"}


def _trade(arrays, bar, exit_bar=None, size=2.0):
    t = {"entry_time": pd.Timestamp(arrays["index"][bar]).isoformat(), "side": "long",
         "entry_px": 700.0, "shares": 1, "still_open": exit_bar is None, "exit_time": None,
         "exit_px": None, "entry_bar": bar, "size": size}
    if exit_bar is not None:
        t.update(exit_time=pd.Timestamp(arrays["index"][exit_bar]).isoformat(), exit_px=701.0)
    return t


def _never_scored(*a, **k):
    raise AssertionError("KEEL must not be scored here")


def test_a_live_seed_absorbs_the_open_trade_and_a_restart_keeps_the_entrys_keel_size(monkeypatch):
    arrays = _arrays()
    idx = arrays["index"]
    cfg = {"keel": KEEL}                     # a LIVE leg: no "shadow" key
    leg_state = {"trades": {}}

    # 1. cold start while trade A is open: SEED only, KEEL never scored, nothing owed downstream
    monkeypatch.setattr(cs, "_keel_size_for_entry", _never_scored)
    ev = cs._diff_leg("NOISE_382", [_trade(arrays, 10)], leg_state, idx[12], cfg=cfg,
                      arrays=arrays, fetch=False, log=QUIET)
    assert [(e["event"], e["keel_size"], e["size"]) for e in ev] == [("SEED", "", "")]
    (rec,) = leg_state["trades"].values()
    assert rec["exit_emitted"] is True and rec.get("seeded") and "keel_size" not in rec
    # ... and when A closes, no EXIT either (the executor never held it)
    ev = cs._diff_leg("NOISE_382", [_trade(arrays, 10, exit_bar=18)], leg_state, idx[20],
                      cfg=cfg, arrays=arrays, fetch=False, log=QUIET)
    assert ev == []

    # 2. a NEW trade B is scored ONCE, at its ENTRY
    monkeypatch.setattr(cs, "_keel_size_for_entry",
                        lambda *a, **k: (1.37, {"z": 0.4, "trust": 0.5, "nd": 900}))
    trades = [_trade(arrays, 10, exit_bar=18), _trade(arrays, 30)]
    (entry,) = cs._diff_leg("NOISE_382", trades, leg_state, idx[31], cfg=cfg, arrays=arrays,
                            fetch=False, log=QUIET)
    assert (entry["event"], entry["keel_size"], entry["size"]) == ("ENTRY", 1.37, 2.0 * 1.37)

    # 3. RESTART mid-trade: state.json round trip, the scorer would now say something else --
    #    the EXIT carries the ENTRY's own size / keel_size and never re-scores
    leg_state = json.loads(json.dumps(leg_state))
    monkeypatch.setattr(cs, "_keel_size_for_entry", _never_scored)
    trades = [_trade(arrays, 10, exit_bar=18), _trade(arrays, 30, exit_bar=40)]
    (exit_,) = cs._diff_leg("NOISE_382", trades, leg_state, idx[41], cfg=cfg, arrays=arrays,
                            fetch=False, log=QUIET)
    assert (exit_["event"], exit_["trade_id"]) == ("EXIT", entry["trade_id"])
    assert (exit_["keel_size"], exit_["size"]) == (entry["keel_size"], entry["size"])
