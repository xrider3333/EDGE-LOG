#!/usr/bin/env python3
"""
tools/webull_board_probe.py -- render gate for LEDGER > WEBULL PAPER (augurSub 'qqqpaper').

WHY THIS EXISTS
---------------
tools/home_render_probe.py gates REAL's LEDGER board on every ship that touches index.html. The
WEBULL PAPER board moved onto the same shared parts (hero + range pills in step 4, the shared
equity chart in step 5) but its only probe, tools/qqq_overview_probe.py, is a long hand-run
verification tool, not a gate. This is the per-board render probe the LEDGER adoption contract
asks for (SHARED_PARTS_CONTRACT.md section 5, LEDGER_UNIFY_SCOPE.md appendix B), short enough for
`wt.py ship`, wired in exactly as REAL's is.

WHAT IT DOES
------------
Serves the repo over loopback, loads index.html in an iframe the way the HOME gate does, waits
for the signed-out screen and keeps it off the page, then hands the board a fixed copy of the
box's status doc (tools/fixtures/qqq_exec_box1005.json: the box's own _build_doc output on
2026-10-05 from a read-only copy of its files, account ids scrubbed; 47 trades from 2026-09-03,
data-caveat days, the NOISE #304 -> #382 run change, ENGU-Q flat since 2026-09-28). Nothing
touches the network or Firestore.

Cases: laptop 1366x768 | phone 375x812, x dark | mono, each a fresh render on ALL. Then one
interaction run on the laptop (Retired group open / close, a chart scrub writing the hero and
putting it back, a legend switch remembered), and one render with ?oldboards=1.

WHAT IT ASSERTS
---------------
Per case:
  * renderApp returned, no uncaught exception, unhandled rejection or console.error
  * the hero ids are there and the big number reads as money; the pills read TODAY 1W 1M 3M YTD ALL
  * the shared chart is drawn at >= 200 px on the laptop and >= 150 px on the phone, with
    >= 2 [data-lgdate] and >= 2 [data-lgtick], [data-lgband] (caveat days) and [data-lgmark]
    (the run change, named with its family), the three strategy lines ORB #314 / ENGU-Q #335 /
    NOISE #382 in the legend with 16 px icons, and the caveat / book-only key under it
  * the Retired group is there, collapsed by default, says 'flat since 2026-09-28', and only
    ORB and NOISE are live rows
  * every trade row names family + run number ('NOISE #382'), never a bare 'ENGUQ' / 'ORB', and the
    run is the one that took the trade (counts per name match the fixture: NOISE #304 / #382 ...)
  * the three faint lines carry three different dashes (MONO turns every colour grey)
  * on a phone the page does not scroll sideways
Interaction run: the Retired group opens (ENGU-Q's row appears, the choice is stored) and closes;
a scrub at the left edge writes $0.00 and 'start of the range' into the hero, at the right edge
the closed P&L of record, and leaving puts the hero back; a legend switch is remembered.
?oldboards=1: the old chart is back and there is no shared chart and no Retired group.

Exit codes as preflight_boot.py: 0 PASS, 1 FAIL, 2 INCONCLUSIVE (never blocks). A non-PASS
attempt is rendered once more before it blocks; a retry that passes prints a FLAKE line.

Usage:
  python tools/webull_board_probe.py                # gates this repo's index.html
  python tools/webull_board_probe.py --file X.html  # gates X as if it were index.html
  python tools/webull_board_probe.py --selftest     # deliberately broken copies (MUTANTS) must
                                                    # FAIL, then the real file must PASS

Stdlib only, plus a subprocess call to local Chrome.
"""
import argparse
import collections
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
FIXTURE = os.path.join(ROOT, 'tools', 'fixtures', 'qqq_exec_box1005.json')

VIEWPORTS = {'laptop': [1366, 768], 'phone': [375, 812]}
CASES = [['%s/%s' % (vp, th), {'vp': vp, 'theme': th}] for vp in ('laptop', 'phone') for th in ('dark', 'mono')]
LEDGER_RANGES = ['TODAY', '1W', '1M', '3M', 'YTD', 'ALL']
WANT_LINES = ['ORB #314', 'ENGU-Q #335', 'NOISE #382']
WANT_LIVE = ['ORB', 'NOISE']
RETIRED_SINCE = '2026-09-28'
LEG_RE = re.compile(r'^(ORB|ENGU-Q|NOISE) #\d+$')
MONEY_RE = re.compile(r'^-?\$[\d,]+\.\d\d$')

