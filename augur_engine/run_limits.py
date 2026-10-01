"""WHAT THIS RUN DOES NOT MODEL - worked out from the run's own settings.

WHY (owner GO 2026-09-30, from MANAGER's ziplime review, idea 3). Every run report states what
the run found. None of them state what it assumed. Those assumptions are written down across
ROLL_AUDIT.md, RESEARCH.md, docs/DATA_TAIL_2026.md and a dozen memory notes, which means they
are remembered by whoever happens to have read them recently. A reader six months from now, or
the owner deciding whether to trade a crown, has no way to see them from the report.

So this builds the list PER RUN, from that run's settings, rather than printing a fixed
paragraph. A run on roll-corrected data should not be warned about roll jumps; a run that ends
before June 2026 should not be warned about the summer data hole. A fixed list would be ignored
within a week - only a list that changes with the run is worth reading.

The CAUTIONS strip already shows profit concentration and failed diagnostics. This is the other
half: the things that did not fail because they were never tested.

Each item is {key, severity, text}. `severity` is "material" when it has been measured to move
a headline number on this kind of run, else "note". The engine emits them; showing them is
COMPARE-RUNBOARD's side.
"""

# Measured facts this module cites, so the numbers live in one place and are traceable.
ROLL_SHARE_OF_ENGUQ_LOCKBOX = 0.31        # ROLL_AUDIT.md: roll jumps were 31% of #335's LB net
RAW_FEED_ENDS = "2026-06-07"              # databento_raw stops here
SUMMER_HOLE = ("2026-06-30", "2026-08-06")
ESTIMATED_SWITCH_MONTH = "2026-06"        # the one 2026 offset that can never be measured


def _overlaps(date_from, date_to, lo, hi):
    """True when [date_from, date_to] overlaps [lo, hi]. Missing bounds mean "open"."""
    a = str(date_from or "0000-00-00")[:10]
    b = str(date_to or "9999-99-99")[:10]
    return not (b < lo or a > hi)


def not_modelled(run):
    """The list for one run.

    `run` is a plain dict of what the report already knows:
        instrument, timeframe, session, source (the master's source tag),
        date_from, date_to, cost_pts, family, n_trades,
        lockbox_trades, lockbox_net, lockbox_top_trade_net,
        pnl_units ('pts' or 'usd'), marked_daily (bool), fill_rule (str)
    Anything missing is simply not asserted about - a thinner run gets a shorter list, never a
    wrong one.
    """
    r = run or {}
    out = []

    def add(key, severity, text):
        out.append(dict(key=key, severity=severity, text=text))

    # ---------------------------------------------------------------- costs and fills
    cost = r.get("cost_pts")
    if cost is not None:
        add("flat_cost", "material",
            "Cost is one flat %.3f points per round trip, the same in a quiet market and a fast "
            "one, and it does not grow with size. The run report's realistic-cost reading shows "
            "what changes when that assumption is dropped." % float(cost))
    if r.get("fill_rule"):
        add("fill_rule", "note",
            "Fills follow this family's rule (%s). A bar that trades through a level is assumed "
            "to fill there; a queue that never reached you is not modelled."
            % r["fill_rule"])
    else:
        add("fill_rule", "note",
            "Fills assume a level touched inside a bar is a level filled. Order queues, partial "
            "fills and a book that thins out are not modelled.")
    add("no_margin", "note",
        "Margin is not modelled: the run never runs out of money, is never called, and never "
        "has a position reduced for it.")

    # ------------------------------------------------------------------------- the data
    src = str(r.get("source") or "")
    if src.startswith(("db_adj", "db_fadj")):
        add("roll_corrected", "note",
            "This run reads roll-corrected prices, so contract changes are taken out. Two 2026 "
            "switches rest on an estimated offset (%s can never be measured - the second feed "
            "starts after it), and any bar that spanned a switch was rebuilt as a body with no "
            "wick." % ESTIMATED_SWITCH_MONTH)
    elif src.startswith(("db_noadj", "nt_noadj", "tv", "merged", "yahoo")):
        add("no_adjust_rolls", "material",
            "Prices are NOT roll-adjusted, so each quarterly contract change leaves a step that "
            "is not a price move. A rule that holds across one books that step as profit or "
            "loss and its stops can fire on it - measured at %d%% of one crown's sealed-year "
            "net." % round(ROLL_SHARE_OF_ENGUQ_LOCKBOX * 100))

    # Only speak about the window when the run actually gave one. Treating a missing bound as
    # "open" made a run with no dates inherit every date-based warning, which is the opposite
    # of the rule this module follows: a thinner run gets a shorter list, never a wrong one.
    has_window = bool(r.get("date_from") or r.get("date_to"))
    if has_window and _overlaps(r.get("date_from"), r.get("date_to"), RAW_FEED_ENDS, "9999-99-99"):
        add("secondary_feed", "material",
            "Bars after %s come from a secondary feed, not the purchased raw one, and were "
            "matched to it only approximately. Anything this run concludes about the last few "
            "months rests on that." % RAW_FEED_ENDS)
    if has_window and _overlaps(r.get("date_from"), r.get("date_to"), *SUMMER_HOLE):
        add("summer_hole", "material",
            "The window spans the %s to %s gap in the minute data. Days inside it are missing "
            "rather than flat, so per-day statistics over that stretch are computed on fewer "
            "days than the calendar suggests." % SUMMER_HOLE)

    # --------------------------------------------------------- how profit is counted
    if r.get("marked_daily") is False:
        add("close_day_pnl", "material",
            "Profit is counted on the day a trade closes, not day by day while it is open, so a "
            "drawdown that happened inside a long hold does not appear. A held position can hide "
            "a dip that a daily mark would show.")
    if str(r.get("pnl_units") or "").lower() == "pts":
        add("points_not_money", "note",
            "Results are in points. Turning them into money assumes one contract size "
            "throughout and no currency effect.")

    # ------------------------------------------------------- how much the test proves
    lb_n = r.get("lockbox_trades")
    if lb_n is not None and lb_n < 50:
        add("thin_lockbox", "material",
            "The sealed test holds only %d trades, below the 50 the house rule asks for, so it "
            "can confirm very little on its own." % int(lb_n))
    net, top = r.get("lockbox_net"), r.get("lockbox_top_trade_net")
    if net and top and net > 0:
        share = float(top) / float(net)
        if share >= 0.5:
            add("one_trade_lockbox", "material",
                "One trade is %d%% of the sealed-test profit. Without it the sealed result is "
                "%s, so the test is really one observation." % (round(share * 100),
                 "still positive" if (net - top) > 0 else "NOT profitable"))
    n = r.get("n_trades")
    if n is not None and n < 100:
        add("thin_sample", "note",
            "%d trades in total. Any per-trade average here moves a lot on one outcome." % int(n))

    add("no_forward_test", "note",
        "This is a backtest. It does not model the broker rejecting an order, a feed dropping "
        "out mid-session, or the machine being off - all three have happened in paper trading.")
    return out


def lines(run):
    """The same list as plain sentences, in report order: material first."""
    items = not_modelled(run)
    mat = [i["text"] for i in items if i["severity"] == "material"]
    note = [i["text"] for i in items if i["severity"] != "material"]
    return mat + note


def counts(run):
    items = not_modelled(run)
    return dict(total=len(items),
                material=sum(1 for i in items if i["severity"] == "material"),
                note=sum(1 for i in items if i["severity"] != "material"))
