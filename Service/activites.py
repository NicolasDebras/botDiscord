import re
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime

import db
from config import ROLES, DEFAULT_TEMPLATES, ACTIVITY_COLORS, DEFAULT_COLOR, ADMIN_ROLE_NAME, MEMBRE_ROLE_NAME
from Service.utils import load_settings, append_bal_log, is_membre

# ── STOCKAGE EN MÉMOIRE  {message_id: data} ──────────────────────────────────
activities: dict[int, dict] = {}

# ── CACHE TEMPLATES CUSTOM (rechargé depuis DB à chaque add/del/on_ready) ────
_templates_cache: dict[str, dict] = {}

# ── CACHE IMAGE OVERRIDES (clé settings : img:{template_name}) ───────────────
_image_overrides: dict[str, str] = {}


async def refresh_templates_cache() -> None:
    global _templates_cache
    _templates_cache = await db.get_custom_templates()


async def refresh_image_overrides() -> None:
    global _image_overrides
    _image_overrides = await db.get_image_overrides()


# ── PERSISTANCE ───────────────────────────────────────────────────────────────

async def save_activities() -> None:
    """Upserte toutes les activités en mémoire vers la DB."""
    for msg_id, data in activities.items():
        await db.save_activity(msg_id, data)


async def remove_activity(msg_id: int) -> None:
    """Supprime une activité de la mémoire ET de la DB."""
    activities.pop(msg_id, None)
    await db.delete_activity(msg_id)


# ── HELPERS FORMAT ARMES ─────────────────────────────────────────────────────

def _parse_weapon_slots(hint: str) -> list[tuple[str, str, int]]:
    """Parse '1H Masse (×2)  ·  Tank flex' → [(display, clean_name, count), ...]"""
    result = []
    for part in hint.split("·"):
        part = part.strip()
        if not part:
            continue
        m     = re.search(r"\(×(\d+)\)", part)
        count = int(m.group(1)) if m else 1
        clean = re.sub(r"\s*\(×\d+\)", "", part).strip()
        result.append((part.strip(), clean, count))
    return result


def _player_weapon(spec: str) -> str:
    """Extrait le nom d'arme depuis 'WeaponName (750)' → 'WeaponName'."""
    return re.sub(r"\s*\(\d+\)\s*$", "", spec).strip()


# ── HELPER : tri des rôles — PF1 d'abord, PF2 ensuite, SCOOT toujours en dernier
def _sort_roles(roles: list[str]) -> list[str]:
    pf1   = [r for r in roles if not r.startswith("PF2:") and r != "SCOOT"]
    pf2   = [r for r in roles if r.startswith("PF2:")]
    scoot = [r for r in roles if r == "SCOOT"]
    return pf1 + pf2 + scoot


# ── HELPER : tous les templates (défaut + custom) ────────────────────────────
def load_all_templates() -> dict[str, dict]:
    return {**DEFAULT_TEMPLATES, **_templates_cache}


def get_pf1(template_data: dict) -> dict[str, int]:
    if "pf_1" in template_data:
        return template_data["pf_1"]
    return {k: v for k, v in template_data.items() if isinstance(v, int)}


def get_pf2(template_data: dict) -> dict[str, int]:
    return template_data.get("pf_2", {})


def get_specs(template_data: dict) -> dict[str, str]:
    return template_data.get("weapon", template_data.get("specs", {}))


