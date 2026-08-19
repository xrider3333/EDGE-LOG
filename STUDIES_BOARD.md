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

Every study renders as one tile. A tile is a heading, a one-line description, a scatter
chart, a scrolling table, and a short list of plain-English notes underneath.

All of the data lives in one array called `RESEARCH_STUDIES`, near the top of the compare
section of `index.html`, directly under the RUNBOARD data. **The renderer below that array
holds no data at all.** You add a study by appending one entry to the array. You never
edit the renderer to add data.

---

## 2. The controls at the top of the board

These controls apply to every study on the board at once, and each one changes the chart
and the table together, so the two can never disagree.

**PROFIT STAGE — in-sample, walk-forward, lockbox, or total.** This picks which stretch of
history every row is read on. It sets the height of every chart point, it highlights the
matching money column in every table, and it drives the profit-divided-by-drawdown column.
A row that genuinely has no figure for the selected stage shows a dash, the dash says why
when you hover it, and the row drops off the chart with the omitted-count line updating.
**A figure from a different stage is never put in its place.**

**VERTICAL AXIS — per study, raw profit, or profit divided by drawdown.** Raw profit plots
the money itself and its tick labels read as dollars. Profit divided by drawdown plots a
plain number and its tick labels carry no dollar sign. PER STUDY lets each study keep the
default it declared. Every study on the board is single strategies on one contract, so they
all declare raw profit today.

**ORDER BY — discovered, date ran, or result.** Discovered keeps the registry order, which
is the order the owner approved. Date ran reads the real finish date out of run history and
splits the table into a block that was run and a block that never was. Result sorts best
first on whatever stage and axis are selected.

**Filters — strategy type, verdict, discovered date, run status, status.** These are built from the
data. The renderer walks every row in the registry, collects the distinct values of each
tag, and makes a button for each one. A new study that tags its rows gets its buttons for
free. Filters narrow the chart and the table at the same time, and the board always states
how many rows are hidden.

**CLEAR FILTERS** appears only while something is filtered and drops all of them.

**COMPARE ON — ratios as is, common window, or per year.** Raw totals measured over different
stretches of history are not comparable, and section 4A explains why the board already knew that.
This control decides the basis every figure on the board is read on, and the board always states
in words which basis is in force and how many of the rows now shown it can actually reach.

- **RATIOS AS IS** is what the board has always done. Every figure is exactly what its row
  recorded, over whatever window that row happens to cover. It reaches every row. The
  common-window warning underneath still says where the windows disagree.
- **COMMON WINDOW** is the rigorous option and it costs no re-running. Where a row is backed by a
  real run with a saved equity curve, the curve is sliced to the stretch the rows on that tile
  genuinely share, and the profit and the worst drawdown are recomputed on exactly that slice.
  Four extra columns appear — COMMON $, COMMON DD, COMMON PF and COMMON ÷DD — and the chart plots
  the sliced figure. **A row that cannot be recomputed shows a dash that says why on hover, never
  its un-sliced figure.** PROFIT STAGE is ignored under this basis and the board says so out loud:
  the shared stretch is a calendar range and a stage is a different cut of the same run.
- **PER YEAR** divides each row's own profit by the number of years its own window covers, so a
  longer window is not automatically flattered. It needs only a recorded data window and not a
  saved curve, which makes it the widest-coverage option. Three extra columns appear — PER YEAR,
  YEARS and PER YR÷DD.

**How the common-window slice actually works, and its three honest limits.** A run saves its
champion equity as a *downsampled* cumulative curve plus the run's from-date and to-date and,
where the run had a lockbox, the index at which the lockbox begins together with the lockbox's own
start date. Those are the only points on the curve whose calendar date is recorded. Everything
between two of them is ordered by trade, not by calendar, so a cut inside a long undated stretch
could only be guessed.

1. **A cut may only land inside a dated stretch of at most 800 days.** Anything else is refused
   with a dash naming the stretch and its length. In practice the common window's start is every
   run's own start date (exact, no placing at all) and its end falls inside the lockbox year, which
   is dated. A run that saved no lockbox boundary is refused, and that is the intended outcome.
2. **The sliced drawdown is a floor.** It is read off the downsampled curve, which nets several
   trades into each point, so the true worst drawdown on the slice can only be deeper. It is also
   not the same measurement as the DRAWDOWN column, which came off the run's own saved figures, so
   the two can differ in either direction. The hover text says both things on every figure.
3. **Profit factor cannot be recomputed at all.** Gross winnings over gross losses needs every
   individual trade, and netting trades into curve points destroys exactly that. COMMON PF is
   therefore always a dash carrying that explanation. It is never estimated.

