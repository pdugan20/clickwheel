"""Unit tests for the primary-artist normalization helper.

Lives behind a tiny string helper but the rules matter — get_ipod_contents
uses this to roll up collabs in the capacity-bar top-N. A regression here
fragments the legend the moment Taylor Swift drops another duet.
"""

from __future__ import annotations

import pytest

from clickwheel.actions import primary_artist


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Comma-separated collab → first artist wins.
        ("Taylor Swift, Ed Sheeran", "Taylor Swift"),
        ("Taylor Swift, Colbie Caillat", "Taylor Swift"),
        # No collab — pass-through.
        ("Taylor Swift", "Taylor Swift"),
        # Whitespace around the comma is normalized.
        ("Taylor Swift,   Ed Sheeran", "Taylor Swift"),
        ("  Taylor Swift  ", "Taylor Swift"),
        # Featured-artist annotations strip cleanly.
        ("Drake feat. Rihanna", "Drake"),
        ("Drake feat Rihanna", "Drake"),
        ("Drake (feat. Rihanna)", "Drake"),
        ("Drake Featuring Rihanna", "Drake"),
        ("Drake with Rihanna", "Drake"),
        # Mixed: featured suffix AFTER a comma split would still work.
        ("Drake, Future feat. Travis Scott", "Drake"),
        # Ampersand stays — legitimate band-name delimiter.
        ("Simon & Garfunkel", "Simon & Garfunkel"),
        # Earth, Wind & Fire — unfortunate edge case where the comma
        # *is* part of the band name. We accept the false positive
        # because correctly-tagged libraries use "Earth, Wind & Fire"
        # rarely and the alternative (no split at all) would defeat the
        # whole rollup.
        ("Earth, Wind & Fire", "Earth"),
        # Empty / None → Unknown.
        ("", "Unknown"),
        (None, "Unknown"),
        ("   ", "Unknown"),
    ],
)
def test_primary_artist(raw: str | None, expected: str) -> None:
    assert primary_artist(raw) == expected
