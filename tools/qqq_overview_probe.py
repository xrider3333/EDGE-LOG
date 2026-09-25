#!/usr/bin/env python3
"""
tools/qqq_overview_probe.py -- verification probe for the QQQ SHADOW BOOK tab.

REWRITTEN 2026-09-24 for the Robinhood re-composition (owner ask: "make more like
robinhood pls. peep the real trading log" -- a two-column shell on a laptop, a big
headline + edge-to-edge chart, a thin status strip, hairline-separated sections instead
of boxed qb-cards, and a Robinhood "Strategies" sidebar). This SUPERSEDES the 2026-09-08
"qb-" re-composition this file used to describe -- every qb- class/data-attribute from
that pass is still there and still wired (nothing renamed), but the SHELL around it moved:

  .qb-shell now contains, top to bottom in DOM order --
    .qbx-hero        the headline: title, big net-P&L number, "+$X (+Y%) today" delta,
                      since-label, book-only note
    .qbx-chart       the .qb-chart-wrap chart (now 300px tall, edge to edge) + the
                      1W/1M/3M/ALL period control as text tabs BELOW it (qbx-chart-tabs)
                      + a hover crosshair (qbCrossLine/qbCrossDot/qbChartReadout) + the
                      legend, then .qbx-status-strip (status sentence + attention chips +
                      Refresh -- this REPLACES the old top-right hero chip row)
    .qbx-side        the "Strategies" sidebar (>=1100px: sticky right column) -- the
                      SAME per-leg qb-row/data-qblegrow markup as before, now also
                      showing a live position line (side/shares/entry/live price/open
                      P&L) sourced from QE.positions_live when a leg holds one -- plus a
                      compact Orders summary (mode pill/daily-stop bar/last-order line)
    .qbx-account     Webull equity/today's change/cash/as-of + the "Webull holds X /
                      legs sum to X" check (per-leg position detail lives in the
                      sidebar now, not duplicated here)
    .qbx-stats       win rate/profit factor/trades/max drawdown as a plain key-value
                      row (.qbx-stat-strip/.qbx-stat-cell, no boxed tiles) + "More
                      stats" (unchanged -- still carries every RATIOS/PERFORMANCE/RISK
                      label the old .ov-rail rail carried; QB_OLD_RAIL_LABELS below)
    .qbx-history     the Trades card (List | Table qb-seg, CSV button, List rows open a
                      qb-sheet with the SAME drawer breakdown as before) + Today's orders
    .qbx-activity    the calendar + "Feed & signals" disclosure (unchanged)
    .qbx-system      ONE new collapsed disclosure (data-qbdisclosure="system", CLOSED BY
                      DEFAULT) holding Status, the full Orders card, "Ready for real
                      shares?", and Integrity -- all four moved here as a group; their
                      OWN content/sheets/disclosures are byte-for-byte the same as
                      before, only their card wrappers and where they sit changed. Being
                      closed by default means none of this is in the DOM on first paint,
                      which is why the structural matrix below now checks for the
                      disclosure control itself (hasSystemDisclosure) rather than the
                      readiness card as a proxy for "hero+chart+tiles rendered", and why
                      the DEEP pass fires this disclosure FIRST before allchecks/any
                      integrity sheet (both now nested inside it).
    .qbx-footer      Rails / Event timeline / Model reference (unchanged)

Below 1100px every qbx- section is a plain block (no grid), so the DOM order above IS
the mobile reading order -- deliberately Strategies-then-Account (a Robinhood mobile
screen), not the old design's interleaved chart/ready, tiles/legs, activity/integrity
pairing.

Renders augurSub='qqqpaper' against these fixtures --
  real      : the real ~2-trade doc (oldest degrade path, minimal data)
  mock      : a synthetic ~40-trade / 3-leg doc carrying every field (readiness NOT
              ready, events of every kind, signals/feed history, repriced trades,
              latency)
  ready     : the same book with every readiness gate passing
  degrade   : the same book with every optional field stripped out
  alarms    : every alert condition ON at once
  healthy   : every alert condition OFF -- proves nothing gets painted with the
              attention colours when there is nothing to flag
  flat      : (NEW 2026-09-24) mock's data with NO open positions at all -- positions={}
              and positions_live.legs=[] -- plus QE.equity/QE.broker/QE.keel, which no
              other fixture carries
  positions : (NEW 2026-09-24) mock's data with an ORB LONG and an ENGUQ SHORT live
              position (QE.positions_live, live prices, open P&L), QE.equity, QE.broker,
              QE.keel, and a NOISE trade (trades_all[0]) whose KEEL drawer text must
              read "2.00 x KEEL 1.50 = 3.00 ... wanted 30 sh" (owner spec) -- see
              tools/fixtures/qqq_exec_positions.json and its generator note.
at three widths -- 1400 / 800 / 390 -- in BOTH [data-theme="mono"] and the default
(dark, no data-theme attribute) theme, 4 fixtures (real/mock/alarms/degrade) x 3 widths x
2 themes = 24 structural passes (no undefined/NaN, no console errors, no horizontal body
overflow at 390, hero+chart+stat-strip present, System disclosure reachable). A deeper
interaction pass (More stats expand, trades List/Table toggle + row count, a trade row
opening its sheet, each Integrity row opening its sheet, the period control changing the
plotted point count) runs on the 'mock' fixture at 1400 in both themes. 'ready' proves
the compact readiness card reads READY; 'alarms'/'healthy' under mono (plus a
default-theme 'alarms' regression pass) prove the --attn-red/--attn-amber/--attn-ok
colours still render non-grey.

ROBINHOOD RE-COMPOSITION MATRIX (2026-09-24, ROBINHOOD_SIZES below) -- the owner's own
laptop/phone acceptance-test sizes: 1366x768 and 1536x864 (laptops), 1600x1000 (owner
circled an empty band on the old layout at this size), 390x844 (phone). Each size x
{flat, positions} fixture x {mono, dark} theme = 16 named screenshots
(rh_<fixture>_<w>x<h>_<theme>.png). LAPTOP FOLD ACCEPTANCE checks, at 1366x768 and
1536x864 in mono, that the headline (.qbx-hero), the FULL chart (.qb-chart-wrap) and the
FIRST sidebar row (.qbx-side [data-qblegrow]) all sit at or above the viewport height --
this REPLACES the old 2026-09-08 density pass's tilesBottom/readinessBottom check against
.qb-sec-tiles/.qb-sec-ready, which no longer exist now that those cards lost their qb-card
wrapper and moved into qbx-stats/qbx-system. A dedicated 'keel_drawer_positions' case
opens the 'positions' fixture's first (newest) trade row and asserts its KEEL drawer text.

LIVE P&L PASS (2026-09-25, owner: "make it simple ... for postions put any open pnl and
then total ... whyd doesnt it show live pnl") -- two more dedicated, non-screenshot cases:
'livepnl_positions' (LIVEPNL flag, 'positions' fixture) proves the ENGU-Q/NOISE notes are
hidden by default, appear after tapping that leg's own info toggle without opening its
row-expand drawer, that a held leg's sidebar line reads "Open ..." then "Total ..." with
Total = closed + open P&L, and that ACCOUNT lists each open position before the Total open
P&L line -- all read straight off QPOSLIVE.legs, so they can never disagree with the hero.
'listener_wiring_check' (LISTENERCHECK flag) swaps in a fake db/auth with a working
onSnapshot and calls _qqqExecEnsureLive() twice in a row (standing in for a second
renderApp() pass), proving it does not throw and never stacks a second listener.

Not wired into wt.py ship (ad hoc verification tool), but written the same way as
tools/paper_render_probe.py: stdlib + a subprocess call to local headless Chrome,
serving the repo over loopback so index.html's own fetches never fire.
"""
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

