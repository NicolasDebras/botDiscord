import asyncio
import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from discord import app_commands

import db
from albion_api import fetch_albion_fame, fmt_fame
from config import ADMIN_ROLE_NAME, MEMBRE_ROLE_NAME, RECRUTEUR_ROLE_ID

_PARIS          = ZoneInfo("Europe/Paris")
_RAPPEL_HEURE   = datetime.time(hour=22, minute=0, tzinfo=_PARIS)
_RAPPEL_SALON   = 1505623773708025992
_RECRUTEUR_ROLE = 1473779038106685568


def _is_recruteur_or_admin(member: discord.Member) -> bool:
    return (
        member.guild_permissions.administrator
        or any(r.id == _RECRUTEUR_ROLE or r.name == ADMIN_ROLE_NAME for r in member.roles)
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

            # Rafraîchir le pseudo IG via l'API Albion (gère les changements de pseudo)
            if p["ig_name"]:
                try:
                    fame = await fetch_albion_fame(p["ig_name"])
                    if fame and fame["name"].lower() != p["ig_name"].lower():
                        await db.update_player_igname(p["user_id"], fame["name"])
                except Exception:
                    pass
                await asyncio.sleep(0.5)  # évite le rate-limit API

        # ── 2. Rappel nouveaux joueurs ────────────────────────────────────────
        pending = await db.get_pending_new_players(min_days=14)

        ping = f"<@&{_RECRUTEUR_ROLE}>"

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
        nouvelle_date = profile["joined_at"] + datetime.timedelta(days=7)
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
