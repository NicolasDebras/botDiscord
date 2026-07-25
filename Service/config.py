import discord
from discord.ext import commands
from discord import app_commands

import db
from config import ADMIN_ROLE_NAME
from Service.utils import is_admin
from Service import vocal_temp, bienvenue, self_roles


# ── EMBEDS ────────────────────────────────────────────────────────────────────

def _main_embed() -> discord.Embed:
    return discord.Embed(
        title="⚙️ Configuration du serveur",
        description="Choisis une section à configurer dans le menu ci-dessous.",
        color=0x3498DB,
    )


def _vocal_embed(guild: discord.Guild, hubs: list[dict]) -> discord.Embed:
    embed = discord.Embed(title="🔊 Salons vocaux temporaires", color=0x3498DB)
    if not hubs:
        embed.description = "Aucun hub configuré. Clique sur **➕ Ajouter un hub** pour commencer."
    else:
        lines = []
        for h in hubs:
            cat = guild.get_channel(h["category_id"]) if h["category_id"] else None
            lines.append(
                f"<#{h['channel_id']}> → `{h['name_template']}`"
                f"  ·  limite : {h['user_limit'] or 'illimitée'}"
                f"  ·  catégorie : {cat.name if cat else 'celle du hub'}"
            )
        embed.description = "\n".join(lines)
    embed.set_footer(text="Rejoindre un salon hub crée automatiquement un salon vocal temporaire, supprimé quand il se vide.")
    return embed


def _welcome_embed(guild: discord.Guild, kind: str) -> discord.Embed:
    cfg = bienvenue._configs.get(guild.id, {})
    if kind == "welcome":
        title, chan_id, msg = "👋 Message de bienvenue", cfg.get("welcome_channel_id"), cfg.get("welcome_message")
    else:
        title, chan_id, msg = "🚪 Message d'au revoir", cfg.get("goodbye_channel_id"), cfg.get("goodbye_message")

    embed = discord.Embed(title=title, color=0x3498DB)
    if chan_id and msg:
        embed.add_field(name="Salon", value=f"<#{chan_id}>", inline=False)
        embed.add_field(name="Message", value=msg[:1024], inline=False)
        if kind == "welcome" and cfg.get("welcome_image"):
            embed.add_field(name="Image / GIF", value=cfg["welcome_image"], inline=False)
            embed.set_image(url=cfg["welcome_image"])
    else:
        embed.description = "Non configuré."
    embed.set_footer(text="Placeholders : {mention} {pseudo} {serveur} {membercount}")
    return embed


def _default_role_embed(guild: discord.Guild) -> discord.Embed:
    cfg = bienvenue._configs.get(guild.id, {})
    role_id = cfg.get("default_role_id")
    embed = discord.Embed(title="🎭 Rôle par défaut à l'arrivée", color=0x3498DB)
    embed.description = f"<@&{role_id}>" if role_id else "Non configuré."
    return embed


async def _recap_embed(guild: discord.Guild) -> discord.Embed:
    channel_id = await db.get_recap_channel(guild.id)
    embed = discord.Embed(title="📋 Salon de récap recrutement (22h)", color=0x3498DB)
    if channel_id:
        embed.description = f"<#{channel_id}>"
    else:
        embed.description = "Non configuré."
    embed.set_footer(text="Récap automatique chaque soir à 22h (heure de Paris) : suivi recrutement, stats silver, membres inactifs.")
    return embed


def _autoroles_embed(guild: discord.Guild) -> discord.Embed:
    menus = self_roles.list_menus(guild.id)
    embed = discord.Embed(title="🏷️ Rôles à la carte (boutons)", color=0x3498DB)
    if not menus:
        embed.description = "Aucun message de rôles configuré. Clique sur **➕ Créer un message de rôles** pour commencer."
    else:
        lines = []
        for m in menus:
            link = f"https://discord.com/channels/{guild.id}/{m['channel_id']}/{m['message_id']}"
            roles_str = ", ".join(f"<@&{r['role_id']}>" for r in m["roles"])
            lines.append(f"[Message]({link}) dans <#{m['channel_id']}> — {roles_str}")
        embed.description = "\n".join(lines)
    embed.set_footer(text="Chaque bouton attribue/retire le rôle correspondant au membre qui clique.")
    return embed


