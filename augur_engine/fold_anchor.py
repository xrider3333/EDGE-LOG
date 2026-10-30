"""FOLD ANCHORS - fold bounds that survive a master change, or refuse loudly (MANAGER #100, design approved #102).

A validate's fold rows store bar INDICES into the window it loaded (auto.py fold rows: train/test bars) plus ET date
labels. A splice, repair or roll rebuild that adds or removes bars ahead of a bound moves every later index: #491's
folds 4-8 sit 740 bars off on today's masters and the book NOISE leg #422's 129 (2020-02-28 +60, 06-30 +69). Every
tool that rebuilds a fold from a saved run (chain reads, wfdive, the TTM crown harness, backfill_wf_oos) then scores
different bars from the ones the run scored, silently.

THREE CALLS
  window_fp(arrays, master)   one small dict per run: bar count, first/last bar, three hashes of the whole window
                              (times / values / shape), bars per year, and the master file name + sha.
  stamp(arrays, a, b, warm)   one small dict per fold or stretch: the bound indices, the TIMES they point at (first
                              and last bar of [a, b), and the warm-start bar), and the same three hashes over [warm, b).
  resolve(arrays, st, fp)     maps a stamp onto a fresh load BY TIMESTAMP and says what happened to its bars:
        same            the bars are identical and at the same indices
        shifted         the bars are identical but sit at other indices (data changed elsewhere): use the new indices
        re-anchored     same times, prices moved by a constant per stretch (an adjusted twin rebuilt after a roll);
                        point-difference logic scores the same bars, level logic does not
        values-changed  same times, other prices (a re-splice or repair inside the span)
        changed         bars added or removed inside the span
        missing         a stamped bar time is not in the new window
      strict (default) accepts only 'same' and 'shifted' and raises BoundsDrift otherwise, naming what moved.

SIZE: a stamp is about 230 bytes and window_fp about 1 KB, so a 10-fold run adds ~3.5 KB to its doc (1 MiB Firestore cap).
Hashes are the first 16 hex of a sha256. Pure functions: no registry, no I/O except the optional master file sha.
"""
import hashlib
import os

import numpy as np

STATUSES = ("same", "shifted", "re-anchored", "values-changed", "changed", "missing")
STRICT_OK = ("same", "shifted")
_HEX = 16
_DEC = 6          # price/volume rounding before hashing (the masters carry quarter ticks; floats only add noise)


class BoundsDrift(Exception):
    """A stored fold bound no longer points at the bars it was scored on."""


def _times(arrays):
    """Bar-start epoch seconds (int64) of a load_master_arrays() window."""
    idx = arrays["index"]
    v = getattr(idx, "asi8", None)
    if v is None:
        v = np.asarray(idx, dtype="datetime64[ns]").astype("int64")
    return np.asarray(v, dtype="int64") // 1_000_000_000


def _h(*parts):
    h = hashlib.sha256()
    for p in parts:
        h.update(np.ascontiguousarray(p).tobytes())
    return h.hexdigest()[:_HEX]


def _cols(arrays, lo, hi):
    out = []
    for k in ("open", "high", "low", "close", "volume"):
        x = arrays.get(k)
        out.append(np.zeros(hi - lo) if x is None else np.round(np.asarray(x[lo:hi], dtype="float64"), _DEC))
    return out


def _hashes(arrays, t, lo, hi):
    """(time, value, shape) hashes of bars [lo, hi). SHAPE drops the level: bar-to-bar close changes, each bar's
    own high/low/open distance to its close, and volume - unchanged when an adjusted twin moves a whole stretch by
    a constant, changed by any real price edit."""
    o, h, l, c, v = _cols(arrays, lo, hi)
    shape = (np.round(np.diff(c), _DEC), np.round(h - c, _DEC), np.round(l - c, _DEC), np.round(o - c, _DEC), v)
    return _h(t[lo:hi]), _h(o, h, l, c, v), _h(*shape)


