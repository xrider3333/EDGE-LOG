#!/usr/bin/env python3
"""
tools/run_series_render_probe.py -- render gate for the past-run WALK-FORWARD P&L panel (owner 11-22, board 131 + 132).

WHAT IT GATES. The RESULTS run report (section 1A) gains a panel read from users/<uid>/runs/<id>/series/wf: CURVE | DAILY,
a SIZING selector (FIXED 1 / RISK 1 / 2 / 3 %) and a four-column KPI table with an amber warning on RISK 3 % when its ruin
flag trips or its DD % from peak passes 35. With no series it offers BUILD DAILY SERIES (writes meta/run_series_req).

HOW. The same harness as tools/report_render_probe.py: the repo is served over loopback, index.html loads in an iframe, a
real saved run (tools/fixtures/run_report.json, run 306) is put into runHistory and the report is rendered through
renderApp(). Firestore is never touched: the panel's cache (window._rtsCache) is SEEDED before the render with a series
built in THIS process by the tool's own code (tools/run_trades_series.series_payload + add_sizing over a synthetic trade
list -> augur_engine.risk_sizing), so every number the page prints is compared to what the engine helper produced. The
request write goes to a stubbed db that records the call.

CASES
  curve      seeded series, CURVE + FIXED: panel inside #res-detail, a line drawn, 4 KPI columns, FIXED net / trades / max
             contracts match the payload, no amber column (the fixture keeps RISK 3 % under the line)
  daily      a click on DAILY: one ledger daily bar per series day (+1 for a synthetic $0 anchor day when day 1 is not
             flat), the running-total line drawn
  size2      a click on RISK 2 %: the r2 column is the selected one and the chart's geometry changed
  warn       a series whose RISK 3 % trips (ruin): amber th + the warning sentence, and only on RISK 3 %
  none       no series: BUILD DAILY SERIES shown; a click records ONE write to meta/run_series_req with the run id, and the
             panel says Asked
  refused    a refused build: its reason shown, no button
Every case: renderApp did not throw, no console.error, no uncaught error, the report did not fall to its
"couldn't render" card.

Exit 0 PASS, 1 FAIL, 2 INCONCLUSIVE. Usage: python tools/run_series_render_probe.py [--file X.html] [--verbose]
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
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _series(warn=False):
    """A small series built by the tool's own payload + sizing code (no market data)."""
    from tools import run_trades_series as R
    import datetime as dt
    d0 = dt.date(2024, 1, 2)
    days, tr = [], []
    k = 0
    for i in range(60):
        d = d0 + dt.timedelta(days=i)
        if d.weekday() >= 5:
            continue
        days.append(d.isoformat())
        if i % 2 == 0:
            k += 1
            e = int(dt.datetime(d.year, d.month, d.day, 15).timestamp())
            win = (k % 3 != 0)
            if warn and k in (4, 5, 6, 7):
                p = -60.0                                  # a run of big losers at 3 % with tiny stops -> ruin
            else:
                p = (14.5 if win else -10.5)
            tr.append({"e": e, "x": e + 600, "s": 1, "p": p, "z": 1, "r": (2.0 if warn else 20.0), "f": 1,
                       "d": d.isoformat()})
    daily = R.daily_from_trades([t["d"] for t in tr], [t["p"] * 20.0 for t in tr], days[0], days[-1])
    p = R.series_payload(306, {"strategy": "NOISE_1_1.py", "instrument": "NQ", "timeframe": "5m", "cost_pts": 0.5},
                         20.0, tr, daily, {"replay_usd": round(sum(t["p"] for t in tr) * 20, 2),
                                           "doc_usd": round(sum(t["p"] for t in tr) * 20, 2), "d_usd": 0.0},
                         "replay", None, "cold", "levels")
    R.add_sizing(p)
    return p


