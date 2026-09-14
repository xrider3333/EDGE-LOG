#!/usr/bin/env python3
"""
tools/qqq_orders_probe.py -- verification probe for the ORDERS section added to the
Webull Paper Trading tab (augurSub='qqqpaper'), 2026-09-14 ("make EDGELOG's Webull paper
trading tab show the ORDER CONNECTION's state, so a halt or block is visible on the
owner's phone").

WHAT THIS COVERS. The new ORDERS card (qbOrdersHtml in index.html, right under the
existing STATUS card) reads TWO brand-new fields api/qqq_exec.py started publishing in
commits eee0253 / bfdec9a: QE.broker (built by _build_broker_status, which flattens
api/webull_orders.py's OrderAdapter.status()) and QE.lease (this host's own heartbeat).
Every other probe in this repo (qqq_overview_probe.py included) was written before those
fields existed, so none of them exercise this card beyond its "not reported yet" empty
state. This probe is the dedicated one for it.

Six cases, each rendered at a desktop width (1400) and the owner's phone width (380px),
always under the mono theme he actually runs (CLAUDE.md: mono has no green/red hue, so a
sentence-only check is the only honest one):
  a_no_broker   -- an older-shaped doc with no QE.broker/QE.lease at all (pre-eee0253) ->
                   "Order status not reported yet", never a blank section or a JS error.
  b_off         -- requested_mode=OFF, effective_mode=OFF (today's actual owner setting).
  c_paper_ok    -- effective_mode=PAPER, healthy, with a real last order (NOISE, sold,
                   10 shares, sent).
  d_blocked     -- effective_mode=PAPER but lease_ok_to_send=False (a second host's claim
                   could not be verified) -> BLOCKED pill, the owner's own wording.
  e_halted      -- halted=True via a reconcile mismatch -> HALTED pill, the owner's own
                   wording ("positions at Webull do not match the notebook").
  f_stop_tripped-- today's realized loss (-412) at/through the configured daily stop
                   (400) -> "stopped for the day", independent of broker mode.

Each case asserts: renderApp() did not throw, the ORDERS card (.qb-sec-orders) exists,
the expected plain-language sentence(s) appear inside it, zero console errors, and (at
380px) no horizontal body overflow. Not wired into wt.py ship (ad hoc verification tool,
same category as tools/qqq_overview_probe.py) -- run by hand: `python
tools/qqq_orders_probe.py`.
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


# Same injection mechanism as tools/qqq_overview_probe.py: an iframe loads the real
# index.html, we hand it a fixture directly on window._qqqExec (skipping Firestore
# entirely) and call renderApp() with augurSub='qqqpaper'.
PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>qqq orders probe</title></head>
<body style="margin:0;background:#0a0a12">
<iframe id="f" src="../index.html" style="width:__IW__px;height:__IH__px;border:0"></iframe>
<pre id="o"></pre>
<script>
var FIX=__FIX__;
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
        +"try{prefs.theme='mono';applyTheme();}catch(e){try{document.documentElement.setAttribute('data-theme','mono');}catch(e2){}}"
        +"window._qqqExec="+JSON.stringify(FIX)+";"
        +"window._qqqExecLoaded=true;window._qqqExecLoading=false;window._qqqExecErr=null;"
        +"window._qqqPaper=null;window._qqqPaperLoaded=true;window._qqqPaperLoading=false;window._qqqPaperErr=null;"
        +"window._qqqCalMonth=null;window._qeDrawerIdx=null;window._qeChartHidden={};window._qeTradesShown=50;window._qeEventsShown=30;"
        +"window._qbSheet=null;window._qbLegOpen=new Set();window._qeTradesView='list';window._qeChartPeriod='ALL';"
        +"activeTab='augur';augurSub='qqqpaper';renderApp();return 'OK';"
        +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
      out.themeApplied=d.documentElement.getAttribute('data-theme');

      var ordersEl=d.querySelector('.qb-sec-orders');
      out.hasOrdersCard=!!ordersEl;
      out.ordersText=ordersEl?ordersEl.textContent:null;
      out.ordersHtml=ordersEl?ordersEl.innerHTML:null;
      out.bodyScrollW=d.body?d.body.scrollWidth:null;
      out.overflowOk=(out.bodyScrollW==null)||(out.bodyScrollW<=IW+2);
      out.consoleErrors=w.eval('window._qeProbeErrors||[]');
      var full=(d.getElementById('app')||d.body||{}).innerHTML||'';
      out.undefCount=(full.match(/undefined/g)||[]).length;
      out.nanCount=(full.match(/NaN/g)||[]).length;
    }catch(e){out.err=String(e&&e.stack?e.stack:e);}
    document.getElementById('o').textContent='QQQORDPROBE: '+JSON.stringify(out);
  }
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){report('load');},3000);});
  setTimeout(function(){report('backstop');},30000);
})();
</script>
</body></html>
"""