def file_sha(path, chunk=1 << 22):
    """sha256 (first 16 hex) of a master file, CRLF-insensitive like the roll tables; '' when unreadable."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for b in iter(lambda: fh.read(chunk), b""):
                h.update(b.replace(b"\r\n", b"\n"))
        return h.hexdigest()[:_HEX]
    except OSError:
        return ""


def window_fp(arrays, master=None, uploads=None):
    """The run-level fingerprint of the window the run loaded (goes in the run doc as `window_fp`)."""
    t = _times(arrays)
    n = len(t)
    ts, vs, ss = _hashes(arrays, t, 0, n)
    years, counts = np.unique((t.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970), return_counts=True)
    fp = dict(v=1, n=int(n), first=int(t[0]) if n else None, last=int(t[-1]) if n else None,
              time_sha=ts, value_sha=vs, shape_sha=ss,
              per_year={str(int(y)): int(k) for y, k in zip(years, counts)})
    if master:
        fn = master.get("filename") or ""
        fp["master"] = fn
        fp["master_sha"] = file_sha(os.path.join(uploads, fn)) if (uploads and fn) else ""
    return fp


def stamp(arrays, a, b, warm_from=None):
    """Stamp the bound [a, b) (warm-up from `warm_from`, default a) of a fold or stretch."""
    t = _times(arrays)
    n = len(t)
    a, b = int(a), int(b)
    w = a if warm_from is None else int(warm_from)
    if not (0 <= w <= a < b <= n):
        raise ValueError("fold_anchor.stamp: need 0 <= warm_from <= a < b <= n, got %d, %d, %d, %d" % (w, a, b, n))
    ts, vs, ss = _hashes(arrays, t, w, b)
    return dict(a=a, b=b, w=w, t_a=int(t[a]), t_last=int(t[b - 1]), t_w=int(t[w]),
                time_sha=ts, value_sha=vs, shape_sha=ss)


def _per_year_moves(fp_old, fp_new):
    if not fp_old or not fp_new:
        return ""
    a, b = fp_old.get("per_year") or {}, fp_new.get("per_year") or {}
    moved = ["%s %+d" % (y, b.get(y, 0) - a.get(y, 0)) for y in sorted(set(a) | set(b)) if a.get(y, 0) != b.get(y, 0)]
    return ("bars per year moved: " + ", ".join(moved)) if moved else "bars per year unchanged"


def resolve(arrays, st, run_fp=None, strict=True, allow=STRICT_OK, explain=None, label="fold"):
    """Map stamp `st` onto `arrays` (a fresh load of the same window). Returns dict(a, b, w, status, note).

    Fast path: when the whole window's time and value hashes equal the run's, nothing moved anywhere.
    Otherwise the bound times are looked up in the new bar grid and the span is re-hashed.
    `explain(st)` may return extra text for the refusal (e.g. the registry splices/repairs since the run)."""
    t = _times(arrays)
    if run_fp is not None:
        cur = window_fp(arrays)
        if cur["time_sha"] == run_fp.get("time_sha") and cur["value_sha"] == run_fp.get("value_sha"):
            return dict(a=st["a"], b=st["b"], w=st["w"], status="same", note="window unchanged")
    else:
        cur = None

    def at(x):
        i = int(np.searchsorted(t, int(x), side="left"))
        return i if i < len(t) and int(t[i]) == int(x) else None

    a, last, w = at(st["t_a"]), at(st["t_last"]), at(st["t_w"])
    if a is None or last is None or w is None:
        status, out = "missing", dict(a=a, b=None if last is None else last + 1, w=w)
        note = "stamped bar time(s) not in this window: " + ", ".join(
            k for k, v in (("start", a), ("last", last), ("warm", w)) if v is None)
    else:
        b = last + 1
        out = dict(a=a, b=b, w=w)
        ts, vs, ss = _hashes(arrays, t, w, b)
        if ts != st["time_sha"]:
            status, note = "changed", "bars added or removed inside the span (%d -> %d bars)" % (
                st["b"] - st["w"], b - w)
        elif vs == st["value_sha"]:
            moved = (a, b, w) != (st["a"], st["b"], st["w"])
            status = "shifted" if moved else "same"
            note = ("same bars, now at %+d" % (a - st["a"])) if moved else "same bars, same indices"
        elif ss == st["shape_sha"]:
            status, note = "re-anchored", "same bars, prices moved by a constant (adjusted twin rebuilt)"
        else:
            status, note = "values-changed", "same bar times, other prices (re-splice or repair inside the span)"
    out.update(status=status, note=note)
    if strict and status not in allow:
        extra = _per_year_moves(run_fp, cur if cur is not None else (window_fp(arrays) if run_fp else None))
        more = explain(st) if explain else ""
        raise BoundsDrift("%s [%d, %d) is %s: %s%s%s" % (label, st["a"], st["b"], status.upper(), note,
                                                       ("; " + extra) if extra else "", ("; " + more) if more else ""))
    return out


# ---------------------------------------------------------------- C5: compact data fingerprint on every run
def data_fp_enabled():
    """Kill switch: AUGUR_DATA_FP=0 turns the per-run data fingerprint off."""
    return os.environ.get("AUGUR_DATA_FP", "1").strip() not in ("0", "false", "no", "off")


def data_fp(arrays, master=None):
    """C5 (board 38): compact fingerprint of the window a run loaded, ~250 bytes.

    {master, bars, first_ts, last_ts, hash}; hash = sha256 over first/last ts + bar count + a cheap content hash
    (times + closes). Metadata only - never feeds a number, a trade or a trial-cache key. None when switched off."""
    if not data_fp_enabled():
        return None
    t = _times(arrays)
    n = int(len(t))
    first = int(t[0]) if n else None
    last = int(t[-1]) if n else None
    content = _h(t, np.round(np.asarray(arrays["close"], dtype="float64"), _DEC))
    h = hashlib.sha256(("%s|%s|%d|%s" % (first, last, n, content)).encode()).hexdigest()[:_HEX]
    name = ""
    if isinstance(master, dict):
        name = master.get("filename") or master.get("name") or ""
    elif master:
        name = str(master)
    return {"v": 1, "master": name, "bars": n, "first_ts": first, "last_ts": last, "hash": h}


def fold_bounds_check(fold, run_fp=None, today_bars=None, today_fp=None, run_label="?"):
    """Board 38 re-read guard for one saved fold row.

    Returns ("ts", (start_ts, end_ts)) when the row carries timestamps (always preferred),
    ("idx", (start, end)) when only indices exist and the data is provably unchanged,
    and raises BoundsDrift with one line when only indices exist and the data changed
    (fingerprint differs, or no fingerprint and the bar count differs) or cannot be checked."""
    s_ts, e_ts = fold.get("test_start_ts"), fold.get("test_end_ts")
    if s_ts is not None and e_ts is not None:
        return "ts", (s_ts, e_ts)
    a, b = fold.get("test_start"), fold.get("test_end")
    old_n = (run_fp or {}).get("bars")
    if run_fp and today_fp:
        if run_fp.get("hash") == today_fp.get("hash"):
            return "idx", (a, b)
        why = "bars %s -> %s" % (old_n, today_fp.get("bars"))
    elif today_bars is not None and old_n is not None and int(old_n) == int(today_bars):
        return "idx", (a, b)
    else:
        why = "bars %s -> %s" % (old_n if old_n is not None else "unknown", today_bars if today_bars is not None else (today_fp or {}).get("bars", "unknown"))
    raise BoundsDrift("FOLD BOUNDS UNSAFE: run #%s stored bar indices only and the data changed since (%s); "
                      "not re-reading" % (run_label, why))
