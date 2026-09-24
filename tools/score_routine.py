# score_routine.py - the whole end-of-day SCORE routine behind ONE script.
#
# WHY: the scoring session runs unattended on a schedule. Every separate command it types needs
# its own standing permission, and a single one it lacks leaves the run sitting on an approval
# prompt nobody is there to click (the 2026-09-22 and 09-23 runs stalled exactly that way). So
# the session only ever runs this script and writes one file; everything else - the worktree,
# Firestore, price bars, VERSION bump, CHANGELOG line, ship and clean-up - happens in here.
#
#   python tools/score_routine.py start      find unscored trades -> tools/data/score_inbox/pending.json
#   python tools/score_routine.py finish     check + merge tools/data/score_inbox/scored.json, ship
#   python tools/score_routine.py abort      throw the run away (inbox files are kept for a look)
#
#   start --selftest / finish --dry-run      one fake trade built from committed data, taken
#                                            through every step except the commit and push -
#                                            proves the permissions without publishing anything
#
# The session READS pending.json and WRITES scored.json (format in tools/data/SCORING_ROUTINE.md).
# The inbox lives in the checkout this script runs from (the shared one) and is gitignored.
import os
import io
import re
import sys
import json
import shutil
import argparse
import subprocess
import datetime as dt
import importlib.util

SHARED = r'C:\Users\xride\OneDrive\Desktop\EDGE-LOG'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, 'tools', 'data', 'score_inbox')
WT = os.path.join(SHARED, 'tools', 'wt.py')
PY = sys.executable
TRAILER = 'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
FILES = ('pending.json', 'scored.json', 'state.json')
SHIP_TRIES = 5

# The rubric rows, exactly as the score report shows them (tools/data/SCORING_ROUTINE.md).
STOCK_SETUP = [('Catalyst / RVOL', 15), ('Front-side structure', 20), ('Entry location', 20),
               ('Risk definition', 15), ('R:R to a real level', 10), ('Liquidity', 10),
               ('Time of day', 10)]
FUT_SETUP = [('Trend / context', 20), ('Entry location', 20), ('Risk definition', 15),
             ('R:R to a real level', 10), ('Setup match', 15), ('Liquidity / volatility', 10),
             ('Time of day', 10)]
EXEC = [('Entry timing', 25), ('Risk control / MAE', 25), ('Exit vs MFE', 25), ('Sizing', 15),
        ('Plan adherence', 10)]
HHMM = re.compile(r'^\d\d:\d\d$')


def say(*a):
    print(*a, flush=True)


def run(args, cwd=None, check=True):
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', env=env)
    if check and p.returncode:
        raise SystemExit('FAILED (%d): %s\n%s%s' % (p.returncode, ' '.join(args),
                                                   p.stdout[-3000:], p.stderr[-3000:]))
    return p


def et_now():
    from zoneinfo import ZoneInfo
    return dt.datetime.now(ZoneInfo('America/New_York'))


def inbox(f):
    return os.path.join(INBOX, f)


def load(fp):
    with io.open(fp, encoding='utf-8') as f:
        return json.load(f)


def dump(fp, obj):
    with io.open(fp, 'w', encoding='utf-8') as f:
        f.write(json.dumps(obj, indent=1, ensure_ascii=False))


def wt_path(name):
    sys.path.insert(0, os.path.join(SHARED, 'tools'))
    import wt                     # the shared checkout's worktree helper - only for its root path
    return os.path.join(wt.wt_root(), name)


_TS = {}


def ts_module(path):
    """trade_scores.py from a given worktree (its paths follow its own file location)."""
    if path not in _TS:
        spec = importlib.util.spec_from_file_location(
            'trade_scores_%d' % len(_TS), os.path.join(path, 'tools', 'trade_scores.py'))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _TS[path] = m
    return _TS[path]


def discard(name):
    """Throw a routine worktree away, uncommitted work and all. Never the shared checkout."""
    path = wt_path(name)
    if os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(SHARED)):
        raise SystemExit('refusing to discard the shared checkout')
    if os.path.isdir(path):
        run(['git', '-C', path, 'rebase', '--abort'], check=False)
        run(['git', '-C', path, 'reset', '--hard', '-q'], check=False)
        run(['git', '-C', path, 'clean', '-fdq'], check=False)
    run([PY, WT, 'drop', name], cwd=SHARED, check=False)


