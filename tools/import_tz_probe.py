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
  * every saved SYMBOL is the contract root (MES / MNQ), never the contract code a file carries
    (MESM6 / MNQM6 / MNQH6): Position History with and without its Product column, Performance,
    the PDF statement, a generic CSV (where a stock ticker must stay as written), and the root
    helper itself on a table of codes
  * a PDF statement for a day the journal already holds is merged, not saved a second time, and
    its fee summary reaches the trades it creates
  * a PDF statement NEVER rewrites a journal trade: a scale-out the journal holds as two 1-lot legs,
    two trades a tick apart, and a same-price trade the other way all leave the journal untouched;
    a trade the journal holds in another direction is reported, one it lacks is created, and every
    fee is the statement's fee per contract x size
  * the statement matches best fit first: a trade the journal lacks never takes its neighbour's copy
    (a minute, an hour or a tick away, or an untimed copy), a reversal fill (long 1, sell 2) makes two
    trades, a clearing fee is split across the day's symbols, and journal fees are left alone when
    the statement cannot account for every contract it charged
  * a roll day pairs each contract month apart, a copy of another size is reported against the
    round trip it fits best (never by time order), and every scale-out leg saved in the wrong zone
    is flagged
  * fills pair across New York midnight (an evening trade is one trade, dated by its entry), a
    position carried in or still open is reported and never paired into a made-up trade, and two
    scale-outs in one minute never swap legs
  * (review 2026-09-30) a statement that does not end flat pairs nothing and lists every fill (its
    open position is not read, so a position carried in AND still open cannot become made-up trades);
    a 2-lot missing one leg never takes the exact copy of a 1-lot beside it (it is reported as another
    size, not the 1-lot saved twice); an evening trade is priced at its trade date's fee rate, not $0;
    created trades carry the statement's account, so a re-import under another Settings account adds
    nothing; M2K is priced at $5 a point, and a contract with no known size is listed, never priced
    like a stock

Exit codes match preflight_boot.py: 0 PASS, 1 FAIL, 2 INCONCLUSIVE (never blocks).

Usage:
  python tools/import_tz_probe.py                # gates this repo's index.html
  python tools/import_tz_probe.py --file X.html  # gates X as if it were index.html
  python tools/import_tz_probe.py --selftest     # asserts FAIL on every KNOWN_BAD build (v73.885
                                                 # times, v73.944 symbols, from git history),
                                                 # PASS on this one

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
KNOWN_BAD = [('5326d02', '73.885', 'saved NinjaTrader export times exactly as printed'),
             ('8de5fcafbe5a82f9cef574244134204f9cbf4e27', '73.944',
              'saved futures contract codes as symbols: PDF trades became MESM / MNQH and were saved '
              'again beside the journal copy, Performance MNQ rows became MES')]

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


def position_history(rows, disp, product=True):
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
            '%.2f' % spx, 'DEMO123', sym + 'M6', sym if product else '', 'Micro contract', '-2', '0', '0.25',
            str(890000 + i),
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
    lines = ['Daily Statement 04/07/2026'] + FLAT
    by_sym = {}
    for t in rows:
        by_sym.setdefault(t[0], []).append(t)
    codes = {'MES': 'MESM6', 'MNQ': 'MNQH6'}
    # Daily Activity Summary: "MM/DD/YYYY <contract>" then "<contracts> <exch> <comm> <nfa> <pnl> ..."
    for sym, ts in by_sym.items():
        for day in sorted(set(et(_utc(t[2])).strftime('%m/%d/%Y') for t in ts)):
            lines.append('%s %s' % (day, codes[sym]))
            lines.append('2 0.40 0.70 0.04 1.25 1,000.00 - -')
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
    """{(date, entry price): (entry HH:MM, exit HH:MM, direction, root symbol)} in New York time."""
    out = {}
    for sym, d, eu, xu, epx, xpx, bf, sf in rows:
        e, x = et(_utc(eu)), et(_utc(xu))
        out[(e.strftime('%Y-%m-%d'), round(epx, 2))] = (e.strftime('%H:%M'), x.strftime('%H:%M'), d, sym)
    return out


# futRoot table: contract code (or ticker) -> the symbol the journal must save
ROOTS = {'MESM6': 'MES', 'MNQM6': 'MNQ', 'MNQH26': 'MNQ', 'ESZ5': 'ES', 'NQU26': 'NQ', '6EM6': '6E',
         'M2KU6': 'M2K', 'MESZ2026': 'MES', 'MES 12-26': 'MES', 'mesm6': 'MES', 'MES': 'MES', 'NQ': 'NQ',
         'AAPL': 'AAPL', 'TQQQ': 'TQQQ', 'SOXL': 'SOXL', 'VEEA': 'VEEA', 'BRK.B': 'BRK.B', 'QQQ': 'QQQ'}