def run_case(chrome, root, fixture, name, width, height):
    pdir = os.path.join(root, '_qqqordprobe')
    if not os.path.isdir(pdir):
        os.makedirs(pdir)
    ppath = os.path.join(pdir, 'probe_%s.html' % name)
    html = (PROBE_HTML.replace('__FIX__', json.dumps(fixture))
            .replace('__IW__', str(width)).replace('__IH__', str(height)))
    io.open(ppath, 'w', encoding='utf-8').write(html)

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(root))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    prof = tempfile.mkdtemp(prefix='qqqordprobe-')
    url = 'http://127.0.0.1:%d/_qqqordprobe/probe_%s.html' % (port, name)
    win_w, win_h = width + 40, height + 80
    try:
        out = subprocess.run(
            [chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
             '--user-data-dir=' + prof, '--virtual-time-budget=50000',
             '--window-size=%d,%d' % (win_w, win_h),
             '--dump-dom', url],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=180).stdout
    finally:
        srv.shutdown()
        try:
            os.remove(ppath)
            os.rmdir(pdir)
        except OSError:
            pass
        shutil.rmtree(prof, ignore_errors=True)

    m = re.search(r'QQQORDPROBE: (\{.*\})\s*</pre>', out, re.S)
    if not m:
        return {'err': 'no readout', 'raw_tail': out[-2000:]}
    try:
        return json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&')
                           .replace('&lt;', '<').replace('&gt;', '>'))
    except Exception as e:
        return {'err': 'unreadable readout: %s' % e}


def run_case_retry(chrome, root, fixture, name, width, height):
    """One retry on a non-PASS render, same rationale as report_render_probe.py's
    _report() -- headless Chrome launched back-to-back (12 renders here, often right
    after a full qqq_overview_probe.py pass) occasionally loses a race against
    index.html's own boot sequence (observed: `currentUser is not defined` when the
    iframe's `load` timeout fires a hair before the app's top-level scope finishes
    executing under system load) and throws before ever reaching augurSub='qqqpaper'.
    A REAL break in the ORDERS card fails deterministically both times; a flake does
    not, and prints a FLAKE line so it is never silently swallowed."""
    r1 = run_case(chrome, root, fixture, name, width, height)
    if not r1.get('err') and r1.get('call') == 'OK':
        return r1
    r2 = run_case(chrome, root, fixture, name, width, height)
    if not r2.get('err') and r2.get('call') == 'OK':
        print('FLAKE: %s failed once (%s) then passed on retry' % (name, r1.get('err') or r1.get('call')))
        return r2
    return r2


def _base_fixture():
    p = os.path.join(ROOT, 'tools', 'fixtures', 'qqq_exec_real.json')
    return json.load(io.open(p, encoding='utf-8'))


def _no_last_order():
    return {"leg": None, "symbol": None, "side": None, "qty": None, "intent": None,
            "mode": None, "ok": None, "sent": None, "reason": None}


