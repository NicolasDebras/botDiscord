"""Commandes BAL qui touchent à l'argent : /addbal, /retirebal, /transferbal, /paybal.
La base est remplacée par un dict en mémoire, Discord par des doubles (aucun appel réseau)."""
import asyncio
from types import SimpleNamespace

import pytest

from Service import bal
from tests.fakes import fake_member, fake_role

GUILD = 111
ADMIN, ALICE, BOB = 1, 2, 3


class FakeDB:
    """Soldes BAL en mémoire, mêmes signatures que db.py."""
    def __init__(self, soldes=None):
        self.soldes = dict(soldes or {})

    async def get_bal(self, uid, guild_id):
        return self.soldes.get(uid, 0)

    async def set_bal(self, uid, total, guild_id):
        self.soldes[uid] = total

    async def increment_bal(self, uid, delta, guild_id):
        self.soldes[uid] = self.soldes.get(uid, 0) + delta
        return self.soldes[uid]

    async def increment_bal_batch(self, deltas, guild_id):
        return {uid: await self.increment_bal(uid, d, guild_id) for uid, d in deltas.items()}

    async def transfer_bal(self, sender, receiver, montant, guild_id):
        if self.soldes.get(sender, 0) < montant:
            return None
        self.soldes[sender] -= montant
        self.soldes[receiver] = self.soldes.get(receiver, 0) + montant
        return self.soldes[sender], self.soldes[receiver]


@pytest.fixture
def env(monkeypatch):
    fake = FakeDB()
    for name in ("get_bal", "set_bal", "increment_bal", "increment_bal_batch", "transfer_bal"):
        monkeypatch.setattr(bal.db, name, getattr(fake, name))
    fake.logs, fake.alerts = [], []

    async def append_bal_log(action, by, entries, **kwargs):
        fake.logs.append((action, by, entries, kwargs))

    async def notify_bal_limit(client, uid, total, guild_id=0):
        fake.alerts.append((uid, total))
    monkeypatch.setattr(bal, "append_bal_log", append_bal_log)
    monkeypatch.setattr(bal, "notify_bal_limit", notify_bal_limit)
    return fake


def member(uid, *roles, name=None, administrator=False):
    m = fake_member(user_id=uid, display_name=name or f"J{uid}", roles=[fake_role(r) for r in roles],
                    administrator=administrator)
    m.mention = f"<@{uid}>"
    m.dms = []

    async def send(content=None, **kwargs):
        m.dms.append(content)
    m.send = send
    return m


def interaction(user):
    inter = SimpleNamespace(user=user, guild=SimpleNamespace(id=GUILD), client=None, replies=[])

    async def send_message(content=None, **kwargs):
        inter.replies.append(content)

    async def defer(**kwargs):
        pass

    async def edit_original_response(**kwargs):
        pass
    inter.response = SimpleNamespace(send_message=send_message, defer=defer)
    inter.followup = SimpleNamespace(send=send_message)
    inter.edit_original_response = edit_original_response
    return inter


def run(command, inter, *args):
    asyncio.run(command.callback(bal.Bal(bot=None), inter, *args))
    return inter


def admin():
    return member(ADMIN, "Officier", name="Off")


# ── /addbal ──────────────────────────────────────────────────────────────────

def test_addbal_credits_logs_and_checks_limit(env):
    env.soldes["2"] = 500
    inter = run(bal.Bal.addbal, interaction(admin()), member(ALICE, name="Alice"), 1_500)
    assert env.soldes["2"] == 2_000
    [(action, by, [entry], kwargs)] = env.logs
    assert (action, by, kwargs["guild_id"]) == ("addbal", "Off", GUILD)
    assert entry == {"uid": "2", "name": "Alice", "delta": 1_500, "total": 2_000}
    assert env.alerts == [(ALICE, 2_000)]
    assert "+1 500" in inter.replies[0] and "2 000" in inter.replies[0]


def test_addbal_refused_without_officer_role(env):
    inter = run(bal.Bal.addbal, interaction(member(BOB, "Membre")), member(ALICE), 1_000)
    assert env.soldes == {} and env.logs == []
    assert "⛔" in inter.replies[0]


def test_addbal_allowed_for_server_administrator(env):
    run(bal.Bal.addbal, interaction(member(BOB, administrator=True)), member(ALICE), 10)
    assert env.soldes["2"] == 10


# ── /retirebal ───────────────────────────────────────────────────────────────

def test_retirebal_removes_amount(env):
    env.soldes["2"] = 1_000
    run(bal.Bal.retirebal, interaction(admin()), member(ALICE), 300)
    assert env.soldes["2"] == 700
    assert env.logs[0][2][0]["delta"] == -300


def test_retirebal_never_goes_below_zero(env):
    env.soldes["2"] = 200
    inter = run(bal.Bal.retirebal, interaction(admin()), member(ALICE), 1_000)
    assert env.soldes["2"] == 0
    assert env.logs[0][2][0] == {"uid": "2", "name": "J2", "delta": -200, "total": 0}   # retrait réel loggé
    assert "-200" in inter.replies[0]


