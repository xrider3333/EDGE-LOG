#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/builder_parity_probe.py -- proves BUILDER (augurSub='exec2', #bb-run) still
queues the IDENTICAL Firestore job the retired BUILDER tab (augurSub='exec',
#ex-run) queued, for every equivalent settings combination.

The old tab was deleted when BUILDER beta replaced it (owner 2026-09-14: "migrate
β"), so its half of every case runs against a PINNED build pulled out of git
history: commit 24433b5, the last main that still had the old tab. The new half
runs against the current index.html. Both load in same-origin iframes over a
throwaway loopback http.server with a fixed metaStrats / metaMasters / metaEta
fixture (one strategy with a real search space, one PINNED with every knob
min==max, three masters spanning NQ/ES, 5m/1m, RTH/ETH) and stubs for btRef.add,
firebase serverTimestamp, confirm and alert, so nothing touches real Firestore.

For each case both sides get the same augurPrefs; the old side then pokes the
fields that lived outside augurPrefs (#ex-folds / #ex-master / .ex-cu rows) and
the new side sets the same through window._bbUi; each clicks its button and the
job handed to btRef.add is captured. A case PASSES when the two jobs are deep-
equal (key order ignored) and the alert counts match, except:
  * pinned_validate - both must queue nothing; the old tab with one PINNED alert,
    BUILDER by disabling Run with the pinned reason printed above it;
  * lockbox_test - the old "TEST LAST WINNER ON LOCKBOX" button against BUILDER's
    "Test the last winner on this holdout" (Holdout row), same backtests fixture.

    python tools/builder_parity_probe.py                 # baseline from git 24433b5
    python tools/builder_parity_probe.py --baseline X    # any other old-tab build

History: the first real finding (2026-09-14) was that the old tab's scope <option>
has no value attribute, so the browser collapses whitespace in the preset label it
queues; BUILDER does the same. A deliberate change to what a Run queues will fail
this probe - update the case (or pin a newer baseline) in the same change.

Same shape as tools/builder_render_probe.py and tools/paper_render_probe.py: stdlib
only, headless Chrome, --dump-dom, the result JSON read back out of a <pre>, the
probe folder removed in `finally`. Exit 0 PASS / 1 FAIL / 2 INCONCLUSIVE (Chrome
missing, git unavailable, or no readable readout).
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

PASS, FAIL, INCONCLUSIVE = 0, 1, 2
BASELINE_COMMIT = '24433b5'   # last main with the old BUILDER tab (VERSION 73.787)

META_STRATS = [
    {'file': 'NOISE_1_0.py',
     'presets': ['Short  (frozen + near plateau)', 'Medium (round-11 core)', 'Long   (full round-11 grid)'],
     'preset_combos': {'Short  (frozen + near plateau)': 1024, 'Medium (round-11 core)': 6144,
                       'Long   (full round-11 grid)': 24576},
     'params': [
         {'name': 'lookback', 'label': 'Noise lookback', 'type': 'int', 'min': 5, 'max': 120, 'step': 1},
         {'name': 'band_mult_long', 'label': 'Upper band', 'type': 'float', 'min': 0.5, 'max': 2.5, 'step': 0.25},
         {'name': 'confirm_bars', 'label': 'Confirm bars', 'type': 'int', 'min': 1, 'max': 4, 'step': 1},
     ]},
    # PINNED: every knob min==max, so Auto-Validate has no surface to search.
    {'file': 'NOISE_1_1_SBS_V90.py', 'presets': ['Short (pinned)'],
     'params': [
         {'name': 'lookback', 'type': 'int', 'min': 14, 'max': 14, 'step': 1},
         {'name': 'band_mult_long', 'type': 'float', 'min': 1.5, 'max': 1.5, 'step': 0.25},
     ]},
]
META_MASTERS = [
    {'name': 'NQ 5m RTH', 'instrument': 'NQ', 'timeframe': '5m', 'session': 'rth',
     'source': 'db_noadj_rth', 'rows': 318240, 'date_from': '2010-06-07', 'date_to': '2026-09-11'},
    {'name': 'NQ 5m RTH (TV)', 'instrument': 'NQ', 'timeframe': '5m', 'session': 'rth',
     'source': 'tv', 'rows': 201112, 'date_from': '2016-01-04', 'date_to': '2026-09-11'},
    # index 2 -- es_eth_master pins the old tab's #ex-master to '2' == this.
    {'name': 'ES 1m ETH', 'instrument': 'ES', 'timeframe': '1m', 'session': 'eth',
     'source': 'nt_noadj_eth', 'rows': 4100000, 'date_from': '2019-01-02', 'date_to': '2026-09-11'},
]
META_ETA = {'sec_per_bt': 0.9, 'bars': 300000}
DEFAULT_STRAT = 'NOISE_1_0.py'
# a finished optimization with a best config, for the lockbox test (newest first, as backtests is)
WINNER_JOBS = [
    {'id': 'job_win', 'strategy': 'NOISE_1_0.py', 'type': 'auto', 'status': 'done', 'instrument': 'NQ',
     'timeframe': '5m', 'session': 'rth', 'source': 'db_noadj_rth', 'cost_pts': 0.283, 'commission_usd': 5.66,
     'slippage_pts': 0, 'mult': 20, 'result': {'best_params': {'lookback': 14, 'band_mult_long': 1.5}}},
]

# (name, strategy, augurPrefs, old-DOM extras, new window._bbUi, options)
#   old extras: folds -> #ex-folds, masterIdx -> #ex-master + change, cu -> .ex-cu rows
#   options: backtests (fixture list), old_btn / new_btn (button ids when not the Run buttons)
CASES = [
    ('single_default', DEFAULT_STRAT, {'mode': 'single'}, None, None, None),
    ('single_gated', DEFAULT_STRAT,
     {'mode': 'single', 'mlf': 'logistic', 'mlth': 62, 'comm_usd': 4.5, 'slip_pts': 0.25}, None, None, None),
    ('grid_preset', DEFAULT_STRAT,
     {'mode': 'grid', 'scope_tier': 'MEDIUM', 'workers': 6, 'min_trades': 40,
      'date_from': '2016-01-04', 'date_to': '2024-12-31'}, None, None, None),
    ('grid_custom', DEFAULT_STRAT, {'mode': 'grid', 'scope_tier': 'CUSTOM', 'workers': 2},
     {'cu': {'lookback': {'max': '30'}}}, {'cu': {'NOISE_1_0.py': {'lookback': {'max': '30'}}}}, None),
    ('auto_holdout', DEFAULT_STRAT,
     {'mode': 'auto', 'trials': 300, 'pills': False, 'lockbox': '2025-06-01', 'date_from': '2015-01-02'},
     None, None, None),
    ('walkforward', DEFAULT_STRAT, {'mode': 'walkforward', 'trials': 200, 'wf_mode': 'rolling'},
     {'folds': 4}, {'folds': 4}, None),
    ('validate_long', DEFAULT_STRAT,
     {'mode': 'validate', 'vscope': 'long', 'xfer': 'ES', 'discover': 'auto', 'equity_points': 800},
     None, None, None),
    ('validate_evolve', DEFAULT_STRAT,
     {'mode': 'validate', 'vscope': 'xl', 'discover': 'evolve', 'provider': 'claude-cli', 'rounds': 6},
     None, None, None),
    ('gate_validate', DEFAULT_STRAT, {'mode': 'gate_validate', 'mlf': 'xgb', 'lockbox': '2025-01-01'},
     None, None, None),
    ('ai_propose', DEFAULT_STRAT,
     {'mode': 'ai', 'rounds': 5, 'provider': 'anthropic', 'scope_tier': 'SHORT', 'workers': 3}, None, None, None),
    ('evolve_custom_tier', DEFAULT_STRAT,
     {'mode': 'evolve', 'rounds': 3, 'provider': 'ollama', 'scope_tier': 'CUSTOM'}, None, None, None),
    ('es_eth_master', DEFAULT_STRAT,
     {'mode': 'single', 'instrument': 'ES', 'timeframe': '1m', 'session': 'eth',
      'bb_master': 'ES|1m|eth|nt_noadj_eth|ES 1m ETH'},
     {'masterIdx': 2}, None, None),
    ('pinned_validate', 'NOISE_1_1_SBS_V90.py', {'mode': 'validate'}, None, None, None),
    ('lockbox_test', DEFAULT_STRAT, {'mode': 'auto', 'lockbox': '2025-06-01'}, None, {'open': 'lockbox'},
     {'backtests': WINNER_JOBS, 'old_btn': 'ex-lockbox-test', 'new_btn': 'bb-lockbox-test'}),
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


STUB_JS = (
    "(function(){try{"
    "window.renderAuth=function(){};"
    "window._cap=[];window._alerts=[];"
    "window.confirm=function(){return true;};"
    "window.alert=function(m){window._alerts.push(String(m));};"
    "currentUser=currentUser||{uid:'probe-uid'};"
    "backtests=[];"
    "try{"
    "if(typeof firebase==='undefined'){window.firebase={firestore:{FieldValue:{serverTimestamp:function(){return '__TS__';}}}};}"
    "else{if(!firebase.firestore)firebase.firestore=function(){};"
    "if(!firebase.firestore.FieldValue)firebase.firestore.FieldValue={};"
    "firebase.firestore.FieldValue.serverTimestamp=function(){return '__TS__';};}"
    "}catch(_fe){}"
    "btRef={add:function(j){window._cap.push(JSON.parse(JSON.stringify(j,function(k,v){return k==='createdAt'?'__TS__':v;})));return Promise.resolve({id:'x'});}};"
    "metaStrats=" + json.dumps(META_STRATS) + ";"
    "metaMasters=" + json.dumps(META_MASTERS) + ";"
    "metaEta=" + json.dumps(META_ETA) + ";"
    "return 'OK';"
    "}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()"
)


def _old_extra_js(extra):
    if not extra:
        return ''
    parts = []
    if extra.get('folds') is not None:
        parts.append("(function(){var e=document.getElementById('ex-folds');if(e)e.value=%s;})();"
                     % json.dumps(str(extra['folds'])))
    if extra.get('masterIdx') is not None:
        parts.append(
            "(function(){var e=document.getElementById('ex-master');if(e){e.value=%s;"
            "e.dispatchEvent(new Event('change',{bubbles:true}));}})();"
            % json.dumps(str(extra['masterIdx'])))
    for p, kv in (extra.get('cu') or {}).items():
        for k, v in kv.items():
            parts.append(
                "(function(){var e=document.querySelector('.ex-cu[data-p=\"%s\"][data-k=\"%s\"]');"
                "if(e){e.value=%s;e.dispatchEvent(new Event('input',{bubbles:true}));}})();"
                % (p, k, json.dumps(str(v))))
    return ''.join(parts)


def _run_js(button_id, sub, prefs, strat, extra_js, bb_ui, bts):
    """One case, one side: fresh prefs -> backtests -> (bbUi) -> render -> DOM extras -> click -> capture."""
    bbui_js = ("window._bbUi=%s;" % json.dumps(bb_ui or {'folds': 0, 'cu': {}})) if sub == 'exec2' else ''
    return (
        "(function(){try{"
        "localStorage.setItem('augurPrefs',%s);"
        "augurExecStrat=%s;backtests=%s;"
        "%s"
        "window._cap=[];window._alerts=[];"
        "activeTab='augur';augurSub=%s;renderApp();"
        "%s"
        "var xb=document.getElementById(%s);var hasBtn=!!xb;var dis=xb?!!xb.disabled:null;"
        "if(xb)xb.click();"
        "var job=(window._cap&&window._cap.length)?window._cap[0]:null;"
        "var blk=document.querySelector('[data-bbblock]');"
        "return JSON.stringify({hasBtn:hasBtn,disabled:dis,block:blk?blk.textContent:'',job:job,alerts:(window._alerts||[]).slice()});"
        "}catch(e){return JSON.stringify({err:String(e&&e.stack?e.stack:e)});}})()"
    ) % (json.dumps(json.dumps(prefs)), json.dumps(strat), json.dumps(bts or []), bbui_js, json.dumps(sub),
         extra_js, json.dumps(button_id))


def build_cases_js():
    out = []
    for nm, strat, prefs, old_extra, bb_ui, opt in CASES:
        opt = opt or {}
        bts = opt.get('backtests')
        old_js = _run_js(opt.get('old_btn', 'ex-run'), 'exec', prefs, strat, _old_extra_js(old_extra), None, bts)
        new_js = _run_js(opt.get('new_btn', 'bb-run'), 'exec2', prefs, strat, '', bb_ui, bts)
        out.append([nm, old_js, new_js])
    return json.dumps(out)


PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>builder parity probe</title></head>
<body style="margin:0;background:#0a0a12">
<iframe id="f" src="../index.html" style="width:1400px;height:1000px;border:0"></iframe>
<iframe id="g" src="baseline.html" style="width:1400px;height:1000px;border:0"></iframe>
<pre id="o"></pre>
<script>
var CASES=__CASES__, STUB=__STUB__;
(function(){
  var reported=false;
  function finish(why){
    if(reported)return; reported=true;
    var out={why:why,cases:{}};
    try{
      var w=document.getElementById('f').contentWindow, wB=document.getElementById('g').contentWindow;
      out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
      out.VERSION_BASE=wB.eval('typeof VERSION!=="undefined"?VERSION:null');
      out.stub=w.eval(STUB);
      out.stubBase=wB.eval(STUB);
      for(var i=0;i<CASES.length;i++){
        var nm=CASES[i][0], r={};
        try{r.old=JSON.parse(wB.eval(CASES[i][1]));}catch(e1){r.old={err:String(e1&&e1.stack?e1.stack:e1)};}
        try{r.new=JSON.parse(w.eval(CASES[i][2]));}catch(e2){r.new={err:String(e2&&e2.stack?e2.stack:e2)};}
        out.cases[nm]=r;
      }
    }catch(e){out.err=String(e&&e.stack?e.stack:e);}
    document.getElementById('o').textContent='BBPROBE: '+JSON.stringify(out);
  }
  function waitReady(win,deadline,cb){
    var ok=false;
    try{ok=!!(win&&win.eval&&win.eval('typeof renderApp')==='function');}catch(e){}
    if(ok||Date.now()>deadline){cb();return;}
    setTimeout(function(){waitReady(win,deadline,cb);},150);
  }
  function boot(){
    var w=document.getElementById('f').contentWindow, wB=document.getElementById('g').contentWindow;
    var deadline=Date.now()+30000;
    waitReady(w,deadline,function(){waitReady(wB,deadline,function(){finish('ready');});});
  }
  window.addEventListener('load',function(){setTimeout(boot,300);});
  setTimeout(function(){finish('backstop');},70000);
})();
</script>
</body></html>
"""


def baseline_html(root, override):
    if override:
        return io.open(override, encoding='utf-8', newline='').read()
    r = subprocess.run(['git', '-C', root, 'show', BASELINE_COMMIT + ':index.html'],
                       capture_output=True, timeout=60)
    if r.returncode != 0:
        return None
    return r.stdout.decode('utf-8')


def run_probe(chrome, root, base_text):
    pdir = os.path.join(root, '_bbparity')
    if not os.path.isdir(pdir):
        os.makedirs(pdir)
    ppath = os.path.join(pdir, 'probe.html')
    bpath = os.path.join(pdir, 'baseline.html')
    html = PROBE_HTML.replace('__CASES__', build_cases_js()).replace('__STUB__', json.dumps(STUB_JS))
    io.open(ppath, 'w', encoding='utf-8').write(html)
    io.open(bpath, 'w', encoding='utf-8', newline='').write(base_text)

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(root))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    prof = tempfile.mkdtemp(prefix='bbparity-')
    try:
        out = subprocess.run(
            [chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
             '--user-data-dir=' + prof, '--virtual-time-budget=90000',
             '--dump-dom', 'http://127.0.0.1:%d/_bbparity/probe.html' % port],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=180).stdout
    finally:
        srv.shutdown()
        for pth in (ppath, bpath):
            try:
                os.remove(pth)
            except OSError:
                pass
        try:
            os.rmdir(pdir)
        except OSError:
            pass
        shutil.rmtree(prof, ignore_errors=True)

    m = re.search(r'BBPROBE: (\{.*\})\s*</pre>', out, re.S)
    if not m:
        return {'harness_err': 'no readout', 'raw_tail': out[-1500:]}
    try:
        return json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&')
                          .replace('&lt;', '<').replace('&gt;', '>'))
    except Exception as e:
        return {'harness_err': 'unreadable readout: %s' % e}


def first_diff_key(a, b):
    if a is None or b is None:
        return None if a == b else '(job presence)'
    for k in sorted(set(a.keys()) | set(b.keys())):
        if a.get(k) != b.get(k):
            return k
    return None


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    argv = sys.argv[1:]
    override = argv[argv.index('--baseline') + 1] if '--baseline' in argv else None
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    chrome = find_chrome()
    if not chrome:
        print('BBPROBE: INCONCLUSIVE -- Chrome not found')
        return INCONCLUSIVE
    if override and not os.path.isfile(override):
        print('BBPROBE: INCONCLUSIVE -- baseline file not found: %s' % override)
        return INCONCLUSIVE
    base_text = baseline_html(root, override)
    if not base_text:
        print('BBPROBE: INCONCLUSIVE -- could not read the baseline build (git show %s:index.html)' % BASELINE_COMMIT)
        return INCONCLUSIVE

    data = run_probe(chrome, root, base_text)
    if data.get('harness_err'):
        print('BBPROBE: INCONCLUSIVE -- %s' % data['harness_err'])
        return INCONCLUSIVE
    if 'cases' not in data:
        print('BBPROBE: FAIL -- probe threw before any case ran: %s' % data.get('err'))
        return FAIL

    print('BBPROBE: current VERSION=%s  baseline VERSION=%s (%s)  stubs=%s/%s'
          % (data.get('VERSION'), data.get('VERSION_BASE'), override or BASELINE_COMMIT,
             data.get('stub'), data.get('stubBase')))
    cases, fails, rows = data['cases'], [], []
    for nm, strat, prefs, old_extra, bb_ui, opt in CASES:
        r = cases.get(nm, {})
        old, new = r.get('old') or {}, r.get('new') or {}
        if old.get('err'):
            fails.append('%s: baseline (old tab) probe threw -- %s' % (nm, old['err']))
        elif not old.get('hasBtn'):
            fails.append('%s: baseline button not found - is that build really pre-migration?' % nm)
        if new.get('err'):
            fails.append('%s: BUILDER probe threw -- %s' % (nm, new['err']))
        elif not new.get('hasBtn'):
            fails.append('%s: BUILDER button not found' % nm)
        old_job, new_job = old.get('job'), new.get('job')
        old_alerts, new_alerts = old.get('alerts') or [], new.get('alerts') or []
        ran = not old.get('err') and not new.get('err') and old.get('hasBtn') and new.get('hasBtn')
        if nm == 'pinned_validate':
            ok = bool(ran) and old_job is None and new_job is None
            if len(old_alerts) != 1 or 'PINNED' not in (old_alerts[0] if old_alerts else ''):
                fails.append('pinned_validate: the old tab did not raise its PINNED alert -- %r' % old_alerts)
            if not (new.get('disabled') and 'pinned' in (new.get('block') or '').lower()):
                fails.append('pinned_validate: BUILDER did not disable Run with the pinned reason -- disabled=%r block=%r'
                             % (new.get('disabled'), new.get('block')))
        else:
            ok = bool(ran) and old_job is not None and old_job == new_job and len(old_alerts) == len(new_alerts)
            if ran and old_job is None:
                fails.append('%s: the old tab queued nothing (alerts %r) - the case is not testing anything' % (nm, old_alerts))
        diff = None if ok else first_diff_key(old_job, new_job)
        if ran and not ok and nm != 'pinned_validate' and old_job is not None:
            fails.append('%s: mismatch at %r (old=%r new=%r alerts old=%d new=%d)'
                         % (nm, diff, old_job, new_job, len(old_alerts), len(new_alerts)))
        rows.append((nm, ok, diff))

    print('%-20s %-7s %s' % ('CASE', 'MATCH', 'FIRST DIFF'))
    for nm, ok, diff in rows:
        print('%-20s %-7s %s' % (nm, ok, diff or '-'))
    if fails:
        print('BBPROBE: FAIL')
        for f in fails:
            print('  - ' + f)
        return FAIL
    print('BBPROBE: PASS (%d cases vs %s)' % (len(CASES), override or BASELINE_COMMIT))
    return PASS


if __name__ == '__main__':
    sys.exit(main())
