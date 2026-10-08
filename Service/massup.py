import io
import time

import discord
from discord.ext import commands
from discord import app_commands

import db
from config import MEMBRE_ROLE_NAME
from Service.activites import activities, _acti_label, _is_creator, build_id_for_role, load_all_templates
from Service.build_image import build_image
from Service.utils import ActivitySelect, is_caller_or_admin, is_membre, log_error

# Anti-spam : un massup par activité toutes les MASSUP_COOLDOWN secondes
MASSUP_COOLDOWN = 120
_last_massup: dict[int, float] = {}

# ── Loot RAID AVA par rôle ────────────────────────────────────────────────────
_LOOT_FIXE: dict[str, str] = {
    "TANK":        "🗺️ Carte / Maps HCE / Pièce",
    "MAIN TANK":   "🗺️ Carte / Maps HCE / Pièce",
    "OFF TANK":    "👻 Âmes / AVA Shard / Artefact *(50k mini)*",
    "MAIN HEAL":   "📚 Books / Energy AVA",
    "COBRA/GA":    "💎 Treasures T5/T6 + Bags + Capes",
    "COBRA":       "💎 Treasures T5/T6 + Bags + Capes",
    "IRON ROOT":   "⚔️ Warrior weapon + Left hand",
    "IRON":        "⚔️ Warrior weapon + Left hand",
    "SC":          "🪖 Helmet *(all)*",
    "FROST":       "👟 Shoes *(all)*",
    "HURLEGIVRE":  "👟 Shoes *(all)*",
    "SCOOT":       "🎒 All",
    "SCOUT":       "🎒 All",
    "LEACHER PVP": "🎒 All",
    "DAMME":       "🎒 All",
}

# Ordre d'affichage imposé (correspond à l'ordre du message de convocation)
_RAID_AVA_ORDER: list[str] = [
    "TANK", "MAIN TANK",
    "OFF TANK",
    "MAIN HEAL",
    "COBRA/GA", "COBRA",
    "IRON ROOT", "IRON",
    "DPS", "FAUX",
    "SC",
    "FROST", "HURLEGIVRE",
    "SCOOT", "SCOUT", "LEACHER PVP", "DAMME",
]

# Pour DPS / FAUX : loot selon la position dans le slot (index 0, 1, 2…)
_LOOT_DPS: list[str] = [
    "🏹 Mage weapon + Left hand",
    "🏹 Hunter weapon + Left hand",
    "🛡️ Armor *(all)*",
]
_DPS_ROLES = {"DPS", "FAUX"}


def _build_raid_ava_lines(data: dict) -> list[str]:
    slots = data["slots"]
    lines = []
    seen  = set()
    for role in _RAID_AVA_ORDER:
        if role not in slots or role in seen:
            continue
        seen.add(role)
        members = slots[role]
        if role in _DPS_ROLES:
            n = max(len(members), len(_LOOT_DPS))
            for i in range(n):
                loot   = _LOOT_DPS[i] if i < len(_LOOT_DPS) else "🎒 All"
                player = f"<@{members[i][0]}>" if i < len(members) else "*Vide*"
                lines.append(f"**{role} {i+1}** - {player} - {loot}")
        else:
            loot = _LOOT_FIXE.get(role, "")
            if members:
                for entry in members:
                    lines.append(f"**{role}** - <@{entry[0]}> - {loot}")
            else:
                lines.append(f"**{role}** - *Vide* - {loot}")
    return lines


# ── Builds imposés (compos du site) : qui reçoit quel build en MP ─────────────
def build_recipients(slots: dict[str, list], template_data: dict) -> dict[int, list[tuple[int, str]]]:
    """{build_id: [(user_id, libellé du rôle), ...]} pour les rôles qui ont un build.
    Les rôles sans build (et le Fill) ne reçoivent rien."""
    out: dict[int, list[tuple[int, str]]] = {}
    for role_key, members in slots.items():
        build_id = build_id_for_role(template_data, role_key)
        if build_id is None:
            continue
        label = f"{role_key[4:]} (PF2)" if role_key.startswith("PF2:") else role_key
        out.setdefault(build_id, []).extend((int(entry[0]), label) for entry in members)
    return out


