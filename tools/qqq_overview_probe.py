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

FILL PARITY PASS (2026-09-28, owner decisions after the 09-28 parity audit) -- the
'parity0928' fixture is BUILT at run time from the real 2026-09-28 rows in
tests/fixtures/parity0928/ through api/qqq_exec.py's own code (reprice merge, fill
parity, P&L of record, summary -- see build_parity0928_fixture), on top of the 'flat'
fixture's non-trade blocks, with the trade rows PACKED exactly as _build_doc publishes
them (_compact_published_trades). Cases: the Integrity > Parity sheet ("WEBULL FILLS vs
BACKTEST") and one flagged trade's sheet (NOISE 09-25 12:10, the 15:59 flatten sold 32
cents a share under the flatten quote), at 1366x768 and 390x844 in mono and dark, plus at
1366x768 mono the NOISE 09-28 12:05 trade (priced against the backtest's real fill, the
12:05 bar's open: 3 cents worse, not flagged) and the 09-24 ENGU-Q trade (a fill that
does not fit the tape, P&L "of record"), all screenshotted
(parity_<what>_<w>x<h>_<theme>.png), and one check that a slow order says SLOW in words,
plus assertions: the old "36 of 36 ... miss their broker-side price" / "engine booked"
wording is gone, the list shows FILL GAP / CHECK FILL / BOOK PRICE / NOT COMPARED pills,
the P&L is the Webull figure, and today's orders show AFTER CLOSE instead of the
bar-start latency. `python tools/qqq_overview_probe.py <out_dir> --parity` runs only
this pass.

LEDGER UNIFY STEP 4 (2026-10-05): the board now wears TRADING-LOG's shared hero
(ledgerHeroHtml: label, big number = P&L of record since the start, today line, range
line, alarm chips in the chip slot, the since line and broker caveat in its note slot)
and the shared range pills (TODAY 1W 1M 3M YTD ALL, data-qbrange) under the chart, on
REAL's own saved range (homeRange in el_view). Every older case starts on ALL
(homeRange='ALL', like window._qeChartPeriod='ALL') so its counts are unchanged.
`--ledger` runs only the new pass: the 'flat' fixture re-dated to end today, at
1366x768 and 390x844 in mono and dark -- the hero numbers against an independent sum
here, each pill click moving the range line / chart / list / stats to the trades that
closed inside it, the pick surviving a live-listener redraw and a page reload, no
undefined/NaN, no sideways scroll -- plus one ?oldboards=1 case that must show the same new
layout (the flag changes nothing any more).

