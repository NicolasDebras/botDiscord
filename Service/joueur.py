import asyncio
import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from discord import app_commands

import db
from albion_api import fetch_albion_fame, fmt_fame
from config import ADMIN_ROLE_NAME, RECRUTEUR_ROLE_ID, MEMBRE_ROLE_NAME
from Service.utils import fmt_silver

_PARIS          = ZoneInfo("Europe/Paris")
_RAPPEL_HEURE   = datetime.time(hour=22, minute=0, tzinfo=_PARIS)
_RAPPEL_SALON   = 1505623773708025992
_ABSENT_ROLE_ID = 1496637644283576452


def _is_recruteur_or_admin(member: discord.Member) -> bool:
    return (
        member.guild_permissions.administrator
        or any(r.id == RECRUTEUR_ROLE_ID or r.name == ADMIN_ROLE_NAME for r in member.roles)
    )


class Joueur(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.rappel_nouveaux.start()

    async def cog_unload(self):
        self.rappel_nouveaux.cancel()

    # ── Logique commune recap ──────────────────────────────────────────────────
    async def _run_recap(self, guild: discord.Guild, purge_immediate: bool = False) -> None:
        channel = self.bot.get_channel(_RAPPEL_SALON)
        if not channel:
            return

        if not guild.chunked:
            await guild.chunk()

        profiles = await db.get_all_profiles()
        now      = datetime.datetime.now(datetime.timezone.utc)
        delai    = datetime.timedelta(days=3)

        # ── 1. Mise à jour / nettoyage des profils ────────────────────────────
        for p in profiles:
            member = guild.get_member(int(p["user_id"]))

            if member is None:
                # purge_immediate = depuis /recap (supprime sans délai)
                # sinon règle des 3 jours
                if purge_immediate or (p["joined_at"] and (now - p["joined_at"]) > delai):
                    await db.delete_player_profile(p["user_id"])
                continue

            if p["ig_name"]:
                try:
                    fame = await fetch_albion_fame(p["ig_name"])
                    if fame:
                        await db.update_player_fame(p["user_id"], fame["name"], fame["pve"], fame["pvp"])
                except Exception:
                    pass
                await asyncio.sleep(0.5)

        # Recharger après purge
        profiles = await db.get_all_profiles()

        # ── 2. Récap suivi recrutement ────────────────────────────────────────
        nouveaux  = [p for p in profiles if not p["is_membre"] and p["joined_at"]]

        moins_1s  = sorted([p for p in nouveaux if (now - p["joined_at"]) < datetime.timedelta(days=7)],  key=lambda p: p["joined_at"])
        moins_2s  = sorted([p for p in nouveaux if datetime.timedelta(days=7) <= (now - p["joined_at"]) < datetime.timedelta(days=14)], key=lambda p: p["joined_at"])
        a_valider = sorted([p for p in nouveaux if (now - p["joined_at"]) >= datetime.timedelta(days=14)], key=lambda p: p["joined_at"])

        def fmt_joueur(p) -> str:
            member  = guild.get_member(int(p["user_id"]))
            mention = member.mention if member else f"*(parti — ID {p['user_id']})*"
            ig      = f"**{p['ig_name']}**" if p["ig_name"] else "*pseudo IG inconnu*"
            depuis  = p["joined_at"].strftime("%d/%m/%Y")
            return f"• {ig} — {mention} — recruté le {depuis}"

        def fmt_section(players) -> str:
            return "\n".join(fmt_joueur(p) for p in players) if players else "*Aucun*"

        ping = f"<@&{RECRUTEUR_ROLE_ID}>"
        await channel.send(
            f"{ping}\n"
            f"📋 **Récap suivi recrutement**\n\n"
            f"**Joueurs qui ont rejoint la guilde il y a moins d'une semaine :**\n{fmt_section(moins_1s)}\n\n"
            f"**Joueurs qui ont rejoint la guilde il y a moins de 2 semaines :**\n{fmt_section(moins_2s)}\n\n"
            f"**Joueurs à valider via `/ancien` (plus de 2 semaines dans la guilde) :**\n{fmt_section(a_valider)}"
        )

        # ── 3. Stats silver depuis lundi ──────────────────────────────────────
        days_since_monday = max(1, now.astimezone(_PARIS).weekday() + 1)
        stats = await db.get_silver_stats(days_since_monday)
        payout_normal = sum(r["total_silver"] for r in stats if r["action"] in ("finacti", "paybal"))
        payout_raid   = sum(r["total_silver"] for r in stats if r["action"] in ("finacti_raid_ava", "paybal_raid_ava"))

        # ── 4. Membres inactifs depuis 2 semaines ─────────────────────────────
        inactive_ids = await db.get_inactive_member_ids(14)
        membre_role  = discord.utils.get(guild.roles, name=MEMBRE_ROLE_NAME)
        inactifs     = []
        if membre_role:
            for m in membre_role.members:
                if str(m.id) in inactive_ids:
                    inactifs.append(m)

        inactifs_str = "\n".join(f"• {m.mention}" for m in inactifs) if inactifs else "*Aucun*"

        await channel.send(
            f"📊 **Stats de la semaine (depuis lundi)**\n\n"
            f"💰 Payout hors RAID AVA : **{fmt_silver(payout_normal)} silver**\n"
            f"⚔️ RAID AVA : **{fmt_silver(payout_raid)} silver**\n\n"
            f"😴 **Membres sans activité depuis 2 semaines :**\n{inactifs_str}"
        )

    # ── Tâche 22h ─────────────────────────────────────────────────────────────
    @tasks.loop(time=_RAPPEL_HEURE)
    async def rappel_nouveaux(self):
        channel = self.bot.get_channel(_RAPPEL_SALON)
        if not channel:
            return
        await self._run_recap(channel.guild, purge_immediate=False)

    @rappel_nouveaux.before_loop
    async def before_rappel(self):
        await self.bot.wait_until_ready()

    # ── /recap ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="recap", description="Relancer manuellement le récap recrutement (purge les profils des partis)")
    async def recap(self, interaction: discord.Interaction):
        if not _is_recruteur_or_admin(interaction.user):
            await interaction.response.send_message(
                "⛔ Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        await self._run_recap(interaction.guild, purge_immediate=True)
        await interaction.followup.send("✅ Récap envoyé et base nettoyée.", ephemeral=True)

    # ── /ancien @joueur ───────────────────────────────────────────────────────
    @app_commands.command(name="ancien", description="Marquer un joueur comme ancien membre (retire le flag Nouveau joueur)")
    @app_commands.describe(joueur="Le joueur à promouvoir")
    async def ancien(self, interaction: discord.Interaction, joueur: discord.Member):
        if not _is_recruteur_or_admin(interaction.user):
            await interaction.response.send_message(
                "⛔ Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
            )
            return

        profile = await db.get_player_profile(str(joueur.id))
        if not profile:
            await interaction.response.send_message(
                f"❌ **{joueur.display_name}** n'a pas de profil enregistré.", ephemeral=True
            )
            return

        nouveau_statut = not profile["is_membre"]
        await db.set_player_is_membre(str(joueur.id), nouveau_statut)

        if nouveau_statut:
            await interaction.response.send_message(
                f"✅ **{joueur.display_name}** est maintenant marqué comme **membre** — flag Nouveau joueur retiré.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"🔄 **{joueur.display_name}** est maintenant marqué comme **nouveau joueur**.",
                ephemeral=True,
            )

    # ── /kick @joueur ─────────────────────────────────────────────────────────
    @app_commands.command(name="kick", description="Passer un joueur en statut AFK (retire tous ses rôles)")
    @app_commands.describe(joueur="Le joueur à passer AFK")
    async def kick(self, interaction: discord.Interaction, joueur: discord.Member):
        if not _is_recruteur_or_admin(interaction.user):
            await interaction.response.send_message(
                "⛔ Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        absent_role = interaction.guild.get_role(_ABSENT_ROLE_ID)
        if not absent_role:
            await interaction.followup.send("❌ Rôle Absent introuvable (ID invalide ?).", ephemeral=True)
            return

        bal = await db.get_bal(str(joueur.id))

        try:
            await joueur.edit(roles=[absent_role])
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Je n'ai pas la permission de modifier les rôles de ce joueur.", ephemeral=True
            )
            return

        dm_ok = True
        try:
            await joueur.send(
                f"👋 Tu as été passé en statut **AFK** sur le serveur de la guilde.\n\n"
                f"Tu as actuellement **{fmt_silver(bal)} silver** sur ta BAL.\n"
                f"Tu as **3 jours** pour te manifester et récupérer tes BAL — "
                f"passé ce délai, elles seront remises à zéro."
            )
        except discord.Forbidden:
            dm_ok = False

        confirm = f"✅ **{joueur.display_name}** est maintenant AFK — tous ses rôles ont été retirés et le rôle Absent ajouté."
        if not dm_ok:
            confirm += "\n⚠️ Impossible d'envoyer le DM (DMs désactivés)."
        await interaction.followup.send(confirm, ephemeral=True)

    # ── /reporter @joueur ─────────────────────────────────────────────────────
    @app_commands.command(name="reporter", description="Repousser le suivi d'un nouveau joueur d'une semaine (vacances, maladie…)")
    @app_commands.describe(joueur="Le joueur à reporter")
    async def reporter(self, interaction: discord.Interaction, joueur: discord.Member):
        if not _is_recruteur_or_admin(interaction.user):
            await interaction.response.send_message(
                "⛔ Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
            )
            return

        profile = await db.get_player_profile(str(joueur.id))
        if not profile:
            await interaction.response.send_message(
                f"❌ **{joueur.display_name}** n'a pas de profil enregistré.", ephemeral=True
            )
            return
        if profile["is_membre"]:
            await interaction.response.send_message(
                f"ℹ️ **{joueur.display_name}** est déjà membre, pas de suivi en cours.", ephemeral=True
            )
            return

        await db.postpone_player_check(str(joueur.id), days=7)
        nouvelle_date = profile["joined_at"] + datetime.timedelta(days=7 + 14)
        await interaction.response.send_message(
            f"📅 Le suivi de **{joueur.display_name}** est repoussé d'une semaine — prochain check après le **{nouvelle_date.strftime('%d/%m/%Y')}**.",
            ephemeral=True,
        )

    # ── /info @joueur ─────────────────────────────────────────────────────────
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

        embed = discord.Embed(title=joueur.display_name, color=color)
        embed.set_image(url=joueur.display_avatar.url)

        # ── Ligne 1 : identité ────────────────────────────────────────────────
        embed.add_field(name="🎮 Pseudo IG", value=ig_name or "*Non enregistré*", inline=True)
        embed.add_field(name="🎯 Activités", value=str(acti_count),               inline=True)
        statut = "🆕 En cours de suivi" if not is_membre else "✅ Intégré"
        embed.add_field(name="📋 Suivi recrutement", value=statut, inline=True)

        # ── Ligne 2 : fame ────────────────────────────────────────────────────
        if ig_name:
            pve_init = profile["initial_pve_fame"] if profile else 0
            pvp_init = profile["initial_pvp_fame"] if profile else 0

            fame_live = None
            try:
                fame_live = await fetch_albion_fame(ig_name)
            except Exception:
                pass

            if fame_live:
                pve_val    = fame_live["pve"]
                pvp_val    = fame_live["pvp"]
                fame_label = ""
            elif profile and profile.get("current_pve_fame"):
                pve_val    = profile["current_pve_fame"]
                pvp_val    = profile["current_pvp_fame"]
                ts         = profile["fame_updated_at"]
                maj        = ts.strftime("%d/%m %H:%M") if ts else "?"
                fame_label = f" *(maj {maj})*"
            else:
                pve_val = pvp_val = None

            if pve_val is not None:
                embed.add_field(
                    name="⚔️ Fame PvP",
                    value=f"**{fmt_fame(pvp_val)}** total{fame_label}\n+{fmt_fame(max(0, pvp_val - pvp_init))} depuis recrutement",
                    inline=True,
                )
                embed.add_field(
                    name="🏰 Fame PvE",
                    value=f"**{fmt_fame(pve_val)}** total{fame_label}\n+{fmt_fame(max(0, pve_val - pve_init))} depuis recrutement",
                    inline=True,
                )
            else:
                embed.add_field(name="Fame Albion", value="*Indisponible — aucune donnée en cache*", inline=False)

        # ── Infos recrutement ─────────────────────────────────────────────────
        if recruitment_info:
            embed.add_field(name="📋 Infos recrutement", value=recruitment_info, inline=False)

        if joined_at:
            embed.set_footer(text=f"Recruté le {joined_at.strftime('%d/%m/%Y')}")

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Joueur(bot))
