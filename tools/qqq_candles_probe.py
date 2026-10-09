#!/usr/bin/env python3
"""
tools/qqq_candles_probe.py -- verification probe for the Webull paper candle charts
(LEDGER > WEBULL PAPER, owner ask via MANAGER 2026-09-28: "OHLC candles on the Webull paper
trades so I can judge the price action behind each one").

Boots index.html headless (same technique as tools/webull_board_probe.py: serve a copy of
index.html from a private temp dir over loopback -- nothing is written into the repo --
load it in a same-origin iframe, drive it from the parent page) against
  tools/fixtures/qqq_exec_candles.json   the status doc, trades_all = the real
                                          2026-09-22..28 closed trades (box ledger copies)
  tools/fixtures/qqq_bars_2026-09-24.json the real day docs tools/qqq_bars_publish.py
  tools/fixtures/qqq_bars_2026-09-28.json built (--dry-run) from the box's bar caches
served to the page through its test hook window._qqqBarsSource (no Firestore), with the
PC's get_bars command stubbed so the probe can COUNT every PC trip.

Probe-only additions, all synthetic and said so here (FULL pass only): the 09-28 doc gets
the session's last settled bars appended (flat at the 15:58 close -- the complete doc the 09:20 run
republishes has them) so the 15:59 exits and the refused close land on the chart; the ORB
mark gets a stop and a target line (phase 2's shape, exercised early); and one book-only
trade (a mark with no Webull rows), one refused-then-held-back trade, one netted trade and
one trade whose sends went unanswered (ledger outcome UNKNOWN: a filled resend follows the
entry's, nothing follows the exit's) with a failed order call (outcome ERROR) are added to
the doc and to trades_all.

Also checked: the unanswered sends / failed call are never drawn or worded "Webull
refused"; a 5-minute signal bar on 1-minute bars spans its five bars, a 1-minute one on
5-minute bars is left off and the legend says why; a trimmed-inside side says its first
try is not on file; the full viewer shows a loading stub before waiting on a day that is
not in memory; at phone width a day with no doc does not point at the hidden EXPAND.

Since LEDGER steps 8 + 9 (re-anchored 2026-10-08): a row tap opens TRADING-LOG's shared trade panel (.lg-panel; its chart slot is the
compact chart, its numbers slot the breakdown), the chart glyph [data-qbchartkey] on every row (LIST and TABLE) opens the full viewer in place
of the old TABLE CHART pill, and LIST | TABLE is the shared frame's [data-lgview] switch.

FULL pass (per theme: dark, paper, mono):
  * a row tap -> the trade panel's compact chart: every marker kind drawn (signal bar, backtest / book /
    Webull fills both directions, refused Webull try, backtest / book / Webull exits, a
    price line), the legend strip, "book only - no Webull order", "signal bar not
    recorded" for ENGU-Q, and a day with no doc says so instead of asking the PC.
  * EXPAND -> full viewer: box bars (zero PC trips), zoomed to the trade, legend, NEXT
    walks the list (PREV here), 1m <-> 5m from the same doc.
  * TABLE view chart glyph -> same viewer from the box doc; a day with no doc falls back
    to the PC (exactly one get_bars) and the sub line says the bars came from the PC.
  * Cache key: prepending a new closed trade shifts every row, yet each trade keeps its
    key, and the pill for the shifted row opens THAT trade.
  * RUN REPORTS UNCHANGED: window.candleSVG output is byte-identical to origin/main's
    candleSVG (extracted with `git show`) for run-report inputs with no marker lists AND
    with empty ones, and a run trade opened in the real viewer draws with exactly the
    arguments and bytes the old function produces (no legend strip added).
Screenshots (named): sheet NOISE / ENGU-Q in dark, paper and mono at 1366x900, the ENGU-Q
sheet at phone width 390x844 in mono, the full viewer in dark and mono, and the synthetic
refused-then-held-back trade in dark and mono (shapes must differ with no colour).

EOD pass (dark, mono): the 09-28 doc exactly as the 16:10 run writes it (5m through
15:50, 1m through 15:58, NO synthetic bars) -- the ORB 15:59 and ENGU-Q 15:59 exits lie
after the last bar, so the shading and the view must run to that bar, the exits must be
marked on it and the legend must say so.

Usage: python tools/qqq_candles_probe.py [out_dir]   (exit 0 = PASS, 1 = FAIL, 2 = no Chrome)
"""
import copy
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tools", "fixtures")
BOOKONLY_ID = "NOISE_382-20260928T170000Z-S"
HELD_ID = "NOISE_382-20260928T173000Z-S"
NET_ID = "ORB_R6-20260928T180000Z-L"
UNK_ID = "NOISE_382-20260928T150000Z-L"


def find_chrome():
    cands = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        cands.append(os.path.join(local, r"Google\Chrome\Application\chrome.exe"))
    for c in cands:
        if os.path.isfile(c):
            return c
    return shutil.which("google-chrome") or shutil.which("chromium")


def make_handler(root):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root, **kw)

        def log_message(self, *a):
            pass
    return H


def old_candle_svg_source():
    """origin/main's window.candleSVG function text (the byte-identity baseline)."""
    for ref in ("origin/main", "HEAD"):
        try:
            txt = subprocess.run(["git", "show", ref + ":index.html"], cwd=ROOT, capture_output=True,
                                 check=True).stdout.decode("utf-8")
            break
        except Exception:
            txt = None
    if not txt:
        return None
    a = txt.index("window.candleSVG=function(bars,overlays,markers,opts){")
    b = txt.index("\n};", a)
    return txt[a + len("window.candleSVG="):b + 2]


def _pack_extra(doc, tf, rows):
    doc["bars"][tf] = doc["bars"][tf] + ";" + ";".join(rows)


