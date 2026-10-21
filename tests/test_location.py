"""Locations d'armes : /location, /recaplocation, /closelocation — montant dû = jours × 100 000 silver."""
import asyncio
from datetime import datetime, UTC
from types import SimpleNamespace

import pytest

from Service import location
from tests.fakes import fake_member, fake_role

GUILD = 111


def loc(**kw):
    row = {"id": 7, "user_id": "2", "user_name": "Alice", "arme": "Hallebarde", "caution": 0,
           "jours_ecoules": 3, "started_at": datetime(2026, 10, 18, 20, 0, tzinfo=UTC), "is_closed": False}
    return row | kw


@pytest.fixture
def env(monkeypatch):
    env = SimpleNamespace(locations=[], created=[], closed=[])

    async def create_location(**kw):
        env.created.append(kw)
        return 12

    async def get_active_locations(guild_id):
        return env.locations

    async def get_location_by_id(loc_id, guild_id):
        return next((l for l in env.locations if l["id"] == loc_id), None)

    async def close_location(loc_id):
        env.closed.append(loc_id)
    for f in (create_location, get_active_locations, get_location_by_id, close_location):
        monkeypatch.setattr(location.db, f.__name__, f)
    return env


def interaction(user, members=()):
    known = {m.id: m for m in members}
    inter = SimpleNamespace(user=user, replies=[], embeds=[],
                            guild=SimpleNamespace(id=GUILD, get_member=lambda uid: known.get(uid)))

    async def send_message(content=None, embed=None, **kwargs):
        inter.replies.append(content)
        inter.embeds.append(embed)
    inter.response = SimpleNamespace(send_message=send_message)
    return inter


def officer():
    return fake_member(user_id=1, display_name="Off", roles=[fake_role("Officier")])


def run(command, inter, *args):
    asyncio.run(command.callback(location.Location(bot=None), inter, *args))
    return inter


def fields(embed):
    return {f.name: f.value for f in embed.fields}


@pytest.mark.parametrize("command, args", [
    (location.Location.location, (fake_member(user_id=2), "Arc", 0)),
    (location.Location.recaplocation, ()),
    (location.Location.closelocation, (7,)),
])
def test_officer_only(env, command, args):
    env.locations = [loc()]
    inter = run(command, interaction(fake_member(user_id=5, roles=[fake_role("Membre")])), *args)
    assert "⛔" in inter.replies[0]
    assert env.created == [] and env.closed == []


def test_create_location(env):
    alice = fake_member(user_id=2, display_name="Alice")
    alice.mention = "<@2>"
    inter = run(location.Location.location, interaction(officer()), alice, "Hallebarde", 2_000_000)
    assert env.created == [{"guild_id": GUILD, "user_id": "2", "user_name": "Alice",
                            "arme": "Hallebarde", "caution": 2_000_000}]
    embed = inter.embeds[0]
    assert embed.title == "📦 Location #12 créée"
    assert fields(embed)["Caution"] == "🔒 2 000 000 silver"


def test_create_location_without_deposit(env):
    alice = fake_member(user_id=2)
    alice.mention = "<@2>"
    inter = run(location.Location.location, interaction(officer()), alice, "Arc", 0)
    assert fields(inter.embeds[0])["Caution"] == "*Aucune*"


def test_recap_shows_amount_owed(env):
    alice = fake_member(user_id=2)
    alice.mention = "<@2>"
    env.locations = [loc(), loc(id=8, user_id="3", user_name="Bob", jours_ecoules=0, caution=500_000)]
    inter = run(location.Location.recaplocation, interaction(officer(), members=[alice]))
    f = fields(inter.embeds[0])
    assert "<@2>" in f["#7 · Alice"] and "**300 000 silver**" in f["#7 · Alice"]
    assert "Début : 18/10/2026" in f["#7 · Alice"]
    assert "Caution" not in f["#7 · Alice"]
    assert f["#8 · Bob"].startswith("Bob")   # parti du serveur : pseudo enregistré
    assert "**0 silver**" in f["#8 · Bob"] and "500 000" in f["#8 · Bob"]
    assert inter.embeds[0].footer.text.startswith("2 location(s)")


def test_recap_empty(env):
    inter = run(location.Location.recaplocation, interaction(officer()))
    assert "Aucune location" in inter.replies[0]


def test_close_location_final_amount_and_deposit(env):
    env.locations = [loc(jours_ecoules=5, caution=1_000_000)]
    inter = run(location.Location.closelocation, interaction(officer()), 7)
    assert env.closed == [7]
    f = fields(inter.embeds[0])
    assert f["Montant final"] == "💰 **500 000 silver**"
    assert f["Caution à rembourser"] == "🔒 **1 000 000 silver**"
    assert f["Joueur"] == "Alice"


def test_close_unknown_location(env):
    inter = run(location.Location.closelocation, interaction(officer()), 99)
    assert "introuvable" in inter.replies[0] and env.closed == []


def test_close_already_closed_location(env):
    env.locations = [loc(is_closed=True)]
    inter = run(location.Location.closelocation, interaction(officer()), 7)
    assert "déjà clôturée" in inter.replies[0] and env.closed == []
