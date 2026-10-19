"""
albion_api.py — Utilitaires pour l'API Albion Online (gameinfo).
Serveur EU : gameinfo-ams.albiononline.com
"""
import asyncio

import aiohttp

_BASE = "https://gameinfo-ams.albiononline.com/api/gameinfo"
_TIMEOUT = aiohttp.ClientTimeout(total=10)
_RETRY_DELAYS = (2, 5)  # secondes entre les essais (API souvent en 429 / 5xx sur les gros lots)


class AlbionApiError(Exception):
    """API indisponible (erreur réseau, 429, 5xx…) après les essais — distinct de « joueur introuvable »."""


async def _get_json(session: aiohttp.ClientSession, url: str, params: dict | None = None) -> dict | None:
    """GET JSON avec nouveaux essais sur erreur passagère. None = 404 ; AlbionApiError si l'API ne répond pas."""
    for delay in (*_RETRY_DELAYS, None):
        try:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
                if resp.status == 404:
                    return None
                error = AlbionApiError(f"HTTP {resp.status}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            error = AlbionApiError(str(e) or type(e).__name__)
        if delay is None:
            raise error
        await asyncio.sleep(delay)


def fmt_fame(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def find_exact_player(players: list[dict], pseudo: str) -> dict | None:
    """Joueur dont le nom correspond exactement à `pseudo` (casse ignorée), sinon None."""
    wanted = pseudo.strip().lower()
    return next((p for p in players if p.get("Name", "").lower() == wanted), None)


def same_guild(a: str | None, b: str | None) -> bool:
    """Compare deux noms de guilde (casse et espaces de bord ignorés)."""
    return (a or "").strip().lower() == (b or "").strip().lower()


def majority_guild(guilds) -> str | None:
    """Guilde la plus représentée (casse ignorée, « sans guilde » exclu), sinon None."""
    counts: dict[str, list] = {}
    for g in guilds:
        g = (g or "").strip()
        if g:
            entry = counts.setdefault(g.lower(), [0, g])
            entry[0] += 1
    if not counts:
        return None
    return max(counts.values(), key=lambda e: e[0])[1]


_NICK_MAX = 32  # limite Discord


TAG_LEN_DEFAULT = 3   # « [Lil] Pseudo » : 3 premiers caractères de la guilde (réglable via /config)
TAG_LEN_MAX     = 15


def tagged_nick(guild: str | None, pseudo: str, tag_len: int = TAG_LEN_DEFAULT) -> str:
    """« [Gui] Pseudo » (`tag_len` premiers caractères de la guilde), pseudo seul s'il n'y a pas la place."""
    pseudo = pseudo[:_NICK_MAX]
    tag    = (guild or "").strip()[:tag_len].strip()
    if not tag or len(pseudo) + len(tag) + 3 > _NICK_MAX:
        return pseudo
    return f"[{tag}] {pseudo}"


async def fetch_albion_fame(pseudo: str) -> dict | None:
    """Retourne {'pve': int, 'pvp': int, 'name': str, 'guild': str} ou None si introuvable.
    Lève AlbionApiError si l'API ne répond pas (à ne pas confondre avec un pseudo inexistant)."""
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        # 1. Recherche — endpoint /search (pas /players/search)
        data = await _get_json(session, f"{_BASE}/search", {"q": pseudo})
        if not data:
            return None

        players = data.get("players") or []
        if not players:
            return None

        # Pseudo exact uniquement (casse ignorée) : pas de repli sur le premier résultat,
        # sinon « Naej » pourrait être enregistré sous le pseudo d'un autre joueur.
        match = find_exact_player(players, pseudo)
        if match is None:
            return None

        # 2. Détails joueur — /players/{id} (pas /players/{id}/stats)
        player = await _get_json(session, f"{_BASE}/players/{match['Id']}")
        if not player:
            return None

    lifetime = player.get("LifetimeStatistics") or {}
    pve = lifetime.get("PvE") or {}
    return {
        "pve":  pve.get("Total", 0),
        "pvp":  player.get("KillFame", 0),
        "name": match["Name"],
        "guild": player.get("GuildName") or "",  # "" = sans guilde
    }
