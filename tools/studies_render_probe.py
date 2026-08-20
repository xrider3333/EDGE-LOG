#!/usr/bin/env python3
"""
tools/studies_render_probe.py -- render gate for COMPARE > STUDIES.

WHY THIS EXISTS
---------------
tools/preflight_boot.py proves index.html BOOTS. It does not prove any particular
VIEW renders, and this project has already shipped a view that crashed while the
boot gate stayed green (v64.22 shipped a _dOpts crash past preflight). The STUDIES
board is a large branch inside renderApp that the boot gate never enters, so it
needs a gate of its own.

WHAT IT DOES
------------
Serves the repo over loopback, loads index.html in an iframe, then -- inside the
iframe's own global scope, where index.html's top-level `let` bindings actually
live -- forces the studies view and re-renders it once per control combination:

    activeTab='augur'; augurSub='cmp'; augurPrefs.cmpMode='research'

For each case it reports how many chart points (data-repoint), table rows
(data-rerow), strategy-rail buttons (data-refam) and chart drag handles
(data-rechh) the render produced, plus any exception renderApp threw.

No Firebase sign-in is needed. The studies registry is static data inside
index.html; run history simply reads as empty, which is a legitimate state (a row
then falls back to the window recorded in the registry, or honestly shows a dash).
That also means the counts here are a FLOOR: signed in, rows backed by real runs
gain their run windows, so the COMMON WINDOW basis reaches more of them.

WHAT IT ASSERTS
---------------
  * every case renders without throwing
  * the ALL case draws ONE chart, not one per study
  * the strategy rail exists and picking a strategy narrows both the chart and
    the tables (fewer rows AND fewer points than ALL)
  * no case silently empties the board

Exit codes match preflight_boot.py: 0 PASS, 1 FAIL, 2 INCONCLUSIVE.

Stdlib only, plus a subprocess call to local Chrome.
"""
import http.server
import json
import os
import re
import subprocess
import sys
import tempfile
import threading

PASS, FAIL, INCONCLUSIVE = 0, 1, 2
PROBE_FILENAME = '_studies_probe.html'

# name -> the augurPrefs the case renders under. 'research' cmpMode is constant.
CASES = [
    ('all',          {}),
    ('fam-ORB',      {'resFilt': '{"fam":["ORB"]}'}),
    ('fam-NOISE',    {'resFilt': '{"fam":["NOISE"]}'}),
    ('stage-is',     {'resStage': 'is'}),
    ('stage-lb',     {'resStage': 'lb'}),
    ('axis-ratio',   {'resAxis': 'ratio'}),
    ('axis-ppt',     {'resAxis': 'ppt'}),
    ('basis-year',   {'resBasis': 'year'}),
    ('order-result', {'resDate': 'res'}),
    ('order-ran',    {'resDate': 'ran'}),
    ('scope-30',     {'resScope': '30'}),
    ('split-side',   {'resSplit': 'side'}),
    ('more-open',    {'resMore': True, 'resHelp': True}),
    ('colour-off',   {'resColour': 'off'}),
    ('vs-crown',     {'resRel': 'crown'}),
    ('vs-crown-orb', {'resRel': 'crown', 'resFilt': '{"fam":["ORB"]}'}),
    ('no-frontier',  {'resFront': False}),
]

PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>studies probe</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html" style="width:1400px;height:900px;border:0"></iframe>
<pre id="o"></pre>
<script>
var CASES = __CASES__;
(function(){
  var reported=false;
  function report(why){
    if(reported)return; reported=true;
    var out={why:why,cases:{}};
    try{
      var w=document.getElementById('f').contentWindow, d=w.document;
      out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
      for(var i=0;i<CASES.length;i++){
        var nm=CASES[i][0], pref=CASES[i][1];
        pref.cmpMode='research';
        var r={};
        r.call=w.eval("(function(){try{"
          +"localStorage.setItem('augurPrefs',"+JSON.stringify(JSON.stringify(pref))+");"
          +"activeTab='augur';augurSub='cmp';renderApp();return 'OK';"
          +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
        r.points=d.querySelectorAll('[data-repoint]').length;
        r.rows=d.querySelectorAll('tr[data-rerow]').length;
        r.rail=d.querySelectorAll('[data-refam]').length;
        r.charts=d.querySelectorAll('[data-rechh]').length;
        var ap=d.getElementById('app');
        r.appLen=ap?ap.innerHTML.length:-1;
        out.cases[nm]=r;
      }
    }catch(e){out.err=String(e);}
    document.getElementById('o').textContent='STUDIESPROBE: '+JSON.stringify(out);
  }
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){report('load');},3000);});
  setTimeout(function(){report('backstop');},30000);
})();
</script>
</body></html>
"""


def find_chrome():
    cands = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]
    local = os.environ.get('LOCALAPPDATA')
    if local:
        cands.append(os.path.join(local, r"Google\Chrome\Application\chrome.exe"))
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def make_handler(root):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root, **kw)

        def log_message(self, *a):
            pass
    return H


def clean(ppath, pdir):
    try:
        os.remove(ppath)
        os.rmdir(pdir)
    except OSError:
        pass


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    chrome = find_chrome()
    if not chrome:
        print('STUDIES PROBE: INCONCLUSIVE (no chrome found)')
        return INCONCLUSIVE
    pdir = os.path.join(root, '_probe')
    os.makedirs(pdir, exist_ok=True)
    ppath = os.path.join(pdir, PROBE_FILENAME)
    with open(ppath, 'w', encoding='utf-8') as f:
        f.write(PROBE_HTML.replace('__CASES__', json.dumps(CASES)))
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(root))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = 'http://127.0.0.1:%d/_probe/%s' % (port, PROBE_FILENAME)
    with tempfile.TemporaryDirectory() as ud:
        args = [chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
                '--hide-scrollbars', '--virtual-time-budget=30000',
                '--user-data-dir=' + ud, '--dump-dom', url]
        try:
            out = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                                 errors='replace', timeout=120).stdout or ''
        except subprocess.TimeoutExpired:
            clean(ppath, pdir)
            print('STUDIES PROBE: INCONCLUSIVE (chrome timed out)')
            return INCONCLUSIVE
    clean(ppath, pdir)
    m = re.search(r'STUDIESPROBE: (\{.*?\})\s*<', out, re.S)
    if not m:
        print('STUDIES PROBE: INCONCLUSIVE (probe produced no reading)')
        return INCONCLUSIVE
    d = json.loads(m.group(1))
    cs = d.get('cases') or {}
    if d.get('err') or not cs:
        print('STUDIES PROBE: INCONCLUSIVE (%s)' % (d.get('err') or 'no cases ran'))
        return INCONCLUSIVE
    print('STUDIES PROBE: version %s, %d cases' % (d.get('VERSION'), len(cs)))
    bad = []
    for nm, _ in CASES:
        r = cs.get(nm)
        if not r:
            bad.append(nm + ': never ran')
            continue
        print('  %-13s points=%-4s rows=%-4s rail=%-2s charts=%-2s %s'
              % (nm, r['points'], r['rows'], r['rail'], r['charts'], r['call']))
        if r['call'] != 'OK':
            bad.append(nm + ': ' + str(r['call'])[:300])
            continue
        if r['charts'] != 1:
            bad.append('%s: %d charts drawn, expected exactly 1' % (nm, r['charts']))
        if r['rail'] < 2:
            bad.append('%s: strategy rail missing (%d buttons)' % (nm, r['rail']))
        if r['rows'] < 1:
            bad.append('%s: no table rows rendered' % nm)
    a, o = cs.get('all'), cs.get('fam-ORB')
    if a and o and o['call'] == 'OK' and a['call'] == 'OK':
        if not (o['rows'] < a['rows'] and o['points'] < a['points']):
            bad.append('picking a strategy did not narrow the board (ALL rows=%s pts=%s, ORB rows=%s pts=%s)'
                       % (a['rows'], a['points'], o['rows'], o['points']))
    if bad:
        print('STUDIES PROBE: FAIL')
        for b in bad:
            print('  - ' + b)
        return FAIL
    print('STUDIES PROBE: PASS')
    return PASS


if __name__ == '__main__':
    sys.exit(main())