async def _validated_role_embed(guild: discord.Guild) -> discord.Embed:
    cfg = await db.get_recruitment_config(guild.id)
    role_id = cfg["validated_role_id"] if cfg else None
    embed = discord.Embed(title="✅ Rôle après validation de candidature", color=0x3498DB)
    embed.description = f"<@&{role_id}>" if role_id else "Non configuré."
    embed.set_footer(text="Attribué automatiquement quand le staff clique sur ✅ Valider (Staff) dans un salon de candidature.")
    return embed


# ── MODALS ────────────────────────────────────────────────────────────────────

class HubDetailsModal(discord.ui.Modal, title="Configurer le hub vocal"):
    template = discord.ui.TextInput(
        label="Nom des salons créés ({pseudo} = pseudo)",
        placeholder="🔊 {pseudo}",
        default="🔊 {pseudo}",
        required=True,
        max_length=90,
    )
    limite = discord.ui.TextInput(
        label="Limite de places (0 = illimité)",
        default="0",
        required=True,
        max_length=3,
    )

    def __init__(self, guild_id: int, hub_channel_id: int, category_id: int | None):
        super().__init__()
        self.guild_id       = guild_id
        self.hub_channel_id = hub_channel_id
        self.category_id    = category_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            limit = max(0, min(99, int(self.limite.value)))
        except ValueError:
            limit = 0
        await vocal_temp.add_hub(self.hub_channel_id, self.guild_id, self.category_id, self.template.value, limit)
        await interaction.response.send_message(
            f"✅ Hub vocal configuré sur <#{self.hub_channel_id}>.", ephemeral=True
        )


class EditHubModal(discord.ui.Modal, title="Modifier le hub vocal"):
    template = discord.ui.TextInput(label="Nom des salons créés ({pseudo} = pseudo)", required=True, max_length=90)
    limite   = discord.ui.TextInput(label="Limite de places (0 = illimité)", required=True, max_length=3)

    def __init__(self, hub: dict):
        super().__init__()
        self.channel_id       = hub["channel_id"]
        self.template.default = hub["name_template"]
        self.limite.default   = str(hub["user_limit"])

    async def on_submit(self, interaction: discord.Interaction):
        try:
            limit = max(0, min(99, int(self.limite.value)))
        except ValueError:
            limit = 0
        await vocal_temp.update_hub(self.channel_id, self.template.value, limit)
        await interaction.response.send_message(f"✅ Hub <#{self.channel_id}> mis à jour.", ephemeral=True)


class MessageModal(discord.ui.Modal, title="Message"):
    message = discord.ui.TextInput(
        label="Message",
        placeholder="Placeholders : {mention} {pseudo} {serveur} {membercount}",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000,
    )

    def __init__(self, guild_id: int, kind: str, channel_id: int):
        super().__init__()
        self.guild_id    = guild_id
        self.kind        = kind
        self.channel_id  = channel_id
        self.image_input = None
        if kind == "welcome":
            self.image_input = discord.ui.TextInput(
                label="Image / GIF (URL, optionnel)",
                placeholder="https://... (laisse vide pour aucune image)",
                required=False,
                max_length=300,
            )
            self.add_item(self.image_input)

    async def on_submit(self, interaction: discord.Interaction):
        if self.kind == "welcome":
            image_url = self.image_input.value.strip() if self.image_input and self.image_input.value else None
            await bienvenue.set_welcome(self.guild_id, self.channel_id, self.message.value, image_url)
        else:
            await bienvenue.set_goodbye(self.guild_id, self.channel_id, self.message.value)
        label = "bienvenue" if self.kind == "welcome" else "au revoir"
        await interaction.response.send_message(
            f"✅ Message de {label} configuré sur <#{self.channel_id}>.", ephemeral=True
        )


