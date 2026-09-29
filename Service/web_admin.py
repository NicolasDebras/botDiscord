import discord
from discord.ext import commands
from discord import app_commands

import db
from config import GM_ROLE_NAME
from Service.utils import can_manage_web_admins

_DENIED = f"⛔ Réservé aux administrateurs du serveur ou au **{GM_ROLE_NAME}**."


class WebAdmin(commands.GroupCog, group_name="webadmin", group_description="[GM] Gérer les admins du site web"):
    """Admins du site web (lilium-site) : niveau au-dessus du staff, donne accès à
    la page Admin du site. Stockés dans la table web_admins, lue par l'API du site."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # =========================================================================
    # /webadmin add @membre
    # =========================================================================
    @app_commands.command(name="add", description="[GM] Donner l'accès admin du site web à un membre")
    @app_commands.describe(membre="Membre à nommer admin du site")
    async def add(self, interaction: discord.Interaction, membre: discord.Member):
        if not can_manage_web_admins(interaction.user):
            await interaction.response.send_message(_DENIED, ephemeral=True)
            return
        if membre.bot:
            await interaction.response.send_message("❌ Un bot ne peut pas être admin du site.", ephemeral=True)
            return

        added = await db.add_web_admin(interaction.guild.id, membre.id, interaction.user.id)
        if added:
            msg = f"✅ {membre.mention} est maintenant **admin du site web** sur ce serveur."
        else:
            msg = f"ℹ️ {membre.mention} est déjà admin du site web."
        await interaction.response.send_message(msg, ephemeral=True)

    # =========================================================================
    # /webadmin remove @membre
    # =========================================================================
    @app_commands.command(name="remove", description="[GM] Retirer l'accès admin du site web à un membre")
    @app_commands.describe(membre="Membre à retirer des admins du site")
    async def remove(self, interaction: discord.Interaction, membre: discord.Member):
        if not can_manage_web_admins(interaction.user):
            await interaction.response.send_message(_DENIED, ephemeral=True)
            return

        removed = await db.remove_web_admin(interaction.guild.id, membre.id)
        if removed:
            msg = f"✅ {membre.mention} n'est plus admin du site web."
        else:
            msg = f"ℹ️ {membre.mention} n'était pas admin du site web."
        await interaction.response.send_message(msg, ephemeral=True)

    # =========================================================================
    # /webadmin list
    # =========================================================================
    @app_commands.command(name="list", description="[GM] Lister les admins du site web sur ce serveur")
    async def list_admins(self, interaction: discord.Interaction):
        if not can_manage_web_admins(interaction.user):
            await interaction.response.send_message(_DENIED, ephemeral=True)
            return

        admins = await db.get_web_admins(interaction.guild.id)
        if not admins:
            await interaction.response.send_message(
                "Aucun admin du site web sur ce serveur. Utilise `/webadmin add @membre`.", ephemeral=True
            )
            return

        lines = [
            f"• <@{a['user_id']}> — ajouté le {a['added_at'].strftime('%d/%m/%Y')} par <@{a['added_by']}>"
            for a in admins
        ]
        embed = discord.Embed(
            title="🛡️ Admins du site web",
            description="\n".join(lines),
            color=0xC8A2FF,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(WebAdmin(bot))
