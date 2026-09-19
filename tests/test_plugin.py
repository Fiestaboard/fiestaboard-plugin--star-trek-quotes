"""Tests for the star_trek_quotes plugin.

Everything here exercises ``plugins.star_trek_quotes`` and the ``quotes.json``
this repo ships. The platform's ``src/utils/star_trek_quotes.py`` (and its
copy of the quote data) was a pre-extraction leftover and is gone; nothing
below imports from ``src.utils``.
"""

import json
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from plugins.star_trek_quotes import Plugin, StarTrekQuotesPlugin

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "manifest.json"
QUOTES_PATH = REPO_ROOT / "quotes.json"
SERIES = ("tng", "voyager", "ds9")


def _manifest():
    with open(MANIFEST_PATH) as f:
        return json.load(f)


def _shipped_quotes():
    with open(QUOTES_PATH) as f:
        return json.load(f)


@pytest.fixture
def plugin():
    return StarTrekQuotesPlugin(_manifest())


class TestPluginConstruction:
    """What the platform does with this package: import ``Plugin`` and build it."""

    def test_module_exports_the_plugin_class(self):
        assert Plugin is StarTrekQuotesPlugin

    def test_plugin_id_matches_manifest(self, plugin):
        assert plugin.plugin_id == _manifest()["id"] == "star_trek_quotes"

    def test_loads_the_shipped_quotes_on_construction(self, plugin):
        """The plugin reads its own quotes.json, not a platform copy."""
        assert plugin._quotes == _shipped_quotes()

    def test_every_series_has_quotes(self, plugin):
        for series in SERIES:
            assert plugin._quotes[series], f"{series} has no quotes"


class TestQuoteData:
    """Integrity of the quote data the plugin ships and serves."""

    def test_every_quote_has_non_empty_text_and_character(self, plugin):
        for series, quotes in plugin._quotes.items():
            for entry in quotes:
                assert isinstance(entry["quote"], str) and entry["quote"].strip(), (
                    f"empty quote in {series}: {entry}"
                )
                assert isinstance(entry["character"], str) and entry["character"].strip(), (
                    f"missing character in {series}: {entry}"
                )

    def test_no_html_in_quotes(self, plugin):
        for series, quotes in plugin._quotes.items():
            for entry in quotes:
                assert "<" not in entry["quote"] and ">" not in entry["quote"], (
                    f"HTML in {series} quote: {entry['quote']!r}"
                )

    def test_all_quotes_fit_the_manifest_max_length(self, plugin):
        max_length = _manifest()["variables"]["simple"]["quote"]["max_length"]
        for series, quotes in plugin._quotes.items():
            for entry in quotes:
                assert len(entry["quote"]) <= max_length, (
                    f"Quote too long: [{series}] {entry['quote'][:50]}... "
                    f"has {len(entry['quote'])} chars, max {max_length}"
                )

    def test_all_character_names_reasonable_length(self, plugin):
        for series, quotes in plugin._quotes.items():
            for entry in quotes:
                assert len(entry["character"]) <= 20, (
                    f"Character name too long: [{series}] {entry['character']}"
                )


class TestFetchData:
    def test_returns_every_manifest_variable(self, plugin):
        result = plugin.fetch_data()
        assert result.available is True
        assert set(result.data) == set(_manifest()["variables"]["simple"])

    def test_serves_a_quote_from_the_shipped_data(self, plugin):
        data = plugin.fetch_data().data
        series = data["series"].lower()
        assert series in SERIES
        shipped = {(q["quote"], q["character"]) for q in _shipped_quotes()[series]}
        assert (data["quote"], data["character"]) in shipped

    def test_quote_and_character_are_non_empty_strings(self, plugin):
        data = plugin.fetch_data().data
        assert isinstance(data["quote"], str) and data["quote"]
        assert isinstance(data["character"], str) and data["character"]

    def test_series_is_upper_cased(self, plugin):
        data = plugin.fetch_data().data
        assert data["series"] in {s.upper() for s in SERIES}

    @pytest.mark.parametrize(
        "ratio,series,color",
        [
            ("1:0:0", "TNG", "{67}"),  # blue
            ("0:1:0", "VOYAGER", "{64}"),  # orange
            ("0:0:1", "DS9", "{68}"),  # violet
        ],
    )
    def test_series_color_is_the_series_own_colour(self, plugin, ratio, series, color):
        plugin.config = {"ratio": ratio}
        data = plugin.fetch_data().data
        assert (data["series"], data["series_color"]) == (series, color)

    def test_series_color_is_a_board_color_code(self, plugin):
        color = plugin.fetch_data().data["series_color"]
        assert color.startswith("{") and color.endswith("}")
        assert color[1:-1].isdigit()

    def test_repeated_fetches_vary(self, plugin):
        random.seed(1234)
        quotes = {plugin.fetch_data().data["quote"] for _ in range(20)}
        assert len(quotes) > 1

    def test_ratio_weights_series_selection(self, plugin):
        """A 0:0:1 ratio only ever draws from DS9."""
        plugin.config = {"ratio": "0:0:1"}
        assert {plugin.fetch_data().data["series"] for _ in range(20)} == {"DS9"}

    def test_falls_back_to_another_series_when_the_chosen_one_is_empty(self, plugin):
        plugin._quotes = {
            "tng": [{"quote": "Test.", "character": "Picard"}],
            "voyager": [],
            "ds9": [],
        }
        plugin.config = {"ratio": "0:1:0"}  # only voyager in the pool
        result = plugin.fetch_data()
        assert result.available is True
        assert result.data["quote"] == "Test."
        assert result.data["series"] == "TNG"

    def test_unavailable_when_there_are_no_quotes(self, plugin):
        plugin._quotes = {"tng": [], "voyager": [], "ds9": []}
        result = plugin.fetch_data()
        assert result.available is False
        assert "No quotes available" in result.error

    def test_reloads_quotes_when_cache_is_empty(self, plugin):
        plugin._quotes = None
        result = plugin.fetch_data()
        assert plugin._quotes == _shipped_quotes()
        assert result.available is True

    def test_exception_is_reported_not_raised(self, plugin):
        with patch("plugins.star_trek_quotes.random.choice", side_effect=RuntimeError("Random error")):
            result = plugin.fetch_data()
        assert result.available is False
        assert "Random error" in result.error