# Builds this gate must catch, made from the CURRENT index.html by one string replacement each.
MUTANTS = [
    ('chart-not-drawn',
     "if(window._qbLgChart){const lgw=content.querySelector('#qb-lg-chart');if(lgw)ledgerChartRender(lgw,window._qbLgChart);}",
     '',
     'the shared chart is never drawn into its box (no error thrown)'),
    ('retired-open-by-default',
     'let qbRetOpen=!!window._qbRetiredOpen;',
     'let qbRetOpen=true;',
     'the Retired group opens by default'),
    ('bare-leg-on-rows',
     "'<span class=\"qb-trade-leg\" title=\"the strategy (family and run number) that took this trade\">'+qeTradeLegName(t)+'</span>'",
     "'<span class=\"qb-trade-leg\">'+naS(t&&t.leg)+'</span>'",
     "trade rows name the box's bare leg key again ('ENGUQ')"),
    ('caveat-days-lost',
     "bands.push({i:i,title:tip+'. These trades still count.'});",
     '',
     'the data-caveat days are no longer hatched on the chart'),
    ('scrub-leaves-hero',
     'h.big.textContent=_hmMoney(qbBase+p.v+(atNow?openMarkPnl:0));',
     '',
     'a chart scrub no longer writes the big number'),
    ('phone-overflow',
     '<div class="qbx-lgchart" id="qb-lg-chart"></div>',
     '<div class="qbx-lgchart" id="qb-lg-chart" style="min-width:640px"></div>',
     'the chart is wider than a phone and the page scrolls sideways'),
    ('wrong-run',
     "if(dg)return '#'+dg[1];",
     "if(dg)return '#999';",
     'trade rows name a run that did not take the trade (the run lookup broke)'),
    ('lines-same-dash',
     "const _LG_DASHES=['none','5 3','1.5 3','7 2 1.5 2'];",
     "const _LG_DASHES=['none','none','none','none'];",
     'the three faint lines share one dash, so MONO cannot tell them apart'),
]

PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>webull board probe</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html" style="width:1366px;height:768px;border:0;display:block"></iframe>
<pre id="o" style="display:none"></pre>
<script>
var CASES=__CASES__, VP=__VP__, FIX=__FIX__;
(function(){
  var out={cases:{},notes:[]}, reported=false, t0=Date.now(), sink=null, phase=0;
  function finish(why){
    if(reported)return; reported=true;
    out.why=why; out.ms=Date.now()-t0;
    document.getElementById('o').textContent='WEBULLPROBE: '+JSON.stringify(out);
  }
  setTimeout(function(){finish('backstop');},52000);
  var fr=document.getElementById('f');
  function W(){return fr.contentWindow;}
  function D(){return fr.contentDocument;}
  function sleep(ms){return new Promise(function(r){setTimeout(r,ms);});}
  async function waitFor(fn,ms){
    var a=Date.now();
    while(Date.now()-a<ms){var v=false;try{v=fn();}catch(_e){} if(v)return true; await sleep(40);}
    try{return !!fn();}catch(_e2){return false;}
  }
  function hook(w){
    if(w.__probeSink)return w.__probeSink;
    var s=w.__probeSink={errors:[],uncaught:[],loadErr:[]};
    var orig=w.console.error;
    w.console.error=function(){
      var p=[];for(var i=0;i<arguments.length;i++){var a=arguments[i];p.push(a&&a.stack?String(a.stack):String(a));}
      s.errors.push(p.join(' '));
      try{orig.apply(w.console,arguments);}catch(_){}
    };
    w.addEventListener('error',function(ev){
      if(/ResizeObserver loop/.test(String(ev&&ev.message||'')))return;
      s.uncaught.push(String(ev&&ev.message||ev)+(ev&&ev.error&&ev.error.stack?' :: '+ev.error.stack:''));});
    w.addEventListener('unhandledrejection',function(ev){
      var r=ev&&ev.reason;s.uncaught.push('unhandledrejection: '+(r&&r.stack?r.stack:String(r)));});
    var le=w._loadError;
    w._loadError=function(err,stage){
      s.loadErr.push(String(err&&err.message||err)+' (stage '+stage+')');
      if(typeof le==='function')return le.apply(this,arguments);
    };
    return s;
  }
  function drain(){
    return {errors:sink.errors.splice(0).slice(0,12),uncaught:sink.uncaught.splice(0).slice(0,12),
            loadErr:sink.loadErr.splice(0).slice(0,12)};
  }
  function overlays(){
    var d=D(),n=0;
    [].slice.call(d.body.children).forEach(function(e){
      if(/^\\s*LOAD ERROR/.test(e.textContent||'')){n++;e.remove();}});
    return n;
  }
  async function setVp(name){
    var v=VP[name];
    fr.style.width=v[0]+'px';fr.style.height=v[1]+'px';
    await waitFor(function(){return W().innerWidth===v[0];},2000);
    await sleep(60);
  }
  function q(sel){return D().querySelector(sel);}
  function txt(sel){var e=q(sel);return e?(e.textContent||'').replace(/\\s+/g,' ').trim():null;}
  function offenders(d){
    var cw=d.documentElement.clientWidth,res=[],fix=[];
    var all=d.querySelectorAll('body *');
    for(var i=0;i<all.length&&res.length<4;i++){
      var e=all[i],r=e.getBoundingClientRect();
      if(r.width<=0||r.right<=cw+1)continue;
      var p=e.parentElement,pr=p?p.getBoundingClientRect():null;
      if(pr&&pr.right>cw+1)continue;
      var pos=d.defaultView.getComputedStyle(e).position;
      (pos==='fixed'?fix:res).push(e.tagName.toLowerCase()+(e.id?'#'+e.id:'')+(typeof e.className==='string'&&e.className?'.'+e.className.trim().split(/\\s+/).join('.'):'')
               +' right='+Math.round(r.right)+(pos!=='static'?' ('+pos+')':''));
    }
    return res.length?res:fix.slice(0,3);
  }
  function seed(cfg){
    var w=W();
    w.__probeFixJson=JSON.stringify(FIX);
    return w.eval("(function(){try{"
      +"try{localStorage.removeItem('el_qb_retired_open');localStorage.removeItem('el_lg_lines_webull');}catch(e){}"
      +"window._qbRetiredOpen=false;"
      +"prefs.theme="+JSON.stringify(cfg.theme)+";applyTheme();"
      +"window._qqqExec=JSON.parse(window.__probeFixJson);"
      +"window._qqqExecLoaded=true;window._qqqExecLoading=false;window._qqqExecErr=null;"
      +"window._qqqPaper=null;window._qqqPaperLoaded=true;window._qqqPaperLoading=false;window._qqqPaperErr=null;"
      +"window._qqqCalMonth=null;window._qeDrawerIdx=null;window._qeChartHidden={};window._qeTradesShown=50;window._qeEventsShown=30;"
      +"window._qbSheet=null;window._qbLegOpen=new Set();window._qbLegNoteOpen={};window._qeTradesView='list';window._qeChartPeriod='ALL';"
      +"window._qbChartHoverActive=false;"
      +"homeRange='ALL';currentUser=currentUser||{uid:'probe-uid'};"
      +"activeTab='augur';augurSub='qqqpaper';window._lastRenderTab='augur';"
      +"try{window.scrollTo(0,0);}catch(e){}"
      +"renderApp();return 'OK';"
      +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
  }
  function sample(){
    var d=D(),w=W(),r={};
    r.innerW=w.innerWidth;
    r.theme=d.documentElement.getAttribute('data-theme');
    r.appLen=(d.getElementById('app')||{innerHTML:''}).innerHTML.length;
    r.heroMissing=['qb-hero-label','qb-hero-value','qb-hero-today','qb-hero-range','qb-hero-chips'].filter(function(i){return !d.getElementById(i);});
    r.heroBig=txt('#qb-hero-value');
    r.heroToday=txt('#qb-hero-today');
    r.pills=[].map.call(d.querySelectorAll('.qbx-range-row [data-qbrange]'),function(b){return b.getAttribute('data-qbrange');}).join(',');
    var csv=d.querySelector('#qb-lg-chart svg');
    r.chart=!!csv;
    r.chartH=0;
    if(csv){var cr=csv.getBoundingClientRect(),vb=(csv.getAttribute('viewBox')||'').split(/[ ,]+/).map(Number);
      r.chartH=Math.round(vb.length===4&&vb[2]>0&&vb[3]>0?vb[3]*Math.min(cr.width/vb[2],cr.height/vb[3]):cr.height);}
    r.chartDates=csv?csv.querySelectorAll('[data-lgdate]').length:0;
    r.chartTicks=csv?csv.querySelectorAll('[data-lgtick]').length:0;
    r.chartBands=csv?csv.querySelectorAll('[data-lgband]').length:0;
    r.chartMarks=csv?csv.querySelectorAll('[data-lgmark]').length:0;
    var mk=csv?csv.querySelector('[data-lgmark]'):null;
    r.markText=mk&&mk.nextElementSibling?(mk.nextElementSibling.textContent||'').trim():null;
    r.lines=[].map.call(d.querySelectorAll('#qb-lg-chart .lg-legend [data-lgline]'),function(b){return (b.textContent||'').trim();});
    r.lineDashes=[].map.call(d.querySelectorAll('#qb-lg-chart .lg-legend svg line'),function(l){return l.getAttribute('stroke-dasharray')||'none';});
    r.lineIconW=Math.max.apply(null,[0].concat([].map.call(d.querySelectorAll('#qb-lg-chart .lg-legend svg'),function(s){return Math.round(s.getBoundingClientRect().width);})));
    r.key=txt('.qbx-lg-key');
    r.liveRows=[].map.call(d.querySelectorAll('.qbx-side [data-qblegrow]'),function(e){return e.getAttribute('data-qblegrow');});
    var rb=d.querySelector('.qbx-side [data-qbretired]');
    r.retired=!!rb;
    r.retiredExpanded=rb?rb.getAttribute('aria-expanded'):null;
    r.retiredText=rb?(rb.textContent||'').replace(/\\s+/g,' ').trim():null;
    r.retiredRows=d.querySelectorAll('.qbx-side [data-qbretiredrow]').length;
    var rows=d.querySelectorAll('[data-qbtraderow]');
    r.tradeRows=rows.length;
    r.tradeLegs=[].map.call(rows,function(e){var s=e.querySelector('.qb-trade-leg');return s?(s.textContent||'').trim():null;});
    r.oldChart=!!d.querySelector('#qbCrossCapture');
    r.scrollW=d.documentElement.scrollWidth;
    r.clientW=d.documentElement.clientWidth;
    if(r.scrollW>r.clientW+1)r.wide=offenders(d);
    r.overlay=overlays();
    return r;
  }
  async function runCase(nm,cfg){
    var r={};
    await setVp(cfg.vp);
    drain();
    try{r.call=seed(cfg);}catch(e){r.call='ERR '+(e&&e.stack?e.stack:e);}
    await sleep(200);
    try{Object.assign(r,sample());}catch(e){r.sampleErr=String(e&&e.stack?e.stack:e);}
    Object.assign(r,drain());
    out.cases[nm]=r;
  }
  async function interact(){
    var w=W(),d=D(),res={};
    await setVp('laptop');
    drain();
    try{res.seed=seed({vp:'laptop',theme:'dark'});}catch(e){res.seed='ERR '+(e&&e.stack?e.stack:e);}
    await sleep(200);
    try{
      // 1. the Retired group opens and closes, and the choice is kept for this viewer
      var rb=q('.qbx-side [data-qbretired]');
      if(rb){rb.click();await sleep(80);}
      var st=null;try{st=w.localStorage.getItem('el_qb_retired_open');}catch(e){}
      res.open={expanded:(q('.qbx-side [data-qbretired]')||{getAttribute:function(){return null;}}).getAttribute('aria-expanded'),
        rows:d.querySelectorAll('.qbx-side [data-qbretiredrow]').length,engu:!!q('.qbx-side [data-qbretiredrow="ENGUQ"] [data-qblegrow="ENGUQ"]'),stored:st};
      rb=q('.qbx-side [data-qbretired]');
      if(rb){rb.click();await sleep(80);}
      res.closed={expanded:(q('.qbx-side [data-qbretired]')||{getAttribute:function(){return null;}}).getAttribute('aria-expanded'),
        rows:d.querySelectorAll('.qbx-side [data-qbretiredrow]').length};
      // 2. a scrub writes the hero and leaving puts it back (no re-render)
      var sv=q('#qb-lg-chart svg'),sc={};
      if(sv){
        var rc=sv.getBoundingClientRect(),y=rc.top+rc.height/2;
        sc.big0=txt('#qb-hero-value');sc.today0=txt('#qb-hero-today');
        sv.dispatchEvent(new w.PointerEvent('pointermove',{clientX:rc.left+2,clientY:y,pointerType:'mouse',bubbles:true}));
        sc.bigStart=txt('#qb-hero-value');sc.todayStart=txt('#qb-hero-today');sc.held=!!w._qbChartHoverActive;
        sc.sameSvg=q('#qb-lg-chart svg')===sv;
        sv.dispatchEvent(new w.PointerEvent('pointermove',{clientX:rc.right-1,clientY:y,pointerType:'mouse',bubbles:true}));
        sc.bigEnd=txt('#qb-hero-value');sc.rangeEnd=txt('#qb-hero-range');
        sv.dispatchEvent(new w.PointerEvent('pointerleave',{clientX:rc.right+5,clientY:y,pointerType:'mouse',bubbles:true}));
        sc.bigAfter=txt('#qb-hero-value');sc.todayAfter=txt('#qb-hero-today');sc.heldAfter=!!w._qbChartHoverActive;
      }
      res.scrub=sc;
      // 3. a legend switch is remembered for this viewer
      var lb=q('#qb-lg-chart .lg-legend [data-lgline="0"]'),lg={};
      if(lb){lb.click();await sleep(60);
        var lb2=q('#qb-lg-chart .lg-legend [data-lgline="0"]');lg.off=!!(lb2&&lb2.classList.contains('off'));
        try{lg.stored=w.localStorage.getItem('el_lg_lines_webull');}catch(e){}}
      res.legend=lg;
    }catch(e){res.threw=String(e&&e.stack?e.stack:e);}
    await sleep(60);
    res.errs=drain();
    out.inter=res;
  }
  async function boot(){
    var w=W();
    try{
      out.VERSION=out.VERSION||w.eval('typeof VERSION!=="undefined"?VERSION:null');
      out.renderApp=typeof w.renderApp;
      sink=hook(w);
    }catch(e){out.err=String(e);finish('hookfail');return false;}
    if(out.renderApp!=='function'){finish('noboot');return false;}
    out.authSettled=await waitFor(function(){return !!D().getElementById('tsu');},12000);
    try{w.eval('renderAuth=function(){};');}catch(e){out.notes.push('renderAuth stub: '+e);}
    await sleep(200);
    drain();
    overlays();
    return true;
  }
  fr.addEventListener('load',function(){
    setTimeout(async function(){
      if(phase===0){
        phase=1;
        if(!(await boot()))return;
        for(var i=0;i<CASES.length;i++)await runCase(CASES[i][0],CASES[i][1]);
        try{await interact();}catch(e){out.inter={threw:String(e&&e.stack?e.stack:e)};}
        fr.src='../index.html?oldboards=1';
        return;
      }
      if(phase===1){
        phase=2;
        if(!(await boot()))return;
        await runCase('oldboards',{vp:'laptop',theme:'mono'});
        finish('done');
      }
    },2500);
  });
})();
</script>
</body></html>
"""


def find_chrome():
    cands = [os.path.join('C:' + os.sep, 'Program Files', 'Google', 'Chrome', 'Application', 'chrome.exe'),
             os.path.join('C:' + os.sep, 'Program Files (x86)', 'Google', 'Chrome', 'Application', 'chrome.exe')]
    local = os.environ.get('LOCALAPPDATA')
    if local:
        cands.append(os.path.join(local, 'Google', 'Chrome', 'Application', 'chrome.exe'))
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


def qe_pnl_of(t):
    """The board's P&L of record for one trade (index.html qePnlOf): pnl_record, else the book
    pnl, else the re-priced real_pnl, else 0. A null or empty field is missing, never $0."""
    for k in ('pnl_record', 'pnl', 'real_pnl'):
        v = t.get(k)
        if v is None or v == '':
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if v == v and v not in (float('inf'), float('-inf')):
            return v
    return 0.0


FAMILY = {'ORB': 'ORB', 'ENGUQ': 'ENGU-Q', 'NOISE': 'NOISE'}
CURRENT_RUN = {'ORB': '#314', 'ENGUQ': '#335', 'NOISE': '#382'}
NOISE_SWITCH = '2026-09-24'   # NOISE #304 -> #382 (index.html QE_LEG_VERSIONS)
TID_RE = re.compile(r'^([A-Za-z0-9_]+)-\d{8}T\d{6}Z-[LS]$')


def expected_leg_name(t):
    """The strategy name a trade row must show, worked out here and not read off the page: the
    run in the trade id when the id carries one (NOISE_304-... -> #304), else NOISE before the
    09-24 switch -> #304, else the leg's current run."""
    leg = str(t.get('leg') or '')
    fam = FAMILY.get(leg, leg)
    m = TID_RE.match(str(t.get('trade_id') or ''))
    dg = re.search(r'_(\d+)$', m.group(1)) if m else None
    if dg:
        return '%s #%s' % (fam, dg.group(1))
    day = str(t.get('entry_ts') or t.get('exit_ts') or '')[:10]
    if leg == 'NOISE' and re.match(r'^\d{4}-\d{2}-\d{2}$', day) and day < NOISE_SWITCH:
        return 'NOISE #304'
    return '%s %s' % (fam, CURRENT_RUN.get(leg, ''))


def money(v):
    return ('-' if v < 0 else '') + '${:,.2f}'.format(abs(v))


def _attempt(chrome, alt_index, fixture):
    pdir = tempfile.mkdtemp(prefix='_webullprobe_', dir=ROOT)
    html = (PROBE_HTML.replace('__CASES__', json.dumps(CASES)).replace('__VP__', json.dumps(VIEWPORTS))
            .replace('__FIX__', json.dumps(fixture)))
    io.open(os.path.join(pdir, 'probe.html'), 'w', encoding='utf-8').write(html)
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(ROOT, alt_index))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    prof = tempfile.mkdtemp(prefix='webullprobe-')
    try:
        out = subprocess.run(
            [chrome, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
             '--user-data-dir=' + prof, '--virtual-time-budget=56000', '--window-size=1500,1000',
             '--dump-dom', 'http://127.0.0.1:%d/%s/probe.html' % (port, os.path.basename(pdir))],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=170).stdout
    except Exception as e:
        return INCONCLUSIVE, ['chrome failed: %s' % e], [], None, True
    finally:
        srv.shutdown()
        shutil.rmtree(pdir, ignore_errors=True)
        shutil.rmtree(prof, ignore_errors=True)
    m = re.search(r'WEBULLPROBE: (\{.*?\})</pre>', out or '', re.S)
    if not m:
        return INCONCLUSIVE, ['probe produced no readout'], [], None, True
    try:
        data = json.loads(m.group(1).replace('&quot;', '"').replace('&lt;', '<').replace('&gt;', '>')
                          .replace('&amp;', '&'))
    except Exception as e:
        return INCONCLUSIVE, ['unreadable readout: %s' % e], [], None, True
    if os.environ.get('WEBULLPROBE_DUMP'):
        print(json.dumps(data, indent=1)[:20000])
    return _judge(data, fixture)


def _first(s, n=300):
    s = str(s or '')
    return s if len(s) <= n else s[:n] + '...'


def _errs(tag, r, fails):
    for k in ('uncaught', 'errors', 'loadErr'):
        for e in (r.get(k) or [])[:3]:
            fails.append('%s: %s -- %s' % (tag, {'uncaught': 'uncaught error', 'errors': 'console.error',
                                                'loadErr': 'LOAD ERROR'}[k], _first(e)))
    if r.get('overlay'):
        fails.append('%s: a LOAD ERROR overlay was on the page' % tag)


def _judge(data, fixture):
    fails, notes, unfinished = [], [], []
    why = data.get('why')
    if data.get('renderApp') != 'function':
        return (INCONCLUSIVE, ['app did not boot (renderApp=%s); see preflight_boot' % data.get('renderApp')],
                notes, data, True)
    if not data.get('authSettled'):
        notes.append('the signed-out screen never appeared; cases ran anyway')
    closed = round(sum(qe_pnl_of(t) for t in fixture.get('trades_all') or []), 2)
    n_rows = min(len(fixture.get('trades_all') or []), 50)
    cases = data.get('cases') or {}
    for nm, cfg in CASES:
        r = cases.get(nm)
        if r is None:
            unfinished.append('%s: never ran (why=%s)' % (nm, why))
            continue
        if r.get('call') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (nm, _first(r.get('call'))))
            continue
        if r.get('sampleErr'):
            fails.append('%s: the probe could not read the page -- %s' % (nm, _first(r['sampleErr'])))
            continue
        _errs(nm, r, fails)
        if r.get('heroMissing'):
            fails.append('%s: hero ids missing: %s' % (nm, ', '.join(r['heroMissing'])))
        if not MONEY_RE.match(r.get('heroBig') or ''):
            fails.append('%s: the hero big number reads %r, not a dollar amount' % (nm, r.get('heroBig')))
        if not (r.get('heroToday') or '').endswith('today'):
            fails.append('%s: the hero has no "today" line (got %r)' % (nm, r.get('heroToday')))
        if r.get('pills') != ','.join(LEDGER_RANGES):
            fails.append('%s: the range pills read %r, not %s' % (nm, r.get('pills'), ' '.join(LEDGER_RANGES)))
        if not r.get('chart'):
            fails.append('%s: the shared equity chart was not drawn (#qb-lg-chart has no svg)' % nm)
        else:
            min_h = 150 if cfg['vp'] == 'phone' else 200
            if (r.get('chartH') or 0) < min_h:
                fails.append('%s: the equity chart is %spx tall (squashed; needs %s+)' % (nm, r.get('chartH'), min_h))
            if (r.get('chartDates') or 0) < 2 or (r.get('chartTicks') or 0) < 2:
                fails.append('%s: the chart has %s date labels and %s price labels (needs 2+ of each)'
                             % (nm, r.get('chartDates'), r.get('chartTicks')))
            if not r.get('chartBands'):
                fails.append('%s: no hatched data-caveat day on the chart ([data-lgband])' % nm)
            if not r.get('chartMarks'):
                fails.append('%s: no run-change marker on the chart ([data-lgmark])' % nm)
            elif 'NOISE' not in (r.get('markText') or '') or '#382' not in (r.get('markText') or ''):
                fails.append('%s: the run-change marker reads %r (needs family + run, e.g. NOISE #304 -> #382)'
                             % (nm, r.get('markText')))
            if r.get('lines') != WANT_LINES:
                fails.append('%s: the chart legend lines are %r, not %r' % (nm, r.get('lines'), WANT_LINES))
            elif (r.get('lineIconW') or 0) > 24:
                fails.append('%s: the legend line icons are %spx wide (the legend wraps; want 16px)'
                             % (nm, r.get('lineIconW')))
            key = r.get('key') or ''
            if 'hatched' not in key or 'book only' not in key:
                fails.append('%s: the caveat / book-only key under the chart reads %r' % (nm, key))
        if not r.get('retired'):
            fails.append('%s: no Retired group under the live strategies' % nm)
        else:
            if r.get('retiredExpanded') != 'false' or r.get('retiredRows'):
                fails.append('%s: the Retired group is not collapsed by default (aria-expanded=%s, %s rows shown)'
                             % (nm, r.get('retiredExpanded'), r.get('retiredRows')))
            if ('flat since ' + RETIRED_SINCE) not in (r.get('retiredText') or ''):
                fails.append('%s: the Retired group reads %r, want "flat since %s"'
                             % (nm, r.get('retiredText'), RETIRED_SINCE))
        if r.get('liveRows') != WANT_LIVE:
            fails.append('%s: the live strategy rows are %r, want %r' % (nm, r.get('liveRows'), WANT_LIVE))
        legs = r.get('tradeLegs') or []
        if r.get('tradeRows') != n_rows:
            fails.append('%s: the trade list shows %s rows for %s trades' % (nm, r.get('tradeRows'), n_rows))
        bad = [x for x in legs if not LEG_RE.match(x or '')]
        if bad:
            fails.append('%s: trade rows without family + run number: %s' % (nm, sorted(set(map(str, bad)))[:5]))
        elif len(fixture.get('trades_all') or []) <= 50:
            want = collections.Counter(expected_leg_name(t) for t in fixture.get('trades_all') or [])
            got = collections.Counter(legs)
            if got != want:
                fails.append('%s: trade rows name the wrong run: shown %s, want %s'
                             % (nm, dict(sorted(got.items())), dict(sorted(want.items()))))
        dashes = r.get('lineDashes') or []
        if r.get('lines') == WANT_LINES and len(set(dashes)) != len(WANT_LINES):
            fails.append('%s: the three faint lines do not carry three different dashes (%r); under MONO they '
                         'cannot be told apart' % (nm, dashes))
        if cfg['vp'] == 'phone' and (r.get('scrollW') or 0) > (r.get('clientW') or 0) + 1:
            fails.append('%s: the page scrolls sideways on a phone (scrollWidth %s > clientWidth %s; sticking out: %s)'
                         % (nm, r.get('scrollW'), r.get('clientW'), ', '.join(r.get('wide') or []) or '?'))
        if (r.get('appLen') or 0) < 3000:
            fails.append('%s: the board rendered almost nothing (%s chars)' % (nm, r.get('appLen')))
    res = data.get('inter')
    if res is None:
        unfinished.append('interaction run: never ran (why=%s)' % why)
    elif res.get('threw') and not res.get('seed'):
        fails.append('interaction run: the probe itself threw -- %s' % _first(res['threw']))
    else:
        tag = 'interaction run'
        if res.get('seed') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (tag, _first(res.get('seed'))))
        if res.get('threw'):
            fails.append('%s: %s' % (tag, _first(res['threw'])))
        _errs(tag, res.get('errs') or {}, fails)
        o, c = res.get('open') or {}, res.get('closed') or {}
        if o.get('expanded') != 'true' or not o.get('engu') or o.get('stored') != '1':
            fails.append('%s: the Retired group did not open with ENGU-Q in it and the choice kept (%s)' % (tag, o))
        if c.get('expanded') != 'false' or c.get('rows'):
            fails.append('%s: the Retired group did not close again (%s)' % (tag, c))
        sc = res.get('scrub') or {}
        if not sc:
            fails.append('%s: no chart to scrub' % tag)
        else:
            if sc.get('bigStart') != '$0.00' or 'start of the range' not in (sc.get('todayStart') or ''):
                fails.append('%s: a scrub at the range start did not write $0.00 / start of the range into the hero '
                             '(got %r / %r)' % (tag, sc.get('bigStart'), sc.get('todayStart')))
            if sc.get('bigEnd') != money(closed):
                fails.append('%s: a scrub at the last day reads %r, want the closed P&L of record %s'
                             % (tag, sc.get('bigEnd'), money(closed)))
            if not sc.get('held') or sc.get('heldAfter'):
                fails.append('%s: the live redraw hold did not follow the scrub (held=%s, after=%s)'
                             % (tag, sc.get('held'), sc.get('heldAfter')))
            if not sc.get('sameSvg'):
                fails.append('%s: the scrub re-rendered the chart' % tag)
            if sc.get('bigAfter') != sc.get('big0') or sc.get('todayAfter') != sc.get('today0'):
                fails.append('%s: leaving the chart did not put the hero back (%r -> %r)'
                             % (tag, sc.get('big0'), sc.get('bigAfter')))
        lg = res.get('legend') or {}
        if not lg.get('off') or 'ORB' not in (lg.get('stored') or ''):
            fails.append('%s: switching the ORB line off was not remembered (%s)' % (tag, lg))
    r = cases.get('oldboards')
    if r is None:
        unfinished.append('oldboards: never ran (why=%s)' % why)
    elif r.get('call') != 'OK':
        fails.append('oldboards: renderApp threw -- %s' % _first(r.get('call')))
    else:
        _errs('oldboards', r, fails)
        if r.get('chart') or not r.get('oldChart') or r.get('retired'):
            fails.append('oldboards: ?oldboards=1 does not show the old Webull chart and strategy list '
                         '(shared chart=%s, old chart=%s, Retired group=%s)'
                         % (r.get('chart'), r.get('oldChart'), r.get('retired')))
    if fails:
        return FAIL, fails, notes, data, True
    if unfinished:
        return INCONCLUSIVE, unfinished, notes, data, True
    return PASS, [], notes, data, False