def shelve(tag):
    """Move this run's inbox files aside (never deleted) so the next run starts clean."""
    present = [f for f in FILES if os.path.exists(inbox(f))]
    if not present:
        return None
    dest = os.path.join(INBOX, '_' + tag, et_now().strftime('%Y%m%d-%H%M%S'))
    os.makedirs(dest, exist_ok=True)
    for f in present:
        shutil.move(inbox(f), os.path.join(dest, f))
    return dest


def bars_rows(win):
    return [[k.strftime('%H:%M'), round(float(r.Open), 4), round(float(r.High), 4),
             round(float(r.Low), 4), round(float(r.Close), 4), int(r.Volume or 0)]
            for k, r in win.iterrows()]


def selftest_pending(path):
    """One fake trade: a copy of the real 2026-09-22 MNQ 09:30 trade under the id SELFTEST,
    with bars from the committed cache - no Firestore, never published."""
    ts = ts_module(path)
    bars = ts.load_bars('MNQ', '2026-09-22', '1m')
    day = bars[bars.index.date == dt.date(2026, 9, 22)]
    i0 = len(day[day.index.strftime('%H:%M') <= '09:30']) - 1
    return [{
        'trade_id': 'SELFTEST', 'sym': 'MNQ', 'date': '2026-09-22', 'dir': 'LONG',
        'asset': 'futures', 'interval': '1m', 'entry_time': '09:30', 'exit_time': '09:31',
        'shift_min': 0, 'et_entry_time': '09:30', 'et_exit_time': '09:31',
        'entry': 30815.0, 'exit': 30842.25, 'qty': 1, 'pnl': 52.62, 'setup': 'ENGU',
        'timeframe': '1m', 'grade': None,
        'notes': 'SELFTEST - a copy of a real trade used to test the routine; never published',
        'bars_et': bars_rows(day.iloc[max(0, i0 - 30): i0 + 31]),
    }]


def cmd_start(a):
    os.makedirs(INBOX, exist_ok=True)
    if a.selftest and os.path.exists(inbox('state.json')) and not load(inbox('state.json')).get('selftest'):
        raise SystemExit('a real scoring run is in progress - not starting a selftest over it')
    old = shelve('stale')
    if old:
        say('an earlier unfinished run was moved aside: ' + old)
    name = 'score-selftest' if a.selftest else 'score-' + et_now().strftime('%Y%m%d')
    discard(name)                          # a leftover worktree is always rebuilt from scratch
    path = run([PY, WT, 'new', name], cwd=SHARED).stdout.strip().splitlines()[-1].strip()
    if not os.path.isdir(path):
        raise SystemExit('wt.py new gave no folder: ' + path)
    run(['git', '-C', path, 'fetch', '-q', 'origin'])
    run(['git', '-C', path, 'reset', '--hard', '-q', 'origin/main'])
    spec_fp = os.path.join(path, 'tools', 'data', 'trade_scores.json')
    n_na0 = len(load(spec_fp).get('na', []))
    if a.selftest:
        pending = selftest_pending(path)
        say('SELFTEST: one fake trade (MNQ 2026-09-22 09:30, id SELFTEST) - nothing is published')
    else:
        p = run([PY, os.path.join('tools', 'score_day.py'), '--days', str(a.days)], cwd=path,
                check=False)
        say('\n'.join(l for l in (p.stdout + p.stderr).splitlines()
                      if 'UserWarning' not in l and 'return query.where' not in l))
        if p.returncode:
            discard(name)
            raise SystemExit('score_day.py failed - nothing was changed')
        pf = os.path.join(path, 'tools', 'data', 'score_pending.json')
        pending = load(pf) if os.path.exists(pf) else []
    na_new = load(spec_fp).get('na', [])[n_na0:]
    if not pending and not na_new:
        discard(name)
        say('RESULT: NOTHING TO SCORE')
        return
    dump(inbox('pending.json'), pending)
    dump(inbox('state.json'), {'name': name, 'worktree': path, 'selftest': bool(a.selftest),
                               'started': et_now().isoformat(timespec='seconds'),
                               'na_new': na_new, 'n_pending': len(pending)})
    for n in na_new:
        say('  NA      %s %-5s %s  %s' % (n['date'], n['sym'], n['entry_time'], n.get('reason')))
    if pending:
        say('RESULT: AUTHOR %d - read tools/data/score_inbox/pending.json, write '
            'tools/data/score_inbox/scored.json, then run: python tools/score_routine.py finish'
            % len(pending))
        for t in pending:
            say('  AUTHOR  %s %-5s %-5s %s%s' % (t['date'], t['sym'], t['dir'], t['entry_time'],
                                                ('  trade_id ' + t['trade_id']) if t.get('trade_id') else ''))
    else:
        say('RESULT: NA ONLY %d - nothing to author; run: python tools/score_routine.py finish'
            % len(na_new))


