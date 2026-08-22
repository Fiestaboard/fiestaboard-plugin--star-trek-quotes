"""Regression tests for the plugin shipping its own quote data.

Background: this plugin was extracted from the FiestaBoard repo, where it
lived at ``plugins/star_trek_quotes/`` and read its quotes from the platform's
``src/utils/star_trek_quotes.json``.  Installed from the registry it lives at
``data/external_plugins/star_trek_quotes/`` instead -- one directory deeper --
so the old relative fallback can never resolve, and the plugin served
``available=False`` ("No quotes available") to every user.

CI hid this by symlinking the platform's data file into the repo before running
the suite, so the tests exercised a layout no user ever has.  These tests
deliberately use only files that ``git`` actually ships and reproduce the real
installed layout.
"""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPECTED_SERIES = ("tng", "voyager", "ds9")


# Names that exist for development or CI only and are not part of an install.
# "plugins" is the self-referential scaffold CI builds (plugins/<id> -> ..) so
# the bundled import path resolves; copying it would recurse forever.
NON_RUNTIME = {
    "tests",
    "docs",
    ".git",
    ".github",
    "__pycache__",
    ".pytest_cache",
    "plugins",
    "star_trek_quotes",
}


def shipped_files() -> set[str]:
    """Files git would hand a user cloning this repo.

    Returns an empty set when git cannot be consulted (e.g. the tree was
    copied into a sandbox without its ownership); callers skip in that case.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return set()
    return {line.strip() for line in out.stdout.splitlines() if line.strip()}


def test_quotes_json_is_tracked_by_git():
    """The quote data must be a committed file, not a CI-time artifact."""
    tracked = shipped_files()
    if not tracked:
        pytest.skip("git unavailable in this environment")
    assert "quotes.json" in tracked, (
        "quotes.json is not tracked by git, so a user installing this plugin "
        "receives no quote data. Do not satisfy this by symlinking the file in CI."
    )


def test_quotes_json_is_a_real_file_not_a_symlink():
    """A symlink would resolve on the CI box and dangle everywhere else."""
    quotes = REPO_ROOT / "quotes.json"
    assert quotes.is_file(), "quotes.json missing from the plugin directory"
    assert not quotes.is_symlink(), (
        "quotes.json is a symlink; it must be a real committed file so it "
        "survives being packaged and installed"
    )


def test_quotes_json_has_the_shape_the_plugin_reads():
    """Guard the contract _load_quotes() depends on."""
    data = json.loads((REPO_ROOT / "quotes.json").read_text())
    assert isinstance(data, dict)
    for series in EXPECTED_SERIES:
        assert series in data, f"missing series: {series}"
        assert data[series], f"series {series} has no quotes"
        for entry in data[series]:
            assert entry.get("quote"), f"empty quote text in {series}"
            assert entry.get("character"), f"missing character in {series}"


def _load_plugin_from(directory: Path):
    """Import the plugin module from an arbitrary install directory."""
    spec = importlib.util.spec_from_file_location(
        f"stq_under_test_{directory.name}", directory / "__init__.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = json.loads((directory / "manifest.json").read_text())
    plugin = module.Plugin(manifest)
    plugin.config = {"enabled": True, "ratio": "3:5:9"}
    return plugin


@pytest.fixture
def externally_installed_plugin(tmp_path):
    """Copy the *shipped* files into the real installed layout.

    Mirrors ``data/external_plugins/star_trek_quotes/`` -- deep enough that the
    old ``parent.parent.parent`` fallback cannot reach a platform checkout.
    """
    install_dir = tmp_path / "data" / "external_plugins" / "star_trek_quotes"
    install_dir.mkdir(parents=True)
    for src in REPO_ROOT.iterdir():
        if src.name in NON_RUNTIME or src.is_symlink():
            continue
        if src.is_file():
            # copy(), not copy2/symlink: an install gets real bytes
            shutil.copy(src, install_dir / src.name)
        elif src.is_dir():
            shutil.copytree(src, install_dir / src.name, symlinks=False)
    return _load_plugin_from(install_dir)


def test_quotes_load_when_installed_externally(externally_installed_plugin):
    """The plugin must find its quotes with no platform checkout nearby."""
    counts = {k: len(v) for k, v in externally_installed_plugin._quotes.items()}
    assert sum(counts.values()) > 0, (
        f"no quotes loaded from an external install: {counts}"
    )


def test_fetch_data_is_available_when_installed_externally(externally_installed_plugin):
    """The user-visible symptom: variables render '???' when this is False."""
    result = externally_installed_plugin.fetch_data()
    assert result.available is True, f"plugin unavailable: {result.error}"
    assert result.data["quote"]
    assert result.data["character"]
    assert result.data["series"] in {s.upper() for s in EXPECTED_SERIES}


def test_formatted_display_renders_when_installed_externally(
    externally_installed_plugin,
):
    """get_formatted_display() returns None whenever the fetch fails."""
    rows = externally_installed_plugin.get_formatted_display()
    assert rows is not None, "no board output from an external install"
    assert any(row.strip() for row in rows), "board output is entirely blank"
    assert all(len(row) <= 22 for row in rows), f"row exceeds board width: {rows}"


def test_manifest_declares_the_quote_data():
    """Declaring quotes.json lets FiestaBoard reject a broken install.

    Without the declaration the platform can only notice the file is missing
    by scanning this module's source, which is a heuristic. With it, an
    install that lacks the file is refused outright.
    """
    manifest = json.loads((REPO_ROOT / "manifest.json").read_text())
    assert "quotes.json" in manifest.get("data_files", []), (
        "manifest.json must declare quotes.json under data_files"
    )


def test_every_declared_data_file_actually_ships():
    """The declaration must describe reality, not intent."""
    manifest = json.loads((REPO_ROOT / "manifest.json").read_text())
    for rel in manifest.get("data_files", []):
        assert (REPO_ROOT / rel).is_file(), f"declared data file {rel!r} does not exist"
