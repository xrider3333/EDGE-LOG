#!/usr/bin/env python3
"""
tools/webull_board_probe.py -- render gate for LEDGER > WEBULL PAPER (augurSub 'qqqpaper').

WHY THIS EXISTS
---------------
tools/home_render_probe.py gates REAL's LEDGER board on every ship that touches index.html. The
WEBULL PAPER board moved onto the same shared parts (hero + range pills in step 4, the shared
equity chart in step 5) but its only probe, tools/qqq_overview_probe.py, is a long hand-run
verification tool, not a gate. This is the per-board render probe the LEDGER adoption contract
asks for (SHARED_PARTS_CONTRACT.md section 5, LEDGER_UNIFY_SCOPE.md appendix B), short enough for
`wt.py ship`, wired in exactly as REAL's is.

WHAT IT DOES
------------
Serves the repo over loopback, loads index.html in an iframe the way the HOME gate does, waits
for the signed-out screen and keeps it off the page, then hands the board a fixed copy of the
box's status doc (tools/fixtures/qqq_exec_box1005.json: the box's own _build_doc output on
2026-10-05 from a read-only copy of its files, account ids scrubbed; 47 trades from 2026-09-03,
data-caveat days, the NOISE #304 -> #382 run change, ENGU-Q flat since 2026-09-28). Nothing
touches the network or Firestore.

Cases: laptop 1366x768 | phone 375x812, x dark | mono, each a fresh render on ALL. Then one
interaction run on the laptop (Retired group open / close, a chart scrub writing the hero and
putting it back, a legend switch remembered), the FRESHNESS variants below, and one render with
?oldboards=1. The page's clock is pinned (window.__qbNowMs) so the fixed doc is judged the same
way on every run: the plain cases see it 24 s after it was written, in the session.

FRESHNESS variants (laptop, dark; sweep 2026-10-05 findings 8, 9, 20-24), each the fixture with
a few fields moved and the clock pinned: fresh in the session; 5 minutes old in the session;
Saturday noon with Friday's 15:58 doc; Monday 08:50 before the open with Friday's doc; a quiet
evening doc 6 minutes old (must NOT read silent); a quiet Saturday doc written after Friday's
close (not silent, but its today figures are Friday's); a weekend wedge (Saturday 17:11 doc on
Sunday, with the box's promised 10-minute cadence); KEEL 4 sessions old; publish failures and a
75 s stall; a gap before the latest save with no failed-save event (UPDATES PAUSED, never
UPDATES FAILING); orders halted; Monday 09:30:30 with Friday's doc (the 90 s after the open must
not hide a frozen doc); Monday 09:31 with a 09:25 doc (the 90 s grace after the open holds);
Friday's doc seen Monday 08:50 with the book armed (PAPER, lease ok) and the System section open
(neither Orders view may still say PAPER / Sending orders); and the same doc on a page whose own
read failed (the top chip blames the page, not the box). Third pass (review 2026-10-05): saves
still failing after the box's 10-minute publish_down event (the page remembers the count going
up); KEEL one session behind on Saturday (the rebuild did not land) and on Monday at 17:00 (the
rebuild is still to come); Tuesday 08:00 before the open with the last session's 75 s stall
(never 'TODAY'); and HOME with Friday's doc on Saturday, laptop and phone (the top bar WEBULL
chip must read STALE away from the board). Fourth pass (review 2026-10-05): the doc listener is
the BOARD's only again (it must not want to run on HOME, and must on the board), so away from the
board the top chip judges its copy as of the page's last check and says 'checked HH:MM' (HOME
checked 30 min ago on a fresh doc: FLAT, never STALE; a .get() landing on HOME redraws the chip in
place); a page that comes back hours later with a higher failed-save count, and a cached first
copy, never raise UPDATES FAILING; Monday 08:50 with a Saturday 17:11 doc and no promised cadence
reads silent; a pause whose last good save was on an earlier day leaves its length out; this
page's own read failure reads THIS PAGE CANNOT READ in the hero and strip, never BOX SILENT; an
open position (WEBULL 1 OPEN, leg pill in colour) and the same position on a silent box (leg pill
grey); a blocked book (WEBULL BLOCKED); Thanksgiving noon with a fresh doc (market closed, not
silent); the 30 s freshness timer exists and its body, run with the clock 5 min on and no new
doc, turns the chip and the hero silent; and the calendar (Thanksgiving closed, the day after a
13:00 close, Friday 2027-12-31 open). The top chip must be drawn, visible, inside the viewport
and not covered, in every case. The
System LAST TICK verdict is read on the quiet evening (fresh) and the armed Monday (stale), and
the box's own NOT READY flag must be greyed on every silent doc. Each asserts the hero's freshness chips
(BOX SILENT / KEEL / UPDATES FAILING / UPDATES PAUSED / BOX STALLED), the status strip, the
hero's today word, the daily-stop caption, the orders header, the leg's TODAY label, the dimming
of every figure from an earlier day, the Account 'as of' + STALE + the dated change + the grey
reconcile line, the NOISE KEEL sentence, the Orders pill, and the top bar WEBULL chip.
Sixth pass (review 2026-10-05): one failed save (a publish_down event with a count of 1, or a rise
of 1 between two saves) never raises UPDATES FAILING; KEEL counts only closed sessions (Monday 08:00
on Thursday's data is 1 session old; Monday in the session on Tuesday's data is 3) and a missed
rebuild raises its chip on Saturday; a cached listener snapshot after a read error still reads THIS
PAGE CANNOT READ; a page shown again away from the board reads at most once per 5 min (30 s on the
board); an open position on a silent box says 'last seen $600.52 at 10:03', never 'now', with its
Open and UNREALIZED figures grey; and three key variants again in MONO at 390x844 (Saturday with
Friday's doc, the page's own failed read, the open position on a silent box). Every variant: no
NaN / undefined / [object Object] on the page, and a phone variant does not scroll sideways.

WHAT IT ASSERTS
---------------
Per case:
  * renderApp returned, no uncaught exception, unhandled rejection or console.error
  * the hero ids are there and the big number reads as money; the pills read TODAY 1W 1M 3M YTD ALL
  * the shared chart is drawn at >= 200 px on the laptop and >= 150 px on the phone, with
    >= 2 [data-lgdate] and >= 2 [data-lgtick], [data-lgband] (caveat days) and [data-lgmark]
    (the run change, named with its family), the three strategy lines ORB #314 / ENGU-Q #335 /
    NOISE #382 in the legend with 16 px icons, and the caveat / book-only key under it
  * the Retired group is there, collapsed by default, says 'flat since 2026-09-28', and only
    ORB and NOISE are live rows
  * every trade row names family + run number ('NOISE #382'), never a bare 'ENGUQ' / 'ORB', and the
    run is the one that took the trade (counts per name match the fixture: NOISE #304 / #382 ...)
  * the three faint lines carry three different dashes (MONO turns every colour grey)
  * on a phone the page does not scroll sideways
  * no BOX SILENT chip on the fresh doc, and the top bar carries the WEBULL chip (FLAT)
Interaction run: the Retired group opens (ENGU-Q's row appears, the choice is stored) and closes;
a scrub at the left edge writes $0.00 and 'start of the range' into the hero, at the right edge
the closed P&L of record, and leaving puts the hero back; a legend switch is remembered.
?oldboards=1: the old chart is back and there is no shared chart and no Retired group.

STATS (LEDGER unify step 6, 2026-10-05): the board's own stat tiles are TRADING-LOG's shared strip now.
Every plain case: the four [data-lgstat] tiles (WIN RATE, PROFIT FACTOR, MAX DRAWDOWN, TRADES) in that
order under the chart, a percent / a ratio / a positive dollar amount / a count, each equal to a
recomputation here from the fixture (P&L of record, close day, walked in exit order), the PROFIT FACTOR
line ('$276 won · $304 lost') and the MAX DRAWDOWN line included. Nine stats cases (the ninth, the unlisted strategy leg, is described under STEPS 7 + 10) with today pinned to
2026-10-05: ALL; 1W (trades that closed on or after 09-28) on the laptop; 1W again on a 390x844 phone in
MONO with More stats open; ALL with one September loss turned into a $0 trade, which must be neither a
win nor a loss in the tiles ('1 even') and in the calendar's month '% won'; TODAY (one trade); 1M on a
375x812 phone with More stats open; TODAY with today pinned to 2026-10-06 (no trade closed yet) with More
stats open, which must still show the Account rows (equity, cash, Open exposure, Daily loss limit,
slippage) under 'No trades in this range.'; and ALL with a shadow row worth $5,000 closed today, which
must leave the tiles, More stats, the hero and the trade list unchanged (the board drops a shadow row once,
where its trade list is built). Each 'More stats open' case opens it the way a reload
does (stored '1', nothing in memory) and must draw it open; its values are checked against the fixture
(Net P&L, Max drawdown, Current streak walked in exit order, Broker made, Book figure over the same trades,
Book-only trades, Fill coverage, best and worst trade, an Average hold that is not '--'), the account's change
is named for its day ('today' on the fresh doc; the TODAY-before-the-first-exit case runs its clock at
2026-10-06 08:00, so it must read 'Account change on Mon 10-05'), under MONO no value or bar has a hue,
'No trades in this range.' keeps at least 8 px above the Account heading, and on a phone it must not scroll
sideways. Every case: the stat strip can be seen (shown, of real size) and starts under the chart, above
Account and History, and on a phone above the Strategies list. The interaction run opens and closes
the More stats fold (aria-expanded true then false, the choice stored for this viewer, Returns / Risk /
Mix / Account with the Webull rows, and on ALL every value worked out here, the current streak too). ?oldboards=1: no shared tiles,
the old Stats section is back.

LEDGER STEPS 7 + 10 (2026-10-06): the board's month calendar and its strategy list are TRADING-LOG's shared parts now
(ledgerCalendarHtml, ledgerListHtml). CALENDAR: one month over the chosen range's trades at the P&L of record on the day each
closed, so a month's total, every day's money and the week cells are recomputed here from the fixture for each case, range and
month shown (ALL, 1W, 1M, TODAY, the empty range, September after the earlier arrow, a $0 trade, a shadow row that must not
enter it); the caveat days (a tape-priced exit, a failed parity check, a book-only trade, a feed flagged invalid - that last one
needs no trade) are hatched amber with the dot; the arrows are disabled at the first and last month with trades; the fold is
open on a laptop and closed on a phone until chosen, and the fold and the month are remembered per viewer (a reload finds
them); a tap on a day scrolls the trade list to that day's newest trade and flashes it (a day whose rows are not on the page yet, because the list shows only its newest rows, draws every row
first). LIST: three groups in order, BOOK
(ORB #314, NOISE #382: family + run number from the leg definitions, the range's P&L of record, trades and win rate, the side;
no switch), Retired (ENGU-Q #335, a fold closed until opened, 'flat since 2026-09-28') and Shadow - not counted (a fold,
closed, its rows faded and never in anything above); BOOK + Retired add up to the account's range figure; a tap on a leg opens
its detail under the row. On a phone every row is one line, the status line, the list and the Account section sit under the
trade list, and the trade list starts within one viewport of the board top (mistake #12); on a laptop the list keeps the
sticky right column. The Table view carries a run number on every row too. A tap on a row's note toggle (the little i beside a run
number) shows that leg's note under the row and leaves its detail shut; a copy of the fixture whose last two ORB trades
belong to a strategy the board has no row for (375x812, both folds open) must draw an Other legs row, so BOOK + Retired +
Other legs still add up to the account's range figure; a copy with ENGU-Q long 10 (375x812 and 1366x768) has no Retired group,
ENGU-Q is a BOOK row reading LONG with its live position line, and the rows still add up. Under MONO no calendar or list value
has a hue.
?oldboards=1 keeps the old month grid and the old rows (and their old page order).

Exit codes as preflight_boot.py: 0 PASS, 1 FAIL, 2 INCONCLUSIVE (never blocks). A non-PASS
attempt is rendered once more before it blocks; a retry that passes prints a FLAKE line.

Usage:
  python tools/webull_board_probe.py                # gates this repo's index.html
  python tools/webull_board_probe.py --file X.html  # gates X as if it were index.html
  python tools/webull_board_probe.py --selftest     # deliberately broken copies (MUTANTS) must
                                                    # FAIL, then the real file must PASS

Stdlib only, plus a subprocess call to local Chrome.
"""
import argparse
import collections
import http.server
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

PASS, FAIL, INCONCLUSIVE = 0, 1, 2
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, 'tools', 'fixtures', 'qqq_exec_box1005.json')

VIEWPORTS = {'laptop': [1366, 768], 'phone': [375, 812], 'phone390': [390, 844]}
CASES = [['%s/%s' % (vp, th), {'vp': vp, 'theme': th}] for vp in ('laptop', 'phone') for th in ('dark', 'mono')]
LEDGER_RANGES = ['TODAY', '1W', '1M', '3M', 'YTD', 'ALL']
WANT_LINES = ['ORB #314', 'ENGU-Q #335', 'NOISE #382']
WANT_LIVE = ['ORB', 'NOISE']
RETIRED_SINCE = '2026-09-28'
LEG_RE = re.compile(r'^(ORB|ENGU-Q|NOISE) #\d+$')
MONEY_RE = re.compile(r'^-?\$[\d,]+\.\d\d$')
# LEDGER step 6: the shared stat tiles, in this order on every board
STAT_KEYS = ['winrate', 'pf', 'maxdd', 'trades']
STAT_TODAY = '2026-10-05'      # the stats cases pin ledgerTodayNY() to the fixture's own day
ACCOUNT_ROWS = ['Account equity', 'Cash', 'Open exposure', 'Daily loss limit', 'Broker made',
                'Book figure', 'Book-only trades', 'Fill coverage', 'Slippage vs backtest']
# the Account rows that do not depend on the range: there even when no trade closed in it
ACCOUNT_ROWS_ANY_RANGE = ['Account equity', 'Cash', 'Open exposure', 'Daily loss limit', 'Slippage vs backtest']



def et_ms(s):
    """'YYYY-MM-DD HH:MM:SS' New York time -> epoch ms, with the US daylight saving rule (second
    Sunday of March 02:00 to first Sunday of November 02:00 is UTC-4, else UTC-5). Stdlib only, no
    tz database needed."""
    import datetime as _dt
    w = _dt.datetime.strptime(s, '%Y-%m-%d %H:%M:%S')

    def nth_sunday(y, m, n):
        d = _dt.datetime(y, m, 1)
        return d + _dt.timedelta(days=(6 - d.weekday()) % 7 + 7 * (n - 1))
    start = nth_sunday(w.year, 3, 2).replace(hour=2)
    end = nth_sunday(w.year, 11, 1).replace(hour=2)
    off = -4 if start <= w < end else -5
    return int(w.replace(tzinfo=_dt.timezone(_dt.timedelta(hours=off))).timestamp() * 1000)


FRESH_NOW = '2026-10-05 10:03:30'   # 24 s after the fixture's updated_at, in the session