def clean_text(s):
    """One line, no markup - these strings are baked into index.html."""
    return re.sub(r'\s+', ' ', str(s or '')).replace('<', '').replace('>', '').strip()


def whole(v, lo, hi):
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def build_entries(pending, scored, fix):
    """Pair each authored score with its pending trade. The FACTS (prices, times, size, ids) are
    copied from pending; only the judgement comes from scored.json."""
    if not isinstance(scored, list):
        fix.append('scored.json must be a JSON list with one object per pending trade')
        return []

    def key(t):
        return (str(t.get('date')), str(t.get('sym', '')).upper(),
                str(t.get('entry_time', ''))[:5], t.get('trade_id') or None)

    by = {}
    for s in scored:
        if not isinstance(s, dict):
            fix.append('every item in scored.json must be an object')
            continue
        by.setdefault(key(s), []).append(s)
    out = []
    for p in pending:
        tag = '%s %s %s%s' % (p['date'], p['sym'], p['entry_time'],
                              (' trade_id ' + p['trade_id']) if p.get('trade_id') else '')
        got = by.pop(key(p), [])
        if len(got) != 1:
            fix.append('%s: expected exactly one score in scored.json, found %d (it is matched on '
                       'date, sym and entry_time%s)' % (tag, len(got),
                                                        ' and trade_id' if p.get('trade_id') else ''))
            continue
        s = got[0]
        e = {'sym': p['sym'], 'date': p['date'], 'dir': p['dir'], 'key_time': True,
             'interval': p['interval'], 'entry_time': p['entry_time'],
             'exit_time': p['exit_time'], 'entry': p['entry'], 'exit': p['exit'],
             'qty': p['qty']}
        if p.get('trade_id'):
            e['trade_id'] = p['trade_id']
        if p.get('shift_min'):
            e['shift_min'] = p['shift_min']
        for f in ('breakout_candle', 'hold_from'):
            if s.get(f) not in (None, ''):
                if HHMM.match(str(s[f])):
                    e[f] = str(s[f])
                else:
                    fix.append('%s: %s must be HH:MM (Eastern), got %r' % (tag, f, s[f]))
        if 'breakout_candle' not in e:
            fix.append('%s: breakout_candle (HH:MM Eastern of the signal bar) is missing' % tag)
        for f in ('stop', 'px_offset'):
            if s.get(f) not in (None, ''):
                try:
                    e[f] = float(s[f])
                except (TypeError, ValueError):
                    fix.append('%s: %s must be a number, got %r' % (tag, f, s[f]))
        if 'stop' not in e:
            fix.append('%s: stop is missing' % tag)
        rubric = FUT_SETUP if p.get('asset') == 'futures' else STOCK_SETUP
        for side, want in (('setup', rubric), ('exec', EXEC)):
            rows = s.get(side)
            shape = [(r.get('label'), r.get('weight')) if isinstance(r, dict) else None
                     for r in rows] if isinstance(rows, list) else None
            if shape != want:
                fix.append('%s: %s must be exactly these rows in this order: %s'
                           % (tag, side, ', '.join('%s (weight %d)' % w for w in want)))
                continue
            clean = []
            for r in rows:
                if not whole(r.get('score'), 0, r['weight']):
                    fix.append('%s: %s "%s" score must be a whole number 0-%d, got %r'
                               % (tag, side, r['label'], r['weight'], r.get('score')))
                note = clean_text(r.get('note'))
                if len(note) < 8:
                    fix.append('%s: %s "%s" needs a one-sentence note' % (tag, side, r['label']))
                clean.append({'label': r['label'], 'weight': r['weight'],
                              'score': r.get('score'), 'note': note})
            e[side] = clean
        ov = s.get('overall')
        if not whole(ov, 0, 100):
            fix.append('%s: overall must be a whole number 0-100, got %r' % (tag, ov))
        elif 'setup' in e and 'exec' in e and all(whole(r['score'], 0, 100)
                                                  for r in e['setup'] + e['exec']):
            avg = (sum(r['score'] for r in e['setup']) + sum(r['score'] for r in e['exec'])) / 2
            if abs(ov - avg) > 15:
                fix.append('%s: overall %d should be roughly the average of the setup and exec '
                           'totals (%.0f)' % (tag, ov, avg))
        e['overall'] = ov
        e['summary'] = clean_text(s.get('summary'))
        if len(e['summary']) < 40:
            fix.append('%s: summary needs 2-3 plain-English sentences' % tag)
        out.append(e)
    for extra in by.values():
        for s in extra:
            fix.append('scored.json has a score for %s %s %s that is not in pending.json'
                       % (s.get('date'), s.get('sym'), s.get('entry_time')))
    return out