def _report(t0, attempt, may_retry, chrome, alt_index, fixture):
    verdict, msgs, notes, data, retry = attempt
    first = None
    if verdict != PASS and retry and may_retry:
        first = (verdict, msgs)
        print('WEBULLPROBE: attempt 1 did not pass, retrying once before blocking -- %s'
              % ('; '.join(msgs[:2]) or 'no detail'))
        verdict, msgs, notes, data, retry = _attempt(chrome, alt_index, fixture)
    elapsed = time.time() - t0
    data = data or {}
    if verdict == INCONCLUSIVE:
        print('WEBULLPROBE: INCONCLUSIVE -- %s' % ('; '.join(msgs[:3]) if msgs else 'no detail'))
        return INCONCLUSIVE
    if verdict == FAIL:
        print('WEBULLPROBE: FAIL (VERSION=%s, %.1fs%s, %d problem(s))'
              % (data.get('VERSION'), elapsed, ', both attempts' if first else '', len(msgs)))
        seen = set()
        for f in msgs:
            if f not in seen and len(seen) < 25:
                seen.add(f)
                print('  - ' + f)
        for n in notes[:6]:
            print('  note: ' + n)
        return FAIL
    lap = (data.get('cases') or {}).get('laptop/dark') or {}
    print('WEBULLPROBE: PASS (VERSION=%s, %d cases + interaction + oldboards, %.1fs; laptop chart %spx, '
          '%s dates, %s price labels, %s caveat days, marker %r)'
          % (data.get('VERSION'), len(CASES), elapsed, lap.get('chartH'), lap.get('chartDates'),
             lap.get('chartTicks'), lap.get('chartBands'), lap.get('markText')))
    if first:
        print('  FLAKE: attempt 1 did not pass on this same file, the retry did. It said:')
        for f in first[1][:4]:
            print('    - ' + f)
    for n in notes[:6]:
        print('  note: ' + n)
    return PASS


