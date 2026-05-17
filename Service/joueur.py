import discord
from discord.ext import commands
from discord import app_commands

import db
from albion_api import fetch_albion_fame, fmt_fame


class Joueur(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="info", description="Voir le profil d'un joueur (fame Albion, activités)")
    @app_commands.describe(joueur="Le joueur à consulter")
    async def info(self, interaction: discord.Interaction, joueur: discord.Member):
        await interaction.response.defer(ephemeral=True)

        profile = await db.get_player_profile(str(joueur.id))

        acti_count       = profile["acti_count"]       if profile else 0
        ig_name          = profile["ig_name"]           if profile and profile["ig_name"] else None
        is_membre        = profile["is_membre"]         if profile else True
        recruitment_info = profile["recruitment_info"]  if profile and profile.get("recruitment_info") else None
        joined_at        = profile["joined_at"]         if profile else None

        color = 0xE67E22 if not is_membre else 0x3498DB

        embed = discord.Embed(
            title=f"{joueur.display_name}",
            color=color,
        )
        embed.set_image(url=joueur.display_avatar.url)

        # ── Ligne 1 : identité ────────────────────────────────────────────────
        embed.add_field(name="🎮 Pseudo IG", value=ig_name or "*Non enregistré*", inline=True)
        embed.add_field(name="🎯 Activités", value=str(acti_count),               inline=True)
        if not is_membre:
            embed.add_field(name="🆕 Statut", value="Nouveau joueur", inline=True)

        # ── Ligne 2 : fame ────────────────────────────────────────────────────
        if ig_name:
            try:
                fame = await fetch_albion_fame(ig_name)
                if fame:
                    pve_init   = profile["initial_pve_fame"] if profile else 0
                    pvp_init   = profile["initial_pvp_fame"] if profile else 0
                    pve_gained = max(0, fame["pve"] - pve_init)
                    pvp_gained = max(0, fame["pvp"] - pvp_init)

                    embed.add_field(
                        name="⚔️ Fame PvP",
                        value=f"**{fmt_fame(fame['pvp'])}** total\n+{fmt_fame(pvp_gained)} depuis recrutement",
                        inline=True,
                    )
                    embed.add_field(
                        name="🏰 Fame PvE",
                        value=f"**{fmt_fame(fame['pve'])}** total\n+{fmt_fame(pve_gained)} depuis recrutement",
                        inline=True,
                    )
                else:
                    embed.add_field(name="Fame Albion", value="*Joueur introuvable sur l'API*", inline=False)
            except Exception:
                embed.add_field(name="Fame Albion", value="*API indisponible*", inline=False)

        # ── Infos recrutement ─────────────────────────────────────────────────
        if recruitment_info:
            embed.add_field(name="📋 Infos recrutement", value=recruitment_info, inline=False)

        if joined_at:
            embed.set_footer(text=f"Recruté le {joined_at.strftime('%d/%m/%Y')}")

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Joueur(bot))
