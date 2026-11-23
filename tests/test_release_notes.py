import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("release_notes", ROOT / "scripts" / "release_notes.py")
notes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(notes)

SAMPLE = """# Changelog

## v1.1.0

### Upgrade steps

Pull and up.

### What's new

- Thing

## v1.0.0

### Upgrade steps

None.
"""


def test_extracts_only_that_section(tmp_path, capsys):
    f = tmp_path / "CHANGELOG.md"
    f.write_text(SAMPLE)
    assert notes.main(["--version", "v1.1.0", "--changelog", str(f)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("### Upgrade steps") and "- Thing" in out and "v1.0.0" not in out


def test_missing_section_or_upgrade_steps_fails(tmp_path):
    f = tmp_path / "CHANGELOG.md"
    f.write_text(SAMPLE + "\n## v2.0.0\n\nNo steps here.\n")
    assert notes.main(["--version", "v9.9.9", "--changelog", str(f)]) == 2
    assert notes.main(["--version", "v2.0.0", "--changelog", str(f)]) == 2


def test_real_changelog_has_notes_for_the_current_version():
    import tomllib

    version = "v" + tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert notes.main(["--version", version]) == 0
