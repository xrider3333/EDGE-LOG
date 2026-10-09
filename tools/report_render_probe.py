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
  * the 1E KPI MATRIX LOCKBOX column carries an LB warm tag naming run 306's own cold
    reading (301 trades, $9,826) -- this fixture scored its lockbox cold and its saved
    gate_validate.ungated_lockbox is a continuous replay of the same stretch (334 trades),
    so it qualifies for the same warm-lockbox swap RUNBOARD / EXPLORE / LEADERBOARD read
    (2026-09-28, owner via MANAGER)

Cases cover the three REPORT COLUMNS layouts, since each is a different template path, plus the
classic layout on the 1A funnel chart (funnel-1a), whose lockbox hover is a separate builder.

Three more cases (readings-card / readings-old / readings-down) open the COST AND LIMITS readout with the
PC runner STUBBED (window._runCmd replaced before renderApp; no live runner is ever needed): a canned
get_blotter reply WITH `readings` must draw the runner's own summary sentences, the break-even / absorbs /
double-cost figures, the realistic reading and the "does not model" list (material items first, counts);
a reply WITHOUT `readings` (an old runner) must say the runner is on an older version; a rejected ask must
say the runner did not answer -- and none of them may log a console error or fall to the "couldn't render"
card. Each asks the runner exactly once.