def _variant_docs(fixture):
    """[(name, now, doc, expect)] -- the freshness variants. expect keys: silent / keel / publish /
    tickgap = the chip text or None (absent); today = the hero today word; top = (state, text) of
    the top bar chip; strip_has / strip_lacks; stop / orders / legtoday = the day word on the
    daily-stop caption / orders header / opened NOISE leg; asof_has; eq_stale."""
    import copy

    def base(keel='2026-10-02'):
        d = copy.deepcopy(fixture)
        d['keel']['NOISE']['trained_through'] = keel
        return d

    def move_to(d, updated, day, as_of, last_ok, fails=0):
        d['updated_at'] = updated
        d['trade_ids']['day'] = day
        d['orb_resting']['day'] = day
        for o in d['today']['orders']:
            o['ts_et'] = day + o['ts_et'][10:]
        for t in d['today']['trades']:
            t['entry_ts'] = day + t['entry_ts'][10:]
            t['exit_ts'] = day + t['exit_ts'][10:]
        d['equity']['as_of_et'] = as_of
        d['health'] = {'publish_fail_today': fails, 'last_publish_ok_et': last_ok, 'tick_gap_max_s_today': 4.2}
        return d

    def fri(d):
        return move_to(d, '2026-10-02 15:58:40', '2026-10-02', '2026-10-02 15:58:10', '15:57:40')

    out = []
    none = {'silent': None, 'keel': None, 'publish': None, 'pubgap': None, 'tickgap': None, 'noread': None}
    out.append(('fresh in the session', FRESH_NOW, base(), dict(none, today='today', top=('flat', 'WEBULL FLAT'),
               strip_has=['box updated 24 s ago', 'feed OK'], strip_lacks=['BOX SILENT'], stop='today',
               orders='today', legtoday='TODAY', asof_has='as of 10:01:35', eq_stale=False, calendar=True)))
    out.append(('5 minutes old in the session', '2026-10-05 10:08:06', base(), dict(none, silent='BOX SILENT 5 min',
               today='today', top=('stale', 'WEBULL STALE 5 min'),
               strip_has=['BOX SILENT 5 min', 'last update from the box Mon 10:03'], strip_lacks=['feed OK'],
               stop='today', orders='today', legtoday='TODAY', asof_has='as of 10:01:35', eq_stale=True,
               eq_why='the box has been silent', mini_silent='Last known: OFF, as of Mon 10:03.')))
    out.append(("Saturday noon, Friday's doc", '2026-10-03 12:00:00', fri(base()), dict(none,
               silent='BOX SILENT since Fri 15:58', today='Fri 10-02', top=('stale', 'WEBULL STALE since Fri 15:58'),
               strip_has=['BOX SILENT since Fri 15:58'], strip_lacks=['feed OK'], stop='Fri 10-02',
               orders='Fri 10-02', legtoday='FRI 10-02', asof_has='as of Fri 10-02 15:58:10', eq_stale=True)))
    out.append(("Monday 08:50 before the open, Friday's doc", '2026-10-05 08:50:00', fri(base()), dict(none,
               silent='BOX SILENT since Fri 15:58', today='Fri 10-02', top=('stale', 'WEBULL STALE since Fri 15:58'),
               strip_has=['BOX SILENT since Fri 15:58'], strip_lacks=['feed OK'], stop='Fri 10-02',
               orders='Fri 10-02', legtoday='FRI 10-02', asof_has='as of Fri 10-02', eq_stale=True,
               keelline='the next session is Mon Oct 5 - up to date')))
    # KEEL rebuilt that evening (a missed rebuild would raise its own chip): only the doc's age is under test
    out.append(('quiet evening, 6 minutes old', '2026-10-05 20:41:00',
               move_to(base('2026-10-05'), '2026-10-05 20:35:00', '2026-10-05', '2026-10-05 15:59:30', '20:25:00', fails=111),
               dict(none, today='today', top=('flat', 'WEBULL FLAT'), strip_has=['box updated 6 min ago', 'feed OK'],
                    strip_lacks=['BOX SILENT'], stop='today', orders='today', legtoday='TODAY',
                    asof_has='as of 15:59:30', eq_stale=False, system=True, lasttick='ok')))
    out.append(('quiet Saturday, written after the close', '2026-10-03 12:00:00',
               move_to(base(), '2026-10-03 11:55:00', '2026-10-02', '2026-10-02 15:59:30', '11:45:00'),
               dict(none, today='Fri 10-02', top=('flat', 'WEBULL FLAT'), strip_has=['box updated 5 min ago'],
                    strip_lacks=['BOX SILENT'], stop='Fri 10-02', orders='Fri 10-02', legtoday='FRI 10-02',
                    asof_has='as of Fri 10-02 15:59:30', eq_stale=False)))
    wedge = move_to(base(), '2026-10-03 17:11:40', '2026-10-02', '2026-10-02 15:59:30', '17:01:40')
    wedge['lease']['renew_every_sec'] = 600.0
    out.append(('weekend wedge, Saturday 17:11 doc on Sunday', '2026-10-04 10:00:00', wedge, dict(none,
               silent='BOX SILENT since Sat 17:11', today='Fri 10-02', top=('stale', 'WEBULL STALE since Sat 17:11'),
               strip_has=['BOX SILENT since Sat 17:11'], strip_lacks=['feed OK'], stop='Fri 10-02',
               orders='Fri 10-02', legtoday='FRI 10-02', eq_stale=True)))
    # Monday in the session on Tuesday's data: 3 CLOSED sessions old (Wed, Thu, Fri), Monday's is under way
    out.append(("KEEL on Tuesday's data, Monday in the session", FRESH_NOW, base('2026-09-29'), dict(none,
               keel='KEEL on Sep 29 data - 3 sessions old', keelwarn='KEEL on Sep 29 data - 3 sessions old',
               keelline='the last closed session is Fri Oct 2, so it is 3 sessions behind',
               today='today', top=('flat', 'WEBULL FLAT'), strip_lacks=['BOX SILENT'], eq_stale=False)))
    pf = base()
    pf['health'] = {'publish_fail_today': 5, 'last_publish_ok_et': '10:00:41', 'tick_gap_max_s_today': 75.0}
    pf['events'] = [{'ts_et': '2026-10-05 10:02:50', 'kind': 'publish_down',
                     'text': 'Firestore publish failing (timed out after 8s) -- shadow keeps ticking, 5 failure(s) today'}] + pf['events']
    out.append(('publish failures + a 75 s stall', FRESH_NOW, pf, dict(none, publish='UPDATES FAILING (5 today)',
               tickgap='BOX STALLED 75 s TODAY', today='today', top=('flat', 'WEBULL FLAT'),
               strip_has=['saves failing (5 today)'], strip_lacks=['BOX SILENT'], eq_stale=False)))
    ht = base()
    ht['broker']['halted'] = True
    ht['broker']['halt_reason'] = 'kill file present'
    out.append(('orders halted', FRESH_NOW, ht, dict(none, today='today', top=('halted', 'WEBULL HALTED'))))
    # review fixes (2026-10-05, second pass)
    out.append(("Monday 09:30:30 just after the open, Friday's doc", '2026-10-05 09:30:30', fri(base()), dict(none,
               silent='BOX SILENT since Fri 15:58', today='Fri 10-02', top=('stale', 'WEBULL STALE since Fri 15:58'),
               strip_has=['BOX SILENT since Fri 15:58'], strip_lacks=['feed OK'], stop='Fri 10-02',
               orders='Fri 10-02', legtoday='FRI 10-02', eq_stale=True)))
    out.append(('Monday 09:31 just after the open, a 09:25 doc', '2026-10-05 09:31:00',
               move_to(base(), '2026-10-05 09:25:00', '2026-10-05', '2026-10-05 09:24:30', '09:24:40'),
               dict(none, today='today', top=('flat', 'WEBULL FLAT'), strip_has=['box updated 6 min ago', 'feed OK'],
                    strip_lacks=['BOX SILENT'], stop='today', orders='today', legtoday='TODAY')))
    armed = fri(base())
    armed['broker'].update({'effective_mode': 'PAPER', 'requested_mode': 'PAPER', 'lease_ok_to_send': True})
    out.append(("armed book, Friday's doc seen Monday 08:50 (System open)", '2026-10-05 08:50:00', armed, dict(none,
               silent='BOX SILENT since Fri 15:58', today='Fri 10-02', top=('stale', 'WEBULL STALE since Fri 15:58'),
               strip_has=['BOX SILENT since Fri 15:58'], stop='Fri 10-02', orders='Fri 10-02',
               mini_silent='Last known: PAPER, as of Fri 15:58.', ordmode='BOX SILENT', eq_stale=True,
               lasttick='stale')))
    gap = base()
    gap['health'] = {'publish_fail_today': 111, 'last_publish_ok_et': '10:00:41', 'tick_gap_max_s_today': 4.2}
    gap['events'] = [e for e in gap['events'] if e.get('kind') != 'publish_down']
    out.append(('a gap before this save, no failed-save event', FRESH_NOW, gap, dict(none, pubgap='UPDATES PAUSED 2 min',
               today='today', top=('flat', 'WEBULL FLAT'), strip_has=['updates paused 2 min before this one'],
               strip_lacks=['BOX SILENT', 'saves failing'], eq_stale=False)))
    # the page's own read failed: the hero and strip blame the page, never the box (review 4th pass)
    out.append(("the page's own read failed, Friday's doc on Monday 08:50", '2026-10-05 08:50:00', fri(base()), dict(none,
               noread='THIS PAGE CANNOT READ (copy from Fri 15:58)', today='Fri 10-02', top=('noread', 'WEBULL NO STATUS'),
               strip_has=['THIS PAGE CANNOT READ', 'its last copy is from Fri 15:58'], strip_lacks=['BOX SILENT', 'feed OK'],
               eq_stale=True, eq_why='this page cannot read', liveErr=True, system=True)))
    # review fixes (2026-10-05, third pass)
    # saves kept failing after the box's one publish_down event (it logs one per 10 min at most):
    # the event is 13.5 min old, but this page saw the count go 5 -> 7 on the 10:03:06 save
    mem_prev = base()
    mem_prev['updated_at'] = '2026-10-05 10:01:06'
    mem_prev['health'] = {'publish_fail_today': 5, 'last_publish_ok_et': '09:57:46', 'tick_gap_max_s_today': 4.2}
    mem = base()
    mem['health'] = {'publish_fail_today': 7, 'last_publish_ok_et': '10:02:46', 'tick_gap_max_s_today': 4.2}
    mem['events'] = [{'ts_et': '2026-10-05 09:50:00', 'kind': 'publish_down',
                      'text': 'Firestore publish failing (timed out after 8s) -- shadow keeps ticking, 3 failure(s) today'}] + \
        [e for e in mem['events'] if e.get('kind') != 'publish_down']
    out.append(("saves still failing after the box's 10-minute event", FRESH_NOW, mem, dict(none,
               publish='UPDATES FAILING (7 today)', today='today', top=('flat', 'WEBULL FLAT'),
               strip_has=['saves failing (7 today)'], strip_lacks=['BOX SILENT'], eq_stale=False, prev=mem_prev)))
    out.append(("quiet Saturday, KEEL missed Friday's rebuild", '2026-10-03 12:00:00',
               move_to(base('2026-10-01'), '2026-10-03 11:55:00', '2026-10-02', '2026-10-02 15:59:30', '11:45:00'),
               dict(none, today='Fri 10-02', top=('flat', 'WEBULL FLAT'), strip_lacks=['BOX SILENT'], eq_stale=False,
                    keel='KEEL on Oct 1 data - 1 session old', keelwarn='KEEL on Oct 1 data - 1 session old',
                    keelline='the latest session is Fri Oct 2, so it is 1 session behind - the last rebuild')))
    out.append(('Monday 17:00 after the close, KEEL rebuild still to come', '2026-10-05 17:00:00',
               move_to(base(), '2026-10-05 16:58:00', '2026-10-05', '2026-10-05 15:59:30', '16:57:00'),
               dict(none, today='today', top=('flat', 'WEBULL FLAT'), strip_lacks=['BOX SILENT'], eq_stale=False,
                    keelline='the latest session is Mon Oct 5 - 1 session behind until tonight')))
    pre = move_to(base('2026-10-05'), '2026-10-06 07:55:00', '2026-10-06', '2026-10-06 07:54:30', '07:45:00')
    pre['health']['tick_gap_max_s_today'] = 75.0
    out.append(("Tuesday 08:00 before the open, the last session's stall", '2026-10-06 08:00:00', pre, dict(none,
               today='today', top=('flat', 'WEBULL FLAT'), strip_lacks=['BOX SILENT'], eq_stale=False,
               keelline='the next session is Tue Oct 6 - up to date')))
    for vp in ('laptop', 'phone'):
        # a phone keeps 'checked HH:MM' in the tooltip while the check is fresh (the chip still takes a row of
        # its own in the phone top bar, 70 to 90 px, even when short: a shared top bar call, routed to TRADING-LOG)
        out.append(("HOME tab (%s), Friday's doc on Saturday" % vp, '2026-10-03 12:00:00', fri(base()), dict(none,
                   tab='home', vp=vp, top=('stale', 'WEBULL STALE since Fri 15:58' + (', checked 12:00' if vp == 'laptop' else '')))))
    # review fixes (2026-10-05, fourth pass)
    # a page back hours later the same day with a higher failed-save count: not two saves in a row
    back_prev = move_to(base(), '2026-10-05 10:00:00', '2026-10-05', '2026-10-05 09:59:30', '09:59:40', fails=0)
    back = move_to(base(), '2026-10-05 14:00:00', '2026-10-05', '2026-10-05 13:59:30', '13:59:40', fails=6)
    back['events'] = [{'ts_et': '2026-10-05 11:00:00', 'kind': 'publish_down',
                       'text': 'Firestore publish failing (timed out after 8s) -- shadow keeps ticking, 1 failure(s) today'}] + \
        [e for e in back['events'] if e.get('kind') != 'publish_down']
    out.append(('page back hours later, more failed saves since', '2026-10-05 14:00:20', back, dict(none,
               today='today', top=('flat', 'WEBULL FLAT'), strip_lacks=['saves failing', 'BOX SILENT'], eq_stale=False,
               prev=back_prev)))
    # the first copy this page saw came from the browser's cache: never a starting count
    cache_prev = base()
    cache_prev['updated_at'] = '2026-10-05 10:02:46'
    cache_prev['health'] = {'publish_fail_today': 5, 'last_publish_ok_et': '10:02:36', 'tick_gap_max_s_today': 4.2}
    out.append(('a cached first copy, then a higher count', FRESH_NOW, mem, dict(none, today='today',
               top=('flat', 'WEBULL FLAT'), strip_lacks=['saves failing'], eq_stale=False, prev=cache_prev, prev_cache=True)))
    # no promised cadence in the doc: the box's slowest rule (10 min) still catches a weekend wedge
    nocad = move_to(base(), '2026-10-03 17:11:40', '2026-10-02', '2026-10-02 15:59:30', '17:01:40')
    nocad['lease'].pop('renew_every_sec', None)
    out.append(('Monday 08:50, a Saturday 17:11 doc, no promised cadence', '2026-10-05 08:50:00', nocad, dict(none,
               silent='BOX SILENT since Sat 17:11', today='Fri 10-02', top=('stale', 'WEBULL STALE since Sat 17:11'),
               strip_has=['BOX SILENT since Sat 17:11'], strip_lacks=['feed OK'], eq_stale=True)))
    # the last good save was on an earlier day (time of day only): the pause's length is left out
    over = move_to(base(), '2026-10-05 09:35:00', '2026-10-05', '2026-10-05 09:34:30', '17:01:40', fails=3)
    over['events'] = [e for e in over['events'] if e.get('kind') != 'publish_down']
    out.append(('a pause from an earlier day (the Sat-Mon wedge)', '2026-10-05 09:35:20', over, dict(none,
               pubgap='UPDATES PAUSED', today='today', top=('flat', 'WEBULL FLAT'),
               strip_has=['updates paused since 17:01:40 before this one'], strip_lacks=['BOX SILENT'], eq_stale=False)))
    # an open position: the chip counts it; on a silent box its leg pill turns grey
    def opened(d):
        d['positions'] = {'NOISE': {'side': 'long', 'shares': '10', 'entry_px': '600.10',
                                    'entry_ts': '2026-10-05 10:00:05', 'unrealized': '4.20'}}
        d['positions_live'] = {'legs': [{'leg': 'NOISE', 'side': 'long', 'shares': 10, 'entry_px': 600.1,
                                         'live_px': 600.52, 'live_source': 'stream', 'live_age_s': 1.0,
                                         'open_pnl': 4.2, 'time_in_trade_min': 3}],
                               'total_open_pnl': 4.2, 'legs_net_qty': 10, 'broker_net_qty': 10, 'mismatch': False}
        return d
    out.append(('an open position', FRESH_NOW, opened(base()), dict(none, today='today', top=('open', 'WEBULL 1 OPEN'),
               legpill='colour', live_has='now $600.52', live_lacks='last seen', openpnl='colour', unreal='colour', eq_stale=False)))
    # silent: no current price - 'last seen ... at' the box's time, never 'now', and the open figures grey
    out.append(('an open position, box silent 5 min', '2026-10-05 10:08:06', opened(base()), dict(none,
               silent='BOX SILENT 5 min', today='today', top=('stale', 'WEBULL STALE 5 min'), legpill='grey',
               live_has='last seen $600.52 at 10:03', live_lacks=' now ', openpnl='grey', unreal='grey', eq_stale=True)))
    blk = base()
    blk['broker'].update({'effective_mode': 'PAPER', 'requested_mode': 'PAPER', 'lease_ok_to_send': False,
                          'lease_block_reason': 'lease held by another host'})
    out.append(('a blocked book', FRESH_NOW, blk, dict(none, today='today', top=('blocked', 'WEBULL BLOCKED'), eq_stale=False)))
    # a holiday is not a session: Thanksgiving noon with a doc written 5 min ago reads quiet, not silent
    out.append(('Thanksgiving noon, a fresh quiet doc', '2026-11-26 12:00:00',
               move_to(base('2026-11-25'), '2026-11-26 11:55:00', '2026-11-25', '2026-11-25 15:59:30', '11:45:00'),
               dict(none, today='Wed 11-25', top=('flat', 'WEBULL FLAT'), strip_has=['market closed', 'box updated 5 min ago'],
                    strip_lacks=['BOX SILENT', 'market open'], stop='Wed 11-25', orders='Wed 11-25', legtoday='WED 11-25',
                    asof_has='as of Wed 11-25 15:59:30', eq_stale=False,
                    keelline='the latest session is Wed Nov 25 - up to date')))
    # the 30 s timer: a page left open while the box goes quiet (finding 8). Rendered fresh, then the
    # clock moves 5 min on and only the timer's body runs - no new doc, no renderApp from the probe
    out.append(('page left open, the box goes quiet (timer)', '2026-10-05 10:08:36', base(), dict(none,
               silent='BOX SILENT 5 min', today='today', top=('stale', 'WEBULL STALE 5 min'),
               strip_has=['BOX SILENT 5 min'], eq_stale=True, tick=True, render_at=FRESH_NOW)))
    # HOME: the chip judges its copy as of the page's last check and says when that was
    out.append(('HOME tab, checked 30 min ago on a fresh doc', '2026-10-05 10:33:30', base(), dict(none,
               tab='home', vp='laptop', top=('flat', 'WEBULL FLAT, checked 10:03'), checked_at=FRESH_NOW)))
    # review fixes (2026-10-05, fifth pass)
    # 09:25 the box goes from every 10 min to every minute: the gap before the first faster save ran
    # under the 10 min rule, so a day with failed saves must not flash UPDATES PAUSED
    flash = move_to(base(), '2026-10-05 09:25:05', '2026-10-05', '2026-10-05 09:24:30', '09:16:40', fails=5)
    flash['lease']['renew_every_sec'] = 60.0
    flash['events'] = [e for e in flash['events'] if e.get('kind') != 'publish_down']
    out.append(('09:25 switch to the faster cadence, failed saves earlier today', '2026-10-05 09:25:20', flash, dict(none,
               today='today', top=('flat', 'WEBULL FLAT'), strip_lacks=['updates paused', 'BOX SILENT'], eq_stale=False)))
    # the clocks go back: a doc written at 01:30 in the repeated (winter time) hour, seen at 01:35 winter time
    dst = move_to(base('2026-10-30'), '2026-11-01 01:30:00', '2026-10-30', '2026-10-30 15:59:30', '01:20:00')
    out.append(('the repeated 01:00 hour when the clocks go back', et_ms('2026-11-01 01:35:00') + 3600000, dst, dict(none,
               today='Fri 10-30', top=('flat', 'WEBULL FLAT'), strip_has=['box updated 5 min ago'], strip_lacks=['BOX SILENT'],
               stop='Fri 10-30', orders='Fri 10-30', eq_stale=False)))
    # this device lost its own network: no listener error arrives, the copy just ages
    out.append(('this device offline, its copy 5 min old in the session', '2026-10-05 10:08:06', base(), dict(none,
               noread='THIS PAGE CANNOT READ (copy from Mon 10:03)', today='today', top=('noread', 'WEBULL NO STATUS'),
               strip_has=['THIS PAGE CANNOT READ'], strip_lacks=['BOX SILENT', 'feed OK'], eq_stale=True,
               eq_why='this page cannot read', offline=True)))
    # a HOME tab left visible overnight: the check is from yesterday and says which day
    eve = move_to(base(), '2026-10-05 19:55:00', '2026-10-05', '2026-10-05 15:59:30', '19:45:00')
    for vp in ('laptop', 'phone'):
        out.append(('HOME tab (%s) left open overnight, checked the evening before' % vp, '2026-10-06 10:00:00', eve, dict(none,
                   tab='home', vp=vp, top=('flat', 'WEBULL FLAT, checked Mon 19:56'), checked_at='2026-10-05 19:56:00')))
    # an account with no Webull paper box: no chip at all
    out.append(('HOME tab, an account with no Webull box', FRESH_NOW, base(), dict(none,
               tab='home', vp='laptop', top=None, top_hidden=True, missing=True)))
    # a phone's first read lands a stale doc away from the board: the longer chip wraps the top bar,
    # and the sticky sub-tab strip must move down with it (scrolled 600 px)
    out.append(('HOME tab (phone), the first read lands a stale doc', '2026-10-03 12:00:00', fri(base()), dict(none,
               tab='home', vp='phone', top=('stale', 'WEBULL STALE since Fri 15:58'), unloaded=True, fetch=fri(base()), pin=True)))
    halted = base()
    halted['updated_at'] = '2026-10-05 10:19:50'
    halted['broker'].update({'halted': True, 'halt_reason': 'kill file present'})
    out.append(('HOME tab, a .get() lands a halted doc', '2026-10-05 10:20:00', base(), dict(none,
               tab='home', vp='laptop', top=('halted', 'WEBULL HALTED, checked 10:20'), checked_at=FRESH_NOW,
               fetch=halted)))
    # review fixes (2026-10-05, sixth pass)
    # one failed save, logged by the box (its publish_down comes on the FIRST failure), the next save
    # worked 60 s later: a blip, not UPDATES FAILING (and a 60 s gap is not UPDATES PAUSED either)
    one = base()
    one['health'] = {'publish_fail_today': 1, 'last_publish_ok_et': '10:02:06', 'tick_gap_max_s_today': 4.2}
    one['events'] = [{'ts_et': '2026-10-05 10:02:30', 'kind': 'publish_down',
                      'text': 'Firestore publish failing (timed out after 8s) -- shadow keeps ticking, 1 failure(s) today'}] + \
        [e for e in one['events'] if e.get('kind') != 'publish_down']
    out.append(('one failed save, the box logged it', FRESH_NOW, one, dict(none, today='today', top=('flat', 'WEBULL FLAT'),
               strip_lacks=['saves failing', 'updates paused', 'BOX SILENT'], eq_stale=False)))
    # this page saw the count go 0 -> 1 between two saves in a row: also a blip
    rise_prev = base()
    rise_prev['updated_at'] = '2026-10-05 10:02:06'
    rise_prev['health'] = {'publish_fail_today': 0, 'last_publish_ok_et': '10:01:56', 'tick_gap_max_s_today': 4.2}
    rise_prev['events'] = [e for e in rise_prev['events'] if e.get('kind') != 'publish_down']
    rise1 = base()
    rise1['health'] = {'publish_fail_today': 1, 'last_publish_ok_et': '10:02:46', 'tick_gap_max_s_today': 4.2}
    rise1['events'] = [e for e in rise1['events'] if e.get('kind') != 'publish_down']
    out.append(('one failed save seen save to save', FRESH_NOW, rise1, dict(none, today='today', top=('flat', 'WEBULL FLAT'),
               strip_lacks=['saves failing'], eq_stale=False, prev=rise_prev)))
    # Monday 08:00 on Thursday's data: only Friday's rebuild was missed (1 closed session), and it is flagged
    out.append(("Monday 08:00, KEEL on Thursday's data", '2026-10-05 08:00:00',
               move_to(base('2026-10-01'), '2026-10-05 07:55:00', '2026-10-02', '2026-10-02 15:59:30', '07:45:00'),
               dict(none, today='Fri 10-02', top=('flat', 'WEBULL FLAT'), strip_lacks=['BOX SILENT'], eq_stale=False,
                    keel='KEEL on Oct 1 data - 1 session old', keelwarn='KEEL on Oct 1 data - 1 session old',
                    keelline='the last closed session is Fri Oct 2, so it is 1 session behind')))
    # the board's listener re-attaches after an error and its first snapshot is this browser's cached
    # copy: that is not a read, so the page still cannot read (it must not start blaming the box)
    out.append(('a cached listener snapshot after a read error', '2026-10-05 08:50:00', fri(base()), dict(none,
               noread='THIS PAGE CANNOT READ (copy from Fri 15:58)', today='Fri 10-02', top=('noread', 'WEBULL NO STATUS'),
               strip_has=['THIS PAGE CANNOT READ'], strip_lacks=['BOX SILENT'], eq_stale=True, liveErr=True, cachesnap=True)))
    # shown again away from the board: one read per 5 min at most there (each read is the whole doc), 30 s on the board
    out.append(('page shown again, HOME and the board', FRESH_NOW, base(), dict(none,
               tab='home', vp='laptop', top=('flat', 'WEBULL FLAT, checked 10:03'), visread=[0, 1, 1])))
    # three key variants again in MONO at 390x844
    for nm, now, doc, ex in [o for o in out if o[0] in ("Saturday noon, Friday's doc",
                                                        "the page's own read failed, Friday's doc on Monday 08:50",
                                                        'an open position, box silent 5 min')]:
        out.append((nm + ' (MONO, 390x844)', now, doc, dict(ex, vp='phone390', theme='mono')))
    return out


# Builds this gate must catch, made from the CURRENT index.html by one string replacement each.
# 'stats-below-history': the shared stat strip's line moved from under the chart to under the History section
_SB_LINES = [
    "          +(LEDGER_OLDBOARDS?'':('<div class=\"qbx-stats qbx-lgstats\">'+qbLgStatsHtml+'</div>'))",
    "          +qbMidSections",
]
_SB_ANCHOR = '\r\n'.join(_SB_LINES)
_SB_MOVED = '\r\n'.join(_SB_LINES[1:] + _SB_LINES[:1])

