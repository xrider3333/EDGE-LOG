"""augur_strategies/ORB_3_6.py -- `session_in_progress` (WEBULL_PAPER_TODO.md item 15).

Root cause: skip_holidays flags any session shorter than 70% of the trailing median as
a half day. On the LIVE engine the LAST session in its rolling window is today's own,
still being built bar by bar, so it is genuinely short for a reason that has nothing to
do with a holiday -- and gets skipped exactly like a real half day, aging a morning
entry past api/cloud_signal.py's freshness window before the session ever counts as
"full". `session_in_progress` (default False, runtime-only -- not a DEFAULT_PARAMS
knob) exempts ONLY the last session from that length test.

Coverage:
  1. Default (omitted / explicit False) is byte-identical to the pre-existing code --
     a short last session is still skipped, exactly like a real holiday.
  2. session_in_progress=True exempts the LAST session only -- an EARLIER short session
     (a genuine holiday, mid-history) is still skipped.
  3. session_in_progress=True is a no-op when the last session is NOT short.
  4. session_in_progress is irrelevant when skip_holidays=False (the block never runs).
  5. Real-master byte-identical check (skipped if the shared checkout's NQ 5m master
     isn't reachable): ORB #314's own parameters, session_in_progress on vs off, produce
     the identical trade list on finished historical data -- see also
     tools/orb_halfday_parity.py for the live-tick-by-tick version of this same check.
"""
import importlib.util
import os

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRAT = os.path.join(ROOT, "augur_strategies")
SHARED_NQ_MASTER = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\augur_uploads\NOADJ_NQ_5m_RTH.csv"


def _load(fname):
    spec = importlib.util.spec_from_file_location("_orbsip_" + fname[:-3],
                                                   os.path.join(STRAT, fname))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ORB = _load("ORB_3_6.py")

BASE_KW = dict(
    or_bars=1, trade_mode="Both", stop_frac=2.0, vpace_filter=0.0, breakout_buf=0.0,
    close_confirm=True, partial_exit_R=0.0, trail_bars=0, be_after_R=0.0,
    atr_filter=0.0, target_R=0.0, flat_eod=True, skip_holidays=True,
)


def _session(n_bars, level=100.0):
    """OR bar (range [level-0.5, level+0.5]) + an immediate close-confirmed breakout to
    level+1.0, then flat padding bars to reach `n_bars` total. `n_bars` >= 2. With
    or_bars=1/breakout_buf=0 this always fires exactly one long trade that then rides
    flat to the session's EOD flatten (target_R/trail_bars/partial_exit_R all off)."""
    assert n_bars >= 2
    o = [level, level]
    h = [level + 0.5, level + 1.5]
    l = [level - 0.5, level]
    c = [level, level + 1.0]
    for _ in range(n_bars - 2):
        o.append(level + 1.0); h.append(level + 1.0); l.append(level + 1.0); c.append(level + 1.0)
    return o, h, l, c


def _build(session_lens):
    """Concatenates one `_session` per length in `session_lens` into one array set,
    with day_id marking session boundaries."""
    O, H, L, C, D = [], [], [], [], []
    for si, n in enumerate(session_lens):
        o, h, l, c = _session(n)
        O += o; H += h; L += l; C += c
        D += [si] * n
    return (np.array(O, float), np.array(H, float), np.array(L, float), np.array(C, float),
            np.array(D, dtype=int))


# 6 sessions: four normal (20 bars), one genuine mid-history "holiday" (5 bars, index 3),
# one short LAST session (6 bars, index 5) standing in for "today, still in progress".
# lengths sorted = [5, 6, 20, 20, 20, 20] -> median 20 -> 70% threshold 14: both the
# 5-bar and 6-bar sessions fall under it.
SESSION_LENS = [20, 20, 20, 5, 20, 6]
N_SESSIONS = len(SESSION_LENS)
LAST_IDX = N_SESSIONS - 1


def _num_trades(session_in_progress=None, skip_holidays=True):
    o, h, l, c, d = _build(SESSION_LENS)
    kw = dict(BASE_KW, skip_holidays=skip_holidays, day_id=d, return_trades=True)
    if session_in_progress is not None:
        kw["session_in_progress"] = session_in_progress
    res = ORB.run_backtest(o, h, l, c, **kw)
    assert res is not None
    return res["num_trades"], res["trades"]


