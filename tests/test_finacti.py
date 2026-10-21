"""/finacti — clôture d'une activité et partage du butin (taxe guilde, carte, pièces, scoot,
multiplicateurs, rôles non payés). Base et Discord remplacés par des doubles."""
import asyncio
from types import SimpleNamespace

import discord
import pytest

from Service import activites
from Service.activites import FinActiModal

ACTI = 4242
GUILD = 111


@pytest.fixture
def env(monkeypatch):
    env = SimpleNamespace(template={"type_acti": "PVE"}, settings={"bal_rate": 85},
                          credited={}, counted=[], logs=[], removed=[], errors=[])

    monkeypatch.setattr(activites, "load_all_templates", lambda gid: {"Donjon": env.template})

    async def load_settings(guild_id=0):
        return env.settings

    async def increment_bal_batch(deltas, guild_id):
        env.credited = dict(deltas)
        return {uid: d + 1_000 for uid, d in deltas.items()}   # 1 000 déjà en BAL

    async def increment_acti_count(ids, guild_id):
        env.counted = sorted(ids)

    async def append_bal_log(action, by, entries, template="", guild_id=0):
        env.logs.append((action, by, entries, template))

    async def remove_activity(msg_id, outcome=None):
        env.removed.append((msg_id, outcome))
        activites.activities.pop(msg_id, None)

    async def noop(*a, **k):
        return None

    async def log_error(where, e, **k):
        env.errors.append(e)

    monkeypatch.setattr(activites, "load_settings", load_settings)
    monkeypatch.setattr(activites.db, "increment_bal_batch", increment_bal_batch)
    monkeypatch.setattr(activites.db, "increment_acti_count", increment_acti_count)
    monkeypatch.setattr(activites, "append_bal_log", append_bal_log)
    monkeypatch.setattr(activites, "remove_activity", remove_activity)
    monkeypatch.setattr(activites, "notify_bal_limit", noop)
    monkeypatch.setattr(activites, "log_error", log_error)
    monkeypatch.setattr(activites, "build_embed", lambda data: discord.Embed(title="Donjon"))
    return env


def acti(monkeypatch, slots):
    data = {"template": "Donjon", "guild_id": GUILD, "channel_id": 1, "slots": slots}
    monkeypatch.setitem(activites.activities, ACTI, data)
    return data


def players(*uids):
    return [(uid, f"J{uid}", "") for uid in uids]


def interaction():
    inter = SimpleNamespace(user=SimpleNamespace(id=9, display_name="Caller"), guild=SimpleNamespace(id=GUILD),
                            client=SimpleNamespace(get_channel=lambda cid: None), replies=[], deferred=False)

    async def send(content=None, **kwargs):
        inter.replies.append(content)

    async def defer(**kwargs):
        inter.deferred = True
    inter.response = SimpleNamespace(send_message=send, defer=defer)
    inter.followup = SimpleNamespace(send=send)
    return inter


def finish(data, recettes, carte="", pieces="", scoot=None):
    """Remplit le modal comme le caller et valide."""
    inter = interaction()

    async def go():
        modal = FinActiModal(ACTI, data)
        modal.recettes._value, modal.cout_carte._value, modal.sac_pieces._value = recettes, carte, pieces
        if scoot is not None:
            modal.scoot_pay._value = scoot
        await modal.on_submit(inter)
    asyncio.run(go())
    return inter


# ── Partage ──────────────────────────────────────────────────────────────────

def test_split_after_costs_tax_and_coins(env, monkeypatch):
    data = acti(monkeypatch, {"TANK": players(1), "DPS": players(2, 3, 4)})
    inter = finish(data, "10 000 000", carte="1 000 000", pieces="350 000")
    # (10 M − 1 M) × 85 % = 7 650 000 ; + 350 000 de pièces = 8 000 000 → 2 000 000 chacun
    assert env.credited == {"1": 2_000_000, "2": 2_000_000, "3": 2_000_000, "4": 2_000_000}
    assert env.counted == ["1", "2", "3", "4"]
    [(action, by, entries, template)] = env.logs
    assert (action, by, template) == ("finacti", "Caller", "Donjon")
    assert entries[0] == {"uid": "1", "name": "J1", "delta": 2_000_000, "total": 2_001_000}
    assert env.removed == [(ACTI, "finacti")]
    summary = inter.replies[-1]
    assert "7 650 000" in summary and "2 000 000" in summary and "Participants : **4**" in summary


def test_split_rounds_down(env, monkeypatch):
    data = acti(monkeypatch, {"DPS": players(1, 2, 3)})
    env.settings = {"bal_rate": 100}
    finish(data, "1 000 000")
    assert env.credited == {"1": 333_333, "2": 333_333, "3": 333_333}   # jamais plus que le distribuable


def test_guild_rate_defaults_to_85(env, monkeypatch):
    data = acti(monkeypatch, {"DPS": players(1)})
    env.settings = {}
    finish(data, "1 000 000")
    assert env.credited == {"1": 850_000}


def test_template_tax_overrides_guild_rate(env, monkeypatch):
    data = acti(monkeypatch, {"DPS": players(1, 2)})
    env.template = {"type_acti": "PVP", "tax_rate": 50}
    finish(data, "1 000 000")
    assert env.credited == {"1": 250_000, "2": 250_000}