MUTANTS = [
    ('chart-not-drawn',
     "if(window._qbLgChart){const lgw=content.querySelector('#qb-lg-chart');if(lgw)ledgerChartRender(lgw,window._qbLgChart);}",
     '',
     'the shared chart is never drawn into its box (no error thrown)'),
    ('retired-open-by-default',
     'let qbRetOpen=!!window._qbRetiredOpen;',
     'let qbRetOpen=true;',
     'the Retired group opens by default'),
    ('bare-leg-on-rows',
     "'<span class=\"qb-trade-leg\" title=\"the strategy (family and run number) that took this trade\">'+qeTradeLegName(t)+'</span>'",
     "'<span class=\"qb-trade-leg\">'+naS(t&&t.leg)+'</span>'",
     "trade rows name the box's bare leg key again ('ENGUQ')"),
    ('caveat-days-lost',
     "bands.push({i:i,title:tip+'. These trades still count.'});",
     '',
     'the data-caveat days are no longer hatched on the chart'),
    ('scrub-leaves-hero',
     'h.big.textContent=_hmMoney(qbBase+p.v+(atNow?openMarkPnl:0));',
     '',
     'a chart scrub no longer writes the big number'),
    ('phone-overflow',
     '<div class="qbx-lgchart" id="qb-lg-chart"></div>',
     '<div class="qbx-lgchart" id="qb-lg-chart" style="min-width:640px"></div>',
     'the chart is wider than a phone and the page scrolls sideways'),
    ('wrong-run',
     "if(dg)return '#'+dg[1];",
     "if(dg)return '#999';",
     'trade rows name a run that did not take the trade (the run lookup broke)'),
    ('lines-same-dash',
     "const _LG_DASHES=['none','5 3','1.5 3','7 2 1.5 2'];",
     "const _LG_DASHES=['none','none','none','none'];",
     'the three faint lines share one dash, so MONO cannot tell them apart'),
    # freshness (sweep 2026-10-05)
    ('silent-chip-never-shown',
     "        if(QF.stale&&!qbNoRead)out.push(qbFreshChip(",
     "        if(false)out.push(qbFreshChip(",
     'a silent box never gets its BOX SILENT chip'),
    ('fetch-clock-age',
     "  const t=qbEtWallMs(QE.updated_at,nowMs);",
     "  const t=window._qqqExecFetchedAt||qbNowMs();",
     "the doc's age is measured from when the page fetched it, not when the box wrote it (finding 8)"),
    ('evening-false-alarm',
     "    r.stale=nowMs>=lc+900e3?t<lc:t<lc-90e3;",
     "    r.stale=r.ageS>90;",
     'a quiet evening doc reads silent again (the fixed 90 s rule, finding 20)'),
    ('old-day-reads-today',
     "  r.isToday=r.docDay===r.todayNY;",
     "  r.isToday=true;",
     "an earlier trading day's figures are labelled today again (finding 9)"),
    ('keel-age-ignored',
     "    const behind=qbSessionsAfter(th,r.lastSession);",
     "    const behind=0;",
     'a KEEL model 4 sessions old reads current (finding 21)'),
    ('top-chip-gone',
     "${typeof qbTopChipHtml==='function'?qbTopChipHtml():''}",
     "",
     'the top bar has no WEBULL chip (finding 23)'),
    # review fixes (second pass)
    ('open-grace-hides-frozen-doc',
     "    r.stale=(nowMs-(okAtOpen?Math.max(t,openMs):t))/1000>90;",
     "    r.stale=(nowMs-Math.max(t,openMs))/1000>90;",
     "for 90 s after the open a doc frozen since Friday reads fresh again"),
    ('no-grace-after-open',
     "    r.stale=(nowMs-(okAtOpen?Math.max(t,openMs):t))/1000>90;",
     "    r.stale=(nowMs-t)/1000>90;",
     "a healthy pre-open doc reads silent in the first 90 s after the open"),
    ('orders-summary-pill-not-silent',
     "            if(QF.stale){pillTxt=qbSilentWord;pillCol=qbNoRead?'var(--attn-amber)':'var(--attn-red)';filled=true;}",
     "",
     "the sidebar Orders pill keeps PAPER while the box is silent (finding 8)"),
    ('orders-card-not-silent',
     "if(QF.stale){sentence=(qbNoRead?",
     "if(false){sentence=(qbNoRead?",
     "the full Orders card keeps PAPER / 'Sending orders' while the box is silent (finding 8)"),
    ('past-day-not-dimmed',
     "const qbDimCss=QF.isToday?'':'opacity:.55;';",
     "const qbDimCss='';",
     "figures from an earlier trading day are no longer dimmed (finding 9)"),
    ('keel-sentence-never-behind',
     "(kf.stale?(', so it is <b>'",
     "(false?(', so it is <b>'",
     "the KEEL line never says how many sessions behind it is (finding 21)"),
    ('account-change-undated',
     "const chgDay=(",
     "const chgDay=null,chgDayWas=(",
     "the Account change reads as today's on an earlier day's doc (finding 24)"),
    ('reconcile-reads-current',
     ":(QF.stale\r\n",
     ":(false\r\n",
     "the Account reconcile line stays OK-green on a silent box"),
    ('cant-read-blames-box',
     "else if(Fnow.stale&&cantRead){",
     "else if(false){",
     "a page whose own read failed tells the owner the box is silent"),
    ('pause-chip-never-shown',
     "if(QF.pubGap)out.push(qbFreshChip(",
     "if(false)out.push(qbFreshChip(",
     "a gap in the box's saves is never shown (finding 22)"),
    # review fixes (third pass)
    ('top-chip-board-only',
     "${typeof qbTopChipHtml==='function'?qbTopChipHtml():''}",
     "${(typeof qbTopChipHtml==='function'&&activeTab==='augur'&&augurSub==='qqqpaper')?qbTopChipHtml():''}",
     'the top bar WEBULL chip is drawn only on the WEBULL PAPER board (finding 23)'),
    ('listener-always-on',
     "return !!(db&&auth&&auth.currentUser&&activeTab==='augur'&&augurSub==='qqqpaper'&&document.visibilityState==='visible');",
     "return !!(db&&auth&&auth.currentUser&&document.visibilityState==='visible');",
     'the full-doc listener runs on every tab (about 0.7 GB a day per visible device against the 10 GiB a month cap)'),
    ('fail-memory-ignored',
     "  if(PM&&PM.riseMs!=null&&PM.day===r.docDate&&nowMs-PM.riseMs<=600e3&&PM.riseMs-nowMs<=60e3)r.pubFailing=true;",
     "",
     "saves that keep failing after the box's one 10-minute event go unreported (finding 22)"),
    ('keel-missed-reads-up-to-date',
     "(kf.rebuild==='missed'?', so it is",
     "(false?', so it is",
     "KEEL one session behind after a missed rebuild says 'up to date' (finding 21)"),
    ('stall-last-session-as-today',
     "  const gapToday=r.isToday&&dp.date===np.date&&qbIsSessionDay(dp.date)&&dp.mins>=565;",
     "  const gapToday=r.isToday;",
     "before the open the last session's longest pause reads 'BOX STALLED ... TODAY' (finding 22)"),
    ('box-flags-not-greyed',
     "const qbChipG=(txt,col)=>qbChip(txt,QF.stale?'var(--text4)':col);",
     "const qbChipG=(txt,col)=>qbChip(txt,col);",
     "the box's own flags (NOT READY, BREAKER, FEED STALE) stay red / amber on a silent box (finding 8)"),
    ('system-tick-fixed-90s',
     "const tickStale=QF.ok&&QF.stale;",
     "const tickStale=QF.ok&&QF.ageS>90;",
     'System LAST TICK goes back to the fixed 90 s rule and calls a quiet evening STALE (finding 20)'),
    # review fixes (fourth pass)
    ('fail-memory-not-in-a-row',
     "if(rise>0&&inARow){",
     "if(rise>0){",
     'a page back hours later reads every failed save since as UPDATES FAILING (false alarm)'),
    ('cached-copy-counts',
     "    if(!QE||fromCache)return;",
     "    if(!QE)return;",
     "the browser's cached first copy becomes the starting count for UPDATES FAILING"),
    ('no-cadence-fallback',
     "const cadEff=(isFinite(cad)&&cad>0)?cad:600;",
     "const cadEff=(isFinite(cad)&&cad>0)?cad:1e9;",
     'a doc without its promised cadence, frozen after the close, reads fresh until the next open'),
    ('pause-length-across-days',
     "'UPDATES PAUSED'+(QF.pubGapDayUnknown?'':(' '+qbAgoText(QF.pubGap)))",
     "'UPDATES PAUSED'+(' '+qbAgoText(QF.pubGap))",
     "a pause from an earlier day shows a length the box cannot know ('16 h' after a 40 h wedge)"),
    ('board-blames-box-on-read-failure',
     "const qbNoRead=QF.ok&&QF.stale&&qbCantRead();",
     "const qbNoRead=false;",
     "the hero and strip say BOX SILENT when it is this page that cannot read"),
    ('new-year-saturday-holiday',
     "return w===6?((m===1&&d===1)?null:qbAddDays(s,-1))",
     "return w===6?(qbAddDays(s,-1))",
     'Friday Dec 31 before a Saturday New Year is treated as a holiday (NYSE is open)'),
    ('holidays-ignored',
     "if(w===0||w===6)return false;return !_qbHolidays(+s.slice(0,4))[s];}",
     "if(w===0||w===6)return false;return true;}",
     'market holidays read as sessions (Thanksgiving noon would call a quiet box silent)'),
    ('top-chip-hidden',
     "'<span id=\"qb-top-chip\" style=\"display:inline-flex;",
     "'<span id=\"qb-top-chip\" style=\"display:none;",
     'the top bar WEBULL chip is in the page but not drawn'),
    ('fresh-timer-removed',
     "window._qbFreshTimer=setInterval(qbFreshTick,30000);",
     "",
     'nothing re-judges the doc while the box is silent, so a page left open never turns stale (finding 8)'),
    ('top-chip-refresh-noop',
     "function qbTopChipRefresh(){try{const el=",
     "function qbTopChipRefresh(){return;try{const el=",
     'the top bar chip is never redrawn in place (a read landing away from the board is not shown)'),
    ('tick-no-board-redraw',
     "!==window._qbFreshDrawnKey)_qqqExecLiveRender();",
     "!==window._qbFreshDrawnKey){}",
     'the board is not redrawn when the box goes quiet with the page open (finding 8)'),
    ('top-chip-judged-now-off-board',
     "const F=live?Fnow:qbFreshness(QE,chk?Math.min(chk,nowMs):nowMs);",
     "const F=Fnow;",
     'away from the board the chip calls a copy it has not re-checked STALE (it claims more than it knows)'),
    ('leg-pill-not-greyed',
     "const badgeColor=QF.stale?'var(--text4)':(",
     "const badgeColor=false?'var(--text4)':(",
     "the strategy rows' position pills stay in colour on a silent box (finding 8)"),
    ('top-chip-always-flat',
     "txt=(nOpen>0?('WEBULL '+nOpen+' OPEN'):'WEBULL FLAT')+chkTxt",
     "txt='WEBULL FLAT'+chkTxt",
     "the top bar chip says FLAT with a position open"),
    # review fixes (fifth pass)
    ('pause-judged-by-new-cadence',
     "const cadOk=Math.max(Number(QE.lease&&QE.lease.renew_every_sec)||0,qbBoxRuleS(okMs));",
     "const cadOk=qbCadenceS(QE,okMs);",
     "the 09:25 switch to the faster cadence flashes UPDATES PAUSED on any day with a failed save"),
    ('fallback-hour-read-early',
     "if(typeof refMs==='number'&&isFinite(refMs)&&refMs-t>1800e3){",
     "if(false){",
     "a doc written in the repeated 01:00 hour in November reads an hour old (BOX SILENT for about 70 min)"),
    ('offline-blames-box',
     "try{if(typeof navigator!=='undefined'&&navigator.onLine===false)return true;}catch(e){}",
     "",
     "a viewer whose own network dropped is told the box is silent"),
    ('check-day-left-out',
     "chkOld=!!chkP&&chkP.date!==qbNyParts(nowMs).date;",
     "chkOld=false;",
     "a HOME tab left open overnight shows yesterday's check as 'checked 19:56', which reads as today"),
    ('chip-for-no-box',
     "if(!QE&&window._qqqExecMissing)return empty;",
     "",
     "an account with no Webull box gets a 'WEBULL ?' chip on every tab"),
    ('sub-strip-not-repinned',
     "if(tb&&sb&&sb.style.position==='sticky')sb.style.top=tb.offsetHeight+'px';",
     "",
     "on a phone the chip wraps the top bar after a read and the sticky sub-tab strip slides under it"),
    ('noread-pill-red',
     "if(QF.stale){pillTxt=qbSilentWord;pillCol=qbNoRead?'var(--attn-amber)':'var(--attn-red)';filled=true;}",
     "if(QF.stale){pillTxt=qbSilentWord;pillCol='var(--attn-red)';filled=true;}",
     "the Orders pill says NO STATUS in BOX SILENT's red when it is this page that cannot read"),
    ('noread-card-pill-red',
     "That may no longer be true.';pillTxt=qbSilentWord;pillCol=qbNoRead?'var(--attn-amber)':'var(--attn-red)';",
     "That may no longer be true.';pillTxt=qbSilentWord;pillCol='var(--attn-red)';",
     "the System Orders card says NO STATUS in BOX SILENT's red when it is this page that cannot read"),
    ('account-stale-blames-box',
     "const eqStaleWhy=qbNoRead?(",
     "const eqStaleWhy=false?(",
     "the Account STALE flag says the box is silent when it is this page that cannot read"),
    ('blocked-never-shown',
     "else if((mode==='PAPER'||mode==='LIVE')&&BR.lease_ok_to_send===false){st='blocked'",
     "else if(false){st='blocked'",
     'a blocked book reads FLAT in the top bar'),
    # review fixes (sixth pass)
    ('one-event-alarms',
     "r.pubFails>=2&&nowMs-lastFail",
     "nowMs-lastFail",
     "one failed save (the box logs publish_down on the first one) shows UPDATES FAILING for 10 min"),
    ('one-rise-alarms',
     ">=2)m.riseMs=t;",
     ">=1)m.riseMs=t;",
     "a failed-save count going up by 1 between two saves shows UPDATES FAILING"),
    ('keel-counts-open-session',
     "    const done=qbSessionsAfter(th,r.lastDone);",
     "    const done=behind;",
     "KEEL's age counts the session under way ('2 sessions old' on Monday morning when only Friday's rebuild was missed)"),
    ('keel-missed-no-chip',
     "warn:behind>1||rebuild==='missed',",
     "warn:behind>1,",
     "a rebuild missed on Friday evening raises no KEEL chip until Monday"),
    ('cached-snapshot-reads',
     "if(!fc){window._qqqExecFetchedAt=Date.now();window._qqqExecTriedAt=Date.now();",
     "if(true){window._qqqExecFetchedAt=Date.now();window._qqqExecTriedAt=Date.now();",
     "a cached listener snapshot after a read error clears THIS PAGE CANNOT READ, so the page blames the box"),
    ('vis-read-30s-everywhere',
     "(onBoard?30000:300000)",
     "30000",
     "every tab reads the whole doc each time the page is shown again, up to twice a minute"),
    ('live-line-says-now',
     "(QF.stale?liveLastSeen:(' · now '",
     "(false?liveLastSeen:(' · now '",
     "an open position on a silent box still says 'now' with a price the page does not have"),
    ('open-pnl-not-greyed',
     "<b data-qbopenpnl=\"'+key+'\" style=\"color:'+(QF.stale?",
     "<b data-qbopenpnl=\"'+key+'\" style=\"color:'+(false?",
     "the Open figure of a position on a silent box stays green / red"),
    ('unreal-not-greyed',
     "data-qbunreal=\"'+key+'\" style=\"font-size:14px;font-weight:600;color:'+(p?(QF.stale?",
     "data-qbunreal=\"'+key+'\" style=\"font-size:14px;font-weight:600;color:'+(p?(false?",
     "the UNREALIZED figure of a position on a silent box stays green / red"),
    # LEDGER step 6 (shared stats strip + More stats)
    ('stats-ignore-range',
     "const qbStatRows=qbRangeTrades.map(",
     "const qbStatRows=trades.map(",
     "the stat tiles count every trade whatever range is chosen"),
    ('zero-is-a-loss',
     "}else if(v<0){losses++;gl-=v;",
     "}else if(v<=0){losses++;gl-=v;",
     "a $0 trade counts as a loss in the win rate (TRADING-LOG mistake item 5)"),
    ('stats-book-pnl',
     "{pnl:qePnlOf,day:qeTradeDate,sorted:true}",
     "{pnl:t=>+t.pnl||0,day:qeTradeDate,sorted:true}",
     "the tiles add up the book's own pnl instead of the P&L of record"),
    ('more-stats-not-wired',
     "content.querySelectorAll('[data-lgmore=\"qb\"]').forEach(",
     "content.querySelectorAll('[data-lgmore=\"qb-off\"]').forEach(",
     "the More stats fold never opens"),
    # LEDGER step 6 review fixes
    ('more-stats-not-remembered',
     "const qbMoreOpen=(()=>{let o=window._qbMoreStatsOpen!=null?!!window._qbMoreStatsOpen:!!(APREF.qqqMoreStatsOpen!=null&&+APREF.qqqMoreStatsOpen);try{const sv=localStorage.getItem('el_qb_morestats_open');if(sv!=null)o=sv==='1';}catch(e){}return o;})();",
     "const qbMoreOpen=!!window._qbMoreStatsOpen;",
     "an open More stats fold is closed again after a reload"),
    ('account-gone-on-empty-range',
     "+((qbMoreOpen&&!qbLs)?qbMoreEmptyHtml():",
     "+(false?qbMoreEmptyHtml():",
     "with no trade closed in the range (TODAY before the first exit) More stats loses equity, open exposure and the loss limit"),
    ('book-figure-counts-book-only',
     "if(t.book_only)bo++;else{broker+=v;const a=qeFinRec(t.pnl),r=qeFinRec(t.real_pnl);book+=a!==null?a:(r!==null?r:0);}",
     "const a=qeFinRec(t.pnl),r=qeFinRec(t.real_pnl);book+=a!==null?a:(r!==null?r:0);if(t.book_only)bo++;else{broker+=v;}",
     "Book figure adds up the book-only trades that Broker made leaves out, so the two rows are not like for like"),
    ('shadow-on-board',
     "const trades=(QE.trades_all||[]).filter(t=>!qbIsShadowRow(t));",
     "const trades=(QE.trades_all||[]).filter(t=>true);",
     "a shadow row enters the hero, the chart, the stat tiles, More stats and the trade list"),
    ('pf-line-swapped',
     "ledgerShortMoney(s.grossWin).slice(1)+' won &middot; '+ledgerShortMoney(s.grossLoss).slice(1)+' lost'",
     "ledgerShortMoney(s.grossLoss).slice(1)+' won &middot; '+ledgerShortMoney(s.grossWin).slice(1)+' lost'",
     "the PROFIT FACTOR line swaps what was won and what was lost"),
    ('best-trade-is-worst',
     "best=Math.max.apply(null,pv)",
     "best=Math.min.apply(null,pv)",
     "More stats' best trade shows the worst one"),
    # LEDGER step 6 review fixes, round 2
    ('stats-strip-hidden',
     ".qbx-lgstats{padding:16px 0 0}",
     ".qbx-lgstats{padding:16px 0 0;display:none}",
     "the stat strip and the More stats fold are on the page but cannot be seen"),
    ('stats-below-history',
     _SB_ANCHOR,
     _SB_MOVED,
     "the stat strip is drawn under the History section (on a phone, under the whole trade list)"),
    ('stats-reverse-order',
     ".sort((a,b)=>qbTsOf(a)<qbTsOf(b)?-1:(qbTsOf(a)>qbTsOf(b)?1:0));",
     ".sort((a,b)=>qbTsOf(a)<qbTsOf(b)?1:(qbTsOf(a)>qbTsOf(b)?-1:0));",
     "the stats walk the trades newest first, so the current streak is the oldest one"),
    ('account-change-undated',
     "acct.push(['Account change '+(chgDay?('on '+chgDay):'today'),",
     "acct.push(['Account change '+(false?('on '+chgDay):'today'),",
     "More stats calls an earlier day's account change 'today'"),
    ('hold-missing',
     "Object.assign({},t,{durationMins:qbHoldMins(t)})",
     "Object.assign({},t,{durationMins:null})",
     "More stats' Average hold reads '--' with every trade's times in the doc"),
    ('mono-hue-in-fold',
     ".qbx-lgstats{padding:16px 0 0}",
     ".qbx-lgstats{padding:16px 0 0}\r\n[data-theme=mono] .qbx-lgstats .lg-ms-row .v.lg-up{color:#e33}",
     "a More stats value is drawn in a colour under MONO (MONO has no hue)"),
    ('empty-fold-no-gap',
     "'<div class=\"lg-ms-grid\" style=\"margin-top:16px\">'",
     "'<div class=\"lg-ms-grid\">'",
     "with no trade in the range, 'No trades in this range.' runs into the ACCOUNT heading"),
    # LEDGER steps 7 + 10 (shared calendar and strategy list on the board)
    ('calendar-wrong-total',
     "const qbCalDays=ledgerCalDays(qbRangeTrades,{pnl:qePnlOf,day:qeTradeDate});",
     "const qbCalDays=ledgerCalDays(qbRangeTrades,{pnl:t=>+t.pnl||0,day:qeTradeDate});",
     "the calendar adds up the book's own pnl instead of the P&L of record, so a month's total is not the sum of its trades"),
    ('calendar-ignores-range',
     "const qbCalDays=ledgerCalDays(qbRangeTrades,{pnl:qePnlOf,day:qeTradeDate});",
     "const qbCalDays=ledgerCalDays(trades,{pnl:qePnlOf,day:qeTradeDate});",
     'the calendar counts every trade whatever range is chosen'),
    ('shadow-in-calendar',
     "const qbCalDays=ledgerCalDays(qbRangeTrades,{pnl:qePnlOf,day:qeTradeDate});",
     "const qbCalDays=ledgerCalDays(qbRangeTrades.concat(qbShadowRange),{pnl:qePnlOf,day:qeTradeDate});",
     "a shadow leg's trades are added into the calendar's days and month total"),
    ('caveat-not-hatched',
     "days:qbCalDays,caveats:qbCalCav,open:qbCalOpen,",
     "days:qbCalDays,caveats:{},open:qbCalOpen,",
     'the data-caveat days are no longer hatched amber with the dot on the calendar'),
    ('caveat-feed-days-lost',
     "if(fd&&fd.valid===false&&(!cut||d>=cut))why.push(",
     "if(false&&fd&&fd.valid===false&&(!cut||d>=cut))why.push(",
     'a day whose feed was flagged invalid is no longer hatched on the calendar'),
    ('day-tap-noop',
     "const t=el||document.getElementById('qe-trades-section');",
     "const t=null;",
     'a tap on a calendar day no longer scrolls the trade list'),
    ('day-attr-missing',
     "data-qbtraderow=\"'+i+'\" data-qbday=\"'+(qeTradeDate(t)||'')+'\"'+(t.trade_id",
     "data-qbtraderow=\"'+i+'\"'+(t.trade_id",
     'the trade rows carry no day, so a calendar tap cannot land on that day'),
    ('cal-month-not-remembered',
     "try{localStorage.setItem('el_qb_cal_month',mo);}catch(e){}",
     "",
     'the month a viewer stepped to is forgotten on a reload'),
    ('cal-open-not-remembered',
     "try{localStorage.setItem('el_qb_cal_open',o?'0':'1');}catch(e){}",
     "",
     'the calendar fold opens again after a reload whatever the viewer chose'),
    ('cal-open-on-a-phone',
     "const qbCalOpen=(()=>{let o=window._qbCalOpen!=null?!!window._qbCalOpen:(window.innerWidth||1200)>=760;",
     "const qbCalOpen=(()=>{let o=window._qbCalOpen!=null?!!window._qbCalOpen:true;",
     'the calendar is open by default on a phone and pushes the rest of the page down'),
    ('cal-arrows-never-disabled',
     "const i=ms.indexOf(mo),atFirst=i<=0,atLast=i<0||i>=ms.length-1;",
     "const i=ms.indexOf(mo),atFirst=false,atLast=false;",
     'the calendar month arrows stay live past the first and last month with trades'),
    ('list-group-order',
     "[gBook,gRet,gShadow].filter(Boolean)",
     "[gRet,gBook,gShadow].filter(Boolean)",
     'the strategy list draws Retired above BOOK'),
    ('shadow-group-missing',
     "[gBook,gRet,gShadow].filter(Boolean)",
     "[gBook,gRet].filter(Boolean)",
     'the strategy list has no Shadow - not counted group'),
    ('shadow-in-list-total',
     "const fg=qbRangeFigs(qbRangeTrades.filter(t=>t.leg===key));",
     "const fg=qbRangeFigs(qbRangeTrades.concat(qbShadowRange).filter(t=>t.leg===key));",
     "a shadow leg's money is added into a BOOK row (and so into the list's total)"),
    ('row-without-run-number',
     "row:{key:key,name:label+' '+qeLegShortTag(key,runNo),",
     "row:{key:key,name:label,",
     'a strategy list row names its family but not its run number'),
    ('list-above-trades-on-phone',
     ":(qbHistSec+qbStatusSec+qbSideSec+qbAcctSec);",
     ":(qbSideSec+qbHistSec+qbStatusSec+qbAcctSec);",
     'on a phone the strategy list sits above the trade list again'),
    ('account-above-trades-on-phone',
     ":(qbHistSec+qbStatusSec+qbSideSec+qbAcctSec);",
     ":(qbAcctSec+qbHistSec+qbStatusSec+qbSideSec);",
     'on a phone the Account section sits above the trade list again'),
    ('status-above-trades-on-phone',
     ":(qbHistSec+qbStatusSec+qbSideSec+qbAcctSec);",
     ":(qbStatusSec+qbHistSec+qbSideSec+qbAcctSec);",
     'on a phone the status line sits above the trade list again, which then starts more than a screen down'),
    ('status-line-gone',
     "const qbStatusSec='<div class=\"qbx-statusline\">'+qbStatusStripHtml+'</div>';",
     "const qbStatusSec='';",
     'the status line (feed, box age, Refresh) is not on the page at all'),
    ('key-long-on-phone',
     "@media(max-width:600px){.qbx-lg-key .qbx-lg-long{display:none}.qbx-lg-key .qbx-lg-short{display:inline}}",
     "@media(max-width:600px){.qbx-lg-key .qbx-lg-short{display:none}}",
     'the chart key is four lines on a phone and the trade list starts more than a screen down'),
    ('list-has-switch',
     "value:fg.n?ledgerSigned(fg.net):'&mdash;',cls:fg.n?ledgerCls(fg.net):'',value2:qbFigsLine(fg)},",
     "value:fg.n?ledgerSigned(fg.net):'&mdash;',cls:fg.n?ledgerCls(fg.net):'',value2:qbFigsLine(fg),sw:{on:true}},",
     'the strategy list draws a switch on each row (this board has none: every leg counts)'),
    ('shadow-open-by-default',
     "let qbShadowOpen=!!window._qbShadowOpen;",
     "let qbShadowOpen=true;",
     'the Shadow - not counted group opens by default'),
    ('folds-not-remembered',
     "try{localStorage.setItem(g[1],o?'0':'1');}catch(e){}",
     "",
     'the Retired and Shadow folds do not keep the open / closed choice'),
    ('row-tap-noop',
     "if(k.charAt(0)==='~')return;   // 'Other legs' and the shadow rows have no detail to open",
     "return;",
     "a tap on a strategy row no longer opens its detail"),
    ('list-total-ignores-range',
     "count:qbRangeTrades.length?(ledgerSigned(qbRangePnl)+' &middot; '+qbRangeWord):qbRangeNone",
     "count:qbRangeTrades.length?(ledgerSigned(closedSum)+' &middot; '+qbRangeWord):qbRangeNone",
     "the list's header total is the all-time figure whatever range is chosen"),
    ('list-not-sticky',
     ".qbx-side{grid-area:side;position:sticky;top:54px;",
     ".qbx-side{grid-area:side;position:static;top:54px;",
     'on a laptop the strategy column no longer sticks while the page scrolls'),
    ('phone-row-two-lines',
     ".qbx-side .lg-row{grid-template-columns:minmax(0,1fr) auto}",
     ".qbx-side .lg-row{display:block}",
     'a strategy row is two lines tall on a phone (the money drops under the name)'),
    ('list-mono-hue',
     ".qbx-side .lg-list{margin-bottom:0}",
     ".qbx-side .lg-list{margin-bottom:0}\r\n[data-theme=mono] .qbx-side .lg-row-val{color:#e33}",
     'a strategy row draws its money in a colour under MONO (MONO has no hue)'),
    ('cal-mono-hue',
     ".qbx-side .lg-list{margin-bottom:0}",
     ".qbx-side .lg-list{margin-bottom:0}\r\n[data-theme=mono] .lg-cal-day .m{color:#e33!important}",
     'a calendar day draws its money in a colour under MONO (MONO has no hue)'),
    ('phone-calendar-overflow',
     ".qbx-side .lg-list{margin-bottom:0}",
     ".qbx-side .lg-list{margin-bottom:0}\r\n.lg-cal-panel{min-width:640px}",
     'the open calendar is wider than a phone and the page scrolls sideways'),
    # LEDGER steps 7 + 10, round 2: the note toggle and the strategy the board has no row for
    ('other-legs-row-missing',
     "if(oth.n)bookRows.push({key:'~other'",
     "if(false&&oth.n)bookRows.push({key:'~other'",
     "a strategy the board has no row for is left out of the list, which no longer adds up to the account's range figure"),
    ('info-toggle-opens-row',
     "ev.stopPropagation();\r\n        const k=el.getAttribute('data-qbleginfo');",
     "const k=el.getAttribute('data-qbleginfo');",
     "a tap on a row's note toggle also opens the row's detail"),
    ('info-toggle-noop',
     "const m=window._qbLegNoteOpen||(window._qbLegNoteOpen={});",
     "const m={};",
     "a tap on a row's note toggle shows no note"),
    ('day-tap-no-show-more',
     "if(!el&&(window._qeTradesShown||50)<1e6){window._qeTradesShown=1e6;renderApp();el=document.querySelector('[data-qbday=\"'+ds+'\"]');}",
     "",
     "a tap on a calendar day whose rows are not on the page yet (the list shows only its newest rows) lands on the top of the list"),
    ('enguq-stays-retired',
     "const qbRetiredNow=!LEDGER_OLDBOARDS&&QE_LEGS_RETIRED.indexOf(key)>=0&&!p&&!qbHeldLive&&!legTodayN;",
     "const qbRetiredNow=!LEDGER_OLDBOARDS&&QE_LEGS_RETIRED.indexOf(key)>=0&&!legTodayN;",
     "a retired leg that holds a position stays in the Retired fold instead of going back to BOOK"),
    ('retired-group-always-drawn',
     "const gRet=retModels.length?{key:'retired'",
     "const gRet=true?{key:'retired'",
     "an empty Retired group is drawn when no leg is retired"),
    ('table-day-attr-missing',
     "<tr data-qetraderow=\"'+i+'\" data-qbday=\"'+(qeTradeDate(t)||'')+'\" style=\"cursor:pointer",
     "<tr data-qetraderow=\"'+i+'\" style=\"cursor:pointer",
     "the Table view rows carry no day, so a calendar tap cannot land on them"),
]

PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>webull board probe</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html" style="width:1366px;height:768px;border:0;display:block"></iframe>
<pre id="o" style="display:none"></pre>
<script>
var CASES=__CASES__, VP=__VP__, FIX=__FIX__, NOW=__NOW__, VARS=__VARS__, STATS=__STATS__;
(function(){
  var out={cases:{},notes:[]}, reported=false, t0=Date.now(), sink=null, phase=0;
  function finish(why){
    if(reported)return; reported=true;
    out.why=why; out.ms=Date.now()-t0;
    document.getElementById('o').textContent='WEBULLPROBE: '+JSON.stringify(out);
  }
  setTimeout(function(){finish('backstop');},110000);
  var fr=document.getElementById('f');
  function W(){return fr.contentWindow;}
  function D(){return fr.contentDocument;}
  function sleep(ms){return new Promise(function(r){setTimeout(r,ms);});}
  async function waitFor(fn,ms){
    var a=Date.now();
    while(Date.now()-a<ms){var v=false;try{v=fn();}catch(_e){} if(v)return true; await sleep(40);}
    try{return !!fn();}catch(_e2){return false;}
  }
  function hook(w){
    if(w.__probeSink)return w.__probeSink;
    var s=w.__probeSink={errors:[],uncaught:[],loadErr:[]};
    var orig=w.console.error;
    w.console.error=function(){
      var p=[];for(var i=0;i<arguments.length;i++){var a=arguments[i];p.push(a&&a.stack?String(a.stack):String(a));}
      s.errors.push(p.join(' '));
      try{orig.apply(w.console,arguments);}catch(_){}
    };
    w.addEventListener('error',function(ev){
      if(/ResizeObserver loop/.test(String(ev&&ev.message||'')))return;
      s.uncaught.push(String(ev&&ev.message||ev)+(ev&&ev.error&&ev.error.stack?' :: '+ev.error.stack:''));});
    w.addEventListener('unhandledrejection',function(ev){
      var r=ev&&ev.reason;s.uncaught.push('unhandledrejection: '+(r&&r.stack?r.stack:String(r)));});
    var le=w._loadError;
    w._loadError=function(err,stage){
      s.loadErr.push(String(err&&err.message||err)+' (stage '+stage+')');
      if(typeof le==='function')return le.apply(this,arguments);
    };
    return s;
  }
  function drain(){
    return {errors:sink.errors.splice(0).slice(0,12),uncaught:sink.uncaught.splice(0).slice(0,12),
            loadErr:sink.loadErr.splice(0).slice(0,12)};
  }
  function overlays(){
    var d=D(),n=0;
    [].slice.call(d.body.children).forEach(function(e){
      if(/^\\s*LOAD ERROR/.test(e.textContent||'')){n++;e.remove();}});
    return n;
  }
  async function setVp(name){
    var v=VP[name];
    fr.style.width=v[0]+'px';fr.style.height=v[1]+'px';
    await waitFor(function(){return W().innerWidth===v[0];},2000);
    await sleep(60);
  }
  function q(sel){return D().querySelector(sel);}
  // the opacity an element is drawn at: its own times every ancestor's (null when it is not there)
  function effOp(e){if(!e)return null;var o=1,w=W();for(var n=e;n&&n.nodeType===1;n=n.parentElement){o*=parseFloat(w.getComputedStyle(n).opacity)||0;}return Math.round(o*100)/100;}
  function txt(sel){var e=q(sel);return e?(e.textContent||'').replace(/\\s+/g,' ').trim():null;}
  // LEDGER steps 7 + 10: the shared calendar (fold, panel, month, summary, every day cell, the week cells, the arrows)
  function calRead(){
    var w=W(),fold=q('[data-lgcalfold="qb"]'),pn=q('#qb-cal'),cal=q('.lg-cal[data-lgcal="qb"]');
    var c={fold:fold?fold.getAttribute('aria-expanded'):null,foldText:fold?(fold.textContent||'').replace(/\\s+/g,' ').trim():null,
      panel:pn?(pn.hasAttribute('hidden')?'hidden':'shown'):null,oldDays:D().querySelectorAll('[data-qcalday]').length,oldNav:D().querySelectorAll('[data-qcalmo]').length};
    if(!cal)return c;
    var sm=cal.querySelector('.lg-cal-sum'),t=cal.querySelector('.lg-cal-title'),grid=cal.querySelector('.lg-cal-grid'),kids=grid?[].slice.call(grid.children):[];
    c.month=cal.getAttribute('data-lgcalmonth');c.title=t?(t.textContent||'').trim():null;
    c.sum=sm?(sm.textContent||'').replace(/\\s+/g,' ').trim():null;
    c.nav=[].map.call(cal.querySelectorAll('[data-lgcalmo]'),function(b){return [b.getAttribute('data-lgcalmo'),!!b.disabled];});
    // 8 header cells (S M T W T F S WEEK), then rows of 7 day slots + 1 week cell
    c.days=[];c.weeks=[];
    kids.slice(8).forEach(function(e,i){
      if(i%8===7){var wm=e.querySelector('.m'),wn=e.querySelector('.n');
        c.weeks.push({title:e.getAttribute('title'),m:wm?(wm.textContent||'').trim():null,n:wn?(wn.textContent||'').trim():null});return;}
      var d=e.querySelector('.d');if(!d)return;
      var m=e.querySelector('.m'),n=e.querySelector('.n'),cs=w.getComputedStyle(e),af=w.getComputedStyle(e,'::after');
      c.days.push({d:+(d.textContent||'').trim(),traded:e.tagName==='BUTTON',ds:e.getAttribute('data-lgcalday'),
        cav:e.classList.contains('cav'),hatch:(cs.backgroundImage||'').indexOf('repeating-linear-gradient')>=0,
        dot:af.content!=='none'&&af.width==='5px',title:e.getAttribute('title'),m:m?(m.textContent||'').trim():null,n:n?(n.textContent||'').trim():null,
        mColor:m?w.getComputedStyle(m).color:null,up:e.classList.contains('up'),down:e.classList.contains('down')});
    });
    c.sumColors=[].map.call(cal.querySelectorAll('.lg-cal-sum span'),function(e){return w.getComputedStyle(e).color;});
    var pr=pn?pn.getBoundingClientRect():null;
    c.box=pr?{l:Math.round(pr.left),r:Math.round(pr.right),w:Math.round(pr.width)}:null;
    c.gridW=grid?Math.round(grid.getBoundingClientRect().width):null;
    return c;
  }
  // the strategy list on the shared list: title and count, the groups in order with their header, fold state and rows, where it sits
  function listRead(){
    var w=W(),lst=q('.qbx-side [data-lglist="qb"]');
    if(!lst)return null;
    function rowRead(b){
      var nm=b.querySelector('.lg-row-name'),cn=nm?nm.cloneNode(true):null,tg=null,tag=cn?cn.querySelector('.lg-row-tag'):null;
      if(tag){tg=(tag.textContent||'').replace(/\\s+/g,' ').trim();tag.parentNode.removeChild(tag);}
      var v=b.querySelector('.lg-row-val'),vc=v?v.cloneNode(true):null,sm=vc?vc.querySelector('small'):null,sm0=v?v.querySelector('small'):null,v2=null;
      if(sm){v2=(sm.textContent||'').replace(/\\s+/g,' ').trim();sm.parentNode.removeChild(sm);}
      var sb=b.querySelector('.lg-row-sub'),rc=b.getBoundingClientRect(),ex=b.nextElementSibling;
      return {key:b.getAttribute('data-lgrow'),name:cn?(cn.textContent||'').replace(/\\s+/g,' ').trim():null,tag:tg,
        sub:sb?(sb.textContent||'').replace(/\\s+/g,' ').trim():null,subShown:sb?w.getComputedStyle(sb).display!=='none':false,
        value:vc?(vc.textContent||'').replace(/\\s+/g,' ').trim():null,value2:v2,value2Shown:sm0?w.getComputedStyle(sm0).display!=='none':false,
        off:b.classList.contains('off'),h:Math.round(rc.height),sw:b.querySelectorAll('[data-lgsw]').length,
        valColor:v?w.getComputedStyle(v).color:null,expanded:b.getAttribute('aria-expanded'),
        extra:(ex&&ex.classList&&ex.classList.contains('qbx-lg-extra'))?ex.getAttribute('data-qbextra'):null};
    }
    var hd=lst.querySelector('.lg-list-hd'),hs=hd?hd.querySelectorAll('span'):[],box=lst.getBoundingClientRect();
    var side=q('.qbx-side'),hist=q('.qbx-history'),acct=q('.qbx-account'),sh=q('.qb-shell'),fr=q('[data-qbtraderow]'),sy=w.scrollY||0;
    var top=function(e){return e?Math.round(e.getBoundingClientRect().top+sy):null;},bot=function(e){return e?Math.round(e.getBoundingClientRect().bottom+sy):null;};
    return {title:hs[0]?(hs[0].textContent||'').trim():null,count:hs[1]?(hs[1].textContent||'').replace(/\\s+/g,' ').trim():null,
      groups:[].map.call(lst.querySelectorAll('.lg-grp'),function(g){
        var h=g.querySelector('.lg-grp-hd'),f=g.querySelector('[data-lggrp]'),n=g.querySelector('.lg-grp-note');
        return {key:g.getAttribute('data-lggroup'),head:h?(h.textContent||'').replace(/\\s+/g,' ').trim():null,fold:!!f,
          expanded:f?f.getAttribute('aria-expanded'):null,note:n?(n.textContent||'').replace(/\\s+/g,' ').trim():null,
          rows:[].map.call(g.querySelectorAll('[data-lgrow]'),rowRead)};}),
      sw:lst.querySelectorAll('[data-lgsw]').length,
      geo:{listTop:top(lst),listBottom:bot(lst),listLeft:Math.round(box.left),listRight:Math.round(box.right),sideTop:top(side),
        histTop:top(hist),histBottom:bot(hist),histLeft:hist?Math.round(hist.getBoundingClientRect().left):null,
        histRight:hist?Math.round(hist.getBoundingClientRect().right):null,acctTop:top(acct),shellTop:top(sh),rowTop:top(fr),
        vh:w.innerHeight,sticky:side?w.getComputedStyle(side).position:null}};
  }
  // the old layout's calendar and list (?oldboards=1 keeps both for one version)
  function oldReads(){
    var d=D();
    return {oldCalDays:d.querySelectorAll('[data-qcalday]').length,oldCalNav:d.querySelectorAll('[data-qcalmo]').length,
      sharedCalFold:!!q('[data-lgcalfold]'),sharedList:!!q('[data-lglist="qb"]'),
      oldLegRows:[].map.call(d.querySelectorAll('.qbx-side [data-qblegrow]'),function(e){return e.getAttribute('data-qblegrow');}),
      oldSideHd:!!q('.qbx-side-hd'),
      order:[].map.call(d.querySelectorAll('.qb-shell > section, .qb-shell > div'),function(e){return e.className.split(' ')[0];}).filter(function(c){return /^qbx-(side|account|history|stats)$/.test(c);})};
  }
  // the More stats panel: shown or hidden, its groups, and every row as 'Group|Label' -> value text
  function moreRead(){
    var mp=q('#qb-more'),m={panel:mp?(mp.hasAttribute('hidden')?'hidden':'shown'):null,groups:[],vals:{},
      empty:!!mp&&(mp.textContent||'').indexOf('No trades in this range.')>=0,hued:[],gap:null};
    if(mp)[].forEach.call(mp.querySelectorAll('[data-lgmsgroup]'),function(g){
      var gt=g.getAttribute('data-lgmsgroup');m.groups.push(gt);
      [].forEach.call(g.querySelectorAll('.lg-ms-row'),function(row){
        var l=row.querySelector('.l'),v=row.querySelector('.v');
        m.vals[gt+'|'+(l?(l.textContent||'').replace(/\\s+/g,' ').trim():'')]=v?(v.textContent||'').replace(/\\s+/g,' ').trim():null;});});
    if(mp&&!mp.hasAttribute('hidden')){
      // MONO has no hue: every value and every bar segment must come out grey (r = g = b)
      var w=W(),chk=function(e,prop){var c=w.getComputedStyle(e)[prop]||'',p=c.replace(/[^0-9.,]/g,'').split(',').map(Number);
        if(p.length>=3&&!(p[0]===p[1]&&p[1]===p[2])&&!(p.length>3&&p[3]===0)&&m.hued.length<6)
          m.hued.push(e.tagName.toLowerCase()+(typeof e.className==='string'&&e.className?'.'+e.className.trim().split(' ').join('.'):'')+' '+prop+' '+c);};
      [].forEach.call(mp.querySelectorAll('.lg-ms-row .v, .lg-ms-row .v *'),function(e){chk(e,'color');});
      [].forEach.call(mp.querySelectorAll('.lg-ms-bar > *'),function(e){chk(e,'backgroundColor');});
      // with no trade in the range: the room between 'No trades in this range.' and the Account heading
      var nt=null;[].forEach.call(mp.querySelectorAll('.lg-ms-note'),function(e){if(!nt&&(e.textContent||'').indexOf('No trades in this range.')>=0)nt=e;});
      var gh=mp.querySelector('.lg-ms-group h4');
      if(nt&&gh)m.gap=Math.round(gh.getBoundingClientRect().top-nt.getBoundingClientRect().bottom);
    }
    return m;
  }
  // wait until the top bar has kept one height for three checks in a row (a busy machine draws late)
  async function settleTopbar(){
    var last=-1,same=0,a=Date.now();
    while(Date.now()-a<3000){var t=D().querySelector('#app .topbar'),h=t?t.offsetHeight:0;
      if(h===last){if(++same>=3)return;}else{same=0;last=h;}await sleep(50);}
  }
  function offenders(d){
    var cw=d.documentElement.clientWidth,res=[],fix=[];
    var all=d.querySelectorAll('body *');
    for(var i=0;i<all.length&&res.length<4;i++){
      var e=all[i],r=e.getBoundingClientRect();
      if(r.width<=0||r.right<=cw+1)continue;
      var p=e.parentElement,pr=p?p.getBoundingClientRect():null;
      if(pr&&pr.right>cw+1)continue;
      var pos=d.defaultView.getComputedStyle(e).position;
      (pos==='fixed'?fix:res).push(e.tagName.toLowerCase()+(e.id?'#'+e.id:'')+(typeof e.className==='string'&&e.className?'.'+e.className.trim().split(/\\s+/).join('.'):'')
               +' right='+Math.round(r.right)+(pos!=='static'?' ('+pos+')':''));
    }
    return res.length?res:fix.slice(0,3);
  }
  function seed(cfg){
    var w=W();
    w.__probeFixJson=JSON.stringify(cfg.fix||FIX);
    w.__qbNowMs=cfg.nowMs||NOW;
    w.__probeOpenLeg=cfg.openLeg||null;
    w.__probeSystemOpen=cfg.systemOpen?1:0;
    w.__probeLiveErr=!!cfg.liveErr;
    w.__probePrevJson=cfg.prev?JSON.stringify(cfg.prev):null;
    w.__probePrevCache=!!cfg.prevCache;
    w.__probeTab=cfg.tab||null;
    w.__probeCheckedMs=cfg.checkedMs||cfg.nowMs||NOW;
    w.__probeOffline=!!cfg.offline;w.__probeMissing=!!cfg.missing;w.__probeUnloaded=!!cfg.unloaded;
    w.__probeRange=cfg.range||null;w.__probeTodayNY=cfg.todayNY||null;w.__probeCalMonth=cfg.calMonth||null;
    w.__probeMoreOpen=!!cfg.moreOpen;
    w.__probeCalOpen=cfg.calOpen||null;w.__probeFolds=!!cfg.folds;
    return w.eval("(function(){try{"
      +"if(!window.__probeLTN)window.__probeLTN=ledgerTodayNY;"
      +"ledgerTodayNY=window.__probeTodayNY?function(){return window.__probeTodayNY;}:window.__probeLTN;"
      // More stats open is stored for this viewer but not in memory: the way a reload finds it
      +"try{if(window.__probeMoreOpen)localStorage.setItem('el_qb_morestats_open','1');else localStorage.removeItem('el_qb_morestats_open');}catch(e){}window._qbMoreStatsOpen=false;"
      +"try{delete navigator.onLine;}catch(e){}"
      +"if(window.__probeOffline)Object.defineProperty(navigator,'onLine',{configurable:true,get:function(){return false;}});"
      +"try{localStorage.removeItem('el_qb_retired_open');localStorage.removeItem('el_lg_lines_webull');}catch(e){}"
      +"window._qbRetiredOpen=false;"
      +"try{localStorage.removeItem('el_qb_cal_open');localStorage.removeItem('el_qb_cal_month');localStorage.removeItem('el_qb_shadow_open');}catch(e){}window._qbCalOpen=null;window._qbShadowOpen=false;"
      +"try{if(window.__probeCalOpen)localStorage.setItem('el_qb_cal_open',window.__probeCalOpen);if(window.__probeFolds){localStorage.setItem('el_qb_retired_open','1');localStorage.setItem('el_qb_shadow_open','1');}}catch(e){}"
      +"prefs.theme="+JSON.stringify(cfg.theme)+";applyTheme();"
      +"window._qqqExec=JSON.parse(window.__probeFixJson);"
      +"window._qbPubFailSeen=null;if(typeof qbNotePubFails==='function'){if(window.__probePrevJson)qbNotePubFails(JSON.parse(window.__probePrevJson),window.__probePrevCache);qbNotePubFails(window._qqqExec);}"
      +"window._qbCheckedMs=window.__probeCheckedMs;window._qqqExecTriedAt=0;"
      +"window._qqqExecLoaded=true;window._qqqExecLoading=false;window._qqqExecErr=null;window._qqqExecMissing=false;"
      +"if(window.__probeMissing){window._qqqExec=null;window._qqqExecMissing=true;}"
      +"if(window.__probeUnloaded){window._qqqExec=null;window._qqqExecLoaded=false;window._qbCheckedMs=0;}"
      +"window._qqqPaper=null;window._qqqPaperLoaded=true;window._qqqPaperLoading=false;window._qqqPaperErr=null;"
      +"window._qqqCalMonth=null;window._qeDrawerIdx=null;window._qeChartHidden={};window._qeTradesShown=50;window._qeEventsShown=30;"
      +"window._qbSheet=null;window._qbLegOpen=new Set(window.__probeOpenLeg?[window.__probeOpenLeg]:[]);window._qeTradesView='list';window._qeChartPeriod='ALL';"
      +"window._qbLegNoteOpen={};if(window.__probeOpenLeg)window._qbLegNoteOpen[window.__probeOpenLeg]=true;"
      +"try{var ap=JSON.parse(localStorage.getItem('augurPrefs')||'{}');ap.qqqSystemOpen=window.__probeSystemOpen;localStorage.setItem('augurPrefs',JSON.stringify(ap));}catch(e){}"
      +"window._qqqExecLive=false;window._qqqExecLiveErrorAt=window.__probeLiveErr?Date.now():null;window._qqqExecFetchedAt=window.__probeLiveErr?0:Date.now();"
      +"window._qbChartHoverActive=false;"
      +"if(window.__probeCalMonth)window._qqqCalMonth=window.__probeCalMonth;"
      +"homeRange=window.__probeRange||'ALL';currentUser=currentUser||{uid:'probe-uid'};"
      +"activeTab=window.__probeTab||'augur';augurSub='qqqpaper';window._lastRenderTab=activeTab;"
      +"try{window.scrollTo(0,0);}catch(e){}"
      +"renderApp();return 'OK';"
      +"}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
  }
  function sample(){
    var d=D(),w=W(),r={};
    r.innerW=w.innerWidth;
    r.theme=d.documentElement.getAttribute('data-theme');
    r.appLen=(d.getElementById('app')||{innerHTML:''}).innerHTML.length;
    r.heroMissing=['qb-hero-label','qb-hero-value','qb-hero-today','qb-hero-range','qb-hero-chips'].filter(function(i){return !d.getElementById(i);});
    r.heroBig=txt('#qb-hero-value');
    r.heroToday=txt('#qb-hero-today');
    r.pills=[].map.call(d.querySelectorAll('.qbx-range-row [data-qbrange]'),function(b){return b.getAttribute('data-qbrange');}).join(',');
    var csv=d.querySelector('#qb-lg-chart svg');
    r.chart=!!csv;
    r.chartH=0;
    if(csv){var cr=csv.getBoundingClientRect(),vb=(csv.getAttribute('viewBox')||'').split(/[ ,]+/).map(Number);
      r.chartH=Math.round(vb.length===4&&vb[2]>0&&vb[3]>0?vb[3]*Math.min(cr.width/vb[2],cr.height/vb[3]):cr.height);}
    r.chartDates=csv?csv.querySelectorAll('[data-lgdate]').length:0;
    r.chartTicks=csv?csv.querySelectorAll('[data-lgtick]').length:0;
    r.chartBands=csv?csv.querySelectorAll('[data-lgband]').length:0;
    r.chartMarks=csv?csv.querySelectorAll('[data-lgmark]').length:0;
    var mk=csv?csv.querySelector('[data-lgmark]'):null;
    r.markText=mk&&mk.nextElementSibling?(mk.nextElementSibling.textContent||'').trim():null;
    r.lines=[].map.call(d.querySelectorAll('#qb-lg-chart .lg-legend [data-lgline]'),function(b){return (b.textContent||'').trim();});
    r.lineDashes=[].map.call(d.querySelectorAll('#qb-lg-chart .lg-legend svg line'),function(l){return l.getAttribute('stroke-dasharray')||'none';});
    r.lineIconW=Math.max.apply(null,[0].concat([].map.call(d.querySelectorAll('#qb-lg-chart .lg-legend svg'),function(s){return Math.round(s.getBoundingClientRect().width);})));
    r.key=txt('.qbx-lg-key');
    r.liveRows=[].map.call(d.querySelectorAll('.qbx-side [data-qblegrow]'),function(e){return e.getAttribute('data-qblegrow');});
    var rb=d.querySelector('.qbx-side [data-qbretired]');
    r.retired=!!rb;
    r.retiredExpanded=rb?rb.getAttribute('aria-expanded'):null;
    r.retiredText=rb?(rb.textContent||'').replace(/\\s+/g,' ').trim():null;
    r.retiredRows=d.querySelectorAll('.qbx-side [data-qbretiredrow]').length;
    var rows=d.querySelectorAll('[data-qbtraderow]');
    r.tradeRows=rows.length;
    r.tradeLegs=[].map.call(rows,function(e){var s=e.querySelector('.qb-trade-leg');return s?(s.textContent||'').trim():null;});
    r.oldChart=!!d.querySelector('#qbCrossCapture');
    r.stats=[].map.call(d.querySelectorAll('.qbx-lgstats [data-lgstat]'),function(e){
      var v=e.querySelector('.lg-stat-val'),s=e.querySelector('.lg-stat-sub');
      return [e.getAttribute('data-lgstat'),v?(v.textContent||'').replace(/\\s+/g,' ').trim():null,s?(s.textContent||'').replace(/\\s+/g,' ').trim():null];});
    r.statTilesAll=d.querySelectorAll('[data-lgstat]').length;
    // the strip must be SEEN, right under the chart: shown, of real size, below the chart box and above the
    // Account and History sections (and on a phone above the Strategies list)
    var sbx=q('.qbx-lgstats');
    if(sbx){var sbr=sbx.getBoundingClientRect(),sbs=w.getComputedStyle(sbx),cbx=q('.qbx-chart');
      var topOf=function(sel){var e=q(sel);return e?Math.round(e.getBoundingClientRect().top):null;};
      r.statBox={disp:sbs.display,vis:sbs.visibility,op:effOp(sbx),w:Math.round(sbr.width),h:Math.round(sbr.height),top:Math.round(sbr.top),
        tileH:Math.min.apply(null,[9999].concat([].map.call(sbx.querySelectorAll('[data-lgstat]'),function(e){return Math.round(e.getBoundingClientRect().height);}))),
        chartBottom:cbx?Math.round(cbx.getBoundingClientRect().bottom):null,sideTop:topOf('.qbx-side'),acctTop:topOf('.qbx-account'),histTop:topOf('.qbx-history')};}
    r.oldStats=!!d.querySelector('.qbx-stat-strip');
    var mbt=q('[data-lgmore="qb"]');r.moreBtn=mbt?mbt.getAttribute('aria-expanded'):null;
    r.more=moreRead();
    var act=q('.qbx-activity'),mwon=act?(act.textContent||'').match(/(\\d+)% won/):null;r.calWon=mwon?+mwon[1]:null;
    r.lgcal=calRead();r.lg=listRead();r.old=oldReads();
    r.scrollW=d.documentElement.scrollWidth;
    r.clientW=d.documentElement.clientWidth;
    if(r.scrollW>r.clientW+1)r.wide=offenders(d);
    r.overlay=overlays();
    // freshness readouts (sweep 2026-10-05)
    r.fresh={};
    [].forEach.call(d.querySelectorAll('#qb-hero-chips [data-qbfresh]'),function(e){r.fresh[e.getAttribute('data-qbfresh')]=(e.textContent||'').trim();});
    r.strip=txt('.qbx-status-strip');
    var tc=d.querySelector('[data-qbtopchip]');
    r.top=tc?[tc.getAttribute('data-qbtopchip'),(tc.textContent||'').slice(1).trim()]:null;
    // the chip must be DRAWN where the owner can see it: shown, inside the viewport, not covered
    var tcw=d.getElementById('qb-top-chip');
    if(tcw){var br=tcw.getBoundingClientRect(),cs=w.getComputedStyle(tcw),cx=br.left+br.width/2,cy=br.top+br.height/2;
      var hit=(br.width>0&&br.height>0&&cx>=0&&cy>=0&&cx<w.innerWidth&&cy<w.innerHeight)?d.elementFromPoint(cx,cy):null;
      r.topBox={l:Math.round(br.left),t:Math.round(br.top),r:Math.round(br.right),b:Math.round(br.bottom),w:Math.round(br.width),h:Math.round(br.height),
        disp:cs.display,vis:cs.visibility,op:effOp(tcw),vw:w.innerWidth,vh:w.innerHeight,
        covered:hit?!(hit===tcw||tcw.contains(hit)):null,coveredBy:hit&&!(hit===tcw||tcw.contains(hit))?(hit.tagName.toLowerCase()+(hit.id?'#'+hit.id:'')):null};}
    r.timer=typeof w._qbFreshTimer;
    r.vis=d.visibilityState;
    var lp=q('[data-qblegpill="NOISE"]');r.legPill=lp?(w.getComputedStyle(lp).color===greyCol()?'grey':'colour'):null;r.legPillTxt=lp?(lp.textContent||'').trim():null;
    r.liveLine=txt('[data-qblive="NOISE"]');
    var op=q('[data-qbopenpnl="NOISE"]');r.openPnl=op?(w.getComputedStyle(op).color===greyCol()?'grey':'colour'):null;
    var ur=q('[data-qbunreal="NOISE"]');r.unreal=ur?(w.getComputedStyle(ur).color===greyCol()?'grey':'colour'):null;
    var at=(d.getElementById('app')||{innerText:''}).innerText||'';r.badTok=(at.match(/NaN|undefined|\\[object Object\\]/g)||[]).slice(0,4);
    try{r.cantRead=w.eval('qbCantRead()');}catch(e){r.cantRead='ERR '+e;}
    r.visRead=w.__probeVisRead||null;w.__probeVisRead=null;
    try{r.cal=w.eval("JSON.stringify([qbIsSessionDay('2026-11-26'),qbIsSessionDay('2027-12-31'),qbIsSessionDay('2027-12-30'),qbCloseMins('2026-11-27'),qbIsSessionDay('2026-10-05')])");}catch(e){r.cal=null;}
    var sp=d.querySelector('[data-qbstop]');r.stop=sp?sp.getAttribute('data-qbstop'):null;r.stopTxt=sp?(sp.textContent||'').trim():null;
    var od=d.querySelector('[data-qbordersday]');r.orders=od?od.getAttribute('data-qbordersday'):null;r.ordersTxt=od?(od.textContent||'').trim():null;
    r.legtoday=txt('[data-qblegtoday]');
    r.asof=txt('[data-qbasof]');
    r.eqStale=!!d.querySelector('[data-qbeqstale]');
    r.keelwarn=txt('[data-qbkeelwarn]');
    r.miniSilent=txt('[data-qbminisilent]');
    r.miniPill=txt('[data-qbminipill]');
    var mp=q('[data-qbminipill]');r.miniPillHtml=mp?mp.innerHTML:null;
    var om=q('[data-qbordmode]');r.ordModeHtml=om?om.innerHTML:null;
    var eqs=q('[data-qbeqstale]');r.eqWhy=eqs?eqs.getAttribute('title'):null;
    r.pin=w.__probePin||null;w.__probePin=null;
    r.onLine=w.navigator.onLine;
    r.miniTxt=txt('.qbx-orders-mini');
    r.ordMode=txt('[data-qbordmode]');
    r.keelLine=txt('[data-qbkeelline="NOISE"]');
    var ec=q('[data-qbeqchg]');r.eqChg=ec?ec.getAttribute('data-qbeqchg'):null;r.eqChgOp=effOp(ec);
    var rc=q('[data-qbrecon]');r.recon=rc?rc.getAttribute('data-qbrecon'):null;r.reconTxt=rc?(rc.textContent||'').replace(/\\s+/g,' ').trim():null;
    r.opNotToday=effOp(q('[data-qbnottoday]'));
    r.opStop=effOp(q('[data-qbstop]'));
    r.opLegToday=effOp(q('[data-qblegtoday]'));
    r.lastTick=(q('[data-qblasttick]')||{getAttribute:function(){return null;}}).getAttribute('data-qblasttick');
    r.tab=w.eval('activeTab');
    // the box's own flags in the hero (not the freshness chips): drawn grey (--text4) or not
    var grey=greyCol();
    r.flags={};
    [].forEach.call(d.querySelectorAll('#qb-hero-chips span:not([data-qbfresh])'),function(e){
      var t=(e.textContent||'').trim();if(t&&!(t in r.flags))r.flags[t]=w.getComputedStyle(e).color===grey?'grey':'colour';});
    // would the full-doc listener run on HOME / on the board (signed in, page visible)? It must be the
    // board's only (QUOTA in index.html). db/auth/visibility stubbed, then put back
    function wants(tab,sub){return w.eval("(function(){var sd=db,sa=auth,st=activeTab,ss=augurSub;try{db={};auth={currentUser:{uid:'probe-uid'}};activeTab='"+tab+"';augurSub='"+sub+"';"
      +"Object.defineProperty(document,'visibilityState',{configurable:true,get:function(){return 'visible';}});"
      +"return _qqqExecWantsLive();}catch(e){return 'ERR '+e;}finally{db=sd;auth=sa;activeTab=st;augurSub=ss;try{delete document.visibilityState;}catch(e2){}}})()");}
    r.wantsLiveHome=wants('home','qqqpaper');
    r.wantsLiveBoard=wants('augur','qqqpaper');
    return r;
  }
  function greyCol(){var d=D(),w=W(),p=d.createElement('span');p.style.color='var(--text4)';d.body.appendChild(p);var g=w.getComputedStyle(p).color;p.remove();return g;}
  // after the seed render: run the 30 s timer's body with the clock moved on, or land a .get() on HOME
  async function after(cfg){
    var w=W();
    if(cfg.visread){
      // the page shown again: on HOME 60 s and 400 s after the last read, then on the board 60 s after it.
      // loadQqqExec is swapped for a counter (no Firestore), qbOnPageShown is the visibility hook's body
      w.__probeVisRead=w.eval("(function(){var orig=loadQqqExec,n=0,res=[];try{loadQqqExec=function(){n++;};"
        +"Object.defineProperty(document,'visibilityState',{configurable:true,get:function(){return 'visible';}});"
        +"[['home',60000],['home',400000],['augur',60000]].forEach(function(c){activeTab=c[0];window._qqqExecLoading=false;window._qqqExecTriedAt=Date.now()-c[1];n=0;qbOnPageShown();res.push(n);});"
        +"return res;}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}finally{loadQqqExec=orig;activeTab=window.__probeTab||'augur';window._qqqExecTriedAt=0;try{delete document.visibilityState;}catch(e2){}}})()");
      return 'OK';
    }
    if(cfg.cachesnap){
      // the listener error was 61 s ago, so the board's listener re-attaches; its first snapshot is cached
      var rc=w.eval("(function(){var sd=db,sa=auth;window.__probeRestore=function(){db=sd;auth=sa;try{delete document.visibilityState;}catch(e2){}};try{"
        +"window._qqqExecLiveErrorAt=Date.now()-61000;window._qqqExecUnsub=null;window._qqqExecLive=false;"
        +"var doc=JSON.parse(window.__probeFixJson),snap={exists:true,data:function(){return doc;},metadata:{fromCache:true}};"
        +"var ref={get:function(){return new Promise(function(){});},onSnapshot:function(a,b){var next=typeof a==='function'?a:b;setTimeout(function(){next(snap);},0);return function(){};}};"
        +"db={collection:function(){return {doc:function(){return {collection:function(){return {doc:function(){return ref;}};}};}};}};"
        +"auth={currentUser:{uid:'probe-uid'}};"
        +"Object.defineProperty(document,'visibilityState',{configurable:true,get:function(){return 'visible';}});"
        +"_qqqExecEnsureLive();window.__probeRestore();return window._qqqExecUnsub?'OK':'the listener did not attach';"
        +"}catch(e){window.__probeRestore();return 'ERR '+(e&&e.stack?e.stack:e);}})()");
      await sleep(150);
      w.eval("window._qqqExecUnsub=null;window._qqqExecLastRenderAt=0;if(typeof qbFreshTick==='function')qbFreshTick();renderApp();");
      return rc;
    }
    if(cfg.tick){
      w.__qbNowMs=cfg.tickTo;w._qqqExecLastRenderAt=0;
      return w.eval("(function(){try{qbFreshTick();return 'OK';}catch(e){return 'ERR '+(e&&e.stack?e.stack:e);}})()");
    }
    if(cfg.fetch){
      var pinTb0=null;
      if(cfg.pin){
        // let renderApp's own pins (rAF, 400 ms, fonts.ready) all run first: only the chip's refresh may re-pin after the read
        try{var fr0=D().fonts;if(fr0&&fr0.ready)await Promise.race([fr0.ready,sleep(5000)]);}catch(e){}
        await sleep(700);
        await settleTopbar();
        var tb0=D().querySelector('#app .topbar');pinTb0=tb0?tb0.offsetHeight:null;
        // Measured in the same turn as the read, right after the page's own handler (the next callback on
        // the same promise), scrolled 600 px with layout forced. Nothing else can run in between: on a busy
        // machine headless Chrome delivers the phone resize event and renderApp's first-frame pin late, and
        // either one landing after the read re-pinned the strip and hid a chip that does not (review 6).
        w.__probeMeasurePin=function(){
          var d=D(),tb=d.querySelector('#app .topbar'),sb=tb&&tb.nextElementSibling,ct=d.querySelector('#app .content'),sp=d.createElement('div');
          sp.style.height='3000px';if(ct)ct.appendChild(sp);
          w.scrollTo(0,600);
          var pin={tbH0:pinTb0,scrollY:Math.round(w.scrollY)};
          if(tb&&sb){var tr=tb.getBoundingClientRect(),sr=sb.getBoundingClientRect();
            pin.tbH1=tb.offsetHeight;pin.tbBottom=Math.round(tr.bottom);pin.subTop=Math.round(sr.top);pin.subStyleTop=sb.style.top;pin.subPos=sb.style.position;}
          w.scrollTo(0,0);sp.remove();
          return pin;
        };
      }
      w.__probeFetchJson=JSON.stringify(cfg.fetch);w.__qbNowMs=cfg.tickTo;w.__probePinNow=!!cfg.pin;
      var res=w.eval("(function(){var sd=db,sa=auth;window.__probeRestore=function(){db=sd;auth=sa;};try{"
        +"var doc=JSON.parse(window.__probeFetchJson),snap={exists:true,data:function(){return doc;},metadata:{fromCache:false}};"
        +"var got=Promise.resolve(snap),ref={get:function(){return got;},onSnapshot:function(){return function(){};}};"
        +"db={collection:function(){return {doc:function(){return {collection:function(){return {doc:function(){return ref;}};}};}};}};"
        +"auth={currentUser:{uid:'probe-uid'}};window._qqqExecLoading=false;loadQqqExec(null,true);"
        +"if(window.__probePinNow)got.then(function(){try{window.__probePin=window.__probeMeasurePin();}catch(e){window.__probePin={err:String(e)};}});"
        +"return 'OK';"
        +"}catch(e){window.__probeRestore();return 'ERR '+(e&&e.stack?e.stack:e);}})()");
      await sleep(150);
      try{w.__probeRestore();}catch(e){}
      w.__probePinNow=false;
      return res;
    }
    return null;
  }
  async function runCase(nm,cfg){
    var r={};
    await setVp(cfg.vp);
    drain();
    try{r.call=seed(cfg);}catch(e){r.call='ERR '+(e&&e.stack?e.stack:e);}
    await sleep(200);
    if(cfg.tick||cfg.fetch||cfg.visread||cfg.cachesnap){try{r.after=await after(cfg);}catch(e){r.after='ERR '+(e&&e.stack?e.stack:e);}await sleep(300);}
    try{Object.assign(r,sample());}catch(e){r.sampleErr=String(e&&e.stack?e.stack:e);}
    Object.assign(r,drain());
    out.cases[nm]=r;
  }
  async function interact(){
    var w=W(),d=D(),res={};
    await setVp('laptop');
    drain();
    try{res.seed=seed({vp:'laptop',theme:'dark'});}catch(e){res.seed='ERR '+(e&&e.stack?e.stack:e);}
    await sleep(200);
    try{
      // 1. the Retired group (a fold of the shared list) opens and closes, and the choice is kept for this viewer; opened it lists
      // ENGU-Q #335 and the rows add up (the whole list is read open, for the judge to add up against the account's figure)
      var none={getAttribute:function(){return null;}};
      var rb=q('.qbx-side [data-lggrp="retired"]');
      if(rb){rb.click();await sleep(80);}
      var st=null;try{st=w.localStorage.getItem('el_qb_retired_open');}catch(e){}
      res.open={expanded:(q('.qbx-side [data-lggrp="retired"]')||none).getAttribute('aria-expanded'),
        rows:d.querySelectorAll('.qbx-side [data-lggroup="retired"] [data-lgrow]').length,engu:!!q('.qbx-side [data-lggroup="retired"] [data-lgrow="ENGUQ"]'),stored:st,list:listRead()};
      rb=q('.qbx-side [data-lggrp="retired"]');
      if(rb){rb.click();await sleep(80);}
      res.closed={expanded:(q('.qbx-side [data-lggrp="retired"]')||none).getAttribute('aria-expanded'),
        rows:d.querySelectorAll('.qbx-side [data-lggroup="retired"] [data-lgrow]').length};
      // 1b. the Shadow group opens (this doc has no shadow leg, so its note says so), closes, and is remembered
      var sb2=q('.qbx-side [data-lggrp="shadow"]'),sd={};
      var grp=function(k){var l=listRead();return l?l.groups.filter(function(g){return g.key===k;})[0]||null:null;};
      if(sb2){sb2.click();await sleep(80);
        sd.open=grp('shadow');
        try{sd.stored=w.localStorage.getItem('el_qb_shadow_open');}catch(e){}
        var sb3=q('.qbx-side [data-lggrp="shadow"]');if(sb3){sb3.click();await sleep(80);}
        sd.closed=grp('shadow');
        try{sd.stored2=w.localStorage.getItem('el_qb_shadow_open');}catch(e){}}
      res.shadow=sd;
      // 1c. a leg row opens its detail right under it and closes again
      var lr=q('.qbx-side [data-lgrow="NOISE"]'),ld={};
      if(lr){lr.click();await sleep(80);
        var r2=q('.qbx-side [data-lgrow="NOISE"]'),ex=q('.qbx-side [data-qbextra="NOISE"]');
        ld.expanded=r2?r2.getAttribute('aria-expanded'):null;
        ld.detail=ex?(ex.textContent||'').replace(/\\s+/g,' ').trim():null;
        lr=q('.qbx-side [data-lgrow="NOISE"]');if(lr){lr.click();await sleep(80);}
        var r3=q('.qbx-side [data-lgrow="NOISE"]');
        ld.expandedAfter=r3?r3.getAttribute('aria-expanded'):null;
        ld.detailAfter=!!q('.qbx-side [data-qbextra="NOISE"] .qb-leg-detail');}
      res.legrow=ld;
      // 1d. the note toggle beside a run number shows that leg's note under its row and leaves the row's detail shut; a second tap hides it
      var ib=q('.qbx-side [data-qbleginfo="NOISE"]'),inf={};
      if(ib){
        var ex0=q('.qbx-side [data-qbextra="NOISE"]');
        inf.titleBefore=ib.getAttribute('title');inf.noteBefore=ex0?(ex0.textContent||''):'';
        ib.click();await sleep(80);
        var rw1=q('.qbx-side [data-lgrow="NOISE"]'),ex1=q('.qbx-side [data-qbextra="NOISE"]'),ib1=q('.qbx-side [data-qbleginfo="NOISE"]');
        inf.expanded=rw1?rw1.getAttribute('aria-expanded'):null;
        inf.note=ex1?(ex1.textContent||''):'';
        inf.detail=!!q('.qbx-side [data-qbextra="NOISE"] .qb-leg-detail');
        inf.title=ib1?ib1.getAttribute('title'):null;
        if(ib1){ib1.click();await sleep(80);}
        var rw2=q('.qbx-side [data-lgrow="NOISE"]'),ex2=q('.qbx-side [data-qbextra="NOISE"]');
        inf.expandedAfter=rw2?rw2.getAttribute('aria-expanded'):null;
        inf.noteAfter=ex2?(ex2.textContent||''):'';
      }
      res.info=inf;
      // 2. a scrub writes the hero and leaving puts it back (no re-render)
      var sv=q('#qb-lg-chart svg'),sc={};
      if(sv){
        var rc=sv.getBoundingClientRect(),y=rc.top+rc.height/2;
        sc.big0=txt('#qb-hero-value');sc.today0=txt('#qb-hero-today');
        sv.dispatchEvent(new w.PointerEvent('pointermove',{clientX:rc.left+2,clientY:y,pointerType:'mouse',bubbles:true}));
        sc.bigStart=txt('#qb-hero-value');sc.todayStart=txt('#qb-hero-today');sc.held=!!w._qbChartHoverActive;
        sc.sameSvg=q('#qb-lg-chart svg')===sv;
        sv.dispatchEvent(new w.PointerEvent('pointermove',{clientX:rc.right-1,clientY:y,pointerType:'mouse',bubbles:true}));
        sc.bigEnd=txt('#qb-hero-value');sc.rangeEnd=txt('#qb-hero-range');
        sv.dispatchEvent(new w.PointerEvent('pointerleave',{clientX:rc.right+5,clientY:y,pointerType:'mouse',bubbles:true}));
        sc.bigAfter=txt('#qb-hero-value');sc.todayAfter=txt('#qb-hero-today');sc.heldAfter=!!w._qbChartHoverActive;
      }
      res.scrub=sc;
      // 3. a legend switch is remembered for this viewer
      var lb=q('#qb-lg-chart .lg-legend [data-lgline="0"]'),lg={};
      if(lb){lb.click();await sleep(60);
        var lb2=q('#qb-lg-chart .lg-legend [data-lgline="0"]');lg.off=!!(lb2&&lb2.classList.contains('off'));
        try{lg.stored=w.localStorage.getItem('el_lg_lines_webull');}catch(e){}}
      res.legend=lg;
      // 4. the More stats fold (LEDGER step 6) opens with the shared groups + Account, closes, and is remembered
      var mb=q('[data-lgmore="qb"]'),fo={};
      if(mb){
        fo.before=mb.getAttribute('aria-expanded');mb.click();await sleep(80);
        var mb2=q('[data-lgmore="qb"]');fo.open=mb2?mb2.getAttribute('aria-expanded'):null;
        var pn=q('#qb-more');fo.panel=pn?(pn.hasAttribute('hidden')?'hidden':'shown'):null;
        fo.groups=[].map.call(d.querySelectorAll('#qb-more [data-lgmsgroup]'),function(g){return g.getAttribute('data-lgmsgroup');});
        fo.acct=[].map.call(d.querySelectorAll('#qb-more [data-lgmsgroup="Account"] .lg-ms-row .l'),function(e){return (e.textContent||'').trim();});
        fo.vals=moreRead().vals;
        fo.bad=((pn&&pn.innerText)||'').match(/NaN|undefined|\\[object Object\\]/g)||[];
        try{fo.stored=w.localStorage.getItem('el_qb_morestats_open');}catch(e){}
        if(mb2){mb2.click();await sleep(80);}
        var mb3=q('[data-lgmore="qb"]');fo.closed=mb3?mb3.getAttribute('aria-expanded'):null;
        var pn3=q('#qb-more');fo.panelAfter=pn3?(pn3.hasAttribute('hidden')?'hidden':'shown'):null;
        try{fo.stored2=w.localStorage.getItem('el_qb_morestats_open');}catch(e){}
      }
      res.fold=fo;
      // 5. the shared calendar (LEDGER step 7): its day taps, month arrows, fold and what a reload finds
      var ca={};
      ca.start=calRead();
      var spy=[],proto=w.Element.prototype,so=proto.scrollIntoView;
      proto.scrollIntoView=function(o){spy.push({day:this.getAttribute?this.getAttribute('data-qbday'):null,id:this.id||null,opt:o||null});};
      try{
        var db=q('[data-lgcalday="2026-10-02"]');
        if(db){db.click();await sleep(60);var rr=q('[data-qbday="2026-10-02"]');ca.tapOct=spy.slice();ca.flashOct=!!(rr&&rr.classList.contains('lg-flash'));
          var all=d.querySelectorAll('[data-qbday="2026-10-02"]');ca.octRows=all.length;ca.octFirstIsTapped=!!(rr&&all[0]===rr);}
        var eb=q('[data-lgcal="qb"][data-lgcalmo="-1"]');
        if(eb){eb.click();await sleep(80);}
        ca.sept=calRead();
        try{ca.storedMonth=w.localStorage.getItem('el_qb_cal_month');}catch(e){}
        ca.memMonth=w._qqqCalMonth||null;
        spy.length=0;
        var d2=q('[data-lgcalday="2026-09-23"]');
        if(d2){d2.click();await sleep(60);ca.tapSep=spy.slice();}
        var fb=q('[data-lgcalfold="qb"]');
        if(fb){fb.click();await sleep(80);}
        ca.closed=calRead();
        try{ca.storedOpen=w.localStorage.getItem('el_qb_cal_open');}catch(e){}
        // a reload: nothing in memory, the stored choices kept
        w.eval("window._qqqCalMonth=null;window._qbCalOpen=null;renderApp();");await sleep(120);
        ca.reload=calRead();
        fb=q('[data-lgcalfold="qb"]');
        if(fb){fb.click();await sleep(80);}
        ca.reopen=calRead();
        try{ca.storedOpen2=w.localStorage.getItem('el_qb_cal_open');}catch(e){}
        var lb=q('[data-lgcal="qb"][data-lgcalmo="1"]');
        if(lb){lb.click();await sleep(80);}
        ca.oct=calRead();
        // 5b. the trade list shows only its newest rows until SHOW MORE: a tap on a day whose rows are not on the page yet draws every
        // row first, then scrolls to that day's newest trade
        w.eval("window._qeTradesShown=1;renderApp();");await sleep(120);
        var fd=q('[data-lgcal="qb"] button[data-lgcalday]');
        ca.moreDay=fd?fd.getAttribute('data-lgcalday'):null;
        ca.moreRowsBefore=d.querySelectorAll('[data-qbtraderow]').length;
        ca.moreHadRow=!!(ca.moreDay&&q('[data-qbday="'+ca.moreDay+'"]'));
        spy.length=0;
        if(fd){fd.click();await sleep(100);}
        ca.moreSpy=spy.slice();
        ca.moreRowsAfter=d.querySelectorAll('[data-qbtraderow]').length;
        ca.moreHasRow=!!(ca.moreDay&&q('[data-qbday="'+ca.moreDay+'"]'));
        w.eval("window._qeTradesShown=null;renderApp();");await sleep(80);
      }finally{proto.scrollIntoView=so;}
      res.cal=ca;
      // 6. the Table view names every strategy with its run number too (family + run number on every trade row)
      var tb=q('[data-qbseg="tradesview"] [data-qbsegval="table"]'),tv={};
      if(tb){tb.click();await sleep(100);
        tv.legs=[].map.call(d.querySelectorAll('[data-qetraderow] .qb-trade-leg'),function(e){return (e.textContent||'').trim();});
        tv.days=[].map.call(d.querySelectorAll('[data-qetraderow]'),function(e){return e.getAttribute('data-qbday');});
        var lb2=q('[data-qbseg="tradesview"] [data-qbsegval="list"]');
        if(lb2){lb2.click();await sleep(100);}}
      res.table=tv;
    }catch(e){res.threw=String(e&&e.stack?e.stack:e);}
    await sleep(60);
    res.errs=drain();
    out.inter=res;
  }
  async function boot(){
    var w=W();
    try{
      out.VERSION=out.VERSION||w.eval('typeof VERSION!=="undefined"?VERSION:null');
      out.renderApp=typeof w.renderApp;
      sink=hook(w);
    }catch(e){out.err=String(e);finish('hookfail');return false;}
    if(out.renderApp!=='function'){finish('noboot');return false;}
    out.authSettled=await waitFor(function(){return !!D().getElementById('tsu');},12000);
    try{w.eval('renderAuth=function(){};');}catch(e){out.notes.push('renderAuth stub: '+e);}
    await sleep(200);
    drain();
    overlays();
    return true;
  }
  fr.addEventListener('load',function(){
    setTimeout(async function(){
      if(phase===0){
        phase=1;
        if(!(await boot()))return;
        for(var i=0;i<CASES.length;i++)await runCase(CASES[i][0],CASES[i][1]);
        try{await interact();}catch(e){out.inter={threw:String(e&&e.stack?e.stack:e)};}
        out.stats={};
        for(var k=0;k<STATS.length;k++){
          var S=STATS[k];
          await runCase('__st'+k,{vp:S.vp,theme:S.theme,fix:S.doc,range:S.range,todayNY:S.today,calMonth:S.calMonth,moreOpen:S.more,calOpen:S.calOpen,folds:S.folds,nowMs:S.nowMs});
          out.stats[S.name]=out.cases['__st'+k];delete out.cases['__st'+k];
        }
        try{W().eval("ledgerTodayNY=window.__probeLTN||ledgerTodayNY;");}catch(e){}
        out.vars={};
        for(var j=0;j<VARS.length;j++){
          var V=VARS[j];
          await runCase('__var'+j,{vp:V.vp||'laptop',theme:V.theme||'dark',fix:V.doc,nowMs:V.renderMs||V.nowMs,openLeg:'NOISE',systemOpen:V.systemOpen,
            liveErr:V.liveErr,prev:V.prev,prevCache:V.prevCache,tab:V.tab,checkedMs:V.checkedMs,tick:V.tick,tickTo:V.nowMs,fetch:V.fetch,
            offline:V.offline,missing:V.missing,unloaded:V.unloaded,pin:V.pin,visread:V.visread,cachesnap:V.cachesnap});
          out.vars[V.name]=out.cases['__var'+j];delete out.cases['__var'+j];
        }
        try{W().eval('delete navigator.onLine');}catch(e){}
        try{var ap0=JSON.parse(W().localStorage.getItem('augurPrefs')||'{}');ap0.qqqSystemOpen=0;W().localStorage.setItem('augurPrefs',JSON.stringify(ap0));}catch(e){}
        fr.src='../index.html?oldboards=1';
        return;
      }
      if(phase===1){
        phase=2;
        if(!(await boot()))return;
        await runCase('oldboards',{vp:'laptop',theme:'mono'});
        finish('done');
      }
    },2500);
  });
})();
</script>
</body></html>
"""


def find_chrome():
    cands = [os.path.join('C:' + os.sep, 'Program Files', 'Google', 'Chrome', 'Application', 'chrome.exe'),
             os.path.join('C:' + os.sep, 'Program Files (x86)', 'Google', 'Chrome', 'Application', 'chrome.exe')]
    local = os.environ.get('LOCALAPPDATA')
    if local:
        cands.append(os.path.join(local, 'Google', 'Chrome', 'Application', 'chrome.exe'))
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


def qe_pnl_of(t):
    """The board's P&L of record for one trade (index.html qePnlOf): pnl_record, else the book
    pnl, else the re-priced real_pnl, else 0. A null or empty field is missing, never $0."""
    for k in ('pnl_record', 'pnl', 'real_pnl'):
        v = t.get(k)
        if v is None or v == '':
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if v == v and v not in (float('inf'), float('-inf')):
            return v
    return 0.0


FAMILY = {'ORB': 'ORB', 'ENGUQ': 'ENGU-Q', 'NOISE': 'NOISE'}
CURRENT_RUN = {'ORB': '#314', 'ENGUQ': '#335', 'NOISE': '#382'}
NOISE_SWITCH = '2026-09-24'   # NOISE #304 -> #382 (index.html QE_LEG_VERSIONS)
TID_RE = re.compile(r'^([A-Za-z0-9_]+)-\d{8}T\d{6}Z-[LS]$')


def expected_leg_name(t):
    """The strategy name a trade row must show, worked out here and not read off the page: the
    run in the trade id when the id carries one (NOISE_304-... -> #304), else NOISE before the
    09-24 switch -> #304, else the leg's current run."""
    leg = str(t.get('leg') or '')
    fam = FAMILY.get(leg, leg)
    m = TID_RE.match(str(t.get('trade_id') or ''))
    dg = re.search(r'_(\d+)$', m.group(1)) if m else None
    if dg:
        return '%s #%s' % (fam, dg.group(1))
    day = str(t.get('entry_ts') or t.get('exit_ts') or '')[:10]
    if leg == 'NOISE' and re.match(r'^\d{4}-\d{2}-\d{2}$', day) and day < NOISE_SWITCH:
        return 'NOISE #304'
    return '%s %s' % (fam, CURRENT_RUN.get(leg, ''))


def money(v):
    return ('-' if v < 0 else '') + '${:,.2f}'.format(abs(v))


def _close_day(t):
    """index.html qeTradeDate: the New York day a trade closed (exit_ts), else its entry day."""
    d = str(t.get('exit_ts') or '')[:10] or str(t.get('entry_ts') or '')[:10]
    return d if re.match(r'^\d{4}-\d{2}-\d{2}$', d) else None


def _is_shadow(t):
    return t.get('shadow') is True or str(t.get('shadow') or '').lower() == 'true' or str(t.get('layer') or '').lower() == 'shadow'


def _js_round(x):
    return int(math.floor(x + 0.5))


def signed(v):
    """index.html ledgerSigned: '+$1.00' / '-$1.00' (a zero reads '+$0.00')."""
    return ('+' if v >= 0 else '-') + money(abs(v))


def short_money(v):
    """index.html ledgerShortMoney without its sign: $276, $1.2k, $12k."""
    a = abs(v)
    if a >= 10000:
        return '$%dk' % _js_round(a / 1000)
    if a >= 1000:
        s = '%.1f' % (a / 1000)
        return '$' + (s[:-2] if s.endswith('.0') else s) + 'k'
    return '$%d' % _js_round(a)


def _fin(v):
    """index.html qeFinRec: a finite number, else None (null / '' / text / NaN are missing)."""
    if v is None or v == '':
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if (v == v and v not in (float('inf'), float('-inf'))) else None


def _range_rows(trades, cutoff=None):
    """The trades the stats count: shadow rows left out, closed on or after `cutoff`, in exit order."""
    rows = [t for t in trades if not _is_shadow(t)]
    if cutoff:
        rows = [t for t in rows if (_close_day(t) or '') >= cutoff]
    return sorted(rows, key=lambda t: str(t.get('exit_ts') or t.get('entry_ts') or ''))


def expected_more(trades, cutoff=None):
    """More stats rows worked out here: {'Group|Label': value text}, or {} when the range is empty."""
    rows = _range_rows(trades, cutoff)
    if not rows:
        return {}
    vals = [qe_pnl_of(t) for t in rows]
    net = run = peak = dd = 0.0
    for v in vals:
        net += v
        run += v
        peak = max(peak, run)
        dd = max(dd, peak - run)
    broker = book = 0.0
    bo = wb = 0
    for t in rows:
        if t.get('book_only'):
            bo += 1
        else:
            broker += qe_pnl_of(t)
            a, r = _fin(t.get('pnl')), _fin(t.get('real_pnl'))
            book += a if a is not None else (r if r is not None else 0.0)
        if str(t.get('pnl_record_src') or '') == 'webull':
            wb += 1
    n = len(rows)
    # the current streak, walked back from the newest exit ($0 trades skipped), as ledgerStats counts it
    sn = sd = 0
    for v in reversed(vals):
        if not v:
            continue
        d = 1 if v > 0 else -1
        if not sn:
            sn, sd = 1, d
        elif d == sd:
            sn += 1
        else:
            break
    streak = '--' if not sn else '%d %s' % (sn, ('wins' if sn > 1 else 'win') if sd > 0 else ('losses' if sn > 1 else 'loss'))
    return {'Returns|Net P&L': signed(net), 'Risk|Max drawdown': money(dd), 'Risk|Current streak': streak,
            'Account|Broker made': signed(broker), 'Account|Book figure': signed(book),
            'Account|Book-only trades': '%d of %d' % (bo, n),
            'Account|Fill coverage': '%d of %d (%d%%)' % (wb, n, _js_round(wb / n * 100)),
            'Best and worst trade|Best trade': signed(max(vals)),
            'Best and worst trade|Worst trade': signed(min(vals))}


def expected_stats(trades, cutoff=None):
    """The four LEDGER tiles worked out here, not read off the page: the trades that closed on or after
    `cutoff` (None = all), shadow rows left out, walked in exit order at the P&L of record. A $0 trade is
    neither a win nor a loss. Returns {key: (value text, sub text)}."""
    rows = _range_rows(trades, cutoff)
    vals = [qe_pnl_of(t) for t in rows]
    n = len(vals)
    w = sum(1 for v in vals if v > 0)
    l = sum(1 for v in vals if v < 0)
    f = n - w - l
    gw = sum(v for v in vals if v > 0)
    gl = -sum(v for v in vals if v < 0)
    run = peak = dd = 0.0
    for v in vals:
        run += v
        peak = max(peak, run)
        dd = max(dd, peak - run)
    days = len(set(d for d in (_close_day(t) for t in rows) if d))
    if not n:
        return {'winrate': ('--', ''), 'pf': ('--', ''), 'maxdd': ('--', ''), 'trades': ('0', '')}
    wr = ('%d%%' % _js_round(w / (w + l) * 100)) if (w + l) else '--'
    pf = '--' if (not gw and not gl) else ('%.2f' % (gw / gl) if gl > 0 else 'no losses')
    return {'winrate': (wr, '%d W · %d L' % (w, l) + (' · %d even' % f if f else '')),
            'pf': (pf, ('%s won · %s lost' % (short_money(gw), short_money(gl))) if (gw or gl) else ''),
            'maxdd': (money(dd), 'worst drop from a high' if dd > 0 else ''),
            'trades': (str(n), 'over %d day%s' % (days, '' if days == 1 else 's'))}


def month_won(trades, month):
    """The calendar's '% won' for one month: wins / (wins + losses), a $0 trade is neither."""
    vals = [qe_pnl_of(t) for t in trades if (_close_day(t) or '').startswith(month)]
    w = sum(1 for v in vals if v > 0)
    l = sum(1 for v in vals if v < 0)
    return _js_round(w / (w + l) * 100) if (w + l) else None


def _zero_doc(fixture):
    """The fixture with its newest September loss turned into a $0 trade (P&L of record 0)."""
    doc = json.loads(json.dumps(fixture))
    for t in doc.get('trades_all') or []:
        if (_close_day(t) or '').startswith('2026-09') and qe_pnl_of(t) < 0:
            t['pnl_record'] = 0.0
            t['pnl'] = '0.0'
            break
    return doc


def _cutoff(range_key, today=STAT_TODAY):
    """index.html ledgerCutoff: the first New York day a range keeps (None = ALL)."""
    if range_key == 'TODAY':
        return today
    if range_key == 'YTD':
        return today[:4] + '-01-01'
    days = {'1W': 7, '1M': 30, '3M': 90}.get(range_key)
    if not days:
        return None
    y, m, d = map(int, today.split('-'))
    import datetime
    return (datetime.date(y, m, d) - datetime.timedelta(days=days)).isoformat()


SHADOW_PNL = 5000.0


def _shadow_doc(fixture):
    """The fixture plus one shadow row worth $5,000 that closed today: it must change no stat."""
    doc = json.loads(json.dumps(fixture))
    tr = doc.get('trades_all') or []
    last = max(tr, key=lambda t: str(t.get('exit_ts') or ''))
    s = json.loads(json.dumps(last))
    s.update({'shadow': True, 'pnl_record': SHADOW_PNL, 'pnl': str(SHADOW_PNL), 'real_pnl': str(SHADOW_PNL),
              'exit_ts': STAT_TODAY + ' 15:50:00', 'trade_id': 'NOISE-20261005T195000Z-L', 'book_only': False})
    tr.append(s)
    return doc


# LEDGER unify steps 7 + 10: the shared calendar and the shared strategy list, recomputed here from the fixture (never read off
# the page). The calendar takes the chosen range's trades at the P&L of record on their close day; the list's rows are the legs
# the board names (ORB #314, ENGU-Q #335, NOISE #382), the range's P&L of record, trades and win rate.
LIST_GROUPS = ['book', 'retired', 'shadow']
BOOK_NAMES = ['ORB #314', 'NOISE #382']       # the rows under BOOK, run numbers included (ENGU-Q #335 is retired in this doc)
RETIRED_NAME = 'ENGU-Q #335'
BOOK_NAMES_LIVE = ['ORB #314', 'ENGU-Q #335', 'NOISE #382']   # while ENGU-Q holds a position it is a BOOK leg again
LEG_KEYS = [('ORB', 'ORB #314'), ('ENGUQ', 'ENGU-Q #335'), ('NOISE', 'NOISE #382')]
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November',
          'December']
RANGE_WORD = {'TODAY': 'today', '1W': 'past week', '1M': 'past month', '3M': 'past 3 months', 'YTD': 'year to date',
              'ALL': 'all time'}
LIST_VH_MAX = 1.0   # phone: the trade list (the History section) starts within this many viewport heights of the board top
PHONE_ROW_MAX_H = 46  # phone: one line per strategy row (padding 9 + 9, one 12 px line)
SHADOW_NOTE = 'None are in the box'
NOTE_MARK = 'was #304'          # NOISE's note under its row: 'since Sep 24 · was #304 · KEEL v12 ...'
OTHER_NAME = 'Other legs'       # the list's row for trades of a strategy the board has no row for
OTHER_LEG = 'TTM'


def _grey(css):
    """'rgb(r, g, b)' / 'rgba(r, g, b, a)' with r = g = b (MONO has no hue); a clear colour passes."""
    p = [float(x) for x in re.findall(r'[\d.]+', css or '')]
    if len(p) >= 4 and p[3] == 0:
        return True
    return len(p) >= 3 and p[0] == p[1] == p[2]


def _money_val(txt):
    """'+$41.11' / '-$1,234.50' -> float, else None."""
    m = re.match(r'^([+-])\$([\d,]+\.\d\d)$', (txt or '').strip())
    return None if not m else (-1 if m.group(1) == '-' else 1) * float(m.group(2).replace(',', ''))


def expected_cal(trades, cutoff=None):
    """{day: {'v': money, 'n': trades, 'w': wins, 'l': losses}} -- what the calendar draws: the range's trades (shadow
    rows left out) at the P&L of record on the New York day each one closed. A $0 trade is neither a win nor a loss."""
    days = {}
    for t in _range_rows(trades, cutoff):
        d = _close_day(t)
        if not d:
            continue
        c = days.setdefault(d, {'v': 0.0, 'n': 0, 'w': 0, 'l': 0})
        v = qe_pnl_of(t)
        c['v'] += v
        c['n'] += 1
        if v > 0:
            c['w'] += 1
        elif v < 0:
            c['l'] += 1
    return days


def expected_caveats(trades, feed_days, cutoff=None):
    """{day: {reasons}} -- the days the calendar hatches: an exit priced from the 1-minute tape (no book pnl, a re-priced one),
    a failed parity check (the NinjaTrader one for a mirrored row, else engine against broker), a book-only trade, or a feed
    flagged invalid (that one needs no trade on the day)."""
    out = {}
    for t in _range_rows(trades, cutoff):
        d = _close_day(t)
        if not d:
            continue
        if _fin(t.get('pnl')) is None and _fin(t.get('real_pnl')) is not None:
            out.setdefault(d, set()).add('tape')
        nt = str(t.get('signal_source') or '').lower() == 'ninjatrader'
        if (t.get('parity_ok') is False) if nt else (t.get('broker_parity_ok') is False):
            out.setdefault(d, set()).add('parity')
        if t.get('book_only'):
            out.setdefault(d, set()).add('book')
    for f in feed_days or []:
        d = f.get('date')
        if d and f.get('valid') is False and (not cutoff or d >= cutoff):
            out.setdefault(d, set()).add('feed')
    return out


def cal_month_figs(days, month):
    """(money, trades, wins, losses) of one month of expected_cal()."""
    v = n = w = l = 0
    for d, c in days.items():
        if d.startswith(month):
            v += c['v']
            n += c['n']
            w += c['w']
            l += c['l']
    return v, n, w, l


def cal_sum_text(v, n, w, l):
    """The summary beside the month title: '-$53.65 · 3 trades · 0% won' (no win rate without a win or a loss)."""
    if not n:
        return 'no trades this month'
    s = '%s · %d trade%s' % (signed(round(v, 2)), n, '' if n == 1 else 's')
    if w + l:
        s += ' · %d%% won' % _js_round(w / (w + l) * 100)
    return s


def cal_weeks(days, month):
    """One entry per Sunday-first week of the month: {'v', 'n'} for a week with trades, None for an empty week."""
    import calendar
    import datetime
    y, m = int(month[:4]), int(month[5:7])
    first = (datetime.date(y, m, 1).weekday() + 1) % 7      # Sunday = 0
    nweeks = (first + calendar.monthrange(y, m)[1] + 6) // 7
    weeks = [None] * nweeks
    for d, c in days.items():
        if d.startswith(month):
            i = (int(d[8:10]) + first - 1) // 7
            w = weeks[i] or {'v': 0.0, 'n': 0}
            w['v'] += c['v']
            w['n'] += c['n']
            weeks[i] = w
    return weeks


def short_signed(v):
    """index.html ledgerShortMoney with its sign: '+$1.2k' / '-$47'."""
    return ('-' if v < 0 else '+') + short_money(v)


def _row_figs(vals):
    """One list row's figures from its trades' P&L of record: the signed total ('—' with no trade), 'N trades · X% won'
    (a $0 trade is neither a win nor a loss), the total and the trade count."""
    n = len(vals)
    net = round(sum(vals), 2)
    w = sum(1 for v in vals if v > 0)
    l = sum(1 for v in vals if v < 0)
    v2 = '%d trade%s' % (n, '' if n == 1 else 's') + ((' · %d%% won' % _js_round(w / (w + l) * 100)) if (w + l) else '')
    return {'value': signed(net) if n else '—', 'value2': v2, 'net': net, 'n': n}


def expected_leg_figs(trades, cutoff=None):
    """{row name: {'value', 'value2', 'net', 'n'}} -- each leg's range: its P&L of record (signed), its trades and win rate."""
    rows = _range_rows(trades, cutoff)
    return dict((nm, _row_figs([qe_pnl_of(t) for t in rows if t.get('leg') == key])) for key, nm in LEG_KEYS)


def expected_other_figs(trades, cutoff=None):
    """The 'Other legs' row: the range's trades of a strategy the board has no row for (not ORB, ENGU-Q or NOISE), else None."""
    keys = set(k for k, _ in LEG_KEYS)
    f = _row_figs([qe_pnl_of(t) for t in _range_rows(trades, cutoff) if t.get('leg') not in keys])
    return f if f['n'] else None


def expected_list_count(trades, cutoff, range_key):
    """The list's header figure: the range's P&L of record and its word, or the board's 'no trades' line."""
    rows = _range_rows(trades, cutoff)
    if not rows:
        return {'TODAY': 'no trades closed today', 'YTD': 'no trades closed this year'}.get(range_key) \
            or ('no trades closed in the ' + RANGE_WORD[range_key])
    return '%s · %s' % (signed(round(sum(qe_pnl_of(t) for t in rows), 2)), RANGE_WORD[range_key])


def expected_shadow_rows(trades, cutoff=None):
    """{row name: signed money} of the no-order shadow rows in the range (the list's Shadow group, never counted)."""
    out = {}
    for t in trades:
        if not _is_shadow(t):
            continue
        d = _close_day(t) or ''
        if cutoff and d < cutoff:
            continue
        nm = expected_leg_name(t)
        out[nm] = out.get(nm, 0.0) + qe_pnl_of(t)
    return dict((k, signed(round(v, 2))) for k, v in out.items())


def _positions(doc):
    """{leg: (Long or Short, shares, entry price)} of the doc's open positions (the status doc's own positions map)."""
    out = {}
    for k, v in (doc.get('positions') or {}).items():
        try:
            out[k] = ('Long' if v.get('side') == 'long' else 'Short', int(float(v.get('shares'))), float(v.get('entry_px')))
        except (TypeError, ValueError, AttributeError):
            pass
    return out


def _cal_open_want(vp, cal_open):
    """open on a laptop, closed on a phone until a viewer chooses; a stored choice wins."""
    if cal_open in ('0', '1'):
        return cal_open == '1'
    return vp == 'laptop'


def _judge_cal(tag, c, vp, theme, doc, cutoff, want_month, open_want, today, fails):
    """The shared calendar under Activity: fold and summary, the month, every day cell, the caveat hatching, the week cells and
    the arrows -- all against the fixture's own trades at the P&L of record on their close day."""
    c = c or {}
    if c.get('fold') is None:
        fails.append('%s: no shared calendar ([data-lgcalfold="qb"]) under Activity' % tag)
        return
    if c.get('oldDays') or c.get('oldNav'):
        fails.append('%s: the old month grid is still drawn beside the shared calendar' % tag)
    trades = doc.get('trades_all') or []
    days = expected_cal(trades, cutoff)
    months = sorted(set(d[:7] for d in days))
    mo = want_month if want_month in months else (months[-1] if months else today[:7])
    y, m = int(mo[:4]), int(mo[5:7])
    tot, n, w_, l_ = cal_month_figs(days, mo)
    if (c.get('fold') == 'true') != open_want or (c.get('panel') == 'shown') != open_want:
        fails.append('%s: the calendar fold reads aria-expanded %r with its panel %s, want %s (open on a laptop, closed on a phone '
                     'until chosen)' % (tag, c.get('fold'), c.get('panel'), 'open' if open_want else 'closed'))
    ft = c.get('foldText') or ''
    if '%s %d' % (MONTHS[m - 1], y) not in ft or (n and signed(round(tot, 2)) not in ft):
        fails.append("%s: the calendar fold reads %r, want the month %s %d and its total %s"
                     % (tag, ft, MONTHS[m - 1], y, signed(round(tot, 2)) if n else '(no trades)'))
    if not open_want:
        return
    if c.get('month') != mo or c.get('title') != '%s %d' % (MONTHS[m - 1], y):
        fails.append('%s: the calendar shows %r (%r), want %s' % (tag, c.get('month'), c.get('title'), mo))
        return
    want_sum = cal_sum_text(tot, n, w_, l_)
    if c.get('sum') != want_sum:
        fails.append('%s: the calendar month total reads %r, the fixture says %r (the sum of that month\'s trades at the P&L '
                     'of record)' % (tag, c.get('sum'), want_sum))
    nav = dict((k, dis) for k, dis in (c.get('nav') or []))
    want_nav = {'-1': (not months) or mo == months[0], '1': (not months) or mo == months[-1]}
    if nav != want_nav:
        fails.append('%s: the month arrows read disabled %r (earlier / later), want %r (disabled at the first and last month '
                     'with trades)' % (tag, nav, want_nav))
    got = dict((x['ds'], x) for x in (c.get('days') or []) if x.get('traded'))
    exp = dict((d, v) for d, v in days.items() if d.startswith(mo))
    if sorted(got) != sorted(exp):
        fails.append('%s: the calendar draws trades on %s, the fixture has them on %s'
                     % (tag, sorted(d[8:] for d in got), sorted(d[8:] for d in exp)))
    page_sum = 0.0
    for d, v in exp.items():
        x = got.get(d)
        if not x:
            continue
        if x.get('m') != short_signed(v['v']) or x.get('n') != '%d tr' % v['n']:
            fails.append('%s: calendar day %s reads %r / %r, the fixture says %s / %d tr'
                         % (tag, d, x.get('m'), x.get('n'), short_signed(v['v']), v['n']))
        tm = re.search(r': ([+-]\$[\d,]+\.\d\d),', x.get('title') or '')
        if not tm or tm.group(1) != signed(round(v['v'], 2)):
            fails.append('%s: calendar day %s says %r, the fixture says %s'
                         % (tag, d, x.get('title'), signed(round(v['v'], 2))))
        else:
            page_sum += _money_val(tm.group(1))
        if (x.get('up'), x.get('down')) != (v['v'] >= 0, v['v'] < 0):
            fails.append('%s: calendar day %s is drawn %s' % (tag, d, 'up' if x.get('up') else 'down' if x.get('down') else 'flat'))
    if exp and abs(page_sum - round(tot, 2)) > 0.011:
        fails.append("%s: the day cells print %s, the month total says %s" % (tag, signed(round(page_sum, 2)), signed(round(tot, 2))))
    cav = expected_caveats(trades, doc.get('feed_days'), cutoff)
    want_cav = sorted(int(d[8:10]) for d in cav if d.startswith(mo))
    got_cav = sorted(x['d'] for x in c.get('days') or [] if x.get('cav'))
    if got_cav != want_cav:
        fails.append('%s: the hatched caveat days are %s, the fixture says %s (tape-priced exit, failed parity, book only, '
                     'feed invalid)' % (tag, got_cav, want_cav))
    unhatched = [x['d'] for x in c.get('days') or [] if x.get('cav') and not (x.get('hatch') and x.get('dot'))]
    if unhatched:
        fails.append('%s: caveat days %s are marked but not hatched amber with the dot' % (tag, unhatched))
    ew, gw = cal_weeks(days, mo), c.get('weeks') or []
    if len(gw) != len(ew):
        fails.append('%s: the calendar has %d week cells, want %d' % (tag, len(gw), len(ew)))
    else:
        for i, (e, g) in enumerate(zip(ew, gw)):
            if e is None:
                if g.get('title') or g.get('m'):
                    fails.append('%s: calendar week %d has no trades but reads %r (an empty week is empty, never $0)'
                                 % (tag, i + 1, g.get('m')))
            else:
                want_t = 'week: %s, %d trade%s' % (signed(round(e['v'], 2)), e['n'], '' if e['n'] == 1 else 's')
                if g.get('title') != want_t or g.get('m') != short_signed(e['v']) or g.get('n') != '%d tr' % e['n']:
                    fails.append('%s: calendar week %d reads %r / %r, the fixture says %r' % (tag, i + 1, g.get('title'), g.get('m'), want_t))
    if theme == 'mono':
        bad = [x['mColor'] for x in c.get('days') or [] if x.get('mColor') and not _grey(x['mColor'])] \
            + [s for s in c.get('sumColors') or [] if not _grey(s)]
        if bad:
            fails.append('%s: the calendar draws colour under MONO (MONO has no hue): %s' % (tag, bad[:3]))
    if c.get('gridW') and c.get('box') and c['gridW'] > c['box']['w'] + 1:
        fails.append('%s: the calendar grid (%s px) is wider than its panel (%s px)' % (tag, c['gridW'], c['box']['w']))


def _judge_list(tag, lg, vp, theme, doc, cutoff, range_key, retired_open, shadow_open, fails, distance=True):
    """The strategy list on the shared list: its three groups in order, the BOOK rows named with run numbers and carrying the
    range's P&L of record, trades and win rate, the Retired and Shadow folds closed (their rows outside the account number),
    no switch, and where it sits: under the trade list on a phone, the sticky right column on a laptop."""
    if not lg:
        fails.append('%s: no strategy list on the shared list ([data-lglist="qb"] in the side column)' % tag)
        return
    trades = doc.get('trades_all') or []
    groups = lg.get('groups') or []
    keys = [g['key'] for g in groups]
    pos = _positions(doc)
    live = 'ENGUQ' in pos     # a retired leg that holds a position is a BOOK leg again (owner decision 9): no Retired group then
    want_keys = [k for k in LIST_GROUPS if not (live and k == 'retired')]
    if keys != want_keys:
        fails.append('%s: the strategy list groups are %r, want %r (BOOK, Retired, Shadow - not counted; no Retired group while '
                     'ENGU-Q holds a position)' % (tag, keys, want_keys))
        return
    by = dict((g['key'], g) for g in groups)
    if lg.get('title') != 'Strategies' or lg.get('count') != expected_list_count(trades, cutoff, range_key):
        fails.append('%s: the list header reads %r / %r, want Strategies / %r'
                     % (tag, lg.get('title'), lg.get('count'), expected_list_count(trades, cutoff, range_key)))
    if lg.get('sw'):
        fails.append('%s: the list draws %d switches; this board has none (every leg counts)' % (tag, lg['sw']))
    figs = expected_leg_figs(trades, cutoff)
    other = expected_other_figs(trades, cutoff)
    want_names = (BOOK_NAMES_LIVE if live else BOOK_NAMES) + ([OTHER_NAME] if other else [])
    if other:
        figs[OTHER_NAME] = other
    bk = by['book']
    if bk.get('fold') or not (bk.get('head') or '').upper().startswith('BOOK') or ('· %d' % len(want_names)) not in (bk.get('head') or ''):
        fails.append('%s: the BOOK group reads %r (fold %s)' % (tag, bk.get('head'), bk.get('fold')))
    names = [x['name'] for x in bk.get('rows') or []]
    if names != want_names:
        fails.append('%s: the BOOK rows are %r, want %r (family + run number, from the leg definitions%s)'
                     % (tag, names, want_names, ', and an Other legs row for a strategy with no row' if other else ''))
    for x in bk.get('rows') or []:
        is_other = x.get('name') == OTHER_NAME
        if not is_other and not LEG_RE.match(x.get('name') or ''):
            fails.append('%s: list row %r has no family + run number' % (tag, x.get('name')))
        e = figs.get(x.get('name'))
        if e and (x.get('value') != e['value'] or x.get('value2') != e['value2']):
            fails.append('%s: list row %s reads %r / %r, the fixture says %r / %r (the range\'s P&L of record, trades, win rate)'
                         % (tag, x.get('name'), x.get('value'), x.get('value2'), e['value'], e['value2']))
        pz = pos.get(x.get('key'))
        want_side = ('LONG' if pz[0] == 'Long' else 'SHORT') if pz else 'FLAT'
        if not is_other and not (x.get('tag') or '').startswith(want_side):
            fails.append('%s: list row %s carries the side %r, want %s' % (tag, x.get('name'), x.get('tag'), want_side))
        if pz and not vp.startswith('phone') and ('%s %d @ %s' % (pz[0], pz[1], money(pz[2]))) not in (x.get('sub') or ''):
            fails.append('%s: list row %s shows %r under its name, want the live position %s %d @ %s'
                         % (tag, x.get('name'), x.get('sub'), pz[0], pz[1], money(pz[2])))
    rt = by.get('retired')
    if rt and (not rt.get('fold') or ('Retired' not in (rt.get('head') or '')) or ('flat since ' + RETIRED_SINCE) not in (rt.get('head') or '')):
        fails.append('%s: the Retired group reads %r (fold %s), want a fold saying "flat since %s"'
                     % (tag, rt.get('head'), rt.get('fold'), RETIRED_SINCE))
    sh = by['shadow']
    shadow = expected_shadow_rows(trades, cutoff)
    if not sh.get('fold') or (sh.get('head') or '').replace('▾', '').strip() != 'Shadow - not counted · %d' % len(shadow):
        fails.append('%s: the Shadow group reads %r (fold %s), want a fold reading "Shadow - not counted · %d"'
                     % (tag, sh.get('head'), sh.get('fold'), len(shadow)))
    for g, is_open in [z for z in ((rt, retired_open), (sh, shadow_open)) if z[0]]:
        want_open = 'true' if is_open else 'false'
        if g.get('expanded') != want_open:
            fails.append('%s: the %s group is aria-expanded=%r, want %r (closed until a viewer opens it)'
                         % (tag, g.get('key'), g.get('expanded'), want_open))
        if (not is_open) and g.get('rows'):
            fails.append('%s: the %s group draws %d rows while closed' % (tag, g.get('key'), len(g['rows'])))
    if (retired_open and rt) or live:
        if rt:
            rn = [x['name'] for x in rt.get('rows') or []]
            if rn != [RETIRED_NAME]:
                fails.append('%s: the Retired rows are %r, want %r' % (tag, rn, [RETIRED_NAME]))
            elif rt['rows'][0].get('value') != figs[RETIRED_NAME]['value'] or rt['rows'][0].get('value2') != figs[RETIRED_NAME]['value2']:
                fails.append('%s: the Retired row reads %r / %r, the fixture says %r / %r' % (
                    tag, rt['rows'][0].get('value'), rt['rows'][0].get('value2'), figs[RETIRED_NAME]['value'], figs[RETIRED_NAME]['value2']))
        # the rows add up to the account's range figure: BOOK + Retired are the legs that count, Shadow is never in it
        counted = [_money_val(x.get('value')) for g in (bk, rt) if g for x in g.get('rows') or []]
        want_tot = round(sum(qe_pnl_of(t) for t in _range_rows(trades, cutoff)), 2)
        if None not in counted and abs(sum(counted) - want_tot) > 0.011:
            fails.append('%s: BOOK + Retired add up to %s, the P&L of record of the range is %s (a shadow leg, or a leg with no row, '
                         'moved the list off the account number)' % (tag, signed(round(sum(counted), 2)), signed(want_tot)))
    if shadow_open:
        sn = dict((x['name'], x['value']) for x in sh.get('rows') or [])
        if sn != shadow:
            fails.append('%s: the Shadow rows are %r, the fixture says %r' % (tag, sn, shadow))
        if any(not x.get('off') for x in sh.get('rows') or []):
            fails.append('%s: a shadow row is not drawn faded (it is not counted)' % tag)
    rows = [x for g in groups for x in g.get('rows') or []]
    if vp.startswith('phone'):
        tall = [(x['name'], x['h']) for x in rows if x.get('h', 0) > PHONE_ROW_MAX_H]
        if tall:
            fails.append('%s: on a phone every list row is one line (<= %d px), but %s are taller' % (tag, PHONE_ROW_MAX_H, tall[:3]))
        if any(x.get('value2Shown') or x.get('subShown') for x in rows):
            fails.append('%s: on a phone a list row still shows its second line' % tag)
    else:
        if any(x.get('value2') and not x.get('value2Shown') for x in rows):
            fails.append('%s: on a laptop the trades / win rate line under the money is hidden' % tag)
    if theme == 'mono':
        bad = [x['valColor'] for x in rows if x.get('valColor') and not _grey(x['valColor'])]
        if bad:
            fails.append('%s: a list row draws its money in colour under MONO (MONO has no hue): %s' % (tag, bad[:3]))
    g = lg.get('geo') or {}
    if vp.startswith('phone'):
        if g.get('listTop') is None or g.get('histBottom') is None or g['listTop'] < g['histBottom'] - 1:
            fails.append('%s: on a phone the strategy list (top %s) is not under the trade list (bottom %s)'
                         % (tag, g.get('listTop'), g.get('histBottom')))
        if g.get('acctTop') is not None and g.get('histBottom') is not None and g['acctTop'] < g['histBottom'] - 1:
            fails.append('%s: on a phone the Account section (top %s) is above the trade list (bottom %s)'
                         % (tag, g['acctTop'], g['histBottom']))
        if distance and (g.get('histTop') is None or g.get('shellTop') is None or g['histTop'] - g['shellTop'] > LIST_VH_MAX * g['vh']):
            fails.append('%s: on a phone the trade list starts %s px under the top of the board (%.2f viewports of %s px); it must '
                         'start within %.1f (mistake #12)' % (tag, (g.get('histTop') or 0) - (g.get('shellTop') or 0),
                         ((g.get('histTop') or 0) - (g.get('shellTop') or 0)) / (g.get('vh') or 1), g.get('vh'), LIST_VH_MAX))
    else:
        if g.get('listLeft') is None or g.get('histRight') is None or g['listLeft'] < g['histRight'] - 1:
            fails.append('%s: on a laptop the strategy list (left %s) is not in the right column (trade list right edge %s)'
                         % (tag, g.get('listLeft'), g.get('histRight')))
        if g.get('sticky') != 'sticky':
            fails.append('%s: on a laptop the strategy column is position %r, want sticky' % (tag, g.get('sticky')))


def _judge_inter_ledger(tag, res, fixture, fails):
    """The interaction run's LEDGER steps 7 + 10 part: the Retired fold open (the list adds up to the account's figure), the
    Shadow fold, a leg row's detail, the table view's run numbers, and the calendar -- day taps, month arrows, fold, and what a
    reload finds."""
    trades = fixture.get('trades_all') or []
    o = res.get('open') or {}
    _judge_list(tag + ' [Retired open]', o.get('list'), 'laptop', 'dark', fixture, None, 'ALL', True, False, fails)
    sd = res.get('shadow') or {}
    if not sd:
        fails.append('%s: no Shadow group to open ([data-lggrp="shadow"])' % tag)
    else:
        so, sc2 = sd.get('open') or {}, sd.get('closed') or {}
        if so.get('expanded') != 'true' or so.get('rows') or SHADOW_NOTE not in (so.get('note') or '') or sd.get('stored') != '1':
            fails.append('%s: the Shadow group did not open with its note and the choice kept (%s, stored %r)'
                         % (tag, {k: so.get(k) for k in ('expanded', 'rows', 'note')}, sd.get('stored')))
        if sc2.get('expanded') != 'false' or sc2.get('rows') or sd.get('stored2') != '0':
            fails.append('%s: the Shadow group did not close again (%s, stored %r)' % (tag, sc2.get('expanded'), sd.get('stored2')))
    lw = res.get('legrow') or {}
    fig = expected_leg_figs(trades)['NOISE #382']
    if lw.get('expanded') != 'true' or any(s not in (lw.get('detail') or '') for s in ('SINCE START', 'UNREALIZED', 'POSITION', fig['value'])):
        fails.append('%s: a tap on the NOISE row did not open its detail under it with since start %s (aria-expanded %r, text %r)'
                     % (tag, fig['value'], lw.get('expanded'), _first(lw.get('detail'), 160)))
    if lw.get('expandedAfter') != 'false' or lw.get('detailAfter'):
        fails.append('%s: a second tap on the NOISE row did not close its detail again (%r, detail still there: %s)'
                     % (tag, lw.get('expandedAfter'), lw.get('detailAfter')))
    inf = res.get('info') or {}
    if not inf:
        fails.append('%s: no note toggle on the NOISE row ([data-qbleginfo="NOISE"])' % tag)
    else:
        if inf.get('titleBefore') != 'show note' or NOTE_MARK in (inf.get('noteBefore') or ''):
            fails.append('%s: the NOISE note is open before any tap (toggle title %r)' % (tag, inf.get('titleBefore')))
        if NOTE_MARK not in (inf.get('note') or '') or inf.get('title') != 'hide note':
            fails.append('%s: a tap on the NOISE note toggle did not show its note under the row (toggle title %r, text %r)'
                         % (tag, inf.get('title'), _first(inf.get('note'), 120)))
        if inf.get('expanded') != 'false' or inf.get('detail'):
            fails.append("%s: a tap on the NOISE note toggle also opened the row's detail (aria-expanded %r, detail drawn: %s)"
                         % (tag, inf.get('expanded'), inf.get('detail')))
        if NOTE_MARK in (inf.get('noteAfter') or '') or inf.get('expandedAfter') != 'false':
            fails.append('%s: a second tap on the NOISE note toggle did not hide the note again (aria-expanded %r)'
                         % (tag, inf.get('expandedAfter')))
    tv = (res.get('table') or {}).get('legs')
    if tv is None:
        fails.append('%s: no Table view to read ([data-qbsegval="table"])' % tag)
    else:
        bad = [x for x in tv if not LEG_RE.match(x or '')]
        if bad or len(tv) != min(len(trades), 50):
            fails.append('%s: the Table view names strategies without family + run number: %s (%d rows for %d trades)'
                         % (tag, sorted(set(map(str, bad)))[:4], len(tv), len(trades)))
        elif len(trades) <= 50 and collections.Counter(tv) != collections.Counter(expected_leg_name(t) for t in trades):
            fails.append('%s: the Table view names the wrong run on a row' % tag)
    tdays = (res.get('table') or {}).get('days')
    if tdays is not None and len(trades) <= 50 and collections.Counter(tdays) != collections.Counter(_close_day(t) or '' for t in trades):
        fails.append('%s: the Table view rows carry the wrong close day (data-qbday), so a calendar tap cannot land on them' % tag)
    ca = res.get('cal') or {}
    if not ca:
        fails.append('%s: no calendar run to read' % tag)
        return

    def tapped(lst, day):
        return bool(lst) and lst[0].get('day') == day
    _judge_cal(tag + ' [calendar, October]', ca.get('start'), 'laptop', 'dark', fixture, None, None, True, STAT_TODAY, fails)
    if not tapped(ca.get('tapOct'), '2026-10-02') or not ca.get('flashOct'):
        fails.append("%s: a tap on Oct 2 did not scroll the trade list to that day's row and flash it (scrolled to %r, flash %s)"
                     % (tag, ca.get('tapOct'), ca.get('flashOct')))
    _judge_cal(tag + ' [calendar, after the earlier arrow]', ca.get('sept'), 'laptop', 'dark', fixture, None, '2026-09', True, STAT_TODAY, fails)
    if ca.get('storedMonth') != '2026-09' or ca.get('memMonth') != '2026-09':
        fails.append('%s: the earlier arrow did not keep the month for this viewer (stored %r, in memory %r)'
                     % (tag, ca.get('storedMonth'), ca.get('memMonth')))
    if not tapped(ca.get('tapSep'), '2026-09-23'):
        fails.append("%s: a tap on Sep 23 did not scroll the trade list to that day's row (scrolled to %r)" % (tag, ca.get('tapSep')))
    _judge_cal(tag + ' [calendar, folded]', ca.get('closed'), 'laptop', 'dark', fixture, None, '2026-09', False, STAT_TODAY, fails)
    if ca.get('storedOpen') != '0':
        fails.append('%s: closing the calendar did not keep the choice for this viewer (stored %r)' % (tag, ca.get('storedOpen')))
    _judge_cal(tag + ' [calendar, after a reload]', ca.get('reload'), 'laptop', 'dark', fixture, None, '2026-09', False, STAT_TODAY, fails)
    _judge_cal(tag + ' [calendar, reopened]', ca.get('reopen'), 'laptop', 'dark', fixture, None, '2026-09', True, STAT_TODAY, fails)
    if ca.get('storedOpen2') != '1':
        fails.append('%s: opening the calendar again did not keep the choice (stored %r)' % (tag, ca.get('storedOpen2')))
    _judge_cal(tag + ' [calendar, after the later arrow]', ca.get('oct'), 'laptop', 'dark', fixture, None, '2026-10', True, STAT_TODAY, fails)
    if not ca.get('moreDay') or ca.get('moreHadRow'):
        fails.append("%s: the probe's own SHOW MORE case is wrong (day %r, its row already on the page: %s)"
                     % (tag, ca.get('moreDay'), ca.get('moreHadRow')))
    elif not tapped(ca.get('moreSpy'), ca['moreDay']) or not ca.get('moreHasRow') or ca.get('moreRowsAfter') != len(trades):
        fails.append("%s: a tap on %s, whose rows were not on the page yet (%s rows shown), did not draw every row and scroll to that "
                     "day's newest trade (rows after %s of %d, scrolled to %r)"
                     % (tag, ca['moreDay'], ca.get('moreRowsBefore'), ca.get('moreRowsAfter'), len(trades), ca.get('moreSpy')))


def _other_doc(fixture):
    """The fixture with its last two ORB trades turned into a strategy the board has no row for (the box started publishing a
    leg before the page learned its name): the list must still add up to the account's figure, so it draws an Other legs row."""
    doc = json.loads(json.dumps(fixture))
    orb = [t for t in doc.get('trades_all') or [] if t.get('leg') == 'ORB']
    for t in sorted(orb, key=lambda t: str(t.get('exit_ts') or ''))[-2:]:
        t['leg'] = OTHER_LEG
    return doc


def _enguq_open_doc(fixture):
    """The fixture with ENGU-Q long 10 @ 600.10 (live 600.52): a retired leg that holds a position is a BOOK leg again (owner
    decision 9), so the list has no Retired group, ENGU-Q reads LONG with its live position line, and the rows still add up."""
    doc = json.loads(json.dumps(fixture))
    doc.setdefault('positions', {})['ENGUQ'] = {'side': 'long', 'shares': '10', 'entry_px': '600.10',
                                                'entry_ts': STAT_TODAY + ' 10:00:05', 'unrealized': '4.20'}
    doc.setdefault('positions_live', {}).update(
        {'broker_net_qty': 10, 'legs_net_qty': 10, 'total_open_pnl': 4.2,
         'legs': [{'leg': 'ENGUQ', 'side': 'long', 'shares': 10, 'entry_px': 600.1, 'live_px': 600.52, 'live_source': 'stream',
                   'live_age_s': 1.0, 'open_pnl': 4.2, 'time_in_trade_min': 3}]})
    return doc


def _stats_cases(fixture):
    """Each: name, range, doc, vp, theme, calendar month, today, more (More stats open as a reload finds
    it), empty (no trade closed in the range)."""
    z = _zero_doc(fixture)

    def c(name, rg, doc, vp='laptop', th='dark', cal=None, today=STAT_TODAY, more=False, empty=False, now=None,
          cal_open=None, folds=False):
        return {'name': name, 'range': rg, 'doc': doc, 'vp': vp, 'theme': th, 'cal': cal, 'today': today,
                'more': more, 'empty': empty, 'now': now or FRESH_NOW, 'cal_open': cal_open, 'folds': folds}
    return [c('ALL', 'ALL', fixture),
            c('1W', '1W', fixture),
            c('1W (MONO, 390x844, More stats open)', '1W', fixture, vp='phone390', th='mono', more=True, cal_open='1'),
            c('$0 trade', 'ALL', z, cal='2026-09'),
            c('TODAY', 'TODAY', fixture),
            c('1M (375x812, More stats open)', '1M', fixture, vp='phone', more=True, cal_open='1'),
            c('TODAY before the first exit (2026-10-06, More stats open)', 'TODAY', fixture, today='2026-10-06',
              more=True, empty=True, now='2026-10-06 08:00:00'),
            c('a shadow row closed today (ALL, More stats open)', 'ALL', _shadow_doc(fixture), th='mono', more=True, folds=True),
            c('an unlisted strategy leg (ALL, 375x812, both folds open)', 'ALL', _other_doc(fixture), vp='phone', folds=True),
            c('ENGU-Q holds a position (ALL, 1366x768)', 'ALL', _enguq_open_doc(fixture)),
            c('ENGU-Q holds a position (ALL, 375x812)', 'ALL', _enguq_open_doc(fixture), vp='phone')]


def _attempt(chrome, alt_index, fixture):
    pdir = tempfile.mkdtemp(prefix='_webullprobe_', dir=ROOT)
    variants = [{'name': nm, 'nowMs': now if isinstance(now, int) else et_ms(now), 'doc': doc,
                 'offline': bool(exp.get('offline')), 'missing': bool(exp.get('missing')), 'unloaded': bool(exp.get('unloaded')),
                 'pin': bool(exp.get('pin')), 'systemOpen': bool(exp.get('ordmode') or exp.get('system')),
                 'liveErr': bool(exp.get('liveErr')), 'prev': exp.get('prev'), 'prevCache': bool(exp.get('prev_cache')),
                 'tab': exp.get('tab'), 'vp': exp.get('vp', 'laptop'),
                 'renderMs': et_ms(exp['render_at']) if exp.get('render_at') else None,
                 'checkedMs': et_ms(exp['checked_at']) if exp.get('checked_at') else None,
                 'tick': bool(exp.get('tick')), 'fetch': exp.get('fetch'), 'theme': exp.get('theme', 'dark'),
                 'visread': bool(exp.get('visread')), 'cachesnap': bool(exp.get('cachesnap'))}
                for nm, now, doc, exp in _variant_docs(fixture)]
    stats = [{'name': c['name'], 'range': c['range'], 'doc': c['doc'], 'vp': c['vp'], 'theme': c['theme'],
              'calMonth': c['cal'], 'today': c['today'], 'more': c['more'], 'calOpen': c['cal_open'], 'folds': c['folds'],
              'nowMs': et_ms(c['now'])}
             for c in _stats_cases(fixture)]
    html = (PROBE_HTML.replace('__CASES__', json.dumps(CASES)).replace('__VP__', json.dumps(VIEWPORTS))
            .replace('__STATS__', json.dumps(stats))
            .replace('__NOW__', json.dumps(et_ms(FRESH_NOW))).replace('__VARS__', json.dumps(variants))
            .replace('__FIX__', json.dumps(fixture)))
    io.open(os.path.join(pdir, 'probe.html'), 'w', encoding='utf-8').write(html)
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(ROOT, alt_index))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    prof = tempfile.mkdtemp(prefix='webullprobe-')
    try:
        out = subprocess.run(
            [chrome, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
             '--user-data-dir=' + prof, '--virtual-time-budget=115000', '--window-size=1500,1000',
             '--dump-dom', 'http://127.0.0.1:%d/%s/probe.html' % (port, os.path.basename(pdir))],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300).stdout
    except Exception as e:
        return INCONCLUSIVE, ['chrome failed: %s' % e], [], None, True
    finally:
        srv.shutdown()
        shutil.rmtree(pdir, ignore_errors=True)
        shutil.rmtree(prof, ignore_errors=True)
    m = re.search(r'WEBULLPROBE: (\{.*?\})</pre>', out or '', re.S)
    if not m:
        return INCONCLUSIVE, ['probe produced no readout'], [], None, True
    try:
        data = json.loads(m.group(1).replace('&quot;', '"').replace('&lt;', '<').replace('&gt;', '>')
                          .replace('&amp;', '&'))
    except Exception as e:
        return INCONCLUSIVE, ['unreadable readout: %s' % e], [], None, True
    if os.environ.get('WEBULLPROBE_DUMP'):
        print(json.dumps(data, indent=1)[:20000])
    return _judge(data, fixture)


