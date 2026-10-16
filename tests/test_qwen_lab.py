"""tools/qwen_lab.py - the QWEN LAB harness (owner 2026-10-15: the local Qwen as a strategy TESTER).

Offline: no test talks to Ollama (a scripted chat stands in), no test posts to MANAGER (a recording poster), no test
reads or writes Firestore (stub live-job lists), and every lab file goes to tmp_path. The SANDBOX tests spawn the real
sandbox subprocess on SYNTHETIC bars; they need the shared checkout's engine and skip without it.

Covers: the safety gate (malicious samples), the sandbox's second and third layers (guarded import, no open, the audit
hook, hash re-check, timeout), the perturbation look-ahead audit (it catches four leak shapes the static gate cannot see),
path confinement, dead-list refusal, prereg-before-run ordering, the hash re-check, the one-validate limit, the lockbox
assertion, that every reported number comes from Python, the closed shelf + shelf-open, GAMMA closed, the broken-plugin
sanity loop, net per trade in points, the push-lock load courtesy (read-only), and fix round 2: shelf-close (latest
open / close line wins), idea-level dedupe with the mechanism-family map, the first-signal-bar contract, the entry-bar
inputs phase of the look-ahead audit, and the one bar-index convention.
"""
import functools
import json
import os
import re
import sys

import numpy as np
import pandas as pd
import pytest

import augur_engine  # noqa: F401  - import the repo's engine first so the harness never touches sys.path in tests

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
sys.path.insert(0, TOOLS)
import qwen_lab as Q  # noqa: E402

HAVE_SHARED = os.path.isdir(os.path.join(Q.SHARED, "augur_engine"))
FSB0 = {"index": 0, "clock": "09:30"}          # first_signal_bar (TTM #144): bar 0 (09:30 open) - every entry allowed
needs_shared = pytest.mark.skipif(not HAVE_SHARED, reason="needs the shared checkout's engine (sandbox child)")


@pytest.fixture(autouse=True)
def _no_real_push_lock(tmp_path, monkeypatch):
    """The load-courtesy probe reads a path that does not exist - no test ever waits on a real ship's push lock."""
    monkeypatch.setenv("QWEN_LAB_PUSH_LOCK", str(tmp_path / "push.lock.absent"))


# ------------------------------------------------------------------------------------------------ the safety gate
def test_template_passes_the_gate():
    ok, reasons = Q.safety_gate(Q.TEMPLATE_PLUGIN)
    assert ok, reasons


MALICIOUS = {
    "import os": "import os\n",
    "import subprocess": "import subprocess\nsubprocess.run(['calc'])\n",
    "from os import system": "from os import system\n",
    "import numpy, os": "import numpy as np, os\n",
    "dunder import": "x = __import__('os')\n",
    "open for write": "def f():\n    open('x.txt', 'w').write('1')\n",
    "eval": "def f(s):\n    return eval(s)\n",
    "exec": "def f(s):\n    exec(s)\n",
    "compile": "def f(s):\n    return compile(s, 'a', 'exec')\n",
    "getattr on dunder": "import numpy as np\ndef f():\n    return getattr(np, 'lo' + 'ad')\n",
    "np.load": "import numpy as np\ndef f():\n    return np.load('x.npy', allow_pickle=True)\n",
    "np.save": "import numpy as np\ndef f(a):\n    np.save('C:/x.npy', a)\n",
    "pd.read_csv": "import pandas as pd\ndef f():\n    return pd.read_csv('C:/secrets.csv')\n",
    "df.to_csv": "import pandas as pd\ndef f(df):\n    df.to_csv('x.csv')\n",
    "df.to_pickle": "def f(df):\n    df.to_pickle('x.pkl')\n",
    "class bases walk": "def f():\n    return ().__class__.__bases__[0].__subclasses__()\n",
    "function globals": "def g():\n    pass\ndef f():\n    return g.__globals__\n",
    "generator frame": "def f():\n    g = (i for i in [1])\n    return g.gi_frame.f_globals\n",
    "builtins string": "def f(d):\n    return d['__builtins__']\n",
    "class with getattr": "class A:\n    def __getattr__(self, k):\n        return 1\n",
    "global statement": "X = 1\ndef f():\n    global X\n    X = 2\n",
    "attribute assignment (monkeypatch numpy)": "import numpy as np\ndef f():\n    np.cumsum = lambda a: a\n",
    "print": "def f():\n    print('ROC 999')\n",
    "importlib": "import importlib\n",
    "pickle": "import pickle\n",
    "socket": "import socket\n",
    "ctypes via ndarray": "import numpy as np\ndef f(a):\n    return a.ctypes.data\n",
    "np.lib": "import numpy as np\ndef f():\n    return np.lib.format.open_memmap('x.npy', mode='w+', shape=(3,))\n",
    "np.ctypeslib": "import numpy as np\nx = np.ctypeslib\n",
    "df.query": "def f(df):\n    return df.query('a > 1')\n",
    "pd.eval": "import pandas as pd\ndef f():\n    return pd.eval('1+1')\n",
    "private attribute": "import numpy as np\ndef f():\n    return np._core\n",
    "relative import": "from . import x\n",
    "star import": "from math import *\n",
    "module-level call": "import numpy as np\nnp.zeros(3)\n",
    "module-level loop": "for i in range(3):\n    pass\n",
    "breakpoint": "def f():\n    breakpoint()\n",
    "globals()": "def f():\n    return globals()\n",
    "vars()": "def f():\n    return vars()\n",
    "type() class factory": "def f():\n    return type('A', (), {})\n",
    "f-string dunder": "def f(x):\n    return f'{x.__class__}'\n",
    "sys": "import sys\n",
    "pathlib": "import pathlib\n",
    "requests": "import requests\n",
    "from numpy import load": "from numpy import load\n",
    "from augur_engine other": "from augur_engine.data import load_master_arrays\n",
    "async": "async def f():\n    pass\n",
    "bytes literal": "X = b'\\x00'\n",
    "dunder argument": "def f(__x):\n    return 1\n",
    "plot / savefig": "def f(df):\n    df.plot().figure.savefig('x.png')\n",
}


@pytest.mark.parametrize("label", sorted(MALICIOUS))
def test_safety_gate_refuses(label):
    ok, reasons = Q.safety_gate(MALICIOUS[label])
    assert not ok, "%s slipped through the gate" % label
    assert reasons and all(isinstance(r, str) for r in reasons)


def test_safety_gate_reasons_are_specific():
    ok, reasons = Q.safety_gate("import numpy as np\ndef f():\n    return np.load('x')\n")
    assert not ok and any(".load" in r for r in reasons)


def test_safety_gate_allows_ordinary_numerics():
    code = ("import numpy as np\nimport pandas as pd\nimport math\nfrom augur_engine.rolls import seam_days\n"
            "X = {'a': {'default': 1}}\n"
            "def f(o, h, l, c, day_id=None, _stop_event=None, **_ignore):\n"
            "    s = pd.Series(c).rolling(5).mean().to_numpy()\n"
            "    with np.errstate(divide='ignore', invalid='ignore'):\n"
            "        z = (np.asarray(c) - s) / np.nanstd(c[:5])\n"
            "    return [math.sqrt(abs(x)) for x in z[:3] if x == x]\n")
    ok, reasons = Q.safety_gate(code)
    assert ok, reasons


def test_clean_code_strips_a_markdown_fence():
    raw = "Here it is:\n```python\nimport math\nX = 1\n```\n"
    assert Q.clean_code(raw) == "import math\nX = 1\n"


# ------------------------------------------------------------------------------------------------ path confinement
@needs_shared
def test_read_repo_file_reads_inside_the_repo(tmp_path):
    lab = Q.Lab(home=str(tmp_path / "home"), plugin_repo=str(tmp_path / "repo"))
    r = Q.read_repo_file("augur_strategies/ORB_FADE_1_0.py", lab=lab)
    assert "STRATEGY_NAME" in r["text"] and r["lines_total"] > 50


@needs_shared
@pytest.mark.parametrize("path", [
    "../../Windows/win.ini", "..\\..\\x.py", "C:/Windows/win.ini", os.path.expanduser("~/x.txt"),
    "serviceAccount.json", ".env", "augur_engine/alpaca_keys.py", ".git/config", "firebase UID.txt",
    "optimizer_history.db", "augur_engine",
])
def test_read_repo_file_refuses(tmp_path, path):
    lab = Q.Lab(home=str(tmp_path / "home"), plugin_repo=str(tmp_path / "repo"))
    with pytest.raises(Q.ToolRefused):
        Q.read_repo_file(path, lab=lab)


def test_plugin_path_cannot_escape(tmp_path):
    lab = Q.Lab(home=str(tmp_path / "home"), plugin_repo=str(tmp_path / "repo"))
    s = Q.IdeaSession(lab, {"id": "t1", "shelf": {"n": 8}})
    for evil in ("../../evil", "..\\..\\evil", "C:/x/evil", "qwen_lab/../../x"):
        n = s._name(evil)
        assert n.startswith("QL_") and "/" not in n and "\\" not in n and ".." not in n
        assert Q.under(s.plugin_path(n), lab.plugin_dir)


def test_plugins_are_never_written_into_the_shared_checkout():
    with pytest.raises(SystemExit):
        Q.check_plugin_repo(Q.SHARED)


# ------------------------------------------------------------------------------------------------ dead list
LEDGER = """
| # | Tried | Source | Outcome |
|---|---|---|---|
| 2.13 | Overnight dealer-inventory drift (Boyarchenko 2023): long NQ 01:30->04:00 ET, alone and after a down day session | `x.py` | Real but tiny. **Dead for ROC**; holding 16:15->09:25 is the dead ONDRIFT |
| 2.61 | ATTN r1 (pre-registered): attention days on NQ | `y.py` | **DEAD at Stage A** - lockbox never read. |
| 2.70 | Round 4: something that passed | `z.py` | PASS, kept as a leg |
"""


def test_dead_rows_parse_only_closed_rows():
    rows = Q.dead_rows(LEDGER)
    assert [r["num"] for r in rows] == ["2.13", "2.61"]


def test_dead_check_refuses_a_clear_rerun():
    rows = Q.dead_rows(LEDGER)
    d = Q.dead_check("QL_OVERNIGHT_DOWN", "Dealer inventory drift lifts NQ overnight after a down session.",
                     "Long NQ from 01:30 to 04:00 ET after a down day session (dealer-inventory drift).", rows)
    assert d["refused"] and "2.13" in d["reason"]


def test_dead_check_refuses_a_closed_family_name():
    rows = Q.dead_rows(LEDGER)
    assert Q.dead_check("QL_ONDRIFT_V2", "a" * 30, "b" * 30, rows)["refused"]
    assert Q.dead_check("ATTN", "a" * 30, "b" * 30, rows)["refused"]


def test_dead_check_passes_a_new_idea():
    rows = Q.dead_rows(LEDGER)
    d = Q.dead_check("QL_TURNPT_NQ", "Slow and fast trend signals that disagree mark turning points.",
                     "Trade NQ open to close in the direction both daily trend speeds agree on; flat when they "
                     "disagree.", rows)
    assert not d["refused"], d


def test_propose_refuses_a_dead_idea_and_never_maps_early(tmp_path):
    lab = Q.Lab(home=str(tmp_path / "home"), plugin_repo=str(tmp_path / "repo"))
    maps = []
    s = Q.IdeaSession(lab, {"id": "t2", "shelf": {"n": 8}}, mapcheck=lambda *a: maps.append(a),
                      dead_rows_fn=lambda: Q.dead_rows(LEDGER))
    r = s.t_propose("QL_OVERNIGHT_DOWN", "Dealer inventory drift lifts NQ overnight after a down session.",
                    "Long NQ from 01:30 to 04:00 ET after a down day session (dealer-inventory drift).", 0.5, 120, "NQ",
                    first_signal_bar=FSB0)
    assert r["accepted"] is False and r["gate"] == "dead list" and not s.closed
    with pytest.raises(Q.ToolRefused):
        s.t_write_plugin("QL_OVERNIGHT_DOWN", Q.TEMPLATE_PLUGIN)
    r = s.t_propose("QL_NEW_THING", "A different idea about intraday reversals after gaps open.",
                    "Fade the first 15 minutes after a gap larger than its trailing median; exit at noon.", 0.4,
                    150, "NQ", first_signal_bar=FSB0)
    assert r["accepted"] is True and not maps          # the map runs inside run_stage_a, after the plugin gates


def test_propose_refuses_an_inflated_prior(tmp_path):
    lab = Q.Lab(home=str(tmp_path / "home"), plugin_repo=str(tmp_path / "repo"))
    s = Q.IdeaSession(lab, {"id": "t3", "shelf": {"n": 8}}, dead_rows_fn=lambda: [])
    with pytest.raises(Q.ToolRefused):
        s.t_propose("QL_X", "h" * 30, "m" * 30, 3.0, 200, "NQ")
    with pytest.raises(Q.ToolRefused):
        s.t_propose("QL_X", "h" * 30, "m" * 30, 0.5, 200, "CL")


# ------------------------------------------------------------------------------------------------ shelf
SHELF = """<script>
const THEMES={1:"x"};
const P=[
{n:7,t:"Paper seven",a:"A. One, B. Two",y:2016,v:"J",l:"https://x.org/a:b",th:2,st:"new",tag:"KEEL",p:1,
 s:"Summary: with a colon, and \\"quotes\\".",w:"why",r:"Not in the repo."},
{n:26,t:"Paper twenty-six",a:"C. Three",y:2012,v:"R",l:"u",th:6,st:"new",tag:"Order flow",p:2,s:"s",w:"w",r:"r"},
{n:5,t:"Dead paper",a:"D",y:2012,v:"J",l:"u",th:2,st:"dead",tag:"T",p:3,s:"s",w:"w",r:"r"}
];
const FIRST=[[7,"x"]];
</script>"""


def test_shelf_ideas_skip_live_dead_taken_and_ledger_rows(tmp_path):
    p = tmp_path / "shelf.html"
    p.write_text(SHELF, encoding="utf-8")
    ledger = "| 2.140 | BVC QA r1 (reading shelf No. 26: Easley) | s | **FAIL** |\n"
    got = Q.shelf_ideas([], shelf_path=str(p), ledger_text=ledger)
    assert [x["n"] for x in got] == [7]
    assert got[0]["summary"].startswith("Summary: with a colon")
    assert Q.shelf_ideas([7], shelf_path=str(p), ledger_text=ledger) == []
    allp = Q.shelf_ideas([7], shelf_path=str(p), ledger_text=ledger, include_taken=True)
    assert {x["n"]: x.get("excluded", "") for x in allp}[26].startswith("already in the ledger")


def test_shelf_paper_taken_when_the_ledger_cites_its_authors(tmp_path):
    p = tmp_path / "shelf.html"
    p.write_text(SHELF, encoding="utf-8")
    ledger = "| 2.131 | KEEL DECOMPOSITION (the owner's question from One-Two 2016 and Nagel 2025) | s | report |\n"
    assert [x["n"] for x in Q.shelf_ideas([], shelf_path=str(p), ledger_text=ledger)] == [26]


# ------------------------------------------------------------------------------------------------ the lockbox guard
def test_wf_window_ends_before_the_lockbox():
    assert Q.WF1 < Q.LB0 and Q.split_date() == Q.LB0


def test_assert_wf_only_refuses_lockbox_rows():
    ok = pd.date_range("2025-06-20 09:30", "2025-06-27 15:55", freq="5min", tz="US/Eastern")
    assert Q.assert_wf_only(ok) == "2025-06-27"
    bad = pd.date_range("2025-06-27 09:30", "2025-06-30 10:00", freq="5min", tz="US/Eastern")
    with pytest.raises(AssertionError, match="LOCKBOX"):
        Q.assert_wf_only(bad)


def test_four_numbers_refuses_arrays_reaching_the_lockbox():
    A = _arrays("2025-06-02", "2025-07-03")
    with pytest.raises(AssertionError, match="LOCKBOX"):
        Q.four_numbers([], A, 20.0)


# ------------------------------------------------------------------------------------------------ numbers from Python
def _arrays(d0="2016-06-01", d1="2017-06-30", per_day=4, seed=3):
    days = pd.bdate_range(d0, d1)
    rng = np.random.default_rng(seed)
    idx = []
    for d in days:
        for k in range(per_day):
            idx.append(pd.Timestamp(d) + pd.Timedelta(hours=10 + k))
    idx = pd.DatetimeIndex(idx).tz_localize("US/Eastern")
    n = len(idx)
    c = 5000 + rng.normal(0, 5, n).cumsum()
    o = c + rng.normal(0, 1, n)
    h = np.maximum(o, c) + 1
    l = np.minimum(o, c) - 1
    return {"open": o, "high": h, "low": l, "close": c, "volume": np.full(n, 100.0),
            "day_id": pd.factorize(pd.Series(idx).dt.date)[0], "index": idx, "fingerprint": "fp-test"}


def _intraday_trades(A, rng=None):
    rng = rng or np.random.default_rng(11)
    did = A["day_id"]
    out = []
    for d in np.unique(did)[::2]:
        ix = np.flatnonzero(did == d)
        e, x = int(ix[0]), int(ix[-1])
        out.append((e, x, float(rng.normal(1.0, 8.0)), 1, float(A["open"][e])))
    return out


def test_four_numbers_match_the_house_helpers_by_hand():
    from augur_engine import book_sizing, drawdowns
    A = _arrays()
    tr = _intraday_trades(A)
    nm = Q.four_numbers(tr, A, 20.0)
    sess = pd.DatetimeIndex(A["index"]).tz_localize(None).normalize()
    wf = [t for t in tr if sess[t[0]] >= pd.Timestamp(Q.WF0)]
    daily = pd.Series(0.0, index=pd.DatetimeIndex(sorted(set(sess[sess >= pd.Timestamp(Q.WF0)]))))
    for t in wf:
        daily.loc[sess[t[1]]] += t[2] * 20.0
    r = book_sizing.stretch_reading(daily, Q.WF0, Q.WF1)
    d5 = drawdowns.dd5(daily)
    assert nm["trades"] == len(wf) and nm["dropped_before_wf"] == len(tr) - len(wf)
    assert nm["roc_30k"] == r["roc_30k"] and nm["sortino"] == r["sortino"]
    assert nm["dd_pct_peak"] == r["dd_pct_peak"] and nm["dd5_usd"] == d5["dd5_usd"]
    assert nm["one_episode"] == d5["one_episode"] and "warning" not in nm


def test_four_numbers_value_multi_day_holds_daily():
    A = _arrays("2016-07-01", "2016-09-30")
    did = A["day_id"]
    e = int(np.flatnonzero(did == 2)[0])
    x = int(np.flatnonzero(did == 6)[-1])
    pnl = float(A["close"][x] - A["open"][e])
    nm = Q.four_numbers([(e, x, pnl, 1, float(A["open"][e]))], A, 20.0)
    assert nm["mtm_marked"] == 1 and abs(nm["net_usd"] - pnl * 20.0) < 0.006


def test_fmt_four_and_the_validate_bar_read_only_computed_numbers():
    nm = {"stretch": "WF", "roc_30k": 16.2, "dd5_usd": 20000.0, "dd5_n": 5, "one_episode": False,
          "dd_pct_peak": 12.5, "sortino": 1.5, "trades": 300, "trades_per_year": 33.3}
    assert Q.fmt_four(nm) == "ROC@30k 16.20 | DD5 $20,000 (n=5) | DD% 12.50% | Sortino 1.500 | trades 300 (33.3/yr)"
    assert Q.validate_bar(nm)[0]
    assert not Q.validate_bar(dict(nm, one_episode=True))[0]
    assert not Q.validate_bar(dict(nm, roc_30k=14.99))[0]
    assert not Q.validate_bar(dict(nm, trades=99))[0]
    assert not Q.validate_bar(nm, peak_gb=5.0)[0]
    assert Q.fmt_four(None).startswith("ROC@30k -")


# ------------------------------------------------------------------------------------------------ the session, end to end
class ScriptChat:
    """Stands in for Ollama: replays scripted assistant messages (native tool calls, or JSON-in-text)."""

    def __init__(self, script):
        self.script = list(script)
        self.seen = []

    def chat(self, messages, tools):
        self.seen.append(messages)
        if not self.script:
            return {"role": "assistant", "content": "done"}, {"secs": 0}
        item = self.script.pop(0)
        if isinstance(item, str):
            return {"role": "assistant", "content": item}, {"secs": 0}
        name, args = item
        return {"role": "assistant", "content": "ROC 999 and Sortino 99 - trust me",
                "tool_calls": [{"function": {"name": name, "arguments": args}}]}, {"secs": 0}


def _clears_map(name, s, n):
    return {"verdict": "CLEARS - worth a prereg", "clears": True, "own_wf_roc_median": 9.1, "p_own_roc_ge_15": 0.31,
            "p_lift_463": 0.44, "book_roc_median": 97.0, "prior": {"n": n, "s_mid": s}, "seed": [1, 2, 0],
            "draws": 2000}


_PRE_CACHE = {}


def _pre_arrays():
    """Synthetic bars over the whole PRE-WF window (2010-06-07..2016-06-30), two a session - no WF row."""
    if "A" not in _PRE_CACHE:
        P = _arrays(Q.PREWF0, Q.PREWF1, per_day=2, seed=4)
        P["fingerprint"] = "fp-pre"
        _PRE_CACHE["A"] = P
    return _PRE_CACHE["A"]


def _pre_trades(promote=True):
    """One trade a session on the PRE-WF bars: a set that clears the promotion bar, or a losing one."""
    key = "promote" if promote else "lose"
    if key not in _PRE_CACHE:
        P = _pre_arrays()
        did = P["day_id"]
        for seed in range(5, 80):
            rng = np.random.default_rng(seed)
            tr = []
            for d in np.unique(did):
                ix = np.flatnonzero(did == d)
                tr.append((int(ix[0]), int(ix[-1]), float(rng.normal(6.0, 4.0) if promote else rng.normal(-1.0, 6.0)),
                           1, float(P["open"][ix[0]])))
            ok = Q.promotion_bar(Q.four_numbers(tr, P, 20.0, wf0=Q.PREWF0, wf1=Q.PREWF1, label="PRE-WF"))[0]
            if ok == promote:
                break
        _PRE_CACHE[key] = tr
    return _PRE_CACHE[key]


