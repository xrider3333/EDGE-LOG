#!/usr/bin/env python3
"""
tools/cmp2_render_probe.py -- render gate for COMPARE beta (augurSub==='cmp2').

WHY THIS EXISTS
---------------
tools/preflight_boot.py proves index.html BOOTS. It never enters the new COMPARE-beta
tab (the "COMPARE \u03b2" LEADERBOARD shipped 2026-09-08), so a crash inside that branch
of renderApp -- or inside its handler wiring -- would ship green through every existing
gate. This is the same lesson studies_render_probe.py / paper_render_probe.py /
report_render_probe.py already encode for their own views, applied to cmp2.

WHAT IT DOES
------------
Serves the repo over loopback, loads index.html in an iframe (like every other render
probe here), then -- inside the iframe's own global scope, where index.html's
top-level `let`/function bindings live -- forces the cmp2 tab and re-renders it for a
handful of states:

    activeTab='augur'; augurSub='cmp2'; renderApp();

with `runHistory`, `window._c2Open` and the `augurPrefs` localStorage doc (c2Screen /
c2Rank / c2Stage) set up per case first. Injecting a real run uses the exact
normalisation report_render_probe.py uses for the same fixture (tools/fixtures/
run_report.json, run #306) -- `_bookUnitsOnRead(_isoTs(doc))` -- so it reads to the
LEADERBOARD exactly as a live Firestore-synced run would.

WHAT IT ASSERTS, per case
--------------------------
  empty            -- no uncaught error, no console.error, body text says NO RUNS YET,
                       and the RANK ON / STAGE segmented controls still exist (4 + 3
                       [data-c2rank]/[data-c2stage] spans) even with zero runs.
  fixture-lb       -- no errors, >=1 [data-c2fam] family row, the champion's .c2-big
                       is non-empty (a number or the em dash), and .c2-note mentions
                       "1 strateg...".
  fixture-expand   -- pre-seeding window._c2Open with the family key read back from
                       fixture-lb reproduces a user's click: >=1 .c2-row.sub[data-c2run]
                       and >=1 [data-c2add] chip appear.
  stages           -- IS / WF / LB all render without throwing (values may honestly be
                       the dash -- this run fixture is thin on some stages).
  placeholders     -- the COMPARE and EXPLORE screens (phases 3/4, not built yet) each
                       show a .c2-hold placeholder card and a [data-c2gocmp] escape
                       hatch back to the old tab, with no errors.

No Firebase sign-in is needed; cmp2 reads only from the global runHistory array. cmp2's
render path is synchronous string-building (no deferred chart draw / no async render
step), so unlike report_render_probe.py this probe does not need to poll for settle --
every case is rendered and sampled back to back inside one script tick.

Exit codes match preflight_boot.py: 0 PASS, 1 FAIL, 2 INCONCLUSIVE.

Usage:
  python tools/cmp2_render_probe.py                # gates this repo's index.html
  python tools/cmp2_render_probe.py --file X.html   # gates X as if it were index.html

Stdlib only, plus a subprocess call to local Chrome.
"""
import argparse
import http.server
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading

PASS, FAIL, INCONCLUSIVE = 0, 1, 2
PROBE_FILENAME = '_cmp2_probe.html'
N_CASES = 5

PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>cmp2 probe</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html" style="width:1400px;height:900px;border:0"></iframe>
<pre id="o"></pre>
<script>
var FIX = __FIX__;
(function(){
  var reported=false;
  function hook(w){
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
  function report(why){
    if(reported)return; reported=true;
    var out={why:why,cases:{}};
    try{
      var fr=document.getElementById('f'), w=fr.contentWindow, d=fr.contentDocument;
      var sink=hook(w);
      out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
      out.renderAppType=w.eval('typeof renderApp');
      if(out.renderAppType!=='function'){out.why='noboot';
        document.getElementById('o').textContent='CMP2PROBE: '+JSON.stringify(out);return;}

      function doRender(prefs, winCode){
        sink.errors.length=0; sink.uncaught.length=0;
        var call;
        try{
          call=w.eval("(function(){try{"
            +"localStorage.setItem('augurPrefs',"+JSON.stringify(JSON.stringify(prefs))+");"
            +winCode
            +"activeTab='augur';augurSub='cmp2';renderApp();return 'OK';"
            +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
        }catch(e){call='ERR '+(e&&e.stack?e.stack:e);}
        return call;
      }
      function snap(name, call){
        var r={call:call,errors:sink.errors.slice(0,10),uncaught:sink.uncaught.slice(0,10)};
        out.cases[name]=r;
        return r;
      }
      var EMPTY_WIN="runHistory=[];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";
      var FIX_WIN="var F="+JSON.stringify(FIX)+";var doc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(F)):F;"
        +"runHistory=[doc];window._runFull={};window._runFullOrder=[];window._runHydrating={};window._c2Open=new Set();";

      // ── case 1: empty ──────────────────────────────────────────────────────────
      (function(){
        var call=doRender({c2Screen:'lead'}, EMPTY_WIN);
        var r=snap('empty', call);
        var bodyTxt=(d.body&&(d.body.innerText||d.body.textContent))||'';
        r.hasNoRuns=bodyTxt.indexOf('NO RUNS YET')>=0;
        r.rankCount=d.querySelectorAll('[data-c2rank]').length;
        r.stageCount=d.querySelectorAll('[data-c2stage]').length;
      })();

      // ── case 2: fixture-lb ─────────────────────────────────────────────────────
      var famKey=null;
      (function(){
        var call=doRender({c2Screen:'lead',c2Rank:'rpy',c2Stage:'lb'}, FIX_WIN);
        var r=snap('fixture-lb', call);
        var famRows=d.querySelectorAll('.c2-row[data-c2fam]');
        r.famRows=famRows.length;
        var champBig=famRows.length?famRows[0].querySelector('.c2-big'):null;
        r.champBigText=champBig?(champBig.textContent||'').trim():null;
        var note=d.querySelector('.c2-note');
        r.noteText=note?(note.textContent||'').trim():null;
        if(famRows.length)famKey=decodeURIComponent(famRows[0].getAttribute('data-c2fam'));
      })();

      // ── case 3: fixture-expand ─────────────────────────────────────────────────
      (function(){
        var wc=FIX_WIN+"window._c2Open=new Set(["+JSON.stringify(famKey)+"]);";
        var call=doRender({c2Screen:'lead',c2Rank:'rpy',c2Stage:'lb'}, wc);
        var r=snap('fixture-expand', call);
        r.famKey=famKey;
        r.subRows=d.querySelectorAll('.c2-row.sub[data-c2run]').length;
        r.addChips=d.querySelectorAll('[data-c2add]').length;
      })();

      // ── case 4: stages (IS / WF / LB) ─────────────────────────────────────────
      (function(){
        var stages=['is','wf','lb'], values={}, anyErr=null, allErrors=[], allUncaught=[];
        stages.forEach(function(st){
          var call=doRender({c2Screen:'lead',c2Rank:'rpy',c2Stage:st}, FIX_WIN);
          var famRows=d.querySelectorAll('.c2-row[data-c2fam]');
          var big=famRows.length?famRows[0].querySelector('.c2-big'):null;
          values[st]={call:call, big:big?(big.textContent||'').trim():null};
          if(call!=='OK'&&!anyErr)anyErr=st+': '+call;
          allErrors=allErrors.concat(sink.errors);
          allUncaught=allUncaught.concat(sink.uncaught);
        });
        var r=snap('stages', anyErr?('ERR '+anyErr):'OK');
        r.values=values;
        r.errors=allErrors.slice(0,10);
        r.uncaught=allUncaught.slice(0,10);
      })();

      // ── case 5: placeholders (cmp / explore) ──────────────────────────────────
      (function(){
        var screens=['cmp','explore'], per={};
        screens.forEach(function(scr){
          var call=doRender({c2Screen:scr}, FIX_WIN);
          per[scr]={call:call,
            hold:!!d.querySelector('.c2-hold'),
            gocmp:!!d.querySelector('[data-c2gocmp]'),
            errors:sink.errors.slice(0,5),
            uncaught:sink.uncaught.slice(0,5)};
        });
        var r=snap('placeholders', (per.cmp.call==='OK'&&per.explore.call==='OK')?'OK':'ERR');
        r.per=per;
      })();

    }catch(e){out.err=String(e&&e.stack?e.stack:e);}
    document.getElementById('o').textContent='CMP2PROBE: '+JSON.stringify(out);
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


def clean(ppath, pdir):
    try:
        os.remove(ppath)
        os.rmdir(pdir)
    except OSError:
        pass


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--file', default=None,
                    help='gate this file as if it were index.html (self-test / diff use)')
    ap.add_argument('--fixture', default=None, help='override the run fixture path')
    args = ap.parse_args(argv)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alt_index = os.path.abspath(args.file) if args.file else None
    if alt_index and not os.path.isfile(alt_index):
        print('CMP2 PROBE: INCONCLUSIVE (--file not found: %s)' % alt_index)
        return INCONCLUSIVE

    fix_path = args.fixture or os.path.join(root, 'tools', 'fixtures', 'run_report.json')
    if not os.path.isfile(fix_path):
        print('CMP2 PROBE: INCONCLUSIVE (fixture missing: %s)' % fix_path)
        return INCONCLUSIVE
    try:
        fixture = json.load(io.open(fix_path, encoding='utf-8'))
    except Exception as e:
        print('CMP2 PROBE: INCONCLUSIVE (fixture unreadable: %s)' % e)
        return INCONCLUSIVE

    chrome = find_chrome()
    if not chrome:
        print('CMP2 PROBE: INCONCLUSIVE (no chrome found)')
        return INCONCLUSIVE

    pdir = os.path.join(root, '_probe')
    os.makedirs(pdir, exist_ok=True)
    ppath = os.path.join(pdir, PROBE_FILENAME)
    html = PROBE_HTML.replace('__FIX__', json.dumps(fixture))
    with open(ppath, 'w', encoding='utf-8') as f:
        f.write(html)

    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(root, alt_index))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = 'http://127.0.0.1:%d/_probe/%s' % (port, PROBE_FILENAME)
    try:
        with tempfile.TemporaryDirectory() as ud:
            cargs = [chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
                     '--hide-scrollbars', '--virtual-time-budget=30000',
                     '--user-data-dir=' + ud, '--dump-dom', url]
            try:
                out = subprocess.run(cargs, capture_output=True, text=True, encoding='utf-8',
                                     errors='replace', timeout=120).stdout or ''
            except subprocess.TimeoutExpired:
                print('CMP2 PROBE: INCONCLUSIVE (chrome timed out)')
                return INCONCLUSIVE
    finally:
        httpd.shutdown()
        clean(ppath, pdir)

    m = re.search(r'CMP2PROBE: (\{.*?\})\s*</pre>', out, re.S)
    if not m:
        print('CMP2 PROBE: INCONCLUSIVE (probe produced no reading)')
        return INCONCLUSIVE
    try:
        data = json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&')
                          .replace('&lt;', '<').replace('&gt;', '>'))
    except Exception as e:
        print('CMP2 PROBE: INCONCLUSIVE (unreadable readout: %s)' % e)
        return INCONCLUSIVE

    if data.get('why') == 'noboot':
        print('CMP2 PROBE: INCONCLUSIVE (app did not boot; see preflight_boot)')
        return INCONCLUSIVE
    if data.get('err'):
        print('CMP2 PROBE: INCONCLUSIVE (probe threw: %s)' % data['err'])
        return INCONCLUSIVE

    cases = data.get('cases') or {}
    if len(cases) != N_CASES:
        print('CMP2 PROBE: INCONCLUSIVE (only %d of %d cases reported, why=%s)'
              % (len(cases), N_CASES, data.get('why')))
        return INCONCLUSIVE

    print('CMP2 PROBE: version %s, %d cases' % (data.get('VERSION'), len(cases)))
    bad = []

    def fail(msg):
        bad.append(msg)

    def line(name, ok, detail):
        print('  %-16s %-4s %s' % (name, 'OK' if ok else 'FAIL', detail))

    # case 1: empty
    r = cases.get('empty', {})
    ok = (r.get('call') == 'OK' and not r.get('errors') and not r.get('uncaught')
          and r.get('hasNoRuns') and r.get('rankCount') == 4 and r.get('stageCount') == 3)
    line('empty', ok, 'call=%s NO_RUNS_YET=%s rank=%s stage=%s errors=%s uncaught=%s'
         % (r.get('call'), r.get('hasNoRuns'), r.get('rankCount'), r.get('stageCount'),
            r.get('errors'), r.get('uncaught')))
    if not ok:
        if r.get('call') != 'OK':
            fail('empty: renderApp threw -- %s' % str(r.get('call'))[:300])
        if r.get('errors'):
            fail('empty: console.error -- %s' % r['errors'][0][:200])
        if r.get('uncaught'):
            fail('empty: uncaught -- %s' % r['uncaught'][0][:200])
        if not r.get('hasNoRuns'):
            fail('empty: body text does not contain NO RUNS YET')
        if r.get('rankCount') != 4:
            fail('empty: expected 4 [data-c2rank] spans, got %s' % r.get('rankCount'))
        if r.get('stageCount') != 3:
            fail('empty: expected 3 [data-c2stage] spans, got %s' % r.get('stageCount'))

    # case 2: fixture-lb
    r = cases.get('fixture-lb', {})
    note_ok = bool(r.get('noteText')) and ('1 strateg' in r['noteText'])
    ok = (r.get('call') == 'OK' and not r.get('errors') and not r.get('uncaught')
          and (r.get('famRows') or 0) >= 1 and r.get('champBigText') and note_ok)
    line('fixture-lb', ok, 'call=%s famRows=%s champBig=%r note=%r errors=%s uncaught=%s'
         % (r.get('call'), r.get('famRows'), r.get('champBigText'), r.get('noteText'),
            r.get('errors'), r.get('uncaught')))
    if not ok:
        if r.get('call') != 'OK':
            fail('fixture-lb: renderApp threw -- %s' % str(r.get('call'))[:300])
        if r.get('errors'):
            fail('fixture-lb: console.error -- %s' % r['errors'][0][:200])
        if r.get('uncaught'):
            fail('fixture-lb: uncaught -- %s' % r['uncaught'][0][:200])
        if (r.get('famRows') or 0) < 1:
            fail('fixture-lb: no [data-c2fam] family rows rendered')
        if not r.get('champBigText'):
            fail('fixture-lb: champion .c2-big is empty')
        if not note_ok:
            fail('fixture-lb: .c2-note does not mention "1 strateg..." (got %r)' % r.get('noteText'))

    # case 3: fixture-expand
    r = cases.get('fixture-expand', {})
    ok = (r.get('call') == 'OK' and not r.get('errors') and not r.get('uncaught')
          and (r.get('subRows') or 0) >= 1 and (r.get('addChips') or 0) >= 1)
    line('fixture-expand', ok, 'call=%s famKey=%r subRows=%s addChips=%s errors=%s uncaught=%s'
         % (r.get('call'), r.get('famKey'), r.get('subRows'), r.get('addChips'),
            r.get('errors'), r.get('uncaught')))
    if not ok:
        if r.get('call') != 'OK':
            fail('fixture-expand: renderApp threw -- %s' % str(r.get('call'))[:300])
        if r.get('errors'):
            fail('fixture-expand: console.error -- %s' % r['errors'][0][:200])
        if r.get('uncaught'):
            fail('fixture-expand: uncaught -- %s' % r['uncaught'][0][:200])
        if not r.get('famKey'):
            fail('fixture-expand: no family key was available from fixture-lb')
        if (r.get('subRows') or 0) < 1:
            fail('fixture-expand: no .c2-row.sub[data-c2run] rendered when the family was pre-opened')
        if (r.get('addChips') or 0) < 1:
            fail('fixture-expand: no [data-c2add] chip rendered')

    # case 4: stages
    r = cases.get('stages', {})
    values = r.get('values') or {}
    stage_ok = (r.get('call') == 'OK' and not r.get('errors') and not r.get('uncaught')
                and all((values.get(s) or {}).get('call') == 'OK' for s in ('is', 'wf', 'lb')))
    line('stages', stage_ok, 'call=%s IS=%r WF=%r LB=%r errors=%s uncaught=%s'
         % (r.get('call'),
            (values.get('is') or {}).get('big'), (values.get('wf') or {}).get('big'),
            (values.get('lb') or {}).get('big'), r.get('errors'), r.get('uncaught')))
    if not stage_ok:
        if r.get('call') != 'OK':
            fail('stages: %s' % r.get('call'))
        if r.get('errors'):
            fail('stages: console.error -- %s' % r['errors'][0][:200])
        if r.get('uncaught'):
            fail('stages: uncaught -- %s' % r['uncaught'][0][:200])
        for s in ('is', 'wf', 'lb'):
            v = values.get(s) or {}
            if v.get('call') != 'OK':
                fail('stages: %s stage threw -- %s' % (s, str(v.get('call'))[:300]))

    # case 5: placeholders
    r = cases.get('placeholders', {})
    per = r.get('per') or {}
    ph_ok = True
    for scr in ('cmp', 'explore'):
        p = per.get(scr) or {}
        if not (p.get('call') == 'OK' and p.get('hold') and p.get('gocmp')
                and not p.get('errors') and not p.get('uncaught')):
            ph_ok = False
    line('placeholders', ph_ok, 'cmp=%s explore=%s'
         % ({k: v for k, v in (per.get('cmp') or {}).items() if k != 'per'},
            {k: v for k, v in (per.get('explore') or {}).items() if k != 'per'}))
    if not ph_ok:
        for scr in ('cmp', 'explore'):
            p = per.get(scr) or {}
            if p.get('call') != 'OK':
                fail('placeholders: %s screen renderApp threw -- %s' % (scr, str(p.get('call'))[:300]))
            if p.get('errors'):
                fail('placeholders: %s console.error -- %s' % (scr, p['errors'][0][:200]))
            if p.get('uncaught'):
                fail('placeholders: %s uncaught -- %s' % (scr, p['uncaught'][0][:200]))
            if p.get('call') == 'OK' and not p.get('hold'):
                fail('placeholders: %s screen has no .c2-hold card' % scr)
            if p.get('call') == 'OK' and not p.get('gocmp'):
                fail('placeholders: %s screen has no [data-c2gocmp] escape hatch' % scr)

    if bad:
        print('CMP2 PROBE: FAIL')
        for b in bad:
            print('  - ' + b)
        return FAIL
    print('CMP2 PROBE: PASS (VERSION=%s, %d cases)' % (data.get('VERSION'), len(cases)))
    return PASS


if __name__ == '__main__':
    sys.exit(main())
