"""The release compose generator must only ever produce pull-based files."""

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("generate_compose", ROOT / "scripts" / "generate_compose.py")
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)

IMAGE = "ghcr.io/AshleyCollinge1/christmas-list-organiser"
DIGEST = "sha256:" + "a" * 64


def _run(tmp_path, version, *extra):
    root_file = tmp_path / "docker-compose.yml"
    rc = gen.main(["--version", version, "--image", IMAGE, "--digest", DIGEST,
                   "--out-dir", str(tmp_path / "out"), "--root-file", str(root_file), *extra])  # fmt: skip
    return rc, tmp_path / "out", root_file


def test_release_writes_versioned_latest_and_root(tmp_path):
    rc, out, root_file = _run(tmp_path, "v1.2.0")
    assert rc == 0
    files = [out / "docker-compose.v1.2.0.yml", out / "docker-compose.latest.yml", root_file]
    for f in files:
        text = f.read_text()
        assert not re.search(r"^\s*build:", text, re.M), f"{f.name} must not build"
        images = re.findall(r"^\s*image:\s*(\S+)", text, re.M)
        app_images = [i for i in images if not i.startswith("postgres:")]
        assert app_images == [f"ghcr.io/ashleycollinge1/christmas-list-organiser:1.2.0@{DIGEST}"]
        assert "__IMAGE__" not in text and "__VERSION__" not in text
    assert "docker compose up -d" in root_file.read_text()
    assert "docker compose -f docker-compose.latest.yml up -d" in files[1].read_text()


def test_prerelease_does_not_move_latest_or_root(tmp_path):
    rc, out, root_file = _run(tmp_path, "v1.3.0-rc.1")
    assert rc == 0
    assert (out / "docker-compose.v1.3.0-rc.1.yml").is_file()
    assert not (out / "docker-compose.latest.yml").exists()
    assert not root_file.exists()


@pytest.mark.parametrize("version", ["1.2.0", "v1.2", "latest", "v1.2.0;rm"])
def test_rejects_non_semver(tmp_path, version):
    rc, _, _ = _run(tmp_path, version)
    assert rc == 2


def test_rejects_bad_digest(tmp_path):
    with pytest.raises(SystemExit):
        gen.main(["--version", "v1.0.0", "--image", IMAGE, "--digest", "sha256:nope", "--out-dir", str(tmp_path)])


def test_template_only_pulls():
    text = (ROOT / "deploy" / "compose.template.yml").read_text()
    assert not re.search(r"^\s*build:", text, re.M)
    images = re.findall(r"^\s*image:\s*(\S+)", text, re.M)
    assert sorted(images) == ["__IMAGE__", "postgres:17-alpine", "postgres:17-alpine"]


def test_committed_root_compose_pulls_and_dev_file_is_separate():
    root_file = ROOT / "docker-compose.yml"
    if root_file.exists():  # written by the first release
        root = root_file.read_text()
        assert not re.search(r"^\s*build:", root, re.M)
        assert "ghcr.io/ashleycollinge1/christmas-list-organiser:" in root
    assert re.search(r"^\s*build:", (ROOT / "docker-compose.dev.yml").read_text(), re.M)