def _first(s, n=300):
    s = str(s or '')
    return s if len(s) <= n else s[:n] + '...'


def _errs(tag, r, fails):
    for k in ('uncaught', 'errors', 'loadErr'):
        for e in (r.get(k) or [])[:3]:
            fails.append('%s: %s -- %s' % (tag, {'uncaught': 'uncaught error', 'errors': 'console.error',
                                                'loadErr': 'LOAD ERROR'}[k], _first(e)))
    if r.get('overlay'):
        fails.append('%s: a LOAD ERROR overlay was on the page' % tag)


def _topbox(tag, r, fails):
    """The top bar WEBULL chip must be drawn where the owner can see it."""
    b = r.get('topBox')
    if not b:
        fails.append('%s: the top bar WEBULL chip is not on the page' % tag)
        return
    why = []
    if b.get('disp') == 'none' or b.get('vis') == 'hidden' or (b.get('op') is not None and b['op'] < 0.5):
        why.append('hidden (display %s, visibility %s, opacity %s)' % (b.get('disp'), b.get('vis'), b.get('op')))
    if not b.get('w') or not b.get('h'):
        why.append('zero size')
    elif b['l'] < -1 or b['t'] < -1 or b['r'] > b['vw'] + 1 or b['b'] > b['vh'] + 1:
        why.append('outside the %sx%s viewport (%s,%s to %s,%s)' % (b['vw'], b['vh'], b['l'], b['t'], b['r'], b['b']))
    if b.get('covered'):
        why.append('covered by %s' % b.get('coveredBy'))
    if why:
        fails.append('%s: the top bar WEBULL chip is %s' % (tag, '; '.join(why)))