# ── CONSTRUCTION DE L'EMBED ──────────────────────────────────────────────────
def build_embed(data: dict) -> discord.Embed:
    template = data.get("template")
    max_p    = data["max_players"]
    bal      = data["bal"]
    creator  = data["creator"]
    created  = data["created_at"]

    color = DEFAULT_COLOR
    if template:
        for key, col in ACTIVITY_COLORS.items():
            if key.lower() in template.lower():
                color = col
                break

    all_templates = load_all_templates()
    tdata         = all_templates.get(template, {})
    description   = tdata.get("description", "")
    image_url     = _image_overrides.get(template, tdata.get("image", ""))

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
    specs_pf2 = tdata.get("weapon_pf2", tdata.get("specs_pf2", {})) if tdata else {}
    type_acti = tdata.get("type_acti", "") if tdata else ""

    pf1_keys      = list(pf1.keys()) if pf1 else list(slots.keys())
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

        count      = f"{len(members)}/{max_r}" if isinstance(max_r, int) else str(len(members))
        label      = f"{role_name} PF2" if is_pf2 else role_name
        field_name = f"{emoji} {label}  [{count}]"

        # ── Format PVP avec specs : sous-groupes par arme ─────────────────
        if type_acti == "PVP" and role_spec:
            weapon_groups = _parse_weapon_slots(role_spec)
            lines = []
            matched_uids: set[int] = set()

            for display, clean_name, n_slots in weapon_groups:
                lines.append(f"**{display}**")
                matched = [e for e in members if _player_weapon(e[2]) == clean_name]
                for entry in matched:
                    uid   = entry[0]
                    level = re.search(r"\((\d+)\)", entry[2])
                    lines.append(f"　-<@{uid}>{f'  ({level.group(1)})' if level else ''}")
                    matched_uids.add(uid)
                for _ in range(max(0, n_slots - len(matched))):
                    lines.append("　-—")

            # Joueurs sans arme reconnue (ajout admin sans spec, etc.)
            for entry in members:
                if entry[0] not in matched_uids:
                    uid  = entry[0]
                    spec = entry[2] if len(entry) > 2 else ""
                    lines.append(f"<@{uid}>{f'  —  {spec}' if spec else ''}")

            value = "\n".join(lines) if lines else "*Personne*"

        # ── Format PVE / sans spec : liste simple ────────────────────────
        else:
            lines = []
            for entry in members:
                uid         = entry[0]
                player_spec = entry[2] if len(entry) > 2 else ""
                lines.append(f"<@{uid}>{f'  —  {player_spec}' if player_spec else ''}")
            value = "\n".join(lines) if lines else "*Personne*"

        embed.add_field(name=field_name[:256], value=value[:1024], inline=False)

    payout_line    = "💰 BAL" if bal else "🆓 Libre"
    total_inscrits = sum(len(v) for v in slots.values())
    embed.add_field(
        name="─────────────────────────",
        value=f"**Pay Out :** {payout_line}    **Inscrits :** {total_inscrits}/{max_p}",
        inline=False,
    )

    waitlist = data.get("waitlist", [])
    if waitlist:
        wl_value = "\n".join(f"{i+1}. <@{uid}>" for i, (uid, _) in enumerate(waitlist))
        embed.add_field(name=f"⏳ Liste d'attente  [{len(waitlist)}]", value=wl_value, inline=False)

    return embed


# ── CONSTRUCTION DE LA VUE ───────────────────────────────────────────────────
def build_view(activity_id: int) -> discord.ui.View:
    return ActivityView(activity_id)


# ── HELPER : logique d'inscription mutualisée ────────────────────────────────
async def _register_player(
    interaction: discord.Interaction,
    activity_id: int,
    chosen_role: str,
    spec: str,
) -> None:
    data = activities.get(activity_id)
    if not data:
        await interaction.response.send_message("❌ Activité introuvable.", ephemeral=True)
        return

    user_id   = interaction.user.id
    user_name = interaction.user.display_name
    slots     = data["slots"]
    max_p     = data["max_players"]
    template  = data.get("template")

    total      = sum(len(v) for v in slots.values())
    already_in = any(entry[0] == user_id for members in slots.values() for entry in members)
    if total >= max_p and not already_in:
        all_templates = load_all_templates()
        has_wl = all_templates.get(template, {}).get("has_waitlist", False) if template else False
        if has_wl:
            waitlist = data.setdefault("waitlist", [])
            in_wl    = any(uid == user_id for uid, _ in waitlist)
            if in_wl:
                await interaction.response.send_message("ℹ️ Tu es déjà en liste d'attente.", ephemeral=True)
            else:
                waitlist.append((user_id, user_name))
                await save_activities()
                try:
                    channel = interaction.client.get_channel(data["channel_id"])
                    msg     = await channel.fetch_message(activity_id)
                    await msg.edit(embed=build_embed(data), view=build_view(activity_id))
                except Exception:
                    pass
                pos = len(waitlist)
                await interaction.response.send_message(
                    f"⏳ L'activité est complète — tu es en **position {pos}** sur la liste d'attente.", ephemeral=True
                )
        else:
            await interaction.response.send_message(f"⛔ L'activité est complète ({max_p} joueurs max).", ephemeral=True)
        return

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

    for role, members in slots.items():
        for entry in list(members):
            if entry[0] == user_id:
                members.remove(entry)
                break

    slots.setdefault(chosen_role, []).append((user_id, user_name, spec))
    await save_activities()

    try:
        channel = interaction.client.get_channel(data["channel_id"])
        msg     = await channel.fetch_message(activity_id)
        await msg.edit(embed=build_embed(data), view=build_view(activity_id))
    except Exception:
        pass

    label   = f"{chosen_role[4:]} PF2" if chosen_role.startswith("PF2:") else chosen_role
    confirm = f"✅ Inscrit en **{label}**{f'  —  {spec}' if spec else ''} !"
    await interaction.response.send_message(confirm, ephemeral=True)