# Every RATIOS/PERFORMANCE/RISK label the pre-redesign .ov-rail sidebar carried. The new
# "More stats" disclosure must still carry all of these -- the PARITY/FEED UPTIME/
# SIGNALS/REPRICE groups moved to the new INTEGRITY list+sheets by design (owner spec
# section 8), so they are deliberately NOT in this list.
QB_OLD_RAIL_LABELS = [
    'WIN RATE', 'PROFIT FACTOR', 'EXPECTANCY', 'PAYOFF',
    'TRADES', 'AVG $/TRADE', 'AVG WIN', 'AVG LOSS', 'BEST', 'WORST', 'CURRENT STREAK',
    'MAX DRAWDOWN', 'RECOVERY FACTOR', 'OPEN EXPOSURE', 'DAILY LOSS LIMIT',
]


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


PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>qqq overview probe</title></head>
<body style="margin:0;background:#0a0a12">
<iframe id="f" src="../index.html" style="width:__IW__px;height:__IH__px;border:0"></iframe>
<!-- REVIEW FIX (2026-09-24): this debug readout used to sit in normal flow right below
     the iframe, so every screenshot showed a line of raw JSON (and, on some fixtures, a
     harness-page horizontal scrollbar caused by THAT long unwrapped line) that had
     nothing to do with the app being tested. FIRST attempt was position:absolute;
     left:-99999px -- not enough: the readout can be tens of thousands of characters on
     one unwrapped white-space:pre line, so at typical monospace character widths the
     line is still hundreds of thousands of px wide and starting it at -99999px left a
     LATER slice of that same line crossing back through the visible viewport (seen as a
     stray fragment of JSON text near the top of qqq_overview_rh_positions_1366x768_
     mono.png). display:none is the actual fix -- it removes the element from rendering
     entirely (no box, no text laid out anywhere, so it truly cannot show up in a
     screenshot or contribute to scrollWidth at any string length) while leaving it
     fully intact for --dump-dom, which serialises the DOM's markup/text content as
     HTML, not the rendered/painted page -- a display:none element's innerHTML/
     textContent is untouched, so the regex extraction below still finds it. -->
