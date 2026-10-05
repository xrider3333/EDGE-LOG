# RESMOM r1 - the forward BOOK line's MONTH-END COMPUTE: #463 + 0.264 x RES (RAW logged beside at 0.233), no orders. Specification: tools/rocfrontier/PREREG_RESMOM_LINE_R1.txt ([F2], LF sha256 9ab77351...) and its
# NOTE 1 (PREREG_RESMOM_LINE_R1_NOTE1.txt, LF sha256 ea559fe9...: [N1] the monitor's constants, [N2] the month-end order pin -> rank -> mark, [N3] the reads, [N4] the sealed year as ranking inputs only, [N5] what this lane does not do).
# The registered strategy is imported, never copied and never edited: r17_resmom.py's universe, hygiene, regression, score, pick, path, cost, borrow and dividend functions are called as they are (the way r17 wraps r15_ddw). Where the specification is silent the
# choice is marked CHOICE [L1] .. [L21] (repeated in the hand-over). Every rule below is NOTE 1 unless marked.
#   python tools/rocfrontier/r17_resmom_line.py freeze                          [N1] ONCE: the 101 walk-forward RES holds' P&Ls (Stage A's registered reading, refused unless they sum to Stage A's net within $1), the monitor's boundary B (false-stop
#                                                                               calibration), the dollar read's null spread (circular block bootstrap on resmom_cells_daily_wf.csv); prints the FROZEN block; re-run after pasting it = must reproduce it exactly
#   python tools/rocfrontier/r17_resmom_line.py pin  --through D [--root R]     [N2](1) hash every file the photograph's manifest lists, refuse on any mismatch, append one dated row to pins.csv (reads no bar)
#   python tools/rocfrontier/r17_resmom_line.py rank --through D [--root R]     [N2](2) the registered functions on the pinned photograph + the house ES master through the month-end close -> rank_<D>.csv, hold_next.txt (the first rank is 2026-10-30)
#   python tools/rocfrontier/r17_resmom_line.py mark --through D [--root R]     [N2](3) value every session after the previous pinned month-end up to D from THIS photograph alone -> line_daily.csv, line_parts.csv, line_log.csv, marks.csv; prints the overlap comparison
#   python tools/rocfrontier/r17_resmom_line.py read                            [N3] the monitor (k, t, B, status) at holds 12 / 18 / 24 / 30 / 36 and the dollar read at hold 36; prints the rows used and the pins
#   python tools/rocfrontier/r17_resmom_line.py parity                          walk-forward ONLY: the rank code path, the mark code path and the freeze's hold P&Ls against the registered harness and resmom_cells_daily_wf.csv
#   python tools/rocfrontier/r17_resmom_line.py selftest                        fakes only: no network, no key, temp folders (fake photographs, fake ES master, fake TBIS file)
# EACH MONTH-END, in this order: pull the photograph (r17_resmom_pull.py pull --through D --hold <resmom_line>\hold_next.txt) -> pin -> rank -> mark -> read; a month-end's mark needs the ranks of the two months before it, never its own.
# Outputs: C:\EdgeLog\_anatomy_cache\rocfrontier\resmom_line\ (env EDGELOG_RESMOM_LINE), outside git: freeze.json (+ .sha256), pins.csv, ranks.csv (which code made which rank file), rank_<D>.csv, hold_next.txt, line_daily.csv, line_parts.csv, line_log.csv, marks.csv (the commit
# record of a mark), overlap_<D>.csv (+ _calendar.csv), line.lock. Atomic writes (temp file + os.replace); append-only logs refuse a second append of the same session / hold; one OS lock around every write; every guard runs before the first write.
# Never here: a network call, an Alpaca key (the pull command r17_resmom_pull.py is NOT imported: it imports the key lookup), a write under C:\EdgeLog\alpaca_cache, an order. The SEALED YEAR (2025-06-30 .. 2026-06-30) is ranking input only: no P&L, statistic or
# figure dated inside it is computed or printed by anything here (guard_dates); freeze / parity read walk-forward data only (the harness's loaders cut every input before 2025-06-30).
import ast, contextlib, csv, hashlib, io, json, math, os, re, shutil, socket, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("EDGELOG_ROOT", os.path.dirname(os.path.dirname(HERE)))
for _p in (REPO, os.path.join(REPO, "tools"), HERE):                                  # r5_siporb's own path set-up (the shared engine + loaders); HERE last in the list = first on the path
    if _p not in sys.path:
        sys.path.insert(0, _p)
import numpy as np, pandas as pd
import r17_resmom as M                                                                  # the registered harness, unchanged (it imports r15_ddw -> r5_siporb / r11_risk / r12_mdl / r13_attn)
from paired_seq_stop import tstat, BOUND_EX                                             # the house t (mean / (sd ddof 1 / sqrt n); 0.0 below 2 values or no spread) and the ex-extreme bound 2.0 - imported, not copied

TS = pd.Timestamp
S, D15, A13, R11 = M.S, M.D15, M.A13, M.R11
refuse, patched, sha_raw = M.refuse, M.patched, M.sha_raw
LINE_OUT = os.environ.get("EDGELOG_RESMOM_LINE", r"C:\EdgeLog\_anatomy_cache\rocfrontier\resmom_line")   # every output of this tool, outside git
ROOT_DEFAULT = r"C:\EdgeLog\alpaca_cache\resmom_fwd"                                    # where r17_resmom_pull.py publishes <ROOT>\<through>\ (read only here)
LINE_PREREG, NOTE_PREREG = os.path.join(HERE, "PREREG_RESMOM_LINE_R1.txt"), os.path.join(HERE, "PREREG_RESMOM_LINE_R1_NOTE1.txt")
LINE_SHA = "9ab77351453c4561cf9f852fe6aea48027a181d3764d7b811d5ea416f2f28211"           # LF sha256 of the line's registration (unchanged so r17_resmom_gate.py still verifies)
NOTE_SHA = "ea559fe9791527ff2a394802aa45a694138ab90e5804a4775a4747b102787bb1"           # LF sha256 of NOTE 1 as committed - the specification of this tool
CELLS_CSV = os.path.join(M.OUT, "resmom_cells_daily_wf.csv")                            # RES / RAW walk-forward daily P&L on #463's index (r17_resmom_export.py)
CELLS_CSV_SHA = "bed7bf8b98d201894471cd3e72bd146bb87260c6cc8d1ac54b8167f923d41819"     # its sha256 (the file's bytes) as exported and registered in NOTE 1 [N1](c)
STAGE_A = os.path.join(M.OUT, "resmom_stageA.json")                                     # Stage A's record: RES / RAW walk-forward nets, harness stamps
C_RES, C_RAW = 0.264, 0.233                                                             # the line's volatility sizes ([F2]: c 0.264 for RES; RAW logged beside at 0.233)
FIRST_RANK, FIRST_FILL = TS("2026-10-30"), TS("2026-11-02")                             # the first month-end rank of the line; its first fills at the open of the next session
SEALED = (M.LB0, M.LB1)                                                                 # 2025-06-30 .. 2026-06-30 INCLUSIVE: ranking input only ([N4])
LOOKS, C_STAR = (12, 18, 24, 30, 36), 2.47                                              # [N3] the monitor's looks (holds) and Q16's 36-month family-wise c* for the dollar read
BOOT = {"draws": 20000, "rows": 756, "block": 21, "chunk": 2500, "seed": 20261016}      # [N1](c) the null spread: 20,000 draws of 756 rows (36 months x 21 sessions), block 21, one sign per block, chunks of 2,500
STOP = {"paths": 4000, "steps": 36, "seed": 20260929, "bounds": tuple(3.0 + 0.25 * i for i in range(21)), "max_false": 0.05}   # [N1](b) B = the smallest of 3.00, 3.25 .. 8.00 with at most 5% false stops
WF_ROWS_FROM, WF_ROWS_ALL = TS("2017-01-03"), TS("2016-07-01")                          # [N1](c) RES's first fill; the same figure from the start of WF is printed beside, never used
CSV_END = M.PRE_END                                                                     # 2025-06-29: the CSV's last row
PHOTO_FILES = ("daily_raw.parquet", "daily_split.parquet", "corporate_actions.csv")     # the three files of a photograph the registered harness reads (the manifest also lists the raw JSONL and symbols.txt)
MIN_SESSIONS = 290                                                                      # r17_resmom_pull's own floor: 252 (regression) + 25 (hygiene lead) + margin
PINS_HEAD = ("through", "folder", "manifest_sha256", "calendar_sha256", "pinned_utc", "files")
LOG_HEADS = {"line_daily.csv": ("date", "RES", "RAW", "RES_line", "RAW_line"), "line_parts.csv": ("through", "rank_date", "part", "from_date", "to_date", "RES", "RAW"),
             "line_log.csv": ("k", "rank_date", "fill_date", "exit_date", "RES", "RAW", "d_k"),
             "marks.csv": ("through", "prev_through", "folder", "manifest_sha256", "calendar_sha256", "utc", "sessions", "first_session", "last_session", "RES", "RAW", "completed_k", "tool_sha256_lf"),
             "ranks.csv": ("through", "folder", "manifest_sha256", "rank_sha256", "pool", "utc", "tool_sha256_lf")}            # ranks.csv = which code made which rank file from which pinned photograph
MARK_LEDGERS = ("line_daily.csv", "line_parts.csv", "line_log.csv", "marks.csv")                                            # what a mark appends to (a first photograph's mark appends to none)
RANK_HEAD = ("cell", "side", "symbol", "score")

# FROZEN-BEGIN (the block the first `freeze` run printed, pasted here: the monitor's B, its false-stop table, the dollar read's spread and the 101 hold P&Ls; `read` uses it; every later `freeze` must reproduce it exactly or refuses)
FROZEN = {
    "c_res": 0.264,
    "c_raw": 0.233,
    "B": 3.0,
    "false_stop": {'3.00': 0.0225},
    "boot": {'draws': 20000, 'rows': 756, 'block': 21, 'chunk': 2500, 'seed': 20261016},
    "stop": {'paths': 4000, 'steps': 36, 'seed': 20260929, 'looks': [12, 18, 24, 30, 36]},
    "rows_from": '2017-01-03',
    "rows_to": '2025-06-27',
    "n_rows": 2214,
    "sd_sum": 91388.28730886769,
    "spread": 24126.50784954107,
    "cells_csv_sha256": 'bed7bf8b98d201894471cd3e72bd146bb87260c6cc8d1ac54b8167f923d41819',
    "res_net": 234037.217375,
    "raw_net": 303027.760496,
    "res_holds": [
        3668.281272, -9939.195668, 1163.151213, -1554.556212, 18647.215724, -12694.058668,
        8366.497469, 8455.859409, -9503.031754, 7323.883813, -11385.604723, -13536.574145,
        6266.69252, 815.89505, -4881.157772, -3280.011628, 16969.854824, -13368.028548,
        -4787.211098, 20046.67966, -904.71708, -4974.543372, -4797.64036, 5336.223902,
        -12210.495061, 7004.031186, 3213.377457, -10514.652227, 27344.631822, -14155.794318,
        7255.76681, 30906.231158, -30408.389762, -3489.813213, -9245.28481, -8910.799368,
        21294.483576, 6742.11744, 31243.197508, -10662.127212, 15314.210795, 11366.058188,
        24590.614419, 766.967438, 12951.832988, -15726.44521, 2608.82466, 6951.27472,
        34238.728693, -6083.494885, -35815.459341, -16245.494233, -6434.835064, 5397.318926,
        -3082.514523, 3796.192579, -5998.977818, 9965.919286, 11343.156833, -14897.10565,
        -6197.83316, 15443.584652, 19400.966358, 23436.675925, 17719.909852, 1206.106161,
        -5372.802374, 14807.275224, 12617.637637, 5679.230727, -2577.045736, -1513.252579,
        -27242.220573, 11327.849953, 4923.661981, -3064.899925, 11357.561304, -4217.47566,
        -9715.329674, 11331.559524, 3135.070295, 5198.002911, 7816.732132, -15427.28583,
        20059.255411, 33238.372037, -4273.153948, -2711.541915, 8604.316331, 4918.510955,
        -8663.355729, 10936.250711, -5445.141636, 6046.754554, -5055.786746, -6362.423407,
        12560.524102, -3444.455039, -1494.373867, 10033.277947, 3149.350873,
    ],
    "raw_holds": [
        5195.089808, -10571.786435, 1627.083825, -4087.419628, 12233.086181, -13324.773823,
        9389.483363, 8048.270396, -4763.655614, 6149.350218, -14329.288208, -6270.928842,
        10110.820957, 2544.971917, -7403.952837, -3914.390672, 17317.524127, -18441.822284,
        -2191.996369, 25851.00668, -1438.282695, -12077.654909, -3594.623135, 3412.970633,
        -7640.399875, 2902.64686, 1996.949486, -5454.903381, 27266.591214, -14825.956233,
        5741.705047, 27654.528448, -28599.702871, 3217.085431, -3767.64535, -10198.982914,
        11967.806697, 10694.592393, 28038.865443, -6290.325605, 6383.619054, 13430.480055,
        32230.1726, -1641.062114, 23626.861537, -12485.356236, -15417.084386, 4833.860076,
        44908.43128, -28473.567275, -30769.64789, -15820.025089, -10702.441369, 19156.388868,
        -11628.54435, 5200.419146, -859.12221, 12785.508228, 19751.314189, -8629.423712,
        5638.720337, 25565.091146, 27139.451778, 29411.010963, 30479.539441, -8905.254656,
        338.37897, 16759.417525, 6989.732065, 12858.523271, 8632.213056, -1889.928041,
        -31223.358831, 5616.58519, 2772.808291, 14184.33562, 3.629928, -14532.088219,
        -9991.813101, 11874.339702, -606.309319, 4318.238989, 10889.766541, -14756.372942,
        12657.585069, 38719.787268, -6308.293421, -9879.339111, 12668.278927, 4957.015877,
        -16429.360411, 1659.331002, 4739.519034, 13089.675464, 24946.408276, -8069.08276,
        10603.151545, -14165.305052, -16184.53184, 16853.948735, 13549.596344,
    ],
}
# FROZEN-END


# ------------------------------------------------------------------ small helpers: hashes, atomic writes, the lock, csv rows, dates
def sha_lf(path):
    return R11.sha_lf(path)


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write_atomic(path, data):
    """temp file in the same folder + os.replace: a reader sees the old file or the new one, never half of one"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "wb") as f:
        f.write(data if isinstance(data, bytes) else data.encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


@contextlib.contextmanager
def line_lock(out=None):
    """ONE OS lock around every write of this tool (msvcrt.locking on byte 0 of an open handle: the kernel drops it when the handle closes or the process dies - no lock file with a stale-breaker; the holder's name
    is written from byte 1 on, because a mandatory lock makes byte 0 unreadable to the others). A second writer REFUSES (it does not wait and does not go ahead without the lock)"""
    out = out or LINE_OUT
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "line.lock")
    if not os.path.exists(path) or os.path.getsize(path) < 80:                         # an 80-byte file, so the holder's line below overwrites in place (the file never grows)
        with open(path, "ab") as g:
            g.write(b"\n" * 80)
    fh = open(path, "r+b")
    try:
        if os.name == "nt":
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        refuse(f"refused: another run of r17_resmom_line.py holds the lock on {out} (one writer at a time) - nothing written")
    try:
        fh.seek(1)
        fh.write(f"pid {os.getpid()} {utc_now()}".encode("ascii").ljust(78) + b"\n")
        fh.flush()
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        fh.close()


def fnum(x):
    """a number as it goes into a log: the shortest string that reads back to the same float"""
    return repr(float(x))


def read_rows(path):
    """a csv log -> [dict of strings] ([] when the file is not there yet)"""
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(path, head, rows):
    """the whole csv (header + rows, LF) written atomically; rows = sequences in the header's order"""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(head)
    for r in rows:
        w.writerow(r)
    write_atomic(path, buf.getvalue())


