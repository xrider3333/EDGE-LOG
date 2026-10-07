#!/usr/bin/env python3
"""
tools/ledger_removed.py -- static lint for the LEDGER unification clean-up (v73.1125).

The ?oldboards=1 escape hatch and the previous layout of the three LEDGER boards (REAL, NT8 PAPER, WEBULL PAPER) were removed
once step 11 was live on all three. This module lists, by board, the identifiers that went with them (the flag itself, the old
sheet / table / drawer / feed builders, the old classes and DOM hooks) and checks that none of them is back in index.html.
Whole-token match, so a kept name that merely CONTAINS one of them (hm-sheet-points, _hmSheetParts) never trips it; the CHANGELOG
is skipped (it is history and may name them).

The three board probes (home_render_probe.py, paper_render_probe.py, webull_board_probe.py) call lint() on the file they gate, and each
runs its own board's group plus the shared one; their --selftest feeds in a copy with LEDGER_OLDBOARDS put back and must FAIL.

  python tools/ledger_removed.py                # lint index.html, every group
  python tools/ledger_removed.py --file X.html  # lint X.html

Exit codes: 0 clean, 1 a removed identifier is back.
"""
import os
import re
import sys

# the flag and what only it served (every board)
SHARED = [
    'LEDGER_OLDBOARDS', 'oldboards',
]

# REAL (HOME): the previous feed / table / sheet / stat strip / toolbar builders and their classes and hooks
REAL = [
    # functions and consts
    '_hmDayLabel', '_hmLedgerStripHtml', '_hmMissedSheetHtml', '_hmMoreStats', '_hmMsRow', '_hmOldListBlockHtml',
    '_hmRenderFeedDay', '_hmRenderFeedTrade', '_hmRenderTable', '_hmSheetHtml', '_hmStatStrip', '_hmTableHeader',
    '_hmTableHeaderSimple', '_hmTableRow', '_hmTableRowSimple', '_hmToolbarHtml', '_hmTradeRow', '_hmWireChart',
    '_HM_VB_W', '_hmEscWired',
    # classes
    'hm-sheet', 'hm-sheet-close', 'hm-sheet-foot', 'hm-sheet-net', 'hm-sheet-sub', 'hm-sheet-sym', 'hm-backdrop',
    'hm-morestats-toggle', 'hm-morestats-panel', 'hm-ms-grid', 'hm-ms-row', 'hm-ms-bar', 'hm-ms-group', 'hm-ms-note',
    'hm-stat-cell', 'hm-stat-val', '.hm-stat-strip', 'hm-day-header', 'hm-day-group', 'hm-toolbar', 'hm-toolbar-count',
    'hm-range-pills', 'hm-range-row', '.hm-mode-toggle', 'hm-filter-row', 'hm-chip-row', 'hm-chip', 'hm-chart-cell',
    'hm-col-in', 'hm-hero', 'hm-chev', 'hm-feed-head', 'hm-sec-journal',
    # DOM ids and data hooks
    'hm-view-toggle', 'hm-morestats-toggle', 'data-hmchip', 'hmSheetIn',
]

# NT8 PAPER: the previous trades table, hero, stats, calendar, rail and their hooks
NT8 = [
    '_p2New', '_tradesHtmlOld', '_p2HeadOld', '_p2Card', '_ptSelBar', '_tieStrip', '_tRows', '_rhStats', '_rhCal', '_psTh',
    '_cumById', '_durTxt', '_psScopeTab', '_pcwSeg', '_rhAcc', '_rhToday', 'curveHtmlNoLegs', 'legsCard', 'legTile',
    'legStripCtl', 'legTable', '_paperShowCfg', 'PCOLMODE', 'PCOLS_ON', 'p2legs', 'p2row',
    'p2sheet', 'p2sh', 'p2hero', 'p2big', 'p2delta', 'p2lbl', 'p2live', 'p2num', 'p2status', 'p2filtrow', 'p2rhhero', 'p2rhcap',
    'p2rhnum', 'p2rhsub', 'p2rhsep', 'p2rhchart', 'p2rhy', 'p2rhxs', 'p2rhx', 'p2rhcur', 'p2rhdot', 'p2rhtabs', 'p2rhrow',
    'p2rhstats', 'p2rhstat', 'p2rhsl', 'p2rhsv', 'p2rhss', 'p2rhcal',
    'ptrades-body', 'pt-selbar', 'data-ptrow', 'data-pcalmo', 'data-pcalday', 'data-pcalcur', 'data-papercols', 'data-papercfg',
    'data-p2otherhd', 'data-patharch', 'data-paperleg', 'data-paperother', 'data-p2chart',
]

