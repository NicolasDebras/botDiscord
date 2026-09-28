"""
web/auth.py — Connexion Discord OAuth2 (scope "identify" uniquement) + session
signée par cookie (pas de stockage serveur). Les vérifications d'appartenance
à un serveur et de rôle staff se font directement via le cache live du bot
(même process), pas via l'API Discord.
"""
import os

import aiohttp
import discord
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from fastapi import Request, HTTPException

import db

DISCORD_CLIENT_ID     = os.environ.get("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI  = os.environ.get("DISCORD_REDIRECT_URI", "")
SESSION_SECRET         = os.environ.get("WEB_SESSION_SECRET", "")

_SESSION_COOKIE = "session"
_SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 jours

_serializer = URLSafeTimedSerializer(SESSION_SECRET or "insecure-dev-secret")


def build_authorize_url() -> str:
    return (
        "https://discord.com/oauth2/authorize"
        f"?client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={DISCORD_REDIRECT_URI}"
        "&response_type=code"
        "&scope=identify"
    )


async def exchange_code(code: str) -> str:
    """Échange le code OAuth2 contre un access_token."""
    data = {
        "client_id":     DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  DISCORD_REDIRECT_URI,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post("https://discord.com/api/oauth2/token", data=data) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=400, detail="Échec de l'authentification Discord.")
            payload = await resp.json()
    return payload["access_token"]


async def fetch_discord_user(access_token: str) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get("https://discord.com/api/users/@me", headers=headers) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=400, detail="Impossible de récupérer le profil Discord.")
            return await resp.json()


def create_session_cookie(user: dict) -> str:
    if user.get("avatar"):
        avatar_url = f"https://cdn.discordapp.com/avatars/{user['id']}/{user['avatar']}.png"
    else:
        avatar_url = "https://cdn.discordapp.com/embed/avatars/0.png"
    return _serializer.dumps({
        "id":         user["id"],
        "username":   user.get("global_name") or user["username"],
        "avatar_url": avatar_url,
    })


def read_session(request: Request) -> dict | None:
    token = request.cookies.get(_SESSION_COOKIE)
    if not token:
        return None
    try:
        return _serializer.loads(token, max_age=_SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def set_session_cookie(response, user: dict) -> None:
    response.set_cookie(
        _SESSION_COOKIE, create_session_cookie(user),
        max_age=_SESSION_MAX_AGE, httponly=True, samesite="lax",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(_SESSION_COOKIE)


def require_login(request: Request) -> dict:
    user = read_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Connexion requise.")
    return user


# ── HELPERS : cache live du bot (même process) ─────────────────────────────────

async def get_member(bot: discord.Client, guild_id: int, user_id: int) -> discord.Member | None:
    guild = bot.get_guild(guild_id)
    if not guild:
        return None
    member = guild.get_member(user_id)
    if member is None and not guild.chunked:
        await guild.chunk()
        member = guild.get_member(user_id)
    return member


def shared_guilds(bot: discord.Client, user_id: int) -> list[discord.Guild]:
    """Serveurs où le bot est présent ET où l'utilisateur est déjà en cache membre.
    Ne force pas le chunk de chaque serveur (coûteux) — un serveur pas encore
    chunké n'apparaîtra pas tant qu'une page qui le chunk n'a pas été visitée."""
    return [g for g in bot.guilds if g.get_member(user_id) is not None]


async def is_staff(bot: discord.Client, guild_id: int, user_id: int) -> bool:
    member = await get_member(bot, guild_id, user_id)
    if not member:
        return False
    if member.guild_permissions.administrator:
        return True
    staff_role_id = await db.get_web_staff_role(guild_id)
    if not staff_role_id:
        return False
    return any(r.id == staff_role_id for r in member.roles)


async def require_membership(request: Request, bot: discord.Client, guild_id: int) -> dict:
    user = require_login(request)
    member = await get_member(bot, guild_id, int(user["id"]))
    if not member:
        raise HTTPException(status_code=403, detail="Tu n'es pas membre de ce serveur.")
    return user


async def require_staff(request: Request, bot: discord.Client, guild_id: int) -> dict:
    user = require_login(request)
    if not await is_staff(bot, guild_id, int(user["id"])):
        raise HTTPException(status_code=403, detail="Réservé au staff du site web (configuré via /config).")
    return user