def selftest():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    src = io.open(os.path.join(ROOT, 'index.html'), encoding='utf-8', newline='').read()
    t0 = time.time()
    tmpdir = tempfile.mkdtemp(prefix='webullprobe-selftest-')
    bad = []
    try:
        for name, anchor, repl, why in MUTANTS:
            n = src.count(anchor)
            if n != 1:
                print('SELFTEST: INCONCLUSIVE -- mutant %r cannot be built: its anchor appears %d times in '
                      'index.html (expected once). Update MUTANTS in tools/webull_board_probe.py: %r'
                      % (name, n, anchor))
                return INCONCLUSIVE
            path = os.path.join(tmpdir, 'index_%s.html' % name)
            io.open(path, 'w', encoding='utf-8', newline='').write(src.replace(anchor, repl))
            print('-- mutant %s (%s): expect FAIL' % (name, why))
            code = main(['--file', path, '--no-retry'])
            if code != FAIL:
                bad.append('mutant %s was NOT caught (exit %d) -- the gate has gone blind to: %s' % (name, code, why))
        print('-- current index.html: expect PASS')
        code = main([])
        if code != PASS:
            bad.append('current index.html did not PASS (exit %d)' % code)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    if bad:
        print('SELFTEST: FAIL (%.1fs)' % (time.time() - t0))
        for b in bad:
            print('  - ' + b)
        return FAIL
    print('SELFTEST: PASS -- gate caught %d/%d broken builds and passed the current one (%.1fs)'
          % (len(MUTANTS), len(MUTANTS), time.time() - t0))
    return PASS


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--file', default=None, help='gate this file as if it were index.html')
    ap.add_argument('--no-retry', action='store_true', help='do not re-render a failed attempt')
    ap.add_argument('--selftest', action='store_true',
                    help='assert FAIL on every MUTANT of index.html, then PASS on the real file')
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    t0 = time.time()
    alt_index = os.path.abspath(args.file) if args.file else None
    if alt_index and not os.path.isfile(alt_index):
        print('WEBULLPROBE: INCONCLUSIVE -- --file not found: %s' % alt_index)
        return INCONCLUSIVE
    if not os.path.isfile(FIXTURE):
        print('WEBULLPROBE: INCONCLUSIVE -- fixture missing: %s' % FIXTURE)
        return INCONCLUSIVE
    fixture = json.load(io.open(FIXTURE, encoding='utf-8'))
    chrome = find_chrome()
    if not chrome:
        print('WEBULLPROBE: INCONCLUSIVE -- Chrome not found')
        return INCONCLUSIVE
    return _report(t0, _attempt(chrome, alt_index, fixture), not args.no_retry, chrome, alt_index, fixture)


if __name__ == '__main__':
    sys.exit(main())
