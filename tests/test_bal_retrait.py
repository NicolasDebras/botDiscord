"""/addbal prévient le joueur en MP ; /retirebal exige un motif (paiement ou amende) et
prévient le joueur en MP d'une amende, avec la raison et le montant retiré."""
import asyncio
from types import SimpleNamespace

import discord
import pytest

import db
from Service import bal


class Member:
    def __init__(self, dm_open=True):
        self.id, self.display_name, self.dms, self.dm_open = 7, "Coskko", [], dm_open

    async def send(self, content):
        if not self.dm_open:
            raise discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "Cannot send messages to this user")
        self.dms.append(content)


@pytest.fixture
def env(monkeypatch):
    state = {"bal": 100_000, "logs": [], "replies": [], "deferred": False}

    async def get_bal(uid, guild_id):
        return state["bal"]

    async def set_bal(uid, total, guild_id):
        state["bal"] = total

    async def increment_bal(uid, delta, guild_id):
        state["bal"] += delta
        return state["bal"]

    async def append_bal_log(action, by, entries, template="", guild_id=0):
        state["logs"].append({"action": action, "entries": entries, "template": template})

    async def noop(*a, **k):
        pass

    monkeypatch.setattr(bal, "is_admin", lambda user: True)
    monkeypatch.setattr(db, "get_bal", get_bal)
    monkeypatch.setattr(db, "set_bal", set_bal)
    monkeypatch.setattr(db, "increment_bal", increment_bal)
    monkeypatch.setattr(bal, "append_bal_log", append_bal_log)
    monkeypatch.setattr(bal, "notify_bal_limit", noop)

    async def defer(**kwargs):
        state["deferred"] = True

    async def reply(content, **kwargs):
        state["replies"].append(content)

    state["inter"] = SimpleNamespace(
        user=SimpleNamespace(id=1, display_name="Ariia"),
        guild=SimpleNamespace(id=999),
        client=None,
        response=SimpleNamespace(defer=defer, send_message=reply),
        followup=SimpleNamespace(send=reply),
    )
    return state


def retire(env, member, montant, motif, raison=None):
    asyncio.run(bal.Bal.retirebal.callback(bal.Bal(bot=None), env["inter"], member, montant, motif, raison))


def test_addbal_sends_the_amount_in_dm(env):
    member = Member()
    asyncio.run(bal.Bal.addbal.callback(bal.Bal(bot=None), env["inter"], member, 50_000))
    assert len(member.dms) == 1
    assert bal.fmt_silver(50_000) in member.dms[0] and bal.fmt_silver(150_000) in member.dms[0]
    assert "Ariia" in member.dms[0]
    assert bal.DM_FAILED not in env["replies"][0]


def test_addbal_still_works_when_dms_are_closed(env):
    asyncio.run(bal.Bal.addbal.callback(bal.Bal(bot=None), env["inter"], Member(dm_open=False), 50_000))
    assert env["bal"] == 150_000
    assert bal.DM_FAILED in env["replies"][0]


def test_amende_sends_reason_and_amount_in_dm(env):
    member = Member()
    retire(env, member, 30_000, bal.MOTIF_AMENDE, "  Retard au CTA ")
    assert env["bal"] == 70_000
    assert len(member.dms) == 1
    assert "Raison : Retard au CTA" in member.dms[0]
    assert bal.fmt_silver(30_000) in member.dms[0] and bal.fmt_silver(70_000) in member.dms[0]
    assert env["logs"][0]["template"] == "Amende : Retard au CTA"
    assert env["logs"][0]["entries"][0]["delta"] == -30_000


def test_amende_dm_shows_what_was_really_taken(env):
    member = Member()
    retire(env, member, 500_000, bal.MOTIF_AMENDE, "AFK")   # plancher à 0 : seuls 100 000 retirés
    assert env["bal"] == 0
    assert bal.fmt_silver(100_000) in member.dms[0]
    assert bal.fmt_silver(500_000) not in member.dms[0]


def test_amende_without_reason_is_refused(env):
    member = Member()
    retire(env, member, 30_000, bal.MOTIF_AMENDE, "   ")
    assert env["bal"] == 100_000 and not env["logs"] and not member.dms
    assert not env["deferred"]
    assert "raison" in env["replies"][0]


def test_paiement_sends_no_dm(env):
    member = Member()
    retire(env, member, 30_000, bal.MOTIF_PAIEMENT)
    assert env["bal"] == 70_000
    assert member.dms == []
    assert env["logs"][0]["template"] == "Paiement"


def test_retrait_label():
    assert bal.retrait_label(bal.MOTIF_PAIEMENT) == "Paiement"
    assert bal.retrait_label(bal.MOTIF_PAIEMENT, "ignoré") == "Paiement"
    assert bal.retrait_label(bal.MOTIF_AMENDE, "Retard") == "Amende : Retard"
