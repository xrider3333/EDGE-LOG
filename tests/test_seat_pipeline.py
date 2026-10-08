"""augur_engine.seat_pipeline - the shared seat read over the RESMOM line (BOOK.md 10ab / 10ai). ELWA-FEATURES' spec (#123): the module must
reproduce its PARITY triple from the file it names to the stated precision (a silent file swap fails), compute the episode / day counts
from the data, REFUSE a different file, and a mutant that rounds the triple to two decimals must make the parity check fail. The real-file
cases skip where the pinned file (outside git) is absent; everything else runs on synthetic series."""
import os

import numpy as np
import pandas as pd
import pytest

from augur_engine import seat_pipeline as SP

LINE_FILE = r"C:\EdgeLog\_anatomy_cache\rocfrontier\resmom_r1\resmom_cells_daily_wf_close.csv"
REGISTERED_FILE = r"C:\EdgeLog\_anatomy_cache\rocfrontier\resmom_r1\resmom_cells_daily_wf.csv"
real = pytest.mark.skipif(not os.path.exists(LINE_FILE), reason="the pinned S1 line file is local-only (outside git)")


def _series(seed=3, n=600, start="2016-07-01"):
    rng = np.random.default_rng(seed)
    ix = pd.bdate_range(start, periods=n)
    return pd.Series(rng.normal(40.0, 500.0, n), index=ix)


def test_max_drawdown_peak_starts_at_zero():
    assert SP.max_drawdown([-5.0, 2.0, -4.0]) == 7.0                       # the first row's loss counts from the flat start
    assert SP.max_drawdown([3.0, -1.0, -1.0, 5.0]) == 2.0
    assert SP.max_drawdown([]) == 0.0


def test_sortino_and_figures_by_hand():
    x = pd.Series([100.0, -50.0, 30.0, -20.0], index=pd.bdate_range("2016-07-01", periods=4))
    dn = np.sqrt(np.mean(np.minimum(x.to_numpy(), 0.0) ** 2))
    assert abs(SP.sortino(x) - x.mean() / dn * np.sqrt(252.0)) < 1e-12
    f = SP.figures(x, x.index[0], x.index[-1])
    yrs = (x.index[-1] - x.index[0]).days / 365.25
    assert abs(f["net_per_year"] - 60.0 / yrs) < 1e-9 and f["dd"] == 50.0 and abs(f["roc30"] - 30.0 * (60.0 / yrs) / 50.0) < 1e-9
    assert f["dd5"] > 0 and isinstance(f["one_episode"], bool)


def test_episodes_house_rule():
    # equity 0 -> 10 -> 4 (dd 6) -> 12 -> 11 (dd 1, < 1/3 of 6: not an episode) -> 13 -> 5 (dd 8, open at the end)
    x = pd.Series([10.0, -6.0, 8.0, -1.0, 2.0, -8.0])
    mask, spans = SP.episodes(x)
    assert [(a, b) for a, b, _ in spans] == [(1, 1), (5, 5)] and [d for _, _, d in spans] == [6.0, 8.0]
    assert mask.tolist() == [False, True, False, False, False, True]


def test_load_pinned_daily_refuses_a_different_file(tmp_path):
    p = tmp_path / "line.csv"
    p.write_text("date,book_mtm,RES\n2016-07-01,1.0,2.0\n2016-07-05,3.0,4.0\n")
    import hashlib
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    d = SP.load_pinned_daily(str(p), h[:12])
    assert list(d.columns) == ["book_mtm", "RES"] and len(d) == 2
    with pytest.raises(ValueError):
        SP.load_pinned_daily(str(p), SP.LINE_FILE_SHA)                    # a different file than the one pinned: refused
    with pytest.raises(ValueError):
        SP.load_pinned_daily(str(p), "abc")                               # a sha too short to pin anything


def test_check_parity_precision_and_counts_from_the_data():
    s = _series()
    f = SP.figures(s)
    mask, spans = SP.episodes(SP.window(s))
    par = {"syn": (round(f["roc30"], 4), round(f["sortino"], 5), round(f["dd"], 2))}
    cnt = {"syn": (len(spans), int(mask.sum()))}
    SP.check_parity(s, "syn", parity=par, counts=cnt)                     # reproduces its own triple
    with pytest.raises(ValueError):                                        # one day changed: the file "swapped"
        s2 = s.copy()
        s2.iloc[10] += 900.0
        SP.check_parity(s2, "syn", parity=par, counts=cnt)
    with pytest.raises(ValueError):                                        # the counts are compared, not assumed
        SP.check_parity(s, "syn", parity=par, counts={"syn": (cnt["syn"][0] + 1, cnt["syn"][1])})


def test_rounding_mutant_fails_the_parity_check():
    s = _series(seed=11)
    f = SP.figures(s)
    mask, spans = SP.episodes(SP.window(s))
    exact = (round(f["roc30"], 4), round(f["sortino"], 5), round(f["dd"], 2))
    mutant = tuple(round(v, 2) for v in exact)
    assert mutant != exact
    with pytest.raises(ValueError):
        SP.check_parity(s, "syn", parity={"syn": mutant}, counts={"syn": (len(spans), int(mask.sum()))})


def test_seat_read_shape_and_earner_flag():
    s = _series(seed=5, n=800)
    res = _series(seed=6, n=800) * 0.5
    x = _series(seed=7, n=800) * 0.2
    r = SP.seat_read(x, s, res, start=s.index[0], end=s.index[-1], draws=np.random.default_rng(1).normal(0, 100, (50, 800)))
    assert set(r["book_add"]) == {"0.25", "0.10"} and "dd5" in r["book_add"]["0.25"]["line_plus"]
    assert r["R_days"] > 0 and isinstance(r["earner"], bool) and set(r["null_on_R"]) == {"p5", "p50", "p95"}
    z = SP.seat_read(x * 0.0, s, res, start=s.index[0], end=s.index[-1])
    assert z["book_add"]["0.25"]["line_plus"] is None                    # no variance in the sizing window: no size, no invented figure


@real
def test_the_pinned_line_reproduces_to_the_stated_precision():
    D = SP.load_pinned_daily(LINE_FILE, SP.LINE_FILE_SHA)
    f = SP.check_parity(SP.window(SP.line_L(D["book_mtm"], D["RES"])), "line_L")
    assert abs(f["dd5"] - 34392.44) < 0.01 and not f["one_episode"]
    SP.check_parity(SP.window(D["book_mtm"]), "book463")


@real
def test_the_pinned_line_fails_a_rounded_parity_and_the_registered_file_is_refused():
    D = SP.load_pinned_daily(LINE_FILE, SP.LINE_FILE_SHA)
    L = SP.window(SP.line_L(D["book_mtm"], D["RES"]))
    mutant = {"line_L": tuple(round(v, 2) for v in SP.PARITY["line_L"])}
    with pytest.raises(ValueError):
        SP.check_parity(L, "line_L", parity=mutant)
    if os.path.exists(REGISTERED_FILE):
        with pytest.raises(ValueError):
            SP.load_pinned_daily(REGISTERED_FILE, SP.LINE_FILE_SHA)       # the superseded registered file is not the pinned one
        R = pd.read_csv(REGISTERED_FILE, parse_dates=["date"]).set_index("date")
        with pytest.raises(ValueError):
            SP.check_parity(SP.window(SP.line_L(R["book_mtm"], R["RES"])), "line_L")   # 120.82 is not 121.0602
