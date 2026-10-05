"""RESMOM r1 - export the registered cells' WF daily P&L on #463's book index, so later families can run their book-add REPORT
INCREMENTALLY over the open RESMOM forward line (standing order addendum 2, MANAGER #73 / #74): #463 + 0.264 x RES + c x cell
against #463 + 0.264 x RES. Same registered reading as Stage A (positions with a flag inside the hold removed), WF only - the
loaders cut every input before 2025-06-30; the sealed year is never read. Writes resmom_cells_daily_wf.csv (date, book_mtm,
RES, RAW) + a .sha256 file beside it.   usage (from the worktree, EDGELOG_ROOT = the shared checkout):
    python tools/rocfrontier/r17_resmom_export.py"""
import hashlib, json, os, sys, time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import r17_resmom as M                                                         # noqa: E402  (the registered harness, unchanged)

OUT_CSV = os.path.join(M.OUT, "resmom_cells_daily_wf.csv")
LINE_C = 0.264                                                                 # the frozen volatility c of the RESMOM forward line (PREREG_RESMOM_LINE_R1.txt [F2])


def main():
    pok = M.prereg_ok()
    t0 = time.time()
    cal, _ = M.wide_load(M.S.LB0)
    B, _ = M.A13.load_463()
    bk, dd, S12 = M.book_checks(B)
    if not (bk["ok"] and dd["ok"]):
        M.refuse("export refused: #463 does not reproduce the registered WF numbers / drawdown structure (nothing written)")
    D = M.load_data(M.S.LB0)
    tbis = M.D15.load_tbis(M.S.LB0)
    es_frames, _ = M.D15.load_es(M.S.LB0)
    W = M.build_world(D, M.S.LB0, es_frames, tbis, cal)
    M.D15.release(D)
    M.apply_audit(W, M.read_audit())
    rows = M.A13.book_rows(B, W)
    L = M.rm_build(W, M.WF0, M.PRE_END, "remove")
    cols = {}
    for cell in M.CELLS:
        base = M.run_cell(W, M.cell_leg(L, cell), M.D15.l1_cfg(), pos=True)
        cols[cell] = M.D15.to_B(base.x, rows, B.n)
    idx = pd.DatetimeIndex(B.index)
    df = pd.DataFrame({"date": idx.strftime("%Y-%m-%d"), "book_mtm": np.asarray(B.raw, float), "RES": cols["RES"], "RAW": cols["RAW"]})
    wf = (idx >= M.WF0) & (idx <= M.PRE_END)
    df = df[wf].reset_index(drop=True)
    assert (pd.to_datetime(df["date"]) < M.S.LB0).all(), "the export must stop before the sealed year"
    # the cross-check that this IS Stage A's reading: the WF nets equal resmom_stageA.json's
    sa = json.load(open(os.path.join(M.OUT, "resmom_stageA.json")))["stageA"]["cells"]
    for cell in M.CELLS:
        want = sa[cell]["base"]["net"]
        got = float(df[cell].sum())
        if abs(got - want) > 0.01:
            M.refuse(f"export refused: {cell}'s WF net {got:,.2f} is not Stage A's {want:,.2f} (nothing written)")
    os.makedirs(M.OUT, exist_ok=True)
    df.to_csv(OUT_CSV, index=False, float_format="%.6f", lineterminator="\n")
    sha = hashlib.sha256(open(OUT_CSV, "rb").read()).hexdigest()
    with open(OUT_CSV + ".sha256", "w") as f:
        f.write(sha + "  " + os.path.basename(OUT_CSV) + "\n")
    line = df["book_mtm"] + LINE_C * df["RES"]
    st = M.R11.stats(line.to_numpy(float), pd.DatetimeIndex(pd.to_datetime(df["date"])))
    print(f"prereg {'verified' if pok['verified'] else 'NOT verified'}; {len(df):,} WF rows {df['date'].iloc[0]} .. {df['date'].iloc[-1]}; nets RES ${df['RES'].sum():,.0f} "
          f"RAW ${df['RAW'].sum():,.0f} (= Stage A's); the forward line's WF reference #463 + {LINE_C} x RES: {json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in st.items() if k in ('roc', 'sort', 'max_dd', 'net')})}")
    print(f"written {OUT_CSV} sha256 {sha} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
