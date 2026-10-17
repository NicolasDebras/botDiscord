"""« !bal » : commande texte de blague (la vraie commande est /monbal)."""
import asyncio
from types import SimpleNamespace

from Service import bal


def test_bang_bal_replies_with_the_guild_joke_without_pinging():
    replies = []

    async def reply(content, **kwargs):
        replies.append((content, kwargs))

    cog = bal.Bal(bot=None)
    ctx = SimpleNamespace(reply=reply)
    asyncio.run(bal.Bal.bal_joke.callback(cog, ctx))
    assert replies == [("connard, c'est mon bal", {"mention_author": False})]


def test_bang_bal_answers_whatever_the_case():
    assert bal.Bal.bal_joke.name == "bal"
    assert {"Bal", "BAL"} <= set(bal.Bal.bal_joke.aliases)
