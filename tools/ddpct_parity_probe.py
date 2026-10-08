#!/usr/bin/env python
"""DD% PARITY - the page's _ddPctPeakOf must agree with augur_engine.drawdowns.dd_pct_peak.

WHY ITS OWN PROBE. The owner's DD% has to exist twice: the engine computes it when a run is
saved, and the page computes it from a saved curve so a hover does not need a round trip. DD5
already lives that way. Two copies of one rule drift silently - nothing fails, the two surfaces
just stop agreeing - and no Python test can see the JavaScript half. There is no Node in this
environment, so the JS is run in the same headless Chrome the report probe uses.

WHAT IT CHECKS. Both implementations, on the same curves, to four decimals: the owner's example
($100k off a $1M peak = 10%), a curve that never makes a new high, the case where the worst fall
in PERCENT is a different episode from the worst in DOLLARS, a fall past zero, and a curve with
no drawdown at all.

    python tools/ddpct_parity_probe.py              # compare the two
    python tools/ddpct_parity_probe.py --selftest   # + require the mutants to be caught

--selftest is the part that makes this worth having: it plants the OLD formula (the dollar fall
over the starting account, which printed 117% for a $116.9k drop) and the plausible-but-wrong one
(the fall over its own episode peak rather than the running maximum) into the page copy and
requires the comparison to fail on both. A parity check that cannot fail is decoration.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OK, FAIL, INCONCLUSIVE = 0, 1, 2

# (name, cumulative P&L per saved point in POINTS, mult, expected %)
CASES = [
    ("owner example: $100k off a $1M peak", [900000.0, 800000.0], 1.0, 10.0),
    # cumulative, so equity goes 50k then 80k and the worst fall from the 100k
    # opening high is the first point, not the last
    ("never makes a new high", [-50000.0, -20000.0], 1.0, 50.0),
    ("worst PERCENT is not the worst DOLLARS",
     [100000.0, 60000.0, 100000.0, 800000.0, 710000.0], 1.0, 20.0),
    ("falls past zero, not capped", [-140000.0], 1.0, 140.0),
    ("no drawdown at all", [1000.0, 2000.0, 3000.0], 1.0, 0.0),
    # 45,000 pts x $20 puts equity at $1M, then it gives back $50k = 5%
    ("points scaled by a multiplier", [45000.0, 42500.0], 20.0, 5.0),
]

MUTANTS = [
    ("the OLD share-of-the-start formula",
     "const f=(P-eq)/P;", "const f=(P-eq)/S;",
     "the dollar fall over the opening balance - what made a $116.9k drop read 117%"),
    ("divided by the episode peak instead of the running high",
     "if(eq>P)P=eq;", "P=eq;",
     "plausible and wrong: with the peak following equity downward every fall measures zero"),
]


def _js_source(index_path):
    """The page's helper, lifted verbatim between its two markers."""
    with open(index_path, encoding="utf-8") as f:
        s = f.read()
    a = s.find("const DD_PCT_START_USD")
    b = s.find("const DD_PCT_LABEL")
    if a < 0 or b < 0 or b <= a:
        return None
    return s[a:b]


def find_chrome():
    cands = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        cands.append(os.path.join(local, r"Google\Chrome\Application\chrome.exe"))
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def _run_js(chrome, js, cases):
    """Each case's percentage, as the PAGE computes it, via headless Chrome."""
    calls = ",".join("f(%s,%s,100000)" % (json.dumps(c), json.dumps(m))
                     for _n, c, m, _w in cases)
    html = (
        "<!doctype html><meta charset=utf-8><body><pre id=out></pre><script>\n"
        + js +
        "\nconst f=_ddPctPeakOf;\n"
        "const rs=[" + calls + "];\n"
        "document.getElementById('out').textContent="
        "JSON.stringify(rs.map(r=>(r&&isFinite(r.pct))?+r.pct.toFixed(4):null));\n"
        "</script></body>")
    d = tempfile.mkdtemp(prefix="ddpctprobe")
    p = os.path.join(d, "probe.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write(html)
    try:
        out = subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--user-data-dir=" + os.path.join(d, "prof"),
             "--virtual-time-budget=5000", "--dump-dom", "file:///" + p.replace("\\", "/")],
            capture_output=True, text=True, timeout=120).stdout
    except Exception as e:
        return None, "chrome failed: %s: %s" % (type(e).__name__, e)
    m = re.search(r'<pre id="out">(.*?)</pre>', out, re.S)
    if not m:
        return None, "the probe page printed nothing"
    try:
        return json.loads(m.group(1).strip()), None
    except Exception as e:
        return None, "unreadable probe output (%s): %r" % (type(e).__name__, m.group(1)[:120])


def compare(chrome, js):
    """[] when the two agree on every case, else one line per disagreement."""
    from augur_engine.drawdowns import dd_pct_peak
    got, err = _run_js(chrome, js, CASES)
    if err:
        return None, err
    bad = []
    for i, (nm, cum, mult, want) in enumerate(CASES):
        daily = [cum[0]] + [cum[k] - cum[k - 1] for k in range(1, len(cum))]
        py = dd_pct_peak([v * mult for v in daily])
        page = got[i] if i < len(got) else None
        if page is None or abs(page - py) > 1e-4:
            bad.append("%s: the page reads %s, the engine %s" % (nm, page, py))
        elif abs(py - want) > 1e-4:
            bad.append("%s: both agree on %s but the case expects %s" % (nm, py, want))
    return bad, None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    selftest = "--selftest" in argv
    idx = os.path.join(ROOT, "index.html")
    chrome = find_chrome()
    if not chrome:
        print("DDPCTPARITY: INCONCLUSIVE -- no Chrome found")
        return INCONCLUSIVE
    js = _js_source(idx)
    if not js:
        print("DDPCTPARITY: FAIL -- _ddPctPeakOf is not in index.html between its markers")
        return FAIL

    bad, err = compare(chrome, js)
    if err:
        print("DDPCTPARITY: INCONCLUSIVE -- %s" % err)
        return INCONCLUSIVE
    if bad:
        print("DDPCTPARITY: FAIL")
        for b in bad:
            print("  - %s" % b)
        return FAIL
    print("DDPCTPARITY: PASS -- the page and the engine agree on %d cases" % len(CASES))
    if not selftest:
        return OK

    worst = OK
    for name, find, repl, why in MUTANTS:
        if find not in js:
            print('-- mutant "%s": INCONCLUSIVE, anchor not found' % name)
            worst = max(worst, INCONCLUSIVE)
            continue
        print('-- mutant "%s": expect FAIL' % name)
        mbad, merr = compare(chrome, js.replace(find, repl, 1))
        if merr:
            print("   INCONCLUSIVE -- %s" % merr)
            worst = max(worst, INCONCLUSIVE)
        elif not mbad:
            print("   NOT CAUGHT -- the parity check is decoration: %s" % why)
            worst = FAIL
        else:
            print("   caught (%d case(s) disagree)" % len(mbad))
    if worst == OK:
        print("SELFTEST: PASS -- both mutants caught and the real pair agrees")
    else:
        print("SELFTEST: FAIL")
    return worst


if __name__ == "__main__":
    sys.exit(main())
