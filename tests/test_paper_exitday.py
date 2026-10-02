"""PAPER board counts a trade's money on the day it CLOSES (owner GO 2026-10-02, FRONTIER inbox #29).

Everything is synthetic: run_shadow is scripted, Firestore is an in-memory fake, the other report
blocks are stubbed. Nothing touches Firestore, C:\\EdgeLog or the network (conftest guards both).
Covers: a multi-day hold counted on its exit day only; an entry after 16:10 ET; an exit after
16:10 ET (lands in its own day's figure from the next nightly run on); a still-open trade excluded
then counted exactly once when it closes; a weekend exit counted on the Monday; the book weights
applied by exit day; the open flag and the end-of-data detection.
"""
import datetime as dt
import os
import sys
import types

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import paper, paper_exitday as xd  # noqa: E402

UID = "uid-test"


def _et(s):
    return pd.Timestamp(s, tz="US/Eastern")


def _trade(entry, exit_, pnl, *, open_=False, key="ORB"):
    return {"leg": key, "strategy": "X.py", "side": 1, "entry_dt": _et(entry), "exit_dt": _et(exit_),
            "entry_px": 100.0, "exit_px": 101.0, "size": 1.0, "pnl_pts": pnl / 20.0, "pnl_usd": float(pnl),
            "raw_pts": None, "open": open_}


# ── in-memory Firestore ──────────────────────────────────────────────────────────────────
class _Snap:
    def __init__(self, ref, data):
        self.reference, self.id, self._d = ref, ref.id, data
        self.exists = data is not None

    def to_dict(self):
        return None if self._d is None else dict(self._d)


