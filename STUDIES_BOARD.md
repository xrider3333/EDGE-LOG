# STUDIES_BOARD.md — how to add a research study to the EDGELOG website

This file is written for a future Claude session. Read it before you touch the studies
registry. It is the contract for the board: what it is, where it lives, every field the
registry accepts, how to add a study or a row, how tagging feeds the filters, which
figures a row needs before it can appear on the chart, and the rules that keep the board
honest.

---

## 1. What the board is and where it lives

The board is called **STUDIES**. It is the fourth mode of the **COMPARE** tab, sitting
beside PICK RUNS, BY STRATEGY and RUNBOARD. It holds completed research studies so the
owner can read them on the site instead of scrolling back through chat.

**There is ONE chart.** It sits at the top of the board and it carries every row now shown,
whatever study the row came from, and a STRATEGY rail above it steps from one strategy family
to the next. Under it, every study is **one closed heading** that opens on click into its
description, its scrolling table and its notes. **A study tile draws no chart of its own.**

**The board is short on purpose, and shortness never costs a figure.** The owner's second note
on 2026-08-19 was blunt: *"the page still has wayyyy to much text on it and to long."* So the
rule for anything you add here is: **print the number, hover the explanation.** Four paragraphs
of running commentary are now four status chips whose hovers carry those paragraphs word for
word; the reference text sits behind the `? HOW TO READ` chip; the secondary controls sit behind
`MORE`; the sixteen tables are closed until asked for. Nothing measured is hidden by any of it —
what is hidden is always explanation, and it is always one hover or one click away. If you find
yourself adding a paragraph to this board, put it on a hover instead.

This is a deliberate reversal, made on 2026-08-19 in the owner's words: *"this was originally
supposed to be one scatter plot and it just got blown up with every claude session and their
respective strategies putting their own scatter plot on it ... the original intent was i could
go from strategy to the next on the tabs by toggling which one on the top and see whats been
tested on the backend."* Sixteen studies had grown fourteen charts, which is fourteen sets of
axes on fourteen scales, so a strategy whose research is spread over five studies could not be
read as one picture. **Do not add a per-study chart back.** If a study needs a different pair
of axes from drawdown-against-profit, that is a different board, not a fifteenth chart on this
one.

Merging them cost nothing, because all fourteen already plotted the same two things: the worst
drawdown across the bottom and the selected profit stage up the side. A row that lacks either
figure is left off the chart and named underneath with the same reason its table dash gives.

All of the data lives in one array called `RESEARCH_STUDIES`, near the top of the compare
section of `index.html`, directly under the RUNBOARD data. **The renderer below that array
holds no data at all.** You add a study by appending one entry to the array. You never
edit the renderer to add data.

---

## 2. The controls at the top of the board

These controls apply to every study on the board at once, and each one changes the chart
and the table together, so the two can never disagree.

**STRATEGY — ALL, or one family.** This is the rail the board is built around and it sits
directly under the top row of controls, with the row count beside each name. Picking a strategy
narrows the chart *and* every table below it together. It writes the **same** strategy-type
filter the chips further down write, so the rail and the chips are one setting and can never
disagree: a rail button ticks exactly that one family, and ALL clears the family filter while
leaving every other filter alone. The buttons are built from the registry, so a family appears
on the rail the moment a row is tagged with it.

**PROFIT STAGE — in-sample, walk-forward, lockbox, or total.** This picks which stretch of
history every row is read on. It sets the height of every chart point, it highlights the
matching money column in every table, and it drives the profit-divided-by-drawdown column.
A row that genuinely has no figure for the selected stage shows a dash, the dash says why
when you hover it, and the row drops off the chart with the omitted-count line updating.
**A figure from a different stage is never put in its place.**

**VERTICAL AXIS — raw profit, MAR, PF, or $/TRADE.** Raw profit plots the money itself with dollar
ticks. **MAR** is profit over the worst drawdown — the same division, and now the same name, the
RUNBOARD and the 1E matrix use. **PF** and **$/TRADE** are the two window-robust readings: both count
trades rather than calendar, so rows covering different years can still be read against each other,
and both state on the axis that they ignore PROFIT STAGE and COMPARE ON because each is recorded
once per row. Coverage differs and it matters — PF places 203 of 215 rows, raw profit 203, $/TRADE
146, and every row it cannot place is named under the chart with the reason.

(There used to be a PER STUDY setting honouring a `yMode` declared by each study. With one chart it
had nothing left to mean — a single axis cannot hold two units — so it and the field are gone.)

**ORDER BY — discovered, date ran, or result** (control 14, on the STUDY TABLES heading). Discovered
keeps the registry order, which is the order the owner approved. Date ran reads the real finish date
out of run history and splits each table into a block that was run and a block that never was.
Result sorts best first on whatever stage and axis are selected.

**It does not change what the chart shows, and it lives with the tables for that reason.** Sorting
cannot move a point, so no row is ever gained or lost by it. Two couplings survive on purpose and
both are named on its hover: under DATE RAN the chart **fades** the never-run points so it matches
the split the tables are showing, and while TIME SCOPE is on, SCOPE DATE defaults to *following* this
control, so it decides which of a row's two dates the scope reads. Set SCOPE DATE explicitly and even
that goes away.

