"""plugin_gate.py - gate LLM-written strategy code BEFORE the engine imports or runs it.

WHY THIS EXISTS (MANAGER, 2026-10-17, owner task "Gate LLM-written strategy code before it runs").
The Qwen Lab (tools/qwen_lab.py) has a local model write strategy plugins; those files land in
augur_strategies/qwen_lab/<QL_NAME>.py and, once a Claude lane reviews one onto main, the runner
can be handed it like any other strategy (an Auto-Validate job carries the absolute path). The
engine's loader - load_strategy(), used by the runner, the book, the forward tools, cloud_signal -
imported ANY file under augur_strategies/ with no check at all: importing a Python file executes
its module body, so a machine-written file that reads or writes disk, opens a socket or reaches
into the interpreter would have run with the runner's rights the moment a job named it. The lab's
own sandbox (restricted builtins, a child process, a static whitelist) protects the lab's runs
only; nothing protected the engine. The house rule "no Qwen-written plugin runs a real
Auto-Validate before a Claude review onto main" was a convention the engine could not see.

WHAT IT DOES. gate_plugin(path) runs before every import of a strategy file the engine does not
already hold in its cache, and before the runner's own pin check:

  1. PROVENANCE. A file counts as LLM-written when ANY of these holds: it sits in a directory
     named in LLM_DIRS (augur_strategies/qwen_lab/), its name starts with an LLM_NAME_PREFIXES
     prefix (QL_), or its source carries a `# AUGUR-SOURCE: <who>` marker whose value is not one
     of HUMAN_SOURCES (hand, human, claude, claude-review). Unknown marker values fail closed:
     they count as machine-written. A hand-written strategy (the 220+ files in augur_strategies/)
     has none of these and is NOT touched: the gate returns at once and nothing changes for it.
  2. REVIEW LEDGER. An LLM-written file must be listed in augur_strategies/qwen_lab/REVIEWED.json
     with the LF sha256 of its bytes (CRLF folded to LF, the lab's lf_sha256). The reviewing
     Claude lane writes that entry in the same ship that lands the plugin:
         python -m augur_engine.plugin_gate --lint <file.py> [...]     look-ahead hits only, any file, exit 1 on a hit
    python -m augur_engine.plugin_gate --stamp <LANE> augur_strategies/qwen_lab/QL_X.py
     No entry, or an entry whose sha differs from the file on disk, = refused before import.
  4. LOOK-AHEAD (board C7, 10-30). lookahead_check() flags code that reads future bars: .shift(-n),
     .diff(-n), .pct_change(-n), x.iloc[i + 1] / x.iat[i + 1] / x.values[i + 1], .rolling(center=True).
     Any hit refuses an LLM file like a safety reason. `--lint <file>` runs it on ANY file (hand-written
     too) and prints the hits without gating.
  3. SAFETY. The source must pass safety_check(): a static whitelist (nothing is imported or
     executed to decide). Imports: numpy, pandas, math, and by name `from augur_engine.rolls
     import seam_days` / `from augur_engine.session_calendar import <helper>`. No os / sys /
     subprocess / socket / open / exec / eval / getattr / ... (FORBIDDEN_NAMES), no file, network
     or interpreter attributes (FORBIDDEN_ATTRS: .load .save .to_csv .read_* .system .environ
     ...), no dunder names or attributes, no class definitions, async, global / nonlocal, no
     bytes literals, no '__' inside strings, only imports / assignments / function definitions /
     docstrings at module level, size caps. This is the lab's own whitelist (tools/qwen_lab.py
     safety_gate, GATES_VERSION 4) with its lab-contract checks left out; the lab keeps its copy
     for the model's feedback loop and can import this one instead.

A refusal raises PluginGateError (a RuntimeError) naming the file, the provenance, the sha and
every reason; the module body never runs. There is NO environment override: a lane that needs
to run an unreviewed plugin by hand loads it in the lab's sandbox or hands the engine a module
object it built itself, as the lab does. The runner is never asked to trust a file on anyone's
word.

CLI:
    python -m augur_engine.plugin_gate <file.py> [...]            PASS / NOT GATED / REFUSED per file, exit 1 on a refusal
    python -m augur_engine.plugin_gate --lint <file.py> [...]     look-ahead hits only, any file, exit 1 on a hit
    python -m augur_engine.plugin_gate --stamp <LANE> <file.py>   safety-check, then write / replace its ledger entry
"""
import ast
import datetime as _dt
import hashlib
import json
import os
import re
import sys