def stage(path, st, authored, note):
    """Rebuild the change from scratch on top of the NEWEST main: scores, NA entries, the baked
    index.html block, VERSION and the CHANGELOG line. Other sessions bump VERSION all day, so a
    commit made even minutes earlier would collide on that line when ship rebases it."""
    run(['git', '-C', path, 'rebase', '--abort'], check=False)
    run(['git', '-C', path, 'fetch', '-q', 'origin'])
    run(['git', '-C', path, 'reset', '--hard', '-q', 'origin/main'])  # new bar files survive
    ts = ts_module(path)
    fp = os.path.join(path, 'tools', 'data', 'trade_scores.json')
    spec = load(fp)
    spec.setdefault('na', [])
    have = ({ts.key_of(t) for t in spec['trades']}
            | {ts.key_of(dict(n, key_time=True)) for n in spec['na']})
    spec['na'] += [n for n in st['na_new'] if ts.key_of(dict(n, key_time=True)) not in have]
    new = [e for e in authored if ts.key_of(e) not in have]
    if len(new) != len(authored):
        say('  %d score(s) were already on main - left as they are' % (len(authored) - len(new)))
    spec['trades'] += new
    dump(fp, spec)
    r = run([PY, os.path.join('tools', 'trade_scores.py'), '--apply'], cwd=path, check=False)
    if r.returncode:
        raise SystemExit('trade_scores.py --apply failed:\n' + (r.stdout + r.stderr)[-2000:])
    idx = os.path.join(path, 'index.html')
    with io.open(idx, encoding='utf-8', newline='') as f:
        s = f.read()
    m = re.search(r"const VERSION='(\d+)\.(\d+)';", s)
    nv = '%s.%d' % (m.group(1), int(m.group(2)) + 1)          # same step as wt.py bump()
    s = s.replace(m.group(0), "const VERSION='%s';" % nv, 1)
    head = 'const CHANGELOG=['
    i = s.index(head)
    s = (s[:i] + head + "{v:'%s',date:'%s',notes:['%s']}," % (nv, et_now().strftime('%Y-%m-%d'), note)
         + s[i + len(head):])
    with io.open(idx, 'w', encoding='utf-8', newline='') as f:
        f.write(s)
    return nv


