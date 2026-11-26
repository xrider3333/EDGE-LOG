import datetime as dt
from api import paper as P


class _Snap:
    def __init__(self, e): self.exists = e


class _Doc:
    def __init__(self, have, k): self.have, self.k = have, k
    def get(self): return _Snap(self.k in self.have)


class _Col:
    def __init__(self, have): self.have = have
    def document(self, k): return _Doc(self.have, k)




class DB:
    def __init__(self, have): self.have = have
    def collection(self, name):
        return _Col(self.have) if name == "paper_reports" else self
    def document(self, name): return self


def test_missing_days_are_weekdays_without_a_report(monkeypatch):
    monkeypatch.setattr(P, "PAPER_START", "2026-09-01")
    have = {"2026-11-18", "2026-11-24", "2026-11-25"}
    got = P._missing_report_days(DB(have), "u", dt.date(2026, 11, 26), days=10)
    assert [d.isoformat() for d in got] == ["2026-11-16", "2026-11-17", "2026-11-19", "2026-11-20", "2026-11-23"]
