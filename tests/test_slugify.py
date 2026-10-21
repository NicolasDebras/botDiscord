"""Nom du salon de candidature : accents convertis, tirets fusionnés."""
import pytest

from Service.recrutement_externe import _slugify


@pytest.mark.parametrize(("text", "expected"), [
    ("candidature-Élodie", "candidature-elodie"),
    ("candidature-a - b", "candidature-a-b"),
    ("Çà_et  là", "ca-et-la"),
    ("Lily!!", "lily"),
    ("!!!", "candidature"),
    ("x" * 120, "x" * 90),
])
def test_slugify(text, expected):
    assert _slugify(text) == expected
