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
    assert needs_validation(acti, member(CALLER, "Caller"), already_in=False)
    assert needs_validation(acti, fake_member(user_id=CALLER, administrator=True), already_in=False)
    assert not needs_validation(acti, member(CREATOR), already_in=False)
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


def test_only_creator_registers_directly(acti):
    client = FakeClient()
    register(member(CREATOR), client, "TANK")
    assert [e[0] for e in acti["slots"]["TANK"]] == [CREATOR]
    assert acti["pending"] == [] and client.dms == []


def test_callers_and_gm_also_need_validation(acti):
    client = FakeClient()
    register(member(CALLER, "Caller"), client, "DPS")
    register(fake_member(user_id=40, display_name="GM", roles=[fake_role("Membre")], administrator=True), client, "TANK")
    assert acti["slots"]["DPS"] == [] and acti["slots"]["TANK"] == []
    assert sorted(p["uid"] for p in acti["pending"]) == [CALLER, 40]
    assert len(client.dms) == 2


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


def test_embed_groups_same_role_slots_under_one_category(acti, monkeypatch):
    tpl = {
        "type_acti": "PVP",
        "pf_1": {"TANK": 1, "TANK · Tank": 1, "DPS": 2},
        "weapon": {"TANK": "ROLE DE TEST", "TANK · Tank": "Tank"},
    }
    monkeypatch.setattr(activites, "load_all_templates", lambda gid: {"T": tpl})
    acti["slots"] = {"TANK": [(PLAYER, "Bob", "ROLE DE TEST")], "TANK · Tank": [], "DPS": []}
    fields = [(f.name, f.value) for f in build_embed(acti).fields]
    assert fields[0] == ("🛡️ TANK  [1/2]", f"**ROLE DE TEST**\n　-<@{PLAYER}>\n**Tank**\n　-—")
    assert fields[1] == ("⚔️ DPS  [0/2]", "*Personne*")


def test_embed_grouped_slot_without_spec_gets_its_label(acti, monkeypatch):
    tpl = {"type_acti": "PVE", "pf_1": {"TANK · Main": 1, "TANK · Off": 1}}
    monkeypatch.setattr(activites, "load_all_templates", lambda gid: {"T": tpl})
    acti["slots"] = {"TANK · Main": [], "TANK · Off": [(PLAYER, "Bob", "")]}
    name, value = (embed := build_embed(acti)).fields[0].name, embed.fields[0].value
    assert name == "🛡️ TANK  [1/2]"
    assert value == f"**Main**\n　-—\n**Off**\n　-<@{PLAYER}>"


def test_embed_bare_first_site_line_shows_its_build_name(acti, monkeypatch):
    # Compo du site : la 1re ligne du rôle garde la clé « TANK », son nom de build est le hint.
    tpl = {"type_acti": "PVE", "pf_1": {"TANK": 1, "TANK · Def tank": 1},
           "weapon": {"TANK": "Main tank", "TANK · Def tank": "Def tank"},
           "builds": {"TANK": 12, "TANK · Def tank": 13}}
    monkeypatch.setattr(activites, "load_all_templates", lambda gid: {"T": tpl})
    acti["slots"] = {"TANK": [], "TANK · Def tank": []}
    value = build_embed(acti).fields[0].value
    assert value.startswith("**Main tank**")
    assert "**TANK**" not in value


def test_embed_shows_custom_shares(acti, monkeypatch):
    tpl = {"type_acti": "PVE", "pf_1": {"TANK": 1, "TANK · Off": 1, "DPS": 2},
           "role_multipliers": {"TANK": 2, "TANK · Off": 1, "DPS": 1.5}}
    monkeypatch.setattr(activites, "load_all_templates", lambda gid: {"T": tpl})
    acti["slots"] = {"TANK": [], "TANK · Off": [], "DPS": []}
    fields = [(f.name, f.value) for f in build_embed(acti).fields]
    tank = fields[0][1].split("\n")
    assert tank[0] == "**TANK**  ·  💰 2 parts"                # sous-bloc à 2 parts
    assert "**Off**" in tank and "💰" not in fields[0][1].split("**Off**")[1]
    assert fields[1][0] == "⚔️ DPS  [0/2]  ·  💰 1,5 part"     # rôle seul : dans l'en-tête


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


# ── Fill : en attente, le caller attribue le rôle ────────────────────────────

def fill(user, client):
    inter = interaction(user, client)
    asyncio.run(activites._request_fill(inter, ACTI))
    return inter


def test_fill_goes_to_pending_and_dms_creator_without_accept_button(acti):
    acti["validation"] = False
    client = FakeClient()
    inter = fill(member(PLAYER, "Membre", name="Bob"), client)

    assert all(v == [] for v in acti["slots"].values())
    [req] = acti["pending"]
    assert req["uid"] == PLAYER and req["role"] == activites.FILL
    [(to, _content, kwargs)] = client.dms
    assert to == CREATOR and "Fill" in kwargs["embed"].title
    assert [c.custom_id for c in kwargs["view"].children] == [f"actival:{ACTI}:{PLAYER}:{req['rid']}:r"]
    assert "Fill" in inter.replies[0]


