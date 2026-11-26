"""NT-check chips (2026-11-26): one-bar-off NinjaTrader fills match their book rows, the backfill
patches only legs whose matched set moves, and paper rows carry a derived exit_reason."""
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from api import paper_reconcile as pr  # noqa: E402
from api.paper import _exit_reason  # noqa: E402
import nt_match_backfill as bf  # noqa: E402


def _sh(hm, px):
    return {"side": -1, "entryIso": f"2026-11-13T{hm}:00-05:00", "entry_px": px, "pnl_usd": 0.0, "size": 3.5}


def _lv(hm, px, xhm):
    return {"date": "2026-11-13", "entryTime": hm, "exitTime": xhm, "type": "SHORT", "entry": px,
            "exit": px, "size": 11, "signal": "NZ", "exit_signal": "NZexit", "pnl": 0.0}


# the real 2026-11-13 NOISE_H_RF day: book entries and the Sim101 NZ fills (fills.csv, ET)
BOOK = [_sh("14:55", 27968.5), _sh("15:05", 28019.25), _sh("15:25", 28014.0),
        _sh("15:35", 27978.75), _sh("15:45", 27982.25)]
LIVE = [_lv("14:55", 27969.075, "15:00"), _lv("15:05", 28019.1, "15:10"),
        _lv("15:30", 27990.3864, "15:35"), _lv("15:40", 27984.7727, "15:45")]


def test_one_bar_off_fills_match():
    rec = pr.match_day({"NOISE_H_RF": BOOK}, LIVE)
    blk = rec["legs"]["NOISE_H_RF"]
    got = {m["shadow_entry"][11:16]: m["live_entry"] for m in blk["matched"]}
    assert got == {"14:55": "14:55", "15:05": "15:05", "15:35": "15:30", "15:45": "15:40"}
    assert [x["entry"][11:16] for x in blk["shadow_only"]] == ["15:25"]
    assert blk["live_only"] == []
    m = [m for m in blk["matched"] if m["live_entry"] == "15:30"][0]
    assert m["live_exit"] == "15:35" and m["exit_signal"] == "NZexit"


def test_far_fill_still_unmatched():
    rec = pr.match_day({"NOISE_H_RF": [_sh("10:00", 1.0)]}, [_lv("10:10", 1.0, "10:15")])
    assert rec["legs"]["NOISE_H_RF"]["matched"] == []


def test_backfill_patches_only_moved_legs():
    old = pr.match_day({"NOISE_H_RF": BOOK}, LIVE, tol_min=3)
    report = {"reconcile": {"legs": old["legs"]}}
    rows = [dict(b, leg="NOISE_H_RF") for b in BOOK]
    patch, v = bf.plan_day("2026-11-13", LIVE, report, rows)
    assert set(patch) == {"NOISE_H_RF"} and len(patch["NOISE_H_RF"]["matched"]) == 4
    assert v is not None
    # re-running on the patched report changes nothing (idempotent, no writes)
    report["reconcile"]["legs"].update(patch)
    assert bf.plan_day("2026-11-13", LIVE, report, rows) == (None, None)


def test_exit_reason_derived():
    e = pd.Timestamp("2026-11-13 14:55", tz="America/New_York")
    assert _exit_reason(e, e + pd.Timedelta(minutes=5), 1.0) == "signal exit"
    assert _exit_reason(e, pd.Timestamp("2026-11-13 15:55", tz="America/New_York"), 1.0) == "EOD flat"
    sf = {"stops": [{"px": 100.0, "reason": "initial"}, {"px": 99.0, "reason": "trail"}], "target_px": 120.0}
    assert _exit_reason(e, e + pd.Timedelta(minutes=30), 99.0, sf) == "stop (trail)"
    assert _exit_reason(e, e + pd.Timedelta(minutes=30), 120.0, sf) == "target"
    assert _exit_reason(e, e + pd.Timedelta(minutes=30), 1.0, is_open=True) is None
