#!/usr/bin/env python3
"""
tools/import_tz_probe.py -- gate for TRADING LOG > IMPORT: imported trade times must be US/Eastern.

WHY THIS EXISTS
---------------
NinjaTrader's web exports (Position History, Performance, Orders, and the Timestamp column of
Fills) print times in whatever zone the platform is set to DISPLAY, with no label. The owner's
own downloads flip between Pacific (Apr 9-17, Jun 1-28 2026) and Eastern (Apr 22 - May 23). The
importer's old parseDT built a Date in the DEVICE's zone and read it back the same way, so it
saved whatever wall-clock was printed: a Pacific export landed 3 hours EARLY, the daily PDF
statement (which prints GMT) landed 4 hours LATE, and every SHORT had its entry and exit times
swapped. Journal rows from Apr 15 - May 18 then carried a 3-hour error that had to be repaired by
hand on 2026-09-23. The 2026-09-24 fix resolves each file's zone first (Fills fill ids > EXPORT TIME ZONE
pick > market hours > ask the owner) and saves every time in Eastern.

WHAT IT DOES
------------
Serves the repo over loopback, loads index.html in an iframe exactly as the boot gate does, and
feeds the app's own importCSV / importPDF SYNTHETIC NinjaTrader exports built below from a small
table of trades with known UTC fill times (no real account data is used or committed). The PDF
text is handed to importPDF through a stand-in pdf.js (headless Chrome under virtual time never
finishes pdf.js's worker). Nothing is committed: commitImport is never called and no one is
signed in, so nothing can reach Firestore.

WHAT IT ASSERTS
---------------
  * every saved entryTime / exitTime / date equals the true New York time of the entry / exit
    fill (so a short's entry is its SELL), for:
      - a Position History export printed in Pacific, with no other help   (market hours)
      - the same trades printed in Eastern                                  (market hours)
      - a Performance export printed in Pacific                             (market hours)
      - a one-trade Eastern file plus fill times from a Fills export       (proof by fill id)
      - the one-trade file with EXPORT TIME ZONE = Eastern                   (owner's pick)
      - a daily PDF statement printing GMT, summer and winter dates         (absolute)
  * the one-trade file with no help is HELD: nothing saved, a zone question returned
  * picking Eastern for the Pacific export is HELD too (market hours flatly contradict it)
  * a journal trade already saved 3 hours late is FLAGGED when the same trade is re-imported,
    and not rewritten
  * the Fills export itself is read as the source of absolute times

Exit codes match preflight_boot.py: 0 PASS, 1 FAIL, 2 INCONCLUSIVE (never blocks).

Usage:
  python tools/import_tz_probe.py                # gates this repo's index.html
  python tools/import_tz_probe.py --file X.html  # gates X as if it were index.html
  python tools/import_tz_probe.py --selftest     # asserts FAIL on the last build before the fix
                                                 # (v73.885, from git history), PASS on this one

Stdlib only, plus a subprocess call to local Chrome.
"""
import argparse
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
import time
from datetime import datetime, timedelta, timezone

PASS, FAIL, INCONCLUSIVE = 0, 1, 2

# The last build before the fix: it saved printed wall-clock times as-is. --selftest asserts
# this gate FAILS it.
KNOWN_BAD = [('5326d02', '73.885', 'saved NinjaTrader export times exactly as printed')]

# (symbol, direction, entry UTC, exit UTC, entry price, exit price, buy fill id, sell fill id)
# Summer rows are EDT (UTC-4), the MNQ row is EST (UTC-5). Times are spread across the session so
# market hours can tell Eastern from Pacific on the multi-trade files.
TRADES = [
    ('MES', 'LONG', '2026-04-07 14:29:06.336', '2026-04-07 14:31:40.120', 6604.75, 6605.00, '9900001', '9900002'),
    ('MES', 'SHORT', '2026-04-08 19:10:01.583', '2026-04-08 19:12:43.004', 6802.75, 6800.25, '9900004', '9900003'),
    ('MES', 'LONG', '2026-04-09 13:33:52.911', '2026-04-09 13:34:28.410', 6834.75, 6835.75, '9900005', '9900006'),
    ('MNQ', 'LONG', '2026-01-15 15:00:05.250', '2026-01-15 15:05:00.700', 21215.00, 21229.75, '9900007', '9900008'),
    ('MES', 'SHORT', '2026-04-10 15:50:17.100', '2026-04-10 15:58:13.900', 6861.50, 6854.25, '9900010', '9900009'),
]
# One mid-day trade: Eastern, Central and Pacific readings all land in market hours.
SMALL = [('MES', 'LONG', '2026-04-14 15:05:10.500', '2026-04-14 15:07:40.250', 6956.75, 6957.00, '9900011', '9900012')]
MULT = {'MES': 5.0, 'MNQ': 2.0}


