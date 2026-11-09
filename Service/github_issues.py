"""
Issues GitHub des erreurs du bot : une issue à la 1ʳᵉ occurrence d'un bug (commande + type
d'erreur), puis plus rien tant qu'elle est ouverte — GitHub prévient le propriétaire (mail,
appli mobile). Un commit « Fixes #N » ferme l'issue : au démarrage suivant (= le déploiement
du correctif) puis toutes les heures, ses erreurs passent en corrigées (error_log.is_fixed).
Une nouvelle occurrence après la fermeture ouvre une nouvelle issue (réapparition).

Désactivé sans GITHUB_TOKEN / GITHUB_REPO. Ne jamais appeler log_error ici : un échec de
l'API GitHub enregistrerait une erreur… qui rappellerait GitHub.
"""
import asyncio
from datetime import datetime, UTC

import aiohttp
from discord.ext import commands, tasks

import config
import db

_API           = "https://api.github.com"
_TIMEOUT       = aiohttp.ClientTimeout(total=10)
LABEL          = "bot-error"
TITLE_MAX      = 120
TRACEBACK_MAX  = 6000
_lock          = asyncio.Lock()       # deux erreurs simultanées du même bug → une seule issue
_tasks: set[asyncio.Task] = set()     # garde une référence aux rapports lancés en tâche de fond


def enabled() -> bool:
    return bool(config.GITHUB_TOKEN and config.GITHUB_REPO)


def _session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(timeout=_TIMEOUT, headers={
        "Authorization":        f"Bearer {config.GITHUB_TOKEN}",
        "Accept":               "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })


def issue_title(entry: dict) -> str:
    """« [acti] KeyError: 'slots' » sur une ligne, coupé à TITLE_MAX."""
    message = " ".join(entry["error_message"].split())
    title = f"[{entry['command']}] {entry['error_type']}" + (f": {message}" if message else "")
    return title if len(title) <= TITLE_MAX else title[:TITLE_MAX - 1] + "…"


def issue_body(entry: dict, reappeared_after: int | None = None) -> str:
    tb = entry["traceback"]
    if len(tb) > TRACEBACK_MAX:                      # la fin du traceback est la plus utile
        tb = "…\n" + tb[-TRACEBACK_MAX:]
    lines = [
        f"**Erreur #{entry['id']}** · `{entry['command']}` · {entry['ts'].strftime('%d/%m/%Y %H:%M')} UTC",
        f"Serveur : `{entry['guild_id'] or '?'}` · déclenchée par : `{entry['user_id'] or '?'}`",
    ]
    if reappeared_after:
        lines.append(f"⚠️ Réapparition après la fermeture de #{reappeared_after}.")
    lines += [
        "",
        f"**{entry['error_type']}** : {entry['error_message']}",
        "",
        "~~~text",
        tb.rstrip(),
        "~~~",
        "",
        "_Les occurrences suivantes de ce bug sont rattachées à cette issue sans nouvelle notification. "
        "Fermer l'issue (ou un commit « Fixes #N ») les passe en corrigées au prochain démarrage du bot._",
    ]
    return "\n".join(lines)


async def report(entry: dict) -> None:
    """Rattache l'erreur à l'issue ouverte de son bug, ou en ouvre une.
    entry : id, ts, guild_id, command, user_id, error_type, error_message, traceback."""
    if not enabled():
        return
    try:
        async with _lock:
            latest = await db.get_latest_error_issue(entry["command"], entry["error_type"])
            if latest and latest["closed_at"] is None:
                await db.set_error_issue(entry["id"], latest["issue_number"])
                return
            reappeared_after = latest["issue_number"] if latest else None
            async with _session() as session:
                async with session.post(f"{_API}/repos/{config.GITHUB_REPO}/issues", json={
                    "title":  issue_title(entry),
                    "body":   issue_body(entry, reappeared_after),
                    "labels": [LABEL],
                }) as resp:
                    if resp.status != 201:
                        print(f"[github_issues] Issue refusée par GitHub : HTTP {resp.status} {(await resp.text())[:300]}")
                        return
                    number = (await resp.json())["number"]
            await db.add_error_issue(number, entry["command"], entry["error_type"], entry["id"])
            print(f"[github_issues] Issue #{number} ouverte pour {entry['command']} · {entry['error_type']}")
    except Exception as e:  # noqa: BLE001 — jamais log_error ici (voir en tête du module)
        print(f"[github_issues] Impossible de créer l'issue : {type(e).__name__}: {e}")


def schedule_report(entry: dict) -> None:
    """Lance report() sans attendre : l'appelant (handler d'erreur) doit encore répondre à
    l'interaction Discord dans les temps."""
    if not enabled():
        return
    task = asyncio.create_task(report(entry))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def sync_closed() -> int:
    """Erreurs des issues fermées sur GitHub → corrigées. Renvoie le nombre d'issues fermées."""
    if not enabled():
        return 0
    numbers = await db.get_open_error_issues()
    if not numbers:
        return 0
    closed = 0
    async with _session() as session:
        for number in numbers:
            async with session.get(f"{_API}/repos/{config.GITHUB_REPO}/issues/{number}") as resp:
                if resp.status == 410:               # issue supprimée : plus rien à attendre
                    closed_at = datetime.now(UTC)
                elif resp.status == 200:
                    data = await resp.json()
                    if data.get("state") != "closed" or not data.get("closed_at"):
                        continue
                    closed_at = datetime.fromisoformat(data["closed_at"])
                else:
                    print(f"[github_issues] Issue #{number} illisible : HTTP {resp.status}")
                    continue
            await db.close_error_issue(number, closed_at)
            closed += 1
    return closed


class GithubIssues(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        if enabled():
            self.sync_loop.start()

    async def cog_unload(self):
        self.sync_loop.cancel()

    # 1er tour dès le démarrage (= juste après le déploiement d'un correctif), puis toutes les heures.
    @tasks.loop(hours=1)
    async def sync_loop(self):
        try:
            n = await sync_closed()
            if n:
                print(f"[github_issues] {n} issue(s) fermée(s) : leurs erreurs passent en corrigées.")
        except Exception as e:  # noqa: BLE001 — une exception non rattrapée arrêterait la boucle
            print(f"[github_issues] Synchronisation impossible : {type(e).__name__}: {e}")

    @sync_loop.before_loop
    async def before_sync(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(GithubIssues(bot))
