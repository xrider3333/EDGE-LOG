"""LIVE KEEL wiring (owner call 10-12 via MANAGER #143): synthetic live NOISE_382 trades go through
the whole box chain -- the scorer and its entry record (api/cloud_signal), the executor's close hook
(api/qqq_exec: queue + emit into cloud_signal/keel_inbox), the handler (tools/keel_intraday.py) --
and every entry is sized exactly as a manual keel_append_trade chain says (1e-12): each trade scored
with every earlier live trade that EXITED before its entry bar (the same-bar reversal included),
P = (pnl / shares) x plugin size x the NQ/QQQ ratio. The nightly reference alone would size them
differently (so the check can tell).
"""
import os
import sys

import numpy as np
import pytest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
for _p in (ROOT, THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api import cloud_signal as cs  # noqa: E402
from api import qqq_exec as qe  # noqa: E402
from augur_engine import ml_keel as K  # noqa: E402
import tools.keel_intraday as KI  # noqa: E402
from _keel_live_world import LEG, QUIET, TRUSTING, TRUSTING_CFG, LiveWorld  # noqa: E402

TOL = 1e-12


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(K.CFG, TRUSTING, TRUSTING_CFG)
        yield LiveWorld(tmp_path_factory.mktemp("keel_live_wiring") / "w", version=TRUSTING)


def test_hook_handler_scorer_give_the_manual_chain(base, tmp_path, monkeypatch):
    w = base.clone(tmp_path / "w")
    monkeypatch.setenv("EDGELOG_HOST_ROLE", "cloud")
    monkeypatch.delenv("EDGELOG_QQQ_EXEC_DIR", raising=False)
    monkeypatch.setattr(cs, "DEFAULT_PATHS", w.cs_paths)          # the executor's keel inbox
    cfg = w.keel_cfg()
    executor = {}                                                  # the executor's state.json
    chain = [dict(w.nightly)]                                      # chain[j]: the cut + j trades
    rows = []
    for t in w.live_trades:
        # 1. the ENTRY: the scorer, then its record (what _diff_leg / _note_keel_entries do)
        sc = {}
        size, diag = cs._keel_size_for_entry(cfg, w.q_arrays, t["e"], t["entry_time"].isoformat(),
                                             log=QUIET, scratch=sc)
        assert isinstance(diag, dict), f"trade {t['k']} fell back: {diag}"
        trade = {"entry_time": t["entry_time"].isoformat(), "entry_bar": t["e"], "side": t["side"]}
        rec = cs._keel_xrow_record(LEG, t["trade_id"], trade, w.q_arrays, cfg, size, diag,
                                   t["plugin"], t["plugin"] * size, sc)
        assert cs._append_keel_xrow(w.files["xrows_path"], rec) is True
        j = sum(1 for u in w.live_trades[:t["k"]] if u["x"] < t["e"])  # exited before this bar
        want = K.keel_score_from_state(chain[j], w.q_arrays, t["e"], x_row=w.x_row(t["e"]),
                                       cross_series=True)[0]
        night = K.keel_score_from_state(w.nightly, w.q_arrays, t["e"], x_row=w.x_row(t["e"]),
                                        cross_series=True)[0]
        rows.append((t["k"], size, want, night, sc.get("state_source"), sc.get("ledger_n"), j))
        # 2. the close: the executor's hook (no Webull order on file -> the book's prices)
        sign = 1 if t["side"] == "long" else -1
        pnl = round((t["exit_px"] - t["entry_px"]) * sign * t["shares"], 2)
        lot = {"leg": "NOISE", "trade_id": t["trade_id"], "entry_ts": t["entry_ts"],
               "_exit_ts": t["exit_ts"], "side": t["side"], "shares_total": t["shares"],
               "entry_px": t["entry_px"]}
        qe._queue_keel_close(executor, lot, t["exit_px"], pnl, "signal exit", log=QUIET)
        qe._maybe_emit_keel_closes(executor, log=QUIET)
        assert executor["_keel_closes"] == []
        # 3. the handler (edgelog-keel-append.path)
        res = KI.process_inbox(w.home, w.nq_master, LEG, log=QUIET,
                               live_from=str(w.live_days[0]))
        assert [r["status"] for r in res] == ["appended"], res
        assert res[0]["n_before"] == chain[-1]["n"], "the chain (prev_trade_id) held: n_before = n"
        # the manual chain
        P = (pnl / t["shares"]) * ((t["plugin"] * size) / size) * w.ratio_for(t["entry_time"].date())
        chain.append(K.keel_append_trade(chain[-1], w.x_row(t["e"]), P,
                                         entry_bar=KI.bar_number(t["entry_time"]),
                                         exit_bar=KI.bar_number(t["exit_ts"])))
    for k, size, want, night, source, n, j in rows:
        assert abs(size - want) <= TOL, (k, size, want)
        assert n == chain[j]["n"], (k, n, j)
    assert rows[0][4] == "nightly", "before the cut: the nightly reference (the cut copies it)"
    assert rows[1][4] == "live_prev", "the same-bar reversal: the state before its last append"
    assert {r[4] for r in rows[2:]} == {"live"}
    assert any(abs(size - night) > 1e-6 for _k, size, _w, night, *_ in rows), \
        "fixture: the nightly alone must size some entry differently, or this proves nothing"
    live = w.load("live_path")
    assert live["n"] == chain[-1]["n"] == w.nightly["n"] + len(w.live_trades)
    assert np.array_equal(live["P"], chain[-1]["P"]) and np.array_equal(live["X"], chain[-1]["X"],
                                                                         equal_nan=True)
    assert np.array_equal(live["z"], chain[-1]["z"], equal_nan=True)
    assert len(cs.read_keel_xrows(w.files["xrows_path"])) == len(w.live_trades)
    # the executor's chain reached the handler: every close named the one before it
    rows_log = KI.read_appends(w.files["appends_path"])
    want_prev = [None] + [t["trade_id"] for t in w.live_trades[:-1]]
    assert [r["prev_trade_id"] for r in rows_log] == want_prev
    assert KI.verify_live_state(w.home, LEG, log=QUIET)["ok"] is True
    assert w.ack()["alerts"] == []
