# score_day.py - the data half of the END-OF-DAY SCORE routine (SCORE column in EDGE LOG).
#
# The routine (a scheduled Claude session, see tools/data/SCORING_ROUTINE.md) runs this first:
#
#   python tools/score_day.py                 today (US/Eastern)
#   python tools/score_day.py --date 2026-09-22
#   python tools/score_day.py --days 3        today and the 2 sessions before (catch-up)
#   python tools/score_day.py --all           every trade in the journal (backfill)
#
# Where bars come from: Yahoo 1m (last ~30 days); futures older than that come from the local
# unadjusted ES / NQ 1-minute masters in augur_uploads (prices match MES / MNQ fills); stocks
# fall back to Yahoo 5m (~60 days). Older stocks have no free source and are marked NA.
#
# For every journal trade on those dates that has no score yet (futures AND stocks):
#   * fetch + cache 1-minute bars for that session (tools/data/score_bars, committed to git);
#   * no bars at all -> append an NA entry to tools/data/trade_scores.json (the SCORE pill
#     then reads NA and says why);
#   * bars found -> write the trade plus a window of bars around it to
#     tools/data/score_pending.json for Claude to author the factor scores.
# It never writes a score itself - scoring is judgement, done by the routine.
import os
import io
import sys
import json
import argparse
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import trade_scores as ts

ROOT = ts.ROOT
PENDING = os.path.join(ts.DATA, 'score_pending.json')
SHARED_CRED = r'C:\Users\xride\OneDrive\Desktop\EDGE-LOG\serviceAccount.json'
DEFAULT_UID = 'IO0K35JpLIcH9YK4C0pMNYUzZOM2'
CONTEXT_BARS = 30          # bars either side of the trade handed to the author
MASTERS = 'C:/Users/xride/OneDrive/Desktop/EDGE-LOG/augur_uploads'
MASTER_OF = {'ES': 'ES', 'MES': 'ES', 'NQ': 'NQ', 'MNQ': 'NQ'}
_master_cache = {}


def master_day(sym, date):
    """One session of 1m bars from the local unadjusted master, cached like a Yahoo pull."""
    root = MASTER_OF.get(sym)
    if not root:
        return None
    if root not in _master_cache:
        fp = os.path.join(MASTERS, 'NOADJ_%s_1m_ETH.csv' % root)
        if not os.path.exists(fp):
            return None
        m = pd.read_csv(fp, usecols=['time', 'open', 'high', 'low', 'close', 'volume'])
        m.index = pd.DatetimeIndex(pd.to_datetime(m.time, unit='s', utc=True)).tz_convert('America/New_York')
        m = m.drop(columns='time')
        m.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        _master_cache[root] = m
    m = _master_cache[root]
    d0 = pd.Timestamp(date).date()
    day = m[m.index.date == d0]
    if not len(day):
        return None
    os.makedirs(ts.CACHE, exist_ok=True)
    day.to_csv(ts.cache_path(sym, date, '1m'))
    return day


def get_day(sym, date, et, xt):
    """(bars for that session, interval) or (None, reason)."""
    tried = []
    for iv in ('1m', '5m'):
        try:
            b = ts.load_bars(sym, date, iv)
            day = b[b.index.date == pd.Timestamp(date).date()]
            if len(day) and len(day.between_time(et, xt) if iv == '1m' else day.between_time(et, et[:4] + '9')):
                return day, iv
            tried.append('Yahoo %s had no bars at %s' % (iv, et))
        except SystemExit:
            tried.append('Yahoo %s out of range' % iv)
        except Exception as e:
            tried.append('Yahoo %s error %s' % (iv, e))
        if iv == '1m' and sym in MASTER_OF:
            day = master_day(sym, date)
            if day is not None and len(day.between_time(et, xt)):
                return day, '1m'
            tried.append('NOBARS_AT_TIME' if day is not None else 'NODAY')
            break                      # futures never drop to 5m
    return None, '; '.join(tried)


def et_today():
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo('America/New_York')).date()
    except Exception:
        return dt.date.today()


def journal(cred, uid, dates, everything=False):
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred))
    col = firestore.client().collection('users').document(uid).collection('trades')
    if everything:
        return [dict(x.to_dict() or {}, _id=x.id) for x in col.stream()]
    out = []
    for d in dates:
        out += [dict(x.to_dict() or {}, _id=x.id) for x in col.where('date', '==', d).stream()]
    return out


