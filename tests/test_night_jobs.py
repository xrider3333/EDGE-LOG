import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import night_jobs as NJ  # noqa: E402


def test_schedule():
    assert NJ.jobs_for(datetime.date(2026, 11, 2)) == ["J1", "J3", "J5"]   # Mon, 1st weekday of Nov
    assert NJ.jobs_for(datetime.date(2026, 11, 4)) == ["J2", "J3"]
    assert NJ.jobs_for(datetime.date(2026, 11, 6)) == ["J3", "J4"]
    assert NJ.jobs_for(datetime.date(2026, 11, 7)) == []


def test_job_text_and_body(tmp_path, monkeypatch):
    md = tmp_path / "nj.md"
    md.write_text("# x\n## Shared guard text\n> no main\n\n## J3 flaky tests (nightly)\n> run 3x\n", encoding="utf-8")
    monkeypatch.setattr(NJ, "JOBS_MD", str(md))
    monkeypatch.setattr(NJ.job_text, "__defaults__", (str(md),))
    g, p = NJ.job_text("J3")
    assert g == "no main" and p == "run 3x"
    b = NJ.body("J3", "x" * (NJ.MAX_RAW + 5), "2026-11-02")
    assert "night/j3-2026-11-02" in b and "cut at" in b and "## RESULT" in b


def test_run_files_task_and_pr_skips_open(tmp_path, monkeypatch):
    monkeypatch.setenv("QWEN_TASKS_DIR", str(tmp_path))
    monkeypatch.setattr(NJ, "STATE", str(tmp_path / "st.json"))
    monkeypatch.setitem(NJ.RUN, "J4", lambda: "raw lint")
    monkeypatch.setattr(NJ, "body", lambda j, raw, d: raw)
    NJ.cmd_run(["J4"], False, "2026-11-06")
    st = NJ.load_state()
    assert st["tasks"][0]["job"] == "J4" and st["tasks"][0]["pushed"] is None
    NJ.cmd_pr(False)                       # task still open -> nothing pushed
    assert NJ.load_state()["tasks"][0]["pushed"] is None