def test_role_multipliers(env, monkeypatch):
    data = acti(monkeypatch, {"TANK": players(1), "DPS": players(2, 3, 4)})
    env.settings = {"bal_rate": 100}
    env.template = {"type_acti": "PVE", "role_multipliers": {"TANK": 1.5}}
    inter = finish(data, "9 000 000")
    # poids total 1.5 + 3 = 4.5 → part de base 2 000 000, tank ×1.5
    assert env.credited == {"1": 3_000_000, "2": 2_000_000, "3": 2_000_000, "4": 2_000_000}
    assert "(×1.5)" in inter.replies[-1]


def test_multiplier_on_base_role_applies_to_pf2_slot(env, monkeypatch):
    data = acti(monkeypatch, {"PF2:HEAL": players(1), "DPS": players(2)})
    env.settings = {"bal_rate": 100}
    env.template = {"type_acti": "PVE", "role_multipliers": {"HEAL": 3}}
    finish(data, "4 000 000")
    assert env.credited == {"1": 3_000_000, "2": 1_000_000}


def test_zero_pay_roles_are_counted_but_not_paid(env, monkeypatch):
    data = acti(monkeypatch, {"TANK": players(1), "DPS": players(2, 3)})
    env.settings = {"bal_rate": 100}
    env.template = {"type_acti": "PVE", "zero_pay_roles": ["TANK"]}
    finish(data, "1 000 000")
    assert env.credited == {"2": 500_000, "3": 500_000}
    assert env.counted == ["1", "2", "3"]   # présence comptée quand même


def test_scoot_paid_fixed_amount_before_split(env, monkeypatch):
    data = acti(monkeypatch, {"SCOOT": players(9), "DPS": players(1, 2)})
    env.settings = {"bal_rate": 100}
    inter = finish(data, "2 000 000", scoot="500 000")
    assert env.credited == {"9": 500_000, "1": 750_000, "2": 750_000}
    assert "Scoot (1 joueur(s))" in inter.replies[-1]


def test_scoot_exceeding_distributable_credits_nothing(env, monkeypatch):
    data = acti(monkeypatch, {"SCOOT": players(9, 8), "DPS": players(1)})
    env.settings = {"bal_rate": 100}
    inter = finish(data, "1 000 000", scoot="600 000")
    assert env.credited == {} and env.removed == []
    assert "dépasse le distribuable" in inter.replies[-1]
    assert ACTI in activites.activities   # l'acti reste ouverte


def test_only_zero_pay_roles_pays_nobody(env, monkeypatch):
    data = acti(monkeypatch, {"TANK": players(1)})
    env.template = {"type_acti": "PVE", "zero_pay_roles": ["TANK"]}
    finish(data, "1 000 000")
    assert env.credited == {} and env.errors == []   # pas de division par zéro


# ── Saisie invalide : rien n'est crédité ─────────────────────────────────────

@pytest.mark.parametrize("fields, error", [
    ({"recettes": "beaucoup"}, "recettes invalide"),
    ({"recettes": "-5"}, "recettes invalide"),
    ({"recettes": "1 000", "carte": "abc"}, "Coût de la carte invalide"),
    ({"recettes": "1 000", "carte": "2 000"}, "dépassent les recettes"),
    ({"recettes": "1 000", "pieces": "?"}, "pièces coffre invalide"),
])
def test_invalid_input_is_refused(env, monkeypatch, fields, error):
    data = acti(monkeypatch, {"DPS": players(1)})
    inter = finish(data, fields["recettes"], carte=fields.get("carte", ""), pieces=fields.get("pieces", ""))
    assert error in inter.replies[0]
    assert not inter.deferred and env.credited == {} and env.removed == []


def test_pvp_repairs_label(env, monkeypatch):
    env.template = {"type_acti": "PVP"}
    data = acti(monkeypatch, {"DPS": players(1)})
    inter = finish(data, "1 000", carte="x")
    assert "Prix des réparations invalide" in inter.replies[0]


def test_invalid_scoot_amount(env, monkeypatch):
    data = acti(monkeypatch, {"SCOOT": players(9), "DPS": players(1)})
    inter = finish(data, "1 000", scoot="")
    assert "Scoot invalide" in inter.replies[0] and env.credited == {}


# ── Anti double paiement ─────────────────────────────────────────────────────

def test_already_closed_activity_is_not_paid_twice(env, monkeypatch):
    data = acti(monkeypatch, {"DPS": players(1)})
    finish(data, "1 000 000")
    env.credited = {}
    inter = finish(data, "1 000 000")   # le modal resoumis après la clôture
    assert env.credited == {} and "déjà clôturée" in inter.replies[0]


def test_concurrent_finish_is_refused(env, monkeypatch):
    data = acti(monkeypatch, {"DPS": players(1)})
    monkeypatch.setattr(activites, "_finishing", {ACTI})   # une clôture déjà en cours
    inter = finish(data, "1 000 000")
    assert env.credited == {} and "déjà clôturée" in inter.replies[0]


def test_finishing_flag_released_after_error(env, monkeypatch):
    data = acti(monkeypatch, {"DPS": players(1)})

    async def boom(deltas, guild_id):
        raise RuntimeError("base indisponible")
    monkeypatch.setattr(activites.db, "increment_bal_batch", boom)
    inter = finish(data, "1 000 000")
    assert "Erreur FinActi" in inter.replies[-1] and len(env.errors) == 1
    assert ACTI not in activites._finishing and ACTI in activites.activities   # on peut réessayer
