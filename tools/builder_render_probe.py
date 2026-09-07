#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/builder_render_probe.py -- verification probe for the BUILDER tab
(augurSub='exec') after the BUILD QUEUE sidebar landed in v73.532.

What it guards, in one sentence each:
  * a RUNNING job that was queued days ago still shows up (the bug: the old listener
    read the newest 12 job documents BY createdAt while the runner claims the OLDEST
    queued job first, so the running job and three waiting ones fell outside it);
  * a queued job written straight in by a script with NO createdAt at all appears,
    sorts LAST, and is labelled rather than silently given a made-up time;
  * the top-bar QUEUE chip and the sidebar report the SAME waiting count, because
    both read the shared _liveJobs() helper;
  * the RECENT section lists the finished jobs with their figures;
  * the two-column layout collapses to one column under 1200px;
  * nothing threw: no window.onerror, no 'runDetail failed' anywhere on the page.

Fixture (built in Python, injected as `backtests` through _btLive/_btRecent so the
real merge + sort code runs): 1 running (progress 29, startedAt 3h ago, createdAt
2 days ago), 3 queued (one WITHOUT createdAt), 2 done, 1 cancelled.

Same shape as tools/qqq_overview_probe.py and tools/paper_render_probe.py: stdlib
only, plus a subprocess call to local headless Chrome, serving the repo over
loopback so index.html's own fetches never fire. Exits 0 on pass, 1 on fail.
"""
import datetime
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


def _iso(hours_ago):
    d = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours_ago)
    return d.isoformat()


def build_fixture():
    """1 running / 3 queued (one with no createdAt) / 2 done / 1 cancelled.

    `live` and `recent` are handed to the app separately, exactly the way the two
    reads in subscribeAll hand them over, so _btMerge does the real sorting."""
    live = [
        # RUNNING, and DELIBERATELY the oldest thing in the set -- this is the job the
        # newest-12-by-createdAt listener used to lose.
        {"id": "job_run", "strategy": "ENGUQ_1M_ETH_ERW_1_0.py", "type": "validate",
         "status": "running", "progress": 29, "mult": 20,
         "startedAt": _iso(3), "createdAt": _iso(48)},
        # WAITING, oldest first once sorted: q_old (30h), q_mid (5h), q_none (no stamp).
        {"id": "job_q_mid", "strategy": "NOISE_5M_1_2.py", "type": "auto",
         "status": "queued", "mult": 20, "createdAt": _iso(5)},
        {"id": "job_q_old", "strategy": "ORB_R6.py", "type": "walkforward",
         "status": "queued", "mult": 20, "createdAt": _iso(30)},
        # queued straight in by a script: no createdAt at all.
        {"id": "job_q_none", "strategy": "A_noise13_wide.py", "type": "grid",
         "status": "queued", "mult": 20},
    ]
    recent = [
        {"id": "job_done_a", "strategy": "ORB_R6.py", "type": "single", "status": "done",
         "mult": 20, "createdAt": _iso(9), "run_id": 316,
         "result": {"total_pnl": 1420.5, "num_trades": 411, "profit_factor": 1.34,
                    "cache_reuse": {"hits": 180, "total": 500, "pct_reused": 36}}},
        {"id": "job_done_b", "strategy": "NOISE_5M_1_2.py", "type": "validate",
         "status": "done", "mult": 20, "createdAt": _iso(20), "repeat_of_run": 304,
         "result": {"best": {"total_pnl": -310.0, "profit_factor": 0.92},
                    "n_valid": 495, "n_combos": 495,
                    "validate": {"n_pass": 6, "n_gates": 6, "verdict": "PASS"}}},
        {"id": "job_cancel", "strategy": "TTM_1_0.py", "type": "grid",
         "status": "cancelled", "mult": 20, "createdAt": _iso(26)},
    ]
    return {"live": live, "recent": recent}


PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>builder probe</title></head>
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
      out.call=w.eval("(function(){try{"
        // the app's own auth.onAuthStateChanged(...) fires asynchronously with no signed-in
        // session and would repaint the sign-in screen over our render. Kill it first.
        +"window.renderAuth=function(){};"
        +"window._bqProbeErrors=[];"
        +"window.onerror=function(m,s,l,c,e){window._bqProbeErrors.push(String(m));};"
        +"currentUser=currentUser||{uid:'probe-uid'};"
        // hand the two reads over exactly as subscribeAll does, then let the real
        // _btMerge do the de-duping and the createdAt-DESC sort.
        +"_btLive="+JSON.stringify(FIX.live)+";"
        +"_btRecent="+JSON.stringify(FIX.recent)+";"
        +"_btMerge();"
        +"activeTab='augur';augurSub='exec';renderApp();return 'OK';"
        +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");

      out.consoleErrors=w.eval('window._bqProbeErrors||[]');

      // ── the merged array, straight out of the helper both readers use ──
      out.helper=w.eval("(function(){try{var L=_liveJobs();return JSON.stringify({"
        +"run:L.run?L.run.id:null,running:L.running.length,"
        +"waiting:L.waiting.map(function(b){return b.id;}),recent:L.recent.map(function(b){return b.id;})"
        +"});}catch(e){return 'ERR '+e;}})()");
      out.mergedOrder=w.eval("(function(){try{return (backtests||[]).map(function(b){return b.id;}).join(',');}catch(e){return 'ERR '+e;}})()");

      // ── sidebar ──
      out.hasShell=!!d.querySelector('.bq-shell');
      out.hasCard=!!d.querySelector('.bq-card');
      var cnt=d.querySelector('[data-bqcount]');
      out.countText=cnt?cnt.textContent.trim():null;
      out.runRows=d.querySelectorAll('[data-bqrunrow]').length;
      out.waitRows=d.querySelectorAll('[data-bqwaitrow]').length;
      out.recentRows=d.querySelectorAll('[data-bqrecentrow]').length;
      out.waitOrder=[].slice.call(d.querySelectorAll('[data-bqwaitrow]'))
        .map(function(e){return e.getAttribute('data-bqwaitrow');});
      var lastWait=d.querySelectorAll('[data-bqwaitrow]');
      lastWait=lastWait.length?lastWait[lastWait.length-1]:null;
      out.lastWaitId=lastWait?lastWait.getAttribute('data-bqwaitrow'):null;
      out.lastWaitHasNoTs=!!(lastWait&&lastWait.querySelector('[data-bqnots]'));
      var nots=d.querySelector('[data-bqnots]');
      out.noTsLabel=nots?nots.textContent.trim():null;
      out.noTsCount=d.querySelectorAll('[data-bqnots]').length;
      out.hasJobCtl=d.querySelectorAll('.bq-card [data-jobctl]').length;
      out.hasReuseChip=(d.querySelector('.bq-card')||{innerHTML:''}).innerHTML.indexOf('\\u267b')>=0;
      out.hasRepeatChip=(d.querySelector('.bq-card')||{innerHTML:''}).innerHTML.indexOf('REPEAT OF #304')>=0;
      out.hasOpenRun=d.querySelectorAll('[data-bqrun]').length;
      out.progressPct=(function(){var e=d.querySelector('[data-bqrunrow]');return e?e.textContent.replace(/\\s+/g,' ').trim():null;})();

      // ── top-bar chip ──
      var chip=d.querySelector('[data-queuechip]');
      out.chipText=chip?chip.textContent.replace(/\\s+/g,' ').trim():null;
      var m=out.chipText?out.chipText.match(/\\+(\\d+)/):null;
      out.chipWaiting=m?parseInt(m[1],10):null;

      // ── layout ──
      var sh=d.querySelector('.bq-shell');
      out.shellDisplay=sh?w.getComputedStyle(sh).display:null;
      var side=d.querySelector('.bq-side');
      out.sideposition=side?w.getComputedStyle(side).position:null;
      out.sideTop=side?w.getComputedStyle(side).top:null;
      out.sideWidth=side?Math.round(side.getBoundingClientRect().width):null;
      // where the pinned sub-tab strip actually ends, so the sticky top can be checked
      var bars=[].slice.call(d.querySelectorAll('div')).filter(function(e){
        return w.getComputedStyle(e).position==='sticky'&&w.getComputedStyle(e).top==='46px';});
      out.subBarBottom=bars.length?Math.round(bars[0].getBoundingClientRect().bottom):null;

      // ── nothing on the tab regressed ──
      // read the RENDERED app, not document.body -- body.innerHTML also carries the
      // whole <script> source, where the literal 'runDetail failed' legitimately lives.
      var ap=d.getElementById('app');
      var body=ap?ap.innerHTML:'';
      out.bodyLen=body.length;
      out.hasApp=!!ap;
      out.hasRunDetailFailed=body.indexOf('runDetail failed')>=0;
      out.hasRunBtn=!!d.getElementById('ex-run');
      out.hasStratSel=!!d.getElementById('ex-strat');
      out.hasExpertTgl=!!d.getElementById('ex-expert');
      out.hasLockbox=!!d.getElementById('ex-lockbox');
      out.hasOldRunsTable=body.indexOf('>BEST $<')>=0;
    }catch(e){out.err=String(e&&e.stack?e.stack:e);}
    document.getElementById('o').textContent='BLDPROBE: '+JSON.stringify(out);
  }
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){report('load');},2500);});
  setTimeout(function(){report('backstop');},30000);
})();
</script>
</body></html>
"""


