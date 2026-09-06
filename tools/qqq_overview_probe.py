#!/usr/bin/env python3
"""
tools/qqq_overview_probe.py -- verification probe for the QQQ SHADOW BOOK overview,
extended 2026-09-06 (round 3) for the readiness gate / event timeline / trade drawer /
real-price columns / signals strip / notional+latency / legend toggle / CSV export /
sticky rail / narrow-layout additions.

Renders augurSub='qqqpaper' against four fixtures --
  real    : the real ~2-trade doc (older shape, exercises the oldest degrade path)
  mock    : a synthetic ~40-trade / 3-leg doc carrying every new field, readiness
            NOT ready (3 missing items), events of every kind, 12 days of signals,
            3 repriced trades, latency p95 > 10s
  ready   : the same book with every readiness gate passing
  degrade : the same book with every new field stripped out
at two widths (1400px and 800px), and drives the trade-drawer click and the
equity-chart legend-toggle click inside the iframe before reading the DOM back out.

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
(function(){
  var reported=false;
  function report(why){
    if(reported)return; reported=true;
    var out={why:why};
    try{
      var fr=document.getElementById('f'), w=fr.contentWindow, d=fr.contentDocument;
      out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
      var consoleErrors=[];
      out.call=w.eval("(function(){try{"
        // the app's own auth.onAuthStateChanged(user=>{...else renderAuth();}) fires
        // asynchronously (real Firebase, no signed-in session in this probe) and would
        // repaint the sign-in screen over whatever we render below -- possibly well
        // after our call returns, once the virtual-time budget runs long enough for it
        // to resolve. Neutralise it FIRST so no later firing can undo our render.
        +"window.renderAuth=function(){};"
        +"window._qeProbeErrors=[];"
        +"window.onerror=function(m,s,l,c,e){window._qeProbeErrors.push(String(m));};"
        +"currentUser=currentUser||{uid:'probe-uid'};"
        +"window._qqqExec="+JSON.stringify(FIX)+";"
        +"window._qqqExecLoaded=true;window._qqqExecLoading=false;window._qqqExecErr=null;"
        +"window._qqqPaper=null;window._qqqPaperLoaded=true;window._qqqPaperLoading=false;window._qqqPaperErr=null;"
        +"window._qqqCalMonth=null;window._qeDrawerIdx=null;window._qeChartHidden={};window._qeTradesShown=50;window._qeEventsShown=30;"
        +"activeTab='augur';augurSub='qqqpaper';renderApp();return 'OK';"
        +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");

      // ── drive the trade-drawer click (row 0) then read the DOM, then close it again ──
      out.drawerClick=w.eval("(function(){try{"
        +"var el=document.querySelector('[data-qetraderow=\\"0\\"]');"
        +"if(!el)return 'NO_ROW';el.click();return 'OK';"
        +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
      out.hasDrawerAfterClick=!!d.querySelector('.qe-drawer');

      // ── drive the equity-chart legend toggle (hide the ORB line) ──
      out.legendClick=w.eval("(function(){try{"
        +"var el=document.querySelector('[data-qelegend=\\"ORB\\"]');"
        +"if(!el)return 'NO_LEGEND';el.click();return 'OK';"
        +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
      out.hasLegendOffClass=!!d.querySelector('.qe-legend-item.off');

      // put the drawer back closed + legend back on for a clean readout
      w.eval("(function(){try{window._qeDrawerIdx=null;window._qeChartHidden={};renderApp();}catch(e){}})()");

      out.consoleErrors=w.eval('window._qeProbeErrors||[]');

      var ap=d.getElementById('app')||d.body;
      out.appLen=ap?ap.innerHTML.length:-1;
      out.html=ap?ap.innerHTML:'';
      out.hasOvShell=!!d.querySelector('.ov-shell');
      out.hasRail=!!d.querySelector('.ov-rail');
      out.hasCal=!!d.querySelector('.ov-cal');
      out.railRows=d.querySelectorAll('.ov-rail .rail-row').length;
      out.calDays=d.querySelectorAll('[data-qcalday]').length;
      out.calNav=d.querySelectorAll('[data-qcalmo]').length;
      out.svgCount=d.querySelectorAll('.ov-cc-grid svg, .ov-shell svg').length;
      out.legCards=d.querySelectorAll('.ov-work').length;
      var undef=(out.html.match(/undefined/g)||[]).length;
      var nan=(out.html.match(/NaN/g)||[]).length;
      out.undefCount=undef; out.nanCount=nan;
      var lbl=d.querySelector('.ov-cal .lbl');
      out.calMonthLabel=lbl?lbl.textContent:null;
      var net=d.querySelector('.ov-rail .rail-net');
      out.railNet=net?net.textContent:null;

      // ── NT PARITY / FEED UPTIME / RATIO HEALTH (2026-09-05) ──
      var railGrps=[].slice.call(d.querySelectorAll('.ov-rail .rail-grp')).map(function(e){return e.textContent;});
      out.hasParityRailGrp=railGrps.indexOf('PARITY')>=0;
      out.hasFeedRailGrp=railGrps.indexOf('FEED UPTIME')>=0;
      out.hasSignalsRailGrp=railGrps.indexOf('SIGNALS')>=0;
      out.hasRepriceRailGrp=railGrps.indexOf('REPRICE')>=0;
      var headerRows=[].slice.call(d.querySelectorAll('table.table thead tr')).map(function(tr){
        return [].slice.call(tr.querySelectorAll('th')).map(function(th){return th.textContent;});
      });
      out.hasNtPointsCol=headerRows.some(function(cols){return cols.indexOf('NT POINTS')>=0;});
      out.hasExpectedCol=headerRows.some(function(cols){return cols.indexOf('EXPECTED $')>=0;});
      out.hasTrackErrCol=headerRows.some(function(cols){return cols.indexOf('TRACK ERR')>=0;});
      out.hasRealPnlCol=headerRows.some(function(cols){return cols.indexOf('REAL P&L')>=0;});
      out.hasSlipCol=headerRows.some(function(cols){return cols.indexOf('SLIP/SH')>=0;});
      out.hasLatencyCol=headerRows.some(function(cols){return cols.indexOf('LATENCY')>=0;});
      out.hasParityChip=out.html.indexOf('PARITY NOTE')>=0||out.html.indexOf('RECONSTRUCTED')>=0;
      out.hasFeedInvalidTag=out.html.indexOf('FEED INVALID')>=0;
      out.hasFeedStrip=out.html.indexOf('FEED UPTIME \u2014 LAST')>=0;
      out.hasSignalsStrip=out.html.indexOf('SIGNALS \u2014 LAST')>=0;
      out.hasRatioToggle=!!d.querySelector('[data-qqqratiotoggle]');
      out.hasWebullLink=out.html.indexOf('app.webull.com')>=0;
      out.hasWebullNote=out.html.indexOf('WEBULL PAPER \u2014 not used')>=0;
      out.hasParityPanel=out.html.indexOf('NT PARITY') >= 0;

      // ── round-3 additions ──
      out.hasReadinessBanner=!!d.querySelector('.qe-ready-banner');
      out.readinessIsReady=!!d.querySelector('.qe-ready-banner.ready');
      out.readinessIsNotReady=!!d.querySelector('.qe-ready-banner.notready');
      out.hasEventsPanel=out.html.indexOf('EVENT TIMELINE')>=0;
      out.eventRowCount=d.querySelectorAll('.qe-evt-row').length;
      out.hasEventsShowMore=!!d.querySelector('[data-qeeventsmore]');
      out.hasNotionalLine=out.html.indexOf('NOTIONAL \u2014')>=0;
      out.hasLatencyPill=out.html.indexOf('LATENCY')>=0;
      out.hasExportBtn=!!d.querySelector('[data-qeexportcsv]');
      out.hasOosTag=out.html.indexOf('NOT MIRRORED')>=0;
      out.hasRepriceNote=out.html.indexOf('re-priced nightly from real QQQ')>=0;
      var ovShellCS=d.querySelector('.ov-shell')?w.getComputedStyle(d.querySelector('.ov-shell')):null;
      out.ovShellDisplay=ovShellCS?ovShellCS.display:null;
    }catch(e){out.err=String(e&&e.stack?e.stack:e);}
    document.getElementById('o').textContent='QQQOVPROBE: '+JSON.stringify(out);
  }
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){report('load');},2500);});
  setTimeout(function(){report('backstop');},30000);
})();
</script>
</body></html>
"""