class Harness:
    """Records the order of everything the session does to the outside world. Stage A answers from the PRE-WF data
    (pre=(arrays, trades); by default a set that clears the promotion bar) or the WF data (A, trades) by req['stretch']."""

    def __init__(self, A, trades, tamper=None, pre=None):
        self.A, self.trades, self.calls, self.posts, self.tamper = A, trades, [], [], tamper
        self.P, self.pre_trades = pre if pre is not None else (_pre_arrays(), _pre_trades(True))
        self.stretches = []

    def sandbox(self, mode, path, sha, req, workdir, timeout=None, label=None):
        self.calls.append(("sandbox", mode))
        if mode == "contract":
            fsb = req.get("first_signal_bar")
            return {"ok": True, "warnings": [], "smoke": {"trades": 223, "years": 1.49, "trades_per_year": 149.7},
                    "corners": [],
                    **({"first_signal_bar": {"first_signal_bar": fsb, "checked": 223, "n": 0,
                                             "earliest_session_bar": fsb, "index_by": "clock"},
                        "first_signal_bar_corners": []} if fsb is not None else {})}
        if mode == "lookahead":
            return {"ok": True, "warnings": [], "la_window": {"trades": 9}, "perturbed_trades": 8, "fills_checked": 18,
                    "entry_bar_checked": 6, "entry_bar_conclusive": 4, "entry_bar_corners": []}
        if mode == "stage_a":
            self.stretches.append((req.get("stretch"), req.get("load_from"), req.get("load_to")))
            A, tr = (self.P, self.pre_trades) if req.get("stretch") == "pre_wf" else (self.A, self.trades)
            return {"ok": True, "trades": [list(t) for t in tr], "bars": len(A["close"]), "stretch": req.get("stretch"),
                    "fingerprint": A["fingerprint"], "params": {}, "peak_gb": 0.2, "secs": 1.0}
        if mode == "guard":
            return {"ok": True, "verdict": "PASS", "reasons": []}
        raise AssertionError(mode)

    def poster(self, text):
        self.calls.append(("post", text[:40]))
        self.posts.append(text)
        if self.tamper:
            self.tamper()
        return len(self.posts)

    def loader(self, inst, tf, date_from=Q.DATA_FROM, date_to=Q.WF1):
        self.calls.append(("load", inst))
        A = self.P if date_to < Q.WF0 else self.A
        return {"filename": "NOADJ_NQ_5m_RTH.csv", "source": "db_noadj_rth", "id": 37}, A


def _no_queue(job):
    raise AssertionError("a test tried to queue a real job")


def _session(tmp_path, harness, **kw):
    lab = Q.Lab(home=str(tmp_path / "home"), plugin_repo=str(tmp_path / "repo"))
    os.makedirs(os.path.join(lab.plugin_repo, "augur_strategies"), exist_ok=True)
    idea = {"id": "t-idea", "shelf": {"n": 8, "title": "Momentum turning points", "authors": "C. Goulding, X",
                                      "year": 2023, "venue": "JFE"}, "shelf_n": 8}
    s = Q.IdeaSession(lab, idea, poster=harness.poster, sandbox=harness.sandbox,
                      mapcheck=kw.pop("mapcheck", _clears_map),
                      dead_rows_fn=lambda: Q.dead_rows(LEDGER), master_loader=harness.loader,
                      live_jobs=kw.pop("live_jobs", lambda: []), queue_job=kw.pop("queue_job", _no_queue), **kw)
    return lab, s


def _propose_and_write(s):
    r = s.t_propose("QL_TURNPT_NQ", "Slow and fast trend signals that disagree mark turning points in NQ.",
                    "Trade NQ open to close in the direction both trend speeds agree on; flat when they disagree.",
                    0.6, 150, "NQ", "5m", first_signal_bar=FSB0)
    assert r["accepted"], r
    w = s.t_write_plugin("QL_TURNPT_NQ", Q.TEMPLATE_PLUGIN)
    assert w["passed"], w
    return w


def test_prereg_is_written_and_posted_before_stage_a(tmp_path):
    A = _arrays()
    h = Harness(A, _intraday_trades(A))
    lab, s = _session(tmp_path, h)
    _propose_and_write(s)
    r = s.t_run_stage_a("QL_TURNPT_NQ")
    assert r["ran"], r
    order = [c[0] if c[0] != "sandbox" else c[1] for c in h.calls]
    assert order.index("post") < order.index("stage_a")
    ev = [e["event"] for e in s.idea["events"]]
    assert (ev.index("prereg_written") < ev.index("prereg_posted") < ev.index("pre_wf_started") < ev.index("pre_wf_done")
            < ev.index("pre_wf_posted") < ev.index("stage_a_started") < ev.index("stage_a_done"))
    assert h.stretches == [("pre_wf", Q.PREWF0, Q.PREWF1), ("wf", Q.DATA_FROM, Q.WF1)]
    gates = [e.get("gate") for e in s.idea["events"] if e["event"] == "gate_order"]
    assert gates == ["safety+contract+lookahead", "dead_list", "power_first_recorded"]
    pre = s.idea["prereg"]
    assert os.path.isfile(pre["path"]) and Q.lf_sha256_file(pre["path"]) == pre["sha"]
    text = open(pre["path"], encoding="utf-8").read()
    assert pre["plugin_sha"] in text and pre["harness_sha"] in text and "NOADJ_NQ_5m_RTH.csv" in text
    assert "%s..%s ONLY" % (Q.WF0, Q.WF1) in text
    assert "Stage 1 - PRE-WF Stage A" in text and "window %s..%s" % (Q.PREWF0, Q.PREWF1) in text
    assert "PROMOTION RULE" in text and "RECORDED, NOT A STOP" in text
    assert h.posts[0].startswith("QWEN LAB: PREREG QL_TURNPT_NQ") and pre["sha"] in h.posts[0]
    assert "TWO STAGES" in h.posts[0] and "PRE-WF %s..%s" % (Q.PREWF0, Q.PREWF1) in h.posts[0]


def _closes_map(name, s, n):
    return {"verdict": "CLOSE at draft (P(book lift) 12% < 30%)", "clears": False, "own_wf_roc_median": 1.0,
            "p_own_roc_ge_15": 0.01, "p_lift_463": 0.12, "prior": {"n": n, "s_mid": s}, "seed": [1, 3, 0],
            "draws": 2000, "book_roc_median": 93.8}


def test_a_closed_map_is_recorded_and_posted_but_no_longer_stops_the_idea(tmp_path):
    A = _arrays()
    h = Harness(A, _intraday_trades(A))
    lab, s = _session(tmp_path, h, mapcheck=_closes_map)
    _propose_and_write(s)
    r = s.t_run_stage_a("QL_TURNPT_NQ")
    assert r["ran"] and s.idea["map"]["stops_idea"] is False
    assert "CLOSED AT THE MAP" not in (s.idea.get("outcome") or "")
    assert h.stretches[0][0] == "pre_wf" and s.idea["stage_pre_wf"]["numbers"]
    assert "CLOSE at draft" in h.posts[0] and "no longer a stop" in h.posts[0]        # the prereg names the verdict
    assert "CLOSE at draft" in h.posts[1] and h.posts[1].startswith("QWEN LAB: QL_TURNPT_NQ PRE-WF")
    gates = [e.get("gate") for e in s.idea["events"] if e["event"] == "gate_order"]
    assert gates == ["safety+contract+lookahead", "dead_list", "power_first_recorded"]


def test_pre_wf_stage_numbers_come_from_python_and_are_posted(tmp_path):
    A = _arrays()
    h = Harness(A, _intraday_trades(A))
    lab, s = _session(tmp_path, h)
    _propose_and_write(s)
    r = s.t_run_stage_a("QL_TURNPT_NQ")
    expect = Q.four_numbers(_pre_trades(True), _pre_arrays(), 20.0, wf0=Q.PREWF0, wf1=Q.PREWF1, label="PRE-WF")
    st = s.idea["stage_pre_wf"]
    assert r["pre_wf_numbers"] == expect and st["numbers"] == expect
    assert expect["stretch"] == "PRE-WF %s..%s" % (Q.PREWF0, Q.PREWF1)
    js = json.load(open(st["numbers_json"], encoding="utf-8"))
    assert os.path.basename(st["numbers_json"]) == "numbers_pre_wf.json" and js["numbers"] == expect
    post = h.posts[1]
    assert post.startswith("QWEN LAB: QL_TURNPT_NQ PRE-WF") and Q.fmt_four(expect) in post
    assert "PROMOTED" in post and st["promoted"] and st["posted_id"] == 2
    assert st["master"] == "NOADJ_NQ_5m_RTH.csv" and st["numbers_json"] in post


def test_not_promoted_stops_before_the_wf_stage(tmp_path):
    A = _arrays()
    h = Harness(A, _intraday_trades(A), pre=(_pre_arrays(), _pre_trades(False)))
    lab, s = _session(tmp_path, h)
    _propose_and_write(s)
    r = s.t_run_stage_a("QL_TURNPT_NQ")
    assert r["ran"] and r["promotion"].startswith("NOT PROMOTED") and "numbers" not in r
    assert [x[0] for x in h.stretches] == ["pre_wf"] and not s.idea.get("stage_a")
    assert s.closed and s.idea["outcome"].startswith("PRE-WF DONE - not promoted")
    assert s.idea["result_posted_inline"] and s.idea["result_post"]["inbox_id"] == 2 and len(h.posts) == 2
    assert "NOT PROMOTED" in h.posts[1]
    s.idea["result_posted_inline"] = False                     # had the inline post failed, the end post still has them
    post = Q.compose_result_post(s.idea)
    assert Q.fmt_four(s.idea["stage_pre_wf"]["numbers"]) in post and "(no curve)" not in post
    with pytest.raises(Q.ToolRefused):
        s.t_queue_validate("QL_TURNPT_NQ")
    with pytest.raises(Q.ToolRefused, match="already ran"):
        s.t_run_stage_a("QL_TURNPT_NQ")


def test_promotion_bar():
    nm = {"roc_30k": 15.0, "one_episode": False}
    assert Q.promotion_bar(nm)[0]
    assert not Q.promotion_bar(dict(nm, roc_30k=14.99))[0]
    assert not Q.promotion_bar(dict(nm, one_episode=True))[0]
    assert not Q.promotion_bar(None)[0] and not Q.promotion_bar({"roc_30k": None})[0]


def test_pre_wf_window_ends_before_the_wf_start():
    assert Q.PREWF0 == "2010-06-07" and Q.PREWF1 == "2016-06-30" and Q.PREWF1 < Q.WF0
    assert Q.assert_pre_wf(_pre_arrays()["index"]) == "2016-06-30"
    with pytest.raises(AssertionError, match="PRE-WF GUARD"):
        Q.assert_pre_wf(_arrays("2016-06-01", "2016-07-05")["index"])
    A = _arrays("2016-06-01", "2016-07-05")
    with pytest.raises(AssertionError, match="PRE-WF GUARD"):
        Q.four_numbers(_intraday_trades(A), A, 20.0, wf0=Q.PREWF0, wf1=Q.PREWF1, label="PRE-WF")
    with pytest.raises(AssertionError, match="PRE-WF GUARD"):
        Q.four_numbers(_intraday_trades(A), A, 20.0, wf0=Q.PREWF0, wf1=Q.WF1, label="PRE-WF")


def test_hash_recheck_before_each_stage(tmp_path):
    A = _arrays()
    holder = {"n": 0}

    def tamper():                                              # the second post is the PRE-WF result
        holder["n"] += 1
        if holder["n"] == 2:
            with open(holder["path"], "a", encoding="utf-8") as f:
                f.write("\n# swapped between the PRE-WF and the WF stage\n")
    h = Harness(A, _intraday_trades(A), tamper=tamper)
    lab, s = _session(tmp_path, h)
    _propose_and_write(s)
    holder["path"] = s.plugin_path("QL_TURNPT_NQ")
    with pytest.raises(Q.ToolRefused, match="HASH MISMATCH before the wf stage"):
        s.t_run_stage_a("QL_TURNPT_NQ")
    assert [x[0] for x in h.stretches] == ["pre_wf"] and not s.idea.get("stage_a")
    checks = [e.get("stage") for e in s.idea["events"] if e["event"] in ("hash_recheck", "hash_mismatch")]
    assert checks == ["pre_wf", "wf"]


def test_the_plugin_and_proposal_freeze_once_the_prereg_is_posted(tmp_path):
    A = _arrays()
    h = Harness(A, _intraday_trades(A))
    lab, s = _session(tmp_path, h)
    _propose_and_write(s)
    s.t_run_stage_a("QL_TURNPT_NQ")
    with pytest.raises(Q.ToolRefused, match="frozen"):
        s.t_write_plugin("QL_TURNPT_NQ", Q.TEMPLATE_PLUGIN)
    with pytest.raises(Q.ToolRefused, match="frozen"):
        s.t_propose("QL_TURNPT_NQ", "x " * 10, "y " * 10, 0.3, 100, "NQ", "5m")


def test_power_first_uses_the_counted_rate_when_the_stated_one_is_off(tmp_path):
    A = _arrays()
    h = Harness(A, _intraday_trades(A))
    seen = []

    def mapcheck(name, s, n):
        seen.append((s, n))
        return _clears_map(name, s, n)
    lab, s = _session(tmp_path, h, mapcheck=mapcheck)
    s.t_propose("QL_TURNPT_NQ", "Slow and fast trend signals that disagree mark turning points in NQ.",
                "Trade NQ open to close in the direction both trend speeds agree on; flat when they disagree.",
                0.3, 40, "NQ", "5m", first_signal_bar=FSB0)
    assert s.t_write_plugin("QL_TURNPT_NQ", Q.TEMPLATE_PLUGIN)["passed"]
    s.t_run_stage_a("QL_TURNPT_NQ")
    assert seen == [(0.3, 149.7)]                       # Sharpe as stated; the rate the rule actually trades
    assert "disagrees" in s.idea["map"]["trade_rate"]["note"]


def test_no_stage_a_when_the_prereg_post_fails(tmp_path):
    A = _arrays()
    h = Harness(A, _intraday_trades(A))

    def broken_poster(text):
        raise RuntimeError("inbox down")
    h.poster = broken_poster
    lab, s = _session(tmp_path, h)
    _propose_and_write(s)
    with pytest.raises(Q.ToolRefused, match="posted"):
        s.t_run_stage_a("QL_TURNPT_NQ")
    assert ("sandbox", "stage_a") not in h.calls and not s.idea.get("stage_a")


def test_hash_recheck_refuses_a_plugin_changed_after_the_gates(tmp_path):
    A = _arrays()
    h = Harness(A, _intraday_trades(A))
    lab, s = _session(tmp_path, h)
    _propose_and_write(s)
    with open(s.plugin_path("QL_TURNPT_NQ"), "a", encoding="utf-8") as f:
        f.write("\n# edited after the gates\n")
    with pytest.raises(Q.ToolRefused, match="has not passed"):
        s.t_run_stage_a("QL_TURNPT_NQ")
    assert ("sandbox", "stage_a") not in h.calls


def test_hash_recheck_refuses_a_plugin_changed_after_the_prereg(tmp_path):
    A = _arrays()
    holder = {}

    def tamper():
        with open(holder["path"], "a", encoding="utf-8") as f:
            f.write("\n# swapped between prereg and run\n")
    h = Harness(A, _intraday_trades(A), tamper=tamper)
    lab, s = _session(tmp_path, h)
    _propose_and_write(s)
    holder["path"] = s.plugin_path("QL_TURNPT_NQ")
    with pytest.raises(Q.ToolRefused, match="HASH MISMATCH"):
        s.t_run_stage_a("QL_TURNPT_NQ")
    assert ("sandbox", "stage_a") not in h.calls
    assert any(e["event"] == "hash_mismatch" for e in s.idea["events"])


def test_stage_a_numbers_come_only_from_python(tmp_path):
    A = _arrays()
    tr = _intraday_trades(A)
    h = Harness(A, tr)
    lab, s = _session(tmp_path, h)
    _propose_and_write(s)
    r = s.t_run_stage_a("QL_TURNPT_NQ")
    expect = Q.four_numbers(tr, A, 20.0)
    assert r["numbers"] == expect and s.idea["stage_a"]["numbers"] == expect
    pre = Q.four_numbers(_pre_trades(True), _pre_arrays(), 20.0, wf0=Q.PREWF0, wf1=Q.PREWF1, label="PRE-WF")
    s.t_finish("my ROC was 999 and the Sortino 99")
    post = Q.compose_result_post(s.idea)
    assert Q.fmt_four(expect) in post and Q.fmt_four(pre) in post and "promoted" in post
    assert "999" not in post and "Qwen supplied none" in post


def test_full_loop_with_a_scripted_model(tmp_path):
    A = _arrays()
    tr = _intraday_trades(A)
    h = Harness(A, tr)
    lab, s = _session(tmp_path, h)
    chat = ScriptChat([
        ("dead_list", {"query": "trend"}),
        ("propose", {"name": "QL_TURNPT_NQ", "hypothesis": "Slow and fast trend signals that disagree mark turning "
                                                          "points in NQ.",
                     "mechanism": "Trade NQ open to close in the direction both trend speeds agree on.",
                     "prior_sharpe_yearly": 0.6, "trades_per_year": 150, "instrument": "NQ", "timeframe": "5m",
                     "first_signal_bar": {"index": 0, "clock": "09:30"}}),
        ("write_plugin", {"name": "QL_TURNPT_NQ", "code": "import os\n"}),           # refused by the safety gate
        '{"tool": "write_plugin", "arguments": {"name": "QL_TURNPT_NQ", "code": %s}}' % json.dumps(Q.TEMPLATE_PLUGIN),
        ("run_stage_a", {"name": "QL_TURNPT_NQ"}),
        ("finish", {"note": "ROC 999"}),
    ])
    out = Q.run_idea(lab, s.idea, chat, max_steps=10,
                     session_kw=dict(poster=h.poster, sandbox=h.sandbox, mapcheck=_clears_map,
                                     dead_rows_fn=lambda: Q.dead_rows(LEDGER), master_loader=h.loader))
    idea = json.load(open(os.path.join(lab.idea_dir("t-idea"), "idea.json"), encoding="utf-8"))
    assert out == "closed" and idea["status"] == "closed"
    assert idea["plugin"]["attempts"] == 2 and idea["protocol"]["json_fallback"] == 1
    assert idea["stage_a"]["numbers"] == Q.four_numbers(tr, A, 20.0)
    assert "999" not in Q.compose_result_post(idea)
    tr_ = json.load(open(os.path.join(lab.idea_dir("t-idea"), "transcript.json"), encoding="utf-8"))
    tool_msgs = [m for m in tr_["messages"] if m.get("role") == "tool"]
    assert any('"gate": "safety"' in m["content"] for m in tool_msgs)


def test_stop_file_leaves_the_idea_resumable(tmp_path):
    A = _arrays()
    h = Harness(A, _intraday_trades(A))
    lab, s = _session(tmp_path, h)
    chat = ScriptChat([("dead_list", {}), ("dead_list", {})])

    class StopAfterOne(ScriptChat):
        def chat(self, messages, tools):
            r = super().chat(messages, tools)
            open(lab.stop_path, "w").write("x")
            return r
    out = Q.run_idea(lab, s.idea, StopAfterOne(chat.script), max_steps=5,
                     session_kw=dict(poster=h.poster, sandbox=h.sandbox))
    assert out == "stopped"
    os.remove(lab.stop_path)
    idea = json.load(open(os.path.join(lab.idea_dir("t-idea"), "idea.json"), encoding="utf-8"))
    assert idea["status"] == "open" and idea["steps"] == 1
    out = Q.run_idea(lab, idea, ScriptChat([("finish", {})]), max_steps=5,
                     session_kw=dict(poster=h.poster, sandbox=h.sandbox))
    tr_ = json.load(open(os.path.join(lab.idea_dir("t-idea"), "transcript.json"), encoding="utf-8"))
    assert out == "closed" and len([m for m in tr_["messages"] if m.get("role") == "tool"]) == 2


def test_reading_budget_before_a_proposal(tmp_path):
    A = _arrays()
    h = Harness(A, _intraday_trades(A))
    lab, s = _session(tmp_path, h)
    script = [("dead_list", {"query": w}) for w in ("trend", "fast", "ema", "phase", "turning")] + [("finish", {})]
    Q.run_idea(lab, s.idea, ScriptChat(script), max_steps=10, session_kw=dict(poster=h.poster, sandbox=h.sandbox))
    tr_ = json.load(open(os.path.join(lab.idea_dir("t-idea"), "transcript.json"), encoding="utf-8"))
    tool = [json.loads(m["content"]) for m in tr_["messages"] if m.get("role") == "tool"]
    assert ["refused" in t for t in tool[:5]] == [False, False, False, True, True]
    assert all("steps_left" in t for t in tool) and tool[0]["steps_left"] == 9


def test_parse_json_action():
    assert Q.parse_json_action('sure: {"tool": "finish", "arguments": {"note": "x"}} ok') == ("finish", {"note": "x"})
    assert Q.parse_json_action("no action here {not json}") is None


# ------------------------------------------------------------------------------------------------ the validate path
def _staged(tmp_path, **kw):
    A = _arrays()
    did = A["day_id"]
    for seed in range(5, 60):                     # a leg that clears the bar (ROC >= 15, not one episode)
        rng = np.random.default_rng(seed)
        tr = []
        for d in np.unique(did):
            ix = np.flatnonzero(did == d)
            tr.append((int(ix[0]), int(ix[-1]), float(rng.normal(6.0, 4.0)), 1, float(A["open"][ix[0]])))
        if Q.validate_bar(Q.four_numbers(tr, A, 20.0))[0]:
            break
    h = Harness(A, tr)
    lab, s = _session(tmp_path, h, **kw)
    _propose_and_write(s)
    r = s.t_run_stage_a("QL_TURNPT_NQ")
    assert r["ran"] and Q.validate_bar(r["numbers"])[0], r["numbers"]
    return lab, s, h


def test_one_qwen_lab_validate_at_a_time(tmp_path):
    live = [("job1", {"status": "running", "preset": "QWEN LAB AUTO-VALIDATE 900: QL_OTHER"})]
    lab, s, h = _staged(tmp_path, live_jobs=lambda: live)
    s.dry = True
    r = s.t_queue_validate("QL_TURNPT_NQ")
    assert r["status"] == "refused" and "one at a time" in r["why"]
    assert ("sandbox", "guard") not in h.calls