def build_fixtures():
    base = _base_fixture()
    fx = {}

    # (a) no broker block at all -- the shape every doc had before eee0253/bfdec9a.
    fx['a_no_broker'] = copy.deepcopy(base)

    # (b) OFF -- today's actual owner setting (order connection mode OFF, paper orders
    # not yet enabled).
    d = copy.deepcopy(base)
    d['broker'] = {
        "requested_mode": "OFF", "effective_mode": "OFF", "mode_reason": "mode=OFF (default)",
        "environment": None, "paper_credentials_present": False, "live_credentials_present": False,
        "live_armed": False, "kill_file_present": False, "halted": False, "halt_reason": None,
        "last_error": None, "last_order": _no_last_order(), "daily_pnl": 0.0, "open_legs": [],
        "lease_ok_to_send": True, "lease_block_reason": None,
    }
    d['lease'] = {"host_id": "OWNER-PC", "leased_at": 1234567890.0}
    fx['b_off'] = d

    # (c) PAPER, healthy, with a real last order (NOISE, sold, 10 shares, sent).
    d = copy.deepcopy(base)
    d['broker'] = {
        "requested_mode": "PAPER", "effective_mode": "PAPER", "mode_reason": "PAPER credentials present",
        "environment": "sandbox", "paper_credentials_present": True, "live_credentials_present": False,
        "live_armed": False, "kill_file_present": False, "halted": False, "halt_reason": None,
        "last_error": None,
        "last_order": {"leg": "NOISE", "symbol": "QQQ", "side": "SELL", "qty": 10, "intent": "CLOSE",
                       "mode": "PAPER", "ok": True, "sent": True, "reason": ""},
        "daily_pnl": -12.5, "open_legs": ["ORB"],
        "lease_ok_to_send": True, "lease_block_reason": None,
    }
    d['lease'] = {"host_id": "OWNER-PC", "leased_at": 1234567890.0}
    fx['c_paper_ok'] = d

    # (d) BLOCKED by lease -- PAPER is armed, but this host cannot verify it is the only
    # one trading (the owner's exact wording lives in index.html's plainReason()).
    d = copy.deepcopy(base)
    d['broker'] = {
        "requested_mode": "PAPER", "effective_mode": "PAPER", "mode_reason": "PAPER credentials present",
        "environment": "sandbox", "paper_credentials_present": True, "live_credentials_present": False,
        "live_armed": False, "kill_file_present": False, "halted": False, "halt_reason": None,
        "last_error": "lease unverifiable: host 'CLOUD-VM' claims the lease but its timestamp is missing",
        "last_order": _no_last_order(), "daily_pnl": 0.0, "open_legs": [],
        "lease_ok_to_send": False,
        "lease_block_reason": "lease unverifiable: host 'CLOUD-VM' claims the lease but its timestamp is missing",
    }
    d['lease'] = {"host_id": "OWNER-PC", "leased_at": 1234567890.0}
    fx['d_blocked'] = d

    # (e) HALTED by a reconcile mismatch (webull_orders.OrderAdapter.reconcile()).
    d = copy.deepcopy(base)
    d['broker'] = {
        "requested_mode": "PAPER", "effective_mode": "PAPER", "mode_reason": "PAPER credentials present",
        "environment": "sandbox", "paper_credentials_present": True, "live_credentials_present": False,
        "live_armed": False, "kill_file_present": False, "halted": True,
        "halt_reason": "reconcile mismatch: [{'symbol': 'QQQ', 'broker': 12.0, 'believed': 22.0}]",
        "last_error": "reconcile mismatch: [{'symbol': 'QQQ', 'broker': 12.0, 'believed': 22.0}]",
        "last_order": _no_last_order(), "daily_pnl": 0.0, "open_legs": ["NOISE"],
        "lease_ok_to_send": True, "lease_block_reason": None,
    }
    d['lease'] = {"host_id": "OWNER-PC", "leased_at": 1234567890.0}
    fx['e_halted'] = d

    # (f) daily stop tripped -- independent of broker mode; uses the shadow book's own
    # today P&L against rails.daily_loss_limit_usd (see index.html comment on lossRow for
    # why -- the broker's own daily_pnl tracker has no caller yet and would always be 0).
    d = copy.deepcopy(base)
    d['broker'] = {
        "requested_mode": "OFF", "effective_mode": "OFF", "mode_reason": "mode=OFF (default)",
        "environment": None, "paper_credentials_present": False, "live_credentials_present": False,
        "live_armed": False, "kill_file_present": False, "halted": False, "halt_reason": None,
        "last_error": None, "last_order": _no_last_order(), "daily_pnl": 0.0, "open_legs": [],
        "lease_ok_to_send": True, "lease_block_reason": None,
    }
    d['lease'] = {"host_id": "OWNER-PC", "leased_at": 1234567890.0}
    d['today'] = {"trades": [], "orders": [], "realized_pnl": -412.0, "unrealized_pnl": 0.0}
    d['rails'] = copy.deepcopy(base['rails'])
    d['rails']['daily_loss_limit_usd'] = 400
    fx['f_stop_tripped'] = d

    return fx


