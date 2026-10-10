"""cbu_forward_log.py - the CBU ALERT's forward log (MANAGER #31 (a): count of fired alerts and the hit rate, weekly).

Replays the final alert (SETUPS_PREREG_R3_CBU_V1.md section 11: any base, all day 09:30-15:44, 200 SMA context, the
same rules as CBU ALERT 1.0 on TradingView) on NQ and ES over CLOSED regular sessions from --from (default 2026-10-05,
the first session after the TradingView alerts went live on 2026-10-02), and scores each alert with the owner's plan:

  entry = the next bar's open; stop = the signal candle's low - 1 tick; R = entry - stop;
  once a bar's high reaches entry + 1R the stop moves to the entry (breakeven), then ride;
  out at the stop, else at the close of the last regular-session bar (15:59).
  A bar that touches both the stop and +1R counts as stopped (the conservative reading of a 1-minute bar).

'Reached +1R' is the hit rate. Each alert is also matched to the owner's SHOULD HAVE TRADED entries (the labelled set,
tools/missed_pull.py) at the signal minute or the minute after. A forward LOG, not a test: nothing here is tuned.
ES on our side stands for the MES1! chart the alert runs on (same price series).

THE READ PROTOCOL (MANAGER GO 10-10, from DISC's power check; replaces "an edge read at 50 alerts", MANAGER #31 (c)):
  - At 50 alerts the log can only see HARM, not an edge. Alerts cluster by day (11 on 2026-10-05), so the effective
    sample is closer to the session count than the alert count. With a per-alert SD of about 1.2R once winners appear,
    the smallest mean a 50-alert read can tell from zero is about 0.4-0.6R. A plausible setup edge (0.1-0.3R) is
    far below that.
  - HARM READ (from HARM_AT = 50 alerts on): mean R < HARM_MEAN_R (-0.3R) AND the session-clustered t < HARM_T (-2)
    -> "HARM": the alert is losing for real; tell MANAGER and stop treating it as a candidate.
  - EDGE READ: only from EDGE_AT_ALERTS = 300 alerts AND EDGE_AT_SESSIONS = 60 sessions with an alert. Before that,
    no edge claim either way.
  read_status() prints which of these applies; the clustered t uses per-session sums of (R - mean) (CR0).

    python tools/cbu_forward_log.py [--from 2026-10-05] [--to YYYY-MM-DD] [--out C:\\EdgeLog\\cbu_forward]
"""
import argparse
import io
import os
import sys

import numpy as np
import pandas as pd

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import point_score as P  # noqa: E402
import cbu_v1_alerts as C  # noqa: E402

LIVE_FROM = '2026-10-05'
OUT_DIR = r'C:\EdgeLog\cbu_forward'
VARIANT = 'sig_any_day'
# the read protocol (module docstring)
HARM_AT = 50
HARM_MEAN_R = -0.3
HARM_T = -2.0
EDGE_AT_ALERTS = 300
EDGE_AT_SESSIONS = 60


def walk(po, ph, pl, pc, dord, mod, i, tick):
    """The owner's plan for the alert at bar i, reading bars i+1.. of the same session only. None if there is no next
    bar in the session."""
    j = i + 1
    if j >= len(po) or dord[j] != dord[i] or mod[j] >= P.RTH_CLOSE:
        return None
    entry, stop = float(po[j]), float(pl[i]) - tick
    r = entry - stop
    if not r > 0:
        return None
    be = hit1 = False
    out, k = None, j
    while k < len(po) and dord[k] == dord[i] and mod[k] < P.RTH_CLOSE:
        cur = entry if be else stop
        if pl[k] <= cur:
            out = cur
            break
        if ph[k] >= entry + r:
            hit1 = be = True
        out = float(pc[k])
        k += 1
    return dict(entry=entry, stop=stop, risk_pts=r, reached_1R=hit1, exit=out, R=(out - entry) / r)


def missed_cbu(path=None):
    """SHOULD HAVE TRADED CBU longs as (root, signal epoch)."""
    out = []
    for e in C._pulled_missed(path):
        if str(e.get('setup', '')).upper() != 'CBU' or str(e.get('type', '')).upper() != 'LONG':
            continue
        root = P.ROOT_OF.get(str(e.get('symbol', '')).upper())
        if root and e.get('date') and e.get('signal_candle'):
            out.append((root, P._epoch('%s %s' % (e['date'], e['signal_candle']))))
    return out