def test_retirebal_refused_without_officer_role(env):
    env.soldes["2"] = 200
    run(bal.Bal.retirebal, interaction(member(BOB, "Membre")), member(ALICE), 100)
    assert env.soldes["2"] == 200 and env.logs == []


# ── /transferbal ─────────────────────────────────────────────────────────────

def test_transferbal_moves_silver_and_dms_receiver(env):
    env.soldes.update({"2": 1_000, "3": 50})
    bob = member(BOB, name="Bob")
    inter = run(bal.Bal.transferbal, interaction(member(ALICE, "Membre", name="Alice")), bob, 400)
    assert env.soldes == {"2": 600, "3": 450}
    [(action, _, entries, _)] = env.logs
    assert action == "transferbal"
    assert [(e["uid"], e["delta"], e["total"]) for e in entries] == [("2", -400, 600), ("3", 400, 450)]
    assert env.alerts == [(ALICE, 600), (BOB, 450)]
    assert "Alice" in bob.dms[0] and "50" in bob.dms[0] and "450" in bob.dms[0]
    assert "600" in inter.replies[0]


def test_transferbal_insufficient_balance_changes_nothing(env):
    env.soldes.update({"2": 100})
    inter = run(bal.Bal.transferbal, interaction(member(ALICE, "Membre")), member(BOB), 1_000)
    assert env.soldes == {"2": 100} and env.logs == []
    assert "Solde insuffisant" in inter.replies[0] and "1 000" in inter.replies[0]


def test_transferbal_to_self_is_refused(env):
    env.soldes["2"] = 100
    inter = run(bal.Bal.transferbal, interaction(member(ALICE, "Membre")), member(ALICE), 50)
    assert env.soldes == {"2": 100}
    assert "toi-même" in inter.replies[0]


def test_transferbal_requires_member_role(env):
    env.soldes["2"] = 100
    inter = run(bal.Bal.transferbal, interaction(member(ALICE)), member(BOB), 50)
    assert env.soldes == {"2": 100}
    assert "⛔" in inter.replies[0]


def test_transferbal_receiver_dms_closed_still_transfers(env):
    env.soldes["2"] = 100
    bob = member(BOB)

    async def closed(*a, **k):
        raise RuntimeError("MP fermés")
    bob.send = closed
    run(bal.Bal.transferbal, interaction(member(ALICE, "Membre")), bob, 100)
    assert env.soldes == {"2": 0, "3": 100}


# ── /paybal ──────────────────────────────────────────────────────────────────

ACTI = 777


@pytest.fixture
def paybal(env, monkeypatch):
    """Lance /paybal et renvoie (le choix d'activité, l'interaction de départ)."""
    selects = []

    class FakeSelect:
        def __init__(self, on_select, placeholder, guild_id):
            selects.append(on_select)

    class FakeView:
        def __init__(self, timeout):
            pass

        def add_item(self, item):
            pass

        def stop(self):
            pass
    monkeypatch.setattr(bal, "ActivitySelect", FakeSelect)
    monkeypatch.setattr(bal.discord.ui, "View", FakeView)
    monkeypatch.setitem(bal.activities, ACTI, {
        "bal": True, "template": "Donjon",
        "slots": {"TANK": [(ALICE, "Alice", "")], "DPS": [(BOB, "Bob", "")]},
    })

    def start(montant=1_000):
        inter = run(bal.Bal.paybal, interaction(admin()), montant)
        return selects[0], inter

    def choose(on_select, value=str(ACTI)):
        inter = interaction(admin())
        asyncio.run(on_select(inter, value))
        return inter
    return SimpleNamespace(start=start, choose=choose, env=env)


def test_paybal_pays_every_participant_once(paybal):
    on_select, _ = paybal.start(1_000)
    paybal.choose(on_select)
    assert paybal.env.soldes == {"2": 1_000, "3": 1_000}
    [(action, by, entries, kwargs)] = paybal.env.logs
    assert (action, by, kwargs["template"]) == ("paybal", "Off", "Donjon")
    assert {e["name"] for e in entries} == {"Alice", "Bob"}

    second = paybal.choose(on_select)   # second clic sur la liste : refusé
    assert paybal.env.soldes == {"2": 1_000, "3": 1_000}
    assert "déjà effectué" in second.replies[0]


def test_paybal_refuses_non_bal_activity(paybal):
    bal.activities[ACTI]["bal"] = False
    on_select, _ = paybal.start()
    inter = paybal.choose(on_select)
    assert paybal.env.soldes == {} and "pas marquée **BAL**" in inter.replies[0]


def test_paybal_activity_without_participants(paybal):
    bal.activities[ACTI]["slots"] = {"TANK": []}
    on_select, _ = paybal.start()
    inter = paybal.choose(on_select)
    assert paybal.env.soldes == {} and "Aucun participant" in inter.replies[0]


def test_paybal_unknown_activity(paybal):
    on_select, _ = paybal.start()
    inter = paybal.choose(on_select, "999")
    assert paybal.env.soldes == {} and "introuvable" in inter.replies[0]


def test_paybal_refused_without_officer_role(env):
    inter = run(bal.Bal.paybal, interaction(member(BOB, "Membre")), 1_000)
    assert "⛔" in inter.replies[0]
