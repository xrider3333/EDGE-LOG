r"""LIVE SAFETY FLAGS -- switches the LIVE path must set for itself, never the backtest's.

WHY THIS MODULE EXISTS (2026-11-18, MANAGER ruling (A') after the VERIFIER's read).

`phantom_safe` (2026-09-26, WEBULL_GO_LIVE.md 3.7) fixes a bug that exists ONLY in an
incremental read: the ENGU-Q fill-window scan clamps `jmax = min(i + n_scan, n - 1)` and reads
a scan cut short by the data running out exactly like a scan that found nothing, so a window
that keeps growing bar by bar can book a trade a full backtest never takes. It shipped as a
kwarg defaulting to False, with api/cloud_signal.py's ENGUQ_335 leg the only caller passing
True -- which made the one leg that had already booked two ghosts safe, and left every future
leg, shadow arm and replay driver to remember a flag nobody would remember.

The obvious fix -- flip the default -- was REFUSED, and rightly. augur_engine/auto.py's
make_slice_evaluator calls `fn(O[a:b], H[a:b], L[a:b], C[a:b], ...)`, so every IS trial window,
every walk-forward fold and the lockbox is handed its own TRUNCATED array: each slice end is an
array end, the guard would fire there, and stored runs could move at every fold boundary and
flip a near-tied IS champion. A frozen crown must not change its answer.

So the default stays False in the strategy files and in the compiled walk -- a BACKTEST is
unchanged, bit for bit -- and safety is applied HERE, at the live path's own door: every live,
paper or replay caller runs an ENGU-Q-family plugin with phantom_safe=True whether its leg
declared the flag or not. A new leg cannot register itself unsafe, because the leg's params are
no longer what decides it.

Used by api/cloud_signal.py (run_leg_trades: the live signal engine, the stream decision, and
tools/live_parity_check.py's nightly replay through leg_decision_trades) and api/paper.py
(run_shadow: the NT-capture shadow arms, which append a fresh tail to the master and so read a
growing window exactly like the live leg does).

This module imports nothing of the engine at import time -- the strategy loader is a lazy
import inside the one function that needs it -- so both callers can import it freely.
"""
import inspect
import os

# The flag's own name, in one place: a rename that misses a caller must break a test, not
# silently stop forcing anything.
PHANTOM_SAFE = "phantom_safe"

# Legs already seen unsafe, so the loud line is written once per (caller, leg, strategy)
# rather than on every tick of every bar for the life of the process.
_SAID = set()


def _module_for(strategy):
    """The strategy module, or None. `strategy` is a bare filename (every CROWN_LEGS /
    SHADOW_LEGS / PAPER_LEGS entry) or an already-loaded module (a test's stub). Never
    raises -- a strategy this cannot resolve declares no safety flag, and the engine call
    right after will surface the real load failure loudly."""
    if hasattr(strategy, "run_backtest"):
        return strategy
    try:
        from augur_engine.strategies import load_strategy
        return load_strategy(strategy)
    except Exception:
        return None


def accepts_phantom_safe(strategy):
    """True iff `strategy`'s run_backtest NAMES a phantom_safe parameter -- the
    api/cloud_signal.py reflection convention: a bare **kwargs catch-all does not count,
    because a file that swallows the kwarg would be forced "safe" while running exactly as
    before, and a forcing that cannot be verified is worse than none."""
    mod = _module_for(strategy)
    if mod is None or not hasattr(mod, "run_backtest"):
        return False
    try:
        return PHANTOM_SAFE in inspect.signature(mod.run_backtest).parameters
    except (TypeError, ValueError):
        return False


def looks_engu_family(strategy):
    """True iff `strategy` looks like an ENGU-Q-family fill-window file, by NAME or by what
    the module carries. Used only to decide whether NOT accepting the flag is suspicious.

    accepts_phantom_safe fails OPEN by design -- a file that does not name the kwarg is left
    alone, because forcing a file that swallows it would claim a safety it does not have. The
    VERIFIER's case (2026-11-18) is the one where that silence is wrong: a wrapper written
    WITHOUT functools.wraps, exposing only *args/**kw, hides a real ENGU-Q run behind a
    signature this module cannot read, and the live path would then run the pre-fix fill scan
    without a word. So the fail-open stays, and this makes it NOISY instead of silent.
    """
    name = getattr(strategy, "__name__", None) or str(strategy)
    if os.path.basename(str(name)).upper().startswith("ENGUQ"):
        return True
    mod = _module_for(strategy)
    if mod is None:
        return False
    if hasattr(mod, "_N_SCAN"):
        return True
    # the compiled walk is the other tell: a file that calls it runs the same fill scan
    try:
        src = inspect.getsource(mod)
    except Exception:
        return False
    return "engu_walk" in src


def force_phantom_safe(strategy, params, *, caller, leg_key=None, log=print):
    """The params dict a LIVE/paper/replay caller must hand the engine.

    Returns `params` unchanged (the same object) when the strategy does not take the flag,
    so no non-ENGU-Q leg's call is touched. Otherwise returns a COPY with
    phantom_safe=True -- always, whatever the leg declared -- and, when the leg had not
    declared True itself, writes ONE loud line per (caller, leg, strategy) saying the live
    path refused to run it with the pre-fix fill scan. That line is the alarm MANAGER asked
    for: it means a leg was registered without the flag and the live path corrected it, so
    the leg's own declaration should be fixed rather than left to this net.
    """
    if not accepts_phantom_safe(strategy):
        # Fail OPEN, but never quietly for a file that LOOKS like the family this guards.
        if looks_engu_family(strategy):
            name = getattr(strategy, "__name__", None) or str(strategy)
            key = ("unreadable", str(caller), str(leg_key), name)
            if key not in _SAID:
                _SAID.add(key)
                log("[live-safety] CANNOT FORCE %s on %s (%s): it looks like an ENGU-Q "
                    "fill-window file but its run_backtest does not NAME the kwarg, so this "
                    "live path may be running the pre-fix fill scan. A wrapper without "
                    "functools.wraps hides the signature -- fix the file or the wrapper."
                    % (PHANTOM_SAFE, name, leg_key or caller))
        return params
    declared = (params or {}).get(PHANTOM_SAFE)
    if declared is not True:
        name = getattr(strategy, "__name__", None) or str(strategy)
        key = (str(caller), str(leg_key), name)
        if key not in _SAID:
            _SAID.add(key)
            log("[live-safety] REFUSED to run %s on the live path with %s=%r: the "
                "incremental fill scan would book phantom entries (WEBULL_GO_LIVE.md 3.7). "
                "Forced True for %s -- fix the leg's own params so it declares its safety."
                % (name, PHANTOM_SAFE, declared, leg_key or caller))
    out = dict(params or {})
    out[PHANTOM_SAFE] = True
    return out


def _reset_said_for_tests():
    """Clear the once-per-leg log memo. Tests only."""
    _SAID.clear()
