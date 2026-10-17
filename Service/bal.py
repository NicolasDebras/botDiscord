import asyncio
import discord
from datetime import datetime
from discord.ext import commands
from discord import app_commands

import db
from config import ADMIN_ROLE_NAME, MEMBRE_ROLE_NAME
from Service.activites import activities
from Service.utils import is_admin, is_membre, ActivitySelect, append_bal_log, load_bal_log, notify_bal_limit, fmt_silver
import contextlib

# Labels affichés dans /ballog
ACTION_LABELS = {
    "addbal":               "➕ Ajout manuel",
    "retirebal":            "➖ Retrait manuel",
    "paybal":               "💰 PayBAL (activité)",
    "paybal_raid_ava":      "💰 PayBAL RAID AVA",
    "finacti":              "🏁 Fin d'activité",
    "finacti_raid_ava":     "🏁 Fin d'activité RAID AVA",
    "transferbal":          "🔄 Transfert entre joueurs",
}


# ══════════════════════════════════════════════════════════════════════════════
# COG BAL
# ══════════════════════════════════════════════════════════════════════════════
# Blague de guilde : /monbal remballe le joueur au lieu d'afficher son solde
# (solde visible sur le site, page Ma BAL ; les officiers ont /baljoueur).
BAL_JOKE = "connard, c'est mon bal"


