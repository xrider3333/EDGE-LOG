#!/usr/bin/env python3
"""
tools/studies_parity_snap.py -- fingerprint the STUDIES scatter, so a refactor can be
PROVEN not to have changed it.

WHY THIS EXISTS
---------------
The COMPARE rebuild has to put the STUDIES scatter on a new screen, and the owner's
one non-negotiable is that the chart keeps behaving exactly as it does today. The
only honest way to move that code is to move it WITHOUT changing it and then show
that the picture is identical - not to eyeball a screenshot and call it the same.

So: snapshot before the change, snapshot after, and diff. A fingerprint is the
scatter's own markup (hashed), plus the point / row / rail counts, plus every
disclosure line under the chart, captured across a spread of control combinations.
If any of those move, the refactor was not a pure move and the diff says which case
and which part.

USAGE
-----
    python tools/studies_parity_snap.py --out baseline.json      # before
    ... make the change ...
    python tools/studies_parity_snap.py --compare baseline.json  # after

    python tools/studies_parity_snap.py --selftest               # is the fingerprint
                                                                 # even deterministic?

--selftest renders every case TWICE in one boot and checks the two fingerprints
match. Run it before trusting a baseline: if the markup carries anything random,
a hash comparison would produce false alarms rather than catching real drift.

WHAT IT DOES NOT COVER - read this before trusting an IDENTICAL
-------------------------------------------------------------
* Only the STUDIES board on the old tab: every case forces cmpMode='research'
  and augurSub='cmp'. RUNBOARD, PICK RUNS, BY STRATEGY and FEATURE BOARD are not
  exercised, so IDENTICAL does not mean 'the old tab is unchanged'.
* Only ONE svg per case - whichever carries the plotted marks, else the largest.
  Page chrome outside that element is not hashed.
* The disclosure lines are found by a text heuristic, not by an attribute: the
  board does not tag them, so this looks for short paragraphs that read like a
  disclosure. It will catch wording changes in those lines; it is not a contract.

Exit codes: 0 pass / identical, 1 a real difference, 2 inconclusive (no Chrome).
No Firebase sign-in is needed; the studies registry is static data in index.html.
"""
import argparse
import hashlib
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading

PASS, FAIL, INCONCLUSIVE = 0, 1, 2
SNAP_FILENAME = '_studies_snap.html'

# A spread wide enough that a broken extraction shows up somewhere: both SHOW modes,
# every profit stage, both evidence levels that draw points, a family filter, each
# chart type, and a min-trades floor.
CASES = [
    ('default',        {}),
    ('configs',        {'resLvl': 'valid', 'resShow': 'configs', 'resCfgRun': ['306']}),
    ('configs-wf',     {'resLvl': 'valid', 'resShow': 'configs', 'resCfgRun': ['306'], 'resSegs': ['wf']}),
    ('configs-lb',     {'resLvl': 'valid', 'resShow': 'configs', 'resCfgRun': ['306'], 'resSegs': ['lb']}),
    ('runs-is',        {'resLvl': 'valid', 'resShow': 'runs', 'resSegs': ['is']}),
    ('fam-NOISE',      {'resFilt': '{"fam":["NOISE"]}'}),
    ('fam-ORB-cfg',    {'resFilt': '{"fam":["ORB"]}', 'resShow': 'configs'}),
    ('lvl-sweeps',     {'resLvl': 'sweep'}),
    ('lvl-valid',      {'resLvl': 'valid'}),
    ('axis-evr-rpy',   {'resAxis': 'evr', 'resXAxis': 'rpy'}),
    ('axis-mar-ddr',   {'resAxis': 'mar', 'resXAxis': 'ddr'}),
    ('mintrd',         {'resLvl': 'valid', 'resShow': 'configs', 'resCfgRun': ['306'], 'resMinTrd': 30}),
    ('chart-parallel', {'resChart': 'parallel'}),
    ('chart-radar',    {'resChart': 'radar'}),
    ('chart-lattice',  {'resChart': 'lattice'}),
    ('split-run',      {'resLvl': 'valid', 'resShow': 'configs', 'resCfgRun': ['306'], 'resSplitRun': True}),
]

