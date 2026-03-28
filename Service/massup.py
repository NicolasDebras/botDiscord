import discord
from discord.ext import commands
from discord import app_commands

from config import MEMBRE_ROLE_NAME
from Service.activites import activities
from Service.utils import ActivitySelect, is_membre


# ══════════════════════════════════════════════════════════════════════════════
# COG MASSUP
# ══════════════════════════════════════════════════════════════════════════════
class MassUp(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # =========================================================================
    # /massup  — ping tous les inscrits d'une activité
    # =========================================================================
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

            participants = [uid for members in data["slots"].values() for uid, _ in members]
            if not participants:
                await inter.response.send_message("ℹ️ Aucun joueur inscrit à cette activité.", ephemeral=True)
                return

            mentions  = " ".join(f"<@{uid}>" for uid in participants)
            template  = data.get("template", "Activité")
            intro     = f"📢 **{template}** — {len(participants)} joueur(s) convoqué(s) !\n"
            if message:
                intro += f"> {message}\n"

            await inter.response.send_message(intro + mentions, delete_after=300)

        view = discord.ui.View(timeout=60)
        view.add_item(ActivitySelect(on_select, "📢 Quelle activité convoquer ?"))
        await interaction.response.send_message(
            "Choisis l'activité à convoquer :", view=view, ephemeral=True
        )


# ── SETUP ─────────────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(MassUp(bot))
