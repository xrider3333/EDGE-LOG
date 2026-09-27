"""A CALLER THAT DOES NOT NAME A SOURCE MUST NEVER BE HANDED A ROLL-CORRECTED MASTER.

WHY THIS EXISTS (2026-09-26). Registering the first roll-corrected masters silently changed
what every UNPINNED master lookup returned. `find_master` took the first row of a list ordered
by source name, and `db_adj_eth` sorts before `db_noadj_eth`, so the moment those rows existed:

    find_master("NQ", "1m", "eth")   ->  ADJ_NQ_1m_ETH.csv     (back-adjusted)
    find_master("NQ", "5m", "rth")   ->  ADJ_NQ_5m_RTH.csv     (back-adjusted)

Three services resolve their data without naming a source: the live NinjaTrader ML gate
(`api/gate_live.py`), the paper leg loader (`api/paper.py`) and the reconcile tool
(`augur_engine/reconcile.py`). All three would have switched to back-adjusted prices, against
the explicit instruction that no live or paper leg's data changes.

The price scales are not close. A back-adjusted NQ series is shifted by about +3,700 points at
its oldest bar, and its recent bars differ from the tradeable front contract wherever a later
switch exists. A gate model refit on that, or a paper leg priced from it, is not slightly off -
it is reading a different instrument.

Nothing was actually rebuilt on adjusted data - the mistake landed on a Saturday with markets
and NinjaTrader closed and no jobs queued - so this file is here to make sure the window never
opens again. Adjusted masters are OPT-IN ONLY.
"""
import json
import os
import sqlite3
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


ROWS = [
    # name, filename, instrument, timeframe, session, source
    ("NQ 1m ETH - no-adj",        "NOADJ_NQ_1m_ETH.csv", "NQ", "1m",  "eth", "db_noadj_eth"),
    ("NQ 1m ETH - back-adjusted", "ADJ_NQ_1m_ETH.csv",   "NQ", "1m",  "eth", "db_adj_eth"),
    ("NQ 1m ETH - forward",       "FADJ_NQ_1m_ETH.csv",  "NQ", "1m",  "eth", "db_fadj_eth"),
    ("NQ 5m RTH - no-adj",        "NOADJ_NQ_5m_RTH.csv", "NQ", "5m",  "rth", "db_noadj_rth"),
    ("NQ 5m RTH - back-adjusted", "ADJ_NQ_5m_RTH.csv",   "NQ", "5m",  "rth", "db_adj_rth"),
    ("ES 30m RTH - back-adj",     "ADJ_ES_30m_RTH.csv",  "ES", "30m", "rth", "db_adj_rth"),
    # deliberately the ONLY master for this pair, so "nothing unadjusted exists" is covered
    ("ES 60m RTH - back-adj",     "ADJ_ES_60m_RTH.csv",  "ES", "60m", "rth", "db_adj_rth"),
    # a non-adjusted sibling that sorts AFTER db_noadj, to prove ordering is otherwise intact
    ("NQ 1m ETH - merged",        "master_231cce27.csv", "NQ", "1m",  "eth", "merged"),
]


@pytest.fixture()
def registry(tmp_path, monkeypatch):
    """A throwaway csv_files registry holding adjusted and unadjusted rows side by side."""
    db = tmp_path / "optimizer_history.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE csv_files (id INTEGER PRIMARY KEY, name TEXT, filename TEXT, "
        "instrument TEXT, rows INTEGER, date_from TEXT, date_to TEXT, created_at TEXT, "
        "timeframe TEXT, is_master INTEGER, source TEXT, provenance TEXT, session TEXT)")
    for name, fn, inst, tf, sess, src in ROWS:
        conn.execute(
            "INSERT INTO csv_files (name,filename,instrument,rows,date_from,date_to,"
            "created_at,timeframe,is_master,source,provenance,session) "
            "VALUES (?,?,?,?,?,?,?,?,1,?,?,?)",
            (name, fn, inst, 1000, "2010-06-07", "2026-09-25", "2026-09-26 18:14:00",
             tf, src, json.dumps({}), sess))
    conn.commit()
    conn.close()

    from augur_engine import data as aedata
    monkeypatch.setattr(aedata, "DB_PATH", str(db))
    return aedata