def _judge_tiles(tag, r, want, fails):
    """The four shared tiles: present, in order, the right kind of text, equal to `want`."""
    st = r.get('stats') or []
    keys = [x[0] for x in st]
    if keys != STAT_KEYS:
        fails.append('%s: the stat tiles under the chart are %r, want %r ([data-lgstat])' % (tag, keys, STAT_KEYS))
        return
    got = {x[0]: (x[1] or '', x[2] or '') for x in st}
    if not re.match(r'^(\d+%|--)$', got['winrate'][0]):
        fails.append('%s: WIN RATE reads %r, not a percent' % (tag, got['winrate'][0]))
    if not re.match(r'^(\d+\.\d\d|no losses|--)$', got['pf'][0]):
        fails.append('%s: PROFIT FACTOR reads %r' % (tag, got['pf'][0]))
    if not re.match(r'^(\$[\d,]+\.\d\d|--)$', got['maxdd'][0]) or (got['maxdd'][0] == '--') != (want['maxdd'][0] == '--'):
        fails.append('%s: MAX DRAWDOWN reads %r, not a positive dollar amount' % (tag, got['maxdd'][0]))
    if not re.match(r'^\d+$', got['trades'][0]):
        fails.append('%s: TRADES reads %r, not a count' % (tag, got['trades'][0]))
    for k in STAT_KEYS:
        wv, ws = want[k]
        if got[k][0] != wv:
            fails.append('%s: %s reads %r, the fixture says %r' % (tag, k, got[k][0], wv))
        if ws is not None and got[k][1] != ws:
            fails.append('%s: the %s tile line reads %r, the fixture says %r' % (tag, k, got[k][1], ws))


