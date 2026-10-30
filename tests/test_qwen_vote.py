import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import qwen_vote as qv  # noqa: E402


def test_parse_vote():
    assert qv.parse_vote("YES") == "YES"
    assert qv.parse_vote(" no.") == "NO"
    assert qv.parse_vote("Maybe") is None


def test_tally_majority_split_and_spoiled():
    assert qv.tally(["YES", "YES", "NO"])["label"] == "YES"
    t = qv.tally(["YES", "NO", None, None])
    assert t["label"] == "SPLIT" and t["spoiled"] == 2
    assert qv.tally([None, None, None])["label"] is None


def test_vote_redacts_and_counts_dead_calls():
    seen = []

    def ask(q, text, seed):
        seen.append(text)
        if seed == 2:
            raise OSError("router down")
        return "YES"
    r = qv.vote("q?", "ok line\napi_key = sk-abcdef1234567890abcdef\n", 3, ask)
    assert r["label"] == "YES" and r["yes"] == 2 and r["spoiled"] == 1
    assert "sk-abcdef" not in seen[0]


def test_items_lines_and_tail(tmp_path):
    f = tmp_path / "a.log"
    f.write_text("one\n\ntwo\nthree\n", encoding="utf-8")
    assert [t for _, t in qv.items([str(f)], lines=True)] == ["one", "two", "three"]
    assert qv.items([str(f)], tail=1)[0][1] == "three"