def build_days(synthetic_tail=True):
    """synthetic_tail=False keeps the 09-28 doc exactly as the 16:10 run publishes it
    (5m through 15:50, 1m through 15:58), so every end-of-day exit lies after its last bar."""
    days = {}
    for d in ("2026-09-24", "2026-09-28"):
        days[d] = json.load(io.open(os.path.join(FIX, "qqq_bars_%s.json" % d), encoding="utf-8"))
    d28 = days["2026-09-28"]
    if not synthetic_tail:
        return days
    # SYNTHETIC: the session's last settled bars (see the module docstring)
    last1 = d28["bars"]["1m"].split(";")[-1].split(",")
    c = last1[4]
    _pack_extra(d28, "1m", ["389,%s,%s,%s,%s,1000" % (c, c, c, c)])
    _pack_extra(d28, "5m", ["385,%s,%s,%s,%s,1000" % (c, c, c, c)])
    d28["bars_through"] = {"1m": "15:59", "5m": "15:55"}
    d28["complete"] = True
    # SYNTHETIC: a try Webull refused followed by one the book held back itself (the real
    # 2026-09-23 NOISE pattern), and an end-of-day style internal cross (netted, no order)
    d28["marks"].append({
        "trade_id": HELD_ID, "leg": "NOISE", "side": "short", "tf": "5m",
        "signal": {"t": None, "rule": "not recorded"}, "signal_out": None, "bt_in": None, "bt_out": None,
        "book_in": {"t": "2026-09-28 13:30:05", "px": 736.3},
        "book_out": {"t": "2026-09-28 13:45:05", "px": 736.1, "why": "signal exit"},
        "wb_in": [{"t": "2026-09-28 13:30:05", "px": None, "ok": False, "sent": True, "outcome": "REFUSED",
                   "side": "SHORT", "why": "This order will generate new short stock positions"}],
        "wb_out": [{"t": "2026-09-28 13:45:05", "px": None, "ok": False, "sent": False, "outcome": "HELD",
                    "side": "BUY", "why": "nothing to close at the broker for leg 'NOISE'"}],
        "book_only": False})
    d28["marks"].append({
        "trade_id": NET_ID, "leg": "ORB", "side": "long", "tf": "5m",
        "signal": None, "signal_out": None, "bt_in": None, "bt_out": None,
        "book_in": {"t": "2026-09-28 14:00:05", "px": 736.0},
        "book_out": {"t": "2026-09-28 14:40:05", "px": 736.4, "why": "flatten"},
        "wb_in": [{"t": "2026-09-28 14:00:05", "px": 736.02, "ok": True, "sent": True, "outcome": "OK",
                   "side": "BUY", "why": ""}],
        "wb_out": [{"t": "2026-09-28 14:40:05", "px": 736.4, "ok": True, "sent": False, "outcome": "NETTED",
                    "side": "SELL", "why": "flatten: crossed internally against NOISE"}],
        "book_only": False})
    # SYNTHETIC: a sent entry whose answer never came back (the ledger's outcome UNKNOWN:
    # a hard-timeout send) followed by its filled resend, and an exit whose order call
    # failed before anything went out (mode ERROR) followed by a send that went unanswered
    # with nothing later on file -- none of them may read "Webull refused"
    d28["marks"].append({
        "trade_id": UNK_ID, "leg": "NOISE", "side": "long", "tf": "5m",
        "signal": {"t": "2026-09-28 10:55", "rule": "recorded"}, "signal_out": None,
        "bt_in": None, "bt_out": None,
        "book_in": {"t": "2026-09-28 11:00:05", "px": 734.9},
        "book_out": {"t": "2026-09-28 11:30:05", "px": 734.7, "why": "signal exit"},
        "wb_in": [{"t": "2026-09-28 11:00:05", "px": None, "ok": False, "sent": True, "outcome": "UNKNOWN",
                   "side": "BUY", "why": "hard timeout: no answer after 25s",
                   "then": {"t": "2026-09-28 11:00:40", "outcome": "OK", "px": 734.95}},
                  {"t": "2026-09-28 11:00:40", "px": 734.95, "ok": True, "sent": True, "outcome": "OK",
                   "side": "BUY", "why": "", "resend": True}],
        "wb_out": [{"t": "2026-09-28 11:30:05", "px": None, "ok": False, "sent": False, "outcome": "ERROR",
                    "side": "SELL", "why": "TypeError: place_stock_order() got an unexpected keyword",
                    },
                   {"t": "2026-09-28 11:30:10", "px": None, "ok": False, "sent": True, "outcome": "UNKNOWN",
                    "side": "SELL", "why": "ConnectionError: connection dropped"}],
        "book_only": False})
    for m in d28["marks"]:
        if m["trade_id"].startswith("ORB_R6-20260928"):
            ep = m["book_in"]["px"]
            m["lines"] = [{"price": round(ep + 2.5, 2), "label": "stop"},
                          {"price": round(ep - 5.0, 2), "label": "target"}]
    d28["marks"].append({
        "trade_id": BOOKONLY_ID, "leg": "NOISE", "side": "short", "tf": "5m",
        "signal": {"t": "2026-09-28 12:55", "rule": "recorded"},
        "bt_in": {"t": "2026-09-28 13:00:00", "px": 736.2},
        "signal_out": {"t": "2026-09-28 13:25", "rule": "recorded"},
        "bt_out": {"t": "2026-09-28 13:30:00", "px": 736.0},
        "book_in": {"t": "2026-09-28 13:00:08", "px": 736.19},
        "book_out": {"t": "2026-09-28 13:30:09", "px": 736.01, "why": "signal exit"},
        "wb_in": [], "wb_out": [], "book_only": True})
    return days


def build_exec():
    ex = json.load(io.open(os.path.join(FIX, "qqq_exec_candles.json"), encoding="utf-8"))
    ex["trades_all"] = [{"leg": "NOISE", "entry_ts": "2026-09-28 13:00:08",
                         "exit_ts": "2026-09-28 13:30:09", "side": "short", "shares": 10,
                         "entry_px": 736.19, "exit_px": 736.01, "pnl": 1.8,
                         "exit_reason": "signal exit", "trade_id": BOOKONLY_ID,
                         "book_only": True, "book_only_reason": "refused send"},
                        {"leg": "NOISE", "entry_ts": "2026-09-28 13:30:05", "exit_ts": "2026-09-28 13:45:05",
                         "side": "short", "shares": 10, "entry_px": 736.3, "exit_px": 736.1, "pnl": 2.0,
                         "exit_reason": "signal exit", "trade_id": HELD_ID},
                        {"leg": "ORB", "entry_ts": "2026-09-28 14:00:05", "exit_ts": "2026-09-28 14:40:05",
                         "side": "long", "shares": 10, "entry_px": 736.0, "exit_px": 736.4, "pnl": 4.0,
                         "exit_reason": "flatten", "trade_id": NET_ID},
                        {"leg": "NOISE", "entry_ts": "2026-09-28 11:00:05", "exit_ts": "2026-09-28 11:30:05",
                         "side": "long", "shares": 10, "entry_px": 734.9, "exit_px": 734.7, "pnl": -2.0,
                         "exit_reason": "signal exit", "trade_id": UNK_ID}] + ex["trades_all"]
    ex["trades_all"].sort(key=lambda t: t["exit_ts"], reverse=True)
    return ex


PROBE_HTML = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>qqq candles probe</title></head>
<body style="margin:0;background:#0a0a12">
<iframe id="f" src="../index.html" style="width:__IW__px;height:__IH__px;border:0"></iframe>
<pre id="o" style="display:none"></pre>
<script>
var EXEC=__EXEC__, DAYS=__DAYS__, OLDSVG=__OLDSVG__, THEME=__THEME__, MODE=__MODE__, IW=__IW__;
var NOISE_ID='NOISE_382-20260928T141500Z-S', ENGU_ID='ENGUQ_335-20260928T163200Z-L',
    ORB_ID='ORB_R6-20260928T144500Z-S', BOOKONLY_ID='__BOOKONLY__', NODOC_ID='NOISE_382-20260925T161000Z-L',
    HELD_ID='__HELD__', NET_ID='__NET__', UNK_ID='__UNK__';