def _judge_strip(tag, r, vp, fails):
    """The shared stat strip is SEEN, right under the chart: shown, of real size, below the chart box, above the
    Account and History sections, and on a phone above the Strategies list (as on REAL)."""
    b = r.get('statBox')
    if not b:
        fails.append('%s: the shared stat strip (.qbx-lgstats) is not on the page' % tag)
        return
    if (b.get('disp') == 'none' or b.get('vis') == 'hidden' or (b.get('op') is not None and b['op'] < 0.5)
            or not b.get('w') or not b.get('h') or not b.get('tileH') or b.get('tileH') == 9999):
        fails.append('%s: the stat strip cannot be seen (display %s, visibility %s, opacity %s, %sx%s px, tiles %s px high)'
                     % (tag, b.get('disp'), b.get('vis'), b.get('op'), b.get('w'), b.get('h'), b.get('tileH')))
        return
    top = b.get('top')
    if b.get('chartBottom') is None or top < b['chartBottom'] - 1:
        fails.append('%s: the stat strip does not start under the chart (strip top %s, chart bottom %s)'
                     % (tag, top, b.get('chartBottom')))
    for k, what in (('acctTop', 'Account'), ('histTop', 'History')):
        if b.get(k) is not None and top >= b[k]:
            fails.append('%s: the stat strip is drawn under the %s section (strip top %s, %s top %s)'
                         % (tag, what, top, what, b[k]))
    if vp.startswith('phone') and b.get('sideTop') is not None and top >= b['sideTop']:
        fails.append('%s: on a phone the stat strip is drawn under the Strategies list (strip top %s, list top %s)'
                     % (tag, top, b['sideTop']))


def _hue_and_label(tag, r, sc_, fixture, fails):
    """An open fold: no hue under MONO, and the account's change named for the day it belongs to."""
    m = r.get('more') or {}
    if sc_['theme'] == 'mono' and m.get('hued'):
        fails.append('%s: More stats draws colour under MONO (MONO has no hue): %s' % (tag, '; '.join(m['hued'][:4])))
    eq = fixture.get('equity') or {}
    if eq.get('net_liq') is None or eq.get('change_today') is None:
        return
    import datetime
    as_day, clock_day = str(eq.get('as_of_et') or '')[:10], sc_['now'][:10]
    if as_day and as_day != clock_day:
        wd = datetime.date(*map(int, as_day.split('-'))).strftime('%a')
        want = 'Account change on %s %s' % (wd, as_day[5:])
    else:
        want = 'Account change today'
    acct = [k.split('|', 1)[1] for k in (m.get('vals') or {}) if k.startswith('Account|')]
    if want not in acct:
        got = [a for a in acct if a.startswith('Account change')]
        fails.append("%s: More stats names the account's change %r, want %r (the doc's balance was read on %s, "
                     "the page's clock reads %s)" % (tag, got, want, as_day, clock_day))


def _judge_more(tag, r, sc_, trades, cutoff, fixture, fails):
    """A stats case's More stats fold: closed unless the case stored it open (as a reload finds it), then
    shown with the right groups and values; with no trade in the range, still the Account rows."""
    m = r.get('more') or {}
    if not sc_['more']:
        if r.get('moreBtn') != 'false' or m.get('panel') != 'hidden':
            fails.append('%s: More stats is not closed (aria-expanded %r, panel %r)' % (tag, r.get('moreBtn'), m.get('panel')))
        return
    if r.get('moreBtn') != 'true' or m.get('panel') != 'shown':
        fails.append('%s: More stats was stored open for this viewer but draws %s (aria-expanded %r) -- an open fold '
                     'is not remembered on reload' % (tag, m.get('panel'), r.get('moreBtn')))
        return
    vals = m.get('vals') or {}
    acct = [k.split('|', 1)[1] for k in vals if k.startswith('Account|')]
    _hue_and_label(tag, r, sc_, fixture, fails)
    if sc_['empty']:
        if not m.get('empty'):
            fails.append("%s: More stats does not say 'No trades in this range.' (groups %r)" % (tag, m.get('groups')))
        elif m.get('gap') is None or m['gap'] < 8:
            fails.append("%s: 'No trades in this range.' runs into the Account heading (%s px between them)"
                         % (tag, m.get('gap')))
        miss = [a for a in ACCOUNT_ROWS_ANY_RANGE if not any(x.startswith(a) for x in acct)]
        if miss:
            fails.append('%s: with no trade closed in the range More stats loses the Account rows %s (has %r)'
                         % (tag, miss, acct))
        eq = fixture.get('equity') or {}
        rails = fixture.get('rails') or {}
        checks = [('Account|Daily loss limit', money(-abs(float(rails['daily_loss_limit_usd'])))
                   if rails.get('daily_loss_limit_usd') is not None else '--')]
        if eq.get('net_liq') is not None:
            checks.append(('Account|Account equity', money(float(eq['net_liq']))))
        for k, w in checks:
            if k in vals and vals[k] != w:
                fails.append('%s: More stats %s reads %r, the fixture says %r' % (tag, k.split('|')[1], vals[k], w))
        ox = vals.get('Account|Open exposure') or ''
        if 'Account|Open exposure' in vals and not re.match(r'^-?\$[\d,]+\.\d\d', ox):
            fails.append('%s: More stats Open exposure reads %r, not a dollar amount' % (tag, ox))
        return
    if (m.get('groups') or [])[:4] != ['Returns', 'Risk', 'Mix', 'Account'] or 'Best and worst trade' not in (m.get('groups') or []):
        fails.append('%s: More stats groups are %r, want Returns, Risk, Mix, Account, Best and worst trade' % (tag, m.get('groups')))
    miss = [a for a in ACCOUNT_ROWS if not any(x.startswith(a) for x in acct)]
    if miss:
        fails.append('%s: the Account group is missing %s (has %r)' % (tag, miss, acct))
    for k, w in expected_more(trades, cutoff).items():
        if vals.get(k) != w:
            fails.append('%s: More stats %s reads %r, the fixture says %r' % (tag, k.replace('|', ' > '), vals.get(k), w))
    timed = [t for t in _range_rows(trades, cutoff) if t.get('entry_ts') and t.get('exit_ts')
             and str(t['exit_ts']) > str(t['entry_ts'])]
    hold = vals.get('Mix|Average hold')
    if timed and (not hold or hold == '--' or not re.search(r'\d', hold)):
        fails.append('%s: More stats Average hold reads %r with %d trades timed in the doc' % (tag, hold, len(timed)))


