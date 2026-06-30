"""Library file-op command handlers for the EDGELOG web Library tab (Commit B).

The web app writes a command doc to users/{uid}/commands/{id}; this runner — on
THIS PC, behind the same uid allowlist as backtest jobs — executes the file op
here and writes the result back. Actions:

  • get_src    download a strategy's .py or .pine source
  • delete     remove a strategy's .py (+ its .pine, + its Library #)
  • add        save a new strategy .py (validated against the plugin contract first)
  • make_pine  generate a .pine for a strategy that lacks one, via the keyless/local
               AI (claude-cli or ollama), falling back to a deterministic scaffold

SAFETY: every filename is basename-sanitised and confined to augur_strategies/ and
pine/ — a web client can never escape those directories or write arbitrary paths.
New code is compile+contract+smoke-tested (validate_strategy_code) before it lands.
"""
import os
import re
import json
import time
import gzip
import base64
import subprocess
from collections import deque

import augur_engine as ae  # noqa: F401  (ensures package import side-effects/paths)
import sqlite3
from augur_engine.paths import STRAT_DIR, PINE_DIR, CONFIG, DB_PATH, UPLOADS
from augur_engine.strategies import _pine_path, load_strategy
from augur_engine.ai import validate_strategy_code, OLLAMA_URL, DEFAULT_OLLAMA_MODEL


def _safe_py(name):
    """Sanitise to a bare ABC.py basename under augur_strategies/. Rejects traversal
    and private/underscore names."""
    base = os.path.basename(str(name or "")).strip()
    if not base.endswith(".py"):
        base += ".py"
    if not base or base == ".py" or base.startswith("_") or "/" in base or "\\" in base:
        raise ValueError(f"unsafe filename: {name!r}")
    return base


def _read(path):
    return open(path, encoding="utf-8").read()


def _tag_pine(content, src):
    """Stamp a provenance marker AUGUR can read back (engine._pine_via). Appended at
    the END so it never displaces Pine's mandatory '//@version' first line. Replaces any
    prior marker so re-reviews don't stack up."""
    body = re.sub(r'(?mi)^//\s*AUGUR-PINE:.*$\n?', '', content).rstrip()
    return body + f"\n\n// AUGUR-PINE: {src}  ({time.strftime('%Y-%m-%d')})\n"


def _provider():
    """AI provider for Pine generation. Default OLLAMA (local qwen — free, zero
    tokens). claude-cli is sharper but spends the user's Claude credits, so it's
    opt-in (chosen in web Settings / passed in the command payload)."""
    try:
        cfg = json.load(open(CONFIG, encoding="utf-8"))
        return (cfg.get("ai_provider") or cfg.get("provider") or "ollama")
    except Exception:
        return "ollama"


# ── handlers ────────────────────────────────────────────────────────────────
def cmd_get_src(p):
    base = _safe_py(p.get("file"))
    if (p.get("kind") or "py") == "pine":
        pp = _pine_path(base)
        if not os.path.exists(pp):
            return {"ok": False, "error": f"no .pine for {base}"}
        return {"ok": True, "filename": os.path.basename(pp), "content": _read(pp)}
    py = os.path.join(STRAT_DIR, base)
    if not os.path.exists(py):
        return {"ok": False, "error": f"not found: {base}"}
    return {"ok": True, "filename": base, "content": _read(py)}


def cmd_delete(p):
    base = _safe_py(p.get("file"))
    removed = []
    py = os.path.join(STRAT_DIR, base)
    if os.path.exists(py):
        os.remove(py); removed.append(base)
    pp = _pine_path(base)
    if os.path.exists(pp):
        os.remove(pp); removed.append(os.path.basename(pp))
    try:  # drop its Library number so the slot is freed
        cfg = json.load(open(CONFIG, encoding="utf-8"))
        nums = cfg.get("strat_nums", {})
        if base in nums:
            nums.pop(base); cfg["strat_nums"] = nums
            json.dump(cfg, open(CONFIG, "w", encoding="utf-8"), indent=2)
    except Exception:
        pass
    if not removed:
        return {"ok": False, "error": f"nothing to delete for {base}"}
    return {"ok": True, "removed": removed}