def test_default_reproduces_the_pre_existing_holiday_skip():
    """Omitting session_in_progress (the new kwarg's own default) skips BOTH short
    sessions -- the holiday (index 3) and the in-progress last one (index 5) -- exactly
    like ORB_3_6.py before this change: 4 of 6 sessions fire (0, 1, 2, 4)."""
    n, trades = _num_trades(session_in_progress=None)
    assert n == 4
    assert _fired_session_indices(trades) == [0, 1, 2, 4]


def test_explicit_false_matches_the_default():
    n_false, trades_false = _num_trades(session_in_progress=False)
    n_default, trades_default = _num_trades(session_in_progress=None)
    assert n_false == n_default == 4
    assert trades_false == trades_default


def _fired_session_indices(trades):
    """Which of SESSION_LENS' sessions produced a trade, by looking up each trade's
    entry bar against the same session boundaries _build laid the bars out with."""
    bounds = []
    a = 0
    for n in SESSION_LENS:
        bounds.append((a, a + n)); a += n
    out = []
    for t in trades:
        entry_bar = t[0]
        for si, (a, b) in enumerate(bounds):
            if a <= entry_bar < b:
                out.append(si)
                break
    return sorted(set(out))


def test_session_in_progress_exempts_only_the_last_session():
    """True exempts index 5 (the last session) but NOT index 3 (an earlier short
    session, a genuine holiday) -- 5 of 6 sessions fire (0, 1, 2, 4, 5)."""
    n, trades = _num_trades(session_in_progress=True)
    assert n == 5
    assert _fired_session_indices(trades) == [0, 1, 2, 4, 5]


def test_session_in_progress_is_a_noop_when_the_last_session_is_not_short():
    """The exemption only ever REMOVES a session from `_holiday_start`; with no short
    last session to begin with, True and False/omitted give identical results."""
    lens = [20, 20, 20, 5, 20, 20]   # holiday mid-history, last session full length
    o, h, l, c, d = _build(lens)
    kw = dict(BASE_KW, day_id=d, return_trades=True)
    r_off = ORB.run_backtest(o, h, l, c, session_in_progress=False, **kw)
    r_on = ORB.run_backtest(o, h, l, c, session_in_progress=True, **kw)
    assert r_off["num_trades"] == r_on["num_trades"] == 5   # only index 3 ever skipped
    assert r_off["trades"] == r_on["trades"]


def test_session_in_progress_irrelevant_when_skip_holidays_is_off():
    """skip_holidays=False never builds `_holiday_start` at all -- session_in_progress
    cannot matter (nor should it), so every session fires either way, including the two
    short ones."""
    n_off, _ = _num_trades(session_in_progress=False, skip_holidays=False)
    n_on, _ = _num_trades(session_in_progress=True, skip_holidays=False)
    assert n_off == n_on == N_SESSIONS


@pytest.mark.skipif(not os.path.exists(SHARED_NQ_MASTER),
                    reason="shared checkout's NQ 5m master not reachable from this machine")
def test_byte_identical_on_real_history_session_in_progress_is_always_a_noop():
    """ORB #314's own parameters (see api/paper.py) over the real NQ 5m master, with
    session_in_progress on vs off: every session in real historical data is long
    finished, so the exemption path (`_si == last session index AND short`) is never
    taken and the two runs must produce the IDENTICAL trade list, bit for bit. This is
    the static counterpart of tools/orb_halfday_parity.py's live tick-by-tick replay."""
    import pandas as pd
    from api.paper import ORB_314

    df = pd.read_csv(SHARED_NQ_MASTER)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df["day_id"] = pd.factorize(dt.dt.date)[0]
    df = df.sort_values("time").reset_index(drop=True)
    args = (df["open"].values, df["high"].values, df["low"].values, df["close"].values)
    kw = dict(volumes=df["volume"].values, day_id=df["day_id"].values, return_trades=True)

    r_off = ORB.run_backtest(*args, **kw, **ORB_314, session_in_progress=False)
    r_on = ORB.run_backtest(*args, **kw, **ORB_314, session_in_progress=True)
    assert r_off["num_trades"] == r_on["num_trades"]
    assert r_off["total_pnl"] == pytest.approx(r_on["total_pnl"], abs=1e-9)
    assert r_off["trades"] == r_on["trades"]