def _judge(data, fixture):
    fails, notes, unfinished = [], [], []
    why = data.get('why')
    if data.get('renderApp') != 'function':
        return (INCONCLUSIVE, ['app did not boot (renderApp=%s); see preflight_boot' % data.get('renderApp')],
                notes, data, True)
    if not data.get('authSettled'):
        notes.append('the signed-out screen never appeared; cases ran anyway')
    closed = round(sum(qe_pnl_of(t) for t in fixture.get('trades_all') or []), 2)
    n_rows = min(len(fixture.get('trades_all') or []), 50)
    cases = data.get('cases') or {}
    for nm, cfg in CASES:
        r = cases.get(nm)
        if r is None:
            unfinished.append('%s: never ran (why=%s)' % (nm, why))
            continue
        if r.get('call') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (nm, _first(r.get('call'))))
            continue
        if r.get('sampleErr'):
            fails.append('%s: the probe could not read the page -- %s' % (nm, _first(r['sampleErr'])))
            continue
        _errs(nm, r, fails)
        if r.get('heroMissing'):
            fails.append('%s: hero ids missing: %s' % (nm, ', '.join(r['heroMissing'])))
        if not MONEY_RE.match(r.get('heroBig') or ''):
            fails.append('%s: the hero big number reads %r, not a dollar amount' % (nm, r.get('heroBig')))
        if not (r.get('heroToday') or '').endswith('today'):
            fails.append('%s: the hero has no "today" line (got %r)' % (nm, r.get('heroToday')))
        if r.get('pills') != ','.join(LEDGER_RANGES):
            fails.append('%s: the range pills read %r, not %s' % (nm, r.get('pills'), ' '.join(LEDGER_RANGES)))
        if not r.get('chart'):
            fails.append('%s: the shared equity chart was not drawn (#qb-lg-chart has no svg)' % nm)
        else:
            min_h = 150 if cfg['vp'] == 'phone' else 200
            if (r.get('chartH') or 0) < min_h:
                fails.append('%s: the equity chart is %spx tall (squashed; needs %s+)' % (nm, r.get('chartH'), min_h))
            if (r.get('chartDates') or 0) < 2 or (r.get('chartTicks') or 0) < 2:
                fails.append('%s: the chart has %s date labels and %s price labels (needs 2+ of each)'
                             % (nm, r.get('chartDates'), r.get('chartTicks')))
            if not r.get('chartBands'):
                fails.append('%s: no hatched data-caveat day on the chart ([data-lgband])' % nm)
            if not r.get('chartMarks'):
                fails.append('%s: no run-change marker on the chart ([data-lgmark])' % nm)
            elif 'NOISE' not in (r.get('markText') or '') or '#382' not in (r.get('markText') or ''):
                fails.append('%s: the run-change marker reads %r (needs family + run, e.g. NOISE #304 -> #382)'
                             % (nm, r.get('markText')))
            if r.get('lines') != WANT_LINES:
                fails.append('%s: the chart legend lines are %r, not %r' % (nm, r.get('lines'), WANT_LINES))
            elif (r.get('lineIconW') or 0) > 24:
                fails.append('%s: the legend line icons are %spx wide (the legend wraps; want 16px)'
                             % (nm, r.get('lineIconW')))
            key = r.get('key') or ''
            if 'hatched' not in key or 'book only' not in key:
                fails.append('%s: the caveat / book-only key under the chart reads %r' % (nm, key))
        _judge_list(nm, r.get('lg'), cfg['vp'], cfg['theme'], fixture, None, 'ALL', False, False, fails)
        _judge_cal(nm, r.get('lgcal'), cfg['vp'], cfg['theme'], fixture, None, None, _cal_open_want(cfg['vp'], None), STAT_TODAY, fails)
        legs = r.get('tradeLegs') or []
        if r.get('tradeRows') != n_rows:
            fails.append('%s: the trade list shows %s rows for %s trades' % (nm, r.get('tradeRows'), n_rows))
        bad = [x for x in legs if not LEG_RE.match(x or '')]
        if bad:
            fails.append('%s: trade rows without family + run number: %s' % (nm, sorted(set(map(str, bad)))[:5]))
        elif len(fixture.get('trades_all') or []) <= 50:
            want = collections.Counter(expected_leg_name(t) for t in fixture.get('trades_all') or [])
            got = collections.Counter(legs)
            if got != want:
                fails.append('%s: trade rows name the wrong run: shown %s, want %s'
                             % (nm, dict(sorted(got.items())), dict(sorted(want.items()))))
        dashes = r.get('lineDashes') or []
        if r.get('lines') == WANT_LINES and len(set(dashes)) != len(WANT_LINES):
            fails.append('%s: the three faint lines do not carry three different dashes (%r); under MONO they '
                         'cannot be told apart' % (nm, dashes))
        if cfg['vp'] == 'phone' and (r.get('scrollW') or 0) > (r.get('clientW') or 0) + 1:
            fails.append('%s: the page scrolls sideways on a phone (scrollWidth %s > clientWidth %s; sticking out: %s)'
                         % (nm, r.get('scrollW'), r.get('clientW'), ', '.join(r.get('wide') or []) or '?'))
        if (r.get('appLen') or 0) < 3000:
            fails.append('%s: the board rendered almost nothing (%s chars)' % (nm, r.get('appLen')))
        if 'silent' in (r.get('fresh') or {}):
            fails.append('%s: the fresh doc (24 s old, in the session) shows %r' % (nm, r['fresh']['silent']))
        _judge_tiles(nm, r, expected_stats(fixture.get('trades_all') or []), fails)
        _judge_strip(nm, r, cfg['vp'], fails)
        if r.get('moreBtn') != 'false':
            fails.append('%s: the More stats fold is not there closed (aria-expanded=%r)' % (nm, r.get('moreBtn')))
        if r.get('oldStats'):
            fails.append('%s: the old stat tiles are still drawn beside the shared ones' % nm)
        if not r.get('top') or r['top'][0] != 'flat':
            fails.append('%s: the top bar WEBULL chip reads %r, want FLAT' % (nm, r.get('top')))
        _topbox(nm, r, fails)
    _judge_variants(data, fixture, fails, unfinished, why)
    got_st = data.get('stats') or {}
    for sc_ in _stats_cases(fixture):
        nm, rg, doc, vp, cm = sc_['name'], sc_['range'], sc_['doc'], sc_['vp'], sc_['cal']
        tag = 'stats [%s]' % nm
        r = got_st.get(nm)
        if r is None:
            unfinished.append('%s: never ran (why=%s)' % (tag, why))
            continue
        if r.get('call') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (tag, _first(r.get('call'))))
            continue
        _errs(tag, r, fails)
        if r.get('badTok'):
            fails.append('%s: the page shows %r' % (tag, r['badTok']))
        tr = doc.get('trades_all') or []
        cut = _cutoff(rg, sc_['today'])
        want = expected_stats(tr, cut)
        n_plain = len([t for t in tr if not _is_shadow(t)])
        if (want['trades'][0] == '0') != sc_['empty'] or (rg != 'ALL' and want['trades'][0] == str(n_plain)):
            fails.append('%s: the probe\'s own case is wrong: %s of %s trades in the range' % (tag, want['trades'][0], len(tr)))
        if any(_is_shadow(t) for t in tr):
            # a shadow row must change nothing: the tiles equal the fixture's own
            if want != expected_stats(fixture.get('trades_all') or [], cut):
                fails.append("%s: the probe's own case is wrong: its shadow row moved the recomputation" % tag)
            # ... and the hero and the trade list count the same trades as the stats (no shadow row anywhere)
            plain = [t for t in tr if not _is_shadow(t)]
            hero = money(_js_round(sum(qe_pnl_of(t) for t in plain) * 100) / 100.0)
            if r.get('heroBig') != hero:
                fails.append('%s: the hero reads %r, the trades without the shadow row make %s' % (tag, r.get('heroBig'), hero))
            if r.get('tradeRows') != min(len(plain), 50):
                fails.append('%s: the trade list shows %s rows, want %s (the shadow row left out)'
                             % (tag, r.get('tradeRows'), min(len(plain), 50)))
        _judge_tiles(tag, r, want, fails)
        _judge_strip(tag, r, vp, fails)
        _judge_more(tag, r, sc_, tr, cut, fixture, fails)
        _judge_list(tag, r.get('lg'), vp, sc_['theme'], doc, cut, rg, sc_['folds'], sc_['folds'], fails, distance=not sc_['more'])
        _judge_cal(tag, r.get('lgcal'), vp, sc_['theme'], doc, cut, cm, _cal_open_want(vp, sc_['cal_open']), sc_['today'], fails)
        if nm == '$0 trade':
            if '1 even' not in (want['winrate'][1] or ''):
                fails.append('%s: the probe\'s $0 fixture trade did not land (%r)' % (tag, want['winrate'][1]))
            cw = month_won(tr, cm)
            if r.get('calWon') != cw:
                fails.append("%s: the calendar's %s '%% won' reads %r, want %r (a $0 trade is neither a win nor a loss)"
                             % (tag, cm, r.get('calWon'), cw))
        if vp.startswith('phone') and (r.get('scrollW') or 0) > (r.get('clientW') or 0) + 1:
            fails.append('%s: the page scrolls sideways on a phone (sticking out: %s)' % (tag, ', '.join(r.get('wide') or []) or '?'))
    res = data.get('inter')
    if res is None:
        unfinished.append('interaction run: never ran (why=%s)' % why)
    elif res.get('threw') and not res.get('seed'):
        fails.append('interaction run: the probe itself threw -- %s' % _first(res['threw']))
    else:
        tag = 'interaction run'
        if res.get('seed') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (tag, _first(res.get('seed'))))
        if res.get('threw'):
            fails.append('%s: %s' % (tag, _first(res['threw'])))
        _errs(tag, res.get('errs') or {}, fails)
        o, c = res.get('open') or {}, res.get('closed') or {}
        if o.get('expanded') != 'true' or not o.get('engu') or o.get('stored') != '1':
            fails.append('%s: the Retired group did not open with ENGU-Q in it and the choice kept (%s)' % (tag, o))
        if c.get('expanded') != 'false' or c.get('rows'):
            fails.append('%s: the Retired group did not close again (%s)' % (tag, c))
        sc = res.get('scrub') or {}
        if not sc:
            fails.append('%s: no chart to scrub' % tag)
        else:
            if sc.get('bigStart') != '$0.00' or 'start of the range' not in (sc.get('todayStart') or ''):
                fails.append('%s: a scrub at the range start did not write $0.00 / start of the range into the hero '
                             '(got %r / %r)' % (tag, sc.get('bigStart'), sc.get('todayStart')))
            if sc.get('bigEnd') != money(closed):
                fails.append('%s: a scrub at the last day reads %r, want the closed P&L of record %s'
                             % (tag, sc.get('bigEnd'), money(closed)))
            if not sc.get('held') or sc.get('heldAfter'):
                fails.append('%s: the live redraw hold did not follow the scrub (held=%s, after=%s)'
                             % (tag, sc.get('held'), sc.get('heldAfter')))
            if not sc.get('sameSvg'):
                fails.append('%s: the scrub re-rendered the chart' % tag)
            if sc.get('bigAfter') != sc.get('big0') or sc.get('todayAfter') != sc.get('today0'):
                fails.append('%s: leaving the chart did not put the hero back (%r -> %r)'
                             % (tag, sc.get('big0'), sc.get('bigAfter')))
        lg = res.get('legend') or {}
        if not lg.get('off') or 'ORB' not in (lg.get('stored') or ''):
            fails.append('%s: switching the ORB line off was not remembered (%s)' % (tag, lg))
        fo = res.get('fold') or {}
        if not fo:
            fails.append('%s: no More stats fold ([data-lgmore="qb"])' % tag)
        else:
            if fo.get('before') != 'false' or fo.get('open') != 'true' or fo.get('panel') != 'shown' or fo.get('stored') != '1':
                fails.append('%s: More stats did not open on a tap (aria-expanded %s -> %s, panel %s, stored %r)'
                             % (tag, fo.get('before'), fo.get('open'), fo.get('panel'), fo.get('stored')))
            if (fo.get('groups') or [])[:4] != ['Returns', 'Risk', 'Mix', 'Account']:
                fails.append('%s: More stats groups are %r, want Returns, Risk, Mix, Account' % (tag, fo.get('groups')))
            miss = [a for a in ACCOUNT_ROWS if not any(x.startswith(a) for x in (fo.get('acct') or []))]
            if miss:
                fails.append('%s: the Account group is missing %s (has %r)' % (tag, miss, fo.get('acct')))
            if fo.get('bad'):
                fails.append('%s: More stats shows %r' % (tag, fo['bad']))
            # on ALL the Webull rows against the fixture (Book figure over the same trades as Broker made)
            fvals = fo.get('vals') or {}
            for k, w in expected_more(fixture.get('trades_all') or []).items():
                if fvals.get(k) != w:
                    fails.append('%s: More stats %s reads %r on ALL, the fixture says %r'
                                 % (tag, k.split('|')[1], fvals.get(k), w))
            if fo.get('closed') != 'false' or fo.get('panelAfter') != 'hidden' or fo.get('stored2') != '0':
                fails.append('%s: More stats did not close again (aria-expanded %s, panel %s, stored %r)'
                             % (tag, fo.get('closed'), fo.get('panelAfter'), fo.get('stored2')))
        _judge_inter_ledger(tag, res, fixture, fails)
    r = cases.get('oldboards')
    if r is None:
        unfinished.append('oldboards: never ran (why=%s)' % why)
    elif r.get('call') != 'OK':
        fails.append('oldboards: renderApp threw -- %s' % _first(r.get('call')))
    else:
        _errs('oldboards', r, fails)
        if r.get('statTilesAll') or not r.get('oldStats'):
            fails.append('oldboards: ?oldboards=1 does not show the old Stats tiles (shared tiles %s, old tiles %s)'
                         % (r.get('statTilesAll'), r.get('oldStats')))
        if r.get('chart') or not r.get('oldChart') or r.get('retired'):
            fails.append('oldboards: ?oldboards=1 does not show the old Webull chart and strategy list '
                         '(shared chart=%s, old chart=%s, Retired group=%s)'
                         % (r.get('chart'), r.get('oldChart'), r.get('retired')))
        o2 = r.get('old') or {}
        if not o2.get('oldCalDays') or not o2.get('oldCalNav') or o2.get('sharedCalFold'):
            fails.append('oldboards: ?oldboards=1 does not keep the old month calendar (old day cells %s, month arrows %s, '
                         'shared fold %s)' % (o2.get('oldCalDays'), o2.get('oldCalNav'), o2.get('sharedCalFold')))
        if o2.get('oldLegRows') != ['ORB', 'ENGUQ', 'NOISE'] or o2.get('sharedList') or not o2.get('oldSideHd'):
            fails.append('oldboards: ?oldboards=1 does not keep the old strategy rows (rows %r, shared list %s, old heading %s)'
                         % (o2.get('oldLegRows'), o2.get('sharedList'), o2.get('oldSideHd')))
        if o2.get('order') != ['qbx-side', 'qbx-account', 'qbx-stats', 'qbx-history']:
            fails.append('oldboards: ?oldboards=1 changed the old page order: %r' % (o2.get('order'),))
    if fails:
        return FAIL, fails, notes, data, True
    if unfinished:
        return INCONCLUSIVE, unfinished, notes, data, True
    return PASS, [], notes, data, False


def _judge_variants(data, fixture, fails, unfinished, why):
    """The freshness variants: each chip, label and the top bar chip, against what the variant's
    clock and doc say they must be."""
    got_all = data.get('vars')
    for nm, _now, _doc, ex in _variant_docs(fixture):
        tag = 'freshness [%s]' % nm
        r = (got_all or {}).get(nm)
        if r is None:
            unfinished.append('%s: never ran (why=%s)' % (tag, why))
            continue
        if r.get('call') != 'OK':
            fails.append('%s: renderApp threw -- %s' % (tag, _first(r.get('call'))))
            continue
        if r.get('sampleErr'):
            fails.append('%s: the probe could not read the page -- %s' % (tag, _first(r['sampleErr'])))
            continue
        _errs(tag, r, fails)
        if r.get('after') not in (None, 'OK'):
            fails.append('%s: the probe step after the render threw -- %s' % (tag, _first(r.get('after'))))
        if r.get('wantsLiveHome') is not False:
            fails.append('%s: the full-doc listener would run on HOME (%r) -- it must be the board\'s only: about 134 KB '
                         'per snapshot, 0.7 GB a day per visible device against the 10 GiB a month cap' % (tag, r.get('wantsLiveHome')))
        if r.get('wantsLiveBoard') is not True:
            fails.append('%s: the doc listener would not run on the WEBULL PAPER board (%r)' % (tag, r.get('wantsLiveBoard')))
        if r.get('timer') != 'number':
            fails.append('%s: the 30 s freshness timer is not running (_qbFreshTimer is %r) -- a page left open never '
                         'turns stale while the box is silent (finding 8)' % (tag, r.get('timer')))
        if r.get('badTok'):
            fails.append('%s: the page shows %r' % (tag, r['badTok']))
        if ex.get('vp', 'laptop') != 'laptop' and (r.get('scrollW') or 0) > (r.get('clientW') or 0) + 1:
            fails.append('%s: the page scrolls sideways at %s (sticking out: %s)'
                         % (tag, ex.get('vp'), ', '.join(r.get('wide') or []) or '?'))
        if ex.get('visread') and r.get('visRead') != ex['visread']:
            fails.append('%s: reads when the page is shown again [HOME 60 s after the last, HOME 400 s after, board 60 s after] '
                         'are %r, want %r -- away from the board at most one per 5 min (each is the whole doc)'
                         % (tag, r.get('visRead'), ex['visread']))
        if ex.get('cachesnap') and r.get('cantRead') is not True:
            fails.append("%s: after a cached listener snapshot qbCantRead() is %r, want true -- a copy from this browser's "
                         'cache is not a read, so the page must not start blaming the box' % (tag, r.get('cantRead')))
        if ex.get('top_hidden'):
            b = r.get('topBox')
            if r.get('top') is not None or (b and b.get('disp') != 'none'):
                fails.append('%s: the top bar shows a WEBULL chip %r for an account with no Webull box' % (tag, r.get('top')))
        else:
            _topbox(tag, r, fails)
        if ex.get('pin'):
            p = r.get('pin') or {}
            if not p.get('tbH1'):
                fails.append('%s: the probe could not measure the top bar and sub-tab strip (%r)' % (tag, p))
            else:
                if (p.get('tbH0') or 0) >= p['tbH1']:
                    fails.append('%s: the stale chip did not make the phone top bar taller (%r to %r px), so this check '
                                 'proves nothing -- give it a longer chip text' % (tag, p.get('tbH0'), p['tbH1']))
                if p.get('subStyleTop') != '%dpx' % p['tbH1'] or p.get('subTop', 0) < p.get('tbBottom', 0) - 1:
                    fails.append('%s: after the read the sticky sub-tab strip is pinned at %s (top %s) under a %s px top bar '
                                 '(bottom %s, scrolled %s) -- it slides under the bar' % (tag, p.get('subStyleTop'), p.get('subTop'),
                                 p['tbH1'], p.get('tbBottom'), p.get('scrollY')))
        if ex.get('calendar'):
            want_cal = [False, True, True, 780, True]
            try:
                got_cal = json.loads(r.get('cal') or 'null')
            except Exception:
                got_cal = r.get('cal')
            if got_cal != want_cal:
                fails.append('%s: the session calendar reads %r for [Thanksgiving 2026-11-26 open?, Fri 2027-12-31 open?, '
                             '2027-12-30 open?, close of 2026-11-27 in minutes, 2026-10-05 open?], want %r'
                             % (tag, got_cal, want_cal))
        if ex.get('tab'):
            # another tab: only the top bar chip is the board's business there
            if r.get('tab') != ex['tab']:
                fails.append('%s: the probe could not open %s (activeTab=%r)' % (tag, ex['tab'], r.get('tab')))
            if tuple(r.get('top') or ()) != tuple(ex['top'] or ()):
                fails.append('%s: the top bar WEBULL chip is %r away from the board, want %r' % (tag, r.get('top'), ex['top']))
            continue
        fresh = r.get('fresh') or {}
        names = {'silent': 'BOX SILENT', 'keel': 'KEEL', 'publish': 'UPDATES FAILING', 'pubgap': 'UPDATES PAUSED',
                 'tickgap': 'BOX STALLED', 'noread': 'THIS PAGE CANNOT READ'}
        for k, label in names.items():
            want = ex.get(k)
            if want is None and k in fresh:
                fails.append('%s: the hero shows %r, want no %s chip' % (tag, fresh[k], label))
            elif want is not None and fresh.get(k) != want:
                fails.append('%s: the hero %s chip reads %r, want %r' % (tag, label, fresh.get(k), want))
        today = r.get('heroToday') or ''
        if ex.get('today') and not today.endswith(ex['today']):
            fails.append('%s: the hero today line reads %r, want it to end with %r' % (tag, today, ex['today']))
        if tuple(r.get('top') or ()) != tuple(ex['top']):
            fails.append('%s: the top bar WEBULL chip is %r, want %r' % (tag, r.get('top'), ex['top']))
        strip = r.get('strip') or ''
        for s in ex.get('strip_has') or []:
            if s not in strip:
                fails.append('%s: the status strip lacks %r (reads %r)' % (tag, s, strip))
        for s in ex.get('strip_lacks') or []:
            if s in strip:
                fails.append('%s: the status strip says %r (reads %r)' % (tag, s, strip))
        for key, what in (('stop', 'daily-stop caption'), ('orders', "orders header"), ('legtoday', "NOISE leg's today label")):
            if key in ex and r.get(key) != ex[key]:
                fails.append('%s: the %s is dated %r, want %r' % (tag, what, r.get(key), ex[key]))
        if ex.get('orders') and ex['orders'] != 'today' and ('Orders on ' + ex['orders']) not in (r.get('ordersTxt') or ''):
            fails.append('%s: the orders header reads %r' % (tag, r.get('ordersTxt')))
        if ex.get('stop') and ex['stop'] != 'today' and ('from ' + ex['stop']) not in (r.get('stopTxt') or ''):
            fails.append('%s: the daily-stop caption reads %r, want "from %s"' % (tag, r.get('stopTxt'), ex['stop']))
        if ex.get('asof_has') and ex['asof_has'] not in (r.get('asof') or ''):
            fails.append('%s: the Account line reads %r, want %r' % (tag, r.get('asof'), ex['asof_has']))
        if 'eq_stale' in ex and bool(r.get('eqStale')) != ex['eq_stale']:
            fails.append('%s: the Account STALE flag is %s, want %s' % (tag, bool(r.get('eqStale')), ex['eq_stale']))
        if ex.get('eq_why') and ex['eq_why'] not in (r.get('eqWhy') or ''):
            fails.append('%s: the Account STALE flag says why as %r, want it to contain %r' % (tag, r.get('eqWhy'), ex['eq_why']))
        if ex.get('keelwarn') and r.get('keelwarn') != ex['keelwarn']:
            fails.append('%s: the NOISE row KEEL warning reads %r, want %r' % (tag, r.get('keelwarn'), ex['keelwarn']))
        if ex.get('silent') and ex.get('mini_silent') and r.get('miniSilent') != ex['mini_silent']:
            fails.append('%s: the Orders summary reads %r, want %r' % (tag, r.get('miniSilent'), ex['mini_silent']))
        # finding 8: neither Orders view may still claim the frozen mode while the box is silent
        stale_like = bool(ex.get('silent') or ex.get('noread'))
        if stale_like:
            want_pill = 'BOX SILENT' if ex.get('silent') else 'NO STATUS'
            if r.get('miniPill') != want_pill:
                fails.append('%s: the sidebar Orders pill reads %r on a stale copy, want %s' % (tag, r.get('miniPill'), want_pill))
            # a page that cannot read is not the box's fault: amber, never BOX SILENT's red
            want_col, bad_col = ('var(--attn-red)', 'var(--attn-amber)') if ex.get('silent') else ('var(--attn-amber)', 'var(--attn-red)')
            for what, h in (('sidebar Orders pill', r.get('miniPillHtml')), ('Orders card pill (System)', r.get('ordModeHtml'))):
                if h is not None and (want_col not in h.split('</span>')[0] or bad_col in h.split('</span>')[0]):
                    fails.append('%s: the %s is not drawn in %s (%r)' % (tag, what, want_col, _first(h, 160)))
            if 'Sending orders' in (r.get('miniTxt') or ''):
                fails.append('%s: the sidebar Orders summary still says it is sending orders (%r)' % (tag, r.get('miniTxt')))
        if ex.get('ordmode'):
            om = r.get('ordMode') or ''
            if not om.startswith(ex['ordmode']) or 'Sending orders' in om or om.startswith('PAPER'):
                fails.append('%s: the Orders card (System) reads %r, want it to start with %r and not say '
                             'PAPER / Sending orders' % (tag, om, ex['ordmode']))
        # finding 9: every figure from an earlier trading day is dimmed
        if ex.get('today') and ex['today'] != 'today':
            for key, what in (('opNotToday', "hero's day line"), ('opStop', 'daily-stop bar'), ('opLegToday', "NOISE leg's day figure")):
                if r.get(key) is None or r[key] >= 1:
                    fails.append('%s: the %s from %s is drawn at opacity %r, want it dimmed' % (tag, what, ex['today'], r.get(key)))
        # finding 24: the Account change carries its own date and is dimmed when it is not today's
        # (every variant's balance was read on the doc's own trading day, so the two dates agree)
        if ex.get('today'):
            want_chg = ex['today']
            if r.get('eqChg') != want_chg:
                fails.append('%s: the Account change is labelled %r, want %r' % (tag, r.get('eqChg'), want_chg))
            elif want_chg != 'today' and (r.get('eqChgOp') is None or r['eqChgOp'] >= 1):
                fails.append('%s: the Account change from %s is not dimmed (opacity %r)' % (tag, want_chg, r.get('eqChgOp')))
            elif want_chg == 'today' and r.get('eqChgOp') is not None and r['eqChgOp'] < 1:
                fails.append("%s: today's Account change is dimmed (opacity %r)" % (tag, r.get('eqChgOp')))
        if stale_like:
            if r.get('recon') != 'stale' or 'as of ' not in (r.get('reconTxt') or ''):
                fails.append('%s: the Account reconcile line reads %r (%s) on a silent box, want it grey with its time'
                             % (tag, r.get('reconTxt'), r.get('recon')))
        elif r.get('recon') == 'stale':
            fails.append('%s: the Account reconcile line is greyed although the box is not silent' % tag)
        if ex.get('keelline') and ex['keelline'] not in (r.get('keelLine') or ''):
            fails.append('%s: the NOISE KEEL line reads %r, want it to contain %r' % (tag, r.get('keelLine'), ex['keelline']))
        if ex.get('lasttick') and r.get('lastTick') != ex['lasttick']:
            fails.append('%s: System LAST TICK reads %r, want %r' % (tag, r.get('lastTick'), ex['lasttick']))
        # finding 8: a flag the box wrote is only as current as the doc -- grey while the box is silent
        nr = (r.get('flags') or {}).get('NOT READY')
        if nr is None:
            fails.append("%s: the box's NOT READY flag is missing from the hero (flags %r)" % (tag, r.get('flags')))
        elif stale_like != (nr == 'grey'):
            fails.append("%s: the box's NOT READY flag is drawn %s, want %s" % (tag, nr, 'grey' if stale_like else 'in colour'))
        if ex.get('legpill') and r.get('legPill') != ex['legpill']:
            fails.append("%s: the NOISE row's position pill (%r) is drawn %s, want %s"
                         % (tag, r.get('legPillTxt'), r.get('legPill'), ex['legpill']))
        if ex.get('live_has') and ex['live_has'] not in (r.get('liveLine') or ''):
            fails.append("%s: the NOISE row's position line reads %r, want it to contain %r" % (tag, r.get('liveLine'), ex['live_has']))
        if ex.get('live_lacks') and ex['live_lacks'] in (r.get('liveLine') or ''):
            fails.append("%s: the NOISE row's position line reads %r, it must not say %r" % (tag, r.get('liveLine'), ex['live_lacks']))
        for key, what in (('openpnl', 'Open figure'), ('unreal', 'UNREALIZED figure')):
            if ex.get(key) and r.get(key if key != 'openpnl' else 'openPnl') != ex[key]:
                fails.append("%s: the NOISE row's %s is drawn %s, want %s"
                             % (tag, what, r.get(key if key != 'openpnl' else 'openPnl'), ex[key]))


def _report(t0, attempt, may_retry, chrome, alt_index, fixture):
    verdict, msgs, notes, data, retry = attempt
    first = None
    if verdict != PASS and retry and may_retry:
        first = (verdict, msgs)
        print('WEBULLPROBE: attempt 1 did not pass, retrying once before blocking -- %s'
              % ('; '.join(msgs[:2]) or 'no detail'))
        verdict, msgs, notes, data, retry = _attempt(chrome, alt_index, fixture)
    elapsed = time.time() - t0
    data = data or {}
    if verdict == INCONCLUSIVE:
        print('WEBULLPROBE: INCONCLUSIVE -- %s' % ('; '.join(msgs[:3]) if msgs else 'no detail'))
        return INCONCLUSIVE
    if verdict == FAIL:
        print('WEBULLPROBE: FAIL (VERSION=%s, %.1fs%s, %d problem(s))'
              % (data.get('VERSION'), elapsed, ', both attempts' if first else '', len(msgs)))
        seen = set()
        for f in msgs:
            if f not in seen and len(seen) < 25:
                seen.add(f)
                print('  - ' + f)
        for n in notes[:6]:
            print('  note: ' + n)
        return FAIL
    lap = (data.get('cases') or {}).get('laptop/dark') or {}
    cal0, lg0 = lap.get('lgcal') or {}, lap.get('lg') or {}
    book = ' | '.join('%s %s' % (x.get('name'), x.get('value')) for g in lg0.get('groups') or [] if g.get('key') == 'book'
                      for x in g.get('rows') or [])
    pg = ((((data.get('cases') or {}).get('phone/dark') or {}).get('lg') or {}).get('geo')) or {}
    print('WEBULLPROBE: PASS (VERSION=%s, %d cases + interaction + %d stats cases + %d freshness variants + oldboards, %.1fs; '
          'laptop chart %spx, %s dates, %s price labels, %s caveat days, marker %r; tiles %s; calendar %s %s; list %s, %s; '
          'phone trade list %s px under the board top)'
          % (data.get('VERSION'), len(CASES), len(data.get('stats') or {}), len(data.get('vars') or {}), elapsed, lap.get('chartH'),
             lap.get('chartDates'), lap.get('chartTicks'), lap.get('chartBands'), lap.get('markText'),
             ' | '.join('%s %s' % (x[0], x[1]) for x in (lap.get('stats') or [])),
             cal0.get('title'), (cal0.get('sum') or '').split(' · ')[0], lg0.get('count'), book,
             (pg.get('histTop') or 0) - (pg.get('shellTop') or 0)))
    if first:
        print('  FLAKE: attempt 1 did not pass on this same file, the retry did. It said:')
        for f in first[1][:4]:
            print('    - ' + f)
    for n in notes[:6]:
        print('  note: ' + n)
    return PASS


def selftest():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    src = io.open(os.path.join(ROOT, 'index.html'), encoding='utf-8', newline='').read()
    t0 = time.time()
    tmpdir = tempfile.mkdtemp(prefix='webullprobe-selftest-')
    bad = []
    try:
        for name, anchor, repl, why in MUTANTS:
            n = src.count(anchor)
            if n != 1:
                print('SELFTEST: INCONCLUSIVE -- mutant %r cannot be built: its anchor appears %d times in '
                      'index.html (expected once). Update MUTANTS in tools/webull_board_probe.py: %r'
                      % (name, n, anchor))
                return INCONCLUSIVE
            path = os.path.join(tmpdir, 'index_%s.html' % name)
            io.open(path, 'w', encoding='utf-8', newline='').write(src.replace(anchor, repl))
            print('-- mutant %s (%s): expect FAIL' % (name, why))
            code = main(['--file', path, '--no-retry'])
            if code != FAIL:
                bad.append('mutant %s was NOT caught (exit %d) -- the gate has gone blind to: %s' % (name, code, why))
        print('-- current index.html: expect PASS')
        code = main([])
        if code != PASS:
            bad.append('current index.html did not PASS (exit %d)' % code)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    if bad:
        print('SELFTEST: FAIL (%.1fs)' % (time.time() - t0))
        for b in bad:
            print('  - ' + b)
        return FAIL
    print('SELFTEST: PASS -- gate caught %d/%d broken builds and passed the current one (%.1fs)'
          % (len(MUTANTS), len(MUTANTS), time.time() - t0))
    return PASS


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--file', default=None, help='gate this file as if it were index.html')
    ap.add_argument('--no-retry', action='store_true', help='do not re-render a failed attempt')
    ap.add_argument('--selftest', action='store_true',
                    help='assert FAIL on every MUTANT of index.html, then PASS on the real file')
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    t0 = time.time()
    alt_index = os.path.abspath(args.file) if args.file else None
    if alt_index and not os.path.isfile(alt_index):
        print('WEBULLPROBE: INCONCLUSIVE -- --file not found: %s' % alt_index)
        return INCONCLUSIVE
    if not os.path.isfile(FIXTURE):
        print('WEBULLPROBE: INCONCLUSIVE -- fixture missing: %s' % FIXTURE)
        return INCONCLUSIVE
    fixture = json.load(io.open(FIXTURE, encoding='utf-8'))
    chrome = find_chrome()
    if not chrome:
        print('WEBULLPROBE: INCONCLUSIVE -- Chrome not found')
        return INCONCLUSIVE
    return _report(t0, _attempt(chrome, alt_index, fixture), not args.no_retry, chrome, alt_index, fixture)


if __name__ == '__main__':
    sys.exit(main())