**Filters — verdict, discovered date, run status, status, study** (controls 9–13). These are built
from the data. Strategy type is not among them: that is control 1, the rail. STUDY is the one to reach for when a family has five studies behind it and you want
to read them one at a time on the single chart; it needs no tagging, because it is built from each
study's own title. The renderer walks every row in the registry, collects the distinct values of each
tag, and makes a button for each one. A new study that tags its rows gets its buttons for
free. Filters narrow the chart and the table at the same time, and the board always states
how many rows are hidden.

**CLEAR FILTERS** appears only while something is filtered and drops all of them.

**MORE / LESS.** Only the STRATEGY rail, PROFIT STAGE, VERTICAL AXIS and ORDER BY are on screen by
default. MORE reveals COMPARE ON, VALUE ZOOM, TIME SCOPE, SCOPE DATE, COLOUR and every filter chip.
A hidden control keeps working exactly as it was set, which is why the status chips below always
state what is in force, and the MORE button itself says `· filtered` when a filter is active.

**? HOW TO READ.** Opens the reference block: what the board is, what it refuses to do, what each
comparison basis means and which ratio survives a mismatched window. Closed by default, remembered
once opened.

**The status chips.** One line under the controls: rows shown, comparison basis, time scope, and
the common data window. Each is a short fact, and the hover on each carries the full paragraph that
used to be printed there. A chip warning about something wears the warning colour.

**How the controls are laid out.** A grid, **two controls per line**, each one **numbered** so it
can be named in a sentence rather than described: name on the left, buttons on the right, wrapping
inside its own cell. Two blocks — 1–6 decide what the chart plots and are always on screen
(1 STRATEGY, 2 PROFIT STAGE, 3 VERTICAL AXIS, 4 READ AS); 5–13 sit behind
MORE (5 COMPARE ON, 6 TIME SCOPE, 7 SCOPE DATE, 8 COLOUR, then the filters 9–13), and **14 ORDER BY sits on the STUDY TABLES heading**, because the tables are the only thing it orders. FRONTIER was a control here until 2026-08-19, when the owner had it removed. **Add a new control as `_reCtl(number, cap, tip, buttons, tone, span)`**, not as another
free-floating `_ctlGrp` in a flex row — that is what made the old block unreadable. `span` gives a
control a full-width line of its own; only 13 STUDY needs it.

**There is exactly one strategy control.** Control 1 IS the `fam` filter. A second row of the same
buttons used to render with the other filter chips and the owner rightly asked why there were two;
the `fam` facet is now excluded from `_reFiltBtns` while staying in `_reFacets` for the filtering
logic. Do not put it back.

**READ AS — absolute, or vs crown.** (Also in the always-on block.) VS CROWN measures both axes *from* the crowned configuration
of each row's own family, so the crown lands on the origin and every other variant reads as the
money it added and the drawdown it added against the thing actually being traded. It is the same
figures the tables print, subtracted — never new data — and it changes the **chart only**; the
tables always show absolute numbers, and the chart says so underneath.

**BASELINE — the rail that appears under VS CROWN.** It names which crowned row each family is
read against. Today **every family has more than one row tagged crowned**, because the
what-is-running-in-paper study restates configurations other studies already crowned, and section 6
says one family, one crown. The board does not average that away and does not silently pick: it
reads against the **lowest-numbered** candidate — a row number is a permanent handle handed out in
order, so the lowest is the first time that crown was recorded and the rest restate it — states that
on the rail in warning colour, and lets one click read against a different one. Choosing there
changes nothing in the registry. **If you fix the duplicate tags, the rail goes quiet by itself.**

**SPLIT SCREEN — the ◧ / ▤ pair on the right of the sub-tab bar.** The same control, in the same
place, that RESULTS, LIBRARY and RESEARCH use; it only appears while STUDIES is the mode on screen.
◧ puts the chart on the left and the study tables on the right, with the chart pinned so it stays in
view while the tables scroll past it. ▤ is the stacked layout. The choice is persisted as
`resSplit`, which is deliberately NOT `resView` — that key already belongs to the RESULTS split.
**Drag the bar between the two columns** to set how much width the chart gets (`resSplitW`, 22–78%,
double-click restores half); the handle underneath the chart still sets its height, so in the split
layout the chart resizes on both axes.

**The tables are compressed on purpose, and ordered on purpose.** Cell padding is 2px, the type is
8.5px, headings are 7px, and the two prose columns — WHAT IT DOES and READ — are clipped to a single
line with the whole sentence on hover. Column order is **rank, row, name, the four stage figures,
drawdown, PF, profit÷DD, trades, read**, and only then the grey descriptive block — what it does,
run, discovered, data window — at the far right, dimmer than the numbers. The money comes first
because the money is what the table is read for.

**There is no STATUS column.** It was a column of dashes for the sake of the one or two rows per
family that carry a pill, so CROWN and PAPER ride beside the NAME of the rows that have them and a
row with neither shows nothing. `_reLiveInline` renders them; the meaning is on the NAME heading.