<pre id="o" style="display:none;margin:0;white-space:pre"></pre>
<script>
var FIX=__FIX__;
var THEME=__THEME__;
var DEEP=__DEEP__;
var KEEPSHEET=__KEEPSHEET__;
var OPENCHECKS=__OPENCHECKS__;
var IW=__IW__;
// LIVEPNL/LISTENERCHECK (2026-09-25, live-P&L pass): see the module docstring addendum
// below the ROBINHOOD_SIZES comment for what each one drives.
var LIVEPNL=__LIVEPNL__;
var LISTENERCHECK=__LISTENERCHECK__;
(function(){
  var reported=false;
  function report(why){
    if(reported)return; reported=true;
    var out={why:why};
    try{
      var fr=document.getElementById('f'), w=fr.contentWindow, d=fr.contentDocument;
      out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
      out.call=w.eval("(function(){try{"
        +"window.renderAuth=function(){};"
        +"window._qeProbeErrors=[];"
        +"window.onerror=function(m,s,l,c,e){window._qeProbeErrors.push(String(m));};"
        +"currentUser=currentUser||{uid:'probe-uid'};"
        +"try{prefs.theme="+JSON.stringify(THEME)+";applyTheme();}catch(e){try{document.documentElement.setAttribute('data-theme',"+JSON.stringify(THEME)+");}catch(e2){}}"
        +"window._qqqExec="+JSON.stringify(FIX)+";"
        +"window._qqqExecLoaded=true;window._qqqExecLoading=false;window._qqqExecErr=null;"
        +"window._qqqPaper=null;window._qqqPaperLoaded=true;window._qqqPaperLoading=false;window._qqqPaperErr=null;"
        +"window._qqqCalMonth=null;window._qeDrawerIdx=null;window._qeChartHidden={};window._qeTradesShown=50;window._qeEventsShown=30;"
        +"window._qbSheet=null;window._qbLegOpen=new Set();window._qbLegNoteOpen={};window._qeTradesView='list';window._qeChartPeriod='ALL';"
        +"activeTab='augur';augurSub='qqqpaper';renderApp();return 'OK';"
        +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
      out.themeApplied=d.documentElement.getAttribute('data-theme');

      function fire(sel){var el=d.querySelector(sel);if(el){el.click();return true;}return false;}
      function html(){var ap=d.getElementById('app')||d.body;return ap?ap.innerHTML:'';}

      // ── structural counts on the FIRST paint (ALL cases) ──
      out.hasQbShell=!!d.querySelector('.qb-shell');
      out.hasHero=!!d.querySelector('.qb-hero-num');
      out.heroText=(d.querySelector('.qb-hero-num')||{}).textContent||null;
      out.hasChart=!!d.querySelector('.qb-chart-wrap svg');
      // ROBINHOOD RE-COMPOSITION (2026-09-24): the 4 boxed qb-tiles are now a plain
      // qbx-stat-strip/qbx-stat-cell key-value row (owner spec: "a clean key-value
      // row"). hasReadinessCard used to prove "hero+chart+tiles rendered" by checking
      // for the readiness card's .qb-bar -- that card (and Status/Orders/Integrity
      // beside it) now lives inside the NEW "System" disclosure, CLOSED BY DEFAULT, so
      // it is correctly absent from first paint; hasSystemDisclosure checks the
      // collapsed CONTROL itself is present/reachable instead.
      out.statCellCount=d.querySelectorAll('.qbx-stat-cell').length;
      out.hasSystemDisclosure=!!d.querySelector('[data-qbdisclosure="system"]');
      out.hasSidebar=!!d.querySelector('.qbx-side');
      out.sidebarRowCount=d.querySelectorAll('.qbx-side [data-qblegrow]').length;
      out.hasStatusStrip=!!d.querySelector('.qbx-status-strip');
      out.legRowCount=d.querySelectorAll('[data-qblegrow]').length;
      out.bodyScrollW=d.body?d.body.scrollWidth:null;
      out.overflowOk=(out.bodyScrollW==null)||(out.bodyScrollW<=IW+2);

      // ── ROBINHOOD RE-COMPOSITION fold measurement (2026-09-24, owner: "at 1366x768
      // and at 1536x864 the headline number, the whole chart and the top of the
      // sidebar list are visible WITHOUT scrolling") -- getBoundingClientRect is
      // viewport-relative and the iframe has no scroll offset at first paint, so these
      // ARE the fold. Supersedes the 2026-09-08 density pass's tilesBottom/
      // readinessBottom reads against .qb-sec-tiles/.qb-sec-ready, which no longer
      // exist (those cards lost their qb-card wrapper and moved into qbx-stats/
      // qbx-system). sideFirstRowBottom is null on the 'flat' fixture at zero legs --
      // cannot happen (QE_LEGS always renders all three legs' rows regardless of
      // position state), kept nullable only for an ERR/degrade case with no sidebar.
      var heroEl=d.querySelector('.qbx-hero');
      out.heroBottom=heroEl?heroEl.getBoundingClientRect().bottom:null;
      var chartEl=d.querySelector('.qb-chart-wrap');
      out.chartBottom=chartEl?chartEl.getBoundingClientRect().bottom:null;
      var sideFirstRowEl=d.querySelector('.qbx-side [data-qblegrow]');
      out.sideFirstRowBottom=sideFirstRowEl?sideFirstRowEl.getBoundingClientRect().bottom:null;

      // ── REVIEW FIX verification (2026-09-24) ──────────────────────────────────
      // Fix 1: sidebar must start level with the hero's own eyebrow label, not a
      // whole hero-height lower. Measured on the OUTER document (both labels are
      // plain HTML, not SVG) via getBoundingClientRect().top -- viewport-relative,
      // so this is meaningful at >=1100px where the two sit side by side in the grid.
      var heroLabelEl=d.querySelector('.qb-hero-title');
      out.heroLabelTop=heroLabelEl?heroLabelEl.getBoundingClientRect().top:null;
      var sideHdEl=d.querySelector('.qbx-side-hd');
      out.sideHdTop=sideHdEl?sideHdEl.getBoundingClientRect().top:null;

      // Fix 2: the NOISE row's top line (name/short-tag/pill/spark/value/chevron)
      // must stay ONE line tall -- it used to wrap into a 6-7 line column when the
      // full "since/was/KEEL" text sat inline. A genuinely single-line flex row at
      // this font size renders well under 40px; the broken version measured 100px+.
      var noiseTopRowEl=d.querySelector('[data-qblegrow="NOISE"]');
      out.noiseTopRowHeight=noiseTopRowEl?noiseTopRowEl.getBoundingClientRect().height:null;

      // Fix 3: the chart's version-marker <text> (there is at most one in this SVG --
      // baseline/axis values are never drawn as SVG text here) must stay fully inside
      // the SVG's own viewBox in SVG user-space (getBBox ignores CSS scaling entirely,
      // so this is exact regardless of the CSS-rendered chart width).
      var chartSvgEl=d.querySelector('.qb-chart-wrap svg');
      out.chartViewBoxW=(chartSvgEl&&chartSvgEl.viewBox&&chartSvgEl.viewBox.baseVal)?chartSvgEl.viewBox.baseVal.width:null;
      var markerTextEl=d.querySelector('.qb-chart-wrap svg text');
      out.markerText=markerTextEl?markerTextEl.textContent:null;
      out.markerBBox=null;
      if(markerTextEl){
        try{
          var bb=markerTextEl.getBBox();
          out.markerBBox={x:bb.x,width:bb.width,right:bb.x+bb.width};
        }catch(e){}
      }

      // Outer harness-page horizontal scroll (owner: "the screenshots show a bottom
      // scrollbar that I believe comes from the probe text; prove it either way") --
      // measured on THIS top-level document (document.documentElement), separate from
      // out.bodyScrollW/overflowOk above, which already measure the IFRAME's own
      // document (the actual app, unaffected by the harness page either way). The
      // debug <pre id="o"> is now position:absolute and off-screen (see PROBE_HTML)
      // specifically so it cannot be the cause any more.
      out.outerScrollWidth=document.documentElement.scrollWidth;
      out.outerClientWidth=document.documentElement.clientWidth;
      out.outerOverflowOk=out.outerScrollWidth<=out.outerClientWidth+2;

      if(OPENCHECKS&&!DEEP){
        // lightweight: open SYSTEM then the readiness "All checks" disclosure (allchecks
        // is now nested inside System, closed by default -- see the module docstring),
        // so a passing sub-check (e.g. "enough trading days") is on the page for the
        // attention-colour scan below, without running the full interactive suite.
        fire('[data-qbdisclosure="system"]');
        fire('[data-qbdisclosure="allchecks"]');
      }

      if(DEEP){
        // Status/Orders/"Ready for real shares?"/Integrity all moved inside the new
        // "System" disclosure (2026-09-24), closed by default -- open it FIRST so the
        // allchecks disclosure and every integrity sheet fired below can find their
        // target element at all.
        fire('[data-qbdisclosure="system"]');

        // ── More stats -> every old-rail label must still be reachable ──
        out.moreStatsBefore=!!d.querySelector('[data-qbdisclosure="morestats"]');
        fire('[data-qbdisclosure="morestats"]');
        out.moreStatsHtml=html();

        // ── All checks disclosure on the readiness card ──
        fire('[data-qbdisclosure="allchecks"]');
        out.hasAllChecksRows=d.querySelectorAll('.qe-check-row').length;

        // ── Feed & signals disclosure under Activity ──
        fire('[data-qbdisclosure="feedsig"]');
        out.hasFeedSigContent=html().indexOf('FEED UPTIME \\u2014 LAST')>=0||html().indexOf('SIGNALS \\u2014 LAST')>=0;

        // ── Footer disclosures ──
        fire('[data-qbdisclosure="rails"]');
        out.hasRailsContent=html().indexOf('SHARES / LEG')>=0;
        fire('[data-qbdisclosure="events"]');
        out.hasEventsContent=d.querySelectorAll('.qe-evt-row').length;

        // ── Trades: List view row count vs trades_all (capped at 50) ──
        out.tradesListRows=d.querySelectorAll('[data-qbtraderow]').length;
        out.tradesAllLen=(FIX.trades_all||[]).length;

        // ── tap a trade row -> sheet opens with the drawer content ──
        out.tradeRowClick=fire('[data-qbtraderow="0"]')?'OK':'NO_ROW';
        out.hasSheetAfterTradeClick=!!d.querySelector('.qb-sheet-backdrop');
        out.hasDrawerInSheet=!!d.querySelector('.qb-sheet .qe-drawer');
        fire('[data-qbsheetclose]');
        out.sheetClosedAfterX=!d.querySelector('.qb-sheet-backdrop');

        // ── List | Table toggle ──
        out.tableSegClick=fire('[data-qbseg="tradesview"] [data-qbsegval="table"]')?'OK':'NO_SEG';
        out.hasTableAfterToggle=!!d.querySelector('table.table thead th');
        out.noListRowsInTableView=d.querySelectorAll('[data-qbtraderow]').length===0;
        fire('[data-qbseg="tradesview"] [data-qbsegval="list"]');
        out.tradesListRowsAfterBack=d.querySelectorAll('[data-qbtraderow]').length;

        // ── Integrity rows each open a sheet ──
        ['parity','feeduptime','ratio','latency','reprice'].forEach(function(k){
          var opened=fire('[data-qbsheet="'+k+'"]');
          out['integrity_'+k+'_opened']=opened&&!!d.querySelector('.qb-sheet-backdrop');
          fire('[data-qbsheetclose]');
        });

        // ── period control changes the plotted point count (hover-dot circles on the
        // TOTAL line, one per plotted date) ──
        var dotSel='.qb-chart-wrap svg circle[fill="transparent"]';
        out.chartDotsAll=d.querySelectorAll(dotSel).length;
        fire('[data-qbseg="period"] [data-qbsegval="1W"]');
        out.chartDots1W=d.querySelectorAll(dotSel).length;
        fire('[data-qbseg="period"] [data-qbsegval="ALL"]');
      }

      if(KEEPSHEET){
        fire('[data-qbtraderow="0"]');
      }

      if(LIVEPNL){
        // ── NOTES UNDER AN EXPANDER (2026-09-25, owner: "make it simple") -- ENGU-Q's
        // ETH-fit caveat and NOISE's since/was/KEEL line must be hidden by default,
        // appear after tapping that leg's own "i" toggle, and that tap must NOT also
        // open the leg's row-expand drawer (.qb-leg-detail) -- stopPropagation check.
        out.legDetailCountBefore=d.querySelectorAll('.qb-leg-detail').length;
        out.noteEnguqBefore=html().indexOf('ETH-fit crown')>=0;
        out.noteNoiseBefore=html().indexOf('KEEL v12')>=0;
        out.hasOrbInfoToggle=!!d.querySelector('[data-qbleginfo="ORB"]'); // ORB has no note -> no toggle
        out.infoToggleEnguqClicked=fire('[data-qbleginfo="ENGUQ"]');
        out.infoToggleNoiseClicked=fire('[data-qbleginfo="NOISE"]');
        out.noteEnguqAfter=html().indexOf('ETH-fit crown')>=0;
        out.noteNoiseAfter=html().indexOf('KEEL v12')>=0;
        out.legDetailCountAfterInfo=d.querySelectorAll('.qb-leg-detail').length;

        // ── SIDEBAR "Open ... / Total ..." (2026-09-25) -- ORB (long 5 @ 498.32, live
        // 501.15, open_pnl 14.15 per tools/fixtures/qqq_exec_positions.json) must show
        // its OPEN P&L and a TOTAL equal to its own closed P&L (220.69) + that open P&L.
        var orbRowTop=d.querySelector('[data-qblegrow="ORB"]');
        var orbRowWrap=orbRowTop?orbRowTop.parentElement:null;
        out.orbLiveText=(function(){
          var el=orbRowWrap?orbRowWrap.querySelector('.qbx-leg-live'):null;
          return el?el.textContent.replace(/\\s+/g,' ').trim():null;
        })();

        // ── ACCOUNT lists each open position, THEN the total (2026-09-25) ──
        var acctEl=d.querySelector('.qbx-account');
        out.accountText=acctEl?acctEl.textContent.replace(/\\s+/g,' ').trim():null;
      }

      if(LISTENERCHECK){
        // ── LIVE LISTENER WIRING (2026-09-25) -- _qqqExecEnsureLive (defined near
        // loadQqqExec in index.html) must not throw against a fake db/auth that has a
        // working onSnapshot, and calling it again (standing in for a second renderApp()
        // pass) must NOT attach a second listener. Runs against a fake db, entirely
        // separate from the real Firebase db/auth this iframe boots with (which stays
        // signed out for every OTHER case in this file, so this is the one case that
        // actually exercises the attach path).
        out.listenerCall=w.eval("(function(){try{"
          +"var _fakeRef={};var _calls=0,_unsubs=0;"
          +"_fakeRef.collection=function(){return _fakeRef;};"
          +"_fakeRef.doc=function(){return _fakeRef;};"
          +"_fakeRef.onSnapshot=function(cb,errCb){_calls++;return function(){_unsubs++;};};"
          +"db=_fakeRef;auth={currentUser:{uid:'probe-uid'}};"
          +"_qqqExecEnsureLive();" // first attach
          +"_qqqExecEnsureLive();" // stand-in for a second render -- must be a same-tick no-op
          +"window._qeProbeListenerCalls=_calls;window._qeProbeListenerUnsubs=_unsubs;"
          +"return 'OK';"
          +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
        out.listenerCalls=w.eval('window._qeProbeListenerCalls');
        out.listenerUnsubs=w.eval('window._qeProbeListenerUnsubs');
        // restore a clean signed-out state so this does not leak into anything else
        // this iframe still does (harmless either way -- each case gets a fresh iframe).
        w.eval("(function(){try{if(window._qqqExecUnsub){window._qqqExecUnsub();}window._qqqExecUnsub=null;window._qqqExecLive=false;db=null;auth=null;return 'OK';}catch(e){return 'ERR '+e;}})()");
      }

      out.consoleErrors=w.eval('window._qeProbeErrors||[]');
      out.html=html();
      var undef=(out.html.match(/undefined/g)||[]).length;
      var nan=(out.html.match(/NaN/g)||[]).length;
      out.undefCount=undef; out.nanCount=nan;

      // ── ATTENTION-colour check (unchanged mechanism -- scans inline style attrs, so it
      // is unaffected by the markup re-composition) ──
      function parseRgb(s){
        s=s||'';
        var m=/rgba?\\(\\s*(\\d+)\\s*,\\s*(\\d+)\\s*,\\s*(\\d+)/.exec(s);
        if(m)return [+m[1],+m[2],+m[3]];
        var m2=/color\\(srgb\\s+([\\d.]+)\\s+([\\d.]+)\\s+([\\d.]+)/.exec(s);
        if(m2)return [Math.round(+m2[1]*255),Math.round(+m2[2]*255),Math.round(+m2[3]*255)];
        return null;
      }
      function isGreyish(rgb){
        if(!rgb)return true;
        var mx=Math.max(rgb[0],rgb[1],rgb[2]),mn=Math.min(rgb[0],rgb[1],rgb[2]);
        return (mx-mn)<=6;
      }
      function scanAttn(varName){
        var sel='[style*="var(--'+varName+')"]';
        var els=[].slice.call(d.querySelectorAll(sel));
        return els.map(function(el){
          var cs=w.getComputedStyle(el);
          var c=parseRgb(cs.color), bc=parseRgb(cs.borderTopColor), bg=parseRgb(cs.backgroundColor);
          return {colorGrey:isGreyish(c),borderGrey:isGreyish(bc),bgGrey:isGreyish(bg),
            color:cs.color,borderColor:cs.borderTopColor,background:cs.backgroundColor,tag:el.tagName,cls:el.className||''};
        });
      }
      out.attnRed=scanAttn('attn-red');
      out.attnAmber=scanAttn('attn-amber');
      out.attnOk=scanAttn('attn-ok');
    }catch(e){out.err=String(e&&e.stack?e.stack:e);}
    document.getElementById('o').textContent='QQQOVPROBE: '+JSON.stringify(out);
  }
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){report('load');},2500);});
  setTimeout(function(){report('backstop');},30000);
})();
</script>
</body></html>
"""


def run_case(chrome, root, fixture, name, shot_path, width=1600, height=1400, theme='dark',
             deep=False, keep_sheet=False, open_checks=False, livepnl=False, listener_check=False):
    pdir = os.path.join(root, '_qqqovprobe')
    if not os.path.isdir(pdir):
        os.makedirs(pdir)
    ppath = os.path.join(pdir, 'probe_%s.html' % name)
    html = (PROBE_HTML.replace('__FIX__', json.dumps(fixture))
            .replace('__THEME__', json.dumps(theme))
            .replace('__DEEP__', 'true' if deep else 'false')
            .replace('__KEEPSHEET__', 'true' if keep_sheet else 'false')
            .replace('__OPENCHECKS__', 'true' if open_checks else 'false')
            .replace('__LIVEPNL__', 'true' if livepnl else 'false')
            .replace('__LISTENERCHECK__', 'true' if listener_check else 'false')
            .replace('__IW__', str(width)).replace('__IH__', str(height)))
    io.open(ppath, 'w', encoding='utf-8').write(html)

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(root))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    prof = tempfile.mkdtemp(prefix='qqqovprobe-')
    url = 'http://127.0.0.1:%d/_qqqovprobe/probe_%s.html' % (port, name)
    win_w, win_h = width + 40, height + 80
    try:
        out = subprocess.run(
            [chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
             '--user-data-dir=' + prof, '--virtual-time-budget=50000',
             '--window-size=%d,%d' % (win_w, win_h),
             '--dump-dom', url],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=180).stdout
        if shot_path:
            subprocess.run(
                [chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
                 '--user-data-dir=' + prof, '--virtual-time-budget=50000',
                 '--window-size=%d,%d' % (win_w, win_h), '--screenshot=' + shot_path, url],
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                timeout=180)
    finally:
        srv.shutdown()
        try:
            os.remove(ppath)
            os.rmdir(pdir)
        except OSError:
            pass
        shutil.rmtree(prof, ignore_errors=True)

    m = re.search(r'QQQOVPROBE: (\{.*\})\s*</pre>', out, re.S)
    if not m:
        return {'err': 'no readout', 'raw_tail': out[-2000:]}
    try:
        return json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&')
                           .replace('&lt;', '<').replace('&gt;', '>'))
    except Exception as e:
        return {'err': 'unreadable readout: %s' % e}


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    chrome = find_chrome()
    if not chrome:
        print('INCONCLUSIVE -- chrome not found')
        return 2

    fx = {}
    fixture_files = {'real': 'qqq_exec_real.json', 'mock': 'qqq_exec_mock.json',
                      'ready': 'qqq_exec_mock_ready.json', 'degrade': 'qqq_exec_degrade.json',
                      'alarms': 'qqq_exec_alarms.json', 'healthy': 'qqq_exec_healthy.json',
                      # NEW 2026-09-24 (Robinhood re-composition verification): 'flat' is
                      # mock's data with every open position cleared (positions={},
                      # positions_live.legs=[]); 'positions' adds an ORB LONG + ENGUQ
                      # SHORT live position and a NOISE trade with a KEEL-sized fill. Both
                      # add QE.equity/QE.broker/QE.keel, which no other fixture carries.
                      'flat': 'qqq_exec_flat.json', 'positions': 'qqq_exec_positions.json'}
    for nm, fname in fixture_files.items():
        p = os.path.join(ROOT, 'tools', 'fixtures', fname)
        fx[nm] = json.load(io.open(p, encoding='utf-8'))

    out_dir = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else ROOT

    results = {}

    # ── 24-case structural matrix: real/mock/alarms/degrade x 1400/800/390 x mono/default ──
    matrix_plan = []
    for fixture_name in ('real', 'mock', 'alarms', 'degrade'):
        for width in (1400, 800, 390):
            for theme in ('mono', 'dark'):
                case = '%s_%d_%s' % (fixture_name, width, theme)
                matrix_plan.append((case, fixture_name, width, max(900, width), theme, False, False, False))

    # ── deep interaction pass (mock fixture, 1400px, both themes) ──
    deep_plan = [
        ('deep_mock_mono', 'mock', 1400, 1400, 'mono', True, False, False),
        ('deep_mock_dark', 'mock', 1400, 1400, 'dark', True, False, False),
    ]

    # ── extra non-screenshot case: alarms with "All checks" pre-opened, so a passing
    # sub-check (e.g. "enough trading days") is on the page for the attn-ok colour scan --
    # the named alarms screenshot below stays in its natural collapsed state.
    extra_plan = [
        ('alarms_checks_open', 'alarms', 1400, 1400, 'mono', False, False, True),
    ]

    # ── named screenshot cases (the 5 the owner asked for, plus 'ready'/'healthy' checks) ──
    # 'ready_1400' now sets open_checks=True: the compact readiness card's READY/NOT
    # READY text lives inside the new "System" disclosure (closed by default, 2026-09-24
    # re-composition), so proving this fixture reads READY needs System opened first --
    # open_checks already does exactly that (see the PROBE_HTML OPENCHECKS branch).
    shot_plan = [
        ('mono_real_1400', 'real', 1400, 900, 'mono', False, False, False),
        ('mono_alarms_1400', 'alarms', 1400, 1400, 'mono', False, False, False),
        ('mono_real_390', 'real', 390, 1000, 'mono', False, False, False),
        ('default_theme_1400', 'mock', 1400, 1400, 'dark', False, False, False),
        ('sheet_open_1400', 'mock', 1400, 1400, 'mono', False, True, False),
        ('ready_1400', 'ready', 1400, 1400, 'dark', False, False, True),
        ('healthy_mono', 'healthy', 1400, 1400, 'mono', False, False, False),
    ]

    # ── ROBINHOOD RE-COMPOSITION matrix (2026-09-24) -- the owner's own laptop/phone
    # acceptance-test sizes, on the two NEW fixtures ('flat' / 'positions'), in both
    # themes. Every one of these 16 cases is also a named screenshot for the owner to
    # review (rh_<fixture>_<w>x<h>_<theme>.png).
    ROBINHOOD_SIZES = [(1366, 768), (1536, 864), (1600, 1000), (390, 844)]
    robinhood_plan = []
    for fixture_name in ('flat', 'positions'):
        for (w, h) in ROBINHOOD_SIZES:
            for theme in ('mono', 'dark'):
                case = 'rh_%s_%dx%d_%s' % (fixture_name, w, h, theme)
                robinhood_plan.append((case, fixture_name, w, h, theme, False, False, False))

    # ── KEEL drawer text check (owner spec: a NOISE trade whose drawer shows "#382 2.00
    # x KEEL 1.50 = 3.00 -> wanted 30 sh") -- 'positions' fixture's trades_all[0] (newest,
    # so List row 0) is exactly that trade; keep_sheet opens it and leaves it open for
    # both the screenshot and the html() substring check in main() below.
    keel_plan = [
        ('keel_drawer_positions', 'positions', 1366, 900, 'mono', False, True, False),
    ]

    shot_names = set(n for n, *_ in shot_plan) | set(n for n, *_ in robinhood_plan) | set(n for n, *_ in keel_plan)
    for case_name, fixture_name, w, h, theme, deep, keep_sheet, open_checks in matrix_plan + deep_plan + extra_plan + shot_plan + robinhood_plan + keel_plan:
        shot = os.path.join(out_dir, 'qqq_overview_%s.png' % case_name) if case_name in shot_names else None
        results[case_name] = run_case(chrome, ROOT, fx[fixture_name], case_name, shot,
                                       width=w, height=h, theme=theme, deep=deep,
                                       keep_sheet=keep_sheet, open_checks=open_checks)
        if shot:
            print('%s shot -> %s' % (case_name, shot))

    # ── LIVE P&L pass (2026-09-25) -- separate small plans (their own tuple shape, so
    # kept out of the shared matrix loop above): notes-under-an-expander + sidebar
    # Open/Total + ACCOUNT positions-then-total, all on the 'positions' fixture (it is
    # the one fixture with a live ORB/ENGUQ position AND a NOISE KEEL note); and the
    # live-listener wiring check, which needs no fixture data at all beyond a render.
    livepnl_plan = [
        ('livepnl_positions', 'positions', 1366, 1200, 'mono', False, False, False, True, False),
    ]
    listener_plan = [
        ('listener_wiring_check', 'flat', 1200, 900, 'mono', False, False, False, False, True),
    ]
    for case_name, fixture_name, w, h, theme, deep, keep_sheet, open_checks, livepnl, listener_check in livepnl_plan + listener_plan:
        results[case_name] = run_case(chrome, ROOT, fx[fixture_name], case_name, None,
                                       width=w, height=h, theme=theme, deep=deep,
                                       keep_sheet=keep_sheet, open_checks=open_checks,
                                       livepnl=livepnl, listener_check=listener_check)

    fails = []

    # ── structural matrix assertions ──
    for case_name, fixture_name, w, h, theme, deep, keep_sheet, open_checks in matrix_plan:
        r = results[case_name]
        if r.get('err'):
            fails.append('%s: %s' % (case_name, r['err']))
            continue
        if r.get('call') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (case_name, r.get('call')))
            continue
        if not r.get('hasQbShell'):
            fails.append('%s: no .qb-shell rendered' % case_name)
        if not r.get('hasHero'):
            fails.append('%s: no hero number rendered' % case_name)
        if not r.get('hasChart'):
            fails.append('%s: no chart svg drawn' % case_name)
        if (r.get('statCellCount') or 0) < 4:
            fails.append('%s: fewer than 4 stat cells rendered (%s)' % (case_name, r.get('statCellCount')))
        if not r.get('hasSystemDisclosure'):
            fails.append('%s: no "System" disclosure control rendered (Status/Orders/Readiness/Integrity unreachable)' % case_name)
        if not r.get('hasSidebar') or not r.get('sidebarRowCount'):
            fails.append('%s: Strategies sidebar missing or has no rows' % case_name)
        if not r.get('hasStatusStrip'):
            fails.append('%s: no status strip under the chart' % case_name)
        if r.get('undefCount'):
            fails.append('%s: literal "undefined" appears %d times' % (case_name, r['undefCount']))
        if r.get('nanCount'):
            fails.append('%s: literal "NaN" appears %d times' % (case_name, r['nanCount']))
        if r.get('consoleErrors'):
            fails.append('%s: console errors -- %s' % (case_name, r['consoleErrors']))
        if w == 390 and not r.get('overflowOk'):
            fails.append('%s: horizontal body overflow at 390px (scrollWidth=%s)' % (case_name, r.get('bodyScrollW')))

    # ── deep interaction assertions (mock fixture) ──
    for case_name, *_r in deep_plan:
        r = results[case_name]
        if r.get('err'):
            fails.append('%s: %s' % (case_name, r['err']))
            continue
        # case-insensitive: the redesign deliberately uses iOS-style sentence-case row
        # labels ("Win rate") instead of the old rail's ALL-CAPS ("WIN RATE") -- same
        # words, same metric, different typography. Section headers stay uppercase.
        more_stats_upper = (r.get('moreStatsHtml') or '').upper()
        missing_labels = [lbl for lbl in QB_OLD_RAIL_LABELS if lbl not in more_stats_upper]
        if missing_labels:
            fails.append('%s: "More stats" is missing old-rail labels: %s' % (case_name, missing_labels))
        if not r.get('hasAllChecksRows'):
            fails.append('%s: "All checks" disclosure produced no qe-check-row rows' % case_name)
        if not r.get('hasFeedSigContent'):
            fails.append('%s: "Feed & signals" disclosure produced no strip content' % case_name)
        if not r.get('hasRailsContent'):
            fails.append('%s: "Rails" footer disclosure missing its content' % case_name)
        if not r.get('hasEventsContent'):
            fails.append('%s: "Event timeline" footer disclosure produced no rows' % case_name)
        expect_rows = min(r.get('tradesAllLen') or 0, 50)
        if r.get('tradesListRows') != expect_rows:
            fails.append('%s: trades LIST row count %s != trades_all length (capped at 50) %s'
                          % (case_name, r.get('tradesListRows'), expect_rows))
        if r.get('tradeRowClick') != 'OK' or not r.get('hasSheetAfterTradeClick') or not r.get('hasDrawerInSheet'):
            fails.append('%s: tapping a trade row did not open a sheet with the drawer content' % case_name)
        if not r.get('sheetClosedAfterX'):
            fails.append('%s: the sheet close (X) did not close the sheet' % case_name)
        if r.get('tableSegClick') != 'OK' or not r.get('hasTableAfterToggle') or not r.get('noListRowsInTableView'):
            fails.append('%s: List->Table toggle did not switch to the table view' % case_name)
        if r.get('tradesListRowsAfterBack') != expect_rows:
            fails.append('%s: Table->List toggle did not restore the list rows' % case_name)
        for k in ('parity', 'feeduptime', 'ratio', 'latency', 'reprice'):
            if not r.get('integrity_%s_opened' % k):
                fails.append('%s: INTEGRITY row "%s" did not open a sheet' % (case_name, k))
        if r.get('chartDotsAll') is None or r.get('chartDots1W') is None:
            fails.append('%s: chart period control produced no readable point count' % case_name)
        elif r.get('chartDots1W') >= r.get('chartDotsAll'):
            fails.append('%s: 1W period did not plot fewer points than ALL (1W=%s, ALL=%s)'
                          % (case_name, r.get('chartDots1W'), r.get('chartDotsAll')))

    # ── readiness READY on the 'ready' fixture ──
    r_ready = results.get('ready_1400', {})
    if r_ready.get('err'):
        fails.append('ready_1400: %s' % r_ready['err'])
    elif 'READY' not in (r_ready.get('html') or '') or 'NOT READY' in (r_ready.get('html') or ''):
        fails.append('ready_1400: compact readiness card is not showing READY on the ready fixture')

    # ── ATTENTION-colour checks ── attn-red/attn-amber are checked on the natural,
    # collapsed 'mono_alarms_1400' state (the Integrity list's dots + hero chips render
    # those without opening anything); attn-ok needs a PASSING sub-check on the page, which
    # on this redesign sits behind the readiness "All checks" disclosure, so that one uses
    # the 'alarms_checks_open' case (same alarms fixture, disclosure pre-opened).
    r_alarms_mono = results.get('mono_alarms_1400', {})
    if not r_alarms_mono.get('err'):
        if r_alarms_mono.get('themeApplied') != 'mono':
            fails.append('mono_alarms_1400: data-theme was not actually "mono" at render time')
        redEls = r_alarms_mono.get('attnRed') or []
        amberEls = r_alarms_mono.get('attnAmber') or []
        if not redEls:
            fails.append('mono_alarms_1400: no element used var(--attn-red) even though every red alarm is ON')
        if not amberEls:
            fails.append('mono_alarms_1400: no element used var(--attn-amber) even though ratio_health.warn/NOT READY/etc are ON')
        for label, els in (('attn-red', redEls), ('attn-amber', amberEls)):
            for e in els:
                if e.get('colorGrey') and e.get('borderGrey') and e.get('bgGrey'):
                    fails.append('mono_alarms_1400: a var(--%s) element rendered GREY under mono (color=%s border=%s, tag=%s)'
                                  % (label, e.get('color'), e.get('borderColor'), e.get('tag')))

    r_alarms_checks = results.get('alarms_checks_open', {})
    if not r_alarms_checks.get('err'):
        okEls = r_alarms_checks.get('attnOk') or []
        if not okEls:
            fails.append('alarms_checks_open: no element used var(--attn-ok) even with the readiness checklist open (a partially-passing gate)')
        for e in okEls:
            if e.get('colorGrey') and e.get('borderGrey') and e.get('bgGrey'):
                fails.append('alarms_checks_open: a var(--attn-ok) element rendered GREY under mono (color=%s border=%s)'
                              % (e.get('color'), e.get('borderColor')))

    r_healthy_mono = results.get('healthy_mono', {})
    if not r_healthy_mono.get('err'):
        if r_healthy_mono.get('themeApplied') != 'mono':
            fails.append('healthy_mono: data-theme was not actually "mono" at render time')
        redEls = r_healthy_mono.get('attnRed') or []
        amberEls = r_healthy_mono.get('attnAmber') or []
        if redEls:
            fails.append('healthy_mono: %d element(s) painted var(--attn-red) on a fixture with every alarm OFF' % len(redEls))
        if amberEls:
            fails.append('healthy_mono: %d element(s) painted var(--attn-amber) on a fixture with every alarm OFF' % len(amberEls))
        for e in (r_healthy_mono.get('attnOk') or []):
            if e.get('colorGrey') and e.get('borderGrey') and e.get('bgGrey'):
                fails.append('healthy_mono: a var(--attn-ok) element rendered GREY under mono (color=%s border=%s)'
                              % (e.get('color'), e.get('borderColor')))

    # ── default-theme alarms regression (proves the qb- work did not regress the non-mono look) ──
    r_alarms_default = results.get('alarms_1400_dark', {})
    if r_alarms_default.get('err'):
        fails.append('alarms_1400_dark: %s' % r_alarms_default['err'])
    elif r_alarms_default.get('call') != 'OK':
        fails.append('alarms_1400_dark: renderApp threw under the default theme -- %s' % r_alarms_default.get('call'))
    elif not r_alarms_default.get('hasQbShell'):
        fails.append('alarms_1400_dark: no .qb-shell rendered under the default theme (regression)')

    # ── sheet_open screenshot case sanity ──
    r_sheet = results.get('sheet_open_1400', {})
    if r_sheet.get('err'):
        fails.append('sheet_open_1400: %s' % r_sheet['err'])

    # ── ROBINHOOD RE-COMPOSITION matrix assertions (2026-09-24) -- same structural bar
    # as the matrix above (shell/hero/chart/stat-strip/status-strip/System-disclosure
    # present, no undefined/NaN, no console errors, no horizontal overflow), on the two
    # NEW fixtures across the owner's own laptop/phone sizes. ──
    for case_name, fixture_name, w, h, theme, deep, keep_sheet, open_checks in robinhood_plan:
        r = results[case_name]
        if r.get('err'):
            fails.append('%s: %s' % (case_name, r['err']))
            continue
        if r.get('call') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (case_name, r.get('call')))
            continue
        if not r.get('hasQbShell'):
            fails.append('%s: no .qb-shell rendered' % case_name)
        if not r.get('hasHero'):
            fails.append('%s: no headline number rendered' % case_name)
        if not r.get('hasChart'):
            fails.append('%s: no chart svg drawn' % case_name)
        if not r.get('hasSidebar') or not r.get('sidebarRowCount'):
            fails.append('%s: Strategies sidebar missing or has no rows' % case_name)
        if not r.get('hasStatusStrip'):
            fails.append('%s: no status strip under the chart' % case_name)
        if not r.get('hasSystemDisclosure'):
            fails.append('%s: no "System" disclosure control rendered' % case_name)
        if r.get('undefCount'):
            fails.append('%s: literal "undefined" appears %d times' % (case_name, r['undefCount']))
        if r.get('nanCount'):
            fails.append('%s: literal "NaN" appears %d times' % (case_name, r['nanCount']))
        if r.get('consoleErrors'):
            fails.append('%s: console errors -- %s' % (case_name, r['consoleErrors']))
        if not r.get('overflowOk'):
            fails.append('%s: horizontal body overflow at %dpx (scrollWidth=%s)' % (case_name, w, r.get('bodyScrollW')))
        # REVIEW FIX verification (2026-09-24): the app's OWN overflow (overflowOk,
        # measured on the iframe's document) is the real acceptance bar; this ALSO
        # checks the outer test-harness page itself never scrolls horizontally, now
        # that its debug readout is off-screen (see PROBE_HTML) -- proving the
        # scrollbar visible in earlier screenshots was the harness's debug text, not
        # the app.
        if not r.get('outerOverflowOk'):
            fails.append('%s: harness page itself scrolls horizontally at %dpx (outerScrollWidth=%s > outerClientWidth=%s)'
                          % (case_name, w, r.get('outerScrollWidth'), r.get('outerClientWidth')))

    # ── LAPTOP FOLD ACCEPTANCE (owner: "Laptop fit is the acceptance test: at 1366x768
    # and at 1536x864 the headline number, the whole chart and the top of the sidebar
    # list are visible WITHOUT scrolling") -- checked on both new fixtures, mono theme
    # (the owner's own theme). Supersedes the 2026-09-08 density pass's tilesBottom/
    # readinessBottom check against .qb-sec-tiles/.qb-sec-ready, which no longer exist.
    for w, h in ((1366, 768), (1536, 864)):
        for fixture_name in ('flat', 'positions'):
            case = 'rh_%s_%dx%d_mono' % (fixture_name, w, h)
            r = results.get(case, {})
            if r.get('err'):
                fails.append('%s (fold): %s' % (case, r['err']))
                continue
            hb = r.get('heroBottom')
            if hb is None or hb > h:
                fails.append('%s (fold): headline (.qbx-hero) bottom %s > %dpx' % (case, hb, h))
            cb = r.get('chartBottom')
            if cb is None or cb > h:
                fails.append('%s (fold): chart (.qb-chart-wrap) bottom %s > %dpx' % (case, cb, h))
            sb = r.get('sideFirstRowBottom')
            if sb is None or sb > h:
                fails.append('%s (fold): first sidebar row bottom %s > %dpx' % (case, sb, h))

    # ── REVIEW FIX 1 (2026-09-24): sidebar top within 8px of the hero label top, at
    # every >=1100px size (both new fixtures, both themes) -- proves "side" now starts
    # in the hero row instead of a whole hero-height lower.
    for case_name, fixture_name, w, h, theme, deep, keep_sheet, open_checks in robinhood_plan:
        if w < 1100:
            continue
        r = results.get(case_name, {})
        if r.get('err'):
            continue
        hlt, sht = r.get('heroLabelTop'), r.get('sideHdTop')
        if hlt is None or sht is None:
            fails.append('%s: could not measure hero label / sidebar heading position' % case_name)
        elif abs(hlt - sht) > 8:
            fails.append('%s: sidebar heading top (%.1f) is %.1fpx from the hero label top (%.1f), want <=8px'
                          % (case_name, sht, abs(hlt - sht), hlt))

    # ── REVIEW FIX 2 (2026-09-24): the NOISE row's top line must stay one line tall at
    # every size (the failure was specifically the 340px sidebar column, but checked at
    # 390px too per the review ask).
    for case_name, fixture_name, w, h, theme, deep, keep_sheet, open_checks in robinhood_plan:
        r = results.get(case_name, {})
        if r.get('err'):
            continue
        nh = r.get('noiseTopRowHeight')
        if nh is None:
            fails.append('%s: NOISE sidebar row not found' % case_name)
        elif nh > 40:
            fails.append('%s: NOISE row top line is %.1fpx tall (want <=40px, i.e. one line, not wrapped)' % (case_name, nh))

    # ── REVIEW FIX 3 (2026-09-24): the chart's version-marker text (NOISE's #304 -> #382
    # switch, the newest plotted day in the 'positions' fixture -- the exact case that
    # used to clip) must render fully inside the SVG viewBox, and must carry the family
    # name prefix. Checked on 'positions' at every size (anchor math is in SVG
    # user-space, so it does not depend on the CSS-rendered width).
    for case_name, fixture_name, w, h, theme, deep, keep_sheet, open_checks in robinhood_plan:
        if fixture_name != 'positions':
            continue
        r = results.get(case_name, {})
        if r.get('err'):
            continue
        vbw = r.get('chartViewBoxW')
        bbox = r.get('markerBBox')
        mtext = r.get('markerText') or ''
        if not mtext:
            fails.append('%s: no version-marker text drawn on the chart' % case_name)
            continue
        if 'NOISE' not in mtext:
            fails.append('%s: version-marker text "%s" is missing the family-name prefix ("NOISE")' % (case_name, mtext))
        if not bbox or vbw is None:
            fails.append('%s: could not measure the version-marker text bounding box' % case_name)
        else:
            if bbox['x'] < -0.5:
                fails.append('%s: version-marker text "%s" overflows the LEFT edge of the chart (bbox.x=%.1f)' % (case_name, mtext, bbox['x']))
            if bbox['right'] > vbw + 0.5:
                fails.append('%s: version-marker text "%s" overflows the RIGHT edge of the chart (right=%.1f > viewBox width=%.1f)'
                              % (case_name, mtext, bbox['right'], vbw))

    # ── REVIEW FIX 4 (2026-09-24): Max Drawdown prints as a positive number (the label
    # already says "drawdown") on both the primary stats row and "More stats". Checked
    # on the 'mock' fixture (deep_mock_mono has More stats open already), which has
    # closed trades so QST.n is truthy and the figure is a real number, not "--".
    r_dd = results.get('deep_mock_mono', {})
    if not r_dd.get('err'):
        html_dd = r_dd.get('html') or ''
        more_dd = r_dd.get('moreStatsHtml') or ''
        if '-$268.57' in html_dd or '-$268.57' in more_dd:
            fails.append('deep_mock_mono: Max Drawdown is still printed with a leading minus sign (-$268.57)')
        if '$268.57' not in html_dd:
            fails.append('deep_mock_mono: Max Drawdown $268.57 not found as a positive figure in the primary stats row')
        if '$268.57' not in more_dd:
            fails.append('deep_mock_mono: Max Drawdown $268.57 not found as a positive figure in "More stats"')

    # ── KEEL drawer text (owner spec: a NOISE trade whose drawer shows "#382 2.00 x
    # KEEL 1.50 = 3.00 -> wanted 30 sh") -- see qeKeelSizeHtml in index.html and
    # tools/fixtures/qqq_exec_positions.json's trades_all[0] (leg NOISE, trade_id
    # NOISE_382-..., size 3.00, keel_size 1.50, shares_wanted 30, shares 20).
    r_keel = results.get('keel_drawer_positions', {})
    if r_keel.get('err'):
        fails.append('keel_drawer_positions: %s' % r_keel['err'])
    else:
        keel_html = r_keel.get('html') or ''
        if '2.00 x KEEL 1.50 = 3.00' not in keel_html:
            fails.append('keel_drawer_positions: NOISE KEEL drawer text missing "2.00 x KEEL 1.50 = 3.00"')
        if 'wanted 30 sh' not in keel_html:
            fails.append('keel_drawer_positions: NOISE KEEL drawer text missing "wanted 30 sh"')
        if 'qb-sheet-backdrop' not in keel_html:
            fails.append('keel_drawer_positions: trade row 0 did not open its drawer sheet')

    # ── LIVE P&L (2026-09-25, owner: "make it simple ... for postions put any open pnl
    # and then total ... whyd doesnt it show live pnl") -- notes-under-an-expander,
    # sidebar Open/Total, ACCOUNT positions-then-total, all on the 'positions' fixture.
    # Expected numbers come straight from tools/fixtures/qqq_exec_positions.json:
    # ORB is long 5 @ 498.32 (positions_live), live 501.15, open_pnl 14.15; its own
    # closed trades_all sum is 220.69 (matches cum_pnl.ORB's own last point), so
    # Total = 220.69 + 14.15 = 234.84. ENGUQ is short 5 @ 505.10, live 507.85,
    # open_pnl -13.75.
    r_lp = results.get('livepnl_positions', {})
    if r_lp.get('err'):
        fails.append('livepnl_positions: %s' % r_lp['err'])
    else:
        if r_lp.get('call') != 'OK':
            fails.append('livepnl_positions: renderApp threw -- %s' % r_lp.get('call'))
        if r_lp.get('legDetailCountBefore'):
            fails.append('livepnl_positions: a leg drawer (.qb-leg-detail) is already open on first paint')
        if r_lp.get('noteEnguqBefore'):
            fails.append('livepnl_positions: ENGU-Q note ("ETH-fit crown...") is visible before its info toggle is clicked')
        if r_lp.get('noteNoiseBefore'):
            fails.append('livepnl_positions: NOISE note ("KEEL v12...") is visible before its info toggle is clicked')
        if r_lp.get('hasOrbInfoToggle'):
            fails.append('livepnl_positions: ORB has no note but still shows an info ("i") toggle')
        if not r_lp.get('infoToggleEnguqClicked'):
            fails.append('livepnl_positions: no info toggle found for ENGU-Q (data-qbleginfo="ENGUQ")')
        if not r_lp.get('infoToggleNoiseClicked'):
            fails.append('livepnl_positions: no info toggle found for NOISE (data-qbleginfo="NOISE")')
        if not r_lp.get('noteEnguqAfter'):
            fails.append('livepnl_positions: ENGU-Q note did not appear after clicking its info toggle')
        if not r_lp.get('noteNoiseAfter'):
            fails.append('livepnl_positions: NOISE note did not appear after clicking its info toggle')
        if r_lp.get('legDetailCountAfterInfo'):
            fails.append('livepnl_positions: clicking an info toggle opened a leg drawer (.qb-leg-detail) -- stopPropagation is not working')
        orb_live = r_lp.get('orbLiveText') or ''
        if 'Open $14.15' not in orb_live:
            fails.append('livepnl_positions: ORB sidebar line missing "Open $14.15" (got %r)' % orb_live)
        if 'Total $234.84' not in orb_live:
            fails.append('livepnl_positions: ORB sidebar line missing "Total $234.84" (got %r)' % orb_live)
        acct = r_lp.get('accountText') or ''
        orb_i, engu_i, total_i = acct.find('ORB'), acct.find('ENGU-Q'), acct.find('Total open P')
        if orb_i < 0 or engu_i < 0 or total_i < 0:
            fails.append('livepnl_positions: ACCOUNT is missing the ORB/ENGU-Q position line(s) or the Total open P&L line (got %r)' % acct)
        elif not (orb_i < total_i and engu_i < total_i):
            fails.append('livepnl_positions: ACCOUNT does not list the open positions BEFORE the total line (got %r)' % acct)
        if '-$13.75' not in acct:
            fails.append('livepnl_positions: ACCOUNT is missing ENGU-Q\'s open P&L -$13.75 (got %r)' % acct)

    # ── LIVE LISTENER WIRING (2026-09-25) -- _qqqExecEnsureLive must not throw against a
    # fake db/auth with a working onSnapshot, and a second call (standing in for a
    # second renderApp() pass) must not attach a second listener.
    r_lc = results.get('listener_wiring_check', {})
    if r_lc.get('err'):
        fails.append('listener_wiring_check: %s' % r_lc['err'])
    else:
        if r_lc.get('listenerCall') != 'OK':
            fails.append('listener_wiring_check: _qqqExecEnsureLive threw -- %s' % r_lc.get('listenerCall'))
        if r_lc.get('listenerCalls') != 1:
            fails.append('listener_wiring_check: expected exactly one onSnapshot attach across two calls, got %s' % r_lc.get('listenerCalls'))

    for nm, r in results.items():
        print(nm.upper(), ':', json.dumps({k: v for k, v in r.items() if k not in ('html', 'moreStatsHtml')}, indent=1))

    if fails:
        print('QQQOVPROBE: FAIL')
        for f in fails:
            print('  - ' + f)
        return 1
    print('QQQOVPROBE: PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
