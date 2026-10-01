"""/acti validation:True — demandes d'inscription validées par le caller (MP + bouton « En attente »).
Aucun appel réseau ni base : Discord, la base et les templates sont remplacés par des faux."""
import asyncio
import re
from types import SimpleNamespace

import discord
import pytest

from Service import activites
from Service.activites import (
    PendingButton, ValidationButton, build_embed, can_validate, needs_validation, registration_error,
)
from tests.fakes import fake_member, fake_role

ACTI = 555
CREATOR = 10
PLAYER = 20
CALLER = 30
GUILD = 111

TEMPLATE = {"type_acti": "PVE", "pf_1": {"TANK": 1, "DPS": 2}}


# ── Faux Discord ─────────────────────────────────────────────────────────────

class FakeResponse:
    def __init__(self, inter):
        self._inter, self._done = inter, False

    def is_done(self):
        return self._done

    async def defer(self, **kwargs):
        self._done = True

    async def send_message(self, content=None, **kwargs):
        self._done = True
        self._inter.replies.append(content)

    async def send_modal(self, modal):
        self._done = True


class FakeDMUser:
    def __init__(self, uid, client, closed=False):
        self.id, self.client, self.closed = uid, client, closed

    async def send(self, content=None, **kwargs):
        if self.closed:
            raise discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "DM fermés")
        self.client.dms.append((self.id, content, kwargs))


class FakeClient:
    def __init__(self, closed=()):
        self.dms, self.closed = [], set(closed)
        self.members = {}

    def get_user(self, uid):
        return FakeDMUser(uid, self, uid in self.closed)

    def get_guild(self, gid):
        return SimpleNamespace(get_member=lambda uid: self.members.get(uid))

    def get_channel(self, cid):
        return None


def interaction(user, client, message=None):
    inter = SimpleNamespace(user=user, client=client, message=message, replies=[])
    inter.response = FakeResponse(inter)

    async def followup_send(content=None, **kwargs):
        inter.replies.append(content)
    inter.followup = SimpleNamespace(send=followup_send)
    return inter


def member(uid, *roles, name=None):
    return fake_member(user_id=uid, display_name=name or f"J{uid}", roles=[fake_role(r) for r in roles])


@pytest.fixture
def acti(monkeypatch):
    data = {
        "creator": "Chef", "creator_id": CREATOR, "created_at": None, "template": "T", "max_players": 3,
        "bal": True, "slots": {"TANK": [], "DPS": []}, "channel_id": 1, "guild_id": GUILD,
        "waitlist": [], "validation": True, "pending": [],
    }
    monkeypatch.setitem(activites.activities, ACTI, data)
    monkeypatch.setattr(activites, "load_all_templates", lambda gid: {"T": TEMPLATE})

    async def noop(*a, **k):
        return None
    monkeypatch.setattr(activites, "save_activities", noop)
    monkeypatch.setattr(activites, "_refresh_activity_message", noop)
    monkeypatch.setattr(activites, "log_error", noop)
    return data


def register(user, client, role="TANK", spec=""):
    inter = interaction(user, client)
    asyncio.run(activites._register_player(inter, ACTI, role, spec))
    return inter


def decide(user, client, uid, rid, accept, from_dm=True, message=None):
    inter = interaction(user, client, message)
    asyncio.run(activites._decide(inter, ACTI, uid, rid, accept, from_dm=from_dm))
    return inter


# ── Règles pures ─────────────────────────────────────────────────────────────

def test_registration_error_role_full_and_ok(acti):
    acti["slots"]["TANK"] = [(1, "A", "")]
    assert "Plus de place en **TANK**" in registration_error(acti, TEMPLATE, 2, "TANK", "")
    assert registration_error(acti, TEMPLATE, 1, "TANK", "") is None   # déjà dans le rôle
    assert registration_error(acti, TEMPLATE, 2, "DPS", "") is None
    assert registration_error(acti, {}, 2, "TANK", "") is None         # acti libre : pas de limite


def test_registration_error_weapon_sub_limit(acti):
    tdata = {"type_acti": "PVP", "pf_1": {"DPS": 5}, "weapon": {"DPS": "Arc (×1) · Épée (×2)"}}
    acti["slots"]["DPS"] = [(1, "A", "Arc (800)")]
    assert "Plus de place pour **Arc**" in registration_error(acti, tdata, 2, "DPS", "Arc (700)")
    assert registration_error(acti, tdata, 2, "DPS", "Épée (700)") is None


