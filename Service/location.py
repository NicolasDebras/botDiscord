import datetime
from datetime import timezone
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from discord import app_commands

import db
from config import ADMIN_ROLE_NAME
from Service.utils import fmt_silver, is_admin

PRICE_PER_DAY = 100_000
_PARIS        = ZoneInfo("Europe/Paris")
_HEURE_22H    = datetime.time(hour=22, minute=0, tzinfo=_PARIS)


class Location(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.increment_locations.start()

    async def cog_unload(self):
        self.increment_locations.cancel()

    # ── Tâche 22h : incrément journalier ──────────────────────────────────────
    @tasks.loop(time=_HEURE_22H)
    async def increment_locations(self):
        try:
            n = await db.increment_active_locations()
            if n:
                print(f"[location] {n} location(s) incrémentée(s) à 22h.")
        except Exception as e:
            print(f"[location] Erreur incrément : {e}")

    @increment_locations.before_loop
    async def before_increment(self):
        await self.bot.wait_until_ready()

    # ── /location ──────────────────────────────────────────────────────────────
    @app_commands.command(name="location", description="[OFFICIER] Créer une location d'arme")
    @app_commands.describe(
        joueur="Le joueur qui loue l'arme",
        arme="Nom de l'arme louée",
        caution="Caution à verser en silver (optionnel)",
    )
    async def location(
        self,
        interaction: discord.Interaction,
        joueur: discord.Member,
        arme: str,
        caution: int = 0,
    ):
        if not is_admin(interaction.user):
            await interaction.response.send_message(
                f"⛔ Réservé aux **{ADMIN_ROLE_NAME}**.", ephemeral=True
            )
            return

        loc_id = await db.create_location(
            guild_id=interaction.guild.id,
            user_id=str(joueur.id),
            user_name=joueur.display_name,
            arme=arme,
            caution=caution,
        )

        embed = discord.Embed(title=f"📦 Location #{loc_id} créée", color=0x3498DB)
        embed.add_field(name="Joueur",  value=joueur.mention,       inline=True)
        embed.add_field(name="Arme",    value=f"⚔️ {arme}",          inline=True)
        embed.add_field(name="Caution", value=f"🔒 {fmt_silver(caution)} silver" if caution else "*Aucune*", inline=True)
        embed.set_footer(text=f"100 000 silver / jour · Le compteur démarre ce soir à 22h · Créé par {interaction.user.display_name}")

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

        embed = discord.Embed(title="📦 Locations actives", color=0xF1C40F)

        for loc in locations:
            jours       = loc["jours_ecoules"]
            amount_owed = jours * PRICE_PER_DAY
            started_paris = loc["started_at"].astimezone(_PARIS)

            value = (
                f"{interaction.guild.get_member(int(loc['user_id'])).mention if interaction.guild.get_member(int(loc['user_id'])) else loc['user_name']}"
                f" — ⚔️ **{loc['arme']}**\n"
                f"📅 Début : {started_paris.strftime('%d/%m/%Y')}\n"
                f"🗓️ Jours comptés : **{jours}**\n"
                f"💰 Dû : **{fmt_silver(amount_owed)} silver**"
                + (f"  ·  🔒 Caution : **{fmt_silver(loc['caution'])} silver**" if loc["caution"] else "")
            )
            embed.add_field(
                name=f"#{loc['id']} · {loc['user_name']}",
                value=value,
                inline=False,
            )

        embed.set_footer(text=f"{len(locations)} location(s) active(s) · 100 000 silver / jour · compteur à 22h")
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

        jours      = loc["jours_ecoules"]
        total_owed = jours * PRICE_PER_DAY

        await db.close_location(id_location)

        member  = interaction.guild.get_member(int(loc["user_id"]))
        mention = member.mention if member else loc["user_name"]

        embed = discord.Embed(title=f"✅ Location #{id_location} clôturée", color=0x2ECC71)
        embed.add_field(name="Joueur",               value=mention,                                                          inline=True)
        embed.add_field(name="Arme",                 value=f"⚔️ {loc['arme']}",                                              inline=True)
        embed.add_field(name="Jours comptés",        value=str(jours),                                                       inline=True)
        embed.add_field(name="Montant final",        value=f"💰 **{fmt_silver(total_owed)} silver**",                         inline=True)
        embed.add_field(name="Caution à rembourser", value=f"🔒 **{fmt_silver(loc['caution'])} silver**" if loc["caution"] else "*Aucune*", inline=True)
        embed.set_footer(text=f"Clôturé par {interaction.user.display_name}")

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Location(bot))
