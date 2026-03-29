import json
import os
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime

from config import ROLES, DEFAULT_TEMPLATES, ACTIVITY_COLORS, DEFAULT_COLOR, TEMPLATES_FILE, ADMIN_ROLE_NAME, MEMBRE_ROLE_NAME
from Service.utils import load_settings, append_bal_log, is_membre

# ── STOCKAGE EN MÉMOIRE  {message_id: data} ──────────────────────────────────
# Importé par d'autres cogs si besoin (ex: bal.py)
activities: dict[int, dict] = {}

ACTIVITIES_FILE = "activities.json"


def save_activities() -> None:
    data = {}
    for msg_id, act in activities.items():
        data[str(msg_id)] = {
            "creator":     act["creator"],
            "created_at":  act["created_at"].isoformat() if isinstance(act["created_at"], datetime) else act["created_at"],
            "template":    act["template"],
            "max_players": act["max_players"],
            "bal":         act["bal"],
            "slots":       {role: [list(entry) for entry in members] for role, members in act["slots"].items()},
            "channel_id":  act["channel_id"],
        }
    with open(ACTIVITIES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_activities() -> None:
    if not os.path.exists(ACTIVITIES_FILE):
        return
    with open(ACTIVITIES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    for msg_id_str, act in data.items():
        try:
            act["created_at"] = datetime.fromisoformat(act["created_at"])
        except Exception:
            act["created_at"] = datetime.utcnow()
        # Normalise en 3-tuple (uid, name, spec) — rétrocompatibilité anciens fichiers 2-tuple
        act["slots"] = {
            role: [(entry[0], entry[1], entry[2] if len(entry) > 2 else "") for entry in members]
            for role, members in act["slots"].items()
        }
        activities[int(msg_id_str)] = act


# ── HELPERS BAL LOCAUX (évite l'import circulaire avec bal.py) ────────────────
def _load_bal() -> dict[str, int]:
    if not os.path.exists("bal.json"):
        return {}
    with open("bal.json", "r", encoding="utf-8") as f:
        return json.load(f)


def _save_bal(data: dict[str, int]) -> None:
    with open("bal.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── HELPER : tri des rôles — PF1 d'abord, PF2 ensuite, SCOOT toujours en dernier
def _sort_roles(roles: list[str]) -> list[str]:
    pf1   = [r for r in roles if not r.startswith("PF2:") and r != "SCOOT"]
    pf2   = [r for r in roles if r.startswith("PF2:")]
    scoot = [r for r in roles if r == "SCOOT"]
    return pf1 + pf2 + scoot


# ── HELPER : tous les templates (défaut + custom) ────────────────────────────
def load_all_templates() -> dict[str, dict]:
    custom = {}
    if os.path.exists(TEMPLATES_FILE):
        with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
            custom = json.load(f)
    return {**DEFAULT_TEMPLATES, **custom}


def get_pf1(template_data: dict) -> dict[str, int]:
    """Retourne les rôles pf_1. Gère l'ancien format {rôle: int} pour la rétrocompatibilité."""
    if "pf_1" in template_data:
        return template_data["pf_1"]
    return {k: v for k, v in template_data.items() if isinstance(v, int)}


def get_pf2(template_data: dict) -> dict[str, int]:
    """Retourne les rôles pf_2 (optionnel — vide si template mono-party)."""
    return template_data.get("pf_2", {})


def get_specs(template_data: dict) -> dict[str, str]:
    """Retourne les specs requises par rôle pour PF1."""
    return template_data.get("specs", {})


# ── CONSTRUCTION DE L'EMBED ──────────────────────────────────────────────────
def build_embed(data: dict) -> discord.Embed:
    template = data.get("template")
    max_p    = data["max_players"]
    bal      = data["bal"]
    creator  = data["creator"]
    created  = data["created_at"]

    # Couleur : première correspondance dans le nom du template
    color = DEFAULT_COLOR
    if template:
        for key, col in ACTIVITY_COLORS.items():
            if key.lower() in template.lower():
                color = col
                break

    all_templates = load_all_templates()
    tdata         = all_templates.get(template, {})
    description   = tdata.get("description", "")
    image_url     = tdata.get("image", "")

    embed = discord.Embed(
        title=f"🗡️  {template or 'Activité'}",
        description=description or None,
        color=color,
        timestamp=created,
    )
    if image_url:
        embed.set_thumbnail(url=image_url)
    embed.set_footer(text=f"Organisé par {creator}  •  Max {max_p} joueurs")

    slots: dict[str, list] = data["slots"]
    pf1       = get_pf1(tdata) if tdata else {}
    pf2       = get_pf2(tdata) if tdata else {}
    specs     = get_specs(tdata) if tdata else {}
    specs_pf2 = tdata.get("specs_pf2", {}) if tdata else {}

    pf1_keys      = list(pf1.keys()) if pf1 else list(ROLES.keys())
    pf2_keys      = [f"PF2:{r}" for r in pf2.keys()]
    roles_to_show = _sort_roles(pf1_keys + pf2_keys)

    pf2_header_done = False
    for role_key in roles_to_show:
        is_pf2    = role_key.startswith("PF2:")
        role_name = role_key[4:] if is_pf2 else role_key
        emoji     = ROLES.get(role_name, "🔹")
        members   = slots.get(role_key, [])

        if is_pf2:
            if not pf2_header_done:
                embed.add_field(name="─────────────────────────\n🔶  PF2", value="\u200b", inline=False)
                pf2_header_done = True
            max_r     = pf2.get(role_name, "∞")
            role_spec = specs_pf2.get(role_name, "")
        else:
            max_r     = pf1.get(role_key, "∞") if pf1 else "∞"
            role_spec = specs.get(role_key, "")

        lines = []
        for entry in members:
            uid         = entry[0]
            player_spec = entry[2] if len(entry) > 2 else ""
            lines.append(f"<@{uid}>{f'  —  {player_spec}' if player_spec else ''}")
        value = "\n\n".join(lines) if lines else "*Personne*"
        count = f"{len(members)}/{max_r}" if isinstance(max_r, int) else str(len(members))

        label      = f"{role_name} PF2" if is_pf2 else role_name
        field_name = f"{emoji} {label}  [{count}]"
        if role_spec:
            field_name = f"{field_name}  ·  {role_spec}"
        embed.add_field(name=field_name[:256], value=value, inline=False)

    payout_line    = "💰 BAL" if bal else "🆓 Libre"
    total_inscrits = sum(len(v) for v in slots.values())
    embed.add_field(
        name="─────────────────────────",
        value=f"**Pay Out :** {payout_line}    **Inscrits :** {total_inscrits}/{max_p}",
        inline=False,
    )
    return embed


# ── CONSTRUCTION DE LA VUE ───────────────────────────────────────────────────
def build_view(activity_id: int) -> discord.ui.View:
    return ActivityView(activity_id)


# ── MODAL INSCRIPTION (spécialisation) ───────────────────────────────────────
class SpecModal(discord.ui.Modal):
    def __init__(self, activity_id: int, chosen_role: str, hint_spec: str = ""):
        role_display = chosen_role[4:] + " (PF2)" if chosen_role.startswith("PF2:") else chosen_role
        super().__init__(title=f"Inscription — {role_display}"[:45])
        self.activity_id = activity_id
        self.chosen_role = chosen_role

        placeholder = (hint_spec if hint_spec else "Ex : Arc Long, Sancti, 1H Masse...")[:100]
        self.spec_input = discord.ui.TextInput(
            label="Votre spécialisation / build",
            placeholder=placeholder,
            required=False,
            max_length=100,
        )
        self.add_item(self.spec_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not is_membre(interaction.user):
            await interaction.response.send_message(
                f"⛔ Tu dois avoir le rôle **{MEMBRE_ROLE_NAME}** pour t'inscrire.", ephemeral=True
            )
            return

        spec        = self.spec_input.value.strip()
        chosen_role = self.chosen_role
        data        = activities.get(self.activity_id)
        if not data:
            await interaction.response.send_message("❌ Activité introuvable.", ephemeral=True)
            return

        user_id   = interaction.user.id
        user_name = interaction.user.display_name
        slots     = data["slots"]
        max_p     = data["max_players"]
        template  = data.get("template")

        # Vérif slot max global
        total      = sum(len(v) for v in slots.values())
        already_in = any(entry[0] == user_id for members in slots.values() for entry in members)
        if total >= max_p and not already_in:
            await interaction.response.send_message(f"⛔ L'activité est complète ({max_p} joueurs max).", ephemeral=True)
            return

        # Vérif slot max du rôle
        all_templates = load_all_templates()
        if template in all_templates:
            tdata     = all_templates[template]
            role_name = chosen_role[4:] if chosen_role.startswith("PF2:") else chosen_role
            max_role  = get_pf2(tdata).get(role_name, 999) if chosen_role.startswith("PF2:") else get_pf1(tdata).get(chosen_role, 999)
            current_in_role = [entry[0] for entry in slots.get(chosen_role, [])]
            if len(current_in_role) >= max_role and user_id not in current_in_role:
                label = f"{role_name} PF2" if chosen_role.startswith("PF2:") else chosen_role
                await interaction.response.send_message(f"⛔ Plus de place en **{label}** ({max_role} max).", ephemeral=True)
                return

        # Changer de rôle si déjà inscrit ailleurs
        for role, members in slots.items():
            for entry in list(members):
                if entry[0] == user_id:
                    members.remove(entry)
                    break

        slots.setdefault(chosen_role, []).append((user_id, user_name, spec))
        save_activities()

        try:
            channel = interaction.client.get_channel(data["channel_id"])
            msg     = await channel.fetch_message(self.activity_id)
            await msg.edit(embed=build_embed(data), view=build_view(self.activity_id))
        except Exception:
            pass

        confirm = f"✅ Inscrit en **{chosen_role}**{f'  —  {spec}' if spec else ''} !"
        await interaction.response.send_message(confirm, ephemeral=True)


# ── SELECT MENU ──────────────────────────────────────────────────────────────
class RoleSelect(discord.ui.Select):
    def __init__(self, activity_id: int, roles: list[str]):
        self.activity_id = activity_id
        options = []
        for role_key in roles:
            is_pf2    = role_key.startswith("PF2:")
            role_name = role_key[4:] if is_pf2 else role_key
            label     = f"{role_name} (PF2)" if is_pf2 else role_name
            desc      = f"PF2 — S'inscrire en {role_name}" if is_pf2 else f"S'inscrire en tant que {role_name}"
            options.append(discord.SelectOption(
                label=label[:100],
                emoji=ROLES.get(role_name, "🔹"),
                description=desc[:100],
                value=role_key,
            ))
        super().__init__(
            placeholder="📋  Choisis ton rôle...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"roleselect_{activity_id}",
        )

    async def callback(self, interaction: discord.Interaction):
        if not is_membre(interaction.user):
            await interaction.response.send_message(
                f"⛔ Tu dois avoir le rôle **{MEMBRE_ROLE_NAME}** pour t'inscrire.", ephemeral=True
            )
            return
        data = activities.get(self.activity_id)
        if not data:
            await interaction.response.send_message("❌ Activité introuvable.", ephemeral=True)
            return

        chosen_role   = self.values[0]
        template      = data.get("template")
        all_templates = load_all_templates()
        tdata         = all_templates.get(template, {}) if template else {}

        if chosen_role.startswith("PF2:"):
            role_name = chosen_role[4:]
            hint_spec = tdata.get("specs_pf2", {}).get(role_name, "")
        else:
            hint_spec = get_specs(tdata).get(chosen_role, "")

        await interaction.response.send_modal(SpecModal(self.activity_id, chosen_role, hint_spec))


# ── BOUTON SE RETIRER ────────────────────────────────────────────────────────
class LeaveButton(discord.ui.Button):
    def __init__(self, activity_id: int):
        super().__init__(
            label="Se retirer", emoji="❌",
            style=discord.ButtonStyle.danger,
            custom_id=f"leave_{activity_id}",
        )
        self.activity_id = activity_id

    async def callback(self, interaction: discord.Interaction):
        if not is_membre(interaction.user):
            await interaction.response.send_message(
                f"⛔ Tu dois avoir le rôle **{MEMBRE_ROLE_NAME}** pour te retirer.", ephemeral=True
            )
            return
        data = activities.get(self.activity_id)
        if not data:
            await interaction.response.send_message("❌ Activité introuvable.", ephemeral=True)
            return

        user_id = interaction.user.id
        removed = False
        for members in data["slots"].values():
            for entry in list(members):
                if entry[0] == user_id:
                    members.remove(entry)
                    removed = True
                    break
            if removed:
                break

        if not removed:
            await interaction.response.send_message("ℹ️ Tu n'es pas inscrit à cette activité.", ephemeral=True)
            return

        save_activities()
        await interaction.message.edit(embed=build_embed(data), view=build_view(self.activity_id))
        await interaction.response.send_message("👋 Tu t'es retiré de l'activité.", ephemeral=True)


# ── MODAL FIN D'ACTIVITÉ ─────────────────────────────────────────────────────
class FinActiModal(discord.ui.Modal, title="Clôturer l'activité"):
    recettes = discord.ui.TextInput(
        label="Recettes totales générées (silver)",
        placeholder="Ex : 10000000",
        required=True,
        max_length=20,
    )

    def __init__(self, activity_id: int, data: dict):
        super().__init__()
        self.activity_id = activity_id
        self.data        = data
        self.has_scoot   = bool(data["slots"].get("SCOOT"))

        # Champ "Coût de la carte" uniquement pour les activités PVE
        template  = data.get("template")
        all_tpl   = load_all_templates()
        type_acti = all_tpl.get(template, {}).get("type_acti", "") if template else ""
        self.is_pve = (type_acti == "PVE")

        if self.is_pve:
            self.cout_carte = discord.ui.TextInput(
                label="Coût de la carte (silver)",
                placeholder="Laisser vide si pas de carte",
                required=False,
                max_length=20,
            )
            self.add_item(self.cout_carte)

        if self.has_scoot:
            self.scoot_pay = discord.ui.TextInput(
                label="Paiement Scoot (silver/joueur)",
                placeholder="Ex : 500000",
                required=True,
                max_length=20,
            )
            self.add_item(self.scoot_pay)

    async def on_submit(self, interaction: discord.Interaction):
        fmt = lambda n: f"{n:,}".replace(",", " ")

        # Parse les montants
        try:
            total = int(self.recettes.value.replace(" ", "").replace(",", "").replace(".", ""))
        except ValueError:
            await interaction.response.send_message("❌ Montant recettes invalide.", ephemeral=True)
            return

        # Coût de la carte (PVE uniquement, optionnel)
        carte_cost = 0
        if self.is_pve and self.cout_carte.value.strip():
            try:
                carte_cost = int(self.cout_carte.value.replace(" ", "").replace(",", "").replace(".", ""))
            except ValueError:
                await interaction.response.send_message("❌ Coût de la carte invalide.", ephemeral=True)
                return

        scoot_amount = 0
        if self.has_scoot:
            try:
                scoot_amount = int(self.scoot_pay.value.replace(" ", "").replace(",", "").replace(".", ""))
            except ValueError:
                await interaction.response.send_message("❌ Montant Scoot invalide.", ephemeral=True)
                return

        data     = self.data
        settings = load_settings()
        rate     = settings.get("bal_rate", 90)

        part_guilde   = total * rate // 100
        distributable = part_guilde - carte_cost   # on déduit la carte avant de répartir

        scoot_members = data["slots"].get("SCOOT", [])
        nb_scoot      = len(scoot_members)
        scoot_total   = scoot_amount * nb_scoot

        other_members = [(entry[0], entry[1]) for role, members in data["slots"].items()
                         for entry in members if role != "SCOOT"]
        nb_others     = len(other_members)
        remaining     = distributable - scoot_total
        part_indiv    = remaining // nb_others if nb_others > 0 else 0

        # Créditer les BAL
        bal         = _load_bal()
        log_entries = []
        for uid, name in other_members:
            key      = str(uid)
            bal[key] = bal.get(key, 0) + part_indiv
            log_entries.append({"uid": key, "name": name, "delta": part_indiv, "total": bal[key]})
        for entry in scoot_members:
            uid, name = entry[0], entry[1]
            key      = str(uid)
            bal[key] = bal.get(key, 0) + scoot_amount
            log_entries.append({"uid": key, "name": name, "delta": scoot_amount, "total": bal[key]})
        _save_bal(bal)
        append_bal_log("finacti", interaction.user.display_name, log_entries)

        # Supprimer l'activité
        activities.pop(self.activity_id, None)
        save_activities()

        # Mettre à jour le message original : même rendu, titre préfixé
        fin_embed       = build_embed(data)
        fin_embed.title = f"🏁 FIN  ·  {fin_embed.title}"
        try:
            channel = interaction.client.get_channel(data["channel_id"])
            msg     = await channel.fetch_message(self.activity_id)
            await msg.edit(embed=fin_embed, view=discord.ui.View())
        except Exception:
            pass

        # Résumé financier en éphémère
        summary = (
            f"✅ **Activité clôturée !**\n\n"
            f"💰 Recettes : **{fmt(total)} silver**\n"
            f"🏦 Part guilde ({rate} %) : **{fmt(part_guilde)} silver**\n"
        )
        if carte_cost:
            summary += f"🗺️ Coût de la carte : **-{fmt(carte_cost)} silver** → distributable : **{fmt(distributable)} silver**\n"
        if self.has_scoot:
            summary += (
                f"🏃 Scoot ({nb_scoot} joueur(s)) : **{fmt(scoot_amount)} silver/joueur**\n"
                f"👥 Reste ({nb_others} joueur(s)) : **{fmt(part_indiv)} silver/joueur**\n"
                f"📊 BAL crédités — Scoot : **+{fmt(scoot_amount)}** · Reste : **+{fmt(part_indiv)}**"
            )
        else:
            nb_total = nb_others
            summary += (
                f"👥 Participants : **{nb_total}**\n"
                f"💵 Part individuelle : **{fmt(part_indiv)} silver**\n"
                f"📊 BAL crédités : **+{fmt(part_indiv)} BAL / joueur**"
            )
        await interaction.response.send_message(summary, ephemeral=True)


# ── BOUTON FIN D'ACTIVITÉ ─────────────────────────────────────────────────────
class FinActiButton(discord.ui.Button):
    def __init__(self, activity_id: int):
        super().__init__(
            label="Fin d'activité", emoji="🏁",
            style=discord.ButtonStyle.success,
            custom_id=f"finacti_{activity_id}",
        )
        self.activity_id = activity_id

    async def callback(self, interaction: discord.Interaction):
        data = activities.get(self.activity_id)
        if not data:
            await interaction.response.send_message("❌ Activité introuvable.", ephemeral=True)
            return

        is_creator = interaction.user.display_name == data["creator"]
        has_role   = any(r.name == ADMIN_ROLE_NAME for r in interaction.user.roles)
        if not (is_creator or has_role or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message(
                f"⛔ Seul l'organisateur ou un **{ADMIN_ROLE_NAME}** peut clôturer l'activité.", ephemeral=True
            )
            return

        # Activité BAL → modal pour saisir les recettes
        if data.get("bal"):
            await interaction.response.send_modal(FinActiModal(self.activity_id, data))
            return

        # Activité Libre → clôture directe, sans calcul BAL
        activities.pop(self.activity_id, None)
        save_activities()

        fin_embed       = build_embed(data)
        fin_embed.title = f"🏁 FIN  ·  {fin_embed.title}"
        try:
            channel = interaction.client.get_channel(data["channel_id"])
            msg     = await channel.fetch_message(self.activity_id)
            await msg.edit(embed=fin_embed, view=discord.ui.View())
        except Exception:
            pass

        await interaction.response.send_message("✅ Activité clôturée !", ephemeral=True)


# ── BOUTON ANNULER ───────────────────────────────────────────────────────────
class CancelButton(discord.ui.Button):
    def __init__(self, activity_id: int):
        super().__init__(
            label="Annuler le raid", emoji="🔴",
            style=discord.ButtonStyle.secondary,
            custom_id=f"cancel_{activity_id}",
        )
        self.activity_id = activity_id

    async def callback(self, interaction: discord.Interaction):
        data = activities.get(self.activity_id)
        if not data:
            await interaction.response.send_message("❌ Activité introuvable.", ephemeral=True)
            return

        is_creator = interaction.user.display_name == data["creator"]
        is_admin   = interaction.user.guild_permissions.administrator
        if not (is_creator or is_admin):
            await interaction.response.send_message("⛔ Seul l'organisateur ou un admin peut annuler.", ephemeral=True)
            return

        del activities[self.activity_id]
        save_activities()
        embed = discord.Embed(
            title="🚫 Activité annulée",
            description=f"L'activité a été annulée par {interaction.user.display_name}.",
            color=0x95A5A6,
        )
        await interaction.message.edit(embed=embed, view=discord.ui.View())
        await interaction.response.send_message("✅ Activité annulée.", ephemeral=True)


# ── VUE PRINCIPALE ───────────────────────────────────────────────────────────
class ActivityView(discord.ui.View):
    def __init__(self, activity_id: int):
        super().__init__(timeout=None)
        data = activities.get(activity_id)
        if not data:
            return

        all_templates = load_all_templates()
        template      = data.get("template")
        tdata         = all_templates.get(template, {}) if template else {}
        pf1           = get_pf1(tdata) if tdata else {}
        pf2           = get_pf2(tdata) if tdata else {}
        pf1_keys      = list(pf1.keys()) if pf1 else list(ROLES.keys())
        pf2_keys      = [f"PF2:{r}" for r in pf2.keys()]
        roles_to_show = _sort_roles(pf1_keys + pf2_keys)

        self.add_item(RoleSelect(activity_id, roles_to_show))
        self.add_item(LeaveButton(activity_id))
        self.add_item(FinActiButton(activity_id))
        self.add_item(CancelButton(activity_id))


# ── AUTOCOMPLÉTION : templates disponibles ───────────────────────────────────
async def template_autocomplete(
    _interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    all_templates = load_all_templates()
    return [
        app_commands.Choice(name=name, value=name)
        for name in all_templates
        if current.lower() in name.lower()
    ][:25]


# ── COG ACTIVITÉS ─────────────────────────────────────────────────────────────
class Activites(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        load_activities()
        for msg_id in list(activities.keys()):
            data = activities[msg_id]
            try:
                channel = self.bot.get_channel(data["channel_id"])
                if channel:
                    msg = await channel.fetch_message(msg_id)
                    await msg.edit(view=build_view(msg_id))
            except Exception:
                activities.pop(msg_id, None)
        save_activities()
        print(f"   {len(activities)} activité(s) rechargée(s) depuis le fichier.")

    # ── /acti ────────────────────────────────────────────────────────────────
    @app_commands.command(name="acti", description="Créer une activité de guilde Albion Online")
    @app_commands.describe(
        nametemplate = "Template de composition",
        nbplayer     = "Nombre de joueurs max (1-50) — calculé automatiquement depuis le template",
        bal          = "Paiement BAL ? (true = BAL, false = Libre)",
    )
    @app_commands.autocomplete(nametemplate=template_autocomplete)
    async def acti(
        self,
        interaction:  discord.Interaction,
        nametemplate: str,
        nbplayer:     app_commands.Range[int, 1, 100] | None = None,
        bal:          bool = False,
    ):
        if not is_membre(interaction.user):
            await interaction.response.send_message(
                f"⛔ Tu dois avoir le rôle **{MEMBRE_ROLE_NAME}** pour créer une activité.", ephemeral=True
            )
            return
        all_templates = load_all_templates()

        # Résolution du template (insensible à la casse)
        template_name = None
        for key in all_templates:
            if key.lower() == nametemplate.lower():
                template_name = key
                break

        if template_name is None:
            templates_list = "\n".join(f"• `{k}`" for k in all_templates)
            await interaction.response.send_message(
                f"❌ Template inconnu. Templates disponibles :\n{templates_list}", ephemeral=True
            )
            return

        pf1   = get_pf1(all_templates[template_name])
        pf2   = get_pf2(all_templates[template_name])
        slots = {role: [] for role in pf1}
        slots.update({f"PF2:{role}": [] for role in pf2})
        nbplayer = nbplayer or (sum(pf1.values()) + sum(pf2.values()))

        data = {
            "creator":     interaction.user.display_name,
            "created_at":  datetime.utcnow(),
            "template":    template_name,
            "max_players": nbplayer,
            "bal":         bal,
            "slots":       slots,
            "channel_id":  interaction.channel_id,
        }

        await interaction.response.send_message(embed=build_embed(data))
        message = await interaction.original_response()
        activities[message.id] = data
        save_activities()
        await message.edit(view=build_view(message.id))

    # ── /templates ───────────────────────────────────────────────────────────
    @app_commands.command(name="templates", description="Afficher les templates de compositions disponibles")
    async def list_templates(self, interaction: discord.Interaction):
        if not is_membre(interaction.user):
            await interaction.response.send_message(
                f"⛔ Tu dois avoir le rôle **{MEMBRE_ROLE_NAME}** pour utiliser cette commande.", ephemeral=True
            )
            return
        all_templates = load_all_templates()
        embed = discord.Embed(title="📋 Templates de compositions", color=0x3498DB)
        for name, tdata in all_templates.items():
            pf1         = get_pf1(tdata)
            type_acti   = tdata.get("type_acti", "—")
            description = tdata.get("description", "")
            tag         = "🔴 PVP" if type_acti == "PVP" else "🟢 PVE" if type_acti == "PVE" else type_acti
            roles_str   = "  ".join(f"{ROLES.get(r, '🔹')} **{r}** ×{n}" for r, n in pf1.items())
            value       = f"{tag}  ·  {description}\n{roles_str}" if description else f"{tag}\n{roles_str}"
            embed.add_field(name=name, value=value, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ── SETUP ─────────────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(Activites(bot))
