"""AI Optimize loop (streamlit-free) — Phase 5 of the EDGELOG port.

Each round: sweep the current parameter ranges on the IN-SAMPLE data, validate the
winner OUT-OF-SAMPLE (75/25 split), hand the results to an LLM, and let it propose the
next ranges to search — focusing the search while distrusting in-sample-only winners.

Pluggable LLM backend (no Anthropic tokens required):
  • provider="ollama"      -> local Ollama (default model qwen3.6) — FREE, on this PC
  • provider="claude-cli"  -> the local `claude -p` CLI (your subscription)
  • provider="anthropic"   -> Anthropic API (needs api_key; pay-per-token)
"""
import re
import json
import subprocess

import requests

from .strategies import load_strategy, strategy_params
from .data import find_master, load_master_arrays
from .optimize import grid_from_preset, run_grid
from .engine import run_backtest

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_OLLAMA_MODEL = "qwen3.6:latest"

_AI_OPT_SYSTEM = (
    "You are a quantitative trading-strategy optimizer embedded in a backtesting tool "
    "called Augur. Each round you receive: the strategy's tunable parameters (with "
    "min/max/type), the latest backtest sweep (top configs by total PNL, plus in-sample "
    "vs out-of-sample PNL), and the best config so far. Propose the NEXT set of parameter "
    "ranges to search, focusing where results look strongest while avoiding overfitting "
    "(a config that wins in-sample but collapses out-of-sample is overfit — distrust it). "
    "Respond ONLY with a compact JSON object, no prose, no markdown fences. Schema:\n"
    '{ "reasoning": "<=2 sentences", '
    '"next_ranges": { "<param>": [v1, v2, ...] }, "stop": false }\n'
    "Only include parameters you want to change; omit others. Keep each list to 2-5 values "
    "so the grid stays small."
)


def _parse_json(text):
    t = (text or "").strip()
    t = re.sub(r"<think>.*?</think>", "", t, flags=re.S).strip()   # qwen reasoning tags
    if t.startswith("```"):
        lines = t.splitlines()
        t = "\n".join(lines[1:-1] if lines and lines[-1].startswith("```") else lines[1:])
    a, b = t.find("{"), t.rfind("}")
    if a >= 0 and b > a:
        t = t[a:b + 1]
    return json.loads(t)


def call_llm(provider, system, user, model=None, api_key=None, max_tokens=2000):
    """Return (text, error). Routes to ollama / claude-cli / anthropic."""
    provider = (provider or "ollama").lower()
    try:
        if provider == "ollama":
            r = requests.post(OLLAMA_URL, timeout=600, json={
                "model": model or DEFAULT_OLLAMA_MODEL,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "stream": False, "format": "json", "think": False,
                "options": {"temperature": 0.4}})
            if r.status_code != 200:
                return "", f"ollama {r.status_code}: {r.text[:160]}"
            return r.json().get("message", {}).get("content", ""), None
        if provider in ("claude-cli", "claude_cli", "cli"):
            p = subprocess.run(
                ["claude", "-p", system + "\n\n" + user + "\n\nRespond ONLY with the JSON object."],
                capture_output=True, text=True, timeout=600)
            if p.returncode != 0:
                return "", f"claude-cli: {p.stderr[:160]}"
            return p.stdout, None
        if provider == "anthropic":
            r = requests.post("https://api.anthropic.com/v1/messages", timeout=120,
                              headers={"x-api-key": api_key or "", "anthropic-version": "2023-06-01",
                                       "content-type": "application/json"},
                              json={"model": model or "claude-sonnet-4-20250514",
                                    "max_tokens": max_tokens, "system": system,
                                    "messages": [{"role": "user", "content": user}]})
            if r.status_code != 200:
                return "", f"anthropic {r.status_code}: {r.text[:160]}"
            return r.json()["content"][0]["text"], None
        return "", f"unknown provider {provider}"
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"


def _split_arrays(arrays, frac):
    """Split into (in-sample, out-of-sample) on a DAY boundary so sessions stay whole."""
    did = arrays["day_id"]
    days = sorted(set(did.tolist()))
    cut = days[max(1, int(len(days) * frac))]
    mis, moos = (did < cut), (did >= cut)

    def sub(m):
        a = {}
        for k in ("open", "high", "low", "close", "volume", "day_id"):
            v = arrays.get(k)
            a[k] = (v[m] if v is not None else None)
        idx = arrays.get("index")
        a["index"] = idx[m] if idx is not None else None
        a["meta"] = arrays.get("meta")
        return a
    return sub(mis), sub(moos)


