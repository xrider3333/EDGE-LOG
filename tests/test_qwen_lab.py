"""tools/qwen_lab.py - the QWEN LAB harness (owner 2026-10-15: the local Qwen as a strategy TESTER).

Offline: no test talks to Ollama (a scripted chat stands in), no test posts to MANAGER (a recording poster), no test
reads or writes Firestore (stub live-job lists), and every lab file goes to tmp_path. The SANDBOX tests spawn the real
sandbox subprocess on SYNTHETIC bars; they need the shared checkout's engine and skip without it.

Covers: the safety gate (malicious samples), the sandbox's second and third layers (guarded import, no open, the audit
hook, hash re-check, timeout), the perturbation look-ahead audit (it catches four leak shapes the static gate cannot see),
path confinement, dead-list refusal, prereg-before-run ordering, the hash re-check, the one-validate limit, the lockbox
assertion, that every reported number comes from Python, the closed shelf + shelf-open, GAMMA closed, the broken-plugin
sanity loop, net per trade in points, and the push-lock load courtesy (read-only).
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

import augur_engine  # noqa: F401  - import the repo's engine first so the harness never touches sys.path in tests

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
sys.path.insert(0, TOOLS)
import qwen_lab as Q  # noqa: E402

HAVE_SHARED = os.path.isdir(os.path.join(Q.SHARED, "augur_engine"))
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
                    "Long NQ from 01:30 to 04:00 ET after a down day session (dealer-inventory drift).", 0.5, 120, "NQ")
    assert r["accepted"] is False and r["gate"] == "dead list" and not s.closed
    with pytest.raises(Q.ToolRefused):
        s.t_write_plugin("QL_OVERNIGHT_DOWN", Q.TEMPLATE_PLUGIN)
    r = s.t_propose("QL_NEW_THING", "A different idea about intraday reversals after gaps open.",
                    "Fade the first 15 minutes after a gap larger than its trailing median; exit at noon.", 0.4,
                    150, "NQ")
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
            return {"ok": True, "warnings": [], "smoke": {"trades": 223, "years": 1.49, "trades_per_year": 149.7},
                    "corners": []}
        if mode == "lookahead":
            return {"ok": True, "warnings": [], "la_window": {"trades": 9}, "perturbed_trades": 8, "fills_checked": 18}
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
                    0.6, 150, "NQ", "5m")
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
                0.3, 40, "NQ", "5m")
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
                     "prior_sharpe_yearly": 0.6, "trades_per_year": 150, "instrument": "NQ", "timeframe": "5m"}),
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
                0.5, 150, "NQ", "5m")
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
                0.6, 150, "NQ", "5m")
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
                    0.4, 120, "NQ", "5m")
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
