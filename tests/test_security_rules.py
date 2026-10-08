"""Règles de sécurité pures : rôles distribuables automatiquement, cibles de /kick, serveurs autorisés."""
from types import SimpleNamespace

from config import ADMIN_ROLE_NAME, GM_ROLE_NAME, MEMBRE_ROLE_NAME, parse_guild_ids
from Service.utils import kick_refusal, role_grant_refusal

OWNER_ID = 1


def role(name="Joueur", role_id=10, position=1, default=False, managed=False, **perms):
    return SimpleNamespace(
        name=name, id=role_id, position=position, managed=managed,
        is_default=lambda: default, permissions=SimpleNamespace(**perms),
    )


def member(user_id=2, top=5, roles=(), administrator=False, bot=False):
    return SimpleNamespace(
        id=user_id, bot=bot, roles=list(roles), top_role=SimpleNamespace(position=top),
        guild=SimpleNamespace(owner_id=OWNER_ID),
        guild_permissions=SimpleNamespace(administrator=administrator),
    )


# ── role_grant_refusal ───────────────────────────────────────────────────────

def test_plain_role_below_actor_is_allowed():
    assert role_grant_refusal(role(position=2), member(top=5)) is None


def test_everyone_and_managed_roles_refused():
    assert role_grant_refusal(role(default=True)) is not None
    assert role_grant_refusal(role(managed=True)) is not None


def test_staff_role_names_refused():
    assert role_grant_refusal(role(name=GM_ROLE_NAME)) is not None
    assert role_grant_refusal(role(name=ADMIN_ROLE_NAME)) is not None


def test_extra_protected_names_and_ids():
    assert role_grant_refusal(role(name=MEMBRE_ROLE_NAME), protected_names=(MEMBRE_ROLE_NAME,)) is not None
    assert role_grant_refusal(role(role_id=77), protected_ids=(77,)) is not None


def test_dangerous_permissions_refused():
    for perm in ("administrator", "manage_roles", "manage_guild", "kick_members", "mention_everyone"):
        assert role_grant_refusal(role(**{perm: True})) is not None, perm


def test_role_at_or_above_actor_refused_unless_owner():
    assert role_grant_refusal(role(position=5), member(top=5)) is not None
    assert role_grant_refusal(role(position=9), member(user_id=OWNER_ID, top=5)) is None


# ── kick_refusal ─────────────────────────────────────────────────────────────

def test_recruiter_can_kick_lower_member():
    assert kick_refusal(member(top=5), member(user_id=3, top=2)) is None


def test_cannot_kick_equal_or_higher_role():
    assert kick_refusal(member(top=5), member(user_id=3, top=5)) is not None
    assert kick_refusal(member(top=5), member(user_id=3, top=8)) is not None


def test_cannot_kick_officer_gm_owner_or_bot():
    actor = member(user_id=OWNER_ID, top=99)
    assert kick_refusal(actor, member(user_id=3, top=1, roles=[role(name=ADMIN_ROLE_NAME)])) is not None
    assert kick_refusal(actor, member(user_id=3, top=1, roles=[role(name=GM_ROLE_NAME)])) is not None
    assert kick_refusal(actor, member(user_id=3, top=1, administrator=True)) is not None
    assert kick_refusal(member(top=99), member(user_id=OWNER_ID, top=1)) is not None
    assert kick_refusal(actor, member(user_id=3, top=1, bot=True)) is not None


# ── parse_guild_ids ──────────────────────────────────────────────────────────

def test_parse_guild_ids():
    assert parse_guild_ids("") == frozenset()
    assert parse_guild_ids(" 123, 456 ;789,") == {123, 456, 789}
