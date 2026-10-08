"""tests/test_webull_freshness_keel_diffs.py -- the KEEL size-diff relay (MANAGER #76):
tools/webull_freshness.py copies the last 20 records of the engine's
cloud_signal/keel_size_diffs.jsonl into status.json "keel_diffs" (no verdict, no push), and
tools/webull_freshness_pc.py posts each record ONCE to the MANAGER and PAPER-WB inboxes
(deduped by date + leg + entry time, at-least-once through its pending-post queue).

Reuses the two monitors' own test harnesses (a fake box home; a fake ssh + inbox).
"""
import datetime as dt
import json
import os
import sys

import pytest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
for _p in (ROOT, THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import tools.webull_freshness as wf  # noqa: E402
import tools.webull_freshness_pc as pc  # noqa: E402
from test_webull_freshness import Home, MON_1030  # noqa: E402
from test_webull_freshness_pc import PC, MON_1100  # noqa: E402


@pytest.fixture(autouse=True)
def _no_ping(monkeypatch):
    monkeypatch.delenv("EDGELOG_FRESHNESS_PING_URL", raising=False)


def _diff(i, leg="NOISE_382", day="2026-10-06"):
    return {"date": day, "leg": leg, "entry_time": f"{day}T10:{i:02d}:00-04:00",
            "side": "long", "keel_size": 0.62, "keel_fixed_size": 1.5, "branch": "shade",
            "t_fast": -1.33, "trust": 0.0, "score": 0.38}


# -- box side ------------------------------------------------------------------------------
def test_status_carries_the_last_20_keel_diffs_and_pushes_nothing_for_them(tmp_path):
    h = Home(tmp_path, MON_1030)
    path = h.paths["keel_diffs"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for i in range(25):
            f.write(json.dumps(_diff(i)) + "\n")
        f.write('{"torn line\n')
    out = h.run()
    st = h.status()
    assert [d["entry_time"] for d in st["keel_diffs"]] == \
        [_diff(i)["entry_time"] for i in range(5, 25)]
    assert out["pushes"] == []
    assert not any("keel" in k.lower() and "diff" in k.lower() for k in st["verdicts"])


def test_status_keel_diffs_empty_without_the_file(tmp_path):
    h = Home(tmp_path, MON_1030)
    h.run()
    assert h.status()["keel_diffs"] == []
    assert wf.read_keel_diffs(str(tmp_path / "nope.jsonl")) == []


# -- PC side -------------------------------------------------------------------------------
def _keel_posts(p):
    return [(c, t) for c, t, _f in p.posts if "KEEL SIZE DIFF" in t]


def test_each_keel_diff_is_posted_once_to_both_inboxes(tmp_path):
    p = PC(tmp_path, MON_1100)
    p.ssh.status["keel_diffs"] = [_diff(5)]
    p.run()
    posts = _keel_posts(p)
    assert sorted(c for c, _t in posts) == sorted(pc.INBOXES)
    text = posts[0][1]
    assert "NOISE_382" in text and "10:05" in text and "0.62" in text and "1.50" in text
    assert "shade" in text and "-1.33" in text

    p.run(MON_1100 + dt.timedelta(minutes=10))                  # same status: nothing new
    assert len(_keel_posts(p)) == len(pc.INBOXES)

    p.ssh.status["keel_diffs"] = [_diff(5), _diff(35)]          # a new one: only it goes out
    p.run(MON_1100 + dt.timedelta(minutes=20))
    posts = _keel_posts(p)
    assert len(posts) == 2 * len(pc.INBOXES)
    assert all("10:35" in t and "10:05" not in t for _c, t in posts[len(pc.INBOXES):])


def test_keel_diff_post_survives_a_failed_inbox_and_is_not_duplicated(tmp_path):
    p = PC(tmp_path, MON_1100)
    p.ssh.status["keel_diffs"] = [_diff(5)]
    p.post_ok = False
    p.run()
    assert _keel_posts(p) == []
    p.post_ok = True
    p.run(MON_1100 + dt.timedelta(minutes=10))
    p.run(MON_1100 + dt.timedelta(minutes=20))
    assert sorted(c for c, _t in _keel_posts(p)) == sorted(pc.INBOXES)


def test_keel_diffs_not_relayed_on_a_failed_box_read_or_a_dry_run(tmp_path):
    p = PC(tmp_path, MON_1100)
    p.ssh.status["keel_diffs"] = [_diff(5)]
    p.ssh.fail = "rc"
    p.run()
    assert _keel_posts(p) == []
    p.ssh.fail = None
    out = p.run(MON_1100 + dt.timedelta(minutes=10), dry_run=True)
    assert "KEEL SIZE DIFF" in (out["text"] or "") and _keel_posts(p) == []
    p.run(MON_1100 + dt.timedelta(minutes=20))                  # the real run still posts it
    assert len(_keel_posts(p)) == len(pc.INBOXES)


def test_compose_keel_diffs_dedupes_and_skips_malformed():
    text, keys = pc.compose_keel_diffs([_diff(5), _diff(5), {"leg": "x"}, "junk"], [])
    assert keys == [pc.keel_diff_key(_diff(5))]
    assert text.count("NOISE_382") == 1
    assert pc.compose_keel_diffs([_diff(5)], keys) == (None, [])
