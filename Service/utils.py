import random
import discord
import db

from config import ADMIN_ROLE_NAME, GM_ROLE_NAME, MEMBRE_ROLE_NAME, CALLER_ROLE_NAME, DEFAULT_BAL_RATE, GUILD_ID as _MAIN_GUILD_ID


def fmt_silver(n: int) -> str:
    """Formate un montant en silver avec espaces comme séparateur de milliers."""
    return f"{n:,}".replace(",", " ")


# ── HELPER : vérification du rôle admin ──────────────────────────────────────
def is_admin(member: discord.Member) -> bool:
    return (
        member.guild_permissions.administrator
        or any(r.name == ADMIN_ROLE_NAME for r in member.roles)
    )


# ── HELPER : vérification du rôle membre ─────────────────────────────────────
def is_membre(member: discord.Member) -> bool:
    return (
        member.guild_permissions.administrator
        or any(r.name in (ADMIN_ROLE_NAME, GM_ROLE_NAME, MEMBRE_ROLE_NAME) for r in member.roles)
    )


# ── HELPER : vérification du rôle Caller ou admin ────────────────────────────
def is_caller_or_admin(member: discord.Member) -> bool:
    return (
        member.guild_permissions.administrator
        or any(r.name in (ADMIN_ROLE_NAME, GM_ROLE_NAME, CALLER_ROLE_NAME) for r in member.roles)
    )


# ── HELPERS : settings persistants (taux de rachat, etc.) ────────────────────
async def load_settings(guild_id: int = 0) -> dict:
    rate = await db.get_bal_rate(guild_id)
    return {"bal_rate": rate}


async def save_settings(data: dict, guild_id: int = 0) -> None:
    await db.set_bal_rate(guild_id, data.get("bal_rate", DEFAULT_BAL_RATE))


# ── HELPERS : log BAL ─────────────────────────────────────────────────────────
async def append_bal_log(action: str, by: str, entries: list, template: str = "", guild_id: int = 0) -> None:
    await db.append_bal_log(action, by, entries, template, guild_id)


BAL_LIMIT = 20_000_000

MESSAGES_BAL_LIMIT = [
    "Ayo {mention} t'as **{total}** silver de BAL qui traîne… la guilde est pas une banque, viens récupérer ta thune gros merdeux 💸",
    "Réveille-toi {mention} 😤 T'as **{total}** silver de BAL qui prend la poussière. La guilde te garde pas la monnaie indéfiniment, bouge toi le fion.",
    "Sérieusement {mention} ? **{total}** silver de BAL et tu viens pas les chercher ? On est une guilde, pas un coffre-fort. Viens récupérer ça ou je t'envoie le recouvrement 🏦",
    "{mention} t'as **{total}** silver de BAL. La guilde te l'a pas mise de côté pour faire joli. Viens chercher ton fric, cornichon 🥒",
]


async def notify_bal_limit(bot: discord.Client, user_id: int, new_total: int, guild_id: int = 0) -> None:
    """Envoie un DM si la BAL franchit BAL_LIMIT à la hausse (une seule fois).
    Remet le flag à false si la BAL repasse sous BAL_LIMIT.
    Les messages sont réservés au serveur principal."""
    uid_str = str(user_id)
    if guild_id != _MAIN_GUILD_ID:
        return
    if new_total >= BAL_LIMIT:
        if await db.get_is_alerted(uid_str, guild_id):
            return  # déjà alerté, on ne respamme pas
        try:
            user = await bot.fetch_user(user_id)
            msg  = random.choice(MESSAGES_BAL_LIMIT).format(mention=user.mention, total=fmt_silver(new_total))
            await user.send(msg)
        except Exception:
            pass
        await db.set_is_alerted(uid_str, True, guild_id)
    else:
        await db.set_is_alerted(uid_str, False, guild_id)


async def load_bal_log(action: str | None = None, guild_id: int = 0) -> list:
    return await db.get_bal_log(action, guild_id)


# ── SELECT : choix d'une activité en cours ───────────────────────────────────
class ActivitySelect(discord.ui.Select):
    """Liste déroulante qui affiche les activités en cours."""

    def __init__(self, callback_fn, placeholder: str = "🗡️ Choisis une activité..."):
        from Service.activites import activities   # import tardif

        self._callback_fn = callback_fn
        options = []
        for msg_id, data in activities.items():
            label = data.get("thread_name") or data["template"] or "Sans template"
            desc  = f"Par {data['creator']} • {sum(len(v) for v in data['slots'].values())}/{data['max_players']} joueurs"
            options.append(discord.SelectOption(label=label[:100], description=desc[:100], value=str(msg_id)))

        if not options:
            options = [discord.SelectOption(label="Aucune activité en cours", value="none")]

        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            await self._callback_fn(interaction, self.values[0])
        except Exception as e:
            msg = f"❌ Erreur inattendue : {e}"
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
