"""secret_scan.py - block a push that would put a credential on GitHub (board C18, owner 10-30).

Scans the ADDED lines of every commit being pushed (or, with --staged, the index) for credential patterns and
forbidden filenames. Exit 0 = clean, 1 = a hit (the push is refused), 2 = could not run (non-blocking).
Never prints a secret: a hit shows file, line and pattern name, with the value masked.

    python tools/secret_scan.py --range <old>..<new>     (what the pre-push hook calls)
    python tools/secret_scan.py --staged
    python tools/secret_scan.py --all                    (every tracked file, for an audit)

A false positive is cleared by putting `secret-scan: allow` on that line, never by --no-verify.
"""
import argparse
import re
import subprocess
import sys

FORBIDDEN_FILES = re.compile(r"(^|/)(serviceAccount[^/]*\.json|credentials[^/]*\.json|\.env|[^/]*\.key|[^/]*\.pem|"
                             r"\.alpaca_keys\.json|webull[^/]*keys[^/]*\.json|augur_config\.json|id_rsa[^/]*)$", re.I)
PATTERNS = [
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("GCP service-account key", re.compile(r'"private_key_id"\s*:\s*"[0-9a-f]{20,}"')),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b|github_pat_[A-Za-z0-9_]{60,}")),
    ("Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("assigned secret", re.compile(r"""(?i)\b(app_?secret|api_?secret|secret_?key|access_?token|refresh_?token|"""
                                   r"""api_?key|password|passwd|pin)\b["']?\s*[:=]\s*["']([A-Za-z0-9/+_\-]{16,})["']""")),
]
ALLOW = "secret-scan: allow"
PLACEHOLDER = re.compile(r"(?i)paste|not_?a|example|placeholder|fake|dummy|test|xxxx|changeme|your_")


def git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def added_lines(diff):
    f, n = None, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            f = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line); n = int(m.group(1)) - 1 if m else 0
        elif line.startswith("+") and f:
            n += 1; yield f, n, line[1:]
        elif not line.startswith("-"):
            n += 1


def scan_lines(items):
    hits = []
    for f, n, text in items:
        if ALLOW in text:
            continue
        for name, rx in PATTERNS:
            m = rx.search(text)
            if m:
                v = m.group(m.lastindex or 0)
                if PLACEHOLDER.search(v):
                    continue
                hits.append((f, n, name, (v[:4] + "..." + v[-2:]) if len(v) > 8 else "***"))
    return hits


def main(argv=None):
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--range"); g.add_argument("--staged", action="store_true"); g.add_argument("--all", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.all:
            files = git("ls-files").splitlines()
            items = []
            for f in files:
                try:
                    for i, t in enumerate(open(f, encoding="utf-8", errors="ignore"), 1):
                        items.append((f, i, t))
                except OSError:
                    pass
        else:
            spec = ["--cached"] if a.staged else [a.range]
            files = git("diff", "--name-only", "--diff-filter=AR", *spec).splitlines()
            items = list(added_lines(git("diff", "-U0", "--no-color", *spec)))
    except Exception as e:                      # tooling failure never blocks a push
        print("secret-scan: could not run (%s) - not blocking" % e); return 2
    bad_files = [f for f in files if FORBIDDEN_FILES.search(f)]
    hits = scan_lines(items)
    for f in bad_files:
        print("secret-scan: FORBIDDEN FILE %s" % f)
    for f, n, name, masked in hits:
        print("secret-scan: %s:%d  %s  (%s)" % (f, n, name, masked))
    if bad_files or hits:
        print("secret-scan: push REFUSED - remove the secret (and rotate it if it was ever committed),"
              " or mark a false positive with '%s' on that line." % ALLOW)
        return 1
    print("secret-scan: clean (%d files, %d added lines)" % (len(files), len(items)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
