# profile_report.py — one-call auto-EDA report per master (Backtesting Stack pill 1.2).
#
# NATIVE implementation on purpose: ydata-profiling/dabl carry heavy pinned deps
# (pydantic/visions/matplotlib versions) that could destabilize the trading PC's
# python env, so this builds a self-contained dark-theme HTML report from the same
# engine machinery the health/profile cards use (augur_engine.data_quality) plus a
# return-distribution histogram computed here. Zero new dependencies.
#
# Run:  python tools/profile_report.py "NQ 5m RTH"     (name substring match)
#       python tools/profile_report.py --all
# Output: augur_uploads/_profiles/<name>.html  (open locally in a browser)
import os
import re
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from augur_engine.data import list_masters                      # noqa: E402
from augur_engine.data_quality import (profile_master, health_summary,   # noqa: E402
                                       tf_seconds, UPLOADS)

OUT_DIR = os.path.join(UPLOADS, "_profiles")

CSS = """
body{margin:0;background:#05050a;color:#c8ccd8;font-family:-apple-system,Segoe UI,sans-serif;font-size:14px}
.wrap{max-width:860px;margin:0 auto;padding:24px 20px 50px}
h1{font-size:18px;margin:0 0 2px} .sub{color:#7070a0;font-size:12px;margin:0 0 16px}
.grid{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px}
.card{flex:1 1 250px;min-width:220px;background:#0e0e1e;border:1px solid #1e1e36;border-radius:10px;padding:10px 12px}
.k{font-size:9px;letter-spacing:1.5px;color:#5a5a78;text-transform:uppercase;margin-bottom:6px}
.stat{display:flex;justify-content:space-between;font-size:12.5px;padding:2px 0;color:#a0a4b8}
.stat b{color:#c8ccd8;font-weight:600}
.warn{color:#f5c842} .bad{color:#ff3d5a} .ok{color:#00e5a0}
svg{display:block;width:100%}
.note{font-size:11.5px;color:#a0a4b8;line-height:1.5;margin:2px 0}
"""


def _svg_bars(vals, labels, color, H=60, tips=None):
    n = len(vals)
    if not n:
        return ""
    W = max(200, n * 10)
    mx = max(vals) or 1
    bars = []
    for i, v in enumerate(vals):
        bh = v / mx * H
        tip = f"<title>{tips[i]}</title>" if tips else ""
        bars.append(f'<rect x="{i*10+1}" y="{H-bh:.1f}" width="8" height="{bh:.1f}" '
                    f'fill="{color}" opacity="0.75">{tip}</rect>')
        if labels and labels[i]:
            bars.append(f'<text x="{i*10+1}" y="{H+9}" font-size="6.5" fill="#5a5a78">{labels[i]}</text>')
    return f'<svg viewBox="0 0 {W} {H+11}" preserveAspectRatio="none">{"".join(bars)}</svg>'


def _ret_hist(df, secs):
    """Within-session bar returns -> (counts, bin centers in sigma units)."""
    t = df["time"].to_numpy("int64")
    c = df["close"].to_numpy(float)
    same = np.diff(t) <= 3 * secs
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.diff(c) / np.where(c[:-1] == 0, np.nan, np.abs(c[:-1]))
    r = r[same]; r = r[np.isfinite(r)]
    if len(r) < 100:
        return None
    sd = r.std() or 1e-9
    z = np.clip((r - r.mean()) / sd, -6, 6)
    counts, edges = np.histogram(z, bins=61)
    return counts, (edges[:-1] + edges[1:]) / 2, len(r)


