import discord
from discord.ext import commands
from discord import app_commands

import db

_RECRUTEMENT_GUILD_ID = 1479604079754743970
_FORUM_CHANNEL_ID     = 1511837675974561942
_RULES_CHANNEL_ID     = 1511837232435171430
_CANDIDAT_ROLE_ID     = 1511832805665931334


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

        forum = interaction.client.get_channel(_FORUM_CHANNEL_ID)
        if not isinstance(forum, discord.ForumChannel):
            await interaction.followup.send("❌ Forum introuvable. Contacte un recruteur.", ephemeral=True)
            return

        # Vérifier si un ticket existe déjà
        existing = await db.get_recruitment_ticket(str(interaction.user.id))
        if existing:
            thread = interaction.client.get_channel(existing)
            if thread:
                await interaction.followup.send(
                    f"⚠️ Tu as déjà une candidature en cours : {thread.mention}", ephemeral=True
                )
                return

        # Créer le thread dans le forum
        embed = discord.Embed(
            title=f"📋 Candidature — {self.pseudo_ig.value}",
            color=0x3498DB,
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="🎮 Pseudo IG",                      value=self.pseudo_ig.value,  inline=False)
        embed.add_field(name="🔍 Comment nous as-tu découvert ?", value=self.decouverte.value, inline=False)
        embed.add_field(name="🕐 Disponibilités",                 value=self.dispo.value,      inline=False)
        embed.add_field(name="⚔️ Contenu favori",                 value=self.contenu.value,    inline=False)
        embed.add_field(name="🏰 Recherche dans une guilde",      value=self.recherche.value,  inline=False)
        embed.set_footer(text=f"Discord : {interaction.user} ({interaction.user.id})")

        thread, _ = await forum.create_thread(
            name=f"{self.pseudo_ig.value} — Candidature",
            embed=embed,
        )
        await db.save_recruitment_ticket(str(interaction.user.id), thread.id)

        await interaction.followup.send(
            f"✅ Ta candidature a bien été envoyée ! Nos recruteurs reviendront vers toi prochainement.",
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


# ── COG ───────────────────────────────────────────────────────────────────────
class RecrutementExterne(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(RecrutementView())

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild.id != _RECRUTEMENT_GUILD_ID:
            return
        candidat_role = member.guild.get_role(_CANDIDAT_ROLE_ID)
        if candidat_role:
            try:
                await member.add_roles(candidat_role)
            except discord.Forbidden:
                pass

    @app_commands.command(
        name="setup-recrutement",
        description="[ADMIN] Poster le message de recrutement dans le canal dédié",
    )
    async def setup_recrutement(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
            return

        channel = self.bot.get_channel(_RULES_CHANNEL_ID)
        if not channel:
            await interaction.response.send_message("❌ Canal introuvable.", ephemeral=True)
            return

        embed = discord.Embed(
            title="⚔️ Rejoindre la guilde",
            description=(
                "Bienvenue !\n\n"
                "Pour déposer ta candidature, clique sur le bouton ci-dessous.\n"
                "Un formulaire s'ouvrira avec quelques questions rapides.\n\n"
                "Nos recruteurs examineront ta candidature et te contacteront pour la suite."
            ),
            color=0xF1C40F,
        )

        await channel.send(embed=embed, view=RecrutementView())
        await interaction.response.send_message("✅ Message de recrutement posté.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(RecrutementExterne(bot))
