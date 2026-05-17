import discord
from discord.ext import commands
from discord import app_commands

import db
from albion_api import fetch_albion_fame, fmt_fame
from config import ADMIN_ROLE_NAME, RECRUTEUR_ROLE_ID, MEMBRE_ROLE_NAME


def is_recruteur(member: discord.Member) -> bool:
    return (
        member.guild_permissions.administrator
        or any(r.id == RECRUTEUR_ROLE_ID or r.name == ADMIN_ROLE_NAME for r in member.roles)
    )


def _has_membre_role(member: discord.Member) -> bool:
    return any(r.name == MEMBRE_ROLE_NAME for r in member.roles)


class RecrutementModal(discord.ui.Modal, title="Fiche de recrutement"):
    def __init__(self, joueur: discord.Member, joueur_est_membre: bool):
        super().__init__()
        self.joueur           = joueur
        self.joueur_est_membre = joueur_est_membre

        self.pseudo_ig = discord.ui.TextInput(
            label="Pseudo IG",
            placeholder="Pseudo en jeu du candidat",
            required=True,
            max_length=100,
        )
        self.info = discord.ui.TextInput(
            label="Informations",
            placeholder="Classe, stuff, IP, disponibilités, motivation…",
            required=True,
            max_length=1000,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.pseudo_ig)
        self.add_item(self.info)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        embed = discord.Embed(
            title=f"📋 Candidature — {self.pseudo_ig.value}",
            description=self.info.value,
            color=0x3498DB,
        )
        embed.add_field(name="Discord", value=self.joueur.mention, inline=True)
        embed.add_field(name="Pseudo IG", value=self.pseudo_ig.value, inline=True)

        if not self.joueur_est_membre:
            embed.add_field(name="🆕 Statut", value="**Nouveau joueur**", inline=True)

        embed.set_thumbnail(url=self.joueur.display_avatar.url)
        embed.set_footer(text=f"Soumis par {interaction.user.display_name}")

        fame = None
        try:
            fame = await fetch_albion_fame(self.pseudo_ig.value)
            if fame:
                embed.add_field(
                    name="Fame Albion",
                    value=f"⚔️ PvP : **{fmt_fame(fame['pvp'])}**\n🏰 PvE : **{fmt_fame(fame['pve'])}**",
                    inline=False,
                )
            else:
                embed.add_field(name="Fame Albion", value="*Joueur introuvable sur l'API*", inline=False)
        except Exception:
            embed.add_field(name="Fame Albion", value="*Impossible de récupérer la fame (API indisponible)*", inline=False)

        if fame:
            await db.save_player_profile(
                str(self.joueur.id),
                fame["name"],
                fame["pve"],
                fame["pvp"],
                self.info.value,
                self.joueur_est_membre,
            )

        await interaction.followup.send(embed=embed)


# ══════════════════════════════════════════════════════════════════════════════
# COG RECRUTEMENT
# ══════════════════════════════════════════════════════════════════════════════
class Recrutement(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="recrutement", description="Enregistrer une candidature de recrutement")
    @app_commands.describe(joueur="Le joueur candidat")
    async def recrutement(self, interaction: discord.Interaction, joueur: discord.Member):
        if not is_recruteur(interaction.user):
            await interaction.response.send_message(
                "⛔ Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
            )
            return

        await interaction.response.send_modal(RecrutementModal(joueur, joueur_est_membre=_has_membre_role(joueur)))


async def setup(bot: commands.Bot):
    await bot.add_cog(Recrutement(bot))
