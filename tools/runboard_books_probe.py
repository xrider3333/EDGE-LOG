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

2026-09-25 (book round 56): a book row also prints the drawdown with OPEN trades valued daily
(`book.mtm`) whenever it differs from the at-close drawdown. The gate now checks, on the
RUNBOARD tile AND on the native COMPARE > BOOKS view, for every stage: the new book prints that
line with the right figures for the stage on screen; a book whose second reading EQUALS the
first (an intraday-only book) prints nothing; and a book saved before the block existed prints
nothing and no "undefined".

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
        # the two day-stamping rules disagree on this one, so the row must say so
        'day_rule': {'used': 'utc_truncated', 'drawdown_differs': True, 'net_differs': False,
                     'session_day': {'total_pnl': 1119697.0, 'max_drawdown': 34903.0,
                                     'worst_stretch': {'from': '2020-02-26', 'to': '2020-03-25',
                                                       'depth': 34903.0}}},
        # open trades valued daily: deeper on every stage, net shifted inside IS and LB only
        'mtm': {'whole': {'total_pnl': 1119697.0, 'max_drawdown': 49855.0},
                'pre_lockbox': {'total_pnl': 941840.0, 'max_drawdown': 34449.0},
                'lockbox': {'total_pnl': 177857.0, 'max_drawdown': 49855.0},
                'drawdown_differs': True, 'net_differs': False, 'marked_trades': 756,
                'multi_day_legs': ['AAA_1_0.py']},
    },
}
# an intraday-only book: its second reading EQUALS the first, so no line may print
FLAT_BOOK = {
    'id': 90002, 'strategy': 'BOOK: probe intraday', 'scope': 'Book',
    'validate': {'verdict': 'PASS'},
    'book': {
        'name': 'PROBE INTRADAY BOOK', 'slices_held': 7, 'slices_n': 8,
        'legs': [{'strategy': 'DDD_1_0.py', 'mult': 20}],
        'whole': {'total_pnl': 300000, 'profit_factor': 1.40, 'max_drawdown': 20000,
                  'num_trades': 800},
        'pre_lockbox': {'total_pnl': 250000, 'profit_factor': 1.38, 'max_drawdown': 20000,
                        'num_trades': 700},
        'lockbox': {'total_pnl': 50000, 'profit_factor': 1.5, 'max_drawdown': 9000,
                    'num_trades': 100},
        'mtm': {'whole': {'total_pnl': 300000.0, 'max_drawdown': 20000.0},
                'pre_lockbox': {'total_pnl': 250000.0, 'max_drawdown': 20000.0},
                'lockbox': {'total_pnl': 50000.0, 'max_drawdown': 9000.0},
                'drawdown_differs': False, 'net_differs': False, 'marked_trades': 0,
                'multi_day_legs': []},
    },
}
# what the open-trades line must say on each stage: (DD valued daily, DD at close, net or None)
MTM_EXPECT = {'full': ('49,855', '34,329', None), 'is': ('34,449', '34,329', '941,840'),
              'lb': ('49,855', '26,235', '177,857')}
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
  // one row's open-trades line, by book name: '' when the row prints none
  function readMtm(rows){
    var o={};
    for(var i=0;i<rows.length;i++){
      var t=rows[i].textContent||'', line='', ds=rows[i].querySelectorAll('div');
      for(var j=0;j<ds.length;j++){var dt=ds[j].textContent||'';if(dt.indexOf('open trades valued daily')===0){line=dt;break;}}
      var nm=(t.indexOf('PROBE NEW BOOK')>=0)?'new':((t.indexOf('PROBE OLD BOOK')>=0)?'old':((t.indexOf('PROBE INTRADAY BOOK')>=0)?'flat':null));
      if(nm)o[nm]=line;
      if(nm&&(t.indexOf('undefined')>=0||t.indexOf('NaN')>=0))o[nm+'Undef']=true;
    }
    return o;
  }
  function report(why){
    if(reported)return; reported=true;
    var out={why:why,cases:{}};
    try{
      var w=document.getElementById('f').contentWindow, d=w.document;
      out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
      for(var i=0;i<SAMPLES.length;i++){
        var smp=SAMPLES[i], r={};
        r.call=w.eval("(function(){try{"
          +"localStorage.setItem('augurPrefs',"+JSON.stringify(JSON.stringify({'cmpMode':'board','rbSample':smp}))+");"
          +"runHistory="+JSON.stringify(RUNS)+";"
          // the tile reads its stage from the saved SAMPLE pick (rbSample); assigning a global
          //   _rbS never reached it, so before 2026-09-25 every pass of this loop rendered LB
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
        r.dayRule=txt.indexOf('day rule')>=0 && txt.indexOf('34,903')>=0 && txt.indexOf('2020-03-25')>=0;
        var oldRow='';
        for(var k3=0;k3<rows.length;k3++)
          if(rows[k3].textContent.indexOf('PROBE OLD BOOK')>=0)oldRow=rows[k3].textContent;
        r.oldNoDayRule=(oldRow.indexOf('day rule')<0);
        r.hasDepth=txt.indexOf('34,329')>=0 || txt.indexOf('34329')>=0;
        r.namesInert=txt.indexOf('BBB_1_0')>=0;
        r.undef=txt.indexOf('undefined')>=0 || txt.indexOf('NaN')>=0;
        // the OLD row must carry no stretch line of its own
        var oldTxt='';
        for(var k2=0;k2<rows.length;k2++)
          if(rows[k2].textContent.indexOf('PROBE OLD BOOK')>=0)oldTxt=rows[k2].textContent;
        r.oldClean=(oldTxt.indexOf('worst stretch')<0);
        r.mtm=readMtm(rows);
        // the same three books on the native COMPARE > BOOKS view, same stage
        r.call2=w.eval("(function(){try{"
          +"localStorage.setItem('augurPrefs',"+JSON.stringify(JSON.stringify({'c2Screen':'cmp','c2View':'books','c2Stage':smp}))+");"
          +"runHistory="+JSON.stringify(RUNS)+";"
          +"activeTab='augur';augurSub='cmp2';renderApp();return 'OK';"
          +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
        var rows2=d.querySelectorAll('tr[data-c2run]');
        r.bookRows2=rows2.length;
        r.mtm2=readMtm(rows2);
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
        f.write(PROBE_HTML.replace('__RUNS__', json.dumps([NEW_BOOK, OLD_BOOK, FLAT_BOOK]))
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
        print('             dayRule=%s oldNoDayRule=%s' % (r.get('dayRule'), r.get('oldNoDayRule')))
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
                       ('oldClean', 'a book with no worst_stretch block printed one anyway'),
                       ('dayRule', 'the day-stamping disagreement is not printed on the row'),
                       ('oldNoDayRule', 'a book with no day_rule block printed one anyway')):
            if not r.get(k):
                bad.append('%s: %s' % (smp, why))
        if r.get('undef'):
            bad.append('%s: a book row printed undefined or NaN' % smp)
        dd_m, dd_c, net_m = MTM_EXPECT[smp]
        for view, key, call in (('RUNBOARD tile', 'mtm', r.get('call')), ('BOOKS view', 'mtm2', r.get('call2'))):
            m = r.get(key) or {}
            print('             %-13s open-trades line: new=%a | old=%a | intraday=%a'
                  % (view, (m.get('new') or '')[:90], m.get('old'), m.get('flat')))
            if call != 'OK':
                bad.append('%s %s: %s' % (smp, view, str(call)[:300]))
                continue
            line = m.get('new') or ''
            if not line:
                bad.append('%s %s: the book with open trades valued daily printed no line' % (smp, view))
            else:
                if dd_m not in line or dd_c not in line:
                    bad.append('%s %s: line does not read DD %s vs %s: %a' % (smp, view, dd_m, dd_c, line))
                if net_m and net_m not in line:
                    bad.append('%s %s: line does not carry the shifted net %s: %a' % (smp, view, net_m, line))
                if not net_m and 'net unchanged' not in line:
                    bad.append('%s %s: whole-run line should say net unchanged: %a' % (smp, view, line))
            if 'old' not in m or m.get('old'):
                bad.append('%s %s: a book saved before the block printed a line (or its row is missing)' % (smp, view))
            if 'flat' not in m or m.get('flat'):
                bad.append('%s %s: an intraday-only book printed a line (or its row is missing)' % (smp, view))
            if any(k.endswith('Undef') for k in m):
                bad.append('%s %s: a book row printed undefined or NaN' % (smp, view))
    if bad:
        print('RUNBOARD BOOKS PROBE: FAIL')
        for b in bad:
            print('  - ' + b)
        return FAIL
    print('RUNBOARD BOOKS PROBE: PASS')
    return PASS


if __name__ == '__main__':
    sys.exit(main())