UNPINNED = [("NQ", "1m", "eth", "NOADJ_NQ_1m_ETH.csv"),
            ("NQ", "5m", "rth", "NOADJ_NQ_5m_RTH.csv")]


@pytest.mark.parametrize("inst,tf,sess,expected", UNPINNED)
def test_an_unpinned_lookup_returns_the_unadjusted_master(registry, inst, tf, sess, expected):
    """The regression itself. This is what the live gate, the paper loader and reconcile ask."""
    m = registry.find_master(inst, tf, sess)
    assert m is not None
    assert m["filename"] == expected
    assert m["source"].startswith("db_noadj")


def test_an_unpinned_lookup_with_no_session_given(registry):
    """api/bars.py, blotter.py, configs.py and similar.py fall all the way back to
    find_master(instrument, timeframe) with neither session nor source."""
    m = registry.find_master("NQ", "1m")
    assert m is not None and not registry.is_adjusted_source(m["source"])


def test_a_named_adjusted_source_still_resolves(registry):
    """Opt-in has to work, or the whole point of building them is lost."""
    assert registry.find_master("NQ", "1m", "eth", "db_adj_eth")["filename"] == "ADJ_NQ_1m_ETH.csv"
    assert registry.find_master("NQ", "1m", "eth", "db_fadj_eth")["filename"] == "FADJ_NQ_1m_ETH.csv"
    assert registry.find_master("ES", "30m", "rth", "db_adj_rth")["filename"] == "ADJ_ES_30m_RTH.csv"


def test_when_only_an_adjusted_master_exists_the_answer_is_None_not_a_substitute(registry):
    """ES 60m RTH is registered ONLY as back-adjusted here.

    Returning it would be the same silent substitution, just rarer and harder to notice.
    Finding no data is recoverable - a caller errors or skips. A live service quietly
    re-pointed at a different price scale is not.
    """
    assert registry.find_master("ES", "60m", "rth") is None
    # and naming it still works
    assert registry.find_master("ES", "60m", "rth", "db_adj_rth") is not None


def test_ordering_among_unadjusted_sources_is_unchanged(registry):
    """The fix must not change which UNADJUSTED master wins when several match.

    NQ 1m ETH has both db_noadj_eth and merged registered; db_noadj sorted first before the
    adjusted masters existed and must still sort first now.
    """
    assert registry.find_master("NQ", "1m", "eth")["source"] == "db_noadj_eth"


def test_is_adjusted_source_recognises_both_families_and_nothing_else(registry):
    f = registry.is_adjusted_source
    assert f("db_adj_rth") and f("db_adj_eth") and f("db_fadj_rth") and f("db_fadj_eth")
    for ok in ("db_noadj_rth", "db_noadj_eth", "tv", "merged", "nt_noadj_eth", "", None):
        assert not f(ok), "%r must not be treated as roll-corrected" % (ok,)


def test_the_live_and_paper_call_sites_still_pass_no_source(registry):
    """If someone later makes gate_live or paper pass source='db_adj_*', that is a decision
    the owner has to make, not a refactor. This notices the change."""
    for rel, needle in (("api/gate_live.py", "find_master(leg[\"instrument\"], leg[\"timeframe\"]"),
                        ("api/paper.py", "find_master(leg[\"instrument\"], leg[\"timeframe\"]")):
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        assert needle in src, "%s no longer resolves its master the way this test assumes" % rel
        i = src.index(needle)
        line = src[src.rindex("\n", 0, i) + 1:src.index("\n", src.index(")", i))]
        assert "db_adj" not in line and "db_fadj" not in line, (
            "%s now names a roll-corrected source: %s" % (rel, line.strip()))