If you add a column, add it in that spirit: a number reads at a glance, a sentence belongs on a
hover, and a column that is mostly empty should not be a column.

**Why some rows are tinted, which is a question the board got asked.** A faint blue tint means the
row's verdict is `champ` — the champion or baseline of that study. That is all it is: the same
verdict the shape beside the name already carries, repeated as background so the one row worth
finding stands out in a long table. No other verdict tints. There used to be a green tint for
`good` as well; the owner had it removed on 2026-08-19 as noise, since the mark already said it.
`_reBg` still keeps the second colour in place behind a `void`, so bringing it back is one line. The *brighter* flash that follows the pointer is a
different mechanism entirely: the live two-way link between a table row and its point on the chart.
Every tinted row carries that explanation on its own hover, and so does the NAME heading.

**Opening a study.** Every study is a closed heading — verdict-free, just the title, its strategy,
`shown/total` and the date discovered. Click to open, click to close, and the open set is
remembered. Two things open a study for you: filtering down to a single study, and clicking a chart
point whose row lives inside a closed one.

**COMPARE ON — ratios as is, or per year.** Raw totals measured over different stretches of history
are not comparable, and section 4A explains why the board already knew that. This control decides the
basis every figure is read on, and the board always states in words which basis is in force and how
many of the rows now shown it can reach.

- **RATIOS AS IS** is what the board has always done. Every figure is exactly what its row recorded,
  over whatever window that row happens to cover. It reaches every row. The common-window warning
  still says where the windows disagree.
- **PER YEAR** divides each row's own profit by the number of years its own window covers, so a longer
  window is not automatically flattered. It needs only a recorded data window, not a saved curve,
  which makes it the wider-coverage option. Three extra columns appear — PER YEAR, YEARS and
  MAR / YR.

**COMMON WINDOW was removed on 2026-08-19, and should not be added back without new data.** It sliced
each run's saved equity curve down to the stretch every visible row shared, and recomputed profit and
drawdown on exactly that slice — rigorous, and it cost no re-running. It also could not reach the
board: slicing needs a saved curve, only a row with a `runs` array has one, and **31 of 216 rows have
a run behind them**. The other 185 are local research. So the basis dashed 85% of the board by
construction, and the owner's objection was the right one — *"since common window only populates for
few runs, and I'm trying to assess the broader picture"* — with the added problem that windows
**diverge** as testing continues, so the shared stretch can only shrink. The code is in git if the
registry ever becomes mostly run-backed.

**What answers the same question now.** `PF` and `$/TRD` are properties of the trade population, not
of the calendar, so a mismatched window barely moves them — those are the fair comparison. PER YEAR
is for reading money against the length of window it was earned over.

**PF and MAR are not the same number, and both headings now say so.** PF is gross winnings
over gross losses, counted trade by trade — how far the winners outweigh the losers, and a property
of the trade population, so a slightly different window barely moves it. MAR is net profit over the single worst peak-to-trough loss — what the rest of the world calls MAR or recovery factor
— so it answers what the worst stretch cost to earn, and it rests on **one event**, which is why it
is the most fragile figure here. A row can have a strong PF and a weak MAR, or the reverse.

**$/TRD is the other window-robust figure**, and it is why the trade count matters. Whole-run profit
over the trade count: the average dollars a variant made per trade it took. Like PF it is a property
of the trade population rather than of the calendar, so it is the fairest reading this board has
without re-running anything. It declares that it cannot follow PROFIT STAGE or COMPARE ON — a count
is recorded once per row, not per stage.

**Where a trade count comes from**, in order: the row's own `trd`; then `validate.total_trades` on
the saved run document where the row has a run number, marked with a small circle; then a dash. **It
is never derived** — a count cannot be worked back out of money, and no rate from a neighbouring row
is ever applied. As of 2026-08-19 that leaves **71 local rows with no count and no way to get one**
short of recording it on the row or persisting the variant as a validate run. **Record `trd` on new
rows.**

**Which ratio survives a slightly mismatched window.** This is printed in the UI under the
controls, and it reflects what this project has measured rather than a preference. Profit factor is
the most robust of the three, because it is a property of the whole trade population, so a few
extra weeks move it only a little. Profit divided by drawdown is the most fragile, because a
drawdown is one single worst event and one extra month can introduce a new worst event that moves
the figure a long way — this project measured the confidence interval around a maximum drawdown to
be wider than the drawdown itself. Sharpe sits between the two. The board carries no Sharpe column
today, so that last point is guidance for reading Sharpe on the run reports.