class AutoRoleTitleModal(discord.ui.Modal, title="Message de rôles"):
    titre = discord.ui.TextInput(
        label="Titre",
        default="🏷️ Choisis tes rôles",
        required=True,
        max_length=100,
    )
    description = discord.ui.TextInput(
        label="Description (optionnel)",
        placeholder="Clique sur un bouton pour t'attribuer ou retirer le rôle correspondant.",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=800,
    )

    def __init__(self, guild_id: int, channel_id: int, roles: list[tuple[int, str]]):
        super().__init__()
        self.guild_id   = guild_id
        self.channel_id = channel_id
        self.roles      = roles  # [(role_id, role_name), ...]

    async def on_submit(self, interaction: discord.Interaction):
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("❌ Le salon choisi est introuvable.", ephemeral=True)
            return

        embed = discord.Embed(
            title=self.titre.value,
            description=self.description.value or None,
            color=0x3498DB,
        )
        embed.set_footer(text="Clique sur un bouton pour t'attribuer / retirer le rôle correspondant.")

        try:
            message = await channel.send(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message(
                f"⛔ Je n'ai pas la permission d'envoyer de message dans <#{self.channel_id}>.", ephemeral=True
            )
            return

        roles_payload = [{"role_id": rid, "label": name} for rid, name in self.roles]
        await self_roles.create_menu(message.id, self.channel_id, self.guild_id, roles_payload)
        await message.edit(view=self_roles.build_view(message.id, roles_payload))

        await interaction.response.send_message(
            f"✅ Message de rôles créé dans <#{self.channel_id}> avec {len(roles_payload)} rôle(s).", ephemeral=True
        )


# ── VUES : SALONS VOCAUX TEMPORAIRES ──────────────────────────────────────────

class AddHubView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=180)
        self.guild_id      = guild_id
        self.hub_channel_id: int | None = None
        self.category_id:    int | None = None

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.voice],
                        placeholder="1️⃣ Choisis le salon vocal hub")
    async def hub_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        self.hub_channel_id = select.values[0].id
        await interaction.response.defer(ephemeral=True)

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.category],
                        placeholder="2️⃣ Catégorie des salons créés (optionnel)")
    async def category_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        self.category_id = select.values[0].id
        await interaction.response.defer(ephemeral=True)

    @discord.ui.button(label="3️⃣ Valider", style=discord.ButtonStyle.success, row=2)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.hub_channel_id:
            await interaction.response.send_message("❌ Choisis d'abord un salon hub.", ephemeral=True)
            return
        await interaction.response.send_modal(
            HubDetailsModal(self.guild_id, self.hub_channel_id, self.category_id)
        )


class ManageHubSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild, hubs: list[dict]):
        self.hubs_by_id = {h["channel_id"]: h for h in hubs}
        options = [
            discord.SelectOption(
                label=(guild.get_channel(h["channel_id"]).name if guild.get_channel(h["channel_id"]) else str(h["channel_id"]))[:100],
                value=str(h["channel_id"]),
            )
            for h in hubs
        ]
        super().__init__(placeholder="Choisis un hub à gérer...", options=options)

    async def callback(self, interaction: discord.Interaction):
        view: ManageHubView = self.view
        view.selected = self.hubs_by_id[int(self.values[0])]
        await interaction.response.defer(ephemeral=True)


class ManageHubView(discord.ui.View):
    def __init__(self, guild: discord.Guild, hubs: list[dict]):
        super().__init__(timeout=180)
        self.selected: dict | None = None
        self.add_item(ManageHubSelect(guild, hubs))

    @discord.ui.button(label="✏️ Modifier", style=discord.ButtonStyle.primary, row=1)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected:
            await interaction.response.send_message("❌ Choisis d'abord un hub dans le menu.", ephemeral=True)
            return
        await interaction.response.send_modal(EditHubModal(self.selected))

    @discord.ui.button(label="🗑️ Supprimer", style=discord.ButtonStyle.danger, row=1)
    async def remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected:
            await interaction.response.send_message("❌ Choisis d'abord un hub dans le menu.", ephemeral=True)
            return
        channel_id = self.selected["channel_id"]
        await vocal_temp.remove_hub(channel_id)
        await interaction.response.send_message(f"🗑️ Hub <#{channel_id}> supprimé.", ephemeral=True)