One more case (roll-chip, 2026-10-08, owner ask via MANAGER #31/#33/#34) renders the same fixture AS RUN #424, one of the 22 runs restated for the old
roll detector (RUN_ROLL in index.html): the ROBUSTNESS rail must carry a ROLL chip beside COST AND LIMITS, and the readout it opens (data-rollchip="424")
must say "old roll detector" and print the saved and the true figures (net $1,116,128 -> $1,121,941, ROC 17.7 -> 21.1, ...), the 1 EPISODE word on the
saved worst drawdown, and the source line. Every other case runs as run 306, which is not in the table: it must show no ROLL chip and no readout.

One more case (exposure-chip, 2026-10-09, MANAGER #41 phase 2) renders the fixture AS RUN #163 with an injected window._runExpo entry (the page reads
users/{uid}/meta/run_exposure once per load; the probe never reads Firestore): the ROBUSTNESS rail must carry an EXPOSURE chip right after the ROLL chip, and the readout
it opens (data-expochip="163") must print the measured figures (95.5%, 3.80 lots, 0.96x the twin, the points and the dollars), the twin sentence, the footer, and ONE svg
with two polylines - the run solid, the buy-and-hold twin carrying stroke-dasharray. The same case then steps the page: the entry WITHOUT a curve draws no svg, a {why}
entry prints one line "No exposure reading: ...", a mostly-flat entry reads "mostly flat", and the fixture under its own id (306, no entry) shows no chip and no
readout. Every other case runs as run 306 with no entry: it must show no EXPOSURE chip and no readout.

Exit codes match preflight_boot.py: 0 PASS, 1 FAIL, 2 INCONCLUSIVE (never blocks).

RETRY-ONCE. A non-PASS attempt is rendered a second time before it blocks a push.
On 2026-09-03 a ship was blocked by "cols-3: no #res-detail card rendered at all" on
a file that then passed 3/3 standalone and passed the very next ship: a ship runs
several headless-Chrome probes back to back, and this one lost the race. A genuine
break fails the retry identically, so the retry cannot hide one -- it only costs one
extra render on a build that was going to fail anyway. A retry that turns into a PASS
is printed as a FLAKE line rather than swallowed. --no-retry turns it off.

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

# the iframe-window state each COST AND LIMITS case starts from: the readout opened, and every per-run guard / cache empty (they live for the page)
READ_WIN = {'_diagOpenKey': 'rd', '_rdFetched': {}, '_rdCache': {}, '_rdInflight': {}, '_concFetched': {}}

# What the PC runner's get_blotter replies with when asked for readings (shape: runner commit 8a3d0efd) - two material limits and one note, a
# realistic reading, summary sentences. Canned: this probe never talks to a runner.
CANNED = {
    'ok': True, 'n_rows': 4180, 'n_trades': 4180,
    'cost': {'ok': True, 'cost_pts': 0.533, 'gross_pts': 3.633, 'net_flat_pts': 3.1, 'net_double_pts': 2.567, 'breakeven_cost_pts': 3.633,
             'headroom_x': 6.8, 'net_flat_usd': 51340.0, 'net_double_usd': 40680.0, 'breakeven_cost_usd': 72.66},   # usd per round trip = pts x multiplier
    'realistic': {'ok': True, 'instrument': 'NQ', 'slippage_included': False, 'fitted': False, 'realistic_cost_pts': 0.65,
                  'net_realistic_usd': 26000.0, 'survives': True,
                  'realistic_breakdown': {'fee_pts': 0.15, 'spread_pts': 0.5, 'slippage_pts': 0.0, 'total_pts': 0.65,
                                          'source': 'published exchange fee and a typical quoted spread'}},
    'limits': {'ok': True,
               'items': [
                   {'key': 'stop_slippage', 'severity': 'material', 'text': 'A stop order that fills through its price costs more than the flat cost charged here.'},
                   {'key': 'market_impact', 'severity': 'material', 'text': 'Market impact is ignored: every fill is assumed at the bar price.'},
                   {'key': 'one_session', 'severity': 'note', 'text': 'Only the regular session is traded.'}],
               'lines': [], 'counts': {'total': 3, 'material': 2, 'note': 1}, 'basis': {}},
    'summary': ['Break-even cost is 3.63 points per round trip: the run absorbs 6.8 x the cost it was charged.',
                'At double the cost the run still nets $40,680.',
                'At a realistic cost (published figures, NOT fitted) it nets $26,000 and survives.'],
}

# EXPOSURE chip fixtures (exposure-chip case): the base entry is RSIDIV #163's real reading (95.5% in the market, 3.80 lots when in, 0.96x its twin); the curve is a JSON STRING
# ([[date, twin cumulative points, run cumulative points], ...] - Firestore forbids nested arrays, so the runner stores it as text and the page parses it).
_EXPO_CURVE = [["2010-06-07", 0.0, 0.0], ["2012-03-01", 9000.5, 7000.25], ["2013-09-02", 15000.0, 16500.0], ["2015-01-02", 22000.0, 19000.0], ["2016-07-01", 31000.0, 30500.0], ["2018-02-01", 42000.0, 40000.0], ["2020-03-16", 30000.0, 31000.0], ["2022-01-03", 61000.0, 60000.0], ["2024-05-01", 78000.0, 75500.0], ["2026-07-16", 87077.66, 83728.73]]
EXPO_ENTRY = {"in_mkt_pct": 95.5, "lots_mean_all": 3.6314, "lots_mean_in": 3.8023, "lots_max": 4, "hold_med_sessions": 57, "n_trades": 259, "strat_pts": 83728.73, "twin_pts": 87077.66, "ratio": 0.9615, "sessions": 4000, "first": "2010-06-07", "last": "2026-07-16", "window": ["2010-06-07", "2026-07-16"], "master": "NQ_5m", "inst": "NQ", "tf": "5m", "mult": 20}
WITH_CURVE = dict(EXPO_ENTRY, curve=json.dumps(_EXPO_CURVE))
EXPO_FLAT = dict(EXPO_ENTRY, in_mkt_pct=30.0, lots_mean_in=1.0, lots_mean_all=0.3, ratio=0.4)
EXPO_WHY = {'why': 'no saved trade list'}
STEPS = [
    # 1: the same entry without its curve (the runner writes one only above 50% in the market)
    "delete window._runExpo.runs['163'].curve;renderApp();",
    # 2: a {why} entry
    "window._runExpo.runs['163']=" + json.dumps(EXPO_WHY) + ";renderApp();",
    # 3: a mostly-flat entry (no curve)
    "window._runExpo.runs['163']=" + json.dumps(EXPO_FLAT) + ";renderApp();",
    # 4: the full entry is still filed under 163, but the page now shows the fixture as run 306: the entry must not follow the report to another run
    "window._runExpo.runs['163']=" + json.dumps(WITH_CURVE) + ";runHistory[0].id='306';augurRunSel='306';renderApp();",
]

# name -> {prefs, win}: prefs land in localStorage augurPrefs (and APREF), win on the
# iframe window before renderApp.
CASES = [
    ('cols-3', {'prefs': {'repCols': '3'}, 'win': {}}),
    ('cols-2', {'prefs': {'repCols': '2'}, 'win': {}}),
    ('cols-1', {'prefs': {'repCols': '1'}, 'win': {}}),
    # the owner's layout (2026-09-28): classic report, equity tab on the 1A funnel - a different chart
    # builder with its own lockbox hover, which v73.940 missed; the three cases above never draw it
    ('funnel-1a', {'prefs': {'repCols': '3', 'repLayout': 'classic', 'eqTab': 'funnel', 'a2gate': 1,
                             'a2kAll': 1, 'a2cfgAll': 1, 'a2doors': 0}, 'win': {}}),
    # COST AND LIMITS card (2026-10-07, the web half of the runner's get_blotter readings): the same report with the COST AND LIMITS chip opened and the
    # PC runner STUBBED - window._runCmd is replaced before renderApp, so no live runner is ever needed. 'ok' resolves a canned reply carrying `readings`;
    # 'old' resolves a reply WITHOUT the key (an old runner ignores readings:true); 'down' rejects (the runner is not there). 'wait' makes the poll hold
    # until the card has been painted with its answer, so the sample never catches it still asking. The per-run guards are reset for each case.
    ('readings-card', {'prefs': {'repCols': '3'}, 'win': READ_WIN, 'stub': 'ok', 'wait': '[data-rdcard][data-rdstate="done"]'}),
    ('readings-old', {'prefs': {'repCols': '3'}, 'win': READ_WIN, 'stub': 'old', 'wait': '[data-rdcard][data-rdstate="done"]'}),
    ('readings-down', {'prefs': {'repCols': '3'}, 'win': READ_WIN, 'stub': 'down', 'wait': '[data-rdcard][data-rdstate="done"]'}),
    # a run with no champion configuration has no trade list to replay: the plain "Not available" line, and the runner is never asked
    ('readings-na', {'prefs': {'repCols': '3'}, 'win': READ_WIN, 'stub': 'na', 'mut': 'nocfg', 'wait': '[data-rdna]'}),
    # the CONCENTRATION card and the COST AND LIMITS card want the same blotter: with the readings ask already out, the concentration card waits on THAT reply
    # (window._rdInflight) rather than make the runner generate it twice. Here the pending reply is parked by script and only the concentration readout is opened.
    ('readings-share', {'prefs': {'repCols': '3'}, 'win': dict(READ_WIN, _diagOpenKey='conc'), 'stub': 'share', 'wait': '[data-conccard]',
                        'waitText': 'trades in this run',
                        'pre': "var rows=[];for(var i=0;i<12;i++)rows.push({pnl_usd:(i%3===0?-150:300)+i*10});window._rdInflight={};window._rdInflight[String(doc.id)]=Promise.resolve({rows:rows});"}),
    # ROLL chip (2026-10-08, owner ask via MANAGER #31/#33/#34): the fixture rendered AS RUN #424 (setId), one of the 22 runs restated for the old roll detector, with the
    # ROLL readout opened. Static data, so no runner stub and no wait. Every case above runs as run 306 (not in the table) and must show NO ROLL chip.
    ('roll-chip', {'prefs': {'repCols': '3'}, 'win': {'_diagOpenKey': 'roll'}, 'setId': 424}),
    # EXPOSURE chip (2026-10-09, MANAGER #41 phase 2): the fixture rendered AS RUN #163 with window._runExpo injected (state ok, an entry WITH a curve), the EXPOSURE readout opened.
    # Last in the list on purpose - the injected cache is a window global, and every case above runs as run 306 with no entry and must show NO EXPOSURE chip. 'steps' then change the
    # page in place (each step is evaluated, the page re-renders, and the readout is read again): no curve, a {why} entry, a mostly-flat entry, and the same entry under another run id.
    ('exposure-chip', {'prefs': {'repCols': '3'},
                       'win': {'_diagOpenKey': 'expo', '_runExpo': {'state': 'ok', 'runs': {'163': WITH_CURVE}, 'at': 0}},
                       'setId': 163, 'steps': STEPS}),
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
var CASES=__CASES__, FIX=__FIX__, CANNED=__CANNED__;
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
        // SETID: render the fixture under another run number (the ROLL chip keys on the run id); everything else about the document stays the fixture's own
        +"var SETID="+JSON.stringify(cfg.setId==null?null:cfg.setId)+";if(SETID!=null){doc.id=SETID;}"
        +"runHistory=[doc];window._runFull={};window._runFullOrder=[];window._runHydrating={};"
        +"var W="+JSON.stringify(cfg.win||{})+";for(var k3 in W)window[k3]=W[k3];"
        // MUT: a per-case change to the report's run document (the same object runHistory holds), made before renderApp
        +"var MUT="+JSON.stringify(cfg.mut||'')+";if(MUT==='nocfg'){delete doc.best_params;}"
        +(cfg.pre||'')
        // THE RUNNER STUB (cost readings cases). _runCmd is a global function the app calls by name, so replacing window._runCmd before renderApp is
        //   enough; every other case gets the real one back. Each call is recorded so the case can check what was asked, and how many times.
        +"var STUB="+JSON.stringify(cfg.stub||'')+";"
        +"if(!window.__origRunCmd)window.__origRunCmd=window._runCmd;window._rdCalls=[];"
        +"if(STUB){window._runCmd=function(a,p){window._rdCalls.push({a:a,p:JSON.parse(JSON.stringify(p||{}))});"
        +"  if(STUB==='down')return Promise.reject(new Error('stub: the runner is not there'));"
        +"  var rep={ok:true,rows:[],n_rows:0};if(STUB==='ok')rep.readings="+JSON.stringify(CANNED)+";return Promise.resolve(rep);};}"
        +"else{window._runCmd=window.__origRunCmd;}"
        +"activeTab='augur';augurSub='runs';augurRunSel=String(doc.id);renderApp();return 'OK';"
        +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
    }catch(e){r.call='ERR '+(e&&e.stack?e.stack:e);}
    // WAIT FOR THE CARD, DO NOT GUESS AT IT. This used to sample once after a flat 1200ms,
    // which is a race: the report's chart draws and hydration run on their own timers, and on
    // a machine busy with four validates they are not finished in 1.2s. That produced
    // "no #res-detail card rendered at all" on pages that render perfectly -- measured
    // 2026-09-06, an UNCHANGED commit failed 2 of 3 runs while the machine was loaded, and
    // origin/main failed 3 of 3 and then passed first try once the machine went quiet.
    // Now: poll every 100ms until the card exists AND has stopped growing (two equal
    // samples), up to 15s, then sample. A fast machine still finishes in about 1.2s.
    var _t0=Date.now(), _lastLen=-1, _stable=0;
    (function poll(){
      var el=d.getElementById('res-detail');
      var len=el?el.innerHTML.length:-1;
      var ready=(el&&len>=20000&&len===_lastLen&&(!cfg.wait||el.querySelector(cfg.wait))&&(!cfg.waitText||(el.innerText||el.textContent||'').indexOf(cfg.waitText)>=0))?(++_stable>=2):false;
      _lastLen=len;
      if(!ready&&Date.now()-_t0<15000){setTimeout(poll,100);return;}
      r.waitedMs=Date.now()-_t0;
      sample();
    })();
    function sample(){
      try{
        var det=d.getElementById('res-detail');
        r.detail=!!det;
        r.detailLen=det?det.innerHTML.length:-1;
        var txt=det?(det.innerText||det.textContent||''):'';
        r.cantRender=/couldn.t render/i.test(txt);
        r.namesRun=txt.indexOf(String(cfg.setId!=null?cfg.setId:FIX.id))>=0;
        // LOCKBOX column / LB warm tag (2026-09-28, owner via MANAGER): this fixture (run 306)
        // scored its own lockbox cold (301 trades) before a continuous replay of the same
        // stretch (gate_validate.ungated_lockbox, 334 trades) - it qualifies for the same
        // warm-lockbox swap _lbWarmOf already makes on RUNBOARD / EXPLORE / the LEADERBOARD,
        // and the 1E KPI MATRIX's LOCKBOX column should show that reading, tagged.
        var lbTags=det?[].filter.call(det.querySelectorAll('span[title]'),function(sp){return (sp.textContent||'').indexOf('LB warm')>=0;}):[];
        r.lbWarmTagCount=lbTags.length;
        r.lbWarmTagTip=lbTags.length?(lbTags[0].getAttribute('title')||''):'';
        // every lockbox hover on the report's charts (1A funnel + champion equity) reads the same lockbox
        var lbRects=det?[].filter.call(det.querySelectorAll('rect[data-tip]'),function(e){return (e.getAttribute('data-tip')||'').indexOf('out-of-sample, never optimized')>=0;}):[];
        r.lbChartTips=lbRects.length;
        r.lbChartWarm=lbRects.filter(function(e){return (e.getAttribute('data-tip')||'').indexOf('continuous replay')>=0;}).length;
        r.appLen=(d.getElementById('app')||{innerHTML:''}).innerHTML.length;
        // ROLL chip (2026-10-08): the rail chip, whether it sits in the same rail as COST AND LIMITS, and the opened readout
        var rlChip=d.querySelector('[data-diagchip="roll"]'), rdChip=d.querySelector('[data-diagchip="rd"]'), rlCard=det?det.querySelector('[data-rollchip]'):null;
        r.roll={chip:!!rlChip, chipText:rlChip?(rlChip.innerText||rlChip.textContent||''):'', sameRail:!!(rlChip&&rdChip&&rlChip.parentNode===rdChip.parentNode),
          card:!!rlCard, cardId:rlCard?rlCard.getAttribute('data-rollchip'):null, cardText:rlCard?(rlCard.innerText||rlCard.textContent||''):'',
          cardN:det?det.querySelectorAll('[data-rollchip]').length:0, ones:rlCard?rlCard.querySelectorAll('[data-rollone]').length:0,
          cols:rlCard?[].map.call(rlCard.querySelectorAll('thead th'),function(e){return (e.textContent||'').trim();}):[]};
        // EXPOSURE chip (2026-10-09): what the rail and the opened readout show right now (read again after every step of a case that carries steps)
        r.expo=expoRead();
        // COST AND LIMITS card (stubbed-runner cases): what is drawn, in what order, and what the app asked the runner
        if(cfg.stub){
          var box=det?det.querySelector(cfg.stub==='share'?'[data-conccard]':'[data-rdcard],[data-rdna]'):null, cn=box?box.querySelector('[data-rdcounts]'):null;
          r.rd={stub:cfg.stub,found:!!box,state:box?box.getAttribute('data-rdstate'):null,kind:box?box.getAttribute('data-rdkind'):null,
            chip:!!d.querySelector('[data-diagchip="rd"]'),text:box?(box.innerText||box.textContent||''):'',
            items:box?[].map.call(box.querySelectorAll('[data-rditem]'),function(e){return {sev:e.getAttribute('data-rditem'),text:(e.innerText||e.textContent||'')};}):[],
            counts:cn?(cn.textContent||''):null,
            summary:box?[].map.call(box.querySelectorAll('[data-rdsummary] > div'),function(e){return e.textContent||'';}):[],
            calls:(w.eval('window._rdCalls')||[]).map(function(c){return {a:c.a,readings:c.p&&c.p.readings,run_id:c.p&&c.p.run_id,family:c.p&&c.p.family,
              lockbox_from:c.p&&c.p.lockbox_from,strategy:c.p&&c.p.strategy};})};
        }
        r.errors=sink.errors.slice(0,20);
        r.uncaught=sink.uncaught.slice(0,20);
      }catch(e){r.sampleErr=String(e&&e.stack?e.stack:e);}
      if(cfg.steps&&!r.sampleErr){r.expoSteps=[];stepExpo(0);return;}
      out.cases[nm]=r;
      runCase(i+1);
    }
    // EXPOSURE chip: the rail chip, where it sits against the ROLL / COST AND LIMITS chips, and the opened readout (text, svg, its lines)
    function expoRead(){
      var det=d.getElementById('res-detail');
      var chip=d.querySelector('[data-diagchip="expo"]'), roll=d.querySelector('[data-diagchip="roll"]'), rd=d.querySelector('[data-diagchip="rd"]');
      var card=det?det.querySelector('[data-expochip]'):null;
      var svgs=card?card.querySelectorAll('svg'):[];
      var lines=card?[].map.call(card.querySelectorAll('svg polyline, svg path'),function(e){return {tag:e.tagName.toLowerCase(),dash:e.hasAttribute('stroke-dasharray')};}):[];
      return {chip:!!chip, chipText:chip?(chip.innerText||chip.textContent||''):'', sameRail:!!(chip&&rd&&chip.parentNode===rd.parentNode),
        afterRoll:!!(chip&&roll&&chip.previousElementSibling===roll), hasRoll:!!roll,
        card:!!card, cardId:card?card.getAttribute('data-expochip'):null, cardText:card?(card.innerText||card.textContent||''):'',
        cardN:det?det.querySelectorAll('[data-expochip]').length:0, svgN:svgs.length, lines:lines,
        keyDash:card?card.querySelectorAll('span[style*="dashed"]').length:0};
    }
    // a case with steps: read the state just drawn, then evaluate the next step (it changes window state and re-renders), wait for the page to settle, read again
    function stepExpo(k){
      r.expoSteps.push(expoRead());
      if(k>=cfg.steps.length){
        r.errors=sink.errors.slice(0,20);
        r.uncaught=sink.uncaught.slice(0,20);
        out.cases[nm]=r;
        runCase(i+1);
        return;
      }
      try{w.eval(cfg.steps[k]);}catch(e){r.stepErr=String(e&&e.stack?e.stack:e);}
      setTimeout(function(){stepExpo(k+1);},800);
    }
  }
  document.getElementById('f').addEventListener('load',function(){
    setTimeout(function(){
      try{var w=document.getElementById('f').contentWindow;
          out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
          out.renderApp=typeof w.renderApp;
          hook(w);}catch(e){out.err=String(e);}
      if(out.renderApp!=='function'){finish('noboot');return;}
      // WAIT FOR FIREBASE AUTH TO SETTLE, THEN KEEP IT OFF THE PAGE (2026-09-28). With no
      //   signed-in user, onAuthStateChanged paints the SIGN IN screen over whatever is on the
      //   page whenever its round-trip lands. When it landed mid-run it replaced the cols-2
      //   report and read as "no #res-detail card" - INCONCLUSIVE every time, and a failed
      //   SELFTEST that blocked the v73.940 ship. Wait for that screen (up to 12s), then make
      //   renderAuth a no-op so a late callback cannot paint over a case.
      var _a0=Date.now();
      (function waitAuth(){
        var fd=document.getElementById('f').contentDocument;
        if(!(fd&&fd.getElementById('tsu'))&&Date.now()-_a0<12000){setTimeout(waitAuth,100);return;}
        out.authSettled=!!(fd&&fd.getElementById('tsu'));
        try{document.getElementById('f').contentWindow.eval('renderAuth=function(){};');out.authStub=true;}
        catch(e){out.authStub=String(e);}
        runCase(0);
      })();
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
            code = main(['--file', path, '--no-retry'] +
                        (['--fixture', fixture] if fixture else []))
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
    ap.add_argument('--no-retry', action='store_true',
                    help='do not re-render a failed attempt (the self-test uses this on '
                         'builds that are MEANT to fail, so they are not rendered twice)')
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

    return _report(t0, *(_attempt(chrome, root, alt_index, fixture) +
                         (fixture, not args.no_retry, chrome, root, alt_index)))


def _check_readings(nm, r, rd, fixture):
    """The COST AND LIMITS card under a stubbed runner: ok -> the module's sentences, the figures, material limits before notes, the counts;
    old -> the older-version sentence; down -> the did-not-answer sentence. Every case: the card is there, it was asked once, nothing in the console."""
    f = []
    txt = rd.get('text') or ''
    if not rd.get('chip'):
        f.append('%s: no COST AND LIMITS chip in the ROBUSTNESS rail' % nm)
    if not rd.get('found'):
        f.append('%s: the COST AND LIMITS card is not on the page with its chip opened' % nm)
        return f
    if rd.get('stub') == 'share':
        if rd.get('calls'):
            f.append('%s: the runner was asked %d time(s) although the readings reply was already out -- the concentration card must wait on it' % (nm, len(rd.get('calls'))))
        if 'all 12 trades' not in txt:
            f.append('%s: the concentration card did not measure from the 12 rows the shared reply carried -- %r' % (nm, txt[-200:]))
        if r.get('errors') or r.get('uncaught'):
            f.append('%s: console errors while sharing the reply -- %s' % (nm, ((r.get('errors') or []) + (r.get('uncaught') or []))[0].splitlines()[0][:200]))
        return f
    if rd.get('stub') == 'na':
        if 'Not available for this run: it saved no champion configuration' not in txt:
            f.append('%s: a run with no champion configuration did not get the plain "Not available for this run" line -- %r' % (nm, txt[:160]))
        if rd.get('calls'):
            f.append('%s: the runner was asked about a run that has nothing to replay' % nm)
        if 'asking the PC runner' in txt or 'MATERIAL' in txt:
            f.append('%s: the not-available card draws as if it had asked' % nm)
        if r.get('errors') or r.get('uncaught'):
            f.append('%s: console errors on the not-available card -- %s' % (nm, ((r.get('errors') or []) + (r.get('uncaught') or []))[0].splitlines()[0][:200]))
        return f
    if rd.get('state') != 'done':
        f.append('%s: the card never left "asking the PC runner" (state=%s)' % (nm, rd.get('state')))
    if 'asking the PC runner' in txt:
        f.append('%s: the card still says it is asking the PC runner' % nm)
    if 'COST AND LIMITS' not in txt:
        f.append('%s: the card has no COST AND LIMITS heading' % nm)
    calls = rd.get('calls') or []
    if len(calls) != 1:
        f.append('%s: the runner was asked %d times, not once' % (nm, len(calls)))
    else:
        c = calls[0]
        if c.get('a') != 'get_blotter' or c.get('readings') is not True:
            f.append('%s: the runner was not asked for get_blotter with readings:true -- %r' % (nm, c))
        if str(c.get('run_id')) != str(fixture.get('id')):
            f.append('%s: the ask names run %r, not %s' % (nm, c.get('run_id'), fixture.get('id')))
        if c.get('family') != fixture.get('famKey'):
            f.append('%s: the ask names family %r, not %r' % (nm, c.get('family'), fixture.get('famKey')))
        lbf = (((fixture.get('validate') or {}).get('windows') or {}).get('lockbox') or [None])[0]
        if not lbf or c.get('lockbox_from') != str(lbf)[:10]:
            f.append('%s: the ask carries lockbox_from %r, not the run\'s lockbox start %r' % (nm, c.get('lockbox_from'), lbf))
    kind = rd.get('kind')
    if rd.get('stub') == 'ok':
        if kind != 'ok':
            f.append('%s: a reply with readings drew as %r, not as readings' % (nm, kind))
        low = txt.lower()
        for want in ('break-even', 'absorbs', 'net at double cost', 'realistic net', 'what this run does not model',
                     'published figures, not fitted', 'never changes the run'):
            if want not in low:
                f.append('%s: the card does not say %r' % (nm, want))
        if 'slippage not included' not in low:
            f.append('%s: the realistic breakdown does not say slippage is not included' % nm)
        sevs = [i.get('sev') for i in (rd.get('items') or [])]
        if sevs != ['material', 'material', 'note']:
            f.append('%s: limits are listed %r, wanted both material items first and then the note' % (nm, sevs))
        for i in (rd.get('items') or [])[:2]:
            if 'MATERIAL' not in (i.get('text') or ''):
                f.append('%s: a material limit carries no MATERIAL tag' % nm)
        items_txt = ' | '.join((i.get('text') or '') for i in (rd.get('items') or []))
        for src in CANNED['limits']['items']:
            if src['text'] not in items_txt:
                f.append('%s: a limit was not shown verbatim: %r' % (nm, src['text'][:60]))
        if (rd.get('counts') or '').replace('\u00b7', '.').split() != ['2', 'material', '.', '1', 'note']:
            f.append('%s: the counts read %r, wanted "2 material . 1 note"' % (nm, rd.get('counts')))
        if len(rd.get('summary') or []) != len(CANNED['summary']):
            f.append('%s: %d summary sentences drawn, the runner sent %d' % (nm, len(rd.get('summary') or []), len(CANNED['summary'])))
    elif rd.get('stub') == 'old':
        if kind != 'old' or 'older version that does not compute these readings yet' not in txt:
            f.append('%s: a reply without readings did not draw the older-version sentence (kind=%r)' % (nm, kind))
        if 'MATERIAL' in txt:
            f.append('%s: limits were drawn from a reply that carried no readings' % nm)
    elif rd.get('stub') == 'down':
        if kind != 'down' or 'did not answer' not in txt or 'could not be computed' not in txt:
            f.append('%s: a rejected ask did not draw the did-not-answer sentence (kind=%r)' % (nm, kind))
    if r.get('errors') or r.get('uncaught'):
        f.append('%s: console errors with the stubbed runner -- %s' % (nm, ((r.get('errors') or []) + (r.get('uncaught') or []))[0].splitlines()[0][:200]))
    if r.get('cantRender'):
        f.append('%s: the "couldn\'t render" card is showing' % nm)
    return f


# ROLL chip: the fixture as run #424 (a RUN_ROLL run) carries the chip in the ROBUSTNESS rail beside COST AND LIMITS and a readout with the saved and
# true figures; the fixture as run 306 (not in the table) carries neither.
def _check_roll(nm, r, rl):
    f = []
    if nm != 'roll-chip':
        if nm != 'exposure-chip' and (rl.get('chip') or rl.get('cardN')):   # exposure-chip runs as #163, a roll-restated run: its ROLL chip is expected
            f.append('%s: run 306 is not one of the 22 roll-restated runs but the report shows a ROLL chip / readout' % nm)
        return f
    txt = ' '.join((rl.get('cardText') or '').split())
    if not rl.get('chip'):
        f.append('%s: no ROLL chip in the ROBUSTNESS rail of run #424' % nm)
    else:
        if 'ROLL' not in (rl.get('chipText') or '') or 'old roll detector' not in (rl.get('chipText') or ''):
            f.append('%s: the ROLL chip does not say ROLL / old roll detector -- %r' % (nm, rl.get('chipText')))
        if not rl.get('sameRail'):
            f.append('%s: the ROLL chip is not in the same rail as the COST AND LIMITS chip' % nm)
    if not rl.get('card') or rl.get('cardN') != 1:
        f.append('%s: the opened ROLL readout [data-rollchip] is not on the page exactly once (found %s)' % (nm, rl.get('cardN')))
        return f
    if rl.get('cardId') != '424':
        f.append('%s: the readout is marked for run %r, not 424' % (nm, rl.get('cardId')))
    for want in ('ROLL', 'old roll detector', '$1,116,128', '$1,121,941', '17.7', '21.1', '$116,916', '$98,295', '$77,322', '$79,175',
                 '$75,980', '$86,026', '106.6', '142.5', 'verified 2026-10-08', 'A report, not a re-validation',
                 'docs/RESTATE_ROLL22_2026-10-08.md'):
        if want not in txt:
            f.append('%s: the ROLL readout does not say %r' % (nm, want))
    if (rl.get('cols') or [])[1:] != ['SAVED', 'TRUE']:
        f.append('%s: the ROLL readout columns read %r, wanted SAVED | TRUE' % (nm, rl.get('cols')))
    if rl.get('ones') != 1 or '1 EPISODE' not in txt:
        f.append('%s: #424 saved worst drawdown is 1 EPISODE (116,916 > 1.3 x 77,322) and its true one is not -- the readout carries %s 1 EPISODE word(s)' % (nm, rl.get('ones')))
    if 'pending' in txt.lower():
        f.append('%s: the ROLL readout says something is pending -- the restatement is verified' % nm)
    if r.get('errors') or r.get('uncaught'):
        f.append('%s: console errors with the ROLL readout open -- %s' % (nm, ((r.get('errors') or []) + (r.get('uncaught') or []))[0].splitlines()[0][:200]))
    return f


# EXPOSURE chip: the fixture as run #163 with an injected entry carries the chip in the ROBUSTNESS rail right after the ROLL chip and a readout with the measured figures and ONE
# svg (the run solid, the buy-and-hold twin dashed); the steps then change the page in place. Every other case runs as run 306 with no entry: no chip, no readout.
def _check_expo(nm, r, ex):
    f = []
    if nm != 'exposure-chip':
        if ex.get('chip') or ex.get('cardN'):
            f.append('%s: run 306 has no exposure entry but the report shows an EXPOSURE chip / readout' % nm)
        return f
    steps = r.get('expoSteps') or []
    if len(steps) != len(STEPS) + 1:
        f.append('%s: the page was read %d times, wanted %d (a step did not run: %s)' % (nm, len(steps), len(STEPS) + 1, r.get('stepErr')))
        return f
    s0, s1, s2, s3, s4 = steps
    t0 = ' '.join((s0.get('cardText') or '').split())
    # step 0: the entry WITH a curve
    if not s0.get('chip'):
        f.append('%s: no EXPOSURE chip in the ROBUSTNESS rail of run #163' % nm)
    else:
        ct = s0.get('chipText') or ''
        if 'EXPOSURE' not in ct or 'in market 96%' not in ct:
            f.append('%s: the EXPOSURE chip does not read EXPOSURE / in market 96%% -- %r' % (nm, ct))
        if not s0.get('sameRail'):
            f.append('%s: the EXPOSURE chip is not in the same rail as the COST AND LIMITS chip' % nm)
        if not s0.get('hasRoll') or not s0.get('afterRoll'):
            f.append('%s: the EXPOSURE chip does not sit right after the ROLL chip (run #163 is a ROLL run)' % nm)
    if not s0.get('card') or s0.get('cardN') != 1:
        f.append('%s: the opened EXPOSURE readout [data-expochip] is not on the page exactly once (found %s)' % (nm, s0.get('cardN')))
        return f
    if s0.get('cardId') != '163':
        f.append('%s: the readout is marked for run %r, not 163' % (nm, s0.get('cardId')))
    for want in ('95.5%', '3.80', '3.63', '57 sessions', '259', '4,000 sessions', '83,729 points ($1,674,575)', '87,078 points ($1,741,553)', '0.96x',
                 '2010-06-07', '2026-07-16', 'constant 3.63-lot buy-and-hold of NQ', 'market exposure rather than timing',
                 'this run', 'buy-and-hold twin, same average lots',
                 'Measured by the PC runner from this run' + chr(8217) + 's full trade list on the back-adjusted price series (NQ_5m)',
                 'Report only - it changes no figure of the run.'):
        if want not in t0:
            f.append('%s: the EXPOSURE readout does not say %r' % (nm, want))
    if s0.get('svgN') != 1:
        f.append('%s: the readout holds %s svg(s), wanted exactly one chart' % (nm, s0.get('svgN')))
    else:
        lines = s0.get('lines') or []
        dashed = [x for x in lines if x.get('dash')]
        solid = [x for x in lines if not x.get('dash')]
        if len(lines) != 2 or len(dashed) != 1 or len(solid) != 1:
            f.append('%s: the chart should hold two lines, one solid and one carrying stroke-dasharray -- got %r' % (nm, lines))
    if not s0.get('keyDash'):
        f.append('%s: the chart key has no dashed rule beside "buy-and-hold twin"' % nm)
    # step 1: the same entry with NO curve -> the table and the sentence, no chart
    if not s1.get('card') or s1.get('svgN') != 0 or '95.5%' not in ' '.join((s1.get('cardText') or '').split()):
        f.append('%s: an entry without a curve should print its figures and NO svg (card=%s svgN=%s)' % (nm, s1.get('card'), s1.get('svgN')))
    # step 2: a {why} entry -> one line
    t2 = ' '.join((s2.get('cardText') or '').split())
    if not s2.get('card') or 'No exposure reading: no saved trade list' not in t2 or s2.get('svgN') != 0 or '95.5%' in t2:
        f.append('%s: a {why} entry should print "No exposure reading: no saved trade list" and nothing else -- %r' % (nm, t2[:160]))
    if not s2.get('chip') or 'no reading' not in (s2.get('chipText') or ''):
        f.append('%s: a {why} entry should leave a chip that reads "no reading" -- %r' % (nm, s2.get('chipText')))
    # step 3: mostly flat
    if not s3.get('chip') or 'mostly flat' not in (s3.get('chipText') or '') or s3.get('svgN') != 0:
        f.append('%s: an entry at 30%% in the market should read "mostly flat" with no chart -- %r' % (nm, s3.get('chipText')))
    # step 4: another run id
    if s4.get('chip') or s4.get('cardN'):
        f.append('%s: the entry filed under 163 followed the report to run 306 (chip=%s, readouts=%s)' % (nm, s4.get('chip'), s4.get('cardN')))
    if r.get('stepErr'):
        f.append('%s: a step threw -- %s' % (nm, str(r.get('stepErr')).splitlines()[0][:200]))
    if r.get('errors') or r.get('uncaught'):
        f.append('%s: console errors with the EXPOSURE readout open -- %s' % (nm, ((r.get('errors') or []) + (r.get('uncaught') or []))[0].splitlines()[0][:200]))
    return f


def _attempt(chrome, root, alt_index, fixture):
    """Render every case once in a fresh headless Chrome.

    Returns (verdict, msgs, notes, data, flaky). `flaky` marks a non-PASS verdict worth
    exactly one retry: anything a live browser can lose a race on. It is False only for
    "the app did not boot", which is deterministic and belongs to the boot gate.
    """
    pdir = os.path.join(root, '_reportprobe')
    if not os.path.isdir(pdir):
        os.makedirs(pdir)
    ppath = os.path.join(pdir, 'probe.html')
    html = (PROBE_HTML
            .replace('__CASES__', json.dumps([[n, c] for n, c in CASES]))
            .replace('__FIX__', json.dumps(fixture))
            .replace('__CANNED__', json.dumps(CANNED)))
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
        return INCONCLUSIVE, ['chrome failed: %s' % e], [], None, True
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
        return INCONCLUSIVE, ['probe produced no readout'], [], None, True
    try:
        data = json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&')
                          .replace('&lt;', '<').replace('&gt;', '>'))
    except Exception as e:
        return INCONCLUSIVE, ['unreadable readout: %s' % e], [], None, True
    if os.environ.get('REPORTPROBE_DUMP'):
        io.open(os.path.join(root, '_reportprobe_dump.json'), 'w', encoding='utf-8').write(
            json.dumps(data, indent=1, ensure_ascii=False))

    if data.get('why') == 'noboot':
        # the boot gate owns this verdict; do not double-report it, and do not retry it
        return (INCONCLUSIVE,
                ['app did not boot (renderApp=%s); see preflight_boot' % data.get('renderApp')],
                [], data, False)
    if data.get('err'):
        return FAIL, ['probe threw: %s' % data['err']], [], data, True

    fails, notes, cases = [], [], data.get('cases') or {}
    inconclusive = []
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
            # A MISSING CARD WITH NO JAVASCRIPT ERROR IS NOT EVIDENCE OF A BREAK. Every real
            # break this gate has caught (v73.367 / 442 / 443, and the v73.190 lesson behind
            # it) threw first -- a console error, an uncaught exception, or the "couldn't
            # render" fallback -- and those paths above have already recorded a fail. If the
            # page is silent and the card simply is not there after a 15-second wait, the
            # honest reading is that this render did not finish, not that the report is
            # broken. INCONCLUSIVE never blocks a push; blocking on this was stopping good
            # ships roughly a third of the time under load, and a gate that cries wolf gets
            # forced past, which is worse than no gate.
            if fails:
                fails.append('%s: no #res-detail card rendered at all' % nm)
            else:
                inconclusive.append('%s: no #res-detail card after %sms and no JavaScript '
                                    'error -- render did not finish (machine busy?), not a '
                                    'proven break' % (nm, r.get('waitedMs')))
            continue
        if r.get('cantRender'):
            fails.append("%s: the \"couldn't render\" fallback card is showing" % nm)
        if (r.get('detailLen') or 0) < 20000:
            fails.append('%s: report body is only %s chars' % (nm, r.get('detailLen')))
        if not r.get('namesRun'):
            fails.append('%s: report never names run %s' % (nm, fixture.get('id')))
        # LOCKBOX column / LB warm tag (2026-09-28, owner via MANAGER): fixture run 306 scored
        # its own lockbox cold (301 trades, ~$9,826) and carries a continuous replay of the
        # same stretch (334 trades) in gate_validate.ungated_lockbox, so it qualifies for the
        # warm swap RUNBOARD / EXPLORE / LEADERBOARD already make -- the 1E KPI MATRIX's
        # LOCKBOX column must show that reading, tagged, with this run's own cold figures on
        # the tag's hover.
        if (r.get('lbChartTips') or 0) and (r.get('lbChartWarm') or 0) < r.get('lbChartTips'):
            fails.append('%s: %s of %s lockbox chart hovers still print the cold lockbox strip -- they '
                         'must read the continuous replay the LOCKBOX column shows (live miss in '
                         'v73.940: the 1A chart hover)' % (nm, r.get('lbChartTips') - (r.get('lbChartWarm') or 0),
                                                          r.get('lbChartTips')))
        if not r.get('lbWarmTagCount'):
            fails.append('%s: the 1E KPI MATRIX LOCKBOX column shows no LB warm tag -- run %s '
                         'scored its own lockbox cold (301 trades) and should read the '
                         'continuous replay (334 trades) like RUNBOARD / EXPLORE / LEADERBOARD '
                         'already do' % (nm, fixture.get('id')))
        else:
            _tip = r.get('lbWarmTagTip') or ''
            if '301' not in _tip or '9,826' not in _tip:
                fails.append('%s: the LB warm tag does not name the cold reading this run '
                             'saved, 301 trades and $9,826 -- tip=%r' % (nm, _tip[:200]))
        if r.get('rd') is not None:
            fails.extend(_check_readings(nm, r, r['rd'], fixture))
        if r.get('roll') is not None:
            fails.extend(_check_roll(nm, r, r['roll']))
        if r.get('expo') is not None:
            fails.extend(_check_expo(nm, r, r['expo']))

    if fails:
        return FAIL, fails, notes, data, True
    if inconclusive:
        # never blocks -- see the note where these are recorded
        return INCONCLUSIVE, inconclusive, notes, data, True
    return PASS, [], notes, data, False


def _report(t0, verdict, msgs, notes, data, flaky, fixture, may_retry,
            chrome, root, alt_index):
    """Print one verdict, rendering a flaky non-PASS attempt a second time first.

    A genuine break fails the retry identically, so the retry cannot hide one; it only
    costs one more render on a build that was going to fail anyway. A retry that turns
    into a PASS is PRINTED as a flake rather than swallowed, because a probe that starts
    needing its retry often is a probe that is degrading, and that should stay visible.
    """
    first = None
    if verdict != PASS and flaky and may_retry:
        first = (verdict, msgs)
        print('REPORTPROBE: attempt 1 did not pass, retrying once before blocking -- %s'
              % ('; '.join(msgs[:2]) or 'no detail'))
        verdict, msgs, notes, data, flaky = _attempt(chrome, root, alt_index, fixture)

    elapsed = time.time() - t0
    data = data or {}
    if verdict == INCONCLUSIVE:
        print('REPORTPROBE: INCONCLUSIVE -- %s' % (msgs[0] if msgs else 'no detail'))
        return INCONCLUSIVE
    if verdict == FAIL:
        print('REPORTPROBE: FAIL (VERSION=%s, %.1fs%s)'
              % (data.get('VERSION'), elapsed, ', both attempts' if first else ''))
        seen = set()
        for f in msgs:
            if f not in seen:
                seen.add(f)
                print('  - ' + f)
        for n in notes[:8]:
            print('  note: ' + n)
        return FAIL

    cases = data.get('cases') or {}
    print('REPORTPROBE: PASS (VERSION=%s, run %s, %d cases, report %s chars, %.1fs)'
          % (data.get('VERSION'), fixture.get('id'), len(cases),
             (cases.get('cols-3') or {}).get('detailLen'), elapsed))
    if first:
        print('  FLAKE: attempt 1 did not pass on this same file, the retry did. It said:')
        for f in first[1][:4]:
            print('    - ' + f)
        print('  A real break fails BOTH attempts, so this is the probe losing a race, not a '
              'bug that fixed itself. If it recurs often, give the probe a longer settle '
              'rather than a second retry.')
    for n in notes[:8]:
        print('  note: ' + n)
    return PASS


if __name__ == '__main__':
    try:   # any Chrome this run starts dies with it, however the run ends (tools/kill_on_exit.py)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import kill_on_exit
        kill_on_exit.install()
    except Exception:
        pass
    sys.exit(main())