def test_the_labs_own_beacon_record_is_not_a_validate(tmp_path):
    beacon = ("b1", {"status": "running", "type": "research", "strategy": "QWEN LAB 20261015-shelf08",
                     "preset": "LOCAL RESEARCH (not a validate - no lockbox, no verdict)",
                     "note": "QWEN LAB: the local model tests one reading-shelf idea"})
    other = ("j2", {"status": "queued", "type": "validate", "preset": "AUTO-VALIDATE 900 NOISE #422 + TARGET"})
    assert not Q._qwen_tagged(beacon[1]) and not Q._qwen_tagged(other[1])
    lab, s, h = _staged(tmp_path, live_jobs=lambda: [beacon, other])
    s.dry = False
    assert s.t_queue_validate("QL_TURNPT_NQ")["status"] == "pending_review"


def test_validate_fails_closed_when_the_queue_cannot_be_read(tmp_path):
    def boom():
        raise RuntimeError("no network")
    lab, s, h = _staged(tmp_path, live_jobs=boom)
    s.dry = True
    assert s.t_queue_validate("QL_TURNPT_NQ")["status"] == "refused"


def test_real_validate_waits_for_review_when_the_file_is_not_on_main(tmp_path):
    queued = []
    lab, s, h = _staged(tmp_path, queue_job=lambda job: queued.append(job) or "id1")
    s.dry = False
    r = s.t_queue_validate("QL_TURNPT_NQ")
    assert r["status"] == "pending_review" and not queued
    assert lab.state["pending_validates"][0]["name"] == "QL_TURNPT_NQ"


@needs_shared
def test_dry_run_validate_builds_the_lanes_job_and_writes_nothing(tmp_path):
    queued = []
    lab, s, h = _staged(tmp_path, queue_job=lambda job: queued.append(job) or "id1")
    s.dry = True
    r = s.t_queue_validate("QL_TURNPT_NQ")
    assert r["status"] == "dry_run" and not queued and ("sandbox", "guard") in h.calls
    job = json.load(open(os.path.join(s.dir, "validate_job.json"), encoding="utf-8"))
    base = Q.lanes_job_base()
    assert set(base) <= set(job)
    assert job["n_trials"] == 900 and job["type"] == "validate" and job["source"] == "db_noadj_rth"
    assert (job["date_from"], job["date_to"], job["lockbox_months"]) == (Q.VALIDATE_FROM, Q.VALIDATE_TO, 12)
    assert job["preset"].startswith("QWEN LAB") and Q._qwen_tagged(job)


def test_validate_refused_below_the_bar(tmp_path):
    A = _arrays()
    h = Harness(A, _intraday_trades(A))
    lab, s = _session(tmp_path, h)
    _propose_and_write(s)
    r = s.t_run_stage_a("QL_TURNPT_NQ")
    if Q.validate_bar(r["numbers"])[0]:
        pytest.skip("synthetic leg happened to clear the bar")
    with pytest.raises(Q.ToolRefused):
        s.t_queue_validate("QL_TURNPT_NQ")


# ------------------------------------------------------------------------------------------------ the sandbox (child)
def _write(tmp_path, name, code):
    p = tmp_path / ("%s.py" % name)
    p.write_text(code, encoding="utf-8", newline="\n")
    return str(p), Q.lf_sha256_file(str(p))


def _sb(tmp_path, mode, code, timeout=None, **req):
    path, sha = _write(tmp_path, "QL_T", code)
    return Q.run_sandbox(mode, path, sha, dict(req, mem_gb=4), str(tmp_path / "work"), timeout=timeout)


@needs_shared
def test_sandbox_runs_the_template_on_synthetic_bars(tmp_path):
    r = _sb(tmp_path, "synthetic", Q.TEMPLATE_PLUGIN, days=30)
    assert r["ok"], r
    assert r["trades"] and not r["blocked"]


@needs_shared
def test_sandbox_pre_wf_stage_refuses_to_load_a_wf_row(tmp_path):
    r = _sb(tmp_path, "stage_a", Q.TEMPLATE_PLUGIN, instrument="NQ", timeframe="5m", source="db_noadj_rth",
            session="RTH", master_filename="NOADJ_NQ_5m_RTH.csv", cost_pts=0.533, mult=20.0, stretch="pre_wf",
            load_from=Q.PREWF0, load_to=Q.WF0)
    assert not r["ok"] and "PRE-WF GUARD" in r["error"]
    r = _sb(tmp_path, "stage_a", Q.TEMPLATE_PLUGIN, instrument="NQ", timeframe="5m", source="db_noadj_rth",
            session="RTH", master_filename="NOADJ_NQ_5m_RTH.csv", cost_pts=0.533, mult=20.0, stretch="wf",
            load_from=Q.DATA_FROM, load_to=Q.LB0)
    assert not r["ok"] and "LOCKBOX GUARD" in r["error"]


@needs_shared
def test_sandbox_refuses_a_hash_mismatch(tmp_path):
    path, sha = _write(tmp_path, "QL_T", Q.TEMPLATE_PLUGIN)
    r = Q.run_sandbox("synthetic", path, "0" * 64, {"days": 10}, str(tmp_path / "w"))
    assert not r["ok"] and "HASH MISMATCH" in r["error"]


# these bypass the AST gate on purpose: they prove the sandbox's own layers hold if the gate ever had a hole
@needs_shared
def test_sandbox_guarded_import_blocks_os(tmp_path):
    r = _sb(tmp_path, "synthetic", "import os\n" + Q.TEMPLATE_PLUGIN, days=10)
    assert not r["ok"] and "import of 'os' is not allowed" in r["error"]


@needs_shared
def test_sandbox_has_no_open_builtin(tmp_path):
    code = Q.TEMPLATE_PLUGIN.replace("    o = np.asarray(opens, float)",
                                     "    open('pwned.txt', 'w')\n    o = np.asarray(opens, float)")
    r = _sb(tmp_path, "synthetic", code, days=10)
    assert not r["ok"] and "NameError" in r["error"]
    assert not os.path.exists(tmp_path / "work" / "pwned.txt")


@needs_shared
def test_sandbox_audit_hook_blocks_a_file_write(tmp_path):
    target = str(tmp_path / "leak.npy").replace("\\", "/")
    code = Q.TEMPLATE_PLUGIN.replace("    o = np.asarray(opens, float)",
                                     "    np.save('%s', np.asarray(opens))\n    o = np.asarray(opens, float)" % target)
    r = _sb(tmp_path, "synthetic", code, days=10)
    assert not r["ok"] and r["blocked"] and "open for write" in r["blocked"][0]
    assert not os.path.exists(target)


@needs_shared
def test_sandbox_timeout_kills_a_runaway_plugin(tmp_path):
    code = Q.TEMPLATE_PLUGIN.replace("    o = np.asarray(opens, float)", "    while True:\n        pass")
    path, sha = _write(tmp_path, "QL_T", code)
    r = Q.run_sandbox("synthetic", path, sha, {"days": 10}, str(tmp_path / "w"), timeout=25)
    assert not r["ok"] and r["error"].startswith("TIMEOUT")


# ------------------------------------------------------------------------------------------------ look-ahead audit
LEAKS = {
    # the decision reads the NEXT bar's close, then fills at that bar's open
    "next bar close": ("            side = 1 if c[k] > hi else (-1 if c[k] < lo else 0)",
                       "            side = 1 if c[k + 1] > hi else (-1 if c[k + 1] < lo else 0)"),
    # fills at the bar's OPEN but decides on the same bar's CLOSE
    "same-bar close": ("            e = k + 1                            # fill at the NEXT bar's open",
                       "            e = k"),
    # a whole-array statistic: the threshold uses every bar, future included
    "full-series percentile": ("        hi = h[a:a + rb].max()", "        hi = float(np.percentile(c, 50))"),
    # the exit peeks one bar ahead
    "exit peek": ("                if side > 0 and l[j] <= stop:",
                  "                if j + 1 < b and side * (c[j + 1] - c[j]) < -3.0:\n"
                  "                    x, px = j, c[j]\n                    break\n"
                  "                if side > 0 and l[j] <= stop:"),
    # the stop distance is the ENTRY bar's own range, and the stop is checked on that bar (the 10-15 QL_ES_MOMBREAK v4
    # shape: an ATR over bars up to AND including the entry bar)
    "stop from the fill bar's range": ("            stop = entry - side * float(stop_frac) * rng",
                                       "            stop = entry - side * float(stop_frac) * 0.5 * (h[e] - l[e])"),
    # a trailing stop raised with bar j's high BEFORE the check (intrabar fills, not only gaps)
    "trail before the check": ("                if side > 0 and l[j] <= stop:",
                               "                if side > 0:\n"
                               "                    stop = max(stop, h[j] - float(stop_frac) * rng)\n"
                               "                if side > 0 and l[j] <= stop:"),
    # TTM #145: a WIDE stop, 3 x an ATR over bars up to AND including the entry bar - almost never hit on the entry
    # bar, so only the entry-bar inputs phase sees the level move (test_entry_bar_phase_* below)
    "wide stop from an ATR that includes the entry bar": (
        "            stop = entry - side * float(stop_frac) * rng",
        "            atr = float(np.mean(h[max(0, e - 13):e + 1] - l[max(0, e - 13):e + 1]))\n"
        "            stop = entry - side * 3.0 * float(stop_frac) * atr"),
    # review round 3 (scratchpad/rev/leaks.py) - what the high / low-only entry-bar phase passed:
    # L1b: an open fill whose stop is anchored at the entry bar's CLOSE
    "stop anchored at the entry bar's close": (
        "            stop = entry - side * float(stop_frac) * rng",
        "            stop = c[e] - side * 1.5 * float(stop_frac) * rng"),
    # L1: an open fill, a wide stop from a close-to-close volatility that includes the entry bar's close
    "stop from a close-to-close vol incl. the entry bar": (
        "            stop = entry - side * float(stop_frac) * rng",
        "            vol = float(np.mean(np.abs(np.diff(c[max(0, e - 14):e + 1]))))\n"
        "            stop = entry - side * 6.0 * float(stop_frac) * vol"),
    # L3: a CLOSE fill whose stop reads the next bar's close (a bar after the fill), checked from that bar
    "close fill, stop reads the next bar's close": (
        "            e = k + 1                            # fill at the NEXT bar's open\n"
        "            entry = o[e]\n"
        "            stop = entry - side * float(stop_frac) * rng\n"
        "            x, px = b - 1, c[b - 1]              # default exit: the session's last close\n"
        "            for j in range(e, b):\n",
        "            e = k\n"
        "            entry = c[e]\n"
        "            vol = float(np.mean(np.abs(np.diff(c[max(0, e - 13):e + 2]))))\n"
        "            stop = entry - side * 6.0 * float(stop_frac) * vol\n"
        "            x, px = b - 1, c[b - 1]\n"
        "            for j in range(e + 1, b):\n"),
    # L2: a buy STOP resting at the opening-range high, filled INSIDE bar e, with a wide stop from an ATR that includes
    # bar e (the QL_ES_MOMBREAK leak with a stop entry instead of an open fill - the phase used to skip intrabar entries)
    "intrabar stop entry, ATR incl. the entry bar": (
        "        for k in range(a + rb, b - 2):          # decide on bar k's CLOSE\n"
        "            side = 1 if c[k] > hi else (-1 if c[k] < lo else 0)\n"
        "            if side == 0:\n"
        "                continue\n"
        "            e = k + 1                            # fill at the NEXT bar's open\n"
        "            entry = o[e]\n"
        "            stop = entry - side * float(stop_frac) * rng\n",
        "        for k in range(a + rb, b - 2):\n"
        "            if o[k] >= hi or h[k] <= hi:        # a buy stop resting at the range high, filled inside bar k\n"
        "                continue\n"
        "            side = 1\n"
        "            e = k\n"
        "            entry = hi\n"
        "            atr = float(np.mean(h[max(0, e - 13):e + 1] - l[max(0, e - 13):e + 1]))\n"
        "            stop = entry - side * 5.0 * float(stop_frac) * atr\n"),
}


STOP_FIRST_TARGET = ("""            x, px = b - 1, c[b - 1]              # default exit: the session's last close
            for j in range(e, b):
                if side > 0 and l[j] <= stop:""", """            x, px = b - 1, c[b - 1]              # default exit: the session's last close
            tgt = entry + side * 0.6 * rng
            for j in range(e, b):
                if side > 0 and l[j] <= stop:
                    x, px = j, (o[j] if o[j] < stop else stop)
                    break
                if side < 0 and h[j] >= stop:
                    x, px = j, (o[j] if o[j] > stop else stop)
                    break
                if side > 0 and h[j] >= tgt:
                    x, px = j, (o[j] if o[j] > tgt else tgt)
                    break
                if side < 0 and l[j] <= tgt:
                    x, px = j, (o[j] if o[j] < tgt else tgt)
                    break
                if side > 0 and l[j] <= stop:""")


@needs_shared
def test_lookahead_audit_passes_a_clean_stop_first_target(tmp_path):
    old, new = STOP_FIRST_TARGET
    assert old in Q.TEMPLATE_PLUGIN
    code = Q.TEMPLATE_PLUGIN.replace(old, new)
    r = _sb(tmp_path, "lookahead", code, synthetic_days=80, la_k=10, instrument="NQ")
    assert r["ok"], r
    assert r["short_holds_sampled"] >= 1


@needs_shared
def test_lookahead_audit_passes_the_template(tmp_path):
    r = _sb(tmp_path, "lookahead", Q.TEMPLATE_PLUGIN, synthetic_days=80, la_k=8, instrument="NQ")
    assert r["ok"], r
    assert r["perturbed_trades"] >= 5 and r["fills_checked"] > 50


@needs_shared
@pytest.mark.parametrize("leak", sorted(LEAKS))
def test_lookahead_audit_catches_leaks_the_static_gate_cannot(tmp_path, leak):
    old, new = LEAKS[leak]
    assert old in Q.TEMPLATE_PLUGIN
    code = Q.TEMPLATE_PLUGIN.replace(old, new)
    assert Q.safety_gate(code)[0], "the leaky variant must be legal code - the audit, not the gate, must catch it"
    r = _sb(tmp_path, "lookahead", code, synthetic_days=80, la_k=10, instrument="NQ")
    assert not r["ok"], "%s was not caught: %s" % (leak, r)
    assert any("LOOK-AHEAD" in p or "fill realism" in p for p in r.get("problems") or []), r


@needs_shared
def test_fill_realism_catches_a_fabricated_pnl(tmp_path):
    code = Q.TEMPLATE_PLUGIN.replace("float(side * (px - entry))", "5.0")
    assert Q.safety_gate(code)[0]
    r = _sb(tmp_path, "lookahead", code, synthetic_days=60, la_k=6, instrument="NQ")
    assert not r["ok"] and any("fill realism" in p for p in r["problems"]), r


@needs_shared
def test_lookahead_audit_catches_a_stop_booked_through_a_gap(tmp_path):
    code = Q.TEMPLATE_PLUGIN.replace("x, px = j, (o[j] if o[j] < stop else stop)", "x, px = j, stop")
    r = _sb(tmp_path, "lookahead", code, synthetic_days=120, la_k=8, instrument="NQ")
    if r.get("ok"):
        pytest.skip("no gap-through stop in this synthetic sample")
    assert any("fill realism" in p for p in r["problems"]), r


# ------------------------------------------------------------------------------------------------ idea sources (MANAGER #133)
def test_skip_list_is_the_union_of_every_claimed_or_closed_paper(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "state.json").write_text(json.dumps({"skip_shelf": [21, 99], "current_idea": None}), encoding="utf-8")
    lab = Q.Lab(home=str(home), plugin_repo=str(tmp_path / "repo"))
    assert set(lab.state["skip_shelf"]) == set(Q.DEFAULT_SKIP_SHELF) | {99}
    assert {8, 12, 13, 19, 26, 27, 29} <= set(lab.state["skip_shelf"])


def test_sources_rotate_scalper_own_shelf_and_skip_an_empty_shelf(tmp_path, monkeypatch):
    lab = Q.Lab(home=str(tmp_path / "home"), plugin_repo=str(tmp_path / "repo"))
    shelf = [{"n": 31, "title": "A New Paper", "authors": "A. Author, B. Author", "year": 2024}]
    monkeypatch.setattr(Q, "shelf_ideas", lambda *a, **k: list(shelf))
    open(lab.shelf_open_path, "w", encoding="utf-8").write("2026-10-15 09:00:00 31\n")
    seen = []
    for _ in range(4):
        pick = Q.compute_next_pick(lab)
        seen.append(pick["source"])
        idea = Q.consume_pick(lab, pick)
        assert lab.state["current_idea"] == idea["id"] and idea["source"] == pick["source"]
    assert seen == ["scalper", "own", "shelf", "scalper"]
    shelf.clear()
    lab.state["rotation_index"] = 2                     # the shelf's turn, but it is empty
    assert Q.compute_next_pick(lab)["source"] == "scalper"
    assert Q.compute_next_pick(lab, "own")["source"] == "own"


def test_next_pick_is_recorded_and_posted_as_harness_text(tmp_path, monkeypatch):
    lab = Q.Lab(home=str(tmp_path / "home"), plugin_repo=str(tmp_path / "repo"))
    monkeypatch.setattr(Q, "shelf_ideas", lambda *a, **k: [])
    posts = []
    pick = Q.record_pick(lab, Q.compute_next_pick(lab), poster=lambda t: posts.append(t) or 7)
    assert posts and posts[0].startswith("QWEN LAB next pick: the owner's scalper ask")
    assert "0.783" in posts[0] and pick["posted_id"] == 7
    st = json.load(open(lab.state_path, encoding="utf-8"))
    assert st["next_pick"]["source"] == "scalper" and st["picks"][-1]["posted_id"] == 7


def test_scalper_source_brings_its_hard_facts_and_its_costs(tmp_path):
    p = Q.idea_prompt({"source": "scalper"}, 18, 6)
    for fact in ("59 NQ 1m short-hold cells", "52.1%", "$6.60", "0.783", "0.613", "2m bars", "LARGE PAYOFF"):
        assert fact in p, fact
    assert "dead_list()" in Q.idea_prompt({"source": "own"}, 18, 6)
    assert Q.idea_costs({"source": "scalper"}, "NQ") == (0.783, 20.0)
    assert Q.idea_costs({"source": "scalper"}, "ES") == (0.613, 50.0)
    assert Q.idea_costs({"source": "own"}, "NQ") == (0.533, 20.0)
    A = _arrays()
    h = Harness(A, _intraday_trades(A))
    reqs = []
    orig = h.sandbox

    def sandbox(mode, path, sha, req, workdir, timeout=None, label=None):
        reqs.append((mode, req.get("cost_pts")))
        return orig(mode, path, sha, req, workdir, timeout, label)
    h.sandbox = sandbox
    lab, s = _session(tmp_path, h)
    s.idea["source"] = "scalper"
    _propose_and_write(s)
    s.t_run_stage_a("QL_TURNPT_NQ")
    assert ("stage_a", 0.783) in reqs and s.idea["stage_a"]["cost_pts"] == 0.783
    assert "the owner's scalper ask" in h.posts[0] and "0.783" in open(s.idea["prereg"]["path"], encoding="utf-8").read()


def test_schedule_check():
    bad = Q.schedule_check(120, 20.1)
    assert not bad["ok"] and len(bad["notes"]) == 2
    assert Q.schedule_check(150, 149.7)["ok"]
    assert not Q.schedule_check(40, 38.0)["ok"]                 # consistent, but greyed under 50 a year


def test_a_revised_proposal_must_be_rewritten_and_regated(tmp_path):
    A = _arrays()
    h = Harness(A, _intraday_trades(A))
    lab, s = _session(tmp_path, h)
    _propose_and_write(s)
    s.t_propose("QL_TURNPT_NQ", "Slow and fast trend signals that disagree mark turning points in NQ (revised).",
                "Trade NQ open to close in the direction both trend speeds agree on; exit at 14:00 instead.",
                0.5, 150, "NQ", "5m", first_signal_bar=FSB0)
    with pytest.raises(Q.ToolRefused, match="has not passed"):
        s.t_run_stage_a("QL_TURNPT_NQ")


def test_a_resumed_idea_gets_the_current_rules(tmp_path):
    A = _arrays()
    h = Harness(A, _intraday_trades(A))
    lab, s = _session(tmp_path, h)
    tpath = os.path.join(lab.idea_dir("t-idea"), "transcript.json")
    os.makedirs(os.path.dirname(tpath), exist_ok=True)
    old = {"messages": [{"role": "system", "content": "OLD RULES: a closed map ends the idea"},
                        {"role": "user", "content": "start"}, {"role": "assistant", "content": "thinking"}],
           "calls": []}
    json.dump(old, open(tpath, "w", encoding="utf-8"))
    chat = ScriptChat([("finish", {})])
    Q.run_idea(lab, s.idea, chat, max_steps=5, session_kw=dict(poster=h.poster, sandbox=h.sandbox))
    sent = chat.seen[0]
    assert sent[0]["content"] == Q.system_prompt() and "PRE-WF" in sent[0]["content"]
    assert any("RESUMED after a harness update" in str(m.get("content")) for m in sent)


# ------------------------------------------------------------------------------------------------ repeat submissions
_LA_PROBLEM = ("LOOK-AHEAD: 1 of 8 sampled trades changed when information that did not exist at the fill was replaced: "
               "EXIT at bar 12 (open fill 2058.0000) changed when the bar's high/low/close/volume and every later bar "
               "were replaced. A decision at bar k may use bars <= k only.")


class LeakyHarness(Harness):
    def sandbox(self, mode, path, sha, req, workdir, timeout=None, label=None):
        if mode == "lookahead":
            self.calls.append(("sandbox", mode))
            return {"ok": False, "problems": [_LA_PROBLEM], "warnings": []}
        return super().sandbox(mode, path, sha, req, workdir, timeout, label)


