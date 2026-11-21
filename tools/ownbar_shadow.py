"""LOG-ONLY own-bar shadow study (runs on the EDGE-LOG paper box, one-shot 09:29-16:05 ET).

For every QQQ 5m bar of the session it logs, to <EDGELOG_HOME>/logs/ownbar_shadow.jsonl:
  * own bar  = the five stream 1m bars (ohlc_stream/QQQ_1m.csv, epoch = bar START) folded
               into one 5m bar, read at close+0.5 s and close+1 s;
  * stream5  = the streamer's own 5m row (ohlc_stream/QQQ_5m.csv) at close+1 s, if present;
  * REST bar = api.cloud_signal._fetch_webull("5m") (the executor's fetch), first read from
               close+1 s, then once a second until the value has read identical for
               STABLE_S (5 s, ProvisionalBarGuard's rule) = "final", capped at MAX_S;
  * per-field differences own@1s - rest_final, rest_first - rest_final, and
    seconds_to_final (when the guard would have released the bar).

SAFETY: no order code is imported or called; it never writes anything except its own jsonl;
it touches no service, unit, cache or config. Reads only: two csv tails + REST market data
(one 5m data request per second for ~6-15 s after each close = extra load on the same
Webull data quota the executor uses; lower with OWNBAR_STEP_S).
Modelled on probe_bar_settle.py. Systemd unit/timer text: deploy/ownbar_shadow.{service,timer}.
"""
import datetime as dt
import json
import os
import sys
import time
from zoneinfo import ZoneInfo

HOME = os.environ.get("EDGELOG_HOME", "/home/ubuntu/edgelog")
sys.path.insert(0, os.path.join(HOME, "EDGE-LOG"))
ET = ZoneInfo("America/New_York")
OUT = os.path.join(HOME, "logs", "ownbar_shadow.jsonl")
S1M = os.path.join(HOME, "ohlc_stream", "QQQ_1m.csv")
S5M = os.path.join(HOME, "ohlc_stream", "QQQ_5m.csv")
STABLE_S = float(os.environ.get("OWNBAR_STABLE_S", "5"))
STEP_S = float(os.environ.get("OWNBAR_STEP_S", "1"))
MAX_S = float(os.environ.get("OWNBAR_MAX_S", "45"))
FIELDS = ("open", "high", "low", "close", "volume")
BACKOFF_429_S = float(os.environ.get("OWNBAR_BACKOFF_429_S", "60"))
_BACKOFF_UNTIL = [0.0]


def _private_token_dir():
    """VERIFIER 11-21: never write the shared Webull token file. Copy the shared token dir
    into a private one and point the SDK there, so any refresh the SDK writes lands in the
    copy. Returns the private path (or None when there is no shared dir to copy)."""
    import shutil
    shared = os.environ.get("EDGELOG_WEBULL_TOKEN_DIR") or os.path.join(HOME, "webull_token")
    if not os.path.isdir(shared):
        return None
    priv = os.path.join(HOME, "ownbar_shadow_token")
    shutil.rmtree(priv, ignore_errors=True)
    shutil.copytree(shared, priv)
    os.environ["EDGELOG_WEBULL_TOKEN_DIR"] = priv
    return priv


def tail_rows(path, nbytes=4096):
    """Last rows of a 6-column epoch csv -> {start_epoch: [o,h,l,c,v]}. Never raises."""
    out = {}
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - nbytes))
            lines = fh.read().decode("ascii", "replace").splitlines()[1:]
    except OSError:
        return out
    for ln in lines:
        p = ln.split(",")
        if len(p) != 6:
            continue
        try:
            out[int(float(p[0]))] = [float(x) for x in p[1:]]
        except ValueError:
            continue
    return out


def fold_own(rows1m, start):
    """Own 5m bar from the 1m rows starting in [start, start+300). None if any minute missing."""
    mins = [rows1m.get(start + 60 * k) for k in range(5)]
    if any(m is None for m in mins):
        return {"bar": None, "minutes": sum(m is not None for m in mins)}
    return {"bar": [mins[0][0], max(m[1] for m in mins), min(m[2] for m in mins),
                    mins[4][3], sum(m[4] for m in mins)], "minutes": 5}


