"""OWN-BAR FAST PATH (owner order 2026-11-21, PAPER only).

The QQQ 5m legs (ORB_R6, NOISE_382) decide from OUR OWN 5m bar, folded from the live
Webull trade stream's five 1m bars at the 5m boundary, instead of waiting ~7 s for the REST
bar to read final (api/close_fetch.py ProvisionalBarGuard). Target: bar end -> order sent
< 300 ms.

WHERE THINGS RUN (two services stay separate -- the engine owns state.json/signals.csv
under its one-engine-per-host lock, the executor owns the stream and the order adapter):
  * edgelog-qqq-exec (api/webull_stream.py WebullBarStreamer._ownbar_loop): wakes at each
    5m boundary + GRACE_S, folds the 1m bars (fold_own_bar), writes
    ohlc_stream/QQQ_5m_ownbar.json and sends one UDP datagram to the engine (ENGINE_PORT).
  * edgelog-cloud-signal (cloud_signal_thread): sleeps on that UDP socket instead of
    time.sleep, so it wakes within ~1 ms; api/cloud_signal_stream.py runs the SAME engine
    path step() uses on the own bar, commits rows to signals.csv per leg, and sends one UDP
    datagram per committed leg to the executor (EXEC_PORT).
  * edgelog-qqq-exec's _wait_next_tick sleeps on its own UDP socket in the post-close
    window, so it reads signals.csv and sends at once.
  UDP on 127.0.0.1 is fire-and-forget: a lost datagram only costs the old 0.25 s polls.

HARD GATES (VERIFIER 11-21, binding): the own bar is used ONLY when the stream is
connected, its last update is <= STALE_S (2.0 s) old at the fold, the stream connected
before the bar opened, and all five 1m bars exist with real prints and are closed (the
clock is past the boundary + GRACE_S). Anything else -> that bar is decided by the REST
+ guard path exactly as today, logged, and phone-alerted once per episode.

Switch: EDGELOG_OWNBAR_DECIDE=1 in BOTH services' environment (default OFF). Refused
(never enabled) while the Webull order config requests LIVE -- PAPER only.
"""
import json
import math
import os
import socket
import threading
import time

BAR_SECONDS = 300
MINUTE = 60


def _env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


def enabled():
    """The config flag. Default OFF."""
    return str(os.environ.get("EDGELOG_OWNBAR_DECIDE", "0")).strip().lower() in ("1", "true", "on", "yes")


def stale_s():
    return _env_float("EDGELOG_OWNBAR_STALE_S", 2.0)


def grace_s():
    return _env_float("EDGELOG_OWNBAR_GRACE_S", 0.05)


def engine_port():
    return int(_env_float("EDGELOG_OWNBAR_ENGINE_PORT", 47615))


def exec_port():
    return int(_env_float("EDGELOG_OWNBAR_EXEC_PORT", 47616))


def warm_lead_s():
    return _env_float("EDGELOG_OWNBAR_WARM_S", 3.0)


def live_refusal(load_config=None):
    """None when the Webull order config requests PAPER; else the reason the fast path
    refuses to switch on (LIVE, OFF, unreadable). Never raises."""
    try:
        if load_config is None:
            from api import webull_orders
            load_config = webull_orders.load_config
        mode = str((load_config() or {}).get("mode") or "").upper()
    except Exception as e:
        return f"broker config unreadable ({type(e).__name__})"
    if mode == "LIVE":
        return "broker mode is LIVE -- own-bar decisions are PAPER only"
    if mode != "PAPER":
        return f"broker mode is {mode or 'unset'}, not PAPER"
    return None


def active(load_config=None):
    """(on, reason). on only when the flag is set AND the broker is PAPER."""
    if not enabled():
        return False, "EDGELOG_OWNBAR_DECIDE not set"
    why = live_refusal(load_config)
    if why:
        return False, why
    return True, "ok"


# -- the fold ---------------------------------------------------------------------------
def _minute_ok(m):
    try:
        if float(m.get("volume")) <= 0:
            return False
        return all(math.isfinite(float(m.get(k))) for k in ("open", "high", "low", "close"))
    except (TypeError, ValueError, AttributeError):
        return False


