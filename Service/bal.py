import discord
from datetime import datetime
from discord.ext import commands
from discord import app_commands

import db
from config import ADMIN_ROLE_NAME, MEMBRE_ROLE_NAME
from Service.activites import activities
from Service.utils import is_admin, is_membre, ActivitySelect, append_bal_log, load_bal_log

# Labels affichés dans /ballog
ACTION_LABELS = {
    "addbal":    "➕ Ajout manuel",
    "retirebal": "➖ Retrait manuel",
    "paybal":    "💰 PayBAL (activité)",
    "finacti":   "🏁 Fin d'activité",
}


# ══════════════════════════════════════════════════════════════════════════════
# COG BAL
# ══════════════════════════════════════════════════════════════════════════════
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

        key       = str(joueur.id)
        new_total = await db.increment_bal(key, montant)
        await append_bal_log("addbal", interaction.user.display_name, [
            {"uid": key, "name": joueur.display_name, "delta": montant, "total": new_total}
        ])

        await interaction.response.send_message(
            f"✅ **{joueur.display_name}** : +{montant} BAL  (total : **{new_total}**)",
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

        key    = str(joueur.id)
        ancien = await db.get_bal(key)
        reel   = min(montant, ancien)   # plancher à 0
        await db.set_bal(key, ancien - reel)

        await append_bal_log("retirebal", interaction.user.display_name, [
            {"uid": key, "name": joueur.display_name, "delta": -reel, "total": ancien - reel}
        ])

        await interaction.response.send_message(
            f"✅ **{joueur.display_name}** : -{reel} BAL  (total : **{ancien - reel}**)",
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
        solde = await db.get_bal(str(interaction.user.id))
        name  = interaction.user.display_name.lower()
        solde_fmt = f"{solde:,}".replace(",", " ")

        easter_eggs = {
            "lilium122": f"👑 Ah, le chef en personne… Ton solde BAL : **{solde_fmt}**. On espère que c'est à la hauteur de ton ego.",
            "naej":      f"🏹 Tiens, le sniper de service. Ton solde BAL : **{solde_fmt}**. Essaie de ne pas tout dépenser en flèches.",
            "arcwolf":   f"🐺 Le loup rôde… Ton solde BAL : **{solde_fmt}**. Toujours à l'affût du bon coup.",
        }

        msg = next((v for k, v in easter_eggs.items() if k in name), f"💰 Ton solde BAL : **{solde_fmt}**")
        await interaction.response.send_message(msg, ephemeral=True)

    # =========================================================================
    # /baljoueur  — voir le solde BAL d'un joueur spécifique
    # =========================================================================
    @app_commands.command(name="baljoueur", description="[ADMIN] Voir le solde BAL d'un joueur")
    @app_commands.describe(joueur="Le joueur dont tu veux voir le solde")
    async def baljoueur(self, interaction: discord.Interaction, joueur: discord.Member):
        if not await self.check_admin(interaction):
            return
        solde = await db.get_bal(str(joueur.id))
        await interaction.response.send_message(
            f"💰 Solde BAL de **{joueur.display_name}** : **{solde:,}**".replace(",", " "),
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
        bal = await db.get_all_bal()
        if not bal:
            await interaction.response.send_message("ℹ️ Aucune donnée BAL pour le moment.", ephemeral=True)
            return

        sorted_bal = sorted(bal.items(), key=lambda x: x[1], reverse=True)
        medals     = ["🥇", "🥈", "🥉"]
        lines      = []
        for i, (uid, amount) in enumerate(sorted_bal[:20]):
            prefix = medals[i] if i < 3 else f"**{i + 1}.**"
            member = interaction.guild.get_member(int(uid))
            name   = member.display_name if member else f"Inconnu ({uid})"
            lines.append(f"{prefix} {name} — **{amount:,}** BAL".replace(",", " "))

        embed = discord.Embed(title="🏆 Classement BAL", description="\n".join(lines), color=0xF1C40F)
        embed.set_footer(text=f"{len(sorted_bal)} joueurs au total")
        await interaction.response.send_message(embed=embed, delete_after=300)

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

        by = interaction.user.display_name

        async def on_select(inter: discord.Interaction, value: str):
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

            payes: list[tuple[int, str, int]] = []
            log_entries = []

            for members in data["slots"].values():
                for entry in members:
                    uid, name = entry[0], entry[1]
                    key       = str(uid)
                    new_total = await db.increment_bal(key, montant)
                    payes.append((uid, name, new_total))
                    log_entries.append({"uid": key, "name": name, "delta": montant, "total": new_total})

            if not payes:
                await inter.response.send_message("ℹ️ Aucun participant inscrit à cette activité.", ephemeral=True)
                return

            await append_bal_log("paybal", by, log_entries)

            lines = "\n".join(f"<@{uid}> +{montant} (total : **{total}**)" for uid, _, total in payes)
            embed = discord.Embed(
                title="💰 BAL distribués",
                description=f"**{montant} BAL** versés à {len(payes)} participant(s) :\n\n{lines}",
                color=0xF1C40F,
            )
            await inter.response.send_message(embed=embed, delete_after=300)

        view = discord.ui.View(timeout=60)
        view.add_item(ActivitySelect(on_select, "💰 Quelle activité payer ?"))
        await interaction.response.send_message(
            f"Choisis l'activité pour distribuer **{montant} BAL** par joueur :",
            view=view, ephemeral=True,
        )

    # =========================================================================
    # /ballog  — historique des 100 dernières actions BAL
    # =========================================================================
    @app_commands.command(name="ballog", description="[ADMIN] Voir l'historique des actions BAL")
    @app_commands.describe(page="Numéro de page (10 entrées par page, défaut : 1)")
    async def ballog(self, interaction: discord.Interaction, page: app_commands.Range[int, 1] = 1):
        if not await self.check_admin(interaction):
            return

        log = await load_bal_log()
        if not log:
            await interaction.response.send_message("ℹ️ Aucune action BAL enregistrée.", ephemeral=True)
            return

        # log est déjà trié du plus récent au plus ancien (ORDER BY id DESC dans db.py)
        per_page   = 10
        total_page = max(1, (len(log) + per_page - 1) // per_page)
        page       = min(page, total_page)
        slice_     = log[(page - 1) * per_page : page * per_page]

        embed = discord.Embed(
            title=f"📋 Historique BAL  —  Page {page}/{total_page}",
            color=0x3498DB,
        )

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

        embed.set_footer(text=f"{len(log)} action(s) au total  •  max 100 conservées")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ── SETUP ─────────────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(Bal(bot))
