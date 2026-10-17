"""!bal : blague de guilde visible de tous (« Connard, c'est /monbal » en gros) ; /monbal garde le solde."""
import asyncio
from types import SimpleNamespace

import db
from Service import bal


def test_bal_joke_is_big_and_visible_to_everyone():
    sent = []

    async def reply(content, **kwargs):
        sent.append((content, kwargs))

    asyncio.run(bal.Bal.bal_joke.callback(bal.Bal(bot=None), SimpleNamespace(reply=reply)))
    assert sent == [("# Connard, c'est /monbal", {"mention_author": False})]   # titre Markdown, pas éphémère


def test_monbal_still_shows_the_balance(monkeypatch):
    sent = []

    async def defer(**kwargs):
        pass

    async def followup_send(content, **kwargs):
        sent.append((content, kwargs))

    async def get_bal(user_id, guild_id):
        return 1_500_000

    monkeypatch.setattr(bal, "is_membre", lambda user: True)
    monkeypatch.setattr(db, "get_bal", get_bal)
    inter = SimpleNamespace(
        user=SimpleNamespace(id=42, display_name="Lily"),
        guild=SimpleNamespace(id=999),                       # serveur tiers : réponse simple
        response=SimpleNamespace(defer=defer),
        followup=SimpleNamespace(send=followup_send),
    )
    asyncio.run(bal.Bal.monbal.callback(bal.Bal(bot=None), inter))
    assert len(sent) == 1
    assert sent[0][1] == {"ephemeral": True}
    assert bal.fmt_silver(1_500_000) in sent[0][0]
