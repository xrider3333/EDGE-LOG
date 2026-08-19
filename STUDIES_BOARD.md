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

## 2. The five controls at the top of the board

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
default it declared, which is the ratio for pooled books and raw profit for single
strategies.

**ORDER BY — discovered, date ran, or result.** Discovered keeps the registry order, which
is the order the owner approved. Date ran reads the real finish date out of run history and
splits the table into a block that was run and a block that never was. Result sorts best
first on whatever stage and axis are selected.

**Filters — strategy type, verdict, discovered date, run status.** These are built from the
data. The renderer walks every row in the registry, collects the distinct values of each
tag, and makes a button for each one. A new study that tags its rows gets its buttons for
free. Filters narrow the chart and the table at the same time, and the board always states
how many rows are hidden.

**CLEAR FILTERS** appears only while something is filtered and drops all of them.

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
| `fam` | yes | The default strategy-type tag for every row, such as `NOISE`, `ORB`, `ENGU-Q` or `BOOK`. This is what the STRATEGY TYPE filter is built from. |
| `isLbl` | yes | The heading for the in-sample money column. Use `IN-SAMPLE` when the study really has a separate walk-forward stage. Use `PRE-LOCKBOX` when that figure is everything before the lockbox pooled together, which is what a pooled book has. |
| `chart` | no | The scatter chart block, described below. Leave it out and the study renders as a table only. |
| `dashWhy` | no | An object mapping a field name to the reason its dash shows, for every row in the study. |
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
| `why` | no | An object mapping a field name to the reason its dash shows, overriding `dashWhy` for this row alone. |

**Do not supply a profit-divided-by-drawdown figure.** The board computes it from the
selected stage profit and the drawdown, so it always matches whatever stage is on screen.

---

## 5. Tagging so the filters pick a row up

Three of the four filters read tags you supply.

**Strategy type** reads `fam` on the row, falling back to `fam` on the study. Use the family
name the owner already says out loud: `NOISE`, `ORB`, `ENGU-Q`, `BOOK`. If you invent a new
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

**Books and single strategies are never compared head to head.** A pooled book trades
several strategies at once, so it ties up more margin than any single strategy. Its raw
dollar profit is bigger for that reason alone and the comparison means nothing. Give every
book study `yMode:'ratio'` so it opens on profit divided by drawdown, which is the fair
cross-study comparison, and say so in the study's notes. Each study also gets its own tile
and its own table for exactly this reason.

**Drawdown is always positive.** The column heading already says drawdown, so a leading minus
sign is wrong. Losing money figures in the profit columns do keep their minus sign.

**Do not compare across windows.** Two rows measured on different date ranges are not
comparable even inside one study. Say so in the row's `what` line and in the study notes, and
use the strategy-type filter to let the owner read each family on its own.

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
- Every row has all four stages, so nothing drops off the chart at any stage setting. Had
  row 69 lacked `wf`, selecting the walk-forward stage would drop it off the chart, the line
  under the chart would say one of three rows is not plotted and why, and its walk-forward
  cell would be a dash. Nothing would be borrowed to fill it.

Finally, follow the repo's standing release rule: bump `VERSION` in `index.html` by 0.1,
prepend a short entry to the `CHANGELOG` array, and ship from your own worktree.
