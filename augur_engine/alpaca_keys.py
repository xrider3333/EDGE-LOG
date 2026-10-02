r"""THE ONE PLACE THE ALPACA KEY IS LOOKED UP.

WHY THIS EXISTS (2026-10-02). The owner saved the key as Windows USER environment variables.
A process only sees those if it STARTED after they were set, so every session and every runner
process already running is blind to them - and restarting the Claude app and the fleet just to
pick up a variable is a poor trade. Windows keeps user variables in the registry at
HKCU\Environment, so reading that directly is the same fact from the same place, without a
restart.

Three tools had grown their own copy of this lookup (tools/import_alpaca_stocks.py,
tools/backfill_qqq_5m_alpaca.py, api/spy_daily.py) with slightly different orders. They all
delegate here now, so the order is one thing and a fix reaches all of them.

HANDLING RULES, enforced by tests in tests/test_alpaca_keys.py:
  - the value is RETURNED to the caller and never printed, logged or written anywhere;
  - `describe()` exists for diagnostics and reports only WHERE a key was found, never what it
    is - not even a prefix, because a key id is enough to identify an account;
  - the registry is read READ-ONLY, under HKCU (the user's own environment), and only for the
    two value names below;
  - every failure is swallowed into "not found": a missing key is recoverable, and an exception
    carrying a registry path into a log is not what anyone wants from a credential lookup.

LOOKUP ORDER - first hit wins:
  1. os.environ                                  (a process started after they were set)
  2. HKCU\Environment via winreg                 (the same user variables, no restart needed)
  3. C:\EdgeLog\secrets\alpaca_keys.json         {"key": ..., "secret": ...}
  4. <repo>/augur_config.json                    {"alpaca_key": ..., "alpaca_secret": ...}
  5. <repo>/tools/.alpaca_keys.json              {"key": ..., "secret": ...}

Every JSON file is read with encoding="utf-8-sig", never "utf-8": the owner's PowerShell
one-liner writes a UTF-8 BOM, and plain "utf-8" raises "Unexpected UTF-8 BOM" on it.
"""
import json
import os

ENV_KEY = "ALPACA_API_KEY"
ENV_SECRET = "ALPACA_SECRET_KEY"
REG_PATH = r"Environment"          # under HKEY_CURRENT_USER

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_SOURCES = (
    (r"C:\EdgeLog\secrets\alpaca_keys.json", "key", "secret"),
    (os.path.join(ROOT, "augur_config.json"), "alpaca_key", "alpaca_secret"),
    (os.path.join(ROOT, "tools", ".alpaca_keys.json"), "key", "secret"),
)


def _from_env():
    k, s = os.environ.get(ENV_KEY), os.environ.get(ENV_SECRET)
    return (k, s) if (k and s) else (None, None)


def _from_registry():
    """The user's own HKCU\\Environment values, read-only.

    This is what makes a key saved minutes ago usable by a process started hours ago. It reads
    exactly the two named values and nothing else, and any failure - not Windows, no such key,
    no permission - is simply "not found".
    """
    try:
        import winreg
    except Exception:
        return (None, None)                      # not Windows
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ) as h:
            out = []
            for name in (ENV_KEY, ENV_SECRET):
                try:
                    val, _kind = winreg.QueryValueEx(h, name)
                except Exception:
                    return (None, None)
                val = str(val).strip() if val is not None else ""
                if not val:
                    return (None, None)
                out.append(val)
            return (out[0], out[1])
    except Exception:
        return (None, None)


def _from_json(path, key_field, secret_field):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            cfg = json.load(fh)
        k, s = cfg.get(key_field), cfg.get(secret_field)
        return (k, s) if (k and s) else (None, None)
    except Exception:
        return (None, None)


def load_keys():
    """(key, secret), or (None, None) when no source has both. Never logs the value."""
    return _resolve()[0]


def describe():
    """Where the key came from, for a diagnostic line. NEVER the value, not even a prefix -
    a key id alone identifies the account."""
    (k, _s), where = _resolve()
    return where if k else "not found"


def _resolve():
    """((key, secret), source_description). One implementation so order cannot drift."""
    k, s = _from_env()
    if k:
        return (k, s), "the process environment"
    k, s = _from_registry()
    if k:
        return (k, s), "the Windows user environment in the registry"
    for path, kf, sf in JSON_SOURCES:
        k, s = _from_json(path, kf, sf)
        if k:
            return (k, s), os.path.basename(path)
    return (None, None), "not found"


HELP = (
    "No Alpaca key found. Either save ALPACA_API_KEY and ALPACA_SECRET_KEY as Windows user\n"
    "environment variables (this reads them straight from the registry, so nothing needs\n"
    "restarting), or put them in C:\\EdgeLog\\secrets\\alpaca_keys.json as\n"
    '  {"key": "...", "secret": "..."}'
)
