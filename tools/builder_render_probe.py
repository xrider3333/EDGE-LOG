#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/builder_render_probe.py -- verification probe for the new BUILDER tab
(augurSub='exec2', every id/class prefixed bb-/data-bb*) that replaced the
retired BUILDER (augurSub='exec', #ex-*, sidebar .bq-*) on 2026-09-14.

What it guards, in one sentence each:
  * a saved or hand-set augurSub='exec' still lands on the new tab -- renderApp
    redirects it to 'exec2' on every call, and the old tab's own markup is gone;
  * the queue rail (aside.bb-rail) shows the same running/waiting/recent picture
    the retired sidebar did: a job queued 48h ago and running right now still
    shows up, and a queued job with NO createdAt at all sorts last and carries
    its own "no timestamp" label instead of a made-up time;
  * the running row carries a pause control and a stop control, and every
    waiting row carries its own stop control;
  * a finished job's cache-reuse figure and its "repeat of #<run>" marker still
    print, and a finished job that carries a run_id is still a click-through
    into RESULTS -- both the rail's latest-result card and its own recent row;
  * the top-bar QUEUE chips agree with the rail on what is running and waiting,
    and clicking a chip from a completely different tab still lands back on
    the builder;
  * the second-level sub-tab strip offers exactly one BUILDER button (exec2,
    no beta mark) and the retired exec button no longer exists;
  * the two-column sticky-rail layout holds at and above 1200px, collapses to
    a floating pill with the rail hidden below that, and window._bbUi.queueOpen
    brings the rail back without needing a wider viewport;
  * the sticky Run button never drifts below the fold, and nothing threw: no
    window.onerror, no console.error, no 'runDetail failed' anywhere on the page.

Fixture (built in Python, handed to the app through _btLive/_btRecent and then
merged for real by _btMerge(), exactly the way subscribeAll does it): 1 running
job (progress 29, createdAt 48h ago -- deliberately the oldest thing in the
set), 3 queued jobs (one of them WITHOUT createdAt), 2 done jobs -- one with a
run_id and a cache_reuse result, one a repeat_of_run that carries its own
run_id too -- and 1 cancelled job. metaStrats/metaMasters/metaEta are stubbed
with one real strategy and one matching market, so the ticket has a data
window and a time estimate to compute rather than an empty state.

Same shape as tools/qqq_overview_probe.py and tools/paper_render_probe.py:
stdlib only, plus a subprocess call to local headless Chrome, serving the repo
over loopback so index.html's own fetches never fire, the probe HTML written
into a throwaway _bldprobe folder at the repo root and removed in `finally`.
tools/builder_parity_probe.py is the sibling that proves a Run click still
queues the identical Firestore job the retired tab queued; this probe never
clicks Run and never touches Firestore -- it only checks what renders. Exits
0 on pass, 1 on fail, 2 if Chrome cannot be found.
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
        # newest-12-by-createdAt listener used to lose, back when the sidebar first shipped.
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
        # a BOOK (several strategies pooled): figures live under result.best, mult 1. The newest done
        # job, so it is also the latest-result card - which printed $0 on the owner's real queue.
        {"id": "job_book", "strategy": "BOOK PROBE: ORB 314 + ENGU-Q 335 + NOISE 304", "type": "book",
         "status": "done", "mult": 1, "createdAt": _iso(2), "run_id": 380,
         "result": {"best": {"total_pnl": 1592187.39, "profit_factor": 1.61}, "book": {"legs": 3},
                    "validate": {"n_pass": 5, "n_gates": 6, "verdict": "PASS"}}},
        {"id": "job_done_a", "strategy": "ORB_R6.py", "type": "single", "status": "done",
         "mult": 20, "createdAt": _iso(9), "run_id": 316,
         "result": {"total_pnl": 1420.5, "num_trades": 411, "profit_factor": 1.34,
                    "cache_reuse": {"hits": 180, "total": 500, "pct_reused": 36}}},
        {"id": "job_done_b", "strategy": "NOISE_5M_1_2.py", "type": "validate",
         "status": "done", "mult": 20, "createdAt": _iso(20), "repeat_of_run": 304,
         "run_id": 305,
         "result": {"best": {"total_pnl": -310.0, "profit_factor": 0.92},
                    "n_valid": 495, "n_combos": 495,
                    "validate": {"n_pass": 6, "n_gates": 6, "verdict": "PASS"}}},
        {"id": "job_cancel", "strategy": "TTM_1_0.py", "type": "grid",
         "status": "cancelled", "mult": 20, "createdAt": _iso(26)},
    ]
    return {"live": live, "recent": recent}


