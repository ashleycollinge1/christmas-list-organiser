#!/usr/bin/env python3
"""Print one version's section of CHANGELOG.md, for the GitHub Release notes.

    python scripts/release_notes.py --version v0.2.0 > notes.md

Exits 2 if the version has no section, or the section has no "### Upgrade steps",
so a release can't go out without notes.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def section(changelog: str, version: str) -> str | None:
    m = re.search(rf"^## {re.escape(version)}\s*$(.*?)(?=^## |\Z)", changelog, re.M | re.S)
    return m.group(1).strip() if m else None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", required=True, help="git tag, e.g. v0.2.0")
    p.add_argument("--changelog", type=Path, default=ROOT / "CHANGELOG.md")
    args = p.parse_args(argv)

    body = section(args.changelog.read_text(), args.version)
    if not body:
        print(f"CHANGELOG.md has no '## {args.version}' section. Add release notes before tagging.", file=sys.stderr)
        return 2
    if args.version != "v0.1.0" and "### Upgrade steps" not in body:
        print(f"'## {args.version}' needs a '### Upgrade steps' subsection.", file=sys.stderr)
        return 2
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
