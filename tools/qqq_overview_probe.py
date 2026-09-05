#!/usr/bin/env python3
"""
tools/qqq_overview_probe.py -- one-off verification probe for the QQQ SHADOW BOOK
overview rebuild (v73.498), extended 2026-09-05 for the NT-parity / feed-uptime /
ratio-health additions. Renders augurSub='qqqpaper' against three fixtures --
the real 2-trade doc, a synthetic ~40-trade / 3-leg mock carrying every new field
(a parity failure, a "reconstructed" row, invalid feed days, a drifting ratio),
and a "degrade" doc that is the same book with every new field stripped out --
and saves a screenshot of each plus a text report of what it found.

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
<iframe id="f" src="../index.html" style="width:1600px;height:1400px;border:0"></iframe>
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
      out.call=w.eval("(function(){try{"
        // the app's own auth.onAuthStateChanged(user=>{...else renderAuth();}) fires
        // asynchronously (real Firebase, no signed-in session in this probe) and would
        // repaint the sign-in screen over whatever we render below -- possibly well
        // after our call returns, once the virtual-time budget runs long enough for it
        // to resolve. Neutralise it FIRST so no later firing can undo our render.
        +"window.renderAuth=function(){};"
        +"currentUser=currentUser||{uid:'probe-uid'};"
        +"window._qqqExec="+JSON.stringify(FIX)+";"
        +"window._qqqExecLoaded=true;window._qqqExecLoading=false;window._qqqExecErr=null;"
        +"window._qqqPaper=null;window._qqqPaperLoaded=true;window._qqqPaperLoading=false;window._qqqPaperErr=null;"
        +"window._qqqCalMonth=null;"
        +"activeTab='augur';augurSub='qqqpaper';renderApp();return 'OK';"
        +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
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
      // grab month label text
      var lbl=d.querySelector('.ov-cal .lbl');
      out.calMonthLabel=lbl?lbl.textContent:null;
      // rail net figure
      var net=d.querySelector('.ov-rail .rail-net');
      out.railNet=net?net.textContent:null;

      // ── NT PARITY / FEED UPTIME / RATIO HEALTH probes (2026-09-05 additions) ──
      var railGrps=[].slice.call(d.querySelectorAll('.ov-rail .rail-grp')).map(function(e){return e.textContent;});
      out.hasParityRailGrp=railGrps.indexOf('PARITY')>=0;
      out.hasFeedRailGrp=railGrps.indexOf('FEED UPTIME')>=0;
      var headerRows=[].slice.call(d.querySelectorAll('table.table thead tr')).map(function(tr){
        return [].slice.call(tr.querySelectorAll('th')).map(function(th){return th.textContent;});
      });
      out.hasNtPointsCol=headerRows.some(function(cols){return cols.indexOf('NT POINTS')>=0;});
      out.hasExpectedCol=headerRows.some(function(cols){return cols.indexOf('EXPECTED $')>=0;});
      out.hasTrackErrCol=headerRows.some(function(cols){return cols.indexOf('TRACK ERR')>=0;});
      out.hasParityChip=out.html.indexOf('PARITY NOTE')>=0||out.html.indexOf('RECONSTRUCTED')>=0;
      out.hasFeedInvalidTag=out.html.indexOf('FEED INVALID')>=0;
      out.hasFeedStrip=out.html.indexOf('FEED UPTIME \u2014 LAST')>=0;
      out.hasRatioToggle=!!d.querySelector('[data-qqqratiotoggle]');
      out.hasWebullLink=out.html.indexOf('app.webull.com')>=0;
      out.hasWebullNote=out.html.indexOf('WEBULL PAPER \u2014 not used')>=0;
      out.hasParityPanel=out.html.indexOf('NT PARITY') >= 0;
    }catch(e){out.err=String(e&&e.stack?e.stack:e);}
    document.getElementById('o').textContent='QQQOVPROBE: '+JSON.stringify(out);
  }
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){report('load');},2500);});
  setTimeout(function(){report('backstop');},30000);
})();
</script>
</body></html>
"""


