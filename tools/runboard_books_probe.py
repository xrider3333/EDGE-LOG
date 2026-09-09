#!/usr/bin/env python3
"""
tools/runboard_books_probe.py -- render gate for the BOOKS tile in COMPARE > RUNBOARD.

WHY THIS EXISTS (2026-09-09). tools/preflight_boot.py proves index.html BOOTS and
tools/studies_render_probe.py proves the STUDIES branch renders; neither enters the
RUNBOARD branch, and the BOOKS tile inside it is where a book run's summary is read.
v73.638 added a WORST-STRETCH line to every book row -- the dates and depth of the
stretch that sets the book's drawdown, plus the names of any leg that took no trades
inside it -- which is exactly the kind of small string-building change that has shipped
broken past the boot gate before (v73.367, v73.442, v73.443).

WHAT IT DOES. Serves the repo over loopback, loads index.html in an iframe, injects a
synthetic run history holding TWO book runs -- one carrying a `worst_stretch` block with
an absent leg, one from before the block existed -- then forces

    activeTab='augur'; augurSub='cmp'; augurPrefs.cmpMode='board'

and re-renders once per SAMPLE setting. It then asserts, from the rendered DOM:

  * renderApp threw nothing;
  * both book rows are present;
  * the row WITH a worst_stretch block prints its dates, its depth and the name of the
    absent leg;
  * the row WITHOUT one prints no stretch line at all and does not print "undefined"
    (the failure mode of reading `.from` off a missing block).

No Firebase sign-in is needed. Exit codes match the other gates: 0 PASS, 1 FAIL,
2 INCONCLUSIVE (tooling could not run).
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
PROBE_FILENAME = '_runboard_books_probe.html'

# Two book runs. NEW carries the v73.638 block; OLD is what every run saved before it looks
# like, and must render exactly as it always did.
NEW_BOOK = {
    'id': 90001, 'strategy': 'BOOK: probe new', 'scope': 'Book',
    'validate': {'verdict': 'PASS'},
    'book': {
        'name': 'PROBE NEW BOOK', 'slices_held': 8, 'slices_n': 8,
        'legs': [{'strategy': 'AAA_1_0.py', 'mult': 20}, {'strategy': 'BBB_1_0.py', 'mult': 50}],
        'whole': {'total_pnl': 1119697, 'profit_factor': 1.49, 'max_drawdown': 34329,
                  'num_trades': 4547},
        'pre_lockbox': {'total_pnl': 926527, 'profit_factor': 1.47, 'max_drawdown': 34329,
                        'num_trades': 4258},
        'lockbox': {'total_pnl': 193170, 'profit_factor': 1.57, 'max_drawdown': 26235,
                    'num_trades': 289},
        'worst_stretch': {'peak': '2022-04-26', 'from': '2022-04-27', 'to': '2022-05-24',
                          'depth': 34329.21, 'trading_days': 15,
                          'legs': [{'leg': 'AAA_1_0.py', 'usd': -34329.21, 'days': 15},
                                   {'leg': 'BBB_1_0.py', 'usd': 0.0, 'days': 0}]},
        'inert_legs': ['BBB_1_0.py'],
    },
}
OLD_BOOK = {
    'id': 90000, 'strategy': 'BOOK: probe old', 'scope': 'Book',
    'validate': {'verdict': 'WEAK'},
    'book': {
        'name': 'PROBE OLD BOOK', 'slices_held': 6, 'slices_n': 8,
        'legs': [{'strategy': 'CCC_1_0.py', 'mult': 20}],
        'whole': {'total_pnl': 500000, 'profit_factor': 1.30, 'max_drawdown': 40000,
                  'num_trades': 1000},
        'pre_lockbox': {'total_pnl': 450000, 'profit_factor': 1.29, 'max_drawdown': 40000,
                        'num_trades': 900},
        'lockbox': {'total_pnl': 50000, 'profit_factor': 1.35, 'max_drawdown': 12000,
                    'num_trades': 100},
    },
}
SAMPLES = ['full', 'is', 'lb']

PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>runboard books probe</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html" style="width:1400px;height:900px;border:0"></iframe>
<pre id="o"></pre>
<script>
var RUNS = __RUNS__, SAMPLES = __SAMPLES__;
(function(){
  var reported=false;
  function report(why){
    if(reported)return; reported=true;
    var out={why:why,cases:{}};
    try{
      var w=document.getElementById('f').contentWindow, d=w.document;
      out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
      for(var i=0;i<SAMPLES.length;i++){
        var smp=SAMPLES[i], r={};
        r.call=w.eval("(function(){try{"
          +"localStorage.setItem('augurPrefs',"+JSON.stringify(JSON.stringify({'cmpMode':'board'}))+");"
          +"runHistory="+JSON.stringify(RUNS)+";"
          +"try{_rbS='"+smp+"';}catch(e){}"
          +"activeTab='augur';augurSub='cmp';renderApp();return 'OK';"
          +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
        var rows=d.querySelectorAll('tr[data-rank-run]');
        r.bookRows=rows.length;
        var txt='';
        for(var k=0;k<rows.length;k++)txt+=rows[k].textContent+'\\n';
        r.hasNew=txt.indexOf('PROBE NEW BOOK')>=0;
        r.hasOld=txt.indexOf('PROBE OLD BOOK')>=0;
        r.hasDates=txt.indexOf('2022-04-27')>=0 && txt.indexOf('2022-05-24')>=0;
        r.hasDepth=txt.indexOf('34,329')>=0 || txt.indexOf('34329')>=0;
        r.namesInert=txt.indexOf('BBB_1_0')>=0;
        r.undef=txt.indexOf('undefined')>=0 || txt.indexOf('NaN')>=0;
        // the OLD row must carry no stretch line of its own
        var oldTxt='';
        for(var k2=0;k2<rows.length;k2++)
          if(rows[k2].textContent.indexOf('PROBE OLD BOOK')>=0)oldTxt=rows[k2].textContent;
        r.oldClean=(oldTxt.indexOf('worst stretch')<0);
        out.cases[smp]=r;
      }
    }catch(e){out.err=String(e);}
    document.getElementById('o').textContent='RBBOOKSPROBE: '+JSON.stringify(out);
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
        print('RUNBOARD BOOKS PROBE: INCONCLUSIVE (no chrome found)')
        return INCONCLUSIVE
    pdir = os.path.join(root, '_probe')
    os.makedirs(pdir, exist_ok=True)
    ppath = os.path.join(pdir, PROBE_FILENAME)
    with open(ppath, 'w', encoding='utf-8') as f:
        f.write(PROBE_HTML.replace('__RUNS__', json.dumps([NEW_BOOK, OLD_BOOK]))
                          .replace('__SAMPLES__', json.dumps(SAMPLES)))
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(root))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = 'http://127.0.0.1:%d/_probe/%s' % (port, PROBE_FILENAME)
    with tempfile.TemporaryDirectory() as ud:
        args = [chrome, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
                '--virtual-time-budget=30000', '--user-data-dir=' + ud, '--dump-dom', url]
        try:
            out = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                                 errors='replace', timeout=120).stdout or ''
        except subprocess.TimeoutExpired:
            clean(ppath, pdir)
            print('RUNBOARD BOOKS PROBE: INCONCLUSIVE (chrome timed out)')
            return INCONCLUSIVE
    clean(ppath, pdir)
    m = re.search(r'RBBOOKSPROBE: (\{.*?\})\s*<', out, re.S)
    if not m:
        print('RUNBOARD BOOKS PROBE: INCONCLUSIVE (probe produced no reading)')
        return INCONCLUSIVE
    d = json.loads(m.group(1))
    cs = d.get('cases') or {}
    if d.get('err') or not cs:
        print('RUNBOARD BOOKS PROBE: INCONCLUSIVE (%s)' % (d.get('err') or 'no cases ran'))
        return INCONCLUSIVE
    print('RUNBOARD BOOKS PROBE: version %s, %d cases' % (d.get('VERSION'), len(cs)))
    bad = []
    for smp in SAMPLES:
        r = cs.get(smp)
        if not r:
            bad.append('%s: never ran' % smp)
            continue
        print('  sample=%-4s rows=%s new=%s old=%s dates=%s depth=%s inert=%s oldClean=%s %s'
              % (smp, r['bookRows'], r['hasNew'], r['hasOld'], r['hasDates'], r['hasDepth'],
                 r['namesInert'], r['oldClean'], r['call']))
        if r['call'] != 'OK':
            bad.append('%s: %s' % (smp, str(r['call'])[:300]))
            continue
        if r['bookRows'] < 2:
            bad.append('%s: expected both book rows, saw %s' % (smp, r['bookRows']))
        for k, why in (('hasNew', 'the new-format book row is missing'),
                       ('hasOld', 'the pre-v73.638 book row is missing'),
                       ('hasDates', 'the worst-stretch dates are not printed'),
                       ('hasDepth', 'the worst-stretch depth is not printed'),
                       ('namesInert', 'the absent leg is not named'),
                       ('oldClean', 'a book with no worst_stretch block printed one anyway')):
            if not r.get(k):
                bad.append('%s: %s' % (smp, why))
        if r.get('undef'):
            bad.append('%s: a book row printed undefined or NaN' % smp)
    if bad:
        print('RUNBOARD BOOKS PROBE: FAIL')
        for b in bad:
            print('  - ' + b)
        return FAIL
    print('RUNBOARD BOOKS PROBE: PASS')
    return PASS


if __name__ == '__main__':
    sys.exit(main())
