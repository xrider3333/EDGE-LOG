import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import weekly_cleanup as wc  # noqa: E402


class _R:
    def __init__(self, out):
        self.stdout, self.returncode = out, 0


LIST = """NAME                        ID              SIZE     MODIFIED
2.qwen3.6:35b-128k          d7845d001024    22 GB    7 hours ago
3.qwen3.6:35b-32k           8c1a39010903    22 GB    12 hours ago
1.qwen3.8:27b-48k           4d23a8b17063    12 GB    12 hours ago
5-qwen3.6-coding:35b-32k    8c1a39010903    22 GB    2 days ago
old-model:7b                aaaaaaaaaaaa    4 GB     9 days ago
"""


def test_models_skip_owner_models_and_flag_unused_and_twins(monkeypatch, tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "x.py").write_text('MODEL = "3.qwen3.6:35b-32k"\n', encoding="utf-8")
    monkeypatch.setattr(wc, "REPO", str(tmp_path))
    monkeypatch.setattr(wc.subprocess, "run", lambda *a, **k: _R(LIST))
    rows = {r["tag"]: r for r in wc.models()}
    assert "1.qwen3.8:27b-48k" not in rows and "2.qwen3.6:35b-128k" not in rows
    assert "3.qwen3.6:35b-32k" not in rows                      # named in code
    assert rows["5-qwen3.6-coding:35b-32k"]["size"] == 0 and "same weights" in rows["5-qwen3.6-coding:35b-32k"]["why"]
    assert rows["old-model:7b"]["size"] == 4e9


def test_scratch_lists_only_old_matching_files(monkeypatch, tmp_path):
    monkeypatch.setattr(wc, "HOME", str(tmp_path))
    old, new, live = tmp_path / "_ship_x.log", tmp_path / "_ship_y.log", tmp_path / "state.json"
    for f in (old, new, live):
        f.write_text("x" * 10)
    t = (datetime.datetime.now() - datetime.timedelta(days=30)).timestamp()
    os.utime(old, (t, t))
    os.utime(live, (t, t))
    paths = [r["path"] for r in wc.scratch(14, datetime.datetime.now())]
    assert paths == [str(old)]


def test_report_never_deletes(monkeypatch, tmp_path):
    monkeypatch.setattr(wc, "worktrees", lambda d, n, s: ([{"path": "A", "age_d": 20, "dirty": False, "merged": True, "size": 1}],
                                                         [{"path": "B", "age_d": 30, "dirty": True, "merged": False, "size": 1}]))
    monkeypatch.setattr(wc, "scratch", lambda d, n: [])
    monkeypatch.setattr(wc, "models", lambda: None)
    text = wc.report(14, datetime.datetime(2026, 10, 28), size=False)
    assert "Nothing was deleted" in text and "- A - 20 d" in text
    assert "- B - 30 d, uncommitted changes, commits not on main" in text
    assert "ollama not reachable" in text