def _digest(top):
    out = []
    for i, t in enumerate(top[:6], 1):
        params = {k: v for k, v in t.items()
                  if k not in ("total_pnl", "num_trades", "win_rate",
                               "profit_factor", "max_drawdown", "avg_pnl")}
        out.append(f"#{i} pnl={t.get('total_pnl', 0):.0f} trades={t.get('num_trades', 0)} "
                   f"pf={min(t.get('profit_factor', 0), 99):.2f} {json.dumps(params)}")
    return "\n".join(out)


def ai_optimize(strategy, *, instrument=None, timeframe="5m", session="rth", source=None,
                master=None, arrays=None, preset=None, grid=None, n_rounds=5,
                provider="ollama", model=None, api_key=None, cost_pts=0.0,
                min_trades=30, workers=1, oos_split=0.75, progress_cb=None,
                date_from=None, date_to=None):
    """Run the AI optimize loop. Returns {provider, model, n_rounds, best_params,
    best_is_pnl, best_oos_pnl, best, rounds[...], oos_split, bars}."""
    mod = load_strategy(strategy) if isinstance(strategy, str) else strategy
    if arrays is None:
        if master is None:
            master = find_master(instrument, timeframe, session, source)
            if master is None:
                raise ValueError(f"no master for {instrument} {timeframe} {session} {source}")
        arrays = load_master_arrays(master, date_from=date_from, date_to=date_to)

    is_arr, oos_arr = _split_arrays(arrays, oos_split)
    cur_grid = dict(grid) if grid else dict(grid_from_preset(mod, preset))
    dp = strategy_params(mod)
    param_spec = {k: {kk: vv for kk, vv in v.items()
                      if kk in ("type", "min", "max", "step", "options")}
                  for k, v in dp.items()}

    best = best_is = best_oos = best_metrics = None
    rounds = []
    for rnd in range(1, n_rounds + 1):
        if progress_cb:
            progress_cb(rnd - 1, n_rounds)
        gr = run_grid(mod, arrays=is_arr, grid=cur_grid, cost_pts=cost_pts,
                      min_trades=min_trades, top_n=8, workers=workers)
        bp = gr.get("best_params")
        if not bp:
            rounds.append({"round": rnd, "error": "no valid configs in-sample"}); break
        oos = run_backtest(mod, arrays=oos_arr, params=bp, cost_pts=cost_pts) or {}
        is_pnl = (gr.get("best") or {}).get("total_pnl", 0.0)
        oos_pnl = oos.get("total_pnl", 0.0)
        if best is None or oos_pnl > (best_oos if best_oos is not None else -1e18):
            best, best_is, best_oos, best_metrics = bp, is_pnl, oos_pnl, gr.get("best")

        oos_note = (f"Winner in-sample PNL {is_pnl:.0f} pts vs out-of-sample {oos_pnl:.0f} pts "
                    f"({'HOLDS' if oos_pnl > 0 else 'COLLAPSES'} out-of-sample).")
        user = (f"Round {rnd} of {n_rounds}.\n\nPARAMETERS:\n{json.dumps(param_spec)}\n\n"
                f"BEST CONFIG SO FAR:\n{json.dumps(best, default=str)}\n\n{oos_note}\n\n"
                f"LATEST RESULTS (in-sample top configs):\n{_digest(gr.get('top') or [])}\n")
        text, err = call_llm(provider, _AI_OPT_SYSTEM, user, model=model, api_key=api_key)
        rec = {"round": rnd, "is_pnl": is_pnl, "oos_pnl": oos_pnl,
               "best_params": bp, "n_combos": gr.get("n_combos")}
        if err:
            rec["error"] = err; rounds.append(rec); break
        try:
            prop = _parse_json(text)
        except Exception as e:
            rec["error"] = f"bad JSON from LLM: {e}"; rec["raw"] = (text or "")[:200]
            rounds.append(rec); break
        rec["reasoning"] = str(prop.get("reasoning", ""))[:300]
        rounds.append(rec)
        for k, vals in (prop.get("next_ranges") or {}).items():
            if k in dp and isinstance(vals, list) and vals:
                cur_grid[k] = vals
        if prop.get("stop"):
            break

    if progress_cb:
        progress_cb(n_rounds, n_rounds)
    return {"provider": provider, "model": model or DEFAULT_OLLAMA_MODEL,
            "n_rounds": len(rounds), "best_params": best, "best_is_pnl": best_is,
            "best_oos_pnl": best_oos, "best": best_metrics, "rounds": rounds,
            "oos_split": oos_split, "bars": int(len(arrays["close"]))}


