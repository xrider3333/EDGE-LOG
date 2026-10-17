# QWEN LAB - the local Qwen as a strategy tester

Owner 2026-10-15 (MANAGER #130): "using qwen to read but not push buttons on EL or develop the backtest (which is in
python not qwen) doesn't make sense." So the local model (qwen3.8:27b in Ollama, `tools/local_llm.py` is the house
client) now proposes an idea, writes a strategy plugin, and `tools/qwen_lab.py` gates it, runs it and reports it.
Built by CUSTOM-ML. Tests: `tests/test_qwen_lab.py`.

## The rule

**PYTHON COMPUTES EVERY NUMBER.** Qwen's text never supplies a number that is reported. The four numbers, the map
read, trade counts and the validate bar are computed by the harness (with the house helpers) from the engine's trade
list and the pinned master. Qwen sees them as tool results. Posts and preregs are composed by the harness from those
computed dicts; Qwen's free text appears only in the prereg's quoted hypothesis / mechanism and is labelled as such.
Its stated prior (yearly Sharpe, trades a year) is a pre-data INPUT and is labelled that way wherever it appears.

## What one session does

One session = one idea from one SOURCE. The sources ROTATE (MANAGER #133, 2026-10-15 - the lab's first #8 runs repeated
two lanes' closed work, so it must not loop on one source):

1. **the owner's scalper ask** - a profitable short-hold NQ / ES strategy. Qwen gets the hard facts up front (the 10-12
   scalp hunt, memory `edgelog-scalp-hunt-1012`): 59 NQ 1m short-hold cells dead (micro opening range, open drive,
   PDH/PDL, range burst, VWAP cross, sweep-reclaim, chop-fade, volume ignition, box break) plus BALANCE VWAP fade,
   REVERT 10s fades and MISC range fades; best gross win rate at ZERO cost 52.1%; median gross $6.60 a trade against a
   $15.66 NQ round trip (0.783 pt), ES 0.613 pt; the only short-hold earner is NOISE's band on 2m bars (4-12 min holds,
   win rate 17-25%, payoff ~4x) - so a scalp must target a large payoff per trade or long-tail winners, never a high
   win rate (fixed-target scalps are dead). Its Stage A (and validate job) charges that basis: **NQ 0.783, ES 0.613**.
   The NQ 2m master (`NOADJ_NQ_2m_RTH.csv`) is pinned for it.
2. **Qwen's own idea** - a new NQ / ES intraday mechanism, checked against `dead_list()` before `propose` (and by the
   harness at `propose` and again at Stage A).
