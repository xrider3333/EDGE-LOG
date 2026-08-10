# Visual PnL & Price-Action Report — build handoff

**Audience:** a Claude Code session that has never seen this work. Everything you need
to pick this up is either in this file or in the two repo artifacts it points at. Read
the artifacts before writing code — this doc summarizes them, it does not replace them.

## 0. Status table

| Area | Status | Where |
|---|---|---|
| Working prototype (data + all 12 charts, dark theme, pure SVG, zero console errors) | **DONE** | `docs/samples/noise_visual_report.html` |
| Data-build script (backend → JSON) | **DONE** (promoted from scratchpad) | `tools/build_visual_report.py` |
| Reusable candlestick-panel drawing function | **DONE**, embedded in the sample HTML's `<script>` | `docs/samples/noise_visual_report.html` — `candlestickChart()` |
| JSON→chart mapping table (which data key feeds which chart) | **DONE**, reproduced below | §2.3 of this doc |
| Exit-price reconstruction fix (cost-inversion) | **DONE**, documented + implemented | `tools/build_visual_report.py` STEP 3 |
| **Phase A** — in-app per-trade candle modal off the blotter row | **SHIPPED v71.16** (2026-08-08) — see §3.4 for what actually shipped and what was deliberately left | `api/bars.py`, `api/runner.py` (`get_bars`), `index.html` (`candleSVG`, `_openCandles`), `tools/candle_probe.py` |
| Blotter exit-price cost-inversion fix (the §2.5 bug, in the LIVE blotter) | **SHIPPED v71.16** — was wrong on 3,397/4,065 ORB trades | `api/blotter.py` `champion_blotter` |
| **Phase B** — TradingView Pine trade-overlay bridge | **NOT STARTED** | design in §4 |
| **Phase C** — static PNG/SVG export attached to saved run reports | **NOT STARTED, optional** | §5 |
| Suggested extras (click-through, keyboard nav, worst-10 filter, overlay toggles, generic overlay contract) | **SUGGESTIONS ONLY, not specced in detail** | §6 |

---

## 1. WHY

The owner assesses a strategy by *looking at the price action on its actual trades* —
not just the aggregate stats — and derives his tweaks that way. He also needs to
reconcile EDGELOG's own backtested trades against what TradingView shows for the same
symbol/window (a running theme in this repo — see `tools/reconcile.py` and
`augur_engine/reconcile.py`, and the `edgelog-reconcile-tool` / `edgelog-trade-timestamp-mixed-tz`
memory items). Today EDGELOG's run report shows equity curves and summary tables but
never draws a single candle — there is no way, in-app, to see *what the bars looked
like* around an entry or exit. This feature closes that gap: charts you can look at a
trade through, and (Phase B) a bridge that puts EDGELOG's own trades on a real
TradingView chart for side-by-side comparison.

## 2. WHAT EXISTS TODAY (done)

### 2.1 The prototype

`docs/samples/noise_visual_report.html` (402,091 bytes ≈ 393 KB) is a **self-contained,
single-file HTML report** — inline SVG, vanilla JS, no external requests, no chart
library, dark theme matching EDGELOG's own palette (`#0d1117` background, accent blue
`#58a6ff`, green/red PnL colors). It was built to visualize **NOISE 1.0**, an
owner-directed backend-testing promotion (`augur_strategies/NOISE_1_0.py`) — **not a
live-book strategy**; it is a research/demo dataset, chosen because it was the run at
hand when this was prototyped. Nothing about the report or the drawing code is
NOISE-specific except the data — that is the point: the drawing functions take generic
`{bars, overlays, markers}` shapes (see §2.4), so they apply to any strategy.

Verified: opened in Chrome, zero console errors, renders end-to-end.

**What it renders** (12 chart panels total, in this order):

1. **Full-history equity curve** (2010 → 2026-06-30, ~3,389 trades, downsampled to
   ≤1,500 points for file size) with an **underwater/drawdown sub-pane** directly below
   it, a shaded "LOCKBOX YEAR" region, and two labelled worst-trade markers (the
   sealed-year worst and the all-time worst).
2. **Sealed-year equity curve**, full resolution (242 trades, one point per trade, no
   downsampling) plus a **monthly net-$ bar chart** for the same 12-month window.
3. **Per-year net-$ bars**, 2010 → 2026 (2026 bar is partial).
4. **"Where it trades"** — four small panels: (a) entry time-of-day histogram (5-minute
   buckets, 09:30–16:00 ET) with an avg-$/trade line overlaid on a second y-axis, (b)
   long vs short split (count, net $, win rate), (c) holding-time histogram (bars held,
   capped at 20+), (d) trade-PnL distribution histogram ($500-wide bins).