def report(master):
    prof = profile_master(master)
    heal = health_summary(master)
    if "error" in prof:
        print(f"  ! {master['name']}: {prof['error']}")
        return None
    secs = tf_seconds(master.get("timeframe")) or 300
    df = pd.read_csv(os.path.join(UPLOADS, master["filename"]),
                     usecols=lambda col: col in ("time", "close"))
    hist = _ret_hist(df, secs)

    rt = prof.get("ret") or {}
    o = prof.get("outliers") or {}
    parts = [f'<h1>{master["name"]}</h1>',
             f'<p class="sub">{master.get("instrument")} · {master.get("timeframe")} · '
             f'{str(master.get("session","")).upper()} · {master.get("source")} · '
             f'{prof.get("bars",0):,} bars · {master.get("date_from")} → {master.get("date_to")}</p>']

    vcls = {"PASS": "ok", "WARN": "warn"}.get(heal.get("verdict"), "bad")
    stats = [("Health verdict", f'<span class="{vcls}">{heal.get("verdict")}</span>'),
             ("Adjustment class", heal.get("adj") or "—"),
             ("Roll seams", heal.get("seams") if heal.get("seams") is not None else "— (no stitch twin)"),
             ("Return σ (bar)", f'{rt.get("std_bp","—")} bp'),
             ("Skew", rt.get("skew", "—")),
             ("Excess kurtosis", rt.get("kurt", "—")),
             ("Price range", f'{prof["price"]["min"]:,} – {prof["price"]["max"]:,}' if prof.get("price") else "—"),
             ("Outlier bars (IF)", f'{o.get("n","—")} of {o.get("scored",0):,} scored')]
    srows = "".join(f'<div class="stat"><span>{k}</span><b>{v}</b></div>' for k, v in stats)
    notes = "".join(f'<div class="note">• {n}</div>' for n in (heal.get("notes") or []))
    parts.append(f'<div class="grid"><div class="card"><div class="k">Summary</div>{srows}{notes}</div>')

    if hist:
        counts, centers, n = hist
        # log-y histogram + a normal reference curve — fat tails jump out immediately
        mx = np.log1p(counts.max()) or 1
        H, W = 90, 61 * 10
        bars = "".join(
            f'<rect x="{i*10}" y="{H-np.log1p(cnt)/mx*H:.1f}" width="9" height="{np.log1p(cnt)/mx*H:.1f}" '
            f'fill="{"#4a9eff" if abs(centers[i])<=3 else "#ff3d5a"}" opacity="0.75">'
            f'<title>{centers[i]:+.1f}σ: {cnt:,}</title></rect>'
            for i, cnt in enumerate(counts))
        norm = counts.sum() * (centers[1] - centers[0]) / np.sqrt(2 * np.pi) * np.exp(-centers ** 2 / 2)
        pts = " ".join(f'{i*10+4.5},{H-np.log1p(y)/mx*H:.1f}' for i, y in enumerate(norm))
        parts.append(f'<div class="card"><div class="k">Return distribution (σ units · log count · red = beyond 3σ)</div>'
                     f'<svg viewBox="0 0 {W} {H+4}" preserveAspectRatio="none">{bars}'
                     f'<polyline points="{pts}" fill="none" stroke="#c8ccd8" stroke-width="1" '
                     f'stroke-dasharray="3,2" opacity="0.8"/></svg>'
                     f'<div class="note">{n:,} within-session bar returns; dashed = normal reference. '
                     f'Bars above the line in the red zone = fat tails (kurt {rt.get("kurt","—")}).</div></div>')
    parts.append('</div>')

    row2 = []
    vb = prof.get("vol_by_year") or []
    if len(vb) > 1:
        row2.append('<div class="card"><div class="k">Annualized vol by year (%)</div>'
                    + _svg_bars([x["vol"] for x in vb],
                                [str(x["y"])[2:] if i % 2 == 0 else "" for i, x in enumerate(vb)],
                                "#4a9eff", tips=[f'{x["y"]}: {x["vol"]}%' for x in vb]) + '</div>')
    hp = prof.get("hour_profile") or []
    if len(hp) > 2:
        row2.append('<div class="card"><div class="k">Activity by ET hour (|ret|, 100 = max)</div>'
                    + _svg_bars([x["a"] for x in hp],
                                [str(x["h"]) if x["h"] % 3 == 0 else "" for x in hp],
                                "#a78bfa", tips=[f'{x["h"]}:00 — {x["a"]}' for x in hp]) + '</div>')
    cov = prof.get("coverage") or []
    if len(cov) > 2:
        cols = ["#00e5a0" if x["pct"] >= 95 else "#f5c842" if x["pct"] >= 85 else "#ff3d5a" for x in cov]
        W, H = max(200, len(cov) * 3), 40
        bars = "".join(f'<rect x="{i*3}" y="{H-x["pct"]/100*H:.1f}" width="2.4" '
                       f'height="{x["pct"]/100*H:.1f}" fill="{cols[i]}" opacity="0.8">'
                       f'<title>{x["m"]}: {x["pct"]}%</title></rect>' for i, x in enumerate(cov))
        row2.append(f'<div class="card"><div class="k">Monthly bar coverage (%)</div>'
                    f'<svg viewBox="0 0 {W} {H+4}" preserveAspectRatio="none">{bars}</svg></div>')
    if row2:
        parts.append('<div class="grid">' + "".join(row2) + '</div>')

    if o.get("examples"):
        parts.append('<div class="card"><div class="k">Most recent outlier bars (IsolationForest — flagged, never deleted)</div>'
                     + "".join(f'<div class="note">▲ {x}</div>' for x in o["examples"]) + '</div>')

    html = (f'<!DOCTYPE html><html><head><meta charset="utf-8"/><title>{master["name"]} — EDA profile</title>'
            f'<style>{CSS}</style></head><body><div class="wrap">{"".join(parts)}'
            f'<p class="sub" style="margin-top:18px">EDGELOG Backtesting Stack pill 1.2 — native auto-EDA report '
            f'(ydata-profiling-style, zero extra deps).</p></div></body></html>')
    os.makedirs(OUT_DIR, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", master["name"]).strip("_")
    path = os.path.join(OUT_DIR, f"{safe}.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"  -> {path}")
    return path


if __name__ == "__main__":
    arg = " ".join(sys.argv[1:]).strip()
    ms = list_masters()
    if not arg:
        print("usage: python tools/profile_report.py <master-name-substring> | --all")
        print("masters:"); [print("  ", m["name"]) for m in ms]
        sys.exit(1)
    sel = ms if arg == "--all" else [m for m in ms if arg.lower() in m["name"].lower()]
    if not sel:
        print(f"no master matches '{arg}'"); sys.exit(1)
    for m in sel:
        report(m)
