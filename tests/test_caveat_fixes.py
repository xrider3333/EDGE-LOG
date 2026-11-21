"""CAVEAT FIXES (owner 11-21, standing order for every calendar): a hatched caveat day is AMBER while its
cause is open and BLUE once the cause is fixed. docs/caveat_fixes.json is the one list that says which
causes are fixed and over which days; index.html's ledgerCavFix / ledgerCavResolve read it.

These tests hold the list honest:
  * every entry names a calendar and cause codes the page actually emits (a typo would silently keep a
    day amber forever);
  * every entry has a fix date, a commit ref and plain words (the hover prints 'fixed: <note> (<date>)');
  * no entry reaches past its own fix date - a cause that comes back after the fix must stay amber;
  * the matching rule (calendar, kind, from <= day <= to-or-fixed_on) behaves as the page's does, on the
    seeded days: 11-13's never-sent NOISE trades are fixed, its two fills worse than the band are not.
"""
import datetime
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXES_PATH = os.path.join(ROOT, 'docs', 'caveat_fixes.json')
INDEX_PATH = os.path.join(ROOT, 'index.html')

KINDS = {
    'qb': {'tape_reprice', 'fill_outside_minute', 'fill_band', 'parity_old', 'book_only_broker',
           'book_only_infra', 'book_only', 'feed_invalid'},
    'p2': {'roll_splice', 'orb_lookahead'},
}


def _fixes():
    with open(FIXES_PATH, encoding='utf-8') as fh:
        return json.load(fh)['fixes']


def _date(s):
    return datetime.date.fromisoformat(s)


def _fixed(cal, kind, day, fixes):
    """Python twin of index.html's ledgerCavFix."""
    for f in fixes:
        if kind not in (f.get('kinds') or []) or not f.get('fixed_on'):
            continue
        cs = f.get('calendars') or []
        if cs and cal not in cs and '*' not in cs:
            continue
        if f.get('from') and day < f['from']:
            continue
        if day > (f.get('to') or f['fixed_on']):
            continue
        return True
    return False


def test_entries_are_well_formed():
    fixes = _fixes()
    assert fixes, 'docs/caveat_fixes.json lists no fix'
    ids = [f['id'] for f in fixes]
    assert len(ids) == len(set(ids)), 'duplicate ids: %r' % ids
    for f in fixes:
        cals = f.get('calendars') or []
        assert cals and all(c in KINDS or c == '*' for c in cals), f
        known = set().union(*(KINDS.values())) if '*' in cals else set().union(*(KINDS[c] for c in cals))
        assert f.get('kinds') and set(f['kinds']) <= known, 'unknown cause code in %s: %r' % (f['id'], f['kinds'])
        fixed_on = _date(f['fixed_on'])
        to = _date(f.get('to') or f['fixed_on'])
        assert to <= fixed_on, '%s reaches past its own fix date' % f['id']
        if f.get('from'):
            assert _date(f['from']) <= to, f['id']
        assert str(f.get('ref') or '').strip(), '%s has no commit ref' % f['id']
        assert len(str(f.get('note') or '').strip()) > 10, '%s has no plain-words note' % f['id']
        assert '<' not in f['note'], 'notes are plain words, not html'


def test_every_cause_code_is_emitted_by_the_page():
    with open(INDEX_PATH, encoding='utf-8') as fh:
        src = fh.read()
    emitted = set(re.findall(r"\{k:'([a-z_]+)',t:", src))
    assert set().union(*KINDS.values()) <= emitted, 'cause codes the page never emits: %r' % (
        set().union(*KINDS.values()) - emitted)
    assert "ledgerCavResolve('qb'" in src and "ledgerCavResolve('p2'" in src
    assert "fetch('docs/caveat_fixes.json" in src


def test_seeded_days_resolve_as_assessed():
    fixes = _fixes()
    # WEBULL PAPER
    assert _fixed('qb', 'book_only_infra', '2026-11-13', fixes)        # lease quota read failed; local lease 11-19
    assert not _fixed('qb', 'fill_band', '2026-11-13', fixes)          # two real fills worse than the band: open
    assert not _fixed('qb', 'book_only_infra', '2026-11-20', fixes)    # the same cause after the fix stays amber
    assert _fixed('qb', 'book_only_broker', '2026-09-23', fixes)       # 8 NOISE 417 refusals; legs netted 09-23
    assert not _fixed('qb', 'book_only_broker', '2026-10-01', fixes)
    for d in ('2026-09-03', '2026-09-08', '2026-09-09', '2026-09-10'):
        assert _fixed('qb', 'feed_invalid', d, fixes)                  # off NinjaTrader's feed 09-13
    assert not _fixed('qb', 'feed_invalid', '2026-11-03', fixes)
    for d in ('2026-09-17', '2026-09-18'):
        assert _fixed('qb', 'tape_reprice', d, fixes)                  # flatten after the bell; back to 15:59 09-20
    for d in ('2026-10-16', '2026-11-04', '2026-11-05', '2026-11-19'):
        assert not _fixed('qb', 'fill_band', d, fixes)
    # NT8 PAPER
    assert _fixed('p2', 'roll_splice', '2026-09-14', fixes)
    assert _fixed('p2', 'roll_splice', '2026-09-16', fixes)
    assert not _fixed('p2', 'roll_splice', '2026-12-14', fixes)        # the December roll is not covered
    assert not _fixed('p2', 'orb_lookahead', '2026-09-16', fixes)      # not clearly fixed: stays amber
    # a cause code on the wrong calendar never matches
    assert not _fixed('p2', 'book_only_infra', '2026-11-13', fixes)