def cmd_add(p):
    base = _safe_py(p.get("name") or p.get("file"))
    content = p.get("content") or ""
    if not content.strip():
        return {"ok": False, "error": "empty content"}
    py = os.path.join(STRAT_DIR, base)
    if os.path.exists(py):
        return {"ok": False, "error": f"{base} already exists"}
    mod, err = validate_strategy_code(content)   # compile + contract + smoke test
    if err:
        return {"ok": False, "error": f"validation failed: {err}"}
    open(py, "w", encoding="utf-8").write(content)
    return {"ok": True, "added": base, "name": getattr(mod, "STRATEGY_NAME", base)}


_PINE_SYS = (
    "You convert a Python trading-strategy plugin into a TradingView Pine Script v5 "
    "strategy. Match the entry/exit logic, the parameters (as Pine inputs), and the "
    "SHARES*(EXIT-ENTRY)+FEE PnL convention as closely as the Python allows. Output "
    "ONLY raw Pine v5 code — no prose, no markdown fences.")


def _llm_raw(provider, system, user):
    """Free-text (NOT json-forced) keyless LLM call. Returns (text, error).
    ollama = local qwen (free); claude-cli = `claude` CLI (uses Claude credits)."""
    prov = (provider or "ollama").lower()
    try:
        if prov in ("claude-cli", "claude_cli", "cli"):
            r = subprocess.run(["claude", "-p", system + "\n\n" + user],
                               capture_output=True, text=True, timeout=600)
            if r.returncode != 0:
                return "", f"claude-cli: {(r.stderr or '')[:200]}"
            return r.stdout, None
        if prov == "ollama":
            import requests
            r = requests.post(OLLAMA_URL, timeout=600, json={
                "model": DEFAULT_OLLAMA_MODEL,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "stream": False, "options": {"temperature": 0.3}})
            if r.status_code != 200:
                return "", f"ollama {r.status_code}: {r.text[:160]}"
            return r.json().get("message", {}).get("content", ""), None
        return "", f"unknown provider {prov}"
    except FileNotFoundError:
        return "", f"{prov} not installed/on PATH"
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"


def _pine_via_llm(provider, src):
    """Pine generation. Returns (pine_text, error)."""
    return _llm_raw(provider, _PINE_SYS, "Convert this strategy to Pine v5:\n\n" + src)


_REVIEW_SYS = (
    "You are reviewing a TradingView Pine v5 strategy auto-translated from a Python "
    "backtest strategy. Verify the Pine faithfully reproduces the Python's entry/exit "
    "logic, parameters, and the SHARES*(EXIT-ENTRY)+FEE PnL convention. First output a "
    "SHORT bullet review of any discrepancies or risks. Then a line containing exactly "
    "---PINE--- on its own. Then the corrected full Pine v5 script (no fences). If it is "
    "already faithful, say so and still emit the (unchanged) script after the marker.")


def cmd_review_pine(p):
    base = _safe_py(p.get("file"))
    py = os.path.join(STRAT_DIR, base)
    pp = _pine_path(base)
    if not os.path.exists(py):
        return {"ok": False, "error": f"not found: {base}"}
    if not os.path.exists(pp):
        return {"ok": False, "error": f"no .pine to review for {base} — make one first"}
    prov = p.get("provider") or "claude-cli"
    text, err = _llm_raw(prov, _REVIEW_SYS,
                         "PYTHON:\n" + _read(py) + "\n\nPINE:\n" + _read(pp))
    if err or not (text or "").strip():
        return {"ok": False, "error": f"review failed: {err or 'no output'}"}
    parts = text.split("---PINE---")
    review = parts[0].strip()
    proposed = ""
    if len(parts) > 1:
        proposed = parts[1].replace("```pine", "").replace("```", "").strip()
    has = "strategy(" in proposed
    return {"ok": True, "via": prov, "review": review[:6000],
            "proposed": proposed if has else "",
            "changed": has and (proposed.strip() != _read(pp).strip())}


def cmd_write_pine(p):
    """Apply a (reviewed) Pine script to pine/<base>.pine."""
    base = _safe_py(p.get("file"))
    content = (p.get("content") or "").strip()
    if "strategy(" not in content:
        return {"ok": False, "error": "content doesn't look like a Pine strategy"}
    pp = _pine_path(base)
    os.makedirs(PINE_DIR, exist_ok=True)
    open(pp, "w", encoding="utf-8").write(_tag_pine(content, "claude-review"))
    return {"ok": True, "made": os.path.basename(pp), "via": "applied review"}