class VocalConfigView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=180)
        self.guild_id = guild_id

    @discord.ui.button(label="➕ Ajouter un hub", style=discord.ButtonStyle.success, row=0)
    async def add_hub(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Sélectionne le salon vocal hub puis (optionnel) la catégorie des salons créés :",
            view=AddHubView(self.guild_id), ephemeral=True,
        )

    @discord.ui.button(label="✏️ Gérer un hub", style=discord.ButtonStyle.secondary, row=0)
    async def manage_hub(self, interaction: discord.Interaction, button: discord.ui.Button):
        hubs = vocal_temp.list_hubs(self.guild_id)
        if not hubs:
            await interaction.response.send_message("ℹ️ Aucun hub configuré.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Choisis le hub à modifier ou supprimer :", view=ManageHubView(interaction.guild, hubs), ephemeral=True
        )

    @discord.ui.button(label="⬅️ Retour", style=discord.ButtonStyle.gray, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=_main_embed(), view=MainConfigView())


# ── VUES : BIENVENUE / AU REVOIR ──────────────────────────────────────────────

class WelcomeConfigView(discord.ui.View):
    def __init__(self, guild_id: int, kind: str):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.kind      = kind  # "welcome" ou "goodbye"

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text],
                        placeholder="Choisis le salon puis renseigne le message")
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await interaction.response.send_modal(MessageModal(self.guild_id, self.kind, select.values[0].id))

    @discord.ui.button(label="🔕 Désactiver", style=discord.ButtonStyle.danger, row=1)
    async def disable(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.kind == "welcome":
            await bienvenue.set_welcome(self.guild_id, None, None)
        else:
            await bienvenue.set_goodbye(self.guild_id, None, None)
        await interaction.response.send_message("🔕 Message désactivé.", ephemeral=True)

    @discord.ui.button(label="⬅️ Retour", style=discord.ButtonStyle.gray, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=_main_embed(), view=MainConfigView())


# ── VUE : RÔLE PAR DÉFAUT ──────────────────────────────────────────────────────

class DefaultRoleView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=180)
        self.guild_id = guild_id

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Choisis le rôle attribué à l'arrivée")
    async def role_select(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        await bienvenue.set_default_role(self.guild_id, select.values[0].id)
        await interaction.response.send_message(
            f"✅ Rôle par défaut : {select.values[0].mention}", ephemeral=True
        )

    @discord.ui.button(label="🔕 Désactiver", style=discord.ButtonStyle.danger, row=1)
    async def disable(self, interaction: discord.Interaction, button: discord.ui.Button):
        await bienvenue.set_default_role(self.guild_id, None)
        await interaction.response.send_message("🔕 Rôle par défaut désactivé.", ephemeral=True)

    @discord.ui.button(label="⬅️ Retour", style=discord.ButtonStyle.gray, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=_main_embed(), view=MainConfigView())


# ── VUE : SALON DE RÉCAP (22H) ─────────────────────────────────────────────────

class RecapConfigView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=180)
        self.guild_id = guild_id

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text],
                        placeholder="Choisis le salon du récap 22h")
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await db.set_recap_channel(self.guild_id, select.values[0].id)
        await interaction.response.send_message(
            f"✅ Salon de récap configuré sur {select.values[0].mention}.", ephemeral=True
        )

    @discord.ui.button(label="🔕 Désactiver", style=discord.ButtonStyle.danger, row=1)
    async def disable(self, interaction: discord.Interaction, button: discord.ui.Button):
        await db.set_recap_channel(self.guild_id, None)
        await interaction.response.send_message("🔕 Récap désactivé sur ce serveur.", ephemeral=True)

    @discord.ui.button(label="⬅️ Retour", style=discord.ButtonStyle.gray, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=_main_embed(), view=MainConfigView())


