#!/usr/bin/env python3
"""Release notes for the Release workflow.

Usage: release_notes.py VERSION [CHANGELOG.md]

Takes the section of CHANGELOG.md for VERSION ("## [1.1.1]", "## 1.1.1" or "## v1.1.1", with or without a date).
If there is none, takes the "## [Unreleased]" section. If that is empty too, lists the commits since the previous
tag (ZIP-import commits are skipped - their messages say nothing). Prints Markdown to stdout.
"""
import re
import subprocess
import sys
from pathlib import Path


def sections(text):
    """{normalized heading: body} for every '## ' heading."""
    out, name, buf = {}, None, []
    for line in text.splitlines():
        m = re.match(r"^##\s+(.*?)\s*$", line)
        if m:
            if name is not None:
                out[name] = "\n".join(buf).strip()
            raw = m.group(1)
            # "[1.1.1] - 2026-11-15" -> "1.1.1"; "[Unreleased]" -> "unreleased"
            name = re.sub(r"\s+[-–—]\s+.*$|\s*\(.*$", "", raw).strip().strip("[]").lstrip("vV").strip().lower()
            buf = []
        elif name is not None:
            buf.append(line)
    if name is not None:
        out[name] = "\n".join(buf).strip()
    return out


def from_commits():
    def git(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()
    prev = git("describe", "--tags", "--abbrev=0", "HEAD^")
    rng = f"{prev}..HEAD" if prev else "HEAD"
    lines = [l for l in git("log", rng, "--no-merges", "--pretty=format:%s (%h)").splitlines()
             if l and not l.startswith("Import ") and "[bot]" not in l]
    if not lines:
        return "No description of changes for this version."
    return "### Changes\n\n" + "\n".join(f"- {l}" for l in lines[:100])


def main():
    version = sys.argv[1].strip().lstrip("vV")
    path = Path(sys.argv[2] if len(sys.argv) > 2 else "CHANGELOG.md")
    secs = sections(path.read_text(encoding="utf-8")) if path.exists() else {}
    body = secs.get(version.lower()) or secs.get("unreleased") or from_commits()
    print(body)


if __name__ == "__main__":
    main()