def run_case(chrome, root, fixture, name, shot_path):
    pdir = os.path.join(root, '_qqqovprobe')
    if not os.path.isdir(pdir):
        os.makedirs(pdir)
    ppath = os.path.join(pdir, 'probe_%s.html' % name)
    html = PROBE_HTML.replace('__FIX__', json.dumps(fixture))
    io.open(ppath, 'w', encoding='utf-8').write(html)

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(root))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    prof = tempfile.mkdtemp(prefix='qqqovprobe-')
    url = 'http://127.0.0.1:%d/_qqqovprobe/probe_%s.html' % (port, name)
    try:
        out = subprocess.run(
            [chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
             '--user-data-dir=' + prof, '--virtual-time-budget=50000',
             '--dump-dom', url],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=180).stdout
        # separate screenshot pass (dump-dom and screenshot can't combine reliably
        # for iframe content on some Chrome builds, so do it as its own invocation)
        subprocess.run(
            [chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
             '--user-data-dir=' + prof, '--virtual-time-budget=50000',
             '--window-size=1600,1400', '--screenshot=' + shot_path, url],
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

    real_path = os.path.join(ROOT, 'tools', 'fixtures', 'qqq_exec_real.json')
    mock_path = os.path.join(ROOT, 'tools', 'fixtures', 'qqq_exec_mock.json')
    degrade_path = os.path.join(ROOT, 'tools', 'fixtures', 'qqq_exec_degrade.json')
    real = json.load(io.open(real_path, encoding='utf-8'))
    mock = json.load(io.open(mock_path, encoding='utf-8'))
    degrade = json.load(io.open(degrade_path, encoding='utf-8'))

    out_dir = sys.argv[1] if len(sys.argv) > 1 else ROOT
    real_shot = os.path.join(out_dir, 'qqq_overview_real.png')
    mock_shot = os.path.join(out_dir, 'qqq_overview_mock.png')
    degrade_shot = os.path.join(out_dir, 'qqq_overview_degrade.png')

    r1 = run_case(chrome, ROOT, real, 'real', real_shot)
    r2 = run_case(chrome, ROOT, mock, 'mock', mock_shot)
    r3 = run_case(chrome, ROOT, degrade, 'degrade', degrade_shot)

    print('REAL   :', json.dumps({k: v for k, v in r1.items() if k != 'html'}, indent=1))
    print('MOCK   :', json.dumps({k: v for k, v in r2.items() if k != 'html'}, indent=1))
    print('DEGRADE:', json.dumps({k: v for k, v in r3.items() if k != 'html'}, indent=1))
    print('Screenshots:', real_shot, mock_shot, degrade_shot)

    fails = []
    for nm, r in [('real', r1), ('mock', r2), ('degrade', r3)]:
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
        if r.get('hasWebullLink'):
            fails.append('%s: WEBULL PAPER trap link still present' % nm)
        if not r.get('hasWebullNote'):
            fails.append('%s: WEBULL PAPER "not used" note missing' % nm)
        if not r.get('hasParityRailGrp'):
            fails.append('%s: rail is missing the PARITY group' % nm)
        if not r.get('hasFeedRailGrp'):
            fails.append('%s: rail is missing the FEED UPTIME group' % nm)
        if not r.get('hasNtPointsCol') or not r.get('hasExpectedCol') or not r.get('hasTrackErrCol'):
            fails.append('%s: CLOSED TRADES is missing an NT-parity column' % nm)
        if not r.get('hasParityPanel'):
            fails.append('%s: no NT PARITY panel rendered' % nm)

    # mock-only: fields that only exist when the mock's real values are present.
    if not r2.get('err'):
        if not r2.get('hasParityChip'):
            fails.append('mock: no parity chip (RECONSTRUCTED/PARITY NOTE) rendered on any trade row')
        if not r2.get('hasFeedInvalidTag'):
            fails.append('mock: no invalid-feed-day tooltip (FEED INVALID) found on the calendar')
        if not r2.get('hasFeedStrip'):
            fails.append('mock: FEED UPTIME strip under the calendar missing')
        if not r2.get('hasRatioToggle'):
            fails.append('mock: hero calibration text has no ratio-health click target')

    if fails:
        print('QQQOVPROBE: FAIL')
        for f in fails:
            print('  - ' + f)
        return 1
    print('QQQOVPROBE: PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
