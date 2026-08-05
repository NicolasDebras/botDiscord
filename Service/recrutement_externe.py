import re
import asyncio

import discord
from discord.ext import commands
from discord import app_commands

import db
from config import ADMIN_ROLE_NAME
from albion_api import fetch_albion_fame, fmt_fame


def _slugify(text: str) -> str:
    """Nettoie un nom de salon Discord (minuscules, tirets, sans caractères spéciaux)."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\-\s]", "", text)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return text[:90] or "candidature"


async def _is_staff(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    if any(r.name == ADMIN_ROLE_NAME for r in member.roles):
        return True
    cfg = await db.get_recruitment_config(member.guild.id)
    if cfg and cfg["recruitment_role_id"]:
        if any(r.id == cfg["recruitment_role_id"] for r in member.roles):
            return True
    return False


# ── MODAL QUESTIONNAIRE ───────────────────────────────────────────────────────
class QuestionnaireModal(discord.ui.Modal, title="📋 Questionnaire de candidature"):
    pseudo_ig = discord.ui.TextInput(
        label="Pseudo IG",
        placeholder="Ton pseudo dans Albion Online",
        required=True,
        max_length=50,
    )
    decouverte = discord.ui.TextInput(
        label="Comment nous as-tu découvert ?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=300,
    )
    dispo = discord.ui.TextInput(
        label="Quand est-ce que tu joues en général ?",
        placeholder="Jours, soirs, nuit / semaine, week end ?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=200,
    )
    contenu = discord.ui.TextInput(
        label="Quel contenu aimes-tu faire ?",
        placeholder="PVE, PVP, etc ?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=200,
    )
    recherche = discord.ui.TextInput(
        label="Que recherches-tu dans une guilde ?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=300,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        cfg   = await db.get_recruitment_config(guild.id)
        if not cfg:
            await interaction.followup.send(
                "❌ Le recrutement n'est pas configuré sur ce serveur. Contacte un administrateur.",
                ephemeral=True,
            )
            return

        # Vérifier si un ticket existe déjà
        existing = await db.get_recruitment_ticket(str(interaction.user.id), guild.id)
        if existing:
            channel = guild.get_channel(existing)
            if channel:
                await interaction.followup.send(
                    f"⚠️ Tu as déjà une candidature en cours : {channel.mention}", ephemeral=True
                )
                return

        fame = None
        try:
            fame = await fetch_albion_fame(self.pseudo_ig.value)
        except Exception:
            fame = None

        if fame:
            try:
                await interaction.user.edit(nick=fame["name"][:32], reason="Candidature — pseudo IG")
            except discord.Forbidden:
                pass

        category = guild.get_channel(cfg["category_id"]) if cfg["category_id"] else None
        if not isinstance(category, discord.CategoryChannel):
            category = None

        recruitment_role = guild.get_role(cfg["recruitment_role_id"]) if cfg["recruitment_role_id"] else None
        officier_role     = discord.utils.get(guild.roles, name=ADMIN_ROLE_NAME)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
        }
        if recruitment_role:
            overwrites[recruitment_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )
        if officier_role:
            overwrites[officier_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

        try:
            channel = await guild.create_text_channel(
                name=_slugify(f"candidature-{self.pseudo_ig.value}"),
                category=category,
                overwrites=overwrites,
                reason=f"Candidature de {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Le bot n'a pas la permission de créer un salon. Contacte un administrateur.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"📋 Candidature — {self.pseudo_ig.value}",
            color=0x3498DB,
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="🎮 Pseudo IG",                      value=self.pseudo_ig.value,  inline=False)
        if fame:
            embed.add_field(
                name="⚔️ Fame Albion",
                value=f"PvP : **{fmt_fame(fame['pvp'])}**\nPvE : **{fmt_fame(fame['pve'])}**",
                inline=False,
            )
        else:
            embed.add_field(name="⚔️ Fame Albion", value="*Joueur introuvable sur l'API Albion Online*", inline=False)
        embed.add_field(name="🔍 Comment nous as-tu découvert ?", value=self.decouverte.value, inline=False)
        embed.add_field(name="🕐 Disponibilités",                 value=self.dispo.value,      inline=False)
        embed.add_field(name="⚔️ Contenu favori",                 value=self.contenu.value,    inline=False)
        embed.add_field(name="🏰 Recherche dans une guilde",      value=self.recherche.value,  inline=False)
        embed.set_footer(text=f"Discord : {interaction.user} ({interaction.user.id})")

        mentions = interaction.user.mention
        if recruitment_role:
            mentions += f" {recruitment_role.mention}"

        await channel.send(content=mentions, embed=embed, view=ValidateCandidatureView())

        if fame:
            demande = (
                f"{interaction.user.mention} pour accélérer la validation, peux-tu nous envoyer :\n"
                f"• une capture d'écran de ton **écran d'accueil** (sélection de personnage)\n"
                f"• une capture de tes **stats** (fame PvP/PvE, équipement)\n\n"
                f"Merci ! 🙏"
            )
        else:
            demande = (
                f"{interaction.user.mention} on n'a pas réussi à retrouver **{self.pseudo_ig.value}** "
                f"sur l'API Albion Online.\n"
                f"Vérifie l'orthographe exacte de ton pseudo (majuscules/minuscules comprises) puis "
                f"utilise `/register` pour l'enregistrer.\n\n"
                f"Merci aussi de nous envoyer une capture d'écran de ton **écran d'accueil** et une "
                f"capture de tes **stats**."
            )
        await channel.send(demande)

        await db.save_recruitment_ticket(str(interaction.user.id), channel.id, guild.id)

        if fame:
            await db.save_player_profile(
                str(interaction.user.id),
                fame["name"],
                fame["pve"],
                fame["pvp"],
                self.recherche.value,
                is_membre=False,
                guild_id=guild.id,
            )

        await interaction.followup.send(
            f"✅ Ta candidature a bien été envoyée ! {channel.mention}",
            ephemeral=True,
        )


# ── VUE PERSISTANTE ───────────────────────────────────────────────────────────
class RecrutementView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📋 Déposer ma candidature",
        style=discord.ButtonStyle.primary,
        custom_id="recru_start",
    )
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(QuestionnaireModal())


# ── VUE PERSISTANTE : VALIDATION CANDIDATURE (STAFF) ──────────────────────────
class ValidateCandidatureView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="✅ Valider (Staff)",
        style=discord.ButtonStyle.success,
        custom_id="recru_validate",
    )
    async def validate(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _is_staff(interaction.user):
            await interaction.response.send_message(
                "⛔ Réservé au staff / rôle recrutement.", ephemeral=True
            )
            return

        candidat_id = await db.get_recruitment_ticket_user(interaction.channel.id)
        candidat     = interaction.guild.get_member(int(candidat_id)) if candidat_id else None
        cfg          = await db.get_recruitment_config(interaction.guild.id)
        mcfg         = await db.get_member_events_config(interaction.guild.id)

        if candidat:
            # ── Retirer les rôles "en cours" (candidat / rôle par défaut) ──────
            roles_a_retirer = []
            if cfg and cfg["candidat_role_id"]:
                r = interaction.guild.get_role(cfg["candidat_role_id"])
                if r and r in candidat.roles:
                    roles_a_retirer.append(r)
            if mcfg and mcfg["default_role_id"]:
                r = interaction.guild.get_role(mcfg["default_role_id"])
                if r and r in candidat.roles and r not in roles_a_retirer:
                    roles_a_retirer.append(r)

            if roles_a_retirer:
                try:
                    await candidat.remove_roles(*roles_a_retirer, reason="Candidature validée")
                except discord.Forbidden:
                    noms = ", ".join(r.name for r in roles_a_retirer)
                    print(
                        f"[recrutement] ⛔ Impossible de retirer les rôles ({noms}) à {candidat} sur {interaction.guild.name} — "
                        f"vérifie que le rôle du bot est bien AU-DESSUS de ces rôles dans la liste des rôles."
                    )

            # ── Attribuer le rôle de validation ─────────────────────────────────
            if cfg and cfg["validated_role_id"]:
                role = interaction.guild.get_role(cfg["validated_role_id"])
                if not role:
                    print(f"[recrutement] Rôle de validation introuvable (ID {cfg['validated_role_id']}) sur {interaction.guild.name}.")
                else:
                    try:
                        await candidat.add_roles(role, reason="Candidature validée")
                    except discord.Forbidden:
                        print(
                            f"[recrutement] ⛔ Impossible d'attribuer le rôle {role.name} à {candidat} sur {interaction.guild.name} — "
                            f"vérifie que le rôle du bot est bien AU-DESSUS de {role.name} dans la liste des rôles."
                        )

        await interaction.response.send_message(
            f"✅ Candidature validée par {interaction.user.mention} — ce salon va être fermé."
        )
        await db.delete_recruitment_ticket_by_channel(interaction.channel.id)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Candidature validée par {interaction.user}")
        except discord.Forbidden:
            pass


# ── COG ───────────────────────────────────────────────────────────────────────
class RecrutementExterne(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(RecrutementView())
        self.bot.add_view(ValidateCandidatureView())

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = await db.get_recruitment_config(member.guild.id)
        if not cfg or not cfg["candidat_role_id"]:
            return
        candidat_role = member.guild.get_role(cfg["candidat_role_id"])
        if not candidat_role:
            print(f"[recrutement] Rôle candidat introuvable (ID {cfg['candidat_role_id']}) sur {member.guild.name}.")
            return
        try:
            await member.add_roles(candidat_role)
        except discord.Forbidden:
            print(
                f"[recrutement] ⛔ Impossible d'attribuer le rôle {candidat_role.name} à {member} sur {member.guild.name} — "
                f"vérifie que le rôle du bot est bien AU-DESSUS de {candidat_role.name} dans la liste des rôles."
            )

    @app_commands.command(
        name="setup-recrutement",
        description="[ADMIN] Configurer et poster le message de recrutement sur ce serveur",
    )
    @app_commands.describe(
        salon_regles     = "Salon où poster le message de candidature",
        role_recrutement = "Rôle qui aura accès aux salons de candidature créés",
        role_candidat    = "Rôle attribué automatiquement aux nouveaux arrivants",
        categorie        = "Catégorie où créer les salons de candidature (optionnel)",
    )
    async def setup_recrutement(
        self,
        interaction: discord.Interaction,
        salon_regles: discord.TextChannel,
        role_recrutement: discord.Role,
        role_candidat: discord.Role,
        categorie: discord.CategoryChannel | None = None,
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
            return

        await db.set_recruitment_config(
            interaction.guild.id,
            salon_regles.id,
            role_recrutement.id,
            role_candidat.id,
            categorie.id if categorie else None,
        )

        embed = discord.Embed(
            title="⚔️ Rejoindre la guilde",
            description=(
                "Bienvenue !\n\n"
                "Pour déposer ta candidature, clique sur le bouton ci-dessous.\n"
                "Un formulaire s'ouvrira avec quelques questions rapides.\n\n"
                "Un salon privé sera créé pour ta candidature, visible par toi et nos recruteurs."
            ),
            color=0xF1C40F,
        )

        await salon_regles.send(embed=embed, view=RecrutementView())
        await interaction.response.send_message(
            f"✅ Recrutement configuré et message posté dans {salon_regles.mention}.", ephemeral=True
        )

    # =========================================================================
    # /register  — enregistrer / corriger son pseudo IG si l'API ne l'a pas trouvé
    # =========================================================================
    @app_commands.command(name="register", description="Enregistrer ou corriger ton pseudo in-game Albion Online")
    @app_commands.describe(pseudo="Ton pseudo exact dans Albion Online (sensible à la casse)")
    async def register(self, interaction: discord.Interaction, pseudo: str):
        await interaction.response.defer(ephemeral=True)

        existing = await db.get_player_profile(str(interaction.user.id), guild_id=interaction.guild.id)
        if existing:
            await interaction.followup.send(
                f"⚠️ Tu es déjà enregistré en tant que **{existing['ig_name']}**.\n"
                f"Contacte le staff (rôle recrutement) si tu dois corriger ton pseudo.",
                ephemeral=True,
            )
            return

        try:
            fame = await fetch_albion_fame(pseudo)
        except Exception:
            fame = None

        if not fame:
            await interaction.followup.send(
                f"❌ Joueur **{pseudo}** introuvable sur l'API Albion Online.\n"
                f"Vérifie l'orthographe exacte (majuscules/minuscules comprises) et réessaie avec `/register`.",
                ephemeral=True,
            )
            return

        try:
            await interaction.user.edit(nick=fame["name"][:32], reason="Pseudo IG enregistré via /register")
        except discord.Forbidden:
            pass

        await db.save_player_profile(
            str(interaction.user.id), fame["name"], fame["pve"], fame["pvp"],
            is_membre=False, guild_id=interaction.guild.id,
        )

        ticket_channel_id = await db.get_recruitment_ticket(str(interaction.user.id), interaction.guild.id)
        if ticket_channel_id:
            channel = interaction.guild.get_channel(ticket_channel_id)
            if channel:
                await channel.send(
                    f"✅ {interaction.user.mention} a enregistré son pseudo via `/register` : **{fame['name']}**\n"
                    f"PvP : {fmt_fame(fame['pvp'])} · PvE : {fmt_fame(fame['pve'])}"
                )

        await interaction.followup.send(
            f"✅ Pseudo enregistré : **{fame['name']}**\nPvP : {fmt_fame(fame['pvp'])} · PvE : {fmt_fame(fame['pve'])}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(RecrutementExterne(bot))