# ── MODAL NIVEAU DE SPÉ (PVP — après sélection de l'arme) ────────────────────
class SpecLevelModal(discord.ui.Modal):
    def __init__(self, activity_id: int, chosen_role: str, chosen_weapon: str):
        super().__init__(title=f"⚔️ {chosen_weapon}"[:45])
        self.activity_id   = activity_id
        self.chosen_role   = chosen_role
        self.chosen_weapon = chosen_weapon

        self.level_input = discord.ui.TextInput(
            label="Niveau de spécialisation (1 — 1000)",
            placeholder="Ex : 750",
            required=True,
            max_length=4,
        )
        self.add_item(self.level_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            level = int(self.level_input.value.strip())
            if not (1 <= level <= 1000):
                raise ValueError()
        except ValueError:
            await interaction.response.send_message(
                "❌ Le niveau doit être un entier entre **1** et **1000**.", ephemeral=True
            )
            return
        spec = f"{self.chosen_weapon} ({level})"
        await _register_player(interaction, self.activity_id, self.chosen_role, spec)


# ── SELECT ARME (PVP uniquement) ─────────────────────────────────────────────
class WeaponSelect(discord.ui.Select):
    def __init__(self, activity_id: int, chosen_role: str, weapons_list: list[str]):
        self.activity_id = activity_id
        self.chosen_role = chosen_role
        options = []
        for w in weapons_list:
            clean = re.sub(r"\s*\(×\d+\)", "", w).strip()
            options.append(discord.SelectOption(label=clean[:100], value=clean[:100]))
        super().__init__(
            placeholder="⚔️  Choisis ton arme...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            SpecLevelModal(self.activity_id, self.chosen_role, self.values[0])
        )


class WeaponSelectView(discord.ui.View):
    def __init__(self, activity_id: int, chosen_role: str, weapons_list: list[str]):
        super().__init__(timeout=120)
        self.add_item(WeaponSelect(activity_id, chosen_role, weapons_list))


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
        type_acti     = tdata.get("type_acti", "")

        if chosen_role.startswith("PF2:"):
            hint_spec = tdata.get("weapon_pf2", tdata.get("specs_pf2", {})).get(chosen_role[4:], "")
        else:
            hint_spec = get_specs(tdata).get(chosen_role, "")

        if type_acti == "PVP" and hint_spec:
            weapons_list = [w.strip() for w in hint_spec.split("·") if w.strip()]
            if weapons_list:
                role_display = (chosen_role[4:] + " (PF2)") if chosen_role.startswith("PF2:") else chosen_role
                await interaction.response.send_message(
                    f"⚔️ **{role_display}** — Quelle arme joues-tu ?",
                    view=WeaponSelectView(self.activity_id, chosen_role, weapons_list),
                    ephemeral=True,
                )
                return

        await _register_player(interaction, self.activity_id, chosen_role, "")


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
            waitlist = data.get("waitlist", [])
            for entry in list(waitlist):
                if entry[0] == user_id:
                    waitlist.remove(entry)
                    removed = True
                    break

        if not removed:
            await interaction.response.send_message("ℹ️ Tu n'es pas inscrit à cette activité.", ephemeral=True)
            return

        await save_activities()
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

        template  = data.get("template")
        all_tpl   = load_all_templates()
        type_acti = all_tpl.get(template, {}).get("type_acti", "") if template else ""
        self.is_pve = (type_acti == "PVE")

        if self.is_pve:
            self.cout_carte = discord.ui.TextInput(
                label="Coût de la carte (silver)  + Prix des Réparation",
                placeholder="Laisser vide si pas de carte",
                required=False,
                max_length=20,
            )
            self.add_item(self.cout_carte)
        else:
            self.cout_carte = discord.ui.TextInput(
                label="Prix des Réparations",
                placeholder="Laisser vide si pas de réparation",
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

        try:
            total = int(self.recettes.value.replace(" ", "").replace(",", "").replace(".", ""))
        except ValueError:
            await interaction.response.send_message("❌ Montant recettes invalide.", ephemeral=True)
            return

        carte_cost = 0
        if self.cout_carte.value.strip():
            try:
                carte_cost = int(self.cout_carte.value.replace(" ", "").replace(",", "").replace(".", ""))
            except ValueError:
                label_err = "Coût de la carte" if self.is_pve else "Prix des réparations"
                await interaction.response.send_message(f"❌ {label_err} invalide.", ephemeral=True)
                return

        scoot_amount = 0
        if self.has_scoot:
            try:
                scoot_amount = int(self.scoot_pay.value.replace(" ", "").replace(",", "").replace(".", ""))
            except ValueError:
                await interaction.response.send_message("❌ Montant Scoot invalide.", ephemeral=True)
                return

        data     = self.data
        settings = await load_settings()
        rate     = settings.get("bal_rate", 90)

        part_guilde   = total * rate // 100
        distributable = part_guilde - carte_cost

        scoot_members = data["slots"].get("SCOOT", [])
        nb_scoot      = len(scoot_members)
        scoot_total   = scoot_amount * nb_scoot

        other_members = [(entry[0], entry[1]) for role, members in data["slots"].items()
                         for entry in members if role != "SCOOT"]
        nb_others     = len(other_members)
        remaining     = distributable - scoot_total
        part_indiv    = remaining // nb_others if nb_others > 0 else 0

        # Créditer les BAL via DB
        log_entries = []
        for uid, name in other_members:
            key       = str(uid)
            new_total = await db.increment_bal(key, part_indiv)
            log_entries.append({"uid": key, "name": name, "delta": part_indiv, "total": new_total})
        for entry in scoot_members:
            uid, name = entry[0], entry[1]
            key       = str(uid)
            new_total = await db.increment_bal(key, scoot_amount)
            log_entries.append({"uid": key, "name": name, "delta": scoot_amount, "total": new_total})
        await append_bal_log("finacti", interaction.user.display_name, log_entries)

        # Supprimer l'activité (mémoire + DB)
        await remove_activity(self.activity_id)

        fin_embed       = build_embed(data)
        fin_embed.title = f"🏁 FIN  ·  {fin_embed.title}"
        try:
            channel = interaction.client.get_channel(data["channel_id"])
            msg     = await channel.fetch_message(self.activity_id)
            await msg.edit(embed=fin_embed, view=discord.ui.View())
        except Exception:
            pass

        summary = (
            f"✅ **Activité clôturée !**\n\n"
            f"💰 Recettes : **{fmt(total)} silver**\n"
            f"🏦 Part guilde ({rate} %) : **{fmt(part_guilde)} silver**\n"
        )
        if carte_cost:
            label_cout = "Coût de la carte + réparations" if self.is_pve else "Prix des réparations"
            summary += f"🗺️ {label_cout} : **-{fmt(carte_cost)} silver** → distributable : **{fmt(distributable)} silver**\n"
        if self.has_scoot:
            summary += (
                f"🏃 Scoot ({nb_scoot} joueur(s)) : **{fmt(scoot_amount)} silver/joueur**\n"
                f"👥 Reste ({nb_others} joueur(s)) : **{fmt(part_indiv)} silver/joueur**\n"
                f"📊 BAL crédités — Scoot : **+{fmt(scoot_amount)}** · Reste : **+{fmt(part_indiv)}**"
            )
        else:
            summary += (
                f"👥 Participants : **{nb_others}**\n"
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

        if data.get("bal"):
            await interaction.response.send_modal(FinActiModal(self.activity_id, data))
            return

        # Activité Libre → clôture directe
        fin_embed       = build_embed(data)
        fin_embed.title = f"🏁 FIN  ·  {fin_embed.title}"
        await remove_activity(self.activity_id)
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

        await remove_activity(self.activity_id)
        embed = discord.Embed(
            title="🚫 Activité annulée",
            description=f"L'activité a été annulée par {interaction.user.display_name}.",
            color=0x95A5A6,
        )
        await interaction.message.edit(embed=embed, view=discord.ui.View())
        await interaction.response.send_message("✅ Activité annulée.", ephemeral=True)


# ── BOUTON LISTE D'ATTENTE ────────────────────────────────────────────────────
class WaitlistButton(discord.ui.Button):
    def __init__(self, activity_id: int):
        super().__init__(
            label="Liste d'attente", emoji="⏳",
            style=discord.ButtonStyle.secondary,
            custom_id=f"waitlist_{activity_id}",
        )
        self.activity_id = activity_id

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

        user_id   = interaction.user.id
        user_name = interaction.user.display_name
        slots     = data["slots"]
        waitlist  = data.setdefault("waitlist", [])

        if any(entry[0] == user_id for members in slots.values() for entry in members):
            await interaction.response.send_message(
                "ℹ️ Tu es déjà inscrit à l'activité.", ephemeral=True
            )
            return

        for entry in list(waitlist):
            if entry[0] == user_id:
                waitlist.remove(entry)
                await save_activities()
                await interaction.message.edit(embed=build_embed(data), view=build_view(self.activity_id))
                await interaction.response.send_message("👋 Tu t'es retiré de la liste d'attente.", ephemeral=True)
                return

        waitlist.append((user_id, user_name))
        await save_activities()
        await interaction.message.edit(embed=build_embed(data), view=build_view(self.activity_id))
        pos = len(waitlist)
        await interaction.response.send_message(
            f"⏳ Inscrit en liste d'attente — position **{pos}**.", ephemeral=True
        )


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
        if tdata.get("has_waitlist"):
            self.add_item(WaitlistButton(activity_id))
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
        # Charger les caches depuis la DB
        await refresh_templates_cache()
        await refresh_image_overrides()

        # Charger toutes les activités depuis la DB
        loaded = await db.load_activities()
        activities.update(loaded)

        # Enregistrer les vues persistantes + vérifier que les messages existent
        to_delete = []
        for msg_id in list(activities.keys()):
            data = activities[msg_id]
            # Enregistrer la vue pour que les boutons/selects fonctionnent sans re-edit
            self.bot.add_view(build_view(msg_id))
            try:
                channel = self.bot.get_channel(data["channel_id"])
                if channel:
                    msg = await channel.fetch_message(msg_id)
                    await msg.edit(view=build_view(msg_id))
                else:
                    to_delete.append(msg_id)
            except Exception:
                to_delete.append(msg_id)

        for msg_id in to_delete:
            activities.pop(msg_id, None)
            await db.delete_activity(msg_id)

        print(f"   {len(activities)} activité(s) rechargée(s) depuis la DB.")

    # ── /acti ────────────────────────────────────────────────────────────────
    @app_commands.command(name="acti", description="Créer une activité de guilde Albion Online")
    @app_commands.describe(
        nametemplate = "Template de composition (optionnel — sans template : activité PVP libre DPS/HEAL/SUPPORT)",
        nbplayer     = "Nombre de joueurs max (calculé automatiquement depuis le template si renseigné)",
        bal          = "Paiement BAL ? (true = BAL, false = Libre)",
    )
    @app_commands.autocomplete(nametemplate=template_autocomplete)
    async def acti(
        self,
        interaction:  discord.Interaction,
        nametemplate: str = "",
        nbplayer:     app_commands.Range[int, 1, 100] | None = None,
        bal:          bool = True,
    ):
        if not is_membre(interaction.user):
            await interaction.response.send_message(
                f"⛔ Tu dois avoir le rôle **{MEMBRE_ROLE_NAME}** pour créer une activité.", ephemeral=True
            )
            return

        # ── Sans template : activité PVP libre DPS / HEAL / SUPPORT ────────
        if not nametemplate:
            slots         = {"DPS": [], "HEAL": [], "SUPPORT": []}
            template_name = None
            nbplayer      = nbplayer or 100
        else:
            all_templates = load_all_templates()
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
            "waitlist":    [],
        }

        await interaction.response.send_message(embed=build_embed(data))
        message = await interaction.original_response()
        activities[message.id] = data
        await save_activities()
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
            pf2         = get_pf2(tdata)
            specs       = get_specs(tdata)
            specs_pf2   = tdata.get("weapon_pf2", tdata.get("specs_pf2", {}))
            type_acti   = tdata.get("type_acti", "—")
            description = tdata.get("description", "")
            tag         = "🔴 PVP" if type_acti == "PVP" else "🟢 PVE" if type_acti == "PVE" else type_acti
            total       = sum(pf1.values()) + sum(pf2.values())

            lines = []
            # PF1
            for role, n in pf1.items():
                emoji    = ROLES.get(role, "🔹")
                spec_str = f"  `{specs[role]}`" if role in specs else ""
                lines.append(f"{emoji} **{role}** ×{n}{spec_str}")
            # PF2
            if pf2:
                lines.append("🔶 **PF2**")
                for role, n in pf2.items():
                    emoji    = ROLES.get(role, "🔹")
                    spec_str = f"  `{specs_pf2[role]}`" if role in specs_pf2 else ""
                    lines.append(f"{emoji} **{role}** ×{n}{spec_str}")

            header = f"{tag}  ·  {total} joueurs  ·  {description}" if description else f"{tag}  ·  {total} joueurs"
            value  = f"*{header}*\n" + "\n".join(lines)
            embed.add_field(name=name, value=value[:1024], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ── SETUP ─────────────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(Activites(bot))
