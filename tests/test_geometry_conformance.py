"""Board-geometry conformance for the Star Trek Quotes plugin.

Runs the shared suite from FiestaBoard core (``src/plugins/geometry_conformance.py``)
across every supported board shape: Flagship (22x6), Note (15x3), and
note_array panels from a tall-narrow 15x12 up to the largest 120x24
FiestaPanel. See that module's docstring for what "conformance" means and
why arrays are not simply "bigger than a Flagship".

``strict_growth`` is deliberately omitted here. This plugin shows one quote
at a time -- like a clock or a single status line, not a list or a feed --
so a taller board never has *more content* to add, only more room to spell
out the one quote it already has (which ``get_formatted_display`` now does;
see ``TestFormattedDisplayBoardAdaptivity`` in ``test_plugin.py``). The
shared suite's growth ladder only measures ``fetch_data``'s
``formatted_lines``/``data['formatted']`` path anyway, and this plugin
renders through template variables instead, so growth is not just
inapplicable here, it is unobservable to that check.
"""

import json
from pathlib import Path

from src.plugins.geometry_conformance import assert_board_conformance

from plugins.star_trek_quotes import StarTrekQuotesPlugin

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "manifest.json"


def _manifest() -> dict:
    with open(MANIFEST_PATH) as f:
        return json.load(f)


def make_plugin() -> StarTrekQuotesPlugin:
    """A fresh, ready-to-render plugin.

    No network access to stub: quotes ship in ``quotes.json`` alongside the
    plugin, so there is nothing for the conformance suite's many renders to
    touch but the local file already loaded at construction time.
    """
    plugin = StarTrekQuotesPlugin(_manifest())
    plugin.config = {"enabled": True, "ratio": "3:5:9"}
    return plugin


def test_renders_on_every_board_shape():
    assert_board_conformance(
        make_plugin,
        manifest=_manifest(),
        require_note_array_preview=True,
    )