LEDGER UNIFY 13 (2026-10-05, review fix): `--record` runs only the record pass on the
parity0928 fixture: every strategy row opened, each row's TODAY figure against
today.legs_record (and the rows adding up to today.realized_pnl_record), the row's note in
words, the POSITION column in line across rows, the daily-stop line reading
today.breaker_input ('breaker figure'), and the CSV's 19 added columns after the original
ones with each trade's P&L of record. Then the same on a copy from an older box (no
legs_record, no breaker_input: the page's own sums, the stop line saying 'estimate') and on
a copy whose breaker_input is null (the breaker has not checked today): the estimate, never
$0.00 as the breaker figure. Review 2026-10-05 added two: the older box's copy last written
on a later day than its trading day (the rows still add up to the hero's today), and TODAY
figures of different widths ($0.00 against -$1,234.56) with the POSITION column in line.

LEDGER UNIFY STEP 5 (2026-10-05): the board's own svg chart is replaced by TRADING-LOG's
shared ledgerChartRender (#qb-lg-chart; the old svg is gone). The period-control and range checks now count the points on the shared chart's
total line (the range start, then one per day, or one per trade when the range holds one or
two days); the version-marker check reads the <text> after the [data-lgmark] line. ENGU-Q #335
sits in a collapsed Retired group (owner decision 9) while it is flat and closed nothing
today, so the record pass opens that group before it opens every strategy row.

This file is not wired into wt.py ship (ad hoc verification tool); the board's ship gate is
tools/webull_board_probe.py (short, offline, wired as REAL's home_render_probe.py is). It is
written the same way as
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
<iframe id="f" src="../index.html__QS__" style="width:__IW__px;height:__IH__px;border:0"></iframe>
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
var OPENPARITY=__OPENPARITY__;
var TRADEIDX=__TRADEIDX__;
var OPENCHECKS=__OPENCHECKS__;
var IW=__IW__;
// LIVEPNL/LISTENERCHECK (2026-09-25, live-P&L pass): see the module docstring addendum
// below the ROBINHOOD_SIZES comment for what each one drives.
var LIVEPNL=__LIVEPNL__;
var LISTENERCHECK=__LISTENERCHECK__;
// LEDGER (2026-10-05, unify step 4): the range-pill pass, in two phases around a reload
var LEDGER=__LEDGER__;
// RECORD (2026-10-05, ledger unify 13 review): the strategy rows' TODAY, the daily stop, the CSV
var RECORD=__RECORD__;
var SETRANGE=true;
(function(){
  var reported=false;
  function report(why){
    if(reported)return; reported=true;
    var out=window._ledgerOut||{why:why};
    var phase2=!!window._ledgerOut;
    if(phase2)SETRANGE=false;
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
        +(SETRANGE?"homeRange='ALL';":"")
        +"activeTab='augur';augurSub='qqqpaper';renderApp();return 'OK';"
        +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
      out.themeApplied=d.documentElement.getAttribute('data-theme');

      function fire(sel){var el=d.querySelector(sel);if(el){el.click();return true;}return false;}
      function html(){var ap=d.getElementById('app')||d.body;return ap?ap.innerHTML:'';}
      // LEDGER step 5: points on the shared chart's total line (one per day, the range start
      // first; a range of one or two days keeps every trade); 0 when the range draws no chart
      function chartPts(){var pl=d.querySelector('#qb-lg-chart svg polyline');
        return pl?String(pl.getAttribute('points')||'').trim().split(/\\s+/).filter(Boolean).length:0;}

      // ── structural counts on the FIRST paint (ALL cases) ──
      out.hasQbShell=!!d.querySelector('.qb-shell');
      out.hasHero=!!d.querySelector('.qb-hero-num, #qb-hero-value');
      out.heroText=(d.querySelector('.qb-hero-num, #qb-hero-value')||{}).textContent||null;
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
      var heroLabelEl=d.querySelector('.qb-hero-title, .lg-hero-label');
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
      // LEDGER step 5: the shared chart draws price labels as svg text too -- the marker's own
      // label is the <text> right after its [data-lgmark] line (the old svg: its only <text>)
      var markLineEl=d.querySelector('.qb-chart-wrap svg [data-lgmark]');
      var markerTextEl=markLineEl?markLineEl.nextElementSibling:d.querySelector('.qb-chart-wrap svg text');
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
        // LEDGER step 5: the shared chart's total-line points (see chartPts)
        out.chartDotsAll=chartPts();
        // LEDGER unify step 4: the shared range pills replaced the 1W/1M/3M/ALL tabs
        fire('[data-qbseg="period"] [data-qbsegval="1W"]')||fire('.qbx-range-row [data-qbrange="1W"]');
        out.chartDots1W=chartPts();
        fire('[data-qbseg="period"] [data-qbsegval="ALL"]')||fire('.qbx-range-row [data-qbrange="ALL"]');
      }

      if(KEEPSHEET){
        fire('[data-qbtraderow="0"]');
      }

      // FILL PARITY PASS (2026-09-28): the list's pills and today's orders header are
      // read on first paint, then either the Integrity > Parity sheet or one trade's
      // sheet is opened and LEFT open for the screenshot.
      out.listHtml=html();
      if(OPENPARITY){
        // the System disclosure's open state is remembered per browser profile, and the
        // screenshot run reuses the dump-dom run's profile -- open it only if it is shut
        if(!d.querySelector('[data-qbsheet="parity"]'))fire('[data-qbdisclosure="system"]');
        out.paritySheetOpened=fire('[data-qbsheet="parity"]')&&!!d.querySelector('.qb-sheet-backdrop');
        var psh=d.querySelector('.qb-sheet');
        out.sheetText=psh?psh.textContent.replace(/\\s+/g,' ').trim():null;
      }
      if(TRADEIDX>=0){
        out.tradeSheetOpened=fire('[data-qbtraderow="'+TRADEIDX+'"]')&&!!d.querySelector('.qb-sheet .qe-drawer');
        var tsh=d.querySelector('.qb-sheet');
        out.sheetText=tsh?tsh.textContent.replace(/\\s+/g,' ').trim():null;
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

      if(LEDGER){
        var txt=function(sel){var el=d.querySelector(sel);return el?el.textContent.replace(/\\s+/g,' ').trim():null;};
        var snap=function(){
          var act=d.querySelector('.qbx-range-row button.active');
          var cells=[].slice.call(d.querySelectorAll('.qbx-stat-cell')).map(function(c){return c.textContent.replace(/\\s+/g,' ').trim();});
          var hd=[].slice.call(d.querySelectorAll('.qb-section-hd span')).map(function(s){return s.textContent;}).filter(function(s){return /^Trades \\(/.test(s);});
          var h=html();
          var sv=null;try{sv=JSON.parse(w.localStorage.getItem('el_view')||'{}').homeRange||null;}catch(e){}
          return {active:act?act.getAttribute('data-qbrange'):null,range:txt('#qb-hero-range'),big:txt('#qb-hero-value'),
            today:txt('#qb-hero-today'),cap:txt('.qbx-chart-cap'),dots:chartPts(),
            listRows:d.querySelectorAll('[data-qbtraderow]').length,tradesHd:hd[0]||null,stats:cells,saved:sv,
            undef:(h.match(/undefined/g)||[]).length,nan:(h.match(/NaN/g)||[]).length,
            scrollW:d.body?d.body.scrollWidth:null};
        };
        if(!phase2){
          out.todayNY=w.eval('ledgerTodayNY()');
          out.cutoffs=w.eval('JSON.stringify(LEDGER_RANGES.map(function(r){return [r,ledgerCutoff(r)];}))');
          out.flagConst=w.eval('typeof LEDGER_OLDBOARDS');
          out.heroLabel=txt('#qb-hero-label');out.heroNote=txt('#qb-hero-note');
          out.heroChipsHtml=(d.querySelector('#qb-hero-chips')||{}).innerHTML||'';
          out.pills=[].slice.call(d.querySelectorAll('.qbx-range-row [data-qbrange]')).map(function(b){return b.getAttribute('data-qbrange');});
          out.oldTabs=!!d.querySelector('[data-qbseg="period"]');
          out.oldHero=!!d.querySelector('.qb-hero-num');
          out.first=snap();
          out.byRange={};
          (out.pills||[]).forEach(function(r){fire('.qbx-range-row [data-qbrange="'+r+'"]');out.byRange[r]=snap();});
          // an empty range says so in words and offers "Show all" (only when TODAY has no trades)
          fire('.qbx-range-row [data-qbrange="TODAY"]');
          var hist=d.querySelector('.qbx-history');
          out.todayHistText=hist?hist.textContent.replace(/\\s+/g,' ').trim():null;
          out.showAll=fire('.qbx-history [data-qbrange="ALL"]');
          out.afterShowAll=snap();
          // a live-listener redraw: a fake db hands the page a fresh copy of the doc through
          // _qqqExecEnsureLive's own onSnapshot callback (which renders at once when the last
          // render is old enough); the pick must survive it
          fire('.qbx-range-row [data-qbrange="1M"]');
          out.beforeRedraw=snap();
          var oldShell=d.querySelector('.qb-shell');if(oldShell)oldShell.setAttribute('data-probe-old','1');
          out.redrawCall=w.eval("(function(){try{var cb=null,ref={};ref.collection=function(){return ref;};ref.doc=function(){return ref;};"
            +"ref.onSnapshot=function(f){cb=f;return function(){};};db=ref;auth={currentUser:{uid:'probe-uid'}};"
            +"window._qqqExecUnsub=null;window._qqqExecLiveErrorAt=0;_qqqExecEnsureLive();if(!cb)return 'NO_LISTENER';"
            +"var doc=JSON.parse(JSON.stringify(window._qqqExec));doc.updated_at=String(doc.updated_at||'')+' ';"
            +"window._qqqExecLastRenderAt=0;window._qeProbeRenders=0;var _ra=renderApp;"
            +"cb({exists:true,data:function(){return doc;}});"
            +"if(window._qqqExecUnsub){window._qqqExecUnsub();}window._qqqExecUnsub=null;window._qqqExecLive=false;db=null;auth=null;"
            +"return window._qqqExec===doc?'OK':'NOT_APPLIED';}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
          out.afterRedraw=snap();
          out.redrawFresh=!!d.querySelector('.qb-shell')&&!d.querySelector('[data-probe-old]');
          // then a reload: phase 2 boots the page again WITHOUT setting the range
          window._ledgerOut=out;reported=false;
          fr.contentWindow.location.reload();
          return;
        }
        out.afterReload=snap();
      }

      if(RECORD){
        var clean=function(el){return el?el.textContent.replace(/\\s+/g,' ').trim():null;};
        var recKeys=[];
        // decision 9: a retired strategy's row sits in the collapsed Retired group -- open it first
        var retBtn=d.querySelector('[data-qbretired]');
        out.recRetired=retBtn?retBtn.getAttribute('aria-expanded'):null;
        if(retBtn&&retBtn.getAttribute('aria-expanded')!=='true')retBtn.click();
        [].slice.call(d.querySelectorAll('[data-qblegrow]')).forEach(function(e){var k=e.getAttribute('data-qblegrow');if(recKeys.indexOf(k)<0)recKeys.push(k);});
        out.recKeys=recKeys;
        // open every strategy row (each tap re-renders, so look the row up again each time)
        recKeys.forEach(function(k){fire('[data-qblegrow="'+k+'"]');});
        out.recLegs={};
        recKeys.forEach(function(k){
          var top=d.querySelector('[data-qblegrow="'+k+'"]');
          var row=top?top.closest('.qb-leg-row'):null;
          var det=row?row.querySelector('.qb-leg-detail'):null;
          if(!det){out.recLegs[k]={open:false};return;}
          var dl=det.getBoundingClientRect().left, cells={};
          [].slice.call(det.children).forEach(function(c){
            var lb=c.querySelector('.qb-row-sublabel');
            if(lb&&lb.parentElement===c)cells[lb.textContent.trim()]={val:clean(lb.nextElementSibling),left:Math.round(c.getBoundingClientRect().left-dl),txt:clean(c)};
          });
          out.recLegs[k]={open:true,today:cells.TODAY?cells.TODAY.val:null,todayCell:cells.TODAY?cells.TODAY.txt:null,
            todayLeft:cells.TODAY?cells.TODAY.left:null,posLeft:cells.POSITION?cells.POSITION.left:null,
            note:clean(det.querySelector('.qb-leg-today-note'))};
        });
        // every daily-stop line on the page (the sidebar's short one, and the Orders card's if drawn)
        out.recStops=[];
        var it=d.createTreeWalker(d.getElementById('app')||d.body,NodeFilter.SHOW_TEXT,null),nd;
        while((nd=it.nextNode())){if(/daily stop used/.test(nd.nodeValue)&&!/^(SCRIPT|STYLE)$/.test(nd.parentElement.tagName)){var pe=nd.parentElement;out.recStops.push({text:clean(pe),title:pe.getAttribute('title'),next:clean(pe.nextElementSibling&&pe.nextElementSibling.nextElementSibling)});}}
        // the CSV download, caught before it leaves the page
        var got=null;w._libDownload=function(nm,c){got={name:nm,content:String(c)};};
        out.recCsvClicked=fire('[data-qeexportcsv]');
        if(got){var ln=got.content.split('\\r\\n');out.recCsvName=got.name;out.recCsvHeader=ln[0];out.recCsvRows=ln.slice(1);}
        out.recScrollW=d.body?d.body.scrollWidth:null;
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
  // (LEDGER) the reload in phase 1 fires this load listener a second time -> phase 2
  setTimeout(function(){report('backstop');},30000);
})();
</script>
</body></html>
"""


def build_parity0928_fixture(base):
    """The 'parity0928' fixture: `base` (the 'flat' fixture -- no open positions) with
    every trade/parity/P&L block rebuilt from the REAL 2026-09-28 rows in
    tests/fixtures/parity0928/ by api/qqq_exec.py's own functions, exactly as _build_doc
    chains them (reprice merge -> fill parity + P&L of record -> summaries -> curve)."""
    import copy
    import csv as _csv
    sys.path.insert(0, ROOT)
    from api import qqq_exec as qe
    fx_dir = os.path.join(ROOT, 'tests', 'fixtures', 'parity0928')
    qe.TRADES_CSV = os.path.join(fx_dir, 'trades.csv')
    qe.BROKER_ORDERS_CSV = os.path.join(fx_dir, 'broker_orders.csv')
    quiet = lambda *a, **k: None  # noqa: E731
    rows = [dict(r) for r in reversed(qe._all_trades_from_csv())]
    for r in rows:
        r.update(qe._trade_parity(r, log=quiet))
    reprice = qe._merge_reprice(rows, log=quiet)
    qe._ENGINE_PX_CACHE['key'] = None
    # the fixture folder holds the box's own 1-minute bars for 09-24 and 09-28: the
    # decide-at-close NOISE rows are priced at the next bar's open from them
    eng = qe._engine_prices_by_trade(path=os.path.join(fx_dir, 'signals.csv'), bars_dir=fx_dir,
                                     log=quiet)
    by_base = qe._broker_orders_by_base(qe._all_broker_orders_from_csv())
    qe._apply_broker_parity(rows, by_base, engine_px=eng, log=quiet)
    broker_parity = qe._broker_parity_summary(rows)
    qe._apply_book_only(rows, by_base, log=quiet)
    day = '2026-09-28'
    with io.open(os.path.join(fx_dir, 'orders.csv'), encoding='utf-8', newline='') as f:
        orders = [o for o in _csv.DictReader(f) if str(o.get('ts_et') or '')[:10] == day]
    # LEDGER UNIFY 13 (2026-10-05): the two today fields the box now sends -- each
    # strategy's TODAY at the P&L of record, and the daily loss breaker's own input (a flat
    # book after the close: realized + the fill shortfall), both from the box's own code
    realized = round(sum(float(r['pnl']) for r in rows
                         if str(r.get('exit_ts') or '')[:10] == day), 2)
    qe._BREAKER_ADJ_CACHE['key'] = None
    fill_adj = qe._breaker_fill_shortfall({'trading_day': day, 'legs': {}}, log=quiet)
    fx = copy.deepcopy(base)
    fx.update({
        'updated_at': '2026-09-28 16:30:00', 'live_from': '2026-09-03',
        'signal_source': 'engine', 'mode': 'SHADOW',
        'trades_all': rows,
        'parity': qe._parity_summary(rows),
        'broker_parity': broker_parity,
        'book_only_summary': qe._book_only_summary(rows),
        'cum_pnl': qe._cum_pnl_by_leg(rows),
        'reprice': reprice,
        'latency': qe._build_latency(orders, log=quiet),
        'today': {'orders': orders,
                  'trades': [r for r in rows if str(r.get('exit_ts') or '')[:10] == day],
                  'realized_pnl': realized,
                  'realized_pnl_record': round(sum(qe._curve_pnl(r) for r in rows
                                                   if str(r.get('exit_ts') or '')[:10] == day), 2),
                  'unrealized_pnl': 0.0, 'breaker_fill_adj': fill_adj,
                  'breaker_input': round(realized + fill_adj, 2),
                  'legs_record': qe._legs_record_today(rows, day)},
        'positions': {},
    })
    fx['readiness'] = qe._build_readiness(fx.get('feed_days') or [], broker_parity, reprice,
                                          {'events': []}, log=quiet)
    # published exactly as _build_doc sends it: fp sides packed, in-band notes dropped
    qe._compact_published_trades(fx['trades_all'])
    return fx


def qe_pnl_of(t):
    """The board's P&L of record for one trade (index.html qePnlOf): pnl_record, else the
    book pnl, else the re-priced real_pnl, else 0 -- re-derived here, not read off the page."""
    for k in ('pnl_record', 'pnl', 'real_pnl'):
        try:
            v = float(t.get(k))
        except (TypeError, ValueError):
            continue
        if v == v and v not in (float('inf'), float('-inf')):
            return v
    return 0.0


def build_ledger_fixture(base, today):
    """The 'flat' fixture (no open positions) with its 40 trades re-dated to end on `today`
    (New York): trade i closes i*i/4 days back (0, 0, 1, 2, 4, 6 ... 380), so TODAY, 1W, 1M,
    3M, YTD and ALL each hold a different set. Times of day are kept."""
    import copy
    import datetime as _dt
    fx = copy.deepcopy(base)
    t0 = _dt.date.fromisoformat(today)
    for i, t in enumerate(fx['trades_all']):  # newest first
        d = (t0 - _dt.timedelta(days=int(i * i / 4))).isoformat()
        for k in ('entry_ts', 'exit_ts'):
            if t.get(k):
                t[k] = d + str(t[k])[10:]
    todays = [t for t in fx['trades_all'] if str(t.get('exit_ts') or '')[:10] == today]
    fx['today'] = dict(fx.get('today') or {}, trades=todays,
                       realized_pnl_record=round(sum(qe_pnl_of(t) for t in todays), 2),
                       unrealized_pnl=0.0)
    fx['updated_at'] = today + ' 15:30:00'
    return fx


def money(v):
    """_hmMoney's text: -$1,234.56 / $0.00"""
    return ('-' if v < 0 else '') + '${:,.2f}'.format(abs(v))


def check_ledger(name, r, fx, w):
    """Assertions for one LEDGER case; returns a list of failure strings."""
    f = []
    if r.get('err'):
        return ['%s: %s' % (name, r['err'])]
    if r.get('call') != 'OK':
        return ['%s: renderApp threw -- %s' % (name, r.get('call'))]
    trades = fx['trades_all']
    want_pills = ['TODAY', '1W', '1M', '3M', 'YTD', 'ALL']
    if r.get('pills') != want_pills:
        f.append('%s: range pills are %s, want %s' % (name, r.get('pills'), want_pills))
    if r.get('oldTabs') or r.get('oldHero'):
        f.append('%s: the old 1W/1M/3M/ALL tabs or old hero are still on the page' % name)
    cut = dict(json.loads(r.get('cutoffs') or '[]'))
    if not cut or cut.get('TODAY') != r.get('todayNY'):
        f.append('%s: could not read the ranges from the page (%s)' % (name, r.get('cutoffs')))
        return f
    total = round(sum(qe_pnl_of(t) for t in trades), 2)
    first = r.get('first') or {}
    if first.get('big') != money(total):
        f.append('%s: big number %r, want the P&L of record since the start %r' % (name, first.get('big'), money(total)))
    tv = round(sum(qe_pnl_of(t) for t in trades if str(t.get('exit_ts'))[:10] == r['todayNY']), 2)
    want_today = ('▲ +' if tv >= 0 else '▼ -') + money(abs(tv)) + ' today'
    if first.get('today') != want_today:
        f.append('%s: today line %r, want %r' % (name, first.get('today'), want_today))
    if 'P&L of record' not in (r.get('heroLabel') or ''):
        f.append('%s: hero label %r does not say P&L of record' % (name, r.get('heroLabel')))
    if 'since ' not in (r.get('heroNote') or '') or '40 closed trades' not in (r.get('heroNote') or ''):
        f.append('%s: the since line is missing under the hero (%r)' % (name, r.get('heroNote')))
    labels = {'TODAY': 'today', '1W': 'past week', '1M': 'past month', '3M': 'past 3 months',
              'YTD': 'year to date', 'ALL': 'all time'}
    seen_ranges = set()
    for rg in want_pills:
        s = (r.get('byRange') or {}).get(rg) or {}
        c = cut.get(rg)
        inr = [t for t in trades if not c or str(t.get('exit_ts'))[:10] >= c]
        v = round(sum(qe_pnl_of(t) for t in inr), 2)
        want_rng = ('▲' if v >= 0 else '▼') + money(abs(v)) + labels[rg]
        if (s.get('range') or '').replace(' ', '') != want_rng.replace(' ', ''):
            f.append('%s %s: range line %r, want %r' % (name, rg, s.get('range'), want_rng))
        seen_ranges.add(s.get('range'))
        if s.get('active') != rg:
            f.append('%s %s: active pill is %r' % (name, rg, s.get('active')))
        if s.get('saved') != rg:
            f.append('%s %s: the pick was not saved for a reload (el_view.homeRange=%r)' % (name, rg, s.get('saved')))
        if s.get('big') != money(total):
            f.append('%s %s: the big number moved with the range (%r)' % (name, rg, s.get('big')))
        days = len(set(str(t.get('exit_ts'))[:10] for t in inr))
        # LEDGER step 5 (shared chart): the range start + one point per day, or + one per trade
        # when the range holds only one or two days; no chart at all for an empty range
        want_pts = 0 if not inr else (days + 1 if days > 2 else len(inr) + 1)
        if s.get('dots') != want_pts:
            f.append('%s %s: chart plots %s points, want %s (%d days, %d trades)'
                     % (name, rg, s.get('dots'), want_pts, days, len(inr)))
        if s.get('listRows') != min(len(inr), 50):
            f.append('%s %s: list shows %s rows, want %s' % (name, rg, s.get('listRows'), min(len(inr), 50)))
        want_cell = 'TRADES' + (str(len(inr)) if inr else '—')
        if not any(x.replace(' ', '').upper() == want_cell for x in (s.get('stats') or [])):
            f.append('%s %s: stats Trades cell is not %d (%s)' % (name, rg, len(inr), s.get('stats')))
        if not (s.get('tradesHd') or '').startswith('Trades (%d' % len(inr)):
            f.append('%s %s: list header %r, want Trades (%d...' % (name, rg, s.get('tradesHd'), len(inr)))
        if rg != 'ALL' and labels[rg] not in (s.get('cap') or ''):
            f.append('%s %s: chart caption %r does not name the range' % (name, rg, s.get('cap')))
        if s.get('undef') or s.get('nan'):
            f.append('%s %s: undefined x%s / NaN x%s on the page' % (name, rg, s.get('undef'), s.get('nan')))
        if s.get('scrollW') is not None and s['scrollW'] > w + 2:
            f.append('%s %s: sideways scroll (scrollWidth %s at %dpx)' % (name, rg, s['scrollW'], w))
    if len(seen_ranges) < 5:
        f.append('%s: the range line did not change across the pills (%s)' % (name, sorted(map(str, seen_ranges))))
    b, a = r.get('beforeRedraw') or {}, r.get('afterRedraw') or {}
    if r.get('redrawCall') != 'OK':
        f.append('%s: the live-listener redraw did not run (%s)' % (name, r.get('redrawCall')))
    if not r.get('redrawFresh'):
        f.append('%s: the live-listener snapshot did not redraw the board' % name)
    if a.get('active') != '1M' or a.get('range') != b.get('range') or a.get('dots') != b.get('dots'):
        f.append('%s: the 1M pick did not survive a live redraw (before %s / after %s)'
                 % (name, (b.get('active'), b.get('range')), (a.get('active'), a.get('range'))))
    z = r.get('afterReload') or {}
    if z.get('active') != '1M' or z.get('range') != b.get('range'):
        f.append('%s: the 1M pick did not survive a reload (got %s)' % (name, (z.get('active'), z.get('range'))))
    if r.get('consoleErrors'):
        f.append('%s: console errors -- %s' % (name, r['consoleErrors']))
    if r.get('undefCount') or r.get('nanCount'):
        f.append('%s: undefined x%s / NaN x%s' % (name, r.get('undefCount'), r.get('nanCount')))
    if not r.get('overflowOk'):
        f.append('%s: horizontal overflow at %dpx (scrollWidth=%s)' % (name, w, r.get('bodyScrollW')))
    return f


def ledger_pass(chrome, out_dir, fx):
    """LEDGER unify step 4 on the Webull board (see the module docstring)."""
    import datetime as _dt
    fails = []
    # today in New York, as the page counts it (ledgerTodayNY) -- read off a first render
    probe = run_case(chrome, ROOT, fx['flat'], 'ledger_today', None, width=1366, height=768,
                     theme='mono', ledger=True)
    today = probe.get('todayNY')
    if not today:
        return ['ledger_today: could not read today in New York from the page (%s)' % probe.get('err')]
    lfx = build_ledger_fixture(fx['flat'], today)
    for (w, h) in ((1366, 768), (390, 844)):
        for theme in ('mono', 'dark'):
            name = 'ledger_%dx%d_%s' % (w, h, theme)
            shot = os.path.join(out_dir, '%s.png' % name)
            r = run_case(chrome, ROOT, lfx, name, shot, width=w, height=h, theme=theme, ledger=True)
            print('%s shot -> %s' % (name, shot))
            print(name.upper(), ':', json.dumps({k: v for k, v in r.items()
                                                 if k not in ('html', 'moreStatsHtml', 'listHtml', 'attnRed',
                                                              'attnAmber', 'attnOk')})[:3000])
            fails.extend(check_ledger(name, r, lfx, w))
            if theme == 'mono' and r.get('themeApplied') != 'mono':
                fails.append('%s: mono theme was not applied' % name)
    # the alarm chips sit in the hero's chip slot, said in words
    ra = run_case(chrome, ROOT, fx['alarms'], 'ledger_alarms', os.path.join(out_dir, 'ledger_alarms_1366x768_mono.png'),
                  width=1366, height=768, theme='mono', ledger=True)
    chips = ra.get('heroChipsHtml') or ''
    for word in ('BREAKER TRIPPED', 'KILL ACTIVE', 'FEED STALE'):
        if word not in chips:
            fails.append('ledger_alarms: hero chip slot is missing %r' % word)
    # an empty range: the same book one day older, so nothing closed today -- the list says
    # so in words and its "Show all" button moves the pills to ALL
    import copy as _copy
    import datetime as _dt2
    efx = build_ledger_fixture(fx['flat'], (_dt2.date.fromisoformat(today) - _dt2.timedelta(days=1)).isoformat())
    efx['today'] = dict(efx['today'], trades=[], realized_pnl_record=0.0)
    re_ = run_case(chrome, ROOT, efx, 'ledger_empty_today', os.path.join(out_dir, 'ledger_empty_today_1366x768_mono.png'),
                   width=1366, height=768, theme='mono', ledger=True)
    fails.extend(check_ledger('ledger_empty_today', re_, efx, 1366))
    ht = re_.get('todayHistText') or ''
    if 'no trades closed today' not in ht or '40 more outside this range' not in ht:
        fails.append('ledger_empty_today: the empty TODAY list does not say so in words (%r)' % ht[:300])
    if not re_.get('showAll') or (re_.get('afterShowAll') or {}).get('active') != 'ALL':
        fails.append('ledger_empty_today: "Show all" did not move the range to ALL (%s)'
                     % ((re_.get('afterShowAll') or {}).get('active'),))
    # ?oldboards=1 no longer changes anything: the page behind it is the new Webull board
    ro = run_case(chrome, ROOT, lfx, 'ledger_flag', None, width=1366, height=768, theme='mono',
                  query='?oldboards=1')
    oh = ro.get('html') or ''
    if ro.get('err') or ro.get('call') != 'OK':
        fails.append('ledger_flag: %s' % (ro.get('err') or ro.get('call')))
    elif ('qb-hero-num' in oh or 'data-qbseg="period"' in oh or 'data-qbrange' not in oh
          or 'lg-hero' not in oh):
        fails.append('ledger_flag: ?oldboards=1 does not show the new Webull layout')
    elif ro.get('flagConst') not in (None, 'undefined'):
        fails.append('ledger_flag: LEDGER_OLDBOARDS is still a name in the page (typeof %s)' % ro.get('flagConst'))
    return fails


RECORD_XCOLS = ['trade_id', 'close_day_ny', 'pnl_record', 'pnl_record_source', 'pnl_record_note',
                'pnl_backtest', 'book_only', 'book_only_reason', 'fills_vs_backtest',
                'fills_vs_backtest_note', 'entry_backtest_px', 'entry_webull_px', 'entry_fill',
                'exit_backtest_px', 'exit_webull_px', 'exit_fill', 'fill_gap_usd', 'design_gap_usd',
                'execution_gap_usd']
RECORD_LEGS = ('ORB', 'ENGUQ', 'NOISE')


def record_want_legs(fx):
    """{leg: {pnl, n, book}} the rows must show: today.legs_record when the box sends it,
    else the page's own sum by the same rule (trades closed on the box's day, each at the
    P&L of record; `book` = not at Webull's fills on both sides), re-derived here."""
    rec = (fx.get('today') or {}).get('legs_record')
    if isinstance(rec, dict):
        return rec
    # the box's day = the hero's day: the newest close day among today's own trades, else
    # today's orders, else the day it last wrote (index.html qeBoxDay)
    ok = lambda s: bool(re.match(r'^\d{4}-\d{2}-\d{2}$', s))
    td = sorted(d for d in (str(t.get('exit_ts') or '')[:10] for t in (fx.get('today') or {}).get('trades') or []) if ok(d))
    od = sorted(d for d in (str(o.get('ts_et') or '')[:10] for o in (fx.get('today') or {}).get('orders') or []) if ok(d))
    day = td[-1] if td else (od[-1] if od else str(fx.get('updated_at') or '')[:10])
    out = {}
    for t in fx.get('trades_all') or []:
        if str(t.get('exit_ts') or '')[:10] != day:
            continue
        b = out.setdefault(t.get('leg') or '?', {'pnl': 0.0, 'n': 0, 'book': 0})
        b['pnl'] += qe_pnl_of(t)
        b['n'] += 1
        if str(t.get('pnl_record_src') or '') != 'webull':
            b['book'] += 1
    for b in out.values():
        b['pnl'] = round(b['pnl'], 2)
    return out


def check_record(name, r, fx, kind, w):
    """kind: 'box' (the box sends legs_record + breaker_input), 'old' (it sends neither),
    'null' (breaker_input is null: the breaker has not checked today)."""
    f = []
    if r.get('err'):
        return ['%s: %s' % (name, r['err'])]
    if r.get('call') != 'OK':
        return ['%s: renderApp threw -- %s' % (name, r.get('call'))]
    t = fx.get('today') or {}
    want = record_want_legs(fx)
    # every kind: the rows add up to the hero's today figure -- an older box's rows too,
    # even when it last wrote on a later day than its trading day (review 2026-10-05)
    tot = round(sum(float(b['pnl']) for b in want.values()), 2)
    if tot != round(float(t.get('realized_pnl_record')), 2):
        f.append('%s: the strategy rows add up to %s, the hero today is %s'
                 % (name, tot, t.get('realized_pnl_record')))
    legs = r.get('recLegs') or {}
    if sorted(legs) != sorted(RECORD_LEGS):
        f.append('%s: strategy rows %s, want %s' % (name, sorted(legs), sorted(RECORD_LEGS)))
    pos = set()
    for k in RECORD_LEGS:
        g = legs.get(k) or {}
        if not g.get('open'):
            f.append('%s %s: the strategy row did not open' % (name, k))
            continue
        b = want.get(k) or {'pnl': 0.0, 'n': 0, 'book': 0}
        if g.get('today') != money(round(float(b['pnl']), 2)):
            f.append('%s %s: TODAY reads %r, want %r' % (name, k, g.get('today'), money(float(b['pnl']))))
        if g.get('todayCell') != 'TODAY' + str(g.get('today')):
            f.append('%s %s: the TODAY cell holds more than its figure (%r)' % (name, k, g.get('todayCell')))
        if b['book']:
            wn = 'Today: %d of %d not fully at Webull fills' % (b['book'], b['n'])
        elif b['n']:
            wn = 'Today: %d closed, all at Webull fills' % b['n']
        else:
            wn = None
        if g.get('note') != wn:
            f.append('%s %s: note %r, want %r' % (name, k, g.get('note'), wn))
        pos.add(g.get('posLeft'))
    if len(pos) != 1 or None in pos:
        f.append('%s: the POSITION column is not in line across the rows (%s)' % (name, sorted(map(str, pos))))
    limit = abs(float((fx.get('rails') or {}).get('daily_loss_limit_usd')))
    if kind in ('box', 'wide'):
        fig, word = float(t['breaker_input']), 'breaker figure'
    else:
        fig = float(t.get('realized_pnl_record')) + float(t.get('unrealized_pnl') or 0)
        word = 'estimate, box not updated yet'
    want_stop = '%s of %s daily stop used' % (money(abs(min(0.0, fig))), money(limit))
    stops = r.get('recStops') or []
    if not stops:
        f.append('%s: no daily-stop line on the page' % name)
    for st in stops:
        txt = (st.get('text') or '') + ' ' + (st.get('title') or '') + ' ' + (st.get('next') or '')
        if not (st.get('text') or '').startswith(want_stop):
            f.append('%s: daily-stop line %r, want it to start %r' % (name, st.get('text'), want_stop))
        if kind in ('box', 'wide'):
            if 'breaker' not in txt or 'Estimate' in txt or 'estimate' in txt:
                f.append('%s: daily-stop line does not say it is the breaker figure (%r)' % (name, txt))
        else:
            if 'stimate' not in txt:
                f.append('%s: daily-stop line does not say estimate (%r)' % (name, txt))
            if 'as the daily loss breaker counts it' in txt:
                f.append('%s: an estimate is labelled as the breaker figure (%r)' % (name, txt))
    mini = [st for st in stops if st.get('title')]
    if mini and word not in (mini[0].get('text') or ''):
        f.append('%s: the short daily-stop line does not end in %r (%r)' % (name, word, mini[0].get('text')))
    # the CSV: the original columns, then the 19 added ones, one row per closed trade
    hdr = (r.get('recCsvHeader') or '').split(',')
    if not r.get('recCsvClicked') or not hdr or hdr[-len(RECORD_XCOLS):] != RECORD_XCOLS:
        f.append('%s: CSV header does not end in the 19 added columns (%s)' % (name, hdr[-21:]))
    elif hdr[:3] != ['entry_ts', 'exit_ts', 'leg']:
        f.append('%s: CSV no longer starts with the original columns (%s)' % (name, hdr[:3]))
    else:
        import csv as _csv
        rows = list(_csv.reader(io.StringIO('\r\n'.join(r.get('recCsvRows') or []))))
        trades = fx.get('trades_all') or []
        if len(rows) != len(trades):
            f.append('%s: CSV has %d rows, want %d' % (name, len(rows), len(trades)))
        ix = {c: i for i, c in enumerate(hdr)}
        srcs = {'Webull fills', 'part book price', 'book price', 're-price minute close', 'none'}
        # a trade by its id, else (older rows with no id) by leg + entry + exit time
        key = lambda tid, leg, en, ex: tid or '%s|%s|%s' % (leg, en, ex)
        by_id = {key(tr.get('trade_id'), tr.get('leg'), tr.get('entry_ts'), tr.get('exit_ts')): tr for tr in trades}
        bad = []
        for row in rows:
            if len(row) != len(hdr):
                bad.append('row width %d' % len(row))
                continue
            tr = by_id.get(key(row[ix['trade_id']], row[ix['leg']], row[ix['entry_ts']], row[ix['exit_ts']]))
            if tr is None:
                bad.append('unknown trade %r' % row[ix['trade_id']])
                continue
            if row[ix['pnl_record']] != '%.2f' % qe_pnl_of(tr):
                bad.append('%s pnl_record %s want %.2f' % (row[ix['trade_id']], row[ix['pnl_record']], qe_pnl_of(tr)))
            if row[ix['pnl_record_source']] not in srcs:
                bad.append('%s source %r' % (row[ix['trade_id']], row[ix['pnl_record_source']]))
            if row[ix['close_day_ny']] != str(tr.get('exit_ts') or tr.get('entry_ts'))[:10]:
                bad.append('%s close day %r' % (row[ix['trade_id']], row[ix['close_day_ny']]))
        if bad:
            f.append('%s: CSV rows wrong -- %s' % (name, bad[:5]))
    if r.get('consoleErrors'):
        f.append('%s: console errors -- %s' % (name, r['consoleErrors']))
    if r.get('undefCount') or r.get('nanCount'):
        f.append('%s: undefined x%s / NaN x%s' % (name, r.get('undefCount'), r.get('nanCount')))
    if r.get('recScrollW') is not None and r['recScrollW'] > w + 2:
        f.append('%s: sideways scroll with the rows open (scrollWidth %s at %dpx)' % (name, r['recScrollW'], w))
    return f


def record_pass(chrome, out_dir, fx_par):
    """LEDGER UNIFY 13 review: the strategy rows' TODAY, the daily stop and the CSV (see the
    module docstring) on parity0928, an older box's copy and a null-breaker copy."""
    import copy as _copy
    old = _copy.deepcopy(fx_par)
    old['today'].pop('legs_record', None)
    old['today'].pop('breaker_input', None)
    nul = _copy.deepcopy(fx_par)
    nul['today']['breaker_input'] = None
    # a strategy with trades not fully at Webull fills: the note must say so in words
    nul['today']['legs_record'] = _copy.deepcopy(nul['today']['legs_record'])
    nul['today']['legs_record']['NOISE']['book'] = 2
    if float(nul['today']['realized_pnl_record']) >= 0:
        return ['record: the parity0928 fixture no longer has a loss today -- the null case proves nothing']
    # review 2026-10-05: an older box that last wrote on a LATER day than its trading day
    # (a weekend, or the runner stopped overnight) -- the rows must still read the hero's day
    wknd = _copy.deepcopy(old)
    wknd['updated_at'] = '2026-10-03 12:00:00'
    if not (wknd['today'].get('trades') or []):
        return ['record: the parity0928 fixture has no trades today -- the later-day case proves nothing']
    # review 2026-10-05: TODAY figures of different widths ($0.00 against -$1,234.56) --
    # the POSITION column must still line up across the rows
    wide = _copy.deepcopy(fx_par)
    wide['today']['legs_record'] = {'ENGUQ': {'pnl': -1234.56, 'n': 3, 'book': 0},
                                    'NOISE': {'pnl': 7.5, 'n': 1, 'book': 1}}
    wide['today']['realized_pnl_record'] = -1227.06
    plan = [('record_box_1366x768_mono', fx_par, 'box', 1366, 768, 'mono'),
            ('record_box_1366x768_dark', fx_par, 'box', 1366, 768, 'dark'),
            ('record_box_390x844_mono', fx_par, 'box', 390, 844, 'mono'),
            ('record_oldbox_1366x768_mono', old, 'old', 1366, 768, 'mono'),
            ('record_oldbox_390x844_mono', old, 'old', 390, 844, 'mono'),
            ('record_nullbreaker_1366x768_mono', nul, 'null', 1366, 768, 'mono'),
            ('record_nullbreaker_390x844_mono', nul, 'null', 390, 844, 'mono'),
            ('record_oldbox_laterday_1366x768_mono', wknd, 'old', 1366, 768, 'mono'),
            ('record_widetoday_1366x768_mono', wide, 'wide', 1366, 768, 'mono'),
            ('record_widetoday_390x844_mono', wide, 'wide', 390, 844, 'mono')]
    fails = []
    for name, fx, kind, w, h, theme in plan:
        shot = os.path.join(out_dir, '%s.png' % name)
        r = run_case(chrome, ROOT, fx, name, shot, width=w, height=h, theme=theme, record=True)
        print('%s shot -> %s' % (name, shot))
        print(name.upper(), ':', json.dumps({k: v for k, v in r.items()
                                             if k in ('err', 'call', 'recLegs', 'recStops', 'recCsvClicked',
                                                      'recScrollW', 'consoleErrors')}))
        fails.extend(check_record(name, r, fx, kind, w))
        if theme == 'mono' and r.get('themeApplied') != 'mono':
            fails.append('%s: mono theme was not applied' % name)
    return fails


def run_case(chrome, root, fixture, name, shot_path, width=1600, height=1400, theme='dark',
             deep=False, keep_sheet=False, open_checks=False, livepnl=False, listener_check=False,
             open_parity=False, trade_idx=-1, ledger=False, query='', record=False):
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
            .replace('__OPENPARITY__', 'true' if open_parity else 'false')
            .replace('__TRADEIDX__', str(int(trade_idx)))
            .replace('__LEDGER__', 'true' if ledger else 'false')
            .replace('__RECORD__', 'true' if record else 'false')
            .replace('__QS__', query)
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

    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    parity_only = '--parity' in sys.argv[1:]
    ledger_only = '--ledger' in sys.argv[1:]
    record_only = '--record' in sys.argv[1:]
    out_dir = os.path.abspath(args[0]) if args else ROOT
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    # ── LEDGER UNIFY 13 review (2026-10-05): strategy TODAY, daily stop, CSV ──
    fx['parity0928'] = build_parity0928_fixture(fx['flat'])
    record_fails = [] if parity_only else record_pass(chrome, out_dir, fx['parity0928'])
    if record_only:
        if record_fails:
            print('QQQOVPROBE RECORD: FAIL')
            for f in record_fails:
                print('  - ' + f)
            return 1
        print('QQQOVPROBE RECORD: PASS')
        return 0

    # ── LEDGER UNIFY STEP 4 (2026-10-05): shared hero + range pills ──
    ledger_fails = [] if parity_only else ledger_pass(chrome, out_dir, fx)
    if ledger_only:
        if ledger_fails:
            print('QQQOVPROBE LEDGER: FAIL')
            for f in ledger_fails:
                print('  - ' + f)
            return 1
        print('QQQOVPROBE LEDGER: PASS')
        return 0

    # ── FILL PARITY PASS (2026-09-28) ── (fx['parity0928'] is built above)
    p_trades = fx['parity0928']['trades_all']
    def _idx(tid):
        return next(i for i, t in enumerate(p_trades) if t.get('trade_id') == tid)
    flagged_idx = _idx('NOISE_382-20260925T161000Z-L')
    t1205_idx = _idx('NOISE_382-20260928T160500Z-S')
    suspect_idx = _idx('ENGUQ_335-20260924T161700Z-L')
    parity_plan = []
    for (w, h) in ((1366, 768), (390, 844)):
        for theme in ('mono', 'dark'):
            parity_plan.append(('parity_sheet_%dx%d_%s' % (w, h, theme), w, h, theme, True, -1))
            parity_plan.append(('parity_trade_%dx%d_%s' % (w, h, theme), w, h, theme, False, flagged_idx))
    parity_plan.append(('parity_trade1205_1366x768_mono', 1366, 768, 'mono', False, t1205_idx))
    parity_plan.append(('parity_suspect_1366x768_mono', 1366, 768, 'mono', False, suspect_idx))
    # the per-case expectations of a trade sheet (text as the sheet shows it)
    trade_wants = {
        flagged_idx: ('FILLS vs BACKTEST', 'FLAGGED', 'backtest 744.50', 'Webull 744.60',
                      'book 744.92', 'design gap 42.0\u00a2 a share better',
                      'slippage 32.0\u00a2 a share worse', 'P&L \u2014 Webull vs backtest',
                      'Webull -$11.25', 'backtest -$14.85', 'book -$8.70'),
        t1205_idx: ('FILLS vs BACKTEST', 'backtest 735.18', 'Webull 735.15',
                    '3.0\u00a2 a share worse', 'Webull -$5.80', 'backtest -$4.60', 'book -$3.30'),
        suspect_idx: ('FILLS vs BACKTEST', 'FLAGGED', '(looks wrong)', 'unexplained',
                      'of record $19.38', 'of record vs backtest'),
    }
    parity_results = {}
    for case_name, w, h, theme, open_parity, tidx in parity_plan:
        shot = os.path.join(out_dir, '%s.png' % case_name)
        parity_results[case_name] = run_case(chrome, ROOT, fx['parity0928'], case_name, shot,
                                              width=w, height=h, theme=theme,
                                              open_parity=open_parity, trade_idx=tidx)
        print('%s shot -> %s' % (case_name, shot))
    parity_fails = []
    # SLOW (MONO: said in words, not only in red): one order more than 60 s after its
    # bar's close, on a copy of the fixture -- a render check only
    import copy as _copy
    fx_slow = _copy.deepcopy(fx['parity0928'])
    for o in fx_slow['today']['orders']:
        if o.get('after_close_s') not in (None, ''):
            o['after_close_s'] = '75.2'
            break
    r_slow = run_case(chrome, ROOT, fx_slow, 'parity_slow_check',
                      os.path.join(out_dir, 'parity_slow_check_1366x768_mono.png'),
                      width=1366, height=768, theme='mono')
    if r_slow.get('err') or 'SLOW' not in (r_slow.get('listHtml') or ''):
        parity_fails.append('parity_slow_check: a 75 s order does not say SLOW (%s)'
                            % (r_slow.get('err') or 'no SLOW on the page'))
    for case_name, w, h, theme, open_parity, tidx in parity_plan:
        r = parity_results[case_name]
        if r.get('err'):
            parity_fails.append('%s: %s' % (case_name, r['err']))
            continue
        if r.get('call') != 'OK':
            parity_fails.append('%s: renderApp threw -- %s' % (case_name, r.get('call')))
            continue
        txt = r.get('sheetText') or ''
        lst = r.get('listHtml') or ''
        for bad in ('miss their broker-side price', 'engine booked', '36 of 36', 'PARITY NOTE'):
            if bad in txt or bad in lst:
                parity_fails.append('%s: old parity wording still on screen: %r' % (case_name, bad))
        if open_parity:
            if not r.get('paritySheetOpened'):
                parity_fails.append('%s: Integrity > Parity sheet did not open' % case_name)
            for want in ('WEBULL FILLS vs BACKTEST', 'Webull fills averaged 2.2',
                         'better than the backtest on slippage', 'design gaps',
                         '1 fill that does not fit the tape (marked CHECK FILL)',
                         'flags: a fill more than 15', 'NOISE: 7 trades, slippage 0.2',
                         'ORB:', 'ENGU-Q: 2 trades, slippage 2.5',
                         '1 fill that looks wrong left out', 'Webull -$54.30 vs backtest -$70.15'):
                if want not in txt:
                    parity_fails.append('%s: parity sheet is missing %r (got %r)' % (case_name, want, txt[:400]))
        else:
            if not r.get('tradeSheetOpened'):
                parity_fails.append('%s: the trade sheet did not open' % case_name)
            if tidx == t1205_idx and 'FLAGGED' in txt:
                parity_fails.append('%s: the 12:05 trade is 3 cents worse -- must not be flagged' % case_name)
            for want in trade_wants[tidx]:
                if want not in txt:
                    parity_fails.append('%s: trade sheet is missing %r (got %r)' % (case_name, want, txt[:600]))
        for pill in ('FILL GAP', 'CHECK FILL', 'BOOK PRICE', 'NOT COMPARED', 'AFTER CLOSE'):
            if pill not in lst:
                parity_fails.append('%s: %r not found on the page' % (case_name, pill))
        if 'from bar start' in lst or '306.65' in lst or '306.7s' in lst:
            parity_fails.append('%s: an order still shows the bar-start latency' % case_name)
        if r.get('undefCount'):
            parity_fails.append('%s: literal "undefined" appears %d times' % (case_name, r['undefCount']))
        if r.get('nanCount'):
            parity_fails.append('%s: literal "NaN" appears %d times' % (case_name, r['nanCount']))
        if r.get('consoleErrors'):
            parity_fails.append('%s: console errors -- %s' % (case_name, r['consoleErrors']))
        if not r.get('overflowOk'):
            parity_fails.append('%s: horizontal overflow at %dpx (scrollWidth=%s)' % (case_name, w, r.get('bodyScrollW')))
        if theme == 'mono' and r.get('themeApplied') != 'mono':
            parity_fails.append('%s: mono theme was not applied' % case_name)
    for nm, r in parity_results.items():
        print(nm.upper(), ':', json.dumps({k: v for k, v in r.items()
                                           if k not in ('html', 'moreStatsHtml', 'listHtml')}, indent=1)[:1500])
    if parity_only:
        if parity_fails:
            print('QQQOVPROBE PARITY: FAIL')
            for f in parity_fails:
                print('  - ' + f)
            return 1
        print('QQQOVPROBE PARITY: PASS')
        return 0

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
        print(nm.upper(), ':', json.dumps({k: v for k, v in r.items() if k not in ('html', 'moreStatsHtml', 'listHtml')}, indent=1))

    fails.extend(parity_fails)
    fails.extend(ledger_fails)
    fails.extend(record_fails)
    if fails:
        print('QQQOVPROBE: FAIL')
        for f in fails:
            print('  - ' + f)
        return 1
    print('QQQOVPROBE: PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
