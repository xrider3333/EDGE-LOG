"""BOOKS toggle (owner 11-19): api/books_toggle.py + its hook in api/qqq_exec.py + the index.html mirror."""
import json
import os
import re

import pytest

from api import books_toggle as bt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _step(tmp_path, doc=None, *, mode="PAPER", flat=True, boot=True, mem=None, read=None,
          says=None, pubs=None, now=1000.0):
    says = [] if says is None else says
    pubs = [] if pubs is None else pubs
    return bt.step(out_dir=str(tmp_path), read_doc=read or (lambda: doc), broker_mode=mode,
                   flat=flat, boot=boot, mem={} if mem is None else mem, now=now,
                   say=lambda rec, line: says.append(line), publish=pubs.append,
                   log=lambda *a: None)


GOOD = {"legs": {"NOISE382": "OFF", "ORB314": "PAPER", "GLDNIGHT": "SHADOW"}, "by": "page",
        "ts": "2026-11-19T15:00:00Z"}


def test_unreadable_doc_changes_nothing(tmp_path):
    bt.save_applied(str(tmp_path), {"legs": {"ORB314": "PAPER"}, "legs_off": []})
    before = open(bt.applied_path(str(tmp_path))).read()

    def boom():
        raise RuntimeError("firestore down")
    assert _step(tmp_path, read=boom) == "unreadable"
    assert _step(tmp_path, {"legs": "garbage"}) == "invalid"
    assert _step(tmp_path, {"legs": {"NOISE382": "OFF", "NOPE": "OFF"}}) == "invalid"
    assert _step(tmp_path, None) == "no doc"
    assert open(bt.applied_path(str(tmp_path))).read() == before


def test_non_paper_mode_refuses(tmp_path):
    for mode in ("LIVE", "OFF", None, "SHADOW"):
        assert _step(tmp_path, GOOD, mode=mode).startswith("refused")
    assert bt.load_applied(str(tmp_path)) is None


def test_only_flat_moments_apply(tmp_path):
    assert _step(tmp_path, GOOD, flat=False, boot=True) == "not flat"
    assert _step(tmp_path, GOOD, flat=False, boot=False) == "not flat"
    assert bt.load_applied(str(tmp_path)) is None
    mem = {}
    says, pubs = [], []
    assert _step(tmp_path, GOOD, mem=mem, says=says, pubs=pubs) == "applied"
    assert len(says) == 1 and len(pubs) == 1 and pubs[0]["applied_by"] == "page"
    # flat again soon after: throttled (one doc read per READ_EVERY_SEC, never per tick)
    assert _step(tmp_path, GOOD, boot=False, mem=mem, now=1000.0 + 5) == "throttled"
    assert _step(tmp_path, GOOD, boot=False, mem=mem, now=1000.0 + bt.READ_EVERY_SEC + 1) == "same"


def test_greyed_and_gated_legs_cannot_be_paper():
    for leg in ("TTMx3", "OPUS55a", "OPUS107a", "TTIBS300", "OPUS58c", "GLDNIGHT", "NOISE422",
                "ORB234", "ENGUQ407", "PICK6", "OPUS86a"):
        assert not bt.allowed(leg, "PAPER"), leg
        ok, _, why = bt.validate({"legs": {leg: "PAPER"}})
        assert not ok and "not allowed" in why
    for leg in ("OPUS55a", "OPUS107a", "TTIBS300", "OPUS58c", "TTMx3"):
        assert not bt.allowed(leg, "SHADOW")
    assert bt.allowed("PICK6", "PAPER", gates={"pick6": True})
    assert bt.allowed("ORB314", "PAPER") and bt.allowed("NOISE382", "PAPER")


def test_every_published_leg_is_classified():
    p = r"C:/EdgeLog/manager/open_board/book_legs.json"
    if not os.path.exists(p):
        pytest.skip("book_legs.json not on this machine")
    d = json.load(open(p, encoding="utf-8"))
    ids = {l["id"] for b in d["books"].values() for l in b["legs"]}
    assert ids <= set(bt.BOOK_LEG_CLASS), ids - set(bt.BOOK_LEG_CLASS)
    assert len(d["books"]) >= 12


def _js_table():
    html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    m = re.search(r"const BOOKS_LEG_CLASS=\{(.*?)\n\};", html.replace("\r\n", "\n"), re.S)
    assert m, "BOOKS_LEG_CLASS not in index.html"
    rows = {}
    for line in m.group(1).strip().splitlines():
        lm = re.match(r"\s*(\w+):\{cls:'(\w+)',max:'(\w+)',exec_leg:(null|'(\w+)'),reason:'([^']*)'", line)
        assert lm, line
        rows[lm.group(1)] = {"cls": lm.group(2), "max": lm.group(3), "exec_leg": lm.group(5),
                             "reason": lm.group(6)}
    g = re.search(r"const BOOKS_GATES=\{(.*?)\};", html).group(1)
    gates = {k: v == "true" for k, v in re.findall(r"(\w+):(true|false)", g)}
    return rows, gates