def generic_csv():
    """A generic broker CSV: one futures contract code row and one stock row (times in Eastern)."""
    return ('Symbol,Qty,Entry Price,Exit Price,Side,Entry Time,Exit Time\r\n'
            'MESZ2026,1,6604.75,6605.00,Buy,04/07/2026 10:29:06,04/07/2026 10:31:40\r\n'
            'AAPL,10,210.50,211.25,Buy,04/08/2026 15:10:01,04/08/2026 15:12:43\r\n')


GENERIC_TRUTH = {('2026-04-07', 6604.75): ('10:29', '10:31', 'LONG', 'MES'),
                 ('2026-04-08', 210.5): ('15:10', '15:12', 'LONG', 'AAPL')}


RECON_DAY = '04/21/2026'   # EDT: GMT = New York + 4h
# Every real statement that ends flat prints this under its Open Trade Equity heading. One that does not
# end flat lists the open positions there instead, and the importer then pairs nothing (it lists every fill).
FLAT = ['Open Trade Equity', 'No Open Trade Equity']


def fill_lines(fills):
    """Statement FILL lines from [(New York HH:MM:SS, 'B'|'S', qty, price[, MM/DD/YYYY])] (EDT)."""
    out = ['Date & Time Code Buy Qty Sell Qty Filled Price Order_Id']
    for i, f in enumerate(fills):
        hms, side, qty, px = f[:4]
        g = datetime.strptime((f[4] if len(f) > 4 else RECON_DAY) + ' ' + hms, '%m/%d/%Y %H:%M:%S') + timedelta(hours=4)
        q = ('%d -' % qty) if side == 'B' else ('- %d' % qty)
        out.append('%s(GMT) FILL %s %s 7,%03d,%03d' % (g.strftime('%m/%d/%Y %I:%M:%S %p'), q,
                                                       ('%.2f' % px).rstrip('0').rstrip('.'), i, i * 7))
    return out


def pdf_day(fills, fee_total, acct='1810769', contracts=None, flat=True, code='MESM6',
            name='Micro E-mini S&P 500 - Jun. 2026'):
    """A one-day statement (MES unless code says otherwise); the summary counts both sides of every
    contract, as NinjaTrader's does. flat=True prints the "No Open Trade Equity" line a statement carries
    when it ends flat; flat=False is one that ends with a position open (its position list unread)."""
    return (['Daily Statement ' + RECON_DAY, 'Account Number: ' + acct]
            + (FLAT if flat else ['Open Trade Equity'])
            + ['%s %s' % (RECON_DAY, code),
             '%d %.2f 0.00 0.00 10.00 1,000.00 - -' % (contracts or sum(f[2] for f in fills), fee_total),
             'Trading details for %s (%s)' % (name, code)] + fill_lines(fills))


def pdf_two_symbols():
    """MES and MNQ on one day with ONE clearing row: 1.52 each + clearing 0.76 split = 1.90 each."""
    return (['Daily Statement ' + RECON_DAY, 'Account Number: 1810769'] + FLAT +
            ['%s MESM6' % RECON_DAY, '2 -0.70 -0.78 -0.04 5.00 1,000.00 - -',
             '%s MNQM6' % RECON_DAY, '2 -0.70 -0.78 -0.04 5.00 1,000.00 - -',
             '%s Clearing_Fee' % RECON_DAY, '- - - - -0.76 -0.76 - -',
             'Trading details for Micro E-mini S&P 500 - Jun. 2026 (MESM6)']
            + fill_lines([('10:00:05', 'B', 1, 7000.00), ('10:02:05', 'S', 1, 7002.00)])
            + ['Trading details for Micro E-mini Nasdaq-100 - Jun. 2026 (MNQM6)']
            + fill_lines([('11:00:05', 'B', 1, 26000.00), ('11:02:05', 'S', 1, 26010.00)]))


def jt(tid, typ, entry, exit_, e, x, size=1, **kw):
    """A journal trade on RECON_DAY (MES, account 1810769, no fee yet)."""
    t = {'id': tid, 'date': '2026-04-21', 'symbol': 'MES', 'type': typ, 'entry': entry, 'exit': exit_,
         'size': size, 'entryTime': e, 'exitTime': x, 'fees': 0, 'account': '1810769'}
    t.update(kw)
    return t