def run_case(chrome, root, fixture, name, shot_path, width, height):
    pdir = os.path.join(root, '_bldprobe')
    if not os.path.isdir(pdir):
        os.makedirs(pdir)
    ppath = os.path.join(pdir, 'probe_%s.html' % name)
    html = (PROBE_HTML.replace('__FIX__', json.dumps(fixture))
            .replace('__IW__', str(width)).replace('__IH__', str(height)))
    io.open(ppath, 'w', encoding='utf-8').write(html)

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(root))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    prof = tempfile.mkdtemp(prefix='bldprobe-')
    url = 'http://127.0.0.1:%d/_bldprobe/probe_%s.html' % (port, name)
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
                 '--window-size=%d,%d' % (win_w, win_h),
                 '--screenshot=' + shot_path, url],
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

    m = re.search(r'BLDPROBE: (\{.*\})\s*</pre>', out, re.S)
    if not m:
        return {'err': 'no readout', 'raw_tail': out[-1500:]}
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

    fx = build_fixture()
    # screenshots go to the system temp dir unless a folder is given, so a probe run
    # never leaves stray PNGs in the repo root.
    out_dir = sys.argv[1] if len(sys.argv) > 1 else tempfile.gettempdir()

    results = {}
    for case, w, h in (('wide_1400', 1400, 1000), ('bp_1200', 1200, 1000),
                       ('narrow_800', 800, 1100)):
        shot = os.path.join(out_dir, 'builder_%s.png' % case)
        results[case] = run_case(chrome, ROOT, fx, case, shot, w, h)
        print('%s shot -> %s' % (case, shot))

    for nm, r in results.items():
        print(nm.upper(), ':', json.dumps(r, indent=1))

    fails = []
    for nm, r in results.items():
        if r.get('err'):
            fails.append('%s: %s' % (nm, r['err']))
            continue
        if r.get('call') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (nm, r.get('call')))
            continue
        if r.get('consoleErrors'):
            fails.append('%s: console errors -- %s' % (nm, r['consoleErrors']))
        if r.get('hasRunDetailFailed'):
            fails.append('%s: "runDetail failed" appears on the page' % nm)
        if not r.get('hasShell') or not r.get('hasCard'):
            fails.append('%s: no BUILD QUEUE card rendered' % nm)

        # RUNNING 1 / WAITING 3
        if r.get('runRows') != 1:
            fails.append('%s: expected 1 RUNNING row, got %s' % (nm, r.get('runRows')))
        if r.get('waitRows') != 3:
            fails.append('%s: expected 3 WAITING rows, got %s' % (nm, r.get('waitRows')))
        if r.get('countText') != '1 RUNNING \u00b7 3 WAITING':
            fails.append('%s: count line reads %r' % (nm, r.get('countText')))
        if '29%' not in (r.get('progressPct') or ''):
            fails.append('%s: RUNNING row does not show 29%% -- %r' % (nm, r.get('progressPct')))

        # claim order: oldest createdAt first, no-timestamp last
        if r.get('waitOrder') != ['job_q_old', 'job_q_mid', 'job_q_none']:
            fails.append('%s: WAITING is not in claim order -- %s' % (nm, r.get('waitOrder')))
        if r.get('lastWaitId') != 'job_q_none':
            fails.append('%s: the no-timestamp job did not sort last -- %s' % (nm, r.get('lastWaitId')))
        if not r.get('lastWaitHasNoTs') or r.get('noTsLabel') != 'no timestamp':
            fails.append('%s: the no-timestamp job is not labelled -- %r' % (nm, r.get('noTsLabel')))
        if r.get('noTsCount') != 1:
            fails.append('%s: expected exactly 1 no-timestamp label, got %s' % (nm, r.get('noTsCount')))

        # chip agrees with the sidebar
        chip = r.get('chipText') or ''
        if '+3' not in chip:
            fails.append('%s: chip text has no "+3" -- %r' % (nm, chip))
        if 'ENGUQ_1M_ETH_ERW_1_0' not in chip.upper():
            fails.append('%s: chip does not name the running strategy -- %r' % (nm, chip))
        if '29%' not in chip:
            fails.append('%s: chip does not show 29%% -- %r' % (nm, chip))
        if r.get('chipWaiting') != r.get('waitRows'):
            fails.append('%s: chip waiting %s != sidebar waiting %s'
                         % (nm, r.get('chipWaiting'), r.get('waitRows')))

        # RECENT
        if r.get('recentRows') != 3:
            fails.append('%s: expected 3 RECENT rows, got %s' % (nm, r.get('recentRows')))
        if not r.get('hasReuseChip'):
            fails.append('%s: the recycle (cache-reuse) chip did not survive the move' % nm)
        if not r.get('hasRepeatChip'):
            fails.append('%s: no REPEAT OF marker on the repeated job' % nm)
        if not r.get('hasOpenRun'):
            fails.append('%s: no click-to-open-run target on a finished row' % nm)
        # 2 stop/pause controls on the running job + 1 stop per waiting job
        if (r.get('hasJobCtl') or 0) < 5:
            fails.append('%s: too few [data-jobctl] controls in the card (%s)'
                         % (nm, r.get('hasJobCtl')))

        # the rest of the tab is untouched
        for key, what in (('hasRunBtn', 'RUN button'), ('hasStratSel', 'strategy dropdown'),
                          ('hasExpertTgl', 'EXPERT view toggle'), ('hasLockbox', 'lockbox field')):
            if not r.get(key):
                fails.append('%s: %s is missing from the main column' % (nm, what))
        if r.get('hasOldRunsTable'):
            fails.append('%s: the old RUNS table is still on the tab' % nm)

    # two-column, sticky, ~340px wide at and above the 1200px breakpoint
    for nm in ('wide_1400', 'bp_1200'):
        r = results.get(nm, {})
        if r.get('err'):
            continue
        if r.get('shellDisplay') != 'grid':
            fails.append('%s: .bq-shell is %r, expected grid at/above 1200px'
                         % (nm, r.get('shellDisplay')))
        if r.get('sideposition') != 'sticky':
            fails.append('%s: sidebar is %r, expected sticky' % (nm, r.get('sideposition')))
        sw = r.get('sideWidth') or 0
        if not (330 <= sw <= 350):
            fails.append('%s: sidebar width is %spx, expected ~340' % (nm, sw))
        sb = r.get('subBarBottom')
        st = r.get('sideTop')
        if sb is not None and st and st.endswith('px') and float(st[:-2]) < sb:
            fails.append('%s: sticky top %s slides under the pinned sub-tab strip, '
                         'which ends at %spx' % (nm, st, sb))
    narrow = results.get('narrow_800', {})
    if not narrow.get('err') and narrow.get('shellDisplay') != 'block':
        fails.append('narrow_800: .bq-shell is %r, expected the stacked block layout at 800px'
                     % narrow.get('shellDisplay'))

    if fails:
        print('BLDPROBE: FAIL')
        for f in fails:
            print('  - ' + f)
        return 1
    print('BLDPROBE: PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
