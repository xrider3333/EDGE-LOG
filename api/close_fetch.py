"""CLOSE-ANCHORED FETCH (owner via MANAGER 2026-11-20, "closefetch").

cloud_signal_thread used to fetch REST bars on a free-running 30 s clock, so the
just-closed 5m bar reached the cache anywhere from ~1 s to ~30 s after its close (orders
went out ~8 s after the close on average). A read-only probe showed the Webull REST
reply already holds the just-closed 5m bar, final, at close+0.77 s.

Two pieces, both pure and testable without a network:

CloseFetchClock -- decides do_fetch for each loop tick. From close+FAST_START_S (1 s)
    it allows one REST fetch every FAST_STEP_S (1 s) until the just-closed 5m slot is
    in the cache (merged), then the classic 30 s clock again. Hard stops: close+
    FAST_STOP_S (20 s), FAST_MAX_CALLS_PER_BAR calls, any fetch error / 429 in the
    window (backed off for that bar). In all of those the classic 30 s clock carries on,
    so the bar is still picked up by the normal path -- never skipped. Only bars inside
    the real session (api.market_calendar: a half day ends at 13:00, its last bar is the
    12:55 slot closing 13:00) get a fast window; outside it there is no fast fetch.
    One summary line per bar: slot, calls, seconds-to-merge (or why it fell back).

ProvisionalBarGuard -- the gate stays "bar is FINAL" (the existing settled-by cutoff in
    fetch_and_merge); this adds: a NEW newest bar is merged only once two reads at least
    STABLE_S (default 5 s, env EDGELOG_BAR_STABLE_S) apart are identical on O, H, L, C AND
    volume. The first read holds it back (it is not in the cache, so no leg can act on
    it). Any change - a volume-only change included - logs 'provisional bar changed' and
    restarts the STABLE_S wait from that read. (MANAGER 11-20: the 11-20 finality probe saw
    2 of 56 5m bars change after a 0.8 s first read; two reads 1 s apart were not enough.)
    Inside the fast window that means a send at about close+6 s; the 30 s fallback clock
    reads 30 s apart, so its second identical read always clears the wait.

Neither piece reads the stream bar; bar_close_from_stream is untouched (stays OFF).
"""
import datetime as _dt
import os as _os
import threading as _threading
import time as _time

BAR_SECONDS = 300
FAST_START_S = 1.0
FAST_STEP_S = 1.0
FAST_STOP_S = 20.0
FAST_MAX_CALLS_PER_BAR = 20
STABLE_S = 5.0                  # MANAGER 11-20: two identical reads >= 5 s apart
SLOW_STEP_S = 30.0

_OHLCV = ("open", "high", "low", "close", "volume")


def _slot_bounds(now_et):
    """(slot_open_et, close_et) of the 5m bar whose close is the latest 5m boundary <= now."""
    floor = now_et.replace(second=0, microsecond=0)
    floor = floor - _dt.timedelta(minutes=floor.minute % 5)
    return floor - _dt.timedelta(seconds=BAR_SECONDS), floor


def _session_window(day, rth_open, calendar):
    """(open_time, close_time) of `day`'s session or None. Never raises."""
    try:
        if not calendar.is_session(day):
            return None
        hh, mm = (int(x) for x in str(calendar.session_close_et(day)).split(":")[:2])
        return rth_open, _dt.time(hh, mm)
    except Exception:
        return None


