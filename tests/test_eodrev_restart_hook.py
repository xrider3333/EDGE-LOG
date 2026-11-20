"""PICK6 #511 restart hook (11-20): `run --resume-only` (edgelog-eodrev-resume.service at
boot) and `alert-failed` (edgelog-eodrev-alert.service, OnFailure=). Resume only inside
15:27-16:00 ET, filled qty only, never a fresh entry; after 16:00 an alert and no order."""
import datetime as dt
import json
import os
from zoneinfo import ZoneInfo

from api import eodrev_exec as ex

ET = ZoneInfo("America/New_York")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeAd:
    def __init__(self):
        self.sent = []

    def place_stock_order(self, **k):
        self.sent.append(k)
        return {"ok": True, "reason": "", "_qty": k["qty"],
                "client_order_id": k["signal_id"], "parts": [{"client_order_id": k["signal_id"]}]}


def _leg(leg, sym, side, qty, bday="2026-11-16", **kw):
    sid = f"EODREV-{bday.replace('-', '')}-{leg.split('_')[-1]}-O"
    return dict({"leg": leg, "sym": sym, "side": side, "qty": qty, "open_ok": True, "open_sid": sid,
                 "open_rec": {"ok": True, "_sid": sid, "client_order_id": sid}}, **kw)


def _state(tmp, entries, bday="2026-11-16"):
    with open(os.path.join(str(tmp), "exec_state.json"), "w") as f:
        json.dump({"open_basket": {"day": bday, "entries": entries}}, f)


def _resume(tmp, monkeypatch, hh, mm, fills=None, signal=False):
    if signal:   # a valid signal + passed probe: a fresh entry WOULD be possible
        with open(os.path.join(str(tmp), "probe.jsonl"), "w") as f:
            f.write(json.dumps({"results": [{"open_ok": 1, "exit_filled": 1}] * 2}) + "\n")
        with open(os.path.join(str(tmp), "signal_2026-11-16.json"), "w") as f:
            json.dump({"date": "2026-11-16", "asof_et": "15:20:00", "status": "OK", "k": 1,
                       "long": [{"sym": "AAPL", "px": 230.0, "exch": "NASDAQ"}],
                       "short": [{"sym": "JPM", "px": 250.0, "exch": "NYSE"}]}, f)
    fills = fills or {}
    monkeypatch.setattr(ex, "lookup", lambda a, rec: fills.get(
        rec["_sid"], {"status": "FILLED", "filled": rec.get("_qty", 0), "price": 1.0}))
    monkeypatch.setattr(ex, "LOOKUP_PAUSE_S", 0)
    ad, notes = FakeAd(), []
    rec = ex.resume_only(ex.paths(str(tmp)), now_fn=lambda: dt.datetime(2026, 11, 16, hh, mm, tzinfo=ET),
                         adapter=ad, log=lambda *a: None, notify=lambda m, **k: notes.append(m),
                         sleep=False)
    return rec, notes, ad


def test_crash_mid_basket_rerun_resumes_and_exits_only_filled_qty(tmp_path, monkeypatch):
    _state(tmp_path, [_leg("EODREV_L1", "AAPL", "long", 14), _leg("EODREV_S1", "JPM", "short", 13)])
    fills = {"EODREV-20261116-L1-O": {"status": "PARTIALLY_FILLED", "filled": 5, "price": 230.0},
             "EODREV-20261116-S1-O": {"status": "FILLED", "filled": 13, "price": 250.0}}
    rec, notes, ad = _resume(tmp_path, monkeypatch, 15, 41, fills)
    q = {k["signal_id"]: k["qty"] for k in ad.sent}
    assert q == {"EODREV-20261116-L1-X": 5, "EODREV-20261116-S1-X": 13}
    assert all(k["intent"] == "CLOSE" for k in ad.sent)
    assert "RESTART" in notes[0] and rec["resumed_on"] == "2026-11-16"
    st = json.load(open(os.path.join(str(tmp_path), "exec_state.json")))
    assert "open_basket" not in st


