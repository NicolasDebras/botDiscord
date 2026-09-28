import io

import discord
from discord.ext import commands
from discord import app_commands

import db
from config import ADMIN_ROLE_NAME
from Service.utils import is_admin


class Errors(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # =========================================================================
    # /errors  — historique des erreurs de commandes (30 jours)
    # =========================================================================
    @app_commands.command(name="errors", description="[ADMIN] Voir l'historique des erreurs de commandes (30 jours)")
    @app_commands.describe(
        page="Numéro de page (10 entrées par page, défaut : 1)",
        commande="Filtrer par nom de commande (ex : totalbal, ballog)",
        id_erreur="Affiche la traceback complète de cette erreur (ignore page/commande)",
    )
    async def errors(
        self,
        interaction: discord.Interaction,
        page: app_commands.Range[int, 1] = 1,
        commande: str | None = None,
        id_erreur: int | None = None,
    ):
        if not is_admin(interaction.user):
            await interaction.response.send_message(
                f"⛔ Tu dois avoir le rôle **{ADMIN_ROLE_NAME}** pour utiliser cette commande.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        if id_erreur is not None:
            entry = await db.get_error_log_by_id(id_erreur, guild_id=interaction.guild.id)
            if not entry:
                await interaction.followup.send(f"❌ Erreur #{id_erreur} introuvable.", ephemeral=True)
                return

            date = entry["ts"].strftime("%d/%m/%Y %H:%M")
            who  = f"<@{entry['user_id']}>" if entry["user_id"] else "?"
            summary = (
                f"**#{entry['id']}** · `/{entry['command']}` · {date} · déclenché par {who}\n"
                f"**{entry['error_type']}** : {entry['error_message']}"
            )
            file = discord.File(io.BytesIO(entry["traceback"].encode("utf-8")), filename=f"error_{entry['id']}.txt")
            await interaction.followup.send(summary[:2000], file=file, ephemeral=True)
            return

        log = await db.get_error_logs(guild_id=interaction.guild.id, command=commande)
        if not log:
            detail = f" pour `/{commande}`" if commande else ""
            await interaction.followup.send(f"✅ Aucune erreur enregistrée{detail} sur les 30 derniers jours.", ephemeral=True)
            return

        per_page   = 10
        total_page = max(1, (len(log) + per_page - 1) // per_page)
        page       = min(page, total_page)
        slice_     = log[(page - 1) * per_page : page * per_page]

        title = f"🩹 Historique des erreurs  —  Page {page}/{total_page}"
        if commande:
            title += f"  —  /{commande}"

        embed = discord.Embed(title=title, color=0xE74C3C)

        for entry in slice_:
            date  = entry["ts"].strftime("%d/%m %H:%M")
            who   = f"<@{entry['user_id']}>" if entry["user_id"] else "?"
            name  = f"#{entry['id']}  ·  /{entry['command']}  ·  {date}"
            value = f"**{entry['error_type']}** : {entry['error_message'][:400]}\nDéclenché par {who}"
            embed.add_field(name=name[:256], value=value[:1024], inline=False)

        embed.set_footer(text=f"{len(log)} erreur(s)  •  historique 30 jours  •  /errors id_erreur:<ID> pour la traceback complète")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Errors(bot))
