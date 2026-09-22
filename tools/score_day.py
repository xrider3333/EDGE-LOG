# score_day.py - the data half of the END-OF-DAY SCORE routine (SCORE column in EDGE LOG).
#
# The routine (a scheduled Claude session, see tools/data/SCORING_ROUTINE.md) runs this first:
#
#   python tools/score_day.py                 today (US/Eastern)
#   python tools/score_day.py --date 2026-09-22
#   python tools/score_day.py --days 3        today and the 2 sessions before (catch-up)
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


def et_today():
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo('America/New_York')).date()
    except Exception:
        return dt.date.today()


def journal(cred, uid, dates):
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred))
    col = firestore.client().collection('users').document(uid).collection('trades')
    out = []
    for d in dates:
        out += [x.to_dict() or {} for x in col.where('date', '==', d).stream()]
    return out


def done_keys(spec):
    ks = {ts.key_of(t) for t in spec['trades']}
    ks |= {ts.key_of(dict(n, key_time=True)) for n in spec.get('na', [])}
    return ks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date')
    ap.add_argument('--days', type=int, default=1)
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
    rows = journal(a.cred, a.uid, dates)
    pending, na_new, skipped = [], [], 0
    for t in sorted(rows, key=lambda r: (str(r.get('date')), str(r.get('entryTime')))):
        sym = str(t.get('symbol') or '').upper()
        et = str(t.get('entryTime') or '')[:5]
        xt = str(t.get('exitTime') or '')[:5] or et
        base = {'sym': sym, 'date': t.get('date'), 'entry_time': et}
        if not sym or not et:
            na_new.append(dict(base, entry_time=et or '00:00',
                               reason='the trade has no entry time, so its bars cannot be lined up'))
            continue
        if ts.key_of(dict(base, key_time=True)) in have:
            skipped += 1
            continue
        try:
            bars = ts.load_bars(sym, t['date'], '1m')
            day = bars[bars.index.date == pd.Timestamp(t['date']).date()]
        except SystemExit as e:
            day, why = None, str(e)
        except Exception as e:           # network / Yahoo hiccup - leave it for the next run
            print('  retry later: %s %s %s (%s)' % (t['date'], sym, et, e))
            continue
        if day is None or not len(day) or not len(day.between_time(et, xt)):
            na_new.append(dict(base, reason='no 1-minute price data for %s on %s (free data only '
                                            'reaches back ~30 days)' % (sym, t['date'])))
            continue
        i0 = day.index.get_indexer([day.between_time(et, et).index[0]
                                    if len(day.between_time(et, et)) else day.index[0]])[0]
        win = day.iloc[max(0, i0 - CONTEXT_BARS): i0 + CONTEXT_BARS + 1]
        pending.append({
            'sym': sym, 'date': t['date'], 'dir': t.get('type', 'LONG'),
            'asset': 'futures' if sym in ts.FUT_ROOTS else 'stock',
            'entry_time': et, 'exit_time': xt,
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
