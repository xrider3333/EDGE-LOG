"""tools/import_nt_ohlc.py imports only the NinjaTrader capture (MANAGER #152, 2026-10-10)."""
from tools import import_nt_ohlc as I


def test_only_files_with_the_order_flow_columns_are_ours():
    nt = "time,open,high,low,close,volume,delta,buy_vol,sell_vol,tick_count,rt".split(",")
    qqq_cache = "time,open,high,low,close,volume".split(",")
    assert I.is_nt_capture(nt)
    assert not I.is_nt_capture(qqq_cache)
