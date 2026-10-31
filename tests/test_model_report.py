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
        if p == mr.TRAP_UNIT[0]:
            return "3.5 points x 2 x $5 = 35.00", 100, 2.0, 50, 0.1
        if p == mr.TRAP_TZ[0]:
            return "14:30 GMT is 10:30 ET", 100, 2.0, 50, 0.1          # the Q4 mistake: ET given, MST asked
        return next(keys), 100, 2.0, 50, 0.1
    r = mr.score("3.fake", gen)
    assert r["score"] == 11 and r["write_tps"] == 50.0 and r["read_tps"] == 500
    assert r["trap_unit"] is True and r["trap_tz"] is False
    md = mr.render([r, {"model": "1.STRATA qwen3.8-flash:125b-256k", "skipped": "before 13:00 MST (owner rule)"}], datetime.datetime(2026, 10, 29, 9, 0))
    assert "| Model | 11 hard Qs | Unit trap | TZ trap |" in md
    assert "| 3.fake | 11/11 | ok | MISS | 50.0 | 500" in md and "| - | - | - | - | - | before 13:00" in md


def test_two_traps_and_their_graders():
    assert len(mr.TRAPS) == 2
    assert mr.grade("in points: 3.5; dollars: 35.00", 35.0) and not mr.grade("7 points, 7", 35.0)
    assert mr.grade_time("14:30 GMT -> 07:30 MST, so 07:30", "07:30") and mr.grade_time("7:30", "07:30")
    assert not mr.grade_time("10:30", "07:30") and not mr.grade_time("08:30 MDT", "07:30") and not mr.grade_time("no time", "07:30")


def test_dry_lists_traps_without_calling_a_model(monkeypatch, capsys):
    monkeypatch.setattr(mr, "ollama_models", lambda: ["3.fake"])
    monkeypatch.setattr(mr, "ollama_gen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("model called")))
    monkeypatch.setattr(mr, "strata_gen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("model called")))
    assert mr.main(["--dry"]) == 0
    out = capsys.readouterr().out
    assert "3.fake" in out and "2 traps" in out and "trap_unit -> 35.0" in out and "trap_tz -> 07:30" in out
    def down():
        raise OSError("no ollama")
    monkeypatch.setattr(mr, "ollama_models", down)
    assert mr.main(["--dry"]) == 0 and "ollama not answering" in capsys.readouterr().out