SNAP_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>studies parity snap</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html" style="width:1400px;height:900px;border:0"></iframe>
<pre id="o"></pre>
<script>
var CASES = __CASES__, TWICE = __TWICE__, FIX = __FIX__;
(function(){
  var reported=false;
  function norm(t){ return String(t||'').replace(/\\s+/g,' ').trim(); }
  function shot(w,d,pref){
    var r={};
    // WITHOUT A RUN IN HISTORY the runs and 1E-configs views have nothing to plot, so
    //   every SHOW and STAGE case renders the same static-registry picture and the
    //   fingerprint cannot tell them apart. One real captured run is injected, and its
    //   whole document is put where the configs view looks for it, so those paths draw.
    var seed = FIX ? ("var F="+JSON.stringify(FIX)+";"
      +"var doc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(F)):F;"
      +"runHistory=[doc];window._runFull={};window._runFull[String(F.id)]=doc;"
      +"window._runCfg={};window._runCfg[String(F.id)]=doc;window._runHydrating={};") : "";
    r.call=w.eval("(function(){try{"
      +"localStorage.setItem('augurPrefs',"+JSON.stringify(JSON.stringify(pref))+");"
      +seed
      +"activeTab='augur';augurSub='cmp';renderApp();return 'OK';"
      +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
    r.points=d.querySelectorAll('[data-repoint]').length;
    r.rows=d.querySelectorAll('tr[data-rerow]').length;
    r.rail=d.querySelectorAll('[data-refam]').length;
    // the chart itself: whichever svg actually carries the plotted marks, else the
    //   biggest one on the page (parallel / radar / lattice do not use data-repoint).
    var svgs=[].slice.call(d.querySelectorAll('svg'));
    var chart=null;
    for(var i=0;i<svgs.length;i++){ if(svgs[i].querySelector('[data-repoint]')){chart=svgs[i];break;} }
    if(!chart){ var best=-1; svgs.forEach(function(s){var n=s.querySelectorAll('*').length; if(n>best){best=n;chart=s;} }); }
    r.svgNodes=chart?chart.querySelectorAll('*').length:0;
    r.svgMarkup=chart?norm(chart.outerHTML):'';
    // every honesty line under the chart, in order
    var notes=[];
    // the board does not tag its honesty lines, so they are found by what they say.
    //   A wording change shows up as a diff, which is the point; this is a heuristic,
    //   not a contract with the markup.
    [].forEach.call(d.querySelectorAll('div,span'),function(n){
      if(n.children.length)return;
      var t=norm(n.textContent);
      if(t.length>40&&t.length<600&&/not on this chart|no configuration records|judged on|omitted|minimum|contributed/i.test(t))notes.push(t); });
    r.notes=notes.slice(0,12);
    return r;
  }
  function report(why){
    if(reported)return; reported=true;
    var out={why:why,cases:{}};
    try{
      var w=document.getElementById('f').contentWindow, d=w.document;
      out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
      for(var i=0;i<CASES.length;i++){
        var nm=CASES[i][0], pref=JSON.parse(JSON.stringify(CASES[i][1]));
        pref.cmpMode='research';
        var a=shot(w,d,pref);
        if(TWICE){ var b=shot(w,d,JSON.parse(JSON.stringify(pref))); a.stable=(a.svgMarkup===b.svgMarkup&&a.points===b.points); }
        out.cases[nm]=a;
      }
    }catch(e){out.err=String(e&&e.stack?e.stack:e);}
    document.getElementById('o').textContent='STUDIESSNAP: '+JSON.stringify(out);
  }
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){report('load');},3500);});
  setTimeout(function(){report('backstop');},60000);
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


