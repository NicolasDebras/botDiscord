import discord
from discord.ext import commands

import db

_RECRUTEMENT_GUILD_ID = 1479604079754743970
_FORUM_CHANNEL_ID     = 1511837675974561942


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

    def __init__(self, thread_id: int):
        super().__init__()
        self.thread_id = thread_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        thread = interaction.client.get_channel(self.thread_id)
        if thread is None:
            try:
                thread = await interaction.client.fetch_channel(self.thread_id)
            except Exception:
                await interaction.followup.send(
                    "❌ Impossible de trouver ton fil de candidature. Contacte un recruteur.", ephemeral=True
                )
                return

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

        await thread.send(embed=embed)
        await db.delete_recruitment_ticket(str(interaction.user.id))
        await interaction.followup.send("✅ Ta candidature a bien été envoyée !", ephemeral=True)


# ── VUE PERSISTANTE (bouton DM) ───────────────────────────────────────────────
class QuestionnairePersistentView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📋 Remplir le questionnaire",
        style=discord.ButtonStyle.primary,
        custom_id="recru_questionnaire",
    )
    async def fill(self, interaction: discord.Interaction, button: discord.ui.Button):
        thread_id = await db.get_recruitment_ticket(str(interaction.user.id))
        if not thread_id:
            await interaction.response.send_message(
                "❌ Aucune candidature en attente trouvée. Contacte un recruteur.", ephemeral=True
            )
            return
        await interaction.response.send_modal(QuestionnaireModal(thread_id))


# ── COG ───────────────────────────────────────────────────────────────────────
class RecrutementExterne(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(QuestionnairePersistentView())

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild.id != _RECRUTEMENT_GUILD_ID:
            return

        forum = self.bot.get_channel(_FORUM_CHANNEL_ID)
        if not isinstance(forum, discord.ForumChannel):
            return

        # Créer le thread dans le forum
        thread, _ = await forum.create_thread(
            name=f"{member.display_name} — Candidature",
            content=(
                f"📥 Nouvelle candidature de {member.mention}\n"
                f"*(En attente du questionnaire…)*"
            ),
        )

        await db.save_recruitment_ticket(str(member.id), thread.id)

        # DM au joueur
        try:
            await member.send(
                "👋 **Bienvenue !**\n\n"
                "Pour rejoindre la guilde, merci de remplir le questionnaire de candidature "
                "en cliquant sur le bouton ci-dessous :",
                view=QuestionnairePersistentView(),
            )
        except discord.Forbidden:
            # DMs désactivés : poster le bouton directement dans le thread
            await thread.send(
                f"{member.mention} Tes DMs sont désactivés — clique ici pour remplir le questionnaire :",
                view=QuestionnairePersistentView(),
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(RecrutementExterne(bot))