# WEBULL PAPER: the previous chart / stats / legs / calendar / trade list, the inline drawer and the old section builders
WEBULL = [
    'legCardsHtml', 'legRowHtml', 'qbLiveRows', 'qbPeriodFilter', 'qbSegHtml', 'qbBuildDrawerFn', 'buildDrawer', 'qeFillsCol',
    'qeExWhy', 'qbFooter', 'qbSystemSection', 'qbSideSec', 'qbAcctSec', 'qbHistSec', 'qbMidSections', 'qbNewBody', 'qbStatsCard',
    'qbTilesHtml', 'qbMoreStatsBody', 'qbActivityCard', 'qbTradesSeg', 'qbCsvBtn', 'qbChartPeriod', 'qbDateRange', 'QSTR',
    'qeCalHtml', 'tradesListHtml', 'qeCumFromTrades', 'qbRangeCum', 'drawerIdx',
    '_qbChartHover', '_qeChartHidden', '_qeChartPeriod', '_qeDrawerEscWired', '_qeDrawerIdx',
    'qe-drawer', 'qe-drawer-col', 'qe-drawer-grid', 'qe-drawer-lbl', 'qe-legend-item', 'qb-hero', 'qb-hero-left', 'qb-hero-title',
    'qb-hero-num', 'qb-hero-sub', 'qb-chip', 'qb-seg', 'qb-pill', 'qb-leg-row', 'qb-leg-row-top', 'qb-spark-cell', 'qb-chart-svg',
    'qb-chart-legend', 'qbx-chart-tabs', 'qbx-chart-readout', 'qbx-stat-strip', 'qbx-stat-cell', 'qbx-stat-lbl', 'qbx-stat-val',
    'qbx-account', 'qbx-system', 'qbx-footer', 'qbx-hero-today', 'qbx-today-suffix', 'qbx-side-hd',
    'data-qbtraderow', 'data-qetraderow', 'data-qelegend', 'data-qbseg', 'data-qblegrow', 'data-qqqmodeltoggle',
    'data-qqqratiotoggle', 'data-qcalmo', 'data-qcalday', 'data-qechart',
]

GROUPS = {'shared': SHARED, 'real': REAL, 'nt8': NT8, 'webull': WEBULL}


def _strip_changelog(text):
    i = text.find('const CHANGELOG=[')
    if i < 0:
        return text
    j = text.find('\n];', i)
    return text[:i] + ('\n' * text[i:j].count('\n')) + text[j:] if j > i else text


def lint(text, groups=None):
    """Return a list of 'name (group): first line' problems; empty when clean."""
    body = _strip_changelog(text)
    lines = body.split('\n')
    problems = []
    for g in (groups or list(GROUPS)):
        for name in GROUPS[g]:
            pat = re.compile(r'(?<![\w$-])' + re.escape(name) + r'(?![\w$-])')
            for i, ln in enumerate(lines, 1):
                if pat.search(ln):
                    problems.append('%s (%s) is back in index.html at line %d' % (name, g, i))
                    break
    return problems


def lint_file(path, groups=None):
    with open(path, 'r', encoding='utf-8', errors='replace', newline='') as f:
        return lint(f.read(), groups)


def main(argv):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'index.html')
    if '--file' in argv:
        path = argv[argv.index('--file') + 1]
    probs = lint_file(path)
    if probs:
        print('LEDGER-REMOVED: FAIL (%d)' % len(probs))
        for p in probs:
            print('  - ' + p)
        return 1
    n = sum(len(v) for v in GROUPS.values())
    print('LEDGER-REMOVED: PASS (%d removed identifiers, none in %s)' % (n, os.path.basename(path)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