LLM_DIRS = {"qwen_lab"}
LLM_NAME_PREFIXES = ("QL_",)
MARKER_RX = re.compile(r"(?mi)^#\s*AUGUR-SOURCE:\s*([a-z0-9][a-z0-9._\-]*)")
HUMAN_SOURCES = {"hand", "human", "claude", "claude-review"}
LEDGER_NAME = "REVIEWED.json"
CODE_MAX_CHARS = 80000
CODE_MAX_LINES = 1500
CODE_MAX_NODES = 30000

# ------------------------------------------------------------------------------------------- the static whitelist
# Kept identical to tools/qwen_lab.py (the lab's safety_gate) so the model is refused the same things in both places.
ALLOWED_IMPORTS = {"numpy", "pandas", "math"}
# None = any non-forbidden name
ALLOWED_FROM = {"augur_engine.rolls": {"seam_days"}, "math": None, "numpy": None,
                "augur_engine.session_calendar": {"session_calendar", "session_dates", "session_index_in_month",
                                                  "days_to_month_end", "is_last_n_sessions_of_month",
                                                  "is_first_n_sessions_of_month", "week_of_month",
                                                  "exchange_sessions", "is_exchange_session"}}
FORBIDDEN_NAMES = {
    "open", "exec", "eval", "compile", "__import__", "globals", "locals", "vars", "dir", "getattr", "setattr",
    "delattr", "hasattr", "input", "breakpoint", "help", "exit", "quit", "print", "memoryview", "type", "super",
    "object", "classmethod", "staticmethod", "property", "__builtins__", "os", "sys", "subprocess", "socket",
    "shutil", "pathlib", "requests", "urllib", "http", "ctypes", "importlib", "pickle", "threading",
    "multiprocessing", "io", "builtins", "inspect", "gc", "marshal", "signal", "asyncio", "tempfile", "glob", "json",
    "codecs", "runpy", "types", "zipimport", "winreg", "msvcrt", "mmap", "sqlite3", "shelve", "dbm", "webbrowser",
    "ftplib", "smtplib", "telnetlib", "ssl", "select", "selectors", "concurrent", "_thread", "platform", "resource"}
FORBIDDEN_ATTRS = {
    "load", "loads", "save", "savez", "savez_compressed", "savetxt", "loadtxt", "genfromtxt", "fromfile", "tofile",
    "memmap", "fromregex", "dump", "dumps", "open", "system", "popen", "eval", "query", "ctypeslib", "ctypes", "lib",
    "f2py", "distutils", "testing", "os", "sys", "ma", "rec", "DataSource", "HDFStore", "ExcelWriter", "ExcelFile",
    "io", "api", "options", "set_option", "get_option", "reset_option", "describe_option", "option_context",
    "show_versions", "plotting", "style", "core", "compat", "util", "mro", "gi_frame", "gi_code", "gi_yieldfrom",
    "cr_frame", "cr_code", "ag_frame", "ag_code", "f_globals", "f_locals", "f_builtins", "f_back", "f_code",
    "tb_frame", "tb_next", "co_code", "co_consts", "func_globals", "exec", "compile", "import_module", "spawn",
    "Popen", "environ", "getenv", "putenv", "unlink", "rmdir", "makedirs", "mkdir", "chdir", "listdir", "scandir",
    "write", "writelines", "urlopen", "request", "connect", "socket", "plot", "figure", "savefig", "clipboard",
    "seterrcall", "setbufsize", "set_printoptions", "open_memmap", "fromstring_file"}
TO_OK = {"to_numpy", "to_list", "to_dict", "to_frame", "to_period", "to_timestamp", "to_pydatetime", "to_datetime",
         "to_numeric", "to_timedelta", "to_series", "to_datetime64", "to_flat_index", "to_offset", "to_string"}
