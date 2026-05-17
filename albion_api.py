"""
albion_api.py — Utilitaires pour l'API Albion Online (gameinfo).
Serveur EU : gameinfo-ams.albiononline.com
"""
import aiohttp

_BASE = "https://gameinfo-ams.albiononline.com/api/gameinfo"
_TIMEOUT = aiohttp.ClientTimeout(total=10)


def fmt_fame(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


async def fetch_albion_fame(pseudo: str) -> dict | None:
    """Retourne {'pve': int, 'pvp': int, 'name': str} ou None si introuvable."""
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        # 1. Recherche — endpoint /search (pas /players/search)
        async with session.get(f"{_BASE}/search", params={"q": pseudo}) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        players = data.get("players") or []
        if not players:
            return None

        match = next((p for p in players if p["Name"].lower() == pseudo.lower()), players[0])

        # 2. Détails joueur — /players/{id} (pas /players/{id}/stats)
        async with session.get(f"{_BASE}/players/{match['Id']}") as resp:
            if resp.status != 200:
                return None
            player = await resp.json()

    lifetime = player.get("LifetimeStatistics") or {}
    pve = lifetime.get("PvE") or {}
    return {
        "pve":  pve.get("Total", 0),
        "pvp":  player.get("KillFame", 0),
        "name": match["Name"],
    }