def test_fill_refused_when_activity_full(acti):
    acti["max_players"] = 1
    acti["slots"]["TANK"] = [(99, "X", "")]
    inter = fill(member(PLAYER, "Membre"), FakeClient())
    assert acti["pending"] == [] and "complète" in inter.replies[0]


def test_fill_needs_a_role_to_be_accepted(acti):
    client = FakeClient()
    fill(member(PLAYER, "Membre"), client)
    client.dms.clear()
    inter = decide(member(CALLER, "Caller"), client, PLAYER, None, True, from_dm=False)
    assert len(acti["pending"]) == 1 and client.dms == []
    assert "choisis le rôle" in inter.replies[0]


def test_caller_places_fill_on_a_free_role_and_player_gets_dm(acti):
    client = FakeClient()
    fill(member(PLAYER, "Membre", name="Bob"), client)
    client.dms.clear()
    inter = interaction(member(CALLER, "Caller", name="Cal"), client)
    asyncio.run(activites._decide(inter, ACTI, PLAYER, None, True, role="DPS"))

    assert acti["slots"]["DPS"] == [(PLAYER, "Bob", "")] and acti["pending"] == []
    [(to, content, _)] = client.dms
    assert to == PLAYER and "t'a placé en **DPS**" in content


def test_caller_cannot_place_fill_on_full_role(acti):
    client = FakeClient()
    fill(member(PLAYER, "Membre"), client)
    acti["slots"]["TANK"] = [(99, "X", "")]
    inter = interaction(member(CALLER, "Caller"), client)
    asyncio.run(activites._decide(inter, ACTI, PLAYER, None, True, role="TANK"))
    assert "Plus de place" in inter.replies[0] and len(acti["pending"]) == 1


def test_assignable_roles_skips_full_roles_and_names_builds(acti):
    acti["slots"]["TANK"] = [(99, "X", "")]
    assert activites.assignable_roles(acti, TEMPLATE) == [("DPS", "DPS")]
    tpl = {"type_acti": "PVE", "pf_1": {"HEAL": 1, "HEAL · Off": 1}, "weapon": {"HEAL": "Main heal"},
           "builds": {"HEAL": 5, "HEAL · Off": 6}}
    assert activites.assignable_roles({"slots": {}}, tpl) == [("HEAL", "HEAL — Main heal"), ("HEAL · Off", "HEAL · Off")]
    assert [k for k, _ in activites.assignable_roles({"slots": {}}, {})] == list(activites.ROLES)


def test_assigned_spec():
    req = {"role": "TANK", "spec": "Tank Masse"}
    tpl = {"pf_1": {"HEAL": 1, "DPS": 1}, "weapon": {"HEAL": "Main heal", "DPS": "Arc"}, "builds": {"HEAL": 5}}
    assert activites.assigned_spec(tpl, req, "TANK") == "Tank Masse"     # rôle demandé : spé conservée
    assert activites.assigned_spec(tpl, req, "HEAL") == "Main heal"      # build imposé
    assert activites.assigned_spec(tpl, req, "DPS") == ""                # liste d'armes : pas de spé


def test_embed_and_view_show_fill_waiting_without_validation(acti):
    acti["validation"] = False
    acti["pending"] = [{"uid": PLAYER, "name": "Bob", "role": "Fill", "spec": "", "rid": "x"}]
    fields = {f.name: f.value for f in build_embed(acti).fields}
    assert fields["⏳ En attente d'un rôle  [1]"] == f"<@{PLAYER}> — 🔀 Fill (rôle à attribuer)"

    async def build():
        return activites.ActivityView(ACTI)
    assert any(isinstance(c, PendingButton) for c in asyncio.run(build()).children)


def test_pending_review_view_offers_role_picker():
    async def build():
        return activites.PendingReviewView(ACTI, [{"uid": PLAYER, "name": "Bob", "role": "Fill", "spec": "", "rid": "x"}],
                                           [("TANK", "TANK"), ("DPS", "DPS")])
    view = asyncio.run(build())
    assert view.select.options[0].label == "Bob — 🔀 Fill"
    assert [o.value for o in view.role_select.options] == ["TANK", "DPS"]


def test_embed_still_shows_players_of_a_line_removed_from_the_compo(acti, monkeypatch):
    """Compo modifiée sur le site après les inscriptions (lignes Crystal Reaper et Weeping fusionnées
    en une ligne « au choix ») : les inscrits de l'ancienne ligne restent visibles dans leur rôle."""
    tpl = {"type_acti": "PVP", "pf_1": {"DPS": 1, "DPS · Crystal": 2},
           "weapon": {"DPS": "SC", "DPS · Crystal": "Crystal / Weeping"},
           "builds": {"DPS": 1, "DPS · Crystal": [2, 3]}}
    monkeypatch.setattr(activites, "load_all_templates", lambda gid: {"T": tpl})
    acti["slots"] = {"DPS": [(PLAYER, "Bob", "SC")], "DPS · Crystal": [],
                     "DPS · Weeping": [(CALLER, "Cal", "Weeping"), (CREATOR, "Cre", "Weeping")]}
    fields = [(f.name, f.value) for f in build_embed(acti).fields]
    name, value = fields[0]
    assert name == "⚔️ DPS  [3/5]"                          # 2 places prises par l'ancienne ligne
    assert f"<@{CALLER}>" in value and f"<@{CREATOR}>" in value
    assert "**Weeping**" in value
