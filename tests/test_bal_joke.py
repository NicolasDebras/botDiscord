"""/monbal : blague de guilde sur le serveur principal, solde simple sur les serveurs tiers."""
import asyncio
from types import SimpleNamespace

import pytest

import db
from Service import bal


def _interaction(guild_id):
    sent = []

    async def send_message(content, **kwargs):
        sent.append(("message", content, kwargs))

    async def defer(**kwargs):
        sent.append(("defer", None, kwargs))

    async def followup_send(content, **kwargs):
        sent.append(("followup", content, kwargs))

    inter = SimpleNamespace(
        user=SimpleNamespace(id=42, display_name="Lily"),
        guild=SimpleNamespace(id=guild_id),
        response=SimpleNamespace(send_message=send_message, defer=defer),
        followup=SimpleNamespace(send=followup_send),
    )
    return inter, sent


@pytest.fixture
def member(monkeypatch):
    monkeypatch.setattr(bal, "is_membre", lambda user: True)


def test_monbal_on_the_main_guild_answers_the_joke_only(monkeypatch, member):
    async def no_db(*args, **kwargs):
        raise AssertionError("pas de lecture du solde pour la blague")

    monkeypatch.setattr(db, "get_bal", no_db)
    inter, sent = _interaction(bal._MAIN_GUILD_ID)
    asyncio.run(bal.Bal.monbal.callback(bal.Bal(bot=None), inter))
    assert sent == [("message", "connard, c'est mon bal", {"ephemeral": True})]


def test_monbal_on_another_guild_still_shows_the_balance(monkeypatch, member):
    async def get_bal(uid, guild_id):
        assert (uid, guild_id) == ("42", 999)
        return 1_500_000

    monkeypatch.setattr(db, "get_bal", get_bal)
    inter, sent = _interaction(999)
    asyncio.run(bal.Bal.monbal.callback(bal.Bal(bot=None), inter))
    assert sent[-1] == ("followup", "💰 Ton solde BAL : **1 500 000 silver**", {"ephemeral": True})