3. **a reading-shelf paper MANAGER opened** (`C:\EdgeLog\manager\papers\reading_shelf.html`). MANAGER #142: #30
   was picked three times, so the shelf is now explicit. A paper the lab has run a SANE PRE-WF Stage A on is CLOSED
   (`closed_shelf` in `state.json`, seeded with 8, 30 and every shelf paper already run) and the picker never takes it
   again. MANAGER #153b: the closure happens only AFTER the broken-plugin check passes - a `BROKEN PLUGIN` run (the
   10-15 QL_TOM_CALENDAR_NQ on #34: 3 trades in six years) or a duplicate never closes the paper. A closure the older
   harness made for a run that was not a verdict is UNDONE when the lab loads `state.json` (moved to
   `shelf_closures_undone` with the reason; on the live state that re-opens #34, which MANAGER opened 10-15), and the
   seed of "papers the lab already ran" takes only `done_ideas` rows that reached a sane PRE-WF Stage A (`PRE-WF DONE`
   / `STAGE A DONE` - not a model that finished before Stage A, a dead-list refusal or a crash). The shelf slot runs ONLY on papers MANAGER opens: `python tools/qwen_lab.py shelf-open 31 32` appends a dated
   line to `C:\EdgeLog\qwen_lab\shelf_open.txt` (a line of bare numbers works too); the running lab reads it at its
   next pick, so there is no state.json race. An open overrides the skip list (2, 3, 6, 8, 10, 12-19, 21, 22, 26, 27,
   29), the shelf's live / dead marks and ledger citations; a paper re-opened after it was closed is open again. While
   no paper is open the shelf slot is skipped and the rotation is scalper -> own -> scalper -> own.
   **MANAGER closes a paper with `python tools/qwen_lab.py shelf-close 31 [32 ...] [--why "..."]`** (MANAGER #147) -
   it appends a dated `YYYY-MM-DD HH:MM:SS CLOSE 31  # why` line to the same file, so nobody hand-edits it. The
   LATEST line naming a paper is authoritative: a close after an open = closed, an open after a close = open; a line
   of bare numbers (or `open: ...`) still means open; `# ...` is a comment. A line is `[YYYY-MM-DD [HH:MM[:SS]]]
   [open...|clos...] n [n, ...]` (`closing 31`, `closes 30`, `2026-10-16 CLOSE 32` all close); ANY other line is
   ignored - it never opens a paper - and `status` / `shelf-open` / `shelf-close` print it as a WARNING. An UNDATED
   line is older than any closure the lab recorded (review round 3: it used to take the file's write time, so the next
   `shelf-close` of another paper re-opened a paper the lab had run) - re-open a paper the lab ran with `shelf-open N`
   (dated). It never touches `state.json` (the lab's
   own closures stay there) and uses the lab's home (`--home`, else `QWEN_LAB_HOME`, else `C:\EdgeLog\qwen_lab`).
   `--idea N` refuses a paper MANAGER closed, and a recorded next pick whose paper was closed after it was posted is
   dropped and picked again. `status` lists the papers closed by the lab, the papers closed by MANAGER (with the
   time) and the open ones.

Each pick is recorded in `state.json` (`next_pick`, `picks`, `rotation_index`) and posted to MANAGER as harness text,
`QWEN LAB next pick: ...`; after every idea the harness records and posts the following pick. `--idea N` forces a shelf
paper (refused when it is closed - `shelf-open N` re-opens it), `--source scalper|own|shelf` forces a source,
`next-pick` records and posts without running.

Qwen talks to the harness only through these tools:

| tool | what it does |
|---|---|
| `read_repo_file(path, start_line)` | read-only, shared checkout (and the lab's plugin folder) only; secrets / `.env` / key / credential / `.git` / registry paths refused; 12k characters a call; key-looking lines redacted (`local_llm.redact_lines`) |
| `list_strategies()` | house plugin files + the lab's own |
| `dead_list(query)` | the closed rows of `RESEARCH_LEDGER.md` section 2, compact |
| `ideas()` | this session's source, its brief, the rotation, the open shelf papers, and every idea the lab already ran (name, families, one-line rule, verdict) with the mechanism-family map |
| `shelf_ideas()` | the papers still open to the lab |
| `propose(name, hypothesis, mechanism, prior_sharpe_yearly, trades_per_year, instrument, timeframe, first_signal_bar, entry_fill, time_stop_bars)` | recorded PRE-DATA; refuses an idea the lab already ran (MANAGER #148/#158: same name, family, near-copy or the SAME normalised rule text - no slot used) and runs the dead-list check; the timing contract is REQUIRED: `first_signal_bar = {"index": k, "clock": "HH:MM"}` (TTM #144), `entry_fill = {"at": "open"/"close"/"level", "bar": k or -1, "clock": "HH:MM"}` and `time_stop_bars = N` (0 = none) (MANAGER #160b/#162); may be revised (3 proposals) until the map reads it inside `run_stage_a`, then frozen (the plugin freezes too once the prereg is posted) |
| `write_plugin(name, code)` | safety gate, then the dedupe on the plugin's LF sha256 (a plugin byte-identical to one ANY run idea ran, or to the one THIS idea already ran, is refused without using an attempt - MANAGER #158/#162/#153a), then written to `augur_strategies/qwen_lab/<name>.py` in the WORKTREE, then contract (incl. the entry-fill, time-stop and trade-rate checks) + look-ahead in the sandbox |
| `run_stage_a(name)` | the dead-list gate, the power-first map (recorded, not a stop), the auto prereg naming both stages posted to MANAGER, the PRE-WF Stage A, and the WF Stage A only if promoted; returns the computed numbers. Refuses a proposal missing any timing-contract field (call `propose` again - a proposal the map or a prereg froze only records the missing fields, written into the prereg / its addendum), a plugin gated by an older harness (`gates_version` < 4: `write_plugin` again) - an in-flight idea from before a gate never runs "not checked" - a plugin whose sha another run idea ran, and a broken-plugin "retry" whose sha this idea already ran |
| `queue_validate(name)` | the 900-trial Auto-Validate, only past the bar |
| `finish(note)` | ends the session (the note is stored, never posted) |

Tool calling: **native Ollama `/api/chat` tool calls work with qwen3.8:27b** (Ollama 0.40.4, verified 2026-10-15,
`think: false`). A strict JSON-action fallback (`{"tool": ..., "arguments": {...}}` in plain text) is parsed too; each
idea's `protocol` block counts which one the model used.

## The gates, in order

MANAGER #134 (2026-10-15, owner: the lab must actually TEST - its first three ideas all closed at the map with no
backtest): gates 1-5 are HARD; the power-first map (6) is recorded and posted but no longer stops an idea; every idea
that passes 1-5 gets the PRE-WF Stage A.

1. **Safety gate** (AST, before the code is written, imported or run). Imports: `numpy`, `pandas`, `math`,
   `from augur_engine.rolls import seam_days` and `from augur_engine.session_calendar import <name>` (by name only:
   `session_calendar`, `session_dates`, `session_index_in_month`, `days_to_month_end`, `is_last_n_sessions_of_month`,
   `is_first_n_sessions_of_month`, `week_of_month`, `exchange_sessions`, `is_exchange_session` - see "Dates and the
   session calendar" below) only. Refused: `open`, `exec`, `eval`, `compile`, `__import__`,
   `globals` / `locals` / `vars`, `getattr` / `setattr` / `hasattr`, `print`, `type`, classes, `global`, attribute
   assignment (no monkeypatching numpy), any dunder or leading-underscore attribute, `'__'` in any string, bytes,
   module-level code other than imports / constants / functions, and the I/O surface of numpy / pandas (`np.load`,
   `np.save*`, `tofile`, `memmap`, `np.lib`, `ctypes`, `ctypeslib`, `pd.read_*`, every `to_*` writer, `query`, `eval`,
   `options`, `plot`, ...). **No state between runs (review round 4, MEMO2):** a same-bar-foresight rule whose trades
   were cached in a module-level `_SEEN = {}` keyed on the bar count passed the contract and the look-ahead audit -
   every audit variant ran on the same module object, so the real bars' answer was replayed to each perturbed run
   (pre-WF 7992 trades, 6311 winners net). The gate now refuses a module-level mutable container other than the
   contract dicts `DEFAULT_PARAMS` / `_AUGUR_MARKET` (a list / dict / set, `dict()` / `list()` / `set()`, a numpy /
   pandas object - use a tuple / number / string), a write into a module-level or imported name from a function (a
   subscript store / `del`, a mutating method call such as `.append` / `.update` / `.setdefault`, also through a method
   chain - `_C.get(k).append(x)` - and into numpy's own containers, `np.typecodes[...]`), and a mutable or call default
   argument. The gate is best-effort (an alias escapes it); the sandbox (2) is the guarantee. The reasons go back to
   Qwen.
2. **Sandbox** - the plugin only ever runs in a child process (`python tools/qwen_lab.py _sandbox`), never in the
   harness: secret-looking environment variables stripped, one thread, a wall-clock timeout, a 6 GB memory watchdog,
   restricted builtins (a guarded `__import__`, no `open` / `eval` / `exec` / `getattr` ...), and an audit hook that,
   while plugin code runs, blocks every file write, reads outside the Python / engine / roll-table folders, subprocess,
   socket, ctypes, registry, `os.*` file operations and new threads. Any blocked event fails the gate. The child
   re-checks the plugin's LF sha256 before it executes a line. **Every `run_backtest` call executes the compiled
   module into a FRESH namespace** (new globals, builtins, function objects and defaults) and calls that copy's
   `run_backtest` on private copies of its array arguments (`_sb_load_plugin`, review round 4) - no run can see
   another run's state, and nothing a plugin writes into its inputs reaches the harness's arrays; the engine reads the
   constants and the signature from the first execution. The same MEMO2 cache now fails the audit like the uncached
   rule (tests: a module-level cache and a mutable-default cache, both bypassing the gate). The Auto-Validate's runner,
   though, runs every trial in ONE process, so the contract also runs the plugin's first namespace on the synthetic
   bars, on a mirrored copy (same length, same first open) and on the bars again, against fresh runs
   (`_sb_state_check`): any difference is a hard failure "STATE BETWEEN RUNS".
3. **Contract** (sandbox): `STRATEGY_NAME`, `DEFAULT_PARAMS` with at least one RANGED numeric knob (a pinned file cannot
   be Auto-Validated), valid `ROLL_SIGNAL`; the synthetic battery of `tests/test_strategy_contract.py` (well-formed,
   5-field trades, deterministic, truncation no-look-ahead); a real-data smoke on the pinned master over the
   PRE-walk-forward bars only (2015-01-02..2016-06-30, through the engine and its roll guard; trade counts reported,
   never P&L); every SEARCHED knob value (`searched_values`): each ranged knob at its min and its max, and each other
   option of a multi-option `str` / `bool` knob (review round 4: options were never run). A `str`
   knob with several options is still warned (the validate searches every option - port trap 2). At most 8 searched
   knobs (`SEARCHED_KNOBS_MAX`; ranged numeric + multi-option str / bool): more is a hard failure - the contract and the
   look-ahead audit cover every one, so pin the rest (min == max, one option).
   **First-signal-bar contract (TTM #144).** QL_VWAPREVERT_NQ's prereg said signals start at in-session bar k >= 25,
   but its plugin fired from bar 20. So every proposal states `first_signal_bar` - the 0-based in-session index of
   the EARLIEST bar on which an entry may FILL, with the clock time of that bar's open (`{"index": 26, "clock":
   "11:40"}` on 5m bars; `propose` refuses a clock that is not that bar's open, an index outside the session, or a
   missing field - no slot used). The smoke reads each entry's in-session index FROM ITS OPEN CLOCK
   (`session_bar_index`: (minutes since 09:30) // bar minutes - the prompt's convention; review round 3: counting
   positions flagged a plugin that entered at 10:30 = bar 60 on 1m holiday sessions with missing bars, e.g.
   2015-02-16, where 10:30 is the 59th bar; `first_bar_violations`): any entry before `first_signal_bar.index` with
   the default knobs is a HARD contract failure, and Qwen gets the offending entries (bar, session bar, time, side)
   plus a `how_to_fix`. So is an entry before it at ANY ranged knob's min or max (review round 3: it was a warning, yet
   the Auto-Validate searches those values - the template's `range_bars` searched down to 3 fills from bar 4 (09:50
   open)): the pre-registered bar holds for the searched rule, Qwen narrows the knob or pre-registers the earliest
   searched bar, and the validate job's note names the bar. The PRE-WF Stage A checks
   EVERY entry again before any verdict: a violation there is not a verdict - the plugin goes back to Qwen like a
   broken plugin (same 2 fix retries, an ADDENDUM posted before each re-run; still violating -> `BROKEN PLUGIN
   (first-signal-bar contract: n entries before bar k)`). The prereg and its MANAGER post name the first entry bar.
   **Entry fill and time stop (MANAGER #160b / #162).** QL_TRENDN's text said 'time stop 12 bars' and the code held
   11 (it counted the entry bar as bar 1). So the proposal also states `entry_fill` - the price point of every entry
   (`{"at": "open", "bar": -1}` = the OPEN of the fill bar, bar -1 when the bar varies with the signal; `"close"`; or
   `"level"` for a stop / limit price inside the bar; a fixed `bar` k with its `clock`, checked by `parse_entry_fill`)
   - and `time_stop_bars` N with ONE convention: **exit at the CLOSE of entry bar + N, so exit_bar - entry_bar = N**
   (0 = no time stop). The smoke checks every entry against it (`entry_fill_violations`: 'open' = the entry price is
   its bar's open, 'close' = its close, a fixed bar = that in-session bar by the clock) and every exit against the time
   stop (`time_stop_violations`: a trade held MORE than N bars; the two off-by-one shapes read from the realised exits -
   no exit at entry bar + N's close while >= 3 and >= 20% exit at entry bar + N-1's close inside the session, or >= 3
   exit at entry bar + N's OPEN; the exit price is rebuilt from the entry price and the gross points, the engine's P&L
   plus the cost it charged). **The plugin's own time stop (review round 4):** a stated 6-bar stop the code ran as 4
   bars passed (368 of 379 real smoke trades exited at entry + 4, none at + 6), and so did an unannounced 6-bar stop
   with `time_stop_bars` 0 (the check returned at once for N 0). Now, when NO trade is held past h bars and >= 3 (>= 20%
   of the trades) exit at the CLOSE of entry bar + h inside the session (not at its last bar, not at a level), h is
   the plugin's time stop (`effective_time_stop`): h < N-1 fails "the plugin's time stop is h bars, the proposal
   states N", and with N 0 any h >= 1 fails "an undeclared h-bar time stop" (a clock exit a fixed number of bars after a
   fixed entry bar is the same thing - state it). Exits spread over several holds (a signal exit), a long stated stop
   that no trade reaches, stops / targets at a level and session-end exits never trip it (tests). **The entry fill at
   every searched knob value (review round 4):** the price point (open / close) is checked at every corner too
   (`entry_fill_corners`; a `fill_q` knob that moved the fill to the bar's close at its max passed) - the fixed bar is
   checked at the defaults only (a knob may move it; first_signal_bar holds the earliest). A violation is a HARD
   contract failure: Qwen gets the offending trades (`offending_entry_fills` / `offending_entry_fill_knob_values` /
   `offending_time_stops` - for EVERY time-stop shape, with bars held and the exit price against the bar's open and
   close; the pattern shapes used to return none - / `time_stop_patterns`) and a `how_to_fix`.
   **Trade-rate check (TTM #155, MANAGER #153a).** QL_TOM_CALENDAR_NQ stated 36 trades a year and its plugin made 2.
   The smoke's trade COUNT a year (`smoke_rate_check`) must be within 3x of the stated prior: more than 3x below it
   (or under 100 a year for a scalp idea) is a HARD failure at `write_plugin` - gate `contract (trade rate - TTM
   #155)`, before the look-ahead run and before any prereg; Qwen fixes the plugin or re-proposes an honest rate (the
   same file then passes). More than 3x ABOVE is flagged in the result and the prereg.
4. **Look-ahead** (sandbox): `tools/exec_feasibility_audit.py`'s file checks on the one file (hidden-knob sweep,
   fabricated metrics, gap-through stops, known leak knobs), then a **perturbation audit** on real PRE-walk-forward
   bars (2015-01-02..2016-06-30; 1m: 2015-07-01..2016-06-30): for 8 sampled trades, everything that did not exist at the
   fill is replaced - every later bar, plus the fill bar's high / low / close / volume for an open fill, or its close /
   volume for an intrabar fill - in two opposite phases, and the trade must not change (entry: bar, side, price; exit:
   bar and P&L). The sample is 8 trades spread through the window PLUS up to 4 of the shortest holds (exits on the
   entry bar first). An INTRABAR fill gets two more phases: the extreme it crossed is pushed further (a stop / limit
   level from bars <= k-1 fills at the same price; a level built from the fill bar's own high / low moves), and for a
   stop-type exit the other extreme is widened by 5 median ranges (catches a trailing extreme updated with the fill
   bar before the check, and a same-bar target checked before the stop). Added 10-15 after the first PRE-WF run:
   QL_ES_MOMBREAK v4 passed the 8-trade audit with an ATR over bars up to AND including the entry bar, used for a stop
   checked on that bar; the new phases catch it on real data and pass QL_MTP_NQ, QL_SCALP2M and the template.
   **Entry-bar inputs phase (TTM #145).** Those phases only see a level built from the entry bar when a sampled trade
   happens to exit ON that bar - a wider stop (3 x an ATR that includes the entry bar) passed them. A plugin reports
   only (entry, exit, P&L, side, price), so the levels and the size are read through the exit: for up to 6 sampled
   trades, the FIRST BAR AT RISK (the entry bar for an open fill AND for an intrabar stop / limit fill - only its open
   and the crossed level existed at that fill; the next bar for a close fill; an entry price equal to both the open
   and the close counts as a close fill) is re-drawn as a ONE-WAY bar from its unchanged open: its adverse extreme
   pushed 10, 30 (and 90) median bar ranges beyond its own with the other extreme pulled in to the open (an intrabar
   fill's price stays inside, and the extreme its stop / limit entry CROSSED stays past it by up to 0.25 median
   ranges, so an entry written 'high > level' still fills), then the favourable side mirrored - so only the levels on
   the pushed side can be crossed and a stop-first / target-first order never flips the exit between two pushes. Each
   push also puts that
   bar's close at a different place (15 / 85 / 50% of the way from the open to the pushed extreme) and its volume at
   0.37 / 1.9 / 1x the median; the deeper pushes replace every later bar (around the bar's new close). The entry must
   not change, and two pushes that both exit on that bar AT A LEVEL (not at its close, which an exit may read) must
   exit at the SAME price with the SAME P&L (a level known at the fill is crossed by both and fills at itself; a
   level or size that reads the bar's own high / low / close / volume, or a later bar, moves); a trade that exits
   there at a level on one push and not on that bar at all on the next, deeper one fails too, and so does a push that
   exits at that bar's (unchanged) OPEN when the real bars do not (a level known at the fill that is past the open books
   it on the real bars too; a stop hung off the entry bar's own favourable extreme - a chandelier from the session high
   INCLUDING the entry bar - is dragged past the open by the favourable push and books it on every push at the same
   P&L, which the level comparison cannot see: `leaks.py` L4, review round 4). The same phase then
   runs at every searched knob value (2 trades each - the Auto-Validate searches there; see the knob corners below).
   No level exit on that bar = inconclusive (no failure; a warning when no sampled trade was conclusive). Review round
   3: the phase had moved only the high / low, so a stop anchored at the entry bar's close, a close-to-close
   volatility that included it, a close fill whose stop read the next bar's close (`LEAKS` L1b / L1 / L3) and a stop
   entry with an ATR that included the entry bar (L2, intrabar entries were skipped) all passed - the tests now hold
   them. Review round 4: that re-draw pulled a stop / limit entry's crossed extreme in to EXACTLY the fill level, so a
   clean entry written with a strict test ('high > level') lost its fill on every push and failed as "the ENTRY itself
   changed" - the crossed extreme now stays past the fill (tests: strict and non-strict stop and limit entries, clean
   and leaky). A stop that scales with the entry bar's OWN range by >= 1x (stop = entry - 1.5 x that range) can never be
   crossed on that bar, so its trades are exactly those of a rule that sets the same level at the bar's close and
   checks it from the next bar - realisable, inconclusive by design (the tests prove the equality); at a knob value
   where the scale drops below 1x (stop_frac 0.25 -> 0.375x) it leaks, and the knob-corner pass catches it. The
   failure returns a `how_to_fix` (build levels and size from bars <= k-1 and bar k's open, `atr[k-1]`; trailing
   levels updated after the bar's check). Re-checked 10-16 (rounds 3 and 4) on copies of the lab's 10 gated plugins on
   real pre-WF bars, the request `write_plugin` builds: it still catches QL_ES_MOMBREAK v4 (6 of 6 trades conclusive);
   round 4's open check also fails QL_MOMDRIVE (both runs 'not promoted', so no verdict moves) - its chandelier takes bar
   j's CLOSE before bar j's low is checked, so a strong entry-bar close drags the stop past the open; the same file with
   the update after the check passes. It passes QL_MTP_NQ, QL_SCALP2M, QL_GAMMA_MOM, QL_VWAPREVERT_NQ v2, QL_GAMMA_ORB,
   QL_TRENDN and QL_NOISE2M_TREND at the defaults and at every knob corner, and QL_TOM_CALENDAR_NQ v8 (no level on the
   entry bar: inconclusive, with the warning). The look-ahead sandbox timeout is 3600 s (QL_NOISE2M_TREND on 2m bars
   took 508 s on a busy machine with the 4-knob corner pass; review round 4 runs every searched knob value).
   **Exits booked at a later bar's open (fix round 3, TTM's MOMDRIVE note).** An exit filled at bar j's OPEN (j after
   the entry bar) may not depend on what bar j did after its open. For up to 6 such trades (spread through the
   candidates; bar j not a doji) bar j is PULLED IN, never widened - its close moved to its adverse extreme (a long's
   low), then its favourable extreme pulled in to max / min(open, close); open, adverse extreme, volume and later bars
   unchanged - and the trade must still exit at bar j's open with the same P&L (`_sb_open_exit_phase`). A chandelier
   raised with bar j's close or high BEFORE bar j is checked, then booked at the open as a 'gap-through', moves; a
   stop-first rule whose bar opened through its target does not (a first, one-way re-draw that WIDENED the bar failed
   the clean stop-first template, so the adverse side is never extended).
   **Every phase at the knob corners (fix round 3).** Fill realism, the perturbation phases, the open-exit phase and
   the entry-bar phase all run again at EVERY searched knob value (`_sb_corner_audit` over `searched_values`: each
   ranged numeric knob's min and max - review round 4: it covered only the first 4 ranged knobs, so a leak at the 5th
   knob's max passed, and the lab's own 20261015-1044-shelf08 plugin has 5 - and each other option of a multi-option
   str / bool knob - a same-bar trail switched on by `trail_on=True` passed, every corner ran `trail_on=False`; 2
   perturbed trades, 2 open exits, 2 entry-bar trades each; more than 8 searched knobs fails hard) - a leak the default
   hides (a trail knob whose default never reaches the stop) is a hard failure "LOOK-AHEAD at the knob values the
   Auto-Validate searches ... at trail_k=0.25: ...". Re-checked 10-16 (fix round 3) on copies of the lab's 10 gated plugins on real pre-WF bars, the
   request `write_plugin` builds: QL_MTP_NQ, QL_SCALP2M, QL_GAMMA_MOM, QL_VWAPREVERT_NQ v2, QL_GAMMA_ORB, QL_TRENDN and
   QL_NOISE2M_TREND pass at the defaults and every corner (QL_NOISE2M_TREND 399 s), QL_TOM_CALENDAR_NQ v8 passes
   inconclusive (warning), QL_ES_MOMBREAK v4 and QL_MOMDRIVE still fail. Plus
   **fill realism**: every entry and exit price must sit inside its bar's range (a stop on a bar that
   opened through it must book the open; P&L must be side x (exit - entry)). `tools/gate_lookahead_audit.py` audits the
   ML gate's feature matrix; a Qwen plugin has no ML gate, so it does not apply. The tests prove the audit catches four
   leak shapes the static gate cannot see (next-bar close, same-bar close with an open fill, a whole-series percentile,
   an exit that peeks a bar ahead) plus a fabricated P&L. A failure returns `how_to_fix` hints by fill kind (open / intrabar /
   close). A file byte-identical to an earlier attempt that failed a gate is refused without using an attempt (the
   10-15 live run re-sent one leaking file three times verbatim).
5. **Dead list**: the proposal's name against closed family names (`ONDRIFT`, `XGAP`, ...), and its content words
   against each closed row (refused at >= 50% of the proposal's words with >= 5 shared). Lexical - it catches clear
   re-runs; Qwen also gets `dead_list()`. Re-run at Stage A on the frozen proposal. On top of the ledger, the lab's
   own closed families (`LAB_DEAD`) refuse any source's proposal that names them: **GAMMA** - gamma exposure, GEX,
   dealer gamma / dealer hedging (MANAGER #142: GAMMA r1 is dead in ledger rows 2.135-2.137, the lab's QL_GAMMA_MOM and
   QL_GAMMA_ORB lost, and gamma is an owner ask-first idea). They head every `dead_list()` answer.
   **Idea dedupe (MANAGER #148)** - QL_VWAPREVERT_NQ ran twice under one name with two different plugins. Qwen's
   first message (and `ideas()`, and a resume note before a proposal) lists every idea the lab already ran - built by
   the harness from `state.json` `done_ideas` + `aborted_ideas` and their `idea.json` files: name, mechanism families,
   one-line rule, verdict (the latest 25 listed; all of them checked). `propose` then REFUSES - with the reason, the
   matches and the list returned to Qwen, and WITHOUT using one of the 3 proposal slots (recorded in
   `idea.json` `dedupe_refusals`):
   - the same NORMALISED name (`QL_`, NQ / ES / MNQ / MES / RTH, version and timeframe tokens out:
     `QL_ES_MOMBREAK` = `QL_MOMBREAK_ES_V2` = `MOMBREAK`) - any source, since plugin files are keyed by name;
   - the same mechanism FAMILY as a run idea (map below; read from the name and from the mechanism, each on its own,
     never the hypothesis, where Qwen may name an idea it contrasts with);
   - a near copy of a run idea's rule that names no family: Jaccard of the SIGNAL / ENTRY clauses' content words
     (`signal_text`: the stop / exit / target / trailing / flat / one-trade clauses out, then house `keywords()`
     minus rule boilerplate) >= 0.45 with >= 6 shared words, against every plugin a name ran with. Re-calibrated 10-16
     on the lab's 11 real proposals: distinct pairs top out at 0.17 (QL_GAMMA_MOM vs QL_MOMDRIVE), a copy with a
     reworded parameter is 1.0; the lab's real REWORDED repeat (QL_TRENDN of QL_ES_MOMBREAK) shares only 3 signal
     words (0.27), which no word count can catch without refusing distinct ideas - the family map catches it. Review
     round 3: on the whole text, an inside-bar breakout that copied QL_MOMDRIVE's chandelier-stop sentence was refused
     at 69%; on the signal it is 0.25.
   - the SAME normalised rule text (`norm_rule`: case, punctuation and spacing out) as a run idea's mechanism - a
     short rule under the near-copy check's 6-word floor is still caught (MANAGER #158).

   **The plugin sha and RESUME (MANAGER #158 / #162).** 10-16 14:02: 20261016-1402-own re-proposed QL_TRENDN and gated
   the SAME plugin (LF sha256 `dbc02a2e...`) that 20261016-1342-own had run; the lab stopped at 14:09 with it open. Now
   `ran_ideas` records every plugin sha a run idea ran (its prereg, its addenda, its broken-plugin retries -
   `idea_ran_shas`), and `write_plugin` and `run_stage_a` refuse a plugin whose sha matches one before any Stage A
   ("the lab never runs the same plugin twice"). On RESUME (`run` picking up an open idea, the live lab's first step)
   `resume_duplicate` checks the open idea's plugin sha, then its normalised rule, then its name, against the run
   ideas: a match closes it `CLOSED AS DUPLICATE of <id> (same plugin sha | same rule | same name)` WITHOUT a run or a
   model turn (`close_duplicate`: event, a MANAGER post `QWEN LAB: <name> (<source>) - CLOSED AS DUPLICATE ...: NOT
   run`), records it in `aborted_ideas` - never in `done_ideas` - and the lab picks a fresh idea. Replayed 10-16 on a
   COPY of `C:\EdgeLog\qwen_lab`: 20261016-1402-own closes as a duplicate of 20261016-1342-own on the first step, the
   #34 closure is undone, and the next pick is shelf #34.

   The NAME check covers every run idea. The family and overlap checks skip a run that was NOT a verdict on the idea -
   a `BROKEN PLUGIN` or an operator `ABORTED` run (MANAGER #139: a broken plugin is a bug) - and, for a session on a
   shelf paper MANAGER RE-OPENED after the lab ran it (`shelf-open N` over the lab's closure), that paper's own
   earlier runs; such a mechanism may be retried under a new name (the list marks those runs "NOT a verdict"; their
   families are not counted as taken). An idea that CLOSED but never got its `done_ideas` row (the run was killed
   between the close and the bookkeeping) is still read from its folder, and the next `run` records it (result post
   and row) before anything else.

   A shelf paper the lab ran is closed by the shelf list; a NEW paper (or the scalper / own source) whose mechanism
   repeats a run idea is refused here. The family map (`IDEA_FAMILIES` in `tools/qwen_lab.py`) - every pattern is a
   family-SPECIFIC phrase; "momentum", "breakout", "VWAP", "range", "month", "first hour", "Tom" or "or breaks"
   alone match nothing, and a phrase in a FILTER / NEGATED clause is a passing mention, not the rule ("No entries in
   the first hour", "skip days where the first-hour range ...", "do not trade on the last 2 days of the month", "avoid
   fading", a warm-up; the revert-to-VWAP patterns also ignore an EXIT clause - "exit when price reverts to VWAP" is
   how a VWAP-trend rule exits). The tests hold 28 such negatives (a VWAP trend rule, a 50-bar breakout, an NR7
   breakout, Donchian breaks after a skipped / warm-up first hour, an afternoon fade with a first-hour filter, a trend
   rule with a month-end filter, "breaks above or below", "not over-extended", "with the opening gap direction", a
   morning-move FADE, `QL_TOM_DEMARK_SEQ`, ...):

   | family | what puts an idea in it |
   |---|---|
   | `VWAP_REVERSION` | name `VWAPREVERT` / `VWAPFADE` / `VWAPSNAP` / `VWAPMR`; "VWAP revert / reversion / fade / snap back / mean-revert"; "revert / fade / snap back ... to VWAP" (not in an exit clause); "target / take profit at VWAP"; VWAP within one clause of "mean-revert / reversion / fade"; the band fade without the words: "close > VWAP + x, enter short" (and the mirror); a VWAP-deviation number with a contrarian entry: "d = (close - VWAP)/ATR; d > 2.5 short", "z-score of (close - VWAP) ... z > 2 sell" |
   | `OPENING_RANGE` | name `ORB` / `OR_BREAK` / `IB_BREAK` / `OPENINGRANGE` / `MORNINGMOM...`; "opening range breakout", "initial balance break / extension"; a range DEFINED over the opening window (opening range / initial balance / morning range / "first-hour range" / "first 12 bars form a range" / "the high and low of the first 30 minutes") followed by a break OF A RANGE (break of the range / box / OR high, above / below / > the range high / low - never a bare "or"); "breaks above the opening range high"; "above the first 30-minute high"; continuation: "in the direction / sign of / with / following the morning / opening / first-window / 09:30-10:30 move / trend / return / displacement" (not "with the opening GAP direction"), "morning momentum", "first half hour's return ... predicts / continues / persists", and the morning quantity followed by an entry IN ITS SIGN ("first-hour close displacement ... > 0, go long", "the 09:30-10:30 return is larger than 0.5% buy" - a fade of the morning move is not this family) |
   | `OPEN_DRIVE` | name `OPENDRIVE` / `MOMDRIVE`; "open(ing) drive", "momentum drive", "drive from / off the open" |
   | `GAMMA` | the `LAB_DEAD` GAMMA pattern (gamma, GEX, dealer gamma / hedging) - closed for the lab anyway |
   | `TURN_OF_MONTH` | name `TOM` (not `TOM_DEMARK`) / `TURNOFMONTH` / `MONTHEND`; "turn of the month", "month-end / month-start", "end / start of (each / the) month", "last / first N trading days of the month" |

   The 10-16 history in that map: QL_VWAPREVERT_NQ -> VWAP_REVERSION; QL_ES_MOMBREAK, QL_GAMMA_MOM, QL_GAMMA_ORB,
   QL_TRENDN -> OPENING_RANGE (the GAMMA pair also GAMMA; QL_TRENDN, QL_ES_MOMBREAK's rule moved to NQ, was accepted
   at 13:42 under the round-2 map); QL_MOMDRIVE -> OPENING_RANGE + OPEN_DRIVE; QL_TOM_CALENDAR_NQ -> TURN_OF_MONTH
   (a BROKEN PLUGIN run - its mechanism may be retried under a new name); QL_TPT_NQ, QL_MTP_NQ, QL_SCALP2M,
   QL_NOISE2M_TREND -> no family (the overlap check covers copies of them). Names are normalised with timeframe /
   version / instrument tokens out also as a token's suffix: `QL_NOISE2M_TREND` = `QL_NOISE_2M_TREND`.
6. **Power first** (inside `run_stage_a`, after gates 1-5 - the order the owner set): `tools/mapcheck_f.py`'s
   generator and rules on the stated prior (Sharpe s as stated, sd max(0.30, s/2), rho 0, t3 tails, clustered vol, the
   tool's 2,000 draws, own seed printed). The stated trades a year are checked against the plugin's own trade COUNT on
   the pre-walk-forward smoke (no P&L); a stated rate off by more than 2x is a factual error about the rule's schedule,
   and the map uses the counted rate (both printed in the prereg) - house power lines also use the real schedule.
   The verdict (CLEARS; GREYED under 50 trades a year; CLOSE) is final for that proposal (the prior is not re-stated
   upward), written into the prereg and both posts - but since MANAGER #134 it is **recorded, not a stop**: the idea
   goes on to the PRE-WF Stage A whatever the map says (`map.stops_idea = false`). Priors above a yearly Sharpe of 1.5
   are refused at `propose`.
7. **Auto prereg** - `C:\EdgeLog\qwen_lab\preregs\<name>_<date>.md`, naming BOTH stages: the source, Qwen's
   hypothesis and mechanism verbatim, the bar-index convention, the timing contract (the first entry bar as
   `bar k (HH:MM open)`, the entry fill, the time stop with its convention, and what Python checked each on), the
   smoke trade rate against the stated rate, the dates the plugin reads (the session-calendar module's path and LF
   sha256), the prior, the map read (marked "recorded, not a stop"), the
   dead-list read, the dedupe read (the result `propose` STORED, plus a re-check at prereg time), the
   gates passed with their version - and every check that did not run is written "NOT checked" (review round 3: a
   resumed pre-change idea's prereg claimed "none matched" and the first-signal-bar / entry-bar checks it never had;
   the MANAGER post says "first entry not stated - not checked" the same way) - the pinned master by filename with
   the PRE-WF slice's fingerprint, both windows, the promotion rule (`PROMOTION RULE: ...`), the broken-plugin rule
   with its retries (`retries k/2`) and the shelf-closes-only-after-a-sane-run line,
   the cost, the reading rules, a line that no walk-forward bar was read before it (gates 3-4 ran on pre-walk-forward
   bars), and the LF sha256 of the plugin and of `tools/qwen_lab.py`. Posted to MANAGER (`chat_inbox.py post MANAGER
   --from QWEN-LAB`; MANAGER's inbox exists so no `--new`; the sender has no inbox, so posts say "Replies ->
   CUSTOM-ML-MODEL-OPTIMIZATION") BEFORE any run. If the post fails, no stage runs. The plugin, harness AND
   session-calendar hashes are re-checked against the prereg before EACH stage (a mismatch refuses that stage; review
   round 4: the prereg said the calendar sha was re-checked, but only the plugin and the harness were - the prereg
   record now keeps `calendar_path` / `calendar_sha`, an older prereg's are read from its '- session calendar helpers'
   line, an ADDENDUM re-pins all three and says so), and the Stage A sandbox loads EXACTLY the pinned calendar file,
   checking its hash itself (`calendar_module(path, sha)` - every sandbox run is handed the file and sha it loads).
   Note: the lab does not push a `prereg/<lane>-<name>` branch (MANAGER #77) - it never pushes; the hashes posted
   before the run and the prereg file under `C:\EdgeLog\qwen_lab\preregs\` are the record.

## One bar-index convention (TTM #145)

Bars are named ONE way everywhere - the system prompt, the proposal, `first_signal_bar`, the prereg, the gate
messages: **bar k = the 0-based IN-SESSION index (bar 0 = the first regular-hours bar, the 09:30 open), always with
the clock time of that bar's OPEN** - `bar 12 (10:30 open)` on 5m bars is the bar from 10:30 to 10:35, `bar 12 (09:42
open)` on 1m bars; bar k's close is bar k+1's open time (on 5m bars bar 11 closes at 10:30). The harness numbers
bars BY THE CLOCK (bar k opens at 09:30 + k x bar minutes), so on a 1m / 2m session with missing bars the 10:30 bar
is still bar 60 on 1m bars (the prompt says so). Every entry and exit says
whether it fills at a bar's OPEN or at its CLOSE ("decide on bar 11's close (10:30), enter at bar 12's open (10:30
open)"); the trade list records the FILL bar. `propose` returns a soft `bar_convention` note when the text names a bar
without its clock or with a clock that is not that bar's open (`bar_convention_notes`; never a refusal), and the
template plugin's comments use the same convention.

## Dates and the session calendar (MANAGER #156)

QL_TOM_CALENDAR_NQ (shelf #34, 10-15) had only `day_id`, a bare session NUMBER, so it counted 21-session blocks from
the load start and traded 3 times in six years. The engine already hands a plugin the bar timestamps when its
`run_backtest` DECLARES `index=None` (engine.py / auto.py / optimize.py / rolls.py: each bar's OPEN time, US/Eastern on
the house masters) - REAL dates, causal (a bar's own date). New `augur_engine/session_calendar.py` (pure numpy /
pandas) turns `index` (+ `day_id`) into calendar facts, one value per BAR, equal on every bar of a session:
`session_dates`, `session_index_in_month` (0 = the month's first session), `days_to_month_end` (sessions LEFT after
this one; 0 = the last), `is_last_n_sessions_of_month(index, n, day_id)`, `is_first_n_sessions_of_month`,
`week_of_month` (1 + (day - 1) // 7: a third Friday is always week 3), and `session_calendar` (all of them plus year /
month / day / weekday / sessions_in_month).

**The future calendar.** "Is today one of the last 3 sessions of the month?" needs the sessions AFTER today. That is
the exchange's published trading calendar, known in advance - not a price - so reading it is not look-ahead. The
positions and counts come from the CME equity-index regular-hours calendar ALONE, across the whole span
(`exchange_sessions`: every weekday except New Year's Day, Good Friday and Christmas - as observed - and the special
full closures; MLK, Presidents, Memorial, Juneteenth, July 4, Labor and Thanksgiving are sessions), never from the
data's own dates. So a bar's answer is a function of its date alone: truncating the data, starting the load later, or
a hole in the data never changes it (tested on synthetic holes - every cut and every 7th start - and on the real
master's holes), and a load starting 2010-06-07 knows it is June's 5th session. A session MISSING from the data is
still a session, with no bars to trade. Review round 4: the first build read the data's own dates inside the loaded
span, and all 7 pinned RTH masters miss the same 15 published sessions (2012-11-22, 2013-01-21, 2013-02-18,
2013-05-27, 2013-07-04, 2013-09-02, 2013-11-28, 2014-01-20, 2014-02-17, 2014-06-12/13, 2014-09-23..25, 2014-12-31) -
146 of 1550 sessions changed their answer when the load was cut right after them, the answer moved with the load START
(fold slices and the Stage A disagreed), and 2 of TTM's 219 trades (2013-11-26, 2014-12-26) existed only on a load
that reached the next month. No master has a session off the published calendar (2010-06..2025-06); one would get its
position among the published sessions around it and shift no other count. **The date of a session** is its TRADING
day: each bar's US/Eastern date, or the next day for a bar at or after 18:00 ET (the CME roll), and sessions are the
day_id runs split where that date changes - regular-hours bars keep their own date (no change on the RTH pins); an
ETH master dates Sunday-evening and evening bars into the next session (review round 4: by the first bar's calendar
date, 13 Sunday chunks counted as sessions in 2016-01..03 and Monday's 18:00-roll sessions were dated Sunday).

The system prompt has a "DATES AND THE SESSION CALENDAR" section with an example (never count sessions from the start
of the data), the template's signature declares `index=None`, and the sandbox's synthetic bars sit on real exchange
sessions from 2026-03-02 (Good Friday 2026-04-03 absent). Before the module ships to main the sandbox loads the
worktree's copy under the same module name (`calendar_module()`); the prereg records its path and LF sha256, both are
re-checked before each stage, and the sandbox loads exactly that file.
**Contract test (TTM's literal build):** a plugin long the last 3 sessions of each month, first bar's open to last
bar's close, on the real PRE-WF window 2010-06-07..2016-06-30 of `NOADJ_NQ_5m_RTH.csv` makes **217 trades = 73 months
x 3 minus the master's holes 2013-11-28 and 2014-12-31 (35.8 a year)**: exactly the last 3 PUBLISHED sessions of
each month that the master has bars for, every entry at 09:30, and the same sessions on loads cut at 2013-11-26 and
2014-12-29 or started at 2014-09-26. TTM's 219 counted the data's own last 3 sessions - its 2013-11-26 and 2014-12-26
trades are data-hole artifacts.

## Stage A - two stages (MANAGER #134)

Both stages run the plugin's FILE DEFAULTS (no tuning) on its PINNED master (by filename: `NOADJ_NQ_5m_RTH.csv`,
`NOADJ_NQ_1m_RTH.csv`, `NOADJ_NQ_2m_RTH.csv`, `NOADJ_ES_5m_RTH.csv`, ... source `db_noadj_rth`; the engine's roll
guard adjusts signals and re-prices fills to raw). House costs: NQ 0.533 pt x $20, ES 0.363 pt x $50, one contract
(the scalper source: NQ 0.783, ES 0.613 - the scalp hunt's basis). Single-threaded sandbox, `AUGUR_TRIAL_CACHE=1`.

1. **PRE-WF Stage A - every idea that passes the hard gates.** Window **2010-06-07..2016-06-30**, the pre-walk-forward
   rows only (the house WF starts 2016-07-01; the validate job's window starts 2010-06-07). Data are loaded for that
   window and nothing later: `PREWF1 < WF0` is asserted at import, the sandbox refuses a pre-WF load that reaches
   2016-07-01 (before and after loading), and the harness asserts it again on its own slice and inside
   `four_numbers`. Never a WF row, never the lockbox. Output: `numbers_pre_wf.json`, `pre_wf_trades.csv`, and the
   MANAGER post `QWEN LAB: <idea> PRE-WF ...` (four numbers + trades + trades a year, the promotion verdict, the map
   verdict, the prereg and numbers paths). The contract smoke and the look-ahead audit read 2015-01-02..2016-06-30
   (inside this window) and report trade counts and pass / fail only - never P&L.
2. **Broken-plugin check, before any verdict (MANAGER #139).** QL_MOMDRIVE made 1 trade in 6 years - a bug that read
   as a dead idea. If the PRE-WF trades a year are more than 3x below the proposal's stated rate, under 20 a year, or
   under 100 a year for a scalp idea (the scalper source, or "scalp" in the proposal) - or the plugin crashes on the
   window - NO verdict is recorded and nothing is posted. Qwen gets the count, trades by year, its first trades and
   three real sessions of bars from the PRE-WF window where it did not trade (the biggest up day, the biggest down day,
   a median-range day; up to 40 bars each, with the session bar index) to check its entry condition against, and
   fixes the plugin. The fix goes through every hard gate again (`write_plugin` reopens for it; +3 attempts and +4
   model turns per retry); `run_stage_a` then appends an ADDENDUM line with the new plugin hash and the harness hash
   to the prereg and posts it to MANAGER (`QWEN LAB: PREREG ADDENDUM <k> ...`) BEFORE the re-run - a failed post
   refuses the run. At most 2 retries. Still failing (or the model finishes / runs out of turns mid-fix): the idea
   closes `BROKEN PLUGIN (n trades; retries k/2[ still broken])` with its numbers posted - a broken plugin, NOT a
   dead idea. **The loop is visible and enforced (MANAGER #153a):** QL_TOM_CALENDAR_NQ re-sent the same plugin 8
   times. A plugin byte-identical (same LF sha) to one this idea already ran NEVER counts as a retry and never re-runs
   - `write_plugin` and `run_stage_a` refuse it without using an attempt or a retry, and every refusal is logged
   (`<tool> REFUSED: ...` in `run.log`, an `identical_sha_refused` event). Each REAL retry (a changed plugin through
   every gate) posts its ADDENDUM before its re-run; every result line, the PRE-WF post and the done row carry
   `retries k/2` (`retries_text`) - review round 4: the final result post of a PROMOTED idea and its PRE-WF fallback
   (a failed PRE-WF post, or a WF stage that errored) left it out; both carry it now.
3. **Promotion (amended by MANAGER 10-16 15:45; was ROC@30k >= 15 and not one episode, #134)**: the WF Stage A runs
   only if **pre-WF gross edge / trade (points) >= the round-trip cost (points) AND net pre-WF ROC@30k > 0 AND
   one-episode False** - `NOT TESTABLE` does not pass (`PROMOTION_RULE`, `promotion_bar`). Gross / trade = the net
   points a trade + the cost the engine charged. Every result line, numbers JSON and post carries `gross/trade <x> pt vs
   cost <c> pt (gross/cost <r>)`. Not promoted: the idea closes `PRE-WF DONE - not promoted (...)` and the PRE-WF post
   is its result post (no second post). The WF -> Auto-Validate bar is unchanged.
   **One-episode NOT TESTABLE (MANAGER #160a).** `dd5` with ONE episode reads worst == average, so the house flag is
   always False - and a curve that never makes a new high (QL_NOISE2M_TREND's long slide) has one episode by
   construction. When DD5 is built from 1 episode or the cumulative P&L never makes a new high, `one_episode` is
   `"NOT TESTABLE"` (with `one_episode_why`) in the four-numbers line (`(n=1 one-episode NOT TESTABLE)`), the numbers
   JSON and the posts, and it fails both the promotion and the validate bar.
4. **WF Stage A - promoted ideas only.** Data loaded 2015-01-02..2025-06-29 (the warm-up years let indicators settle;
   trades entering before 2016-07-01 are dropped); the stretch is the house walk-forward **2016-07-01..2025-06-29
   only**. The lockbox (2025-06-30..2026-06-30) is never loaded: the sandbox and the harness both assert the last bar
   is before it. Output: `numbers.json`, `stage_a_trades.csv`, then the Auto-Validate rule below.

For each stage the harness loads the same slice itself, checks the sandbox's bar count and fingerprint match, and
computes:

- the valued-daily series with `augur_engine.book._mtm_increments` (open trades marked at each session's last close),
  every session of the stretch, zeros included;
- **ROC %/yr at a $30k drawdown**, **Sortino**, **DD % from peak** ($100k start) - `augur_engine.book_sizing.stretch_reading`;
- **DD5** and the **one-episode** flag - `augur_engine.drawdowns.dd5`;
- trades, trades a year, **net per trade in points and $** (MANAGER #142: every loser so far read about -4.5 to
  -5.0 ROC@30k, so the per-trade net tells a steady small loser from a broken one), net, PF, win rate, peak RAM.

Every result line (posts, `status`, `run.log`) reads `ROC@30k | DD5 | DD% | Sortino | trades (n/yr) | net/trade
<pts> pt ($) | gross/trade <pts> pt vs cost <pts> pt (gross/cost <ratio>)`.

## Load courtesy (MANAGER #143)

While a ship holds the machine-wide push lock (`C:\EdgeLog\state\push.lock`, `tools/push_lock.py`), the lab starts no
NEW Qwen generation and no NEW Stage A; it re-checks every 60 s, logs the wait (`LOAD COURTESY: ...` in `run.log`, the
last 50 in `state.json` `courtesy_waits`) and finishes whatever is already running. It only READS the file - never
takes, creates or deletes the lock. Held vs stale: push_lock holds an OS lock on byte 0 and writes the holder's name
from byte 1, and the name stays after a release, so the name alone proves nothing. On Windows the byte-0 lock is
mandatory, so reading byte 0 fails with a permission error exactly while a ship holds it (elsewhere: a named holder
whose pid is alive). A STOP file ends a wait before a generation or before Stage A starts (nothing has been written
then); the short wait right before each stage is not interruptible. `status` shows the lock and the last waits.

## Auto-Validate

Only for a PROMOTED idea whose WF Stage A has WF ROC@30k >= 15, not one episode (`NOT TESTABLE` fails), >= 100 WF trades and a sandbox
peak under 4 GB (a validate runs three fold processes - port trap 1). Then:

1. at most ONE Qwen-lab validate queued / running / paused (Firestore read, the lanes' query; fail closed if it cannot
   be read);
2. the file must be on main with the SAME LF hash (`augur_strategies/<name>.py` or `augur_strategies/qwen_lab/<name>.py`
   in the shared checkout - the runner reads the shared checkout and executes the plugin in-process, unsandboxed, so a
   Claude lane review comes first). Not there: the request is recorded as **pending review** in `state.json`;
   `python tools/qwen_lab.py queue-pending` queues it once the reviewed file has landed;
3. `tools/queue_guard.py`'s `guard()` runs in the sandbox (an ARTIFACT verdict refuses; its printout, which includes
   the guard's own lockbox slice, stays in the idea folder and is never shown to Qwen or posted);
4. the job is the lanes' shape (`tools/noise_queue_422_tp_validate.BASE`): 900 trials (owner rule), window
   2010-06-07..2026-06-30 with a 12-month lockbox (split 2025-06-30 = the house lockbox start), 8 folds, warm_days 300,
   the pinned source, house cost; preset / note tagged `QWEN LAB`.

`--dry-run-validate` runs all of it except the Firestore write (and, when the file is not on main yet, still builds
the job and runs the guard on the worktree file so the path is exercised); the job lands in `validate_job.json`.

## Run, stop, resume

```
python tools/qwen_lab.py next-pick                               # record + post the next pick (rotation)
python tools/qwen_lab.py run --once --dry-run-validate            # test the recorded pick, validate in dry run
python tools/qwen_lab.py run --source scalper --dry-run-validate  # force a source (or --idea N for a shelf paper)
python tools/qwen_lab.py run                                      # idea after idea, rotating the sources
python tools/qwen_lab.py launch [flags]                           # the same, detached (pythonw, no console)
python tools/qwen_lab.py stop                                     # STOP file: saves and exits at the next step
python tools/qwen_lab.py status
python tools/qwen_lab.py queue-pending [--dry-run-validate]
python tools/qwen_lab.py shelf-open 31 32                         # MANAGER opens shelf papers for the lab
python tools/qwen_lab.py shelf-close 31 --why "done"              # MANAGER closes them (the latest line wins)
```

Run it from a git **worktree**: plugins are written to `<worktree>\augur_strategies\qwen_lab\` and the tool refuses the
shared checkout as the plugin repo. A second `run` refuses while one is alive (`run.lock`). A stopped or killed run
resumes the open idea from its saved transcript. Ollama must be up (`python tools/local_llm.py --status`; CPU ONLY
after a reboot = restart Ollama). Long runs show on the top-bar dials through `tools/research_beacon.py` (`--no-beacon`
to skip).

Limits: 18 model turns an idea (every tool result carries `steps_left`), at most 3 turns of pure reading before a
proposal (the first live run spent 9 turns on one-word `dead_list` searches), 6 plugin attempts, 3 proposals, 4 h wall, 30 min a model reply, sandbox timeouts
15 / 25 / 40 / 40 min (contract / look-ahead / Stage A / guard), 6 GB sandbox memory, 32k context (old tool results and
old plugin code are trimmed from what is sent; the transcript keeps everything).

## Where outputs go

`C:\EdgeLog\qwen_lab\`:
- `state.json` - current idea, done ideas (outcome + PRE-WF and WF four numbers + `retries`), aborted ideas (operator
  aborts and `CLOSED AS DUPLICATE` ideas, with `duplicate_of`), validates, pending reviews, the shelf skip list,
  `closed_shelf` (+ `shelf_closures_undone`), the source rotation and picks, `courtesy_waits`
- `shelf_open.txt` - the papers MANAGER opened (`shelf-open`) or closed (`shelf-close`: a `CLOSE` line), one dated
  line per call; the latest line per paper wins
- `run.log` - every step, tool call and gate result
- `ideas\<id>\` - `idea.json` (events in order, proposal, map, gates, prereg, Stage A, validate), `transcript.json`
  (every message and model timing), `plugin_v<k>.py.txt` (inert copies of each attempt), `gates_v<k>.json`,
  `sandbox_*` requests / results / logs, `pre_wf_trades.csv` + `numbers_pre_wf.json` (PRE-WF stage),
  `stage_a_trades.csv` + `numbers.json` (WF stage), `sanity_r<k>.json` + `pre_wf_r<k>_trades.csv` (broken-plugin
  retries), `validate_job.json`, a prereg copy (with any addenda)
- `preregs\<name>_<date>.md`

MANAGER posts per idea: the prereg (`QWEN LAB: PREREG ...`) before any run, the `QWEN LAB: <name> PRE-WF ...` post
with the PRE-WF numbers, and - for a promoted idea, or one that ended before the PRE-WF stage - one end post
`QWEN LAB: <name> (<source>) - ...` (both stages' numbers, or `-` and why); then the harness's `QWEN LAB next pick:
...` post. A run resumed under a changed harness gets the current system prompt and a note of what changed. A plugin's `write_plugin` result also carries a
`schedule_check`: its own trade COUNT on the pre-walk-forward bars against the proposal (counts only) - a rate off by
more than 2x, or under the map's 50 a year, is flagged so Qwen can revise before the map reads it; a revised proposal
forces the plugin to be rewritten and re-gated.

## Shipping

**Nothing in `augur_strategies/qwen_lab/` ships to main without a Claude lane review.** The lab writes into a
worktree; it never commits, pushes, ships, touches the box, NinjaTrader, Webull, live or paper systems, or downloads
anything. A lane reviews the plugin (the same audit as any new strategy file: `tests/test_roll_detector_lint.py`, the
strategy contract tests, a peak-RAM read on the full window - see the port-validate traps) before it ships, and only a
shipped file with the prereg's hash can be Auto-Validated.