class Bal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Guard admin ──────────────────────────────────────────────────────────
    async def check_admin(self, interaction: discord.Interaction) -> bool:
        if not is_admin(interaction.user):
            await interaction.response.send_message(
                f"⛔ Tu dois avoir le rôle **{ADMIN_ROLE_NAME}** pour utiliser cette commande.",
                ephemeral=True,
            )
            return False
        return True

    # =========================================================================
    # /addbal  — ajouter des BAL à un joueur
    # =========================================================================
    @app_commands.command(name="addbal", description="[ADMIN] Ajouter des BAL à un joueur")
    @app_commands.describe(joueur="Le joueur", montant="Montant à ajouter")
    async def addbal(self, interaction: discord.Interaction, joueur: discord.Member, montant: app_commands.Range[int, 1]):
        if not await self.check_admin(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        key       = str(joueur.id)
        new_total = await db.increment_bal(key, montant, guild_id=interaction.guild.id)
        await append_bal_log("addbal", interaction.user.display_name, [
            {"uid": key, "name": joueur.display_name, "delta": montant, "total": new_total}
        ], guild_id=interaction.guild.id)
        await notify_bal_limit(interaction.client, joueur.id, new_total, guild_id=interaction.guild.id)

        await interaction.followup.send(
            f"✅ **{joueur.display_name}** : +{fmt_silver(montant)} silver  (total : **{fmt_silver(new_total)} silver**)",
            ephemeral=True,
        )

    # =========================================================================
    # /retirebal  — retirer des BAL à un joueur
    # =========================================================================
    @app_commands.command(name="retirebal", description="[ADMIN] Retirer des BAL à un joueur")
    @app_commands.describe(joueur="Le joueur", montant="Montant à retirer")
    async def retirebal(self, interaction: discord.Interaction, joueur: discord.Member, montant: app_commands.Range[int, 1]):
        if not await self.check_admin(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        key    = str(joueur.id)
        ancien = await db.get_bal(key, guild_id=interaction.guild.id)
        reel   = min(montant, ancien)   # plancher à 0
        new_total = ancien - reel
        await db.set_bal(key, new_total, guild_id=interaction.guild.id)

        await append_bal_log("retirebal", interaction.user.display_name, [
            {"uid": key, "name": joueur.display_name, "delta": -reel, "total": new_total}
        ], guild_id=interaction.guild.id)
        await notify_bal_limit(interaction.client, joueur.id, new_total, guild_id=interaction.guild.id)

        await interaction.followup.send(
            f"✅ **{joueur.display_name}** : -{fmt_silver(reel)} silver  (total : **{fmt_silver(new_total)} silver**)",
            ephemeral=True,
        )

    # =========================================================================
    # /monbal  — voir son propre solde
    # =========================================================================
    @app_commands.command(name="monbal", description="Voir ton solde BAL")
    async def monbal(self, interaction: discord.Interaction):
        if not is_membre(interaction.user):
            await interaction.response.send_message(
                f"⛔ Tu dois avoir le rôle **{MEMBRE_ROLE_NAME}** pour utiliser cette commande.", ephemeral=True
            )
            return
        await interaction.response.send_message(BAL_JOKE, ephemeral=True)

    # =========================================================================
    # /baljoueur  — voir le solde BAL d'un joueur spécifique
    # =========================================================================
    @app_commands.command(name="baljoueur", description="[ADMIN] Voir le solde BAL d'un joueur")
    @app_commands.describe(joueur="Le joueur dont tu veux voir le solde")
    async def baljoueur(self, interaction: discord.Interaction, joueur: discord.Member):
        if not await self.check_admin(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        solde = await db.get_bal(str(joueur.id), guild_id=interaction.guild.id)
        await interaction.followup.send(
            f"💰 Solde BAL de **{joueur.display_name}** : **{fmt_silver(solde)} silver**",
            ephemeral=True,
        )

    # =========================================================================
    # /classement  — classement BAL du serveur
    # =========================================================================
    @app_commands.command(name="classement", description="Voir le classement BAL du serveur")
    async def classement(self, interaction: discord.Interaction):
        if not is_membre(interaction.user):
            await interaction.response.send_message(
                f"⛔ Tu dois avoir le rôle **{MEMBRE_ROLE_NAME}** pour utiliser cette commande.", ephemeral=True
            )
            return
        await interaction.response.defer()
        bal = await db.get_all_bal(guild_id=interaction.guild.id)
        if not bal:
            await interaction.followup.send("ℹ️ Aucune donnée BAL pour le moment.")
            return

        bot_id     = str(interaction.client.user.id)
        sorted_bal = sorted(
            [(uid, amt) for uid, amt in bal.items() if uid != bot_id and amt > 0],
            key=lambda x: x[1], reverse=True,
        )
        if not sorted_bal:
            await interaction.followup.send("ℹ️ Aucun solde positif pour le moment.")
            return

        medals = ["🥇", "🥈", "🥉"]
        lines  = []
        for i, (uid, amount) in enumerate(sorted_bal[:20]):
            prefix = medals[i] if i < 3 else f"**{i + 1}.**"
            member = interaction.guild.get_member(int(uid))
            name   = member.display_name if member else f"Inconnu ({uid})"
            lines.append(f"{prefix} {name} — **{amount:,}** BAL".replace(",", " "))

        embed = discord.Embed(title="🏆 Classement BAL", description="\n".join(lines), color=0xF1C40F)
        embed.set_footer(text=f"{len(sorted_bal)} joueurs au total")
        await interaction.followup.send(embed=embed)

    # =========================================================================
    # /paybal  — distribuer les BAL aux participants d'une activité
    # =========================================================================
    @app_commands.command(name="paybal", description="[ADMIN] Distribuer des BAL aux participants d'une activité")
    @app_commands.describe(montant="Montant BAL par participant")
    async def paybal(self, interaction: discord.Interaction, montant: app_commands.Range[int, 1]):
        if not await self.check_admin(interaction):
            return

        if not activities:
            await interaction.response.send_message("ℹ️ Aucune activité en cours.", ephemeral=True)
            return

        by   = interaction.user.display_name
        paid = False  # un /paybal = un seul paiement (la liste reste cliquable 60 s)

        async def on_select(inter: discord.Interaction, value: str):
            nonlocal paid
            if paid:
                await inter.response.send_message("ℹ️ Paiement déjà effectué — relance `/paybal` si besoin.", ephemeral=True)
                return
            if value == "none":
                await inter.response.send_message("ℹ️ Aucune activité disponible.", ephemeral=True)
                return

            msg_id = int(value)
            data   = activities.get(msg_id)
            if not data:
                await inter.response.send_message("❌ Activité introuvable.", ephemeral=True)
                return

            if not data.get("bal"):
                await inter.response.send_message(
                    "⚠️ Cette activité n'est pas marquée **BAL** — paiement annulé.", ephemeral=True
                )
                return

            participants = [
                (entry[0], entry[1])
                for members in data["slots"].values()
                for entry in members
            ]

            if not participants:
                await inter.response.send_message("ℹ️ Aucun participant inscrit à cette activité.", ephemeral=True)
                return

            paid = True  # posé avant tout await : un second clic est refusé
            view.stop()
            await inter.response.defer()
            with contextlib.suppress(discord.HTTPException):
                await interaction.edit_original_response(view=None)
            deltas      = {str(uid): montant for uid, _ in participants}
            new_totals  = await db.increment_bal_batch(deltas, guild_id=inter.guild.id)
            log_entries = [
                {"uid": str(uid), "name": name, "delta": montant, "total": new_totals[str(uid)]}
                for uid, name in participants
            ]

            await append_bal_log("paybal", by, log_entries, template=data.get("template", ""), guild_id=inter.guild.id)
            await asyncio.gather(*[
                notify_bal_limit(interaction.client, uid, new_totals[str(uid)], guild_id=inter.guild.id)
                for uid, _ in participants
            ])

            payes = [(uid, name, new_totals[str(uid)]) for uid, name in participants]
            lines = "\n".join(f"<@{uid}> +{montant} (total : **{total}**)" for uid, _, total in payes)
            embed = discord.Embed(
                title="💰 BAL distribués",
                description=f"**{montant} BAL** versés à {len(payes)} participant(s) :\n\n{lines}",
                color=0xF1C40F,
            )
            await inter.followup.send(embed=embed, delete_after=300)

        view = discord.ui.View(timeout=60)
        view.add_item(ActivitySelect(on_select, "💰 Quelle activité payer ?", guild_id=interaction.guild.id))
        await interaction.response.send_message(
            f"Choisis l'activité pour distribuer **{montant} BAL** par joueur :",
            view=view, ephemeral=True,
        )

    # =========================================================================
    # /transferbal  — s'échanger de la BAL entre membres
    # =========================================================================
    @app_commands.command(name="transferbal", description="Transférer de la BAL à un autre joueur")
    @app_commands.describe(joueur="Le joueur qui reçoit", montant="Montant à transférer")
    async def transferbal(
        self,
        interaction: discord.Interaction,
        joueur: discord.Member,
        montant: app_commands.Range[int, 1],
    ):
        if not is_membre(interaction.user):
            await interaction.response.send_message(
                f"⛔ Tu dois avoir le rôle **{MEMBRE_ROLE_NAME}** pour utiliser cette commande.", ephemeral=True
            )
            return

        if joueur.id == interaction.user.id:
            await interaction.response.send_message("❌ Tu peux pas te transférer de la BAL à toi-même.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        sender_key   = str(interaction.user.id)
        receiver_key = str(joueur.id)

        old_receiver = await db.get_bal(receiver_key, guild_id=interaction.guild.id)
        result = await db.transfer_bal(sender_key, receiver_key, montant, guild_id=interaction.guild.id)
        if result is None:
            solde_sender = await db.get_bal(sender_key, guild_id=interaction.guild.id)
            await interaction.followup.send(
                f"❌ Solde insuffisant. Tu as **{solde_sender:,} silver** de BAL, tu veux en transférer **{montant:,}**."
                .replace(",", " "), ephemeral=True
            )
            return
        new_sender, new_receiver = result

        await append_bal_log("transferbal", interaction.user.display_name, [
            {"uid": sender_key,   "name": interaction.user.display_name, "delta": -montant,  "total": new_sender},
            {"uid": receiver_key, "name": joueur.display_name,           "delta":  montant,  "total": new_receiver},
        ], guild_id=interaction.guild.id)

        await notify_bal_limit(interaction.client, interaction.user.id, new_sender, guild_id=interaction.guild.id)
        await notify_bal_limit(interaction.client, joueur.id, new_receiver, guild_id=interaction.guild.id)

        with contextlib.suppress(Exception):
            await joueur.send(
                f"💰 **{interaction.user.display_name}** t'a transféré **{fmt_silver(montant)} silver** depuis sa BAL.\n"
                f"Tu es passé de **{fmt_silver(old_receiver)}** à **{fmt_silver(new_receiver)} silver**."
            )

        await interaction.followup.send(
            f"✅ **{fmt_silver(montant)} silver** transférés à {joueur.mention} !\n"
            f"Ton nouveau solde : **{fmt_silver(new_sender)} silver**",
            ephemeral=True,
        )

    # =========================================================================
    # /ballog  — historique BAL sur 6 mois
    # =========================================================================
    @app_commands.command(name="ballog", description="[ADMIN] Voir l'historique des actions BAL (6 mois)")
    @app_commands.describe(
        page="Numéro de page (10 entrées par page, défaut : 1)",
        joueur="Filtrer pour un joueur spécifique (optionnel)",
        action="Filtrer par type d'action (optionnel)",
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="🏁 Fin d'activité",          value="finacti"),
        app_commands.Choice(name="➕ Ajout manuel",             value="addbal"),
        app_commands.Choice(name="➖ Retrait manuel",           value="retirebal"),
        app_commands.Choice(name="💰 PayBAL (activité)",        value="paybal"),
        app_commands.Choice(name="🔄 Transfert entre joueurs",  value="transferbal"),
    ])
    async def ballog(
        self,
        interaction: discord.Interaction,
        page:   app_commands.Range[int, 1] = 1,
        joueur: discord.Member | None = None,
        action: str | None = None,
    ):
        if not await self.check_admin(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        log = await load_bal_log(action=action, guild_id=interaction.guild.id)
        if not log:
            await interaction.followup.send("ℹ️ Aucune action BAL enregistrée.", ephemeral=True)
            return

        # Filtrage par joueur : on ne garde que les entrées qui le concernent
        if joueur:
            uid_str = str(joueur.id)
            filtered = []
            for entry in log:
                matching = [e for e in entry["entries"] if str(e["uid"]) == uid_str]
                if matching:
                    filtered.append({**entry, "entries": matching})
            log = filtered

        if not log:
            detail = joueur.mention if joueur else (ACTION_LABELS.get(action, action) if action else None)
            msg    = f"ℹ️ Aucune action BAL trouvée{f' pour {detail}' if detail else ''}."
            await interaction.followup.send(msg, ephemeral=True)
            return

        # log est déjà trié du plus récent au plus ancien (ORDER BY id DESC dans db.py)
        per_page   = 10
        total_page = max(1, (len(log) + per_page - 1) // per_page)
        page       = min(page, total_page)
        slice_     = log[(page - 1) * per_page : page * per_page]

        title = f"📋 Historique BAL  —  Page {page}/{total_page}"
        if joueur:
            title += f"  —  {joueur.display_name}"
        if action:
            title += f"  —  {ACTION_LABELS.get(action, action)}"

        embed = discord.Embed(title=title, color=0x3498DB)

        for entry in slice_:
            try:
                dt   = datetime.fromisoformat(entry["ts"])
                date = dt.strftime("%d/%m %H:%M")
            except Exception:
                date = entry["ts"]

            label   = ACTION_LABELS.get(entry["action"], entry["action"])
            title_f = f"{label}  ·  {date}  ·  par {entry['by']}"

            lines = []
            for e in entry["entries"][:5]:
                sign = "+" if e["delta"] >= 0 else ""
                lines.append(f"<@{e['uid']}> {sign}{e['delta']} → **{e['total']}**")
            if len(entry["entries"]) > 5:
                lines.append(f"*... et {len(entry['entries']) - 5} autre(s)*")

            embed.add_field(name=title_f, value="\n".join(lines) or "—", inline=False)

        footer = f"{len(log)} action(s)  •  historique 6 mois"
        embed.set_footer(text=footer)
        await interaction.followup.send(embed=embed, ephemeral=True)


    # =========================================================================
    # /statbal  — silver distribué sur une période
    # =========================================================================
    @app_commands.command(name="statbal", description="[ADMIN] Total silver distribué sur une période (défaut : 7 jours)")
    @app_commands.describe(jours="Période en jours (1–90, défaut : 7)")
    async def statbal(self, interaction: discord.Interaction, jours: app_commands.Range[int, 1, 90] = 7):
        if not await self.check_admin(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        rows = await db.get_silver_stats(jours, guild_id=interaction.guild.id)

        if not rows:
            await interaction.followup.send(f"ℹ️ Aucune distribution BAL sur les {jours} derniers jours.", ephemeral=True)
            return

        total_global = sum(r["total_silver"] for r in rows)

        embed = discord.Embed(
            title=f"📊 Silver distribué — {jours} dernier(s) jour(s)",
            color=0xF1C40F,
        )

        for r in rows:
            base_label = ACTION_LABELS.get(r["action"], r["action"])
            tpl = r.get("template", "")
            label = f"{base_label} — {tpl}" if tpl else base_label
            embed.add_field(
                name=label,
                value=f"**{fmt_silver(r['total_silver'])}** silver\n{r['nb_actions']} action(s) · {r['nb_joueurs']} joueur(s)",
                inline=True,
            )

        embed.add_field(
            name="─────────────────",
            value=f"**Total : {fmt_silver(total_global)} silver**",
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


# ── SETUP ─────────────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(Bal(bot))