def build_meta():
    """One real strategy + one matching market, so the ticket has a data window and
    a time estimate to draw instead of the "no data yet" empty state. The instrument/
    timeframe/session line up with what a fresh augurPrefs defaults to (NQ/5m/RTH)."""
    strats = [{
        "file": "NOISE_1_0.py",
        "presets": ["Short  (frozen + near plateau)", "Medium (round-11 core)"],
        "params": [{"name": "lookback", "label": "Noise lookback", "type": "int",
                     "min": 5, "max": 120, "step": 1}],
        "preset_combos": {"Short  (frozen + near plateau)": 9, "Medium (round-11 core)": 48},
    }]
    masters = [{
        "name": "NQ 5m RTH", "instrument": "NQ", "timeframe": "5m", "session": "rth",
        "source": "db_noadj_rth", "rows": 318240,
        "date_from": "2010-06-07", "date_to": "2026-09-11",
    }]
    eta = {"sec_per_bt": 0.9, "bars": 300000}
    return {"strats": strats, "masters": masters, "eta": eta}


PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>builder probe</title></head>
<body style="margin:0;background:#0a0a12">
<iframe id="f" src="../index.html" style="width:__IW__px;height:__IH__px;border:0"></iframe>
<pre id="o"></pre>
<script>
(function(){
  var reported=false;
  function report(why){
    if(reported)return; reported=true;
    var out={why:why};
    try{
      var fr=document.getElementById('f'), w=fr.contentWindow, d=fr.contentDocument;
      out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');

      // ── drive the app: kill auth, hang the fixture off _btLive/_btRecent, merge it
      //    through the real _btMerge, then force the redirect every case exercises ──
      out.call=w.eval(`(function(){try{
        window.renderAuth=function(){};
        window._bbProbeErr=[];
        window.onerror=function(m,s,l,c,e){window._bbProbeErr.push('onerror: '+String(m));};
        window._bbProbeCE=console.error.bind(console);
        console.error=function(){window._bbProbeErr.push('console.error: '+Array.prototype.slice.call(arguments).join(' '));window._bbProbeCE.apply(console,arguments);};
        currentUser=currentUser||{uid:'probe-uid'};
        metaStrats=__METASTRATS__;
        metaMasters=__METAMASTERS__;
        metaEta=__METAETA__;
        _btLive=__LIVE__;
        _btRecent=__RECENT__;
        _btMerge();
        localStorage.setItem('augurPrefs', JSON.stringify({mode:'validate'}));
        __OPEN__
        activeTab='augur';augurSub='exec';renderApp();
        return 'OK';
      }catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()`);

      out.augurSubAfterRedirect=w.eval("typeof augurSub!=='undefined'?augurSub:null");

      // ── shape: [data-bb] > .bb-shell > (.bb-main, aside.bb-rail) ──
      out.hasBB=!!d.querySelector('[data-bb]');
      out.hasShell=!!d.querySelector('.bb-shell');
      out.hasMain=!!d.querySelector('.bb-shell>.bb-main');
      out.hasRailEl=!!d.querySelector('.bb-shell>aside.bb-rail');

      // ── header ──
      out.hasStrat=!!d.getElementById('bb-strat');
      out.hasMarket=!!d.getElementById('bb-market');
      out.hasGoalBacktest=!!d.getElementById('bb-goal-backtest');
      out.hasGoalOptimize=!!d.getElementById('bb-goal-optimize');
      out.hasGoalValidate=!!d.getElementById('bb-goal-validate');
      out.hasGoalAi=!!d.getElementById('bb-goal-ai');
      var runBtn=d.getElementById('bb-run');
      out.hasRunBtn=!!runBtn;
      var barEl=runBtn?runBtn.closest('.bb-bar'):null;
      out.runInBar=!!barEl;
      out.barPosition=barEl?w.getComputedStyle(barEl).position:null;
      out.barBottom=barEl?w.getComputedStyle(barEl).bottom:null;

      // ── rail: latest result + queue ──
      out.hasLastCard=!!d.querySelector('.bb-last');
      var lastBig=d.querySelector('.bb-last .bb-big');
      out.lastBig=lastBig?lastBig.textContent.trim():null;
      var lastSub=d.querySelector('.bb-last .bb-lastsub');
      out.lastSub=lastSub?lastSub.textContent.trim():null;
      var bookRow=d.querySelector('[data-bbrecentrow="job_book"]');
      out.bookRowText=bookRow?bookRow.textContent.replace(/\\s+/g,' ').trim():null;
      var cnt=d.querySelector('[data-bbcount]');
      out.countText=cnt?cnt.textContent.trim():null;

      var runRows=[].slice.call(d.querySelectorAll('[data-bbrunrow]'));
      out.runRows=runRows.length;
      var runRow0=runRows.length?runRows[0]:null;
      out.runRowText=runRow0?runRow0.textContent.replace(/\\s+/g,' ').trim():null;
      out.runRowHasPause=!!(runRow0&&runRow0.querySelector('button[data-bbctl="pause"]'));
      out.runRowHasRun=!!(runRow0&&runRow0.querySelector('button[data-bbctl="run"]'));
      out.runRowHasStop=!!(runRow0&&runRow0.querySelector('button[data-bbctl="stop"]'));

      var waitRows=[].slice.call(d.querySelectorAll('[data-bbwaitrow]'));
      out.waitRows=waitRows.length;
      out.waitOrder=waitRows.map(function(e){return e.getAttribute('data-bbwaitrow');});
      var lastWait=waitRows.length?waitRows[waitRows.length-1]:null;
      out.lastWaitId=lastWait?lastWait.getAttribute('data-bbwaitrow'):null;
      out.lastWaitHasNoTs=!!(lastWait&&lastWait.querySelector('[data-bbnots]'));
      var nots=d.querySelector('[data-bbnots]');
      out.noTsLabel=nots?nots.textContent.trim():null;
      out.noTsCount=d.querySelectorAll('[data-bbnots]').length;
      out.waitStopCounts=waitRows.map(function(e){return e.querySelectorAll('button[data-bbctl="stop"]').length;});

      out.recentRows=d.querySelectorAll('[data-bbrecentrow]').length;
      var qCard=d.querySelector('.bb-q');
      var qHtml=qCard?qCard.innerHTML:'';
      out.hasReuseChip=qHtml.indexOf('\\u267b 180/500')>=0;
      out.hasRepeatChip=qHtml.indexOf('repeat of #304')>=0;
      var doneARow=d.querySelector('[data-bbrecentrow="job_done_a"]');
      out.doneARunId=doneARow?doneARow.getAttribute('data-bbrun'):null;
      var doneBRow=d.querySelector('[data-bbrecentrow="job_done_b"]');
      out.doneBRunId=doneBRow?doneBRow.getAttribute('data-bbrun'):null;

      // ── top-bar queue chips ──
      var chips=d.querySelectorAll('[data-queuechip]');
      out.chipCount=chips.length;
      out.firstChipText=chips.length?chips[0].textContent.replace(/\\s+/g,' ').trim():null;

      // ── sub-tab strip: exactly one BUILDER, the retired button gone ──
      out.subExec2Count=d.querySelectorAll('[data-asubtop="exec2"]').length;
      var subExec2=d.querySelector('[data-asubtop="exec2"]');
      out.subExec2Text=subExec2?subExec2.textContent.trim():null;
      out.subExecCount=d.querySelectorAll('[data-asubtop="exec"]').length;

      // ── layout ──
      var shell=d.querySelector('.bb-shell');
      out.shellGridCols=shell?w.getComputedStyle(shell).gridTemplateColumns:null;
      var rail=d.querySelector('.bb-rail');
      out.railDisplay=rail?w.getComputedStyle(rail).display:null;
      out.railPosition=rail?w.getComputedStyle(rail).position:null;
      var qpill=d.getElementById('bb-qpill');
      out.qpillDisplay=qpill?w.getComputedStyle(qpill).display:null;
      var bbRoot=d.querySelector('[data-bb]');
      out.rootHasQopen=!!(bbRoot&&bbRoot.classList.contains('qopen'));

      // ── nothing regressed ──
      var ap=d.getElementById('app');
      out.hasApp=!!ap;
      out.hasRunDetailFailed=(ap?ap.innerHTML:'').indexOf('runDetail failed')>=0;

      // ── the sticky Run button stays on screen ──
      if(runBtn){
        var rc=runBtn.getBoundingClientRect();
        out.runBottom=rc.bottom;out.innerHeight=w.innerHeight;
        out.runFits=rc.bottom<=w.innerHeight+0.5;
      }

      // ── a queue chip clicked from a completely different tab returns to the builder ──
      out.clickFlow=w.eval(`(function(){try{
        augurSub='runs';renderApp();
        var c=document.querySelector('[data-queuechip]');
        if(!c)return {ok:false,why:'no chip found'};
        c.click();
        return {ok:true,augurSub:(typeof augurSub!=='undefined'?augurSub:null),activeTab:(typeof activeTab!=='undefined'?activeTab:null)};
      }catch(e){return {ok:false,why:String(e&&e.stack?e.stack:e)};}})()`);

      out.consoleErrors=w.eval('window._bbProbeErr||[]');
    }catch(e){out.err=String(e&&e.stack?e.stack:e);}
    document.getElementById('o').textContent='BLDPROBE: '+JSON.stringify(out);
  }
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){report('load');},2500);});
  setTimeout(function(){report('backstop');},30000);
})();
</script>
</body></html>
"""


def run_case(chrome, root, fixture, meta, name, shot_path, width, height, open_queue=False):
    pdir = os.path.join(root, '_bldprobe')
    if not os.path.isdir(pdir):
        os.makedirs(pdir)
    ppath = os.path.join(pdir, 'probe_%s.html' % name)
    open_js = 'window._bbUi={queueOpen:true};' if open_queue else ''
    html = (PROBE_HTML
            .replace('__LIVE__', json.dumps(fixture['live']))
            .replace('__RECENT__', json.dumps(fixture['recent']))
            .replace('__METASTRATS__', json.dumps(meta['strats']))
            .replace('__METAMASTERS__', json.dumps(meta['masters']))
            .replace('__METAETA__', json.dumps(meta['eta']))
            .replace('__OPEN__', open_js)
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
    meta = build_meta()
    # screenshots go to the system temp dir unless a folder is given, so a probe run
    # never leaves stray PNGs in the repo root.
    out_dir = sys.argv[1] if len(sys.argv) > 1 else tempfile.gettempdir()

    cases = (
        ('wide_1400', 1400, 1000, False),
        ('bp_1200', 1200, 1000, False),
        ('narrow_800', 800, 1100, False),
        ('narrow_800_open', 800, 1100, True),
    )
    results = {}
    for case, w, h, openq in cases:
        shot = os.path.join(out_dir, 'builder_%s.png' % case)
        results[case] = run_case(chrome, ROOT, fx, meta, case, shot, w, h, openq)
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
        if r.get('hasRunDetailFailed'):
            fails.append('%s: "runDetail failed" appears on the page' % nm)
        if not r.get('hasApp'):
            fails.append('%s: #app did not render' % nm)

        # the redirect every case exercises: a stale/typed augurSub='exec' lands on exec2
        if r.get('augurSubAfterRedirect') != 'exec2':
            fails.append("%s: augurSub='exec' did not redirect to 'exec2' -- got %r"
                         % (nm, r.get('augurSubAfterRedirect')))
        if not r.get('hasBB'):
            fails.append('%s: [data-bb] root did not render' % nm)

        # shape: .bb-shell = .bb-main + aside.bb-rail
        if not r.get('hasShell') or not r.get('hasMain') or not r.get('hasRailEl'):
            fails.append('%s: .bb-shell / .bb-main / aside.bb-rail is missing' % nm)

        # header
        for key, what in (('hasStrat', '#bb-strat'), ('hasMarket', '#bb-market'),
                          ('hasGoalBacktest', '#bb-goal-backtest'), ('hasGoalOptimize', '#bb-goal-optimize'),
                          ('hasGoalValidate', '#bb-goal-validate'), ('hasGoalAi', '#bb-goal-ai'),
                          ('hasRunBtn', '#bb-run')):
            if not r.get(key):
                fails.append('%s: %s is missing' % (nm, what))
        if not r.get('runInBar'):
            fails.append('%s: #bb-run is not inside .bb-bar' % nm)
        if r.get('barPosition') != 'sticky':
            fails.append('%s: .bb-bar position is %r, expected sticky' % (nm, r.get('barPosition')))
        if r.get('barBottom') != '10px':
            fails.append('%s: .bb-bar bottom is %r, expected 10px' % (nm, r.get('barBottom')))

        # rail: latest-result card
        if not r.get('hasLastCard'):
            fails.append('%s: .bb-last is missing though a done job carries a run_id' % nm)
        # the newest done job is a BOOK: its net comes from result.best at mult 1, and it keeps its own name
        if r.get('lastBig') != '+$1,592,187':
            fails.append('%s: latest-result card reads %r, expected the BOOK net +$1,592,187' % (nm, r.get('lastBig')))
        if not (r.get('lastSub') or '').startswith('BOOK PROBE: ORB 314') or 'PASS 5/6' not in (r.get('lastSub') or ''):
            fails.append('%s: latest-result subtitle lost the BOOK name or its verdict -- %r' % (nm, r.get('lastSub')))
        if '+$1,592,187' not in (r.get('bookRowText') or '') or 'Book' not in (r.get('bookRowText') or ''):
            fails.append('%s: the BOOK recent row does not show Book and +$1,592,187 -- %r' % (nm, r.get('bookRowText')))

        # queue count / running row
        if r.get('countText') != '1 running \u00b7 3 up next':
            fails.append('%s: queue count line reads %r' % (nm, r.get('countText')))
        if r.get('runRows') != 1:
            fails.append('%s: expected 1 running row, got %s' % (nm, r.get('runRows')))
        if '29%' not in (r.get('runRowText') or ''):
            fails.append('%s: running row does not show 29%% -- %r' % (nm, r.get('runRowText')))
        if not r.get('runRowHasPause'):
            fails.append('%s: running row has no data-bbctl="pause" control' % nm)
        if r.get('runRowHasRun'):
            fails.append('%s: running row has a data-bbctl="run" (resume) control though the job is not paused' % nm)
        if not r.get('runRowHasStop'):
            fails.append('%s: running row has no data-bbctl="stop" control' % nm)

        # waiting: claim order, no-timestamp sorts last and is labelled, one stop control each
        if r.get('waitRows') != 3:
            fails.append('%s: expected 3 waiting rows, got %s' % (nm, r.get('waitRows')))
        if r.get('waitOrder') != ['job_q_old', 'job_q_mid', 'job_q_none']:
            fails.append('%s: waiting is not in claim order -- %s' % (nm, r.get('waitOrder')))
        if r.get('lastWaitId') != 'job_q_none':
            fails.append('%s: the no-timestamp job did not sort last -- %s' % (nm, r.get('lastWaitId')))
        if not r.get('lastWaitHasNoTs') or r.get('noTsLabel') != 'no timestamp':
            fails.append('%s: the no-timestamp job is not labelled -- %r' % (nm, r.get('noTsLabel')))
        if r.get('noTsCount') != 1:
            fails.append('%s: expected exactly 1 no-timestamp label, got %s' % (nm, r.get('noTsCount')))
        if r.get('waitStopCounts') != [1, 1, 1]:
            fails.append('%s: each waiting row should carry exactly one stop control -- %s'
                         % (nm, r.get('waitStopCounts')))

        # recent: figures survived the move, and finished jobs link their run
        if r.get('recentRows') != 4:
            fails.append('%s: expected 4 recent rows, got %s' % (nm, r.get('recentRows')))
        if not r.get('hasReuseChip'):
            fails.append('%s: the cache-reuse chip (\u267b 180/500) did not survive the move' % nm)
        if not r.get('hasRepeatChip'):
            fails.append('%s: no "repeat of #304" marker on the repeated job' % nm)
        if r.get('doneARunId') != '316':
            fails.append('%s: the done single job does not link run #316 -- data-bbrun=%r'
                         % (nm, r.get('doneARunId')))
        if r.get('doneBRunId') != '305':
            fails.append('%s: the done validate job does not link run #305 -- data-bbrun=%r'
                         % (nm, r.get('doneBRunId')))

        # top-bar chips agree with the rail
        if r.get('chipCount') != 4:
            fails.append('%s: expected 4 top-bar queue chips (1 running + 3 waiting), got %s'
                         % (nm, r.get('chipCount')))
        chip = r.get('firstChipText') or ''
        if 'ENGUQ_1M_ETH_ERW' not in chip:
            fails.append('%s: first chip does not name the running strategy -- %r' % (nm, chip))
        if '29%' not in chip:
            fails.append('%s: first chip does not show 29%% -- %r' % (nm, chip))

        # sub-tab strip: exactly one BUILDER, no beta mark, the retired button is gone
        if r.get('subExec2Count') != 1:
            fails.append('%s: expected exactly one [data-asubtop="exec2"] button, got %s'
                         % (nm, r.get('subExec2Count')))
        subtxt = r.get('subExec2Text') or ''
        if 'BUILDER' not in subtxt.upper():
            fails.append('%s: [data-asubtop="exec2"] does not read BUILDER -- %r' % (nm, subtxt))
        if '\u03b2' in subtxt:
            fails.append('%s: [data-asubtop="exec2"] still shows a beta mark -- %r' % (nm, subtxt))
        if r.get('subExecCount'):
            fails.append('%s: the retired [data-asubtop="exec"] button still exists' % nm)

        # the sticky Run button never drifts below the fold - with the queue folded. Opening the queue
        # on a narrow screen deliberately puts the whole list above the ticket, so Run may sit below it.
        if nm.endswith('_open'):
            pass
        elif r.get('runFits') is False:
            fails.append('%s: #bb-run bottom (%.1fpx) is below the viewport (%.1fpx)'
                         % (nm, r.get('runBottom') or -1, r.get('innerHeight') or -1))
        elif r.get('runFits') is None:
            fails.append('%s: could not measure #bb-run against the viewport' % nm)

        # a queue chip clicked from a different tab returns to the builder
        cf = r.get('clickFlow') or {}
        if not cf.get('ok'):
            fails.append('%s: clicking the first queue chip failed -- %s' % (nm, cf.get('why')))
        elif cf.get('augurSub') != 'exec2':
            fails.append('%s: clicking the first queue chip left augurSub=%r, expected exec2'
                         % (nm, cf.get('augurSub')))

        # nothing threw across the whole run: setup, both renders, and the click
        if r.get('consoleErrors'):
            fails.append('%s: console/window errors -- %s' % (nm, r['consoleErrors']))

    # layout: two columns + sticky rail at and above 1200px; a floating pill with the
    # rail collapsed below that; queueOpen brings the rail back without a wider viewport
    for nm in ('wide_1400', 'bp_1200'):
        r = results.get(nm, {})
        if r.get('err') or r.get('call') != 'OK':
            continue
        cols = (r.get('shellGridCols') or '').split()
        if len(cols) != 2:
            fails.append('%s: .bb-shell grid-template-columns is %r, expected 2 tracks at/above 1200px'
                         % (nm, r.get('shellGridCols')))
        if r.get('railDisplay') == 'none':
            fails.append('%s: .bb-rail is hidden, expected visible at/above 1200px' % nm)
        if r.get('railPosition') != 'sticky':
            fails.append('%s: .bb-rail position is %r, expected sticky' % (nm, r.get('railPosition')))
        if r.get('qpillDisplay') != 'none':
            fails.append('%s: #bb-qpill is %r, expected hidden at/above 1200px' % (nm, r.get('qpillDisplay')))

    narrow = results.get('narrow_800', {})
    if not narrow.get('err') and narrow.get('call') == 'OK':
        cols = (narrow.get('shellGridCols') or '').split()
        if len(cols) != 1:
            fails.append('narrow_800: .bb-shell grid-template-columns is %r, expected 1 track below 1200px'
                         % narrow.get('shellGridCols'))
        if narrow.get('railDisplay') != 'none':
            fails.append('narrow_800: .bb-rail is %r, expected hidden below 1200px' % narrow.get('railDisplay'))
        if narrow.get('qpillDisplay') != 'inline-flex':
            fails.append('narrow_800: #bb-qpill is %r, expected visible below 1200px' % narrow.get('qpillDisplay'))
        if narrow.get('rootHasQopen'):
            fails.append('narrow_800: root already carries class qopen though queueOpen was never set')

    nopen = results.get('narrow_800_open', {})
    if not nopen.get('err') and nopen.get('call') == 'OK':
        if not nopen.get('rootHasQopen'):
            fails.append('narrow_800_open: root does not carry class qopen though window._bbUi.queueOpen was set')
        if nopen.get('railDisplay') == 'none':
            fails.append('narrow_800_open: .bb-rail stayed hidden though queueOpen was set')
        if nopen.get('qpillDisplay') != 'inline-flex':
            fails.append('narrow_800_open: #bb-qpill is %r, expected still visible' % nopen.get('qpillDisplay'))

    if fails:
        print('BLDPROBE: FAIL')
        for f in fails:
            print('  - ' + f)
        return 1
    print('BLDPROBE: PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