def _pine_scaffold(mod, base):
    """Deterministic fallback: a compilable Pine v5 skeleton exposing the strategy's
    params as inputs, with the entry/exit logic left as a clearly-marked TODO."""
    name = getattr(mod, "STRATEGY_NAME", base)
    params = getattr(mod, "DEFAULT_PARAMS", {}) or {}
    lines = [f'//@version=5', f'strategy("{name} (scaffold)", overlay=true, '
             'default_qty_type=strategy.fixed, default_qty_value=1)', '']
    for k, v in params.items():
        if not isinstance(v, dict):
            continue
        d = v.get("default"); t = v.get("type", "float")
        if t == "bool":
            lines.append(f'{k} = input.bool({str(bool(d)).lower()}, "{v.get("label", k)}")')
        elif t == "int":
            lines.append(f'{k} = input.int({int(d) if d is not None else 0}, "{v.get("label", k)}")')
        elif t == "str":
            lines.append(f'{k} = input.string("{d}", "{v.get("label", k)}")')
        else:
            lines.append(f'{k} = input.float({float(d) if d is not None else 0.0}, "{v.get("label", k)}")')
    lines += ['', '// TODO: port entry/exit logic from the Python run_backtest().',
              '// This scaffold only exposes the parameters as inputs.',
              '// longCond = ...', '// if longCond', '//     strategy.entry("L", strategy.long)']
    return "\n".join(lines)


def cmd_make_pine(p):
    base = _safe_py(p.get("file"))
    py = os.path.join(STRAT_DIR, base)
    if not os.path.exists(py):
        return {"ok": False, "error": f"not found: {base}"}
    pp = _pine_path(base)
    if os.path.exists(pp) and not p.get("overwrite"):
        return {"ok": False, "error": f"{os.path.basename(pp)} already exists (pass overwrite)"}
    try:
        mod = load_strategy(base)
    except Exception as e:
        return {"ok": False, "error": f"load failed: {e}"}
    # 1) module-provided canonical Pine
    canon = getattr(mod, "_PINE", None)
    if canon and str(canon).strip():
        out = _tag_pine(str(canon), "bundled")
        os.makedirs(PINE_DIR, exist_ok=True)
        open(pp, "w", encoding="utf-8").write(out)
        return {"ok": True, "made": os.path.basename(pp), "via": "module _PINE",
                "content": out}
    # 2) keyless/local AI conversion
    prov = p.get("provider") or _provider()
    src_lbl = "qwen" if prov == "ollama" else ("claude" if prov in ("claude-cli", "claude_cli", "cli") else prov)
    pine, err = _pine_via_llm(prov, _read(py))
    pine = (pine or "").replace("```pine", "").replace("```", "").strip()
    if pine and "strategy(" in pine:
        out = _tag_pine(pine, src_lbl)
        os.makedirs(PINE_DIR, exist_ok=True)
        open(pp, "w", encoding="utf-8").write(out)
        return {"ok": True, "made": os.path.basename(pp), "via": prov, "content": out}
    # 3) deterministic scaffold (always produces something usable). Skipped when the
    # caller passes no_scaffold (auto-pine) so a transient AI outage doesn't bake in a
    # useless scaffold that then blocks a real conversion on the next attempt.
    if p.get("no_scaffold"):
        return {"ok": False, "skipped": True,
                "error": f"AI unavailable ({err or 'no usable output'}); left .pine missing for retry"}
    scaf = _tag_pine(_pine_scaffold(mod, base), "scaffold")
    os.makedirs(PINE_DIR, exist_ok=True)
    open(pp, "w", encoding="utf-8").write(scaf)
    return {"ok": True, "made": os.path.basename(pp), "via": "scaffold",
            "warning": f"AI unavailable ({err or 'no usable output'}); wrote a params-only "
                       "scaffold — port the entry/exit logic before trusting it.",
            "content": scaf}


def cmd_delete_run(p):
    """Delete a run from optimizer_history.db so it doesn't re-sync back (the web also
    deletes its Firestore doc). payload: {id} or {ids:[...]}."""
    ids = p.get("ids") or ([p.get("id")] if p.get("id") is not None else [])
    ids = [int(x) for x in ids if x is not None]
    if not ids:
        return {"ok": False, "error": "no run id(s)"}
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.executemany("DELETE FROM runs WHERE id=?", [(i,) for i in ids])
        conn.commit()
        return {"ok": True, "deleted": cur.rowcount, "ids": ids}
    finally:
        conn.close()