def test_python_and_js_tables_agree():
    rows, gates = _js_table()
    assert gates == bt.GATES
    assert set(rows) == set(bt.BOOK_LEG_CLASS)
    for k, c in bt.BOOK_LEG_CLASS.items():
        assert rows[k] == {x: c[x] for x in ("cls", "max", "exec_leg", "reason")}, k


def test_applied_file_round_trip_and_load_config(tmp_path, monkeypatch):
    assert _step(tmp_path, GOOD) == "applied"
    rec = bt.load_applied(str(tmp_path))
    assert rec["legs"] == GOOD["legs"] and rec["legs_off"] == ["NOISE"]
    assert rec["src_ts"] == GOOD["ts"] and rec["applied_ts"].endswith("Z")
    assert "record only" in rec["effects"]["GLDNIGHT"]
    assert bt.applied_legs_off(str(tmp_path)) == ["NOISE"]
    from api import qqq_exec as qe
    cfg = qe.load_config(path=str(tmp_path / "config.json"), log=lambda *a: None)
    assert cfg["shares"]["NOISE"] == 0 and cfg["shares"]["ORB"] > 0
    # PAPER back on: NOISE leaves the toggle's legs_off (config.json's own legs_off is untouched)
    doc2 = dict(GOOD, legs={"NOISE382": "PAPER"}, ts="2026-11-19T16:00:00Z")
    assert _step(tmp_path, doc2) == "applied"
    cfg = qe.load_config(path=str(tmp_path / "config.json"), log=lambda *a: None)
    assert cfg["shares"]["NOISE"] > 0


def test_qqq_exec_hook_reads_once_and_never_when_open(tmp_path, monkeypatch):
    from api import qqq_exec as qe
    reads = []

    class Snap:
        exists = True

        def to_dict(self):
            reads.append(1)
            return dict(GOOD)

    class Ref:
        def __init__(self, name):
            self.name = name

        def get(self):
            return Snap()

        def set(self, rec):
            reads.append(("set", self.name))

        def collection(self, *_):
            return self

        def document(self, name):
            return Ref(name)

    class DB(Ref):
        def __init__(self):
            super().__init__("root")

    class Ad:
        def effective_mode(self):
            return ("PAPER", "")
    monkeypatch.setattr(qe, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: Ad())
    monkeypatch.setattr(qe, "_say", lambda *a, **k: (None, None))
    monkeypatch.setattr(qe, "_BOOKS_TOGGLE_MEM", {})
    state = {"legs": {"ORB": {"shares_remaining": 5}}}
    assert qe._books_toggle_step(DB(), "u", state, log=lambda *a: None, now=1.0) == "not flat"
    assert reads == []
    assert qe._books_toggle_step(DB(), "u", {"legs": {}}, log=lambda *a: None, now=2.0) == "applied"
    assert qe._books_toggle_step(DB(), "u", {"legs": {}}, log=lambda *a: None, now=3.0) == "throttled"
    assert reads.count(1) == 1 and ("set", "books_toggle_applied") in reads


def test_absent_doc_or_first_boot_leaves_legs_off_identical(tmp_path):
    from api import qqq_exec as qe
    cfgp = tmp_path / "config.json"
    cfgp.write_text(json.dumps({"legs_off": ["ORB"]}))
    before = qe.load_config(path=str(cfgp), log=lambda *a: None)["shares"]
    assert _step(tmp_path, None) == "no doc"                       # no books_toggle doc
    assert _step(tmp_path, {"legs": {}}, mem={}) == "applied"       # doc with every leg missing
    assert bt.load_applied(str(tmp_path))["legs_off"] == []
    after = qe.load_config(path=str(cfgp), log=lambda *a: None)["shares"]
    assert after == before and after["ORB"] == 0 and after["NOISE"] > 0


def test_shadow_on_exec_leg_means_no_orders(tmp_path):
    assert _step(tmp_path, dict(GOOD, legs={"ORB314": "SHADOW"}, ts="x2")) == "applied"
    rec = bt.load_applied(str(tmp_path))
    assert rec["legs_off"] == ["ORB"]
    assert rec["effects"]["ORB314"] == "SHADOW: no orders, signal on the shadow board"


def test_invalid_doc_one_line_per_ts_and_invalid_echo(tmp_path):
    mem, says, pubs = {}, [], []
    bad = {"legs": {"NOPE": "OFF"}, "ts": "t9"}
    assert _step(tmp_path, bad, mem=mem, says=says, pubs=pubs) == "invalid"
    assert _step(tmp_path, bad, mem=mem, says=says, pubs=pubs, now=5000.0) == "invalid"
    assert len(says) == 1 and len(pubs) == 1
    assert pubs[0]["status"] == "invalid" and "unknown leg" in pubs[0]["reason"] and pubs[0]["src_ts"] == "t9"
    assert bt.load_applied(str(tmp_path)) is None          # nothing applied
    bad2 = dict(bad, ts="t10")
    assert _step(tmp_path, bad2, mem=mem, says=says, pubs=pubs, now=9000.0) == "invalid"
    assert len(says) == 2