def fold_own_bar(minutes, bar_start, now, last_update_epoch, connected, connect_epoch,
                 stale_after=None, grace=None):
    """(bar, reason). `minutes` = {1m bar start epoch: {open,high,low,close,volume}}.
    bar is the folded 5m dict (time = bar_start) or None with the reason it may not be
    used (then the REST path decides). Pure."""
    stale_after = stale_s() if stale_after is None else stale_after
    grace = grace_s() if grace is None else grace
    close = bar_start + BAR_SECONDS
    if not connected:
        return None, "stream not connected"
    if last_update_epoch is None:
        return None, "no stream update seen"
    age = now - last_update_epoch
    if age > stale_after:
        return None, f"stream stale: last update {age:.2f}s old (limit {stale_after:g}s)"
    if connect_epoch is None or connect_epoch > bar_start:
        return None, "stream (re)connected inside this bar -- partial"
    if now < close + grace:
        return None, "last 1m bar not closed yet"
    rows = []
    for k in range(5):
        m = minutes.get(bar_start + MINUTE * k)
        if m is None:
            return None, f"missing minute {k + 1}/5"
        if not _minute_ok(m):
            return None, f"minute {k + 1}/5 has no real prints"
        rows.append(m)
    bar = {"time": int(bar_start), "open": float(rows[0]["open"]),
           "high": max(float(r["high"]) for r in rows),
           "low": min(float(r["low"]) for r in rows),
           "close": float(rows[-1]["close"]),
           "volume": float(sum(float(r["volume"]) for r in rows))}
    return bar, "ok"


def next_boundary(now):
    return (math.floor(now / BAR_SECONDS) + 1) * BAR_SECONDS


# -- hand-off file ------------------------------------------------------------------------
def handoff_path(home):
    return os.path.join(home, "ohlc_stream", "QQQ_5m_ownbar.json")


def write_handoff(home, payload):
    path = handoff_path(home)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.replace(tmp, path)


def read_handoff(home):
    try:
        with open(handoff_path(home), encoding="utf-8") as f:
            p = json.load(f)
        return p if isinstance(p, dict) else None
    except Exception:
        return None


# -- UDP wake -----------------------------------------------------------------------------
def wake(port, msg=b"bar"):
    """Fire-and-forget datagram to 127.0.0.1:port. Never raises."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.sendto(msg, ("127.0.0.1", int(port)))
        finally:
            s.close()
    except Exception:
        pass


class WakeSocket:
    """Bound UDP listener. wait(timeout) -> datagram bytes or None. A bind failure leaves
    it inert (wait() just sleeps), so a port clash costs latency, never a crash."""

    def __init__(self, port):
        self.sock = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind(("127.0.0.1", int(port)))
            self.sock = s
        except Exception:
            self.sock = None

    def wait(self, timeout):
        timeout = max(0.0, float(timeout))
        if self.sock is None:
            time.sleep(timeout)
            return None
        try:
            self.sock.settimeout(timeout if timeout > 0 else 0.0001)
            data, _ = self.sock.recvfrom(256)
            return data
        except (socket.timeout, BlockingIOError):
            return None
        except Exception:
            time.sleep(timeout)
            return None

    def close(self):
        try:
            if self.sock is not None:
                self.sock.close()
        except Exception:
            pass
        self.sock = None


_SOCKS = {}
_SOCKS_LOCK = threading.Lock()


def shared_socket(port):
    with _SOCKS_LOCK:
        s = _SOCKS.get(port)
        if s is None:
            s = _SOCKS[port] = WakeSocket(port)
        return s


# -- alert once per episode ---------------------------------------------------------------
class EpisodeAlert:
    """fail() pushes only on the first failure of an episode; ok() ends the episode."""

    def __init__(self):
        self.in_episode = {}

    def fail(self, key, msg, push):
        if self.in_episode.get(key):
            return False
        self.in_episode[key] = True
        try:
            push(msg)
        except Exception:
            pass
        return True

    def ok(self, key):
        self.in_episode[key] = False


# -- audit jsonl --------------------------------------------------------------------------
def audit_path(home):
    return os.path.join(home, "logs", "ownbar_audit.jsonl")


def append_audit(home, rec):
    try:
        path = audit_path(home)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except Exception:
        pass


# -- latency summary ----------------------------------------------------------------------
def pct(values, q):
    v = sorted(x for x in values if x is not None and math.isfinite(x))
    if not v:
        return None
    i = min(len(v) - 1, max(0, int(math.ceil(q / 100.0 * len(v))) - 1))
    return v[i]


def _ms(a, b):
    try:
        if a in (None, "") or b in (None, ""):
            return None
        return (float(b) - float(a)) * 1000.0
    except (TypeError, ValueError):
        return None


def latency_line(rows):
    """One phone line from broker_orders rows carrying bar_end_ts/send_ts/ack_ts/fill_ts
    (epoch seconds). '' when no row has them."""
    pairs = (("bar->send", "bar_end_ts", "send_ts"), ("send->ack", "send_ts", "ack_ts"),
             ("send->fill", "send_ts", "fill_ts"))
    parts = []
    for name, a, b in pairs:
        vals = [_ms(r.get(a), r.get(b)) for r in rows]
        vals = [x for x in vals if x is not None]
        if vals:
            parts.append(f"{name} p50 {pct(vals, 50):.0f} / p90 {pct(vals, 90):.0f} ms")
    if not parts:
        return ""
    return "latency " + "; ".join(parts)