def cmd_relabel_run(p):
    """Re-label a run's strategy in optimizer_history.db. payload: {id|ids, strategy}."""
    ids = p.get("ids") or ([p.get("id")] if p.get("id") is not None else [])
    ids = [int(x) for x in ids if x is not None]
    label = p.get("strategy") or p.get("label")
    if not ids or not label:
        return {"ok": False, "error": "need id(s) + strategy"}
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.executemany("UPDATE runs SET strategy=? WHERE id=?",
                               [(str(label), i) for i in ids])
        conn.commit()
        return {"ok": True, "updated": cur.rowcount, "ids": ids, "strategy": label}
    finally:
        conn.close()


def _resolve_master(payload):
    """Map a master's logical key (instrument,timeframe,source) to its CSV file via the
    csv_files registry. Returns (abs_path, meta). Basename-confined to UPLOADS — the web
    sends only the logical key, never a path, so it cannot escape the uploads dir."""
    inst = str(payload.get("instrument", "")).strip()
    tf   = str(payload.get("timeframe", "")).strip()
    src  = str(payload.get("source", "")).strip()
    if not inst or not tf:
        raise ValueError("need instrument + timeframe")
    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        if src:
            row = conn.execute(
                "SELECT filename,name,rows FROM csv_files WHERE is_master=1 AND "
                "instrument=? AND timeframe=? AND source=?", (inst, tf, src)).fetchone()
        else:
            row = conn.execute(
                "SELECT filename,name,rows FROM csv_files WHERE is_master=1 AND "
                "instrument=? AND timeframe=? ORDER BY rows DESC", (inst, tf)).fetchone()
    finally:
        conn.close()
    if not row:
        raise ValueError(f"no master for {inst} {tf} {src or '(any source)'}")
    fn = os.path.basename(str(row[0]))
    path = os.path.join(UPLOADS, fn)
    if not os.path.isfile(path):
        raise ValueError(f"master file missing on disk: {fn}")
    return path, {"filename": fn, "name": row[1], "rows": row[2]}


def cmd_peek_master(payload):
    """Preview a master CSV for the web viewer: header + last N rows (default 200) + total
    row count. Tiny payload — fits the Firestore result doc with no gzip needed."""
    path, meta = _resolve_master(payload)
    n = max(1, min(int(payload.get("n", 200) or 200), 1000))
    with open(path, "r", encoding="utf-8") as fh:
        header = fh.readline().rstrip("\r\n")
        tail = deque(fh, maxlen=n)              # last N data lines, O(n) memory
    rows = [ln.rstrip("\r\n") for ln in tail if ln.strip()]
    return {"ok": True, "filename": meta["filename"], "name": meta["name"],
            "header": header, "rows": rows, "shown": len(rows), "total": meta["rows"]}


def cmd_get_master(payload):
    """Full master CSV, gzip+base64-encoded, for download WITHOUT Firebase Storage. CSV
    compresses ~8x, so the 10s/1m masters (~2 MB) fit under Firestore's ~1 MB doc cap; the
    big 5m/1m masters do not and are refused with a clear, actionable message."""
    path, meta = _resolve_master(payload)
    raw = open(path, "rb").read()
    b64 = base64.b64encode(gzip.compress(raw, 6)).decode("ascii")
    if len(b64) > 950000:                      # headroom under the 1,048,576-byte doc cap
        return {"ok": False, "error":
                f"{meta['filename']} is too large to download inline "
                f"({len(raw)//1024} KB raw -> {len(b64)//1024} KB gzipped). Without Firebase "
                f"Storage, only smaller masters (10s, 1m) download this way; use the VIEW "
                f"button for a preview of large ones."}
    return {"ok": True, "filename": meta["filename"], "gzip_b64": b64,
            "raw_bytes": len(raw), "rows": meta["rows"]}


HANDLERS = {"get_src": cmd_get_src, "delete": cmd_delete,
            "add": cmd_add, "make_pine": cmd_make_pine,
            "review_pine": cmd_review_pine, "write_pine": cmd_write_pine,
            "delete_run": cmd_delete_run, "relabel_run": cmd_relabel_run,
            "peek_master": cmd_peek_master, "get_master": cmd_get_master}


def process_command(action, payload, log=print):
    """Dispatch one command. Never raises — returns {ok:bool, ...}."""
    h = HANDLERS.get(action)
    if not h:
        return {"ok": False, "error": f"unknown action: {action}"}
    try:
        out = h(payload or {})
        log(f"  command {action} -> {'ok' if out.get('ok') else 'ERR: ' + str(out.get('error'))}")
        return out
    except Exception as e:
        log(f"  command {action} -> EXC {type(e).__name__}: {e}")
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