def test_a_failed_file_resent_verbatim_is_refused_without_using_an_attempt(tmp_path):
    A = _arrays()
    h = LeakyHarness(A, _intraday_trades(A))
    lab, s = _session(tmp_path, h)
    s.t_propose("QL_TURNPT_NQ", "Slow and fast trend signals that disagree mark turning points in NQ.",
                "Trade NQ open to close in the direction both trend speeds agree on; flat when they disagree.",
                0.6, 150, "NQ", "5m", first_signal_bar=FSB0)
    w = s.t_write_plugin("QL_TURNPT_NQ", Q.TEMPLATE_PLUGIN)
    assert not w["passed"] and w["gate"] == "look-ahead audit"
    assert w["how_to_fix"] and "AFTER the bar-k exit check" in w["how_to_fix"][0] and "bar 12" in w["how_to_fix"][0]
    with pytest.raises(Q.ToolRefused, match="IDENTICAL to attempt 1"):
        s.t_write_plugin("QL_TURNPT_NQ", "```python\n" + Q.TEMPLATE_PLUGIN.replace("\n", "\r\n") + "\n```")
    assert s.idea["plugin"]["attempts"] == 1 and h.calls.count(("sandbox", "lookahead")) == 1
    w2 = s.t_write_plugin("QL_TURNPT_NQ", Q.TEMPLATE_PLUGIN + "\n# changed\n")
    assert s.idea["plugin"]["attempts"] == 2 and not w2["passed"]


def test_lookahead_hints_by_fill_kind():
    assert Q.lookahead_hints(["ENTRY at bar 5 (close fill 1.0) changed when every later bar were replaced"])[0] \
        .startswith("the ENTRY is filled at bar 5's close")
    assert "intrabar" not in Q.lookahead_hints([_LA_PROBLEM])[0][:40]
    assert Q.lookahead_hints(["nothing to see"]) == []



# ------------------------------------------------------------------------------------------------ MANAGER #137-#143
_FAKE_SHELF = [{"n": 30, "title": "Gamma Fragility", "authors": "Andrea Barbon, Andrea Buraschi", "year": 2021},
               {"n": 31, "title": "A New Paper", "authors": "A. Author, B. Author", "year": 2024},
               {"n": 32, "title": "Another Paper", "authors": "C. Author", "year": 2025}]


def test_the_closed_shelf_is_seeded_and_the_picker_never_retakes_a_closed_paper(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / "state.json").write_text(json.dumps({"done_ideas": [{"id": "x", "shelf_n": 12}], "current_idea": None}),
                                     encoding="utf-8")
    lab = Q.Lab(home=str(home), plugin_repo=str(tmp_path / "repo"))
    assert {"8", "12", "30"} <= set(lab.state["closed_shelf"])
    monkeypatch.setattr(Q, "shelf_ideas", lambda *a, **k: [dict(p) for p in _FAKE_SHELF])
    assert Q.open_shelf_papers(lab) == []                       # nothing opened by MANAGER: the shelf slot is skipped
    open(lab.shelf_open_path, "w", encoding="utf-8").write("2026-10-15 09:00:00 30 31\n")
    assert [p["n"] for p in Q.open_shelf_papers(lab)] == [31]  # 30 stays closed: it was closed after that open
    with pytest.raises(SystemExit, match="CLOSED"):
        Q.pick_idea(lab, 30)
    lab.close_shelf(31, "idea-31", "test")
    assert Q.open_shelf_papers(lab) == [] and Q.compute_next_pick(lab, None)["source"] in ("scalper", "own")
    with open(lab.shelf_open_path, "a", encoding="utf-8") as f:
        f.write("2099-01-01 00:00:00 31\n")                    # MANAGER re-opens it later
    assert [p["n"] for p in Q.open_shelf_papers(lab)] == [31]


def test_rotation_alternates_scalper_and_own_while_no_shelf_paper_is_open(tmp_path, monkeypatch):
    lab = Q.Lab(home=str(tmp_path / "home"), plugin_repo=str(tmp_path / "repo"))
    monkeypatch.setattr(Q, "shelf_ideas", lambda *a, **k: [dict(p) for p in _FAKE_SHELF])
    seen = []
    for _ in range(5):
        pick = Q.compute_next_pick(lab)
        seen.append(pick["source"])
        Q.consume_pick(lab, pick)
    assert seen == ["scalper", "own", "scalper", "own", "scalper"]
    with pytest.raises(SystemExit, match="no shelf paper is open"):
        Q.compute_next_pick(lab, "shelf")
    assert "none" in Q.compose_pick_post(lab, {"source": "own", "label": "Qwen's own idea"})