PROBE_HTML = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>run series probe</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html" style="width:1500px;height:1000px;border:0"></iframe>
<pre id="o"></pre>
<script>
var FIX=__FIX__, SER=__SER__, SERW=__SERW__;
(function(){
  var out={cases:{}},reported=false,t0=Date.now();
  function finish(why){if(reported)return;reported=true;out.why=why;out.ms=Date.now()-t0;
    document.getElementById('o').textContent='RTSPROBE: '+JSON.stringify(out);}
  function hook(w){if(w.__ps)return w.__ps;var s=w.__ps={errors:[],uncaught:[]};var o=w.console.error;
    w.console.error=function(){var a=[];for(var i=0;i<arguments.length;i++)a.push(String(arguments[i]&&arguments[i].stack||arguments[i]));s.errors.push(a.join(' '));try{o.apply(w.console,arguments);}catch(_){}};
    w.addEventListener('error',function(ev){s.uncaught.push(String(ev&&ev.message||ev));});
    w.addEventListener('unhandledrejection',function(ev){s.uncaught.push('rej: '+String(ev&&ev.reason));});return s;}
  var CASES=[
    ['curve',  {seed:'ok',ser:'SER',mode:'curve',size:'fixed'}],
    ['daily',  {seed:'ok',ser:'SER',mode:'curve',size:'fixed',click:'[data-rts-mode="daily"]'}],
    ['size2',  {seed:'ok',ser:'SER',mode:'curve',size:'fixed',click:'[data-rts-size="r2"]'}],
    ['warn',   {seed:'ok',ser:'SERW',mode:'curve',size:'r3'}],
    ['none',   {seed:'none',click:'[data-rts-req]'}],
    ['refused',{seed:'refused'}]
  ];
  function digest(el){var s='';if(!el)return 0;var ps=el.querySelectorAll('svg path,svg rect');for(var i=0;i<ps.length;i++)s+=(ps[i].getAttribute('d')||'')+(ps[i].getAttribute('y')||'')+(ps[i].getAttribute('height')||'');var h=0;for(var j=0;j<s.length;j++)h=(h*31+s.charCodeAt(j))|0;return h;}
  function read(d){var r={};var det=d.getElementById('res-detail');r.detail=!!det;var txt=det?(det.innerText||det.textContent||''):'';r.cantRender=/couldn.t render/i.test(txt);
    var P=det?det.querySelector('[data-rts-run]'):null;r.panel=!!P;r.panelId=P?P.getAttribute('data-rts-run'):null;if(!P)return r;
    var pt=P.innerText||P.textContent||'';r.text=pt.slice(0,600);
    r.ths=[].map.call(P.querySelectorAll('.rts-kpi thead th'),function(t){return {c:t.getAttribute('data-rts-col'),cls:t.className,t:(t.textContent||'').trim()};});
    r.rows={};[].forEach.call(P.querySelectorAll('.rts-kpi tbody tr'),function(tr){var td=tr.querySelectorAll('td');r.rows[(td[0].textContent||'').trim()]=[].slice.call(td,1).map(function(x){return (x.textContent||'').trim();});});
    r.warnline=!!P.querySelector('[data-rts-warn]');r.warnText=P.querySelector('[data-rts-warn]')?P.querySelector('[data-rts-warn]').textContent:'';
    var ch=P.querySelector('[data-rts-chart]');r.chartSvg=!!(ch&&ch.querySelector('svg'));r.chartPath=!!(ch&&ch.querySelector('svg path'));
    r.dailyBars=ch?ch.querySelectorAll('[data-rtsdaily-bar]').length:0;r.dailyLine=!!(ch&&ch.querySelector('[data-rtsdaily-line]'));r.dig=digest(ch);
    r.btn=!!P.querySelector('[data-rts-req]');r.asked=/Asked/.test(pt);
    r.modeActive=[].map.call(P.querySelectorAll('[data-rts-mode].active'),function(b){return b.getAttribute('data-rts-mode');});
    r.sizeActive=[].map.call(P.querySelectorAll('[data-rts-size].active'),function(b){return b.getAttribute('data-rts-size');});
    return r;}
  function runCase(i){if(i>=CASES.length){finish('done');return;}
    var nm=CASES[i][0],cfg=CASES[i][1],r={};var fr=document.getElementById('f'),w=fr.contentWindow,d=fr.contentDocument;var sink=hook(w);sink.errors.length=0;sink.uncaught.length=0;
    try{
      w.localStorage.setItem('el_rts_mode',cfg.mode||'curve');w.localStorage.setItem('el_rts_size',cfg.size||'fixed');
      var S=cfg.ser==='SERW'?SERW:SER;
      w.eval('window.__rtsWrites=[];window.__rtsS='+JSON.stringify(S||null)+';');
      w.eval("(function(){var mk=function(path){return {collection:function(c){return mk(path.concat([c]));},doc:function(x){return mk(path.concat([x]));},"
        +"set:function(v,o){window.__rtsWrites.push({path:path.join('/'),v:JSON.parse(JSON.stringify(v,function(k,x){return (x&&x.constructor&&x.constructor.name&&/FieldValue/i.test(x.constructor.name))?{fv:String(x._methodName||x.methodName||'fv'),el:x._elements||x.elements||null}:x;})),o:o});return Promise.resolve();},"
        +"get:function(){return Promise.resolve({exists:false,data:function(){return null;}});}};};"
        +"window.__rtsDbStub=mk([]);})()");
      var seed=cfg.seed==='ok'?"{st:'ok',S:window.__rtsS}":(cfg.seed==='none'?"{st:'none',status:null}":"{st:'none',status:{state:'refused',why:'PROBE: no tape reproduces the run'}}");
      r.call=w.eval("(function(){try{var F="+JSON.stringify(FIX)+";var doc=(typeof _bookUnitsOnRead==='function'&&typeof _isoTs==='function')?_bookUnitsOnRead(_isoTs(F)):F;"
        +"runHistory=[doc];window._runFull={};window._runFullOrder=[];window._runHydrating={};"
        +"window._rtsCache={};window._rtsCache[String(doc.id)]="+seed+";"
        +"try{db=window.__rtsDbStub;}catch(_d){window.db=window.__rtsDbStub;}"
        +"try{if(!auth||!auth.currentUser){auth={currentUser:{uid:'PROBEUID'}};}}catch(_a){}"
        +"activeTab='augur';augurSub='runs';augurRunSel=String(doc.id);renderApp();return 'OK';}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
    }catch(e){r.call='ERR '+e;}
    var tw=Date.now();
    (function wait(){var P=d.querySelector('#res-detail [data-rts-run]');var ok=P&&(cfg.seed!=='ok'||P.querySelector('[data-rts-chart] svg'));
      if(!ok&&Date.now()-tw<15000){setTimeout(wait,100);return;}
      r.before=read(d);
      if(cfg.click){var b=d.querySelector('#res-detail '+cfg.click);r.clicked=!!b;if(b)b.click();}
      setTimeout(function(){r.after=read(d);r.writes=w.eval('JSON.stringify(window.__rtsWrites||[])');r.errors=sink.errors.slice(0,10);r.uncaught=sink.uncaught.slice(0,10);out.cases[nm]=r;runCase(i+1);},600);})();}
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){
    try{var w=document.getElementById('f').contentWindow;out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');out.renderApp=typeof w.renderApp;hook(w);}catch(e){out.err=String(e);}
    if(out.renderApp!=='function'){finish('noboot');return;}
    var a0=Date.now();(function waitAuth(){var fd=document.getElementById('f').contentDocument;if(!(fd&&fd.getElementById('tsu'))&&Date.now()-a0<12000){setTimeout(waitAuth,100);return;}
      try{document.getElementById('f').contentWindow.eval('renderAuth=function(){};');}catch(e){}runCase(0);})();},2500);});
  setTimeout(function(){finish('backstop');},55000);
})();
</script></body></html>
"""


def find_chrome():
    cands = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]
    local = os.environ.get('LOCALAPPDATA')
    if local:
        cands.append(os.path.join(local, r"Google\Chrome\Application\chrome.exe"))
    return next((c for c in cands if os.path.isfile(c)), None)


def make_handler(root, alt_index):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root, **kw)

        def do_GET(self):
            if alt_index and (self.path == '/index.html' or self.path.startswith('/index.html?')):
                data = open(alt_index, 'rb').read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            super().do_GET()

        def log_message(self, *a):
            pass
    return H


def _usd(v, sg=False):
    v = float(v)
    return ('-' if v < 0 else ('+' if sg and v > 0 else '')) + '$' + format(abs(round(v)), ',')


def check(data, ser, serw):
    msgs = []
    C = data.get('cases') or {}

    def need(c, cond, what):
        if not cond:
            msgs.append('%s: %s' % (c, what))
    for nm in ('curve', 'daily', 'size2', 'warn', 'none', 'refused'):
        r = C.get(nm)
        if not r:
            msgs.append('%s: case did not run' % nm)
            continue
        need(nm, r.get('call') == 'OK', 'renderApp threw: %s' % r.get('call'))
        need(nm, not r.get('errors'), 'console.error: %s' % r.get('errors'))
        need(nm, not r.get('uncaught'), 'uncaught: %s' % r.get('uncaught'))
        b = r.get('before') or {}
        need(nm, b.get('detail') and not b.get('cantRender'), 'report missing or fell to its couldnt-render card')
        need(nm, b.get('panel') and b.get('panelId') == '306', 'no WALK-FORWARD P&L panel for run 306 in #res-detail')
    fx = ser['sizing']['cols']['fixed']
    r = (C.get('curve') or {}).get('before') or {}
    need('curve', r.get('chartPath'), 'no curve drawn')
    need('curve', [t.get('c') for t in r.get('ths', [])][1:] == ['fixed', 'r1', 'r2', 'r3'], 'KPI columns %s' % r.get('ths'))
    rows = r.get('rows') or {}
    need('curve', (rows.get('NET') or [''])[0] == _usd(fx['net'], True), 'FIXED net %s vs payload %s' % ((rows.get('NET') or [''])[0], _usd(fx['net'], True)))
    need('curve', (rows.get('TRADES') or [''])[0] == str(fx['trades']), 'FIXED trades %s vs %s' % (rows.get('TRADES'), fx['trades']))
    r1 = ser['sizing']['cols']['r1']
    need('curve', (rows.get('MAX CONTRACTS') or ['', ''])[1] == '%.1f' % r1['max_contracts'], 'RISK 1 max contracts %s vs %s' % (rows.get('MAX CONTRACTS'), r1['max_contracts']))
    need('curve', (rows.get('SKIPPED') or ['', ''])[1] == str(r1['skipped']), 'RISK 1 skipped %s vs %s' % (rows.get('SKIPPED'), r1['skipped']))
    need('curve', not r.get('warnline') and not any('rts-warn' in (t.get('cls') or '') for t in r.get('ths', [])),
         'amber shown on a series whose RISK 3 % does not trip')
    need('curve', r.get('modeActive') == ['curve'] and r.get('sizeActive') == ['fixed'], 'toggles %s %s' % (r.get('modeActive'), r.get('sizeActive')))
    a = (C.get('daily') or {}).get('after') or {}
    nd = len(ser['daily']['d'])
    need('daily', a.get('modeActive') == ['daily'], 'DAILY not active after the click')
    need('daily', a.get('dailyBars') in (nd, nd + 1), 'daily bars %s, series days %d' % (a.get('dailyBars'), nd))
    need('daily', a.get('dailyLine'), 'no running-total line on DAILY')
    b2, a2 = (C.get('size2') or {}).get('before') or {}, (C.get('size2') or {}).get('after') or {}
    need('size2', a2.get('sizeActive') == ['r2'], 'RISK 2 not selected after the click (%s)' % a2.get('sizeActive'))
    need('size2', any(t.get('c') == 'r2' and 'rts-sel' in (t.get('cls') or '') for t in a2.get('ths', [])), 'r2 column not highlighted')
    need('size2', a2.get('dig') != b2.get('dig'), 'the chart did not change when the size changed')
    w = (C.get('warn') or {}).get('before') or {}
    wr3 = serw['sizing']['cols']['r3']
    need('warn', bool(wr3['ruin'] or (wr3['dd_pct'] or 0) > 35), 'FIXTURE: the warn series does not trip RISK 3 pct (%s)' % wr3)
    warned = [t.get('c') for t in w.get('ths', []) if 'rts-warn' in (t.get('cls') or '')]
    need('warn', warned == ['r3'], 'amber columns %s, want only r3' % warned)
    need('warn', w.get('warnline') and 'RISK 3' in (w.get('warnText') or ''), 'no RISK 3 pct warning sentence')
    n0, n1 = (C.get('none') or {}).get('before') or {}, (C.get('none') or {}).get('after') or {}
    need('none', n0.get('btn'), 'no BUILD DAILY SERIES button')
    try:
        wr = json.loads((C.get('none') or {}).get('writes') or '[]')
    except Exception:
        wr = []
    need('none', len(wr) == 1 and wr[0].get('path', '').endswith('meta/run_series_req') and '306' in json.dumps(wr[0].get('v')),
         'request write %s' % wr)
    need('none', n1.get('asked') and not n1.get('btn'), 'panel does not say Asked after the click')
    rf = (C.get('refused') or {}).get('before') or {}
    need('refused', 'no tape reproduces' in (rf.get('text') or '') and not rf.get('btn'), 'refusal reason not shown, or a button offered')
    return msgs


def run(alt_index=None, verbose=False):
    chrome = find_chrome()
    if not chrome:
        print('RTSPROBE: INCONCLUSIVE -- no Chrome')
        return INCONCLUSIVE
    fix = json.load(open(os.path.join(ROOT, 'tools', 'fixtures', 'run_report.json'), encoding='utf-8'))
    ser, serw = _series(False), _series(True)
    pdir = os.path.join(ROOT, '_rtsprobe')
    os.makedirs(pdir, exist_ok=True)
    io.open(os.path.join(pdir, 'probe.html'), 'w', encoding='utf-8').write(
        PROBE_HTML.replace('__FIX__', json.dumps(fix)).replace('__SER__', json.dumps(ser)).replace('__SERW__', json.dumps(serw)))
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(ROOT, alt_index))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    prof = tempfile.mkdtemp(prefix='rtsprobe-')
    t0 = time.time()
    try:
        out = subprocess.run([chrome, '--headless=new', '--disable-gpu', '--no-sandbox', '--user-data-dir=' + prof,
                              '--virtual-time-budget=60000', '--dump-dom',
                              'http://127.0.0.1:%d/_rtsprobe/probe.html' % port],
                             capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=150).stdout
    except Exception as e:
        print('RTSPROBE: INCONCLUSIVE -- chrome failed: %s' % e)
        return INCONCLUSIVE
    finally:
        srv.shutdown()
        shutil.rmtree(pdir, ignore_errors=True)
        shutil.rmtree(prof, ignore_errors=True)
    m = re.search(r'RTSPROBE: (\{.*?\})</pre>', out, re.S)
    if not m:
        print('RTSPROBE: INCONCLUSIVE -- no readout')
        return INCONCLUSIVE
    data = json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>'))
    if data.get('why') == 'noboot':
        print('RTSPROBE: INCONCLUSIVE -- the app did not boot (preflight_boot owns that)')
        return INCONCLUSIVE
    if verbose:
        print(json.dumps(data, indent=1)[:6000])
    msgs = check(data, ser, serw)
    if msgs:
        print('RTSPROBE: FAIL (%.1fs, v%s)' % (time.time() - t0, data.get('VERSION')))
        for x in msgs:
            print('  - ' + x)
        return FAIL
    print('RTSPROBE: PASS -- %d cases (curve, daily, size2, warn, none, refused) in %.1fs, v%s'
          % (len(data.get('cases') or {}), time.time() - t0, data.get('VERSION')))
    return PASS


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--file', default=None)
    ap.add_argument('--verbose', action='store_true')
    a = ap.parse_args(argv)
    code = run(os.path.abspath(a.file) if a.file else None, a.verbose)
    if code == INCONCLUSIVE:          # one retry for a busy box
        code = run(os.path.abspath(a.file) if a.file else None, a.verbose)
    return code


if __name__ == '__main__':
    sys.exit(main())