# case -> substrings that MUST all appear inside the ORDERS card's own text (not the
# whole page -- scoped to .qb-sec-orders so a coincidental match elsewhere never counts).
EXPECT = {
    'a_no_broker': ['Order status not reported yet'],
    'b_off': ['OFF', 'Simulated only', 'OWNER-PC', 'one-computer check', 'OK',
              'No order has been attempted yet'],
    'c_paper_ok': ['PAPER', 'Webull paper', 'NOISE', 'sold', '10 shares', 'sent'],
    'd_blocked': ['BLOCKED', "can't confirm this is the only computer trading"],
    'e_halted': ['HALTED', "positions at Webull don't match the notebook"],
    'f_stop_tripped': ['stopped for the day', '$412.00', '$400.00'],
}

WIDTHS = [(1400, 1000, 'desktop'), (380, 1000, 'phone')]


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    chrome = find_chrome()
    if not chrome:
        print('INCONCLUSIVE -- chrome not found')
        return 2

    fx = build_fixtures()
    results = {}
    for case_name, fixture in fx.items():
        for width, height, tag in WIDTHS:
            key = '%s_%s' % (case_name, tag)
            results[key] = run_case_retry(chrome, ROOT, fixture, key, width, height)

    fails = []
    for case_name in fx:
        for width, height, tag in WIDTHS:
            key = '%s_%s' % (case_name, tag)
            r = results[key]
            if r.get('err'):
                fails.append('%s: %s' % (key, r['err']))
                continue
            if r.get('call') != 'OK':
                fails.append('%s: renderApp threw -- %s' % (key, r.get('call')))
                continue
            if not r.get('hasOrdersCard'):
                fails.append('%s: no .qb-sec-orders card rendered' % key)
                continue
            text = r.get('ordersText') or ''
            for needle in EXPECT[case_name]:
                if needle not in text:
                    fails.append('%s: expected text %r not found in the ORDERS card (got: %.300s)'
                                  % (key, needle, text))
            if r.get('consoleErrors'):
                fails.append('%s: console errors -- %s' % (key, r['consoleErrors']))
            if r.get('undefCount'):
                fails.append('%s: literal "undefined" appears %d times on the page' % (key, r['undefCount']))
            if r.get('nanCount'):
                fails.append('%s: literal "NaN" appears %d times on the page' % (key, r['nanCount']))
            if width == 380 and not r.get('overflowOk'):
                fails.append('%s: horizontal body overflow at 380px (scrollWidth=%s)'
                              % (key, r.get('bodyScrollW')))

    for nm, r in results.items():
        print(nm, ':', json.dumps({k: v for k, v in r.items() if k != 'ordersHtml'}, indent=1))

    if fails:
        print('QQQORDPROBE: FAIL')
        for f in fails:
            print('  - ' + f)
        return 1
    print('QQQORDPROBE: PASS (%d cases x %d widths)' % (len(fx), len(WIDTHS)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