# ── VUE : RÔLE APRÈS VALIDATION DE CANDIDATURE ─────────────────────────────────

class ValidatedRoleView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=180)
        self.guild_id = guild_id

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Choisis le rôle attribué à la validation")
    async def role_select(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        await db.set_recruitment_validated_role(self.guild_id, select.values[0].id)
        await interaction.response.send_message(
            f"✅ Rôle de validation : {select.values[0].mention}", ephemeral=True
        )

    @discord.ui.button(label="🔕 Désactiver", style=discord.ButtonStyle.danger, row=1)
    async def disable(self, interaction: discord.Interaction, button: discord.ui.Button):
        await db.set_recruitment_validated_role(self.guild_id, None)
        await interaction.response.send_message("🔕 Rôle de validation désactivé.", ephemeral=True)

    @discord.ui.button(label="⬅️ Retour", style=discord.ButtonStyle.gray, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=_main_embed(), view=MainConfigView())


# ── VUES : RÔLES À LA CARTE (BOUTONS) ───────────────────────────────────────────

class CreateAutoRoleView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=180)
        self.guild_id   = guild_id
        self.channel_id: int | None = None
        self.roles: list[tuple[int, str]] = []

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text],
                        placeholder="1️⃣ Salon de publication du message")
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        self.channel_id = select.values[0].id
        await interaction.response.defer(ephemeral=True)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="2️⃣ Rôles proposés (jusqu'à 25)",
                        min_values=1, max_values=25)
    async def role_select(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.roles = [(r.id, r.name) for r in select.values]
        await interaction.response.defer(ephemeral=True)

    @discord.ui.button(label="3️⃣ Valider", style=discord.ButtonStyle.success, row=2)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.channel_id:
            await interaction.response.send_message("❌ Choisis d'abord un salon.", ephemeral=True)
            return
        if not self.roles:
            await interaction.response.send_message("❌ Choisis au moins un rôle.", ephemeral=True)
            return
        await interaction.response.send_modal(
            AutoRoleTitleModal(self.guild_id, self.channel_id, self.roles)
        )


class ManageAutoRoleSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild, menus: list[dict]):
        self.menus_by_id = {m["message_id"]: m for m in menus}
        options = [
            discord.SelectOption(
                label=(guild.get_channel(m["channel_id"]).name if guild.get_channel(m["channel_id"]) else str(m["channel_id"]))[:100],
                description=f"{len(m['roles'])} rôle(s)",
                value=str(m["message_id"]),
            )
            for m in menus
        ]
        super().__init__(placeholder="Choisis un message à supprimer...", options=options)

    async def callback(self, interaction: discord.Interaction):
        view: ManageAutoRoleView = self.view
        view.selected = self.menus_by_id[int(self.values[0])]
        await interaction.response.defer(ephemeral=True)


class ManageAutoRoleView(discord.ui.View):
    def __init__(self, guild: discord.Guild, menus: list[dict]):
        super().__init__(timeout=180)
        self.selected: dict | None = None
        self.add_item(ManageAutoRoleSelect(guild, menus))

    @discord.ui.button(label="🗑️ Supprimer", style=discord.ButtonStyle.danger, row=1)
    async def remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected:
            await interaction.response.send_message("❌ Choisis d'abord un message dans le menu.", ephemeral=True)
            return

        message_id, channel_id = self.selected["message_id"], self.selected["channel_id"]
        await self_roles.delete_menu(message_id)

        channel = interaction.guild.get_channel(channel_id)
        if channel:
            try:
                msg = await channel.fetch_message(message_id)
                await msg.delete()
            except discord.HTTPException:
                pass

        await interaction.response.send_message("🗑️ Message de rôles supprimé.", ephemeral=True)