_BAD_ATTR_PREFIX = ("_", "read_", "save", "load", "dump")
_MODULE_STMTS = (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.FunctionDef)
_BANNED_NODES = {ast.ClassDef: "class definitions", ast.Global: "global statements", ast.Nonlocal: "nonlocal",
                 ast.AsyncFunctionDef: "async functions", ast.Await: "await", ast.AsyncFor: "async for",
                 ast.AsyncWith: "async with"}
if hasattr(ast, "TypeAlias"):
    _BANNED_NODES[ast.TypeAlias] = "type aliases"


class PluginGateError(RuntimeError):
    """An LLM-written strategy file was refused before import. .report holds the gate's findings."""

    def __init__(self, report):
        self.report = report
        why = "; ".join(report.get("reasons") or ["refused"])
        super().__init__("PLUGIN GATE refused %s (%s; LF sha256 %s): %s"
                         % (report.get("path"), report.get("llm"), (report.get("sha") or "?")[:16], why))


# ------------------------------------------------------------------------------------------- hashing
def lf_bytes(b):
    return b.replace(b"\r\n", b"\n")


def lf_sha256_bytes(b):
    """sha256 of the bytes with CRLF folded to LF - the lab's hash, so a Windows checkout and the lab agree."""
    return hashlib.sha256(lf_bytes(b)).hexdigest()


def lf_sha256_file(path):
    with open(path, "rb") as f:
        return lf_sha256_bytes(f.read())


# ------------------------------------------------------------------------------------------- provenance
def provenance(path, src=None):
    """Why `path` counts as LLM-written: 'dir qwen_lab/', 'name QL_', 'marker <who>' - or None for a hand-written
    file. Unknown `# AUGUR-SOURCE:` values count as machine-written (fail closed)."""
    path = os.path.abspath(path)
    base = os.path.basename(path)
    parent = os.path.basename(os.path.dirname(path))
    if parent in LLM_DIRS:
        return "dir %s/" % parent
    for p in LLM_NAME_PREFIXES:
        if base.startswith(p):
            return "name %s" % p
    if src is None:
        try:
            with open(path, "rb") as f:
                src = lf_bytes(f.read()).decode("utf-8", "replace")
        except OSError:
            return None
    m = MARKER_RX.search(src)
    if m and m.group(1).lower() not in HUMAN_SOURCES:
        return "marker %s" % m.group(1)
    return None


def ledger_path(path):
    """augur_strategies/qwen_lab/REVIEWED.json - next to the file when it lives in an LLM dir, else under the
    strategies directory's qwen_lab/ (an LLM file placed in the root dir still needs the one ledger)."""
    d = os.path.dirname(os.path.abspath(path))
    if os.path.basename(d) in LLM_DIRS:
        return os.path.join(d, LEDGER_NAME)
    return os.path.join(d, sorted(LLM_DIRS)[0], LEDGER_NAME)


