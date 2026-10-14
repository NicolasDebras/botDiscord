"""/acti heure:… — lecture de l'heure de départ (heure de Paris) et affichage dans l'embed."""
from datetime import datetime, UTC

import pytest

from Service import activites
from Service.activites import PARIS, build_embed, heure_line, parse_heure

# Mardi 14 octobre 2026, 18:00 à Paris (heure d'été, UTC+2)
NOW = datetime(2026, 10, 14, 18, 0, tzinfo=PARIS)


def paris(dt):
    return dt.astimezone(PARIS).strftime("%d/%m %H:%M")


@pytest.mark.parametrize("text, expected", [
    ("21h", "14/10 21:00"),
    ("21H30", "14/10 21:30"),
    ("21:30", "14/10 21:30"),
    ("21 h 05", "14/10 21:05"),
    ("21", "14/10 21:00"),
    ("9h", "15/10 09:00"),          # déjà passée aujourd'hui → demain
    ("17h58", "14/10 17:58"),       # 2 min de retard tolérées (on crée l'acti « pour maintenant »)
    ("18/10 21h", "18/10 21:00"),
    ("1/11 20:30", "01/11 20:30"),
])
def test_parse_heure_formats(text, expected):
    start = parse_heure(text, NOW)
    assert start.tzinfo == UTC
    assert paris(start) == expected


def test_parse_heure_empty_means_no_time():
    assert parse_heure("", NOW) is None
    assert parse_heure("   ", NOW) is None


@pytest.mark.parametrize("text", ["25h", "21h75", "demain", "21h30 ce soir", "13/10 21h", "31/02 21h", "21/13 21h"])
def test_parse_heure_rejects_invalid_or_past(text):
    with pytest.raises(ValueError):
        parse_heure(text, NOW)


def test_parse_heure_keeps_paris_wall_time_across_dst_change():
    # Samedi 24/10 22:00 ; passage à l'heure d'hiver dans la nuit : « 21h » = dimanche 21:00 à Paris (UTC+1)
    start = parse_heure("21h", datetime(2026, 10, 24, 22, 0, tzinfo=PARIS))
    assert paris(start) == "25/10 21:00"
    assert start.hour == 20   # 21:00 Paris en hiver = 20:00 UTC


def test_heure_line_uses_discord_timestamps():
    start = datetime(2026, 10, 14, 19, 0, tzinfo=UTC)
    ts = int(start.timestamp())
    assert heure_line(start) == f"🕘 **Heure :** <t:{ts}:F> (<t:{ts}:R>)"
    assert heure_line(None) == ""


def test_embed_shows_the_start_time_above_place_and_tier(monkeypatch):
    monkeypatch.setattr(activites, "load_all_templates", lambda gid: {})
    start = datetime(2026, 10, 14, 19, 0, tzinfo=UTC)
    data = {
        "creator": "Chef", "created_at": datetime(2026, 10, 14, 16, 0, tzinfo=UTC), "template": None, "max_players": 10,
        "bal": True, "slots": {"DPS": []}, "guild_id": 1, "depart": "HO", "tier": "T8", "start_at": start,
    }
    desc = build_embed(data).description
    lines = desc.split("\n")
    assert lines[0] == heure_line(start)
    assert "📍 **Départ :** HO" in lines[1] and "⚔️ **Tier :** T8" in lines[1]
    assert "🕘" not in build_embed({**data, "start_at": None}).description