**VALUE ZOOM is gone** (removed 2026-08-19 at the owner's ask). The axes span only the rows now
shown, so controls 1 and 11–15 already rescale the chart; trimming the range on top of that was a
second, blunter version of the same job and it needed a pinned-to-the-edge special case to stay
honest about what it pushed out of view. Do not add it back — narrow the rows instead.

**Chart height — the drag handle under the chart.** The chart carries the same slim drag
bar the run report puts under every one of its charts. Drag it down and the chart grows, drag it up
and it shrinks, double-click it and the chart returns to the standard height. The size is remembered
once (`resChH.board`) and persisted like every other view preference here, so it survives a reload.
What is
stored is the chart's drawing height in its own drawing units rather than a pixel count, which is
why a resized chart still fills the width of its tile at any browser size and why its axis captions,
tick numbers and legend stay exactly the size they always were — the plot area is the part that
grows.

**TIME SCOPE — all time, past week, past month, past three months.** This narrows the whole
board to recent work. It applies to the charts and the tables together, and the board states
how many rows it is holding back, separately from the count the filters print, so you can
always tell which control is responsible.

**SCOPE DATE — follows order by, discovered, or date ran.** Every row carries two different
dates and they answer different questions: the date the result was **discovered** in research,
which every row has, and the date it **ran** as a real validate run, which only rows persisted
as runs have at all. The board therefore never chooses for you. SCOPE DATE defaults to
following the ORDER BY control, and a line under the controls says in words which of the two
dates is in force and what cut-off date it is using. ORDER BY RESULT is not a date at all, so
under that setting the scope falls back to the date discovered **and says so** rather than
quietly picking one.

A row that was never run has no date ran, so a run-date scope cannot place it. Those rows are
held back, but they are never dropped without a word: they are counted and named by row number
under the controls and again under each study chart, together with the two ways to bring them
back. This is the same honesty the DATE RAN ordering already uses when it puts those rows in
their own labelled block instead of inventing a date for them.

**COLOUR — colour, or shapes only.** This changes this board alone and never touches the app
theme. COLOUR follows the app theme where the theme carries real colour, and uses the five approved
colours — blue champion, green held up, amber fragile, red failed, grey reference — where it does
not. SHAPES ONLY drops everything to one neutral ink.

There used to be a third setting, THEME, and on 2026-08-19 the owner asked whether it and COLOUR
were the same thing. For him they were. The MONO theme's accent variables are all greys (blue
#b0b0b0, green #f0f0f0, yellow #999999, red #4d4d4d), so THEME already fell back to the approved
five rather than paint five near-identical greys — which made it pixel-for-pixel identical to
COLOUR. The fallback survives inside COLOUR; the duplicate button does not.

**The verdict shapes are drawn in both settings.** Colour is reinforcement laid on top of
the shape and is never a substitute for it, so turning colour off loses no meaning and nothing
becomes unreadable. Money keeps its minus sign in every setting. The choice is persisted the
same way every other view preference on this board is.

---

## 3. The registry — study fields

Each entry in `RESEARCH_STUDIES` is one study.

| Field | Required | What it is |
| --- | --- | --- |
| `key` | yes | A short unique lowercase id. It is half of the handle that links a chart point to its table row, so it must not change once shipped. |
| `title` | yes | The study name the owner reads at the top of the tile. |
| `sub` | yes | One plain-English line saying what was tested, on what instrument, over what window. |
| `notes` | no | An array of plain-English bullets printed under the table. A single `note` string still works and renders as one bullet. |
| `disc` | yes | The date the study was discovered, written `YYYY-MM-DD`. Any row may override it. |
| `fam` | yes | The default strategy-type tag for every row, such as `NOISE`, `ORB` or `ENGU-Q`. This is what the STRATEGY TYPE filter is built from. |
| `isLbl` | yes | The heading for the in-sample money column. Use `IN-SAMPLE` when the study really has a separate walk-forward stage. Use `PRE-LOCKBOX` when that figure is everything before the lockbox pooled together, which is what a pooled book has. |
| `dashWhy` | no | An object mapping a field name to the reason its dash shows, for every row in the study. |
| `win` | no | The default **data window** for every row in the study that has neither a run nor its own `win`. See section 4A. |
| `rows` | yes | The array of rows. |

### There is no `chart` block any more

A study declares no chart at all. **The board owns the one chart and both of its axes**, and a
study cannot opt out of it, opt into a different one, or declare its own default:

- **Horizontal is always `dd`, the worst drawdown**, captioned "Worst drawdown — further LEFT is
  better". Every study that ever declared a chart declared exactly this, which is why they could
  be merged without inventing anything.
- **Vertical is always the profit stage the owner selected**, raw or divided by drawdown, with the
  caption written for you.

That is what keeps the board apples to apples: two rows on screen are always read on the same
stretch of history in the same unit. A study needs no chart field to appear on the chart — a row
plots as soon as it has a drawdown and a figure for the selected stage, and is named under the
chart with the reason when it does not.

**A note on the in-sample stage.** It is the one figure that does not mean the same thing in
every study — `isLbl` exists precisely because some studies have no separate walk-forward stage —
so when rows with different `isLbl` values are plotted together on PROFIT STAGE = IN-SAMPLE, the
chart says so in a warning underneath and names which study means which. TOTAL and LOCKBOX mean
the same thing everywhere.

---

## 4. The registry — row fields

| Field | Required | What it is |
| --- | --- | --- |
| `n` | yes | The **row number**. See the permanence rule in section 6. |
| `name` | yes | The short name, exactly as the owner has already seen it. |
| `what` | yes | A plain-English sentence saying what the variant does. |
| `tone` | yes | One of `champ`, `good`, `frag`, `fail`, `ref`. See section 5. |
| `read` | yes | The short verdict text shown in the last column. |
| `fam` | no | Overrides the study strategy-type tag for this row alone. |
| `runs` | no | An array of the real Auto-Validate run ids that persisted this row. **Leave the field out entirely** for local-only research; the row then prints `local` in the RUN column, the same convention the RUNBOARD uses, and it carries no date ran. |
| `repeats` | no | An array of run ids that repeated this row's exact configuration and have since been **archived**. Keep them OUT of `runs`. The `+N` marker beside a run number exists so the owner can go and open those runs, and an archived run is hidden from Past Runs, so counting it there would promise something the board cannot deliver. The row prints its own archived-repeat marker instead, and its hover says a duplicate job was queued by mistake, the figures came out identical, and the repeat is hidden rather than deleted. Omit the field when there are none. |
| `disc` | no | Overrides the study discovery date for this row alone. |
| `is` `wf` `lb` `tot` | no | The four stage profits, in dollars. Leave a field out when it does not exist. |
| `dd` | no | The worst drawdown, **always written as a positive number**. |
| `pf` | no | The profit factor. |
| `trd` | no | The trade count. |
| `live` | no | The row's **status**: `'crown'`, `'paper'`, `'both'`, or left out. See section 4B. |
| `liveWhy` | no | One plain-English sentence explaining that status, shown when the reader hovers the status pills. Leave it out and a sensible default sentence is used. |
| `why` | no | An object mapping a field name to the reason its dash shows, overriding `dashWhy` for this row alone. |
| `win` | no | `{from:'YYYY-MM-DD', to:'YYYY-MM-DD'}` — the **data window** this row's figures cover. See section 4A. |

**A `win` on a local row is worth more than it used to be.** It is what lets the PER YEAR basis
place that row, so a local research row that records its window is readable on two of the three
bases instead of one. It still cannot be read on COMMON WINDOW, because that needs a saved curve
and a local row has none — it shows a dash saying exactly that.

**Do not supply a profit-divided-by-drawdown figure.** The board computes it from the
selected stage profit and the drawdown, so it always matches whatever stage is on screen.

---

## 4A. The data window, and why the board warns about it

Rows on this board were computed at different times, over different date ranges, and the
underlying price data has been backfilled since some of them were run. Two totals can therefore
look directly comparable and not be. The board makes that visible rather than leaving the owner
to discover it.

**Every study table has a DATA WINDOW column.** It shows the stretch of history behind every
figure on that row, and where it came from is fixed by one rule:

- **A row with a `runs` array reads its window off the saved run document**, from the run's own
  from-date and to-date. That is the truth for that row, so anything written in the registry for
  it is ignored. You never have to supply a window for a row that was persisted as a run.
- **A row without one reads `win` on the row, falling back to `win` on the study.** This is the
  only case where you supply a window by hand, and it is for local research where nothing else
  records the range.
- **A row with neither shows a dash that says the window is unknown.** That is the honest answer.

**Never guess a window.** An assumed range is exactly the error this column exists to catch. A
dash saying "unknown" is always better than a range nobody measured.

**The common window** is printed under every study chart and once for the whole board. It is the
stretch every visible row that records a window genuinely shares: the latest start and the
earliest end across them. When the visible rows do not all cover it, the line warns you, names
the rows that reach outside it and says by how much, and those rows also carry a warning sign in
their own window cell with the gap spelled out on hover. Rows recording no window at all are
counted and named too, because "we cannot tell" is a different statement from "they agree".

The point is narrow and worth stating plainly: **the owner should never put two totals side by
side without knowing whether they cover the same stretch of history.** Surfacing the window is what
this column does.

Acting on it is the job of the **COMPARE ON** control described in section 2. Where a row is backed
by a run with a saved equity curve, COMMON WINDOW slices that curve to the shared stretch and
recomputes the row on it; PER YEAR divides by the row's own length instead and reaches every row
that records a window at all. Neither re-runs anything, and neither invents a figure for a row it
cannot place. Re-running a row on a fresh common window is still a separate and much larger piece
of work that nothing on this board attempts.

---

## 4B. Status — crowned, forward-tested, both, or neither

The owner asked for this on 2026-08-19: *"way to see whats being forward tested in addition to
whats crowned?"* A good backtest and a thing that is actually being traded forward are two
different claims, and the board must never let them blur together.

So every row can declare a `live` value. There are four states and only the first three are
written down; the fourth is what a row means when it says nothing.

| `live` | Meaning | How it looks |
| --- | --- | --- |
| `'crown'` | The row is the standing champion of its family, and it is **not** one of the configurations running in the paper forward test. | A blue CROWN pill in the STATUS column, and a thin solid ring around its chart mark. |
| `'paper'` | This exact configuration is running in the nightly paper forward test right now, and it is **not** the standing champion of its family. | A green PAPER pill, and a dashed green ring around its chart mark. |
| `'both'` | It is the standing champion **and** the configuration running in paper. | Both pills and both rings. |
| left out | Neither. This is the normal state of a research variant. | A dash in the STATUS column and no ring. |

Four rules keep this honest.

**Declare it, never infer it.** The renderer does not go looking for a run number in the paper
configuration and guess. If a row carries no `live` value it reads as *neither*, not as *unknown*.
That is deliberate: a wrong "this is live" claim is far worse than a missing one.

**One family, one crown.** Exactly one row per strategy family should carry `'crown'` or `'both'`.
If the crown moves, move the tag in the same commit that records the new crown.

**Paper means the shadow forward test.** The authority for what is running is the paper leg list
in `api/paper.py`. A row is tagged `'paper'` only when its configuration matches a leg there. A
strategy compiled for NinjaTrader but not on that list is not forward-tested for this purpose;
say so in `liveWhy` if it is worth saying.

**A mismatch is the point, not an embarrassment.** When the crowned row and the paper row are
different rows, tag them honestly, say so in each row's `liveWhy`, and put it in the study notes.
That contrast is exactly what the owner asked the board to show.

The STATUS filter is built from these values the same way every other filter is built, so a study
that tags its rows gets its buttons for free.

---

## 5. Tagging so the filters pick a row up

Three of the four filters read tags you supply.

**Strategy type** reads `fam` on the row, falling back to `fam` on the study. Use the family
name the owner already says out loud: `NOISE`, `ORB`, `ENGU-Q`. If you invent a new
one it appears as its own button automatically, so pick a name the owner will recognise and
then use exactly that name everywhere.

**Verdict** reads `tone`. The five values are fixed, and each one has its own shape on the
chart so the verdict survives the monochrome theme with no colour at all:

| `tone` | Meaning | Mark on the chart |
| --- | --- | --- |
| `champ` | champion or baseline | large filled circle with a bright outline |
| `good` | beat it and held up | filled square |
| `frag` | works but fragile | hollow circle |
| `fail` | failed | cross |
| `ref` | reference or superseded | hollow triangle |

**Discovered** reads `disc` on the row, falling back to `disc` on the study.

**Run status** is derived: a row with a `runs` array is "ran as a run", a row without one is
"local only". You do not tag this yourself.

**Status** reads `live`, described in section 4B. Unlike run status you DO tag this yourself, and
an untagged row reads as neither crowned nor forward-tested.

**Study** is derived from the study's own `title`. You do not tag it.

---

## 6. The rules that keep the board honest

**Row numbers are permanent handles.** Once the owner has seen a numbered row, that number
belongs to that configuration forever. Never renumber a row, never reuse a number for
something else, and never close a gap left by a retired row. New rows take the next free
number across the whole board, not the next free number within one study. The row number is
also the link between a chart point and its table row, so changing one silently breaks the
other. The RANK column is the only ranking on the board that moves, and it is clearly
labelled as a position rather than a name.

**A missing figure is a dash with a reason, never a substitution.** If a row has no
walk-forward figure, it shows a dash, the dash explains why on hover, and the row leaves the
chart while that stage is selected. Never fill the gap with a number measured over a
different window, a different stage, or a different date range. Write the reason once in the
study's `dashWhy` and let every row inherit it; use the row's own `why` when one row has a
different reason from the rest.

**This board is for single strategies only. Combination studies do not belong on it.** The
owner decided this on 2026-08-19, in his own words: *"remove the orb+noise suggestion. we
arent comparing combining strategies."* The reason is margin. A pooled book trades several
strategies at once, so it ties up more margin than any single strategy does, and its raw
dollar profit is therefore bigger for that reason alone. The two can never be read as a
like-for-like comparison, which is exactly why the owner had the book studies taken off the
board. Do not add a pooled book, a two-leg or three-leg combination, or a weighting grid over
several strategies as a study here. Compare whole combinations in the RUNBOARD mode, which
exists for that job, and keep the research itself in the repository documents.

The removal was a clean deletion of the study entries from the registry and nothing else. No
rendering code was taken out, so the board could carry a combination study again unchanged if
the owner ever reverses the decision, and every result that was removed is still written down
in `BOOK.md`.

**Drawdown is always positive.** The column heading already says drawdown, so a leading minus
sign is wrong. Losing money figures in the profit columns do keep their minus sign.

**Do not compare across windows.** Two rows measured on different date ranges are not
comparable even inside one study. Say so in the row's `what` line and in the study notes, use
the strategy-type filter to let the owner read each family on its own, and record a `win` for
any local row whose range you actually know so the DATA WINDOW column and the common-window
warning can do their job. Never invent one to fill the column.

---

## 6A. The render gate

`tools/studies_render_probe.py` renders this board headlessly under a dozen control combinations
— every strategy, one strategy, each profit stage, each comparison basis, each ordering, the
value zoom and the time scope — and fails if any of them throws, draws more than one chart, or
empties the tables. `tools/wt.py ship` runs it whenever `index.html` changed, alongside the boot
gate. The boot gate only ever proved that the app starts; it never enters a view, and this repo
has shipped a view that crashed behind a green boot gate.

Run it yourself after touching the registry or the renderer:

    python tools/studies_render_probe.py

It needs no Firebase sign-in, because the registry is static data inside `index.html`. Run
history therefore reads as empty in the probe, so its counts are a floor: signed in, rows backed
by real runs pick up their run windows and the COMMON WINDOW basis reaches more of them.

---

## 7. Worked example — adding one new study

Suppose a new study finished: three volatility-band variants of ORB, discovered on
2026-09-02, two of them saved as real validate runs. The highest free row number on the
board is 66, so the new rows are 67, 68 and 69.

Append this to the end of the `RESEARCH_STUDIES` array:

```js
{key:'orbband',title:'ORB volatility-band variants',disc:'2026-09-02',isLbl:'IN-SAMPLE',fam:'ORB',
 sub:'Three volatility-band widths on the standing ORB crown. NQ 5-minute bars, 2010 to 2026.',
 notes:['The wide band is the only variant that held its lockbox stretch.',
        'Read this study on raw profit. Every row trades one strategy on one contract, so the dollars are comparable.'],
 dashWhy:{trd:'The study recorded money and ratios only, so no trade count exists for this row.'},
 rows:[
  {n:67,name:'ORB Crown',what:'The standing ORB crown, no band.',tone:'champ',read:'The thing to beat',
   live:'crown',liveWhy:'The standing ORB champion. It is not the configuration running in paper.',
   runs:[234],is:300932,wf:210441,lb:88943,tot:389874,dd:29142,pf:1.31,trd:2607},
  {n:68,name:'Band Wide',what:'Enter only outside a wide volatility band.',tone:'good',read:'Beats it and held up',
   runs:[271],is:311204,wf:219880,lb:94110,tot:405314,dd:27503,pf:1.34,trd:2402},
  {n:69,name:'Band Tight',what:'Enter only outside a tight volatility band.',tone:'fail',read:'Fails on profit',
   is:262040,wf:181330,lb:70115,tot:332155,dd:31880,pf:1.24}
 ]}
```

What happens with no further code change:

- A tile appears at the bottom of the board with the chart, the table and the two notes.
- `ORB` already exists as a strategy-type button, so these rows join it. Had `fam` been a new
  name, a new button would have appeared on its own.
- `2026-09-02` appears as a new DISCOVERED filter button.
- Rows 67 and 68 count as "ran as a run" and open their reports when clicked. Row 69 prints
  `local` and shows a dash under DATE RAN.
- Row 69 has no `trd`, so its trade cell is a dash that says the study recorded money and
  ratios only.
- Row 67 shows a CROWN pill and a thin ring on the chart; rows 68 and 69 show a dash under STATUS
  because they declared no `live` value, which is the correct reading for a research variant.
- Every row has all four stages, so nothing drops off the chart at any stage setting. Had
  row 69 lacked `wf`, selecting the walk-forward stage would drop it off the chart, the line
  under the chart would say one of three rows is not plotted and why, and its walk-forward
  cell would be a dash. Nothing would be borrowed to fill it.

Finally, follow the repo's standing release rule: bump `VERSION` in `index.html` by 0.1,
prepend a short entry to the `CHANGELOG` array, and ship from your own worktree.

---

## 7A. The view preferences this board persists

All of them go through the same `savePref` store every other view preference on the site uses, so
they survive a reload and a re-render. None of them is registry data.

| Preference | Values | What it holds |
| --- | --- | --- |
| `resStage` | `is` `wf` `lb` `tot` | the profit stage |
| `resAxis` | `auto` `raw` `ratio` | the vertical axis |
| `resDate` | `disc` `ran` `res` | the order-by control |
| `resFilt` | JSON object of arrays | the filter chips |
| `resScope` | `all` `7` `30` `90` | the time scope |
| `resSBasis` | `follow` `disc` `ran` | which date the time scope reads |
| `resColour` | `theme` `on` `off` | the board-only colour setting |
| `resBasis` | `asis` `common` `year` | **new** — the fair-comparison basis |
| `resZoom` | `all` `95` `90` `80` | **new** — how much of the value range the axes trim |
| `resChH` | object, study `key` to a number | **new** — the dragged chart height per study, in the chart's own drawing units, clamped to 260–1400. A study absent from the object is at the standard 440. |

---

## 8. What is on the board today (2026-08-19)

16 studies, 215 rows.

| Study | Rows | What it covers |
| --- | --- | --- |
| NOISE single-strategy variants | 1–27 | The twenty-six filter variants of the NOISE strategy. |
| Does the weak-close filter transfer? | 47–66 | The weak-close filters carried across to ORB and ENGU-Q. |
| ORB breakeven and plateau hunt | 67–77 | Eleven exit variants of the ORB crown on identical entries. |
| ORB grail hunt, round one | 78–83 | The six searches that rebuilt ORB on a legally fillable entry. |
| ENGU-Q session and entry variants | 84–92 | Day session against 24 hours, timeframe, and how the entry fills. |
| What is running in paper right now | 93–99 | The live paper legs. Table only, no chart. |
| ORB round three, the entry re-opened | 100–115 | The ORB entry re-tested under the current exit. |
| ORB ideas tested and killed | 116–129 | ORB ideas measured against the crown and rejected. |
| ENGU-Q limit depth, the whole curve | 130–142 | The rest of the ENGU-Q limit-depth curve. |
| ENGU-Q short mirror | 143–146 | The ENGU-Q short mirror. |
| ENGU-Q bar type and trailing stop | 147–158 | ENGU-Q bar type and trailing stop. |
| ENGU-Q concurrent positions | 159–160 | ENGU-Q concurrent positions. |
| NOISE parameter sweep, the cells behind the headlines | 161–183 | The NOISE campaign cells the round log only reported as a family verdict. |
| Do the NOISE filters carry to the ES contract? | 184–192 | The same nine NOISE configurations on a second contract, nothing re-fitted. |
| NOISE trade-context scan | 193–198 | Six blind scans, ninety-six statistical tests. Table only, no chart. |
| ORB hunt, the rest of the local cells | 199–235 | The rest of the August 17th ORB exit hunt, never saved as runs. |

Row 26 sits inside the NOISE study as a cross-reference to the older ORB crown, which is one
reason the NOISE study's row numbers are not contiguous. The other reason is row 25, which was
retired on 2026-08-19 and is described immediately below.

### Retired row numbers — never reuse these

On 2026-08-19 the owner had every pooled-book study taken off this board, for the reason given
in section 6. Forty-six rows were removed and their numbers are retired for good. Row numbers
are permanent handles, so nothing that stayed was renumbered and none of these numbers may ever
be handed to a future row. The next free row number on this board is 262, not 236 and not 25.

| Retired | Count | What it was |
| --- | --- | --- |
| 25 | 1 | The ORB-plus-NOISE pooled book that sat inside the NOISE study as a cross-reference. This is the row the owner named directly. |
| 28–46 | 19 | The pooled-books study: every two-leg and three-leg combination. |
| 236–251 | 16 | The book leg weighting grid. |
| 252–261 | 10 | The ten book legs re-measured on the book's own drawdown convention. |

None of the retired rows was tagged as crowned or as running in the paper forward test, so no
status tag moved and nothing on the board claims a book is being forward-tested. The research
behind all forty-six rows is untouched and still recorded in `BOOK.md`.

**The mismatch the board currently shows.** The crowned ORB configuration is row 67, and the
configuration the paper forward test is actually running is rows 26, 83 and 93 — the *previous*
crown. Filtering STATUS to CROWNED ONLY and then to IN PAPER ONLY shows this in two clicks. Fixing
it is a deployment decision and belongs to the owner, not to the board.

---

## 9. Local research, and the three rules it needs

Most of the studies added on 2026-08-19 are **local research**: work run through a committed
Python harness that never became a saved Auto-Validate run. None of those rows carries a `runs`
array, so every one of them prints `local` in the RUN column and none of them carries a date ran.
Three rules apply to this kind of study, and they matter more here than anywhere else on the
board.

**Never write a figure you did not measure.** Every number in those studies came either verbatim
from a committed round log or from re-running the committed harness. Where a harness was re-run,
the cells that overlap rows already on the board were checked against them and reproduce them to
the dollar; that check is what licenses the rest of the re-run. If you cannot reproduce a figure
cheaply, the row still belongs on the board with a dash and a reason.

**A cell that was tested and died still belongs on the board.** Two rows in the NOISE parameter
sweep carry dashes across every column, because the round log recorded that the cell was run and
failed but never wrote down its settings or its figures. They are on the board anyway, with the
reason on hover, because "this was tried and it did not work" is exactly the thing the board
exists to stop somebody rediscovering the expensive way.

**Say when a row is not one tested configuration.** Two of these studies are not straightforward
grids of backtests, and each says so in its own description rather than letting the reader assume.
The trade-context study is six statistical scans standing for ninety-six tests, over only two
backtested configurations, both of which were already on the board. A summarised row must never
be presented as if it were a single tested configuration, and a re-measurement must never be
counted as a new thing tested.

**One more practical note.** Several sessions add to this registry at the same time. Before you
write a row number, read the highest number currently on `origin/main` rather than the highest
number in your own checkout, and if you find that a concurrent session has already recorded a
configuration you were about to add, leave theirs alone and say in your own study's notes which
rows carry the rest of the family. Row numbers are permanent handles and a duplicate is worse
than a gap.

### Repeats and the duplicate-work guard

On 18 August 2026 four pinned NOISE validates ran twice. One session queued them and died;
a second session checked the queue, saw only jobs that were still queued or running, did not
see the four that had already **finished**, and queued them again. The repeats produced
identical figures, which is a real reliability check but adds no new evidence.

Two things came out of that. The repeats (runs 251, 252, 253 and 254) were archived, and the
four rows that named them moved those ids from `runs` into the new `repeats` field. And the
system now notices: every job is fingerprinted on the fields that decide its numbers, and that
fingerprint is compared against finished jobs as well as in-flight ones. The Builder asks
before queueing a repeat; the runner lets it through but tags it, so a future repeat arrives on
this board already labelled instead of waiting for somebody to spot four identical rows.