def pdf_roll():
    """A roll day: MESM6 long and MESU6 short open at the same time (1.90 per round-trip contract)."""
    return (['Daily Statement ' + RECON_DAY, 'Account Number: 1810769'] + FLAT +
            ['%s MESM6' % RECON_DAY, '2 1.90 0.00 0.00 10.00 1,000.00 - -',
             '%s MESU6' % RECON_DAY, '2 1.90 0.00 0.00 10.00 1,000.00 - -',
             'Trading details for Micro E-mini S&P 500 - Jun. 2026 (MESM6)']
            + fill_lines([('10:00:05', 'B', 1, 7000.00), ('10:05:00', 'S', 1, 7002.00)])
            + ['Trading details for Micro E-mini S&P 500 - Sep. 2026 (MESU6)']
            + fill_lines([('10:01:05', 'S', 1, 7050.00), ('10:06:00', 'B', 1, 7048.00)]))


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
        {'name': 'ph-contract-only', 'kind': 'csv', 'text': position_history(TRADES, et, product=False),
         'opts': {'tz': 'America/New_York'}, 'expect': 'rows', 'truth': truth(TRADES)},
        {'name': 'generic-root-and-stock', 'kind': 'csv', 'text': generic_csv(),
         'opts': {'tz': 'America/New_York'}, 'expect': 'rows', 'truth': GENERIC_TRUTH},
        {'name': 'pdf-fees', 'kind': 'pdf', 'lines': pdf_lines(TRADES), 'opts': {'tz': 'auto'},
         'expect': 'rows', 'truth': truth(TRADES), 'fees': True},
        {'name': 'pdf-merges-journal-day', 'kind': 'pdf', 'lines': pdf_lines(TRADES), 'opts': {'tz': 'auto'},
         'trades': [dict(late, id='probe-journal', entryTime=e0.strftime('%H:%M'), exitTime=x0.strftime('%H:%M'))],
         'expect': 'pdfmerge', 'skip_date': e0.strftime('%Y-%m-%d'), 'n': len(TRADES) - 1},
        {'name': 'root-table', 'kind': 'roots', 'inputs': list(ROOTS), 'expect': 'roots'},
        # --- PDF statement vs the journal: match one-to-one, never rewrite (3.80 over 2 contracts) ---
        {'name': 'pdf-scaleout-legs', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 2, 7000.00), ('10:05:10', 'S', 1, 7002.00),
                           ('10:10:20', 'S', 1, 7004.00)], 3.80),
         'trades': [jt('leg-a', 'LONG', 7000.00, 7002.00, '10:00', '10:05'),
                    jt('leg-b', 'LONG', 7000.00, 7004.00, '10:00', '10:10')],
         'rows': [], 'flags': 0, 'fees': {'leg-a': 1.90, 'leg-b': 1.90}},
        {'name': 'pdf-tick-apart', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:30:05', 'B', 1, 6604.75), ('10:31:40', 'S', 1, 6605.00),
                           ('10:40:05', 'B', 1, 6605.00), ('10:45:30', 'S', 1, 6605.25)], 3.80),
         'trades': [jt('tick-1', 'LONG', 6604.75, 6605.00, '10:30', '10:31'),
                    jt('tick-2', 'LONG', 6605.00, 6605.25, '10:40', '10:45')],
         'rows': [], 'flags': 0, 'fees': {'tick-1': 1.90, 'tick-2': 1.90}},
        {'name': 'pdf-opposite-missing', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('11:00:10', 'S', 1, 6700.00), ('11:01:50', 'B', 1, 6698.00),
                           ('11:02:10', 'B', 1, 6699.00), ('11:04:00', 'S', 1, 6700.00)], 3.80),
         'trades': [jt('long-only', 'LONG', 6699.00, 6700.00, '11:02', '11:04')],
         'rows': [('SHORT', 6700.00, '11:00', 1.90)], 'flags': 0, 'fees': {'long-only': 1.90}},
        {'name': 'pdf-direction-differs', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('09:45:00', 'S', 1, 6750.00), ('09:47:00', 'B', 1, 6751.00)], 1.90),
         'trades': [jt('wrong-way', 'LONG', 6750.00, 6751.00, '09:45', '09:47')],
         'rows': [], 'flags': 1, 'fees': {}},
        {'name': 'pdf-partial-day', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 1, 6800.00), ('10:02:05', 'S', 1, 6802.00),
                           ('10:20:05', 'B', 1, 6810.00), ('10:22:05', 'S', 1, 6812.00)], 3.80),
         'trades': [jt('held', 'LONG', 6800.00, 6802.00, '10:00', '10:02')],
         'rows': [('LONG', 6810.00, '10:20', 1.90)], 'flags': 0, 'fees': {'held': 1.90}},
        {'name': 'pdf-journal-3h-late', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 1, 6900.00), ('10:02:05', 'S', 1, 6901.00)], 1.90),
         'trades': [jt('late3', 'LONG', 6900.00, 6901.00, '13:00', '13:02')],
         'rows': [], 'flags': 0, 'fees': {'late3': 1.90}, 'drift': ['late3']},
        {'name': 'pdf-other-account', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 1, 6950.00), ('10:02:05', 'S', 1, 6951.00)], 1.90),
         'trades': [jt('other-acct', 'LONG', 6950.00, 6951.00, '10:00', '10:02', account='DEMO999')],
         'rows': [('LONG', 6950.00, '10:00', 1.90)], 'flags': 0, 'fees': {}},
        # --- review 2026-09-30: best fit first, reversals, clearing, incomplete days ---
        {'name': 'pdf-reversal-journal', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 1, 7000.00), ('10:05:00', 'S', 2, 7005.00),
                           ('10:08:00', 'B', 1, 7003.00)], 3.80),
         'trades': [jt('rv-long', 'LONG', 7000.00, 7005.00, '10:00', '10:05'),
                    jt('rv-short', 'SHORT', 7005.00, 7003.00, '10:05', '10:08')],
         'rows': [], 'flags': 0, 'fees': {'rv-long': 1.90, 'rv-short': 1.90}},
        {'name': 'pdf-reversal-empty', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 1, 7000.00), ('10:05:00', 'S', 2, 7005.00),
                           ('10:08:00', 'B', 1, 7003.00)], 3.80),
         'trades': [], 'rows': [('LONG', 7000.00, '10:00', 1.90), ('SHORT', 7005.00, '10:05', 1.90)],
         'flags': 0, 'fees': {}},
        {'name': 'pdf-missing-hour-neighbour', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 1, 6604.75), ('10:00:40', 'S', 1, 6605.00),
                           ('11:00:05', 'B', 1, 6604.75), ('11:00:40', 'S', 1, 6605.00)], 3.80),
         'trades': [jt('nb-11', 'LONG', 6604.75, 6605.00, '11:00', '11:00')],
         'rows': [('LONG', 6604.75, '10:00', 1.90)], 'flags': 0, 'fees': {'nb-11': 1.90}},
        {'name': 'pdf-missing-minute-neighbour', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 1, 7000.00), ('10:00:50', 'S', 1, 7001.25),
                           ('10:01:10', 'B', 1, 7000.25), ('10:01:40', 'S', 1, 7001.00)], 3.80),
         'trades': [jt('mn-2', 'LONG', 7000.25, 7001.00, '10:01', '10:01')],
         'rows': [('LONG', 7000.00, '10:00', 1.90)], 'flags': 0, 'fees': {'mn-2': 1.90}},
        {'name': 'pdf-untimed-copy-first', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 1, 7000.00), ('10:02:05', 'S', 1, 7002.00),
                           ('11:30:05', 'B', 1, 7000.00), ('11:32:05', 'S', 1, 7002.00)], 3.80),
         'trades': [jt('ut-none', 'LONG', 7000.00, 7002.00, None, None),
                    jt('ut-10', 'LONG', 7000.00, 7002.00, '10:00', '10:02')],
         'rows': [], 'flags': 0, 'fees': {'ut-none': 1.90, 'ut-10': 1.90}},
        {'name': 'pdf-drift-next-to-neighbour', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 1, 7000.00), ('10:01:30', 'S', 1, 7002.00),
                           ('10:02:05', 'B', 1, 7000.00), ('10:03:30', 'S', 1, 7002.00)], 3.80),
         'trades': [jt('sd-1', 'LONG', 7000.00, 7002.00, '13:00', '13:01'),
                    jt('sd-2', 'LONG', 7000.00, 7002.00, '10:02', '10:03')],
         'rows': [], 'flags': 0, 'fees': {'sd-1': 1.90, 'sd-2': 1.90}, 'drift': ['sd-1']},
        {'name': 'pdf-two-lot-and-one-lot', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 2, 7000.00), ('10:00:30', 'S', 2, 7002.00),
                           ('10:00:40', 'B', 1, 7000.00), ('10:00:55', 'S', 1, 7002.00)], 5.70),
         'trades': [jt('one', 'LONG', 7000.00, 7002.00, '10:00', '10:00'),
                    jt('two', 'LONG', 7000.00, 7002.00, '10:00', '10:00', size=2)],
         'rows': [], 'flags': 0, 'fees': {'one': 1.90, 'two': 3.80}},
        {'name': 'pdf-clearing-two-symbols', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_two_symbols(),
         'trades': [jt('cl-mes', 'LONG', 7000.00, 7002.00, '10:00', '10:02', fees=1.90),
                    jt('cl-mnq', 'LONG', 26000.00, 26010.00, '11:00', '11:02', fees=1.90, symbol='MNQ')],
         'rows': [], 'flags': 0, 'fees': {}},
        {'name': 'pdf-day-not-all-accounted', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('19:00:05', 'B', 1, 6990.00, '04/20/2026'), ('19:02:05', 'S', 1, 6991.00, '04/20/2026'),
                           ('10:00:05', 'B', 1, 7000.00), ('10:02:05', 'S', 1, 7002.00)], 3.80),
         'trades': [jt('rth', 'LONG', 7000.00, 7002.00, '10:00', '10:02')],
         'rows': [('LONG', 6990.00, '19:00', 1.90)], 'flags': 0, 'fees': {}},
        # --- review round 2: roll day, pass-3 ownership, drift per scale-out leg ---
        {'name': 'pdf-roll-day-journal', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_roll(),
         'trades': [jt('roll-m', 'LONG', 7000.00, 7002.00, '10:00', '10:05'),
                    jt('roll-u', 'SHORT', 7050.00, 7048.00, '10:01', '10:06')],
         'rows': [], 'flags': 0, 'fees': {'roll-m': 1.90, 'roll-u': 1.90}},
        {'name': 'pdf-roll-day-empty', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_roll(), 'trades': [],
         'rows': [('LONG', 7000.00, '10:00', 1.90), ('SHORT', 7050.00, '10:01', 1.90)], 'flags': 0, 'fees': {}},
        {'name': 'pdf-missing-before-short-part', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 1, 7000.00), ('10:00:40', 'S', 1, 7002.00),
                           ('10:00:50', 'S', 2, 7002.00), ('10:01:10', 'B', 1, 7000.00),
                           ('10:01:30', 'B', 1, 7000.25)], 5.70),
         'trades': [jt('sp-1', 'SHORT', 7002.00, 7000.00, '10:00', '10:01')],
         'rows': [('LONG', 7000.00, '10:00', 1.90)], 'flags': 1, 'fees': {}},
        {'name': 'pdf-missing-before-long-part', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'S', 1, 7000.00), ('10:00:40', 'B', 1, 6999.00),
                           ('10:01:00', 'B', 2, 6999.25), ('10:01:30', 'S', 2, 7000.25)], 5.70),
         'trades': [jt('lp-1', 'LONG', 6999.25, 7000.25, '10:01', '10:01')],
         'rows': [('SHORT', 7000.00, '10:00', 1.90)], 'flags': 1, 'fees': {}},
        {'name': 'pdf-untimed-part-far', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 1, 7000.00), ('10:00:40', 'S', 1, 7002.00),
                           ('14:00:05', 'S', 2, 7002.00), ('14:02:05', 'B', 2, 7000.00)], 5.70),
         'trades': [jt('uf-1', 'SHORT', 7002.00, 7000.00, None, None)],
         'rows': [('LONG', 7000.00, '10:00', 1.90)], 'flags': 1, 'fees': {}},
        {'name': 'pdf-one-copy-two-trades', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 1, 7000.00), ('10:00:20', 'S', 1, 7002.00),
                           ('10:00:30', 'B', 1, 7000.00), ('10:00:50', 'S', 1, 7002.00)], 3.80),
         'trades': [jt('oc-2', 'LONG', 7000.00, 7002.00, '10:00', '10:00', size=2)],
         'rows': [], 'flags': 2, 'fees': {}},
        {'name': 'pdf-scaleout-legs-3h-late', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 2, 7000.00), ('10:05:10', 'S', 1, 7002.00),
                           ('10:40:20', 'S', 1, 7004.00)], 3.80),
         'trades': [jt('sl-a', 'LONG', 7000.00, 7002.00, '13:00', '13:05'),
                    jt('sl-b', 'LONG', 7000.00, 7004.00, '13:00', '13:40')],
         'rows': [], 'flags': 0, 'fees': {'sl-a': 1.90, 'sl-b': 1.90}, 'drift': ['sl-a', 'sl-b']},
        # --- review round 3: New York midnight, carried / open positions, same-minute scale-outs ---
        {'name': 'pdf-across-midnight', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('23:55:00', 'B', 1, 7000.00, '04/20/2026'), ('00:05:00', 'S', 1, 7003.00),
                           ('09:35:00', 'B', 1, 7010.00), ('09:40:00', 'S', 1, 7012.00)], 3.80, flat=True),
         'trades': [jt('mid-20', 'LONG', 7000.00, 7003.00, '23:55', '00:05', date='2026-04-20'),
                    jt('mid-21', 'LONG', 7010.00, 7012.00, '09:35', '09:40')],
         'rows': [], 'flags': 0, 'fees': {}},
        {'name': 'pdf-across-midnight-empty', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('23:55:00', 'B', 1, 7000.00, '04/20/2026'), ('00:05:00', 'S', 1, 7003.00),
                           ('09:35:00', 'B', 1, 7010.00), ('09:40:00', 'S', 1, 7012.00)], 3.80, flat=True),
         'trades': [], 'rows': [('LONG', 7000.00, '23:55', 1.90), ('LONG', 7010.00, '09:35', 1.90)],
         'flags': 0, 'fees': {}},
        {'name': 'pdf-carried-in', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('09:31:00', 'S', 1, 7005.00), ('09:35:00', 'B', 1, 7010.00),
                           ('09:40:00', 'S', 1, 7012.00)], 2.85, flat=True),
         'trades': [], 'rows': [('LONG', 7010.00, '09:35', 1.90)], 'flags': 0, 'fees': {}, 'open': 1},
        # not flat at the end and its open position unread: the start is unknown (this could as well be long 1
        # carried in, making 09:35-09:40 no round trip at all), so every fill is listed and nothing is made
        {'name': 'pdf-still-open', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('09:35:00', 'B', 1, 7010.00), ('09:40:00', 'S', 1, 7012.00),
                           ('15:50:00', 'B', 1, 7020.00)], 2.85, flat=False),
         'trades': [], 'rows': [], 'flags': 0, 'fees': {}, 'open': 3},
        {'name': 'pdf-same-minute-scale-then-one', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:13', 'B', 2, 7000.25), ('10:00:26', 'S', 1, 7002.00), ('10:00:29', 'S', 1, 7000.50),
                           ('10:00:50', 'B', 1, 7000.25), ('10:00:53', 'S', 1, 7001.25)], 5.70),
         'trades': [jt('so-a', 'LONG', 7000.25, 7002.00, '10:00', '10:00'),
                    jt('so-b', 'LONG', 7000.25, 7000.50, '10:00', '10:00'),
                    jt('re-1', 'LONG', 7000.25, 7001.25, '10:00', '10:00')],
         'rows': [], 'flags': 0, 'fees': {'so-a': 1.90, 'so-b': 1.90, 're-1': 1.90}},
        {'name': 'pdf-same-minute-two-scaleouts', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 2, 7000.00), ('10:00:15', 'S', 1, 7001.00), ('10:00:25', 'S', 1, 7003.00),
                           ('10:00:35', 'B', 2, 7000.00), ('10:00:45', 'S', 1, 7002.00), ('10:00:55', 'S', 1, 7002.25)], 7.60),
         'trades': [jt('a1', 'LONG', 7000.00, 7001.00, '10:00', '10:00'), jt('a2', 'LONG', 7000.00, 7003.00, '10:00', '10:00'),
                    jt('b1', 'LONG', 7000.00, 7002.00, '10:00', '10:00'), jt('b2', 'LONG', 7000.00, 7002.25, '10:00', '10:00')],
         'rows': [], 'flags': 0, 'fees': {'a1': 1.90, 'a2': 1.90, 'b1': 1.90, 'b2': 1.90}},
        {'name': 'pdf-averaged-row-on-a-fill-price', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 3, 7000.00), ('10:00:20', 'S', 1, 7001.75),
                           ('10:00:40', 'S', 1, 7002.00), ('10:00:55', 'S', 1, 7002.25)], 5.70),
         'trades': [jt('nt3', 'LONG', 7000.00, 7002.00, '10:00', '10:00', size=3)],
         'rows': [], 'flags': 0, 'fees': {'nt3': 5.70}},
        {'name': 'pdf-missing-one-lot-before-its-twin-leg', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:17:05', 'B', 1, 7000.25), ('10:17:15', 'S', 1, 7001.25),
                           ('10:17:30', 'B', 2, 7000.25), ('10:17:40', 'S', 1, 7000.50), ('10:17:55', 'S', 1, 7001.25)], 5.70),
         'trades': [jt('tw-1', 'LONG', 7000.25, 7000.50, '10:17', '10:17'),
                    jt('tw-2', 'LONG', 7000.25, 7001.25, '10:17', '10:17')],
         'rows': [('LONG', 7000.25, '10:17', 1.90)], 'flags': 0, 'fees': {'tw-1': 1.90, 'tw-2': 1.90}},
        {'name': 'pdf-averaged-rows-same-minute', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'S', 1, 7001.00), ('10:00:15', 'S', 1, 7000.50), ('10:00:25', 'S', 1, 7000.50),
                           ('10:00:35', 'B', 2, 6999.75), ('10:00:50', 'B', 1, 6998.75),
                           ('10:00:55', 'S', 3, 7001.00), ('10:01:05', 'B', 1, 6999.25), ('10:01:20', 'B', 2, 7000.00)], 11.40),
         'trades': [jt('av-a', 'SHORT', 7000.6667, 6999.4167, '10:00', '10:00', size=3),
                    jt('av-b', 'SHORT', 7001.00, 6999.75, '10:00', '10:01', size=3)],
         'rows': [], 'flags': 0, 'fees': {'av-a': 5.70, 'av-b': 5.70}},
        # --- review 2026-09-30 (#3 #8 #13 #14) ---
        # #3: long carried in, closed 09:31, a long 09:35-09:40, a long opened 15:50 and held. The fills net to zero,
        # and pairing from flat made two SHORTs that never happened. Not flat at the end -> listed, never paired.
        {'name': 'pdf-carried-and-open', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('09:31:00', 'S', 1, 7005.00), ('09:35:00', 'B', 1, 7010.00),
                           ('09:40:00', 'S', 1, 7012.00), ('15:50:00', 'B', 1, 7020.00)], 3.80, flat=False),
         'trades': [jt('co-long', 'LONG', 7010.00, 7012.00, '09:35', '09:40')],
         'rows': [], 'flags': 0, 'fees': {}, 'open': 4},
        # #8: a 1-lot (q) next to a 2-lot scale-out (p); the journal holds q exactly and one of p's two legs. q keeps
        # its exact copy (it used to be taken by p and q re-created as a duplicate); p is reported as another size.
        {'name': 'pdf-leg-steal', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 1, 7000.00), ('10:00:20', 'S', 1, 7002.00),
                           ('10:00:30', 'B', 2, 7000.00), ('10:00:40', 'S', 1, 7001.75), ('10:00:50', 'S', 1, 7002.25)], 5.70),
         'trades': [jt('j1-q', 'LONG', 7000.00, 7002.00, '10:00', '10:00'),
                    jt('j2-pleg', 'LONG', 7000.00, 7001.75, '10:00', '10:00')],
         'rows': [], 'flags': 1, 'fees': {'j1-q': 1.90}},
        {'name': 'pdf-leg-steal-wide-exit', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 1, 7000.00), ('10:00:20', 'S', 1, 7002.00),
                           ('10:00:30', 'B', 2, 7000.00), ('10:00:40', 'S', 1, 7001.75), ('10:00:50', 'S', 1, 7010.00)], 5.70),
         'trades': [jt('j1-q', 'LONG', 7000.00, 7002.00, '10:00', '10:00'),
                    jt('j2-pleg', 'LONG', 7000.00, 7001.75, '10:00', '10:00')],
         'rows': [], 'flags': 1, 'fees': {'j1-q': 1.90}},
        # #13: a created trade carries the statement's account, so saving it with a different Settings account
        # (commitImport stamps that only on a row with no account) and importing again creates nothing
        {'name': 'pdf-reimport-other-settings-account', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 1, 7000.00), ('10:02:05', 'S', 1, 7002.00)], 1.90),
         'trades': [], 'rows': [('LONG', 7000.00, '10:00', 1.90)], 'flags': 0, 'fees': {},
         'acct': '1810769', 'reimport': {'settings_acct': '1676735'}},
        # #14: Micro Russell is $5 a point (it was priced as a stock, $1 a point); a contract with no known size is
        # listed, never priced
        {'name': 'pdf-m2k', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 1, 2200.00), ('10:02:05', 'S', 1, 2210.00)], 1.90,
                          code='M2KZ6', name='Micro E-mini Russell 2000 - Dec. 2026'),
         'trades': [], 'rows': [('LONG', 2200.00, '10:00', 1.90)], 'flags': 0, 'fees': {},
         'sym': 'M2K', 'gross': {2200.00: 50.00}},
        {'name': 'pdf-no-contract-size', 'kind': 'pdf', 'opts': {'tz': 'auto'}, 'expect': 'recon',
         'lines': pdf_day([('10:00:05', 'B', 1, 90000.00), ('10:02:05', 'S', 1, 90500.00)], 1.90,
                          code='XYZZ6', name='Probe contract with no size - Dec. 2026'),
         'trades': [], 'rows': [], 'flags': 0, 'fees': {}, 'open': 2},
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
        if(c.kind==='roots'){r.roots=c.inputs.map(function(s){try{return w.futRoot(s);}catch(e){return 'ERR '+e;}});out.cases[c.name]=r;continue;}
        var res;
        if(c.kind==='pdf'){fakePdf(w,c.lines);
          res=await w.importPDF(new w.File([new Uint8Array([37,80,68,70])],'probe.pdf',{type:'application/pdf'}),c.opts);}
        else res=w.importCSV(c.text,c.name+'.csv',c.opts);
        r.type=res.type;
        r.rows=(res.batch||[]).map(function(t){return {date:t.date,sym:t.symbol,dir:t.type,entry:t.entry,exit:t.exit,e:t.entryTime,x:t.exitTime,fees:t.fees,gross:t.grossPnl,acct:t.account||null};});
        r.ask=res.tzAsk?{why:res.tzAsk.why}:null;
        r.note=res.tzNote?{how:res.tzNote.how,tz:res.tzNote.tz}:null;
        r.drift=(res.tzDrift||[]).map(function(d){return {id:d.id,hours:d.hours};});
        r.merges=(res.merges||[]).map(function(m){return m.updates;});
        r.feeUps=(res.feeUpdates||[]).map(function(f){return {id:f.id,fees:f.fees};});
        r.flags=(res.pdfFlags||[]).length;
        r.open=(res.pdfOpen||[]).length;
        // the import result box must render what was listed (it is only drawn after a real drop)
        if(r.open)r.openHtml=typeof w._impPdfOpenHtml==='function'?String(w._impPdfOpenHtml(res.pdfOpen)).length:0;
        r.fills=res.fillUTC?Object.keys(res.fillUTC).length:null;
        if(c.reimport){
          // save the created rows the way commitImport does (the Settings account only on a row with none),
          // then import the same statement again
          var saved=(res.batch||[]).map(function(t,k){var s=Object.assign({id:'reimport-'+k},t);if(!s.account)s.account=c.reimport.settings_acct;return s;});
          w.eval('trades='+JSON.stringify(saved)+';');fakePdf(w,c.lines);
          var res2=await w.importPDF(new w.File([new Uint8Array([37,80,68,70])],'probe.pdf',{type:'application/pdf'}),c.opts);
          r.re={rows:(res2.batch||[]).length,flags:(res2.pdfFlags||[]).length,open:(res2.pdfOpen||[]).length};
        }
      }catch(e){r.err=String(e&&e.stack?e.stack:e);}
      out.cases[c.name]=r;
    }
    try{w.eval('trades=[];');}catch(_){}
    finish('done');
  }
  document.getElementById('f').addEventListener('load',function(){setTimeout(function(){run().catch(function(e){out.err=String(e);finish('threw');});},2500);});
  setTimeout(function(){finish('backstop');},58000);
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
        if exp == 'roots':
            got_roots = r.get('roots') or []
            if got_roots and all(str(g).startswith('ERR') for g in got_roots):
                fails.append('%s: the contract-root helper is missing or throws -- %s' % (nm, got_roots[0][:120]))
                continue
            for inp, g in zip(c['inputs'], got_roots):
                if g != ROOTS[inp]:
                    fails.append('%s: %r saved as symbol %r, expected %r' % (nm, inp, g, ROOTS[inp]))
            if len(got_roots) != len(c['inputs']):
                fails.append('%s: %d of %d codes answered' % (nm, len(got_roots), len(c['inputs'])))
            continue
        if exp == 'pdfmerge':
            rows = r.get('rows') or []
            dup = [x for x in rows if x['date'] == c['skip_date']]
            if dup:
                fails.append('%s: the statement re-created %s %s, a day the journal already holds as MES '
                             '(saved again as %s)' % (nm, c['skip_date'], dup[0]['dir'], dup[0]['sym']))
            if len(rows) != c['n']:
                fails.append('%s: %d trade(s) created for the other days, expected %d' % (nm, len(rows), c['n']))
            continue
        if exp == 'recon':
            rows = r.get('rows') or []
            got_rows = sorted((x['dir'], round(float(x['entry']), 2), x['e'], round(float(x.get('fees') or 0), 2))
                              for x in rows)
            want_rows = sorted((d, round(e, 2), hm, round(f, 2)) for d, e, hm, f in c['rows'])
            if got_rows != want_rows:
                fails.append('%s: created %s, expected %s' % (nm, got_rows or 'nothing', want_rows or 'nothing'))
            want_sym = c.get('sym')
            bad = [x for x in rows if (x['sym'] != want_sym if want_sym else x['sym'] not in ('MES', 'MNQ'))]
            if bad:
                fails.append('%s: created trades saved as symbol %s, expected %s' % (nm, bad[0]['sym'], want_sym or 'MES'))
            for px, g in (c.get('gross') or {}).items():
                hit = [x for x in rows if abs(float(x['entry']) - px) < 1e-6]
                if hit and round(float(hit[0].get('gross') or 0), 2) != round(g, 2):
                    fails.append('%s: the %s trade from %s saved gross $%s, expected $%.2f (its contract size)'
                                 % (nm, hit[0]['sym'], px, hit[0].get('gross'), g))
            if c.get('acct'):
                off = [x for x in rows if x.get('acct') != c['acct']]
                if off:
                    fails.append('%s: a created trade carries account %s, expected the statement account %s'
                                 % (nm, off[0].get('acct'), c['acct']))
            if c.get('reimport'):
                re_ = r.get('re') or {}
                if re_.get('rows') or re_.get('flags') or 're' not in r:
                    fails.append('%s: importing the statement again (trades saved with Settings account %s) created %s '
                                 'and flagged %s, expected nothing' % (nm, c['reimport']['settings_acct'],
                                                                      re_.get('rows'), re_.get('flags')))
            if r.get('open') and not r.get('openHtml'):
                fails.append('%s: the import result box did not render the %d listed item(s)' % (nm, r['open']))
            if r.get('merges'):
                fails.append('%s: the statement REWROTE journal trades %s -- it may only add or report'
                             % (nm, r['merges'][:3]))
            if (r.get('flags') or 0) != c['flags']:
                fails.append('%s: %s statement/journal mismatch(es) reported, expected %d'
                             % (nm, r.get('flags'), c['flags']))
            fu = dict((f['id'], round(float(f['fees']), 2)) for f in (r.get('feeUps') or []))
            if fu != c['fees']:
                fails.append('%s: journal fee updates %s, expected %s (the statement fee per contract x size)'
                             % (nm, fu or 'none', c['fees'] or 'none'))
            if (r.get('open') or 0) != c.get('open', 0):
                fails.append('%s: %s position(s) reported as only partly on the statement, expected %d'
                             % (nm, r.get('open'), c.get('open', 0)))
            want_d = sorted(c.get('drift') or [])
            got_d = sorted(d.get('id') for d in (r.get('drift') or []))
            if got_d != want_d:
                fails.append('%s: drift flagged on %s, expected %s' % (nm, got_d or 'nothing', want_d or 'nothing'))
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
            if (x['e'], x['x'], x['dir']) != want[:3]:
                fails.append('%s: %s %s %s saved %s-%s, true New York time is %s-%s'
                             % (nm, x['date'], x['sym'], x['dir'], x['e'], x['x'], want[0], want[1]))
            if x['sym'] != want[3]:
                fails.append('%s: %s %s saved as symbol %s, expected %s' % (nm, x['date'], x['dir'], x['sym'], want[3]))
            if c.get('fees') and not (x.get('fees') or 0) > 0:
                fails.append('%s: %s %s got no fee from the statement summary (fees=%s)'
                             % (nm, x['date'], x['sym'], x.get('fees')))
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
             '--virtual-time-budget=60000', '--dump-dom',
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
    try:   # any Chrome this run starts dies with it, however the run ends (tools/kill_on_exit.py)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import kill_on_exit
        kill_on_exit.install()
    except Exception:
        pass
    sys.exit(main())