def read_ledger(lp):
    """{basename: {sha256_lf, reviewed_by, date, note}}; {} when the ledger is missing. A ledger that cannot be
    parsed is an error: a broken ledger must refuse every LLM file, never let one through."""
    if not os.path.exists(lp):
        return {}
    with open(lp, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("%s: the ledger must be a JSON object" % lp)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def reviewed_entry(path, ledger=None):
    """The ledger entry for `path`, or None."""
    if ledger is None:
        ledger = read_ledger(ledger_path(path))
    e = ledger.get(os.path.basename(path))
    return e if isinstance(e, dict) else None


# ------------------------------------------------------------------------------------------- the safety check
def _attr_problem(attr):
    if attr.startswith("__") or attr.endswith("__"):
        return "dunder attribute .%s" % attr
    if attr in FORBIDDEN_ATTRS:
        return "forbidden attribute .%s (file / network / interpreter access)" % attr
    if attr.startswith("to_") and attr not in TO_OK:
        return "forbidden attribute .%s (pandas / numpy writers are I/O)" % attr
    for p in _BAD_ATTR_PREFIX:
        if attr.startswith(p):
            return "forbidden attribute .%s (private, or a reader / writer)" % attr
    return None


def safety_check(code):
    """Reasons the source is refused ([] = passes). Static: nothing is imported or executed here."""
    reasons = []
    if not isinstance(code, str) or not code.strip():
        return ["no code"]
    if len(code) > CODE_MAX_CHARS:
        return ["code is %d chars (cap %d)" % (len(code), CODE_MAX_CHARS)]
    if code.count("\n") > CODE_MAX_LINES:
        return ["more than %d lines" % CODE_MAX_LINES]
    try:
        tree = ast.parse(code, filename="<llm_plugin>")
    except SyntaxError as e:
        return ["syntax error line %s: %s" % (e.lineno, e.msg)]
    nodes = list(ast.walk(tree))
    if len(nodes) > CODE_MAX_NODES:
        return ["more than %d syntax nodes" % CODE_MAX_NODES]

    def bad(node, msg):
        reasons.append("line %s: %s" % (getattr(node, "lineno", "?"), msg))

    for st in tree.body:
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant) and isinstance(st.value.value, str):
            continue                                             # a docstring / comment string
        if not isinstance(st, _MODULE_STMTS):
            bad(st, "only imports, assignments, function definitions and docstrings are allowed at module level "
                    "(found %s)" % type(st).__name__)
    for node in nodes:
        for cls, what in _BANNED_NODES.items():
            if isinstance(node, cls):
                bad(node, "%s are not allowed" % what)
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name not in ALLOWED_IMPORTS:
                    bad(node, "import %s is not allowed (numpy, pandas, math only)" % a.name)
                if a.asname and (a.asname.startswith("__") or a.asname in FORBIDDEN_NAMES):
                    bad(node, "import alias %s is not allowed" % a.asname)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level:
                bad(node, "relative imports are not allowed")
            elif mod not in ALLOWED_FROM:
                bad(node, "from %s import ... is not allowed (only `from augur_engine.rolls import seam_days`, "
                          "`from augur_engine.session_calendar import <helper>`, math, numpy)" % mod)
            else:
                allow = ALLOWED_FROM[mod]
                for a in node.names:
                    if a.name == "*":
                        bad(node, "star imports are not allowed")
                    elif allow is not None and a.name not in allow:
                        bad(node, "from %s import %s is not allowed" % (mod, a.name))
                    elif _attr_problem(a.name) or a.name in FORBIDDEN_NAMES:
                        bad(node, "importing %s is not allowed" % a.name)
                    if a.asname and (a.asname.startswith("__") or a.asname in FORBIDDEN_NAMES):
                        bad(node, "import alias %s is not allowed" % a.asname)
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES:
                bad(node, "name %s is not allowed" % node.id)
            elif node.id.startswith("__"):
                bad(node, "dunder name %s is not allowed" % node.id)
        elif isinstance(node, ast.Attribute):
            p = _attr_problem(node.attr)
            if p:
                bad(node, p)
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                bad(node, "assigning or deleting an attribute (.%s) is not allowed" % node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.Lambda)):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("__"):
                bad(node, "dunder function name %s" % node.name)
            args = node.args
            for a in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs) + \
                    [x for x in (args.vararg, args.kwarg) if x is not None]:
                if a.arg.startswith("__") or a.arg in FORBIDDEN_NAMES:
                    bad(node, "argument name %s is not allowed" % a.arg)
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, str) and "__" in node.value:
                bad(node, "strings may not contain '__'")
            elif isinstance(node.value, bytes):
                bad(node, "bytes literals are not allowed")
        elif isinstance(node, ast.ExceptHandler):
            if node.name and (node.name.startswith("__") or node.name in FORBIDDEN_NAMES):
                bad(node, "exception name %s is not allowed" % node.name)
    seen, out = set(), []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out[:25]


# ------------------------------------------------------------------------------------------- the look-ahead linter
_POS_INDEX_ATTRS = {"iloc", "iat", "values"}


def _const_int(node):
    """The int value of a literal (also -n written as a unary minus), else None."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        v = _const_int(node.operand)
        return -v if v is not None else None
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return node.value
    return None


def _terms(node, sign=1):
    """Flatten + / - chains into [(sign, leaf)]."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
        return _terms(node.left, sign) + _terms(node.right, sign if isinstance(node.op, ast.Add) else -sign)
    return [(sign, node)]