def test_shelf_open_command_appends_and_never_touches_state(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(Q, "LAB_HOME", Q.LAB_HOME)
    monkeypatch.setattr(Q, "shelf_ideas", lambda *a, **k: [dict(p) for p in _FAKE_SHELF])
    home = str(tmp_path / "home")
    lab = Q.Lab(home=home, plugin_repo=str(tmp_path / "repo"))
    lab.save()
    before = open(lab.state_path, encoding="utf-8").read()
    assert Q.main(["shelf-open", "32", "31", "--home", home]) == 0
    assert open(lab.state_path, encoding="utf-8").read() == before
    assert Q.Lab(home=home).open_shelf_numbers() == [31, 32]
    assert "shelf #31 opened" in capsys.readouterr().out


def test_a_shelf_paper_closes_after_its_stage_a(tmp_path):
    A = _arrays()
    h = Harness(A, _intraday_trades(A))
    lab, s = _session(tmp_path, h)
    s.idea.update(source="shelf", shelf_n=31)
    _propose_and_write(s)
    s.t_run_stage_a("QL_TURNPT_NQ")
    c = lab.state["closed_shelf"]["31"]
    assert c["idea"] == "t-idea" and "PRE-WF" in c["why"]
    assert json.load(open(lab.state_path, encoding="utf-8"))["closed_shelf"]["31"]["idea"] == "t-idea"


def test_gamma_is_closed_for_the_lab(tmp_path):
    for name, hyp in (("QL_GAMMA_ORB", "Opening range on short-gamma days."),
                      ("QL_GEXFLIP", "When GEX flips sign, intraday drift follows."),
                      ("QL_HEDGEFLOW", "Dealer hedging flows push the afternoon close.")):
        r = Q.dead_check(name, hyp, "Trade NQ in the direction of the flow.", Q.dead_rows(LEDGER))
        assert r["refused"] and "GAMMA is closed for the lab" in r["reason"], name
    assert not Q.dead_check("QL_TURNPT_NQ", "Slow and fast trend signals that disagree mark turning points.",
                            "Trade with both trend speeds.", Q.dead_rows(LEDGER))["refused"]
    assert Q.dead_list(text=LEDGER)["list"][0].startswith("LAB GAMMA -> CLOSED")
    A = _arrays()
    lab, s = _session(tmp_path, Harness(A, _intraday_trades(A)))
    r = s.t_propose("QL_DEALERS", "Dealer gamma positioning sets the intraday regime.", "Fade or follow by gamma sign.",
                    0.4, 120, "NQ", "5m", first_signal_bar=FSB0)
    assert r.get("accepted") is not True


def test_net_per_trade_in_points_is_on_every_result_line():
    A = _arrays()
    tr = _intraday_trades(A)
    nm = Q.four_numbers(tr, A, 20.0)
    kept = [x for x in tr if pd.Timestamp(A["index"][x[0]]).tz_localize(None).normalize() >= pd.Timestamp(Q.WF0)]
    assert abs(nm["net_pts_per_trade"] - np.mean([x[2] for x in kept])) < 1e-3
    assert abs(nm["net_usd_per_trade"] - nm["net_usd"] / nm["trades"]) < 0.01
    line = Q.fmt_four(nm)
    assert "net/trade" in line and " pt (" in line and "/yr)" in line


# ---- the broken-plugin sanity loop (MANAGER #139)
class SeqHarness(Harness):
    """PRE-WF stage answers from a queue of trade sets (one per run); 'crash' makes the sandbox fail."""

    def __init__(self, A, trades, pre_sets):
        super().__init__(A, trades)
        self.pre_sets = list(pre_sets)

    def sandbox(self, mode, path, sha, req, workdir, timeout=None, label=None):
        if mode == "stage_a" and req.get("stretch") == "pre_wf":
            self.calls.append(("sandbox", mode))
            self.stretches.append(("pre_wf", req.get("load_from"), req.get("load_to")))
            tr = self.pre_sets.pop(0)
            if tr == "crash":
                return {"ok": False, "error": "IndexError: index 99999 is out of bounds"}
            return {"ok": True, "trades": [list(x) for x in tr], "bars": len(self.P["close"]), "stretch": "pre_wf",
                    "fingerprint": self.P["fingerprint"], "params": {}, "peak_gb": 0.2, "secs": 1.0}
        return super().sandbox(mode, path, sha, req, workdir, timeout, label)


def _few(n=3):
    return _pre_trades(True)[:n]


def test_sanity_check_thresholds():
    idea = {"source": "own", "proposal": {"name": "QL_X", "hypothesis": "h", "mechanism": "m", "trades_per_year": 150}}
    assert Q.sanity_check({"trades": 240, "trades_per_year": 40.0}, idea)          # > 3x below the stated 150
    assert Q.sanity_check({"trades": 600, "trades_per_year": 100.0}, idea) is None
    idea["proposal"]["trades_per_year"] = 30
    assert Q.sanity_check({"trades": 150, "trades_per_year": 25.0}, idea) is None
    assert "under 20" in Q.sanity_check({"trades": 90, "trades_per_year": 15.0}, idea)
    assert Q.sanity_check({"trades": 1, "trades_per_year": 0.2}, idea).startswith("1 trade in")
    idea.update(source="scalper")
    assert "scalp" in Q.sanity_check({"trades": 480, "trades_per_year": 80.0}, idea)
    idea.update(source="own", proposal=dict(idea["proposal"], name="QL_SCALPX"))
    assert Q.sanity_check({"trades": 480, "trades_per_year": 80.0}, idea)


def test_a_plugin_that_barely_trades_goes_back_to_qwen_and_the_fix_is_preregistered(tmp_path):
    A = _arrays()
    h = SeqHarness(A, _intraday_trades(A), [_few(3), _pre_trades(True)])
    lab, s = _session(tmp_path, h)
    _propose_and_write(s)
    r = s.t_run_stage_a("QL_TURNPT_NQ")
    assert r["verdict"].startswith("NONE YET") and r["fix_retries_left"] == 2 and not s.closed
    assert r["trades"] == 3 and len(r["sessions"]) == 3 and r["_cap"] == Q.SANITY_RESULT_CHARS
    for ses in r["sessions"]:
        assert len(ses["bars"]) <= Q.SANITY_ROWS and not ses["your_trades_this_session"] and len(ses["columns"]) == 7
    assert len(h.posts) == 1 and not s.idea.get("stage_pre_wf")          # the prereg only: no verdict, no PRE-WF post
    assert s.idea["sanity_open"] and s.idea["bonus_steps"] == Q.SANITY_BONUS_STEPS
    with pytest.raises(Q.ToolRefused, match="unchanged"):
        s.t_run_stage_a("QL_TURNPT_NQ")
    w = s.t_write_plugin("QL_TURNPT_NQ", Q.TEMPLATE_PLUGIN + "\n# fixed the entry window\n")
    assert w["passed"]
    old_sha = s.idea["prereg"]["history"][0]["plugin_sha"] if s.idea["prereg"].get("history") else None
    r2 = s.t_run_stage_a("QL_TURNPT_NQ")
    pre = s.idea["prereg"]
    assert old_sha is None and pre["plugin_sha"] == w["sha256"] and pre["history"][0]["plugin_sha"] != w["sha256"]
    assert h.posts[1].startswith("QWEN LAB: PREREG ADDENDUM 1 QL_TURNPT_NQ") and w["sha256"] in h.posts[1]
    text = open(pre["path"], encoding="utf-8").read()
    assert "## Addendum 1" in text and w["sha256"] in text and Q.lf_sha256_file(pre["path"]) == pre["sha"]
    ev = [e["event"] for e in s.idea["events"]]
    assert ev.index("prereg_addendum") < ev.index("pre_wf_r1_started")
    assert r2["promotion"].startswith("PROMOTED") and h.posts[2].startswith("QWEN LAB: QL_TURNPT_NQ PRE-WF")
    assert "Broken-plugin fix retries: 1" in h.posts[2]


def test_still_broken_after_two_retries_is_a_broken_plugin_not_a_dead_idea(tmp_path):
    A = _arrays()
    h = SeqHarness(A, _intraday_trades(A), [_few(2), "crash", _few(1)])
    lab, s = _session(tmp_path, h)
    _propose_and_write(s)
    assert s.t_run_stage_a("QL_TURNPT_NQ")["fix_retries_left"] == 2
    s.t_write_plugin("QL_TURNPT_NQ", Q.TEMPLATE_PLUGIN + "\n# try 2\n")
    r = s.t_run_stage_a("QL_TURNPT_NQ")
    assert r["fix_retries_left"] == 1 and "crashed" in r["verdict"] and "IndexError" in r["error"]
    s.t_write_plugin("QL_TURNPT_NQ", Q.TEMPLATE_PLUGIN + "\n# try 3\n")
    r = s.t_run_stage_a("QL_TURNPT_NQ")
    assert r["verdict"] == "BROKEN PLUGIN (1 trade)" and s.closed
    assert s.idea["outcome"].startswith("BROKEN PLUGIN (1 trade)") and "dead" not in s.idea["outcome"].lower()
    assert "BROKEN PLUGIN" in h.posts[-1] and h.posts[-1].startswith("QWEN LAB: QL_TURNPT_NQ PRE-WF")
    assert [p.split(" ")[4] for p in h.posts if "ADDENDUM" in p] == ["1", "2"]
    assert s.idea["result_posted_inline"] and s.idea["stage_pre_wf"]["broken"]


def test_finishing_during_a_fix_records_a_broken_plugin(tmp_path):
    A = _arrays()
    h = SeqHarness(A, _intraday_trades(A), [_few(4)])
    lab, s = _session(tmp_path, h)
    _propose_and_write(s)
    s.t_run_stage_a("QL_TURNPT_NQ")
    s.t_finish("it is fine")
    assert s.idea["outcome"].startswith("BROKEN PLUGIN (4 trades)") and "finished without a fix" in s.idea["outcome"]


# ---- load courtesy (MANAGER #143)
def test_push_lock_state_is_read_only_and_tells_a_stale_file_from_a_free_one(tmp_path):
    p = tmp_path / "push.lock"
    assert Q.push_lock_state(str(p)) == (False, "")
    p.write_bytes(b"#docs-1015c  pid 999999  since 13:13:05")
    before = (p.read_bytes(), os.path.getmtime(p))
    held, who = Q.push_lock_state(str(p))
    assert not held and who.startswith("docs-1015c")              # a name left behind after a release = stale
    assert (p.read_bytes(), os.path.getmtime(p)) == before


@needs_shared
@pytest.mark.skipif(os.name != "nt", reason="the byte-0 lock is mandatory only on Windows")
def test_push_lock_state_sees_a_live_holder(tmp_path):
    import subprocess
    import time as _t
    p = tmp_path / "push.lock"
    code = ("import sys, time; sys.path.insert(0, %r); import push_lock as P; fd = P.hold('lane-x', path=%r, "
            "log=lambda *a: None); print('held', flush=True); time.sleep(30)" % (os.path.join(Q.SHARED, "tools"),
                                                                                 str(p)))
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "held"
        held, who = Q.push_lock_state(str(p))
        assert held and who.startswith("lane-x")
    finally:
        proc.kill()
        proc.wait()
    _t.sleep(0.2)
    assert Q.push_lock_state(str(p))[0] is False                 # the kernel dropped it with the process


def test_courtesy_wait_rechecks_every_minute_and_logs(tmp_path):
    lab = Q.Lab(home=str(tmp_path / "home"), plugin_repo=str(tmp_path / "repo"))
    answers = [(True, "lane-x  pid 1  since 10:00:00")] * 3 + [(False, "")]
    clock = {"t": 0.0}
    sleeps = []

    def sleep(sec):
        sleeps.append(sec)
        clock["t"] += sec
    assert Q.courtesy_wait(lab, "Stage A", "i1", check=lambda: answers.pop(0), sleep=sleep,
                           clock=lambda: clock["t"])
    assert sleeps == [60, 60, 60]
    log = open(lab.log_path, encoding="utf-8").read()
    assert "LOAD COURTESY: push.lock held (lane-x" in log and "free after 180 s" in log
    assert lab.state["courtesy_waits"][-1]["secs"] == 180 and lab.state["courtesy_waits"][-1]["what"] == "Stage A"
    open(lab.stop_path, "w").write("x")
    assert Q.courtesy_wait(lab, "Qwen generation", "i1", check=lambda: (True, "lane-y"), sleep=sleep) is False
    assert Q.courtesy_wait(lab, "Stage A (pre_wf)", "i1", interruptible=False,
                           check=iter([(True, "y"), (False, "")]).__next__, sleep=sleep)


def test_no_new_generation_or_stage_a_while_the_push_lock_is_held(tmp_path):
    A = _arrays()
    h = Harness(A, _intraday_trades(A))
    lab, s = _session(tmp_path, h)
    seen = []

    def courtesy(lab_, what, idea_id=None, interruptible=True, **kw):
        seen.append(what)
        return True
    chat = ScriptChat([("finish", {})])
    Q.run_idea(lab, s.idea, chat, max_steps=5, session_kw=dict(poster=h.poster, sandbox=h.sandbox, courtesy=courtesy))
    assert seen == ["Qwen generation"] and len(chat.seen) == 1
    # a STOP during the wait: no generation starts, the idea stays open
    lab2, s2 = _session(tmp_path / "b", h)
    chat2 = ScriptChat([("finish", {})])
    out = Q.run_idea(lab2, s2.idea, chat2, max_steps=5,
                     session_kw=dict(poster=h.poster, sandbox=h.sandbox, courtesy=lambda *a, **k: False))
    assert out == "stopped" and chat2.seen == []
    # Stage A: waits first (interruptible, before anything is written), and again right before each stage
    lab3, s3 = _session(tmp_path / "c", h, courtesy=courtesy)
    seen.clear()
    _propose_and_write(s3)
    s3.t_run_stage_a("QL_TURNPT_NQ")
    assert seen[:2] == ["Stage A", "Stage A (pre_wf)"]
    lab4, s4 = _session(tmp_path / "d", Harness(A, _intraday_trades(A)), courtesy=lambda *a, **k: False)
    _propose_and_write(s4)
    with pytest.raises(Q.LabStopped):
        s4.t_run_stage_a("QL_TURNPT_NQ")
    assert not s4.idea.get("prereg") and not s4.idea.get("map")


# ======================================================================== fix round 2 (MANAGER #147/#148, TTM #144/#145)
# ---- A. shelf-close (MANAGER #147): the latest open / close line per paper wins; state.json is never touched
def _shelf_lines(lab):
    return open(lab.shelf_open_path, encoding="utf-8").read().splitlines()


def test_shelf_close_appends_a_dated_close_line_and_the_latest_line_wins(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(Q, "LAB_HOME", Q.LAB_HOME)
    monkeypatch.setattr(Q, "shelf_ideas", lambda *a, **k: [dict(p) for p in _FAKE_SHELF])
    home = str(tmp_path / "home")
    lab = Q.Lab(home=home, plugin_repo=str(tmp_path / "repo"))
    lab.save()
    before = open(lab.state_path, encoding="utf-8").read()
    assert Q.main(["shelf-open", "31", "32", "--home", home]) == 0
    assert Q.main(["shelf-close", "31", "--why", "MANAGER #147: done # really", "--home", home]) == 0
    out = capsys.readouterr().out
    assert "shelf #31 CLOSED for the lab" in out and "open now: [32]" in out
    last = _shelf_lines(lab)[-1]
    assert re.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d CLOSE 31  # MANAGER  147: done   really$", last), last
    lab = Q.Lab(home=home)
    assert lab.open_shelf_numbers() == [32] and set(lab.shelf_closed_by_manager()) == {31}
    assert lab.shelf_marks()[31][0] == "close" and lab.shelf_marks()[32][0] == "open"
    with pytest.raises(SystemExit, match="CLOSED by MANAGER"):
        Q.pick_idea(lab, 31)
    assert [p["n"] for p in Q.open_shelf_papers(lab)] == [32]
    # an open AFTER the close re-opens it; a close after that closes it again (file order is the authority)
    assert Q.main(["shelf-open", "31", "--home", home]) == 0
    assert Q.Lab(home=home).open_shelf_numbers() == [31, 32]
    assert Q.main(["shelf-close", "31", "32", "--home", home]) == 0
    assert Q.Lab(home=home).open_shelf_numbers() == []
    assert open(lab.state_path, encoding="utf-8").read() == before          # never touches state.json


def test_shelf_marks_plain_number_lines_mean_open_and_a_hand_edited_file_is_safe(tmp_path, capsys):
    home = str(tmp_path / "home")
    lab = Q.Lab(home=home, plugin_repo=str(tmp_path / "repo"))
    with open(lab.shelf_open_path, "w", encoding="utf-8") as f:
        f.write("# MANAGER's file\n33 34\n2026-10-15 13:50:57 35\n2026-10-15 14:00:00 closed: 34\n36")   # no newline
    lab = Q.Lab(home=home)
    assert lab.open_shelf_numbers() == [33, 35, 36] and set(lab.shelf_closed_by_manager()) == {34}
    assert Q.main(["shelf-close", "36", "--home", home]) == 0
    lines = _shelf_lines(lab)
    assert lines[-2] == "36" and re.search(r" CLOSE 36$", lines[-1])        # the new line did not run into the last
    assert Q.Lab(home=home).open_shelf_numbers() == [33, 35]
    assert "it was not open" not in capsys.readouterr().out
    assert Q.main(["shelf-close", "99", "--home", home]) == 0
    assert "shelf #99 CLOSED for the lab (it was not open)" in capsys.readouterr().out


def test_shelf_close_uses_the_labs_home_override(tmp_path, monkeypatch):
    env_home = tmp_path / "env_home"
    monkeypatch.setenv("QWEN_LAB_HOME", str(env_home))
    assert Q.main(["shelf-close", "40"]) == 0
    assert re.search(r" CLOSE 40$", (env_home / Q.SHELF_OPEN_FILE).read_text(encoding="utf-8").splitlines()[-1])
    assert not (env_home / "state.json").exists()                          # the command never writes state.json
    assert Q.Lab().home == str(env_home) and 40 in Q.Lab().shelf_closed_by_manager()


def test_status_shows_the_open_and_closed_shelf_and_the_ideas_already_run(tmp_path, capsys):
    home = str(tmp_path / "home")
    lab = Q.Lab(home=home, plugin_repo=str(tmp_path / "repo"))
    with open(lab.shelf_open_path, "w", encoding="utf-8") as f:
        f.write("2026-10-15 09:00:00 31 32\n2026-10-16 09:00:00 CLOSE 31\n")
    assert Q.main(["status", "--home", home]) == 0
    out = capsys.readouterr().out
    assert "closed shelf by MANAGER (shelf-close; latest line wins): #31 (2026-10-16 09:00:00)" in out
    assert "open shelf (MANAGER shelf-open): [32]" in out
    assert "ideas already run (refused at propose - MANAGER #148): 0 names" in out


def test_a_recorded_shelf_pick_closed_since_it_was_posted_is_not_run(tmp_path, monkeypatch):
    import argparse
    monkeypatch.setattr(Q, "shelf_ideas", lambda *a, **k: [dict(p) for p in _FAKE_SHELF])
    home = str(tmp_path / "home")
    repo = tmp_path / "repo"
    (repo / "augur_strategies").mkdir(parents=True)
    lab = Q.Lab(home=home, plugin_repo=str(repo))
    with open(lab.shelf_open_path, "w", encoding="utf-8") as f:
        f.write("2026-10-15 09:00:00 31\n")
    pick = Q.record_pick(lab, Q.compute_next_pick(lab, "shelf"), post=False)
    assert pick["shelf"]["n"] == 31 and Q.pick_still_open(lab, pick)
    with open(lab.shelf_open_path, "a", encoding="utf-8") as f:
        f.write("2026-10-15 10:00:00 CLOSE 31\n")                         # MANAGER closes it after the pick
    assert not Q.pick_still_open(lab, pick) and Q.pick_still_open(lab, {"source": "own"})
    A = _arrays()
    h = Harness(A, _intraday_trades(A))
    args = argparse.Namespace(home=home, plugin_repo=str(repo), idea=None, source=None, think=False, no_beacon=True,
                              max_steps=3, dry_run_validate=True, once=True, no_next_pick=True)
    assert Q.run(args, chat=ScriptChat([("finish", {})]), session_kw=dict(poster=h.poster, sandbox=h.sandbox)) == 0
    st = json.load(open(os.path.join(home, "state.json"), encoding="utf-8"))
    assert st["done_ideas"][-1]["source"] in ("scalper", "own") and st["done_ideas"][-1]["shelf_n"] is None
    assert "was closed since it was posted - picking again" in open(lab.log_path, encoding="utf-8").read()


# ---- B. idea-level dedupe (MANAGER #148)
_VWAP_V1 = ("On NQ 5m regular-hours bars (09:30-16:00 ET). At each bar k (k >= 25), compute: (1) session VWAP = "
            "sum(close[session_start..k]) / (k - session_start + 1) as a proxy; (2) ATR20 = mean of "
            "(high[i]-low[i]) over bars k-19..k. If close[k] > VWAP + 2.5*ATR20, enter SHORT at bar k+1's open. "
            "If close[k] < VWAP - 2.5*ATR20, enter LONG at bar k+1's open. Stop: 1.0*ATR20 against entry (intrabar, "
            "gap-through books the open). Target: 1.5*ATR20 in favor. Flat at session's last bar. One trade per "
            "session (first signal wins).")
_TPT = ("On 5m NQ bars, compute fast EMA (span=20) and slow EMA (span=60) on close. Phase = +1 if close > fast > slow "
        "(bull), -1 if close < fast < slow (bear), 0 otherwise (turning point). Enter long at next bar's open when "
        "phase transitions from 0 to +1; enter short when phase transitions from 0 to -1. Exit when phase returns to 0 "
        "or at session's last bar. One trade per session. Stop: 1.5x ATR(14) from entry.")
# the lab's REAL proposals (C:\EdgeLog\qwen_lab\ideas\*\idea.json, 10-15 / 10-16), verbatim
_REAL_MOMBREAK = (
    "Signal: At bar 12 (10:30 ET), compute the morning range = max(high[0:12]) - min(low[0:12]). Compute morning "
    "direction = sign(close[11] - open[0]). If |close[11] - open[0]| >= threshold * morning_range, enter in the direction "
    "of the morning move at bar 13's open. Exit: trailing stop at stop_frac * ATR(14) from the highest/lowest price since "
    "entry, or flat at session's last bar. One trade per session.")
_REAL_TRENDN = (
    "NQ 5m bars, regular hours 09:30-16:00 ET. Signal: at bar 12 (end of first hour, 10:30 ET), compute the first-hour "
    "range (high - low of bars 0-11) and the first-hour close displacement (close[11] - open[0]). If |displacement| >= "
    "threshold_frac x range AND displacement > 0, go long at bar 13's open. If displacement < 0, go short. Trailing stop: "
    "initial stop at entry -/+ stop_frac x range; after entry, the stop ratchets to the highest close seen (long) or "
    "lowest close seen (short) minus/plus trail_frac x range. Exit when price trades through the trailing stop "
    "(intrabar, book the open if it gaps through). Flat at session's last bar. One trade per session.")
_REAL_MOMDRIVE = (
    "NQ 2m bars, RTH 09:30-16:00. Setup: first 12 bars (24 min) form a range. If range <= compress_k x ATR(14 bars, "
    "trailing), the session is \"quiet\". Signal: a bar whose close breaks above the range high (long) or below the range "
    "low (short). Entry: next bar's open. Stop: 2.0 x ATR trailing (chandelier-style: highest close since entry minus "
    "2*ATR for longs; lowest close plus 2*ATR for shorts). Exit: stop hit (intrabar, gap-through books the open) OR "
    "session's last bar close. One trade per session max.")
_REAL_VWAPREVERT = (
    "On NQ 5m regular-hours bars (09:30-16:00 ET). At each bar k (k >= 25), compute: (1) session VWAP = "
    "sum(close[session_start..k]) / (k - session_start + 1) as a proxy (no volume data needed for the signal; the engine "
    "charges cost separately); (2) ATR20 = mean of (high[i]-low[i]) over bars k-19..k. If close[k] > VWAP + 2.5*ATR20, "
    "enter SHORT at bar k+1's open. If close[k] < VWAP - 2.5*ATR20, enter LONG at bar k+1's open. Stop: 1.0*ATR20 "
    "against entry (intrabar, gap-through books the open). Target: 1.5*ATR20 in favor (intrabar, gap-through books the "
    "open). Flat at session's last bar. One trade per session (first signal wins).")
_REAL_TOM = ("On the last 3 trading days of each calendar month (determined by day_id session dates), buy 1 contract at "
             "the first bar's open (09:30 ET) and hold to the last bar's close (16:00 ET). No stop, no intrabar exit. "
             "One trade per qualifying session. Flat all other days.")
# (id, source, state list, name, mechanism, outcome) - the shapes of the lab's real 10-15 ideas
_RAN = [
    ("i1", "own", "done", "QL_VWAPREVERT_NQ", _VWAP_V1, "PRE-WF DONE - not promoted (pre-WF ROC@30k -4.75 < 15)"),
    ("i2", "scalper", "done", "QL_MOMDRIVE",
     "NQ 2m bars, RTH 09:30-16:00. Setup: first 12 bars (24 min) form a range. If range <= compress_k x ATR(14 bars, "
     "trailing), the session is quiet. Signal: a bar whose close breaks above the range high (long) or below the range "
     "low (short). Entry: next bar's open.", "PRE-WF DONE - not promoted (pre-WF ROC@30k -4.95 < 15)"),
    ("i3", "own", "done", "QL_ES_MOMBREAK",
     "At bar 12 (10:30 ET), compute the morning range = max(high[0:12]) - min(low[0:12]) and the morning direction = "
     "sign(close[11] - open[0]); enter in the direction of the morning move at bar 13's open.",
     "PRE-WF DONE - not promoted (pre-WF ROC@30k -4.81 < 15)"),
    ("i4", "shelf", "done", "QL_TPT_NQ", _TPT, "CLOSED AT THE MAP (power first: GREYED)"),
    ("i5", "own", "done", "QL_VWAPREVERT_NQ", _VWAP_V1.replace("2.5*ATR20", "2.0*ATR20").replace("k >= 25", "k >= 20"),
     "PRE-WF DONE - not promoted (pre-WF ROC@30k -4.91 < 15)"),
    ("i6", "shelf", "done", "QL_TOM_CALENDAR_NQ",
     "On the last 3 trading days of each calendar month buy 1 contract at the first bar's open and hold to the close.",
     "PRE-WF DONE - not promoted (pre-WF ROC@30k -1.20 < 15)"),
    ("i7", "shelf", "aborted", None, None, "ABORTED by the operator at step 9 (no proposal)"),
    # an operator abort AFTER a proposal: an idea the lab ran (its name is taken), but no verdict on its mechanism
    ("i8", "scalper", "aborted", "QL_GAPSCALP_NQ",
     "Buy a 1m bar whose close is in the top 10% of its range after a gap down of 0.3%; exit after 8 bars.",
     "ABORTED by the operator at step 6"),
]


def _ran_lab(tmp_path, rows=None, closed_shelf=None):
    """A lab home whose state.json + idea folders hold `rows` (default _RAN): (id, source, done|aborted, name,
    mechanism, outcome[, shelf_n])."""
    home = tmp_path / "home"
    st = {"done_ideas": [], "aborted_ideas": [], "current_idea": None}
    if closed_shelf:
        st["closed_shelf"] = closed_shelf
    for row in (_RAN if rows is None else rows):
        iid, src, where, name, mech, outcome = row[:6]
        sh = {"shelf_n": row[6]} if len(row) > 6 else {}
        st["%s_ideas" % where].append(dict({"id": iid, "source": src, "outcome": outcome}, **sh))
        idea = dict({"id": iid, "source": src, "outcome": outcome, "status": "closed"}, **sh)
        if name:
            idea["proposal"] = {"name": name, "hypothesis": "h" * 30, "mechanism": mech}
        d = home / "ideas" / iid
        d.mkdir(parents=True)
        (d / "idea.json").write_text(json.dumps(idea), encoding="utf-8")
    (home / "state.json").write_text(json.dumps(st), encoding="utf-8")
    return Q.Lab(home=str(home), plugin_repo=str(tmp_path / "repo"))


FAMILY_POS = [
    ("QL_VWAPREVERT_NQ", "anything at all in the rule text", "VWAP_REVERSION"),
    ("QL_X", _VWAP_V1, "VWAP_REVERSION"),                            # the band fade without the word 'revert'
    ("QL_X", "Fade moves of more than 2 ATR away from the session VWAP; target the VWAP.", "VWAP_REVERSION"),
    ("QL_X", "If close < session VWAP - 2*SD, go long; exit when price reverts to the VWAP.", "VWAP_REVERSION"),
    ("QL_X", "Mean-revert to VWAP after a 2-sigma stretch, stop 1 ATR.", "VWAP_REVERSION"),
    ("QL_X", "Opening range = first 6 bars (30 min). On the first bar whose CLOSE breaks above the range high, buy.",
     "OPENING_RANGE"),
    ("QL_X", _RAN[1][4], "OPENING_RANGE"),
    ("QL_X", "Opening range = first range_bars bars. On the first bar where close > range high, fill next open.",
     "OPENING_RANGE"),
    ("QL_X", _RAN[2][4], "OPENING_RANGE"),
    ("QL_X", "Buy a close above the first 30-minute high; sell a close below the first 30-minute low.", "OPENING_RANGE"),
    ("QL_X", "Opening range breakout on 5m bars with a volume filter.", "OPENING_RANGE"),
    ("QL_ORB_VOL_NQ", "Trade breaks with a volume filter.", "OPENING_RANGE"),
    ("QL_X", "The first half hour's return predicts the last half hour: trade in the same direction at 15:30.",
     "OPENING_RANGE"),
    ("QL_X", "Trade the open drive: if the first 3 bars all close up, buy.", "OPEN_DRIVE"),
    ("QL_MOMDRIVE", "something else entirely", "OPEN_DRIVE"),
    ("QL_X", "Momentum drive from the open, hold to noon.", "OPEN_DRIVE"),
    ("QL_TOM_CALENDAR_NQ", "Buy and hold.", "TURN_OF_MONTH"),
    ("QL_X", _RAN[5][4], "TURN_OF_MONTH"),
    ("QL_X", "Long into the turn of the month.", "TURN_OF_MONTH"),
    ("QL_X", "Month-end rebalancing flows: short the last trading day of the month.", "TURN_OF_MONTH"),
    ("QL_X", "Dealer gamma positioning: fade when gamma is long.", "GAMMA"),
    # review round 3: the lab's own reworded repeat and the paraphrases the old map let through
    ("QL_TRENDN", _REAL_TRENDN, "OPENING_RANGE"),                       # QL_ES_MOMBREAK's rule, moved to NQ
    ("QL_X", "At bar 12 (10:30 open), measure the first-hour displacement close[11] - open[0]. If it exceeds 0.4 x the "
             "first-hour range, enter at bar 12's open in the sign of the displacement.", "OPENING_RANGE"),
    ("QL_X", "On 5m NQ bars, if the 09:30-10:30 return is larger than 0.5% buy (smaller than -0.5% sell) at bar 12 "
             "(10:30 open) and hold to the close.", "OPENING_RANGE"),
    ("QL_X", _REAL_MOMBREAK.replace("morning", "first-hour"), "OPENING_RANGE"),
    ("QL_X", "Buy when price breaks above the opening range high; sell below the opening range low.", "OPENING_RANGE"),
    ("QL_X", "Compute session VWAP; let d = (close - VWAP)/ATR20. If d > 2.5 short at the next bar's open, if d < -2.5 "
             "go long; stop 1 ATR, take profit 1.5 ATR.", "VWAP_REVERSION"),
    ("QL_X", "Compute session VWAP and the z-score of (close - VWAP) over the last 20 bars. When z > 2 sell at the next "
             "bar's open, when z < -2 buy. Exit when z crosses 0.", "VWAP_REVERSION"),
]
# family-SPECIFIC phrases only: none of these is in a family ('momentum', 'breakout', 'VWAP', 'range', 'month',
# 'first hour', 'Tom', 'or breaks' alone must not block an idea)
FAMILY_NEG = [
    ("QL_MOM12", "Buy when 5m momentum (ROC of 12 bars) is positive and the 50-bar trend is up; exit at the close."),
    ("QL_BREAKOUT", "Momentum breakout: a close above the 50-bar high buys; trailing stop 2 ATR."),
    ("QL_NR7", "Breakout of a 20-bar range after a volatility contraction (NR7): buy a close above the range high."),
    ("QL_VWAPTREND", "Long when price is above the session VWAP and the 20-bar slope is up; exit on a close below "
                     "VWAP."),
    ("QL_VWAPX", "Long when close > VWAP + 0.5*ATR, short when close < VWAP - 0.5*ATR (momentum); stop 1 ATR."),
    ("QL_EXITVWAP", "Long on a 20-bar high; exit at VWAP or at the close."),
    ("QL_DONCH", "Skip the first 30 minutes; then a close that breaks above the 20-bar Donchian high enters long."),
    ("QL_FIRSTHOUR_VOL", "In the first hour, compute realised volatility; if it is in the top decile, short at 11:00."),
    ("QL_LUNCH", "After the first hour, fade any move larger than 2 ATR toward the 20-bar mean."),
    ("QL_TD9", "Tom DeMark's TD Sequential 9-count exhaustion: fade the 9th bar."),
    ("QL_TGT", "Exit at the target or breaks the trailing stop; enter on a 20-bar high."),
    ("QL_MTREND", "Monthly trend filter: trade only when the close is above the 1-month moving average."),
    ("QL_GAPFADE", "Fade the overnight gap: short when the open is above yesterday's close by 1 ATR, cover at "
                   "yesterday's close."),
    ("QL_TPT_NQ", _TPT),
    # review round 3: passing mentions - a filter, a warm-up, an exit, a negated clause, a gap, a name - are not the rule
    ("QL_DONCHIAN_PM", "No entries in the first hour. After 10:30, compute a rolling 20-bar range; when a bar closes "
                       "above the range high buy at the next bar's open, below the range low sell."),
    ("QL_DONCH20", "The first 6 bars are warm-up only (no trades). Then a 12-bar box: a close above the box high buys at "
                   "the next bar's open; a close below the box low sells."),
    ("QL_PM_REVERSAL", "Skip days where the first hour range is below its 20-day median. After 14:00, if price is above "
                       "the range high of the day, sell at the next bar's open (late-day exhaustion fade)."),
    ("QL_VWAP_TREND", "After 10:30, when the 5m close crosses above session VWAP and the VWAP slope is positive, buy at "
                      "the next bar's open. Exit when price reverts to VWAP or at the last bar."),
    ("QL_VWAP_PULLBACK", "In an uptrend (close above VWAP for 12 bars) buy the first pullback that touches VWAP; skip "
                         "entries when price is over-extended (> 2 ATR above the 20-bar mean)."),
    ("QL_VOLTREND", "Trade the 50-bar EMA slope on 5m bars, size by inverse 20-bar ATR; do not trade on the last 2 "
                    "trading days of the month (index rebalancing noise)."),
    ("QL_TOM_DEMARK_SEQ", "DeMark setup: 9 consecutive closes above the close 4 bars earlier; sell the next bar's open."),
    ("QL_X8", "No entries in the first 6 bars (09:30-10:00). Then buy when the close breaks above or equals the 20-bar "
              "high."),
    ("QL_X9", "Ignore signals during the first hour. Afterwards go long when price breaks above or below the 20-bar "
              "Donchian channel."),
    ("QL_X10", "Momentum: buy a 20-bar high when price is above the session VWAP and not over-extended (RSI(14) < 70)."),
    ("QL_X11", "In an uptrend (close above VWAP), buy a pullback that holds above the VWAP; avoid fading strong trends."),
    ("QL_RSIVWAP", "Buy when RSI(14) crosses above 50 and price is above VWAP; skip if over-extended."),
    ("QL_X13", "Trade with the opening gap direction when the gap is more than 0.5 ATR."),
    ("QL_FADE_AM", "If the first-hour move is larger than 2 ATR, short at bar 12 (10:30 open); stop 1 ATR."),
]


@pytest.mark.parametrize("name,mech,fam", FAMILY_POS)
def test_the_family_map_puts_a_known_mechanism_in_its_family(name, mech, fam):
    assert fam in Q.idea_families(name, mech), (name, mech)


@pytest.mark.parametrize("name,mech", FAMILY_NEG)
def test_the_family_map_never_matches_a_generic_word(name, mech):
    assert Q.idea_families(name, mech) == {}


def test_families_read_the_name_and_mechanism_never_the_hypothesis(tmp_path):
    assert set(Q.family_map_brief()) == {"VWAP_REVERSION", "OPENING_RANGE", "OPEN_DRIVE", "GAMMA", "TURN_OF_MONTH"}
    lab = _ran_lab(tmp_path)
    s = Q.IdeaSession(lab, {"id": "t-hyp", "source": "own"}, dead_rows_fn=lambda: [])
    r = s.t_propose("QL_HIGH50_NQ", "Unlike a VWAP mean-reversion fade to VWAP or an opening range breakout, a fresh "
                    "50-bar high late in the day marks trend continuation.",
                    "Buy at bar 60 (14:30 open) when bar 59's close is a 50-bar high; exit at the session's last bar.",
                    0.4, 120, "NQ", "5m", first_signal_bar={"index": 60, "clock": "14:30"})
    assert r["accepted"] is True, r


def test_norm_idea_name():
    assert Q.norm_idea_name("QL_VWAPREVERT_NQ") == "VWAPREVERT"
    assert Q.norm_idea_name("QL_ES_MOMBREAK") == Q.norm_idea_name("QL_MOMBREAK_ES_V2") == "MOMBREAK"
    assert Q.norm_idea_name("QL_TPT_NQ_5M") == "TPT"
    # review #19: a timeframe / version / instrument token glued to a word is the same name as the underscored one
    assert Q.norm_idea_name("QL_NOISE2M_TREND") == Q.norm_idea_name("QL_NOISE_2M_TREND") == "NOISETREND"
    assert Q.norm_idea_name("QL_SCALP2M") == Q.norm_idea_name("QL_SCALP_2M") == "SCALP"
    assert Q.norm_idea_name("QL_TRENDV2") == Q.norm_idea_name("QL_TREND_V2") == "TREND"
    assert Q.norm_idea_name("QL_VWAPNQ") == Q.norm_idea_name("QL_VWAP_NQ") == "VWAP"
    assert Q.norm_idea_name("QL_TRENDN") == "TRENDN" and Q.norm_idea_name("QL_MOM12") == "MOM12"


def test_ran_ideas_reads_state_and_the_idea_folders(tmp_path):
    lab = _ran_lab(tmp_path)
    ran = Q.ran_ideas(lab)
    assert [r["name"] for r in ran] == ["QL_VWAPREVERT_NQ", "QL_MOMDRIVE", "QL_ES_MOMBREAK", "QL_TPT_NQ",
                                        "QL_TOM_CALENDAR_NQ", "QL_GAPSCALP_NQ"]  # one per name; no-proposal i7 out
    v = ran[0]
    assert v["runs"] == 2 and v["ids"] == ["i1", "i5"] and len(v["_mechs"]) == 2 and "-4.91" in v["verdict"]
    assert v["families"] == ["VWAP_REVERSION"] and ran[1]["families"] == ["OPENING_RANGE", "OPEN_DRIVE"]
    assert ran[4]["families"] == ["TURN_OF_MONTH"] and ran[3]["families"] == []
    assert not ran[4]["retry_ok"] and ran[5]["retry_ok"] and ran[5]["verdict"].startswith("ABORTED")
    assert [r["name"] for r in Q.ran_ideas(lab, exclude="i4")] == ["QL_VWAPREVERT_NQ", "QL_MOMDRIVE",
                                                                   "QL_ES_MOMBREAK", "QL_TOM_CALENDAR_NQ",
                                                                   "QL_GAPSCALP_NQ"]
    brief = Q.ran_ideas_brief(ran)
    assert brief[0].startswith("QL_VWAPREVERT_NQ [VWAP_REVERSION] (own, ran 2x): On NQ 5m") and "-> PRE-WF" in brief[0]
    assert "NOT a verdict on the idea" in brief[5] and "NOT a verdict" not in brief[4]
    assert sorted(os.listdir(os.path.join(lab.home, "ideas"))) == ["i%d" % k for k in range(1, 9)]   # read only


def test_every_run_idea_is_checked_though_only_the_latest_are_listed(tmp_path):
    ran = [{"name": "QL_IDEA%02d" % i, "norm": "IDEA%02d" % i, "source": "own", "runs": 1, "ids": [str(i)],
            "mechanism": "rule %d" % i, "verdict": "x", "families": [], "_mechs": ["rule %d" % i]} for i in range(30)]
    brief = Q.ran_ideas_brief(ran)
    assert len(brief) == Q.RAN_LIST_MAX + 1 and brief[-1].startswith("... and 5 older ideas")
    assert brief[0].startswith("QL_IDEA05")
    assert Q.dedupe_check("QL_IDEA00", "a different rule entirely, long and short", ran)["refused"]


def test_propose_refuses_an_idea_the_lab_already_ran_without_using_a_slot(tmp_path):
    A = _arrays()
    h = Harness(A, _intraday_trades(A))
    lab = _ran_lab(tmp_path)
    os.makedirs(os.path.join(lab.plugin_repo, "augur_strategies"), exist_ok=True)
    s = Q.IdeaSession(lab, {"id": "t-dd", "source": "shelf", "shelf": {"n": 40}, "shelf_n": 40}, poster=h.poster,
                      sandbox=h.sandbox, dead_rows_fn=lambda: [], master_loader=h.loader)
    hyp = "A hypothesis about intraday NQ behaviour that is long enough."
    # (1) the same name, a different plugin (the 10-15 QL_VWAPREVERT_NQ x2)
    r = s.t_propose("QL_VWAPREVERT_NQ", hyp, "Short a close 3 ATR above the 50-bar mean; cover at the mean.", 0.4,
                    150, "NQ", "5m", first_signal_bar=FSB0)
    assert r["accepted"] is False and r["gate"] == "already run (MANAGER #148)"
    assert "already ran an idea named QL_VWAPREVERT_NQ" in r["reason"] and r["proposal_slots_left"] == Q.MAX_PROPOSALS
    assert any(x.startswith("QL_VWAPREVERT_NQ [VWAP_REVERSION]") for x in r["already_run"])
    # (2) a new name in a family the lab ran - a shelf idea whose mechanism duplicates a run idea
    r = s.t_propose("QL_SNAPBACK_NQ", hyp, "Fade moves of more than 2 ATR away from the session VWAP; target the VWAP.",
                    0.4, 150, "NQ", "5m", first_signal_bar=FSB0)
    assert r["accepted"] is False and "mechanism family VWAP_REVERSION" in r["reason"]
    assert "QL_VWAPREVERT_NQ" in r["reason"]
    r = s.t_propose("QL_FIRSTBAR_ES", hyp, "Buy a close above the first 30-minute high; sell below its low.", 0.4, 150,
                    "ES", "5m", first_signal_bar=FSB0)
    assert r["accepted"] is False and r["matches"][0]["family"] == "OPENING_RANGE"
    # (3) a near copy of a run idea's rule under a new name (no family)
    r = s.t_propose("QL_EMAPHASE_NQ", hyp, _TPT.replace("span=20", "span 20").replace("One trade per session. ", ""),
                    0.4, 150, "NQ", "5m", first_signal_bar=FSB0)
    assert r["accepted"] is False and r["matches"][0]["why"] == "overlap" and "QL_TPT_NQ" in r["reason"]
    assert s.idea["proposals"] == [] and len(s.idea["dedupe_refusals"]) == 4          # no slot used
    assert [e["event"] for e in s.idea["events"]].count("dedupe_refused") == 4
    # a momentum idea that is in no taken family passes
    r = s.t_propose("QL_ROC12_NQ", hyp, "Buy at bar 13 (10:35 open) when the 12-bar rate of change is positive and the "
                    "50-bar slope is up; exit at the session's last bar.", 0.4, 150, "NQ", "5m",
                    first_signal_bar={"index": 13, "clock": "10:35"})
    assert r["accepted"] is True and "not a repeat of the 6 ideas" in r["already_run"]
    assert s.idea["proposal"]["families"] == [] and len(s.idea["proposals"]) == 1
    dd = s.idea["proposal"]["dedupe"]                                            # stored for the prereg (review #16)
    assert dd["ideas_checked"] == 6 and dd["reason"].startswith("not a repeat") and dd["at"]


def test_qwen_gets_the_ideas_the_lab_already_ran_before_it_proposes(tmp_path):
    lab = _ran_lab(tmp_path)
    ran = Q.ran_ideas(lab)
    p = Q.idea_prompt({"source": "own"}, 18, 6, ran=ran)
    assert "IDEAS THE LAB HAS ALREADY RUN" in p and "QL_VWAPREVERT_NQ [VWAP_REVERSION] (own, ran 2x)" in p
    assert "Mechanism families already taken: " in p and "TURN_OF_MONTH (turn-of-the-month" in p
    assert "IDEAS THE LAB HAS ALREADY RUN" not in Q.idea_prompt({"source": "own"}, 18, 6)
    s = Q.IdeaSession(lab, {"id": "t-ideas", "source": "own"}, dead_rows_fn=lambda: [])
    t = s.t_ideas()
    assert len(t["already_run"]) == 6 and "OPENING_RANGE" in t["families_taken"] and "VWAP_REVERSION" in t["family_map"]
    assert "propose() refuses" in Q.system_prompt() and "the LAB already ran" in Q.system_prompt()
    chat = ScriptChat([("finish", {})])
    Q.run_idea(lab, s.idea, chat, max_steps=3, session_kw=dict(poster=lambda t: 1, sandbox=None))
    assert "QL_MOMDRIVE [OPENING_RANGE, OPEN_DRIVE] (scalper)" in chat.seen[0][1]["content"]


# ---- C. the first-signal-bar contract (TTM #144) and E. the bar-index convention (TTM #145)
def test_bar_labels_name_a_bar_one_way():
    assert Q.bar_label(12, "5m") == "bar 12 (10:30 open)" and Q.bar_clock(11, "5m") == "10:25"
    assert Q.bar_label(12, "1m") == "bar 12 (09:42 open)" and Q.bar_label(0, "15m") == "bar 0 (09:30 open)"
    assert Q.bar_label(25, "2m") == "bar 25 (10:20 open)" and Q.bars_per_session("5m") == 78


@pytest.mark.parametrize("value,tf,index", [
    ({"index": 12, "clock": "10:30"}, "5m", 12), ('{"index": 26, "clock": "11:40"}', "5m", 26),
    ("bar 12 (10:30 open)", "5m", 12), ([12, "09:42"], "1m", 12), ({"index": 0, "clock": "9:30"}, "15m", 0),
])
def test_parse_first_signal_bar_accepts_one_convention(value, tf, index):
    got = Q.parse_first_signal_bar(value, tf)
    assert got["index"] == index and got["label"] == Q.bar_label(index, tf) and got["timeframe"] == tf


@pytest.mark.parametrize("value,match", [
    (None, "first_signal_bar is required"), ({"index": 12}, "clock is required"),
    ({"index": 12, "clock": "10:35"}, "disagree: on 5m bars, bar 12 OPENS at 10:30"),
    ({"index": 78, "clock": "16:00"}, "outside the session"), ({"index": 2.5, "clock": "09:40"}, "whole number"),
])
def test_parse_first_signal_bar_refuses(value, match):
    with pytest.raises(Q.ToolRefused, match=match):
        Q.parse_first_signal_bar(value, "5m")


def test_propose_requires_the_first_signal_bar_and_lints_bar_names(tmp_path):
    A = _arrays()
    lab, s = _session(tmp_path, Harness(A, _intraday_trades(A)))
    args = ("QL_TURNPT_NQ", "Slow and fast trend signals that disagree mark turning points in NQ.",
            "Decide on bar 25's close, enter at bar 26 (11:45 open) in the direction both trend speeds agree on.",
            0.6, 150, "NQ", "5m")
    with pytest.raises(Q.ToolRefused, match="first_signal_bar is required"):
        s.t_propose(*args)
    with pytest.raises(Q.ToolRefused, match="disagree"):
        s.t_propose(*args, first_signal_bar={"index": 26, "clock": "11:45"})
    assert s.idea["proposals"] == []                                           # refusals use no slot
    r = s.t_propose(*args, first_signal_bar={"index": 26, "clock": "11:40"})
    assert r["accepted"] and r["first_signal_bar"].startswith("bar 26 (11:40 open) on 5m bars")
    assert s.idea["proposal"]["first_signal_bar"] == {"index": 26, "clock": "11:40", "label": "bar 26 (11:40 open)",
                                                      "timeframe": "5m"}
    notes = " | ".join(r["bar_convention"])
    assert "'bar 25' -> 'bar 25 (11:35 open)'" in notes and "bar 26 OPENS at 11:40" in notes
    spec = next(t for t in Q.TOOLS if t["name"] == "propose")["parameters"]
    assert "first_signal_bar" in spec["required"]


def test_first_bar_violations_use_the_in_session_index():
    idx = pd.DatetimeIndex([pd.Timestamp("2015-01-05 09:30") + pd.Timedelta(minutes=5 * k) for k in range(78)] +
                           [pd.Timestamp("2015-01-06 09:30") + pd.Timedelta(minutes=5 * k) for k in range(78)])
    did = np.r_[np.zeros(78, int), np.ones(78, int)]
    trades = [(3, 10, 1.0, 1, 1.0), (78 + 25, 78 + 30, 1.0, -1, 1.0), (78 + 30, 78 + 40, 1.0, 1, 1.0)]
    v = Q.first_bar_violations(trades, did, idx, 26)
    assert (v["n"], v["checked"], v["earliest_session_bar"], v["first_signal_bar"]) == (2, 3, 3, 26)
    assert v["examples"][0] == {"entry_bar": 3, "session_bar": 3, "time": "2015-01-05 09:45", "side": 1}
    assert v["examples"][1]["session_bar"] == 25 and v["examples"][1]["side"] == -1
    assert Q.first_bar_violations(trades, did, None, 3)["n"] == 0


class _FsbContractHarness(Harness):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.reqs = []

    def sandbox(self, mode, path, sha, req, workdir, timeout=None, label=None):
        self.reqs.append((mode, dict(req)))
        if mode == "contract":
            self.calls.append(("sandbox", mode))
            return {"ok": False, "warnings": [], "problems": ["FIRST-SIGNAL-BAR CONTRACT (TTM #144): 1 of 9 smoke ..."],
                    "first_signal_bar": {"first_signal_bar": 7, "checked": 9, "n": 1, "earliest_session_bar": 3},
                    "first_signal_bar_violations": [{"entry_bar": 5, "session_bar": 3, "time": "2015-01-02 09:45",
                                                     "side": 1}]}
        return super().sandbox(mode, path, sha, req, workdir, timeout, label)


def test_a_smoke_entry_before_the_first_signal_bar_fails_the_contract_gate(tmp_path):
    A = _arrays()
    h = _FsbContractHarness(A, _intraday_trades(A))
    lab, s = _session(tmp_path, h)
    assert s.t_propose("QL_TURNPT_NQ", "Slow and fast trend signals that disagree mark turning points in NQ.",
                       "Decide on bar 6's close (10:05), fill at bar 7 (10:05 open); trade with both trend speeds.",
                       0.6, 150, "NQ", "5m", first_signal_bar={"index": 7, "clock": "10:05"})["accepted"]
    w = s.t_write_plugin("QL_TURNPT_NQ", Q.TEMPLATE_PLUGIN)
    assert not w["passed"] and w["gate"] == "contract" and w["offending_entries"][0]["session_bar"] == 3
    assert "bar 7 (10:05 open)" in w["how_to_fix"][0] and "FILL bar is >= 7" in w["how_to_fix"][0]
    assert h.reqs[0][0] == "contract" and h.reqs[0][1]["first_signal_bar"] == 7
    assert ("sandbox", "lookahead") not in h.calls


def _pre_trades_at_bar1():
    """The promoted PRE-WF set, but every entry on the session's SECOND bar (the 11:00 bar = bar 18 by the clock on 5m
    bars; the first, 10:00, is bar 6)."""
    P = _pre_arrays()
    did = P["day_id"]
    out = []
    for t in _pre_trades(True):
        ix = np.flatnonzero(did == did[t[0]])
        out.append((int(ix[1]), int(ix[1]), t[2], 1, float(P["open"][ix[1]])))
    return out


def _fsb_session(tmp_path, pre_sets):
    A = _arrays()
    h = SeqHarness(A, _intraday_trades(A), pre_sets)
    lab, s = _session(tmp_path, h)
    assert s.t_propose("QL_TURNPT_NQ", "Slow and fast trend signals that disagree mark turning points in NQ.",
                       "Decide on bar 6's close (10:05), fill at bar 7 (10:05 open) in the direction both trend speeds "
                       "agree on.", 0.6, 150, "NQ", "5m", first_signal_bar={"index": 7, "clock": "10:05"})["accepted"]
    assert s.t_write_plugin("QL_TURNPT_NQ", Q.TEMPLATE_PLUGIN)["passed"]
    return lab, s, h


def test_a_pre_wf_entry_before_the_first_signal_bar_is_a_hard_gate_not_a_verdict(tmp_path):
    lab, s, h = _fsb_session(tmp_path, [_pre_trades(True), _pre_trades_at_bar1()])
    r = s.t_run_stage_a("QL_TURNPT_NQ")
    assert r["verdict"].startswith("NONE YET - hard gate: FIRST-SIGNAL-BAR CONTRACT (TTM #144)"), r
    # the synthetic sessions' first bar opens at 10:00 = bar 6 by the clock (the convention), the first in its session
    off = r["offending_entries"][0]
    assert r["first_signal_bar"] == "bar 7 (10:05 open)" and off["session_bar"] == 6 and off["time"].endswith("10:00")
    assert off["position_in_session"] == 0
    assert r["fix_retries_left"] == 2 and "proposal is frozen" in r["what_to_do"]
    assert len(h.posts) == 1 and not s.idea.get("stage_pre_wf") and s.idea["sanity_open"]     # the prereg only
    assert s.idea["sanity"][-1]["kind"] == "first_signal_bar"
    text = open(s.idea["prereg"]["path"], encoding="utf-8").read()
    assert "## Timing contract - the first entry bar (TTM #144)" in text and "bar 7 (10:05 open)" in text
    assert "no entry may FILL at an in-session bar index < 7" in text and "first entry bar 7 (10:05 open)" in h.posts[0]
    assert s.t_write_plugin("QL_TURNPT_NQ", Q.TEMPLATE_PLUGIN + "\n# entries from bar 1\n")["passed"]
    r2 = s.t_run_stage_a("QL_TURNPT_NQ")
    assert r2["ran"] and "pre_wf_numbers" in r2 and s.idea["stage_pre_wf"]["first_signal_bar_check"]["n"] == 0
    assert "TTM #144 fix retry 1" in h.posts[1] and h.posts[2].startswith("QWEN LAB: QL_TURNPT_NQ PRE-WF")


def test_still_entering_early_after_two_retries_is_a_broken_plugin(tmp_path):
    early = _pre_trades(True)
    lab, s, h = _fsb_session(tmp_path, [early, early, early])
    s.t_run_stage_a("QL_TURNPT_NQ")
    for k in (1, 2):
        assert s.t_write_plugin("QL_TURNPT_NQ", Q.TEMPLATE_PLUGIN + "\n# try %d\n" % k)["passed"]
        r = s.t_run_stage_a("QL_TURNPT_NQ")
    assert r["verdict"].startswith("BROKEN PLUGIN (first-signal-bar contract: %d entries before bar 7)" % len(early))
    assert s.closed and "dead" not in s.idea["outcome"].lower()


@needs_shared
def test_sandbox_contract_checks_the_first_signal_bar_on_real_pre_wf_bars(tmp_path):
    base = dict(instrument="NQ", timeframe="5m", source="db_noadj_rth", session="rth",
                master_filename="NOADJ_NQ_5m_RTH.csv", cost_pts=0.533, mult=20.0, smoke_to=Q.SMOKE_TO)
    r = _sb(tmp_path, "contract", Q.TEMPLATE_PLUGIN, first_signal_bar=8, **base)
    assert not r["ok"] and r["first_signal_bar"]["earliest_session_bar"] == 7 and r["first_signal_bar"]["n"] > 0
    assert any(p.startswith("FIRST-SIGNAL-BAR CONTRACT (TTM #144)") for p in r["problems"])
    assert r["first_signal_bar_violations"][0]["session_bar"] == 7
    assert any(x["time"][11:16] == "10:05" for x in r["first_signal_bar_violations"])   # bar 7 (10:05 open)
    assert r["first_signal_bar"]["index_by"] == "clock"
    # review #11: the defaults fill from bar 7, but range_bars is SEARCHED down to 3 (fills from bar 4 (09:50 open)) -
    # a hard failure now (it was a warning), with the offending knob value
    r = _sb(tmp_path, "contract", Q.TEMPLATE_PLUGIN, first_signal_bar=7, **base)
    assert not r["ok"] and r["first_signal_bar"]["n"] == 0
    bad = r["first_signal_bar_corner_violations"]
    assert [(b["knob"], b["value"], b["earliest_session_bar"]) for b in bad] == [("range_bars", 3, 4)]
    assert any("at the knob values the Auto-Validate searches: range_bars=3" in p for p in r["problems"])
    r = _sb(tmp_path, "contract", Q.TEMPLATE_PLUGIN, first_signal_bar=4, **base)
    assert r["ok"], r
    assert r["first_signal_bar"]["n"] == 0 and r["first_signal_bar"]["checked"] == r["smoke"]["trades"] > 100
    assert len(r["first_signal_bar_corners"]) == 4 and all(c["n"] == 0 for c in r["first_signal_bar_corners"])


def test_the_prompt_and_the_prereg_name_bars_one_way(tmp_path):
    sp = Q.system_prompt()
    assert "BAR INDEX CONVENTION" in sp and "'bar 12 (10:30 open)'" in sp and "0-based IN-SESSION index" in sp
    assert "fills at a bar's OPEN or at its CLOSE" in sp and "first_signal_bar" in sp
    assert "atr[k-1] - never an ATR / range / volatility window that includes bar k" in sp
    A = _arrays()
    h = Harness(A, _intraday_trades(A))
    lab, s = _session(tmp_path, h)
    _propose_and_write(s)
    s.t_run_stage_a("QL_TURNPT_NQ")
    text = open(s.idea["prereg"]["path"], encoding="utf-8").read()
    assert "## Bar index convention (TTM #145)" in text and "on 5m bars bar 12 (10:30 open)" in text
    assert "(bar 11 closes at 10:30)" in text and "'at bar k's open' fills at bar k's OPEN price" in text
    assert "first_signal_bar (Qwen's stated pre-data input): bar 0 (09:30 open)" in text
    assert "entry-bar inputs - the first bar at risk's high / low / close / volume moved - on 6 trades, 4 conclusive" \
        in text
    assert "every searched knob at its min and its max (0 knob values, none earlier)" in text
    assert "## Hard gates passed before this prereg (gates v2)" in text
    assert not re.search(r"NOT (?:checked|recorded|run)", text)                 # every check here ran (review #16)
    assert "checked at propose (" in text and "re-checked now: not a repeat" in text


def test_bar_convention_notes_are_soft_lint():
    assert Q.bar_convention_notes("enter at bar 12 (10:30 open), exit at bar 77 (15:55 open)", "5m") == []
    n = Q.bar_convention_notes("enter at bar 12's open", "5m")
    assert n == ["name bars as 'bar k (HH:MM open)': 'bar 12' -> 'bar 12 (10:30 open)'"]
    assert "bar 12 OPENS at 10:30 (its close is 10:35)" in Q.bar_convention_notes("bar 12 (10:35 close)", "5m")[0]


# ---- D. entry-bar stop / size inputs (TTM #145)
# the QL_ES_MOMBREAK shape with a WIDE stop: 3 x an ATR over bars up to AND including the entry bar - the stop is almost
# never hit on the entry bar, so the exit-bar phases (and the short-hold sample) never see the level move
_STOP_LINE, _ATR_INCL = LEAKS["wide stop from an ATR that includes the entry bar"]
_ATR_BEFORE = ("            atr = float(np.mean(h[max(0, e - 14):e] - l[max(0, e - 14):e]))\n"
               "            stop = entry - side * 3.0 * float(stop_frac) * atr")


@needs_shared
def test_entry_bar_phase_catches_an_atr_that_includes_the_entry_bar(tmp_path):
    code = Q.TEMPLATE_PLUGIN.replace(_STOP_LINE, _ATR_INCL)
    assert code != Q.TEMPLATE_PLUGIN and Q.safety_gate(code)[0]
    old = _sb(tmp_path, "lookahead", code, synthetic_days=80, la_k=10, instrument="NQ", eb_k=0)
    assert old["ok"], "the exit-bar phases alone should miss this shape (else the test proves nothing): %s" % old
    assert old["entry_bar_checked"] == 0
    r = _sb(tmp_path, "lookahead", code, synthetic_days=80, la_k=10, instrument="NQ")
    assert not r["ok"] and r["entry_bar_conclusive"] >= 1
    p = next(p for p in r["problems"] if p.startswith("LOOK-AHEAD (entry-bar inputs, TTM #145)"))
    assert "(open fill" in p and "moved with that bar's own" in p
    hint = Q.lookahead_hints(r["problems"])[0]
    assert hint.startswith("the trade entered at bar") and "atr[k-1]" in hint


@needs_shared
def test_entry_bar_phase_passes_an_atr_from_the_bars_before_the_entry(tmp_path):
    code = Q.TEMPLATE_PLUGIN.replace(_STOP_LINE, _ATR_BEFORE)
    r = _sb(tmp_path, "lookahead", code, synthetic_days=80, la_k=10, instrument="NQ")
    assert r["ok"], r
    assert r["entry_bar_checked"] >= 3 and r["entry_bar_conclusive"] >= 3


def test_entry_bar_push_redraws_the_bar_one_way_from_its_open():
    A = _arrays("2016-06-01", "2016-06-10")
    o = A["open"][5]
    B, ext = Q._sb_push(A, 5, 1, "adverse", 7.0)
    # a long's adverse push: the low 7 below its own, the high pulled in to the open (no target can be crossed)
    assert ext == "low" and B["low"][5] == A["low"][5] - 7.0 and B["high"][5] == o and B["open"][5] == o
    for k in ("open", "high", "low", "close", "volume"):
        assert np.array_equal(np.delete(B[k], 5), np.delete(A[k], 5)), k             # nothing else moves
    assert B["close"][5] == A["close"][5]                                            # no close_q: the close stays
    B, ext = Q._sb_push(A, 5, -1, "adverse", 7.0, close_q=0.85, vol=55.0)
    assert ext == "high" and B["high"][5] == A["high"][5] + 7.0 and B["low"][5] == o
    assert abs(B["close"][5] - (o + 0.85 * (B["high"][5] - o))) < 1e-9 and B["volume"][5] == 55.0
    # an intrabar entry's fill price stays inside the bar (keep)
    B, ext = Q._sb_push(A, 5, 1, "adverse", 7.0, keep=o + 3.0)
    assert B["high"][5] == o + 3.0 and B["low"][5] == A["low"][5] - 7.0
    B, ext = Q._sb_push(A, 5, 1, "favourable", 7.0, later=(2.0, 100.0), close_q=0.15)
    assert ext == "high" and B["high"][5] == A["high"][5] + 7.0 and B["low"][5] == o
    assert np.array_equal(B["close"][:5], A["close"][:5]) and not np.array_equal(B["close"][6:], A["close"][6:])
    assert abs(B["open"][6] - B["close"][5]) <= 1.0 + 1e-9                         # later bars around bar f's NEW close


def test_lookahead_hints_for_the_entry_bar_phase():
    p = ("LOOK-AHEAD (entry-bar inputs, TTM #145): 1 of 6 trades: ENTRY-BAR INPUT at bar 40 (close fill 2050.2500), "
         "first bar at risk 41: pushes ...")
    h = Q.lookahead_hints([p])
    assert h[0].startswith("the trade entered at bar 40's CLOSE") and "bar 41's high / low" in h[0]
    h = Q.lookahead_hints([p.replace("(close fill", "(open fill").replace("risk 41", "risk 40")])
    assert h[0].startswith("the trade entered at bar 40's OPEN") and "bar 40's own high / low / close" in h[0]
    h = Q.lookahead_hints(["at stop_frac=0.25: " + p.replace("(close fill", "(intrabar fill").replace("risk 41",
                                                                                                    "risk 40")])
    assert h[0].startswith("the trade entered INSIDE bar 40") and "atr[k-1]" in h[0]


# ======================================================================== review round 3 (fix round 2's review)
# ---- A. shelf_open.txt: an undated line never takes the file's write time; an unknown line never opens a paper
def test_an_undated_line_never_reopens_a_paper_the_lab_closed(tmp_path, monkeypatch, capsys):
    import datetime as dt
    monkeypatch.setattr(Q, "LAB_HOME", Q.LAB_HOME)
    monkeypatch.setattr(Q, "shelf_ideas", lambda *a, **k: [dict(p) for p in _FAKE_SHELF])
    old = dt.datetime(2026, 10, 15, 13, 50, 57).timestamp()
    # (1) the reviewer's a1.py: a bare '34', the lab closed 34 at 14:52:43, then MANAGER closes another paper
    home = str(tmp_path / "h1")
    lab = Q.Lab(home=home, plugin_repo=str(tmp_path / "repo"))
    lab.state["closed_shelf"]["34"] = {"at": "2026-10-15 14:52:43", "idea": "x", "why": "the lab ran a PRE-WF Stage A"}
    lab.save()
    with open(lab.shelf_open_path, "w", encoding="utf-8") as f:
        f.write("34\n")
    os.utime(lab.shelf_open_path, (old, old))
    assert Q.Lab(home=home).shelf_marks()[34] == ("open", "") and Q.Lab(home=home).open_shelf_numbers() == []
    assert Q.main(["shelf-close", "12", "--home", home]) == 0
    assert "open now: none" in capsys.readouterr().out
    assert Q.Lab(home=home).open_shelf_numbers() == []                   # the append did not re-open 34
    # (2) mtime_repro.py: a bare '12' the lab closed, a dated open of 34, then shelf-close 34 - 12 stays closed
    home = str(tmp_path / "h2")
    lab = Q.Lab(home=home, plugin_repo=str(tmp_path / "repo"))
    lab.state["closed_shelf"]["12"] = {"at": "2026-10-15 10:00:00", "idea": "y", "why": "the lab ran it"}
    lab.save()
    with open(lab.shelf_open_path, "w", encoding="utf-8") as f:
        f.write("12\n2026-10-15 13:50:57 34\n")
    os.utime(lab.shelf_open_path, (old, old))
    assert Q.Lab(home=home).open_shelf_numbers() == [34]
    assert Q.main(["shelf-close", "34", "--home", home]) == 0
    assert Q.Lab(home=home).open_shelf_numbers() == []
    # a bare line still opens a paper the lab never ran, and a DATED re-open (shelf-open) still beats a lab closure
    with open(lab.shelf_open_path, "a", encoding="utf-8") as f:
        f.write("40\n")
    assert Q.Lab(home=home).open_shelf_numbers() == [40]
    assert Q.main(["shelf-open", "12", "--home", home]) == 0
    assert Q.Lab(home=home).open_shelf_numbers() == [12, 40]


def test_the_shelf_file_ignores_a_line_it_does_not_understand(tmp_path, capsys):
    home = str(tmp_path / "home")
    lab = Q.Lab(home=home, plugin_repo=str(tmp_path / "repo"))
    with open(lab.shelf_open_path, "w", encoding="utf-8") as f:
        f.write("2026-10-16 11:00:00 open 30 31\n"
                "2026-10-16 11:05:00 closing 31\n"              # 'closing' / 'closes' are closes (were read as opens)
                "2026-10-16 11:06 closes 30\n"                  # HH:MM is a time
                "2026-10-16 CLOSE 32\n"                         # a date alone (its numbers were all read as opens)
                "2026-10-15 09:00:00 32, 33\n"                  # file order wins: 32 re-opened
                "please open 10 and 16\n"                       # not a shelf line: ignored, never opens 10 / 16
                "2026-10-16 reopen 17\n")
    lab = Q.Lab(home=home)
    marks = lab.shelf_marks()
    assert marks[31] == ("close", "2026-10-16 11:05:00") and marks[30] == ("close", "2026-10-16 11:06:00")
    assert marks[33] == ("open", "2026-10-15 09:00:00") and not {10, 16, 17, 2026} & set(marks)
    assert lab.open_shelf_numbers() == [32, 33]
    assert len(lab.shelf_warnings) == 2 and "line 6 ignored" in lab.shelf_warnings[0]
    assert Q.main(["status", "--home", home]) == 0
    assert "WARNING shelf_open.txt line 7 ignored" in capsys.readouterr().out


# ---- B. dedupe: the lab's own reworded repeat, risk boilerplate, no-verdict runs, re-opened papers, lost done rows
def test_dedupe_refuses_the_labs_own_reworded_repeat(tmp_path):
    lab = _ran_lab(tmp_path, [("m1", "own", "done", "QL_ES_MOMBREAK", _REAL_MOMBREAK, "PRE-WF DONE - not promoted"),
                              ("d1", "scalper", "done", "QL_MOMDRIVE", _REAL_MOMDRIVE, "PRE-WF DONE - not promoted"),
                              ("v1", "own", "done", "QL_VWAPREVERT_NQ", _REAL_VWAPREVERT, "PRE-WF DONE - not promoted")])
    ran = Q.ran_ideas(lab)
    d = Q.dedupe_check("QL_TRENDN", _REAL_TRENDN, ran)                # 10-16 13:42: it was accepted
    assert d["refused"] and d["matches"][0]["idea"] == "QL_ES_MOMBREAK" and d["matches"][0]["family"] == "OPENING_RANGE"
    w1, w2 = Q._mech_words(_REAL_TRENDN), Q._mech_words(_REAL_MOMBREAK)
    assert len(w1 & w2) / len(w1 | w2) < Q.DEDUPE_JACCARD          # a word count cannot see it - the family does
    d = Q.dedupe_check("QL_VWAP_DEV", "Compute session VWAP; let d = (close - VWAP)/ATR20. If d > 2.5 short at the next "
                       "bar's open, if d < -2.5 go long.", ran)
    assert d["refused"] and d["matches"][0]["idea"] == "QL_VWAPREVERT_NQ"


def test_the_near_copy_check_reads_the_signal_not_the_stop_wording(tmp_path):
    lab = _ran_lab(tmp_path, [("d1", "scalper", "done", "QL_MOMDRIVE", _REAL_MOMDRIVE, "PRE-WF DONE - not promoted"),
                              ("v1", "own", "done", "QL_VWAPREVERT_NQ", _REAL_VWAPREVERT, "PRE-WF DONE - not promoted"),
                              ("t1", "shelf", "done", "QL_TPT_NQ", _TPT, "CLOSED AT THE MAP"),
                              ("n1", "own", "done", "QL_TRENDN", _REAL_TRENDN, "PRE-WF DONE - not promoted")])
    ran = Q.ran_ideas(lab)
    # a new one-line signal followed by QL_TRENDN's whole trailing-stop paragraph: 46% of the words, 6 shared, on the
    # whole text - none on the signal
    rsi2 = ("NQ 5m bars, regular hours 09:30-16:00 ET. Signal: RSI(2) below 5 above the 200-bar EMA, go long at the next "
            "bar's open. " + _REAL_TRENDN[_REAL_TRENDN.index("Trailing stop:"):])
    assert Q.signal_text(rsi2).endswith("go long at the next bar's open.")
    assert not Q.dedupe_check("QL_RSI2_TRAIL", rsi2, ran)["refused"]
    inside = _REAL_MOMDRIVE.replace("Setup: first 12 bars (24 min) form a range. If range <= compress_k x ATR(14 bars, "
                                    "trailing), the session is \"quiet\". Signal: a bar whose close breaks above the "
                                    "range high (long) or below the range low (short).",
                                    "Setup: an inside bar (high < prior high and low > prior low) after bar 15. Signal: "
                                    "a bar whose close breaks above the inside bar's high (long) or below its low "
                                    "(short).")
    assert inside != _REAL_MOMDRIVE and "chandelier-style" in inside
    d = Q.dedupe_check("QL_INSIDE_BAR", inside, ran)                 # dd5.py: was refused at 69% overlap
    assert not d["refused"], d
    assert "chandelier" not in Q.signal_text(_REAL_MOMDRIVE) and "Entry: next bar's open." in Q.signal_text(
        _REAL_MOMDRIVE)
    rsi = _REAL_VWAPREVERT.replace("(1) session VWAP = sum(close[session_start..k]) / (k - session_start + 1) as a "
                                   "proxy (no volume data needed for the signal; the engine charges cost separately)",
                                   "(1) RSI(14) of closes over bars k-13..k").replace(
        "If close[k] > VWAP + 2.5*ATR20, enter SHORT at bar k+1's open. If close[k] < VWAP - 2.5*ATR20, enter LONG",
        "If RSI(14) > 85, enter SHORT at bar k+1's open. If RSI(14) < 15, enter LONG")
    assert "vwap" not in rsi.lower()
    assert not Q.dedupe_check("QL_RSI_EXTREME", rsi, ran)["refused"]
    d = Q.dedupe_check("QL_EMAPHASE_NQ", _TPT.replace("span=20", "span 20").replace("Stop: 1.5x ATR(14) from entry.",
                                                                                     "Stop: 3 x range."), ran)
    assert d["refused"] and d["matches"][0]["why"] == "overlap"      # a copy of the SIGNAL is still a copy


def test_a_run_with_no_verdict_and_a_reopened_paper_block_only_their_name(tmp_path):
    rows = [("s34", "shelf", "done", "QL_TOM_CALENDAR_NQ", _REAL_TOM, "PRE-WF DONE - not promoted (-1.1 < 15)", 34),
            ("b1", "scalper", "done", "QL_DRIVE_NQ", "Momentum drive from the open: if the first 3 bars all close up, "
             "buy bar 3's open; hold 30 minutes.", "BROKEN PLUGIN (3 trades) - the model finished without a fix"),
            ("v1", "own", "done", "QL_VWAPREVERT_NQ", _REAL_VWAPREVERT, "PRE-WF DONE - not promoted")]
    lab = _ran_lab(tmp_path, rows, closed_shelf={"34": {"at": "2026-10-15 14:52:43", "idea": "s34", "why": "ran"}})
    with open(lab.shelf_open_path, "w", encoding="utf-8") as f:
        f.write("2026-10-16 09:00:00 34\n")                          # MANAGER re-opened #34 after the lab ran it
    lab = Q.Lab(home=lab.home, plugin_repo=lab.plugin_repo)
    assert lab.open_shelf_numbers() == [34]
    ran = Q.ran_ideas(lab)
    assert Q.families_taken(ran) == ["TURN_OF_MONTH", "VWAP_REVERSION"]     # the broken OPEN_DRIVE run is not a verdict
    hyp = "Month-end pension rebalancing flows lift index futures into the turn of the month."
    tom = "Buy at bar 0 (09:30 open) on the last 2 trading days of each calendar month; flat at the session's last bar."
    shelf = Q.IdeaSession(lab, {"id": "t-34", "source": "shelf", "shelf": {"n": 34}, "shelf_n": 34},
                          dead_rows_fn=lambda: [])
    assert shelf.t_propose("QL_TOM_CALENDAR_NQ", hyp, tom, 0.3, 30, "NQ", "5m", first_signal_bar=FSB0)[
        "gate"] == "already run (MANAGER #148)"                      # the name: never
    r = shelf.t_propose("QL_TOM_V2_NQ", hyp, tom, 0.3, 30, "NQ", "5m", first_signal_bar=FSB0)
    assert r["accepted"] is True and "QL_TOM_CALENDAR_NQ" in r["already_run"]    # reopen.py: was refused
    own = Q.IdeaSession(lab, {"id": "t-own", "source": "own"}, dead_rows_fn=lambda: [])
    r = own.t_propose("QL_MONTHFLOW_NQ", hyp, tom, 0.3, 30, "NQ", "5m", first_signal_bar=FSB0)
    assert r["accepted"] is False and r["matches"][0]["family"] == "TURN_OF_MONTH"   # another source: still refused
    drive = "Trade the open drive: if the first 3 bars all close down, sell bar 3's open; stop above bar 0's high."
    r = own.t_propose("QL_DRIVE_NQ", hyp, drive, 0.3, 60, "NQ", "5m", first_signal_bar=FSB0)
    assert r["accepted"] is False and r["matches"][0]["why"] == "name"
    r = own.t_propose("QL_OPENDRIVE_SHORT", hyp, drive, 0.3, 60, "NQ", "5m", first_signal_bar=FSB0)
    assert r["accepted"] is True and "QL_DRIVE_NQ" in r["already_run"]   # BROKEN PLUGIN: a retry under a new name


def test_a_closed_idea_without_its_done_row_is_still_an_idea_the_lab_ran(tmp_path):
    import argparse
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    (repo / "augur_strategies").mkdir(parents=True)
    d = home / "ideas" / "20261016-1500-own"
    d.mkdir(parents=True)
    (d / "idea.json").write_text(json.dumps({                       # b_crash.py: closed, then the run was killed
        "id": "20261016-1500-own", "source": "own", "status": "closed",
        "outcome": "PRE-WF DONE - not promoted (pre-WF ROC@30k -4.75 < 15)",
        "proposal": {"name": "QL_VWAPREVERT_NQ", "hypothesis": "h" * 30, "mechanism": _REAL_VWAPREVERT}}),
        encoding="utf-8")
    (home / "state.json").write_text(json.dumps({"current_idea": "20261016-1500-own", "done_ideas": []}),
                                     encoding="utf-8")
    lab = Q.Lab(home=str(home), plugin_repo=str(repo))
    assert [r["name"] for r in Q.ran_ideas(lab)] == ["QL_VWAPREVERT_NQ"]     # the folder scan sees it already
    A = _arrays()
    h = Harness(A, _intraday_trades(A))
    chat = ScriptChat([("propose", {"name": "QL_VWAPREVERT_NQ", "hypothesis": "A stretch from VWAP snaps back intraday.",
                                    "mechanism": _REAL_VWAPREVERT, "prior_sharpe_yearly": 0.4, "trades_per_year": 150,
                                    "instrument": "NQ", "timeframe": "5m", "first_signal_bar": {"index": 26,
                                                                                                "clock": "11:40"}}),
                       ("finish", {})])
    args = argparse.Namespace(home=str(home), plugin_repo=str(repo), idea=None, source="own", think=False,
                              no_beacon=True, max_steps=4, dry_run_validate=True, once=True, no_next_pick=True)
    assert Q.run(args, chat=chat, session_kw=dict(poster=h.poster, sandbox=h.sandbox)) == 0
    st = json.load(open(home / "state.json", encoding="utf-8"))
    assert [x["id"] for x in st["done_ideas"]][0] == "20261016-1500-own"   # recorded first, with its result post
    assert h.posts[0].startswith("QWEN LAB: QL_VWAPREVERT_NQ (Qwen's own idea)") and "-4.75" in h.posts[0]
    new = json.load(open(home / "ideas" / st["done_ideas"][1]["id"] / "idea.json", encoding="utf-8"))
    assert new["dedupe_refusals"][0]["name"] == "QL_VWAPREVERT_NQ" and not new.get("proposal")


def test_a_resumed_session_without_a_proposal_gets_the_ideas_the_lab_ran(tmp_path):
    lab = _ran_lab(tmp_path)
    for iid, prop in (("t-res", None), ("t-res2", {"name": "QL_ROC12_NQ", "mechanism": "m" * 30})):
        idea = {"id": iid, "source": "own", "harness_sha": "0" * 64, **({"proposal": prop} if prop else {})}
        d = lab.idea_dir(iid)
        Q.jdump(os.path.join(d, "transcript.json"), {"messages": [
            {"role": "system", "content": "old rules"}, {"role": "user", "content": "old first message"},
            {"role": "assistant", "content": "thinking"}], "calls": []})
        chat = ScriptChat([("finish", {})])
        Q.run_idea(lab, idea, chat, max_steps=3, session_kw=dict(poster=lambda t: 1, sandbox=None))
        note = chat.seen[0][-1]["content"]
        assert note.startswith("RESUMED after a harness update") and "Fix round 3" in note
        assert ("IDEAS THE LAB HAS ALREADY RUN" in note) == (prop is None), iid


# ---- C. the first-signal-bar contract counts bars by the clock; a searched knob is held to it (sandbox test above)
def test_first_bar_violations_count_bars_by_the_clock():
    # a 1m holiday session with two bars missing (09:40, 09:41): the 10:30 bar is the 59th bar, yet bar 60 by the clock
    t0 = pd.Timestamp("2015-02-16 09:30", tz="US/Eastern")
    idx = pd.DatetimeIndex([t0 + pd.Timedelta(minutes=m) for m in range(390) if m not in (10, 11)])
    did = np.zeros(len(idx), int)
    e1030 = int(np.flatnonzero(idx == t0 + pd.Timedelta(minutes=60))[0])
    e1029 = e1030 - 1
    assert e1030 == 58
    v = Q.first_bar_violations([(e1030, e1030 + 5, 1.0, 1, 1.0)], did, idx, 60, tf="1m")
    assert (v["n"], v["earliest_session_bar"], v["index_by"]) == (0, 60, "clock")      # clockfsb.py: was a violation
    v = Q.first_bar_violations([(e1029, e1029 + 5, 1.0, -1, 1.0)], did, idx, 60, tf="1m")
    assert v["n"] == 1 and v["examples"][0]["session_bar"] == 59 and v["examples"][0]["position_in_session"] == 57
    assert v["examples"][0]["time"].endswith("10:29")
    assert Q.first_bar_violations([(e1030, e1030 + 5, 1.0, 1, 1.0)], did, None, 60)["n"] == 1   # no stamps: position
    assert Q.session_bar_index(e1030, 0, idx, "2m") == 30 and Q.session_bar_index(5, 0, None, "1m") == 5


# ---- legacy in-flight ideas (review #9 / #16): never 'not checked' at Stage A; the prereg says what really ran
def test_a_proposal_without_first_signal_bar_never_reaches_stage_a(tmp_path):
    A = _arrays()
    h = Harness(A, _intraday_trades(A))
    lab, s = _session(tmp_path, h)
    _propose_and_write(s)
    pr = s.idea["proposal"]                                   # the 10-16 in-flight shape: before TTM #144 / MANAGER #148
    pr["first_signal_bar"] = None
    pr.pop("families")
    pr.pop("dedupe")
    with pytest.raises(Q.ToolRefused, match="predates the first-signal-bar contract"):
        s.t_run_stage_a("QL_TURNPT_NQ")
    with pytest.raises(Q.ToolRefused, match="predates the first-signal-bar contract"):
        s.t_write_plugin("QL_TURNPT_NQ", Q.TEMPLATE_PLUGIN)
    assert not s.idea.get("prereg") and not s.idea.get("map") and h.posts == []
    # not frozen: a full new proposal (the dedupe runs again), then the current gates, then Stage A
    _propose_and_write(s)
    assert s.idea["proposal"]["dedupe"] and s.idea["plugin"]["gates_version"] == Q.GATES_VERSION
    s.idea["plugin"]["gates_version"] = 1                     # a plugin gated by the older harness
    with pytest.raises(Q.ToolRefused, match="OLDER version of the gates"):
        s.t_run_stage_a("QL_TURNPT_NQ")
    s.idea["plugin"]["gates_version"] = Q.GATES_VERSION
    assert s.t_run_stage_a("QL_TURNPT_NQ")["ran"]


def test_a_frozen_older_proposal_records_only_its_first_signal_bar(tmp_path):
    A = _arrays()
    h = SeqHarness(A, _intraday_trades(A), [_few(3), _pre_trades(True)])
    lab, s = _session(tmp_path, h)
    _propose_and_write(s)
    assert s.t_run_stage_a("QL_TURNPT_NQ")["fix_retries_left"] == 2   # prereg posted, a broken-plugin retry open
    pr = s.idea["proposal"]
    pr["first_signal_bar"] = None                             # an older proposal frozen by its posted prereg
    with pytest.raises(Q.ToolRefused, match="predates"):
        s.t_run_stage_a("QL_TURNPT_NQ")
    with pytest.raises(Q.ToolRefused, match="call propose with ITS name"):
        s.t_propose("QL_OTHER_NQ", "x" * 30, "y" * 30, 0.5, 100, "NQ", "5m", first_signal_bar=FSB0)
    with pytest.raises(Q.ToolRefused, match="disagree"):
        s.t_propose("QL_TURNPT_NQ", "x" * 30, "y" * 30, 0.5, 100, "NQ", "5m", first_signal_bar={"index": 7,
                                                                                               "clock": "10:00"})
    r = s.t_propose("QL_TURNPT_NQ", "ignored", "ignored", 9, 9, "NQ", "5m", first_signal_bar={"index": 0,
                                                                                             "clock": "09:30"})
    assert r["amended"] == "first_signal_bar" and pr["hypothesis"].startswith("Slow and fast") and pr["trades_per_year"] == 150
    assert pr["first_signal_bar"]["label"] == "bar 0 (09:30 open)" and not s.idea["plugin"]["gates_ok"]
    with pytest.raises(Q.ToolRefused, match="has not passed"):
        s.t_run_stage_a("QL_TURNPT_NQ")
    assert s.t_write_plugin("QL_TURNPT_NQ", Q.TEMPLATE_PLUGIN + "\n# fixed\n")["passed"]
    s.t_run_stage_a("QL_TURNPT_NQ")
    assert "first_signal_bar AMENDED at" in h.posts[1] and "to bar 0 (09:30 open)" in h.posts[1]
    assert "## Addendum 1" in open(s.idea["prereg"]["path"], encoding="utf-8").read()


def test_the_prereg_says_not_checked_when_a_check_did_not_run(tmp_path):
    A = _arrays()
    h = Harness(A, _intraday_trades(A))
    lab, s = _session(tmp_path, h)
    _propose_and_write(s)
    pr, g = s.idea["proposal"], s.idea["gates"]
    pr.pop("families")
    pr.pop("dedupe")
    for k in ("first_signal_bar", "entry_bar_checked", "entry_bar_conclusive", "version"):
        g.pop(k, None)
    s.idea["map"] = _clears_map(pr["name"], 0.6, 150)
    pre = s.write_prereg({"filename": "NOADJ_NQ_5m_RTH.csv", "source": "db_noadj_rth", "id": 37}, _pre_arrays())
    text = open(pre["path"], encoding="utf-8").read()
    assert "NOT checked at propose (the proposal predates MANAGER #148); re-checked now: not a repeat" in text
    assert "NOT checked by the contract" in text and "first-signal-bar check NOT recorded" in text
    assert "entry-bar inputs NOT checked (older gates)" in text and "idea dedupe NOT run at propose" in text
    assert "none matched" not in text
    pr["first_signal_bar"] = None
    post = Q.compose_prereg_post(s.idea, pre)
    assert "first entry not stated - not checked" in post and "checked on every PRE-WF entry" not in post


# ---- D. the entry-bar phase: close / volume of the first bar at risk, intrabar entries, mutation survivors
def _eb_plugin(stop=None, target=None, fill="open", check_from_next=False, strict=False):
    """One trade a session: side = sign(close of bar 3 - open of bar 0); fill at bar 4's OPEN ('open'), at bar 3's
    CLOSE ('close', checked from bar 4), INSIDE bar 4 at bar 3's high / low ('intrabar': a stop entry, only when bar
    4 opens inside it and trades through it) or at bar 3's low / high ('limit': a buy limit below bar 4's open, a sell
    limit above it). strict: the entry needs the bar to trade strictly PAST the level ('high > level'). stop /
    target(o, h, l, c, v, e, side, entry) -> a level, set at entry; stop checked first, from the first bar at risk
    (check_from_next: one bar later); a bar that opens past a level books its open; else flat at the session's last
    close."""
    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, return_trades=False, **_ignore):
        o, h, l, c = (np.asarray(x, float) for x in (opens, highs, lows, closes))
        v = np.asarray(volumes, float) if volumes is not None else np.ones(len(c))
        did = np.asarray(day_id)
        starts = np.flatnonzero(np.r_[True, did[1:] != did[:-1]])
        ends = np.r_[starts[1:], len(c)]
        trades = []
        for a, b in zip(starts, ends):
            if a < 20 or b - a < 12:                              # room for the trailing windows; a full session
                continue
            k = a + 3
            side = 1 if c[k] >= o[a] else -1
            if fill == "open":
                e, entry, j0 = k + 1, o[k + 1], k + 1
            elif fill == "close":
                e, entry, j0 = k, c[k], k + 1
            elif fill == "limit":
                e, lvl = k + 1, (l[k] if side > 0 else h[k])
                past = (lvl > l[e] if strict else lvl >= l[e]) if side > 0 else (lvl < h[e] if strict else lvl <= h[e])
                if not ((o[e] > lvl if side > 0 else o[e] < lvl) and past):
                    continue
                entry, j0 = lvl, e
            else:
                e, lvl = k + 1, (h[k] if side > 0 else l[k])
                past = (h[e] > lvl if strict else h[e] >= lvl) if side > 0 else (l[e] < lvl if strict else l[e] <= lvl)
                if not ((o[e] < lvl if side > 0 else o[e] > lvl) and past):
                    continue
                entry, j0 = lvl, e
            st = stop(o, h, l, c, v, e, side, entry) if stop else None
            tg = target(o, h, l, c, v, e, side, entry) if target else None
            x, px = b - 1, c[b - 1]
            for j in range(j0 + int(check_from_next), b):
                if st is not None and (l[j] <= st if side > 0 else h[j] >= st):
                    x, px = j, (o[j] if (o[j] < st if side > 0 else o[j] > st) else st)
                    break
                if tg is not None and (h[j] >= tg if side > 0 else l[j] <= tg):
                    x, px = j, (o[j] if (o[j] > tg if side > 0 else o[j] < tg) else tg)
                    break
            trades.append((int(e), int(x), float(side * (px - entry)), int(side), float(entry)))
        return {"trades": trades} if trades else None
    import types
    return types.SimpleNamespace(run_backtest=run_backtest, DEFAULT_PARAMS={})


def _eb_bars(doji=False):
    A = Q._sb_synthetic(40, 30, seed=11)
    if doji:                                                  # every decision bar (bar 3) opens at its close
        did = A["day_id"]
        starts = np.flatnonzero(np.r_[True, did[1:] != did[:-1]])
        O = np.array(A["open"], float)
        O[starts + 3] = A["close"][starts + 3]
        A = dict(A, open=O)
    return A


def _eb(mod, A, k=6):
    full = Q._sb_direct(mod, A, {}, None, 300)
    amp = float(np.median(A["high"] - A["low"]))
    return Q._sb_entry_bar_inputs(mod, A, {}, None, 300, full, list(range(len(full))), amp,
                                  float(np.median(A["volume"])), k)


def _atr_before(h, l, e, n=10):
    return float(np.mean(h[e - n:e] - l[e - n:e]))


@functools.lru_cache(maxsize=None)
def _eb_amp():
    A = _eb_bars()
    return float(np.median(A["high"] - A["low"])), float(np.median(A["volume"]))


def test_entry_bar_phase_never_flips_a_legit_stop_first_exit_into_a_target():
    # the one-way re-draw: on an ADVERSE push the bar never trades above its open, so a near target known at the fill
    # (crossed by the original bar) cannot win on the 10-range push and lose to a wide stop on the 30-range one - two
    # level exits at different prices from a perfectly legit rule (stop checked first, both levels set at the fill)
    A = _eb_bars()
    amp = _eb_amp()[0]
    mod = _eb_plugin(stop=lambda o, h, l, c, v, e, s, x: x - s * 15.0 * amp,
                     target=lambda o, h, l, c, v, e, s, x: x + s * 0.3 * _atr_before(h, l, e))
    fails, n, conc = _eb(mod, A)
    assert not fails and n >= 3 and conc >= 3, fails[:1]


@pytest.mark.parametrize("label,kw,leaks", [
    ("clean stop + target from the bars before", dict(
        stop=lambda o, h, l, c, v, e, s, x: x - s * 3 * _atr_before(h, l, e),
        target=lambda o, h, l, c, v, e, s, x: x + s * 4 * _atr_before(h, l, e)), False),
    ("clean close fill: a stop from the fill bar's own range", dict(
        fill="close", stop=lambda o, h, l, c, v, e, s, x: x - s * 1.0 * (h[e] - l[e])), False),
    ("clean intrabar stop entry", dict(
        fill="intrabar", stop=lambda o, h, l, c, v, e, s, x: x - s * 3 * _atr_before(h, l, e)), False),
    # review #7 / D-close: what the old phase (high / low only) passed
    ("L1b open fill, stop anchored at the entry bar's close", dict(
        stop=lambda o, h, l, c, v, e, s, x: c[e] - s * 2 * _atr_before(h, l, e)), True),
    ("L1 open fill, close-to-close vol incl. the entry bar's close", dict(
        stop=lambda o, h, l, c, v, e, s, x: x - s * 8 * float(np.mean(np.abs(np.diff(c[e - 14:e + 1]))))), True),
    ("L3 close fill, vol reads the next bar's close", dict(
        fill="close", stop=lambda o, h, l, c, v, e, s, x: x - s * 8 * float(np.mean(np.abs(np.diff(c[e - 13:e + 2]))))),
     True),
    # review #8: an intrabar (stop-entry) fill was skipped
    ("L2 intrabar entry, ATR incl. the entry bar", dict(
        fill="intrabar", stop=lambda o, h, l, c, v, e, s, x: x - s * 3 * float(np.mean(h[e - 13:e + 1] - l[e - 13:e + 1]))),
     True),
    ("L2b intrabar entry, the same at 5x", dict(
        fill="intrabar", stop=lambda o, h, l, c, v, e, s, x: x - s * 5 * float(np.mean(h[e - 13:e + 1] - l[e - 13:e + 1]))),
     True),
    # mutation D7: only the FAVOURABLE push sees a target from the entry bar's own range (no stop)
    ("target from the entry bar's own range", dict(
        target=lambda o, h, l, c, v, e, s, x: x + s * 0.5 * (h[e] - l[e])), True),
])
def test_entry_bar_phase_in_process(label, kw, leaks):
    A = _eb_bars()
    fails, n, conc = _eb(_eb_plugin(**kw), A)
    assert n >= 3, label
    assert bool(fails) == leaks, (label, fails[:2])
    if not leaks:
        assert conc >= 1, label                                  # the clean levels WERE exercised
    else:
        kind = "(intrabar fill" if "intrabar" in label else "(close fill" if "close fill" in label else "(open fill"
        assert fails[0].startswith("ENTRY-BAR INPUT at bar") and kind in fails[0], fails[0]


def test_entry_bar_phase_reads_a_doji_entry_as_a_close_fill():
    # mutation D4: an entry price equal to bar e's open AND close is read as a CLOSE fill (lenient). Read as an open
    # fill, the phase would move bar e's close - the decision bar of this legit close-fill rule - and fail it.
    A = _eb_bars(doji=True)
    mod = _eb_plugin(fill="close", stop=lambda o, h, l, c, v, e, s, x: x - s * 1.0 * (h[e] - l[e]))
    full = Q._sb_direct(mod, A, {}, None, 300)
    kinds = {ke for _, _, ke in Q._sb_entry_bar_cands(A, full, range(len(full)))}
    assert kinds == {"close"} and all(abs(t[4] - A["open"][t[0]]) < 1e-9 for t in full)
    fails, n, conc = _eb(mod, A)
    assert not fails and n >= 3 and conc >= 1, fails[:1]


def test_entry_bar_phase_needs_the_anomaly_branch_the_later_bars_and_the_third_push():
    amp, vmed = _eb_amp()
    A = _eb_bars()
    # mutation D3: a level that reads the entry bar's VOLUME - crossed on the first push, out of reach on the deeper
    # ones: only the 'exits on bar f at 10 but not at 30' branch can see it
    mod = _eb_plugin(stop=lambda o, h, l, c, v, e, s, x: x - s * amp * (5.0 if v[e] < 0.5 * vmed else 200.0))
    fails, _, _ = _eb(mod, A)
    assert fails and "but NOT on bar" in fails[0]
    # mutation D5: a forward window (bars AFTER the first bar at risk) - only the later-bar replacement moves it
    mod = _eb_plugin(stop=lambda o, h, l, c, v, e, s, x: x - s * (2 * amp + 2 * abs(c[e + 2] - c[e + 1])))
    fails, _, _ = _eb(mod, A)
    assert fails and "both exit on bar" in fails[0]
    # mutation D8: a level out of reach of the 10-range push - only the 30 vs 90 pair settles it
    mod = _eb_plugin(stop=lambda o, h, l, c, v, e, s, x: x - s * (15 * amp + 0.3 * (h[e] - l[e])))
    fails, _, _ = _eb(mod, A)
    assert fails and "by 30 and 90 median ranges" in fails[0]


# ---- review round 4: a strict stop / limit entry keeps its fill; a level dragged past bar f's unchanged open
def test_entry_bar_push_keeps_an_intrabar_fill_crossed():
    A = _eb_bars()
    f = next(k for k in range(20, len(A["close"])) if min(A["high"][k] - A["open"][k], A["open"][k] - A["low"][k]) > 1)
    o, h, l = (float(A[k][f]) for k in ("open", "high", "low"))
    buy_stop, buy_limit = o + 0.5 * (h - o), o - 0.5 * (o - l)
    # a buy STOP crossed the high: the adverse push pulls the high in, but it stays past the fill by min(overshoot, pen)
    B, _ = Q._sb_push(A, f, 1, "adverse", 7.0, keep=buy_stop, pen=0.1)
    assert B["high"][f] == buy_stop + 0.1 and B["low"][f] == l - 7.0
    B, _ = Q._sb_push(A, f, 1, "adverse", 7.0, keep=buy_stop, pen=100.0)
    assert B["high"][f] == h                                                         # never past its own extreme
    assert Q._sb_push(A, f, 1, "adverse", 7.0, keep=buy_stop)[0]["high"][f] == buy_stop   # pen 0: exactly the fill
    # a buy LIMIT crossed the low: the favourable push pulls the low in, past the fill; the adverse one keeps the open
    B, _ = Q._sb_push(A, f, 1, "favourable", 7.0, keep=buy_limit, pen=0.1)
    assert B["low"][f] == buy_limit - 0.1 and B["high"][f] == h + 7.0
    assert Q._sb_push(A, f, 1, "adverse", 7.0, keep=buy_limit, pen=0.1)[0]["high"][f] == o
    # a SELL stop (below the open) mirrored
    B, _ = Q._sb_push(A, f, -1, "adverse", 7.0, keep=buy_limit, pen=0.1)
    assert B["low"][f] == buy_limit - 0.1 and B["high"][f] == h + 7.0


@pytest.mark.parametrize("fill", ["intrabar", "limit"])
def test_entry_bar_phase_keeps_a_strict_stop_or_limit_entry_filled(fill):
    # the one-way re-draw used to pull the crossed extreme in to EXACTLY the fill level, so a legit stop / limit entry
    # written with a strict test ('high > level') lost its fill on every push: 'the ENTRY itself changed' - a false
    # look-ahead that failed a clean rule at write_plugin
    A = _eb_bars()
    clean = lambda o, h, l, c, v, e, s, x: x - s * 3 * _atr_before(h, l, e)
    leak = lambda o, h, l, c, v, e, s, x: x - s * 3 * float(np.mean(h[e - 9:e + 1] - l[e - 9:e + 1]))
    for strict in (False, True):
        fails, n, conc = _eb(_eb_plugin(fill=fill, strict=strict, stop=clean), A)
        assert not fails and n >= 3 and conc >= 3, (fill, strict, fails[:1])
        fails, n, conc = _eb(_eb_plugin(fill=fill, strict=strict, stop=leak), A)
        assert fails and "both exit on bar" in fails[0] and "(intrabar fill" in fails[0], (fill, strict, fails[:1])


def test_entry_bar_phase_sees_a_level_dragged_past_the_open():
    # leaks.py L4: a stop hung off the entry bar's FAVOURABLE extreme (a chandelier from the session high INCLUDING the
    # entry bar). The favourable push drags it past bar f's unchanged open, so every push books that open - the same
    # P&L each time, invisible to the level comparison. A level known at the fill that is past that open books it on
    # the real bars too; this one never does.
    A = _eb_bars()
    amp = _eb_amp()[0]
    hi = (lambda n: lambda o, h, l, c, v, e, s, x:
          (float(np.max(h[e - 5:e + n])) if s > 0 else float(np.min(l[e - 5:e + n]))) - s * 2 * amp)
    for fill, n in (("open", 1), ("close", 2)):                    # the entry bar / the bar after a close fill
        fails, _, _ = _eb(_eb_plugin(fill=fill, stop=hi(n)), A)
        assert fails and "OPEN" in fails[0] and "but not on the real bars" in fails[0], (fill, fails[:1])
        assert fails[0].startswith("ENTRY-BAR INPUT at bar") and "(%s fill" % fill in fails[0]
    for fill, n in (("open", 0), ("close", 1)):                    # the same chandelier from what existed at the fill
        fails, _, conc = _eb(_eb_plugin(fill=fill, stop=hi(n)), A)
        assert not fails and conc >= 3, (fill, fails[:1])
    # a level known at the fill that is already past the open books that open on the real bars too - not a leak
    fails, _, conc = _eb(_eb_plugin(stop=lambda o, h, l, c, v, e, s, x: x + s * 0.5 * amp), A)
    assert not fails and conc >= 3, fails[:1]


def _chandelier_plugin(update_first):
    """QL_MOMDRIVE's exit (the lab's real 10-15 plugin, both runs 'not promoted'): fill at bar 4's open, a chandelier
    stop = best close since entry -/+ 2 x the ATR of the bars before the fill; update_first raises `best` with bar j's
    CLOSE before checking bar j's low (as QL_MOMDRIVE did), else after the check."""
    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, return_trades=False, **_ignore):
        o, h, l, c = (np.asarray(x, float) for x in (opens, highs, lows, closes))
        did = np.asarray(day_id)
        starts = np.flatnonzero(np.r_[True, did[1:] != did[:-1]])
        trades = []
        for a, b in zip(starts, np.r_[starts[1:], len(c)]):
            if a < 20 or b - a < 12:
                continue
            side = 1 if c[a + 3] >= o[a] else -1
            e = a + 4
            entry, atr, best = o[e], _atr_before(h, l, e), o[e]
            x, px = b - 1, c[b - 1]
            for j in range(e, b):
                if update_first:
                    best = max(best, c[j]) if side > 0 else min(best, c[j])
                st = best - side * 2 * atr
                if l[j] <= st if side > 0 else h[j] >= st:
                    x, px = j, (o[j] if (o[j] < st if side > 0 else o[j] > st) else st)
                    break
                if not update_first:
                    best = max(best, c[j]) if side > 0 else min(best, c[j])
            trades.append((int(e), int(x), float(side * (px - entry)), int(side), float(entry)))
        return {"trades": trades} if trades else None
    import types
    return types.SimpleNamespace(run_backtest=run_backtest, DEFAULT_PARAMS={})


