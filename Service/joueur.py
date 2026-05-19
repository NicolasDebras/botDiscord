import asyncio
import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from discord import app_commands

import db
from albion_api import fetch_albion_fame, fmt_fame
from config import ADMIN_ROLE_NAME, MEMBRE_ROLE_NAME, RECRUTEUR_ROLE_ID, GM_ROLE_NAME
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

    # ── Tâche 22h ─────────────────────────────────────────────────────────────
    @tasks.loop(time=_RAPPEL_HEURE)
    async def rappel_nouveaux(self):
        channel = self.bot.get_channel(_RAPPEL_SALON)
        if not channel:
            return

        guild    = channel.guild
        profiles = await db.get_all_profiles()
        now      = datetime.datetime.now(datetime.timezone.utc)
        une_semaine = datetime.timedelta(days=7)

        # ── 1. Mise à jour des profils ────────────────────────────────────────
        for p in profiles:
            member = guild.get_member(int(p["user_id"]))

            # Parti du Discord depuis > 1 semaine → on supprime le profil
            if member is None:
                if p["joined_at"] and (now - p["joined_at"]) > une_semaine:
                    await db.delete_player_profile(p["user_id"])
                continue

            # Mettre à jour is_membre selon le rôle Discord actuel
            est_membre = any(r.name == MEMBRE_ROLE_NAME for r in member.roles)
            if est_membre != p["is_membre"]:
                await db.set_player_is_membre(p["user_id"], est_membre)

            # Rafraîchir fame + pseudo IG via l'API Albion
            if p["ig_name"]:
                try:
                    fame = await fetch_albion_fame(p["ig_name"])
                    if fame:
                        await db.update_player_fame(p["user_id"], fame["name"], fame["pve"], fame["pvp"])
                except Exception:
                    pass
                await asyncio.sleep(0.5)  # évite le rate-limit API

        # ── 2. Rappel nouveaux joueurs ────────────────────────────────────────
        pending = await db.get_pending_new_players(min_days=14)

        ping = f"<@&{RECRUTEUR_ROLE_ID}>"

        if not pending:
            await channel.send(f"{ping}\n✅ Aucun nouveau joueur à suivre cette semaine.")
            return

        lines = []
        for p in pending:
            member  = guild.get_member(int(p["user_id"]))
            mention = member.mention if member else f"*(parti — ID {p['user_id']})*"
            ig      = f"**{p['ig_name']}**" if p["ig_name"] else "*pseudo IG inconnu*"
            depuis  = p["joined_at"].strftime("%d/%m/%Y")
            lines.append(f"• {ig} — {mention} — recruté le {depuis}")

        await channel.send(
            f"{ping}\n"
            f"🆕 **Suivi nouveaux joueurs — recrutés il y a plus de 2 semaines** ({len(pending)})\n"
            f"Pensez à vérifier leur activité et à leur donner le rôle **{MEMBRE_ROLE_NAME}** si tout est bon.\n\n"
            + "\n".join(lines)
        )

    @rappel_nouveaux.before_loop
    async def before_rappel(self):
        await self.bot.wait_until_ready()

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
        is_gm = (
            interaction.user.guild_permissions.administrator
            or any(r.name == GM_ROLE_NAME for r in interaction.user.roles)
        )
        if not is_gm:
            await interaction.response.send_message(
                "⛔ Cette commande est réservée au **Maître de guilde**.", ephemeral=True
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
        statut = "🆕 Nouveau joueur" if not is_membre else "✅ Membre"
        embed.add_field(name="📋 Statut", value=statut, inline=True)

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
