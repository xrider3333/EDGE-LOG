"""weekly_cleanup.py -- B10 (AUTOMATIONS.md): the weekly DRY-RUN list of what could be cleared on the
PC: old worktrees, old scratch/backup/log files under C:/EdgeLog, and local model files nothing uses.

REPORT ONLY. This script never deletes, moves or edits anything: every row is a suggestion with its
size and why; deleting needs the owner's GO, row by row (MANAGER #220).

A worktree is listed when ALL hold: its last commit is older than --days (14), it has no uncommitted
changes, and its HEAD is already on origin/main (nothing would be lost). A dirty or unmerged old
worktree is listed separately as "keep - has work" so nobody deletes it by accident.
A model is listed when no tools/*.py names its tag, or it is a second name for weights another tag
already has (same ollama ID).

    python tools/weekly_cleanup.py [--days 14] [--out-dir C:/EdgeLog/manager/cleanup] [--no-size]
"""
import argparse
import datetime
import glob
import os
import re
import subprocess
import sys

HOME = os.environ.get("EDGELOG_HOME", r"C:\EdgeLog")
WT_ROOT = os.path.join(os.environ.get("LOCALAPPDATA", ""), "EdgeLog-worktrees")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(HOME, "manager", "cleanup")
# C:/EdgeLog top-level names that are old copies / one-off logs, never live state
SCRATCH_PATTERNS = ("*.bak-*", "_*backup*", "_ship_*.log", "_ship_*.err", "*.log.old",
                    os.path.join("ship_logs", "*.log"), os.path.join("_build_tmp", "*"))


def _git(args, cwd, timeout=60):
    try:
        r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip()
    except Exception as e:
        return 1, str(e)


def dir_size(path, cap_files=200000):
    total, n = 0, 0
    for root, dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
            n += 1
            if n >= cap_files:
                return total
    return total


def gb(n):
    return f"{n / 1e9:.2f} GB" if n >= 1e8 else f"{n / 1e6:.0f} MB"


def worktrees(days, now, size=True):
    """(clear, keep): worktrees older than `days` that are safe to drop / that hold work."""
    rc, out = _git(["worktree", "list", "--porcelain"], REPO)
    paths = [ln[9:] for ln in out.splitlines() if ln.startswith("worktree ")] if rc == 0 else []
    clear, keep = [], []
    for p in paths:
        if os.path.normcase(os.path.abspath(p)) == os.path.normcase(REPO) or not os.path.isdir(p):
            continue
        rc, ts = _git(["log", "-1", "--format=%ct"], p)
        if rc != 0 or not ts.isdigit():
            continue
        age = (now - datetime.datetime.fromtimestamp(int(ts))).days
        if age < days:
            continue
        _, dirty = _git(["status", "--porcelain", "--untracked-files=no"], p)
        merged = _git(["merge-base", "--is-ancestor", "HEAD", "origin/main"], p)[0] == 0
        row = {"path": p, "age_d": age, "dirty": bool(dirty), "merged": merged,
               "size": dir_size(p) if size else None}
        (clear if (merged and not dirty) else keep).append(row)
    return clear, keep


def scratch(days, now):
    rows, seen = [], set()
    for pat in SCRATCH_PATTERNS:
        for p in glob.glob(os.path.join(HOME, pat)):
            if p in seen:
                continue
            seen.add(p)
            try:
                age = (now - datetime.datetime.fromtimestamp(os.path.getmtime(p))).days
            except OSError:
                continue
            if age < days:
                continue
            sz = dir_size(p) if os.path.isdir(p) else os.path.getsize(p)
            rows.append({"path": p, "age_d": age, "size": sz})
    return sorted(rows, key=lambda r: -r["size"])


def _size_bytes(s):
    m = re.match(r"([\d.]+)\s*(GB|MB|KB|B)", s or "")
    if not m:
        return 0
    return int(float(m.group(1)) * {"GB": 1e9, "MB": 1e6, "KB": 1e3, "B": 1}[m.group(2)])