def test_who_can_validate(acti):
    assert can_validate(member(CREATOR), acti)
    assert can_validate(member(CALLER, "Caller"), acti)
    assert not can_validate(member(PLAYER, "Membre"), acti)
    assert not can_validate(SimpleNamespace(id=PLAYER, display_name="x"), acti)   # utilisateur sans rôles (MP)


def test_needs_validation(acti):
    assert needs_validation(acti, member(PLAYER, "Membre"), already_in=False)
    assert not needs_validation(acti, member(PLAYER, "Membre"), already_in=True)    # changement de rôle
    assert not needs_validation(acti, member(CALLER, "Caller"), already_in=False)
    assert not needs_validation({**acti, "validation": False}, member(PLAYER), already_in=False)


# ── Demande d'inscription ────────────────────────────────────────────────────

def test_registration_goes_to_pending_and_dms_creator(acti):
    client = FakeClient()
    inter = register(member(PLAYER, "Membre", name="Bob"), client, "TANK", "Tank Masse")

    assert acti["slots"]["TANK"] == []
    [req] = acti["pending"]
    assert req["uid"] == PLAYER and req["role"] == "TANK" and req["spec"] == "Tank Masse"
    [(to, _content, kwargs)] = client.dms
    assert to == CREATOR
    assert "Bob" in kwargs["embed"].description
    ids = [c.custom_id for c in kwargs["view"].children]
    assert ids == [f"actival:{ACTI}:{PLAYER}:{req['rid']}:a", f"actival:{ACTI}:{PLAYER}:{req['rid']}:r"]
    assert "Demande d'inscription" in inter.replies[0]


def test_new_request_replaces_previous_one(acti):
    client = FakeClient()
    register(member(PLAYER, "Membre"), client, "TANK")
    first = acti["pending"][0]["rid"]
    register(member(PLAYER, "Membre"), client, "DPS")
    [req] = acti["pending"]
    assert req["role"] == "DPS" and req["rid"] != first


def test_creator_and_callers_register_directly(acti):
    client = FakeClient()
    register(member(CREATOR), client, "TANK")
    register(member(CALLER, "Caller"), client, "DPS")
    assert [e[0] for e in acti["slots"]["TANK"]] == [CREATOR]
    assert [e[0] for e in acti["slots"]["DPS"]] == [CALLER]
    assert acti["pending"] == [] and client.dms == []


def test_accepted_player_changes_role_without_new_validation(acti):
    acti["slots"]["TANK"] = [(PLAYER, "Bob", "")]
    register(member(PLAYER, "Membre"), FakeClient(), "DPS")
    assert acti["slots"]["TANK"] == [] and [e[0] for e in acti["slots"]["DPS"]] == [PLAYER]
    assert acti["pending"] == []


def test_without_validation_nothing_changes(acti):
    acti["validation"] = False
    client = FakeClient()
    register(member(PLAYER, "Membre"), client, "TANK")
    assert [e[0] for e in acti["slots"]["TANK"]] == [PLAYER]
    assert acti["pending"] == [] and client.dms == []


def test_full_role_is_refused_before_any_request(acti):
    acti["slots"]["TANK"] = [(99, "X", "")]
    client = FakeClient()
    inter = register(member(PLAYER, "Membre"), client, "TANK")
    assert acti["pending"] == [] and client.dms == []
    assert "Plus de place" in inter.replies[0]


def test_creator_dms_closed_keeps_request(acti):
    client = FakeClient(closed={CREATOR})
    inter = register(member(PLAYER, "Membre"), client, "TANK")
    assert len(acti["pending"]) == 1
    assert "depuis l'activité" in inter.replies[0]


# ── Accepter / refuser ───────────────────────────────────────────────────────

def _pending(acti, client, role="TANK"):
    register(member(PLAYER, "Membre", name="Bob"), client, role)
    client.dms.clear()
    return acti["pending"][0]["rid"]


def test_accept_from_dm(acti):
    client = FakeClient()
    client.members[CREATOR] = member(CREATOR)
    rid = _pending(acti, client)
    edited = []

    async def edit(**kwargs):
        edited.append(kwargs)
    decide(SimpleNamespace(id=CREATOR, display_name="Chef"), client, PLAYER, rid, True,
           message=SimpleNamespace(edit=edit))

    assert [e[0] for e in acti["slots"]["TANK"]] == [PLAYER]
    assert acti["pending"] == []
    [(to, content, _)] = client.dms
    assert to == PLAYER and "validée" in content
    assert edited and edited[0]["view"] is None and "Acceptée" in edited[0]["content"]