async def send_build_dms(
    inter: discord.Interaction, data: dict, label: str,
) -> tuple[int, list[int]]:
    """Envoie à chaque joueur l'image du build de son rôle. Retourne (nb envoyés, ids aux MP fermés)."""
    template = data.get("template")
    tdata = load_all_templates(data.get("guild_id", 0)).get(template, {}) if template else {}
    recipients = build_recipients(data["slots"], tdata)
    sent, closed = 0, []

    for build_id, players in recipients.items():
        build = await db.get_build_by_id(build_id, data.get("guild_id", 0))
        if not build:
            continue
        try:
            png = await build_image(build)
        except Exception as e:
            await log_error("massup.build_image", e, guild_id=data.get("guild_id"))
            continue

        for user_id, role_label in players:
            try:
                user = inter.guild.get_member(user_id) or await inter.client.fetch_user(user_id)
                await user.send(
                    f"📢 **{label}** — tu es convoqué en **{role_label}**.\n"
                    f"Ton build : **{build['name']}**",
                    file=discord.File(io.BytesIO(png), filename="build.png"),
                )
                sent += 1
            except discord.Forbidden:
                closed.append(user_id)
            except Exception as e:
                await log_error("massup.dm", e, guild_id=data.get("guild_id"), user_id=user_id)
    return sent, closed


def dm_summary(sent: int, closed: list[int]) -> str | None:
    if not sent and not closed:
        return None
    text = f"✉️ {sent} build(s) envoyé(s) en MP."
    if closed:
        text += f" {len(closed)} joueur(s) ont les MP fermés : " + " ".join(f"<@{u}>" for u in closed)
    return text


# ══════════════════════════════════════════════════════════════════════════════
# COG MASSUP
# ══════════════════════════════════════════════════════════════════════════════
class MassUp(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="massup", description="Ping tous les joueurs inscrits à une activité")
    @app_commands.describe(message="Message optionnel à joindre au ping")
    async def massup(self, interaction: discord.Interaction, message: str | None = None):
        if not is_membre(interaction.user):
            await interaction.response.send_message(
                f"⛔ Tu dois avoir le rôle **{MEMBRE_ROLE_NAME}** pour utiliser cette commande.", ephemeral=True
            )
            return
        if not activities:
            await interaction.response.send_message("ℹ️ Aucune activité en cours.", ephemeral=True)
            return

        async def on_select(inter: discord.Interaction, value: str):
            if value == "none":
                await inter.response.send_message("ℹ️ Aucune activité disponible.", ephemeral=True)
                return

            msg_id = int(value)
            data   = activities.get(msg_id)
            if not data:
                await inter.response.send_message("❌ Activité introuvable.", ephemeral=True)
                return

            if not (_is_creator(inter.user, data) or is_caller_or_admin(inter.user)):
                await inter.response.send_message(
                    "⛔ Seul le créateur de l'activité ou un Caller peut la convoquer.", ephemeral=True
                )
                return

            now = time.monotonic()
            wait = MASSUP_COOLDOWN - (now - _last_massup.get(msg_id, -MASSUP_COOLDOWN))
            if wait > 0:
                await inter.response.send_message(
                    f"⏳ Cette activité vient d'être convoquée — réessaie dans {int(wait) + 1} s.", ephemeral=True
                )
                return

            participants = [entry[0] for members in data["slots"].values() for entry in members]
            if not participants:
                await inter.response.send_message("ℹ️ Aucun joueur inscrit à cette activité.", ephemeral=True)
                return

            label    = _acti_label(data)
            template = data.get("template", "")
            intro    = f"📢 **{label}** — {len(participants)} joueur(s) convoqué(s) !\n"
            if message:
                intro += f"> {message}\n"

            is_raid_ava = template and "RAID AVA" in template.upper()
            if is_raid_ava:
                intro += "`#forcecityoverload true`\n"
            if is_raid_ava:
                body = "\n".join(_build_raid_ava_lines(data))
            else:
                body = " ".join(f"<@{uid}>" for uid in participants)

            _last_massup[msg_id] = now
            await inter.response.send_message(intro + body)

            # Compo du site : chaque joueur reçoit l'image du build de son rôle en MP.
            summary = dm_summary(*await send_build_dms(inter, data, label))
            if summary:
                await inter.followup.send(summary, ephemeral=True)

        view = discord.ui.View(timeout=60)
        view.add_item(ActivitySelect(on_select, "📢 Quelle activité convoquer ?", guild_id=interaction.guild.id))
        await interaction.response.send_message(
            "Choisis l'activité à convoquer :", view=view, ephemeral=True
        )


# ── SETUP ─────────────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(MassUp(bot))
