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
    """Retourne {'pve': int, 'pvp': int, 'name': str, 'guild': str} ou None si introuvable."""
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        # 1. Recherche — endpoint /search (pas /players/search)
        async with session.get(f"{_BASE}/search", params={"q": pseudo}) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        players = data.get("players") or []
        if not players:
            return None

        # Pseudo exact uniquement (casse ignorée) : pas de repli sur le premier résultat,
        # sinon « Naej » pourrait être enregistré sous le pseudo d'un autre joueur.
        match = find_exact_player(players, pseudo)
        if match is None:
            return None

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
        "guild": player.get("GuildName") or "",  # "" = sans guilde
    }
