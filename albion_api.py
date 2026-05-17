"""
albion_api.py — Utilitaires pour l'API Albion Online (gameinfo).
Serveur EU : gameinfo.albiononline.com (serveur principal, joueurs EU inclus)
"""
import aiohttp

_BASE = "https://gameinfo.albiononline.com/api/gameinfo"
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
        async with session.get(f"{_BASE}/players/search", params={"q": pseudo}) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        players = data.get("players") or []
        if not players:
            return None

        match = next((p for p in players if p["Name"].lower() == pseudo.lower()), players[0])

        async with session.get(f"{_BASE}/players/{match['Id']}/stats") as resp:
            if resp.status != 200:
                return None
            stats = await resp.json()

    lifetime = stats.get("LifetimeStatistics") or {}
    pve = lifetime.get("PvE") or {}
    pvp = lifetime.get("PvP") or {}
    return {
        "pve":  pve.get("Total", 0),
        "pvp":  pvp.get("KillFame", pvp.get("Total", 0)),
        "name": match["Name"],
    }
