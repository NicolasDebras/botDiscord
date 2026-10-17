"""/monbal : blague de guilde (« connard, c'est mon bal ») au lieu du solde, sur tous les serveurs."""
import asyncio
from types import SimpleNamespace

import pytest

import db
from config import GUILD_ID
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


@pytest.mark.parametrize("guild_id", [GUILD_ID, 999])   # serveur principal et serveur tiers
def test_monbal_answers_the_joke_only_on_every_server(monkeypatch, member, guild_id):
    async def no_db(*args, **kwargs):
        raise AssertionError("pas de lecture du solde pour la blague")

    monkeypatch.setattr(db, "get_bal", no_db)
    inter, sent = _interaction(guild_id)
    asyncio.run(bal.Bal.monbal.callback(bal.Bal(bot=None), inter))
    assert sent == [("message", "connard, c'est mon bal", {"ephemeral": True})]
