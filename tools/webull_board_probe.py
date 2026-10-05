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
]

PROBE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>webull board probe</title></head>
<body style="margin:0">
<iframe id="f" src="../index.html" style="width:1366px;height:768px;border:0;display:block"></iframe>
<pre id="o" style="display:none"></pre>
<script>
var CASES=__CASES__, VP=__VP__, FIX=__FIX__, NOW=__NOW__, VARS=__VARS__;
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
    return w.eval("(function(){try{"
      +"try{delete navigator.onLine;}catch(e){}"
      +"if(window.__probeOffline)Object.defineProperty(navigator,'onLine',{configurable:true,get:function(){return false;}});"
      +"try{localStorage.removeItem('el_qb_retired_open');localStorage.removeItem('el_lg_lines_webull');}catch(e){}"
      +"window._qbRetiredOpen=false;"
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
      +"homeRange='ALL';currentUser=currentUser||{uid:'probe-uid'};"
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
        var tb0=D().querySelector('#app .topbar');pinTb0=tb0?tb0.offsetHeight:null;
      }
      w.__probeFetchJson=JSON.stringify(cfg.fetch);w.__qbNowMs=cfg.tickTo;
      var res=w.eval("(function(){var sd=db,sa=auth;window.__probeRestore=function(){db=sd;auth=sa;};try{"
        +"var doc=JSON.parse(window.__probeFetchJson),snap={exists:true,data:function(){return doc;},metadata:{fromCache:false}};"
        +"var ref={get:function(){return Promise.resolve(snap);},onSnapshot:function(){return function(){};}};"
        +"db={collection:function(){return {doc:function(){return {collection:function(){return {doc:function(){return ref;}};}};}};}};"
        +"auth={currentUser:{uid:'probe-uid'}};window._qqqExecLoading=false;loadQqqExec(null,true);return 'OK';"
        +"}catch(e){window.__probeRestore();return 'ERR '+(e&&e.stack?e.stack:e);}})()");
      await sleep(150);
      try{w.__probeRestore();}catch(e){}
      if(cfg.pin){
        var d=D(),tb=d.querySelector('#app .topbar'),sb=tb&&tb.nextElementSibling,ct=d.querySelector('#app .content'),sp=d.createElement('div');
        sp.style.height='3000px';if(ct)ct.appendChild(sp);
        w.scrollTo(0,600);await sleep(80);
        var pin={tbH0:pinTb0,scrollY:Math.round(w.scrollY)};
        if(tb&&sb){var tr=tb.getBoundingClientRect(),sr=sb.getBoundingClientRect();
          pin.tbH1=tb.offsetHeight;pin.tbBottom=Math.round(tr.bottom);pin.subTop=Math.round(sr.top);pin.subStyleTop=sb.style.top;pin.subPos=sb.style.position;}
        w.__probePin=pin;
        w.scrollTo(0,0);sp.remove();
      }
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
      // 1. the Retired group opens and closes, and the choice is kept for this viewer
      var rb=q('.qbx-side [data-qbretired]');
      if(rb){rb.click();await sleep(80);}
      var st=null;try{st=w.localStorage.getItem('el_qb_retired_open');}catch(e){}
      res.open={expanded:(q('.qbx-side [data-qbretired]')||{getAttribute:function(){return null;}}).getAttribute('aria-expanded'),
        rows:d.querySelectorAll('.qbx-side [data-qbretiredrow]').length,engu:!!q('.qbx-side [data-qbretiredrow="ENGUQ"] [data-qblegrow="ENGUQ"]'),stored:st};
      rb=q('.qbx-side [data-qbretired]');
      if(rb){rb.click();await sleep(80);}
      res.closed={expanded:(q('.qbx-side [data-qbretired]')||{getAttribute:function(){return null;}}).getAttribute('aria-expanded'),
        rows:d.querySelectorAll('.qbx-side [data-qbretiredrow]').length};
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
    html = (PROBE_HTML.replace('__CASES__', json.dumps(CASES)).replace('__VP__', json.dumps(VIEWPORTS))
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
        if not r.get('retired'):
            fails.append('%s: no Retired group under the live strategies' % nm)
        else:
            if r.get('retiredExpanded') != 'false' or r.get('retiredRows'):
                fails.append('%s: the Retired group is not collapsed by default (aria-expanded=%s, %s rows shown)'
                             % (nm, r.get('retiredExpanded'), r.get('retiredRows')))
            if ('flat since ' + RETIRED_SINCE) not in (r.get('retiredText') or ''):
                fails.append('%s: the Retired group reads %r, want "flat since %s"'
                             % (nm, r.get('retiredText'), RETIRED_SINCE))
        if r.get('liveRows') != WANT_LIVE:
            fails.append('%s: the live strategy rows are %r, want %r' % (nm, r.get('liveRows'), WANT_LIVE))
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
        if not r.get('top') or r['top'][0] != 'flat':
            fails.append('%s: the top bar WEBULL chip reads %r, want FLAT' % (nm, r.get('top')))
        _topbox(nm, r, fails)
    _judge_variants(data, fixture, fails, unfinished, why)
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
    r = cases.get('oldboards')
    if r is None:
        unfinished.append('oldboards: never ran (why=%s)' % why)
    elif r.get('call') != 'OK':
        fails.append('oldboards: renderApp threw -- %s' % _first(r.get('call')))
    else:
        _errs('oldboards', r, fails)
        if r.get('chart') or not r.get('oldChart') or r.get('retired'):
            fails.append('oldboards: ?oldboards=1 does not show the old Webull chart and strategy list '
                         '(shared chart=%s, old chart=%s, Retired group=%s)'
                         % (r.get('chart'), r.get('oldChart'), r.get('retired')))
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
    print('WEBULLPROBE: PASS (VERSION=%s, %d cases + interaction + %d freshness variants + oldboards, %.1fs; '
          'laptop chart %spx, %s dates, %s price labels, %s caveat days, marker %r)'
          % (data.get('VERSION'), len(CASES), len(data.get('vars') or {}), elapsed, lap.get('chartH'), lap.get('chartDates'),
             lap.get('chartTicks'), lap.get('chartBands'), lap.get('markText')))
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
