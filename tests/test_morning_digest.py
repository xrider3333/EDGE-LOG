import datetime
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import chat_inbox  # noqa: E402
import morning_digest as md  # noqa: E402

NOW = datetime.datetime(2026, 10, 29, 5, 45)

BOARD = """# board
## WORK
- **item 3** [block] RESMOM real data pull | who: You | date: 2026-10-11
  - what: leave the PC on
  - statusText: NEEDS YOU 10-31
- **item 9** [done] NT8 keep running | who: NT8 chat | date: 2026-10-15
  - statusText: CONFIRMED
- **item 53** [run] Webull next trade | who: Webull chat | date: 2026-10-28
  - statusText: SHIPPING
- **test 32** [open] Some test | who: TV | date: 2026-10-20
"""


def _inbox(tmp_path, monkeypatch, rows):
    box = tmp_path / "inbox"
    box.mkdir()
    monkeypatch.setattr(chat_inbox, "BOX", str(box))
    with open(box / "PAPER-WB.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_facts_newest_first_done_hidden_ids_masked(tmp_path, monkeypatch):
    _inbox(tmp_path, monkeypatch, [
        {"id": 1, "at": "2026-10-01 09:00", "from": "MANAGER", "text": "old standing order", "status": "open"},
        {"id": 2, "at": "2026-10-28 20:00", "from": "MANAGER", "text": "acct 123456789 newer", "status": "open"},
        {"id": 3, "at": "2026-10-29 05:00", "from": "MANAGER", "text": "newest", "status": "open"},
        {"id": 4, "at": "2026-10-29 05:10", "from": "MANAGER", "text": "closed one", "status": "done"},
    ])
    b = tmp_path / "board.md"
    b.write_text(BOARD, encoding="utf-8")
    text = md.build("2026-10-29", NOW, use_model=False, board_path=str(b))
    assert "**PAPER-WB**: 3 open, 2 new in the last 24 h" in text
    assert text.index("#3 ") < text.index("#2 ")          # newest first
    assert "old standing order" not in text and "closed one" not in text
    assert "123456789" not in text and "<id>" in text
    assert "item 3: RESMOM real data pull - NEEDS YOU 10-31" in text
    assert "## Board: 3 row(s) not done" in text and "NT8 keep running" not in text
    assert "run: item 53" in text and "open: test 32" in text


def test_no_model_answer_says_why(tmp_path, monkeypatch):
    _inbox(tmp_path, monkeypatch, [])
    monkeypatch.setattr(md, "summarize", lambda t: (None, "Strata off; Ollama off"))
    text = md.build("2026-10-29", NOW, use_model=True, board_path=str(tmp_path / "missing.md"))
    assert "## Summary: none (Strata off; Ollama off)" in text
    assert "## Board: not found" in text


def test_model_text_marked_unverified_and_think_stripped(tmp_path, monkeypatch):
    _inbox(tmp_path, monkeypatch, [])
    monkeypatch.setattr(md, "summarize", lambda t: ("Ollama x", "<think>hidden</think>- look at item 3"))
    text = md.build("2026-10-29", NOW, use_model=True, board_path=str(tmp_path / "missing.md"))
    assert "## Summary (Ollama x, unverified" in text
    assert "hidden" not in text and "- look at item 3" in text


def test_main_writes_dated_and_latest(tmp_path, monkeypatch):
    _inbox(tmp_path, monkeypatch, [])
    monkeypatch.setattr(md, "BOARD", str(tmp_path / "missing.md"))
    assert md.main(["--no-model", "--date", "2026-10-29", "--out-dir", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out" / "digest-2026-10-29.md").exists()
    assert (tmp_path / "out" / "digest-latest.md").exists()