A figure whose end-of-window cut had to be placed rather than read carries a `≈` after it, and the
hover says which dated stretch it was placed inside and how long that stretch was.

**Which ratio survives a slightly mismatched window.** This is printed in the UI under the
controls, and it reflects what this project has measured rather than a preference. Profit factor is
the most robust of the three, because it is a property of the whole trade population, so a few
extra weeks move it only a little. Profit divided by drawdown is the most fragile, because a
drawdown is one single worst event and one extra month can introduce a new worst event that moves
the figure a long way — this project measured the confidence interval around a maximum drawdown to
be wider than the drawdown itself. Sharpe sits between the two. The board carries no Sharpe column
today, so that last point is guidance for reading Sharpe on the run reports.

**VALUE ZOOM — fit all, trim 5%, trim 10%, trim 20%.** The chart axes have always spanned only the
rows actually plotted, so filtering already rescales them; FIT ALL is that plain fit-to-visible
reading and is the default. What filtering cannot fix is one distant row squashing all the others
into a band, and the trim settings drop that percentage of the most extreme values off both axis
ranges so the cluster spreads out. **Nothing is hidden by it.** A row pushed outside the range is
still drawn, pinned to the edge it ran off, given a dashed warning ring, and named under the chart
with the figure it actually holds.

**Chart height — the drag handle under every study chart.** Each chart carries the same slim drag
bar the run report puts under every one of its charts. Drag it down and the chart grows, drag it up
and it shrinks, double-click it and the chart returns to the standard height. The size is remembered
**per study** and persisted like every other view preference here, so it survives a reload. What is
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

**COLOUR — theme, colour, or shapes only.** This changes this board alone and never touches the
app theme. COLOUR forces the five approved colours whatever the theme is doing: blue for the
champion, green for held up, amber for fragile, red for failed and grey for reference. SHAPES
ONLY drops everything to one neutral ink.

THEME follows the app theme, with one deliberate exception. The MONO theme has no colours to
follow: its accent variables are all greys (blue #b0b0b0, green #f0f0f0, yellow #999999, red
#4d4d4d), so following it paints all five verdicts in five near-identical greys and two of them
are nearly invisible on the dark background. THEME therefore reads the accent variables at render
time, measures how much colour they actually carry, and when they are genuinely greyscale it
falls back to the five approved colours rather than five greys. On a colour theme THEME behaves
exactly as it always did. The app theme itself is never modified in either case, and SHAPES ONLY
is still there for anyone who wants the pure one-ink reading.

**The verdict shapes are drawn in all three settings.** Colour is reinforcement laid on top of
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
| `chart` | no | The scatter chart block, described below. Leave it out and the study renders as a table only. |
| `dashWhy` | no | An object mapping a field name to the reason its dash shows, for every row in the study. |
| `win` | no | The default **data window** for every row in the study that has neither a run nor its own `win`. See section 4A. |
| `rows` | yes | The array of rows. |

### The `chart` block

| Field | Required | What it is |
| --- | --- | --- |
| `x` | yes | The field name driving horizontal position. In every study so far this is `dd`, the worst drawdown. |
| `xCap` | yes | The horizontal axis caption. It must say which direction is better, for example "Worst drawdown — further LEFT is better". |
| `yMode` | yes | The study default for the vertical axis: `ratio` or `raw`. |
| `tip` | no | An array of extra field names named in the hover text of every point. |
| `xFmt` | no | `money` or `num` for the horizontal ticks. It defaults to money for the money columns and to a plain number otherwise. |

**There is no `y` field and no `yCap` field.** The vertical axis is always the profit stage
the owner selected, either raw or divided by drawdown, and its caption is written for you.
That is what makes every study on the board apples to apples: two studies open side by side
are always being read on the same stretch of history in the same unit.

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

## 7. Worked example — adding one new study

Suppose a new study finished: three volatility-band variants of ORB, discovered on
2026-09-02, two of them saved as real validate runs. The highest free row number on the
board is 66, so the new rows are 67, 68 and 69.

Append this to the end of the `RESEARCH_STUDIES` array:

```js
{key:'orbband',title:'ORB volatility-band variants',disc:'2026-09-02',isLbl:'IN-SAMPLE',fam:'ORB',
 sub:'Three volatility-band widths on the standing ORB crown. NQ 5-minute bars, 2010 to 2026.',
 chart:{x:'dd',xCap:'Worst drawdown — further LEFT is better',yMode:'raw',tip:['dd','tot']},
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