(function(){
  var out={mode:MODE,theme:THEME}, done=false;
  function finish(why){if(done)return;done=true;out.why=why;
    document.getElementById('o').textContent='QQQCANDLES: '+JSON.stringify(out);}
  function sleep(ms){return new Promise(function(r){setTimeout(r,ms);});}
  async function waitFor(fn,ms){for(var t=0;t<(ms||8000);t+=50){try{var v=fn();if(v)return v;}catch(e){}await sleep(50);}return null;}
  async function run(){
    var fr=document.getElementById('f'), w=fr.contentWindow, d=fr.contentDocument;
    function q(s){return d.querySelector(s);} function qa(s){return [].slice.call(d.querySelectorAll(s));}
    function kinds(root){return root?[].slice.call(root.querySelectorAll('[data-mk]')).map(function(e){return e.getAttribute('data-mk');}):[];}
    function uniq(a){var o=[];a.forEach(function(x){if(o.indexOf(x)<0)o.push(x);});return o.sort();}
    // ── boot the tab against the fixtures ──
    out.boot=w.eval("(function(){try{"
      +"window.renderAuth=function(){};window._qeProbeErrors=[];"
      +"window.onerror=function(m){window._qeProbeErrors.push(String(m));};"
      +"currentUser=currentUser||{uid:'probe-uid'};"
      +"try{prefs.theme="+JSON.stringify(THEME)+";applyTheme();}catch(e){document.documentElement.setAttribute('data-theme',"+JSON.stringify(THEME)+");}"
      +"window._qqqExec="+JSON.stringify(EXEC)+";"
      +"window._qqqExecLoaded=true;window._qqqExecLoading=false;window._qqqExecErr=null;"
      +"window._qqqPaper=null;window._qqqPaperLoaded=true;window._qqqPaperLoading=false;window._qqqPaperErr=null;"
      +"window._qqqCalMonth=null;window._qeDrawerIdx=null;window._qeChartHidden={};window._qeTradesShown=50;window._qeEventsShown=30;"
      +"window._qbSheet=null;window._qbLegOpen=new Set();window._qbLegNoteOpen={};window._qeTradesView='list';window._qeChartPeriod='ALL';homeRange='ALL';"
      +"window._oldCandleSVG="+(OLDSVG?OLDSVG:'null')+";"
      +"activeTab='augur';augurSub='qqqpaper';renderApp();return 'OK';"
      +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
    // the box's day docs arrive through the page's own test hook -- no Firestore
    w._probeReads=[];
    w._qqqBarsSource=function(date){w._probeReads.push(date);return Promise.resolve(DAYS[date]?JSON.parse(JSON.stringify(DAYS[date])):null);};
    // the PC's get_bars: counted, answered with a flat synthetic session
    w._probeCmds=[];
    w._runCmd=function(action,payload){w._probeCmds.push({action:action,entry:payload&&payload.entry_time,tf:payload&&payload.timeframe});
      if(action!=='get_bars')return Promise.reject(new Error('probe: no '+action));
      var day=String(payload.entry_time||'2026-09-25 10:00').slice(0,10),bars=[];
      for(var i=0;i<78;i++){var m=570+5*i,p=740+Math.sin(i/5);bars.push({t:day+' '+('0'+Math.floor(m/60)).slice(-2)+':'+('0'+m%60).slice(-2),o:p,h:p+0.4,l:p-0.4,c:p+0.1,v:1000});}
      return Promise.resolve({bars:bars,entry_idx:20,exit_idx:30,overlays:{},meta:{master:'QQQ_5m (probe PC)'}});};
    function rerender(){w.eval('renderApp()');}
    // a trade row of the shared list frame (LEDGER step 8): its key is the trade's row key, QE:<trade id>
    function tradeRowSel(tid){return '[data-lgtrade="QE:'+tid+'"]';}
    // a tap on the row's strategy cell opens TRADING-LOG's shared trade panel (LEDGER step 9): the chart slot holds the compact chart,
    // the numbers slot the breakdown
    async function openSheet(tid){
      var row=q(tradeRowSel(tid));if(!row)return {err:'no row '+tid};
      (row.querySelector('.lg-c-sym')||row).click();
      var sv=await waitFor(function(){var p=q('.lg-panel[data-lgpanel-trade="QE:'+tid+'"]'),b=p&&p.querySelector('[data-qbcandlesbody]');return b&&(b.querySelector('svg')||/no candles/.test(b.textContent))?b:null;},8000);
      var sheet=q('.lg-panel');
      var svg=sv&&sv.querySelector('svg');
      return {opened:!!sheet,hasSvg:!!svg,kinds:uniq(kinds(sv)),
        shade:!!(svg&&svg.querySelector('rect[opacity="0.05"]')),
        texts:svg?[].slice.call(svg.querySelectorAll('text')).map(function(t){return t.textContent.trim();}):[],
        expand:!!q('.lg-panel [data-qbcandlesexpand]'),
        legend:(q('.lg-panel .qb-candle-legend')||{}).textContent||'',body:(sv||{}).textContent||'',
        hasDrawer:!!q('.lg-panel [data-lgpanel-slot="numbers"] .lg-panel-row'),
        html:sheet?sheet.innerHTML:''};
    }
    async function closeSheet(){var c=q('[data-lgpanel-close]');if(c){c.click();await waitFor(function(){return !q('.lg-panel');},3000);}}
    function viewerState(){var m=qa('#chart-body svg');var sv=m.length?m[m.length-1]:null;
      return {open:!!q('#chart-body'),kinds:uniq(kinds(sv)),shade:!!(sv&&sv.querySelector('rect[opacity="0.05"]')),
        view:w.eval('(_cndl&&_cndl.view)?_cndl.view.slice():null'),nbars:w.eval('(_cndl&&_cndl.r&&_cndl.r.bars)?_cndl.r.bars.length:null'),
        sub:(q('#chart-sub')||{}).textContent||'',legend:(q('#cndl-legend')||{}).textContent||'',
        zoom:(q('#cndl-zoom')||{}).textContent||'',tid:w.eval('(_cndl&&_cndl.x)?_cndl.x._tid:null'),
        src:w.eval('(_cndl&&_cndl.r)?(_cndl.r.src||"pc"):null'),tf:w.eval('(_cndl&&_cndl.r)?(_cndl.r.tf||null):null')};}
    function closeViewer(){var b=q('#chart-close');if(b)b.click();}
    await waitFor(function(){return q('[data-lgtrade]');},8000);
    out.listRows=qa('[data-lgtrade]').length;

    if(MODE==='sheet_noise'||MODE==='viewer_noise'){
      out.noise=await openSheet(NOISE_ID);
      if(MODE==='viewer_noise'){var eb=q('[data-qbcandlesexpand]');if(eb)eb.click();
        await waitFor(function(){return q('#chart-body svg [data-mk]');},8000);out.viewer=viewerState();}
      out.errors=w.eval('window._qeProbeErrors');return finish('shot');
    }
    if(MODE==='sheet_held'){out.held=await openSheet(HELD_ID);out.errors=w.eval('window._qeProbeErrors');return finish('shot');}
    if(MODE==='sheet_unknown'){out.unk=await openSheet(UNK_ID);delete out.unk.html;out.errors=w.eval('window._qeProbeErrors');return finish('shot');}
    if(MODE==='sheet_nodoc'){out.nodoc=await openSheet(NODOC_ID);delete out.nodoc.html;
      out.scrollW=d.body.scrollWidth;out.errors=w.eval('window._qeProbeErrors');return finish('shot');}
    if(MODE==='viewer_noise_1m'){out.noise=await openSheet(NOISE_ID);delete out.noise.html;
      var eb1=q('[data-qbcandlesexpand]');if(eb1)eb1.click();
      await waitFor(function(){return q('#chart-body svg [data-mk]');},8000);
      var t1m=q('[data-cndltf="1m"]');if(t1m)t1m.click();
      await waitFor(function(){return w.eval('(_cndl&&_cndl.r)?_cndl.r.tf:null')==='1m';},8000);await sleep(200);
      out.viewer=viewerState();
      var sr=q('#chart-body svg [data-mk="signal"] rect');out.sigW=sr?+sr.getAttribute('width'):null;
      out.errors=w.eval('window._qeProbeErrors');return finish('shot');}
    if(MODE==='sheet_enguq'){out.engu=await openSheet(ENGU_ID);
      out.scrollW=d.body.scrollWidth;out.errors=w.eval('window._qeProbeErrors');return finish('shot');}

    // ── EOD pass: the 09-28 doc exactly as the 16:10 run writes it (5m through 15:50,
    //    1m through 15:58) -- every end-of-day exit lies after its last bar ──
    if(MODE==='eod'){
      async function rbFor(tid,tf){var x=(w._qeCandleRows||[]).filter(function(r){return r._tid===tid;})[0];
        var rb=x?await w._qqqBarsForTrade(x,tf):null;
        return rb?{n:rb.bars.length,exit_idx:rb.exit_idx,after:rb.exit_after_last,last:rb.bars[rb.bars.length-1].t,asof:rb.asof}:null;}
      out.orbRb=await rbFor(ORB_ID);
      out.enguRb=await rbFor(ENGU_ID);
      out.noiseRb=await rbFor(NOISE_ID);
      out.orb=await openSheet(ORB_ID);delete out.orb.html;
      var eb2=q('[data-qbcandlesexpand]');if(eb2)eb2.click();
      await waitFor(function(){return q('#chart-body svg [data-mk]');},8000);await sleep(150);
      out.orbViewer=viewerState();closeViewer();await closeSheet();
      out.engu=await openSheet(ENGU_ID);delete out.engu.html;await closeSheet();
      out.noise=await openSheet(NOISE_ID);delete out.noise.html;await closeSheet();
      out.errors=w.eval('window._qeProbeErrors');return finish('eod');
    }

    // ── FULL pass ──────────────────────────────────────────────────────────────
    // 1. byte identity of run-report charts vs origin/main's candleSVG
    out.bytes=w.eval("(function(){try{if(!window._oldCandleSVG)return {skipped:'no old source'};"
      +"function mk(day0,nd,nb){var b=[];for(var k=0;k<nd;k++){var dd='2026-09-'+('0'+(day0+k)).slice(-2);for(var i=0;i<nb;i++){var m=570+5*i,p=18000+50*Math.sin((k*nb+i)/7);b.push({t:dd+' '+('0'+Math.floor(m/60)).slice(-2)+':'+('0'+m%60).slice(-2),o:p,h:p+9,l:p-7,c:p+(i%3-1)*4});}}return b;}"
      +"var one=mk(21,1,60),three=mk(21,3,40);"
      +"var ov={vwap:one.map(function(b,i){return i<3?null:b.c-2;}),ub:one.map(function(b){return b.h+5;}),lb:one.map(function(b){return b.l-5;})};"
      +"var cases=["
      +"[one,ov,{entryIdx:12,exitIdx:30,entryPrice:18010.25,exitPrice:18042.5,side:'long',pnlUsd:640,shadeFrom:12,shadeTo:30},{}],"
      +"[one,{},{entryIdx:40,exitIdx:41,entryPrice:18030,exitPrice:18012,side:'short',pnlUsd:-360},{yZoom:1.6}],"
      +"[three,{},{entryIdx:50,exitIdx:95,entryPrice:18000,exitPrice:18020,side:'long',pnlUsd:400,shadeFrom:50,shadeTo:95},{yRange:[17900,18100]}],"
      +"[one,{},{entryIdx:5,entryPrice:18001,side:'long',pnlUsd:0},{height:300}],"
      +"[one,{},{exitIdx:59,exitPrice:18050,pnlUsd:-5},{width:700,height:240}],"
      +"[one,{},{},{}],[[],{},{},{}]];"
      +"var res=[];cases.forEach(function(c,k){var a=window._oldCandleSVG(c[0],c[1],c[2],c[3]);"
      +"var b=window.candleSVG(c[0],c[1],JSON.parse(JSON.stringify(c[2])),c[3]);"
      +"var e=Object.assign(JSON.parse(JSON.stringify(c[2])),{points:[],lines:[]});var c2=window.candleSVG(c[0],c[1],e,c[3]);"
      +"res.push({k:k,same:a===b,sameEmpty:a===c2,len:a.length});});return res;"
      +"}catch(e){return {err:String(e&&e.stack||e)};}})()");

    // 2. a run-report trade in the real viewer: same arguments + bytes as the old function
    out.runViewer=await (async function(){
      var calls=[];var orig=w.candleSVG;
      w.candleSVG=function(b,o,m,op){var s=orig(b,o,m,op);calls.push({b:b,o:o,m:m,op:op,s:s});return s;};
      w.eval("window._openTradeCandles({_no:7,_et:'2026-09-25 10:00',_xt2:'2026-09-25 12:30',_ep:740.1,_xp:740.3,_pts:0.2,_usd:40,_side:'long'},null,{B:{run_id:123,instrument:'NQ',timeframe:'5m',session:'rth'},all:function(){return [];},order:function(){return [];}})");
      await waitFor(function(){return calls.length&&q('#chart-body svg line');},8000);
      await sleep(200);
      var last=calls[calls.length-1],r={calls:calls.length,legend:!!q('#cndl-legend')};
      if(last&&w._oldCandleSVG){r.noPoints=!('points' in last.m)&&!('lines' in last.m)&&!('hideSideGlyph' in last.m);
        r.same=(w._oldCandleSVG(last.b,last.o,last.m,last.op)===last.s);}
      w.candleSVG=orig;closeViewer();return r;})();
    w._probeCmds.length=0;

    // 3. LIST sheets: every marker kind + legend wording
    out.noise=await openSheet(NOISE_ID);await closeSheet();
    out.engu=await openSheet(ENGU_ID);await closeSheet();
    out.orb=await openSheet(ORB_ID);await closeSheet();
    out.bookonly=await openSheet(BOOKONLY_ID);await closeSheet();
    out.held=await openSheet(HELD_ID);await closeSheet();
    out.net=await openSheet(NET_ID);await closeSheet();
    out.unk=await openSheet(UNK_ID);await closeSheet();
    out.nodoc=await openSheet(NODOC_ID);await closeSheet();
    ['noise','engu','orb','bookonly','held','net','unk','nodoc'].forEach(function(k){if(out[k]){
      out[k].undef=(out[k].html.match(/undefined/g)||[]).length;out[k].nan=(out[k].html.match(/NaN/g)||[]).length;delete out[k].html;}});
    out.pcAfterSheets=w._probeCmds.length;

    // 4. EXPAND -> full viewer, NEXT, 1m <-> 5m
    await openSheet(NOISE_ID);
    var eb=q('[data-qbcandlesexpand]');if(eb)eb.click();
    await waitFor(function(){return q('#chart-body svg [data-mk]');},8000);
    out.viewer=viewerState();
    var nb=q('#cndl-prev');if(nb)nb.click();
    await waitFor(function(){return w.eval('(_cndl&&_cndl.x)?_cndl.x._tid:null')!==NOISE_ID&&q('#chart-body svg');},8000);
    await sleep(150);
    out.viewerNext=viewerState();
    var t1=q('[data-cndltf="1m"]');out.hasTf1m=!!t1;if(t1)t1.click();
    await waitFor(function(){return w.eval('(_cndl&&_cndl.r)?_cndl.r.tf:null')==='1m';},8000);
    await sleep(150);
    out.viewer1m=viewerState();
    // plain words: the TOP-10 menu and the saved picture's name carry no trade ids
    var sel=q('#cndl-top');out.topOpts=sel?[].slice.call(sel.options).map(function(o){return o.textContent;}):null;
    // (a real download stalls headless Chrome: keep the name, skip the file)
    var oc=w.HTMLAnchorElement.prototype.click;w.HTMLAnchorElement.prototype.click=function(){if(this.download)return;return oc.call(this);};
    w._lastCandlePNG=null;var sb=q('#cndl-save');if(sb)sb.click();
    await waitFor(function(){return w._lastCandlePNG;},6000);
    out.pngName=w._lastCandlePNG?w._lastCandlePNG.name:null;
    closeViewer();await closeSheet();
    out.pcAfterViewer=w._probeCmds.length;

    // 5. TABLE view chart glyph -> box doc; a day with no doc -> the PC, once (the glyph on a row opens the full viewer, never the panel)
    var ts=q('[data-lgview="table"]');if(ts)ts.click();
    await waitFor(function(){return q('tr[data-lgtrade] [data-qbchartkey]');},8000);
    function pillFor(tid){var x=(w._qeCandleRows||[]).filter(function(r){return r._tid===tid;})[0];
      return x?[].filter.call(d.querySelectorAll('[data-qbchartkey]'),function(e){return e.getAttribute('data-qbchartkey')===String(x._no);})[0]||null:null;}
    var p=pillFor(ORB_ID);if(p)p.click();
    await waitFor(function(){return q('#chart-body svg [data-mk]');},8000);await sleep(100);
    out.tableOrb=viewerState();closeViewer();
    out.pcAfterTableOrb=w._probeCmds.length;
    p=pillFor(NODOC_ID);if(p)p.click();
    await waitFor(function(){return q('#chart-body svg line')&&/bars from your PC/.test((q('#chart-sub')||{}).textContent||'');},8000);
    out.tableNoDoc=viewerState();closeViewer();
    out.pcAfterNoDoc=w._probeCmds.length;

    // 6. cache keyed by the trade: prepend a new closed trade, every row shifts
    var before={};(w._qeCandleRows||[]).forEach(function(x,i){before[x._tid||x._no]={no:x._no,i:i};});
    w.eval("window._qqqExec.trades_all.unshift({leg:'NOISE',entry_ts:'2026-09-28 15:00:05',exit_ts:'2026-09-28 15:40:05',side:'short',shares:10,entry_px:736.5,exit_px:736.2,pnl:3,exit_reason:'signal exit',trade_id:'NOISE_382-20260928T190000Z-S'});renderApp();");
    await waitFor(function(){return (w._qeCandleRows||[]).length&&w._qeCandleRows[0]._tid==='NOISE_382-20260928T190000Z-S';},8000);
    var after=w._qeCandleRows||[],same=0,shifted=0,total=0,noiseShifted=false;
    after.forEach(function(x,i){var b=before[x._tid||x._no];if(!b)return;total++;if(b.no===x._no)same++;if(b.i!==i){shifted++;if(x._tid===NOISE_ID)noiseShifted=true;}});
    out.cacheKey={total:total,sameKey:same,shifted:shifted,noiseShifted:noiseShifted,noiseKey:(after.filter(function(x){return x._tid===NOISE_ID;})[0]||{})._no};
    p=pillFor(NOISE_ID);if(p)p.click();
    await waitFor(function(){return q('#chart-body svg [data-mk]');},8000);await sleep(100);
    out.afterShift=viewerState();closeViewer();

    out.reads=w._probeReads.slice();
    // 6b. signal bars across timeframes (unit level, on synthetic bars): a 5-minute
    //     decision bar on 1-minute bars spans the five bars inside it; a 1-minute one on
    //     5-minute bars is left off and the legend says why; a side cut inside by the trim
    out.tfSig=(function(){try{
      function mkBars(step,n){var b=[];for(var i=0;i<n;i++){var m=600+step*i;
        b.push({t:'2026-09-28 '+('0'+Math.floor(m/60)).slice(-2)+':'+('0'+m%60).slice(-2),o:1,h:2+(i%3)*0.1,l:0.5,c:1.5});}return b;}
      var b1=mkBars(1,30),b5=mkBars(5,10);
      var mk5={tf:'5m',side:'long',signal:{t:'2026-09-28 10:10',rule:'recorded'},book_in:{t:'2026-09-28 10:15:05',px:1.5}};
      var pp=w._qbMarkPoints(mk5,b1,0,29,'1m'),sp=pp.points.filter(function(p){return p.kind==='signal';})[0]||{};
      var one=JSON.parse(JSON.stringify(sp));one.span=1;
      var wide=w.candleSVG(b1,{},{points:[sp],lines:[]},{}),narrow=w.candleSVG(b1,{},{points:[one],lines:[]},{});
      function rw(svg){var m=/data-mk="signal"><title>[^<]*<\/title><rect x="[^"]*" y="[^"]*" width="([^"]*)"/.exec(svg);return m?+m[1]:null;}
      var mk1={tf:'1m',side:'long',signal:{t:'2026-09-28 10:12',rule:'recorded'},wb_part:['out'],
        book_in:{t:'2026-09-28 10:12:30',px:1.5}};
      var pp5=w._qbMarkPoints(mk1,b5,0,9,'5m');
      var lg=w._qbMarkLegend(mk1,{tf:'5m',bars:b5,src:'box'},pp5,null).replace(/<[^>]+>/g,'');
      var same=w._qbMarkPoints(mk5,b5,0,9,'5m').points.filter(function(p){return p.kind==='signal';})[0]||{};
      return {spanI:sp.i,span:sp.span,wide:rw(wide),narrow:rw(narrow),coarse:pp5.coarse,
        drawn5:pp5.points.filter(function(p){return p.kind==='signal';}).length,legend:lg,
        sameI:same.i,sameSpan:same.span||1};
    }catch(e){return {err:String(e&&e.stack||e)};}})();
    // 6c. the full viewer shows a loading stub before waiting on a day not in memory
    out.stub=await (async function(){try{
      var p3=pillFor(NOISE_ID);if(p3)p3.click();     // (the trade list is on TABLE here)
      await waitFor(function(){return q('#chart-body svg [data-mk]');},8000);await sleep(150);
      w._qqqBarsReset();
      var pb=q('#cndl-prev')&&!q('#cndl-prev').disabled?q('#cndl-prev'):q('#cndl-next');pb.click();
      var r={sub:(q('#chart-sub')||{}).textContent||'',legend:(q('#cndl-legend')||{}).textContent||'',
        marks:q('#chart-body svg [data-mk]')?1:0};
      await waitFor(function(){return q('#chart-body svg [data-mk]');},8000);await sleep(150);
      r.after=viewerState().kinds.length;closeViewer();return r;
    }catch(e){return {err:String(e&&e.stack||e)};}})();
    // 7. a cached FINAL day is re-checked once per page load: a stale copy in IndexedDB
    //    is served at once, then replaced by the newer published copy in the background
    // the background re-check is real IndexedDB I/O under headless virtual time, so wait for its
    // RESULT (the newer copy in the cache) with a deadline, never a fixed sleep (flaked once: idb {});
    // a run cut short by the backstop says so here instead of an empty {}
    out.idb={pending:'step 7 started, cut short before it finished (see main: re-rendered once)'};
    out.idb=await (async function(){try{
      var D='2026-09-24',stale=JSON.parse(JSON.stringify(DAYS[D]));
      stale.published_at='2026-01-01T00:00:00-05:00';stale.marks=[];
      w._qqqBarsIdbWaitMs=0;   // virtual time: no race timer around the IndexedDB read
      await w._qqqBarsIdb.put(D,stale);w._qqqBarsReset();
      var r0=w._probeReads.length,first=await w._qqqBarsDay(D);
      await waitFor(function(){return w._probeReads.length>r0;},8000);
      var cached=null;
      for(var t0=0;t0<8000;t0+=50){cached=await w._qqqBarsIdb.get(D);
        if(cached&&cached.published_at===DAYS[D].published_at)break;await sleep(50);}
      var second=await w._qqqBarsDay(D);
      var r1=w._probeReads.length;await w._qqqBarsDay(D);
      return {firstStale:!!first&&first.published_at===stale.published_at,
        secondFresh:!!second&&second.published_at===DAYS[D].published_at,
        idbFresh:!!cached&&cached.published_at===DAYS[D].published_at,
        reads:r1-r0,readsAfter:w._probeReads.length-r1,key:w._qqqBarsIdb.key(D)};
    }catch(e){return {err:String(e&&e.stack||e)};}})();
    out.errors=w.eval('window._qeProbeErrors');
    finish('full');
  }
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){run().catch(function(e){out.err=String(e&&e.stack||e);finish('error');});},2000);});
  setTimeout(function(){finish('backstop');},85000);
})();
</script>
</body></html>
"""


def run_case(chrome, name, mode, theme, width, height, shot_path, exec_doc, days, old_src):
    # served from a private temp dir holding a COPY of index.html plus the probe page --
    # nothing is written into the repo and nothing else in it is served on loopback
    srv_root = tempfile.mkdtemp(prefix="qqqcandsrv-")
    shutil.copyfile(os.path.join(ROOT, "index.html"), os.path.join(srv_root, "index.html"))
    pdir = os.path.join(srv_root, "_qqqcandprobe")
    os.makedirs(pdir, exist_ok=True)
    ppath = os.path.join(pdir, "probe_%s.html" % name)

    def js(v):
        return json.dumps(v).replace("</", "<\\/")
    html = (PROBE_HTML.replace("__EXEC__", js(exec_doc)).replace("__DAYS__", js(days))
            .replace("__OLDSVG__", js(old_src)).replace("__THEME__", js(theme))
            .replace("__MODE__", js(mode)).replace("__BOOKONLY__", BOOKONLY_ID)
            .replace("__HELD__", HELD_ID).replace("__NET__", NET_ID).replace("__UNK__", UNK_ID)
            .replace("__IW__", str(width)).replace("__IH__", str(height)))
    io.open(ppath, "w", encoding="utf-8").write(html)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), make_handler(srv_root))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    prof = tempfile.mkdtemp(prefix="qqqcandprobe-")
    url = "http://127.0.0.1:%d/_qqqcandprobe/probe_%s.html" % (port, name)
    ww, wh = width + 40, height + 80
    try:
        outp = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
                               "--user-data-dir=" + prof, "--virtual-time-budget=90000",
                               "--window-size=%d,%d" % (ww, wh), "--dump-dom", url],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=240).stdout
        if shot_path:
            prof2 = tempfile.mkdtemp(prefix="qqqcandprobe-")
            subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
                            "--user-data-dir=" + prof2, "--virtual-time-budget=90000",
                            "--window-size=%d,%d" % (ww, wh), "--screenshot=" + shot_path, url],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=240)
            shutil.rmtree(prof2, ignore_errors=True)
    finally:
        srv.shutdown()
        srv.server_close()
        shutil.rmtree(srv_root, ignore_errors=True)
        shutil.rmtree(prof, ignore_errors=True)
    m = re.search(r"QQQCANDLES: (\{.*\})\s*</pre>", outp, re.S)
    if not m:
        return {"err": "no readout", "raw_tail": outp[-1500:]}
    return json.loads(m.group(1).replace("&quot;", '"').replace("&amp;", "&")
                      .replace("&lt;", "<").replace("&gt;", ">"))


ALL_KINDS = {"signal", "signal_out", "bt_in", "book_in", "wb_in", "wb_refused", "wb_held",
             "wb_netted", "wb_unknown", "wb_error", "bt_out", "book_out", "wb_out", "line"}


def check_full(r):
    """[(ok, what)] for one FULL-pass readout."""
    c = []

    def ok(cond, what):
        c.append((bool(cond), what))
    ok(r.get("boot") == "OK", "tab boots with the fixtures (%s)" % str(r.get("boot"))[:80])
    ok(not r.get("err"), "no probe error %s" % (r.get("err") or "")[:200])
    b = r.get("bytes")
    ok(isinstance(b, list) and b and all(x["same"] and x["sameEmpty"] for x in b),
       "run-report candleSVG byte-identical to origin/main (no lists, and empty lists): %s" % b)
    rv = r.get("runViewer") or {}
    ok(rv.get("same") and rv.get("noPoints") and not rv.get("legend"),
       "run trade in the real viewer: old bytes, no marker keys, no legend (%s)" % rv)
    n, e, o, bo, nd = (r.get(k) or {} for k in ("noise", "engu", "orb", "bookonly", "nodoc"))
    hd, nt, uk = r.get("held") or {}, r.get("net") or {}, r.get("unk") or {}
    for nm, s in (("NOISE", n), ("ENGU-Q", e), ("ORB", o), ("book-only", bo), ("held", hd), ("netted", nt),
                  ("unknown answer", uk)):
        ok(s.get("opened") and s.get("hasSvg") and s.get("hasDrawer"),
           "%s sheet: compact chart above the breakdown" % nm)
        ok(s.get("undef") == 0 and s.get("nan") == 0, "%s sheet: no undefined/NaN" % nm)
    ok({"signal", "signal_out", "bt_in", "book_in", "wb_in", "bt_out", "book_out", "wb_out"} <= set(n.get("kinds", [])),
       "NOISE markers %s" % n.get("kinds"))
    ok({"bt_in", "book_in", "wb_in", "wb_refused", "book_out", "wb_out"} <= set(e.get("kinds", []))
       and "signal" not in e.get("kinds", []), "ENGU-Q markers incl. refused close %s" % e.get("kinds"))
    ok("signal bar not recorded" in e.get("legend", ""), "ENGU-Q legend says the signal bar is not recorded")
    ok("Webull refused" in e.get("legend", ""), "ENGU-Q legend lists the refused close")
    ok({"signal", "line"} <= set(o.get("kinds", [])) and "stop" in o.get("legend", ""),
       "ORB markers + stop/target lines %s" % o.get("kinds"))
    ok("book only - no Webull order" in bo.get("legend", "") and not
       ({"wb_in", "wb_out", "wb_refused"} & set(bo.get("kinds", []))), "book-only row: no Webull markers, says so")
    ok(nd.get("opened") and not nd.get("hasSvg") and "no candles from the box" in nd.get("body", ""),
       "a day with no doc says so in the sheet")
    ok({"wb_refused", "wb_held"} <= set(hd.get("kinds", [])) and "Webull refused" in hd.get("legend", "")
       and "not sent" in hd.get("legend", "") and "held back by the book" in hd.get("legend", "")
       and "book only" not in hd.get("legend", ""),
       "a try the book held back is 'not sent - held back', not 'Webull refused' %s" % hd.get("kinds"))
    ok("wb_netted" in nt.get("kinds", []) and "no Webull order out" in nt.get("legend", "")
       and "netted against another leg" in nt.get("legend", "") and "refused" not in nt.get("legend", ""),
       "an internal cross is 'no Webull order - netted' %s" % nt.get("kinds"))
    ukl = uk.get("legend", "")
    ok({"wb_unknown", "wb_error", "wb_in"} <= set(uk.get("kinds", [])) and "wb_refused" not in uk.get("kinds", [])
       and "refused" not in ukl,
       "an unanswered send and a failed order call are never drawn or worded as refused %s" % uk.get("kinds"))
    ok("sent" in ukl and "Webull's answer unknown - then 11:00:40: the next try filled at 734.95" in ukl,
       "unknown answer: 'sent - Webull's answer unknown' + what the ledger shows came next")
    ok("Webull's answer unknown - no later answer on file" in ukl,
       "unknown answer with nothing later on file says so")
    ok("not sent" in ukl and "the order call failed: TypeError" in ukl and "held back by the book" not in ukl,
       "a failed order call reads 'not sent - the order call failed: <reason>'")
    ok("Webull in 734.95" in ukl, "the filled resend after the unknown answer is the Webull fill")
    tf = r.get("tfSig") or {}
    ok(tf.get("spanI") == 10 and tf.get("span") == 5 and tf.get("wide") and tf.get("narrow")
       and tf["wide"] > 4 * tf["narrow"] * 0.8,
       "a 5-minute signal bar on 1-minute bars is outlined across its five bars (%s)" % tf)
    ok(tf.get("sameI") == 2 and tf.get("sameSpan") == 1, "same timeframe: one bar, as before")
    ok(tf.get("coarse") == ["signal"] and tf.get("drawn5") == 0
       and "not drawn on 5m bars; switch to 1m to see it" in tf.get("legend", ""),
       "a 1-minute signal bar on 5-minute bars is left off, and the legend says why")
    ok("first exit try not on file" in tf.get("legend", ""),
       "a side cut inside by the trim says its first try is not on file")
    st = r.get("stub") or {}
    ok(not st.get("err") and "loading this day's candles from the box" in st.get("sub", "")
       and st.get("marks") == 0 and st.get("legend", "") == "" and st.get("after"),
       "full viewer: loading stub before waiting on a day not in memory, then the chart (%s)"
       % {k: st.get(k) for k in ("sub", "marks", "after", "err")})
    ok("exit signal bar 11:35" in n.get("legend", ""), "legend lists the exit signal bar")
    ok("backtest in 732.33 · 10:50" in o.get("legend", ""),
       "ORB backtest fill stamped at its fill moment (10:50, the 10:45 bar's close)")
    to = r.get("topOpts") or []
    ok(to and not [t for t in to if "QE:" in t or "_382-" in t or "Z-S" in t],
       "TOP-10 menu shows leg + time, no trade ids (%s)" % (to[2:4] if to else to))
    ok(re.match(r"^webull_[A-Za-z0-9._-]+_candles\.png$", str(r.get("pngName") or "")),
       "SAVE PNG name is plain (%s)" % r.get("pngName"))
    idb = r.get("idb") or {}
    ok(idb.get("firstStale") and idb.get("secondFresh") and idb.get("idbFresh") and idb.get("readsAfter") == 0
       and str(idb.get("key", "")).startswith("c2:"),
       "a cached final day is served, re-checked once in the background and replaced (%s)" % idb)
    allk = set(n.get("kinds", [])) | set(e.get("kinds", [])) | set(o.get("kinds", [])) | set(bo.get("kinds", []))
    allk |= set(hd.get("kinds", [])) | set(nt.get("kinds", [])) | set(uk.get("kinds", []))
    ok(ALL_KINDS <= allk, "every marker kind drawn somewhere: missing %s" % sorted(ALL_KINDS - allk))
    ok("no stop or target lines" in n.get("legend", ""), "legend says stop/target are not recorded")
    ok("the box" in n.get("legend", "") and "through" in n.get("legend", ""), "legend names the box bars + as-of time")
    ok(r.get("pcAfterSheets") == 0, "sheets made no PC trip (%s)" % r.get("pcAfterSheets"))
    v, vn, v1 = (r.get(k) or {} for k in ("viewer", "viewerNext", "viewer1m"))
    ok(v.get("src") == "box" and v.get("tid") and "NOISE_382-20260928T141500Z-S" == v.get("tid"),
       "EXPAND opens the full viewer on the box bars for this trade (%s)" % v.get("tid"))
    ok("/" in v.get("zoom", "") and v.get("legend"), "viewer opens zoomed to the trade + legend (%s)" % v.get("zoom"))
    ok("the box" in v.get("sub", ""), "viewer sub line names the box bars")
    ok(vn.get("tid") and vn.get("tid") != v.get("tid") and vn.get("kinds"), "PREV walks to another trade with markers")
    ok(r.get("hasTf1m") and v1.get("tf") == "1m" and v1.get("src") == "box" and v1.get("kinds"),
       "1m switch comes from the same day doc")
    ok(r.get("pcAfterViewer") == 0, "viewer made no PC trip (%s)" % r.get("pcAfterViewer"))
    t = r.get("tableOrb") or {}
    ok(t.get("src") == "box" and t.get("tid") == "ORB_R6-20260928T144500Z-S" and "line" in t.get("kinds", []),
       "TABLE CHART pill opens the box chart (%s)" % t.get("tid"))
    ok(r.get("pcAfterTableOrb") == 0, "TABLE pill made no PC trip")
    nd2 = r.get("tableNoDoc") or {}
    ok(r.get("pcAfterNoDoc") == 1 and nd2.get("src") == "pc" and "bars from your PC" in nd2.get("sub", ""),
       "no doc -> exactly one PC trip, labelled (%s)" % r.get("pcAfterNoDoc"))
    ck = r.get("cacheKey") or {}
    # the shared list draws the rows by close day (LEDGER step 8), so the rows that closed after the new trade keep their place: most rows
    # shift, the NOISE trade among them, and every row keeps its trade key
    ok(ck.get("total") and ck.get("sameKey") == ck.get("total") and ck.get("shifted", 0) >= ck.get("total") // 2 and ck.get("noiseShifted")
       and str(ck.get("noiseKey", "")).startswith("QE:NOISE_382-20260928T141500Z-S"),
       "the rows shifted (the NOISE trade's among them) but each kept its trade key (%s)" % ck)
    a = r.get("afterShift") or {}
    ok(a.get("tid") == "NOISE_382-20260928T141500Z-S", "after the shift the pill opens the same trade")
    ok(not r.get("errors"), "no console errors %s" % r.get("errors"))
    reads = r.get("reads") or []
    ok(len(reads) <= 6, "day docs read once each, then cached (%s reads)" % len(reads))
    return c


def check_eod(r):
    """[(ok, what)] for the EOD readout (the unmodified 16:10 doc)."""
    c = []

    def ok(cond, what):
        c.append((bool(cond), what))
    ok(r.get("boot") == "OK" and not r.get("err"), "eod: boots (%s)" % (r.get("err") or r.get("boot")))
    orb, eng, noi = (r.get(k) or {} for k in ("orbRb", "enguRb", "noiseRb"))
    ok(orb.get("n") == 77 and orb.get("last", "").endswith("15:50") and orb.get("after")
       and orb.get("exit_idx") == orb.get("n", 0) - 1,
       "ORB 15:59 exit after the 15:50 bar: exit index = the last bar (%s)" % orb)
    ok(eng.get("last", "").endswith("15:58") and eng.get("after") and eng.get("exit_idx") == eng.get("n", 0) - 1,
       "ENGU-Q 1m exit after the 15:58 bar: exit index = the last bar (%s)" % eng)
    ok(noi.get("after") is False and noi.get("exit_idx") is not None and noi.get("exit_idx") < noi.get("n", 0) - 1,
       "a mid-day exit is untouched (%s)" % noi)
    s, v, e, n = (r.get(k) or {} for k in ("orb", "orbViewer", "engu", "noise"))
    ok(s.get("hasSvg") and s.get("shade") and {"book_out", "wb_out"} <= set(s.get("kinds", [])),
       "ORB sheet: shaded to the end, exits marked on the last bar %s" % s.get("kinds"))
    ok("15:50" in s.get("texts", []), "ORB sheet view ends at the 15:50 bar")
    ok("after the last published bar" in s.get("legend", "") and "not on this view" not in s.get("legend", ""),
       "ORB legend says the exit is after the last published bar")
    ok(v.get("shade") and v.get("view") and v.get("nbars") and v["view"][1] == v["nbars"] - 1
       and "book_out" in v.get("kinds", []),
       "ORB viewer: zoom runs to the last bar, shaded, exit marked (%s / %s)" % (v.get("view"), v.get("nbars")))
    ok("after the last published bar" in v.get("legend", ""), "ORB viewer legend says so too")
    ok(e.get("shade") and {"book_out", "wb_out", "wb_refused"} <= set(e.get("kinds", []))
       and "after the last published bar" in e.get("legend", ""),
       "ENGU-Q sheet: shaded to 15:58, refused + retried close marked %s" % e.get("kinds"))
    ok(n.get("shade") and "after the last published bar" not in n.get("legend", ""),
       "NOISE 11:40 exit: no after-the-last-bar note")
    for k in ("orb", "engu", "noise"):
        x = r.get(k) or {}
        ok(x.get("undef") in (None, 0) and x.get("nan") in (None, 0), "eod %s: no undefined/NaN" % k)
    ok(not r.get("errors"), "eod: no console errors %s" % r.get("errors"))
    return c


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    chrome = find_chrome()
    if not chrome:
        print("INCONCLUSIVE -- chrome not found")
        return 2
    out_dir = (os.path.abspath(sys.argv[1]) if len(sys.argv) > 1
               else os.path.join(tempfile.gettempdir(), "qqq_candles_probe"))
    os.makedirs(out_dir, exist_ok=True)
    ex, days, old = build_exec(), build_days(), old_candle_svg_source()
    days_real = build_days(synthetic_tail=False)
    fails = 0
    for theme in ("dark", "paper", "mono"):
        r = run_case(chrome, "full_" + theme, "full", theme, 1366, 900, None, ex, days, old)
        # KNOWN FLAKE (2026-10-08, 2 runs in 10): step 7's IndexedDB re-check is real I/O, which headless
        # Chrome's virtual time does not wait for, so on a loaded machine the clock can jump to the backstop
        # while it is still pending ('cut short' below; before then an empty {}). That is the instrument, not
        # the page: re-render the case ONCE and say so. A finished step with wrong values is never retried.
        if (r.get("idb") or {}).get("pending"):
            print("NOTE [%s] the IndexedDB re-check step was cut short by headless virtual time (%s) - "
                  "re-rendering this case once" % (theme, r.get("why")))
            r = run_case(chrome, "full_" + theme, "full", theme, 1366, 900, None, ex, days, old)
        for good, what in check_full(r):
            print(("PASS " if good else "FAIL ") + "[%s] %s" % (theme, what))
            fails += 0 if good else 1
    for theme in ("dark", "mono"):
        r = run_case(chrome, "eod_" + theme, "eod", theme, 1366, 900, None, ex, days_real, old)
        for good, what in check_eod(r):
            print(("PASS " if good else "FAIL ") + "[eod %s] %s" % (theme, what))
            fails += 0 if good else 1
    shots = [("sheet_noise", "sheet_noise", t, 1366, 900) for t in ("dark", "paper", "mono")]
    shots += [("sheet_enguq", "sheet_enguq", t, 1366, 900) for t in ("dark", "mono")]
    shots += [("sheet_held", "sheet_held", t, 1366, 900) for t in ("dark", "mono")]
    shots += [("sheet_unknown", "sheet_unknown", t, 1366, 900) for t in ("dark", "mono")]
    shots += [("sheet_enguq_phone", "sheet_enguq", "mono", 390, 844),
              ("sheet_nodoc_phone", "sheet_nodoc", "mono", 390, 844),
              ("viewer_noise", "viewer_noise", "dark", 1366, 900),
              ("viewer_noise", "viewer_noise", "mono", 1366, 900),
              ("viewer_noise_1m", "viewer_noise_1m", "mono", 1366, 900)]
    for base, mode, theme, w, h in shots:
        name = "%s_%s_%dx%d" % (base, theme, w, h)
        shot = os.path.join(out_dir, "qqq_candles_%s.png" % name)
        r = run_case(chrome, name, mode, theme, w, h, shot, ex, days, old)
        sheet = r.get("noise") or r.get("engu") or r.get("held") or r.get("unk") or {}
        good = sheet.get("hasSvg") and not r.get("errors") and not r.get("err")
        if mode == "viewer_noise":
            good = good and (r.get("viewer") or {}).get("kinds")
        if mode == "viewer_noise_1m":
            v = r.get("viewer") or {}
            # the 11:35 exit signal bar is in view: its outline spans five 1-minute bars
            good = good and v.get("tf") == "1m" and "signal" in v.get("kinds", []) and (r.get("sigW") or 0) > 12
        if mode == "sheet_unknown":
            good = good and {"wb_unknown", "wb_error"} <= set(sheet.get("kinds", [])) \
                and "refused" not in sheet.get("legend", "")
        if mode == "sheet_nodoc":
            nd = r.get("nodoc") or {}
            good = (nd.get("opened") and "no candles from the box" in nd.get("body", "")
                    and "EXPAND" not in nd.get("body", "") and "wider screen" in nd.get("body", "")
                    and not nd.get("expand") and not r.get("errors") and not r.get("err"))
        if w <= 400:
            good = good and (r.get("scrollW") or 0) <= w + 2
        print(("PASS " if good else "FAIL ") + "shot %s -> %s" % (name, shot))
        fails += 0 if good else 1
    print("RESULT: %s (%d failing checks)" % ("PASS" if not fails else "FAIL", fails))
    return 0 if not fails else 1


if __name__ == "__main__":
    try:   # any Chrome this run starts dies with it, however the run ends (tools/kill_on_exit.py)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import kill_on_exit
        kill_on_exit.install()
    except Exception:
        pass
    sys.exit(main())
