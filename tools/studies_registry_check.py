#!/usr/bin/env python3
"""Check RESEARCH_STUDIES against the rules written in STUDIES_BOARD.md.

Evaluates the registry literal in headless Chrome (it is JavaScript, so the browser is
the only honest parser), dumps it to JSON, then asserts the contract in Python:
  - row numbers are unique across the WHOLE board and never reused
  - every row has the required fields
  - drawdown is always positive
  - tone is one of the five allowed values
  - no row supplies a profit-divided-by-drawdown figure (the board computes it)
  - chart blocks carry no y / yCap (the vertical axis is chosen by the reader)
  - a row claiming a run number actually names one
"""
import json
import os
import re
import subprocess
import sys
import tempfile

WT = r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\enguq-lim-cards"
sys.path.insert(0, os.path.join(WT, "tools"))
from preflight_boot import find_chrome  # noqa: E402

src = open(os.path.join(WT, "index.html"), encoding="utf-8").read()
i = src.index("const RESEARCH_STUDIES=[")
d, j = 0, i
while True:
    if src[j] == "[":
        d += 1
    elif src[j] == "]":
        d -= 1
        if d == 0:
            break
    j += 1
lit = src[i:j + 1]

page = ("<!doctype html><meta charset=\"utf-8\"><body><script>\ntry{\n" + lit +
        ";\ndocument.title='OK:'+JSON.stringify(RESEARCH_STUDIES);}"
        "catch(e){document.title='ERR:'+String(e&&e.message||e);}\n</script></body>")

tmp = tempfile.mkdtemp()
fp = os.path.join(tmp, "reg.html")
open(fp, "w", encoding="utf-8").write(page)

chrome = find_chrome()
if not chrome:
    print("INCONCLUSIVE: no chrome")
    sys.exit(2)
out = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
                      "--virtual-time-budget=4000", "--dump-dom",
                      "file:///" + fp.replace("\\", "/")],
                     capture_output=True, text=True, timeout=120).stdout

m = re.search(r"<title>(OK|ERR):(.*?)</title>", out, re.S)
if not m:
    print("INCONCLUSIVE: no marker")
    sys.exit(2)
if m.group(1) == "ERR":
    print("FAIL - the registry does not parse:", m.group(2)[:400])
    sys.exit(1)

studies = json.loads(m.group(2))
print("studies:", len(studies))

fails, seen, tones = [], {}, {"champ", "good", "frag", "fail", "ref"}
total_rows = 0
for st in studies:
    for f in ("key", "title", "sub", "disc", "fam", "isLbl", "rows"):
        if f not in st:
            fails.append("study %s missing %s" % (st.get("key"), f))
    ch = st.get("chart")
    if ch:
        for bad in ("y", "yCap"):
            if bad in ch:
                fails.append("study %s chart must not define %s" % (st["key"], bad))
        for f in ("x", "xCap", "yMode"):
            if f not in ch:
                fails.append("study %s chart missing %s" % (st["key"], f))
    for r in st.get("rows", []):
        total_rows += 1
        n = r.get("n")
        if n is None:
            fails.append("row without a number in %s" % st["key"])
            continue
        if n in seen:
            fails.append("row %s duplicated: %s and %s" % (n, seen[n], st["key"]))
        seen[n] = st["key"]
        for f in ("name", "what", "tone", "read"):
            if f not in r:
                fails.append("row %s missing %s" % (n, f))
        if r.get("tone") not in tones:
            fails.append("row %s bad tone %r" % (n, r.get("tone")))
        if "dd" in r and r["dd"] is not None and r["dd"] < 0:
            fails.append("row %s drawdown is negative" % n)
        for bad in ("mar", "netdd", "ratio"):
            if bad in r:
                fails.append("row %s supplies %s, which the board computes" % (n, bad))
        if "runs" in r and not r["runs"]:
            fails.append("row %s has an empty runs array; omit the field instead" % n)

nums = sorted(seen)
print("rows: %d, numbers %d..%d, unique: %s" % (total_rows, nums[0], nums[-1],
                                                len(nums) == total_rows))
mine = [n for n in nums if n >= 130]
print("newly added: %d rows (%d..%d)" % (len(mine), min(mine), max(mine)))
print("families:", sorted({r.get("fam", st.get("fam"))
                           for st in studies for r in st.get("rows", [])}))

print("\n" + ("FAIL:\n  " + "\n  ".join(fails) if fails else
             "PASS - registry parses, %d rows, all numbers unique, contract holds"
             % total_rows))
sys.exit(1 if fails else 0)