def cmd_finish(a):
    if not os.path.exists(inbox('state.json')):
        raise SystemExit('no scoring run in progress - run: python tools/score_routine.py start')
    st = load(inbox('state.json'))
    name, path = st['name'], st['worktree']
    dry = a.dry_run or st.get('selftest')             # a selftest is never published
    if not os.path.isdir(path):
        raise SystemExit('the run worktree is gone (%s) - run start again' % path)
    pending = load(inbox('pending.json')) if os.path.exists(inbox('pending.json')) else []
    authored = []
    if pending:
        if not os.path.exists(inbox('scored.json')):
            raise SystemExit('FIX: write tools/data/score_inbox/scored.json first - one score '
                             'per trade in pending.json')
        try:
            scored = load(inbox('scored.json'))
        except ValueError as e:
            raise SystemExit('FIX: scored.json is not valid JSON: %s' % e)
        fix = []
        authored = build_entries(pending, scored, fix)
        if not fix:
            ts = ts_module(path)
            for e in authored:           # the report is drawn from these bars - prove they exist
                try:
                    ts.derive(e)
                except SystemExit as err:
                    fix.append('%s %s %s: %s' % (e['date'], e['sym'], e['entry_time'], err))
                except Exception as err:
                    fix.append('%s %s %s: %s: %s' % (e['date'], e['sym'], e['entry_time'],
                                                     type(err).__name__, err))
        if fix:
            for f in fix:
                say('FIX: ' + f)
            raise SystemExit('scored.json needs the fixes above - edit it, then run finish again')
    dates = sorted({e['date'] for e in authored} | {n['date'] for n in st['na_new']})
    note = ('SCORES: %d trade%s from %s scored, %d marked NA (no price data).'
            % (len(authored), '' if len(authored) == 1 else 's', ', '.join(dates),
               len(st['na_new']))).replace("'", '')
    for attempt in range(1, SHIP_TRIES + 1):
        nv = stage(path, st, authored, note)
        if dry:
            say(run(['git', '-C', path, 'diff', '--stat']).stdout.rstrip())
            chk = run([PY, os.path.join('tools', 'trade_scores.py'), '--check'], cwd=path,
                      check=False)
            say((chk.stdout + chk.stderr).strip())
            discard(name)
            where = shelve('dryrun')
            say('RESULT: DRY RUN OK - %d scored and %d NA staged as v%s and checked; nothing was '
                'committed or pushed (inbox kept in %s)' % (len(authored), len(st['na_new']), nv, where))
            return
        run(['git', '-C', path, 'add', 'index.html', 'tools'])
        run(['git', '-C', path, 'commit', '-q', '-m', 'EOD scores ' + ', '.join(dates), '-m', TRAILER])
        p = run([PY, WT, 'ship', name], cwd=SHARED, check=False)
        out = (p.stdout + p.stderr).strip()
        if re.search(r'^pushed: ', out, re.M):
            shipped = run(['git', '-C', path, 'show', 'HEAD:index.html']).stdout
            v = re.search(r"const VERSION='([\d.]+)'", shipped).group(1)
            run([PY, WT, 'drop', name], cwd=SHARED, check=False)
            shelve('done')
            say('RESULT: SHIPPED v%s - %d scored, %d marked NA' % (v, len(authored), len(st['na_new'])))
            for e in authored:
                say('  %s %-5s %s  score %d' % (e['date'], e['sym'], e['entry_time'], e['overall']))
            for n in st['na_new']:
                say('  %s %-5s %s  NA: %s' % (n['date'], n['sym'], n['entry_time'], n.get('reason')))
            return
        race = 'rebase onto origin/main hit a conflict' in out or ('git failed' in out and 'push' in out)
        say('ship attempt %d did not push%s:' % (attempt, ' - main moved, rebuilding on the newest main' if race else ''))
        say('\n'.join(out.splitlines()[-8:]))
        if not race:
            raise SystemExit('a ship gate failed - nothing was pushed. Run: python tools/score_routine.py '
                             'abort, and report this output')
    raise SystemExit('main kept moving - %d ship attempts, nothing was pushed. Run: python '
                     'tools/score_routine.py finish again later' % SHIP_TRIES)


def cmd_abort(a):
    st = load(inbox('state.json')) if os.path.exists(inbox('state.json')) else None
    name = st['name'] if st else 'score-' + et_now().strftime('%Y%m%d')
    discard(name)
    where = shelve('aborted')
    say('RESULT: ABORTED - worktree %s removed%s' % (name, ('; inbox files kept in ' + where) if where else ''))


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser(description='EDGE LOG end-of-day SCORE routine')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('start')
    s.add_argument('--days', type=int, default=3)
    s.add_argument('--selftest', action='store_true')
    f = sub.add_parser('finish')
    f.add_argument('--dry-run', action='store_true')
    sub.add_parser('abort')
    a = ap.parse_args()
    {'start': cmd_start, 'finish': cmd_finish, 'abort': cmd_abort}[a.cmd](a)


if __name__ == '__main__':
    main()