def run_case(chrome, root, fixture, name, shot_path, width=1600, height=1400):
    pdir = os.path.join(root, '_qqqovprobe')
    if not os.path.isdir(pdir):
        os.makedirs(pdir)
    ppath = os.path.join(pdir, 'probe_%s.html' % name)
    html = (PROBE_HTML.replace('__FIX__', json.dumps(fixture))
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
        # separate screenshot pass (dump-dom and screenshot can't combine reliably
        # for iframe content on some Chrome builds, so do it as its own invocation)
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
                      'ready': 'qqq_exec_mock_ready.json', 'degrade': 'qqq_exec_degrade.json'}
    for nm, fname in fixture_files.items():
        p = os.path.join(ROOT, 'tools', 'fixtures', fname)
        fx[nm] = json.load(io.open(p, encoding='utf-8'))

    out_dir = sys.argv[1] if len(sys.argv) > 1 else ROOT

    results = {}
    # 1400px width: real, mock, ready, degrade. 800px width: mock only (plus a
    # degrade pass to prove the narrow layout doesn't break the emptiest doc).
    plan = [
        ('mock_1400', 'mock', 1400, 900),
        ('ready_1400', 'ready', 1400, 900),
        ('real_1400', 'real', 1400, 900),
        ('degrade_1400', 'degrade', 1400, 900),
        ('mock_800', 'mock', 800, 1000),
        ('degrade_800', 'degrade', 800, 1000),
    ]
    for case_name, fixture_name, w, h in plan:
        shot = os.path.join(out_dir, 'qqq_overview_%s.png' % case_name)
        results[case_name] = run_case(chrome, ROOT, fx[fixture_name], case_name, shot, width=w, height=h)
        print('%s shot -> %s' % (case_name, shot))

    for nm, r in results.items():
        print(nm.upper(), ':', json.dumps({k: v for k, v in r.items() if k != 'html'}, indent=1))

    fails = []
    for nm, r in results.items():
        if r.get('err'):
            fails.append('%s: %s' % (nm, r['err']))
            continue
        if r.get('call') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (nm, r.get('call')))
        if not r.get('hasOvShell'):
            fails.append('%s: no .ov-shell rendered' % nm)
        if not r.get('hasRail'):
            fails.append('%s: no .ov-rail rendered' % nm)
        if not r.get('hasCal'):
            fails.append('%s: no .ov-cal rendered' % nm)
        if not r.get('railRows'):
            fails.append('%s: rail has no rows' % nm)
        if not r.get('svgCount'):
            fails.append('%s: no chart svg drawn' % nm)
        if r.get('undefCount'):
            fails.append('%s: literal "undefined" appears %d times' % (nm, r['undefCount']))
        if r.get('nanCount'):
            fails.append('%s: literal "NaN" appears %d times' % (nm, r['nanCount']))
        if r.get('consoleErrors'):
            fails.append('%s: console errors -- %s' % (nm, r['consoleErrors']))
        if r.get('hasWebullLink'):
            fails.append('%s: WEBULL PAPER trap link still present' % nm)
        if not r.get('hasWebullNote'):
            fails.append('%s: WEBULL PAPER "not used" note missing' % nm)
        if not r.get('hasParityRailGrp'):
            fails.append('%s: rail is missing the PARITY group' % nm)
        if not r.get('hasFeedRailGrp'):
            fails.append('%s: rail is missing the FEED UPTIME group' % nm)
        if not r.get('hasRepriceRailGrp'):
            fails.append('%s: rail is missing the REPRICE group' % nm)
        if not r.get('hasNtPointsCol') or not r.get('hasExpectedCol') or not r.get('hasTrackErrCol'):
            fails.append('%s: CLOSED TRADES is missing an NT-parity column' % nm)
        if not r.get('hasRealPnlCol') or not r.get('hasSlipCol'):
            fails.append('%s: CLOSED TRADES is missing REAL P&L / SLIP/SH column' % nm)
        if not r.get('hasParityPanel'):
            fails.append('%s: no NT PARITY panel rendered' % nm)
        if not r.get('hasExportBtn'):
            fails.append('%s: no EXPORT CSV button' % nm)

    # mock-only: fields that only exist when the mock's real values are present.
    for nm in ('mock_1400', 'mock_800'):
        r = results.get(nm, {})
        if r.get('err'):
            continue
        if not r.get('hasParityChip'):
            fails.append('%s: no parity chip (RECONSTRUCTED/PARITY NOTE) rendered on any trade row' % nm)
        if not r.get('hasFeedInvalidTag'):
            fails.append('%s: no invalid-feed-day tooltip (FEED INVALID) found on the calendar' % nm)
        if not r.get('hasFeedStrip'):
            fails.append('%s: FEED UPTIME strip under the calendar missing' % nm)
        if not r.get('hasSignalsStrip'):
            fails.append('%s: SIGNALS strip under the calendar missing' % nm)
        if not r.get('hasRatioToggle'):
            fails.append('%s: hero calibration text has no ratio-health click target' % nm)
        if not r.get('hasReadinessBanner') or not r.get('readinessIsNotReady'):
            fails.append('%s: readiness banner missing or not showing NOT READY' % nm)
        if not r.get('hasEventsPanel') or not r.get('eventRowCount'):
            fails.append('%s: event timeline missing or empty' % nm)
        if not r.get('hasNotionalLine'):
            fails.append('%s: no NOTIONAL line on a leg card' % nm)
        if not r.get('hasOosTag'):
            fails.append("%s: no NOT MIRRORED (OOS) tag on today's orders" % nm)
        if not r.get('hasRepriceNote'):
            fails.append('%s: no nightly-reprice note under CLOSED TRADES' % nm)
        if r.get('drawerClick') != 'OK' or not r.get('hasDrawerAfterClick'):
            fails.append('%s: trade drawer did not open on row click' % nm)
        if r.get('legendClick') != 'OK' or not r.get('hasLegendOffClass'):
            fails.append('%s: chart legend toggle did not mark the line off' % nm)

    r_ready = results.get('ready_1400', {})
    if not r_ready.get('err'):
        if not r_ready.get('readinessIsReady'):
            fails.append('ready_1400: readiness banner is not showing READY on the ready fixture')

    r800 = results.get('mock_800', {})
    if not r800.get('err'):
        if r800.get('ovShellDisplay') != 'block':
            fails.append('mock_800: .ov-shell did not switch to the stacked (display:block) narrow layout at 800px')

    if fails:
        print('QQQOVPROBE: FAIL')
        for f in fails:
            print('  - ' + f)
        return 1
    print('QQQOVPROBE: PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