def render(twice):
    """Boot index.html headlessly and return the raw snapshot dict, or None."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    chrome = find_chrome()
    if not chrome:
        return None
    pdir = os.path.join(root, '_probe')
    os.makedirs(pdir, exist_ok=True)
    ppath = os.path.join(pdir, SNAP_FILENAME)
    with open(ppath, 'w', encoding='utf-8') as f:
        fix = None
        fpath = os.path.join(root, 'tools', 'fixtures', 'run_report.json')
        if os.path.isfile(fpath):
            try:
                fix = json.load(open(fpath, encoding='utf-8'))
            except Exception:
                fix = None
        f.write(SNAP_HTML.replace('__CASES__', json.dumps(CASES))
                         .replace('__TWICE__', 'true' if twice else 'false')
                         .replace('__FIX__', json.dumps(fix)))
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(root))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = 'http://127.0.0.1:%d/_probe/%s' % (port, SNAP_FILENAME)
    try:
        with tempfile.TemporaryDirectory() as ud:
            out = subprocess.run(
                [chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
                 '--hide-scrollbars', '--virtual-time-budget=70000',
                 '--user-data-dir=' + ud, '--dump-dom', url],
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                timeout=180).stdout or ''
    except Exception:
        return None
    finally:
        httpd.shutdown()
        try:
            os.remove(ppath)
            os.rmdir(pdir)
        except OSError:
            pass
    i = out.find('STUDIESSNAP: ')
    if i < 0:
        return None
    blob = out[i + len('STUDIESSNAP: '):]
    j = blob.find('</pre>')
    if j >= 0:
        blob = blob[:j]
    try:
        return json.loads(blob.replace('&quot;', '"').replace('&amp;', '&')
                              .replace('&lt;', '<').replace('&gt;', '>'))
    except Exception:
        try:
            return json.loads(blob)
        except Exception:
            return None


def fingerprint(data):
    """Hash the heavy markup so a saved baseline stays small and diffs stay readable."""
    fp = {'VERSION': data.get('VERSION'), 'cases': {}}
    for nm, c in sorted((data.get('cases') or {}).items()):
        fp['cases'][nm] = {
            'call': c.get('call'),
            'points': c.get('points'),
            'rows': c.get('rows'),
            'rail': c.get('rail'),
            'svgNodes': c.get('svgNodes'),
            'svgHash': hashlib.sha256((c.get('svgMarkup') or '').encode('utf-8')).hexdigest()[:16],
            'notes': c.get('notes') or [],
            'stable': c.get('stable'),
        }
    return fp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out')
    ap.add_argument('--compare')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    data = render(twice=args.selftest)
    if data is None:
        print('STUDIES SNAP: INCONCLUSIVE (no chrome, or the page did not report)')
        return INCONCLUSIVE
    if data.get('err'):
        print('STUDIES SNAP: INCONCLUSIVE (%s)' % str(data['err'])[:200])
        return INCONCLUSIVE
    fp = fingerprint(data)

    threw = [n for n, c in fp['cases'].items() if c['call'] != 'OK']
    if threw:
        print('STUDIES SNAP: FAIL -- these cases threw: %s' % ', '.join(sorted(threw)))
        for n in sorted(threw):
            print('  %-16s %s' % (n, str(fp['cases'][n]['call'])[:220]))
        return FAIL

    if args.selftest:
        unstable = [n for n, c in fp['cases'].items() if c.get('stable') is False]
        empty = [n for n, c in fp['cases'].items() if not c['svgNodes']]
        print('STUDIES SNAP SELFTEST: VERSION=%s, %d cases' % (fp['VERSION'], len(fp['cases'])))
        for n, c in sorted(fp['cases'].items()):
            print('  %-16s points=%-5s rows=%-5s svgNodes=%-6s %s'
                  % (n, c['points'], c['rows'], c['svgNodes'],
                     'stable' if c.get('stable') else 'NOT STABLE'))
        if unstable:
            print('FAIL -- the fingerprint is not deterministic for: %s' % ', '.join(sorted(unstable)))
            print('       a hash baseline would raise false alarms; fix the fingerprint first.')
            return FAIL
        if empty:
            print('  (note: no chart markup captured for: %s)' % ', '.join(sorted(empty)))
        print('STUDIES SNAP SELFTEST: PASS -- fingerprints are reproducible')
        return PASS

    if args.compare:
        try:
            base = json.load(open(args.compare, encoding='utf-8'))
        except Exception as e:
            print('STUDIES SNAP: INCONCLUSIVE (cannot read baseline %s: %s)' % (args.compare, e))
            return INCONCLUSIVE
        diffs = []
        names = sorted(set(base.get('cases', {})) | set(fp['cases']))
        for n in names:
            b, a = base.get('cases', {}).get(n), fp['cases'].get(n)
            if b is None or a is None:
                diffs.append('%s: present in only one snapshot' % n)
                continue
            for k in ('points', 'rows', 'rail', 'svgNodes', 'svgHash'):
                if b.get(k) != a.get(k):
                    diffs.append('%s: %s %r -> %r' % (n, k, b.get(k), a.get(k)))
            if (b.get('notes') or []) != (a.get('notes') or []):
                diffs.append('%s: the disclosure lines under the chart changed' % n)
        print('STUDIES SNAP: baseline %s vs now %s, %d cases'
              % (base.get('VERSION'), fp['VERSION'], len(names)))
        if diffs:
            print('STUDIES SNAP: DIFFERS -- the chart is not what it was:')
            for d in diffs[:40]:
                print('  - ' + d)
            return FAIL
        print('STUDIES SNAP: IDENTICAL -- every case draws exactly what it drew before')
        return PASS

    # default under _probe/ so a snapshot never litters the repo root
    out = args.out
    if not out:
        d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '_probe')
        os.makedirs(d, exist_ok=True)
        out = os.path.join(d, 'studies_parity_baseline.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(fp, f, indent=1, sort_keys=True)
    print('STUDIES SNAP: wrote %s (VERSION=%s, %d cases)' % (out, fp['VERSION'], len(fp['cases'])))
    for n, c in sorted(fp['cases'].items()):
        print('  %-16s points=%-5s rows=%-5s svgNodes=%-6s notes=%d'
              % (n, c['points'], c['rows'], c['svgNodes'], len(c['notes'])))
    return PASS


if __name__ == '__main__':
    sys.exit(main())