def parse_day(text, what="--through"):
    s = str(text or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        refuse(f"refused: {what} {s!r} is not a date written YYYY-MM-DD (nothing done)")
    try:
        return TS(s)
    except ValueError:
        refuse(f"refused: {what} {s!r} is not a real calendar date (nothing done)")


def nth_weekday(year, month, wd, n):
    """the n-th (n >= 1) or last (n = -1) weekday `wd` (0 = Monday) of a month"""
    d = TS(year=year, month=month, day=1)
    if n > 0:
        d += pd.Timedelta(days=(wd - d.dayofweek) % 7 + 7 * (n - 1))
        return d
    d = d + pd.offsets.MonthEnd(0)
    return d - pd.Timedelta(days=(d.dayofweek - wd) % 7)


def nyse_closed(d):
    """CHOICE [L4]: an NYSE full-day closure by the regular holiday rules (New Year's Day - a Sunday one on the Monday, a Saturday one not observed -, Martin Luther King Jr. Day, Washington's Birthday, Good Friday, Memorial Day, Juneteenth,
    Independence Day, Labor Day, Thanksgiving, Christmas; a Saturday holiday is observed on the Friday, a Sunday one on the Monday). Special closures are not known here; the selftest compares this with r17_resmom_pull's table for 2026-2027"""
    from dateutil.easter import easter
    d = TS(d).normalize()
    y, hol = d.year, set()
    for yy in (y - 1, y, y + 1):
        ny = TS(year=yy, month=1, day=1)
        hol.add(ny + pd.Timedelta(days=1) if ny.dayofweek == 6 else ny)
        hol.update((nth_weekday(yy, 1, 0, 3), nth_weekday(yy, 2, 0, 3), TS(easter(yy)) - pd.Timedelta(days=2), nth_weekday(yy, 5, 0, -1), nth_weekday(yy, 9, 0, 1), nth_weekday(yy, 11, 3, 4)))
        for mo, dy in ((6, 19), (7, 4), (12, 25)):
            h = TS(year=yy, month=mo, day=dy)
            hol.add(h - pd.Timedelta(days=1) if h.dayofweek == 5 else h + pd.Timedelta(days=1) if h.dayofweek == 6 else h)
    return d in hol


def month_end_session(d):
    """True when d is the last session of its calendar month by the weekday / NYSE-closure rule: a weekday, not closed, and every later weekday of the month a closure. The harness's schedule takes each month's last session in the data as the
    rank; with data only through D a rank date must be certified month-end from the calendar - CHOICE [L4]"""
    d = TS(d).normalize()
    if d.dayofweek >= 5 or nyse_closed(d):
        return False
    q = d + pd.Timedelta(days=1)
    while q.month == d.month:
        if q.dayofweek < 5 and not nyse_closed(q):
            return False
        q += pd.Timedelta(days=1)
    return True


def parse_through(text, first=None, what="the command"):
    """--through: a real month-end session, on/after the line's first rank - else a refusal (nothing done)"""
    d = parse_day(text)
    if not month_end_session(d):
        refuse(f"refused: --through {d:%Y-%m-%d} is not the last NYSE session of its month - the line's ranks are month-ends only (nothing done)")
    first = FIRST_RANK if first is None else first
    if d < first:
        refuse(f"refused: --through {d:%Y-%m-%d} is before the line's first month-end {first:%Y-%m-%d} - {what} starts there (nothing done)")
    return d


def next_weekday(d):
    q = TS(d).normalize() + pd.Timedelta(days=1)
    while q.dayofweek >= 5:
        q += pd.Timedelta(days=1)
    return q


def guard_dates(dates, what):
    """the sealed-year guard: a P&L, statistic or figure dated 2025-06-30 .. 2026-06-30 is never computed for printing here ([N4]) - refuses before anything is shown"""
    bad = [TS(d) for d in dates if SEALED[0] <= TS(d) <= SEALED[1]]
    if bad:
        refuse(f"refused: {what} would print a figure dated inside the sealed year ({SEALED[0]:%Y-%m-%d} .. {SEALED[1]:%Y-%m-%d}; first such date {min(bad):%Y-%m-%d}) - the sealed year is ranking input only (nothing printed)")


def money(x):
    """dollars for a print: the sign before the $ sign, whole dollars from 1,000 up, cents below"""
    body = f"${abs(x):,.0f}" if abs(x) >= 1000 else f"${abs(x):,.2f}"
    return ("-" if x < 0 and abs(x) >= 0.005 else "") + body


def check_registered():
    """the two registrations this tool implements must still be the committed ones (a changed spec = a new file): the line's registration, NOTE 1, and the strategy's own (r17_resmom.prereg_ok: its sha and the committed blob)"""
    for p, sha, nm in ((LINE_PREREG, LINE_SHA, "PREREG_RESMOM_LINE_R1.txt"), (NOTE_PREREG, NOTE_SHA, "PREREG_RESMOM_LINE_R1_NOTE1.txt")):
        if not os.path.exists(p):
            refuse(f"refused: {nm} is not next to this file - the specification cannot be verified (nothing done)")
        if sha_lf(p) != sha:
            refuse(f"refused: {nm} DIFFERS from the registered text (LF sha256 {sha[:8]}...) - a changed spec is a new file (nothing done)")
    with contextlib.redirect_stdout(io.StringIO()):
        pok = M.prereg_ok()
    return {"line_prereg_sha256_lf": LINE_SHA, "note1_sha256_lf": NOTE_SHA, "resmom_prereg_sha256_lf": M.PREREG_SHA, "resmom_prereg_committed": pok["committed"]}


# ------------------------------------------------------------------ the photograph: manifest check and the pin ([N2](1))
def folder_name(through, rev=1):
    return f"{TS(through):%Y-%m-%d}" if rev == 1 else f"{TS(through):%Y-%m-%d}_r{rev}"


def verify_photo(folder, through):
    """hash every file the photograph's manifest lists; refuse on any mismatch (a missing manifest, a listed file that is missing or whose sha256 is not the manifest's, a manifest of another month-end, a listed name that points out of the
    folder, a photograph without the three files the harness reads). Reads no bar -> {manifest_sha256, calendar_sha256, files, man}"""
    mp = os.path.join(folder, "manifest.json")
    if not os.path.isfile(mp):
        refuse(f"refused: {folder} holds no manifest.json - not a published photograph (nothing read)")
    try:
        with open(mp, encoding="utf-8") as f:
            man = json.load(f)
    except (OSError, ValueError):
        refuse(f"refused: {mp} is not readable JSON (nothing read)")
    shas = man.get("sha256") if isinstance(man, dict) else None
    if not isinstance(shas, dict) or not shas:
        refuse(f"refused: {mp} lists no files (no sha256 section) (nothing read)")
    if man.get("through") != f"{TS(through):%Y-%m-%d}":
        refuse(f"refused: {mp} is the photograph through {man.get('through')}, not {TS(through):%Y-%m-%d} (nothing read)")
    miss = [n for n in PHOTO_FILES if n not in shas]
    if miss:
        refuse(f"refused: the manifest does not list {miss} - the files the harness reads (nothing read)")
    bad = []
    for nm, want in sorted(shas.items()):
        p = os.path.join(folder, nm)
        if os.path.basename(nm) != nm or not os.path.isfile(p):
            bad.append(f"{nm}: missing")
        elif sha_raw(p) != want:
            bad.append(f"{nm}: sha256 differs from the manifest's")
    if bad:
        refuse(f"refused: the photograph {folder} does not match its manifest ({'; '.join(bad)}) - changed or incomplete after it was published (nothing read)")
    return {"manifest_sha256": sha_raw(mp), "calendar_sha256": shas["corporate_actions.csv"], "files": len(shas), "man": man}


def pin_cmd(through, root=None, rev=1, out=None, first=None):
    """[N2](1) PIN, before any bar is read: the manifest's files hashed (verify_photo), then ONE dated row (through date, manifest sha256, calendar sha256, UTC time + the folder name and the number of files hashed) appended to pins.csv.
    CHOICE [L9]: a month-end is pinned once - an identical second pin is a no-op, another photograph of the same month-end (a re-pull, _r2) refuses: which one the line reads is the lead's call, never silent"""
    out = out or LINE_OUT
    t = parse_through(through, first, "the pin")
    check_registered()
    root = os.path.abspath(root or ROOT_DEFAULT)
    folder = os.path.join(root, folder_name(t, rev))
    if not os.path.isdir(folder):
        have = sorted(d for d in os.listdir(root) if d.startswith(f"{t:%Y-%m-%d}")) if os.path.isdir(root) else []
        refuse(f"refused: no photograph folder {folder} (published here: {have or 'none for this month-end'}; use --rev N for a re-pull) (nothing pinned)")
    v = verify_photo(folder, t)
    with line_lock(out):
        pp = os.path.join(out, "pins.csv")
        pins = read_rows(pp)
        same = [p for p in pins if p["through"] == f"{t:%Y-%m-%d}"]
        if same:
            if same[0]["manifest_sha256"] == v["manifest_sha256"] and same[0]["folder"] == os.path.basename(folder):
                print(f"pin {t:%Y-%m-%d}: already pinned (identical manifest sha256 {v['manifest_sha256'][:16]}..., pinned {same[0]['pinned_utc']}) - nothing appended")
                return same[0]
            refuse(f"refused: {t:%Y-%m-%d} is already pinned to {same[0]['folder']} (manifest sha256 {same[0]['manifest_sha256'][:16]}...); this is {os.path.basename(folder)} ({v['manifest_sha256'][:16]}...) - a re-pull is the lead's call (nothing appended)")
        row = [f"{t:%Y-%m-%d}", os.path.basename(folder), v["manifest_sha256"], v["calendar_sha256"], utc_now(), str(v["files"])]
        write_rows(pp, PINS_HEAD, [[p[h] for h in PINS_HEAD] for p in pins] + [row])
    print(f"pin {t:%Y-%m-%d}: {os.path.basename(folder)}: {v['files']} files hashed against the manifest, all match; manifest sha256 {v['manifest_sha256']}; calendar sha256 {v['calendar_sha256']}; appended to {pp}")
    return dict(zip(PINS_HEAD, row))


def pin_lookup(out, through):
    """the pin row of a month-end (refuses without one: a photograph is read only through its pin)"""
    rows = [p for p in read_rows(os.path.join(out, "pins.csv")) if p["through"] == f"{TS(through):%Y-%m-%d}"]
    if not rows:
        refuse(f"refused: {TS(through):%Y-%m-%d} is not pinned (run `pin --through {TS(through):%Y-%m-%d}` first: a photograph is read only through its pin) (nothing read)")
    return rows[0]


def open_pinned(out, through, root=None):
    """the pinned photograph's folder after re-verifying it against its pin: the manifest's sha256 is the pinned one and every listed file still hashes to the manifest's"""
    pin = pin_lookup(out, through)
    folder = os.path.join(os.path.abspath(root or ROOT_DEFAULT), pin["folder"])
    if not os.path.isdir(folder):
        refuse(f"refused: the pinned photograph folder {folder} is not there (nothing read)")
    v = verify_photo(folder, TS(through))
    if v["manifest_sha256"] != pin["manifest_sha256"] or v["calendar_sha256"] != pin["calendar_sha256"]:
        refuse(f"refused: {folder} is not the photograph that was pinned on {pin['pinned_utc']} (manifest sha256 {v['manifest_sha256'][:16]}... vs the pin's {pin['manifest_sha256'][:16]}...) (nothing read)")
    return folder, pin, v


# ------------------------------------------------------------------ the photograph's World: the registered loaders on its bars + its calendar (+ one phantom session as the fill / exit row)
def add_phantom(df, date):
    """a long daily frame (symbol categorical, date, o h l c v) + ONE session `date` on which every symbol has a row with no price and no volume - the session the loaders then see as the last row"""
    cats = df["symbol"].cat.categories
    ph = pd.DataFrame({"symbol": pd.Categorical(cats, categories=cats), "date": TS(date), "o": np.nan, "h": np.nan, "l": np.nan, "c": np.nan, "v": np.nan})
    out = pd.concat([df, ph], ignore_index=True)
    out["symbol"] = out["symbol"].astype("category")
    return out


def es_stub():
    """an ES master with no bar: mark values positions and reads no market return (CHOICE [L3]) - r15's es_prints / es_series turn it into all-NaN returns"""
    e = pd.DataFrame({"open": np.array([], float), "close": np.array([], float)}, index=pd.DatetimeIndex([], tz="US/Eastern"))
    return {"raw": e, "adj": e.copy()}


def photo_world(folder, through, es="real"):
    """the registered World of a photograph through `through` -> (W, info). CHOICE [L1]: the harness's loaders are called as they are on the photograph's own files (r5_siporb.path_of / read_long swapped for the block, never edited) and ONE phantom
    session - the next weekday, every name with no price - is appended to both daily frames, so the unmodified universe / hygiene / return arrays have a row for the rank's FILL session (r = T-2, f = T-1) and for a held position's EXIT session
    that does not exist yet. The phantom row carries no price: nothing is read from it except the universe (computed from sessions before it). CHOICE [L2]: the calendar is the photograph's own (wide_load enforce=False: the pin, not WIDE_CA_SHA, vouches for it).
    CHOICE [L3]: es='real' = the house ES master through the month-end close (rank); es='stub' = none (mark: valuation reads no ES); TBIS = the harness's file as it is - it ends 2026-06-30, so no session of a photograph carries a TBIS flag and that hygiene reason cannot fire
    (printed 'n/a (no forward TBIS)')"""
    through = TS(through)
    P = next_weekday(through)
    t_end = P + pd.Timedelta(days=1)
    orig = S.read_long
    buf = io.StringIO()
    with patched(S, path_of=lambda *p: os.path.join(folder, *p), read_long=lambda kind, cut: add_phantom(orig(kind, cut), P)):
        with contextlib.redirect_stdout(buf):                                          # r5_siporb.Data prints its own universe line (with the phantom date) and add_tbis_flags its counts: shown below, in our words
            D = M.load_data(t_end)
        tbis = D15.load_tbis(t_end)
        es_frames = es_stub() if es == "stub" else D15.load_es(t_end)[0]
        cal, winfo = M.wide_load(t_end, need=True, enforce=False, csv=os.path.join(folder, "corporate_actions.csv"), manifest=os.path.join(folder, "manifest.json"))
        W = M.build_world(D, t_end, es_frames, tbis, cal)
        D15.release(D)
    lines = [ln.strip() for ln in buf.getvalue().splitlines() if ln.strip().startswith(("TBIS", "WARNING")) or "WARNING" in ln]
    info = {"phantom": P, "t_end": t_end, "n_real": W.T - 1, "first": W.days[0], "last": W.days[-2], "tbis_rows": int(len(tbis)), "tbis_last_day": (TS(tbis["day"].max()) if len(tbis) else None), "loader_lines": lines, "es": es}
    return W, info


def check_world(W, through, need_es=False):
    """a photograph's world must hold the month-end as its last real session, enough history for the registered windows and a calendar that starts before the regression window (r17's [D1] gap cannot arise: the pull's calendar starts 430 days back)
    -> (r, f): the rank row and the (phantom) fill row"""
    r, f = W.T - 2, W.T - 1
    if W.days[r] != TS(through):
        refuse(f"refused: the photograph's last real session is {W.days[r]:%Y-%m-%d}, not {TS(through):%Y-%m-%d} (nothing computed)")
    if r + 1 < MIN_SESSIONS or r < M.SPEC["win"] - 1:
        refuse(f"refused: the photograph holds {r + 1} sessions, fewer than the {MIN_SESSIONS} its window needs (252 + the hygiene lead + margin) (nothing computed)")
    start = M.calendar_start(W.ca["file"]["manifest"])
    a = M.windows(r)[0]
    if start is None or start > W.days[a]:
        refuse(f"refused: the photograph's calendar starts {None if start is None else f'{start:%Y-%m-%d}'}, after the regression window's first session {W.days[a]:%Y-%m-%d} - dividends would be missing from the windows (nothing computed)")
    if need_es and not np.isfinite(W.es.ret[r]):
        refuse(f"refused: the house ES master has no return for the month-end session {W.days[r]:%Y-%m-%d} (its last bar is earlier: refresh it first) - the ranking would silently skip the latest session (nothing computed)")
    return r, f


# ------------------------------------------------------------------ [N2](2) RANK: the registered pool / score / pick functions at the month-end close
def rank_picks(W, r, f, x=-1, post_mode="remove", phantom_fill=True):
    """the registered rm_one at rank row r (units=False: picks only) -> (rec, cnt). CHOICE [L5]: at a forward rank no hold exists yet (x = -1), so the registered reading's look-ahead removals - a hygiene flag or a spin-off inside the hold,
    which r17 applies BEFORE ranking - cannot be made; the pool is the registered one without them. CHOICE [L6]: nor can the fill be known: rm_one's 'a name with no open at the fill session cannot be filled' reads W.Ao[f], so for the call that
    row holds the rank close's split-safe price - a name is fillable iff it has a close and a split factor at the rank session (put back afterwards). x given (parity) = the registered call"""
    saved = None
    if phantom_fill:
        saved = W.Ao[f].copy()
        W.Ao[f] = W.Ac[r]
    try:
        return M.rm_one(W, r, f, x, post_mode, units=False)
    finally:
        if saved is not None:
            W.Ao[f] = saved


def rank_rows_of(W, rec):
    """a rebalance's picks -> [(cell, side, symbol, score)]: per cell the 50 longs (highest score first) then the 50 shorts (lowest first)"""
    rows = []
    for cell in M.CELLS:
        lg, sh = rec.pick[cell]
        for side, idx in (("long", lg), ("short", sh)):
            rows += [(cell, side, str(W.syms[rec.pool[i]]), float(rec.score[cell][i])) for i in idx]
    return rows


def rank_bytes(rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(RANK_HEAD)
    for cell, side, sym, sc in rows:
        w.writerow([cell, side, sym, fnum(sc)])
    return buf.getvalue().encode("ascii")


def rank_files(out):
    """[(date, path)] of the rank_<date>.csv files, oldest first"""
    if not os.path.isdir(out):
        return []
    found = [(TS(m.group(1)), os.path.join(out, nm)) for nm in os.listdir(out) for m in [re.fullmatch(r"rank_(\d{4}-\d{2}-\d{2})\.csv", nm)] if m]
    return sorted(found)


def read_rank(path):
    return read_rows(path)


def prev_month_key(d):
    d = TS(d)
    return (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)


def hold_next_sets(out, upto):
    """the names (both cells, both sides) of each of the last TWO ranks at / before `upto`, oldest first -> [(rank date, set of symbols)]; one entry only for the first rank, which has no earlier one"""
    last2 = [(d, p) for d, p in rank_files(out) if d <= TS(upto)][-2:]
    return [(d, {r["symbol"] for r in read_rank(p)}) for d, p in last2]


def write_hold_next(out, upto):
    """[N2](2) hold_next.txt = the UNION of the last TWO ranks' names - RES and RAW, longs and shorts - sorted, one symbol a line, written atomically. Hold k exits at the open AFTER month-end k+1, which only the photograph after that holds, so the pull for it must still
    carry hold k's names (a name delisted mid-hold falls out of the base list and the active set) -> {'names', 'this': (rank date, names), 'prev': (rank date, names) or None, 'prev_only': names only in the earlier rank, 'union'}"""
    sets = hold_next_sets(out, upto)
    names = sorted(set().union(*(st for _, st in sets)))
    write_atomic(os.path.join(out, "hold_next.txt"), "\n".join(names) + "\n")
    (d1, s1), prev = sets[-1], (sets[-2] if len(sets) > 1 else None)
    return {"names": names, "this": (d1, len(s1)), "prev": None if prev is None else (prev[0], len(prev[1])), "prev_only": 0 if prev is None else len(prev[1] - s1), "union": len(names)}


def rank_core(folder, t, es="real"):
    """world -> checks -> the registered picks of the month-end -> (W, info, r, f, rec, cnt, rows)"""
    W, info = photo_world(folder, t, es)
    r, f = check_world(W, t, need_es=(es == "real"))
    rec, cnt = rank_picks(W, r, f)
    if not rec.traded:
        refuse(f"refused: the pool at {TS(t):%Y-%m-%d} holds {len(rec.pool)} names, fewer than the {2 * M.SPEC['n_side']} the registered rule needs - no trade this month; the lead decides (nothing written)")
    return W, info, r, f, rec, cnt, rank_rows_of(W, rec)


def print_counts(W, info, r, rec, cnt):
    """the hygiene / eligibility counts of a rank, in r17's words; the TBIS reason is 'n/a' where the TBIS file ends before the window starts"""
    lo_pre = r - M.SPEC["skip"] - M.SPEC["hyg_lead"] + 1
    last = info["tbis_last_day"]
    na_pre = last is None or last < W.days[lo_pre]
    keys = [k for k in M.COUNT_KEYS if not k.startswith("post_") and k not in ("kept_naive", "audit")]
    parts = []
    for k in keys:
        if k == "pre_tbis" and na_pre:
            parts.append("pre_tbis n/a (no forward TBIS)")
        else:
            parts.append(f"{k} {cnt.get(k, 0)}")
    print("  eligibility, each name at its FIRST reason: " + ", ".join(parts))
    print(f"  TBIS flag file: {info['tbis_rows']} symbol-days listed" + (f", the last on {last:%Y-%m-%d}" if last is not None else "") + f" - sessions after it carry no TBIS flag (CHOICE [L3]: the reason cannot fire there); regression window {W.days[M.windows(r)[0]]:%Y-%m-%d} .. {W.days[r]:%Y-%m-%d}")


def rank_cmd(through, root=None, out=None, first=None):
    """[N2](2): the pinned photograph + the house ES master -> rank_<D>.csv (cell, side, symbol, score) and hold_next.txt. Refuses without a pin, before the first month-end, when the previous month-end is not ranked (the holds chain by month), or
    when a rank_<D>.csv of another content is on file (CHOICE [L7]: an identical re-run is a no-op, a different one never overwrites a rank that marks may already use)"""
    out = out or LINE_OUT
    t = parse_through(through, first, "the first rank")
    first = FIRST_RANK if first is None else first
    check_registered()
    folder, pin, v = open_pinned(out, t, root)
    have = rank_files(out)
    if t > first and not any(prev_month_key(t) == (d.year, d.month) for d, _ in have):
        refuse(f"refused: the previous month-end has no rank_<date>.csv in {out} - the line's holds chain month by month; rank the earlier month-ends first (nothing written)")
    t0 = time.time()
    W, info, r, f, rec, cnt, rows = rank_core(folder, t)
    print(f"rank {t:%Y-%m-%d}: photograph {os.path.basename(folder)} (pin of {pin['pinned_utc']} verified: manifest sha256 {pin['manifest_sha256'][:16]}...); world {info['n_real']:,} sessions {info['first']:%Y-%m-%d} .. {info['last']:%Y-%m-%d} "
          f"(+ the phantom fill session), {W.S:,} names ever in the universe, built in {time.time() - t0:.0f}s")
    for ln in info["loader_lines"]:
        print("  " + ln)
    print(f"  universe at the fill session: {rec.nu} names; names with a full window {rec.nfull}; eligible pool {len(rec.pool)}")
    print_counts(W, info, r, rec, cnt)
    print("  " + M.es_report(W, W.days[M.windows(r)[0]], W.days[r])[0])
    data = rank_bytes(rows)
    path = os.path.join(out, f"rank_{t:%Y-%m-%d}.csv")
    with line_lock(out):
        if os.path.exists(path):
            with open(path, "rb") as fh:
                old = fh.read()
            if old != data:
                refuse(f"refused: {path} is on file with other content (it differs from this run's picks: the data or the code changed since it was written) - never overwritten; the lead decides (nothing written)")
            print(f"  {os.path.basename(path)} is on file and IDENTICAL to this run's picks (deterministic) - nothing rewritten")
        else:
            write_atomic(path, data)
            old_ranks = read_rows(os.path.join(out, "ranks.csv"))
            write_rows(os.path.join(out, "ranks.csv"), LOG_HEADS["ranks.csv"], [[r_[h] for h in LOG_HEADS["ranks.csv"]] for r_ in old_ranks]
                       + [[f"{t:%Y-%m-%d}", pin["folder"], pin["manifest_sha256"], hashlib.sha256(data).hexdigest(), str(len(rec.pool)), utc_now(), sha_lf(os.path.abspath(__file__))]])
            print(f"  written {path} ({len(rows)} rows, sha256 {hashlib.sha256(data).hexdigest()[:16]}...); ranks.csv records the pin, the tool and the pool")
        if rank_files(out)[-1][0] == t:                                                # CHOICE [L8]: hold_next.txt - always the UNION of the last two ranks - is rewritten only when this rank is the LATEST on file (re-running an old month never rewinds it)
            hn = write_hold_next(out, t)
            print(f"  hold_next.txt (the --hold file of the next pull: both cells, both sides, one symbol a line): rank {hn['this'][0]:%Y-%m-%d} {hn['this'][1]} names"
                  + (f", rank {hn['prev'][0]:%Y-%m-%d} only {hn['prev_only']} more (it has {hn['prev'][1]}), union {hn['union']}" if hn["prev"] else f", no earlier rank (the first), union {hn['union']}"))
    for cell in M.CELLS:
        lg, sh = rec.pick[cell]
        print(f"  {cell}: longs {', '.join(str(W.syms[rec.pool[i]]) for i in lg[:3])} ... shorts {', '.join(str(W.syms[rec.pool[i]]) for i in sh[:3])} ... ({len(lg)} + {len(sh)} names; scores {rec.score[cell][lg[0]]:+.2f} .. {rec.score[cell][lg[-1]]:+.2f} / "
              f"{rec.score[cell][sh[0]]:+.2f} .. {rec.score[cell][sh[-1]]:+.2f})")
    return rows


# ------------------------------------------------------------------ [N2](3) MARK: sessions valued from ONE photograph with the registered path functions
def hold_values(Wv, f, x, long_cols, short_cols):
    """one cell's hold priced by the registered rules over rows f .. x -> (P (x-f+1,), info). The paths are r17's rm_units (r15's unit_path: entry at the open of f, a mark at every close - a missing bar carries the last mark -, exit at the open of x or,
    for a name with no open there, at its last mark; + the cash dividends: a long receives, a short pays, the fill session's own ex-date is bought ex) and r15's l1_pnl through r17's l1_pnl_x (5 bps of the notional a side, 0.25% a year borrow on the
    shorts' marks the night before each session after the fill) at $4,000 a name - the very functions Stage A's l1_cell sums. CHOICE [L10]: positions are priced SPLIT-SAFE whatever flag falls inside the hold (no removal is possible forward: the registered
    reading's look-ahead removal is not made; mark counts and lists the flags). CHOICE [L11]: a pick with no open at its fill session is not filled (its slot stays empty: no P&L, no cost), counted"""
    cols = np.r_[np.asarray(long_cols, int), np.asarray(short_cols, int)]
    side = np.r_[np.ones(len(long_cols)), -np.ones(len(short_cols))]
    ok = np.isfinite(Wv.Ao[f, cols])
    tot = np.zeros(x - f + 1)
    info = {"filled": int(ok.sum()), "unfilled_cols": cols[~ok], "stopped_cols": np.zeros(0, int), "stopped_side": np.zeros(0)}
    if ok.any():
        U = M.rm_units(Wv, f, x, cols[ok], None)
        sd, cfg = side[ok], D15.l1_cfg()
        for s in (1, -1):
            idx = np.flatnonzero(sd == s)
            if len(idx):
                tot += M.l1_pnl_x(U, idx, s, cfg).sum(axis=0)
        st = np.asarray(U.st, bool)
        info["stopped_cols"], info["stopped_side"] = cols[ok][st], sd[st]
    return M.SPEC["slot"] * tot, info


def value_sessions(Wv, lo, hi, a=None, b=None):
    """the sessions lo .. hi valued from ONE world (one photograph's bars and calendar): hold B, filled at the open of lo (the rank was the session before), contributes its fill, its daily marks and its dividends through the close of hi; hold A, whose exit
    is the open of lo (the first session after the previous month-end), contributes its EXIT LEG only - the open against the prior close, the exit cost, the night's borrow, the exit session's dividend - because every earlier session of A was valued from
    the earlier photographs. a / b = None or {'f': the hold's fill row, cell: (long cols, short cols)}. Wv needs a row hi + 1 (the phantom session: nothing is read from it) -> {cell: {daily (hi-lo+1,), a_exit, b_part, a, b}}"""
    if Wv.Ao.shape[0] <= hi + 1 or Wv.Ac.shape[0] <= hi + 1:
        refuse("refused: the valued world has no row after the last session - the open hold would have no exit row (nothing valued)")
    res = {}
    for cell in M.CELLS:
        daily, rec = np.zeros(hi - lo + 1), {"a_exit": 0.0, "b_part": 0.0, "a": None, "b": None}
        if b is not None:
            if b["f"] != lo:
                refuse(f"refused: the hold filled at row {b['f']} is not the one filled at the first valued session (row {lo}) (nothing valued)")
            tot, rec["b"] = hold_values(Wv, lo, hi + 1, *b[cell])
            daily += tot[:-1]                                                          # the last column is the (absent) exit session: dropped
            rec["b_part"] = float(tot[:-1].sum())
        if a is not None:
            if not a["f"] < lo:
                refuse(f"refused: the hold whose exit is the open of row {lo} was filled at row {a['f']} (nothing valued)")
            tot, rec["a"] = hold_values(Wv, a["f"], lo, *a[cell])
            rec["a_exit"] = float(tot[-1])
            daily[0] += tot[-1]
        rec["daily"] = daily
        res[cell] = rec
    return res


def missing_held(W, rows):
    """the symbols of a rank file's picks that this photograph's World does not hold, sorted"""
    j = pd.Index(W.syms).get_indexer([r["symbol"] for r in rows])
    return sorted({rows[i]["symbol"] for i in np.flatnonzero(j < 0)})


def hold_picks(W, rank_date, rows, label=None):
    """a rank file's picks -> {'f': the fill row, cell: (long cols, short cols)} on this world's columns; a held name the photograph's world does not hold refuses, naming the hold it belongs to (mark_core has named every hold's missing names already)"""
    rank_date = TS(rank_date)
    if rank_date not in W.days:
        refuse(f"refused: the rank session {rank_date:%Y-%m-%d} is not a session of this photograph (nothing valued)")
    ix = pd.Index(W.syms)
    j = ix.get_indexer([r["symbol"] for r in rows])
    missing = missing_held(W, rows)
    if missing:
        refuse(f"refused: held name(s) {missing[:10]} of {label or f'the hold of the {rank_date:%Y-%m-%d} rank'} are not in this photograph's world (no bars, or never in its universe) (nothing valued)")
    out = {"f": int(W.days.get_loc(rank_date)) + 1, "rank_date": rank_date}
    for cell in M.CELLS:
        out[cell] = tuple(np.array([j[i] for i, r in enumerate(rows) if r["cell"] == cell and r["side"] == sd], int) for sd in ("long", "short"))
        if any(len(c) == 0 for c in out[cell]):
            refuse(f"refused: the {rank_date:%Y-%m-%d} rank file has no {cell} longs or no {cell} shorts (nothing valued)")
    return out


def booked_flags(W, lo, hi, a=None, b=None):
    """the hygiene reasons that fall on the booked sessions of the held names (r17's [T2] flags + [D2] spin-offs / stock dividends: B on sessions lo .. hi - the spin-off of the fill session itself is bought ex -, A on its exit session lo): COUNTED and
    LISTED, never removed (CHOICE [L10]) -> {reason: positions} + the (cell, symbol, reasons) rows. The TBIS reason has no flag after the TBIS file's last day (printed n/a by the caller)"""
    names = {}
    for tag, pk, r0, r1, s0 in (("B", b, lo, hi, lo + 1), ("A", a, lo, lo, lo)):
        if pk is None:
            continue
        for cell in M.CELLS:
            cols = np.r_[pk[cell][0], pk[cell][1]]
            hy = W.hyg(r0, r1, cols)
            sp = M.spn_hit(W, s0, r1, cols)
            for q, c in enumerate(cols):
                why = [h for h, v in zip(M.HYG, hy[:, q]) if v] + (["spin"] if sp[q] else [])
                if why:
                    names.setdefault((cell, str(W.syms[c])), set()).update(why)
    cnt = {k: sum(k in v for v in names.values()) for k in (*M.HYG, "spin")}
    return cnt, sorted((c, s, "+".join(sorted(v))) for (c, s), v in names.items())


FRAME_FIELDS = ("o", "h", "l", "c", "v")


def read_frame(folder, name, lo, hi):
    import pyarrow.parquet as pq
    t = pq.read_table(os.path.join(folder, name), filters=[("date", ">=", TS(lo).to_pydatetime()), ("date", "<=", TS(hi).to_pydatetime())])
    df = t.to_pandas()
    df["symbol"] = df["symbol"].astype(str)
    return df


def concat_frames(frames, columns):
    """pd.concat of the non-empty frames (an empty one only changes dtypes and warns), an empty frame of `columns` when none is left"""
    frames = [f for f in frames if len(f)]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)


def compare_frames(a, b):
    """two long daily frames on the same dates -> (summary, the differing cells as a frame, the rows only in one of the two as a frame): every (symbol, date, field) whose value differs (NaN equals NaN)"""
    m = a.merge(b, on=["symbol", "date"], how="outer", suffixes=("_prev", "_cur"), indicator=True)
    both = m[m["_merge"] == "both"]
    cells, per_field, differing = [], {}, np.zeros(len(both), bool)
    for fld in FRAME_FIELDS:
        x, y = both[fld + "_prev"].to_numpy(float), both[fld + "_cur"].to_numpy(float)
        ne = ~((x == y) | (np.isnan(x) & np.isnan(y)))
        per_field[fld] = int(ne.sum())
        differing |= ne
        if ne.any():
            cells.append(pd.DataFrame({"symbol": both["symbol"].to_numpy()[ne], "date": both["date"].to_numpy()[ne], "field": fld, "prev": x[ne], "cur": y[ne]}))
    cells = concat_frames(cells, ["symbol", "date", "field", "prev", "cur"])
    only = []
    for flag, side, col in (("left_only", "previous", "c_prev"), ("right_only", "current", "c_cur")):
        sel = (m["_merge"] == flag).to_numpy()
        only.append(pd.DataFrame({"symbol": m["symbol"].to_numpy()[sel], "date": m["date"].to_numpy()[sel], "side": side, "c": m[col].to_numpy(float)[sel]}))
    rows = concat_frames(only, ["symbol", "date", "side", "c"])
    summ = {"rows_prev": int(len(a)), "rows_cur": int(len(b)), "compared": int(len(both)), "only_prev": int((m["_merge"] == "left_only").sum()), "only_cur": int((m["_merge"] == "right_only").sum()),
            "differing_rows": int(differing.sum()), "cells_by_field": per_field, "symbols_differing": int(both["symbol"][differing].nunique())}
    return summ, cells, rows


def compare_calendars(prev_csv, cur_csv, lo, hi):
    """the two calendars' rows dated lo .. hi (by ex-date, else process date): the rows only in the previous one / only in the current one (tuples in M.CA_COLS order)"""
    sets = []
    for p in (prev_csv, cur_csv):
        df = pd.read_csv(p, dtype=str, keep_default_na=False)
        ev = pd.to_datetime(df["ex_date"].replace("", np.nan), errors="coerce").fillna(pd.to_datetime(df["process_date"].replace("", np.nan), errors="coerce"))
        sets.append(set(map(tuple, df.loc[(ev >= lo) & (ev <= hi), list(M.CA_COLS)].to_numpy())))
    only_prev, only_cur = sorted(sets[0] - sets[1]), sorted(sets[1] - sets[0])
    return {"rows_prev": len(sets[0]), "rows_cur": len(sets[1]), "only_prev": len(only_prev), "only_cur": len(only_cur), "rows_only_prev": only_prev, "rows_only_cur": only_cur}


PRINT_CELLS = 25                                                                        # differences printed one a line per frame (and per calendar side); the rest are in the csv


def overlap_compare(fold_prev, fold_cur, prev_through, out_csv=None, cap=1_000_000):
    """[N2](3): the bars the two photographs share - sessions from the later photograph's window start through the previous month-end - compared field by field, raw and split frames (rows only in one of them too), and the calendars' rows over the same dates. EVERY difference
    is reported: the counts, the symbols with the most, the first 25 a frame (printed a line each) and ALL of them written to out_csv (cells and one-sided rows; the calendar's rows to a twin file); CHOICE [L15]: out_csv is capped at `cap` lines, said so. Nothing is patched"""
    def start(folder):
        with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as f:
            return TS(json.load(f)["start"])
    lo, hi = max(start(fold_prev), start(fold_cur)), TS(prev_through)
    res, allcells, allrows = {"window": [f"{lo:%Y-%m-%d}", f"{hi:%Y-%m-%d}"], "frames": {}}, [], []
    for kind, nm in (("raw", "daily_raw.parquet"), ("split", "daily_split.parquet")):
        summ, cells, rows = compare_frames(read_frame(fold_prev, nm, lo, hi), read_frame(fold_cur, nm, lo, hi))
        top = cells.groupby("symbol").size().sort_values(ascending=False)[:8] if len(cells) else pd.Series(dtype=int)
        summ["top_symbols"] = {str(k): int(v) for k, v in top.items()}
        summ["first_cells"] = [[r.symbol, f"{TS(r.date):%Y-%m-%d}", r.field, float(r.prev), float(r.cur)] for r in cells.head(PRINT_CELLS).itertuples()]
        summ["first_rows"] = [[r.symbol, f"{TS(r.date):%Y-%m-%d}", r.side, float(r.c)] for r in rows.head(PRINT_CELLS).itertuples()]
        summ["cells_total"] = int(len(cells))
        res["frames"][kind] = summ
        allcells.append(cells.assign(frame=kind))
        allrows.append(rows.assign(frame=kind))
    cal = compare_calendars(os.path.join(fold_prev, "corporate_actions.csv"), os.path.join(fold_cur, "corporate_actions.csv"), lo, hi)
    res["calendar"] = cal
    cells, rows = concat_frames(allcells, ["symbol", "date", "field", "prev", "cur", "frame"]), concat_frames(allrows, ["symbol", "date", "side", "c", "frame"])
    res["cells_total"], res["rows_total"] = int(len(cells)), int(len(rows))
    res["lines_written"] = int(min(len(cells) + len(rows), cap))
    res["calendar_csv"] = None
    if out_csv and (len(cells) or len(rows)):
        recs = [("cell", r.frame, r.symbol, r.date, r.field, r.prev, r.cur) for r in cells.itertuples()]
        recs += [(f"row_only_{r.side}", r.frame, r.symbol, r.date, "c", r.c if r.side == "previous" else np.nan, r.c if r.side == "current" else np.nan) for r in rows.itertuples()]
        w = pd.DataFrame(recs[:cap], columns=["kind", "frame", "symbol", "date", "field", "prev", "cur"])
        w["date"] = pd.to_datetime(w["date"]).dt.strftime("%Y-%m-%d")
        write_atomic(out_csv, w.to_csv(index=False, lineterminator="\n"))
    if out_csv and (cal["only_prev"] or cal["only_cur"]):
        res["calendar_csv"] = os.path.splitext(out_csv)[0] + "_calendar.csv"
        write_rows(res["calendar_csv"], ("side",) + M.CA_COLS, [["previous_only", *r] for r in cal["rows_only_prev"]] + [["current_only", *r] for r in cal["rows_only_cur"]])
    return res


def print_overlap(res, out_csv):
    print(f"  overlap with the previous photograph, sessions {res['window'][0]} .. {res['window'][1]} (bars both hold; every difference is reported, nothing is patched):")
    for kind, s in res["frames"].items():
        if not s["differing_rows"] and not s["only_prev"] and not s["only_cur"]:
            print(f"    {kind} frame: {s['compared']:,} name-sessions compared, all identical")
            continue
        print(f"    {kind} frame: {s['compared']:,} compared; {s['differing_rows']:,} name-sessions differ in {s['symbols_differing']} symbols (cells by field {s['cells_by_field']}); in the previous only {s['only_prev']:,}, in the current only {s['only_cur']:,}; "
              f"most affected {s['top_symbols']}")
        for sym, day, fld, a, b in s["first_cells"]:
            print(f"      {sym} {day} {fld}: previous {a:.6g} -> current {b:.6g}")
        for sym, day, side, c in s["first_rows"]:
            print(f"      {sym} {day}: a bar only in the {side} photograph (close {c:.6g})")
        more = max(s["cells_total"] - len(s["first_cells"]), 0) + max(s["only_prev"] + s["only_cur"] - len(s["first_rows"]), 0)
        if more:
            print(f"      ... {more:,} more cells / one-sided bars of this frame in {out_csv}")
    c = res["calendar"]
    print(f"    calendar rows over the same dates: previous {c['rows_prev']:,}, current {c['rows_cur']:,}; only in the previous {c['only_prev']:,}, only in the current {c['only_cur']:,}")
    for side, rows in (("previous", c["rows_only_prev"]), ("current", c["rows_only_cur"])):
        for r in rows[:PRINT_CELLS]:
            d = dict(zip(M.CA_COLS, r))
            print(f"      only in the {side}: {d['type']} {d['symbol']} ex {d['ex_date'] or '-'} process {d['process_date'] or '-'} rate {d['rate'] or '-'} new {d['new_rate'] or '-'} old {d['old_rate'] or '-'} cash {d['cash'] or '-'}")
        if len(rows) > PRINT_CELLS:
            print(f"      ... {len(rows) - PRINT_CELLS:,} more {side}-only calendar rows in {res['calendar_csv']}")
    if res["cells_total"] or res["rows_total"]:
        print(f"    all {res['cells_total']:,} differing cells and {res['rows_total']:,} one-sided bars -> {out_csv}" + (f" (the first {res['lines_written']:,} lines written: capped)" if res["lines_written"] < res["cells_total"] + res["rows_total"] else ""))
    if res["calendar_csv"]:
        print(f"    all differing calendar rows -> {res['calendar_csv']}")


def first_session_after(W, d):
    """(row of the first session after the date d, d's own row): d must be a session of the world"""
    if TS(d) not in W.days:
        refuse(f"refused: {TS(d):%Y-%m-%d} is not a session of this photograph (nothing valued)")
    i = int(W.days.get_loc(TS(d)))
    return i + 1, i


def mark_core(W, t, tp, rk_b, rk_a, ta=None, ks=None):
    """the valuation of the sessions after the previous month-end tp up to t on a built world: -> (lo, hi, a, b, vals, flags, listed). ks = (hold number of the exiting hold or None, of the open hold): a held name the world does not hold refuses naming
    its hold - the exiting hold A (rank ta, exits at the open of the first session here) and / or the open hold B (rank tp) - and the hold_next.txt the pull of this photograph should have been given"""
    lo, _ = first_session_after(W, tp)
    hi = W.T - 2
    if W.days[hi] != TS(t):
        refuse(f"refused: the photograph's last real session is {W.days[hi]:%Y-%m-%d}, not {TS(t):%Y-%m-%d} (nothing valued)")
    holds = ([] if rk_a is None else [("A", ta, rk_a, f"exits at the open of {W.days[lo]:%Y-%m-%d}")]) + [("B", tp, rk_b, "open at this month-end")]
    label = {tag: (f"hold {ks[0 if tag == 'A' else 1]} (rank {d:%Y-%m-%d}, {role})" if ks else f"the hold of the {d:%Y-%m-%d} rank ({role})") for tag, d, _, role in holds}
    gaps = [(tag, missing_held(W, rows)) for tag, _, rows, _ in holds]
    gaps = [(tag, m) for tag, m in gaps if m]
    if gaps:
        refuse("refused: held name(s) " + "; ".join(f"{m[:10]}{' ...' if len(m) > 10 else ''} of {label[tag]}" for tag, m in gaps) + f" are not in this photograph's world (no bars, or never in its universe): the pull of this photograph must carry them - "
               f"they are in the hold_next.txt written after the {tp:%Y-%m-%d} rank, its --hold file (nothing valued)")
    b = hold_picks(W, tp, rk_b, label["B"])
    a = None if rk_a is None else hold_picks(W, ta, rk_a, label["A"])
    vals = value_sessions(W, lo, hi, a, b)
    flags, listed = booked_flags(W, lo, hi, a, b)
    return lo, hi, a, b, vals, flags, listed


def mark_cmd(through, root=None, out=None, first=None):
    """[N2](3) MARK. Every session after the previous PINNED month-end up to this one is valued from THIS photograph's bars and calendar alone (its prior close included) - fills, daily marks, exits at the open after a rank, costs, borrow, dividends, all by
    the registered rules (hold_values) - and appended ONCE to line_daily.csv (date, RES, RAW, 0.264 x RES, 0.233 x RAW); a session is never re-valued from a later photograph. A hold's P&L is complete at the photograph that holds its exit and is appended
    once to line_log.csv (k, rank date, fill date, exit date, RES, RAW, d_k); the by-hold, by-photograph pieces are kept in line_parts.csv (CHOICE [L12]: the exit session is the previous hold's exit leg AND the next hold's first day, so a hold's total is
    the sum of its pieces; CHOICE [L14]: k = the rank's position among the rank files on file, 1 = the first rank 2026-10-30). The first photograph (the first month-end) has no session to value (CHOICE [L13]: a no-op). Refuses a month-end already marked, a gap in the chain of pins / ranks, and a sealed-year date"""
    out = out or LINE_OUT
    first = FIRST_RANK if first is None else first
    t = parse_through(through, first, "the line")
    check_registered()
    pins = sorted(read_rows(os.path.join(out, "pins.csv")), key=lambda p: p["through"])
    pin_lookup(out, t)
    if t == first:
        print(f"mark {t:%Y-%m-%d}: the line's first photograph - no session lies between a previous pinned month-end and this one; the first fills are at the open of {next_weekday(t):%Y-%m-%d} (valued by the next photograph's mark). Nothing appended.")
        return None
    before = [p for p in pins if p["through"] < f"{t:%Y-%m-%d}"]
    if not before:
        refuse("refused: no earlier pinned month-end - there is no previous photograph to start the valuation from (nothing appended)")
    tp = TS(before[-1]["through"])
    if prev_month_key(t) != (tp.year, tp.month):
        refuse(f"refused: the previous pinned month-end is {tp:%Y-%m-%d}, not the month before {t:%Y-%m-%d} - a photograph is missing from the chain; the lead decides (nothing appended)")
    if any(m["through"] == f"{t:%Y-%m-%d}" for m in read_rows(os.path.join(out, "marks.csv"))):
        refuse(f"refused: {t:%Y-%m-%d} is already marked (marks.csv) - a session is valued once, from the photograph it belongs to (nothing appended)")
    rk = dict(rank_files(out))
    if tp not in rk:
        refuse(f"refused: no rank_{tp:%Y-%m-%d}.csv - the hold filled after {tp:%Y-%m-%d} is unknown (nothing appended)")
    ta = None
    if tp > first:
        ta = next((d for d in rk if prev_month_key(tp) == (d.year, d.month)), None)
        if ta is None:
            refuse(f"refused: no rank file for the month before {tp:%Y-%m-%d} - the hold that exits at the first session of this photograph is unknown (nothing appended)")
        if not any(p["rank_date"] == f"{ta:%Y-%m-%d}" and p["part"] == "fill+marks" for p in read_rows(os.path.join(out, "line_parts.csv"))):
            refuse(f"refused: the {ta:%Y-%m-%d} hold has no valued fill and marks in line_parts.csv - the previous photograph's mark is missing (nothing appended)")
    fold_t, pin_t, _ = open_pinned(out, t, root)
    fold_p, pin_p, _ = open_pinned(out, tp, root)
    t0 = time.time()
    W, info = photo_world(fold_t, t, "stub")
    check_world(W, t)
    order = [d for d, _ in rank_files(out)]
    lo, hi, a, b, vals, flags, listed = mark_core(W, t, tp, read_rank(rk[tp]), None if ta is None else read_rank(rk[ta]), ta, (None if ta is None else order.index(ta) + 1, order.index(tp) + 1))
    dates = [W.days[i] for i in range(lo, hi + 1)]
    guard_dates(dates, "this mark")
    print(f"mark {t:%Y-%m-%d}: photograph {os.path.basename(fold_t)} (pin {pin_t['pinned_utc']}), previous pinned month-end {tp:%Y-%m-%d} (photograph {os.path.basename(fold_p)}, pin {pin_p['pinned_utc']}); world {info['n_real']:,} sessions, built in {time.time() - t0:.0f}s")
    for ln in info["loader_lines"]:
        print("  " + ln)
    ov_csv = os.path.join(out, f"overlap_{t:%Y-%m-%d}.csv")
    bad = [c for c in M.CELLS if not (np.isfinite(vals[c]["daily"]).all() and np.isfinite(vals[c]["a_exit"]) and np.isfinite(vals[c]["b_part"]))]
    if bad:
        refuse(f"refused: a non-finite value in the valuation of {', '.join(bad)} - nothing is appended (nothing appended)")
    with line_lock(out):
        parts, daily, log = (read_rows(os.path.join(out, nm)) for nm in ("line_parts.csv", "line_daily.csv", "line_log.csv"))
        k_a, tot_a = None, {c: 0.0 for c in M.CELLS}
        if ta is not None:
            k_a = [d for d, _ in rank_files(out)].index(ta) + 1
            tot_a = {c: sum(float(p[c]) for p in parts if p["rank_date"] == f"{ta:%Y-%m-%d}") + vals[c]["a_exit"] for c in M.CELLS}
        if any(p["through"] == f"{t:%Y-%m-%d}" for p in parts):                           # every guard BEFORE the first write: a mark that stopped half way is never completed or repeated silently
            refuse(f"refused: line_parts.csv already holds rows of the {t:%Y-%m-%d} mark - an earlier run stopped half way; the lead repairs the ledgers by hand (nothing appended)")
        if daily and TS(daily[-1]["date"]) >= dates[0]:
            refuse(f"refused: line_daily.csv already holds {daily[-1]['date']}; the first session of this mark is {dates[0]:%Y-%m-%d} - a session is appended once (nothing appended)")
        if ta is not None and any(int(r["k"]) == k_a for r in log):
            refuse(f"refused: hold {k_a} is already in line_log.csv - a hold is appended once (nothing appended)")
        ov = overlap_compare(fold_p, fold_t, tp, ov_csv)
        print_overlap(ov, ov_csv)
        new_parts = [[f"{t:%Y-%m-%d}", f"{tp:%Y-%m-%d}", "fill+marks", f"{dates[0]:%Y-%m-%d}", f"{dates[-1]:%Y-%m-%d}", fnum(vals["RES"]["b_part"]), fnum(vals["RAW"]["b_part"])]]
        if ta is not None:
            new_parts.insert(0, [f"{t:%Y-%m-%d}", f"{ta:%Y-%m-%d}", "exit", f"{dates[0]:%Y-%m-%d}", f"{dates[0]:%Y-%m-%d}", fnum(vals["RES"]["a_exit"]), fnum(vals["RAW"]["a_exit"])])
        new_daily = [[f"{d:%Y-%m-%d}", fnum(vals["RES"]["daily"][i]), fnum(vals["RAW"]["daily"][i]), fnum(C_RES * vals["RES"]["daily"][i]), fnum(C_RAW * vals["RAW"]["daily"][i])] for i, d in enumerate(dates)]
        new_log = [] if ta is None else [[str(k_a), f"{ta:%Y-%m-%d}", f"{W.days[a['f']]:%Y-%m-%d}", f"{dates[0]:%Y-%m-%d}", fnum(tot_a["RES"]), fnum(tot_a["RAW"]), fnum(C_RES * tot_a["RES"])]]
        mrow = [f"{t:%Y-%m-%d}", f"{tp:%Y-%m-%d}", pin_t["folder"], pin_t["manifest_sha256"], pin_t["calendar_sha256"], utc_now(), str(len(dates)), f"{dates[0]:%Y-%m-%d}", f"{dates[-1]:%Y-%m-%d}",
                fnum(vals["RES"]["daily"].sum()), fnum(vals["RAW"]["daily"].sum()), "" if k_a is None else str(k_a), sha_lf(os.path.abspath(__file__))]
        for nm, new in (("line_parts.csv", new_parts), ("line_log.csv", new_log), ("line_daily.csv", new_daily), ("marks.csv", [mrow])):      # marks.csv last: its row is the commit record
            old = read_rows(os.path.join(out, nm))
            write_rows(os.path.join(out, nm), LOG_HEADS[nm], [[r[h] for h in LOG_HEADS[nm]] for r in old] + new)
    print_mark(W, t, lo, hi, a, b, vals, flags, listed, dates, k_a, tot_a, info, out)
    return {"dates": dates, "vals": vals, "completed_k": k_a, "overlap": ov, "flags": flags, "listed": listed}


def print_mark(W, t, lo, hi, a, b, vals, flags, listed, dates, k_a, tot_a, info, out):
    n = len(dates)
    print(f"  valued {n} sessions {dates[0]:%Y-%m-%d} .. {dates[-1]:%Y-%m-%d}: hold filled at the open of {dates[0]:%Y-%m-%d} (rank {b['rank_date']:%Y-%m-%d}) from its fill through the close of {dates[-1]:%Y-%m-%d}"
          + ("" if a is None else f"; the hold of rank {a['rank_date']:%Y-%m-%d} exits at the open of {dates[0]:%Y-%m-%d} (its exit leg only)"))
    for cell, c in (("RES", C_RES), ("RAW", C_RAW)):
        v, sd = vals[cell], vals[cell]["daily"]
        print(f"  {cell}: these sessions {money(sd.sum())} (x {c} = {money(c * sd.sum())}): the new hold so far {money(v['b_part'])}" + ("" if a is None else f", the exiting hold's exit leg {money(v['a_exit'])}")
              + f"; unfilled picks {len(v['b']['unfilled_cols']) + (0 if a is None else len(v['a']['unfilled_cols']))}")
        if a is not None:
            sc, ss = v["a"]["stopped_cols"], v["a"]["stopped_side"]
            if len(sc):
                print("      exiting names with no open at the exit session (stopped printing: exit at the last mark, the registered rule): " + ", ".join(f"{W.syms[c]} ({'long' if s > 0 else 'short'})" for c, s in zip(sc, ss)))
    last = info["tbis_last_day"]
    tb = "tbis n/a (no forward TBIS)" if (last is None or last < W.days[lo]) else f"tbis {flags['tbis']}"
    print(f"  hygiene flags inside the booked sessions of the held names (kept, split-safe: nothing can be removed forward [L10]): split {flags['split']}, gap {flags['gap']}, {tb}, jump {flags['jump']}, spin-off / stock dividend {flags['spin']}"
          + (("; " + ", ".join(f"{c} {sym} ({why})" for c, sym, why in listed[:10]) + (f", ... {len(listed) - 10} more" if len(listed) > 10 else "")) if listed else ""))
    if k_a is not None:
        print(f"  hold {k_a} (rank {a['rank_date']:%Y-%m-%d}) is complete: RES {money(tot_a['RES'])}, RAW {money(tot_a['RAW'])}, d_{k_a} = {C_RES} x RES = {money(C_RES * tot_a['RES'])} -> line_log.csv")
    daily = read_rows(os.path.join(out, "line_daily.csv"))
    print(f"  appended {n} rows to line_daily.csv ({len(daily)} in all: RES {money(sum(float(r['RES']) for r in daily))}, RAW {money(sum(float(r['RAW']) for r in daily))} since {daily[0]['date']}), line_parts.csv, marks.csv" + ("" if k_a is None else ", line_log.csv"))


# ------------------------------------------------------------------ [N1] / [N3] numerics: the weekend fold, the null spread, the false-stop calibration, the monitor, the dollar read
def fold_weekends(dates, vals):
    """RES's rows as Q16's: one per weekday, a Saturday or Sunday stamp folded into the Friday before it (q16_forward_bar.rows) -> a Series on the weekdays. CHOICE [L16]: that exact fold"""
    s = pd.Series(np.asarray(vals, float), index=pd.DatetimeIndex(dates))
    return s.groupby(s.index - pd.to_timedelta(np.maximum(s.index.dayofweek - 4, 0), unit="D")).sum()


def boot_sums(x, draws=BOOT["draws"], rows=BOOT["rows"], block=BOOT["block"], chunk=BOOT["chunk"], seed=BOOT["seed"]):
    """the null of the dollar read: `draws` draws of `rows` rows of x by circular block bootstrap (blocks of `block` consecutive rows from a random start, wrapping at the end), every block carrying ONE common random sign (+1 / -1) -> the draws' sums.
    CHOICE [L17]: numpy default_rng(seed) is consumed DRAW BY DRAW - for each draw its `rows / block` block starts (rng.integers(0, n)) and then its signs (rng.integers(0, 2): 0 -> -1, 1 -> +1) - so the sequence does not depend on how the draws are
    batched; `chunk` (2,500) only batches the arithmetic. rows must be a multiple of block (756 = 36 x 21)"""
    x = np.asarray(x, float)
    n, nb = len(x), rows // block
    if nb * block != rows or n < 2:
        raise ValueError("rows must be a whole number of blocks and x needs two rows")
    rng, off, sums = np.random.default_rng(seed), np.arange(block), np.empty(draws)
    for c0 in range(0, draws, chunk):
        nd = min(chunk, draws - c0)
        st, sg = np.empty((nd, nb), np.int64), np.empty((nd, nb))
        for q in range(nd):
            st[q] = rng.integers(0, n, size=nb)
            sg[q] = rng.integers(0, 2, size=nb) * 2.0 - 1.0
        blk = x[(st[:, :, None] + off[None, None, :]) % n].sum(axis=2)
        sums[c0:c0 + nd] = (blk * sg).sum(axis=1)
    return sums


def spread_of(x, c, **kw):
    """SPREAD = c x the standard deviation of the draws' sums. CHOICE [L17]: population sd (numpy's default, ddof 0) as q16_forward_bar's sdL - the c* 2.47 was calibrated on that convention"""
    sums = boot_sums(x, **kw)
    sd = float(np.std(sums))
    return {"sd_sum": sd, "spread": c * sd, "mean_sum": float(np.mean(sums)), "rows": int(len(x)), "draws": int(len(sums))}


def read_stats(path, looks=LOOKS):
    """one path's reads: at each look t (the house tstat of the first L values), t without its largest value, t without its smallest - the three numbers the stop rule compares"""
    out = []
    for L in looks:
        y = np.asarray(path[:L], float)
        out.append((tstat(y), tstat(np.delete(y, int(np.argmax(y)))), tstat(np.delete(y, int(np.argmin(y))))))
    return out


def stops_at(t, tx, tn, B):
    """(either side) a stop at a look: t >= B with t still >= 2.0 without the largest value, or t <= -B with t still <= -2.0 without the smallest (docs/PREREG_paired_sequential_stop_2026-09-29.md; paired_seq_stop.read_pair)"""
    return ((t >= B) & (tx >= BOUND_EX)) | ((t <= -B) & (tn <= -BOUND_EX))


def false_stop_rates(d, bounds=STOP["bounds"], paths=STOP["paths"], steps=STOP["steps"], seed=STOP["seed"], looks=LOOKS):
    """[N1](b): paths of `steps` draws with replacement from d with its mean removed, each read at `looks` and stopped at the first look where either side's rule fires -> {B: the share of paths that stop}. CHOICE [L18]: one draw
    rng.integers(0, len(d), (paths, steps)) of numpy default_rng(seed) (row = a path, row-major), and every B is read on the SAME paths (as paired_seq_stop.calibrate, which re-seeds per B)"""
    d0 = np.asarray(d, float) - float(np.mean(d))
    X = d0[np.random.default_rng(seed).integers(0, len(d0), size=(paths, steps))]
    T = np.array([read_stats(X[p], looks) for p in range(paths)])
    t, tx, tn = T[:, :, 0], T[:, :, 1], T[:, :, 2]
    return {float(B): float(stops_at(t, tx, tn, B).any(axis=1).mean()) for B in bounds}


def choose_bound(rates, max_false=STOP["max_false"]):
    """B = the smallest bound whose false-stop rate is at most max_false -> (B or None, [(bound, rate) tried up to and including it])"""
    tried = []
    for B in sorted(rates):
        tried.append((B, rates[B]))
        if rates[B] <= max_false:
            return B, tried
    return None, tried


def monitor(d, B, looks=LOOKS):
    """[N3] the monitor's state on d_1 .. d_k at the registered looks: t of the first L values and t without the most negative one; EARLY FAIL only ([F2]): t <= -B AND t still <= -2.0 without the single most negative d - it ends the line, later looks
    are not read (CHOICE [L19]); the up side is never acted on (there is no early pass) -> ([{look, state, t, t_ex_min, t_ex_max}], the look the line ended at or None)"""
    d, rows, ended = np.asarray(d, float), [], None
    for L in looks:
        if ended is not None:
            rows.append({"look": L, "state": f"not read: the line ended at look {ended}"})
        elif len(d) < L:
            rows.append({"look": L, "state": f"not yet (k = {len(d)} of {L})"})
        else:
            x = np.asarray(d[:L], float)
            t, tn, tx = tstat(x), tstat(np.delete(x, int(np.argmin(x)))), tstat(np.delete(x, int(np.argmax(x))))
            fail = bool(t <= -B and tn <= -BOUND_EX)
            rows.append({"look": L, "state": "EARLY FAIL" if fail else ("continue (the last look: no early fail)" if L == looks[-1] else "continue"), "t": t, "t_ex_min": tn, "t_ex_max": tx})
            ended = L if fail else None
    return rows, ended


def dollar_read(d, first_fill, last_exit, spread, c_star=C_STAR, rows=BOOT["rows"]):
    """[N3] the dollar read, once, at hold 36: the summed forward 0.264 x RES P&L of the 36 holds / the null spread scaled by sqrt(n / 756), n = the weekday rows inside the 36 holds. CHOICE [L20]: the sum is the 36 d_k (= the daily rows of the
    36 holds, without the next hold's entry leg that shares the last exit session) and n counts the weekdays from the first fill through the 36th exit session inclusive (the null's rows are weekdays, holidays included as zero rows)"""
    n = int(len(pd.bdate_range(TS(first_fill), TS(last_exit))))
    s = float(np.sum(d))
    scaled = spread * math.sqrt(n / rows)
    z = s / scaled
    return {"sum": s, "n_rows": n, "scaled_spread": scaled, "z": z, "c_star": c_star, "pass": bool(z >= c_star)}


def read_cmd(out=None, frozen=None):
    """[N3] the monitor's state (k, t, B, status) at the registered looks and the dollar read at hold 36 on what the marks have appended; prints the forward rows used and the pins they came through. Refuses without the frozen constants"""
    out = out or LINE_OUT
    fz = FROZEN if frozen is None else frozen
    if fz is None:
        refuse("refused: FROZEN is not set in this tool - run `freeze` and paste its block first (nothing read)")
    check_registered()
    log = sorted(read_rows(os.path.join(out, "line_log.csv")), key=lambda r: int(r["k"]))
    daily, pins, marks = read_rows(os.path.join(out, "line_daily.csv")), read_rows(os.path.join(out, "pins.csv")), read_rows(os.path.join(out, "marks.csv"))
    guard_dates([r["date"] for r in daily] + [r["exit_date"] for r in log], "this read")
    if [int(r["k"]) for r in log] != list(range(1, len(log) + 1)):
        refuse("refused: line_log.csv's holds are not 1 .. k in order (nothing read)")
    bad = [r["k"] for r in log if abs(float(r["d_k"]) - fz["c_res"] * float(r["RES"])) > 1e-6]
    if bad:
        refuse(f"refused: line_log.csv's d_k is not {fz['c_res']} x RES for hold(s) {bad[:5]} (nothing read)")
    d = np.array([float(r["d_k"]) for r in log])
    fsr = fz["false_stop"][f"{fz['B']:.2f}"]
    print(f"read: frozen B {fz['B']:.2f} (false stops {fsr:.1%} on the WF holds), dollar-read spread {money(fz['spread'])} on {fz['boot']['rows']} rows, c* {C_STAR}; looks at holds {', '.join(map(str, LOOKS))}")
    print(f"  rows used: line_daily.csv {len(daily)} sessions" + (f" {daily[0]['date']} .. {daily[-1]['date']}, RES {money(sum(float(r['RES']) for r in daily))}, 0.264 x RES {money(sum(float(r['RES_line']) for r in daily))}, "
          f"RAW {money(sum(float(r['RAW']) for r in daily))}" if daily else "") + f"; line_log.csv {len(log)} complete holds" + (f" (ranks {log[0]['rank_date']} .. {log[-1]['rank_date']}, d_k sum {money(d.sum())})" if len(log) else ""))
    print("  pins the rows came through: " + ("; ".join(f"{m['through']} -> {m['folder']} (manifest sha256 {m['manifest_sha256'][:12]}..., marked {m['utc']})" for m in marks) if marks else "none yet (no mark has appended a session)")
          + f"; {len(pins)} month-ends pinned")
    rows, ended = monitor(d, fz["B"])
    for r in rows:
        if "t" in r:
            print(f"  look {r['look']:>2}: k {r['look']}, t {r['t']:+.2f} (without the most negative d {r['t_ex_min']:+.2f}), B {fz['B']:.2f} -> {r['state']}")
        else:
            print(f"  look {r['look']:>2}: {r['state']}")
    dr = None
    if len(log) >= LOOKS[-1]:
        dr = dollar_read(d[:LOOKS[-1]], log[0]["fill_date"], log[LOOKS[-1] - 1]["exit_date"], fz["spread"])
        print(f"  dollar read at hold {LOOKS[-1]}: summed 0.264 x RES {money(dr['sum'])} over {dr['n_rows']} weekday rows / spread {money(dr['scaled_spread'])} (scaled by sqrt({dr['n_rows']}/{fz['boot']['rows']})) = {dr['z']:.2f} vs c* {C_STAR} -> "
              + ("PASS (the line is not ended; adoption is the owner's alone)" if dr["pass"] else "BELOW c*: the line ends without adoption") + (f" - NOTE the monitor ended the line at look {ended}" if ended else ""))
    else:
        print(f"  dollar read: not yet (k = {len(log)} of {LOOKS[-1]}; it is read once, at hold {LOOKS[-1]})")
    return {"rows": rows, "ended": ended, "dollar": dr, "k": len(log)}


# ------------------------------------------------------------------ [N1] FREEZE: the constants of the monitor and of the dollar read, computed ONCE from walk-forward data
def wf_world():
    """the world of Stage A / r17_resmom_export.py: the registered loaders on the cached bars through 2025-06-27 (every input is cut before 2025-06-30 at read), the registered wide calendar (its sha pinned by WIDE_CA_SHA), TBIS, the house ES masters
    and the hand-audit file exactly as Stage A applied it (apply_audit(read_audit()): none on file = nothing removed)"""
    t0 = time.time()
    cal, _ = M.wide_load(S.LB0)
    D = M.load_data(S.LB0)
    tbis = D15.load_tbis(S.LB0)
    es_frames, _ = D15.load_es(S.LB0)
    W = M.build_world(D, S.LB0, es_frames, tbis, cal)
    D15.release(D)
    aud = M.apply_audit(W, M.read_audit())
    print(f"WF world ready ({time.time() - t0:.0f}s): {W.T:,} sessions {W.days[0]:%Y-%m-%d} .. {W.days[-1]:%Y-%m-%d} (every input cut before {S.LB0:%Y-%m-%d}), {W.S:,} names ever in the universe; hand-audit file: {aud['rows']} rows")
    return W


def wf_holds(W, L):
    """per cell, every traded WF rebalance's net P&L as Stage A books it: r17's run_cell on the registered picks, the hold's positions' P&L summed over its whole path (the fill at the open after the rank through the exit at the next rebalance's fill; costs,
    borrow and dividends in) - and the daily series by stock session -> (meta [(rank date, fill date, exit date)], {cell: (n,)}, {cell: (T,)})"""
    idx = [i for i, rec in enumerate(L.recs) if rec.traded]
    meta = [(W.days[L.recs[i].r], W.days[L.recs[i].f], W.days[L.recs[i].x]) for i in idx]
    pnl, series = {}, {}
    for cell in M.CELLS:
        run = M.run_cell(W, M.cell_leg(L, cell), D15.l1_cfg(), pos=True)
        by = np.bincount(np.asarray(run.pos.rec, int), weights=np.asarray(run.pos.pnl, float), minlength=len(L.recs))
        pnl[cell], series[cell] = by[idx], np.asarray(run.x, float)
    return meta, pnl, series


def stage_a_record():
    if not os.path.exists(STAGE_A):
        refuse(f"refused: {STAGE_A} is not on file - Stage A's record is the reference of the freeze (nothing computed)")
    with open(STAGE_A, encoding="utf-8") as f:
        sa = json.load(f)
    cells = sa["stageA"]["cells"]
    return {c: float(cells[c]["base"]["net"]) for c in M.CELLS}, {c: int(cells[c]["base"]["n_units"]) for c in M.CELLS}, sa


def same_value(a, b, tol=1e-6, rel=1e-9):
    """recursive equality for the frozen block: numbers within max(tol, rel x |b|), everything else exactly"""
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(same_value(a[k], b[k], tol, rel) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(same_value(x, y, tol, rel) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(a - b) <= max(tol, rel * abs(b))
    return a == b


def frozen_diff(new, old):
    return [k for k in sorted(set(new) | set(old)) if k not in new or k not in old or not same_value(new[k], old[k])]


def frozen_source(fz):
    """the block as Python source, ready to paste between FROZEN-BEGIN and FROZEN-END"""
    lines = ["FROZEN = {"]
    for k, v in fz.items():
        if isinstance(v, list) and len(v) > 8:
            lines.append(f'    "{k}": [')
            lines += ["        " + ", ".join(repr(x) for x in v[i:i + 6]) + "," for i in range(0, len(v), 6)]
            lines.append("    ],")
        else:
            lines.append(f'    "{k}": {v!r},')
    return "\n".join(lines + ["}"])


def freeze_cmd(out=None, frozen=None):
    """[N1] ONCE, from walk-forward data only. (a) d_k = 0.264 x RES's net P&L of WF rebalance k = 1 .. 101, each as Stage A's registered reading books it (the 101 must sum to Stage A's RES net within $1, RAW's printed and held to the same
    standard - CHOICE [L21] - else the freeze refuses); (b) B = the smallest of 3.00, 3.25 .. 8.00 whose false-stop rate is at most 5% (4,000 paths of 36 draws from the 101 d_k with their mean removed, numpy seed 20260929, read at 12 / 18 / 24 / 30 / 36);
    (c) the dollar read's null spread from resmom_cells_daily_wf.csv (refused unless its sha256 is the registered one): weekend stamps folded into the Friday, rows from 2017-01-03, 20,000 draws of 756 rows, block 21, one sign per block, seed 20261016.
    Prints the FROZEN block; with a FROZEN pasted in this file the run must reproduce it exactly or it refuses"""
    out = out or LINE_OUT
    fz0 = FROZEN if frozen is None else frozen
    reg = check_registered()
    if not os.path.exists(CELLS_CSV) or sha_raw(CELLS_CSV) != CELLS_CSV_SHA:
        refuse(f"refused: {CELLS_CSV} is not the registered export (sha256 {CELLS_CSV_SHA[:8]}...: {'missing' if not os.path.exists(CELLS_CSV) else sha_raw(CELLS_CSV)}) (nothing computed)")
    cs = pd.read_csv(CELLS_CSV, parse_dates=["date"])
    guard_dates(cs["date"], "the freeze")
    if cs["date"].min() != M.WF0 or cs["date"].max() != CSV_END:
        refuse(f"refused: the export does not run {M.WF0:%Y-%m-%d} .. {CSV_END:%Y-%m-%d} (nothing computed)")
    t0 = time.time()
    W = wf_world()
    L = M.rm_build(W, M.WF0, M.PRE_END, "remove")
    meta, pnl, _ = wf_holds(W, L)
    nets, units, sa = stage_a_record()
    stamp_now, stamp_a = M.stamp(), {k: sa.get(k) for k in M.stamp()}
    same_stamp = [k for k in stamp_now if stamp_now[k] != stamp_a[k]]
    print("harness stamps vs Stage A's: " + ("all equal (r17_resmom.py, r15_ddw.py, r5_siporb.py, r11_risk.py, r12_mdl.py, r13_attn.py, the wide calendar's sha, the half-day list)" if not same_stamp else f"DIFFER in {same_stamp} (information: the $1 check below is the proof)"))
    n = len(meta)
    print(f"(a) {n} walk-forward rebalances (ranks {meta[0][0]:%Y-%m-%d} .. {meta[-1][0]:%Y-%m-%d}; holds {meta[0][1]:%Y-%m-%d} .. {meta[-1][2]:%Y-%m-%d}), net P&L of each hold as Stage A's registered reading books it (a flag inside the hold removes the position before ranking):")
    for i, (rk, fi, ex) in enumerate(meta):
        print(f"    k {i + 1:>3}  rank {rk:%Y-%m-%d}  fill {fi:%Y-%m-%d}  exit {ex:%Y-%m-%d}  RES {pnl['RES'][i]:>11,.2f}  RAW {pnl['RAW'][i]:>11,.2f}  d_k {C_RES * pnl['RES'][i]:>10,.2f}")
    for cell in M.CELLS:
        s = float(pnl[cell].sum())
        print(f"    {cell}: the {n} holds sum to {s:,.4f}; Stage A's WF net {nets[cell]:,.4f} (difference {s - nets[cell]:+.6f}); Stage A's rebalances {units[cell]}")
        if n != units[cell] or abs(s - nets[cell]) > 1.0:
            refuse(f"refused: {cell}'s {n} hold P&Ls sum to {s:,.4f}, not Stage A's {nets[cell]:,.4f} within $1 ({units[cell]} rebalances there) - the registered reading is not reproduced (nothing frozen)")
    for cell in M.CELLS:
        cx = float(cs[cell].sum())
        if abs(cx - float(pnl[cell].sum())) > 0.01:
            refuse(f"refused: the export's {cell} column sums to {cx:,.4f}, not the holds' {float(pnl[cell].sum()):,.4f} (nothing frozen)")
    d = C_RES * pnl["RES"]
    rates = false_stop_rates(d)
    B, tried = choose_bound(rates)
    print(f"(b) false-stop rate of the stop rule on {STOP['paths']:,} paths of {STOP['steps']} draws from the {n} d_k (mean removed; seed {STOP['seed']}; looks {', '.join(map(str, LOOKS))}; either side counts), at every B tried:")
    print("    " + "; ".join(f"B {b:.2f}: {r:.2%}" for b, r in tried))
    if B is None:
        refuse(f"refused: no B up to {STOP['bounds'][-1]:.2f} keeps the false-stop rate at {STOP['max_false']:.0%} or below ({'; '.join(f'{b:.2f}: {r:.2%}' for b, r in tried[-3:])}) (nothing frozen)")
    print(f"    B = {B:.2f} (the smallest bound with a false-stop rate of at most {STOP['max_false']:.0%}: {rates[B]:.2%})")
    s_all = fold_weekends(cs["date"], cs["RES"])
    reg_rows, all_rows = s_all[(s_all.index >= WF_ROWS_FROM) & (s_all.index <= CSV_END)], s_all[(s_all.index >= WF_ROWS_ALL) & (s_all.index <= CSV_END)]
    sp, sp_all = spread_of(reg_rows.to_numpy(), C_RES), spread_of(all_rows.to_numpy(), C_RES)
    print(f"(c) null spread of the dollar read (RES's daily series, weekend stamps folded into the Friday; {BOOT['draws']:,} draws of {BOOT['rows']} rows, circular block bootstrap, block {BOOT['block']}, one sign per block, seed {BOOT['seed']}, chunks of {BOOT['chunk']:,}; "
          f"sd of the draws' sums x {C_RES}):")
    print(f"    registered rows {reg_rows.index[0]:%Y-%m-%d} .. {reg_rows.index[-1]:%Y-%m-%d} ({sp['rows']:,} weekday rows): sd of the sums {sp['sd_sum']:,.2f}, SPREAD = {C_RES} x that = {sp['spread']:,.2f}")
    print(f"    beside, never used: all rows from {all_rows.index[0]:%Y-%m-%d} ({sp_all['rows']:,} rows): sd of the sums {sp_all['sd_sum']:,.2f}, spread {sp_all['spread']:,.2f}")
    fz = {"c_res": C_RES, "c_raw": C_RAW, "B": float(B), "false_stop": {f"{b:.2f}": float(r) for b, r in tried}, "boot": dict(BOOT), "stop": {"paths": STOP["paths"], "steps": STOP["steps"], "seed": STOP["seed"], "looks": list(LOOKS)},
          "rows_from": f"{reg_rows.index[0]:%Y-%m-%d}", "rows_to": f"{reg_rows.index[-1]:%Y-%m-%d}", "n_rows": int(sp["rows"]), "sd_sum": sp["sd_sum"], "spread": sp["spread"], "cells_csv_sha256": CELLS_CSV_SHA,
          "res_net": round(float(pnl["RES"].sum()), 6), "raw_net": round(float(pnl["RAW"].sum()), 6), "res_holds": [round(float(x), 6) for x in pnl["RES"]], "raw_holds": [round(float(x), 6) for x in pnl["RAW"]]}
    rec = {"frozen": fz, "holds": [{"k": i + 1, "rank": f"{rk:%Y-%m-%d}", "fill": f"{fi:%Y-%m-%d}", "exit": f"{ex:%Y-%m-%d}", "RES": float(pnl["RES"][i]), "RAW": float(pnl["RAW"][i]), "d_k": float(d[i])} for i, (rk, fi, ex) in enumerate(meta)],
           "spread_all_rows_beside_never_used": {"rows": sp_all["rows"], "sd_sum": sp_all["sd_sum"], "spread": sp_all["spread"]}, "stage_a": {"net": nets, "rebalances": units, "harness_stamp_differs": same_stamp},
           "registered": reg, "harness_stamp": stamp_now, "tool_sha256_lf": sha_lf(os.path.abspath(__file__)), "created_utc": utc_now()}
    if fz0 is not None:
        bad = frozen_diff(fz, fz0)
        if bad:
            refuse(f"refused: this run does not reproduce the FROZEN block in this file (differs in {bad}) - the harness, the data or the code changed since it was frozen (nothing written)")
        print(f"FROZEN reproduced EXACTLY by this re-run (B {fz['B']:.2f}, spread {fz['spread']:,.2f}, the {n} RES and {n} RAW hold P&Ls, the false-stop table) - took {time.time() - t0:.0f}s")
    else:
        print("\nFROZEN block (paste it between FROZEN-BEGIN and FROZEN-END in r17_resmom_line.py, then run `freeze` again: it must reproduce it exactly):")
        print(frozen_source(fz))
    jp = os.path.join(out, "freeze.json")
    with line_lock(out):
        if os.path.exists(jp):
            with open(jp, encoding="utf-8") as f:
                old = json.load(f)
            if frozen_diff(fz, old["frozen"]):
                refuse(f"refused: {jp} holds a different freeze (differs in {frozen_diff(fz, old['frozen'])}) - never overwritten (nothing written)")
            print(f"{jp} is on file and agrees with this run - nothing rewritten")
        else:
            write_atomic(jp, json.dumps(rec, indent=1, default=R11.js))
            write_atomic(jp + ".sha256", f"{sha_raw(jp)}  freeze.json\n")
            print(f"written {jp} (+ .sha256 {sha_raw(jp)})")
    return fz


# ------------------------------------------------------------------ photographs written locally (the selftest's fakes and parity's slices of the walk-forward cache): r17_resmom_pull.py's layout, nothing pulled
def write_photo(folder, through, raw, split, cal, rev=1):
    """a photograph in r17_resmom_pull's layout: daily_raw.parquet / daily_split.parquet (the SIPORB cache's schema), corporate_actions.csv (r16_xgap's flat columns), the raw JSONL, symbols.txt and manifest.json holding the sha256 of the other four"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    sch = pa.schema([("symbol", pa.string()), ("date", pa.timestamp("ns")), ("o", pa.float64()), ("h", pa.float64()), ("l", pa.float64()), ("c", pa.float64()), ("v", pa.int64())])
    os.makedirs(folder)
    for nm, df in (("daily_raw.parquet", raw), ("daily_split.parquet", split)):
        d = df.sort_values(["symbol", "date"], kind="stable")
        pq.write_table(pa.Table.from_pandas(d[list(sch.names)], schema=sch, preserve_index=False), os.path.join(folder, nm), compression="zstd")
    cal[list(M.CA_COLS)].to_csv(os.path.join(folder, "corporate_actions.csv"), index=False, lineterminator="\n")
    write_atomic(os.path.join(folder, "corporate_actions_raw.jsonl"), "")
    write_atomic(os.path.join(folder, "symbols.txt"), "\n".join(sorted(raw["symbol"].astype(str).unique())) + "\n")
    names = PHOTO_FILES + ("corporate_actions_raw.jsonl", "symbols.txt")
    man = {"created": utc_now(), "through": f"{TS(through):%Y-%m-%d}", "start": f"{TS(through) - pd.Timedelta(days=430):%Y-%m-%d}", "end": f"{TS(through):%Y-%m-%d}", "folder": os.path.basename(folder), "revision": rev, "rows": int(len(cal)),
           "sha256": {nm: sha_raw(os.path.join(folder, nm)) for nm in names}}
    write_atomic(os.path.join(folder, "manifest.json"), json.dumps(man, indent=1))
    return man


def photo_from_cache(through, folder):
    """parity only: a photograph of the walk-forward cache - the bars of through - 430 days .. through (raw and split, cut before 2025-06-30 AT READ) and the registered wide calendar's rows dated in the same window - written to a temp folder"""
    import pyarrow.parquet as pq
    through = TS(through)
    if through >= S.LB0:
        refuse(f"refused: a parity photograph through {through:%Y-%m-%d} would read the sealed year (nothing built)")
    start = through - pd.Timedelta(days=430)
    frames = {}
    for kind in ("raw", "split"):
        t = pq.read_table(S.path_of(f"daily_{kind}") + ".parquet", filters=[("date", ">=", start.to_pydatetime()), ("date", "<=", through.to_pydatetime())], read_dictionary=["symbol"])
        frames[kind] = t.to_pandas()
        frames[kind]["symbol"] = frames[kind]["symbol"].astype(str)
        A13.assert_cut(f"parity photograph {kind}", frames[kind]["date"], S.LB0)
    df = pd.read_csv(M.wide_paths()["csv"], dtype=str, keep_default_na=False)
    ev = pd.to_datetime(df["ex_date"].replace("", np.nan), errors="coerce").fillna(pd.to_datetime(df["process_date"].replace("", np.nan), errors="coerce"))
    return write_photo(folder, through, frames["raw"], frames["split"], df[(ev >= start) & (ev <= through)])


# ------------------------------------------------------------------ PARITY: walk-forward only, against the registered harness and resmom_cells_daily_wf.csv
class View:
    """a causal slice of a World for the mark path: the arrays hold_values reads, rows 0 .. hi and ONE NaN row after them (the phantom exit row) - nothing after hi is visible, so a month's mark cannot see the future"""
    def __init__(self, W, hi):
        pad = lambda a, v=np.nan: np.vstack([a[:hi + 1], np.full((1, a.shape[1]), v)])
        self.Ao, self.Ac, self.Od, self.Cl, self.Dv, self.Dr = pad(W.Ao), pad(W.Ac), pad(W.Od), pad(W.Cl), pad(W.Dv, 0.0), pad(W.Dr, 0.0)
        self.T = hi + 2


def rec_hold(rec):
    """a registered rebalance in the shape value_sessions reads: {'f': fill row, cell: (long cols, short cols)}"""
    return {"f": rec.f, **{c: (rec.pool[rec.pick[c][0]], rec.pool[rec.pick[c][1]]) for c in M.CELLS}}


def emulate_marks(W, L):
    """the code path `mark` uses (value_sessions) run month by month over the registered rebalances: for each month-end photograph m the world is the causal View through its close, hold B = rebalance m-1 (filled at the first session after the previous
    month-end, marked through this close) and hold A = rebalance m-2 (its exit leg at that session). The last step is the exit leg of the last resolved hold alone (its exit session is the first one after the last month-end in the data).
    -> daily {cell: (T,) by stock session}, parts {cell: (n,) each hold's fill+marks piece + exit leg}"""
    recs = L.recs
    n = len(recs)
    ranks = [rec.r for rec in recs] + [r for r in M.rm_schedule(W.days)[0].tolist() if r > recs[-1].r][:1]
    daily, parts = {c: np.zeros(W.T) for c in M.CELLS}, {c: np.zeros(n) for c in M.CELLS}
    pk = rec_hold
    for m in range(1, n + 2):
        lo = ranks[m - 1] + 1
        hi = ranks[m] if m < len(ranks) else lo
        b = pk(recs[m - 1]) if m - 1 < n else None
        a = pk(recs[m - 2]) if 2 <= m and m - 2 < n else None
        v = value_sessions(View(W, hi), lo, hi, a, b)
        for c in M.CELLS:
            daily[c][lo:hi + 1] += v[c]["daily"]
            if b is not None:
                parts[c][m - 1] += v[c]["b_part"]
            if a is not None:
                parts[c][m - 2] += v[c]["a_exit"]
    return daily, parts


def check_rank_identity(W, L):
    """(i-1) the rank code path at the 101 WF ranks, given the registered inputs (the hold's exit row, so rm_one's look-ahead hygiene is the registered one): its picks - written to the rank file's bytes and read back - equal Stage A's
    registered picks (names, sides, order, scores) in both cells -> (ok, worst rank date or None, n ranks)"""
    bad, n = [], 0
    for rec in L.recs:
        if not rec.traded:
            continue
        n += 1
        rec2, _ = rank_picks(W, rec.r, rec.f, rec.x, "remove", phantom_fill=False)
        back = list(csv.DictReader(io.StringIO(rank_bytes(rank_rows_of(W, rec2)).decode("ascii"))))
        for c in M.CELLS:
            for sd, idx in (("long", rec.pick[c][0]), ("short", rec.pick[c][1])):
                want = [(str(W.syms[rec.pool[i]]), float(rec.score[c][i])) for i in idx]
                got = [(r["symbol"], float(r["score"])) for r in back if r["cell"] == c and r["side"] == sd]
                if got != want or len(want) != M.SPEC["n_side"]:
                    bad.append(W.days[rec.r])
    return not bad, (bad[0] if bad else None), n


def check_forward_information(W, L):
    """(i-2) the forward rank cannot know the hold (CHOICE [L5]) nor the fill's open (CHOICE [L6]): at each of the 101 WF ranks, rank_picks with x = -1 and the phantom fill rule against Stage A's registered picks. Differences must be explained: every name the
    forward picks hold and the registered ones do not must be a name the registered reading removed before ranking (a hygiene flag or a spin-off inside the hold, no open at the fill session) -> (ok, info dict)"""
    n_diff_ranks, n_names, n_picks, why, unexplained, worst = 0, 0, 0, {}, [], (0, None)
    for rec in L.recs:
        if not rec.traded:
            continue
        rec2, _ = rank_picks(W, rec.r, rec.f, -1, "remove", phantom_fill=True)
        k = 0
        for c in M.CELLS:
            for q, sd in ((0, "long"), (1, "short")):
                reg = {int(rec.pool[i]) for i in rec.pick[c][q]}
                fwd = {int(rec2.pool[i]) for i in rec2.pick[c][q]} if rec2.traded else set()
                n_picks += len(reg)
                for j in sorted(fwd - reg):
                    k += 1
                    hy = W.hyg(rec.f, rec.x, np.array([j]))[:, 0]
                    sp = bool(M.spn_hit(W, rec.f + 1, rec.x, np.array([j]))[0])
                    reasons = ["post_" + h for h, v in zip(M.HYG, hy) if v] + (["post_spin"] if sp else []) + (["no_real_open"] if not np.isfinite(W.Ao[rec.f, j]) else [])
                    for rs in reasons or ["UNEXPLAINED"]:
                        why[rs] = why.get(rs, 0) + 1
                    if not reasons:
                        unexplained.append((f"{W.days[rec.r]:%Y-%m-%d}", c, sd, str(W.syms[j])))
        n_names += k
        n_diff_ranks += int(k > 0)
        if k > worst[0]:
            worst = (k, W.days[rec.r])
    return not unexplained, {"ranks": sum(r.traded for r in L.recs), "ranks_differing": n_diff_ranks, "names_differing": n_names, "picks": n_picks, "reasons": why, "unexplained": unexplained[:5], "worst": worst}


def check_daily(W, daily, cs):
    """(ii) the mark path's daily series against resmom_cells_daily_wf.csv. The CSV is on #463's index (weekdays and weekend stamps, every row a date of that index); the mark path's series is by stock session. Common index = the CSV's rows: the mark path's
    value on a date that is not a stock session is zero by construction, and the check also sums what the mark path books on dates the CSV does not have (must be 0) -> {cell: record}"""
    idx = pd.DatetimeIndex(cs["date"])
    res = {}
    for c in M.CELLS:
        s = pd.Series(daily[c], index=W.days)
        mine = s.reindex(idx).fillna(0.0).to_numpy()
        diff = mine - cs[c].to_numpy(float)
        j = int(np.argmax(np.abs(diff)))
        res[c] = {"rows": int(len(idx)), "max_abs": float(abs(diff[j])), "worst_date": idx[j], "mine": float(mine[j]), "csv": float(cs[c].to_numpy(float)[j]), "off_index": float(np.abs(s[~s.index.isin(idx)]).sum()),
                  "sum_mine": float(mine.sum()), "sum_csv": float(cs[c].sum())}
    return res


def check_chain(W, L, meta, pnl, cs, tmp, dates, make=None):
    """(iv) the whole forward chain on real WF data: photographs of the cache for consecutive month-ends (built in a temp folder), rank files written from the REGISTERED picks (so the valuation alone is under test), then pin -> mark for each month through the
    code the real run uses (the first month-end of the chain plays the line's first photograph) -> the sessions line_daily.csv books equal the CSV's rows to the cent (the first session less the exit leg of the hold before the chain's first rank: the line has no hold before its
    first rank), and each completed hold equals the freeze's hold P&L"""
    root, out = os.path.join(tmp, "photos"), os.path.join(tmp, "line_out")
    os.makedirs(root)
    first = TS(dates[0])
    ranks = {W.days[rec.r]: i for i, rec in enumerate(L.recs)}
    lo0 = int(W.days.get_loc(first)) + 1                                                                                  # the line starts with the hold of its first rank: the hold BEFORE it (rank i0 - 1) exits at the open of lo0, a leg the line does not have - the registered series does
    i0 = ranks[first]
    prev = value_sessions(View(W, lo0), lo0, lo0, rec_hold(L.recs[i0 - 1]), None) if i0 > 0 else None
    adj, first_day = {c: (prev[c]["a_exit"] if prev else 0.0) for c in M.CELLS}, f"{W.days[lo0]:%Y-%m-%d}"
    for d in dates:
        (make or photo_from_cache)(d, os.path.join(root, f"{TS(d):%Y-%m-%d}"))
        i = ranks[TS(d)]
        write_atomic(os.path.join(out, f"rank_{TS(d):%Y-%m-%d}.csv"), rank_bytes(rank_rows_of(W, L.recs[i])))
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        for d in dates:
            pin_cmd(f"{TS(d):%Y-%m-%d}", root, 1, out, first)
        for d in dates:
            mark_cmd(f"{TS(d):%Y-%m-%d}", root, out, first)
    daily, log = read_rows(os.path.join(out, "line_daily.csv")), read_rows(os.path.join(out, "line_log.csv"))
    csv_by = {f"{r.date:%Y-%m-%d}": r for r in cs.itertuples()}
    worst, nrows = (0.0, None, None), 0
    for r in daily:
        for c in M.CELLS:
            e = abs(float(r[c]) - (float(getattr(csv_by[r["date"]], c)) - (adj[c] if r["date"] == first_day else 0.0)))
            nrows += 1
            if e > worst[0]:
                worst = (e, r["date"], c)
    hold_err = (0.0, None)
    for r in log:
        i = ranks[TS(r["rank_date"])]
        for c in M.CELLS:
            e = abs(float(r[c]) - float(pnl[c][i]))
            if e > hold_err[0]:
                hold_err = (e, r["rank_date"])
    ok = bool(daily) and worst[0] < 0.005 and hold_err[0] < 0.005 and len(log) == len(dates) - 2
    return ok, {"months": [f"{TS(d):%Y-%m-%d}" for d in dates], "sessions": len(daily), "cells_compared": nrows, "worst": worst, "holds_completed": len(log), "hold_worst": hold_err, "overlap_clean": "all identical" in buf.getvalue() or "differ" not in buf.getvalue()}


def check_photo_picks(W, dates, tmp, make=None):
    """(i-3) the forward rank path through a PHOTOGRAPH (a 430-day slice of the cache in the pull's layout, pinned, read through the phantom-session wrappers, the house ES master through the date) against the same function on the full WF world:
    the rank rows equal (names, sides, order; scores to 1e-12) at each date -> (ok, [(date, n rows, ok)])"""
    res = []
    for d in dates:
        folder = os.path.join(tmp, "rank_photos", f"{TS(d):%Y-%m-%d}")
        (make or photo_from_cache)(d, folder)
        with contextlib.redirect_stdout(io.StringIO()):
            _, _, _, _, _, _, rows = rank_core(folder, TS(d))
        i = int(W.days.get_loc(TS(d)))
        rec2, _ = rank_picks(W, i, i + 1, -1, "remove", phantom_fill=True)
        rows2 = rank_rows_of(W, rec2)
        ok = len(rows) == len(rows2) and all(a[:3] == b[:3] and abs(a[3] - b[3]) <= 1e-12 * max(1.0, abs(b[3])) for a, b in zip(rows, rows2))
        res.append((f"{TS(d):%Y-%m-%d}", len(rows), ok))
    return all(r[2] for r in res), res


def parity_cmd(out=None):
    """walk-forward ONLY (every input is cut before 2025-06-30 by the harness's loaders; the photographs below are slices of that cut cache): PASS / FAIL per check with the worst row. The checks: (i-1) the rank code path reproduces Stage A's registered
    picks at the 101 ranks; (i-2) the forward-information picks differ from them only by the registered reading's look-ahead removals (counted, explained); (i-3) the rank path through a photograph equals the same function on the full cache; (ii) the mark
    code path, month by month, reproduces resmom_cells_daily_wf.csv's RES and RAW columns to the cent; (iii) the freeze's 101 hold P&Ls equal the daily series summed by hold; (iv) pin -> mark through photographs of the cache reproduce the CSV's rows"""
    check_registered()
    if not os.path.exists(CELLS_CSV) or sha_raw(CELLS_CSV) != CELLS_CSV_SHA:
        refuse(f"refused: {CELLS_CSV} is not the registered export (nothing computed)")
    cs = pd.read_csv(CELLS_CSV, parse_dates=["date"])
    guard_dates(cs["date"], "the parity run")
    t0, fails = time.time(), []
    W = wf_world()
    L = M.rm_build(W, M.WF0, M.PRE_END, "remove")
    meta, pnl, series = wf_holds(W, L)
    nets, units, _ = stage_a_record()
    print(f"parity (walk-forward only): {len(meta)} registered rebalances, RES {pnl['RES'].sum():,.2f} / RAW {pnl['RAW'].sum():,.2f} (Stage A {nets['RES']:,.2f} / {nets['RAW']:,.2f})")

    def verdict(name, ok, text):
        print(f"{name}: {'PASS' if ok else 'FAIL'} - {text}")
        if not ok:
            fails.append(name)
    ok, worst, n = check_rank_identity(W, L)
    verdict("(i-1) rank path = Stage A's registered picks", ok, f"{n} ranks x 2 cells x (50 long + 50 short): names, sides, order and scores equal after the rank file's write / read-back" + ("" if ok else f"; first mismatch {worst:%Y-%m-%d}"))
    ok, info = check_forward_information(W, L)
    print(f"(i-2) {'PASS' if ok else 'FAIL'} - forward-information picks (no hold known, no fill open: [L5] [L6]) against the registered picks: {info['ranks_differing']} of {info['ranks']} ranks differ, {info['names_differing']} of {info['picks']:,} picks "
          f"({info['names_differing'] / max(info['picks'], 1):.2%}) are names the registered reading removed before ranking; by reason (a name may carry several) {info['reasons']}; worst rank {info['worst'][1]:%Y-%m-%d} ({info['worst'][0]} names)"
          + ("" if ok else f"; UNEXPLAINED {info['unexplained']}"))
    if not ok:
        fails.append("(i-2)")
    daily, parts = emulate_marks(W, L)
    res = check_daily(W, daily, cs)
    ok = all(r["max_abs"] < 0.005 and r["off_index"] == 0.0 for r in res.values())
    verdict("(ii) mark path = resmom_cells_daily_wf.csv", ok, "; ".join(f"{c}: {r['rows']:,} rows, worst {r['worst_date']:%Y-%m-%d} (mark path {r['mine']:,.6f} vs CSV {r['csv']:,.6f}, |diff| {r['max_abs']:.2e}), booked off the CSV's index {r['off_index']:.2f}, sums {r['sum_mine']:,.4f} / {r['sum_csv']:,.4f}"
                                                                for c, r in res.items()) + " (the CSV is on #463's index - weekdays plus Sunday stamps; the stock cell's value there is 0 and the mark path books by stock session: compared on the CSV's rows)")
    err = {c: np.abs(parts[c] - pnl[c]) for c in M.CELLS}
    worst_i = {c: int(np.argmax(err[c])) for c in M.CELLS}
    ok = all(err[c].max() < 0.005 for c in M.CELLS)
    verdict("(iii) freeze's hold P&Ls = the daily series summed by hold", ok, "; ".join(f"{c}: {len(pnl[c])} holds, worst k {worst_i[c] + 1} (rank {meta[worst_i[c]][0]:%Y-%m-%d}) |diff| {err[c].max():.2e}" for c in M.CELLS))
    tmp = tempfile.mkdtemp(prefix="resmomline_parity_")
    try:
        ok, res3 = check_photo_picks(W, ("2018-06-29", "2020-03-31", "2025-04-30"), tmp)
        verdict("(i-3) rank path through a photograph = the full cache", ok, "; ".join(f"{d}: {n} rows {'equal' if o else 'DIFFER'}" for d, n, o in res3))
        ok, r4 = check_chain(W, L, meta, pnl, cs, tmp, ("2020-02-28", "2020-03-31", "2020-04-30", "2020-05-29"))
        verdict("(iv) pin -> mark through photographs = the CSV", ok, f"months {', '.join(r4['months'])} (the first plays the line's first photograph): {r4['sessions']} sessions, {r4['cells_compared']} cell-rows compared, worst |diff| {r4['worst'][0]:.2e} "
                                                                    f"({r4['worst'][1]} {r4['worst'][2]}); {r4['holds_completed']} completed holds vs the freeze's, worst |diff| {r4['hold_worst'][0]:.2e} ({r4['hold_worst'][1]}); overlap between consecutive photographs {'identical' if r4['overlap_clean'] else 'DIFFERS'}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"PARITY: {'ALL PASS' if not fails else 'FAIL ' + ', '.join(fails)} ({time.time() - t0:.0f}s)")
    if fails:
        raise SystemExit(1)
    return True


# ------------------------------------------------------------------ SELFTEST: fakes only - no network, no key, no real file; every output goes to a temp folder
def say(text):
    print("  ok - " + text, flush=True)


def refuses(fn, frag, what):
    """fn() must end in a refusal (SystemExit with a message) holding `frag` -> that message; a call that goes through, or refuses for another reason, fails the test"""
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            fn()
    except SystemExit as e:
        txt = str(e.code)
        assert frag in txt, f"{what}: refused with {txt[:400]!r}, wanted {frag!r}"
        return txt
    raise AssertionError(f"{what}: the call went through, wanted a refusal naming {frag!r}")


def captured(fn, *a, **kw):
    """(fn's result, what it printed)"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        res = fn(*a, **kw)
    return res, buf.getvalue()


def month_ends(n, first=FIRST_RANK):
    """the first n month-end sessions from `first` on (the line's ranks, by month_end_session)"""
    out, d = [], TS(first)
    while len(out) < n:
        out.append(d)
        d = TS(d.year + (d.month == 12), d.month % 12 + 1, 1) + pd.offsets.MonthEnd(0)
        while not month_end_session(d):
            d -= pd.Timedelta(days=1)
    return out


def flip_byte(path):
    """change ONE byte in the middle of a file"""
    with open(path, "rb") as f:
        b = bytearray(f.read())
    b[len(b) // 2] ^= 0x01
    with open(path, "wb") as f:
        f.write(bytes(b))


class FakeMarket:
    """the selftest's market: 36 names on every session of 2024-11-01 .. 2027-02-26 but the NYSE closures, ONE consistent history from which any month-end's photograph is cut in r17_resmom_pull's layout (the bars of the 430 days before it, the calendar rows of the same
    days; a split taken by then adjusts the split frame of every photograph pulled after it, never the raw frame). The market return is the fake ES master's own (r15_ddw.ESFake), so the regression recovers the planted betas. Planted: UPA / SPLX / NOFILL / DLST are persistent winners
    (DLST's last bar is 2026-11-18: it is delisted inside the first hold; NOFILL has no bar on 2026-11-02, the first hold's fill session; SPLX splits 2-for-1 on 2026-12-09, inside the second hold), EARLY / LATE / UPB are winners for ONE stretch only (EARLY inside the formation window of the
    2026-10-30 rank alone, LATE and UPB inside the 2026-11-30 rank's alone: the two ranks' picks differ), DNA .. DNE are persistent losers (DNA falls 15% on a spin-off ex-date, 2026-11-12, DNB pays dividends while it is short); UPA pays dividends on 2026-11-13, on 2026-12-01 (the first
    hold's exit session = the second hold's fill session) and on 2026-12-18; N03 carries one TBIS flag (2025-12-05); 24 noise names fill the universe"""
    FIRST, LAST = "2024-11-01", "2027-02-26"
    SPLIT_DAY, DELIST_DAY, SPIN_DAY, NOFILL_DAY, TBIS_DAY = TS("2026-12-09"), TS("2026-11-18"), TS("2026-11-12"), TS("2026-11-02"), "2025-12-05"

    def __init__(self, seed=5):
        rng = np.random.default_rng(seed)
        days = self.days = pd.DatetimeIndex([d for d in pd.bdate_range(self.FIRST, self.LAST) if not nyse_closed(d)])
        T = len(days)
        pos = lambda s: int(days.get_loc(TS(s)))
        self.es = D15.ESFake(days)
        pc, rc = (np.array([tab[d] for d in days]) for tab in (self.es.p_close, self.es.raw_close))
        m = np.r_[0.0, (pc[1:] - pc[:-1]) / rc[:-1]]                                       # the fake ES master's own daily return = the market factor the stocks load on
        i10, t_ = pos("2026-10-30"), np.arange(T)
        burst = lambda a, b: np.where((t_ >= a) & (t_ <= b), 0.08, 0.0)
        plan = {"UPA": (30.0, 0.0035), "SPLX": (30.0, 0.0035), "NOFILL": (30.0, 0.0035), "DLST": (30.0, 0.0035),
                "EARLY": (40.0, burst(i10 - 250, i10 - 236)), "LATE": (40.0, burst(i10 - 18, i10 - 4)), "UPB": (40.0, burst(i10 - 17, i10 - 3))}
        plan.update({f"DN{c}": (200.0 + 10 * k, -0.0035) for k, c in enumerate("ABCDE")})
        plan.update({f"N{j:02d}": (40.0 + 2 * j, 0.0) for j in range(24)})
        frames = []
        for name, (p0, drift) in plan.items():
            ret = rng.uniform(0.5, 1.5) * m + drift + rng.normal(0.0, 0.012, T)
            ret[0] = 0.0
            if name == "DNA":
                ret[pos(self.SPIN_DAY)] = -0.15
            c = p0 * np.cumprod(1.0 + ret)
            gap = rng.normal(0.0, 0.004, T)
            gap[0] = 0.0
            o = np.r_[c[0], c[:-1]] * (1.0 + gap)
            frames.append(pd.DataFrame({"symbol": name, "date": days, "o": o, "h": np.maximum(o, c) * 1.01, "l": np.minimum(o, c) * 0.99, "c": c, "v": rng.uniform(2e6, 5e6, T).astype("int64")}))
        eco = pd.concat(frames, ignore_index=True)
        gone = ((eco["symbol"] == "DLST") & (eco["date"] > self.DELIST_DAY)) | ((eco["symbol"] == "NOFILL") & (eco["date"] == self.NOFILL_DAY))
        self.eco = eco[~gone].reset_index(drop=True)                                       # the economic series: split-adjusted as of the latest pull
        self.raw = self.eco.copy()
        pre = ((self.raw["symbol"] == "SPLX") & (self.raw["date"] < self.SPLIT_DAY)).to_numpy()
        self.raw.loc[pre, ["o", "h", "l", "c"]] *= 2.0                                     # the share price as it printed before the 2-for-1
        rows = []

        def add(typ, sym, day, rate="", new_rate="", old_rate=""):
            rows.append({**{c_: "" for c_ in M.CA_COLS}, "type": typ, "symbol": sym, "ex_date": f"{TS(day):%Y-%m-%d}", "process_date": f"{TS(day):%Y-%m-%d}", "rate": rate, "new_rate": new_rate, "old_rate": old_rate, "special": "false"})
        for d in ("2026-11-13", "2026-12-01", "2026-12-18"):
            add("cash_dividend", "UPA", d, "0.3")
        for d in ("2026-11-20", "2026-12-15"):
            add("cash_dividend", "DNB", d, "0.4")
        for i in range(10, T, 63):
            add("cash_dividend", "N05", days[i], "0.2")
        add("cash_dividend", "ZZZZ", "2026-11-16", "0.1")                                    # a name no photograph holds: counted by the loader, never placed
        add("forward_split", "SPLX", self.SPLIT_DAY, "2", "2", "1")
        add("spin_off", "DNA", self.SPIN_DAY)
        self.ca = pd.DataFrame(rows)

    def photograph(self, through):
        """(raw, split, calendar) of the photograph through `through`, as fresh frames"""
        through = TS(through)
        start = through - pd.Timedelta(days=430)
        cut = lambda df: df[(df["date"] >= start) & (df["date"] <= through)].reset_index(drop=True)
        ev = pd.to_datetime(self.ca["ex_date"])
        return cut(self.raw), cut(self.eco if through >= self.SPLIT_DAY else self.raw), self.ca[(ev >= start) & (ev <= through)].reset_index(drop=True)

    def make(self, through, folder):
        raw, spl, cal = self.photograph(through)
        return write_photo(folder, through, raw, spl, cal)

    def write(self, root, through, rev=1, restate=None):
        """the photograph through `through` as <root>\\<through>[_rN] (restate(raw, split, calendar) -> the three frames as a later pull would hold them)"""
        raw, spl, cal = self.photograph(through)
        if restate is not None:
            raw, spl, cal = restate(raw, spl, cal)
        return write_photo(os.path.join(root, folder_name(through, rev)), through, raw, spl, cal, rev)

    def write_full(self, folder):
        """the whole history in one folder: the parity check's registered world (the harness's loaders on files)"""
        return write_photo(folder, self.LAST, self.raw, self.eco, self.ca)


def no_network(*a, **k):
    raise AssertionError("a network connection was attempted")


@contextlib.contextmanager
def fake_env(mk, tmp, es_days=None, n_side=5):
    """the selftest's inputs: the fake ES master (r15_ddw.ESFake, 5-minute RTH bars), a fake TBIS list with ONE flag (2025-12-05), n_side 5 (the registered 50 needs 100 eligible names) and every default output / root of this module pointed at a temp folder that
    must stay empty (a test that forgot to pass its own would write there); a socket connect raises (no network)"""
    tb = os.path.join(tmp, "tbis_fake.csv")
    write_atomic(tb, f"symbol,day,price_ratio,vol_ratio,split_like\nN03,{mk.TBIS_DAY},0.5,2.0,True\n")
    data, me = A13.data_mod(), sys.modules[__name__]
    keep = (data.find_master, data.load_master_arrays)
    (mk.es if es_days is None else D15.ESFake(es_days)).install()
    try:
        with patched(D15, TBIS_CSV=tb), patched(A13, TBIS_QA=tb), M.spec(n_side=n_side), patched(me, LINE_OUT=os.path.join(tmp, "default_out_unused"), ROOT_DEFAULT=os.path.join(tmp, "default_root_unused")),                 patched(socket.socket, connect=no_network), patched(socket, create_connection=no_network):
            yield
    finally:
        data.find_master, data.load_master_arrays = keep


# ---- plain-python oracles (r17's own brute_* recounts, not the vectorised path the tool uses)
def world_with_calendar(folder, t, es="stub"):
    """a photograph's World with the recounts' inputs attached: W.Dr_in / W.Sp_in read from the calendar CSV by r17's csv-module readers (not by the harness's pandas ones)"""
    W, info = photo_world(folder, t, es)
    p = os.path.join(folder, "corporate_actions.csv")
    W.Dr_in, W.Sp_in = M.brute_div_matrix(p, W.days, W.syms, info["t_end"]), M.brute_spin_matrix(p, W.days, W.syms, info["t_end"])
    return W, info


def oracle_daily(W, ranks, rows, hi):
    """plain python: every cell's daily P&L by session of the holds of `ranks` (hold k = rank k: filled at the open after it, exits at the open after the NEXT rank; the last is open and valued through row hi), from the rank files' names and M.brute_path (carried marks, 5 bps a side,
    borrow, dividends) at $4,000 a name; a pick with no open at its fill session is not filled -> ({cell: (T,)}, {(rank date, cell): the hold's total through min(exit, hi)})"""
    ix = {str(s_): j for j, s_ in enumerate(W.syms)}
    out, tot = {c: np.zeros(W.T) for c in M.CELLS}, {}
    for k, rk in enumerate(ranks):
        f = int(W.days.get_loc(rk)) + 1
        x = int(W.days.get_loc(ranks[k + 1])) + 1 if k + 1 < len(ranks) else hi + 1
        last = min(x, hi)
        for c in M.CELLS:
            tot[(rk, c)] = 0.0
            for r in rows[rk]:
                j = ix[r["symbol"]]
                if r["cell"] != c or not math.isfinite(W.Od[f, j] / W.F[f, j]):
                    continue
                path, _ = M.brute_path(W, f, x, j, 1 if r["side"] == "long" else -1, False)
                v = M.SPEC["slot"] * np.array(path[:last - f + 1])
                out[c][f:last + 1] += v
                tot[(rk, c)] += float(v.sum())
    return out, tot


def brute_forward_rank(W, r, f):
    """plain python: the picks a FORWARD rank makes at row r - the names in the universe at the fill row f with >= 230 own returns and ES pairs (brute_scores: the OLS by lstsq, loops), a close and a factor at the rank session, finite scores, no hygiene reason on r-25 .. r (all four) or on
    r-251 .. r-26 (gap, tbis, jump); no hold exists and the fill is unknown (CHOICE [L5] [L6]) -> ({cell: ([(col, score)] the n_side highest, [..] the n_side lowest)}, pool size)"""
    sp, nn = M.SPEC, M.SPEC["n_side"]
    a, lo_pre = M.windows(r)[0], r - sp["skip"] - sp["hyg_lead"] + 1
    pool = {}
    for j in [j for j in range(W.S) if W.U[f, j]]:
        n_ret, n_pair, res, raw = M.brute_scores(W, r, j)
        if n_ret < sp["min_n"] or n_pair < sp["min_n"] or not math.isfinite(W.Cl[r, j] / W.F[r, j]) or not (math.isfinite(res) and math.isfinite(raw)):
            continue
        if any(any(D15.brute_flags(W, s, j)) for s in range(lo_pre, r + 1)) or any(any(D15.brute_flags(W, s, j)[1:]) for s in range(max(a, 0), lo_pre)):
            continue
        pool[j] = (res, raw)
    out = {}
    for q, c in enumerate(M.CELLS):
        order = sorted(pool, key=lambda j: (pool[j][q], j))
        out[c] = ([(j, pool[j][q]) for j in order[::-1][:nn]], [(j, pool[j][q]) for j in order[:nn]])
    return out, len(pool)


def names_of(rows, cell, side):
    return [r["symbol"] for r in rows if r["cell"] == cell and r["side"] == side]

# ---- the tests without a photograph
HOLDER = """import os, sys
fh = open(sys.argv[1], "r+b")
if os.name == "nt":
    import msvcrt
    fh.seek(0)
    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
else:
    import fcntl
    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
print("locked", flush=True)
sys.stdin.readline()
"""
FZ_TEST = {"c_res": C_RES, "B": 3.0, "false_stop": {"3.00": 0.049}, "spread": 10000.0, "boot": dict(BOOT)}


def t_constants():
    """the registered numbers as written in NOTE 1 / the line's registration, and the two registrations unchanged"""
    assert (C_RES, C_RAW, LOOKS, C_STAR, FIRST_RANK, FIRST_FILL) == (0.264, 0.233, (12, 18, 24, 30, 36), 2.47, TS("2026-10-30"), TS("2026-11-02"))
    assert BOOT == {"draws": 20000, "rows": 756, "block": 21, "chunk": 2500, "seed": 20261016} and BOOT["rows"] == 36 * BOOT["block"]
    assert STOP["paths"] == 4000 and STOP["steps"] == 36 and STOP["seed"] == 20260929 and STOP["max_false"] == 0.05 and len(STOP["bounds"]) == 21 and STOP["bounds"][0] == 3.0 and STOP["bounds"][-1] == 8.0 and BOUND_EX == 2.0
    assert SEALED == (TS("2025-06-30"), TS("2026-06-30")) and WF_ROWS_FROM == TS("2017-01-03") and WF_ROWS_ALL == TS("2016-07-01") and CSV_END == TS("2025-06-29")
    assert CELLS_CSV_SHA == "bed7bf8b98d201894471cd3e72bd146bb87260c6cc8d1ac54b8167f923d41819" and M.CELLS == ("RES", "RAW") and M.SPEC["n_side"] == 50 and M.SPEC["slot"] == 4000.0
    reg = check_registered()
    assert reg["note1_sha256_lf"] == NOTE_SHA and reg["line_prereg_sha256_lf"] == LINE_SHA
    with patched(sys.modules[__name__], NOTE_SHA="0" * 64):
        refuses(check_registered, "DIFFERS from the registered text", "a changed NOTE 1")
    say("constants as registered (c 0.264 / 0.233, looks 12 .. 36, c* 2.47, bootstrap 20,000 x 756 block 21 seed 20261016, stop 4,000 x 36 seed 20260929 B 3.00 .. 8.00, bound 2.0); the line's registration and NOTE 1 verified by LF sha256, a changed one refuses")


def t_hold_next(tmp):
    """[N2](2) hold_next.txt = the UNION of the last TWO ranks' names (RES and RAW, longs and shorts), sorted, one symbol a line, written atomically: three hand-made ranks - the first has no earlier one (its own picks only), a name only in the OLDER rank (either cell, either side)
    must be in the file after the second, a third rank drops the oldest rank's names; the counts printed are (this rank, the earlier rank's only, union)"""
    out = os.path.join(tmp, "hold_next_out")
    os.makedirs(out)

    def fake_rank(day, picks):
        write_atomic(os.path.join(out, f"rank_{day}.csv"), rank_bytes([(c, sd, sym, 10.0 - i) for (c, sd), names in picks.items() for i, sym in enumerate(names)]))
    R1 = {("RES", "long"): ["A1", "A2", "SH"], ("RES", "short"): ["B1", "B2"], ("RAW", "long"): ["A1", "C1"], ("RAW", "short"): ["B1", "D1"]}
    R2 = {("RES", "long"): ["A3", "SH"], ("RES", "short"): ["B3", "B1"], ("RAW", "long"): ["A3", "C2"], ("RAW", "short"): ["B3", "E1"]}
    R3 = {("RES", "long"): ["A4"], ("RES", "short"): ["B4"], ("RAW", "long"): ["A4", "C2"], ("RAW", "short"): ["B4"]}
    nm = lambda R: {x for v in R.values() for x in v}
    text = lambda: open(os.path.join(out, "hold_next.txt"), "rb").read().decode("ascii")
    fake_rank("2026-10-30", R1)
    hn = write_hold_next(out, "2026-10-30")                                                                                   # the first rank: its own picks only
    assert hn["names"] == sorted(nm(R1)) and hn["prev"] is None and hn["prev_only"] == 0 and hn["this"] == (TS("2026-10-30"), len(nm(R1))) and hn["union"] == len(nm(R1)) == 7
    assert text() == "\n".join(sorted(nm(R1))) + "\n"
    fake_rank("2026-11-30", R2)
    hn = write_hold_next(out, "2026-11-30")
    old_only = nm(R1) - nm(R2)
    assert old_only == {"A1", "A2", "B2", "C1", "D1"} and {"C1", "D1"} <= set(hn["names"]) and old_only <= set(hn["names"])           # names only in the older rank - RES and RAW, long and short - are in
    assert hn["names"] == sorted(nm(R1) | nm(R2)) and hn["this"] == (TS("2026-11-30"), len(nm(R2))) and hn["prev"] == (TS("2026-10-30"), len(nm(R1))) and hn["prev_only"] == len(old_only) == 5 and hn["union"] == len(nm(R1) | nm(R2)) == 11
    assert text() == "\n".join(sorted(nm(R1) | nm(R2))) + "\n" and text().count("\n") == 11 and "" not in text().split("\n")[:-1] and text().endswith("\n") and "\r" not in text()
    fake_rank("2026-12-31", R3)
    hn = write_hold_next(out, "2026-12-31")
    gone = nm(R1) - nm(R2) - nm(R3)                                                                                              # the oldest rank's names that the two newest do not carry
    assert gone == {"A1", "A2", "B2", "C1", "D1"} and not gone & set(hn["names"]) and hn["names"] == sorted(nm(R2) | nm(R3)) and hn["prev"] == (TS("2026-11-30"), len(nm(R2))) and hn["prev_only"] == len(nm(R2) - nm(R3)) == 5 and hn["union"] == len(nm(R2) | nm(R3)) == 8
    assert {"SH", "B1"} <= set(hn["names"]) and sorted(os.listdir(out)) == ["hold_next.txt", "rank_2026-10-30.csv", "rank_2026-11-30.csv", "rank_2026-12-31.csv"]       # SH / B1 are still in the second rank; no temp file is left
    assert [d for d, _ in hold_next_sets(out, "2026-11-30")] == [TS("2026-10-30"), TS("2026-11-30")] and [d for d, _ in hold_next_sets(out, "2026-10-30")] == [TS("2026-10-30")]
    say("hold_next: three hand-made ranks - the first writes its own 7 names, the second writes the UNION of both (11; the 5 names only in the older rank, RES / RAW and long / short, are in it), the third drops the oldest rank's names (union of ranks 2 and 3: 8); sorted, one symbol a line, LF, no temp file left; "
        "the counts (this rank / the earlier rank's only / union) come out as printed")


def t_frozen():
    """the pasted FROZEN block is internally consistent (a damaged paste cannot pass): the constants are the registered ones, B is on the grid and the smallest bound within 5% of the printed table, the net / spread / hold counts agree with each other"""
    if FROZEN is None:
        say("FROZEN is not pasted yet (read refuses until it is)")
        return
    fz = FROZEN
    assert fz["c_res"] == C_RES and fz["c_raw"] == C_RAW and fz["boot"] == BOOT and fz["cells_csv_sha256"] == CELLS_CSV_SHA and fz["stop"] == {"paths": STOP["paths"], "steps": STOP["steps"], "seed": STOP["seed"], "looks": list(LOOKS)}
    assert fz["rows_from"] == f"{WF_ROWS_FROM:%Y-%m-%d}" and fz["n_rows"] > 2000 and abs(fz["spread"] - C_RES * fz["sd_sum"]) < 1e-6 * fz["spread"]
    assert len(fz["res_holds"]) == len(fz["raw_holds"]) == 101 and abs(sum(fz["res_holds"]) - fz["res_net"]) < 1e-3 and abs(sum(fz["raw_holds"]) - fz["raw_net"]) < 1e-3
    tried = sorted(float(k) for k in fz["false_stop"])
    assert tried == [b for b in STOP["bounds"] if b <= fz["B"]] and fz["B"] in STOP["bounds"] and all(fz["false_stop"][f"{b:.2f}"] > STOP["max_false"] for b in tried[:-1]) and fz["false_stop"][f"{fz['B']:.2f}"] <= STOP["max_false"]
    assert frozen_diff(json.loads(json.dumps(fz)), fz) == []
    say(f"FROZEN block consistent: B {fz['B']:.2f} on the grid and the smallest bound within 5% of its printed table ({', '.join(f'{k}: {v:.2%}' for k, v in fz['false_stop'].items())}), spread = 0.264 x the sd of the sums, 101 RES / RAW holds summing to the nets, the registered constants")


def t_calendar():
    ends = [month_end_session(d) for d in ("2026-10-30", "2026-10-29", "2026-10-31", "2026-11-30", "2026-11-27", "2026-12-31", "2027-01-29", "2027-01-31", "2027-02-26", "2027-05-28", "2027-05-31", "2026-01-30", "2026-06-30", "2025-12-31")]
    assert ends == [True, False, False, True, False, True, True, False, True, True, False, True, True, True], ends
    assert nth_weekday(2026, 11, 3, 4) == TS("2026-11-26") and nth_weekday(2027, 5, 0, -1) == TS("2027-05-31") and nth_weekday(2026, 1, 0, 3) == TS("2026-01-19")
    src = open(os.path.join(HERE, "r17_resmom_pull.py"), encoding="utf-8").read()
    blk = src[src.index("NYSE_CLOSED = {"):src.index("_SECRETS")]
    table = set(re.findall(r'"(\d{4}-\d{2}-\d{2})":', blk))
    assert len(table) == 31, len(table)
    for a, b in (("2026-01-01", "2027-12-31"), ("2025-01-01", "2025-12-31")):
        mine = {f"{d:%Y-%m-%d}" for d in pd.bdate_range(a, b) if nyse_closed(d)}
        theirs = {d for d in table if a <= d <= b} - {"2025-01-09"}                       # the one special closure (the National Day of Mourning) no holiday rule knows
        assert mine == theirs, (a, sorted(mine ^ theirs))
    for txt, frag in (("2026-10-31", "not the last NYSE session"), ("2026-10-29", "not the last NYSE session"), ("2026-09-30", "before the line's first month-end"), ("20261030", "not a date written YYYY-MM-DD"), ("2026-02-30", "not a real calendar date"),
                      ("", "not a date written"), ("2026-11-27", "not the last NYSE session")):
        refuses(lambda t=txt: parse_through(t), frag, f"--through {txt!r}")
    assert parse_through("2026-10-30") == FIRST_RANK and parse_through("2026-12-31") == TS("2026-12-31") and parse_through("2026-02-27", first=TS("2026-02-27")) == TS("2026-02-27")
    assert next_weekday("2026-10-30") == FIRST_FILL and next_weekday("2026-12-31") == TS("2027-01-01")
    assert [f"{d:%Y-%m-%d}" for d in month_ends(5)] == ["2026-10-30", "2026-11-30", "2026-12-31", "2027-01-29", "2027-02-26"]
    say("month-end rule: 14 hand-picked dates; the holiday rules agree with r17_resmom_pull's closure table for every weekday of 2026 - 2027 (and of 2025 but its one special closure); --through refuses a non-month-end, a weekend, a date before 2026-10-30, a bad format and a non-date")


def t_guard():
    guard_dates(["2025-06-29", "2026-07-01", "2020-03-31", TS("2027-01-04")], "x")
    for d in ("2025-06-30", "2026-06-30", "2025-12-31", TS("2026-03-02")):
        refuses(lambda d=d: guard_dates([d], "this mark"), "sealed year", f"guard {d}")
    refuses(lambda: photo_from_cache("2025-06-30", os.path.join(tempfile.gettempdir(), "resmomline_never_made")), "sealed year", "a parity photograph on the cut")
    say("sealed-year guard: 2025-06-29 and 2026-07-01 pass, both ends of 2025-06-30 .. 2026-06-30 and the inside refuse before anything is shown; a parity photograph through 2025-06-30 refuses before reading")


def t_files(tmp):
    p = os.path.join(tmp, "a", "b.txt")
    write_atomic(p, "one")
    write_atomic(p, b"two")
    assert open(p, "rb").read() == b"two" and os.listdir(os.path.dirname(p)) == ["b.txt"]
    p2 = os.path.join(tmp, "a", "c.csv")
    write_rows(p2, ("a", "b"), [[1, 2.5], ["x,y", "z"]])
    assert read_rows(p2) == [{"a": "1", "b": "2.5"}, {"a": "x,y", "b": "z"}] and read_rows(os.path.join(tmp, "nothing.csv")) == []
    assert open(p2, "rb").read() == b"a,b\n1,2.5\n\"x,y\",z\n" and fnum(0.1 + 0.2) == "0.30000000000000004" and float(fnum(1 / 3)) == 1 / 3
    out = os.path.join(tmp, "lockdir")
    with line_lock(out):
        refuses(lambda: line_lock(out).__enter__(), "holds the lock", "a second lock in the process")
    with line_lock(out):
        pass
    size = os.path.getsize(os.path.join(out, "line.lock"))
    child = os.path.join(tmp, "holder.py")
    write_atomic(child, HOLDER)
    proc = subprocess.Popen([sys.executable, child, os.path.join(out, "line.lock")], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "locked"
        def grab():
            with line_lock(out):
                pass
        refuses(grab, "holds the lock", "a lock held by another process")
    finally:
        proc.stdin.close()
        proc.wait(timeout=60)
    with line_lock(out):
        pass
    assert os.path.getsize(os.path.join(out, "line.lock")) == size == 80
    say("files: atomic writes leave no temp file and replace in place, csv rows round-trip, floats print shortest-exact; the OS lock refuses a second writer in this process AND in another one (not waiting), is free again when the other process ends, and its file never grows")


def t_numerics():
    d = pd.DatetimeIndex(["2017-01-05", "2017-01-06", "2017-01-07", "2017-01-08", "2017-01-09"])
    s = fold_weekends(d, [1.0, 10.0, 100.0, 1000.0, 10000.0])
    assert list(s.index) == [TS("2017-01-05"), TS("2017-01-06"), TS("2017-01-09")] and list(s.values) == [1.0, 1110.0, 10000.0]
    x = np.random.default_rng(3).normal(0.0, 1.0, 100)
    kw = dict(draws=300, rows=63, block=21)
    a = boot_sums(x, chunk=300, seed=11, **kw)
    assert np.array_equal(a, boot_sums(x, chunk=300, seed=11, **kw)) and not np.array_equal(a, boot_sums(x, chunk=300, seed=12, **kw))
    assert all(np.array_equal(a, boot_sums(x, chunk=ch, seed=11, **kw)) for ch in (1, 7, 70, 299, 301, 5000))                  # chunk-invariant: the chunk only batches the arithmetic
    rng, n, want = np.random.default_rng(11), len(x), []
    for q in range(300):                                                                                               # the documented draw order, in plain python: per draw the 3 block starts, then the 3 signs
        st = rng.integers(0, n, size=3)
        sg = rng.integers(0, 2, size=3) * 2.0 - 1.0
        want.append(sum(sg[k] * sum(x[(st[k] + o) % n] for o in range(21)) for k in range(3)))
    assert np.allclose(a, want, rtol=0, atol=1e-9)
    sums = boot_sums(np.full(40, 2.0), draws=500, rows=63, block=21, chunk=100, seed=4)                                    # constant series: every block sums to 42, the draw to 42 x (sum of 3 signs)
    assert set(np.round(sums / 42.0).astype(int)) <= {-3, -1, 1, 3} and len(set(np.round(sums / 42.0).astype(int))) == 4
    sp = spread_of(x, 0.5, chunk=300, seed=11, **kw)
    assert abs(sp["sd_sum"] - float(np.std(a))) < 1e-12 and abs(sp["spread"] - 0.5 * float(np.std(a))) < 1e-12 and sp["rows"] == 100 and sp["draws"] == 300
    refuses_val = False
    try:
        boot_sums(x, draws=10, rows=50, block=21)
    except ValueError:
        refuses_val = True
    assert refuses_val
    dd = np.random.default_rng(5).normal(-200.0, 3000.0, 101)                                                         # the false-stop rates against a plain-python recount on the same draws
    bounds, paths, steps = (2.0, 3.0, 4.5), 80, 36
    rates = false_stop_rates(dd, bounds=bounds, paths=paths, steps=steps, seed=7)
    X = (dd - dd.mean())[np.random.default_rng(7).integers(0, 101, size=(paths, steps))]

    def tt(y):
        n_, m_ = len(y), sum(y) / len(y)
        sd = math.sqrt(sum((v - m_) ** 2 for v in y) / (n_ - 1))
        return m_ / (sd / math.sqrt(n_)) if sd > 0 else 0.0
    for B in bounds:
        stops = 0
        for p in range(paths):
            hit = False
            for L in LOOKS:
                y = [float(v) for v in X[p][:L]]
                t_all, t_nomax, t_nomin = tt(y), tt(sorted(y)[:-1]), tt(sorted(y)[1:])
                hit |= (t_all >= B and t_nomax >= 2.0) or (t_all <= -B and t_nomin <= -2.0)
            stops += hit
        assert abs(rates[B] - stops / paths) < 1e-12, (B, rates[B], stops / paths)
    assert rates[2.0] >= rates[3.0] >= rates[4.5] > -1e-12
    assert choose_bound({3.0: 0.2, 3.25: 0.06, 3.5: 0.05, 3.75: 0.01}) == (3.5, [(3.0, 0.2), (3.25, 0.06), (3.5, 0.05)]) and choose_bound({3.0: 0.2, 3.25: 0.06})[0] is None
    one = lambda v: np.array([float(v)])                                                                                 # stops_at(t, t without the largest, t without the smallest, B): either side, each with its ex-extreme condition
    assert stops_at(one(3.0), one(2.0), one(0.0), 3.0).tolist() == [True] and stops_at(one(3.0), one(1.9), one(-9.0), 3.0).tolist() == [False]
    assert stops_at(one(-3.0), one(0.0), one(-2.0), 3.0).tolist() == [True] and stops_at(one(-3.0), one(-9.0), one(-1.9), 3.0).tolist() == [False] and stops_at(one(-2.9), one(0.0), one(-9.0), 3.0).tolist() == [False]
    fz = {"a": 1.5, "B": 3.25, "false_stop": {"3.00": 0.1, "3.25": 0.04}, "boot": {"draws": 20000}, "res_holds": [float(i) + 0.5 for i in range(101)], "rows_from": "2017-01-03", "n": 756}
    src = frozen_source(fz)
    assert src.startswith("FROZEN = {") and ast.literal_eval(src.split("=", 1)[1].strip()) == fz
    assert frozen_diff(fz, json.loads(json.dumps(fz))) == [] and frozen_diff({**fz, "a": 1.5 * (1 + 1e-12)}, fz) == []
    bad = {**fz, "res_holds": fz["res_holds"][:100] + [999.0]}
    assert frozen_diff(bad, fz) == ["res_holds"] and frozen_diff({**fz, "B": 3.5}, fz) == ["B"] and frozen_diff({k: v for k, v in fz.items() if k != "a"}, fz) == ["a"]
    sd1 = dollar_read(np.full(36, 1000.0), "2026-11-02", "2029-11-01", 10000.0)
    n = len(pd.bdate_range("2026-11-02", "2029-11-01"))
    scaled = 10000.0 * math.sqrt(n / 756)
    assert sd1["n_rows"] == n and abs(sd1["scaled_spread"] - scaled) < 1e-9 and abs(sd1["z"] - 36000.0 / scaled) < 1e-9
    lo, hi = np.full(36, 2.47 * scaled / 36 * 0.999), np.full(36, 2.47 * scaled / 36 * 1.001)
    assert not dollar_read(lo, "2026-11-02", "2029-11-01", 10000.0)["pass"] and dollar_read(hi, "2026-11-02", "2029-11-01", 10000.0)["pass"]
    say("numerics: the weekend fold; the bootstrap is deterministic, differs by seed, is chunk-invariant (chunks 1 .. 5,000), follows the documented draw order (recounted in plain python), constant input gives 42 x {-3, -1, 1, 3}; the false-stop rates equal a plain-python recount of the same draws at 3 bounds and fall as B rises; B is the smallest bound within 5%; "
        "the stop rule's two-sided exceptions; the FROZEN block round-trips through ast.literal_eval and its diff sees one changed hold, one changed B and a missing key but not a 1e-12 wobble; the dollar read scales the spread by sqrt(n / 756) and flips at c* 2.47")


def t_monitor():
    k = np.arange(12)
    d = 0.264 * (-9000.0 + 700.0 * np.sin(k))                                                                            # a consistent loser: EARLY FAIL at the first look
    rows, ended = monitor(np.r_[d, d[:6] * 0.9, d[:12]], 3.0)
    assert ended == 12 and rows[0]["state"] == "EARLY FAIL" and rows[0]["t"] < -3.0 and rows[0]["t_ex_min"] <= -2.0 and all(r["state"].startswith("not read: the line ended at look 12") for r in rows[1:])
    rng = np.random.default_rng(2)
    flat = rng.normal(0.0, 3000.0, 36)                                                                                    # no stop: noise around zero reads at every look and never fails
    rows, ended = monitor(flat, 8.0)
    assert ended is None and [r["state"] for r in rows] == ["continue"] * 4 + ["continue (the last look: no early fail)"]
    up = rng.normal(5000.0, 1000.0, 36)                                                                                   # the up side is never acted on: t >> B and still no stop (there is no early pass)
    rows, ended = monitor(up, 3.0)
    assert ended is None and all(r["t"] >= 3.0 for r in rows) and not any("EARLY" in r["state"] for r in rows)
    x1 = np.r_[-1250.0, np.linspace(-1100.0, 500.0, 11)]                                                                  # the most negative draw carries the t: t = -2.28 <= -B (B 2.0) but -1.87 without it -> the ex-extreme rule withholds the stop
    assert tstat(x1) <= -2.0 and tstat(np.delete(x1, 0)) > -2.0
    rows, ended = monitor(x1, 2.0)
    assert rows[0]["t"] <= -2.0 and rows[0]["t_ex_min"] > -2.0 and ended is None and rows[0]["state"] == "continue", rows[0]
    x2 = np.r_[-1250.0, np.linspace(-700.0, 100.0, 11)]                                                                   # the same most negative draw on a consistently negative run: t -3.52, -3.75 without it -> EARLY FAIL
    assert tstat(x2) <= -3.0 and tstat(np.delete(x2, 0)) <= -2.0
    for B in (2.0, 3.0):
        rows, ended = monitor(x2, B)
        assert ended == 12 and rows[0]["state"] == "EARLY FAIL" and rows[0]["t_ex_min"] <= -2.0
    rows, ended = monitor(flat[:5], 3.0)
    assert ended is None and [r["state"] for r in rows] == [f"not yet (k = 5 of {L})" for L in LOOKS]
    rows, ended = monitor(flat[:20], 3.0)
    assert [r["state"] for r in rows[:2]] == ["continue", "continue"] and rows[2]["state"] == "not yet (k = 20 of 24)"
    say("monitor reads on synthetic d's: a consistent loser stops at look 12 (later looks not read), noise never stops, a strong winner is never acted on, a most negative draw that carries the t does not stop it (t -2.28 <= -B but -1.87 without it: the ex-extreme rule) while the same draw on a consistently negative run does, k < look reads 'not yet'")


def fake_logs(out, res, with_pins=True):
    """hand-made line_log.csv (hold k: rank = the k-th month-end from 2026-10-30, fill / exit = the next weekday after it / after the next month-end) with the given RES, RAW 0.9 x RES, d_k = 0.264 x RES, and a three-session line_daily.csv"""
    ranks = month_ends(len(res) + 1)
    rows = [[str(k + 1), f"{ranks[k]:%Y-%m-%d}", f"{next_weekday(ranks[k]):%Y-%m-%d}", f"{next_weekday(ranks[k + 1]):%Y-%m-%d}", fnum(v), fnum(0.9 * v), fnum(C_RES * v)] for k, v in enumerate(res)]
    write_rows(os.path.join(out, "line_log.csv"), LOG_HEADS["line_log.csv"], rows)
    write_rows(os.path.join(out, "line_daily.csv"), LOG_HEADS["line_daily.csv"], [[f"2026-11-0{i}", "1.0", "2.0", fnum(C_RES), fnum(C_RAW * 2.0)] for i in (2, 3, 4)])


def t_read(tmp):
    out = os.path.join(tmp, "read_out")
    rng = np.random.default_rng(2)
    with patched(sys.modules[__name__], FROZEN=None):
        refuses(lambda: read_cmd(out), "FROZEN is not set in this tool", "read without FROZEN")
    fake_logs(out, -9000.0 + 700.0 * np.sin(np.arange(12)))                                                              # (a) EARLY FAIL at look 12
    r, text = captured(read_cmd, out, FZ_TEST)
    assert r["ended"] == 12 and r["dollar"] is None and r["k"] == 12 and "look 12: k 12, t -" in text and "EARLY FAIL" in text and "look 18: not read: the line ended at look 12" in text and "dollar read: not yet (k = 12 of 36" in text, text
    fake_logs(out, rng.normal(4000.0, 3000.0, 36))                                                                        # (b) 36 holds, up: no stop, the dollar read PASSES at spread 10,000
    r, text = captured(read_cmd, out, FZ_TEST)
    assert r["ended"] is None and r["k"] == 36 and r["dollar"]["pass"] and "dollar read at hold 36" in text and "PASS (the line is not ended; adoption is the owner's alone)" in text and text.count("-> continue") == 5, text
    r, text = captured(read_cmd, out, {**FZ_TEST, "spread": 30000.0})                                                      # (c) the same rows, a wider null: BELOW c*
    assert not r["dollar"]["pass"] and "BELOW c*: the line ends without adoption" in text
    fake_logs(out, rng.normal(0.0, 3000.0, 5))                                                                            # (d) five holds: nothing to read yet
    r, text = captured(read_cmd, out, FZ_TEST)
    assert r["ended"] is None and r["k"] == 5 and "look 12: not yet (k = 5 of 12)" in text and "line_log.csv 5 complete holds" in text and "none yet (no mark has appended a session)" in text
    rows = read_rows(os.path.join(out, "line_log.csv"))                                                                   # (e) refusals: d_k that is not 0.264 x RES, holds out of order, a sealed-year row
    rows[2]["d_k"] = "1.0"
    write_rows(os.path.join(out, "line_log.csv"), LOG_HEADS["line_log.csv"], [[r[h] for h in LOG_HEADS["line_log.csv"]] for r in rows])
    refuses(lambda: read_cmd(out, FZ_TEST), "is not 0.264 x RES", "a tampered d_k")
    fake_logs(out, rng.normal(0.0, 3000.0, 5))
    rows = read_rows(os.path.join(out, "line_log.csv"))
    write_rows(os.path.join(out, "line_log.csv"), LOG_HEADS["line_log.csv"], [[r[h] for h in LOG_HEADS["line_log.csv"]] for r in rows[::-1]])            # the file's order does not matter (sorted by k)
    r, _ = captured(read_cmd, out, FZ_TEST)
    assert r["k"] == 5
    write_rows(os.path.join(out, "line_log.csv"), LOG_HEADS["line_log.csv"], [[r[h] for h in LOG_HEADS["line_log.csv"]] for r in rows[:2] + rows[3:]])
    refuses(lambda: read_cmd(out, FZ_TEST), "not 1 .. k in order", "a hold missing from the log")
    write_rows(os.path.join(out, "line_log.csv"), LOG_HEADS["line_log.csv"], [[r[h] for h in LOG_HEADS["line_log.csv"]] for r in rows[:3] + rows[2:]])
    refuses(lambda: read_cmd(out, FZ_TEST), "not 1 .. k in order", "a hold twice in the log")
    fake_logs(out, rng.normal(0.0, 3000.0, 5))
    rows = read_rows(os.path.join(out, "line_log.csv"))
    rows[1]["exit_date"] = "2026-03-02"
    write_rows(os.path.join(out, "line_log.csv"), LOG_HEADS["line_log.csv"], [[r[h] for h in LOG_HEADS["line_log.csv"]] for r in rows])
    refuses(lambda: read_cmd(out, FZ_TEST), "sealed year", "a sealed-year hold in the log")
    say("read: EARLY FAIL on a loser (looks after it 'not read', no dollar read), no stop on a winner with the dollar read at hold 36 (PASS at spread 10,000, BELOW c* at 30,000), 'not yet' below the first look, and refusals for no frozen block, a d_k that is not 0.264 x RES, a hold missing or doubled in the log and a log row inside the sealed year")

# ---- the chain on fake photographs: pin -> rank -> mark, four month-ends, every refusal
def t_chain(tmp, mk):
    """four fake photographs (2026-10-30 / 11-30 / 12-31 / 2027-01-29 - the line's first four month-ends; the third as Alpaca pulled it that day: the close of UPA on 11-30 restated +1%, one bar of N10 missing, one calendar row more) through pin, rank and mark by the code the real run uses, with
    the numbers recounted by plain python (r17's brute_* on ONE unrestated world) -> the facts parity-on-fakes and the hand-over use"""
    me = sys.modules[__name__]
    root, out = os.path.join(tmp, "photos"), os.path.join(tmp, "line_out")
    T = [TS(d) for d in ("2026-10-30", "2026-11-30", "2026-12-31", "2027-01-29")]
    D = [f"{t:%Y-%m-%d}" for t in T]
    pp = os.path.join(out, "pins.csv")

    def restate(raw, spl, cal):
        for df in (raw, spl):
            m_ = ((df["symbol"] == "UPA") & (df["date"] == T[1])).to_numpy()
            df.loc[m_, "c"] = df.loc[m_, "c"] * 1.01
        gone = lambda df: df[~((df["symbol"] == "N10") & (df["date"] == TS("2026-11-12")))].reset_index(drop=True)
        extra = {**{c_: "" for c_ in M.CA_COLS}, "type": "cash_dividend", "symbol": "QQQQ", "ex_date": "2026-11-16", "process_date": "2026-11-16", "rate": "0.15", "special": "false"}
        return gone(raw), gone(spl), pd.concat([cal, pd.DataFrame([extra])], ignore_index=True)

    def tweak(raw, spl, cal):
        m_ = ((raw["symbol"] == "N00") & (raw["date"] == T[0])).to_numpy()
        raw.loc[m_, "c"] = raw.loc[m_, "c"] * 1.01
        return raw, spl, cal
    for i, t in enumerate(T):
        mk.write(root, t, restate=restate if i == 2 else None)
    mk.write(root, T[0], rev=2, restate=tweak)

    # ---------------------------------------------------------------- PIN ([N2](1))
    _, text = captured(pin_cmd, D[0], root, 1, out)
    pins = read_rows(pp)
    man0 = json.load(open(os.path.join(root, D[0], "manifest.json")))
    assert len(pins) == 1 and pins[0]["through"] == D[0] and pins[0]["folder"] == D[0] and pins[0]["files"] == "5" and pins[0]["manifest_sha256"] == sha_raw(os.path.join(root, D[0], "manifest.json"))
    assert pins[0]["calendar_sha256"] == man0["sha256"]["corporate_actions.csv"] and "5 files hashed against the manifest, all match" in text
    before = open(pp, "rb").read()
    _, text = captured(pin_cmd, D[0], root, 1, out)
    assert "already pinned" in text and open(pp, "rb").read() == before
    refuses(lambda: pin_cmd("2026-10-29", root, 1, out), "not the last NYSE session", "a non-month-end")
    refuses(lambda: pin_cmd("2026-09-30", root, 1, out), "before the line's first month-end", "before the first rank")
    refuses(lambda: pin_cmd("2027-02-26", root, 1, out), "no photograph folder", "a month-end with no photograph")
    refuses(lambda: pin_cmd(D[0], root, 2, out), "already pinned to", "another photograph (a re-pull) of a pinned month-end")
    for nm, damage in (("daily_raw.parquet", flip_byte), ("daily_split.parquet", flip_byte), ("corporate_actions.csv", flip_byte), ("corporate_actions_raw.jsonl", flip_byte), ("symbols.txt", os.remove)):
        bad = os.path.join(tmp, "bad_" + nm.split(".")[0])
        shutil.copytree(os.path.join(root, D[1]), os.path.join(bad, D[1]))
        if nm.endswith("jsonl"):                                                                                            # the JSONL is empty in a fake: give it a byte to change
            write_atomic(os.path.join(bad, D[1], nm), "x")
        damage(os.path.join(bad, D[1], nm))
        refuses(lambda b=bad: pin_cmd(D[1], b, 1, out), "does not match its manifest", f"{nm} changed after publication")
    nomf = os.path.join(tmp, "bad_nomanifest")
    shutil.copytree(os.path.join(root, D[1]), os.path.join(nomf, D[1]))
    os.remove(os.path.join(nomf, D[1], "manifest.json"))
    refuses(lambda: pin_cmd(D[1], nomf, 1, out), "holds no manifest.json", "no manifest")
    shutil.copytree(os.path.join(root, D[1]), os.path.join(tmp, "bad_month", D[0]))
    refuses(lambda: pin_cmd(D[0], os.path.join(tmp, "bad_month"), 1, os.path.join(tmp, "out_throwaway")), "is the photograph through 2026-11-30", "the manifest of another month-end")
    assert open(pp, "rb").read() == before
    say("pin: one dated row (through, folder, manifest sha256, calendar sha256, UTC time, 5 files hashed); an identical second pin is a no-op; a re-pull of a pinned month-end, a non-month-end, a date before the first rank, a missing folder / manifest, a manifest of another month-end and ONE changed byte in any of the five files "
        "(or one file missing) all refuse - pins.csv untouched")

    # ---------------------------------------------------------------- RANK ([N2](2))
    def boom(*a, **k):
        raise AssertionError("a bar was read")
    with patched(me, photo_world=boom):
        refuses(lambda: rank_cmd(D[1], root, out), "is not pinned", "a rank without a pin")
        refuses(lambda: rank_cmd("2026-09-30", root, out), "before the line's first month-end", "a rank before 2026-10-30")
    _, text0 = captured(rank_cmd, D[0], root, out)
    rk0 = os.path.join(out, f"rank_{D[0]}.csv")
    got0, bytes0 = read_rank(rk0), open(rk0, "rb").read()
    assert list(got0[0]) == list(RANK_HEAD) and len(got0) == 20 and bytes0.endswith(b"\n") and b"\r" not in bytes0
    for c in M.CELLS:
        assert set(names_of(got0, c, "long")) == {"UPA", "SPLX", "NOFILL", "DLST", "EARLY"} and set(names_of(got0, c, "short")) == {"DNA", "DNB", "DNC", "DND", "DNE"}, ("fixture", c, names_of(got0, c, "long"), names_of(got0, c, "short"))
    assert "pre_tbis n/a (no forward TBIS)" in text0 and "TBIS flag file: 1 symbol-days listed, the last on 2025-12-05" in text0 and "old_gap 1" in text0 and "(CHOICE [L3]: the reason cannot fire there)" in text0, text0
    npool = int(re.search(r"eligible pool (\d+)", text0).group(1))
    (W0, info0), _ = captured(world_with_calendar, os.path.join(root, D[0]), T[0], "real")
    r0, f0 = check_world(W0, T[0], need_es=True)
    want, npool0 = brute_forward_rank(W0, r0, f0)
    assert npool0 == npool and info0["phantom"] == FIRST_FILL and W0.T - 1 == f0
    for c in M.CELLS:
        for q, side in enumerate(("long", "short")):
            g = [(r["symbol"], float(r["score"])) for r in got0 if r["cell"] == c and r["side"] == side]
            w = [(str(W0.syms[j]), v) for j, v in want[c][q]]
            assert [a for a, _ in g] == [a for a, _ in w] and np.allclose([b for _, b in g], [b for _, b in w], rtol=1e-9, atol=1e-12), (c, side, g, w)
    _, text = captured(rank_cmd, D[0], root, out)
    assert "IDENTICAL" in text and open(rk0, "rb").read() == bytes0
    rl = read_rows(os.path.join(out, "ranks.csv"))
    assert len(rl) == 1 and rl[0]["through"] == D[0] and rl[0]["rank_sha256"] == hashlib.sha256(bytes0).hexdigest() and rl[0]["pool"] == str(npool) and rl[0]["manifest_sha256"] == pins[0]["manifest_sha256"] and rl[0]["tool_sha256_lf"] == sha_lf(os.path.abspath(__file__))
    out_b = os.path.join(tmp, "line_out_b")
    captured(pin_cmd, D[0], root, 1, out_b)
    captured(rank_cmd, D[0], root, out_b)
    assert open(os.path.join(out_b, f"rank_{D[0]}.csv"), "rb").read() == bytes0
    out_t = os.path.join(tmp, "line_out_tamper")
    shutil.copytree(out, out_t)
    with open(os.path.join(out_t, f"rank_{D[0]}.csv"), "ab") as fh:
        fh.write(b"RES,long,ZZZ,1.0\n")
    refuses(lambda: rank_cmd(D[0], root, out_t), "never overwritten", "a rank file of other content on file")
    hn = lambda: open(os.path.join(out, "hold_next.txt")).read().split()
    assert hn() == sorted({r["symbol"] for r in got0}) and len(hn()) == 10
    root_t = os.path.join(tmp, "photos_t")
    shutil.copytree(root, root_t)
    flip_byte(os.path.join(root_t, D[0], "daily_raw.parquet"))
    refuses(lambda: rank_cmd(D[0], root_t, out), "does not match its manifest", "a pinned photograph changed after the pin")
    root_r = os.path.join(tmp, "photos_r")
    os.makedirs(root_r)
    mk.write(root_r, T[0], restate=tweak)
    refuses(lambda: rank_cmd(D[0], root_r, out), "is not the photograph that was pinned", "another photograph under the pinned name")
    out_c = os.path.join(tmp, "line_out_c")
    captured(pin_cmd, D[0], root, 1, out_c)
    captured(pin_cmd, D[2], root, 1, out_c)
    refuses(lambda: rank_cmd(D[2], root, out_c), "previous month-end has no rank_<date>.csv", "a rank with the month before it unranked")
    out_e = os.path.join(tmp, "line_out_e")
    captured(pin_cmd, D[0], root, 1, out_e)
    with fake_env(mk, tmp, es_days=[d for d in mk.days if d != T[0]]):
        refuses(lambda: rank_cmd(D[0], root, out_e), "has no return for the month-end session", "an ES master that stops before the month-end")
    assert not os.path.exists(os.path.join(out_e, f"rank_{D[0]}.csv"))
    refuses(lambda: check_world(W0, T[1]), "last real session is 2026-10-30, not 2026-11-30", "a photograph of another month-end")
    with patched(me, MIN_SESSIONS=10 ** 6):
        refuses(lambda: check_world(W0, T[0]), "fewer than the", "too few sessions")
    man_ = W0.ca["file"]["manifest"]
    keep_start, man_["start"] = man_["start"], "2026-06-01"
    refuses(lambda: check_world(W0, T[0]), "calendar starts 2026-06-01", "a calendar that starts inside the regression window")
    man_["start"] = keep_start
    out_p = os.path.join(tmp, "line_out_pool")
    captured(pin_cmd, D[0], root, 1, out_p)
    with M.spec(n_side=40):
        refuses(lambda: rank_cmd(D[0], root, out_p), "fewer than the 80 the registered rule needs", "a pool too small to trade")
    assert not os.path.exists(os.path.join(out_p, f"rank_{D[0]}.csv"))
    say(f"rank 2026-10-30: 10 + 10 picks (5 long / 5 short a cell) equal a plain-python recount (brute_scores' lstsq OLS, the hygiene windows, the universe) name for name, side for side, score to 1e-9 - pool {npool}; planted winners / losers on the right sides; TBIS reason printed 'n/a (no forward TBIS)' with the "
        "file's last day; rank file deterministic (re-run IDENTICAL, a second folder byte-equal), never overwritten with other content; refuses without a pin (before reading a bar), before 2026-10-30, with the previous month unranked, on a pinned photograph that changed or was re-published, on an ES master with no return at the month-end, on a photograph of another month-end, with too few sessions or a calendar that starts inside the window, and on a pool too small to trade")

    captured(pin_cmd, D[1], root, 1, out)
    _, text1 = captured(rank_cmd, D[1], root, out)
    got1 = read_rank(os.path.join(out, f"rank_{D[1]}.csv"))
    n0, n1 = {r["symbol"] for r in got0}, {r["symbol"] for r in got1}
    assert hn() == sorted(n0 | n1) and (n0 - n1) and (n1 - n0) and "DLST" not in n1, (sorted(n0), sorted(n1))
    assert (n0 - n1) <= set(hn()) and "DLST" in hn() and "DLST" in n0                                                       # the delisted name only the OLDER rank holds is still on the file: the next pull must carry it
    assert f"rank {D[0]} {len(n0)} names, no earlier rank (the first), union {len(n0)}" in text0, text0
    assert f"rank {D[1]} {len(n1)} names, rank {D[0]} only {len(n0 - n1)} more (it has {len(n0)}), union {len(n0 | n1)}" in text1, text1
    assert {"UPA", "SPLX", "LATE", "UPB"} <= set(names_of(got1, "RES", "long")) and "EARLY" not in names_of(got1, "RES", "long"), names_of(got1, "RES", "long")
    captured(rank_cmd, D[0], root, out)
    assert hn() == sorted(n0 | n1)
    captured(pin_cmd, D[2], root, 1, out)
    captured(rank_cmd, D[2], root, out)
    got2 = read_rank(os.path.join(out, f"rank_{D[2]}.csv"))
    n2 = {r["symbol"] for r in got2}
    gone = (n0 - n1) - n2
    assert hn() == sorted(n1 | n2) and set(hn()) != n1 | n0 and gone and not gone & set(hn()) and "DLST" not in hn(), (sorted(gone), hn())     # the third rank drops the oldest rank's names
    captured(pin_cmd, D[3], root, 1, out)
    captured(rank_cmd, D[3], root, out)
    assert hn() == sorted(n2 | {r["symbol"] for r in read_rank(os.path.join(out, f"rank_{D[3]}.csv"))})
    say(f"hold_next.txt = the union of the LAST TWO ranks' names, both cells, both sides: {len(n0 | n1)} names after the second rank ({len(n0 - n1)} only in the first, {len(n1 - n0)} only in the second), the oldest rank's names dropped after the third and fourth; re-running an old month never rewinds it")

    # ---------------------------------------------------------------- MARK ([N2](3))
    r, text = captured(mark_cmd, D[0], root, out)
    assert r is None and "first photograph" in text and not any(os.path.exists(os.path.join(out, n)) for n in MARK_LEDGERS)
    r1, text1 = captured(mark_cmd, D[1], root, out)
    days1 = list(mk.days[(mk.days > T[0]) & (mk.days <= T[1])])
    L = lambda n: read_rows(os.path.join(out, n))
    assert r1["dates"] == days1 and len(days1) == 20 and r1["completed_k"] is None
    assert [len(L(n)) for n in ("line_daily.csv", "line_parts.csv", "line_log.csv", "marks.csv")] == [20, 1, 0, 1] and [r_["date"] for r_ in L("line_daily.csv")] == [f"{d:%Y-%m-%d}" for d in days1]
    assert text1.count("unfilled picks 1") == 2 and "tbis n/a (no forward TBIS)" in text1 and r1["flags"]["spin"] == 2 and ("RES", "DNA", "spin") in r1["listed"], (text1, r1["listed"])
    ov = r1["overlap"]
    assert text1.count("all identical") == 2 and ov["cells_total"] == 0 and all(f_["differing_rows"] == f_["only_prev"] == f_["only_cur"] == 0 for f_ in ov["frames"].values()) and ov["calendar"]["only_prev"] == ov["calendar"]["only_cur"] == 0
    assert ov["rows_total"] == 0 and ov["calendar_csv"] is None and not os.path.exists(os.path.join(out, f"overlap_{D[1]}.csv")) and L("marks.csv")[0]["sessions"] == "20" and L("marks.csv")[0]["completed_k"] == "" and len(L("marks.csv")[0]["tool_sha256_lf"]) == 64
    snap = {n: open(os.path.join(out, n), "rb").read() for n in MARK_LEDGERS}
    refuses(lambda: mark_cmd(D[1], root, out), "already marked", "a second mark of the same month-end")
    assert all(open(os.path.join(out, n), "rb").read() == snap[n] for n in MARK_LEDGERS)
    os.replace(os.path.join(out, "marks.csv"), os.path.join(tmp, "marks_aside.csv"))                                         # the guards behind marks.csv's: a mark that stopped half way (parts written, commit record not) is never repeated
    refuses(lambda: mark_cmd(D[1], root, out), "line_parts.csv already holds rows of the 2026-11-30 mark", "a mark that stopped half way: its parts are on file")
    write_rows(os.path.join(out, "line_parts.csv"), LOG_HEADS["line_parts.csv"], [])
    refuses(lambda: mark_cmd(D[1], root, out), "line_daily.csv already holds", "a session already in line_daily.csv")
    os.replace(os.path.join(tmp, "marks_aside.csv"), os.path.join(out, "marks.csv"))
    with open(os.path.join(out, "line_parts.csv"), "wb") as fh:
        fh.write(snap["line_parts.csv"])
    assert all(open(os.path.join(out, n), "rb").read() == snap[n] for n in MARK_LEDGERS)
    out_n = os.path.join(tmp, "line_out_nan")
    os.makedirs(out_n)
    write_rows(os.path.join(out_n, "pins.csv"), PINS_HEAD, [[p_[h] for h in PINS_HEAD] for p_ in read_rows(os.path.join(out, "pins.csv")) if p_["through"] in (D[0], D[1])])
    for n in (f"rank_{D[0]}.csv", f"rank_{D[1]}.csv"):
        shutil.copy(os.path.join(out, n), os.path.join(out_n, n))
    nan_vals = lambda W_, lo_, hi_, a_=None, b_=None: {c: {"daily": np.full(hi_ - lo_ + 1, np.nan), "a_exit": 0.0, "b_part": float("nan")} for c in M.CELLS}
    with patched(me, value_sessions=nan_vals):
        refuses(lambda: mark_cmd(D[1], root, out_n), "a non-finite value in the valuation", "a valuation that is not a number")
    assert not any(os.path.exists(os.path.join(out_n, n)) for n in MARK_LEDGERS)
    out_g = os.path.join(tmp, "line_out_gap")
    captured(pin_cmd, D[0], root, 1, out_g)
    captured(pin_cmd, D[2], root, 1, out_g)
    refuses(lambda: mark_cmd(D[2], root, out_g), "missing from the chain", "a month with no pin between two photographs")
    out_h = os.path.join(tmp, "line_out_norank")
    captured(pin_cmd, D[0], root, 1, out_h)
    captured(pin_cmd, D[1], root, 1, out_h)
    refuses(lambda: mark_cmd(D[1], root, out_h), "no rank_2026-10-30.csv", "a mark with no rank file for the hold")
    refuses(lambda: mark_cmd(D[3], root, os.path.join(tmp, "line_out_nopin")), "is not pinned", "a mark with no pin")
    out_m, root_m = os.path.join(tmp, "line_out_m"), os.path.join(tmp, "photos_m")
    shutil.copytree(out, out_m)
    pins_m = [p_ for p_ in read_rows(os.path.join(out_m, "pins.csv")) if p_["through"] in (D[0], D[1])]                    # the state when only the first two photographs were pinned (2026-12-31 not yet)
    write_rows(os.path.join(out_m, "pins.csv"), PINS_HEAD, [[p_[h] for h in PINS_HEAD] for p_ in pins_m])
    out_m2, root_m2 = os.path.join(tmp, "line_out_m2"), os.path.join(tmp, "photos_m2")
    shutil.copytree(out_m, out_m2)
    shutil.copytree(os.path.join(root, D[1]), os.path.join(root_m, D[1]))
    shutil.copytree(os.path.join(root, D[1]), os.path.join(root_m2, D[1]))
    drop = lambda sym: (lambda raw, spl, cal: (raw[raw["symbol"] != sym].reset_index(drop=True), spl[spl["symbol"] != sym].reset_index(drop=True), cal))
    mk.write(root_m, T[2], restate=drop("UPA"))                                                                            # UPA is a pick of BOTH holds (ranks 10-30 and 11-30): both are named
    captured(pin_cmd, D[2], root_m, 1, out_m)
    msg = refuses(lambda: mark_cmd(D[2], root_m, out_m), "['UPA'] of hold 1 (rank 2026-10-30, exits at the open of 2026-12-01)", "a held name the photograph does not carry")
    assert "['UPA'] of hold 2 (rank 2026-11-30, open at this month-end)" in msg and "hold_next.txt written after the 2026-11-30 rank" in msg, msg
    mk.write(root_m2, T[2], restate=drop("EARLY"))                                                                         # EARLY is a pick of the 10-30 rank only: only the exiting hold 1 is named
    captured(pin_cmd, D[2], root_m2, 1, out_m2)
    msg = refuses(lambda: mark_cmd(D[2], root_m2, out_m2), "held name(s) ['EARLY'] of hold 1 (rank 2026-10-30, exits at the open of 2026-12-01) are not in this photograph's world", "a held name of the exiting hold only")
    assert "hold 2" not in msg
    assert [len(read_rows(os.path.join(out_m, n))) for n in ("line_daily.csv", "marks.csv")] == [20, 1] and [len(read_rows(os.path.join(out_m2, n))) for n in ("line_daily.csv", "marks.csv")] == [20, 1]
    out_k = os.path.join(tmp, "line_out_nopart")
    os.makedirs(out_k)
    for n in ("pins.csv", f"rank_{D[0]}.csv", f"rank_{D[1]}.csv"):
        shutil.copy(os.path.join(out, n), os.path.join(out_k, n))
    refuses(lambda: mark_cmd(D[2], root, out_k), "no valued fill and marks", "the previous photograph was never marked")
    say("mark 2026-11-30 (the first photograph that can append): 20 sessions valued from this photograph, 1 part, no completed hold, appended once to line_daily / line_parts / marks; the NOFILL pick unfilled (counted), the DNA spin-off flagged and kept; the overlap with the 10-30 photograph all identical; "
        "a duplicate refuses (marks.csv, and with that row removed the half-way guards on line_parts.csv and line_daily.csv) leaving every ledger byte-equal, a valuation that is not a number refuses before any write; refuses a gap in the chain of pins, a missing rank file, a missing pin, a held name the photograph does not carry (naming the hold: number, rank, role) and a previous photograph never marked")

    real_pw = photo_world
    calls = []

    def spy(folder, through, es="real"):
        calls.append((os.path.basename(folder), TS(through), es))
        return real_pw(folder, through, es)
    with patched(me, photo_world=spy):
        r2, text2 = captured(mark_cmd, D[2], root, out)
    assert calls == [(D[2], T[2], "stub")], calls                                                                           # ONE world: this photograph's, no earlier photograph's bars are valued
    log = L("line_log.csv")
    assert r2["completed_k"] == 1 and [x_["k"] for x_ in log] == ["1"] and log[0]["rank_date"] == D[0] and log[0]["fill_date"] == "2026-11-02" and log[0]["exit_date"] == "2026-12-01"
    assert "hold 1 (rank 2026-10-30) is complete" in text2 and "DLST (long)" in text2 and text2.count("unfilled picks 1") == 2 and any(x_[1] == "SPLX" and "split" in x_[2] for x_ in r2["listed"]) and r2["flags"]["split"] >= 1
    lo_ = max(TS(json.load(open(os.path.join(root, f, "manifest.json")))["start"]) for f in (D[1], D[2]))
    n_win = int(((mk.days >= lo_) & (mk.days <= T[1])).sum())
    ov = r2["overlap"]
    assert ov["frames"]["raw"]["differing_rows"] == 1 and ov["frames"]["raw"]["cells_by_field"] == {"o": 0, "h": 0, "l": 0, "c": 1, "v": 0} and ov["frames"]["raw"]["only_prev"] == 1 and ov["frames"]["raw"]["only_cur"] == 0
    assert ov["frames"]["split"]["differing_rows"] == n_win + 1 and ov["frames"]["split"]["cells_by_field"] == {"o": n_win, "h": n_win, "l": n_win, "c": n_win + 1, "v": 0} and ov["frames"]["split"]["only_prev"] == 1
    assert ov["calendar"]["only_prev"] == 0 and ov["calendar"]["only_cur"] == 1 and ov["cells_total"] == 4 * n_win + 2 and "differ" in text2
    csv_rows = read_rows(os.path.join(out, f"overlap_{D[2]}.csv"))
    assert len(csv_rows) == ov["cells_total"] + ov["rows_total"] == ov["lines_written"] and ov["rows_total"] == 2 and sum(r_["kind"] == "row_only_previous" and r_["symbol"] == "N10" for r_ in csv_rows) == 2
    assert [r_["symbol"] for r_ in csv_rows if r_["kind"] == "cell" and r_["symbol"] == "UPA"] == ["UPA", "UPA"] and any(r_["symbol"] == "UPA" and r_["date"] == D[1] and r_["field"] == "c" and r_["frame"] == "raw" for r_ in csv_rows)
    cal_rows = read_rows(ov["calendar_csv"])
    assert len(cal_rows) == 1 and cal_rows[0]["side"] == "current_only" and cal_rows[0]["symbol"] == "QQQQ" and cal_rows[0]["ex_date"] == "2026-11-16"
    assert "only in the current: cash_dividend QQQQ ex 2026-11-16" in text2 and "N10 2026-11-12: a bar only in the previous photograph" in text2 and f"UPA {D[1]} c: previous" in text2 and "more cells / one-sided bars of this frame in" in text2
    say(f"mark 2026-12-31 builds exactly ONE world (this photograph's: no earlier photograph's bars are valued), completes hold 1 (RES / RAW, d_1 = 0.264 x RES) in line_log.csv, exits the delisted DLST by the registered rule (no open at the exit session: its last mark, printed), flags SPLX's split inside the booked hold; "
        f"the overlap print reports EVERY difference against the 11-30 photograph - the restated UPA close (1 cell in each frame), the missing N10 bar, the extra calendar row and the {n_win} SPLX sessions the split restated in the split frame ({4 * n_win + 2} cells, all written to overlap_{D[2]}.csv)")

    r3, text3 = captured(mark_cmd, D[3], root, out)
    ov = r3["overlap"]
    assert r3["completed_k"] == 2 and ov["frames"]["raw"]["differing_rows"] == 1 and ov["frames"]["raw"]["only_cur"] == 1 and ov["frames"]["raw"]["only_prev"] == 0 and ov["frames"]["split"]["differing_rows"] == 1 and ov["frames"]["split"]["only_cur"] == 1
    assert ov["calendar"]["only_prev"] == 1 and ov["calendar"]["only_cur"] == 0
    snap_final = {n: open(os.path.join(out, n), "rb").read() for n in MARK_LEDGERS}
    assert snap_final["line_daily.csv"].startswith(snap["line_daily.csv"]) and snap_final["line_parts.csv"].startswith(snap["line_parts.csv"])                  # append-only: the first mark's rows are byte-for-byte where they were

    # ---------------------------------------------------------------- every appended number against ONE unrestated world, recounted in plain python
    (W3, info3), _ = captured(world_with_calendar, os.path.join(root, D[3]), T[3], "stub")
    ranks = [d for d, _ in rank_files(out)][:3]
    rows_by = {d: read_rank(p) for d, p in rank_files(out)}
    hi = W3.T - 2
    assert W3.days[hi] == T[3] and ranks == T[:3]
    orc, tot = oracle_daily(W3, ranks, rows_by, hi)
    ix = {str(s_): j for j, s_ in enumerate(W3.syms)}
    jU, f0_, i1 = ix["UPA"], int(W3.days.get_loc(T[0])) + 1, int(W3.days.get_loc(T[1]))
    mrel = W3.Ac[i1, jU] / W3.Ao[f0_, jU]
    delta = {}
    for c in M.CELLS:                                                                                                       # the restated UPA close is in the 12-31 photograph only: hold 1's exit leg, valued there, moves by -side x slot x 1% of the close / the entry (+ a short's borrow on it)
        side = next((1 if r_["side"] == "long" else -1 for r_ in rows_by[T[0]] if r_["cell"] == c and r_["symbol"] == "UPA"), 0)
        delta[c] = M.SPEC["slot"] * (side * (-0.01 * mrel) - (side < 0) * (M.BORROW / 252.0) * 0.01 * mrel)
    assert delta["RES"] != 0.0
    daily = L("line_daily.csv")
    first_row = int(W3.days.get_loc(T[0])) + 1
    assert [r_["date"] for r_ in daily] == [f"{d:%Y-%m-%d}" for d in W3.days[first_row:hi + 1]], len(daily)
    exit_day = f"{W3.days[i1 + 1]:%Y-%m-%d}"
    worst = 0.0
    for r_ in daily:
        i = int(W3.days.get_loc(TS(r_["date"])))
        for c in M.CELLS:
            worst = max(worst, abs(float(r_[c]) - (orc[c][i] + (delta[c] if r_["date"] == exit_day else 0.0))))
        assert abs(float(r_["RES_line"]) - C_RES * float(r_["RES"])) < 1e-9 and abs(float(r_["RAW_line"]) - C_RAW * float(r_["RAW"])) < 1e-9
    assert worst < 1e-6, worst
    log = L("line_log.csv")
    assert [x_["k"] for x_ in log] == ["1", "2"] and [x_["rank_date"] for x_ in log] == [D[0], D[1]] and log[1]["fill_date"] == "2026-12-01" and log[1]["exit_date"] == "2027-01-04"
    for k in (0, 1):
        for c in M.CELLS:
            assert abs(float(log[k][c]) - (tot[(ranks[k], c)] + (delta[c] if k == 0 else 0.0))) < 1e-6, (k, c, log[k][c], tot[(ranks[k], c)])
        assert abs(float(log[k]["d_k"]) - C_RES * float(log[k]["RES"])) < 1e-9
    parts = L("line_parts.csv")
    assert [(p["rank_date"], p["part"]) for p in parts] == [(D[0], "fill+marks"), (D[0], "exit"), (D[1], "fill+marks"), (D[1], "exit"), (D[2], "fill+marks")]
    for c in M.CELLS:
        assert abs(float(parts[4][c]) - tot[(ranks[2], c)]) < 1e-6 and abs(sum(float(p[c]) for p in parts) - sum(float(r_[c]) for r_ in daily)) < 1e-6
    assert abs(float(parts[0]["RES"]) + float(parts[1]["RES"]) - float(log[0]["RES"])) < 1e-9 and abs(float(parts[2]["RES"]) + float(parts[3]["RES"]) - float(log[1]["RES"])) < 1e-9
    say(f"every appended number against ONE unrestated world and M.brute_path (plain python: carried marks, 5 bps a side, borrow, the dividends incl. the one on the exit session, the 2-for-1 split, the delisting, the spin-off): {len(daily)} sessions x 2 cells equal to {worst:.1e}, except the restated-close session which "
        f"moves by exactly the analytic {delta['RES']:+,.2f} (RES); hold 1 and hold 2 totals (RES / RAW), the open hold 3's piece and every part sum to the same figures; line_log d_k = 0.264 x RES; the first mark's rows are untouched by later marks (append-only)")

    _, text = captured(read_cmd, out, FZ_TEST)
    assert "line_log.csv 2 complete holds" in text and "4 month-ends pinned" in text and text.count("manifest sha256") >= 3 and "look 12: not yet (k = 2 of 12)" in text
    return {"T": T, "D": D, "root": root, "out": out, "rows_by": rows_by}


def t_sealed(tmp, mk):
    """a mark whose sessions lie inside 2025-06-30 .. 2026-06-30 refuses before anything is printed or appended (the ranks of the sealed year are inputs and may be made)"""
    root, out = os.path.join(tmp, "sealed_photos"), os.path.join(tmp, "sealed_out")
    a, b = TS("2026-02-27"), TS("2026-03-31")
    for t in (a, b):
        mk.write(root, t)
        captured(pin_cmd, f"{t:%Y-%m-%d}", root, 1, out, a)
    _, text = captured(rank_cmd, "2026-02-27", root, out, a)
    assert "rank 2026-02-27" in text and os.path.exists(os.path.join(out, "rank_2026-02-27.csv"))
    msg = refuses(lambda: mark_cmd("2026-03-31", root, out, a), "sealed year", "a mark of sessions inside the sealed year")
    assert "first such date 2026-03-02" in msg and not any(os.path.exists(os.path.join(out, n)) for n in MARK_LEDGERS) and not os.path.exists(os.path.join(out, "overlap_2026-03-31.csv"))
    say("sealed year: a rank dated inside it is made (a ranking input), the mark of the next month refuses naming the first sealed session (2026-03-02) before any figure is printed, appended or overlapped - no ledger, no overlap file")

# ---- the parity machinery on the fake market's REGISTERED world, then the odds and ends
def t_parity_fake(tmp, mk):
    """the parity checks (i) .. (iv) on the fake market's registered world (the harness's own loaders on ONE full-history folder, the registered 'remove' reading): they pass where they must - the rank path equals the registered picks, the forward-information picks differ only by
    the look-ahead removals the registered reading makes (here: SPLX's split inside the second hold, DNA's spin-off inside the first, NOFILL's missing fill open, each counted and explained), the mark path equals the registered daily series and hold P&Ls, a rank through a photograph equals the
    full world's, and pin -> mark over four photographs reproduces the series - and they FAIL when a number is moved"""
    full = os.path.join(tmp, "full_history")
    mk.write_full(full)
    (W, info), _ = captured(photo_world, full, mk.days[-1], "real")
    assert W.days[-2] == mk.days[-1]
    L = M.rm_build(W, W.days[0], W.days[-2], "remove")
    n = len(L.recs)
    assert n >= 12 and all(rec.traded for rec in L.recs) and W.days[L.recs[-1].r] == TS("2026-12-31"), (n, W.days[L.recs[-1].r])
    meta, pnl, series = wf_holds(W, L)
    assert len(meta) == n and meta[-1][0] == TS("2026-12-31") and all(abs(pnl[c].sum() - series[c].sum()) < 1e-6 for c in M.CELLS)
    ok, worst, n_r = check_rank_identity(W, L)
    assert ok and worst is None and n_r == n
    ok, inf = check_forward_information(W, L)
    assert ok and not inf["unexplained"] and inf["names_differing"] >= 3 and {"post_split", "post_spin", "no_real_open"} <= set(inf["reasons"]), inf
    daily, parts = emulate_marks(W, L)
    cs = pd.DataFrame({"date": W.days, "RES": series["RES"], "RAW": series["RAW"]})
    res = check_daily(W, daily, cs)
    assert all(r_["max_abs"] < 1e-6 and r_["off_index"] == 0.0 and r_["rows"] == len(W.days) for r_ in res.values()), res
    assert all(np.abs(parts[c] - pnl[c]).max() < 1e-6 for c in M.CELLS)
    bad = {c: daily[c].copy() for c in M.CELLS}
    i = int(W.days.get_loc(TS("2026-12-15")))
    bad["RES"][i] += 1.0
    rb = check_daily(W, bad, cs)
    assert abs(rb["RES"]["max_abs"] - 1.0) < 1e-9 and rb["RES"]["worst_date"] == W.days[i] and rb["RAW"]["max_abs"] < 1e-6
    off = {c: daily[c].copy() for c in M.CELLS}
    off["RAW"][-1] += 5.0                                                                                                   # a value booked on a date the series does not have (the phantom row): caught beside the common index
    assert check_daily(W, off, cs.iloc[:-1])["RAW"]["off_index"] == 5.0
    ptmp = os.path.join(tmp, "parity")
    os.makedirs(ptmp)
    ok3, res3 = check_photo_picks(W, ("2026-09-30", "2026-10-30"), ptmp, make=mk.make)
    assert ok3 and [(d_, n_, o_) for d_, n_, o_ in res3] == [("2026-09-30", 20, True), ("2026-10-30", 20, True)]
    ok4, r4 = check_chain(W, L, meta, pnl, cs, ptmp, ("2026-09-30", "2026-10-30", "2026-11-30", "2026-12-31"), make=mk.make)
    assert ok4 and r4["holds_completed"] == 2 and r4["worst"][0] < 0.005 and r4["hold_worst"][0] < 0.005 and r4["sessions"] == int(((W.days > TS("2026-09-30")) & (W.days <= TS("2026-12-31"))).sum()), r4
    r_, f_ = int(W.days.get_loc(TS("2026-10-30"))), int(W.days.get_loc(TS("2026-10-30"))) + 1
    rec, cnt = rank_picks(W, r_, f_)
    for last, na in ((TS("2025-12-05"), True), (None, True), (W.days[r_], False)):                                          # the TBIS reason prints 'n/a' while the TBIS file ends before the hygiene window starts, its count once the file reaches it
        _, txt = captured(print_counts, W, {"tbis_last_day": last, "tbis_rows": 0 if last is None else 1}, r_, rec, cnt)
        assert ("pre_tbis n/a (no forward TBIS)" in txt) == na and (f"pre_tbis {cnt.get('pre_tbis', 0)}" in txt) == (not na), txt
    say(f"parity machinery on the fake market's registered world ({n} rebalances 2025-11 .. 2026-12): (i-1) the rank path = the registered picks (names, sides, order, scores, through the rank file's write / read-back); (i-2) the forward-information picks differ in {inf['names_differing']} of {inf['picks']} picks, all explained "
        f"{inf['reasons']}; (ii) the mark path = the registered daily series on every row and (iii) = every hold's P&L ({max(np.abs(parts[c] - pnl[c]).max() for c in M.CELLS):.1e}); (i-3) the rank through a photograph = the full world's at 2 dates; (iv) pin -> mark over 4 photographs reproduces the series "
        f"(worst {r4['worst'][0]:.1e}) and both completed holds; a $1 move on one row is caught (|diff| 1.000, on that date), a value off the CSV's index is caught; the TBIS 'n/a' print follows the file's last day")


def t_misc(tmp):
    me = sys.modules[__name__]
    bad = os.path.join(tmp, "not_the_export.csv")
    write_atomic(bad, "date,RES,RAW\n2017-01-03,1,2\n")
    fz_out = os.path.join(tmp, "fz_out")
    with patched(me, CELLS_CSV=bad):
        refuses(lambda: freeze_cmd(fz_out), "is not the registered export", "freeze on another export")
        refuses(parity_cmd, "is not the registered export", "parity on another export")
    assert not os.path.exists(fz_out)
    with patched(me, NOTE_PREREG=os.path.join(tmp, "nowhere.txt")):
        refuses(check_registered, "is not next to this file", "NOTE 1 missing")
    with patched(me, LINE_SHA="0" * 64):
        refuses(lambda: freeze_cmd(fz_out), "DIFFERS from the registered text", "the line's registration changed")
    seen = []
    with patched(me, pin_cmd=lambda *a: seen.append(("pin", a)), rank_cmd=lambda *a: seen.append(("rank", a)), mark_cmd=lambda *a: seen.append(("mark", a))):
        main(["prog", "pin", "--through=2026-10-30", "--root", r"C:\x", "--rev", "2"])
        main(["prog", "rank", "--through", "2026-11-30"])
        main(["prog", "mark", "--root", r"C:\y", "--through", "2026-12-31"])
    assert seen == [("pin", ("2026-10-30", r"C:\x", 2)), ("rank", ("2026-11-30", None)), ("mark", ("2026-12-31", r"C:\y"))], seen
    for argv, frag in ((["p"], "unknown command"), (["p", "bogus"], "unknown command"), (["p", "pin"], "needs --through"), (["p", "pin", "--through", "2026-10-30", "--bogus", "x"], "unknown option"), (["p", "rank", "--through"], "needs a value"),
                       (["p", "mark", "--through", "2026-10-30", "--through", "2026-11-30"], "given twice"), (["p", "read", "--through", "2026-10-30"], "unknown option"), (["p", "pin", "--through", "2026-10-30", "--rev", "x"], "not a whole number"),
                       (["p", "rank", "2026-10-30"], "unexpected argument")):
        refuses(lambda a=argv: main(a), frag, f"arguments {argv}")
    say("odds and ends: freeze / parity refuse another export before loading anything, a changed registration refuses every command, the command line is parsed strictly (options with = or a space, a missing value, a repeated or unknown option, a bad --rev, a stray argument)")


def selftest():
    """fakes only (no network - a socket connect raises -, no key, no real file; every output in one temp folder): constants / calendar / guard / files / locks / numerics / monitor / read, then the chain pin -> rank -> mark on four fake photographs with every refusal and every number recounted in plain
    python, the sealed-year guard, the parity machinery on the fake market's registered world, the command line"""
    t0 = time.time()
    tmp = tempfile.mkdtemp(prefix="resmomline_selftest_")
    print(f"selftest of r17_resmom_line.py: fakes only, temp folder {tmp}; the registered harness r17_resmom.py imported as it is")
    try:
        t_constants()
        t_frozen()
        t_hold_next(tmp)
        t_calendar()
        t_guard()
        t_files(tmp)
        t_numerics()
        t_monitor()
        t_read(tmp)
        mk = FakeMarket()
        say(f"fake market: {len(mk.eco['symbol'].unique())} names x {len(mk.days)} sessions {mk.days[0]:%Y-%m-%d} .. {mk.days[-1]:%Y-%m-%d}, {len(mk.ca)} calendar rows, the fake ES master (r15_ddw.ESFake) as the market factor")
        with fake_env(mk, tmp):
            t_chain(tmp, mk)
            t_sealed(tmp, mk)
            t_parity_fake(tmp, mk)
        t_misc(tmp)
        assert not os.path.exists(os.path.join(tmp, "default_out_unused")) and not os.path.exists(os.path.join(tmp, "default_root_unused")), "a test wrote to the default output / root"
        assert "alpaca_keys" not in sys.modules and "r17_resmom_pull" not in sys.modules, "the key lookup or the pull module was imported"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"selftest ok ({time.time() - t0:.0f}s): constants and registrations, the month-end rule (= the pull's closure table), the sealed-year guard, atomic writes and the cross-process lock, the bootstrap (deterministic, chunk-invariant, plain-python draw order), the false-stop calibration "
          "(recounted), the stop rule's exceptions, the monitor and the dollar read, pin / rank / mark on four fake photographs with every refusal (a changed byte, a re-pull, no pin, a gap, a missing rank, a missing name, a duplicate, a sealed-year session) and every ledger number equal to a plain-python "
          "recount - the delisting, the split, the spin-off, the dividends, the restated bar and the overlap print included -, hold_next = the last two ranks, and the parity checks passing on a registered world and failing when a number moves")


USAGE = """usage (from the worktree, EDGELOG_ROOT = the shared checkout): python tools/rocfrontier/r17_resmom_line.py <command>
    freeze                                   [N1] once: the monitor's B and the dollar read's spread from walk-forward data; prints the FROZEN block
    pin  --through YYYY-MM-DD [--root R] [--rev N]    [N2](1) hash the photograph's files against its manifest, append one dated row to pins.csv
    rank --through YYYY-MM-DD [--root R]              [N2](2) the registered picks at the month-end close -> rank_<D>.csv, hold_next.txt
    mark --through YYYY-MM-DD [--root R]              [N2](3) value the sessions since the previous month-end from this photograph alone -> line_daily.csv, line_log.csv
    read                                     [N3] the monitor's state and the dollar read
    parity                                   walk-forward only: the rank, mark and freeze code paths against the registered harness
    selftest                                 fakes only"""


def parse_opts(args, allowed, cmd):
    """['--through', 'D', '--root=R'] -> {'through': 'D', 'root': 'R'}; a stray argument, an option the command does not take, a repeated one or one without a value refuses"""
    opts, i = {}, 0
    while i < len(args):
        a = args[i]
        if not a.startswith("--"):
            refuse(f"refused: unexpected argument {a!r} for {cmd}\n{USAGE}")
        key, eq, val = a[2:].partition("=")
        if key not in allowed:
            refuse(f"refused: unknown option --{key} for {cmd} (it takes: {', '.join('--' + k for k in allowed) or 'none'})\n{USAGE}")
        if not eq:
            i += 1
            if i >= len(args) or args[i].startswith("--"):
                refuse(f"refused: --{key} needs a value\n{USAGE}")
            val = args[i]
        if key in opts:
            refuse(f"refused: --{key} given twice\n{USAGE}")
        opts[key] = val
        i += 1
    return opts


def main(argv):
    cmd, args = (argv[1], argv[2:]) if len(argv) > 1 else ("", [])
    takes = {"freeze": (), "selftest": (), "read": (), "parity": (), "pin": ("through", "root", "rev"), "rank": ("through", "root"), "mark": ("through", "root")}
    if cmd not in takes:
        refuse(f"refused: unknown command {cmd!r}\n{USAGE}")
    o = parse_opts(args, takes[cmd], cmd)
    if cmd in ("pin", "rank", "mark") and "through" not in o:
        refuse(f"refused: {cmd} needs --through YYYY-MM-DD\n{USAGE}")
    if cmd == "pin":
        try:
            rev = int(o.get("rev", 1))
        except ValueError:
            refuse(f"refused: --rev {o['rev']!r} is not a whole number\n{USAGE}")
        pin_cmd(o["through"], o.get("root"), rev)
    elif cmd == "rank":
        rank_cmd(o["through"], o.get("root"))
    elif cmd == "mark":
        mark_cmd(o["through"], o.get("root"))
    else:
        {"freeze": freeze_cmd, "selftest": selftest, "read": read_cmd, "parity": parity_cmd}[cmd]()


if __name__ == "__main__":
    main(sys.argv)