def test_entry_bar_phase_catches_a_chandelier_raised_with_the_bars_own_close():
    # review round 4, on COPIES of the lab's gated plugins on real pre-WF bars (scratchpad r4_real_la.py): the new
    # open check fails QL_MOMDRIVE - its chandelier takes bar j's close BEFORE bar j's low is checked, so on the entry
    # bar a strong close drags the stop past the open (a look-ahead the round-3 phases passed); with the update after
    # the check it passes
    A = _eb_bars()
    fails, _, _ = _eb(_chandelier_plugin(update_first=True), A)
    assert fails and "OPEN" in fails[0] and "but not on the real bars" in fails[0], fails[:1]
    fails, n, conc = _eb(_chandelier_plugin(update_first=False), A)
    assert not fails and n >= 3, fails[:1]


def test_a_stop_scaled_1x_or_more_by_the_entry_bars_range_is_realisable_at_that_scale():
    # review #12 (d_scale_probe.py): stop = entry - 1.5 x the entry bar's own range can NEVER be crossed on the entry bar
    # (it sits below that bar's low), so its trades equal those of a rule that sets the same level at the entry bar's
    # CLOSE and checks it from the next bar - realisable, nothing to flag at that scale. The phase reports it as
    # inconclusive, and the same shape at 0.5x is caught.
    A = _eb_bars()
    lvl = (lambda m: lambda o, h, l, c, v, e, s, x: x - s * m * (h[e] - l[e]))
    leaky = Q._sb_direct(_eb_plugin(stop=lvl(1.5)), A, {}, None, 300)
    realisable = Q._sb_direct(_eb_plugin(stop=lvl(1.5), check_from_next=True), A, {}, None, 300)
    assert leaky == realisable and len(leaky) >= 30
    fails, n, conc = _eb(_eb_plugin(stop=lvl(1.5)), A)
    assert not fails and n >= 3 and conc == 0
    assert _eb(_eb_plugin(stop=lvl(0.5)), A)[0]
    assert Q._sb_direct(_eb_plugin(stop=lvl(0.5)), A, {}, None, 300) != Q._sb_direct(
        _eb_plugin(stop=lvl(0.5), check_from_next=True), A, {}, None, 300)       # at 0.5x it IS a different rule


