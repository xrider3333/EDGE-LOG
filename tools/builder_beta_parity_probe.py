#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/builder_beta_parity_probe.py -- proves BUILDER beta (augurSub='exec2',
#bb-run) queues the IDENTICAL Firestore job as the old BUILDER tab (augurSub=
'exec', #ex-run) for every equivalent settings combination.

Serves the repo over loopback, loads index.html in an iframe, injects a fixed
metaStrats/metaMasters/metaEta fixture (one strategy with a real search space,
one PINNED with every knob min==max, three masters spanning NQ/ES, 5m/1m,
RTH/ETH) and stubs btRef.add / firebase.firestore.FieldValue.serverTimestamp /
confirm / alert so nothing touches real Firestore. For each of 13 settings
combinations it (1) writes augurPrefs fresh, sets augurExecStrat, renders the
OLD tab, pokes the old-DOM-only fields that live outside augurPrefs (#ex-folds
/ #ex-master / .ex-cu custom-grid rows), clicks #ex-run and captures the job
handed to btRef.add (or null) plus any alert() text; then (2) resets augurPrefs
to the SAME object, sets window._bbUi (the new tab's carrier for those same
old-DOM-only fields), renders the NEW tab, clicks #bb-run and captures the same
two things. A case PASSES when the two jobs are deep-equal (key order does not
matter) and the two alert counts match. Case 13 pins a strategy whose every
param has min==max, which both tabs must refuse -- BUILDER with one PINNED
alert on Run, BUILDER beta by disabling Run with the pinned reason printed
above it -- so a silent crash on both sides cannot pass as "no job either way".

--baseline <path-to-another-index.html> copies that file in beside the probe
(same-origin) and re-runs ONLY the old-tab half of every case against it,
requiring those jobs to deep-equal the current file's old-tab jobs -- proof a
refactor of the OLD handler changed nothing. Typical use before shipping a
change to either Run path:
    git show origin/main:index.html > %TEMP%\\base_index.html
    python tools/builder_beta_parity_probe.py --baseline %TEMP%\\base_index.html
The first real finding (2026-09-14): BUILDER's scope <option> has no value
attribute, so the browser collapses whitespace in the preset label it queues;
BUILDER beta now does the same.

Same shape as tools/builder_render_probe.py and tools/paper_render_probe.py:
stdlib only, a subprocess call to local headless Chrome, a throwaway loopback
http.server over the repo root, a probe HTML in a temp subfolder removed in
`finally`, --dump-dom, the result JSON read back out of a <pre>. Exit 0 PASS /
1 FAIL / 2 INCONCLUSIVE (Chrome missing, or no/unreadable readout).
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

# ── fixture: metaStrats / metaMasters / metaEta, exactly as specified ──────────────
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
    # index 2 -- es_eth_master (case 12) pins the OLD tab's #ex-master to '2' == this.
    {'name': 'ES 1m ETH', 'instrument': 'ES', 'timeframe': '1m', 'session': 'eth',
     'source': 'nt_noadj_eth', 'rows': 4100000, 'date_from': '2019-01-02', 'date_to': '2026-09-11'},
]
META_ETA = {'sec_per_bt': 0.9, 'bars': 300000}
DEFAULT_STRAT = 'NOISE_1_0.py'