def _forward_offset(node):
    """True when an index is <variable> plus a positive constant net (i + 1, 1 + i, i + 2 - 1), with nothing
    subtracted that could pull it back (d + 1 - L is a trailing window start, not a later bar)."""
    const, has_var = 0, False
    for sg, leaf in _terms(node):
        v = _const_int(leaf)
        if v is not None:
            const += sg * v
        elif sg < 0:
            return False
        else:
            has_var = True
    return has_var and const > 0


def lookahead_check(code):
    """Reasons the source reads FUTURE bars (board C7; [] = none found). Static, like safety_check. Flags:
    .shift(-n) / .shift(periods=-n) / .diff(-n) / .pct_change(-n), a positional index forward of a variable
    (x.iloc[i + 1], x.iat[i + 1], x.values[i + 1]), and .rolling(..., center=True). A
    linter, not a proof: a next-bar FILL written as .iloc[i + 1] is flagged too - review it by hand."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []                                                # safety_check reports the syntax error
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            name = node.func.attr
            if name in ("shift", "diff", "pct_change"):
                arg = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "periods"), None)
                v = _const_int(arg) if arg is not None else None
                if v is not None and v < 0:
                    out.append("line %s: .%s(%d) reads %d bar(s) ahead" % (node.lineno, name, v, -v))
            if name == "rolling":
                for k in node.keywords:
                    if k.arg == "center" and isinstance(k.value, ast.Constant) and k.value.value is True:
                        out.append("line %s: .rolling(center=True) averages future bars into today" % node.lineno)
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
            idx = node.slice
            if isinstance(idx, ast.Tuple) and idx.elts:
                idx = idx.elts[0]
            if isinstance(idx, ast.Slice):
                continue                                         # x[i:i + 2] windows are read elsewhere; keep it simple
            tgt = node.value
            if isinstance(tgt, ast.Attribute) and tgt.attr in _POS_INDEX_ATTRS:
                if _forward_offset(idx):
                    out.append("line %s: index %s reads a later bar" % (node.lineno, ast.unparse(idx)))
    return sorted(set(out), key=lambda r: int(r.split()[1].rstrip(":")))[:25]


# ------------------------------------------------------------------------------------------- the gate
def inspect_plugin(path, src=None):
    """The gate's findings for `path` without raising: {path, llm, sha, reviewed, reviewed_by, reasons, ok}.
    A hand-written file gets llm=None, ok=True and no further checks."""
    path = os.path.abspath(path)
    rep = {"path": path, "llm": None, "sha": None, "reviewed": None, "reviewed_by": None, "reasons": [], "ok": True}
    raw = None
    if src is None:
        with open(path, "rb") as f:
            raw = f.read()
        src = lf_bytes(raw).decode("utf-8", "replace")
    rep["llm"] = provenance(path, src)
    if rep["llm"] is None:
        return rep
    rep["sha"] = lf_sha256_bytes(raw) if raw is not None else lf_sha256_bytes(src.encode("utf-8"))
    try:
        entry = reviewed_entry(path)
    except (ValueError, OSError) as e:
        entry = None
        rep["reasons"].append("review ledger unreadable: %s" % e)
    lp = ledger_path(path)
    if entry is None:
        if not rep["reasons"]:
            rep["reasons"].append("not reviewed: no entry for %s in %s (a Claude lane reviews the file onto main and "
                                  "stamps it: python -m augur_engine.plugin_gate --stamp <LANE> <file>)"
                                  % (os.path.basename(path), lp))
    else:
        rep["reviewed_by"] = entry.get("reviewed_by")
        want = str(entry.get("sha256_lf") or "")
        if want == rep["sha"]:
            rep["reviewed"] = want
        else:
            rep["reasons"].append("reviewed sha %s does not match the file on disk %s - the file changed after its "
                                  "review (re-review and re-stamp it)" % (want[:16] or "?", rep["sha"][:16]))
    rep["reasons"].extend("safety: " + r for r in safety_check(src))
    rep["reasons"].extend("look-ahead: " + r for r in lookahead_check(src))
    rep["ok"] = not rep["reasons"]
    return rep


def gate_plugin(path, src=None):
    """Raise PluginGateError when `path` is LLM-written and unreviewed, changed since review, or unsafe. Returns the
    report otherwise. Call it BEFORE importing a strategy file; a hand-written file passes straight through."""
    rep = inspect_plugin(path, src)
    if not rep["ok"]:
        raise PluginGateError(rep)
    return rep


def stamp_reviewed(path, by, note=""):
    """Write / replace the ledger entry for `path` after a passing safety check. Returns the entry. Refuses a file
    that is not LLM-written (a hand file needs no stamp) and an unsafe one (review is not a waiver)."""
    path = os.path.abspath(path)
    with open(path, "rb") as f:
        raw = f.read()
    src = lf_bytes(raw).decode("utf-8", "replace")
    who = provenance(path, src)
    if who is None:
        raise ValueError("%s is not LLM-written (no qwen_lab/ dir, QL_ name or AUGUR-SOURCE marker) - no stamp needed"
                         % path)
    bad = ["safety: " + r for r in safety_check(src)] + ["look-ahead: " + r for r in lookahead_check(src)]
    if bad:
        raise PluginGateError({"path": path, "llm": who, "sha": lf_sha256_bytes(raw), "reasons": bad})
    if not str(by or "").strip():
        raise ValueError("--stamp needs the reviewing lane's name")
    lp = ledger_path(path)
    ledger = {}
    if os.path.exists(lp):
        with open(lp, encoding="utf-8") as f:
            ledger = json.load(f)
        if not isinstance(ledger, dict):
            raise ValueError("%s: the ledger must be a JSON object" % lp)
    entry = {"sha256_lf": lf_sha256_bytes(raw), "reviewed_by": str(by).strip(),
             "date": _dt.date.today().isoformat(), "note": str(note or "")}
    ledger.setdefault("_doc", "LLM-written strategy files a Claude lane reviewed onto main, by LF sha256. Written by "
                              "`python -m augur_engine.plugin_gate --stamp <LANE> <file>`; read by the engine's "
                              "plugin gate before any import. An entry whose sha no longer matches the file refuses it.")
    ledger[os.path.basename(path)] = entry
    os.makedirs(os.path.dirname(lp), exist_ok=True)
    body = json.dumps(ledger, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with open(lp, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)
    return entry


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.split("CLI:", 1)[-1].strip())
        return 0
    if argv[0] == "--lint":
        rc = 0
        for p in argv[1:]:
            with open(p, "rb") as f:
                hits = lookahead_check(lf_bytes(f.read()).decode("utf-8", "replace"))
            print("%s %s" % ("LOOKAHEAD" if hits else "CLEAN    ", p))
            for h in hits:
                print("    - " + h)
            rc = rc or (1 if hits else 0)
        return rc
    if argv[0] == "--stamp":
        if len(argv) < 3:
            print("usage: python -m augur_engine.plugin_gate --stamp <LANE> <file.py> [note...]")
            return 2
        lane, path, note = argv[1], argv[2], " ".join(argv[3:])
        try:
            e = stamp_reviewed(path, lane, note)
        except (PluginGateError, ValueError) as ex:
            print("REFUSED %s" % ex)
            return 1
        print("STAMPED %s sha %s by %s -> %s" % (os.path.basename(path), e["sha256_lf"][:16], e["reviewed_by"],
                                                ledger_path(path)))
        return 0
    rc = 0
    for p in argv:
        try:
            rep = inspect_plugin(p)
        except OSError as ex:
            print("ERROR   %s: %s" % (p, ex))
            rc = 1
            continue
        if rep["llm"] is None:
            print("NOT GATED %s (hand-written: no qwen_lab/ dir, QL_ name or AUGUR-SOURCE marker)" % p)
        elif rep["ok"]:
            print("PASS    %s (%s; reviewed by %s; sha %s)" % (p, rep["llm"], rep["reviewed_by"], rep["sha"][:16]))
        else:
            rc = 1
            print("REFUSED %s (%s; sha %s)" % (p, rep["llm"], (rep["sha"] or "?")[:16]))
            for r in rep["reasons"]:
                print("    - " + r)
    return rc


if __name__ == "__main__":
    sys.exit(main())