def _utc(s):
    return datetime.strptime(s, '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=timezone.utc)


def _us_dst(d):
    """US DST window for this year (2nd Sunday of March 02:00 local .. 1st Sunday of Nov)."""
    y = d.year
    mar = datetime(y, 3, 8) + timedelta(days=(6 - datetime(y, 3, 8).weekday()) % 7)
    nov = datetime(y, 11, 1) + timedelta(days=(6 - datetime(y, 11, 1).weekday()) % 7)
    return mar, nov


def _local(u, std_off):
    """UTC -> wall-clock in a US zone with standard offset std_off hours (DST adds 1)."""
    w = u.replace(tzinfo=None) + timedelta(hours=std_off)
    mar, nov = _us_dst(w)
    if mar.replace(hour=2) <= w < nov.replace(hour=1):
        w += timedelta(hours=1)
    return w


def et(u):
    return _local(u, -5)


def pt(u):
    return _local(u, -8)


def _legs(t):
    """(buy utc, sell utc, buy px, sell px) for a trade row."""
    sym, d, eu, xu, epx, xpx, bf, sf = t
    eu, xu = _utc(eu), _utc(xu)
    return (eu, xu, epx, xpx) if d == 'LONG' else (xu, eu, xpx, epx)


def position_history(rows, disp):
    hdr = ('Position ID,Timestamp,Trade Date,Net Pos,Net Price,Bought,Avg. Buy,Sold,Avg. Sell,Account,'
           'Contract,Product,Product Description,_priceFormat,_priceFormatType,_tickSize,Pair ID,'
           'Buy Fill ID,Sell Fill ID,Paired Qty,Buy Price,Sell Price,P/L,Currency,Bought Timestamp,'
           'Sold Timestamp')
    out = [hdr]
    for i, t in enumerate(rows):
        sym, d, eu, xu, epx, xpx, bf, sf = t
        bu, su, bpx, spx = _legs(t)
        f = lambda u: disp(u).strftime('%m/%d/%Y %H:%M:%S')
        close = max(bu, su)
        pl = (spx - bpx) * MULT[sym]
        out.append(','.join([
            str(880000 + i), f(close), et(_utc(eu)).strftime('%Y-%m-%d'), '0', '', '1', '%.2f' % bpx, '1',
            '%.2f' % spx, 'DEMO123', sym + 'M6', sym, 'Micro contract', '-2', '0', '0.25', str(890000 + i),
            bf, sf, '1', '%.2f' % bpx, '%.2f' % spx, '%.2f' % pl, 'USD', f(bu), f(su)]))
    return '\r\n'.join(out) + '\r\n'


def performance(rows, disp):
    out = ['symbol,_priceFormat,_priceFormatType,_tickSize,buyFillId,sellFillId,qty,buyPrice,sellPrice,'
           'pnl,boughtTimestamp,soldTimestamp,duration']
    for t in rows:
        sym, d, eu, xu, epx, xpx, bf, sf = t
        bu, su, bpx, spx = _legs(t)
        f = lambda u: disp(u).strftime('%m/%d/%Y %H:%M:%S')
        pl = (spx - bpx) * MULT[sym]
        pls = ('$%.2f' % pl) if pl >= 0 else ('$(%.2f)' % -pl)
        out.append(','.join([sym + 'M6', '-2', '0', '0.25', bf, sf, '1', '%.2f' % bpx, '%.2f' % spx, pls,
                             f(bu), f(su), '1min']))
    return '\r\n'.join(out) + '\r\n'


def fills(rows, disp):
    out = ['_id,_orderId,_contractId,_timestamp,_tradeDate,_action,_qty,_price,_active,_accountId,Fill ID,'
           'Order ID,Timestamp,Date,Account,B/S,Quantity,Price,_priceFormat,_priceFormatType,_tickSize,'
           'Contract,Product,Product Description,commission']
    for t in rows:
        sym, d, eu, xu, epx, xpx, bf, sf = t
        bu, su, bpx, spx = _legs(t)
        for fid, u, px, side in ((bf, bu, bpx, 'Buy'), (sf, su, spx, 'Sell')):
            out.append(','.join([fid, str(int(fid) + 7), '4327108', u.strftime('%Y-%m-%d %H:%M:%S.%f')[:23] + 'Z',
                                 et(u).strftime('%Y-%m-%d'), '0' if side == 'Buy' else '1', '1', '%.2f' % px,
                                 'true', '1676735', fid, str(int(fid) + 7), disp(u).strftime('%m/%d/%Y %H:%M:%S'),
                                 '%d/%d/%02d' % (disp(u).month, disp(u).day, disp(u).year % 100),
                                 'DEMO123', ' ' + side, '1', '%.2f' % px, '-2', '0', '0.25', sym + 'M6', sym,
                                 'Micro contract', '0.39']))
    return '\r\n'.join(out) + '\r\n'


def pdf_lines(rows):
    """The text lines of a NinjaTrader daily statement's fills section (times printed in GMT)."""
    lines = ['Daily Statement 04/07/2026']
    by_sym = {}
    for t in rows:
        by_sym.setdefault(t[0], []).append(t)
    names = {'MES': 'Micro E-mini S&P 500 - Jun. 2026 (MESM6)', 'MNQ': 'Micro E-mini Nasdaq-100 - Mar. 2026 (MNQH6)'}
    for sym, ts in by_sym.items():
        lines.append('Trading details for ' + names[sym])
        lines.append('Date & Time Code Buy Qty Sell Qty Filled Price Order_Id')
        for t in ts:
            bu, su, bpx, spx = _legs(t)
            for u, px, side in sorted(((bu, bpx, 'B'), (su, spx, 'S'))):
                stamp = u.strftime('%m/%d/%Y %I:%M:%S %p') + '(GMT)'
                qty = '1 -' if side == 'B' else '- 1'
                lines.append('%s FILL %s %s 1,%03d,%03d' % (stamp, qty, ('%.2f' % px).rstrip('0').rstrip('.'),
                                                            len(lines), len(lines) * 7 % 1000))
    return lines


def truth(rows):
    """{(date, entry price): (entry HH:MM, exit HH:MM, direction)} in New York time."""
    out = {}
    for sym, d, eu, xu, epx, xpx, bf, sf in rows:
        e, x = et(_utc(eu)), et(_utc(xu))
        out[(e.strftime('%Y-%m-%d'), round(epx, 2))] = (e.strftime('%H:%M'), x.strftime('%H:%M'), d)
    return out


def fill_utc(rows):
    fu = {}
    for t in rows:
        bu, su, _, _ = _legs(t)
        fu[t[6]] = int(bu.timestamp() * 1000)
        fu[t[7]] = int(su.timestamp() * 1000)
    return fu


def build_cases():
    all_rows = TRADES + SMALL
    small_t = truth(SMALL)
    # the existing journal trade for the drift case: the first TRADES row, saved 3 hours late
    e0, x0 = et(_utc(TRADES[0][2])), et(_utc(TRADES[0][3]))
    late = {'id': 'probe-late', 'date': e0.strftime('%Y-%m-%d'), 'symbol': 'MES', 'type': 'LONG',
            'entry': TRADES[0][4], 'exit': TRADES[0][5], 'size': 1,
            'entryTime': (e0 + timedelta(hours=3)).strftime('%H:%M'),
            'exitTime': (x0 + timedelta(hours=3)).strftime('%H:%M')}
    return [
        {'name': 'ph-pacific-auto', 'kind': 'csv', 'text': position_history(TRADES, pt), 'opts': {'tz': 'auto'},
         'expect': 'rows', 'truth': truth(TRADES), 'zone': 'America/Los_Angeles'},
        {'name': 'ph-eastern-auto', 'kind': 'csv', 'text': position_history(TRADES, et), 'opts': {'tz': 'auto'},
         'expect': 'rows', 'truth': truth(TRADES), 'zone': 'America/New_York'},
        {'name': 'perf-pacific-auto', 'kind': 'csv', 'text': performance(TRADES, pt), 'opts': {'tz': 'auto'},
         'expect': 'rows', 'truth': truth(TRADES), 'zone': 'America/Los_Angeles'},
        {'name': 'small-eastern+fills', 'kind': 'csv', 'text': position_history(SMALL, et),
         'opts': {'tz': 'auto', 'fillUTC': fill_utc(all_rows)}, 'expect': 'rows', 'truth': small_t,
         'zone': 'America/New_York', 'how': 'fills'},
        {'name': 'small-eastern-picked', 'kind': 'csv', 'text': position_history(SMALL, et),
         'opts': {'tz': 'America/New_York'}, 'expect': 'rows', 'truth': small_t, 'zone': 'America/New_York'},
        {'name': 'small-eastern-auto-held', 'kind': 'csv', 'text': position_history(SMALL, et),
         'opts': {'tz': 'auto'}, 'expect': 'ask'},
        {'name': 'pacific-picked-eastern-held', 'kind': 'csv', 'text': position_history(TRADES, pt),
         'opts': {'tz': 'America/New_York'}, 'expect': 'ask'},
        {'name': 'pdf-gmt', 'kind': 'pdf', 'lines': pdf_lines(TRADES), 'opts': {'tz': 'auto'},
         'expect': 'rows', 'truth': truth(TRADES)},
        {'name': 'drift-flagged', 'kind': 'csv', 'text': position_history(TRADES[:1], et), 'opts': {'tz': 'America/New_York'},
         'trades': [late], 'expect': 'drift'},
        {'name': 'fills-export', 'kind': 'csv', 'text': fills(all_rows, pt), 'opts': {'tz': 'auto'},
         'expect': 'fills', 'n': 2 * len(all_rows)},
    ]


PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>import tz probe</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html" style="width:1200px;height:800px;border:0"></iframe>
<pre id="o"></pre>
<script>
var CASES=__CASES__;
(function(){
  var out={cases:{}},done=false;
  function finish(why){if(done)return;done=true;out.why=why;
    document.getElementById('o').textContent='IMPORTTZPROBE: '+JSON.stringify(out);}
  function fakePdf(w,lines){
    // one text item per line, top to bottom, the shape importPDF reads from pdf.js
    var items=lines.map(function(s,i){return {str:s,transform:[1,0,0,1,40,800-i*14]};});
    w.pdfjsLib={getDocument:function(){return {promise:Promise.resolve({numPages:1,getPage:function(){
      return Promise.resolve({getTextContent:function(){return Promise.resolve({items:items});}});}})};}};
  }
  async function run(){
    var w=document.getElementById('f').contentWindow;
    out.VERSION=w.eval('typeof VERSION!=="undefined"?VERSION:null');
    out.hasImport=w.eval('typeof importCSV')==='function'&&w.eval('typeof importPDF')==='function';
    if(!out.hasImport){finish('noimport');return;}
    for(var i=0;i<CASES.length;i++){
      var c=CASES[i],r={};
      try{
        w.eval('trades='+JSON.stringify(c.trades||[])+';');
        var res;
        if(c.kind==='pdf'){fakePdf(w,c.lines);
          res=await w.importPDF(new w.File([new Uint8Array([37,80,68,70])],'probe.pdf',{type:'application/pdf'}),c.opts);}
        else res=w.importCSV(c.text,c.name+'.csv',c.opts);
        r.type=res.type;
        r.rows=(res.batch||[]).map(function(t){return {date:t.date,sym:t.symbol,dir:t.type,entry:t.entry,exit:t.exit,e:t.entryTime,x:t.exitTime};});
        r.ask=res.tzAsk?{why:res.tzAsk.why}:null;
        r.note=res.tzNote?{how:res.tzNote.how,tz:res.tzNote.tz}:null;
        r.drift=(res.tzDrift||[]).map(function(d){return {id:d.id,hours:d.hours};});
        r.merges=(res.merges||[]).map(function(m){return m.updates;});
        r.fills=res.fillUTC?Object.keys(res.fillUTC).length:null;
      }catch(e){r.err=String(e&&e.stack?e.stack:e);}
      out.cases[c.name]=r;
    }
    try{w.eval('trades=[];');}catch(_){}
    finish('done');
  }
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){run().catch(function(e){out.err=String(e);finish('threw');});},2500);});
  setTimeout(function(){finish('backstop');},14000);
})();
</script>
</body></html>
"""


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


def make_handler(root, alt_index):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root, **kw)

        def do_GET(self):
            if alt_index and (self.path == '/index.html' or self.path.startswith('/index.html?')):
                try:
                    with open(alt_index, 'rb') as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except OSError as e:
                    self.send_error(500, str(e))
                return
            super().do_GET()

        def log_message(self, *a):
            pass
    return H


def judge(cases, data):
    fails = []
    got = data.get('cases') or {}
    for c in cases:
        nm, r = c['name'], got.get(c['name'])
        if r is None:
            fails.append('%s: no result' % nm)
            continue
        if r.get('err'):
            fails.append('%s: threw -- %s' % (nm, r['err'].splitlines()[0][:240]))
            continue
        exp = c['expect']
        if exp == 'ask':
            if not r.get('ask') or r.get('rows'):
                fails.append('%s: expected the file to be HELD with a time-zone question, got %d trade(s) '
                             'saved%s' % (nm, len(r.get('rows') or []), (' at ' + ', '.join(
                                 '%s %s-%s' % (x['date'], x['e'], x['x']) for x in r['rows'][:3])) if r.get('rows') else ''))
            continue
        if exp == 'drift':
            ds = r.get('drift') or []
            if not any(d.get('id') == 'probe-late' and d.get('hours') == 3 for d in ds):
                fails.append('%s: a trade saved 3 hours late was not flagged (drift=%s)' % (nm, ds))
            touched = [m for m in (r.get('merges') or []) if 'entryTime' in m or 'exitTime' in m]
            if touched:
                fails.append('%s: the import REWROTE saved times %s -- it may only flag them' % (nm, touched))
            continue
        if exp == 'fills':
            if r.get('fills') != c['n']:
                fails.append('%s: expected %d absolute fill times read, got %s' % (nm, c['n'], r.get('fills')))
            continue
        # rows: every expected trade present with New York entry / exit
        rows = r.get('rows') or []
        if r.get('ask'):
            fails.append('%s: held with a time-zone question (%s) -- expected it to import' % (nm, r['ask'].get('why')))
            continue
        if len(rows) != len(c['truth']):
            fails.append('%s: %d trade(s) saved, expected %d' % (nm, len(rows), len(c['truth'])))
        for x in rows:
            key = (x['date'], round(float(x['entry']), 2))
            want = c['truth'].get(key)
            if not want:
                fails.append('%s: unexpected trade %s entry %s (date or entry price wrong)' % (nm, x['date'], x['entry']))
                continue
            if (x['e'], x['x'], x['dir']) != want:
                fails.append('%s: %s %s %s saved %s-%s, true New York time is %s-%s'
                             % (nm, x['date'], x['sym'], x['dir'], x['e'], x['x'], want[0], want[1]))
        note = r.get('note') or {}
        if c.get('zone') and note.get('tz') and note.get('tz') != c['zone']:
            fails.append('%s: read as %s, expected %s' % (nm, note.get('tz'), c['zone']))
        if c.get('how') and note.get('how') != c['how']:
            fails.append('%s: zone decided by %s, expected %s' % (nm, note.get('how'), c['how']))
    return fails


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--file', default=None, help='gate this file as if it were index.html')
    ap.add_argument('--selftest', action='store_true',
                    help='assert FAIL on the last pre-fix build from git history, then PASS on index.html')
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    t0 = time.time()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alt_index = os.path.abspath(args.file) if args.file else None
    if alt_index and not os.path.isfile(alt_index):
        print('IMPORTTZPROBE: INCONCLUSIVE -- --file not found: %s' % alt_index)
        return INCONCLUSIVE
    chrome = find_chrome()
    if not chrome:
        print('IMPORTTZPROBE: INCONCLUSIVE -- Chrome not found')
        return INCONCLUSIVE
    cases = build_cases()
    js_cases = [{k: v for k, v in c.items() if k not in ('truth',)} for c in cases]

    pdir = tempfile.mkdtemp(prefix='_importtzprobe-', dir=root)
    sub = os.path.basename(pdir)
    io.open(os.path.join(pdir, 'probe.html'), 'w', encoding='utf-8').write(
        PROBE_HTML.replace('__CASES__', json.dumps(js_cases)))
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(root, alt_index))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    prof = tempfile.mkdtemp(prefix='importtzprobe-')
    try:
        out = subprocess.run(
            [chrome, '--headless=new', '--disable-gpu', '--no-sandbox', '--user-data-dir=' + prof,
             '--virtual-time-budget=15000', '--dump-dom',
             'http://127.0.0.1:%d/%s/probe.html' % (srv.server_address[1], sub)],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120).stdout
    except Exception as e:
        print('IMPORTTZPROBE: INCONCLUSIVE -- chrome failed: %s' % e)
        return INCONCLUSIVE
    finally:
        srv.shutdown()
        shutil.rmtree(pdir, ignore_errors=True)
        shutil.rmtree(prof, ignore_errors=True)

    m = re.search(r'IMPORTTZPROBE: (\{.*?\})</pre>', out, re.S)
    if not m:
        print('IMPORTTZPROBE: INCONCLUSIVE -- probe produced no readout')
        return INCONCLUSIVE
    try:
        data = json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&')
                          .replace('&lt;', '<').replace('&gt;', '>'))
    except Exception as e:
        print('IMPORTTZPROBE: INCONCLUSIVE -- unreadable readout: %s' % e)
        return INCONCLUSIVE
    if data.get('why') == 'noimport':
        print('IMPORTTZPROBE: INCONCLUSIVE -- importCSV / importPDF not defined (VERSION=%s); '
              'see preflight_boot' % data.get('VERSION'))
        return INCONCLUSIVE
    if data.get('why') != 'done':
        print('IMPORTTZPROBE: INCONCLUSIVE -- probe did not finish (%s)%s'
              % (data.get('why'), (' -- ' + data['err']) if data.get('err') else ''))
        return INCONCLUSIVE
    fails = judge(cases, data)
    if fails:
        print('IMPORTTZPROBE: FAIL (VERSION=%s, %.1fs)' % (data.get('VERSION'), time.time() - t0))
        for f in fails:
            print('  - ' + f)
        return FAIL
    print('IMPORTTZPROBE: PASS (VERSION=%s, %d cases, %.1fs)' % (data.get('VERSION'), len(cases), time.time() - t0))
    return PASS


def selftest():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmpdir = tempfile.mkdtemp(prefix='importtzprobe-selftest-')
    bad = []
    try:
        for commit, ver, why in KNOWN_BAD:
            path = os.path.join(tmpdir, 'index_%s.html' % ver.replace('.', '_'))
            r = subprocess.run(['git', '-C', root, 'show', commit + ':index.html'], capture_output=True, timeout=60)
            if r.returncode != 0 or len(r.stdout) < 100000:
                print('SELFTEST: INCONCLUSIVE -- could not read %s:index.html from history' % commit)
                return INCONCLUSIVE
            with open(path, 'wb') as f:
                f.write(r.stdout)
            print('-- known-bad build v%s (%s): expect FAIL' % (ver, commit))
            code = main(['--file', path])
            if code != FAIL:
                bad.append('v%s (%s) was NOT caught (exit %d) -- the gate has gone blind to: %s' % (ver, commit, code, why))
        print('-- current index.html: expect PASS')
        code = main([])
        if code != PASS:
            bad.append('current index.html did not PASS (exit %d)' % code)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    if bad:
        print('SELFTEST: FAIL')
        for b in bad:
            print('  - ' + b)
        return FAIL
    print('SELFTEST: PASS -- gate caught %d known-bad build(s) and passed the current one' % len(KNOWN_BAD))
    return PASS


if __name__ == '__main__':
    sys.exit(main())