5. **Six candlestick price-action panels** — one full RTH session (5-minute OHLC bars)
   per chosen trade: biggest winner, biggest loser, and two "median" winners/losers
   each (the trades nearest the middle of the sorted winner/loser PnL lists). Each panel
   draws that session's candles, the strategy's own upper/lower band curves (`UB`/`LB`,
   recomputed from the frozen config — NOISE 1.0's 1.5σ envelope), the session VWAP,
   entry/exit markers (▲/▼ glyph + a colored exit dot), and a shaded rectangle over the
   held window.

A footer table (built from `DATA.schema_notes` by `renderFooter()`) documents which
JSON key feeds which chart — reproduced in §2.3 below.

### 2.2 The generator

`tools/build_visual_report.py` (promoted verbatim from the scratchpad prototype,
originally `build_noise_report_data.py`) is the **data-build half** of the pipeline. It:

1. Re-runs NOISE 1.0 through `augur_engine.engine.run_backtest` on a pre-lockbox window
   as a **sanity gate** (must match a hardcoded expected n/net/PF/DD), then cross-checks
   the same window against `tools/noise_research.py`'s `run_noise2()` directly — both
   must agree before it proceeds.
2. Loads the full history via `augur_engine.data.load_master_arrays` and re-runs
   `run_noise2()` over the whole span (2010 → 2026-06-30) to get every trade.
3. Builds per-trade records (§2.5 covers the exit-price reconstruction it does here).
4. Splits pre-lockbox vs sealed-year, computes headline stats, the downsampled equity
   series, the histograms, and picks the 6 representative trades for the candlestick
   panels (biggest winner/loser + 2 median winners + 2 median losers).
5. Writes one JSON file: `noise_visual_data.json` (**not copied into the repo** — see
   note below).

**Important — this script only produces the JSON.** The actual chart-rendering code
(the SVG helper functions and the reusable `candlestickChart()`) live in a separate
template file (`report_template.html`, 716 lines) that has a `/*__DATA_JSON__*/`
placeholder; a third tiny script (`assemble_html.py`) does a straight string-substitution
of the JSON into that placeholder to produce the final HTML. **Only the data-build
script and the final assembled HTML were promoted into this repo** (per this task's
scope) — `report_template.html` and `assemble_html.py` themselves are still in the
(volatile) scratchpad and were not copied. This is not a loss: because the assemble step
is a pure substitution, the exact same JS/SVG drawing code — including
`candlestickChart()` — is fully present, verbatim, inside the `<script>` block of
`docs/samples/noise_visual_report.html`. That committed HTML file **is the source of
truth** for the drawing code. `noise_visual_data.json` (the standalone data file,
~363 KB) was likewise not copied separately, for the same reason: it is embedded
verbatim inside the committed HTML's `<script id="noise-data" type="application/json">`
block. If a future session wants the template/assemble scaffolding back (e.g. to
regenerate a report for a different strategy without hand-editing a 400 KB HTML file),
it will need to be reconstructed from `docs/samples/noise_visual_report.html`'s
`<script>` contents — extracting the JS above the `renderHeader()`/`renderEquityFull()`
call site back out into a template is mechanical (the file is well-commented and
section-divided).

**Note on the 393 KB file size**: this is fine for git (small by repo standards) but is
larger than any other single file in this repo. If a future version of this report needs
to be generated repeatedly (e.g. one per run), consider NOT committing each instance —
this one sample stays as the reference/prototype; Phase A below does not generate or
store HTML files like this at all, it renders charts live in the app from JSON the
runner returns.

### 2.3 JSON key → chart mapping (reproduced from the HTML's own footer table)

This is the exact table the shipped HTML renders (`renderFooter()`, reading
`DATA.schema_notes`) — the report's own self-documentation of its data contract:

| JSON key (`noise_visual_data.json`) | Feeds |
|---|---|
| `equity_full.points[].cum` | chart 1 — full-history equity curve (cumulative net $, x = trade sequence) |
| `drawdown_full.points[].dd` | chart 1 — underwater sub-pane beneath the equity curve |
| `equity_full.lockbox_start_index` | chart 1 — x-index where the LOCKBOX YEAR shading begins |
| `markers.sealed_worst` / `markers.alltime_worst` | chart 1 — the two labelled worst-trade dots |
| `equity_sealed.points[].cum` | chart 2 — sealed-year-only equity curve (242 trades, full resolution) |
| `sealed_monthly` | chart 2 — sealed-year monthly net $ bars (2025-07 .. 2026-06) |
| `per_year` | chart 3 — per-year net $ bars (2010-2026) |
| `tod_histogram` | chart 4a — entry time-of-day histogram (count bars) + avg $/trade line overlay |
| `long_short` | chart 4b — long vs short counts/net $ |
| `holding_hist` | chart 4c — holding-time-in-bars histogram |
| `pnl_hist` | chart 4d — trade PnL distribution histogram |
| `panels[]` | charts 5.1-5.6 — one candlestick session panel per chosen sealed-year trade (bars/ub/lb/vwap/entry-exit markers) |

Each `panels[]` entry also carries: `category` (which of the 6 slots), `date`, `side`,
`entry_time`/`exit_time`, `entry_px`/`exit_px`, `pnl_usd`/`pnl_pts`, `holding_bars`,
`session_open`/`session_close`, `entry_bar_local`/`exit_bar_local` (index into that
session's own bar array), and the three parallel per-bar arrays `bars`/`ub`/`lb`/`vwap`.

### 2.4 The reusable SVG drawing function

`candlestickChart(bars, overlays, markers, opts) -> SVGSVGElement`, defined at
`docs/samples/noise_visual_report.html:23349` (source line 498 of the original
`report_template.html`). Signature, read directly from the code:

```
candlestickChart(bars, overlays, markers, opts) -> SVGSVGElement
  bars     : [{t, o, h, l, c, v}, ...]                      (one full RTH session, 5m bars)
  overlays : {ub: [num|null,...], lb: [...], vwap: [...]}   (same length as bars)
  markers  : {entryIdx, entryPrice, side, exitIdx, exitPrice, shadeFrom, shadeTo}
  opts     : {width, height, marginLeft, marginRight, marginTop, marginBottom}
```

It draws gridlines + y-axis, a shaded held-window rectangle, the UB/LB/VWAP overlay
lines, the OHLC candles themselves, x-axis time labels, and the entry (▲/▼ glyph) and
exit (colored dot) markers with price labels. It appends nothing to the DOM itself —
callers `appendChild` the returned `<svg>`. This is called once per panel by
`renderPanels()` (`docs/samples/noise_visual_report.html:23440`), which also builds the
title/subtitle/legend chrome around each panel card. **This is the function Phase A
should call directly** for the in-app single-trade viewer — the prototype's own comment
in the template says exactly that ("the in-app single-trade viewer this prototypes would
call it directly with live bars/overlays/markers").

The file also defines smaller generic helpers worth knowing about: `baseChart(w,h,margin)`,
`drawYAxis`, `drawXAxisCategorical`, `scaleLinear`, `niceTicks`, `pathFromXY`,
`renderBarChart` (generic vertical bar chart used for 4 different charts above), and
`el()`/`htmlEl()` (namespaced SVG/HTML element builders). None of this uses a chart
library — it is what EDGELOG's own `index.html` already does (pure inline SVG), so the
prototype is idiomatically consistent with the house style, not a foreign pattern.

### 2.5 The exit-price reconstruction gotcha (read this before touching fill prices)

The generator does **not** trust "last bar of the session ⇒ exit fills at that bar's
close" — that heuristic is **wrong** for this engine's exit logic. From
`tools/noise_research.py`'s `run_noise2._simulate_session` (`tools/noise_research.py:131`):
fills queued from a signal on one bar's close get **executed on the following bar**
(`STEP A`, `tools/noise_research.py:159`), and only if nothing has fired by the session's
last bar does the `STEP E` EOD backstop (`tools/noise_research.py:233`) force-flatten at
that bar's close. So a VWAP-cross signalled on the **second-to-last** bar of a session
defers its fill to the **last bar's OPEN**, not its close — the naive heuristic
mismatched one real trade by 85.5 points before this was caught.

**The fix used (cost-inversion):** the engine already returns net PnL in points per
trade. Since `pnl = (exit_px - entry_px)` for a long (or the mirror for a short), and
gross = net + cost, the exit price can be reconstructed exactly:

```
gross_pts = net_pnl_pts + cost_pts
exit_px   = entry_px + gross_pts   (long)
exit_px   = entry_px - gross_pts   (short)
```

This is the *exact* fill price the simulator used — not an approximation — because it
inverts the same arithmetic the simulator ran forward. `tools/build_visual_report.py`
(STEP 3) does this for every trade, then runs an informational QA check: the
reconstructed `exit_px` must equal either that bar's OPEN or its CLOSE (the only two
legal fill prices under this engine's exit modes) — the generator's own log line reports
`exit price matches bar OPEN or CLOSE for N/total trades (mismatches=X)`; this ran clean
(0 mismatches) across all 3,389 trades when last generated. **Any Phase A implementation
that needs a trade's exit price for a marker must use this same cost-inversion approach
(or pull the true fill price straight from the engine's trade tuple, if the engine is
changed to carry it) — do not assume "last bar of session = close".** This is a general
engine-fill-modeling lesson, not specific to NOISE 1.0; check each strategy's own
`_simulate_session`-equivalent exit-timing logic before assuming close-fills.

---

## 3. PHASE A — in-app trade chart (RECOMMENDED FIRST)

### 3.1 Design

Add a 🕯 button to each row of the existing per-trade blotter table — the **▦ TRADES**
panel that already exists inside the equity-curve expand modal (`window.expandEquity`,
opened from the run report's champion equity chart). Clicking 🕯 opens a chart showing
that trade's session candles with overlays: reuse `window.expandChart` (a simpler,
already-existing modal shell — see §3.2b) to host a single `candlestickChart()` SVG for
that trade, using the same `{bars, overlays, markers}` contract as the prototype.

### 3.2 What already exists to build on (file:line, read these before writing code)

**(a) How the blotter is loaded today.** The web calls a runner command named
`get_blotter`. Dispatch: `api/runner.py:763-772` —

```python
if action == "get_blotter":
    from api.blotter import load_blotter_rows
    ...
    res = load_blotter_rows(ROOT, doc.get("payload") or {}, log)
```

`load_blotter_rows` (`api/blotter.py:144-217`) first looks for a cached CSV at
`{root}/blotters/run{id}_{inst}_{tf}.csv`, and if none exists, regenerates it by
re-running the champion strategy via `champion_blotter` (`api/blotter.py:13-48`), which
calls `augur_engine.run_backtest(..., return_trades=True)` and returns rows shaped like
`{trade_no, entry_time, exit_time, hold_bars, entry_px, exit_px, pnl_pts, pnl_usd,
cum_usd}`. **Caution for Phase A**: `champion_blotter`'s `exit_px` is currently just
`close[xb]` (`api/blotter.py:46`, `xb` = exit bar index) — the SAME naive
"exit-bar-close" assumption §2.5 found wrong for NOISE 1.0's VWAP exit. Whether this
actually produces a wrong price depends on each strategy's own exit-timing logic
(a strategy that always closes exactly at its last computed bar would be fine); it was
not verified strategy-by-strategy here. If Phase A markers need to be pixel-accurate
against the real fill, re-check this function against the target strategy's engine
logic, or reuse the cost-inversion approach from §2.5.

On the web side, `index.html` calls this via `_runCmd('get_blotter', B)` at
`index.html:3300` (inside `expandEquity`'s `_fetchBlot()`), and renders the result as an
HTML table via `renderBlot()` at `index.html:3229-3238` — **this is the exact function
whose row markup (`index.html:3237`) needs a new `<td>` with the 🕯 button**. Each row
already carries `entry_time`/`exit_time`/`entry_px`/`exit_px`/`side` implicitly via its
bound `x` object (`_et`, `_xt2`, `_ep`, `_xp` — see the `_applyBlot` mapper at
`index.html:3277`); the new button's `onclick` needs the trade's date (for the session
window) plus those same fields to pass through to the new chart command.

**(b) The existing expand-modal machinery to reuse.** Two modal builders already exist
in `index.html`:
- `window.expandChart(title, svgHTML, opts)` (`index.html:2764-2801` and on) — the
  simpler, generic one: takes a title string and a raw SVG/HTML string, wraps it in a
  fullscreen dark modal with crosshair + tooltip + a CLOSE button. **This is the right
  one to reuse for a single-trade candle view** — pass it the SVG that
  `candlestickChart()` returns (as `outerHTML`, same pattern as the existing 2B/2C
  config-space caller at `index.html:2983`).
- `window.expandEquity(host)` (`index.html:3000` onward) — the heavier, purpose-built
  equity-curve explorer (pan/zoom/scale-y, the ▦ TRADES blotter panel itself,
  category-menu column sorting). This is the modal the 🕯 button will live INSIDE (as a
  row action in its blotter table), not the one to open when it's clicked.

**(c) Where a new runner command would be registered.** Runner command dispatch is a
sequence of `if action == "...":` blocks in `api/runner.py`, immediately following the
`get_blotter` block (`api/runner.py:759` onward — see also the `reconcile` command at
`api/runner.py:741-759` for another example of the same pattern: parse `doc.get("payload")`,
call a plain function, write `res` back via `ref.update(...)`). Propose a new command,
e.g.:

```python
if action == "get_bars":
    from api.bars import load_session_bars   # new module, mirrors api/blotter.py's shape
    try:
        res = load_session_bars(ROOT, doc.get("payload") or {}, log)
    except Exception as e:
        res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    ref.update({"status": "done" if res.get("ok") else "error",
                "result": json_safe(res), "finishedAt": time.time()})
    n += 1
    continue
```

`load_session_bars(root, payload, log)` would take `{master/instrument, timeframe,
session, source, date_from, date_to}` (a single session window — see the payload-size
math in (d) below), call `augur_engine.data.find_master` +
`load_master_arrays(master, date_from=..., date_to=...)` (both already used by
`api/blotter.py` — see `api/blotter.py:7`), and return
`{ok, bars: [{t,o,h,l,c,v}, ...]}` — exactly the `bars` shape `candlestickChart()`
expects (§2.4). Whether it also computes and returns `overlays` is the design question
in (d).

**(d) Strategy-specific overlays: emit them from the engine, don't recompute in the
browser.** NOISE 1.0's UB/LB bands are `ref_price * (1 ± band_mult * sigma)`, where
`sigma` comes from a **14-session rolling lookback** (`FROZEN["lookback"]` in
`tools/build_visual_report.py:45`) — i.e. computing it for one session requires the
*prior 14 sessions'* worth of history, not just the bars in the window being charted.
Every strategy's overlay math will differ (some need rolling stats, some need
cross-session state, some need nothing). **Recommendation: have the backtest engine
optionally emit a per-bar overlay series** (keyed by whatever names that strategy wants
— `ub`/`lb`/`vwap` for NOISE 1.0, something else for another strategy) as part of
`return_trades=True` output, the same way it already returns bar-indexed trade tuples.
The browser then just plots whatever series come back — it never needs to know the
strategy's math. **Why not recompute in the browser**: the browser only has the bars in
the requested window; reproducing a rolling-sigma or any other multi-session-lookback
quantity would require re-fetching and re-deriving arbitrary amounts of prior history
per strategy, duplicating engine logic in JS that could drift from the Python source of
truth. A generic overlay-series contract (name → array, same length as `bars`) is also
exactly what unlocks the "any strategy" version of this feature — see §6.

**Payload-size math**: one RTH session on 5-minute bars = **78 bars** (09:30–16:00 =
390 minutes / 5 = 78). A view showing the trade's own session plus one session before
and after (±1 session, to see context) ≈ **234 bars**. At roughly 6 numeric fields per
bar (`t,o,h,l,c,v`) plus 2-3 overlay values, that is a few hundred bars × ~10 numbers —
trivially small for a Firestore command-doc round trip (contrast with the `get_blotter`
command's existing 1 MB Firestore doc cap and its `MAXR=6000`-row truncation for
multi-thousand-trade blotters, `api/blotter.py:162` — nowhere near that scale here).

### 3.3 What Phase A does NOT need to solve

Multi-strategy overlay math, a generic strategy-agnostic renderer, and click-through
from the equity curve are all real improvements but are NOT required to ship a first
version — ship it for one strategy family first (reusing NOISE 1.0's or another
in-book strategy's existing overlay computation), prove the modal/runner-command path
end to end, then generalize.

### 3.4 WHAT SHIPPED (v71.16, 2026-08-08) — read before extending Phase A

**Backend.** `api/bars.py` → `load_session_bars(root, payload, log)`, registered as the
`get_bars` runner command (`api/runner.py`, immediately after `get_blotter`). Payload:
`{instrument, timeframe, session, source, entry_time, exit_time, pad_sessions=1}`. It
resolves the master with `champion_blotter`'s exact fallback chain, loads a
calendar-padded window (`pad_sessions + 5` days each side so weekends cannot starve the
padding), groups bars by session date, keeps the trade's session ±`pad_sessions`, and
returns `{ok, bars:[{t,o,h,l,c,v}], overlays:{vwap:[...]}, entry_idx, exit_idx,
meta:{master, source, sessions, n}}`. VWAP is session-anchored and re-anchors per session
(verified: it resets across a session boundary rather than carrying the prior day's
running average); it emits `null` for a session whose bars carry no volume.

**The §2.5 exit-price bug was live in the real blotter, and is now fixed.** Inspecting the
engine settled an open question §3.2(a) left open: `run_backtest(return_trades=True)`
returns whatever tuple each strategy plugin emits, and the shape is **not uniform** —
two families exist:
- 5-tuple `(entry_bar, exit_bar, pnl_pts, side, entry_px)` with `side` = `1`/`-1` —
  ORB_3_0/3_1, AOSTOCH, BBRSI, EMAX, DRIVE, all ENGUQ variants.
- 3-tuple `(entry_bar, exit_bar, pnl_pts)` — legacy ENGU_1_1_x / ENGU_1_3_x. No side, no
  entry price.

**Neither family carries a true exit fill price**, so §2.5's cost-inversion is the general
answer, not a NOISE-1.0 workaround. `champion_blotter` now reconstructs
`exit_px = entry_px ± (pnl_pts + cost_pts)` and emits a `side` column (from `t[3]`, or —
for the 3-tuple family only — inferred by which direction's implied exit lands nearer the
exit bar's close). Measured impact: on ORB_3_1 / NQ 5m / 2010-2026, **3,397 of 4,065
trades (83.6%) had a different exit price than the old `close[xb]`** — the blotter's EXIT
PX column was simply wrong for most trades that exit on a stop or target.

**Cache caveat (deliberate, not a bug).** `side` was appended to `FIELDS` so old blotter
CSVs still read fine, but blotters cached before this fix (on disk under `blotters/`, and
in the browser copy) still hold the naive exit price. The candle modal detects this (the
row has no `side`) and says so in its subtitle rather than drawing a wrong exit dot
silently; Shift+click TRADES regenerates. Nothing auto-invalidates the caches.

**Frontend.** `window.candleSVG(bars, overlays, markers, opts)` sits immediately above
`window.expandChart` in `index.html`. It is a re-port of the prototype's
`candlestickChart()`, not a copy — the prototype builds SVG DOM nodes via helpers
(`el`, `scaleLinear`, `niceTicks`, `pathFromXY`) that do not exist in `index.html` (`el`
there is `getElementById`), so this version returns an **SVG string** (what `expandChart`
takes) and carries its own local scale/tick/path helpers. It also went slightly beyond the
prototype: `overlays` is iterated **generically** as `{name: [num|null, ...]}` rather than
hardcoding ub/lb/vwap — this is the §3.2(d)/§6 overlay contract, so any strategy series
added later draws with no JS change — and multi-session windows get dashed session-divider
lines plus a bold `M/D` x-label at each session start (bare `HH:MM` repeats once per day
otherwise). The 🕯 button lives in each `renderBlot()` row inside `expandEquity`;
`_openCandles(x, glyphEl)` fetches `get_bars` and opens `expandChart`. Since v71.27
(shipped in the v71.23 bundle, logged at 71.27): a per-bar OHLC hover readout in the
modal's ctl row (time · O/H/L/C · V · every overlay value, generic over overlay keys),
the 1A blotter meta line and candle subtitle name the config ("champion config" — the 1A
blotter is always the crowned config), and the 2A compare-explorer blotter column headers
render cfg-numbered series as "config N · 2B RANK N" (config N = the RANK N column in the
2B CONFIGS card) instead of the raw `#cfgN` id.

**Deliberately NOT done** (§3.3 said to ship one strategy first, then generalize):
- **Strategy-specific overlays (UB/LB bands etc.) are not emitted.** Only the generic
  session VWAP ships. The renderer already accepts any series; what is missing is the
  engine side of §3.2(d) — `return_trades=True` emitting a per-bar overlay series. That is
  the single highest-value next step and it unlocks every strategy at once.
- Session grouping is by **calendar date**, which is correct for RTH but would split an
  overnight/ETH session at midnight. Revisit if this is pointed at an ETH session.
- No click-through from the equity curve, no keyboard next/prev trade, no overlay toggles
  (§6 suggestions, still just suggestions).

**Two render bugs were caught only by LOOKING at a real render** (v71.19) — worth repeating
as method, since both passed every structural assertion: on a multi-session window the bold
`M/D` session label and the nearest evenly-spaced `HH:MM` tick printed on top of each other,
and the session-anchored VWAP was joined straight across the overnight gap, drawing a move
that never happened. Fixed by letting a date label suppress a clock label within half a slot
of it, and by breaking every overlay path at a session boundary (and at any null).
`tools/candle_render_check.py` renders a real `get_bars` payload through the shipped
`candleSVG` → `expandChart` path in headless Chrome and screenshots it — run it after
touching the drawing code, because a DOM-count assertion will not catch a collision.

**Verification actually run** (not inferred): `python tools/preflight_boot.py` → PASS;
`tools/candle_probe.py` (promoted out of the volatile scratchpad per the
`edgelog-scratchpad-volatility` lesson) boots `index.html` in headless Chrome and asserts
`candleSVG` against synthetic single-session, 3-session, empty-bars and empty-markers
cases — session dividers, bold `M/D` labels, null-tolerant overlays. `load_session_bars`
was exercised against the real NQ 5m RTH master (201 bars over 2018-06-29..2018-07-03).
**Verified end-to-end in the live logged-in app** (2026-08-08, runner v71.19): run #202
(NOISE 1.0, 5,616 trades) → expand 1A → ▦ TRADES → 🕯 on trade #5616 fired `get_bars`
through Firestore to the runner and opened the modal with real candles (07/15 + 07/16
sessions, divider, per-session VWAP, held-window shade, entry ▼ / exit dot, correct
"SHORT · net -$1,636 · master: NQ 5m RTH - no-adj" subtitle). Runner-side blotter
auto-saves made after this ship (run #202 onward) already carry `side` + the corrected
exit price.

---

## 4. PHASE B — TradingView bridge

### 4.1 Design

A button (likely alongside the 🕯 button, or on the run report itself) that:
1. Generates a **Pine v5 snippet** with the run's trades **hardcoded** as labels/boxes
   — literal entry/exit timestamps and prices baked into the script as data, not
   re-derived from indicator logic.
2. Copies that snippet to the clipboard.
3. Opens a TradingView chart at the right symbol/interval via URL, e.g.
   `https://www.tradingview.com/chart/?symbol=CME_MINI%3ANQ1%21&interval=5`.

### 4.2 What TradingView's URL API can and cannot do

**CAN**: set the chart's **symbol** and **interval** via query parameters (confirmed
pattern: `?symbol=EXCHANGE%3ATICKER&interval=N`). **CANNOT**: auto-inject a Pine script
into the editor, or auto-add an indicator/strategy to the chart — TradingView's URL API
has no parameter for that. **Pasting into the Pine Editor is unavoidable** — the button
can only get the user to the right chart and put the right text on their clipboard; they
still paste it into Pine Editor → Add to Chart themselves. State this plainly in the UI
(a one-line "paste this into Pine Editor" instruction next to the copy button) so it is
not a broken promise.

### 4.3 Why hardcode the trades instead of pasting the strategy port

EDGELOG already has Pine ports of strategies in `pine/*.pine` (e.g. `pine/ORB_1_0.pine`,
`pine/ENGUQ_1M_1_0.pine`, `pine/NOISE`-family if/when ported). Pasting one of those and
letting it **re-derive** its own entries on the TV chart is tempting but wrong for this
use case: a re-derived strategy **hides fill differences** — if TV's Pine engine fills a
trade one bar later, or its data has a slightly different tick, the re-derivation will
silently produce a *different* trade instead of showing you where it diverged. **Hardcoding
the trades (entry/exit timestamp + price, taken directly from EDGELOG's own backtest
output) exposes exactly those differences** — you see EDGELOG's fill sitting at the price
EDGELOG says it filled at, on TradingView's own candles, so any gap between the two
platforms' data or fill assumptions is immediately visible. **This is precisely the
reconciliation use case** the owner asked for: not "does this strategy also work on TV"
(that's what the Pine ports are for) but "do these two platforms agree on what actually
happened."

### 4.4 Relationship to the existing reconciler

This complements, not duplicates, `augur_engine/reconcile.py` (`run_reconcile`,
`augur_engine/reconcile.py:475`) and `tools/reconcile.py`, wired into the web at
**Settings ▸ GENERAL ▸ OPEN RECONCILER** (shipped v48.9, `index.html:756`) and dispatched
via the `reconcile` runner command (`api/runner.py:741-759`). The existing reconciler is
**numeric/automated**: paste an exported TV or NinjaTrader trade list, and it reruns the
same strategy on the same master and diffs it trade-for-trade (matched %, total-PnL Δ,
auto-diagnosis of tz/DST offset, fees, ETH-vs-RTH, contract rolls, fill-model, side
flips). The Phase B Pine bridge is **visual/manual**: instead of a text diff, you *see*
EDGELOG's fills drawn on TradingView's own candles, which is what the owner wants for
the "assess by looking at price action" half of the ask (§1) — the automated reconciler
tells you THAT something is off and gives a first-pass diagnosis; the visual bridge lets
you look at exactly WHERE and confirm the diagnosis (or catch something the auto-diagnosis
missed) with your own eyes on the real chart.

---

## 5. PHASE C (optional) — static PNG/SVG per-trade export

Attach a static image export of a trade's candle chart to a saved run report, so the
chart survives without needing the live app (e.g. for sharing, or archiving a
particularly instructive trade). Since the charts are already pure SVG, this is
"serialize the SVG string" (trivial) plus, if a raster PNG is wanted, a headless-Chrome
render step similar to what `tools/preflight_boot.py` already does for boot-checking
`index.html` (same technique, different target). Not designed further here — genuinely
optional, lowest priority of the three phases.

---

## 6. SUGGESTED EXTRAS (suggestions, not requirements)

**Status update (v71.54, 2026-08-09):** most of this list SHIPPED, owner-driven. The candle
modal is now a viewer: PREV/NEXT + arrow-key stepping through the blotter's current sort
order, a TOP 10 winners/losers jump menu, drag-across-candles zoom (+ TRADE/FULL buttons,
double-click reset — client-side re-render of the cached bars, no refetch), SAVE PNG (CSS
vars resolved to literals before rasterising, 2x scale), per-trade bars cache + quiet
neighbour prefetch so stepping is instant. Still open from this list: click-through from
equity-curve points, overlay toggles, and the §3.2(d) engine-emitted strategy overlays.

These are ideas, not a spec — evaluate/design each on its own if pursued:

- **Click-through from any equity-curve point** to that trade's chart (from inside
  `expandEquity`'s pan/zoom view, not just the blotter table rows).
- **Keyboard next/prev trade** inside the candle modal (arrow keys stepping through the
  blotter in PnL or chronological order).
- **A "worst 10 trades" quick-filter** on the blotter table (reuse the existing
  win/loss column-menu filter pattern at `index.html:3239-3256`, which already supports
  a sort+filter menu per column).
- **Overlay toggles** (bands / VWAP / stop) so a busy chart can be decluttered.
- **Rendering ANY strategy's overlays** via the generic overlay-series contract
  described in §3.2(d) — the real unlock that turns this from "a NOISE 1.0 demo" into
  "a feature every strategy gets for free."

---

## 7. HOUSE RULES the implementer must follow

Pulled from this repo's `CLAUDE.md` — read the full file, this is not exhaustive:

- **Pure SVG, no chart libraries.** Every existing chart in `index.html` (and the
  prototype) is hand-built inline SVG with vanilla JS helpers (`el()`, `scaleLinear()`,
  etc.) — no D3/Chart.js/etc. Stay consistent.
- **NEVER put a raw apostrophe inside a single-quoted JS string in `index.html`** — it
  terminates the string and white-screens the whole app. This applies to CHANGELOG note
  text and any UI copy you add (e.g. write "does not" / "cannot", never "doesn't" /
  "can't", inside single-quoted strings).
- **Bump `const VERSION` by 0.1** (`index.html`, currently a single top-level `const`)
  **and prepend a `{v,date,notes:[...]}` entry to the `CHANGELOG` array** immediately
  below it, on every push. `git fetch` + re-read the current `VERSION` first — do not
  assume the next number; another session may have pushed since you last looked
  (multi-session repo).
- **The pre-push preflight boot gate must PASS.** A `git push` runs
  `tools/preflight_boot.py` via the `pre-push` hook automatically; it boots `index.html`
  headlessly and checks it actually rendered. Run it by hand any time:
  `python tools/preflight_boot.py`. Never `git push --no-verify` unless the owner
  explicitly asks for it.
- **`git add` only your own files** (multi-session protocol — this repo's working tree
  is sometimes shared by more than one active Claude session). `git diff` your files
  before committing; if a file you need to touch already carries uncommitted edits you
  did not make, stop and wait rather than bundling someone else's half-finished work.
- **Verify the rendered result in the live logged-in app — never assume from code.**
  The in-app preview browser is NOT signed in; use the real authenticated Chrome
  session to check a UI change actually renders (per this project's
  `edgelog-verify-via-chrome` convention). For a deployed change, load
  `https://xrider3333.github.io/EDGE-LOG/?fresh=<timestamp>` and read the console for a
  clean boot (`[LOAD] SCRIPT START … RENDER`, no `SyntaxError`/`is not a function`).

---

## Appendix — file inventory for this feature

| File | What |
|---|---|
| `docs/VISUAL_TRADE_REPORT.md` | this doc |
| `docs/samples/noise_visual_report.html` | the working prototype — source of truth for the SVG drawing code (`candlestickChart()` and friends), see §2.4 |
| `tools/build_visual_report.py` | the data-build half of the prototype's generator (JSON only — see §2.2's note on what was and was not promoted) |
| `api/blotter.py` | existing per-trade blotter load/regenerate (`load_blotter_rows`, `champion_blotter`) — Phase A's `get_bars` should mirror this shape |
| `api/runner.py` | runner command dispatch — `get_blotter` (:763) and `reconcile` (:741) are the patterns to copy for a new `get_bars` command |
| `augur_engine/data.py` | `find_master` / `load_master_arrays` — what any new bar-fetching command will call |
| `augur_engine/reconcile.py`, `tools/reconcile.py` | the existing numeric reconciler (Phase B complements, not replaces) |
| `pine/*.pine` | existing strategy Pine ports (Phase B's hardcoded-trade snippet is a NEW small script, distinct from these) |
