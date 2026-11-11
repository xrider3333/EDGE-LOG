"""api/nt_account.py: the NT paper account is ONE value, and never the real account."""
from api import nt_account as A


def test_env_wins_and_real_account_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(A, "ACCOUNT_FILE", str(tmp_path / "none.txt"))
    monkeypatch.setenv("EDGELOG_NT_ACCOUNT", "DEMO7240108")
    assert A.paper_account() == "DEMO7240108"
    monkeypatch.setenv("EDGELOG_NT_ACCOUNT", "1810769")
    assert A.paper_account() != "1810769"


def test_file_then_default(monkeypatch, tmp_path):
    monkeypatch.delenv("EDGELOG_NT_ACCOUNT", raising=False)
    f = tmp_path / "acct.txt"
    monkeypatch.setattr(A, "ACCOUNT_FILE", str(f))
    assert A.paper_account() == "Sim101"
    f.write_text("DEMO7240108\n")
    assert A.paper_account() == "DEMO7240108"
    f.write_text("1810769\n")
    assert A.paper_account() == "Sim101"
