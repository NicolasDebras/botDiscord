import discord
from discord.ext import commands
from discord import app_commands

from config import MEMBRE_ROLE_NAME
from Service.activites import activities, _acti_label
from Service.utils import ActivitySelect, is_membre

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
    "🏹 Hunter weapon + Left hand",
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

            await inter.response.send_message(intro + body, delete_after=300)

        view = discord.ui.View(timeout=60)
        view.add_item(ActivitySelect(on_select, "📢 Quelle activité convoquer ?"))
        await interaction.response.send_message(
            "Choisis l'activité à convoquer :", view=view, ephemeral=True
        )


# ── SETUP ─────────────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(MassUp(bot))
