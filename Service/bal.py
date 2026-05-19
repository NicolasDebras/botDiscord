import asyncio
import random
import discord
from datetime import datetime
from discord.ext import commands
from discord import app_commands

import db
from config import ADMIN_ROLE_NAME, MEMBRE_ROLE_NAME
from Service.activites import activities
from Service.utils import is_admin, is_membre, ActivitySelect, append_bal_log, load_bal_log, notify_bal_limit, fmt_silver

# Labels affichés dans /ballog
ACTION_LABELS = {
    "addbal":      "➕ Ajout manuel",
    "retirebal":   "➖ Retrait manuel",
    "paybal":      "💰 PayBAL (activité)",
    "finacti":     "🏁 Fin d'activité",
    "transferbal": "🔄 Transfert entre joueurs",
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

        await interaction.response.defer(ephemeral=True)

        key       = str(joueur.id)
        new_total = await db.increment_bal(key, montant)
        await append_bal_log("addbal", interaction.user.display_name, [
            {"uid": key, "name": joueur.display_name, "delta": montant, "total": new_total}
        ])
        await notify_bal_limit(interaction.client, joueur.id, new_total)

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
        ancien = await db.get_bal(key)
        reel   = min(montant, ancien)   # plancher à 0
        new_total = ancien - reel
        await db.set_bal(key, new_total)

        await append_bal_log("retirebal", interaction.user.display_name, [
            {"uid": key, "name": joueur.display_name, "delta": -reel, "total": new_total}
        ])
        await notify_bal_limit(interaction.client, joueur.id, new_total)

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
        await interaction.response.defer(ephemeral=True)
        solde     = await db.get_bal(str(interaction.user.id))
        name      = interaction.user.display_name.lower()
        solde_fmt = f"{solde:,}".replace(",", " ")

        # ── Easter eggs joueurs ───────────────────────────────────────────
        easter_eggs = {
            "lilium122": random.choice([
                f"👑 Ah, le chef en personne… **{solde_fmt} silver**. On espère que c'est à la hauteur de ton ego. (c'est pas possible de toute façon)",
                f"😤 **{solde_fmt} silver**. T'es déjà en train de faire croire que c'est grâce à toi si la guilde tourne. C'est mignon.",
                f"🎭 **{solde_fmt} silver**. Tu vas encore faire un discours sur tes mérites ? On t'écoute... non en fait on t'écoute pas.",
                f"📣 **{solde_fmt} silver**. T'as déjà informé tout le monde 3 fois ce soir. On sait, Lilium. On sait.",
                f"🦚 **{solde_fmt} silver**. Impressionnant. Presque autant que ton ego. Presque.",
            ]),
            "naej": random.choice([
                f"🏹 Tiens, le vieux GM reprend du service. **{solde_fmt} silver**. Essaie de pas tout dépenser avant la retraite.",
                f"👴 **{solde_fmt} silver**. *'De mon temps on farmait avec les pieds et on était content.'* C'est toi qui vas dire ça un jour.",
                f"🏺 **{solde_fmt} silver**. Tu veilles. Tu juges. Tu te souviens d'un temps où les pixels coûtaient moins cher.",
                f"☕ **{solde_fmt} silver**. T'as vérifié ta BAL entre deux doléances sur l'ancienne meta. Respect quand même.",
                f"📜 **{solde_fmt} silver**. T'as parlé. Les anciens se souviennent. Les jeunes s'en foutent. C'est l'ordre des choses.",
            ]),
            "arcwolf": random.choice([
                f"💅 **{solde_fmt} silver**. Les riches vérifient quand même, on sait jamais.",
                f"💰 **{solde_fmt} silver**. Tu regardes ça comme si c'était de la monnaie de poche. Pour toi c'est probablement le cas.",
                f"🐺 **{solde_fmt} silver**. Toujours au top, toujours classe. T'es la star de la guilde et tu le sais.",
                f"👛 **{solde_fmt} silver**. T'as vérifié juste pour t'assurer que t'es toujours la plus riche. Spoiler : probablement oui.",
                f"💎 **{solde_fmt} silver**. Le reste de la guilde farm pour atteindre ton niveau. Toi, tu farm par habitude.",
            ]),
            "g3": random.choice([
                f"😤 **{solde_fmt} silver**. Au moins ta BAL elle répond, contrairement aux DPS de ton dernier raid.",
                f"📢 **{solde_fmt} silver**. *'LES DPS ILS BOUGENT PAS, ILS FARM PAS, ILS...'* — Toi, en permanence.",
                f"🤬 **{solde_fmt} silver**. T'as vérifié ta BAL entre deux plaintes sur les DPS. La constance, respect.",
                f"⚔️ **{solde_fmt} silver**. Les DPS vont encore t'entendre ce soir, c'est sûr.",
                f"🎙️ **{solde_fmt} silver**. T'as la BAL, t'as la voix, t'as les plaintes. Le package complet.",
            ]),
        }
        egg = next((v for k, v in easter_eggs.items() if k in name), None)
        if egg:
            await interaction.followup.send(egg, ephemeral=True)
            return

        # ── Messages selon le solde ───────────────────────────────────────
        M = 1_000_000
        s = f"**{solde_fmt} silver**"

        if solde == 0:
            msg = random.choice([
                f"💸 {s}… T'as même pas un radis. Va farmer au lieu de traîner ici.",
                f"🪹 {s}. Vide. Comme ton inventaire et ta vie sociale.",
                f"😂 {s}. Bro t'as même pas participé une seule fois ? Sérieusement ?",
                f"🦗 {s}. On entend les grillons dans ton portefeuille.",
                f"💀 {s}. Financièrement décédé. Repose en paix.",
                f"🙈 {s}. G3 a raison sur les DPS, et toi t'as même pas la BAL pour lui répondre.",
                f"🫙 {s}. Même le coffre de guilde est plus riche que toi. C'est triste vraiment.",
                f"👻 {s}. T'es un fantôme dans les raids ET dans la BAL. Double performance.",
            ])
        elif solde < 2 * M:
            msg = random.choice([
                f"🪙 {s}. C'est… quelque chose. Continue d'essayer.",
                f"😬 {s}. T'as participé une fois et tu viens vérifier toutes les 5 minutes hein.",
                f"🐣 {s}. Bébé farmer. Mignon. Inutile, mais mignon.",
                f"📉 {s}. Les marchés ont vu mieux. Toi aussi on espère.",
                f"🙃 {s}. C'est un début… très très humble.",
                f"🙃 {s}. Plus pauvre que Beban, je ne pensais pas que c'était possible.",
                f"🤡 {s}. T'as pas honte de vérifier ça ? Retourne farmer.",
                f"🧸 {s}. Adorable. Complètement inutile financièrement, mais adorable.",
            ])
        elif solde < 5 * M:
            msg = random.choice([
                f"🪙 {s}. C'est tout ? Même les recrues font mieux.",
                f"😐 {s}. Tu existes, à peine. Keep going.",
                f"🐌 {s}. Tu farm au ralenti ou c'est juste toi ?",
                f"📦 {s}. Du potentiel. Enfoui très très profond.",
                f"🤏 {s}. Un peu. Vraiment un peu.",
                f"🧱 {s}. Solide comme un mur. Un mur en carton.",
                f"😑 {s}. G3 te demanderait pas de jouer DPS avec une BAL pareille. Soyons honnêtes.",
                f"🐢 {s}. T'avances. Lentement. Très lentement. Mais t'avances.",
            ])
        elif solde < 7 * M:
            msg = random.choice([
                f"📦 {s}. Moyen. Tu commences à exister, à peine.",
                f"🙂 {s}. La moyenne syndicale. Félicitations je suppose.",
                f"🤷 {s}. Pas ouf, pas nul. Tu es quelqu'un de très quelconque.",
                f"📊 {s}. Statistiquement dans la moyenne. C'est déjà ça.",
                f"😑 {s}. Tu fais le minimum et ça se voit.",
                f"🥱 {s}. Bof. T'as survécu, c'est l'essentiel.",
                f"🎯 {s}. Dans la moyenne. Ni honte ni fierté. Juste... là.",
                f"🌫️ {s}. Tu passes inaperçu. Comme toujours. C'est ton super-pouvoir.",
            ])
        elif solde < 10 * M:
            msg = random.choice([
                f"⚔️ {s}. Pas mal, tu participes au moins.",
                f"💪 {s}. On commence à te remarquer. Continue.",
                f"🗡️ {s}. Solide effort. T'es pas une charge pour la guilde, c'est déjà bien.",
                f"👀 {s}. Tiens tiens. Quelqu'un qui bosse. Rare.",
                f"😏 {s}. Pas mal du tout. T'es clairement là quand ça compte.",
                f"🔥 {s}. T'es dans les bons élèves. Enfin un peu.",
                f"💡 {s}. Respectable. Pas au niveau d'Arc évidemment, mais respectable.",
                f"🎖️ {s}. T'as de la gueule. Même G3 ne peut pas se plaindre de toi. Enfin, il va quand même le faire.",
            ])
        elif solde < 15 * M:
            msg = random.choice([
                f"💰 {s}. Solide. La guilde peut compter sur toi.",
                f"🔥 {s}. En forme. On aime voir ça.",
                f"🏅 {s}. Au-dessus de la moyenne. Tu te la pètes un peu mais c'est mérité.",
                f"😎 {s}. Classe. Vraiment classe.",
                f"💼 {s}. Professionnel. On apprécie.",
                f"💰 {s}. Solide. Pense à faire un don à Beban...",
                f"🦅 {s}. T'as travaillé dur. Même G3 ne peut pas se plaindre. Même si il va essayer.",
                f"🏹 {s}. Naej serait fier... s'il se souvenait de ton nom.",
            ])
        elif solde < 20 * M:
            msg = random.choice([
                f"🏆 {s}. Gros farmer détecté. Respect.",
                f"🚀 {s}. T'es en mode no-life et ça se voit. Chapeau.",
                f"👑 {s}. La guilde t'aime. Vraiment.",
                f"🤑 {s}. Riche. Genre vraiment riche pour un pixel.",
                f"🦁 {s}. Tu rugis, la bourse tremble.",
                f"💎 {s}. Élite. Arc commence à te regarder d'un autre œil.",
                f"🎖️ {s}. Impressionnant. Même Naej a lâché son café en voyant ça.",
                f"🌟 {s}. T'as pas de vie mais t'as une BAL. C'est un choix de vie valable.",
            ])
        elif solde < 30 * M:
            msg = random.choice([
                f"💎 {s}. T'as dépassé les 20M. Arc a vérifié sa propre BAL par réflexe.",
                f"🤯 {s}. On pensait que seul Arc avait autant. T'as du talent ou pas de vie — dans les deux cas, respect.",
                f"🦈 {s}. T'es un prédateur financier maintenant. La guilde te regarde autrement.",
                f"🏦 {s}. Les 30 millions dans le viseur. Arc vient de recalculer son avance.",
                f"👁️ {s}. Les gens commencent à chuchoter ton nom dans les raids. C'est du respect ou de la jalousie.",
                f"🧲 {s}. Richissime. G3 va arrêter de râler sur toi pour râler sur les autres.",
                f"💰 {s}. T'es dans le top tier. Même Lilium122 te regarde de travers.",
            ])
        elif solde < 50 * M:
            msg = random.choice([
                f"💎 {s}. Tu es une machine. T'as pas de vie ou quoi ?",
                f"🧠 {s}. Calculateur. Implacable. Légèrement flippant.",
                f"🤖 {s}. T'es un bot ? Personne farm autant normalement.",
                f"😱 {s}. On est impressionné et inquiet à la fois.",
                f"🏦 {s}. À ce stade t'es toi-même une institution financière.",
                f"🔱 {s}. Arc t'a envoyé un message privé pour te demander tes secrets. Elle nie.",
                f"💫 {s}. Légendaire. Même Naej arrête de parler de l'ancien temps pour parler de toi.",
                f"🌙 {s}. T'as plus besoin de travailler. Enfin si, t'es dans un jeu, mais tu vois l'idée.",
            ])
        elif solde < 75 * M:
            msg = random.choice([
                f"🌟 {s}. 75 millions dans le radar. T'as officiellement plus de silver que de sens commun.",
                f"👑 {s}. Arc a vérifié ta BAL, s'est sentie pauvre, et est allée farmer. Tu lui as rendu service.",
                f"🚁 {s}. À ce niveau de richesse t'arrives en hélico aux raids. C'est légitime.",
                f"🦋 {s}. Transformation complète. De simple membre à pilier financier de la guilde.",
                f"⚡ {s}. T'es devenu une légende urbaine. Les recrues racontent des histoires sur toi.",
                f"🌌 {s}. Naej t'a félicité. C'est sa façon de dire qu'il est jaloux mais digne.",
                f"🏆 {s}. G3 a arrêté de râler sur les DPS pour râler sur toi. Prends ça comme un honneur.",
                f"💼 {s}. Arc a organisé une réunion pour comprendre comment t'as fait. Elle a pris des notes.",
            ])
        elif solde < 100 * M:
            msg = random.choice([
                f"🌌 {s}. Presque 100 millions. T'as plus besoin de jouer, t'es la guilde maintenant.",
                f"😵 {s}. On sait même pas quoi dire. T'as sacrifié QUOI pour farm autant ?",
                f"👽 {s}. T'es pas humain. On a pas vérifié, mais on se pose la question.",
                f"💼 {s}. Arc a organisé un séminaire 'comment atteindre ce niveau'. Elle sait pas non plus.",
                f"🔮 {s}. Lilium122 a essayé de faire croire que c'était grâce à lui. On lui a dit de se taire.",
                f"📜 {s}. Naej a sorti ses lunettes pour bien lire le chiffre. Il a dit 'de mon temps on farmait pas autant'. Classique.",
                f"⭐ {s}. G3 râle toujours sur les DPS mais il te parle avec respect maintenant. C'est dire.",
                f"🎯 {s}. T'as presque atteint le mythe. Arc est ton seule rival. Elle le sait. Toi aussi.",
            ])
        else:
            msg = random.choice([
                f"👑 {s}. Légende vivante. On parle de toi dans les tavernes.",
                f"🌌 {s}. T'as transcendé le jeu. Tu ES le jeu.",
                f"🥇 {s}. Historique. Quelqu'un devrait écrire un livre.",
                f"😵 {s}. On sait même pas quoi dire. Chapeau l'artiste.",
                f"⚡ {s}. À ce niveau c'est plus du farming, c'est de l'art.",
                f"🏛️ {s}. 100 MILLIONS. Arc a revérifié sa BAL. Naej a dit 'c'était mieux de mon temps'. G3 râle. Lilium122 revendique la paternité de ton succès. La guilde est en feu.",
                f"🌠 {s}. T'as atteint la transcendance financière. La guilde ne peut plus rien pour toi. Tu ES la guilde.",
                f"🎯 {s}. Cent millions. Arc pleure. G3 est muet pour une fois. Naej fait semblant de s'en foutre. Lilium122 se prend en photo à côté de toi. Tu gagnes.",
            ])

        await interaction.followup.send(msg, ephemeral=True)

    # =========================================================================
    # /baljoueur  — voir le solde BAL d'un joueur spécifique
    # =========================================================================
    @app_commands.command(name="baljoueur", description="[ADMIN] Voir le solde BAL d'un joueur")
    @app_commands.describe(joueur="Le joueur dont tu veux voir le solde")
    async def baljoueur(self, interaction: discord.Interaction, joueur: discord.Member):
        if not await self.check_admin(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        solde = await db.get_bal(str(joueur.id))
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
        bal = await db.get_all_bal()
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

            participants = [
                (entry[0], entry[1])
                for members in data["slots"].values()
                for entry in members
            ]

            if not participants:
                await inter.response.send_message("ℹ️ Aucun participant inscrit à cette activité.", ephemeral=True)
                return

            await inter.response.defer()
            deltas      = {str(uid): montant for uid, _ in participants}
            new_totals  = await db.increment_bal_batch(deltas)
            log_entries = [
                {"uid": str(uid), "name": name, "delta": montant, "total": new_totals[str(uid)]}
                for uid, name in participants
            ]

            await append_bal_log("paybal", by, log_entries)
            await asyncio.gather(*[
                notify_bal_limit(interaction.client, uid, new_totals[str(uid)])
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
        view.add_item(ActivitySelect(on_select, "💰 Quelle activité payer ?"))
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

        solde_sender = await db.get_bal(sender_key)
        if solde_sender < montant:
            await interaction.followup.send(
                f"❌ Solde insuffisant. Tu as **{solde_sender:,} silver** de BAL, tu veux en transférer **{montant:,}**."
                .replace(",", " "), ephemeral=True
            )
            return

        old_receiver = await db.get_bal(receiver_key)
        new_sender   = await db.increment_bal(sender_key, -montant)
        new_receiver = await db.increment_bal(receiver_key, montant)

        await append_bal_log("transferbal", interaction.user.display_name, [
            {"uid": sender_key,   "name": interaction.user.display_name, "delta": -montant,  "total": new_sender},
            {"uid": receiver_key, "name": joueur.display_name,           "delta":  montant,  "total": new_receiver},
        ])

        await notify_bal_limit(interaction.client, interaction.user.id, new_sender)
        await notify_bal_limit(interaction.client, joueur.id, new_receiver)

        try:
            await joueur.send(
                f"💰 **{interaction.user.display_name}** t'a transféré **{fmt_silver(montant)} silver** depuis sa BAL.\n"
                f"Tu es passé de **{fmt_silver(old_receiver)}** à **{fmt_silver(new_receiver)} silver**."
            )
        except Exception:
            pass

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

        log = await load_bal_log(action=action)
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


# ── SETUP ─────────────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(Bal(bot))
