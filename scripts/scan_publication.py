#!/usr/bin/env python3
"""Scan publishable files and all reachable Git objects without printing secret values.

This is a targeted guard, not proof that arbitrary text is non-private. Manually
review the complete file list and use a general secret scanner before publishing.
"""

import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "api-key": re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}"),
    "github-token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    "private-key": re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"),
    "bearer-secret": re.compile(r"(?i)bearer\s+[A-Za-z0-9._~-]{24,}"),
    "mac-user-path": re.compile("/" + "Users" + r'/[^\s/"\']+'),
    "linux-user-path": re.compile("/" + "home" + r'/[^\s/"\']+'),
    "private-cloud-id": re.compile(r"\b(?:tunnel_|asdk_app_|proj_|org-)[A-Za-z0-9]{16,}"),
    "real-note-id": re.compile(r"x-coredata://[A-Fa-f0-9-]{32,}/IC(?:Note|Folder)/"),
}
SKIP = {".git", ".venv", "venv", "__pycache__", ".ruff_cache", "build", "dist"}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL)


def matches(data):
    text = data.decode("utf-8", errors="replace")
    return [name for name, pattern in PATTERNS.items() if pattern.search(text)]


def main():
    failures = []
    try:
        tracked = git("ls-files", "-z").decode().split("\0")
        files = [ROOT / p for p in tracked if p]
        in_git = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        files = [
            p
            for p in ROOT.rglob("*")
            if p.is_file()
            and not any(x in SKIP or x.endswith(".egg-info") for x in p.relative_to(ROOT).parts)
        ]
        in_git = False
    for p in files:
        rel = str(p.relative_to(ROOT))
        if p.is_symlink():
            failures.append((rel, "symlink"))
            continue
        if p.name != ".env.example" and (
            p.name.startswith(".env")
            or p.suffix in {".key", ".pem", ".p12", ".pfx", ".log"}
            or any(
                x in {"backups", "runtime", "private", "transfers"}
                for x in p.relative_to(ROOT).parts
            )
        ):
            failures.append((rel, "private-file-type"))
        if p.stat().st_size > 2 * 1024 * 1024:
            failures.append((rel, "unexpected-large-file"))
            continue
        failures.extend((rel, kind) for kind in matches(p.read_bytes()))
    objects = 0
    if in_git:
        for row in git("rev-list", "--objects", "--all").decode().splitlines():
            sha = row.split(" ", 1)[0]
            kind = git("cat-file", "-t", sha).decode().strip()
            if kind not in {"blob", "commit", "tag"}:
                continue
            data = git("cat-file", "-p", sha)
            objects += 1
            failures.extend(("git-object:" + sha[:12], item) for item in matches(data))
    for location, kind in failures:
        print(f"{location}: {kind}")
    print(
        f"Scanned {len(files)} files and {objects} Git objects; findings={len(failures)}. Values never printed."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