class CloseFetchClock:
    def __init__(self, rth_open, calendar, log=print, slow_step_s=SLOW_STEP_S):
        self.rth_open = rth_open
        self.calendar = calendar
        self.log = log
        self.slow_step_s = slow_step_s
        self.last_fetch_wall = 0.0
        self.last_fast_wall = 0.0
        self.slot = None            # epoch of the bar slot (bar OPEN time) being chased
        self.slot_close_wall = None
        self.calls = 0
        self.state = None           # None (chasing) | "merged" | "fallback:<why>"
        self.day = None
        self.day_calls = 0

    # -- per tick -------------------------------------------------------------------
    def fast_slot(self, now_et):
        """(slot_epoch, close_epoch) when `now_et` is inside a just-closed in-session bar's
        fast window (close+FAST_START_S .. close+FAST_STOP_S), else None."""
        slot_open, close = _slot_bounds(now_et)
        win = _session_window(slot_open.date(), self.rth_open, self.calendar)
        if win is None:
            return None
        if slot_open.time() < win[0] or close.time() > win[1] or close.date() != slot_open.date():
            return None
        elapsed = (now_et - close).total_seconds()
        if elapsed < FAST_START_S or elapsed > FAST_STOP_S:
            return None
        return int(slot_open.timestamp()), int(close.timestamp())

    def sleep_cap(self, now_et):
        """Longest sleep that cannot step over a fast window: FAST_STEP_S while inside one
        and still chasing, else the seconds to the next 5m close + FAST_START_S."""
        fast = self.fast_slot(now_et)
        if fast is not None and not (self.slot == fast[0] and self.state is not None):
            return FAST_STEP_S
        _, close = _slot_bounds(now_et)
        nxt = close + _dt.timedelta(seconds=FAST_START_S)
        if now_et >= nxt:
            nxt = nxt + _dt.timedelta(seconds=BAR_SECONDS)
        return max(0.05, (nxt - now_et).total_seconds())

    def decide(self, now_et, now_wall, merged_newest=None):
        """True when this tick should fetch. `merged_newest` = newest 5m bar epoch in the
        cache (None if unknown). Records the fetch time itself."""
        if self.day != now_et.date():
            self.day, self.day_calls = now_et.date(), 0
        fast = self.fast_slot(now_et)
        if fast is not None and fast[0] != self.slot:
            self._summarise()
            self.slot, self.calls, self.state = fast[0], 0, None
            self.slot_close_wall = now_wall - (now_et.timestamp() - fast[1])
        if (self.slot is not None and self.state is None and merged_newest is not None
                and merged_newest >= self.slot):
            self.state = "merged"
            self._summarise()
        if fast is None and self.slot is not None and self.state is None:
            self.state = "fallback:window closed (close+%ds)" % int(FAST_STOP_S)
            self._summarise()
        if (fast is not None and self.state is None and self.calls >= FAST_MAX_CALLS_PER_BAR):
            self.state = "fallback:call cap %d" % FAST_MAX_CALLS_PER_BAR
            self._summarise()
        do_fast = (fast is not None and self.state is None
                   and (now_wall - self.last_fast_wall) >= FAST_STEP_S)
        do_fetch = do_fast or (now_wall - self.last_fetch_wall) >= self.slow_step_s
        if do_fetch:
            self.last_fetch_wall = now_wall
            if do_fast:
                self.last_fast_wall = now_wall
                self.calls += 1
                self.day_calls += 1
        return do_fetch

    def after_fetch(self, ok, merged_newest=None, now_wall=None):
        """Report a fetch's outcome. A failed fetch (error, 429, yfinance fallback) in the
        fast window backs off to the 30 s clock for this bar."""
        if self.slot is None or self.state is not None:
            return
        if not ok:
            self.state = "fallback:fetch error"
            self._summarise()
            return
        if merged_newest is not None and merged_newest >= self.slot:
            self.state = "merged"
            self._summarise(now_wall)

    def _summarise(self, now_wall=None):
        if self.slot is None or getattr(self, "_said", None) == self.slot:
            return
        if self.state is None:
            self.state = "fallback:superseded"
        self._said = self.slot
        took = ""
        if self.state == "merged" and now_wall is not None and self.slot_close_wall is not None:
            took = " in %.1fs after close" % (now_wall - self.slot_close_wall)
        elif self.state == "merged":
            took = " (merged)"
        else:
            took = " -- " + self.state.split(":", 1)[1] + "; 30s clock picks it up"
        stamp = _dt.datetime.fromtimestamp(self.slot, tz=_dt.timezone.utc).strftime("%H:%MZ")
        try:
            self.log("[cloud-signal] CLOSEFETCH bar %s (%d): %d fast call(s)%s; %d today"
                     % (stamp, self.slot, self.calls, took, self.day_calls))
        except Exception:
            pass


def stable_s_from_env(default=STABLE_S):
    """EDGELOG_BAR_STABLE_S (seconds, >= 1); anything unreadable -> default."""
    try:
        v = float(_os.environ.get("EDGELOG_BAR_STABLE_S", "") or default)
        return v if v >= 1.0 else default
    except (TypeError, ValueError):
        return default


class ProvisionalBarGuard:
    """Holds a new newest bar back until it has read identical (OHLC + volume) across at
    least `stable_s` seconds (see module docstring)."""

    def __init__(self, stable_s=None, clock=None):
        self.held = {}              # timeframe -> (epoch, ohlcv tuple, wall time first read so)
        self.lock = _threading.Lock()
        self.stable_s = float(stable_s if stable_s is not None else stable_s_from_env())
        self.clock = clock or _time.monotonic

    @staticmethod
    def _row(fresh, i):
        return tuple(float(fresh[c].iloc[i]) for c in _OHLCV)

    def filter(self, timeframe, fresh, old_newest, log=print):
        """Return `fresh` with its newest bar removed unless that bar is already in the
        cache (<= old_newest) or has read identical for at least stable_s seconds."""
        if fresh is None or not len(fresh):
            return fresh
        i = int(fresh["time"].values.argmax())
        t = int(fresh["time"].iloc[i])
        if old_newest is not None and t <= old_newest:
            with self.lock:
                self.held.pop(timeframe, None)
            return fresh
        row = self._row(fresh, i)
        now = self.clock()
        with self.lock:
            prev = self.held.get(timeframe)
            if prev is not None and prev[0] == t and prev[1] == row:
                if now - prev[2] >= self.stable_s:
                    self.held.pop(timeframe, None)
                    return fresh                              # stable >= stable_s: final
                return fresh[fresh["time"] != t].reset_index(drop=True)
            if prev is not None and prev[0] == t:
                try:
                    log(f"[cloud-signal] provisional bar changed: {timeframe} {t} "
                        f"{prev[1]} -> {row}; waiting {self.stable_s:g}s of identical reads")
                except Exception:
                    pass
            self.held[timeframe] = (t, row, now)
        return fresh[fresh["time"] != t].reset_index(drop=True)
