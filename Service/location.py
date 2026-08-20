import datetime
from datetime import timezone

import discord
from discord.ext import commands
from discord import app_commands

import db
from config import ADMIN_ROLE_NAME
from Service.utils import fmt_silver, is_admin

PRICE_PER_DAY = 100_000


class Location(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /location ──────────────────────────────────────────────────────────────
    @app_commands.command(name="location", description="[OFFICIER] Créer une location d'arme")
    @app_commands.describe(
        joueur="Le joueur qui loue l'arme",
        arme="Nom de l'arme louée",
        duree="Durée de location en jours",
        caution="Caution à verser en silver (optionnel)",
    )
    async def location(
        self,
        interaction: discord.Interaction,
        joueur: discord.Member,
        arme: str,
        duree: app_commands.Range[int, 1, 365],
        caution: int = 0,
    ):
        if not is_admin(interaction.user):
            await interaction.response.send_message(
                f"⛔ Réservé aux **{ADMIN_ROLE_NAME}**.", ephemeral=True
            )
            return

        loc_id   = await db.create_location(
            guild_id=interaction.guild.id,
            user_id=str(joueur.id),
            user_name=joueur.display_name,
            arme=arme,
            duree_jours=duree,
            caution=caution,
        )
        end_dt = datetime.datetime.now(timezone.utc) + datetime.timedelta(days=duree)
        total  = duree * PRICE_PER_DAY

        embed = discord.Embed(title=f"📦 Location #{loc_id} créée", color=0x3498DB)
        embed.add_field(name="Joueur",       value=joueur.mention,                                         inline=True)
        embed.add_field(name="Arme",         value=f"⚔️ {arme}",                                           inline=True)
        embed.add_field(name="Durée",        value=f"{duree} jour(s)",                                     inline=True)
        embed.add_field(name="Fin prévue",   value=f"<t:{int(end_dt.timestamp())}:D>",                    inline=True)
        embed.add_field(name="Total prévu",  value=f"💰 {fmt_silver(total)} silver",                       inline=True)
        embed.add_field(name="Caution",      value=f"🔒 {fmt_silver(caution)} silver" if caution else "*Aucune*", inline=True)
        embed.set_footer(text=f"100 000 silver / jour · Créé par {interaction.user.display_name}")

        await interaction.response.send_message(embed=embed)

    # ── /recaplocation ─────────────────────────────────────────────────────────
    @app_commands.command(name="recaplocation", description="Récapitulatif des locations d'armes actives")
    async def recaplocation(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            await interaction.response.send_message(
                f"⛔ Réservé aux **{ADMIN_ROLE_NAME}**.", ephemeral=True
            )
            return

        locations = await db.get_active_locations(interaction.guild.id)
        if not locations:
            await interaction.response.send_message("📭 Aucune location active.", ephemeral=True)
            return

        now   = datetime.datetime.now(timezone.utc)
        embed = discord.Embed(title="📦 Locations actives", color=0xF1C40F)

        for loc in locations:
            started   = loc["started_at"]
            end_dt    = started + datetime.timedelta(days=loc["duree_jours"])
            elapsed_s = (now - started).total_seconds()
            elapsed_d = elapsed_s / 86400
            remaining = end_dt - now

            amount_owed = int(elapsed_d * PRICE_PER_DAY)

            if remaining.total_seconds() > 0:
                rem_d = remaining.days
                rem_h = remaining.seconds // 3600
                status = f"⏱️ {rem_d}j {rem_h}h restants"
            else:
                over_d = abs(remaining.days)
                status = f"⚠️ Dépassé de {over_d} jour(s)"

            member  = interaction.guild.get_member(int(loc["user_id"]))
            mention = member.mention if member else f"*(ID {loc['user_id']})*"

            value = (
                f"{mention} — ⚔️ **{loc['arme']}**\n"
                f"{status}\n"
                f"💰 Dû : **{fmt_silver(amount_owed)} silver**"
                + (f"  ·  🔒 Caution : **{fmt_silver(loc['caution'])} silver**" if loc["caution"] else "")
                + f"\n📅 Fin : <t:{int(end_dt.timestamp())}:D>"
            )
            embed.add_field(
                name=f"#{loc['id']} · {loc['user_name']}",
                value=value,
                inline=False,
            )

        embed.set_footer(text=f"{len(locations)} location(s) active(s) · 100 000 silver / jour")
        await interaction.response.send_message(embed=embed)

    # ── /closelocation ─────────────────────────────────────────────────────────
    @app_commands.command(name="closelocation", description="[OFFICIER] Clôturer une location d'arme")
    @app_commands.describe(id_location="ID de la location (visible dans /recaplocation)")
    async def closelocation(self, interaction: discord.Interaction, id_location: int):
        if not is_admin(interaction.user):
            await interaction.response.send_message(
                f"⛔ Réservé aux **{ADMIN_ROLE_NAME}**.", ephemeral=True
            )
            return

        loc = await db.get_location_by_id(id_location, interaction.guild.id)
        if not loc:
            await interaction.response.send_message("❌ Location introuvable.", ephemeral=True)
            return
        if loc["is_closed"]:
            await interaction.response.send_message("❌ Cette location est déjà clôturée.", ephemeral=True)
            return

        now         = datetime.datetime.now(timezone.utc)
        elapsed_d   = (now - loc["started_at"]).total_seconds() / 86400
        total_owed  = int(elapsed_d * PRICE_PER_DAY)

        await db.close_location(id_location)

        member  = interaction.guild.get_member(int(loc["user_id"]))
        mention = member.mention if member else f"*(ID {loc['user_id']})*"

        embed = discord.Embed(title=f"✅ Location #{id_location} clôturée", color=0x2ECC71)
        embed.add_field(name="Joueur",             value=mention,                                                     inline=True)
        embed.add_field(name="Arme",               value=f"⚔️ {loc['arme']}",                                         inline=True)
        embed.add_field(name="Durée réelle",        value=f"{elapsed_d:.1f} jour(s)",                                 inline=True)
        embed.add_field(name="Montant final",       value=f"💰 **{fmt_silver(total_owed)} silver**",                   inline=True)
        embed.add_field(name="Caution à rembourser", value=f"🔒 **{fmt_silver(loc['caution'])} silver**" if loc["caution"] else "*Aucune*", inline=True)
        embed.set_footer(text=f"Clôturé par {interaction.user.display_name}")

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Location(bot))
