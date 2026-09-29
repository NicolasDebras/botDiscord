"""Doubles légers pour discord.Member/Role — juste ce dont les tests ont besoin,
pas de dépendance à un vrai objet discord.py ni à une connexion Gateway."""
from types import SimpleNamespace


def fake_role(name: str = "", role_id: int = 0):
    return SimpleNamespace(name=name, id=role_id)


def fake_member(*, roles=(), administrator=False, user_id: int = 1, display_name: str = "Testeur"):
    return SimpleNamespace(
        id=user_id,
        display_name=display_name,
        roles=list(roles),
        guild_permissions=SimpleNamespace(administrator=administrator),
    )
