#!/usr/bin/env python
"""ONE MONEY FORMAT probe - pins index.html's elMoney (ledger calm-down item 6).

There is no Node here, so the page's own function is lifted verbatim between its EL_MONEY_START / EL_MONEY_END
markers and run in headless Chrome (the ddpct_parity_probe pattern). Every case states the exact string expected.

    python tools/money_fmt_probe.py              # check the cases
    python tools/money_fmt_probe.py --selftest   # + plant three mutants and require each to be caught
"""
import json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OK, FAIL, INCONCLUSIVE = 0, 1, 2

# (value, opts, expected)
CASES = [
    (987654.0, {"signed": True}, "+$987.7k"),          # the scope's own example
    (991900.0, {}, "$991.9k"),
    (-987654.0, {"signed": True}, "-$987.7k"),
    (999950.0, {}, "$1.00M"),                          # never '$1000.0k'
    (999949.0, {}, "$999.9k"),
    (1234567.0, {"signed": True}, "+$1.23M"),
    (100000.0, {}, "$100.0k"),                         # compact starts at $100,000
    (99999.4, {}, "$99,999"),
    (12345.67, {}, "$12,346"),                         # no cents from $1,000
    (1000.0, {"signed": True}, "+$1,000"),
    (999.994, {}, "$999.99"),
    (999.996, {}, "$1,000"),                           # rounds into the no-cents band
    (987.654, {}, "$987.65"),
    (-0.42, {"signed": True}, "-$0.42"),
    (0.0, {"signed": True}, "$0.00"),                  # zero carries no sign
    (-0.001, {"signed": True}, "$0.00"),               # rounds to zero: no '-$0.00'
    (-0.0, {}, "$0.00"),
    (None, {}, "\u2014"),
    ("", {}, "\u2014"),
    ("abc", {}, "\u2014"),
    ("1500", {}, "$1,500"),                            # numeric strings are numbers
    (250000.0, {"compactFrom": float("inf")}, "$250,000"),
    (12345.0, {"compactFrom": 10000}, "$12.3k"),
]

MUTANTS = [
    ("cents kept over $1,000", "body='$'+Math.round(a).toLocaleString('en-US');\n  }else{", "body='$'+a.toFixed(2);\n  }else{"),
    ("no M roll-over at 999,950", "if(a>=999950)", "if(a>=1e9)"),
    ("sign on zero", "n<0?'-':(opts.signed&&n>0?'+':'')", "n<0?'-':(opts.signed&&n>=0?'+':'')"),
]


def lift(src):
    a, b = src.find("const EL_MONEY_START"), src.find("const EL_MONEY_END")
    return src[a:b] if 0 <= a < b else None


def find_chrome():
    c = [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]
    if os.environ.get("LOCALAPPDATA"):
        c.append(os.path.join(os.environ["LOCALAPPDATA"], r"Google\Chrome\Application\chrome.exe"))
    return next((x for x in c if os.path.isfile(x)), None)


def run(chrome, js):
    calls = ",".join("elMoney(%s,%s)" % (json.dumps(v), json.dumps(o)) for v, o, _w in CASES)
    html = ("<!doctype html><meta charset=utf-8><body><pre id=out></pre><script>\n" + js +
            "\ndocument.getElementById('out').textContent=JSON.stringify([" + calls + "]);\n</script></body>")
    d = tempfile.mkdtemp(prefix="moneyfmt")
    p = os.path.join(d, "p.html")
    open(p, "w", encoding="utf-8").write(html)
    out = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--user-data-dir=" + os.path.join(d, "prof"),
                          "--virtual-time-budget=5000", "--dump-dom", "file:///" + p.replace("\\", "/")],
                         capture_output=True, text=True, encoding="utf-8", timeout=120).stdout
    m = re.search(r'<pre id="out">(.*?)</pre>', out, re.S)
    if not m:
        return None
    import html as H
    return json.loads(H.unescape(m.group(1).strip()))


def check(chrome, js):
    got = run(chrome, js)
    if got is None:
        return None
    return ["%r %s: got %r, want %r" % (v, o, g, w) for (v, o, w), g in zip(CASES, got) if g != w]


def main():
    src = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    js = lift(src)
    if not js:
        print("INCONCLUSIVE: EL_MONEY markers not found"); return INCONCLUSIVE
    chrome = find_chrome()
    if not chrome:
        print("INCONCLUSIVE: no Chrome"); return INCONCLUSIVE
    bad = check(chrome, js)
    if bad is None:
        print("INCONCLUSIVE: probe page printed nothing"); return INCONCLUSIVE
    for b in bad:
        print("FAIL", b)
    print("%d of %d cases agree" % (len(CASES) - len(bad), len(CASES)))
    rc = FAIL if bad else OK
    if "--selftest" in sys.argv:
        for name, a, b in MUTANTS:
            if a not in js:
                print("SELFTEST INCONCLUSIVE: mutant anchor missing:", name); rc = rc or INCONCLUSIVE; continue
            mb = check(chrome, js.replace(a, b, 1))
            caught = bool(mb)
            print("selftest mutant %-28s %s" % (name, "CAUGHT (%d cases)" % len(mb) if caught else "MISSED"))
            if not caught:
                rc = FAIL
    print("PASS" if rc == OK else "NOT PASS")
    return rc


if __name__ == "__main__":
    sys.exit(main())
