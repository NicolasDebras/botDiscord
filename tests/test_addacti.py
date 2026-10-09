"""/addacti : rôles proposés et rôle retenu = ceux des activités en cours (lignes de compo du site, PF2…)."""
import asyncio
from types import SimpleNamespace

import pytest

from Service import activites
from Service.admin import guild_role_keys, resolve_role, role_autocomplete

SLOTS = {"TANK · Def tank": [], "TANK · Main tank": [], "HEAL": [], "DPS": [], "PF2:DPS": [], "PF2:Fill": []}


@pytest.fixture
def running(monkeypatch):
    """Deux activités sur le serveur 1 (compo du site + acti simple), une sur un autre serveur."""
    acts = {
        10: {"guild_id": 1, "slots": SLOTS},
        11: {"guild_id": 1, "slots": {"HEAL": [], "Éclaireur": []}},
        12: {"guild_id": 2, "slots": {"SECRET": []}},
    }
    monkeypatch.setattr(activites, "activities", acts)
    monkeypatch.setattr("Service.admin.activities", acts)
    return acts


def test_resolve_role_exact_case_label_and_unique_base():
    assert resolve_role(SLOTS, "TANK · Main tank") == "TANK · Main tank"
    assert resolve_role(SLOTS, "tank · main tank") == "TANK · Main tank"   # plus de .upper() qui cassait la clé
    assert resolve_role(SLOTS, "dps pf2") == "PF2:DPS"
    assert resolve_role(SLOTS, "DPS (PF2)") == "PF2:DPS"
    assert resolve_role(SLOTS, "heal") == "HEAL"
    assert resolve_role({"TANK · Main tank": [], "HEAL": []}, "TANK") == "TANK · Main tank"   # une seule ligne TANK


def test_resolve_role_unknown_or_ambiguous():
    assert resolve_role(SLOTS, "TANK") is None        # deux lignes TANK : il faut préciser
    assert resolve_role(SLOTS, "SUPPORT") is None


def test_guild_role_keys_come_from_running_activities_of_this_server(running):
    keys = guild_role_keys(1)
    assert keys[:2] == ["TANK · Def tank", "TANK · Main tank"]
    assert "Éclaireur" in keys and "PF2:DPS" in keys
    assert keys.count("HEAL") == 1
    assert "SECRET" not in keys                         # autre serveur
    assert "SUPPORT" in guild_role_keys(99)             # aucune activité : rôles par défaut


def test_autocomplete_shows_readable_labels(running):
    inter = SimpleNamespace(guild_id=1)
    choices = asyncio.run(role_autocomplete(inter, "dps"))
    assert [(c.name, c.value) for c in choices] == [("DPS", "DPS"), ("DPS PF2", "PF2:DPS")]
    tanks = asyncio.run(role_autocomplete(inter, "main"))
    assert [c.value for c in tanks] == ["TANK · Main tank"]
