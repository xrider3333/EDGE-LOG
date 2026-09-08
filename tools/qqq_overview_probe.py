#!/usr/bin/env python3
"""
tools/qqq_overview_probe.py -- verification probe for the QQQ SHADOW BOOK tab, REWRITTEN
2026-09-08 for the Robinhood/iOS "qb-" re-composition (owner ask: "improve the layout.
need it to be more modern, slick, and simple to use. combination of robinhood and ios").

The old .ov-shell / .ov-rail sidebar layout is gone -- this file used to assert against
that DOM shape. It now asserts against the new single-column shell: .qb-shell containing
a hero number, a chart with a 1W/1M/3M/ALL qb-seg period control, four qb-tile stat tiles
behind a "More stats" disclosure (must still carry every RATIOS/PERFORMANCE/RISK label the
old .ov-rail rail carried -- QB_OLD_RAIL_LABELS below is that list, extracted from the
pre-redesign branch before it was touched), a compact READY/NOT READY card, a Legs list
(tap-to-expand), an Activity calendar (calendar cells + a "Feed & signals" disclosure), a
Trades card (List | Table qb-seg, CSV icon button, List rows open a qb-sheet holding the
same drawer breakdown the Table view's inline row always showed), an Integrity list (tap a
row -> a qb-sheet with that figure's existing detail panel), and footer disclosures
(Rails / Event timeline / Model reference).

Renders augurSub='qqqpaper' against these fixtures --
  real    : the real ~2-trade doc (oldest degrade path, minimal data)
  mock    : a synthetic ~40-trade / 3-leg doc carrying every field (readiness NOT ready,
            events of every kind, signals/feed history, repriced trades, latency)
  ready   : the same book with every readiness gate passing
  degrade : the same book with every optional field stripped out
  alarms  : every alert condition ON at once
  healthy : every alert condition OFF -- proves nothing gets painted with the attention
            colours when there is nothing to flag
at three widths -- 1400 / 800 / 390 -- in BOTH [data-theme="mono"] and the default
(dark, no data-theme attribute) theme, 4 fixtures (real/mock/alarms/degrade) x 3 widths x
2 themes = 24 structural passes (no undefined/NaN, no console errors, no horizontal body
overflow at 390, hero+chart+tiles present). A deeper interaction pass (More stats expand,
trades List/Table toggle + row count, a trade row opening its sheet, each Integrity row
opening its sheet, the period control changing the plotted point count) runs on the 'mock'
fixture at 1400 in both themes. 'ready' proves the compact readiness card reads READY;
'alarms'/'healthy' under mono (plus a default-theme 'alarms' regression pass) prove the
--attn-red/--attn-amber/--attn-ok colours still render non-grey.

Not wired into wt.py ship (ad hoc verification tool), but written the same way as
tools/paper_render_probe.py: stdlib + a subprocess call to local headless Chrome,
serving the repo over loopback so index.html's own fetches never fire.

DENSITY PASS 2026-09-08 (owner: 1920x1080 screenshot, "seems like I have to scroll down a
lot" -- a 48px hero spread over four stacked lines, a ~330px chart with two dots, then the
tiles, then everything else off-screen). Compacted the hero to one row, gave the chart a
fixed 220px/180px height, tightened qb-card padding, and added a >=1100px two-column shell
(left: chart/tiles/activity/trades/footer, right: a sticky Readiness->Legs->Integrity rail)
that collapses back to the same single-column DOM order below 1100px. 'mono_real_1400' and
'fold_mock_1400' below measure getBoundingClientRect().bottom of the tiles row and the
readiness card at 1400x900 and assert both are <=900px -- see the FOLD_LIMIT block in main().
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
<pre id="o"></pre>
<script>
var FIX=__FIX__;
var THEME=__THEME__;
var DEEP=__DEEP__;
var KEEPSHEET=__KEEPSHEET__;
var OPENCHECKS=__OPENCHECKS__;
var IW=__IW__;
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
        +"window._qbSheet=null;window._qbLegOpen=new Set();window._qeTradesView='list';window._qeChartPeriod='ALL';"
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
      out.tileCount=d.querySelectorAll('.qb-tile').length;
      out.hasReadinessCard=!!d.querySelector('.qb-card .qb-bar');
      out.legRowCount=d.querySelectorAll('[data-qblegrow]').length;
      out.bodyScrollW=d.body?d.body.scrollWidth:null;
      out.overflowOk=(out.bodyScrollW==null)||(out.bodyScrollW<=IW+2);

      // ── density pass 2026-09-08 fold measurement -- the owner's complaint was
      // "seems like I have to scroll down a lot"; these read back the ACTUAL rendered
      // bottom (getBoundingClientRect, viewport-relative, iframe has no scroll offset at
      // first paint) of the tiles row and the compact readiness card so the acceptance
      // check (<=900px at 1400x900) is measured, not eyeballed. readinessBottom is null
      // when the fixture published no readiness doc (e.g. the 'real' fixture) -- that is
      // an honest "not applicable", not a failure.
      var tilesEl=d.querySelector('.qb-sec-tiles');
      out.tilesBottom=tilesEl?tilesEl.getBoundingClientRect().bottom:null;
      var readyEl=d.querySelector('.qb-sec-ready');
      out.readinessBottom=readyEl?readyEl.getBoundingClientRect().bottom:null;

      if(OPENCHECKS&&!DEEP){
        // lightweight: open ONLY the readiness "All checks" disclosure, so a passing
        // sub-check (e.g. "enough trading days") is on the page for the attention-colour
        // scan below, without running the full interactive suite.
        fire('[data-qbdisclosure="allchecks"]');
      }

      if(DEEP){
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
             deep=False, keep_sheet=False, open_checks=False):
    pdir = os.path.join(root, '_qqqovprobe')
    if not os.path.isdir(pdir):
        os.makedirs(pdir)
    ppath = os.path.join(pdir, 'probe_%s.html' % name)
    html = (PROBE_HTML.replace('__FIX__', json.dumps(fixture))
            .replace('__THEME__', json.dumps(theme))
            .replace('__DEEP__', 'true' if deep else 'false')
            .replace('__KEEPSHEET__', 'true' if keep_sheet else 'false')
            .replace('__OPENCHECKS__', 'true' if open_checks else 'false')
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
                      'alarms': 'qqq_exec_alarms.json', 'healthy': 'qqq_exec_healthy.json'}
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
        # density pass 2026-09-08 -- 'mock' fixture DOES publish a readiness doc (unlike
        # 'real', a 2-trade doc with no readiness field yet), so this case is what proves
        # the readiness card itself also clears the 1400x900 fold, not just the tiles row.
        ('fold_mock_1400', 'mock', 1400, 900, 'mono', False, False, False),
    ]

    # ── named screenshot cases (the 5 the owner asked for, plus 'ready'/'healthy' checks) ──
    shot_plan = [
        ('mono_real_1400', 'real', 1400, 900, 'mono', False, False, False),
        ('mono_alarms_1400', 'alarms', 1400, 1400, 'mono', False, False, False),
        ('mono_real_390', 'real', 390, 1000, 'mono', False, False, False),
        ('default_theme_1400', 'mock', 1400, 1400, 'dark', False, False, False),
        ('sheet_open_1400', 'mock', 1400, 1400, 'mono', False, True, False),
        ('ready_1400', 'ready', 1400, 1400, 'dark', False, False, False),
        ('healthy_mono', 'healthy', 1400, 1400, 'mono', False, False, False),
    ]

    shot_names = set(n for n, *_ in shot_plan)
    for case_name, fixture_name, w, h, theme, deep, keep_sheet, open_checks in matrix_plan + deep_plan + extra_plan + shot_plan:
        shot = os.path.join(out_dir, 'qqq_overview_%s.png' % case_name) if case_name in shot_names else None
        results[case_name] = run_case(chrome, ROOT, fx[fixture_name], case_name, shot,
                                       width=w, height=h, theme=theme, deep=deep,
                                       keep_sheet=keep_sheet, open_checks=open_checks)
        if shot:
            print('%s shot -> %s' % (case_name, shot))

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
        if (r.get('tileCount') or 0) < 4:
            fails.append('%s: fewer than 4 stat tiles rendered (%s)' % (case_name, r.get('tileCount')))
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

    # ── density pass 2026-09-08 fold check (owner: "seems like I have to scroll down a
    # lot" at 1920x1080, screenshot showed a near-empty ~330px chart and everything below
    # the four tiles off-screen). Acceptance: at 1400x900, hero + chart + tiles + readiness
    # (start of legs) fit without scrolling -- measured via getBoundingClientRect, not
    # eyeballed. 'mono_real_1400' is the named screenshot the owner asked for (the REAL
    # fixture, no readiness doc published yet, so only the tiles bound applies there);
    # 'fold_mock_1400' is the same 1400x900 mono render on a fixture that DOES publish
    # readiness, so the readiness-card bound gets a real check too. ──
    FOLD_LIMIT = 900
    r_fold_real = results.get('mono_real_1400', {})
    if r_fold_real.get('err'):
        fails.append('mono_real_1400 (fold): %s' % r_fold_real['err'])
    else:
        tb = r_fold_real.get('tilesBottom')
        if tb is None:
            fails.append('mono_real_1400 (fold): tiles row (.qb-sec-tiles) not found')
        elif tb > FOLD_LIMIT:
            fails.append('mono_real_1400 (fold): tiles row bottom %.1fpx > %dpx' % (tb, FOLD_LIMIT))
        rb = r_fold_real.get('readinessBottom')
        if rb is not None and rb > FOLD_LIMIT:
            fails.append('mono_real_1400 (fold): readiness card bottom %.1fpx > %dpx' % (rb, FOLD_LIMIT))
        # rb is None here in the current fixture set (the 'real' doc has not published a
        # readiness block yet) -- that is a data gap, not a layout failure; fold_mock_1400
        # below is what actually exercises the readiness-card bound.

    r_fold_mock = results.get('fold_mock_1400', {})
    if r_fold_mock.get('err'):
        fails.append('fold_mock_1400 (fold): %s' % r_fold_mock['err'])
    else:
        tb = r_fold_mock.get('tilesBottom')
        if tb is None:
            fails.append('fold_mock_1400 (fold): tiles row (.qb-sec-tiles) not found')
        elif tb > FOLD_LIMIT:
            fails.append('fold_mock_1400 (fold): tiles row bottom %.1fpx > %dpx' % (tb, FOLD_LIMIT))
        rb = r_fold_mock.get('readinessBottom')
        if rb is None:
            fails.append('fold_mock_1400 (fold): readiness card (.qb-sec-ready) not found on a fixture that publishes readiness')
        elif rb > FOLD_LIMIT:
            fails.append('fold_mock_1400 (fold): readiness card bottom %.1fpx > %dpx' % (rb, FOLD_LIMIT))

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