def test_reboot_after_1600_alerts_only_no_order(tmp_path, monkeypatch):
    _state(tmp_path, [_leg("EODREV_L1", "AAPL", "long", 14), _leg("EODREV_S1", "JPM", "short", 13)])
    rec, notes, ad = _resume(tmp_path, monkeypatch, 16, 12)
    assert not ad.sent
    assert len(notes) == 1 and "after 16:00" in notes[0] and "2 basket legs" in notes[0]
    assert rec["result"] == "resume-only: after 16:00, alert only"


def test_no_basket_file_is_a_noop(tmp_path, monkeypatch):
    rec, notes, ad = _resume(tmp_path, monkeypatch, 15, 40, signal=True)
    assert rec["result"] == "resume-only: nothing to resume" and not ad.sent and not notes


def test_resume_only_never_makes_a_fresh_entry(tmp_path, monkeypatch):
    # valid signal + probe, no basket, inside the window: still nothing sent
    rec, notes, ad = _resume(tmp_path, monkeypatch, 15, 29, signal=True)
    assert not ad.sent and not notes
    # a basket whose legs are all already exited: nothing to resume either
    _state(tmp_path, [_leg("EODREV_L1", "AAPL", "long", 14, exit_ok=True,
                           exit_rec={"ok": True, "_sid": "EODREV-20261116-L1-X"})])
    rec, notes, ad = _resume(tmp_path, monkeypatch, 15, 45, signal=True)
    assert not ad.sent and rec["result"] == "resume-only: nothing to resume"
    # and run_day(resume_only=True) with no basket returns before any entry path
    rec = ex.run_day(ex.paths(str(tmp_path)), now_fn=lambda: dt.datetime(2026, 11, 16, 15, 29, tzinfo=ET),
                     adapter=ad, log=lambda *a: None, notify=lambda m, **k: None, sleep=False,
                     resume_only=True)
    assert not ad.sent


def test_before_window_and_yesterdays_basket_are_noops(tmp_path, monkeypatch):
    _state(tmp_path, [_leg("EODREV_L1", "AAPL", "long", 14)])
    rec, notes, ad = _resume(tmp_path, monkeypatch, 9, 31)
    assert not ad.sent and not notes and "before 15:27" in rec["result"]
    _state(tmp_path, [_leg("EODREV_L1", "AAPL", "long", 14, bday="2026-11-13")], bday="2026-11-13")
    rec, notes, ad = _resume(tmp_path, monkeypatch, 15, 40)
    assert not ad.sent and rec["result"] == "resume-only: nothing to resume"


def test_alert_failed_line(tmp_path):
    _state(tmp_path, [_leg("EODREV_L1", "AAPL", "long", 14), _leg("EODREV_S1", "JPM", "short", 13)])
    notes = []
    out = ex.alert_failed(ex.paths(str(tmp_path)),
                          now_fn=lambda: dt.datetime(2026, 11, 16, 15, 44, tzinfo=ET),
                          log=lambda *a: None, notify=lambda m, **k: notes.append(m))
    assert notes == ["PICK6 unit failed at 15:44, basket 2 legs open"] and out["result"] == "alert"


def test_units_carry_the_hook():
    d = os.path.join(REPO, "deploy", "cloud")
    svc = open(os.path.join(d, "edgelog-eodrev.service")).read()
    for k in ("Restart=on-failure", "RestartSec=20", "StartLimitIntervalSec=600",
              "StartLimitBurst=5", "OnFailure=edgelog-eodrev-alert.service"):
        assert k in svc
    res = open(os.path.join(d, "edgelog-eodrev-resume.service")).read()
    assert "run --resume-only" in res and "WantedBy=multi-user.target" in res
    assert "After=network-online.target" in res
    assert "alert-failed" in open(os.path.join(d, "edgelog-eodrev-alert.service")).read()
