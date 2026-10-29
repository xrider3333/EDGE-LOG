r"""REPO MAP (Open Board B13, owner 10-29 via MANAGER #137) - every tracked file, a one-line purpose, its key functions.

Writes C:\EdgeLog\manager\repo_map.md (override with --out). Read-only on the repo: it lists `git ls-files` and parses each
file; nothing is imported or executed. Purpose lines come from what the file already says about itself:
    .py          the module docstring's first sentence; key functions = top-level def / class names (ast, no import)
    .md          the first heading (or first non-empty line)
    .html / .js  <title> or the first comment line
    anything else  its type and size
A file that cannot be parsed says so on its own line instead of stopping the map.

When the map is written it sends one phone push through api/ntfy_push (no push without NTFY_TOPIC; --no-ping to skip).

    pythonw tools/repo_map.py            (the nightly task - windowless)
    python  tools/repo_map.py --no-ping --out some.md
"""
import argparse
import ast
import datetime
import os
import re
import subprocess
import sys
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = r"C:\EdgeLog\manager\repo_map.md"
MAX_FUNCS = 12
MAX_PURPOSE = 160


def tracked_files(root=ROOT):
    out = subprocess.run(["git", "-C", root, "ls-files"], capture_output=True, text=True, check=True).stdout
    return sorted(p for p in out.splitlines() if p.strip())


def _clip(s, n=MAX_PURPOSE):
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n - 3].rstrip() + "..."


def _first_sentence(doc):
    doc = doc.strip()
    if not doc:
        return ""
    para = doc.split("\n\n")[0]
    m = re.match(r"(.+?[.!?])(\s|$)", " ".join(para.split()))
    return m.group(1) if m else para


def describe_py(text):
    """(purpose, [key function / class names]) from source text, without importing it."""
    with warnings.catch_warnings():               # other files' bad escapes are not this tool's to report
        warnings.simplefilter("ignore")
        tree = ast.parse(text)
    purpose = _first_sentence(ast.get_docstring(tree) or "")
    names = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
             and not n.name.startswith("_")]
    if not purpose:
        for line in text.splitlines():
            if line.startswith("#") and len(line.strip("# ").strip()) > 3 and not line.startswith("#!") and "coding" not in line:
                purpose = line.strip("# ").strip()
                break
    return purpose, names


def describe_md(text):
    for line in text.splitlines():
        s = line.strip()
        if s:
            return s.lstrip("#").strip(), []
    return "", []


def describe_web(text):
    m = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
    if m:
        return m.group(1).strip(), []
    m = re.search(r"(?://|<!--|/\*)\s*(.+)", text)
    return (m.group(1).strip(" -*>") if m else ""), []


def describe(path, root=ROOT):
    full = os.path.join(root, path)
    ext = os.path.splitext(path)[1].lower()
    try:
        size = os.path.getsize(full)
    except OSError:
        return "(missing from the working tree)", []
    if ext in (".py", ".md", ".html", ".htm", ".js", ".txt", ".vbs", ".bat", ".ps1", ".pine", ".cs", ".yml", ".yaml", ".toml", ".json", ".ini", ".cfg"):
        if size > 3_000_000:
            return "%s file, %s bytes (too large to read)" % (ext.lstrip("."), f"{size:,}"), []
        try:
            text = open(full, encoding="utf-8", errors="replace").read()
        except OSError as e:
            return "(unreadable: %s)" % e, []
        try:
            if ext == ".py":
                p, f = describe_py(text)
            elif ext == ".md":
                p, f = describe_md(text)
            elif ext in (".html", ".htm", ".js"):
                p, f = describe_web(text)
            else:
                first = next((l.strip() for l in text.splitlines() if l.strip()), "")
                p, f = (first.lstrip("#'; ").strip() if ext in (".vbs", ".bat", ".ps1", ".txt", ".pine", ".cs", ".yml", ".yaml",
                                                               ".toml", ".ini", ".cfg") else "%s data, %s bytes" % (ext.lstrip("."), f"{size:,}")), []
        except SyntaxError as e:
            return "(python file that does not parse: line %s)" % e.lineno, []
        return (p or "(no self-description)"), f
    return "%s file, %s bytes" % (ext.lstrip(".") or "no-extension", f"{size:,}"), []


def build(files, root=ROOT, now=None):
    now = now or datetime.datetime.now()
    groups = {}
    for p in files:
        groups.setdefault(p.split("/")[0] if "/" in p else "(root)", []).append(p)
    lines = ["# EDGE-LOG repo map", "",
             "Built %s by tools/repo_map.py from `git ls-files` (%d files). One line per file: purpose (from the file's own "
             "docstring / heading) - key functions." % (now.strftime("%Y-%m-%d %H:%M"), len(files)), "",
             "| Folder | Files |", "|---|---|"]
    lines += ["| %s | %d |" % (g, len(v)) for g, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))]
    for g in sorted(groups):
        lines += ["", "## %s (%d)" % (g, len(groups[g])), ""]
        for p in groups[g]:
            purpose, funcs = describe(p, root)
            row = "- `%s` - %s" % (p, _clip(purpose))
            if funcs:
                row += " | " + ", ".join(funcs[:MAX_FUNCS]) + (" +%d more" % (len(funcs) - MAX_FUNCS) if len(funcs) > MAX_FUNCS else "")
            lines.append(row)
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--no-ping", action="store_true")
    a = ap.parse_args(argv)
    files = tracked_files()
    text = build(files)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    tmp = a.out + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, a.out)
    msg = "Repo map rebuilt: %d files -> %s" % (len(files), a.out)
    print(msg)
    if not a.no_ping:
        sys.path.insert(0, ROOT)
        try:
            from api import ntfy_push
            ntfy_push.push(msg, title="Repo map ready")
        except Exception as e:          # a ping failure never loses the map
            print("ping failed: %s: %s" % (type(e).__name__, e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