class AutoRolesConfigView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=180)
        self.guild_id = guild_id

    @discord.ui.button(label="➕ Créer un message de rôles", style=discord.ButtonStyle.success, row=0)
    async def create(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Sélectionne le salon de publication puis les rôles à proposer :",
            view=CreateAutoRoleView(self.guild_id), ephemeral=True,
        )

    @discord.ui.button(label="🗑️ Supprimer un message", style=discord.ButtonStyle.secondary, row=0)
    async def manage(self, interaction: discord.Interaction, button: discord.ui.Button):
        menus = self_roles.list_menus(self.guild_id)
        if not menus:
            await interaction.response.send_message("ℹ️ Aucun message de rôles configuré.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Choisis le message de rôles à supprimer :", view=ManageAutoRoleView(interaction.guild, menus), ephemeral=True
        )

    @discord.ui.button(label="⬅️ Retour", style=discord.ButtonStyle.gray, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=_main_embed(), view=MainConfigView())


# ── VUE PRINCIPALE ─────────────────────────────────────────────────────────────

class MainConfigSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Salons vocaux temporaires", value="vocal", emoji="🔊",
                                  description="Hubs qui créent un salon vocal à la volée"),
            discord.SelectOption(label="Message de bienvenue", value="bienvenue", emoji="👋",
                                  description="Message envoyé à l'arrivée d'un membre"),
            discord.SelectOption(label="Message d'au revoir", value="aurevoir", emoji="🚪",
                                  description="Message envoyé au départ d'un membre"),
            discord.SelectOption(label="Rôle par défaut", value="role_defaut", emoji="🎭",
                                  description="Rôle attribué automatiquement à l'arrivée"),
            discord.SelectOption(label="Salon de récap (22h)", value="recap", emoji="📋",
                                  description="Salon du récap recrutement automatique"),
            discord.SelectOption(label="Rôle après validation candidature", value="role_validation", emoji="✅",
                                  description="Rôle attribué quand le staff valide une candidature"),
            discord.SelectOption(label="Rôles à la carte (boutons)", value="autoroles", emoji="🏷️",
                                  description="Message avec boutons pour s'attribuer un rôle"),
        ]
        super().__init__(placeholder="Choisis une section à configurer...", options=options)

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        if value == "vocal":
            hubs  = vocal_temp.list_hubs(interaction.guild.id)
            embed = _vocal_embed(interaction.guild, hubs)
            await interaction.response.edit_message(embed=embed, view=VocalConfigView(interaction.guild.id))
        elif value == "bienvenue":
            embed = _welcome_embed(interaction.guild, "welcome")
            await interaction.response.edit_message(embed=embed, view=WelcomeConfigView(interaction.guild.id, "welcome"))
        elif value == "aurevoir":
            embed = _welcome_embed(interaction.guild, "goodbye")
            await interaction.response.edit_message(embed=embed, view=WelcomeConfigView(interaction.guild.id, "goodbye"))
        elif value == "role_defaut":
            embed = _default_role_embed(interaction.guild)
            await interaction.response.edit_message(embed=embed, view=DefaultRoleView(interaction.guild.id))
        elif value == "recap":
            embed = await _recap_embed(interaction.guild)
            await interaction.response.edit_message(embed=embed, view=RecapConfigView(interaction.guild.id))
        elif value == "role_validation":
            embed = await _validated_role_embed(interaction.guild)
            await interaction.response.edit_message(embed=embed, view=ValidatedRoleView(interaction.guild.id))
        else:
            embed = _autoroles_embed(interaction.guild)
            await interaction.response.edit_message(embed=embed, view=AutoRolesConfigView(interaction.guild.id))


class MainConfigView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(MainConfigSelect())


# ── COG ────────────────────────────────────────────────────────────────────────

class Config(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="config", description="[ADMIN] Configurer le serveur (vocaux temporaires, bienvenue, au revoir)")
    async def config(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            await interaction.response.send_message(
                f"⛔ Tu dois avoir le rôle **{ADMIN_ROLE_NAME}** pour utiliser cette commande.", ephemeral=True
            )
            return
        await interaction.response.send_message(embed=_main_embed(), view=MainConfigView(), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Config(bot))
