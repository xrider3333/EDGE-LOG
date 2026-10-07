"""api/delta_alarm.py - live alarm for lost buy/sell classification, on synthetic CSVs in tmp_path.

The phone text is the one plain format of api/ntfy_push.py (2026-10-07): "Order flow: data gap" /
"Order flow: OK", "Trading: not affected.", the problem with one number, "Do: nothing", low priority,
times on the owner's Phoenix clock (NOW = 12:30 ET = 09:30 Phoenix). `push` receives (message, title, priority).
"""
import datetime as dt
from zoneinfo import ZoneInfo

from api import delta_alarm as DA
from api import ntfy_push as N

ET = ZoneInfo("America/New_York")
NOW = int(dt.datetime(2026, 10, 2, 12, 30, tzinfo=ET).timestamp())
HEADER = "time,open,high,low,close,volume,delta,buy_vol,sell_vol,tick_count,rt\n"


def _row(t, ok=True, rt=1, vol=10):
    bs = (6, 4) if ok else (0, 0)
    if rt == 3:
        bs = (0, 0)
    return "%d,100,101,99,100,%d,%d,%d,%d,5,%d\n" % (t, vol, bs[0] - bs[1], bs[0], bs[1], rt)


def _write(path, spec, end=NOW, header=True):
    """spec(i, t) -> (ok, rt) for bar i, bars every 10 s ending at `end`, 2 hours of them."""
    lines = [HEADER] if header else []
    n = 720
    for i in range(n):
        t = end - (n - 1 - i) * 10
        ok, rt = spec(i, t)
        lines.append(_row(t, ok, rt))
    path.write_text("".join(lines))
    return str(path)


LAST = []        # (title, priority) of every push the last _run made, same order as the messages


def _run(path, prior=None, now=NOW, out=None, instruments=("NQ",)):
    pushed = out if out is not None else []
    LAST.clear()

    def push(m, t, p):
        pushed.append(m)
        LAST.append((t, p))
        assert not N.lint({"title": t, "message": m, "priority": p}), N.lint({"title": t, "message": m, "priority": p})
    blk = DA.check(now, prior, push, instruments=instruments,
                   rows_for=lambda inst: DA.read_tail(str(path)))
    return blk, pushed


def test_healthy_is_silent(tmp_path):
    p = tmp_path / "NQ_10s.csv"
    _write(p, lambda i, t: (True, 1))
    blk, pushed = _run(p)
    assert pushed == [] and blk["NQ"]["alerted"] is False and blk["NQ"]["state"] == "ok"


def test_zero_coverage_alerts_once_with_text(tmp_path):
    p = tmp_path / "NQ_10s.csv"
    since = NOW - 1500  # unclassified from 24 min before now onward is not enough; use whole last 40 min
    cut = NOW - 40 * 60
    _write(p, lambda i, t: (t <= cut, 1 if t <= cut else 3))
    blk, pushed = _run(p)
    assert len(pushed) == 1
    m = pushed[0]
    assert LAST == [("Order flow: data gap", "low")]                     # no buzz: trading is not affected
    assert m.split("\n")[0] == "Trading: not affected."
    assert m.split("\n")[1] == "Order-flow data is missing on NQ since 08:50 (0% of bars have it)."   # 11:50 ET = 08:50 Phoenix
    assert m.split("\n")[2].startswith("Do: nothing")
    assert "ET" not in m.replace("NinjaTrader", "") and "rt=3" not in m and "tick" not in m.lower()
    assert blk["NQ"]["alerted"] is True and blk["NQ"]["last_push"] == NOW


def test_rt3_run_counts_as_unclassified_even_with_volume_split(tmp_path):
    p = tmp_path / "NQ_10s.csv"
    # rt=3 rows that (wrongly) carry a buy/sell split still count as missing
    lines = [HEADER]
    for i in range(720):
        t = NOW - (719 - i) * 10
        lines.append("%d,1,1,1,1,10,2,6,4,5,3\n" % t)
    p.write_text("".join(lines))
    blk, pushed = _run(p)
    assert len(pushed) == 1 and "(0% of bars have it)" in pushed[0]


def test_no_rt_column_still_works(tmp_path):
    p = tmp_path / "NQ_10s.csv"
    lines = ["%d,1,1,1,1,10,0,0,0,5\n" % (NOW - (719 - i) * 10) for i in range(720)]
    p.write_text("".join(lines))
    blk, pushed = _run(p)
    assert len(pushed) == 1 and "(0% of bars have it)" in pushed[0]


def test_partial_coverage_threshold(tmp_path):
    p = tmp_path / "NQ_10s.csv"
    _write(p, lambda i, t: (i % 5 != 0, 1))            # 80% classified: not below 80, silent
    assert _run(p)[1] == []
    _write(p, lambda i, t: (i % 4 == 0, 1))            # 25% classified
    blk, pushed = _run(p)
    assert len(pushed) == 1 and "(25% of bars have it)" in pushed[0]


def test_too_few_bars_skips(tmp_path):
    p = tmp_path / "NQ_10s.csv"
    lines = [HEADER] + [_row(NOW - k * 10, ok=False, rt=3) for k in range(20)]   # 20 bars only
    p.write_text("".join(lines))
    blk, pushed = _run(p)
    assert pushed == [] and blk["NQ"]["state"] == "skip"
    # zero-volume bars do not count either
    lines = [HEADER] + [_row(NOW - k * 10, ok=False, rt=3, vol=0) for k in range(200)]
    p.write_text("".join(lines))
    assert _run(p)[1] == []