def _is_429(text):
    t = str(text or "").lower()
    return "429" in t or "rate limit" in t or "too many" in t


def rest_read(cs, start):
    """One REST read. VERIFIER 11-21: on a 429 from the shared Webull key, stop reading for
    BACKOFF_429_S so the executor keeps the quota; reads inside a back-off return 'BACKOFF'."""
    if time.time() < _BACKOFF_UNTIL[0]:
        return "BACKOFF"
    try:
        df = cs._fetch_webull("5m", count=3, log=lambda *a: None)
    except Exception as e:  # noqa: BLE001 - log-only probe
        if _is_429(e):
            _BACKOFF_UNTIL[0] = time.time() + BACKOFF_429_S
            return "ERR 429"
        return "ERR " + type(e).__name__
    if df is None:
        txt = str(getattr(cs, "_WEBULL_LAST_ERR", {}).get("text"))
        if _is_429(txt):
            _BACKOFF_UNTIL[0] = time.time() + BACKOFF_429_S
            return "ERR 429"
        return "ERR " + txt[:80]
    for _, r in df.iterrows():
        if int(r["time"]) == start:
            return [float(r[k]) for k in FIELDS]
    return None


def diff(a, b):
    if not isinstance(a, list) or not isinstance(b, list):
        return None
    return {f: round(x - y, 6) for f, x, y in zip(FIELDS, a, b)}


def wait_until(t):
    while time.time() < t:
        time.sleep(0.02)


def one_bar(cs, close):
    start = close - 300
    rec = {"bar_start": start,
           "close_et": dt.datetime.fromtimestamp(close, ET).strftime("%Y-%m-%d %H:%M")}
    wait_until(close + 0.5)
    rec["own_0_5"] = fold_own(tail_rows(S1M), start)
    wait_until(close + 1.0)
    rec["own_1_0"] = fold_own(tail_rows(S1M), start)
    rec["stream5_1_0"] = tail_rows(S5M, 1024).get(start)
    reads, first, first_s, val, since = [], None, None, None, None
    final, final_s = None, None
    t = close + 1.0
    while t <= close + MAX_S:
        wait_until(t)
        v = rest_read(cs, start)
        if v in ("ERR 429", "BACKOFF"):
            reads.append([round(time.time() - close, 2), v])
            break
        off = round(time.time() - close, 2)
        reads.append([off, v])
        if isinstance(v, list):
            if first is None:
                first, first_s = v, off
            if v != val:
                val, since = v, off
            elif off - since >= STABLE_S:
                final, final_s = v, off
                break
        t += STEP_S
    rec.update(rest_first=first, rest_first_s=first_s, rest_final=final,
               seconds_to_final=final_s, rest_value_since_s=since, rest_reads=reads)
    own = rec["own_1_0"]["bar"]
    rec["diff_own1_vs_final"] = diff(own, final)
    rec["diff_own05_vs_final"] = diff(rec["own_0_5"]["bar"], final)
    rec["diff_first_vs_final"] = diff(first, final)
    rec["own1_identical"] = bool(own is not None and final is not None and own == final)
    return rec


def main():
    _private_token_dir()   # before the SDK is imported: it reads the dir at import / first call
    from api import cloud_signal as cs  # data fetch only; no order path is touched
    now = dt.datetime.now(ET)
    if now.weekday() >= 5:
        return
    end = now.replace(hour=16, minute=0, second=0, microsecond=0).timestamp()
    first_close = now.replace(hour=9, minute=35, second=0, microsecond=0).timestamp()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    while True:
        close = max(first_close, (int(time.time()) // 300 + 1) * 300)
        if close > end:
            break
        try:
            rec = one_bar(cs, close)
        except Exception as e:  # noqa: BLE001 - never die mid-session
            rec = {"bar_start": close - 300, "error": repr(e)[:200]}
        with open(OUT, "a") as fh:
            fh.write(json.dumps(rec) + "\n")


if __name__ == "__main__":
    main()