def test_refuse(acti):
    client = FakeClient()
    rid = _pending(acti, client)
    inter = decide(member(CREATOR), client, PLAYER, rid, False, from_dm=False)
    assert acti["pending"] == [] and acti["slots"]["TANK"] == []
    assert "refusée" in client.dms[0][1]
    assert "Refusée" in inter.replies[0]


def test_accept_when_role_became_full_keeps_request(acti):
    client = FakeClient()
    rid = _pending(acti, client)
    acti["slots"]["TANK"] = [(99, "X", "")]
    inter = decide(member(CREATOR), client, PLAYER, rid, True)
    assert len(acti["pending"]) == 1 and client.dms == []
    assert "reste en attente" in inter.replies[0]


def test_accept_when_activity_full_keeps_request(acti):
    client = FakeClient()
    rid = _pending(acti, client, role="DPS")
    acti["slots"]["TANK"] = [(97, "X", "")]
    acti["slots"]["DPS"] = [(98, "Y", "")]
    acti["max_players"] = 2
    inter = decide(member(CREATOR), client, PLAYER, rid, True)
    assert "complète" in inter.replies[0] and len(acti["pending"]) == 1


def test_stale_request_id(acti):
    client = FakeClient()
    _pending(acti, client)
    inter = decide(member(CREATOR), client, PLAYER, "deadbe", True)
    assert "obsolète" in inter.replies[0]
    assert len(acti["pending"]) == 1


def test_caller_can_validate_without_request_id(acti):
    client = FakeClient()
    _pending(acti, client)
    decide(member(CALLER, "Caller"), client, PLAYER, None, True, from_dm=False)
    assert [e[0] for e in acti["slots"]["TANK"]] == [PLAYER]


def test_simple_member_cannot_validate(acti):
    client = FakeClient()
    rid = _pending(acti, client)
    inter = decide(member(40, "Membre"), client, PLAYER, rid, True, from_dm=False)
    assert "Seuls le créateur" in inter.replies[0]
    assert len(acti["pending"]) == 1


def test_validator_in_dm_is_resolved_as_guild_member(acti):
    """En MP, interaction.user n'a pas de rôles : on récupère le membre du serveur."""
    client = FakeClient()
    client.members[CALLER] = member(CALLER, "Caller")
    _pending(acti, client)
    decide(SimpleNamespace(id=CALLER, display_name="Cal"), client, PLAYER, None, True, from_dm=False)
    assert [e[0] for e in acti["slots"]["TANK"]] == [PLAYER]


def test_unknown_activity(acti):
    inter = interaction(member(CREATOR), FakeClient())
    asyncio.run(activites._decide(inter, 999, PLAYER, None, True))
    assert "introuvable" in inter.replies[0]


# ── Composants / embed ───────────────────────────────────────────────────────

def test_validation_button_custom_id_roundtrip():
    btn = ValidationButton(ACTI, PLAYER, "a1b2c3", False)
    match = re.fullmatch(ValidationButton.__discord_ui_compiled_template__, btn.item.custom_id)
    parsed = asyncio.run(ValidationButton.from_custom_id(None, btn.item, match))
    assert (parsed.activity_id, parsed.user_id, parsed.rid, parsed.accept) == (ACTI, PLAYER, "a1b2c3", False)


def test_embed_shows_pending_and_validation_line(acti):
    acti["pending"] = [{"uid": PLAYER, "name": "Bob", "role": "PF2:HEAL", "spec": "Heal Traque", "rid": "x"}]
    embed = build_embed(acti)
    fields = {f.name: f.value for f in embed.fields}
    pending = next(v for k, v in fields.items() if k.startswith("⏳ En attente"))
    assert f"<@{PLAYER}> — HEAL PF2  (Heal Traque)" in pending
    assert any("Inscriptions sur validation" in v for v in fields.values())


def test_activity_view_has_pending_button_only_with_validation(acti):
    async def build():
        return activites.ActivityView(ACTI)
    view = asyncio.run(build())
    assert any(isinstance(c, PendingButton) for c in view.children)
    acti["validation"] = False
    view = asyncio.run(build())
    assert not any(isinstance(c, PendingButton) for c in view.children)


def test_leave_removes_pending_request(acti):
    acti["pending"] = [{"uid": PLAYER, "name": "Bob", "role": "TANK", "spec": "", "rid": "x"}]
    inter = interaction(member(PLAYER, "Membre"), FakeClient())

    async def edit(**kwargs):
        return None
    inter.message = SimpleNamespace(edit=edit)
    asyncio.run(activites.LeaveButton(ACTI).callback(inter))
    assert acti["pending"] == []
