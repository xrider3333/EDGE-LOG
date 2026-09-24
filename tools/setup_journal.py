# setup_journal.py — the per-setup trade journals under setups/ (CBU.md, ENGU.md, EBU.md, CBD.md,
# ENGD.md + README.md), built from the owner's REAL discretionary futures trades in EDGE LOG.
#
# Each journal lists every real trade the owner tagged with that setup: the chart link(s) he
# saved, the fill, and the OHLC of the bars that matter (the signal candle, the entry bar, every
# bar held, the exit bar, and a short run of context either side), plus the geometry the setup
# is judged by (stop beyond the signal candle, chase, R, MAE, MFE). The point is a growing,
# reproducible dataset per setup - the same role tools/data/trade_scores.json plays for scores.
#
#   python tools/setup_journal.py prep      pull trades (read-only) + sheet links + bars -> cache
#   python tools/setup_journal.py render    tools/data/setup_journal.json + cache -> setups/*.md
#   python tools/setup_journal.py check     exit 1 if setups/*.md is stale vs the spec
#
# SOURCES, in order of trust:
#   labels / links / notes : EDGE LOG trades (Firestore, read-only) - the owner edits there.
#                            TRADETRACKER 2026 sheet only fills a label or link EL leaves blank,
#                            and every such fill is marked "sheet" in the journal.
#   resolved times, signal candle, stop : tools/data/trade_scores.json (the SCORE routine already
#                            anchored every futures trade to Eastern time) unless the spec below
#                            overrides it after a snapshot check.
#   bars : 1m  = augur_uploads NOADJ_{ES,NQ}_1m_ETH.csv (unadjusted, any age; gap Jul 1 - Aug 5)
#          10s = augur_uploads NT 10s masters (NinjaTrader capture, 2026-06-23 onward), also
#                resampled to 1m to fill the gap above. The capture is stored with bar-END
#                stamps (the repo convention), so they are shifted back 10 seconds on load.
#   fill seconds : C:/EdgeLog/fills.csv (the NinjaTrader AddOn fill log) places each entry and
#                exit on its exact 10-second bar when the fill is still in that rolling file.
#   MES trades read ES bars and MNQ trades read NQ bars - same price, same contract month
#   (px_offset in trade_scores.json covers the one trade on a different month).
#
# The judgement for each trade (which candle is the signal, the stop, what the snapshot shows)
# lives in tools/data/setup_journal.json. This file only fetches, measures and renders.
import os
import io
import re
import sys
import json
import argparse
import urllib.request

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'tools', 'data')
SPEC = os.path.join(DATA, 'setup_journal.json')
SCORES = os.path.join(DATA, 'trade_scores.json')
BARS_DIR = os.path.join(DATA, 'setup_bars')        # versioned trimmed windows (permanent record)
OUT_DIR = os.path.join(ROOT, 'setups')
UPLOADS = os.path.join(ROOT, 'augur_uploads')
if not os.path.isdir(UPLOADS):                     # worktrees have no augur_uploads
    UPLOADS = os.path.join(os.path.expanduser('~'), 'OneDrive', 'Desktop', 'EDGE-LOG', 'augur_uploads')
CRED = os.path.join(ROOT, 'serviceAccount.json')
if not os.path.exists(CRED):
    CRED = os.path.join(os.path.expanduser('~'), 'OneDrive', 'Desktop', 'EDGE-LOG', 'serviceAccount.json')
UID = 'IO0K35JpLIcH9YK4C0pMNYUzZOM2'
SHEET = '1BI0ajajIn1Oc0p7iDsp6Wc3g-zaqVuE5qSz1sw8TFto'
ET = 'America/New_York'

MASTER_1M = {'ES': 'NOADJ_ES_1m_ETH.csv', 'NQ': 'NOADJ_NQ_1m_ETH.csv'}
MASTER_10S = {'ES': 'master_c279374a.csv', 'NQ': 'master_b1335b7e.csv'}
TEN_SEC_FROM = '2026-06-23'
ROOT_OF = {'MES': 'ES', 'ES': 'ES', 'MNQ': 'NQ', 'NQ': 'NQ'}
POINT_VALUE = {'MES': 5.0, 'ES': 50.0, 'MNQ': 2.0, 'NQ': 20.0}
SETUPS = ['CBU', 'ENGU', 'EBU', 'CBD', 'ENGD']

# context kept either side of the trade, in bars of each resolution
PRE_1M, POST_1M = 15, 15
PRE_10S, POST_10S = 18, 30


# ------------------------------------------------------------------ sources

def snap_png(url):
    m = re.search(r'tradingview\.com/x/([A-Za-z0-9]+)', url or '')
    if not m:
        return None
    i = m.group(1)
    return 'https://s3.tradingview.com/snapshots/%s/%s.png' % (i[0].lower(), i)


def load_el_trades():
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(CRED))
    col = firestore.client().collection('users').document(UID).collection('trades')
    rows = []
    for d in col.stream():
        t = d.to_dict() or {}
        if t.get('assetType') != 'futures':
            continue
        t['_id'] = d.id
        rows.append({k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in t.items()})
    rows.sort(key=lambda t: (str(t.get('date')), str(t.get('entryTime')), t['_id']))
    return rows


