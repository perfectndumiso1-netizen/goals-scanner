#!/usr/bin/env python3
"""Secret guard for PlayReport (and any repo that copies it).

Scans the files git tracks for high-signal credential patterns and exits non-zero
if anything is found. No dependencies, no network. Run it before pushing:

    python3 scripts/check_secrets.py

It deliberately looks at tracked files only (that is what gets published).
GitHub's own secret scanning covers the full history of the public repo.
"""
from __future__ import annotations
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# name -> compiled pattern. High signal only: things that are never legitimate in a repo.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b")),
    ("GitHub fine-grained PAT", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("Telegram bot token", re.compile(r"\b\d{8,12}:AA[A-Za-z0-9_-]{30,}\b")),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("Stripe key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{20,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("Bearer literal", re.compile(r"(?i)authorization\s*[:=]\s*[\"']?bearer\s+[A-Za-z0-9._-]{25,}")),
    ("Hard-coded password", re.compile(r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*[\"'][^\"']{8,}[\"']")),
    # Bare shell-style assignments like KEY="deadbeef…" — the exact shape of the
    # leak found in the Forex repo on 2026-09-28 (a live Twelve Data key, public since the first commit).
    ("Hard-coded key variable", re.compile(r"(?i)\b(?:key|apikey|api_key|token|secret|auth|pass|credential)\s*=\s*[\"'][A-Za-z0-9_\-]{16,}[\"']")),
    ("Opaque 32-char hex literal", re.compile(r"[\"'][0-9a-fA-F]{32}[\"']")),
]

# Values that are obviously placeholders or wiring, not credentials.
SAFE_HINTS = re.compile(
    r"(?i)(your[_-]?|example|placeholder|dummy|redacted|changeme|<[^>]+>|x{4,}|\*\*\*|"
    r"secrets\.[A-Z_]+|process\.env|System\.getenv|os\.environ|getenv\(|hash|integrity|sha256|md5|checksum|"
    r"token\s*[:=]\s*[\"']?\$|secret\s*[:=]\s*[\"']?\$)"
)

SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".apk", ".p12", ".jks",
                 ".zip", ".gz", ".woff", ".woff2", ".ttf", ".mp3", ".ogg", ".wav", ".m4a", ".aiff"}
SKIP_NAMES = {"marked.min.js", "package-lock.json", "yarn.lock", "app.css"}
MAX_BYTES = 2_000_000


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True).stdout
    return [p for p in out.decode("utf-8", "replace").split("\0") if p]


def redact(line: str) -> str:
    line = line.strip()
    return line[:60] + ("…" if len(line) > 60 else "")


def scan() -> int:
    findings: list[str] = []
    scanned = 0
    for rel in tracked_files():
        p = ROOT / rel
        if not p.is_file() or p.suffix.lower() in SKIP_SUFFIXES or p.name in SKIP_NAMES:
            continue
        if p.stat().st_size > MAX_BYTES:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        scanned += 1
        for i, line in enumerate(text.splitlines(), 1):
            if len(line) > 400 or SAFE_HINTS.search(line):
                continue
            for name, rx in PATTERNS:
                if rx.search(line):
                    findings.append(f"  {rel}:{i}  {name}\n      {redact(line)}")
                    break
    print(f"check_secrets: scanned {scanned} tracked files")
    if findings:
        print(f"\nFAIL — {len(findings)} possible credential(s) in tracked files:\n")
        print("\n".join(findings))
        print("\nRemove the value, rotate the credential at its provider, then commit the fix.")
        print("GitHub's secret scanning covers history; this guard stops new leaks reaching main.")
        return 1
    print("OK — no credential patterns found in tracked files")
    return 0


if __name__ == "__main__":
    sys.exit(scan())