def test_stale_file_is_not_this_alarms_job(tmp_path):
    p = tmp_path / "NQ_10s.csv"
    _write(p, lambda i, t: (False, 3), end=NOW - 6 * 3600)   # bars are 6 hours old
    blk, pushed = _run(p)
    assert pushed == [] and blk["NQ"]["state"] == "skip"


def test_missing_file_never_raises(tmp_path):
    blk = DA.check(NOW, None, lambda m, t, p: None, instruments=("NQ",),
                   rows_for=lambda inst: DA.read_tail(str(tmp_path / "nope.csv")))
    assert blk["NQ"]["state"] == "skip"


def test_rate_limit_two_hours_then_reminder(tmp_path):
    p = tmp_path / "NQ_10s.csv"
    _write(p, lambda i, t: (False, 3))
    blk, pushed = _run(p)
    assert len(pushed) == 1
    # 20 minutes later, still bad -> no second push
    later = NOW + 20 * 60
    _write(p, lambda i, t: (False, 3), end=later)
    blk2, pushed2 = _run(p, prior=blk, now=later)
    assert pushed2 == [] and blk2["NQ"]["alerted"] is True and blk2["NQ"]["last_push"] == NOW
    # just under a day -> still silent (two hours later is no longer enough); a day -> one reminder
    t1 = NOW + 24 * 3600 - 60
    _write(p, lambda i, t: (False, 3), end=t1)
    assert _run(p, prior=blk, now=t1)[1] == []
    t2 = NOW + 24 * 3600
    _write(p, lambda i, t: (False, 3), end=t2)
    blk3, pushed3 = _run(p, prior=blk, now=t2)
    assert len(pushed3) == 1 and blk3["NQ"]["last_push"] == t2


def test_recovery_after_15_clean_minutes_and_no_refire(tmp_path):
    p = tmp_path / "NQ_10s.csv"
    _write(p, lambda i, t: (False, 3))
    blk, pushed = _run(p)
    assert len(pushed) == 1
    # clean for the last 10 min only: no recovery yet, and no new alert
    now = NOW + 3600
    _write(p, lambda i, t: (t > now - 600, 1 if t > now - 600 else 3), end=now)
    blk2, pushed2 = _run(p, prior=blk, now=now)
    assert pushed2 == [] and blk2["NQ"]["alerted"] is True
    # clean for 16 min -> one recovery message; latch clears
    _write(p, lambda i, t: (t > now - 960, 1 if t > now - 960 else 3), end=now)
    blk3, pushed3 = _run(p, prior=blk, now=now)
    assert len(pushed3) == 1 and LAST == [("Order flow: OK", "low")]
    assert pushed3[0].split("\n")[1] == "Order-flow data is back on NQ (it was missing from 07:30); the gap stays empty."
    assert blk3["NQ"]["alerted"] is False
    # next pass (still inside the old 30-min window) must not re-alert
    blk4, pushed4 = _run(p, prior=blk3, now=now + 60)
    assert pushed4 == [] and blk4["NQ"]["alerted"] is False


def test_recovery_message_not_sent_without_prior_alert(tmp_path):
    p = tmp_path / "NQ_10s.csv"
    _write(p, lambda i, t: (True, 1))
    assert _run(p, prior={"NQ": {"alerted": False}})[1] == []


def test_tail_read_is_bounded_and_skips_torn_lines(tmp_path):
    p = tmp_path / "NQ_10s.csv"
    _write(p, lambda i, t: (True, 1))
    with open(p, "a") as f:
        f.write("123456,1,2")                          # torn final line
    rows = DA.read_tail(str(p), nbytes=4096)
    assert 0 < len(rows) < 150 and rows[-1][0] == NOW


def test_heartbeat_publish_hook_stores_state(monkeypatch):
    """publish() writes the delta_feed block into meta/nt_alert (check() stubbed, no files, no push)."""
    from api import nt_heartbeat as H
    seen = {}

    class Doc:
        def __init__(self, name): self.name = name
        def get(self):
            class R: exists = False
            return R()
        def set(self, rep): seen["rep"] = rep

    class Meta:
        def document(self, name): return Doc(name)

    class Col:
        def document(self, uid): return self
        def collection(self, name): return Meta()

    class DB:
        def collection(self, name): return Col()

    monkeypatch.setattr(DA, "check", lambda now, prior, push: {"NQ": {"alerted": False, "state": "ok"}})
    monkeypatch.setattr(H, "newest_tick_bar_epoch", lambda *a, **k: None)
    H.publish(DB(), "u1")
    assert seen["rep"]["delta_feed"]["NQ"]["state"] == "ok"


def test_nq_and_es_gap_in_the_same_pass_is_one_push(tmp_path):
    p = tmp_path / "NQ_10s.csv"
    _write(p, lambda i, t: (False, 3))
    blk, pushed = _run(p, instruments=("NQ", "ES"))
    assert len(pushed) == 1
    assert pushed[0].split("\n")[1].startswith("Order-flow data is missing on NQ and ES since ")
    assert blk["NQ"]["alerted"] and blk["ES"]["alerted"]


def test_gap_with_no_classified_bar_in_the_tail_says_or_earlier(tmp_path):
    p = tmp_path / "NQ_10s.csv"
    _write(p, lambda i, t: (False, 3))
    blk, pushed = _run(p)
    assert pushed[0].split("\n")[1] == "Order-flow data is missing on NQ since 07:30 or earlier (0% of bars have it)."
