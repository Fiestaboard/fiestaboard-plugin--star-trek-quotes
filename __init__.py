"""Star Trek Quotes plugin for FiestaBoard.

Displays random Star Trek quotes from TNG, Voyager, and DS9.
"""

from typing import Any, Dict, List, Optional
import logging
import json
import random
from pathlib import Path

from src.devices import BoardContext
from src.plugins.base import PluginBase, PluginResult
from src.text_to_board import count_tiles

logger = logging.getLogger(__name__)


def _wrap_text(text: str, width: int) -> List[str]:
    """Word-wrap *text* to at most *width* tiles per line.

    Greedy word wrap measured in tiles (``count_tiles``), not characters, so
    a colour marker would count as one tile if the text ever carried one.
    Never drops a word here -- that job belongs to :func:`_fit_lines`, which
    knows the line budget and can abbreviate visibly instead of silently.
    """
    width = max(1, width)
    lines: List[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if count_tiles(candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        # A single word wider than the board (rare, but a narrow Note makes
        # it more likely) must still be hard-broken -- a row wider than the
        # board is a conformance failure, not just an ugly one.
        while count_tiles(word) > width:
            lines.append(word[:width])
            word = word[width:]
        current = word
    if current:
        lines.append(current)
    return lines or [""]


def _fit_lines(lines: List[str], max_lines: int, width: int) -> List[str]:
    """Fit *lines* into *max_lines*, abbreviating rather than dropping content.

    When everything fits, ``lines`` is returned unchanged. When it doesn't,
    the lines that don't fit are folded into the last available line and
    trimmed to *width* with a trailing ellipsis, so a reader sees the quote
    was cut rather than getting a quietly truncated sentence.
    """
    max_lines = max(1, max_lines)
    if len(lines) <= max_lines:
        return lines

    kept = lines[: max_lines - 1]
    overflow = " ".join(lines[max_lines - 1 :])
    if count_tiles(overflow) > width:
        overflow = overflow[: max(0, width - 1)].rstrip() + "…"
    kept.append(overflow)
    return kept


class StarTrekQuotesPlugin(PluginBase):
    """Star Trek quotes plugin.
    
    Provides random quotes from TNG, Voyager, and DS9 with
    configurable series weighting.
    """
    
    # Series color mapping
    SERIES_COLORS = {
        "tng": "{67}",     # Blue
        "voyager": "{64}", # Orange
        "ds9": "{68}",     # Violet
    }
    
    def __init__(self, manifest: Dict[str, Any]):
        """Initialize the Star Trek quotes plugin."""
        super().__init__(manifest)
        self._quotes: Dict[str, List[Dict]] = {}
        self._load_quotes()
    
    @property
    def plugin_id(self) -> str:
        return "star_trek_quotes"
    
    def _load_quotes(self) -> None:
        """Load quotes from the JSON file shipped alongside this plugin.

        The data file must live in the plugin directory.  There is deliberately
        no fallback to the platform's ``src/utils/star_trek_quotes.json``: that
        path only resolved while this plugin was bundled inside the FiestaBoard
        repo, and silently failing over to it hid the fact that ``quotes.json``
        was never shipped to users.
        """
        try:
            quotes_file = Path(__file__).parent / "quotes.json"

            if not quotes_file.exists():
                logger.error(
                    "Star Trek quotes data missing: expected %s. The plugin "
                    "install is incomplete; reinstall the plugin.",
                    quotes_file,
                )
                self._quotes = {"tng": [], "voyager": [], "ds9": []}
                return

            with open(quotes_file, 'r') as f:
                self._quotes = json.load(f)
            
            logger.info(
                f"Loaded Star Trek quotes: TNG={len(self._quotes.get('tng', []))}, "
                f"Voyager={len(self._quotes.get('voyager', []))}, "
                f"DS9={len(self._quotes.get('ds9', []))}"
            )
        except Exception as e:
            logger.error(f"Error loading Star Trek quotes: {e}")
            self._quotes = {"tng": [], "voyager": [], "ds9": []}
    
    def _parse_ratio(self) -> tuple:
        """Parse the series ratio from config."""
        ratio_str = self.config.get("ratio", "3:5:9")
        try:
            parts = ratio_str.split(":")
            if len(parts) == 3:
                return int(parts[0]), int(parts[1]), int(parts[2])
        except (ValueError, AttributeError):
            pass
        return 3, 5, 9
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate star trek quotes configuration."""
        errors = []
        
        ratio = config.get("ratio", "3:5:9")
        if ratio:
            parts = ratio.split(":")
            if len(parts) != 3:
                errors.append("Ratio must be in format N:N:N (e.g., 3:5:9)")
            else:
                for part in parts:
                    try:
                        int(part)
                    except ValueError:
                        errors.append("Ratio parts must be integers")
                        break
        
        return errors
    
    def fetch_data(self) -> PluginResult:
        """Fetch a random Star Trek quote."""
        if not self._quotes:
            self._load_quotes()
        
        if not any(self._quotes.values()):
            return PluginResult(
                available=False,
                error="No quotes available"
            )
        
        try:
            tng_weight, voyager_weight, ds9_weight = self._parse_ratio()
            
            # Create weighted pool
            series_pool = (
                ['tng'] * tng_weight +
                ['voyager'] * voyager_weight +
                ['ds9'] * ds9_weight
            )
            
            # Select random series
            selected_series = random.choice(series_pool)
            series_quotes = self._quotes.get(selected_series, [])
            
            if not series_quotes:
                # Fallback to any available series
                all_quotes = []
                for series, quotes_list in self._quotes.items():
                    all_quotes.extend([{**q, 'series': series} for q in quotes_list])
                if not all_quotes:
                    return PluginResult(
                        available=False,
                        error="No quotes available"
                    )
                quote_data = random.choice(all_quotes)
            else:
                quote_data = random.choice(series_quotes)
                quote_data = {**quote_data, 'series': selected_series}
            
            data = {
                "quote": quote_data.get("quote", ""),
                "character": quote_data.get("character", "Unknown"),
                "series": quote_data.get("series", "").upper(),
                "series_color": self.SERIES_COLORS.get(quote_data.get("series", ""), ""),
            }
            
            return PluginResult(
                available=True,
                data=data
            )
            
        except Exception as e:
            logger.exception("Error fetching Star Trek quote")
            return PluginResult(
                available=False,
                error=str(e)
            )
    
    def get_formatted_display(self) -> Optional[List[str]]:
        """Return a formatted quote display sized to the current board.

        ``self.board`` is unset (``None``) outside a board-scoped render --
        unit tests and legacy callers both hit this -- so that case is
        treated as a Flagship (22x6), the platform's own default. Every
        other dimension is derived from ``board.cols``/``board.rows``: a
        Note gets two lines of quote and a truncated-with-ellipsis
        attribution if needed, while a tall note_array panel gets as many
        wrapped lines as it has rows for, instead of being cut to five.
        """
        result = self.fetch_data()
        if not result.available or not result.data:
            return None

        data = result.data
        quote = data["quote"]
        character = data["character"]

        board = self.board or BoardContext.from_device_type("flagship")
        cols = board.cols
        # Every row but the last is quote text; the last is the attribution.
        content_budget = max(1, board.rows - 1)

        lines = _fit_lines(_wrap_text(quote, cols), content_budget, cols)
        while len(lines) < content_budget:
            lines.append("")

        attribution = f"- {character}"
        if count_tiles(attribution) > cols:
            attribution = attribution[: max(0, cols - 1)].rstrip() + "…"
        lines.append(attribution.rjust(cols))

        return lines


# Export the plugin class
Plugin = StarTrekQuotesPlugin