def _merge(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = v


class _Doc:
    def __init__(self, db, path):
        self.db, self.path, self.id = db, path, path.rsplit("/", 1)[-1]

    def get(self):
        return _Snap(self, self.db.store.get(self.path))

    def set(self, data, merge=False):
        if merge and self.path in self.db.store:
            _merge(self.db.store[self.path], data)
        else:
            self.db.store[self.path] = dict(data)

    def collection(self, name):
        return _Col(self.db, self.path + "/" + name)


class _Col:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def document(self, i):
        return _Doc(self.db, self.path + "/" + i)

    def where(self, field, op, val):
        return _Query(self, field, val)

    def stream(self):
        pre = self.path + "/"
        return [_Snap(_Doc(self.db, p), d) for p, d in sorted(self.db.store.items())
                if p.startswith(pre) and "/" not in p[len(pre):]]


class _Query:
    def __init__(self, col, field, val):
        self.col, self.field, self.val = col, field, val

    def stream(self):
        return [s for s in self.col.stream() if (s.to_dict() or {}).get(self.field) == self.val]


class _Batch:
    def __init__(self, db):
        self.db, self.ops = db, []

    def set(self, ref, data, merge=False):
        self.ops.append(("set", ref, data, merge))

    def delete(self, ref):
        self.ops.append(("del", ref))

    def commit(self):
        for op in self.ops:
            if op[0] == "set":
                op[1].set(op[2], merge=op[3])
            else:
                self.db.store.pop(op[1].path, None)
        self.ops = []


class FakeDB:
    def __init__(self):
        self.store = {}

    def collection(self, name):
        return _Col(self, name)

    def batch(self):
        return _Batch(self)

    def report(self, day):
        return self.store.get(f"users/{UID}/paper_reports/{day}")

    def trade_docs(self, leg=None):
        pre = f"users/{UID}/paper_trades/"
        return {p[len(pre):]: d for p, d in self.store.items()
                if p.startswith(pre) and (leg is None or d.get("leg") == leg)}


class FakeQ:
    def __init__(self, db):
        self.db, self.allow = db, [UID]


LEGS = [{"key": k, "strategy": k + ".py", "timeframe": "1m", "session": "eth", "params": {}}
        for k in ("ORB", "ENGUQ_335", "TTM_299_SSOF2", "NOISE_422")]
BOOK_W = {"ORB": 1.0, "ENGUQ_335": 1.0, "TTM_299_SSOF2": 3.0, "NOISE_422": 1.0}


@pytest.fixture
def board(monkeypatch):
    """A scripted board: `board.trades[leg]` is the full trade list run_shadow returns each night."""
    monkeypatch.setitem(sys.modules, "firebase_admin",
                        types.SimpleNamespace(firestore=types.SimpleNamespace(SERVER_TIMESTAMP="TS")))
    from api import book_shadow, capture_health, gate_audit, paper_reconcile

    class B:
        trades = {l["key"]: [] for l in LEGS}
        db = FakeDB()

        def night(self, day):
            return paper._run_one_uid(FakeQ(self.db), UID, dt.date.fromisoformat(day))

    b = B()
    b.trades = {l["key"]: [] for l in LEGS}
    monkeypatch.setattr(paper, "PAPER_LEGS", LEGS)
    monkeypatch.setattr(paper, "run_shadow", lambda leg, d: {
        "trades": list(b.trades[leg["key"]]), "ungated_trades": [], "gate": None, "bars_appended": 0,
        "data_fresh_thru": None, "warnings": [], "ran_ok": True})
    monkeypatch.setattr(paper, "collect_live_fills", lambda d: {})
    monkeypatch.setattr(paper, "PAPER_START", "2026-09-01")
    monkeypatch.setattr(book_shadow, "vt_block",
                        lambda book_pnl, day: {"pnl_usd": 2.0 * book_pnl, "multiplier": 2.0})
    monkeypatch.setattr(capture_health, "capture_health", lambda d: {})
    monkeypatch.setattr(paper_reconcile, "run", lambda d, r, live_expected=None: {"ok": True})
    monkeypatch.setattr(gate_audit, "audit", lambda d, report=None: {"ok": True})
    return b


def _leg_pnl(db, day, key):
    return db.report(day)["legs"][key]["pnl_usd"]


# ── pure helpers ─────────────────────────────────────────────────────────────────────────
def test_exit_day_is_the_eastern_calendar_date_and_a_weekend_rolls_to_monday():
    assert xd.et_date(_et("2026-09-15 23:59")) == dt.date(2026, 9, 15)
    assert xd.et_date(pd.Timestamp("2026-09-16 03:30", tz="UTC")) == dt.date(2026, 9, 15)   # 23:30 ET
    assert xd.et_date(pd.Timestamp("2026-09-15 20:00")) == dt.date(2026, 9, 15)             # naive = Eastern
    assert xd.close_day(_et("2026-09-20 19:00")) == dt.date(2026, 9, 21)                    # Sunday evening
    assert xd.close_day(_et("2026-09-19 12:00")) == dt.date(2026, 9, 21)                    # Saturday
    assert xd.close_day(_et("2026-09-18 16:30")) == dt.date(2026, 9, 18)                    # Friday after 16:10


def test_open_means_exit_on_the_last_bar_and_not_the_end_of_the_leg_session():
    idx = pd.DatetimeIndex([_et("2026-09-15 15:53"), _et("2026-09-15 15:54"), _et("2026-09-15 16:09")])
    eth = {"session": "eth", "timeframe": "1m"}
    assert xd.is_open(eth, idx, 2) is True               # held to the final bar of the data
    assert xd.is_open(eth, idx, 1) is False              # closed with bars still to come
    rth5 = {"session": "rth", "timeframe": "5m"}
    cash = pd.DatetimeIndex([_et("2026-09-15 15:50"), _et("2026-09-15 15:55")])
    assert xd.is_open(rth5, cash, 1) is False            # flattened on the last 5m bar of the cash session
    mid = pd.DatetimeIndex([_et("2026-09-15 11:50"), _et("2026-09-15 11:55")])
    assert xd.is_open(rth5, mid, 1) is True              # mid-session run: still held
    assert xd.is_open({"session": "rth", "timeframe": "30m"}, pd.DatetimeIndex([_et("2026-09-15 15:30")]), 0) is False


def test_extract_trades_writes_the_open_flag(monkeypatch):
    idx = pd.DatetimeIndex([_et("2026-09-15 10:00"), _et("2026-09-15 10:01"), _et("2026-09-15 10:02")])
    arrays = {"index": idx, "open": [100.0, 101.0, 102.0]}
    leg = {"key": "ENGUQ_335", "strategy": "E.py", "mult": 20.0, "session": "eth", "timeframe": "1m"}
    out = paper._extract_trades(leg, arrays, [((0, 1, 1.0, 1, 100.0), 1.0), ((1, 2, 2.0, 1, 101.0), 1.0)])
    assert [t["open"] for t in out] == [False, True]


def test_bucket_counts_closed_trades_once_on_their_close_day_and_sets_open_aside():
    ts = [_trade("2026-09-14 22:28", "2026-09-15 10:00", 1000),       # multi-day hold
          _trade("2026-09-15 17:00", "2026-09-15 20:00", 300),        # entry AND exit after 16:10
          _trade("2026-09-18 17:30", "2026-09-20 19:00", 50),         # Sunday exit -> Monday
          _trade("2026-09-16 09:35", "2026-09-16 16:09", 500, open_=True)]
    pnl, cnt, open_n, open_pnl = xd.bucket(ts)
    assert pnl == {"2026-09-15": 1300.0, "2026-09-21": 50.0}
    assert cnt == {"2026-09-15": 2, "2026-09-21": 1}
    assert (open_n, open_pnl) == (1, 500.0)
    assert sum(pnl.values()) == sum(t["pnl_usd"] for t in ts if not t["open"])     # nothing lost, nothing twice


# ── the nightly run, end to end ──────────────────────────────────────────────────────────
def test_multiday_hold_counts_on_its_exit_day_only(board):
    # entered Mon 09-14 22:28, exits Wed 09-16 10:00: Monday and Tuesday carry nothing, Wednesday all of it
    board.trades["ENGUQ_335"] = [_trade("2026-09-14 22:28", "2026-09-16 10:00", 3751, key="ENGUQ_335")]
    for day in ("2026-09-15", "2026-09-16"):
        board.night(day)
    assert _leg_pnl(board.db, "2026-09-15", "ENGUQ_335") == 0.0
    assert _leg_pnl(board.db, "2026-09-16", "ENGUQ_335") == 3751.0
    doc = board.db.trade_docs("ENGUQ_335")
    assert len(doc) == 1
    d = next(iter(doc.values()))
    assert d["run_date"] == "2026-09-14"                   # the entry date stays visible on the doc
    assert d["exit_date"] == "2026-09-16" and d["close_day"] == "2026-09-16" and d["open"] is False
    assert list(doc)[0].startswith("pt_ENGUQ_335_")        # id scheme still entry-keyed
    assert board.db.report("2026-09-15")["legs"]["ENGUQ_335"]["n_signals"] == 0


def test_entry_after_1610_is_counted_when_it_closes_not_lost(board):
    # the owner's example: entered 09-15 22:28 ET (after that day's 16:10 report), +3751 at its 09-16 exit
    board.trades["ENGUQ_335"] = [_trade("2026-09-15 22:28", "2026-09-16 09:40", 3751, key="ENGUQ_335")]
    board.night("2026-09-15")
    assert _leg_pnl(board.db, "2026-09-15", "ENGUQ_335") == 0.0
    board.night("2026-09-16")
    assert _leg_pnl(board.db, "2026-09-16", "ENGUQ_335") == 3751.0
    assert board.db.report("2026-09-16")["book"]["pnl_usd"] == 3751.0


def test_exit_after_1610_lands_in_its_own_day_from_the_next_nightly_run(board):
    # ENTERS and EXITS on 09-15 but after the 16:10 report: 09-15's report cannot see it that night
    board.trades["NOISE_422"] = [_trade("2026-09-15 09:35", "2026-09-15 15:55", 200, key="NOISE_422")]
    board.trades["ENGUQ_335"] = []
    board.night("2026-09-15")
    assert _leg_pnl(board.db, "2026-09-15", "NOISE_422") == 200.0
    board.trades["ENGUQ_335"] = [_trade("2026-09-15 16:20", "2026-09-15 20:00", 300, key="ENGUQ_335")]
    # the 09-15 report already ran; the 09-16 run must put the 300 into 09-15 and into nothing else
    board.night("2026-09-16")
    assert _leg_pnl(board.db, "2026-09-15", "ENGUQ_335") == 300.0
    assert _leg_pnl(board.db, "2026-09-16", "ENGUQ_335") == 0.0
    assert board.db.report("2026-09-15")["book"]["pnl_usd"] == 500.0         # 200 NOISE + 300 ENGU-Q, weight 1 each
    assert board.db.report("2026-09-15")["blend"]["pnl_usd"] == 0.0          # the blend is the ORB + ENGUQ legs only
    # a third night changes nothing (idempotent: the figure is a function of the trade list)
    before = {d: dict(board.db.report(d)["book"]) for d in ("2026-09-15", "2026-09-16")}
    board.night("2026-09-17")
    assert {d: dict(board.db.report(d)["book"]) for d in ("2026-09-15", "2026-09-16")} == before


def test_open_trade_is_excluded_then_counted_exactly_once_when_it_closes(board):
    board.trades["ENGUQ_335"] = [_trade("2026-09-15 10:00", "2026-09-15 16:09", 800, open_=True, key="ENGUQ_335")]
    board.night("2026-09-15")
    r = board.db.report("2026-09-15")["legs"]["ENGUQ_335"]
    assert r["pnl_usd"] == 0.0 and r["open_n"] == 1 and r["open_pnl_usd"] == 800.0      # a labelled mark, no day
    d = next(iter(board.db.trade_docs("ENGUQ_335").values()))
    assert d["open"] is True and d["close_day"] is None
    # it moves overnight and closes the next afternoon at +1200
    board.trades["ENGUQ_335"] = [_trade("2026-09-15 10:00", "2026-09-16 14:00", 1200, key="ENGUQ_335")]
    board.night("2026-09-16")
    assert _leg_pnl(board.db, "2026-09-15", "ENGUQ_335") == 0.0
    assert _leg_pnl(board.db, "2026-09-16", "ENGUQ_335") == 1200.0
    assert board.db.report("2026-09-16")["legs"]["ENGUQ_335"]["open_n"] == 0
    board.night("2026-09-17")
    total = sum(_leg_pnl(board.db, d, "ENGUQ_335") for d in ("2026-09-15", "2026-09-16", "2026-09-17"))
    assert total == 1200.0                                        # once, not twice
    d = next(iter(board.db.trade_docs("ENGUQ_335").values()))
    assert d["open"] is False and d["close_day"] == "2026-09-16" and d["pnl_usd"] == 1200.0


def test_weekend_exit_is_counted_on_the_monday_report(board):
    board.trades["ENGUQ_335"] = [_trade("2026-09-18 15:00", "2026-09-20 19:30", 640, key="ENGUQ_335")]
    board.night("2026-09-18")
    board.night("2026-09-21")
    assert _leg_pnl(board.db, "2026-09-18", "ENGUQ_335") == 0.0
    assert _leg_pnl(board.db, "2026-09-21", "ENGUQ_335") == 640.0
    d = next(iter(board.db.trade_docs("ENGUQ_335").values()))
    assert d["exit_date"] == "2026-09-20" and d["close_day"] == "2026-09-21"


def test_book_weights_are_applied_by_exit_day_and_the_shadow_lines_follow(board):
    from api import book_shadow
    board.trades["ORB"] = [_trade("2026-09-15 09:40", "2026-09-15 11:00", 100, key="ORB")]
    board.trades["ENGUQ_335"] = [_trade("2026-09-14 22:00", "2026-09-15 09:50", 1000, key="ENGUQ_335")]
    board.trades["TTM_299_SSOF2"] = [_trade("2026-09-14 10:00", "2026-09-15 15:30", 50, key="TTM_299_SSOF2")]
    board.trades["NOISE_422"] = [_trade("2026-09-15 10:00", "2026-09-15 14:00", -20, key="NOISE_422")]
    board.night("2026-09-15")
    rep = board.db.report("2026-09-15")
    assert rep["book"]["weights"] == BOOK_W
    assert rep["book"]["pnl_usd"] == 100 + 1000 + 3 * 50 - 20       # ORB 1, ENGUQ_335 1, TTM 3, NOISE 1
    assert rep["book_shadow_vt"]["pnl_usd"] == 2.0 * rep["book"]["pnl_usd"]
    expect_q4 = sum(float(rep["legs"].get(k, {}).get("pnl_usd", 0.0)) * w
                    for k, w in book_shadow.SUM_SHADOWS["book_shadow_q4"]["weights"].items())
    assert rep["book_shadow_q4"]["pnl_usd"] == expect_q4
    # the TTM trade ENTERED on 09-14 but its money is on 09-15, the day it closed; 09-14 carries none
    board.night("2026-09-16")
    assert board.db.report("2026-09-15")["book"]["pnl_usd"] == 1230.0
    assert board.db.report("2026-09-16")["book"]["pnl_usd"] == 0.0


def test_a_leg_whose_run_failed_never_zeroes_stored_history(board, monkeypatch):
    board.trades["ENGUQ_335"] = [_trade("2026-09-15 10:00", "2026-09-15 13:00", 500, key="ENGUQ_335")]
    board.night("2026-09-15")
    real = paper.run_shadow

    def flaky(leg, d):
        if leg["key"] == "ENGUQ_335":
            return {"trades": [], "ungated_trades": [], "gate": None, "bars_appended": 0,
                    "data_fresh_thru": None, "warnings": ["exception in run_shadow(ENGUQ_335)"], "ran_ok": False}
        return real(leg, d)

    monkeypatch.setattr(paper, "run_shadow", flaky)
    board.night("2026-09-16")
    assert _leg_pnl(board.db, "2026-09-15", "ENGUQ_335") == 500.0
    assert board.db.report("2026-09-15")["book"]["pnl_usd"] == 500.0


def test_rebucket_payload_only_touches_what_the_doc_already_has_and_what_changed():
    old = {"legs": {"ORB": {"pnl_usd": 10.0, "n_signals": 1}, "NEWLEG": {"pnl_usd": 7.0}},
           "blend": {"pnl_usd": 10.0}, "book": {"pnl_usd": 10.0, "weights": {"ORB": 1.0, "ENGUQ_335": 1.0}},
           "book_shadow_vt": {"pnl_usd": 15.0, "multiplier": 1.5}}
    p = xd.rebucket_payload(old, {"ORB": {"2026-09-15": 10.0}, "ENGUQ_335": {"2026-09-15": 40.0}}, "2026-09-15")
    # ENGUQ_335 is not a leg of that doc: its trades are not added to the book (same rule as the nightly run)
    assert p is None
    old["legs"]["ENGUQ_335"] = {"pnl_usd": 0.0}
    p = xd.rebucket_payload(old, {"ORB": {"2026-09-15": 10.0}, "ENGUQ_335": {"2026-09-15": 40.0}}, "2026-09-15")
    assert p["legs"] == {"ENGUQ_335": {"pnl_usd": 40.0}}
    assert p["book"] == {"pnl_usd": 50.0} and p["book_shadow_vt"] == {"pnl_usd": 75.0}
    assert "NEWLEG" not in p["legs"] and "blend" not in p