class TestRatio:
    def test_validate_config_accepts_default_ratio(self, plugin):
        assert plugin.validate_config({"ratio": "3:5:9"}) == []

    def test_validate_config_rejects_non_ratio(self, plugin):
        assert plugin.validate_config({"ratio": "invalid"}) == [
            "Ratio must be in format N:N:N (e.g., 3:5:9)"
        ]

    def test_validate_config_rejects_two_parts(self, plugin):
        assert "Ratio must be in format" in plugin.validate_config({"ratio": "1:2"})[0]

    def test_validate_config_rejects_non_integer_parts(self, plugin):
        assert plugin.validate_config({"ratio": "1:2:a"}) == ["Ratio parts must be integers"]

    def test_parse_ratio_reads_config(self, plugin):
        plugin.config = {"ratio": "1:2:3"}
        assert plugin._parse_ratio() == (1, 2, 3)

    def test_parse_ratio_defaults_when_unset(self, plugin):
        plugin.config = {}
        assert plugin._parse_ratio() == (3, 5, 9)

    def test_parse_ratio_defaults_on_garbage(self, plugin):
        plugin.config = {"ratio": "not-valid"}
        assert plugin._parse_ratio() == (3, 5, 9)

    def test_parse_ratio_defaults_on_wrong_part_count(self, plugin):
        plugin.config = {"ratio": "1:2"}
        assert plugin._parse_ratio() == (3, 5, 9)

    def test_parse_ratio_defaults_when_not_a_string(self, plugin):
        plugin.config = {"ratio": 12345}
        assert plugin._parse_ratio() == (3, 5, 9)


class TestFormattedDisplay:
    def test_renders_at_most_six_rows_with_attribution(self, plugin):
        lines = plugin.get_formatted_display()
        assert lines is not None
        assert len(lines) == 6
        assert lines[-1].strip().startswith("- ")
        assert all(len(line) <= 22 for line in lines)

    def test_word_wraps_a_long_quote(self, plugin):
        plugin._quotes = {
            "tng": [
                {
                    "quote": "This is a very long quote that should definitely wrap "
                    "across multiple lines when displayed on the board.",
                    "character": "Picard",
                }
            ],
            "voyager": [],
            "ds9": [],
        }
        plugin.config = {"ratio": "1:0:0"}
        lines = plugin.get_formatted_display()
        assert len(lines) == 6
        assert lines[1] == "This is a very long"
        assert lines[-1].endswith("- Picard")
        assert all(len(line) <= 22 for line in lines)

    def test_returns_none_when_no_quotes(self, plugin):
        plugin._quotes = {"tng": [], "voyager": [], "ds9": []}
        assert plugin.get_formatted_display() is None


class TestLoadQuotes:
    def test_missing_file_yields_empty_series(self):
        real_exists = Path.exists

        def mock_exists(self):
            if str(self).endswith("quotes.json"):
                return False
            return real_exists(self)

        with patch.object(Path, "exists", mock_exists):
            plugin = StarTrekQuotesPlugin(_manifest())
        assert plugin._quotes == {"tng": [], "voyager": [], "ds9": []}

    def test_unreadable_file_yields_empty_series(self):
        manifest = _manifest()  # read before json.load is patched
        with patch("plugins.star_trek_quotes.json.load", side_effect=OSError("Read error")):
            plugin = StarTrekQuotesPlugin(manifest)
        assert plugin._quotes == {"tng": [], "voyager": [], "ds9": []}


class TestManifestMetadata:
    """Tests for the rich metadata format in the manifest."""

    def test_manifest_uses_dict_simple_format(self):
        simple = _manifest()["variables"]["simple"]
        assert isinstance(simple, dict), "simple should use the rich dict format"

    def test_all_variables_have_descriptions(self):
        for var_name, meta in _manifest()["variables"]["simple"].items():
            assert "description" in meta and meta["description"], (
                f"Variable '{var_name}' missing description"
            )

    def test_all_variables_have_valid_groups(self):
        manifest = _manifest()
        groups = set(manifest["variables"].get("groups", {}).keys())
        for var_name, meta in manifest["variables"]["simple"].items():
            group = meta.get("group", "")
            if group:
                assert group in groups, (
                    f"Variable '{var_name}' references undefined group '{group}'"
                )

    def test_groups_are_defined(self):
        groups = _manifest()["variables"].get("groups", {})
        assert len(groups) > 0, "Manifest should define at least one group"
        for group_id, group_def in groups.items():
            assert "label" in group_def, f"Group '{group_id}' missing label"