# ── the 13 cases: (name, strategy file, augurPrefs, old-DOM extra, new _bbUi extra) ──
# old extra: folds->#ex-folds, masterIdx->#ex-master+change, cu->.ex-cu rows
# new extra (window._bbUi): folds, cu keyed by strategy file then param then min/max/step
CASES = [
    ('single_default', DEFAULT_STRAT, {'mode': 'single'}, None, None),
    ('single_gated', DEFAULT_STRAT,
     {'mode': 'single', 'mlf': 'logistic', 'mlth': 62, 'comm_usd': 4.5, 'slip_pts': 0.25}, None, None),
    ('grid_preset', DEFAULT_STRAT,
     {'mode': 'grid', 'scope_tier': 'MEDIUM', 'workers': 6, 'min_trades': 40,
      'date_from': '2016-01-04', 'date_to': '2024-12-31'}, None, None),
    ('grid_custom', DEFAULT_STRAT, {'mode': 'grid', 'scope_tier': 'CUSTOM', 'workers': 2},
     {'cu': {'lookback': {'max': '30'}}}, {'cu': {'NOISE_1_0.py': {'lookback': {'max': '30'}}}}),
    ('auto_holdout', DEFAULT_STRAT,
     {'mode': 'auto', 'trials': 300, 'pills': False, 'lockbox': '2025-06-01', 'date_from': '2015-01-02'},
     None, None),
    ('walkforward', DEFAULT_STRAT, {'mode': 'walkforward', 'trials': 200, 'wf_mode': 'rolling'},
     {'folds': 4}, {'folds': 4}),
    ('validate_long', DEFAULT_STRAT,
     {'mode': 'validate', 'vscope': 'long', 'xfer': 'ES', 'discover': 'auto', 'equity_points': 800},
     None, None),
    ('validate_evolve', DEFAULT_STRAT,
     {'mode': 'validate', 'vscope': 'xl', 'discover': 'evolve', 'provider': 'claude-cli', 'rounds': 6},
     None, None),
    ('gate_validate', DEFAULT_STRAT, {'mode': 'gate_validate', 'mlf': 'xgb', 'lockbox': '2025-01-01'},
     None, None),
    ('ai_propose', DEFAULT_STRAT,
     {'mode': 'ai', 'rounds': 5, 'provider': 'anthropic', 'scope_tier': 'SHORT', 'workers': 3}, None, None),
    ('evolve_custom_tier', DEFAULT_STRAT,
     {'mode': 'evolve', 'rounds': 3, 'provider': 'ollama', 'scope_tier': 'CUSTOM'}, None, None),
    ('es_eth_master', DEFAULT_STRAT,
     {'mode': 'single', 'instrument': 'ES', 'timeframe': '1m', 'session': 'eth',
      'bb_master': 'ES|1m|eth|nt_noadj_eth|ES 1m ETH'},
     {'masterIdx': 2}, None),
    # PINNED: expect no job, exactly one alert, on BOTH tabs.
    ('pinned_validate', 'NOISE_1_1_SBS_V90.py', {'mode': 'validate'}, None, None),
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


# ── JS source generation (Python builds the strings; the page just evals them) ─────
STUB_JS = (
    "(function(){try{"
    "window.renderAuth=function(){};"
    "window._cap=[];window._alerts=[];"
    "window.confirm=function(){return true;};"
    "window.alert=function(m){window._alerts.push(String(m));};"
    "currentUser=currentUser||{uid:'probe-uid'};"
    "backtests=[];"
    # firebase loads over the network and may not be there -- build the path if
    # missing, then stamp OUR serverTimestamp either way (stable sentinel below).
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


def _run_js(button_id, sub, prefs, strat, extra_js, bb_ui):
    """One case, one tab: fresh prefs -> (bbUi) -> render -> DOM extras -> click -> capture."""
    bbui_js = ("window._bbUi=%s;" % json.dumps(bb_ui or {'folds': 0, 'cu': {}})) if button_id == 'bb-run' else ''
    return (
        "(function(){try{"
        "localStorage.setItem('augurPrefs',%s);"
        "augurExecStrat=%s;"
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
    ) % (json.dumps(json.dumps(prefs)), json.dumps(strat), bbui_js, json.dumps(sub),
         extra_js, json.dumps(button_id))


def build_cases_js():
    out = []
    for nm, strat, prefs, old_extra, bb_ui in CASES:
        old_js = _run_js('ex-run', 'exec', prefs, strat, _old_extra_js(old_extra), None)
        new_js = _run_js('bb-run', 'exec2', prefs, strat, '', bb_ui)
        out.append([nm, old_js, new_js])
    return json.dumps(out)


PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>builder beta parity probe</title></head>
<body style="margin:0;background:#0a0a12">
<iframe id="f" src="../index.html" style="width:1400px;height:1000px;border:0"></iframe>
__IFRAME_G__
<pre id="o"></pre>
<script>
var CASES=__CASES__, STUB=__STUB__, HAS_BASE=__HASBASE__;
(function(){
  var reported=false;
  function finish(why){
    if(reported)return; reported=true;
    var out={why:why,cases:{}};
    try{
      var fr=document.getElementById('f'), w=fr.contentWindow;
      var frB=HAS_BASE?document.getElementById('g'):null, wB=frB?frB.contentWindow:null;
      out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
      out.stub=w.eval(STUB);
      if(wB)out.stubBase=wB.eval(STUB);
      for(var i=0;i<CASES.length;i++){
        var nm=CASES[i][0], oldJs=CASES[i][1], newJs=CASES[i][2], r={};
        try{r.old=JSON.parse(w.eval(oldJs));}catch(e1){r.old={err:String(e1&&e1.stack?e1.stack:e1)};}
        try{r.new=JSON.parse(w.eval(newJs));}catch(e2){r.new={err:String(e2&&e2.stack?e2.stack:e2)};}
        if(wB){try{r.base=JSON.parse(wB.eval(oldJs));}catch(e3){r.base={err:String(e3&&e3.stack?e3.stack:e3)};}}
        out.cases[nm]=r;
      }
    }catch(e){out.err=String(e&&e.stack?e.stack:e);}
    document.getElementById('o').textContent='BBPROBE: '+JSON.stringify(out);
  }
  // renderApp is a hoisted function declaration, so it exists even if a later
  // top-level statement (e.g. firebase init, offline) threw -- but wait for it
  // explicitly rather than assuming a fixed delay is always enough.
  function waitReady(win,deadline,cb){
    var ok=false;
    try{ok=!!(win&&win.eval&&win.eval('typeof renderApp')==='function');}catch(e){}
    if(ok){cb();return;}
    if(Date.now()>deadline){cb();return;}
    setTimeout(function(){waitReady(win,deadline,cb);},150);
  }
  function boot(){
    var fr=document.getElementById('f'), w=fr.contentWindow;
    var frB=HAS_BASE?document.getElementById('g'):null, wB=frB?frB.contentWindow:null;
    var deadline=Date.now()+30000;
    waitReady(w,deadline,function(){
      if(!wB){finish('ready');return;}
      waitReady(wB,deadline,function(){finish('ready');});
    });
  }
  window.addEventListener('load',function(){setTimeout(boot,300);});
  setTimeout(function(){finish('backstop');},70000);
})();
</script>
</body></html>
"""


def run_probe(chrome, root, baseline_path):
    pdir = os.path.join(root, '_bbparity')
    if not os.path.isdir(pdir):
        os.makedirs(pdir)
    ppath = os.path.join(pdir, 'probe.html')
    bpath = os.path.join(pdir, 'baseline.html')
    has_base = baseline_path is not None
    iframe_g = ('<iframe id="g" src="baseline.html" style="width:1400px;height:1000px;border:0"></iframe>'
                if has_base else '')
    html = (PROBE_HTML.replace('__IFRAME_G__', iframe_g)
            .replace('__CASES__', build_cases_js())
            .replace('__STUB__', json.dumps(STUB_JS))
            .replace('__HASBASE__', 'true' if has_base else 'false'))
    io.open(ppath, 'w', encoding='utf-8').write(html)
    if has_base:
        shutil.copyfile(baseline_path, bpath)

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
    baseline_arg = argv[argv.index('--baseline') + 1] if '--baseline' in argv else None

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    chrome = find_chrome()
    if not chrome:
        print('BBPROBE: INCONCLUSIVE -- Chrome not found')
        return INCONCLUSIVE
    baseline_path = None
    if baseline_arg:
        baseline_path = os.path.abspath(baseline_arg)
        if not os.path.isfile(baseline_path):
            print('BBPROBE: INCONCLUSIVE -- baseline file not found: %s' % baseline_path)
            return INCONCLUSIVE

    data = run_probe(chrome, root, baseline_path)
    if data.get('harness_err'):
        print('BBPROBE: INCONCLUSIVE -- %s' % data['harness_err'])
        return INCONCLUSIVE
    if 'cases' not in data:
        print('BBPROBE: FAIL -- probe threw before any case ran: %s' % data.get('err'))
        return FAIL

    print('BBPROBE: VERSION=%s  old-tab stub=%s  baseline stub=%s'
          % (data.get('VERSION'), data.get('stub'), data.get('stubBase', '-')))
    cases = data['cases']
    fails = []
    rows = []
    for nm, strat, prefs, old_extra, bb_ui in CASES:
        r = cases.get(nm, {})
        old, new = r.get('old') or {}, r.get('new') or {}
        base = r.get('base') if baseline_path else None
        if old.get('err'):
            fails.append('%s: OLD-tab probe threw -- %s' % (nm, old['err']))
        elif not old.get('hasBtn'):
            fails.append('%s: OLD tab #ex-run not found (unexpected)' % nm)
        new_missing = not new.get('err') and not new.get('hasBtn')
        if new_missing:
            fails.append('%s: new tab missing (#bb-run not found)' % nm)
        elif new.get('err'):
            fails.append('%s: NEW-tab probe threw -- %s' % (nm, new['err']))
        old_job, new_job = old.get('job'), new.get('job')
        old_alerts, new_alerts = old.get('alerts') or [], new.get('alerts') or []
        on_eq = (not new_missing) and (not old.get('err')) and (not new.get('err')) \
            and old_job == new_job and len(old_alerts) == len(new_alerts)
        if nm == 'pinned_validate':
            # BUILDER alerts on Run; BUILDER beta refuses up front - Run disabled, the reason printed
            # above it. Same outcome (no job), different surface, so alert counts are not compared.
            on_eq = (not new_missing) and (not old.get('err')) and (not new.get('err')) \
                and old_job is None and new_job is None
        diff = None if on_eq else first_diff_key(old_job, new_job)
        if not on_eq and not new_missing and not old.get('err') and not new.get('err'):
            fails.append('%s: old vs new mismatch at %r (old=%r new=%r alerts old=%d new=%d)'
                          % (nm, diff, old_job, new_job, len(old_alerts), len(new_alerts)))
        ob_eq = None
        if base is not None:
            if base.get('err'):
                fails.append('%s: BASELINE-tab probe threw -- %s' % (nm, base['err']))
                ob_eq = False
            else:
                ob_eq = (old_job == base.get('job'))
                if not ob_eq:
                    fails.append('%s: old vs baseline mismatch at %r' % (nm, first_diff_key(old_job, base.get('job'))))
        # extra rigor on the PINNED case: a silent crash on both sides would also
        # show old_job==new_job==None -- require the refusal actually happened.
        if nm == 'pinned_validate':
            if len(old_alerts) != 1 or 'PINNED' not in (old_alerts[0] if old_alerts else ''):
                fails.append('pinned_validate: OLD tab did not raise the expected PINNED alert -- %r' % old_alerts)
            if not new_missing and not (new.get('disabled') and 'pinned' in (new.get('block') or '').lower()):
                fails.append('pinned_validate: NEW tab did not disable Run with the pinned reason -- disabled=%r block=%r alerts=%r'
                             % (new.get('disabled'), new.get('block'), new_alerts))
        rows.append((nm, new_missing, on_eq, ob_eq, diff))

    hdr = '%-20s %-12s %-14s %s' % ('CASE', 'OLD==NEW', 'OLD==BASELINE', 'FIRST DIFF')
    print(hdr)
    for nm, new_missing, on_eq, ob_eq, diff in rows:
        on_s = 'MISSING' if new_missing else str(on_eq)
        ob_s = '-' if ob_eq is None else str(ob_eq)
        print('%-20s %-12s %-14s %s' % (nm, on_s, ob_s, diff or '-'))

    sample = ((cases.get('single_default') or {}).get('old') or {}).get('job')
    print('SAMPLE JOB (single_default, OLD tab):')
    print(json.dumps(sample, indent=1, sort_keys=True))

    if fails:
        print('BBPROBE: FAIL')
        for f in fails:
            print('  - ' + f)
        return FAIL
    print('BBPROBE: PASS (%d cases%s)' % (len(CASES), ', vs baseline' if baseline_path else ''))
    return PASS


if __name__ == '__main__':
    sys.exit(main())
