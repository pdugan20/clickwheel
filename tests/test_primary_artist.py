"""Unit tests for the primary-artist resolution helper.

Confirms the album-artist-first strategy: trust album_artist when set,
fall back to per-track artist, strip "feat./featuring/with X"
annotations, and never try to parse multi-artist strings (because the
separators we'd split on appear in legitimate band names).
"""

from __future__ import annotations

import pytest

from clickwheel.actions import primary_artist

# (artist, album_artist, expected) — None means missing tag.
CASES: list[tuple[str | None, str | None, str]] = [
    # === album_artist wins when present ===
    # The screenshot case: per-track artist has the collab variant,
    # album_artist is the canonical lead.
    ("Taylor Swift / HAIM", "Taylor Swift", "Taylor Swift"),
    ("Taylor Swift / Bon Iver", "Taylor Swift", "Taylor Swift"),
    ("Taylor Swift, Ed Sheeran", "Taylor Swift", "Taylor Swift"),
    ("Daft Punk feat. Julian Casablancas", "Daft Punk", "Daft Punk"),
    ("Norah Jones with Brian Blade", "Norah Jones", "Norah Jones"),
    ("Doja Cat, SZA", "Doja Cat", "Doja Cat"),
    # === real band names with embedded separators stay intact ===
    ("AC/DC", "AC/DC", "AC/DC"),
    ("Crosby, Stills and Nash", "Crosby, Stills and Nash", "Crosby, Stills and Nash"),
    ("Belle & Sebastian", "Belle & Sebastian", "Belle & Sebastian"),
    ("Earth, Wind & Fire", "Earth, Wind & Fire", "Earth, Wind & Fire"),
    ("Simon & Garfunkel", "Simon & Garfunkel", "Simon & Garfunkel"),
    (
        "Sly and the Family Stone",
        "Sly and the Family Stone",
        "Sly and the Family Stone",
    ),
    # Duos that record together — album_artist preserves the duo identity.
    ("Beyoncé & Jay-Z", "Beyoncé & Jay-Z", "Beyoncé & Jay-Z"),
    # === fallback to artist when album_artist missing or empty ===
    ("AC/DC", None, "AC/DC"),
    ("Taylor Swift", "", "Taylor Swift"),
    ("Taylor Swift", "   ", "Taylor Swift"),
    # === fallback when album_artist is the compilation marker ===
    ("Calvin Harris, Dua Lipa", "Various Artists", "Calvin Harris, Dua Lipa"),
    ("Some Artist", "various artists", "Some Artist"),  # case-insensitive
    ("Some Artist", "VARIOUS ARTISTS", "Some Artist"),
    # === feat./featuring/with stripped from either field ===
    # Album_artist sometimes leaks collab annotations.
    (None, "Daft Punk feat. Pharrell Williams", "Daft Punk"),
    (None, "Drake (feat. Rihanna)", "Drake"),
    (None, "Courtney Barnett featuring Marlon Williams", "Courtney Barnett"),
    (None, "Aretha Franklin With the Royal Philarmonic Orchestra", "Aretha Franklin"),
    # When album_artist is missing, the strip applies to the artist fallback too.
    ("Drake feat. Rihanna", None, "Drake"),
    ("Norah Jones with Jeff Tweedy", None, "Norah Jones"),
    # === empty / None / whitespace ===
    (None, None, "Unknown"),
    ("", None, "Unknown"),
    ("   ", "   ", "Unknown"),
    (None, "", "Unknown"),
    # === whitespace normalization ===
    ("  Taylor Swift  ", None, "Taylor Swift"),
    (None, "  Taylor Swift  ", "Taylor Swift"),
]


@pytest.mark.parametrize("artist,album_artist,expected", CASES)
def test_primary_artist(
    artist: str | None,
    album_artist: str | None,
    expected: str,
) -> None:
    assert primary_artist(artist, album_artist) == expected


def test_primary_artist_default_album_artist_is_none() -> None:
    """The album_artist arg defaults to None — single-arg calls still work."""
    assert primary_artist("Taylor Swift") == "Taylor Swift"
    assert primary_artist("AC/DC") == "AC/DC"
    # No album_artist fallback to strip collab text from the artist field —
    # but the feat./with suffix strip still applies.
    assert primary_artist("Daft Punk feat. Pharrell") == "Daft Punk"