def done_keys(spec):
    ks = {ts.key_of(t) for t in spec['trades']}
    ks |= {ts.key_of(dict(n, key_time=True)) for n in spec.get('na', [])}
    return ks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date')
    ap.add_argument('--days', type=int, default=1)
    ap.add_argument('--all', action='store_true', help='every trade in the journal')
    ap.add_argument('--cred', default=SHARED_CRED)
    ap.add_argument('--uid', default=DEFAULT_UID)
    a = ap.parse_args()

    end = dt.date.fromisoformat(a.date) if a.date else et_today()
    dates, d = [], end
    while len(dates) < a.days:
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d -= dt.timedelta(days=1)

    spec = json.load(io.open(ts.SPEC, encoding='utf-8'))
    spec.setdefault('na', [])
    have = done_keys(spec)
    rows = journal(a.cred, a.uid, dates, a.all)
    if a.all:
        dates = ['ALL']
    pending, na_new, skipped = [], [], 0
    from collections import Counter
    minute = Counter((str(r.get('date')), str(r.get('symbol') or '').upper(),
                      str(r.get('entryTime') or '')[:5]) for r in rows)
    for t in sorted(rows, key=lambda r: (str(r.get('date')), str(r.get('entryTime')))):
        sym = str(t.get('symbol') or '').upper()
        et = str(t.get('entryTime') or '')[:5]
        xt = str(t.get('exitTime') or '')[:5] or et
        base = {'sym': sym, 'date': t.get('date'), 'entry_time': et}
        if minute[(str(t.get('date')), sym, et)] > 1:
            base['trade_id'] = t['_id']
        if not sym or not et:
            na_new.append(dict(base, entry_time=et or '00:00',
                               reason='the trade has no entry time, so its bars cannot be lined up'))
            continue
        # an older hand-authored score is keyed date|SYM and covers that trade already
        if ts.key_of(dict(base, key_time=True)) in have or ts.key_of(base) in have:
            skipped += 1
            continue
        if not str(t.get('date') or '')[:4].isdigit():
            na_new.append(dict(base, date=str(t.get('date')), reason='the trade has no valid date'))
            continue
        shift = 0
        day, iv = get_day(sym, t['date'], et, xt)
        cand = day
        if day is None and 'NOBARS_AT_TIME' in iv:      # e.g. 17:10 logged = inside the CME break
            cand = master_day(sym, t['date'])
        if cand is not None and sym in MASTER_OF and t.get('entry') is not None:
            day0, day = day, cand
            # Some journal imports logged Pacific (or Central) clock time. If the fill is not
            # inside the bar at the logged minute but is at -3h / -1h, read the bars there.
            def hits(hm):
                b = day.between_time(hm, hm)
                return len(b) and float(b.Low.min()) - 0.25 <= float(t['entry']) <= float(b.High.max()) + 0.25
            sh_t = lambda hm, m: (pd.Timestamp(t['date'] + ' ' + hm) + pd.Timedelta(minutes=m)).strftime('%H:%M')
            if not hits(et):
                for m in (-180, -60, 180, 60):
                    if hits(sh_t(et, m)):
                        shift = m
                        break
            if shift:
                et, xt = sh_t(et, shift), sh_t(xt, shift)
                iv = '1m'
            else:
                day = day0
        if day is None:
            if 'error' in iv:              # network / Yahoo hiccup - leave it for the next run
                print('  retry later: %s %s %s (%s)' % (t['date'], sym, et, iv))
                continue
            if 'NOBARS_AT_TIME' in iv:
                why = ('the futures market has no bars at %s ET that day (CME closes 17:00-18:00 ET '
                       'and on holidays)' % et)
            elif sym in MASTER_OF:
                why = ('no 1-minute %s data for %s. Yahoo only keeps 30 days and the local ES/NQ '
                       'files have a gap there' % (sym, t['date']))
            else:
                why = ('no intraday price data for %s on %s. Free stock data only reaches back '
                       'about 60 days' % (sym, t['date']))
            na_new.append(dict(base, reason=why))
            continue
        at = day[day.index.strftime('%H:%M') <= et]
        i0 = len(at) - 1 if len(at) else 0
        win = day.iloc[max(0, i0 - CONTEXT_BARS): i0 + CONTEXT_BARS + 1]
        pending.append({
            'trade_id': base.get('trade_id'),
            'sym': sym, 'date': t['date'], 'dir': t.get('type', 'LONG'),
            'asset': 'futures' if sym in ts.FUT_ROOTS else 'stock', 'interval': iv,
            'entry_time': base['entry_time'], 'exit_time': str(t.get('exitTime') or '')[:5] or base['entry_time'],
            'shift_min': shift, 'et_entry_time': et, 'et_exit_time': xt,
            'entry': t.get('entry'), 'exit': t.get('exit'), 'qty': t.get('size'),
            'pnl': t.get('pnl'), 'setup': t.get('setup'), 'timeframe': t.get('timeframe'),
            'notes': t.get('notes'), 'grade': t.get('grade'),
            'bars_et': [[k.strftime('%H:%M'), round(float(r.Open), 4), round(float(r.High), 4),
                         round(float(r.Low), 4), round(float(r.Close), 4), int(r.Volume or 0)]
                        for k, r in win.iterrows()],
        })

    if na_new:
        spec['na'] += na_new
        io.open(ts.SPEC, 'w', encoding='utf-8').write(json.dumps(spec, indent=1, ensure_ascii=False))
    io.open(PENDING, 'w', encoding='utf-8').write(json.dumps(pending, indent=1))
    print('dates %s | journal trades %d | already scored %d | marked NA %d | to author %d'
          % (','.join(dates), len(rows), skipped, len(na_new), len(pending)))
    for p in pending:
        print('  AUTHOR  %s %-5s %-5s %s %s->%s' % (p['date'], p['sym'], p['dir'], p['entry_time'],
                                                  p['entry'], p['exit']))
    for n in na_new:
        print('  NA      %s %-5s %s  %s' % (n['date'], n['sym'], n['entry_time'], n['reason']))
    print('pending worksheet: %s' % PENDING)


if __name__ == '__main__':
    main()