_AI_EVOLVE_SYSTEM = (
    "You are a quantitative trading-strategy engineer embedded in Augur. In addition to "
    "tuning parameters, you may REWRITE the strategy's Python code to improve it (add a "
    "filter, change exit logic, fix a weakness visible in the results). You receive the "
    "current full strategy source, its parameters, and backtest results (in-sample vs "
    "out-of-sample). A config that wins in-sample but fails out-of-sample is overfit — prefer "
    "robust, simple changes over complex ones that only fit noise. The file MUST keep the "
    "Augur plugin contract: module globals STRATEGY_NAME, DEFAULT_PARAMS (dict of "
    "{type,min,max,step,label,tooltip}), PARAM_GRID_PRESETS, and run_backtest(opens,highs,"
    "lows,closes,**params,return_trades=False,_stop_event=None,_pause_event=None) returning a "
    "dict with total_pnl,num_trades,win_rate,profit_factor,max_drawdown,avg_pnl,wins,losses. "
    "Respond ONLY with compact JSON, no markdown fences. Schema:\n"
    '{ "reasoning": "<=3 sentences", "next_ranges": { "<param>": [..] }, '
    '"code_edit": null, "code_edit_summary": "", "stop": false }\n'
    "Only set code_edit when a code change is warranted; most rounds should be null. When you "
    "do edit, return the ENTIRE file as a string, not a diff."
)


def validate_strategy_code(code):
    """Validate AI-written strategy code against the plugin contract WITHOUT persisting.
    Returns (module, error). Compiles, imports, checks the contract, smoke-tests run_backtest
    on synthetic data. This is the SAFETY GATE — bad code never reaches a real run."""
    import os
    import tempfile
    import importlib.util
    import numpy as np
    try:
        compile(code, "<ai_strategy>", "exec")
    except SyntaxError as se:
        return None, f"Syntax error: {se}"
    tmpf = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as f:
            f.write(code); tmpf = f.name
        spec = importlib.util.spec_from_file_location("_ai_cand", tmpf)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for attr in ("STRATEGY_NAME", "DEFAULT_PARAMS", "run_backtest"):
            if not hasattr(mod, attr):
                return None, f"Missing required '{attr}'"
        if not isinstance(mod.DEFAULT_PARAMS, dict) or not mod.DEFAULT_PARAMS:
            return None, "DEFAULT_PARAMS must be a non-empty dict"
        n = 300; rng = np.random.RandomState(0)
        c = np.cumsum(rng.randn(n)) + 100
        o = c + rng.randn(n) * 0.2
        h = np.maximum(o, c) + 0.3; l = np.minimum(o, c) - 0.3
        defaults = {k: v.get("default") for k, v in mod.DEFAULT_PARAMS.items() if isinstance(v, dict)}
        res = mod.run_backtest(o, h, l, c, **defaults)
        if res is not None:
            for mk in ("total_pnl", "num_trades", "win_rate"):
                if mk not in res:
                    return None, f"run_backtest result missing '{mk}'"
        return mod, None
    except Exception as ex:
        return None, f"Validation run failed: {ex}"
    finally:
        if tmpf:
            try:
                os.unlink(tmpf)
            except Exception:
                pass


def _default_grid(mod):
    from .strategies import strategy_params
    return {k: [v.get("default")] for k, v in strategy_params(mod).items()
            if isinstance(v, dict) and v.get("default") is not None}


