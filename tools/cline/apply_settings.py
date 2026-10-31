#!/usr/bin/env python3
"""apply_settings.py -- write the checked-in Cline template (tools/cline/settings_template/) into
~/.cline so the owner's Cline setup is versioned and one command away (board C26, scope P7/P6).

What it touches (and nothing else):
  ~/.cline/data/settings/cline_mcp_settings.json  <- mcpServers.edgelog replaced (other servers kept)
  ~/.cline/data/settings/models.json              <- providers.openai-compatible.models replaced by the 5 names
  ~/.cline/data/settings/providers.json           <- only provider/baseUrl/model under openai-compatible.settings;
                                                     the API key is kept as it is and redacted in the printed diff
  ~/.cline/data/globalState.json                  <- the keys in global_state.json merged (auto-approve =
                                                     read-only + safe commands + MCP, checkpoints on, router URL)
  Documents\\Cline\\Rules\\edgelog.md              <- NOT touched; the repo root .clinerules is the versioned copy

Default is --dry-run: prints a unified diff per file, writes nothing. --apply writes each file after a
<file>.bak-YYYYMMDD-HHMMSS copy. Run --apply only with Cline CLOSED (it rewrites globalState.json on exit).
Stdlib only. Never starts a server or a model.
"""
from __future__ import annotations

import argparse
import copy
import difflib
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "settings_template")
CLINE = os.environ.get("CLINE_DATA") or os.path.join(os.path.expanduser("~"), ".cline", "data")
SETTINGS = os.path.join(CLINE, "settings")
SECRET_RE = ("apikey", "api_key", "token", "secret", "password")


def _load(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _tmpl(name):
    d = _load(os.path.join(TEMPLATE, name))
    d.pop("_comment", None)
    return d


def _redact(obj):
    """Copy with every secret-looking string value replaced, for the printed diff only."""
    if isinstance(obj, dict):
        return {k: ("***" if any(s in k.lower() for s in SECRET_RE) and isinstance(v, str) else _redact(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


def plan():
    """Return [(path, current_dict, new_dict)] - pure, no writes."""
    out = []
    # 1. MCP server entry
    p = os.path.join(SETTINGS, "cline_mcp_settings.json")
    cur = _load(p)
    new = copy.deepcopy(cur)
    new.setdefault("mcpServers", {})["edgelog"] = _tmpl("cline_mcp_settings.json")["mcpServers"]["edgelog"]
    out.append((p, cur, new))
    # 2. the five model names
    p = os.path.join(SETTINGS, "models.json")
    cur = _load(p)
    new = copy.deepcopy(cur)
    new.setdefault("version", 1)
    new.setdefault("providers", {}).setdefault("openai-compatible", {})["models"] = \
        _tmpl("models.json")["providers"]["openai-compatible"]["models"]
    out.append((p, cur, new))
    # 3. router URL (key left exactly as it is)
    p = os.path.join(SETTINGS, "providers.json")
    cur = _load(p)
    new = copy.deepcopy(cur)
    want = _tmpl("providers.json")["providers"]["openai-compatible"]["settings"]
    st = new.setdefault("providers", {}).setdefault("openai-compatible", {}).setdefault("settings", {})
    for k in ("provider", "baseUrl", "model"):
        st[k] = want[k]
    out.append((p, cur, new))
    # 4. globalState: merge listed keys only
    p = os.path.join(CLINE, "globalState.json")
    cur = _load(p)
    new = copy.deepcopy(cur)
    new.update(_tmpl("global_state.json"))
    out.append((p, cur, new))
    return out


def diff_text(path, cur, new):
    a = json.dumps(_redact(cur), indent=2, sort_keys=True).splitlines()
    b = json.dumps(_redact(new), indent=2, sort_keys=True).splitlines()
    rel = os.path.relpath(path, os.path.dirname(CLINE))
    lines = list(difflib.unified_diff(a, b, "a/" + rel, "b/" + rel, lineterm="", n=2))
    return "\n".join(lines) if lines else "%s: no change" % rel


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="print diffs only (default)")
    g.add_argument("--apply", action="store_true", help="write the files after a timestamped backup")
    a = ap.parse_args(argv)
    if not os.path.isdir(CLINE):
        print("no Cline data folder at %s" % CLINE)
        return 2
    stamp = time.strftime("%Y%m%d-%H%M%S")
    changed = 0
    for path, cur, new in plan():
        print(diff_text(path, cur, new))
        print()
        if cur == new:
            continue
        changed += 1
        if a.apply:
            if os.path.exists(path):
                shutil.copy2(path, "%s.bak-%s" % (path, stamp))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(new, fh, indent=2)
                fh.write("\n")
            os.replace(tmp, path)
            print("WROTE %s (backup .bak-%s)" % (path, stamp))
    mode = "APPLIED" if a.apply else "DRY RUN"
    print("%s: %d file(s) %s. Restart Cline (VS Code) afterwards."
          % (mode, changed, "written" if a.apply else "would change"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
