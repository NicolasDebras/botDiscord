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

        embed = discord.Embed(
            title=f"👤 {joueur.display_name}",
            color=0x3498DB,
        )
        embed.set_thumbnail(url=joueur.display_avatar.url)

        acti_count = profile["acti_count"] if profile else 0
        ig_name    = profile["ig_name"]    if profile and profile["ig_name"] else None

        embed.add_field(name="🎯 Activités terminées", value=str(acti_count), inline=True)
        embed.add_field(name="🎮 Pseudo IG",           value=ig_name or "*Non enregistré*", inline=True)

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

        if profile and profile["joined_at"]:
            embed.set_footer(text=f"Recruté le {profile['joined_at'].strftime('%d/%m/%Y')}")

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Joueur(bot))
