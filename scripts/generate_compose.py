#!/usr/bin/env python3
"""Render deploy/compose.template.yml into a version-pinned compose file.

    python scripts/generate_compose.py --version v1.2.0 \
        --image ghcr.io/ashleycollinge1/christmas-list-organiser [--digest sha256:...]

Writes deploy/compose/docker-compose.v1.2.0.yml and, for non-pre-releases,
deploy/compose/docker-compose.latest.yml plus the repo-root docker-compose.yml
(the file people run on a host). All of them pull the pre-built image; none build.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "deploy" / "compose.template.yml"
OUT_DIR = ROOT / "deploy" / "compose"
ROOT_COMPOSE = ROOT / "docker-compose.yml"
SEMVER = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(?:-[0-9A-Za-z.-]+)?$")


def render(version: str, image: str, digest: str | None) -> str:
    tag = version.removeprefix("v")
    ref = f"{image.lower()}:{tag}"
    if digest:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise SystemExit(f"invalid digest: {digest}")
        ref += f"@{digest}"
    return TEMPLATE.read_text().replace("__IMAGE__", ref).replace("__VERSION__", version)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", required=True, help="git tag, e.g. v1.2.0")
    p.add_argument("--image", required=True, help="image repository without tag")
    p.add_argument("--digest", help="optional image digest to pin (sha256:...)")
    p.add_argument("--out-dir", type=Path, default=OUT_DIR, help="output folder (default deploy/compose)")
    p.add_argument("--no-latest", action="store_true", help="don't update latest / the root compose file")
    p.add_argument(
        "--root-file", type=Path, default=ROOT_COMPOSE, help="root compose path (default ./docker-compose.yml)"
    )
    args = p.parse_args(argv)

    if not SEMVER.match(args.version):
        print(f"version must look like v1.2.3, got {args.version!r}", file=sys.stderr)
        return 2

    content = render(args.version, args.image, args.digest)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"docker-compose.{args.version}.yml"
    out.write_text(content)
    print(f"wrote {out}")
    # Pre-releases (v1.2.0-rc.1) don't move "latest".
    if not args.no_latest and "-" not in args.version:
        latest = args.out_dir / "docker-compose.latest.yml"
        latest.write_text(content.replace(f"docker-compose.{args.version}.yml", "docker-compose.latest.yml"))
        print(f"wrote {latest}")
        args.root_file.write_text(
            content.replace(f"docker compose -f docker-compose.{args.version}.yml up -d", "docker compose up -d")
        )
        print(f"wrote {args.root_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
