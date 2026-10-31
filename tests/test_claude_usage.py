#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C24: claude_usage.py - dollars per model, 7-day trend, the short status line.

What these hold onto:
  * a model id is priced by its OWN row - Fable is not Opus money, Haiku 5.5 is not Haiku 4.5 money;
    an unknown id falls back to the default model's price instead of crashing;
  * each assistant message is counted once even when the transcript repeats it;
  * the 7-day table carries the 7d avg and today-vs-avg for every chat and for ALL;
  * the status line is one short line and never dies on empty stdin or a missing cache.
"""
import datetime as dt
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import claude_usage as cu  # noqa: E402


def _u(inp=0, out=0, cw=0, cr=0):
    return {"input_tokens": inp, "output_tokens": out, "cache_creation_input_tokens": cw, "cache_read_input_tokens": cr}


def test_prices_follow_the_model_id():
    one_m_out = _u(out=1_000_000)
    assert cu.dollars("claude-fable-5-1", one_m_out) == 50
    assert cu.dollars("claude-opus-5-5", one_m_out) == 20
    assert cu.dollars("claude-opus-5", one_m_out) == 25
    assert cu.dollars("claude-opus-4-8", one_m_out) == 25
    assert cu.dollars("claude-sonnet-5-5", one_m_out) == 10
    assert cu.dollars("claude-haiku-5-5", one_m_out) == 0.5
    assert cu.dollars("claude-haiku-4-5", one_m_out) == 5
    # unknown / missing model -> default price, no crash
    assert cu.dollars("something-new", one_m_out) == cu.dollars("claude-opus-5-5", one_m_out)
    assert cu.dollars(None, one_m_out) == cu.DEFAULT_PRICE[1]


def test_cache_tokens_are_priced_too():
    assert abs(cu.dollars("claude-opus-5-5", _u(inp=1e6, cw=1e6, cr=1e6)) - (4 + 5 + 0.2)) < 1e-9
    assert cu.dollars("claude-opus-5-5", _u()) == 0


def test_vs_avg_and_trend():
    assert cu.vs_avg(0, 0) == "n/a"
    assert cu.vs_avg(5, 4) == "+25%"
    assert cu.vs_avg(3, 4) == "-25%"
    t = cu.trend([0, 1, 2, 4])
    assert len(t) == 4 and t[0] == "_" and t[-1] == "@"


def _write_transcript(folder, sid, title, lines):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, sid + ".jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "custom-title", "customTitle": title}) + "\n")
        for ln in lines:
            f.write(json.dumps(ln) + "\n")


def _asst(mid, model, usage, when):
    return {"type": "assistant", "sessionId": None, "timestamp": when,
            "message": {"id": mid, "model": model, "usage": usage}}


def test_write_md_counts_each_message_once_and_prints_the_week(tmp_path, monkeypatch):
    now = dt.datetime.now().astimezone()
    today = now.isoformat()
    yesterday = (now - dt.timedelta(days=1)).isoformat()
    proj = tmp_path / "projects" / "p1"
    _write_transcript(str(proj), "s1", "Relay lane", [
        _asst("m1", "claude-haiku-5-5", _u(out=1000), today),
        _asst("m1", "claude-haiku-5-5", _u(out=1000), today),  # streamed repeat - counted once
        _asst("m2", "claude-haiku-5-5", _u(out=1000), yesterday),
    ])
    _write_transcript(str(proj), "s2", "Fable | lane", [
        _asst("m3", "claude-fable-5-1", _u(out=1000), today),
    ])
    monkeypatch.setattr(cu, "PROJECTS", str(tmp_path / "projects"))
    monkeypatch.setattr(cu, "OUT", str(tmp_path / "usage.md"))
    monkeypatch.setattr(cu, "CACHE", str(tmp_path / "cache.json"))
    cu.write_md(7)
    md = open(str(tmp_path / "usage.md"), encoding="utf-8").read()
    assert "| 7d avg $ |" in md and "Today vs avg" in md
    assert "Fable / lane" in md                       # pipes in titles are escaped
    rows, _ = cu.collect(7)
    day = dt.date.today().isoformat()
    s1 = rows[(day, "s1")]
    assert s1["msgs"] == 1 and s1["out"] == 1000     # duplicate message id dropped
    assert abs(cu.usd(s1) - 0.0005) < 1e-6           # Haiku 5.5: $0.50 per 1M out
    assert abs(cu.usd(rows[(day, "s2")]) - 0.05) < 1e-6
    cache = json.load(open(str(tmp_path / "cache.json")))
    assert len(cache["week_usd"]) == 7 and abs(cache["week_usd"][-1] - 0.0505) < 1e-6
    assert "**ALL**" in md and "n/a" not in md.split("**ALL**")[1].split("\n")[0]


def test_statusline_is_one_short_line():
    assert cu.statusline_text("Fable", 72, 0.4, 4.1, 3.6) == "Fable 72% | this chat $0.40 | $4.10 today | 7d avg $3.6"
    assert cu.statusline_text("", 0, 0, 0, 0) == "0% | this chat $0.00 | $0.00 today | 7d avg $0.0"


def test_statusline_survives_empty_stdin_and_no_cache(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cu, "PROJECTS", str(tmp_path / "none"))
    monkeypatch.setattr(cu, "CACHE", str(tmp_path / "missing.json"))
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    cu.statusline()
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1 and "7d avg $" in out[0] and "today" in out[0]
