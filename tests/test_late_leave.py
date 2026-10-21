"""Désinscription tardive : un joueur qui se retire à moins de 30 min du départ → MP au créateur de l'acti."""
import asyncio
from datetime import datetime, timedelta, UTC
from types import SimpleNamespace

import pytest

from Service import activites
from Service.activites import LeaveButton, is_late_leave
from tests.test_validation import ACTI, CREATOR, PLAYER, FakeClient, interaction, member

NOW = datetime(2026, 10, 21, 19, 0, tzinfo=UTC)


@pytest.mark.parametrize("start, late", [
    (None, False),                          # pas d'heure de départ
    (NOW + timedelta(hours=2), False),
    (NOW + timedelta(minutes=31), False),
    (NOW + timedelta(minutes=30), True),
    (NOW + timedelta(minutes=5), True),
    (NOW - timedelta(minutes=10), True),    # déjà commencée
])
def test_is_late_leave(start, late):
    assert is_late_leave(start, NOW) is late


@pytest.fixture
def acti(monkeypatch):
    data = {
        "creator": "Chef", "creator_id": CREATOR, "created_at": None, "template": "Donjon", "max_players": 3,
        "bal": True, "slots": {"TANK": [(PLAYER, "Bob", "Tank Masse")], "DPS": []}, "channel_id": 1,
        "guild_id": 111, "waitlist": [(40, "Zed")], "validation": False, "pending": [],
        "start_at": datetime.now(UTC) + timedelta(minutes=10),
    }
    monkeypatch.setitem(activites.activities, ACTI, data)

    async def noop(*a, **k):
        return None
    monkeypatch.setattr(activites, "save_activities", noop)
    monkeypatch.setattr(activites, "log_error", noop)
    monkeypatch.setattr(activites, "build_embed", lambda data: None)
    monkeypatch.setattr(activites, "build_view", lambda aid: None)
    return data


def leave(user, client):
    inter = interaction(user, client, message=SimpleNamespace(edit=lambda **k: asyncio.sleep(0)))
    asyncio.run(LeaveButton(ACTI).callback(inter))
    return inter


def test_late_leave_dms_creator(acti):
    client = FakeClient()
    leave(member(PLAYER, "Membre", name="Bob"), client)
    assert acti["slots"]["TANK"] == []
    [(to, content, _)] = client.dms
    assert to == CREATOR
    assert "Bob" in content and "Donjon" in content and "TANK" in content
    assert f"/111/1/{ACTI}" in content


def test_early_leave_sends_nothing(acti):
    acti["start_at"] = datetime.now(UTC) + timedelta(hours=2)
    client = FakeClient()
    leave(member(PLAYER, "Membre"), client)
    assert acti["slots"]["TANK"] == [] and client.dms == []


def test_leaving_waitlist_sends_nothing(acti):
    client = FakeClient()
    leave(member(40, "Membre"), client)
    assert acti["waitlist"] == [] and client.dms == []


def test_creator_leaving_is_not_notified(acti):
    acti["slots"]["DPS"].append((CREATOR, "Chef", ""))
    client = FakeClient()
    leave(member(CREATOR, "Membre"), client)
    assert client.dms == []


def test_creator_dms_closed_does_not_fail(acti):
    client = FakeClient(closed={CREATOR})
    inter = leave(member(PLAYER, "Membre"), client)
    assert "retiré" in inter.replies[-1]