def models():
    """[{tag, id, size, why}] of ollama models nothing names, or that repeat another tag's weights."""
    try:
        out = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return None
    rows = []
    for ln in out.splitlines()[1:]:
        parts = re.split(r"\s{2,}", ln.strip())
        if len(parts) >= 3:
            rows.append({"tag": parts[0], "id": parts[1], "size": _size_bytes(parts[2])})
    code = ""
    for f in glob.glob(os.path.join(REPO, "tools", "*.py")) + glob.glob(os.path.join(REPO, "api", "*.py")):
        try:
            code += open(f, encoding="utf-8", errors="replace").read()
        except OSError:
            pass
    used = {r["tag"] for r in rows if r["tag"] in code or r["tag"].split(":")[0] in code}
    out_rows, by_id = [], {}
    for r in rows:
        by_id.setdefault(r["id"], []).append(r["tag"])
    for r in rows:
        if re.match(r"^[1-4][.-]", r["tag"]):
            continue                  # the owner's own numbered models (Cline in VS Code): never listed
        twins = [t for t in by_id[r["id"]] if t != r["tag"]]
        if r["tag"] not in used and twins and any(t in used for t in twins):
            out_rows.append(dict(r, why="same weights as " + ", ".join(twins) + " (removing a second name frees ~0 GB)", size=0))
        elif r["tag"] not in used:
            out_rows.append(dict(r, why="no tools/ or api/ file names it"))
    return out_rows


def report(days, now, size=True):
    clear, keep = worktrees(days, now, size)
    sc = scratch(days, now)
    md = models()
    L = [f"# Weekly cleanup (DRY RUN) {now:%Y-%m-%d}", "",
         "Nothing was deleted. Each row needs the owner's GO before anyone removes it.", ""]
    tot = sum(r["size"] or 0 for r in clear)
    L.append(f"## Worktrees safe to remove: {len(clear)}" + (f" ({gb(tot)})" if size else ""))
    L.append(f"Older than {days} days, no uncommitted changes, already on origin/main. "
             "Remove with `git worktree remove <path>` from the main checkout.")
    for r in sorted(clear, key=lambda r: -r["age_d"])[:400]:
        L.append(f"- {r['path']} - {r['age_d']} d" + (f", {gb(r['size'])}" if size else ""))
    if len(clear) > 400:
        L.append(f"- (+{len(clear) - 400} more)")
    L += ["", f"## Old worktrees to KEEP (they hold work): {len(keep)}"]
    for r in sorted(keep, key=lambda r: -r["age_d"]):
        why = ", ".join(w for w, on in (("uncommitted changes", r["dirty"]), ("commits not on main", not r["merged"])) if on)
        L.append(f"- {r['path']} - {r['age_d']} d, {why}")
    L += ["", f"## Old scratch / backup / log files under {HOME}: {len(sc)} ({gb(sum(r['size'] for r in sc))})"]
    for r in sc[:200]:
        L.append(f"- {r['path']} - {r['age_d']} d, {gb(r['size'])}")
    L.append("")
    if md is None:
        L.append("## Models: ollama not reachable, not checked")
    else:
        L.append(f"## Local model files nothing uses: {len(md)} ({gb(sum(r['size'] for r in md))})")
        for r in md:
            L.append(f"- {r['tag']} ({r['id']}) - {gb(r['size'])}: {r['why']}. Remove with `ollama rm {r['tag']}`")
        L.append("Ollama shares weight files between tags, so the space freed can be less than listed. "
                 "The owner's numbered 1.*-4.* models (old 1.* aliases + 2-4 owner models) are never listed.")
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--out-dir", default=OUT_DIR)
    ap.add_argument("--no-size", action="store_true")
    a = ap.parse_args(argv)
    now = datetime.datetime.now()
    text = report(a.days, now, size=not a.no_size)
    os.makedirs(a.out_dir, exist_ok=True)
    p = os.path.join(a.out_dir, f"cleanup-{now:%Y-%m-%d}.md")
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(p + ".tmp", p)
    print(f"cleanup report (dry run, nothing deleted): {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