def load_sheet_rows():
    """Futures 2026 tab: # DATE SY TF DIR UN PV ENTRY EXIT FEE PTS PNL BAL SETUP CHART NOTES."""
    import urllib.parse
    from google.oauth2 import service_account
    import google.auth.transport.requests as gr
    cr = service_account.Credentials.from_service_account_file(
        CRED, scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
    s = gr.AuthorizedSession(cr)
    rng = urllib.parse.quote("'Futures 2026'!A1:P200")
    vals = s.get('https://sheets.googleapis.com/v4/spreadsheets/%s/values/%s?valueRenderOption=FORMULA'
                 % (SHEET, rng)).json().get('values', [])
    out, on = [], False
    for row in vals:
        if row and str(row[0]).strip() == '#':
            on = True
            continue
        # the # column is sometimes a number and sometimes a COUNTA formula: key on DATE + SY
        if not on or len(row) < 9 or not isinstance(row[1], (int, float)) or not str(row[2]).strip():
            continue
        row = row + [''] * (16 - len(row))
        url = ''
        m = re.search(r'https?://[^"\s]+', str(row[14]))
        if m:
            url = m.group(0)
        d = row[1]
        if isinstance(d, (int, float)):            # sheet serial date
            d = (pd.Timestamp('1899-12-30') + pd.Timedelta(days=int(d))).strftime('%Y-%m-%d')
        out.append({'n': len(out) + 1, 'date': str(d), 'sym': str(row[2]), 'tf': str(row[3]),
                    'dir': str(row[4]), 'entry': row[7], 'exit': row[8], 'setup': str(row[13]).strip(),
                    'chart': url, 'notes': str(row[15]).strip()})
    return out


def match_sheet(t, sheet):
    for r in sheet:
        try:
            if (r['date'] == t['date'] and r['sym'] == t['symbol'] and r['dir'] == t['type']
                    and abs(float(r['entry']) - float(t['entry'])) < 1e-6
                    and abs(float(r['exit']) - float(t['exit'])) < 1e-6):
                return r
        except (TypeError, ValueError):
            continue
    return None


def load_scores():
    d = json.load(io.open(SCORES, encoding='utf-8'))
    by = {}
    for s in d['trades']:
        if s['sym'] in ROOT_OF:
            by.setdefault((s['date'], s['sym']), []).append(s)
    return by


def score_for(t, by):
    c = by.get((t['date'], t['symbol']), [])
    for s in c:
        if s.get('trade_id') == t['_id']:
            return s
    c = [s for s in c if not s.get('trade_id')]
    for s in c:
        if abs(float(s['entry']) - float(t['entry'])) < 1e-6 and abs(float(s['exit']) - float(t['exit'])) < 1e-6:
            return s
    return None


_cache = {}


def day_bars(root, date, res):
    """All bars of one ET calendar day, index = ET timestamps."""
    key = (root, date, res)
    if key in _cache:
        return _cache[key]
    path = os.path.join(UPLOADS, (MASTER_1M if res == '1m' else MASTER_10S)[root])
    d0 = pd.Timestamp(date, tz=ET)
    lo, hi = int((d0 - pd.Timedelta(hours=2)).timestamp()), int((d0 + pd.Timedelta(hours=26)).timestamp())
    parts = []
    for ch in pd.read_csv(path, usecols=['time', 'open', 'high', 'low', 'close', 'volume'], chunksize=500000):
        ch = ch[(ch.time >= lo) & (ch.time < hi)]
        if len(ch):
            parts.append(ch)
    if not parts:
        _cache[key] = None
        return None
    b = pd.concat(parts).drop_duplicates('time').sort_values('time')
    # The NinjaTrader 10s capture is kept raw with bar-END stamps (NinjaScript Time[0]) by design:
    # tools/import_nt_ohlc.py restamps only minute-or-larger series, and readers shift the 10s rows
    # themselves (api/paper.py::_resample, stamp="end"). Every other master is stamped at the bar
    # OPEN, so shift back one bar here (checked 2026-09-24: resampled 10s then matches the 1m
    # masters on 96-100% of RTH minutes, against 6-21% unshifted).
    t = b.time - (10 if res == '10s' else 0)
    b.index = pd.to_datetime(t, unit='s', utc=True).dt.tz_convert(ET)
    b = b[b.index.strftime('%Y-%m-%d') == date][['open', 'high', 'low', 'close', 'volume']]
    _cache[key] = b if len(b) else None
    return _cache[key]


def bars_1m(root, date):
    b = day_bars(root, date, '1m')
    if b is not None and len(b) > 300:
        return b, 'NOADJ 1m'
    if date >= TEN_SEC_FROM:
        t = day_bars(root, date, '10s')
        if t is not None:
            r = t.resample('1min', label='left', closed='left').agg(
                {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
            return r, 'NT 10s resampled to 1m'
    return b, 'NOADJ 1m'


# ------------------------------------------------------------------ prep

def prep(a):
    os.makedirs(a.cache, exist_ok=True)
    snaps = os.path.join(a.cache, 'snaps')
    os.makedirs(snaps, exist_ok=True)
    el = load_el_trades()
    sheet = load_sheet_rows()
    by = load_scores()
    out = []
    for i, t in enumerate(el, 1):
        sr = match_sheet(t, sheet)
        sc = score_for(t, by)
        el_setup = (t.get('setup') or '').strip()
        el_setup = '' if el_setup in ('—', '-') else el_setup
        rec = {
            'n': i, 'trade_id': t['_id'], 'date': t['date'], 'sym': t['symbol'], 'dir': t['type'],
            'entry': float(t['entry']), 'exit': float(t['exit']), 'qty': t.get('size'),
            'pnl': t.get('pnl'), 'fees': t.get('fees'),
            'el_entry_time': t.get('entryTime'), 'el_exit_time': t.get('exitTime'),
            'dur_secs': t.get('durationSecs'), 'dur_mins': t.get('durationMins'),
            'el_setup': el_setup, 'el_grade': t.get('grade'), 'el_tf': t.get('timeframe'),
            'el_notes': t.get('notes') or '', 'el_link': t.get('chartUrl') or '', 'el_tags': t.get('tags'),
            'source': t.get('source'),
            'sheet': sr,
            'score': ({k: sc.get(k) for k in ('entry_time', 'exit_time', 'hold_from', 'breakout_candle',
                                             'stop', 'px_offset', 'overall', 'summary')} if sc else None),
        }
        links = []
        for u in (rec['el_link'], (sr or {}).get('chart', '')):
            if u and u not in links:
                links.append(u)
        rec['links'] = links
        rec['snap_files'] = []
        for u in links:
            png = snap_png(u)
            if not png:
                continue
            fp = os.path.join(snaps, png.rsplit('/', 1)[1])
            if not os.path.exists(fp):
                try:
                    req = urllib.request.Request(png, headers={'User-Agent': 'Mozilla/5.0'})
                    io.open(fp, 'wb').write(urllib.request.urlopen(req, timeout=30).read())
                except Exception as e:                 # a dead link is itself a finding
                    print('snapshot fetch failed', u, e)
                    continue
            rec['snap_files'].append(fp)
        root = ROOT_OF[t['symbol']]
        b1, src1 = bars_1m(root, t['date'])
        if b1 is not None:
            fp = os.path.join(a.cache, 'bars', '%s_%s_1m.csv' % (root, t['date']))
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            if not os.path.exists(fp):
                b1.to_csv(fp)
            rec['bars_1m'] = fp
        rec['bars_1m_source'] = src1
        if t['date'] >= TEN_SEC_FROM:
            b10 = day_bars(root, t['date'], '10s')
            if b10 is not None:
                fp = os.path.join(a.cache, 'bars', '%s_%s_10s.csv' % (root, t['date']))
                if not os.path.exists(fp):
                    b10.to_csv(fp)
                rec['bars_10s'] = fp
        out.append(rec)
        print('%2d %s %s %-5s %-4s el=%-4s sheet=%-4s links=%d snaps=%d 1m=%s 10s=%s score=%s' % (
            i, t['date'], t['symbol'], t['type'], '', el_setup or '-', (sr or {}).get('setup') or '-',
            len(links), len(rec['snap_files']), 'y' if rec.get('bars_1m') else 'n',
            'y' if rec.get('bars_10s') else 'n', 'y' if sc else 'NA'))
    json.dump(out, io.open(os.path.join(a.cache, 'prep.json'), 'w', encoding='utf-8'), indent=1, default=str)
    print('\n%d futures trades -> %s' % (len(out), os.path.join(a.cache, 'prep.json')))


# ------------------------------------------------------------------ geometry + render

def _t(date, hhmm, sec=False):
    return pd.Timestamp('%s %s' % (date, hhmm), tz=ET)


def window(b, t0, t1, pre, post, step):
    lo = t0 - pd.Timedelta(seconds=pre * step)
    hi = t1 + pd.Timedelta(seconds=post * step)
    return b[(b.index >= lo) & (b.index <= hi)]


def hold_bars(j, b1, b10):
    """Bars that are certainly AFTER the fill and not after the exit.

    With 10-second bars the hold is exact (entry 10s bar -> exit 10s bar). With 1-minute bars
    alone, the entry minute also holds price action from BEFORE the fill whenever the fill came
    inside it, so it is skipped; a trade in and out inside one minute then has no measurable heat.
    Returns (bars, how) where how says which it was."""
    d = j['date']
    if b10 is not None and j.get('entry_ts') and j.get('exit_ts'):
        t0 = pd.Timestamp('%s %s' % (d, j['entry_ts']), tz=ET)
        t1 = pd.Timestamp('%s %s' % (d, j['exit_ts']), tz=ET)
        h = b10[(b10.index >= t0) & (b10.index <= t1)]
        if len(h):
            return h, '10s'
    step = pd.Timedelta(minutes=int(re.sub(r'[^0-9]', '', j.get('interval', '1m')) or 1))
    start = _t(d, j['hold_from']) if j.get('hold_from') else _t(d, j['entry_time']).floor(step) + step
    end = _t(d, j['exit_time']).floor(step)          # the exit bar also holds prices after the exit
    h = b1[(b1.index >= start) & (b1.index < end)]
    return h, j.get('interval', '1m')


def sig_bars(j, b1):
    """The bars the signal is measured on: the data's own, or combined up to signal_iv (5m)."""
    siv = j.get('signal_iv')
    if not siv or siv == j.get('interval', '1m'):
        return b1
    return b1.resample(siv.replace('m', 'min'), label='left', closed='left').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()


def geometry(j, b1, b10=None):
    """Everything measured, never judged. j = one resolved spec entry."""
    E, X, stop = j['entry'], j['exit'], j.get('stop')
    long_ = j['dir'] == 'LONG'
    sgn = 1 if long_ else -1
    off = j.get('px_offset') or 0.0                 # bars are on another contract month
    bs = sig_bars(j, b1)
    sig = bs.loc[bs.index == _t(j['date'], j['signal_candle'])]
    g = {}
    px = j.get('signal_px')                          # candle read off the snapshot (no bar exists)
    if len(sig) or px:
        if px:
            so, sh, sl, sc = px['o'], px['h'], px['l'], px['c']
        else:
            s = sig.iloc[0]
            so, sh, sl, sc = s.open + off, s.high + off, s.low + off, s.close + off
        rng = sh - sl
        g.update(sig_o=so, sig_h=sh, sig_l=sl, sig_c=sc, sig_range=round(rng, 4),
                 sig_body_pct=round(abs(sc - so) / rng * 100) if rng else None)
        if len(sig) and not px:
            prior = bs[bs.index < sig.index[0]].tail(10)
            if len(prior):
                med_body = (prior.close - prior.open).abs().median()
                g['body_x'] = round(abs(sc - so) / med_body, 1) if med_body else None
                mv = prior.volume.mean()
                g['vol_x'] = round(s.volume / mv, 1) if mv else None
        # chase: how far past the signal close the fill sat, as a share of the signal range. When the
        # signal bar is the same bar the fill came in, its close came AFTER the fill: no chase.
        iv_min = int(re.sub(r'[^0-9]', '', j.get('signal_iv') or j.get('interval', '1m')) or 1)
        same = (not px) and _t(j['date'], j['signal_candle']) == _t(j['date'], j['entry_time']).floor('%dmin' % iv_min)
        g['same_bar'] = same
        g['chase_pct'] = None if same else (round(sgn * (E - sc) / rng * 100, 1) if rng else None)
    if stop is not None:
        risk = sgn * (E - stop)
        g['risk'] = round(risk, 4)
        g['R'] = round(sgn * (X - E) / risk, 2) if risk > 0 else None
    t_out = _t(j['date'], j['exit_time'])
    hold, how = hold_bars(j, b1, b10)
    g['hold_res'] = how if len(hold) else None
    res = sgn * (X - E)
    if len(hold):
        hi, lo = hold.high.max() + off, hold.low.min() + off
        # the exit price itself traded while held, so best / worst can never sit inside it
        hi, lo = max(hi, X), min(lo, X)
        mae = (E - lo) if long_ else (hi - E)
        mfe = (hi - E) if long_ else (E - lo)
        g['mae_pts'] = round(max(mae, 0.0), 2)
        g['mfe_pts'] = round(max(mfe, 0.0), 2)
        if stop is not None and g.get('risk'):
            g['mae_of_risk'] = round(max(mae, 0.0) / g['risk'] * 100)
        g['capture'] = round(res / mfe * 100) if (mfe > 0 and res >= 0) else None
    after = b1[(b1.index > t_out) & (b1.index <= t_out + pd.Timedelta(minutes=15))]
    if len(after):
        best = (after.high.max() + off - E) if long_ else (E - after.low.min() - off)
        g['next15_best_pts'] = round(best, 2)
        worst = (E - after.low.min() - off) if long_ else (after.high.max() + off - E)
        g['next15_worst_pts'] = round(worst, 2)
        if stop is not None:
            hit = after[(after.low + off <= stop)] if long_ else after[(after.high + off >= stop)]
            g['stop_hit_next15'] = hit.index[0].strftime('%H:%M') if len(hit) else None
    return g


def px_str(x):
    """A traded price with every decimal it really has (29189.75, 7678.625, 1.1486)."""
    for nd in (2, 3, 4):
        if abs(round(x, nd) - x) < 1e-9:
            return '%.*f' % (nd, x)
    return '%.4f' % x


def fmt(x, nd=2):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return '—'
    if isinstance(x, float):
        out = ('%.' + str(nd) + 'f') % x
        return out[1:] if out.startswith('-') and float(out) == 0 else out
    return str(x)


SOURCE_NAME = {'NOADJ 1m': '1-minute CME bars, unadjusted',
               'NT 10s resampled to 1m': 'NinjaTrader 10-second bars combined into 1-minute bars',
               'Yahoo 1m (score cache)': 'Yahoo 1-minute bars', 'Yahoo 5m (score cache)': 'Yahoo 5-minute bars'}
TAG_NAME = {'CHoS': 'CHoS (change of structure)'}


def pxf(x):
    return '—' if x is None or (isinstance(x, float) and pd.isna(x)) else px_str(round(float(x), 6))


def ohlc_table(w, marks, off, step_label):
    rows = ['| %s ET | O | H | L | C | Vol | |' % step_label, '|---|---|---|---|---|---|---|']
    for ts, r in w.iterrows():
        k = ts.strftime('%H:%M:%S') if step_label == '10s' else ts.strftime('%H:%M')
        tag = ' · '.join(m for t, m in marks if t == ts)
        rows.append('| %s | %s | %s | %s | %s | %d | %s |' % (
            k, pxf(r.open + off), pxf(r.high + off), pxf(r.low + off), pxf(r.close + off),
            int(r.volume), tag))
    return '\n'.join(rows)


def load_bars(rel):
    b = pd.read_csv(os.path.join(DATA, rel), index_col=0)
    b.index = pd.to_datetime(b.index, utc=True).tz_convert(ET)
    b.columns = [c.lower() for c in b.columns]
    return b[['open', 'high', 'low', 'close', 'volume']]


def trade_block(j, cache):
    b1 = load_bars(j['bars_file'])
    b10 = load_bars(j['bars_10s_file']) if j.get('bars_10s_file') else None
    iv = j.get('interval', '1m')
    step = 60 * int(re.sub(r'\D', '', iv) or 1)
    off = j.get('px_offset') or 0.0
    g = geometry(j, b1, b10)
    d = j['date']
    t_sig, t_in, t_out = _t(d, j['signal_candle']), _t(d, j['entry_time']), _t(d, j['exit_time'])
    fut = j.get('asset', 'futures') == 'futures'
    L = []
    title = '%s · %s %s %s · %s' % (d, j['sym'], j['dir'], '%s→%s' % (px_str(j['entry']), px_str(j['exit'])),
                                   ('%+.2f' % j['pnl']) if j.get('pnl') is not None else '')
    L.append('#### %s' % title)
    L.append('')
    facts = [
        ('EL trade', '%sTRADING LOG ▸ TRADES, %s %s (id …%s)' % (
            ('#%s in ' % j['n']) if fut else '', d, j['sym'], j['trade_id'][-6:])),
        ('Label', j['label'] + (' (from the TRADETRACKER sheet — EL has none)' if j.get('label_source') == 'sheet' else '')),
        ('Grade · TF', '%s · %s' % (j.get('grade') or '—', j.get('tf') or '—')),
        ('Times (ET)', 'signal %s · in %s%s · out %s%s%s' % (
            j['signal_candle'], j['entry_time'], (' (10-second bar %s)' % j['entry_ts']) if j.get('entry_ts') else '',
            j['exit_time'], (' (10-second bar %s)' % j['exit_ts']) if j.get('exit_ts') else '',
            (' — journal said %s' % j['el_times']) if j.get('el_times') else '')),
        ('Size', ('%s × %s ($%g/pt)' % (j.get('qty'), j['sym'], POINT_VALUE[j['sym']])) if fut
                 else '%s shares' % j.get('qty')),
        ('Notes', j.get('notes') or '—'),
    ]
    if j.get('tags'):
        facts.append(('Tags', ', '.join(TAG_NAME.get(t, t) for t in j['tags'])))
    if j.get('fill_seconds'):
        facts.append(('Fill seconds', j['fill_seconds']))
    for u in j.get('links', []):
        facts.append(('Chart', '[%s](%s) · [png](%s)' % (u.rstrip('/').rsplit('/', 1)[-1], u, snap_png(u))))
    if j.get('link_note'):
        facts.append(('Chart', j['link_note']))
    if j.get('signal_iv') and j['signal_iv'] != iv:
        facts.append(('Signal candle', 'the %s-minute candle he traded, %s-%s, built from the 1-minute bars' % (
            re.sub(r'\D', '', j['signal_iv']), j['signal_candle'],
            (t_sig + pd.Timedelta(minutes=int(re.sub(r'\D', '', j['signal_iv'])) - 1)).strftime('%H:%M'))))
    if j.get('signal_px', {}).get('text'):
        facts.append(('Signal candle', j['signal_px']['text']))
    elif j.get('signal_px'):
        facts.append(('Signal candle', 'read off the %s chart in the snapshot (%s); the free data for this day only has %s bars' % (
            j['signal_px'].get('tf', '1-minute'), j['signal_px'].get('how', 'pixel read'),
            {'1m': '1-minute', '5m': '5-minute'}.get(iv, iv))))
    if j.get('snapshot_created'):
        facts.append(('Snapshot taken', j['snapshot_created'] + ' ET'))
    if j.get('snapshot_read'):
        facts.append(('Snapshot shows', j['snapshot_read']))
    drawn = j.get('drawn') or {}
    if any(drawn.get(k) is not None for k in ('entry', 'stop', 'target')):
        facts.append(('Drawn on the chart', 'entry %s · stop %s · target %s' % (
            pxf(drawn.get('entry')), pxf(drawn.get('stop')), pxf(drawn.get('target')))))
    if j.get('signal_note'):
        facts.append(('Signal note', j['signal_note']))
    if g.get('same_bar'):
        facts.append(('Signal = fill bar', "the fill came inside the signal %s, so that bar's close, high and low include prices "
                      "after the fill; chase is not measured and the stop is the whole bar's %s" % (
                          {'1m': 'minute', '5m': '5-minute bar'}.get(iv, 'bar'), 'low' if j['dir'] == 'LONG' else 'high')))
    for k, lab in (('entry', 'entry'), ('exit', 'exit')):
        tt = t_in if k == 'entry' else t_out
        bar = b1.loc[b1.index == tt.floor('%dmin' % (step // 60))]
        if fut and len(bar):
            lo, hi, pxv = bar.low.iloc[0] + off, bar.high.iloc[0] + off, j[k]
            if not (lo - 1e-9 <= pxv <= hi + 1e-9) and min(abs(pxv - lo), abs(pxv - hi)) <= 0.5:
                facts.append(('Data note', 'the %s price %s is one tick outside the %s bar (%s-%s): a %s print the full-size contract did not trade' % (
                    lab, px_str(pxv), 'ES' if ROOT_OF[j['sym']] == 'ES' else 'NQ', px_str(lo), px_str(hi), j['sym'])))
    if j.get('caveat'):
        facts.append(('Caveat', j['caveat']))
    if j.get('check'):
        facts.append(('Checked', j['check'][:1].upper() + j['check'][1:]))
    for k, v in facts:
        L.append('- **%s:** %s' % (k, v))
    L.append('')
    L.append('| Signal O/H/L/C | Range | Body % | Body × prior-10 | Vol × prior-10 | Stop | Risk pts | Chase % | R | MAE % of risk | MFE pts | Capture % | Best next 15m |')
    L.append('|---|---|---|---|---|---|---|---|---|---|---|---|---|')
    L.append('| %s / %s / %s / %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
        pxf(g.get('sig_o')), pxf(g.get('sig_h')), pxf(g.get('sig_l')), pxf(g.get('sig_c')),
        pxf(g.get('sig_range')), fmt(g.get('sig_body_pct')), fmt(g.get('body_x'), 1), fmt(g.get('vol_x'), 1),
        pxf(j.get('stop')), pxf(g.get('risk')), 'same bar' if g.get('same_bar') else fmt(g.get('chase_pct'), 1), fmt(g.get('R')),
        fmt(g.get('mae_of_risk')), fmt(g.get('mfe_pts')), fmt(g.get('capture')), fmt(g.get('next15_best_pts'))))
    L.append('')
    fl = lambda t: t.floor('%dmin' % (step // 60))
    siv = j.get('signal_iv')
    if siv and siv != iv:
        n_min = int(re.sub(r'\D', '', siv))
        s_lab = 'SIGNAL (%s-minute candle %s-%s)' % (n_min, j['signal_candle'],
                                                     (t_sig + pd.Timedelta(minutes=n_min - 1)).strftime('%H:%M'))
    elif 'second' in (j.get('signal_px') or {}).get('tf', ''):
        s_lab = 'SIGNAL (a %s candle inside this bar)' % j['signal_px']['tf']
    else:
        s_lab = 'SIGNAL' if fl(t_sig) == t_sig else 'SIGNAL inside (%s 1m)' % j['signal_candle']
    marks = [(fl(t_sig), s_lab),
             (fl(t_in), 'IN %s' % px_str(j['entry']))]
    fills = j.get('exit_fills') or []
    if fills:
        marks += [(fl(pd.Timestamp('%s %s' % (d, f['ts']), tz=ET).floor('1min')), 'OUT %s' % px_str(f['px'])) for f in fills]
    else:
        marks.append((fl(t_out), 'OUT %s' % px_str(j['exit'])))
    pre, post = (PRE_1M, POST_1M) if step == 60 else (8, 8)
    w = window(b1, t_sig, t_out, pre, post, step)
    L.append('<details><summary>%s OHLC (%s)%s</summary>\n' % (
        {'1m': '1-minute', '5m': '5-minute'}.get(iv, iv), SOURCE_NAME.get(j.get('bars_source', ''), j.get('bars_source', '')),
        ' · prices shifted %+g to the traded contract' % off if off else ''))
    L.append(ohlc_table(w, marks, off, iv))
    L.append('\n</details>')
    if b10 is not None:
        w10 = window(b10, t_sig, t_out + pd.Timedelta(seconds=50), PRE_10S, POST_10S, 10)
        m10 = []
        e_ts = pd.Timestamp('%s %s' % (d, j['entry_ts']), tz=ET) if j.get('entry_ts') else None
        x_ts = pd.Timestamp('%s %s' % (d, j['exit_ts']), tz=ET) if j.get('exit_ts') else None
        for ts in w10.index:
            if ts == t_sig:
                m10.append((ts, 'SIGNAL %s candle starts' % ('5-minute' if j.get('signal_iv') == '5m' else 'minute')))
            if e_ts is not None and ts == e_ts:
                m10.append((ts, 'IN %s' % px_str(j['entry'])))
            if fills:
                m10 += [(ts, 'OUT %s' % px_str(f['px'])) for f in fills
                        if ts == pd.Timestamp('%s %s' % (d, f['ts']), tz=ET)]
            elif x_ts is not None and ts == x_ts:
                m10.append((ts, 'OUT %s' % px_str(j['exit'])))
        L.append('\n<details><summary>10-second OHLC (NinjaTrader capture)</summary>\n')
        L.append(ohlc_table(w10, m10, off, '10s'))
        L.append('\n</details>')
    L.append('')
    return L, g


def summary_row(j, g):
    return {'date': j['date'], 'sym': j['sym'], 'dir': j['dir'], 'pnl': j.get('pnl') or 0.0,
            'R': g.get('R'), 'chase': g.get('chase_pct'), 'capture': g.get('capture'),
            'mae': g.get('mae_of_risk'), 'vol_x': g.get('vol_x'), 'body_x': g.get('body_x'),
            'grade': j.get('grade')}


def render_setup(code, entries, spec):
    meta = spec['setups'].get(code, {})
    L = ['# %s — %s' % (code, meta.get('name', '')), '']
    L.append('> Built from the real trades in EDGE LOG (TRADING LOG ▸ TRADES) and the chart links saved with them. '
             'The page is regenerated each time new trades are added, so hand edits here would be lost: '
             'change a label or note in TRADING LOG, or ask Claude to correct a reading.')
    L.append('')
    if meta.get('rule'):
        L.append('## The rule as written')
        L.append('')
        L += ['- %s' % r for r in meta['rule']]
        L.append('')
    if meta.get('findings'):
        L.append('## What the data says so far')
        L.append('')
        L += ['- %s' % f for f in meta['findings']]
        L.append('')
    for asset, head in (('futures', 'Futures'), ('stock', 'Stocks')):
        ent = [j for j in entries if j.get('asset', 'futures') == asset]
        if ent:
            L += render_section(head, ent)
    nd = spec.get('nodata', {}).get(code, [])
    if nd:
        L.append('## Stock trades tagged %s in the TRADETRACKER sheet, with no intraday data' % code)
        L.append('')
        L.append('> Free minute data does not reach back this far, so these carry only what the sheet recorded: '
                 'the fill, and the float / relative volume / breakout columns he filled in by hand. '
                 '"In EL" = the trade is also in TRADING LOG (Webull history there starts 2026-01-12).')
        L.append('')
        L.append('| Date | Sym | In EL | TF | Shares | Entry | Exit | P&L $ | Float (M sh) | Rel. vol | Breakout vol (M) | Breakout pts | Breakout % | Chart | Sheet note |')
        L.append('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
        for r in sorted(nd, key=lambda r: (r['date'], r['sym'])):
            ch = r.get('chart') or ''
            L.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
                r['date'], r['sym'], 'yes (unlabelled there)' if r.get('in_el') else 'no',
                r.get('tf') or '—', r.get('shares') if r.get('shares') not in (None, '') else '—',
                pxf(r['entry']), pxf(r['exit']), fmt(r.get('pnl')),
                fmt(r.get('float_m')), fmt(r.get('rvol'), 1), fmt(r.get('bo_vol_m'), 3), fmt(r.get('bo_pts')),
                fmt(r.get('bo_pct'), 1), ('[%s](%s)' % (ch.rstrip('/').rsplit('/', 1)[-1], ch)) if ch else '—',
                (r.get('notes') or '—').replace('|', '/')))
        L.append('')
    L.append('## How the columns are measured')
    L.append('')
    L += ['- **Signal** = the candle the setup keys on, measured on the 1-minute bar that holds it (the 5-minute candle on a trade he took off the 5-minute chart, or read off his own chart where a line says so); **stop** = beyond it (its low for a long, its high for a short).',
          '- **Chase %** = how far the fill sat past the signal close, as a share of the signal range. 0 = filled at the close; negative = better than the close. **same bar** = the fill came inside the signal bar itself (he traded a 5- or 10-second chart), so that bar closed after the fill and chase cannot be measured from these bars.',
          '- **R** = the result in price points divided by the risk to the stop, before fees. **P&L $** is after fees (about $1.90 a round trip on a micro), so a small positive R can still be a dollar loss; a win = P&L above $0.',
          '- **MAE % of risk** = the worst move against him while held, divided by the risk. **MFE pts** = the best move in his favour while held, in points. **Capture %** = his result divided by MFE pts (winners and scratches only).',
          '- **Best next 15m** = the best move, in points from his entry price, in the 15 one-minute bars after the exit (negative when price never got back to his entry). Stocks with only 5-minute bars use the three 5-minute bars after the exit bar, so theirs is approximate.',
          '- While held means: from 10-second bars when they exist (trades from 2026-06-26 on), to the nearest 10 seconds (the 10-second bars the fill and the exit fall in are counted whole). Otherwise the bar the fill came in and the bar the exit came in are both left out, because each also holds prices from outside the trade (the exit price itself still counts). A trade that did not stay through one full bar shows —.',
          "- **Vol × / Body ×** = the signal bar's volume and body against the average / median of the 10 bars before it.",
          '- Futures prices are unadjusted CME front-month bars (MES is read from ES bars and MNQ from NQ bars; the micro and full-size prints can differ by a tick or two on a fast bar). 10-second bars are the NinjaTrader capture, moved back 10 seconds because it stamps each bar at its close. Stock bars are Yahoo 1- or 5-minute bars kept with the scores.']
    L.append('')
    return '\n'.join(L)


def render_section(head, entries):
    blocks, sums = [], []
    for j in sorted(entries, key=lambda x: (x['date'], x['entry_time'])):
        B, g = trade_block(j, None)
        blocks.append(B)
        sums.append((j, g))
    L = []
    n = len(sums)
    wins = sum(1 for j, g in sums if (j.get('pnl') or 0) > 0)
    net = sum(j.get('pnl') or 0 for j, g in sums)
    Rs = [g['R'] for j, g in sums if g.get('R') is not None]
    ch = [g['chase_pct'] for j, g in sums if g.get('chase_pct') is not None]
    cap = [g['capture'] for j, g in sums if g.get('capture') is not None]
    mae = [g['mae_of_risk'] for j, g in sums if g.get('mae_of_risk') is not None]
    L.append('## %s — %d real trade%s' % (head, n, '' if n == 1 else 's'))
    L.append('')
    L.append('| Trades | Wins | Net $ | Avg R | Median chase % | Median MFE capture % | Median MAE % of risk |')
    L.append('|---|---|---|---|---|---|---|')
    med = lambda v: fmt(float(pd.Series(v).median()), 1) if v else '—'
    L.append('| %d | %d | %s | %s | %s | %s | %s |' % (
        n, wins, fmt(net), fmt(sum(Rs) / len(Rs)) if Rs else '—', med(ch), med(cap), med(mae)))
    L.append('')
    L.append('| Date | Sym | Dir | P&L $ | R | Chase % | Capture % | Vol × | Body × | Grade | Label from |')
    L.append('|---|---|---|---|---|---|---|---|---|---|---|')
    for j, g in sums:
        L.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            j['date'], j['sym'], j['dir'], fmt(j.get('pnl')), fmt(g.get('R')),
            'same bar' if g.get('same_bar') else fmt(g.get('chase_pct'), 1), fmt(g.get('capture')), fmt(g.get('vol_x'), 1),
            fmt(g.get('body_x'), 1), j.get('grade') or '—', j.get('label_source', 'EL')))
    L.append('')
    L.append('### %s trades, one by one' % head)
    L.append('')
    for b in blocks:
        L += b
    return L


def render(a):
    spec = json.load(io.open(SPEC, encoding='utf-8'))
    os.makedirs(OUT_DIR, exist_ok=True)
    files = {}
    by = {}
    for j in spec['trades']:
        if j.get('label') in SETUPS:
            by.setdefault(j['label'], []).append(j)
    for code in SETUPS:
        if by.get(code):
            files['%s.md' % code] = render_setup(code, by[code], spec)
    files['README.md'] = render_index(spec, by)
    if a.check:
        stale = [f for f, s in files.items()
                 if not os.path.exists(os.path.join(OUT_DIR, f))
                 or io.open(os.path.join(OUT_DIR, f), encoding='utf-8', newline='').read().replace(chr(13) + chr(10), chr(10)) != s]
        if stale:
            print('STALE:', ', '.join(stale), '- run: python tools/setup_journal.py render')
            sys.exit(1)
        print('up to date')
        return
    for f, s in files.items():
        io.open(os.path.join(OUT_DIR, f), 'w', encoding='utf-8', newline='').write(s)
    print('wrote', ', '.join(sorted(files)))


def render_index(spec, by):
    L = ['# Setup journals — real discretionary trades', '']
    L.append('> One page per setup label. Each lists every real trade tagged with it in EDGE LOG '
             '(TRADING LOG ▸ TRADES), the chart links saved with it, and the OHLC behind it.')
    L.append('')
    L.append('| Setup | Meaning | Futures trades | Futures wins | Futures net $ | Stock trades | Stock net $ | Older sheet-only stock trades | Page |')
    L.append('|---|---|---|---|---|---|---|---|---|')
    for code in SETUPS:
        e = by.get(code, [])
        if not e:
            continue
        f = [j for j in e if j.get('asset', 'futures') == 'futures']
        s = [j for j in e if j.get('asset') == 'stock']
        L.append('| %s | %s | %d | %d | %s | %d | %s | %d | [%s.md](%s.md) |' % (
            code, spec['setups'].get(code, {}).get('name', ''), len(f),
            sum(1 for j in f if (j.get('pnl') or 0) > 0), fmt(sum(j.get('pnl') or 0 for j in f)),
            len(s), fmt(sum(j.get('pnl') or 0 for j in s)) if s else '—',
            len(spec.get('nodata', {}).get(code, [])), code, code))
    L.append('')
    for sec in ('unlabelled', 'conflicts', 'notes'):
        if spec.get(sec):
            L.append('## %s' % {'unlabelled': 'Real trades with no setup label yet',
                                 'conflicts': 'Where EL and the TRADETRACKER sheet disagree',
                                 'notes': 'Notes'}[sec])
            L.append('')
            L += ['- %s' % x for x in spec[sec]]
            L.append('')
    return '\n'.join(L)


# ------------------------------------------------------------------ build (one-off merge of the checks)

FIELD = {'times.entry_time': 'entry_time', 'times.exit_time': 'exit_time', 'times.hold_from': 'hold_from',
         'times.entry_ts_10s': 'entry_ts', 'times.exit_ts_10s': 'exit_ts', 'signal.signal_candle': 'signal_candle',
         'signal.stop': 'stop', 'signal.px_offset': 'px_offset', 'label.chosen': 'label',
         'snapshot.created_et': 'snapshot_created'}


def trim_save(b, t0, t1, pre, post, rel):
    w = b[(b.index >= t0 - pd.Timedelta(minutes=pre)) & (b.index <= t1 + pd.Timedelta(minutes=post))]
    fp = os.path.join(DATA, rel)
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    w.to_csv(fp)
    return rel


def build(a):
    """Merge the per-trade snapshot checks (reader -> skeptic -> judge) into the spec.

    --results is the JSON the checking workflow returned: {results: [{n, claim, verdict, judge}]}.
    Final value per field = the judge's decision where the skeptic refuted it, else the reader's."""
    prepd = {}
    for f in ('prep.json', 'prep_stock.json'):
        fp = os.path.join(a.cache, f)
        if os.path.exists(fp):
            prepd.update({r['n']: r for r in json.load(io.open(fp, encoding='utf-8'))})
    res = []
    for f in a.results.split(','):
        r = json.load(io.open(f, encoding='utf-8'))
        res += r.get('results', r) if isinstance(r, dict) else r
    spec = json.load(io.open(SPEC, encoding='utf-8')) if os.path.exists(SPEC) else {'setups': {}}
    done = {r['n'] for r in res if r.get('claim')}
    keep = [j for j in spec.get('trades', []) if j['n'] not in done]
    trades = []
    for r in sorted(res, key=lambda r: r['n']):
        c = r.get('claim')
        if not c:
            continue
        p = prepd[r['n']]
        v = {
            'entry_time': c['times']['entry_time'], 'exit_time': c['times']['exit_time'],
            'hold_from': c['times'].get('hold_from'), 'entry_ts': c['times'].get('entry_ts_10s'),
            'exit_ts': c['times'].get('exit_ts_10s'), 'signal_candle': c['signal']['signal_candle'],
            'stop': c['signal']['stop'], 'px_offset': c['signal'].get('px_offset') or 0.0,
            'label': c['label']['chosen'], 'snapshot_created': c['snapshot'].get('created_et'),
        }
        refuted = [f for f in ((r.get('verdict') or {}).get('fields') or []) if f['verdict'] == 'refuted']
        decided = {d['field']: d for d in ((r.get('judge') or {}).get('decisions') or [])}
        changed = []
        for f in refuted:
            k = FIELD.get(f['field'])
            if not k:
                continue
            d = decided.get(f['field'])
            new = d['final'] if d else None
            if d and new is not None and new != v.get(k):
                if k in ('stop', 'px_offset'):
                    new = float(new)
                changed.append('%s %s→%s' % (k.replace('_', ' '), v.get(k), new))
                v[k] = new
        if not refuted:
            check = 'chart and bars read, then re-checked by a second, independent pass: every field confirmed'
        elif changed:
            check = 'the second check disputed %d field%s; a third check re-read the files and set %s' % (
                len(refuted), '' if len(refuted) == 1 else 's', '; '.join(changed))
        else:
            check = 'the second check disputed %d field%s; a third check re-read the files and kept the first reading' % (
                len(refuted), '' if len(refuted) == 1 else 's')
        sheet = p.get('sheet') or {}
        label_source = 'EL' if p['el_setup'] else ('sheet' if sheet.get('setup') else '')
        shift = c['times'].get('journal_shift_min') or 0
        asset = p.get('asset', 'futures')
        root = ROOT_OF.get(p['sym'], p['sym'])
        iv = p.get('bars_interval', '1m')
        d = p['date']
        t0 = _t(d, v['signal_candle'])
        t1 = _t(d, v['exit_time'])
        b1 = pd.read_csv(p['bars_1m'], index_col=0)
        b1.index = pd.to_datetime(b1.index, utc=True).tz_convert(ET)
        b1.columns = [x.lower() for x in b1.columns]
        b1 = b1[['open', 'high', 'low', 'close', 'volume']]
        pad = 45 if iv == '1m' else 120
        bars_file = trim_save(b1, t0, t1, pad, pad, 'setup_bars/%s_%s_n%d_%s.csv' % (root, d, p['n'], iv))
        e = {
            'n': p['n'], 'asset': asset, 'trade_id': p['trade_id'], 'date': d, 'sym': p['sym'],
            'dir': p['dir'], 'entry': p['entry'], 'exit': p['exit'], 'qty': p['qty'], 'pnl': p['pnl'],
            'label': v['label'], 'label_source': label_source, 'el_label': p['el_setup'],
            'sheet_label': sheet.get('setup') or '', 'grade': p.get('el_grade'),
            'tf': p.get('el_tf') or sheet.get('tf'), 'notes': p.get('el_notes') or sheet.get('notes') or '',
            'links': p['links'], 'signal_candle': v['signal_candle'], 'entry_time': v['entry_time'],
            'exit_time': v['exit_time'], 'hold_from': v['hold_from'], 'entry_ts': v['entry_ts'],
            'exit_ts': v['exit_ts'], 'stop': v['stop'], 'px_offset': v['px_offset'],
            'snapshot_created': v['snapshot_created'],
            'snapshot_read': c['snapshot'].get('read'),
            'snapshot_depicts': c['snapshot'].get('depicts_this_trade'),
            'drawn': {'entry': c['snapshot'].get('drawn_entry'), 'stop': c['snapshot'].get('drawn_stop'),
                      'target': c['snapshot'].get('drawn_target')},
            'label_evidence': c['label'].get('evidence'), 'label_snapshot_supports': c['label'].get('snapshot_supports'),
            'el_times': ('%s–%s' % (p['el_entry_time'], p['el_exit_time'])) if shift else None,
            'bars_file': bars_file, 'interval': iv, 'bars_source': p.get('bars_1m_source'),
            'check': check, 'confidence': c.get('confidence'),
            'issues': (c.get('issues') or []) + ((r.get('verdict') or {}).get('extra_issues') or []),
        }
        if p.get('bars_10s'):
            b10 = pd.read_csv(p['bars_10s'], index_col=0)
            b10.index = pd.to_datetime(b10.index, utc=True).tz_convert(ET)
            e['bars_10s_file'] = trim_save(b10, t0, t1, 4, 6, 'setup_bars/%s_%s_n%d_10s.csv' % (root, d, p['n']))
        else:                                       # no 10s bars exist: a 10s stamp can't be real
            e['entry_ts'] = e['exit_ts'] = None
        trades.append(e)
    spec['trades'] = trades + keep
    io.open(SPEC, 'w', encoding='utf-8', newline='\n').write(json.dumps(spec, indent=1, ensure_ascii=False))
    print('spec: %d futures + %d stock entries -> %s' % (len(trades), len(keep), SPEC))


def main():
    ap = argparse.ArgumentParser(description='per-setup journals of the real futures trades')
    ap.add_argument('cmd', choices=['prep', 'build', 'render', 'check'])
    ap.add_argument('--cache', default=os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Temp',
                                                    'setup_journal_cache'))
    ap.add_argument('--results', help='build: the checking workflow result JSON')
    a = ap.parse_args()
    a.check = a.cmd == 'check'
    if a.cmd == 'prep':
        prep(a)
    elif a.cmd == 'build':
        build(a)
    else:
        render(a)


if __name__ == '__main__':
    main()