def ai_evolve(strategy, *, instrument=None, timeframe="5m", session="rth", source=None,
              master=None, arrays=None, preset=None, grid=None, n_rounds=4,
              provider="ollama", model=None, api_key=None, cost_pts=0.0,
              min_trades=30, workers=1, oos_split=0.75, save_dir=None, progress_cb=None,
              date_from=None, date_to=None):
    """Like ai_optimize, but the LLM may also REWRITE the strategy code each round. Every
    code edit is validated (compile+contract+smoke) before use and saved as a NEW file in
    save_dir (default augur_strategies/), so existing strategies are never modified."""
    import os
    import time
    from .paths import STRAT_DIR
    from .strategies import load_strategy, _resolve, strategy_params
    from .data import find_master, load_master_arrays
    from .optimize import grid_from_preset, run_grid
    from .engine import run_backtest

    mod = load_strategy(strategy) if isinstance(strategy, str) else strategy
    src_path = _resolve(strategy) if isinstance(strategy, str) else None
    cur_src = open(src_path, encoding="utf-8").read() if src_path and os.path.exists(src_path) else ""
    base = os.path.splitext(os.path.basename(src_path))[0] if src_path else "evolved"
    save_dir = save_dir or STRAT_DIR

    if arrays is None:
        if master is None:
            master = find_master(instrument, timeframe, session, source)
            if master is None:
                raise ValueError(f"no master for {instrument} {timeframe} {session} {source}")
        arrays = load_master_arrays(master, date_from=date_from, date_to=date_to)
    is_arr, oos_arr = _split_arrays(arrays, oos_split)
    try:
        cur_grid = dict(grid) if grid else dict(grid_from_preset(mod, preset))
    except Exception:
        cur_grid = _default_grid(mod)

    best = best_is = best_oos = best_metrics = None
    rounds = []
    evolved_file = None
    for rnd in range(1, n_rounds + 1):
        if progress_cb:
            progress_cb(rnd - 1, n_rounds)
        gr = run_grid(mod, arrays=is_arr, grid=cur_grid, cost_pts=cost_pts,
                      min_trades=min_trades, top_n=8, workers=1)
        bp = gr.get("best_params")
        if not bp:
            rounds.append({"round": rnd, "error": "no valid configs in-sample"}); break
        oos = run_backtest(mod, arrays=oos_arr, params=bp, cost_pts=cost_pts) or {}
        is_pnl = (gr.get("best") or {}).get("total_pnl", 0.0)
        oos_pnl = oos.get("total_pnl", 0.0)
        if best is None or oos_pnl > (best_oos if best_oos is not None else -1e18):
            best, best_is, best_oos, best_metrics = bp, is_pnl, oos_pnl, gr.get("best")

        dp = strategy_params(mod)
        param_spec = {k: {kk: vv for kk, vv in v.items()
                          if kk in ("type", "min", "max", "step", "options")}
                      for k, v in dp.items()}
        oos_note = (f"Winner in-sample {is_pnl:.0f} pts vs out-of-sample {oos_pnl:.0f} pts "
                    f"({'HOLDS' if oos_pnl > 0 else 'COLLAPSES'} out-of-sample).")
        user = (f"Round {rnd} of {n_rounds}.\n\nPARAMETERS:\n{json.dumps(param_spec)}\n\n"
                f"BEST CONFIG SO FAR:\n{json.dumps(best, default=str)}\n\n{oos_note}\n\n"
                f"LATEST RESULTS:\n{_digest(gr.get('top') or [])}\n\n"
                f"CURRENT STRATEGY SOURCE:\n```python\n{cur_src}\n```")
        text, err = call_llm(provider, _AI_EVOLVE_SYSTEM, user, model=model,
                             api_key=api_key, max_tokens=8000)
        rec = {"round": rnd, "is_pnl": is_pnl, "oos_pnl": oos_pnl}
        if err:
            rec["error"] = err; rounds.append(rec); break
        try:
            prop = _parse_json(text)
        except Exception as e:
            rec["error"] = f"bad JSON: {e}"; rounds.append(rec); break
        rec["reasoning"] = str(prop.get("reasoning", ""))[:300]
        code_edit = prop.get("code_edit")
        if code_edit and isinstance(code_edit, str) and len(code_edit) > 120:
            newmod, verr = validate_strategy_code(code_edit)
            if verr:
                rec["code_error"] = verr            # rejected — keep current strategy
            else:
                evolved_file = f"{base}_evo_{int(time.time())}.py"
                with open(os.path.join(save_dir, evolved_file), "w", encoding="utf-8") as f:
                    f.write(code_edit)
                mod, cur_src = newmod, code_edit
                cur_grid = _default_grid(mod)
                rec["code_edit"] = str(prop.get("code_edit_summary", ""))[:160]
                rec["evolved_file"] = evolved_file
        rounds.append(rec)
        for k, vals in (prop.get("next_ranges") or {}).items():
            if k in strategy_params(mod) and isinstance(vals, list) and vals:
                cur_grid[k] = vals
        if prop.get("stop"):
            break

    if progress_cb:
        progress_cb(n_rounds, n_rounds)
    return {"provider": provider, "model": model or DEFAULT_OLLAMA_MODEL, "mode": "evolve",
            "n_rounds": len(rounds), "best_params": best, "best_is_pnl": best_is,
            "best_oos_pnl": best_oos, "best": best_metrics, "rounds": rounds,
            "evolved_file": evolved_file, "oos_split": oos_split,
            "bars": int(len(arrays["close"]))}
