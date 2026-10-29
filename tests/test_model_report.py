import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import model_report as mr  # noqa: E402


def test_grade_takes_last_number_with_tolerance():
    assert mr.grade("working 0.52*1.2 ...\n0.144", 0.144)
    assert mr.grade("balance\n$9,801.00", 9801.0)
    assert not mr.grade("I think 25%\nfinal 24", 25.0)
    assert not mr.grade("no number", 1.0)


def test_eleven_questions():
    assert len(mr.Q) == 11


def test_score_and_render_with_fake_model():
    keys = iter([str(w) for _, w in mr.Q])
    def gen(p, n):
        if "site source" in p:
            return "tabs", 10, 1.0, 20000, 40.0
        return next(keys), 100, 2.0, 50, 0.1
    r = mr.score("3.fake", gen)
    assert r["score"] == 11 and r["write_tps"] == 50.0 and r["read_tps"] == 500
    md = mr.render([r, {"model": "4.STRATA", "skipped": "before 13:00 MST (owner rule)"}], datetime.datetime(2026, 10, 29, 9, 0))
    assert "| 3.fake | 11/11 | 50.0 | 500" in md and "before 13:00" in md
