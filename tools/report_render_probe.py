#!/usr/bin/env python3
"""
tools/report_render_probe.py -- render gate for the RESULTS run report (runDetail).

WHY THIS EXISTS
---------------
tools/preflight_boot.py proves index.html BOOTS. The STUDIES and PAPER probes prove two
views draw. None of them ever opened a RUN REPORT, and the report is the view that has
shipped broken most often behind a green boot gate:

  v73.367  ReferenceError: _reXNm is not defined   (a caption pointed at another
                                                     function's consts)
  v73.442  TypeError: undefined is not a function   (an _hRow on the GATE / TILT /
                                                     HYBRID tables built without its
                                                     heat getter)
  v73.443  _matrixTbl: cannot read map of undefined (the hotfix's own EV R row sat
                                                     outside the row list)

Each one blanked EVERY run report on the live site until a hotfix, because runDetail's
own try/catch swallows the throw, logs "runDetail failed for run ..." and paints the
"This run's detail couldn't render" card instead. The app survives; the report is gone.

WHAT IT DOES
------------
Serves the repo over loopback, loads index.html in an iframe exactly as the boot gate
does, then injects ONE real saved run document (tools/fixtures/run_report.json -- run
306, a NOISE validate run carrying gate_validate with 20 candidates / 10 tilts / 5
hybrids, captured by tools/capture_run_fixture.py) into runHistory the same way the
Firestore listener would, selects it (activeTab='augur', augurSub='runs',
augurRunSel=<its id>) and calls renderApp() -- the same path a click on a PAST RUNS
row takes. No Firebase sign-in is needed.

Before each render it hooks the iframe's console.error, window 'error' and
'unhandledrejection' events, so nothing runDetail's try/catch swallows, and nothing
that escapes a deferred chart draw, can hide.

WHAT IT ASSERTS, per case
-------------------------
  * renderApp returned without throwing
  * NO console.error containing "runDetail failed"
  * NO uncaught exception / unhandled rejection during or shortly after the render
  * #res-detail exists, does not carry the "couldn't render" card, and is not tiny
  * the report names the fixture run

Cases cover the three REPORT COLUMNS layouts, since each is a different template path.

Exit codes match preflight_boot.py: 0 PASS, 1 FAIL, 2 INCONCLUSIVE (never blocks).

Usage:
  python tools/report_render_probe.py                # gates this repo's index.html
  python tools/report_render_probe.py --file X.html  # gates X as if it were index.html
  python tools/report_render_probe.py --selftest     # proves the gate itself still works:
                                                     # pulls every KNOWN_BAD build out of git
                                                     # history and asserts FAIL on each, then
                                                     # asserts PASS on the current index.html

THE SELF-TEST. A gate that watches for one string can go blind without anyone noticing --
a renamed log line, a fixture that no longer reaches the tables, a hook that stopped
firing -- and it would keep printing PASS. So the gate carries the builds it was written
to catch and re-catches them on demand. wt.py ship runs --selftest whenever this file or
the fixture changes.

Stdlib only, plus a subprocess call to local Chrome. Runs in well under 20s.
"""
import argparse
import http.server
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

PASS, FAIL, INCONCLUSIVE = 0, 1, 2

# name -> {prefs, win}: prefs land in localStorage augurPrefs (and APREF), win on the
# iframe window before renderApp.
CASES = [
    ('cols-3', {'prefs': {'repCols': '3'}, 'win': {}}),
    ('cols-2', {'prefs': {'repCols': '2'}, 'win': {}}),
    ('cols-1', {'prefs': {'repCols': '1'}, 'win': {}}),
]

# Builds this gate exists to catch. Each is a commit on main whose index.html blanked every
# run report on the live site; --selftest asserts the gate still FAILS on all of them.
# (commit, VERSION, what was wrong)
KNOWN_BAD = [
    ('aa7537e2c39f6ebeb42f23fadb83dfbccb0c1790', '73.367',
     "ReferenceError: _reXNm is not defined -- the RISK MAP x caption pointed at the RANKINGS "
     "scatter's axis consts, which live in a different function"),
    ('db1f5e9ec010da8a4d26fcbaaeccebbf9557e81e', '73.442',
     "TypeError: undefined is not a function -- the EV R row on the GATE / TILT / HYBRID tables "
     "was built without the heat getter every row there must carry"),
    ('19e4fc86e4ce174402689b5bf817b54eef2ab031', '73.443',
     "TypeError: cannot read map of undefined -- the hotfix's own EV R row sat one line past the "
     "end of the reward-risk row list, a group with no rows"),
]

PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>report probe</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html" style="width:1500px;height:1000px;border:0"></iframe>
<pre id="o"></pre>
<script>
var CASES=__CASES__, FIX=__FIX__;
(function(){
  var reported=false, out={cases:{}}, t0=Date.now();
  function finish(why){
    if(reported)return; reported=true;
    out.why=why; out.ms=Date.now()-t0;
    document.getElementById('o').textContent='REPORTPROBE: '+JSON.stringify(out);
  }
  function hook(w){
    // one shared sink; each case drains it before rendering
    if(w.__probeSink)return w.__probeSink;
    var sink=w.__probeSink={errors:[],uncaught:[]};
    var orig=w.console.error;
    w.console.error=function(){
      var parts=[];for(var i=0;i<arguments.length;i++){var a=arguments[i];
        parts.push(a&&a.stack?String(a.stack):String(a));}
      sink.errors.push(parts.join(' '));
      try{orig.apply(w.console,arguments);}catch(_){}
    };
    w.addEventListener('error',function(ev){
      sink.uncaught.push(String(ev&&ev.message||ev)+(ev&&ev.error&&ev.error.stack?' :: '+ev.error.stack:''));});
    w.addEventListener('unhandledrejection',function(ev){
      var r=ev&&ev.reason;sink.uncaught.push('unhandledrejection: '+(r&&r.stack?r.stack:String(r)));});
    return sink;
  }
  function runCase(i){
    if(i>=CASES.length){finish('done');return;}
    var nm=CASES[i][0], cfg=CASES[i][1], r={};
    var fr=document.getElementById('f'), w=fr.contentWindow, d=fr.contentDocument;
    var sink=hook(w);
    sink.errors.length=0; sink.uncaught.length=0;
    try{
      r.call=w.eval("(function(){try{"
        +"localStorage.setItem('augurPrefs',"+JSON.stringify(JSON.stringify(cfg.prefs||{}))+");"
        +"if(typeof APREF==='object'&&APREF){for(var k in APREF)delete APREF[k];"
        +"  var P="+JSON.stringify(cfg.prefs||{})+";for(var k2 in P)APREF[k2]=P[k2];}"
        +"var F="+JSON.stringify(FIX)+";"
        // the same normalisation the Firestore read paths apply
        +"var doc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(F)):F;"
        +"runHistory=[doc];window._runFull={};window._runFullOrder=[];window._runHydrating={};"
        +"var W="+JSON.stringify(cfg.win||{})+";for(var k3 in W)window[k3]=W[k3];"
        +"activeTab='augur';augurSub='runs';augurRunSel=String(doc.id);renderApp();return 'OK';"
        +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
    }catch(e){r.call='ERR '+(e&&e.stack?e.stack:e);}
    // deferred chart draws run on timers after the paint; give them a beat before sampling
    setTimeout(function(){
      try{
        var det=d.getElementById('res-detail');
        r.detail=!!det;
        r.detailLen=det?det.innerHTML.length:-1;
        var txt=det?(det.innerText||det.textContent||''):'';
        r.cantRender=/couldn.t render/i.test(txt);
        r.namesRun=txt.indexOf(String(FIX.id))>=0;
        r.appLen=(d.getElementById('app')||{innerHTML:''}).innerHTML.length;
        r.errors=sink.errors.slice(0,20);
        r.uncaught=sink.uncaught.slice(0,20);
      }catch(e){r.sampleErr=String(e&&e.stack?e.stack:e);}
      out.cases[nm]=r;
      runCase(i+1);
    },1200);
  }
  document.getElementById('f').addEventListener('load',function(){
    setTimeout(function(){
      try{var w=document.getElementById('f').contentWindow;
          out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
          out.renderApp=typeof w.renderApp;
          hook(w);}catch(e){out.err=String(e);}
      if(out.renderApp!=='function'){finish('noboot');return;}
      runCase(0);
    },2500);
  });
  setTimeout(function(){finish('backstop');},40000);
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


def make_handler(root, alt_index):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root, **kw)

        def do_GET(self):
            if alt_index and (self.path == '/index.html' or self.path.startswith('/index.html?')):
                try:
                    with open(alt_index, 'rb') as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except OSError as e:
                    self.send_error(500, str(e))
                return
            super().do_GET()

        def log_message(self, *a):
            pass
    return H


def selftest(fixture=None):
    """Exit 0 when the gate FAILS every KNOWN_BAD build and PASSES the current index.html;
    1 when any expectation breaks; 2 when git or a commit is unavailable (shallow clone)."""
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    t0 = time.time()
    tmpdir = tempfile.mkdtemp(prefix='reportprobe-selftest-')
    bad, results = [], []
    try:
        for commit, ver, why in KNOWN_BAD:
            path = os.path.join(tmpdir, 'index_%s.html' % ver.replace('.', '_'))
            try:
                r = subprocess.run(['git', '-C', root, 'show', commit + ':index.html'],
                                   capture_output=True, timeout=60)
            except Exception as e:
                print('SELFTEST: INCONCLUSIVE -- git unavailable: %s' % e)
                return INCONCLUSIVE
            if r.returncode != 0 or len(r.stdout) < 100000:
                print('SELFTEST: INCONCLUSIVE -- could not read %s:index.html from history '
                      '(%s)' % (commit, (r.stderr or b'').decode('utf-8', 'replace').strip()[:200]))
                return INCONCLUSIVE
            with open(path, 'wb') as f:
                f.write(r.stdout)
            print('-- known-bad build v%s (%s): expect FAIL' % (ver, commit))
            code = main(['--file', path] + (['--fixture', fixture] if fixture else []))
            results.append((ver, code))
            if code != FAIL:
                bad.append('v%s (%s) was NOT caught (exit %d) -- the gate has gone blind to: %s'
                           % (ver, commit, code, why))
        print('-- current index.html: expect PASS')
        code = main(['--fixture', fixture] if fixture else [])
        results.append(('current', code))
        if code != PASS:
            bad.append('current index.html did not PASS (exit %d)' % code)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    if bad:
        print('SELFTEST: FAIL (%.1fs)' % (time.time() - t0))
        for b in bad:
            print('  - ' + b)
        return FAIL
    print('SELFTEST: PASS -- gate caught %d/%d known-bad builds and passed the current one (%.1fs)'
          % (len(KNOWN_BAD), len(KNOWN_BAD), time.time() - t0))
    return PASS


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--file', default=None,
                    help='gate this file as if it were index.html (self-test use)')
    ap.add_argument('--fixture', default=None, help='override the run fixture path')
    ap.add_argument('--selftest', action='store_true',
                    help='assert FAIL on every KNOWN_BAD build from git history, then PASS on '
                         'the current index.html')
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest(args.fixture)
    t0 = time.time()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alt_index = os.path.abspath(args.file) if args.file else None
    if alt_index and not os.path.isfile(alt_index):
        print('REPORTPROBE: INCONCLUSIVE -- --file not found: %s' % alt_index)
        return INCONCLUSIVE
    fix_path = args.fixture or os.path.join(root, 'tools', 'fixtures', 'run_report.json')
    if not os.path.isfile(fix_path):
        print('REPORTPROBE: INCONCLUSIVE -- fixture missing: %s (capture one with '
              'tools/capture_run_fixture.py <run id>)' % fix_path)
        return INCONCLUSIVE
    chrome = find_chrome()
    if not chrome:
        print('REPORTPROBE: INCONCLUSIVE -- Chrome not found')
        return INCONCLUSIVE
    try:
        fixture = json.load(io.open(fix_path, encoding='utf-8'))
    except Exception as e:
        print('REPORTPROBE: INCONCLUSIVE -- fixture unreadable: %s' % e)
        return INCONCLUSIVE

    pdir = os.path.join(root, '_reportprobe')
    if not os.path.isdir(pdir):
        os.makedirs(pdir)
    ppath = os.path.join(pdir, 'probe.html')
    html = (PROBE_HTML
            .replace('__CASES__', json.dumps([[n, c] for n, c in CASES]))
            .replace('__FIX__', json.dumps(fixture)))
    io.open(ppath, 'w', encoding='utf-8').write(html)

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(root, alt_index))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    prof = tempfile.mkdtemp(prefix='reportprobe-')
    try:
        out = subprocess.run(
            [chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
             '--user-data-dir=' + prof, '--virtual-time-budget=45000',
             '--dump-dom', 'http://127.0.0.1:%d/_reportprobe/probe.html' % port],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=120).stdout
    except Exception as e:
        print('REPORTPROBE: INCONCLUSIVE -- chrome failed: %s' % e)
        return INCONCLUSIVE
    finally:
        srv.shutdown()
        try:
            os.remove(ppath)
            os.rmdir(pdir)
        except OSError:
            pass
        shutil.rmtree(prof, ignore_errors=True)

    m = re.search(r'REPORTPROBE: (\{.*?\})</pre>', out, re.S)
    if not m:
        print('REPORTPROBE: INCONCLUSIVE -- probe produced no readout')
        return INCONCLUSIVE
    try:
        data = json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&')
                          .replace('&lt;', '<').replace('&gt;', '>'))
    except Exception as e:
        print('REPORTPROBE: INCONCLUSIVE -- unreadable readout: %s' % e)
        return INCONCLUSIVE
    if os.environ.get('REPORTPROBE_DUMP'):
        io.open(os.path.join(root, '_reportprobe_dump.json'), 'w', encoding='utf-8').write(
            json.dumps(data, indent=1, ensure_ascii=False))

    elapsed = time.time() - t0
    if data.get('why') == 'noboot':
        # the boot gate owns this verdict; do not double-report it
        print('REPORTPROBE: INCONCLUSIVE -- app did not boot (renderApp=%s); see preflight_boot'
              % data.get('renderApp'))
        return INCONCLUSIVE
    if data.get('err'):
        print('REPORTPROBE: FAIL -- probe threw: %s' % data['err'])
        return FAIL

    fails, notes, cases = [], [], data.get('cases') or {}
    if len(cases) != len(CASES):
        fails.append('only %d of %d cases reported (why=%s)' % (len(cases), len(CASES), data.get('why')))
    for nm, r in cases.items():
        if r.get('call') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (nm, r.get('call')))
            continue
        if r.get('sampleErr'):
            fails.append('%s: could not read the rendered page -- %s' % (nm, r['sampleErr']))
            continue
        for e in r.get('errors') or []:
            if 'runDetail failed' in e:
                fails.append('%s: %s' % (nm, e.splitlines()[0][:300]))
            else:
                notes.append('%s: console.error: %s' % (nm, e.splitlines()[0][:200]))
        for e in r.get('uncaught') or []:
            fails.append('%s: uncaught -- %s' % (nm, e.splitlines()[0][:300]))
        if not r.get('detail'):
            fails.append('%s: no #res-detail card rendered at all' % nm)
            continue
        if r.get('cantRender'):
            fails.append("%s: the \"couldn't render\" fallback card is showing" % nm)
        if (r.get('detailLen') or 0) < 20000:
            fails.append('%s: report body is only %s chars' % (nm, r.get('detailLen')))
        if not r.get('namesRun'):
            fails.append('%s: report never names run %s' % (nm, fixture.get('id')))

    if fails:
        print('REPORTPROBE: FAIL (VERSION=%s, %.1fs)' % (data.get('VERSION'), elapsed))
        seen = set()
        for f in fails:
            if f not in seen:
                seen.add(f)
                print('  - ' + f)
        for n in notes[:8]:
            print('  note: ' + n)
        return FAIL
    print('REPORTPROBE: PASS (VERSION=%s, run %s, %d cases, report %s chars, %.1fs)'
          % (data.get('VERSION'), fixture.get('id'), len(cases),
             (cases.get('cols-3') or {}).get('detailLen'), elapsed))
    for n in notes[:8]:
        print('  note: ' + n)
    return PASS


if __name__ == '__main__':
    sys.exit(main())
