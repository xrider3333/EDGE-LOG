"""tools/chat_inbox.py refuses chat names with no inbox (MANAGER #33, 2026-10-05: ENGUQ read 'ENGU-Q' all day, saw 'empty')."""
import os, subprocess, sys

TOOL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "chat_inbox.py")


def run(box, *args):
    env = dict(os.environ, EDGELOG_CHAT_INBOX=str(box))
    return subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, env=env)


def test_new_chat_needs_new_flag_then_reads_back(tmp_path):
    r = run(tmp_path, "post", "ENGUQ", "hello", "--from", "MANAGER")
    assert r.returncode != 0 and "REFUSED" in r.stderr and "--new" in r.stderr
    assert not (tmp_path / "ENGUQ.jsonl").exists()
    r = run(tmp_path, "post", "ENGUQ", "hello", "--from", "MANAGER", "--new")
    assert r.returncode == 0 and "posted #1 to ENGUQ" in r.stdout
    r = run(tmp_path, "read", "ENGUQ")
    assert r.returncode == 0 and "hello" in r.stdout


def test_misspelt_read_is_refused_with_the_right_suggestion(tmp_path):
    run(tmp_path, "post", "ENGUQ", "item", "--from", "MANAGER", "--new")
    run(tmp_path, "post", "MANAGER", "x", "--from", "ENGUQ", "--new")
    r = run(tmp_path, "read", "ENGUQQ")
    assert r.returncode != 0
    assert "inbox empty" not in r.stdout
    assert "did you mean: ENGUQ" in r.stderr and "known chats: ENGUQ, MANAGER" in r.stderr
    assert not (tmp_path / "ENGUQQ.jsonl").exists()


def test_short_names_resolve_to_the_live_inbox(tmp_path):
    """2026-10-05: posts to FRONTIER / STRATEGY-BEATING / NQBRD / ENGU-Q sat in stray files the lanes never read."""
    for live in ("FRONTIER-MODELS-ROC-YR-OPTIMIZATION", "STRATEGY-BEATING-FRONTIER-MODELS-ON-ROC-Y", "ENGUQ", "TV", "ELWA-FEATURES"):
        run(tmp_path, "post", live, "seed", "--from", "MANAGER", "--new")
    (tmp_path / "FRONTIER.jsonl").write_text("", encoding="utf-8")          # a stray short-name file must not catch posts
    r = run(tmp_path, "post", "Frontier", "seat numbers", "--from", "TV")
    assert r.returncode == 0 and "posted #2 to FRONTIER-MODELS-ROC-YR-OPTIMIZATION" in r.stdout
    assert (tmp_path / "FRONTIER.jsonl").read_text(encoding="utf-8") == ""
    r = run(tmp_path, "post", "NQBRD", "receipts", "--from", "ELWA")
    assert "posted #2 to STRATEGY-BEATING-FRONTIER-MODELS-ON-ROC-Y" in r.stdout and "warning" not in r.stderr
    r = run(tmp_path, "read", "ENGU-Q")
    assert r.returncode == 0 and "[ENGUQ]" in r.stdout and "seed" in r.stdout
    r = run(tmp_path, "read", "frontier")
    assert "seat numbers" in r.stdout


def test_post_and_done_to_unknown_names_are_refused(tmp_path):
    run(tmp_path, "post", "PAPER-WB", "a", "--from", "TV", "--new")
    r = run(tmp_path, "post", "PAPER WB2", "b", "--from", "TV")
    assert r.returncode != 0 and "dead inbox" in r.stderr
    r = run(tmp_path, "done", "PAPERWB", "1")
    assert r.returncode != 0 and "did you mean: PAPER-WB" in r.stderr
    r = run(tmp_path, "done", "paper: wb", "1", "handled")
    assert r.returncode == 0 and "closed #1 in PAPER-WB" in r.stdout


def test_unknown_sender_only_warns(tmp_path):
    run(tmp_path, "post", "TV", "a", "--from", "MANAGER", "--new")
    r = run(tmp_path, "post", "TV", "b", "--from", "NOBODY")
    assert r.returncode == 0 and "posted #2 to TV" in r.stdout and "warning: sender NOBODY" in r.stderr

def test_read_survives_a_cp1252_console_on_non_ascii_text(tmp_path):
    """2026-10-07: `read` died with UnicodeEncodeError on an arrow - Python on Windows encodes a
    piped console (how every Claude session runs this) as cp1252. Every command must print any
    item text, and print it intact as UTF-8."""
    text = "ship moved → pre-lock; β and — too"
    env = dict(os.environ, EDGELOG_CHAT_INBOX=str(tmp_path), PYTHONIOENCODING="cp1252")
    probe = subprocess.run([sys.executable, "-c", "print('\u2192')"], env=env, capture_output=True)
    assert probe.returncode != 0 and b"UnicodeEncodeError" in probe.stderr, "the console is not really cp1252"
    r = subprocess.run([sys.executable, TOOL, "post", "MANAGER", text, "--from", "MANAGER", "--new"],
                       env=env, capture_output=True)
    assert r.returncode == 0, r.stderr
    for args in (["read", "MANAGER"], ["all"], ["read", "MANAGER", "--all"]):
        r = subprocess.run([sys.executable, TOOL] + args, env=env, capture_output=True)
        out, err = r.stdout.decode("utf-8"), r.stderr.decode("utf-8", "replace")
        assert r.returncode == 0 and "Traceback" not in err, err
        assert text in out, out
    r = subprocess.run([sys.executable, TOOL, "done", "MANAGER", "1", "fixed → done"], env=env,
                       capture_output=True)
    assert r.returncode == 0, r.stderr