def forward(date_from=LIVE_FROM, date_to=None, missed=None, bars=None):
    lo = np.datetime64(date_from, 'D').astype('int64')
    hi = np.datetime64(date_to, 'D').astype('int64') if date_to else None
    missed = missed_cbu() if missed is None else missed
    rows = []
    for root in ('NQ', 'ES'):
        b = bars[root] if bars else P.load_bars(root)
        d = C.decisions(b, 'sma')
        closed = C.closed_sessions(d)
        po, ph, pl, pc, _ = b.adjusted()
        dord, mod, t = d['dord'].to_numpy(), d['mod'].to_numpy(), d['t'].to_numpy()
        ok = d[VARIANT].to_numpy() & (dord >= lo) & np.isin(dord, list(closed))
        if hi is not None:
            ok &= dord <= hi
        tick = P.TICK.get(root, 0.25)
        for i in C.episodes(np.flatnonzero(ok)):
            w = walk(po, ph, pl, pc, dord, mod, i, tick)
            if w is None:
                continue
            ti = int(t[i])
            mark = any(r == root and ti <= s0 <= ti + 60 for r, s0 in missed)
            rows.append(dict(root=root, signal_et=P._et_str(ti), session=C.ord_str(int(dord[i])),
                             should_have_traded=mark, **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in w.items()}))
    return pd.DataFrame(rows)


def summary(df):
    if df.empty:
        return 'no alerts in the window'
    s = pd.to_datetime(df['session'])
    df = df.assign(week=(s - pd.to_timedelta(s.dt.weekday, unit='D')).dt.strftime('%Y-%m-%d'))
    lines = ['week of      alerts  NQ  ES  reached+1R  mean R  total R  marked']
    for wk, g in df.groupby('week'):
        lines.append('%-12s %6d %3d %3d %6d (%3.0f%%) %7.2f %8.2f %7d' % (
            wk, len(g), int((g.root == 'NQ').sum()), int((g.root == 'ES').sum()), int(g.reached_1R.sum()),
            100 * g.reached_1R.mean(), g.R.mean(), g.R.sum(), int(g.should_have_traded.sum())))
    lines.append('all          %6d %3d %3d %6d (%3.0f%%) %7.2f %8.2f %7d   (%d sessions with an alert)' % (
        len(df), int((df.root == 'NQ').sum()), int((df.root == 'ES').sum()), int(df.reached_1R.sum()),
        100 * df.reached_1R.mean(), df.R.mean(), df.R.sum(), int(df.should_have_traded.sum()), df.session.nunique()))
    lines.append(read_status(df))
    return '\n'.join(lines)


def clustered_t(df):
    """Mean R / its session-clustered standard error (CR0: per-session sums of R - mean). None below 2 sessions or
    with no spread."""
    if df.empty or df.session.nunique() < 2:
        return None
    r = df.R.astype(float)
    dev = (r - r.mean()).groupby(df.session).sum()
    se = float(np.sqrt((dev ** 2).sum())) / len(r)
    return float(r.mean()) / se if se > 0 else None


def read_status(df):
    """One line: which read of the protocol (module docstring) applies now, and its numbers."""
    n = 0 if df.empty else len(df)
    s = 0 if df.empty else int(df.session.nunique())
    if n < HARM_AT:
        return 'READ: none yet - the harm read starts at %d alerts (%d/%d); an edge read needs %d alerts and %d sessions' % (
            HARM_AT, n, HARM_AT, EDGE_AT_ALERTS, EDGE_AT_SESSIONS)
    m, t = float(df.R.mean()), clustered_t(df)
    tt = 'n/a' if t is None else '%.2f' % t
    harm = t is not None and m < HARM_MEAN_R and t < HARM_T
    head = ('HARM READ: HARM - mean %.2fR, session-clustered t %s (bar: mean < %.1fR and t < %.0f); tell MANAGER'
            % (m, tt, HARM_MEAN_R, HARM_T) if harm else
            'HARM READ: no harm shown - mean %.2fR, session-clustered t %s (bar: mean < %.1fR and t < %.0f)'
            % (m, tt, HARM_MEAN_R, HARM_T))
    if n >= EDGE_AT_ALERTS and s >= EDGE_AT_SESSIONS:
        return head + ' | EDGE READ DUE: %d alerts, %d sessions' % (n, s)
    return head + ' | edge read waits for %d alerts and %d sessions (now %d / %d)' % (EDGE_AT_ALERTS, EDGE_AT_SESSIONS, n, s)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='date_from', default=LIVE_FROM)
    ap.add_argument('--to', dest='date_to', default=None)
    ap.add_argument('--out', default=OUT_DIR)
    a = ap.parse_args(argv)
    df = forward(a.date_from, a.date_to)
    text = summary(df)
    print(text)
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        df.to_csv(os.path.join(a.out, 'alerts.csv'), index=False)
        io.open(os.path.join(a.out, 'summary.txt'), 'w', encoding='utf-8').write(text + '\n')


if __name__ == '__main__':
    main()
