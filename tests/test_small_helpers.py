"""Petits helpers : message de bienvenue, nom du salon de candidature, format des posts acti flash."""
import asyncio
from types import SimpleNamespace

import discord
import pytest

from Service import moderation
from Service.bienvenue import _format
from Service.recrutement_externe import _slugify


# ── Bienvenue / départ ───────────────────────────────────────────────────────

def test_welcome_placeholders():
    member = type("M", (), {"mention": "<@2>", "display_name": "Alice", "__str__": lambda self: "alice#0"})()
    guild = SimpleNamespace(name="Lilium", member_count=42)
    text = _format("Bienvenue {mention} ({pseudo} / {nom}) sur {serveur}, tu es le {membercount}e !", member, guild)
    assert text == "Bienvenue <@2> (Alice / alice#0) sur Lilium, tu es le 42e !"


def test_welcome_without_placeholders_is_unchanged():
    member = type("M", (), {"mention": "", "display_name": "", "__str__": lambda self: ""})()
    assert _format("Salut !", member, SimpleNamespace(name="L", member_count=1)) == "Salut !"


# ── Nom du salon de candidature ──────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("Alice", "alice"),
    ("  Jean Michel  ", "jean-michel"),
    ("Élodie_42", "lodie42"),          # accents et _ retirés (caractères non autorisés)
    ("a   b", "a-b"),                 # espaces multiples → un seul tiret
    ("🔥🔥", "candidature"),           # rien d'exploitable
    ("", "candidature"),
])
def test_slugify(raw, expected):
    assert _slugify(raw) == expected


def test_slugify_is_capped_to_90_chars():
    assert len(_slugify("a" * 200)) == 90


# ── Posts du salon acti flash ────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["21/05 - 21h30 - RAID AVA", "01/11-20H00-Donjon", "21/05 - 21h30 - Raid\nmulti-ligne"])
def test_flash_format_accepted(name):
    assert moderation._FORMAT_RE.match(name)


@pytest.mark.parametrize("name", ["RAID AVA ce soir", "21/05 - RAID", "21/5 - 21h30 - Raid", "21/05 - 21h30 -", "21/05 21h30 Raid"])
def test_flash_format_rejected(name):
    assert not moderation._FORMAT_RE.match(name)


class FakeThread:
    def __init__(self, name, parent_id=moderation._ACTI_FLASH_ID, forbidden=False):
        self.name, self.parent_id, self.owner_id, self.forbidden = name, parent_id, 5, forbidden
        self.deleted = False

    async def delete(self):
        if self.forbidden:
            raise discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "non")
        self.deleted = True


def handle(thread):
    dms = []

    async def fetch_user(uid):
        async def send(content):
            dms.append((uid, content))
        return SimpleNamespace(send=send)
    cog = moderation.Moderation(bot=SimpleNamespace(fetch_user=fetch_user))
    asyncio.run(cog._handle_thread_create(thread))
    return dms


def test_bad_flash_post_is_deleted_and_author_warned():
    thread = FakeThread("raid ce soir")
    [(uid, content)] = handle(thread)
    assert thread.deleted and uid == 5 and "JJ/MM - HHhMM" in content


def test_good_flash_post_is_kept():
    thread = FakeThread("21/05 - 21h30 - RAID AVA")
    assert handle(thread) == [] and not thread.deleted


def test_other_channels_are_ignored():
    thread = FakeThread("n'importe quoi", parent_id=1)
    assert handle(thread) == [] and not thread.deleted


def test_no_dm_if_bot_cannot_delete():
    thread = FakeThread("raid", forbidden=True)
    assert handle(thread) == []