# the template's stop as a knob-scaled multiple of the ENTRY bar's own range: 1.5x at the default stop_frac 1.0
# (realisable, see above), 0.375x at the searched min 0.25 (a leak the validate would search)
_RANGE_SCALED = ("            stop = entry - side * float(stop_frac) * rng",
                 "            stop = entry - side * float(stop_frac) * 1.5 * (h[e] - l[e])")


@needs_shared
def test_lookahead_audit_checks_the_entry_bar_at_the_knob_corners(tmp_path):
    code = Q.TEMPLATE_PLUGIN.replace(*_RANGE_SCALED)
    assert code != Q.TEMPLATE_PLUGIN and Q.safety_gate(code)[0]
    r = _sb(tmp_path, "lookahead", code, synthetic_days=80, la_k=10, instrument="NQ", eb_corner_knobs=0)
    assert r["ok"], r                                         # at the defaults: inconclusive, a warning, no failure
    assert r["entry_bar_conclusive"] == 0 and any("were not exercised" in w for w in r["warnings"])
    r = _sb(tmp_path, "lookahead", code, synthetic_days=80, la_k=10, instrument="NQ")
    assert not r["ok"]
    p = next(p for p in r["problems"] if p.startswith("LOOK-AHEAD (entry-bar inputs, TTM #145)"))
    assert "at stop_frac=0.25: ENTRY-BAR INPUT" in p
    rows = {(c["knob"], c["value"]): c for c in r["entry_bar_corners"]}
    assert rows[("stop_frac", 0.25)]["conclusive"] >= 1 and rows[("stop_frac", 2.0)]["conclusive"] == 0
