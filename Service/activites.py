import io
import re
import secrets
import asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone

import db
from config import ROLES, DEFAULT_TEMPLATES, ACTIVITY_COLORS, DEFAULT_COLOR, ADMIN_ROLE_NAME, MEMBRE_ROLE_NAME
from Service.build_image import compo_image, compo_rows
from Service.utils import load_settings, append_bal_log, is_membre, is_caller_or_admin, notify_bal_limit, fmt_silver, log_error

# ── STOCKAGE EN MÉMOIRE  {message_id: data} ──────────────────────────────────
activities: dict[int, dict] = {}

# ── CACHE TEMPLATES CUSTOM par serveur (rechargé depuis DB à chaque add/del/on_ready) ─
_templates_cache: dict[int, dict[str, dict]] = {}

# ── CACHE IMAGE OVERRIDES par serveur (clé settings : img:{guild_id}:{template_name}) ─
_image_overrides: dict[int, dict[str, str]] = {}

# ── CACHE DESCRIPTION OVERRIDES par serveur (clé settings : desc:{guild_id}:{template_name}) ─
_description_overrides: dict[int, dict[str, str]] = {}


# Activités en cours de clôture (anti double /finacti)
_finishing: set[int] = set()

MAX_SILVER = 1_000_000_000_000


def parse_silver(raw: str) -> int | None:
    """Montant saisi (« 1 200 000 », « 1,200,000 », « 1.200.000 ») → int.
    None si invalide, négatif ou absurde (> MAX_SILVER)."""
    cleaned = raw.strip().replace(" ", "").replace(",", "").replace(".", "")
    if not (cleaned.isascii() and cleaned.isdigit()):
        return None
    value = int(cleaned)
    return value if value <= MAX_SILVER else None


async def refresh_templates_cache() -> None:
    global _templates_cache
    _templates_cache = await db.get_custom_templates()


async def refresh_image_overrides() -> None:
    global _image_overrides
    _image_overrides = await db.get_image_overrides()


async def refresh_description_overrides() -> None:
    global _description_overrides
    _description_overrides = await db.get_description_overrides()


# ── PERSISTANCE ───────────────────────────────────────────────────────────────

async def save_activities(only: int | None = None) -> None:
    """Upserte les activités en mémoire vers la DB. Si only est fourni, ne sauvegarde que cette activité."""
    if only is not None:
        if only in activities:
            await db.save_activity(only, activities[only])
    else:
        for msg_id, data in activities.items():
            await db.save_activity(msg_id, data)


async def remove_activity(msg_id: int, outcome: str | None = None) -> None:
    """Supprime une activité de la mémoire ET de la DB. `outcome` ('finacti' | 'fin' | 'annulée') :
    l'activité terminée est d'abord copiée dans activity_log (stats d'activité du site) —
    une erreur d'historique ne doit jamais empêcher la fin de l'acti."""
    data = activities.pop(msg_id, None)
    if data and outcome:
        try:
            tdata = load_all_templates(data.get("guild_id", 0)).get(data.get("template") or "", {})
            await db.add_activity_log(activity_log_row(data, tdata, outcome))
        except Exception as e:
            from Service.utils import log_error
            await log_error("activites.activity_log", e, guild_id=data.get("guild_id"))
    await db.delete_activity(msg_id)


def activity_log_row(data: dict, tdata: dict, outcome: str) -> dict:
    """Instantané d'une activité terminée : qui était inscrit où, et combien de places il y avait."""
    capacity = {**get_pf1(tdata), **{f"PF2:{r}": n for r, n in get_pf2(tdata).items()}} if tdata else {}
    created = data.get("created_at")
    return {
        "guild_id":    int(data.get("guild_id") or 0),
        "created_at":  created if isinstance(created, datetime) else None,
        "template":    data.get("template") or "",
        "type_acti":   tdata.get("type_acti", "") if tdata else "",
        "creator_id":  str(data.get("creator_id") or ""),
        "max_players": int(data.get("max_players") or 0),
        "slots":       {role: [str(e[0]) for e in members] for role, members in data.get("slots", {}).items() if members},
        "capacity":    {role: int(n) for role, n in capacity.items()},
        "outcome":     outcome,
    }


# ── HELPERS FORMAT ARMES ─────────────────────────────────────────────────────

MAX_WEAPON_SLOTS = 50  # au-delà, un « (×N) » géant ferait générer N lignes à chaque affichage (mémoire)


def _parse_weapon_slots(hint: str) -> list[tuple[str, str, int | None]]:
    """Parse '1H Masse (×2) · Brassards (×infini)' → [(display, clean_name, count|None), ...]
    count=None = illimité ; un compteur > MAX_WEAPON_SLOTS est ramené à MAX_WEAPON_SLOTS.
    """
    result = []
    for part in hint.split("·"):
        part = part.strip()
        if not part:
            continue
        if re.search(r"\(×(?:infini|∞)\)", part, re.IGNORECASE):
            count = None
            clean = re.sub(r"\s*\(×(?:infini|∞)\)", "", part, flags=re.IGNORECASE).strip()
        else:
            m     = re.search(r"\(×(\d+)\)", part)
            count = min(int(m.group(1)), MAX_WEAPON_SLOTS) if m else 1
            clean = re.sub(r"\s*\(×\d+\)", "", part).strip()
        result.append((part.strip(), clean, count))
    return result


def _player_weapon(spec: str) -> str:
    """Extrait le nom d'arme depuis 'WeaponName (750)' → 'WeaponName'."""
    return re.sub(r"\s*\(\d+\)\s*$", "", spec).strip()


# ── HELPER : rôle de base d'une clé de slot ─────────────────────────────────
# Une compo du site peut avoir plusieurs lignes du même rôle (ex. 2 tanks avec des builds
# différents) : leurs clés deviennent « TANK · Def tank », « TANK · Main tank » (ou « TANK 2 »
# pour une ligne libre). Emoji, couleur, tri, paie et loot se basent sur le rôle de base.
_DUP_SUFFIX = re.compile(r"^(.*\S) \d+$")


def base_role(key: str) -> str:
    """« PF2:TANK · Main tank » → « TANK » ; « DPS 2 » → « DPS » (si DPS est un rôle connu)."""
    role = key[4:] if key.startswith("PF2:") else key
    role = role.split(" · ", 1)[0].strip()
    m = _DUP_SUFFIX.match(role)
    if m and m.group(1) in ROLES:
        return m.group(1)
    return role


# ── HELPER : tri des rôles — PF1 d'abord, PF2 ensuite, SCOOT toujours en dernier
def _sort_roles(roles: list[str]) -> list[str]:
    pf1   = [r for r in roles if not r.startswith("PF2:") and r != "SCOOT"]
    pf2   = [r for r in roles if r.startswith("PF2:")]
    scoot = [r for r in roles if r == "SCOOT"]
    return pf1 + pf2 + scoot


# ── HELPER : tous les templates visibles sur un serveur (défaut + custom) ────
def load_all_templates(guild_id: int) -> dict[str, dict]:
    defaults = {
        name: tpl for name, tpl in DEFAULT_TEMPLATES.items()
        if not tpl.get("guild_ids") or guild_id in tpl["guild_ids"]
    }
    return {**defaults, **_templates_cache.get(guild_id, {})}


def get_pf1(template_data: dict) -> dict[str, int]:
    if "pf_1" in template_data:
        return template_data["pf_1"]
    return {k: v for k, v in template_data.items() if isinstance(v, int)}


def get_pf2(template_data: dict) -> dict[str, int]:
    return template_data.get("pf_2", {})


def get_specs(template_data: dict) -> dict[str, str]:
    return template_data.get("weapon", template_data.get("specs", {}))


def build_ids_for_role(template_data: dict, role_key: str) -> list[int]:
    """Builds proposés pour ce rôle par une compo du site (clés "builds" / "builds_pf2") :
    {rôle: id} (ancien format, un build imposé) ou {rôle: [id, id…]} (plusieurs builds au choix).
    role_key = "TANK" ou "PF2:TANK". Liste vide = pas de build."""
    if role_key.startswith("PF2:"):
        builds, role = template_data.get("builds_pf2") or {}, role_key[4:]
    else:
        builds, role = template_data.get("builds") or {}, role_key
    value = builds.get(role)
    if value is None:
        return []
    return [int(v) for v in (value if isinstance(value, list) else [value])]


def build_id_for_role(template_data: dict, role_key: str) -> int | None:
    """Premier build proposé pour ce rôle, ou None."""
    ids = build_ids_for_role(template_data, role_key)
    return ids[0] if ids else None


# ── HELPER : lignes d'un créneau de rôle dans l'embed ───────────────────────
def _slot_lines(members: list, role_spec: str, tdata: dict, type_acti: str, grouped: bool) -> list[str]:
    """Lignes affichées pour un créneau (jamais vide). grouped = le créneau est un sous-bloc
    d'une catégorie (ex. 2 lignes TANK) : joueurs indentés, place libre en « -— »."""
    empty = "　-—" if grouped else "*Personne*"

    # ── Format PVP avec specs : sous-groupes par arme ─────────────────────
    if type_acti == "PVP" and role_spec and not tdata.get("no_spec"):
        # Mode compact (free_pick) : hint sur une ligne + joueur par ligne
        if tdata.get("free_pick"):
            lines = [f"*{role_spec}*"]
            for entry in members:
                uid    = entry[0]
                spec   = entry[2] if len(entry) > 2 else ""
                weapon = _player_weapon(spec) if spec else ""
                level  = re.search(r"\((\d+)\)", spec) if spec else None
                if weapon:
                    lines.append(f"{weapon} — <@{uid}>{f' — {level.group(1)}' if level else ''}")
                else:
                    lines.append(f"<@{uid}>")
            return lines if members else [*lines, empty]

        lines = []
        matched_uids: set[int] = set()
        for display, clean_name, n_slots in _parse_weapon_slots(role_spec):
            lines.append(f"**{display}**")
            matched = [e for e in members if _player_weapon(e[2]) == clean_name]
            for entry in matched:
                uid   = entry[0]
                level = re.search(r"\((\d+)\)", entry[2])
                lines.append(f"　-<@{uid}>{f'  ({level.group(1)})' if level else ''}")
                matched_uids.add(uid)
            if n_slots is not None:
                for _ in range(max(0, n_slots - len(matched))):
                    lines.append("　-—")
        for entry in members:
            if entry[0] not in matched_uids:
                uid  = entry[0]
                spec = entry[2] if len(entry) > 2 else ""
                lines.append(f"<@{uid}>{f'  —  {spec}' if spec else ''}")
        return lines or [empty]

    # ── Format PVE / sans spec : liste simple ────────────────────────────
    lines = []
    if role_spec and tdata.get("no_spec"):
        lines.append(f"*{role_spec}*")
    indent = "　-" if grouped else ""
    for entry in members:
        uid         = entry[0]
        player_spec = entry[2] if len(entry) > 2 else ""
        lines.append(f"{indent}<@{uid}>{f'  —  {player_spec}' if player_spec else ''}")
    return lines if members else [*lines, empty]


# ── CONSTRUCTION DE L'EMBED ──────────────────────────────────────────────────
def build_embed(data: dict) -> discord.Embed:
    template = data.get("template")
    max_p    = data["max_players"]
    bal      = data["bal"]
    creator  = data["creator"]
    created  = data["created_at"]
    depart   = data.get("depart", "")
    tier     = data.get("tier", "")
    guild_id = data.get("guild_id", 0)

    color = DEFAULT_COLOR
    if template:
        for key, col in ACTIVITY_COLORS.items():
            if key.lower() in template.lower():
                color = col
                break

    all_templates = load_all_templates(guild_id)
    tdata         = all_templates.get(template, {})
    guild_desc_overrides  = _description_overrides.get(guild_id, {})
    guild_image_overrides = _image_overrides.get(guild_id, {})
    tpl_desc    = guild_desc_overrides.get(template, tdata.get("description", "")) if template else tdata.get("description", "")
    custom_desc = data.get("custom_description", "")
    top_info_parts = []
    if depart:
        top_info_parts.append(f"📍 **Départ :** {depart}")
    if tier:
        top_info_parts.append(f"⚔️ **Tier :** {tier}")
    top_info   = "   ".join(top_info_parts)
    desc_block = "\n".join(filter(None, [tpl_desc, custom_desc]))
    if desc_block and top_info:
        full_desc = f"{desc_block}\n\n{top_info}"
    else:
        full_desc = desc_block or top_info or None
    image_url     = guild_image_overrides.get(template, tdata.get("image", ""))

    embed = discord.Embed(
        title=f"🗡️  {template or 'Activité'}  de {creator}",
        description=full_desc,
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

    pf1_has_any_full = pf1 and any(
        len(slots.get(role, [])) >= pf1.get(role, 0)
        for role in pf1 if pf1.get(role, 0) > 0
    )

    # Créneaux regroupés par catégorie (PF, rôle de base) : « TANK » et « TANK · Main tank »
    # s'affichent sous un seul en-tête 🛡️ TANK, chaque créneau en sous-bloc.
    groups: dict[tuple[bool, str], list[str]] = {}
    for role_key in roles_to_show:
        if role_key in ("Fill", "PF2:Fill"):
            continue
        groups.setdefault((role_key.startswith("PF2:"), base_role(role_key)), []).append(role_key)

    pf2_header_done = False
    for (is_pf2, base), keys in groups.items():
        if is_pf2 and not pf2_header_done:
            if pf1_has_any_full:
                pf2_label = "─────────────────────────\n🔶  PF2"
            else:
                pf2_label = "─────────────────────────\n🔒  PF2  —  disponible quand un rôle PF1 est complet"
            embed.add_field(name=pf2_label, value="​", inline=False)
            pf2_header_done = True

        grouped       = len(keys) > 1
        blocks        = []
        filled, total = 0, 0
        for role_key in keys:
            role_name = role_key[4:] if is_pf2 else role_key
            members   = slots.get(role_key, [])
            if is_pf2:
                max_r     = pf2.get(role_name, "∞")
                role_spec = specs_pf2.get(role_name, "")
            else:
                max_r     = pf1.get(role_key, "∞") if pf1 else "∞"
                role_spec = specs.get(role_key, "")
            filled += len(members)
            total   = total + max_r if isinstance(total, int) and isinstance(max_r, int) else "∞"

            lines = _slot_lines(members, role_spec, tdata, type_acti, grouped)
            if grouped:
                # Sous-titre du créneau, sauf si son arme (déjà en gras) le porte déjà
                sub = role_name.split(" · ", 1)[1].strip() if " · " in role_name else ""
                if not lines[0].startswith("**") or (sub and sub.lower() not in lines[0].lower()):
                    lines.insert(0, f"**{sub or role_name}**")
            blocks.append("\n".join(lines))

        label      = base if grouped else (keys[0][4:] if is_pf2 else keys[0])
        label      = f"{label} PF2" if is_pf2 else label
        count      = f"{filled}/{total}" if isinstance(total, int) else str(filled)
        field_name = f"{ROLES.get(base, '🔹')} {label}  [{count}]"
        embed.add_field(name=field_name[:256], value="\n".join(blocks)[:1024], inline=False)

    fill_members = slots.get("Fill", [])
    if fill_members:
        fill_value = "\n".join(f"<@{entry[0]}>" for entry in fill_members)
        embed.add_field(name=f"🔀 Fill  [{len(fill_members)}]", value=fill_value[:1024], inline=False)

    pending = data.get("pending", [])
    if pending:
        pending_value = "\n".join(
            f"<@{p['uid']}> — {_role_label(p['role'])}" + (f"  ({p['spec']})" if p.get("spec") else "")
            for p in pending
        )
        embed.add_field(name=f"⏳ En attente de validation  [{len(pending)}]", value=pending_value[:1024], inline=False)

    payout_line    = "💰 BAL" if bal else "🆓 Libre"
    total_inscrits = sum(len(v) for v in slots.values())
    validation     = "\n🔒 Inscriptions sur validation du caller" if data.get("validation") else ""
    embed.add_field(
        name="─────────────────────────",
        value=f"**Pay Out :** {payout_line}    **Inscrits :** {total_inscrits}/{max_p}{validation}",
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


async def _post_compo_image(interaction: discord.Interaction, template_name: str, template_data: dict) -> None:
    """Poste, juste après l'embed de l'acti, l'image de tous les builds de la compo
    (compos du site uniquement). Ne bloque jamais l'acti en cas d'erreur."""
    rows = compo_rows(template_data)
    if not rows:
        return
    try:
        builds = await db.get_builds_by_ids([bid for *_, bid in rows], interaction.guild.id)
        png = await compo_image(template_name, template_data, builds)
        if png:
            await interaction.followup.send(file=discord.File(io.BytesIO(png), filename="compo.png"))
    except Exception as e:
        await log_error("activites.compo_image", e, guild_id=interaction.guild.id, user_id=interaction.user.id)


# ── HELPER : label affiché d'une activité ───────────────────────────────────
def _acti_label(data: dict) -> str:
    return data.get("thread_name") or data.get("template") or "Activité"


# ── HELPER : vérification créateur ──────────────────────────────────────────
def _is_creator(user: discord.User | discord.Member, data: dict) -> bool:
    # Pas de repli sur le pseudo : n'importe qui pourrait prendre le même display_name
    return bool(data.get("creator_id")) and user.id == data["creator_id"]


# ── HELPER : logique d'inscription mutualisée ────────────────────────────────
async def _reply(interaction: discord.Interaction, *args, **kwargs) -> None:
    """Répond via followup si déjà déféré, sinon via send_message."""
    if interaction.response.is_done():
        await interaction.followup.send(*args, **kwargs)
    else:
        await interaction.response.send_message(*args, **kwargs)


async def _register_player(
    interaction: discord.Interaction,
    activity_id: int,
    chosen_role: str,
    spec: str,
) -> None:
    data = activities.get(activity_id)
    if not data:
        await _reply(interaction, "❌ Activité introuvable.", ephemeral=True)
        return

    user_id   = interaction.user.id
    user_name = interaction.user.display_name
    slots     = data["slots"]
    max_p     = data["max_players"]
    template  = data.get("template")

    total      = sum(len(v) for v in slots.values())
    already_in = any(entry[0] == user_id for members in slots.values() for entry in members)
    if total >= max_p and not already_in:
        all_templates = load_all_templates(data.get("guild_id", 0))
        has_wl = all_templates.get(template, {}).get("has_waitlist", False) if template else False
        if has_wl:
            waitlist = data.setdefault("waitlist", [])
            in_wl    = any(uid == user_id for uid, _ in waitlist)
            if in_wl:
                await _reply(interaction, "ℹ️ Tu es déjà en liste d'attente.", ephemeral=True)
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
                await _reply(interaction,
                    f"⏳ L'activité est complète — tu es en **position {pos}** sur la liste d'attente.", ephemeral=True
                )
        else:
            await _reply(interaction, f"⛔ L'activité est complète ({max_p} joueurs max).", ephemeral=True)
        return

    all_templates = load_all_templates(data.get("guild_id", 0))
    tdata = all_templates.get(template, {}) if template else {}
    error = registration_error(data, tdata, user_id, chosen_role, spec)
    if error:
        await _reply(interaction, error, ephemeral=True)
        return

    # Acti sur validation : la demande part au caller au lieu d'inscrire directement.
    if needs_validation(data, interaction.user, already_in):
        await _request_validation(interaction, activity_id, chosen_role, spec)
        return

    _place_player(data, user_id, user_name, chosen_role, spec)
    await save_activities(only=activity_id)
    await _refresh_activity_message(interaction.client, activity_id)
    await _reply(interaction, f"✅ Inscrit en **{_role_label(chosen_role)}**{f'  —  {spec}' if spec else ''} !",
                 ephemeral=True)


def _role_label(role_key: str) -> str:
    return f"{role_key[4:]} PF2" if role_key.startswith("PF2:") else role_key


def registration_error(data: dict, tdata: dict, user_id: int, chosen_role: str, spec: str) -> str | None:
    """Contrôles de place d'un rôle (et de la sous-limite d'arme) : message d'erreur ou None.
    Utilisé à l'inscription et à l'acceptation d'une demande (/acti validation)."""
    if not tdata:
        return None
    slots     = data["slots"]
    is_pf2    = chosen_role.startswith("PF2:")
    role_name = chosen_role[4:] if is_pf2 else chosen_role
    max_role  = get_pf2(tdata).get(role_name, 999) if is_pf2 else get_pf1(tdata).get(chosen_role, 999)
    current_in_role = [entry[0] for entry in slots.get(chosen_role, [])]
    if len(current_in_role) >= max_role and user_id not in current_in_role:
        return f"⛔ Plus de place en **{_role_label(chosen_role)}** ({max_role} max)."

    # ── Sous-limite d'arme (ignorée en mode free_pick) ──────────────────────
    # Pas pour une ligne avec build imposé (compo du site) : le hint y est le NOM du build,
    # pas une liste d'armes « (×N) » — seul le nombre de places de la ligne compte.
    if build_id_for_role(tdata, chosen_role) is not None:
        return None
    if spec and tdata.get("type_acti") == "PVP" and not tdata.get("free_pick"):
        hint_spec = (
            tdata.get("weapon_pf2", tdata.get("specs_pf2", {})).get(role_name, "")
            if is_pf2 else get_specs(tdata).get(chosen_role, "")
        )
        if hint_spec:
            weapon_name = _player_weapon(spec)
            for _display, clean_name, n_slots in _parse_weapon_slots(hint_spec):
                if clean_name == weapon_name and n_slots is not None:
                    taken = sum(
                        1 for e in slots.get(chosen_role, [])
                        if _player_weapon(e[2]) == weapon_name and e[0] != user_id
                    )
                    if taken >= n_slots:
                        return f"⛔ Plus de place pour **{weapon_name}** ({n_slots} max)."
                    break
    return None


def _place_player(data: dict, user_id: int, user_name: str, chosen_role: str, spec: str) -> None:
    """Retire le joueur de son ancien rôle (et de ses demandes en attente) puis l'inscrit."""
    for members in data["slots"].values():
        for entry in members[:]:
            if entry[0] == user_id:
                members.remove(entry)
                break
    data["pending"] = [p for p in data.get("pending", []) if p["uid"] != user_id]
    data["slots"].setdefault(chosen_role, []).append((user_id, user_name, spec))


async def _refresh_activity_message(client: discord.Client, activity_id: int) -> None:
    data = activities.get(activity_id)
    if not data:
        return
    try:
        channel = client.get_channel(data["channel_id"])
        msg     = await channel.fetch_message(activity_id)
        await msg.edit(embed=build_embed(data), view=build_view(activity_id))
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# INSCRIPTIONS SUR VALIDATION (/acti validation:True)
# Chaque nouvelle inscription part dans data["pending"] ; le créateur reçoit un MP
# (boutons persistants ValidationButton) et les Caller/Officiers/GM peuvent aussi
# trancher via le bouton « ⏳ En attente » de l'acti. Le joueur en attente
# n'occupe pas de place (ni pingé par /massup, ni payé par /finacti).
# ══════════════════════════════════════════════════════════════════════════════

def can_validate(member, data: dict) -> bool:
    """Créateur de l'acti, ou Caller / Officier / GM / administrateur."""
    if _is_creator(member, data):
        return True
    return hasattr(member, "roles") and is_caller_or_admin(member)


def needs_validation(data: dict, member, already_in: bool) -> bool:
    """Seuls le créateur de l'acti et un joueur déjà accepté qui change de rôle passent directement
    (les Caller/Officiers/GM/admins passent aussi par la validation, mais peuvent valider les autres)."""
    return bool(data.get("validation")) and not already_in and not _is_creator(member, data)


def _new_rid() -> str:
    return secrets.token_hex(3)


def _find_pending(data: dict, user_id: int) -> dict | None:
    return next((p for p in data.get("pending", []) if p["uid"] == user_id), None)


def _activity_link(data: dict, activity_id: int) -> str:
    return f"https://discord.com/channels/{data.get('guild_id', 0)}/{data['channel_id']}/{activity_id}"


def _request_embed(data: dict, activity_id: int, req: dict) -> discord.Embed:
    spec = f"  —  {req['spec']}" if req.get("spec") else ""
    return discord.Embed(
        title="⏳ Demande d'inscription",
        description=(
            f"<@{req['uid']}> (**{req['name']}**) veut s'inscrire en **{_role_label(req['role'])}**{spec}\n"
            f"à **{_acti_label(data)}** → [voir l'activité]({_activity_link(data, activity_id)})"
        ),
        color=DEFAULT_COLOR,
    )


class ValidationButton(discord.ui.DynamicItem[discord.ui.Button],
                       template=r"actival:(?P<aid>\d+):(?P<uid>\d+):(?P<rid>[0-9a-f]+):(?P<act>[ar])"):
    """Bouton Accepter / Refuser du MP envoyé au créateur — persistant (survit aux redémarrages)."""

    def __init__(self, activity_id: int, user_id: int, rid: str, accept: bool):
        self.activity_id, self.user_id, self.rid, self.accept = activity_id, user_id, rid, accept
        super().__init__(discord.ui.Button(
            label="Accepter" if accept else "Refuser",
            emoji="✅" if accept else "❌",
            style=discord.ButtonStyle.success if accept else discord.ButtonStyle.danger,
            custom_id=f"actival:{activity_id}:{user_id}:{rid}:{'a' if accept else 'r'}",
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["aid"]), int(match["uid"]), match["rid"], match["act"] == "a")

    async def callback(self, interaction: discord.Interaction):
        await _decide(interaction, self.activity_id, self.user_id, self.rid, self.accept, from_dm=True)


def validation_view(activity_id: int, user_id: int, rid: str) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(ValidationButton(activity_id, user_id, rid, True))
    view.add_item(ValidationButton(activity_id, user_id, rid, False))
    return view


async def _dm(client: discord.Client, user_id: int, *args, **kwargs) -> bool:
    """MP sans jamais lever : False si MP fermés / utilisateur introuvable."""
    try:
        user = client.get_user(user_id) or await client.fetch_user(user_id)
        await user.send(*args, **kwargs)
        return True
    except (discord.Forbidden, discord.NotFound):
        return False
    except Exception as e:
        await log_error("activites.validation_dm", e, user_id=user_id)
        return False


async def _request_validation(interaction: discord.Interaction, activity_id: int, chosen_role: str, spec: str) -> None:
    data = activities[activity_id]
    user = interaction.user
    req  = {"uid": user.id, "name": user.display_name, "role": chosen_role, "spec": spec, "rid": _new_rid()}
    data["pending"] = [p for p in data.get("pending", []) if p["uid"] != user.id] + [req]
    await save_activities(only=activity_id)
    await _refresh_activity_message(interaction.client, activity_id)

    sent = False
    if data.get("creator_id"):
        sent = await _dm(interaction.client, data["creator_id"],
                         embed=_request_embed(data, activity_id, req),
                         view=validation_view(activity_id, user.id, req["rid"]))
    where = "Le caller a reçu ta demande en MP." if sent else "Un caller la validera depuis l'activité."
    await _reply(interaction,
                 f"⏳ Demande d'inscription en **{_role_label(chosen_role)}** envoyée — {where} "
                 f"Tu recevras un MP quand elle sera traitée.", ephemeral=True)


async def _validator(interaction: discord.Interaction, data: dict):
    """Membre du serveur qui clique (en MP, interaction.user n'a pas de rôles)."""
    user = interaction.user
    if hasattr(user, "roles"):
        return user
    guild = interaction.client.get_guild(data.get("guild_id", 0))
    if guild is None:
        return user
    try:
        return guild.get_member(user.id) or await guild.fetch_member(user.id)
    except Exception:
        return user


async def _decide(interaction: discord.Interaction, activity_id: int, user_id: int, rid: str | None,
                  accept: bool, *, from_dm: bool = False) -> None:
    """Accepte ou refuse une demande en attente (MP du créateur ou bouton « En attente » de l'acti)."""
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)   # MP + base : peut dépasser les 3 s de Discord
    data = activities.get(activity_id)
    if not data:
        await _reply(interaction, "❌ Activité introuvable (terminée ou annulée).", ephemeral=True)
        return
    if not can_validate(await _validator(interaction, data), data):
        await _reply(interaction, "⛔ Seuls le créateur de l'acti et les Caller/Officiers/GM peuvent valider.",
                     ephemeral=True)
        return
    req = _find_pending(data, user_id)
    if not req or (rid and req["rid"] != rid):
        await _reply(interaction, "ℹ️ Demande obsolète : déjà traitée, retirée ou remplacée.", ephemeral=True)
        return

    label = _acti_label(data)
    if accept:
        tdata = load_all_templates(data.get("guild_id", 0)).get(data.get("template") or "", {})
        error = registration_error(data, tdata, user_id, req["role"], req["spec"])
        total = sum(len(v) for v in data["slots"].values())
        if not error and total >= data["max_players"]:
            error = f"⛔ L'activité est complète ({data['max_players']} joueurs max)."
        if error:
            await _reply(interaction, f"{error} La demande de <@{user_id}> reste en attente.", ephemeral=True)
            return
        _place_player(data, user_id, req["name"], req["role"], req["spec"])
    else:
        data["pending"] = [p for p in data["pending"] if p["uid"] != user_id]
    await save_activities(only=activity_id)
    await _refresh_activity_message(interaction.client, activity_id)

    role_txt = _role_label(req["role"])
    by       = interaction.user.display_name
    if accept:
        player_msg = (f"✅ Ton inscription à **{label}** en **{role_txt}** a été validée par {by}."
                      f"  →  {_activity_link(data, activity_id)}")
    else:
        player_msg = f"❌ Ton inscription à **{label}** en **{role_txt}** a été refusée par {by}."
    await _dm(interaction.client, user_id, player_msg)

    done = f"{'✅ Acceptée' if accept else '❌ Refusée'} : <@{user_id}> en **{role_txt}** (par {by})."
    if from_dm and interaction.message:
        try:   # le MP du créateur garde la demande, sans les boutons
            await interaction.message.edit(content=done, view=None)
            return
        except Exception:
            pass
    await _reply(interaction, done, ephemeral=True)


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
        await interaction.response.defer(ephemeral=True)
        spec = f"{self.chosen_weapon} ({level})"
        await _register_player(interaction, self.activity_id, self.chosen_role, spec)


# ── MODAL ARME LIBRE (no_spec — rôles avec * dans le hint) ──────────────────
class FreeWeaponModal(discord.ui.Modal):
    def __init__(self, activity_id: int, chosen_role: str, hint: str):
        super().__init__(title=f"⚔️ {chosen_role}"[:45])
        self.activity_id = activity_id
        self.chosen_role = chosen_role

        placeholder = re.sub(r"\s*\*", "", hint).strip()[:100]
        self.weapon_input = discord.ui.TextInput(
            label="Quelle arme joues-tu ?",
            placeholder=placeholder,
            required=True,
            max_length=50,
        )
        self.add_item(self.weapon_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await _register_player(interaction, self.activity_id, self.chosen_role, self.weapon_input.value.strip())


# ── MODAL ARME + SPÉ (free_pick — une ligne par joueur dans l'embed) ─────────
class WeaponAndSpecModal(discord.ui.Modal):
    def __init__(self, activity_id: int, chosen_role: str, hint: str):
        super().__init__(title=f"⚔️ {chosen_role}"[:45])
        self.activity_id = activity_id
        self.chosen_role = chosen_role

        self.weapon_input = discord.ui.TextInput(
            label="Quelle arme joues-tu ?",
            placeholder=hint[:100],
            required=True,
            max_length=50,
        )
        self.level_input = discord.ui.TextInput(
            label="Niveau de spécialisation (1 — 1000)",
            placeholder="Ex : 750",
            required=True,
            max_length=4,
        )
        self.add_item(self.weapon_input)
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
        await interaction.response.defer(ephemeral=True)
        spec = f"{self.weapon_input.value.strip()} ({level})"
        await _register_player(interaction, self.activity_id, self.chosen_role, spec)


# ── SELECT ARME (PVP uniquement) ─────────────────────────────────────────────
class WeaponSelect(discord.ui.Select):
    def __init__(self, activity_id: int, chosen_role: str, weapons_list: list[str],
                 current_members: list):
        self.activity_id = activity_id
        self.chosen_role = chosen_role
        options = []
        for w in weapons_list:
            parsed = _parse_weapon_slots(w)
            if not parsed:
                continue
            _display, clean, n_slots = parsed[0]
            if n_slots is not None:
                taken = sum(1 for e in current_members if _player_weapon(e[2]) == clean)
                if taken >= n_slots:
                    continue  # arme pleine, on ne la propose pas
            options.append(discord.SelectOption(label=clean[:100], value=clean[:100]))
        if not options:
            options = [discord.SelectOption(label="Aucune arme disponible", value="__full__")]
        super().__init__(
            placeholder="⚔️  Choisis ton arme...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "__full__":
            await interaction.response.send_message(
                "⛔ Toutes les armes sont complètes pour ce rôle.", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            SpecLevelModal(self.activity_id, self.chosen_role, self.values[0])
        )


class WeaponSelectView(discord.ui.View):
    def __init__(self, activity_id: int, chosen_role: str, weapons_list: list[str],
                 current_members: list):
        super().__init__(timeout=120)
        self.add_item(WeaponSelect(activity_id, chosen_role, weapons_list, current_members))


# ── HELPERS : rôles encore ouverts, regroupés par rôle de base ───────────────
def available_role_keys(data: dict, tdata: dict, roles: list[str]) -> list[str]:
    """Clés de rôle encore proposables : rôles pleins masqués, PF2 masquée tant
    qu'aucun rôle PF1 n'est complet."""
    slots = data.get("slots", {})
    pf1   = get_pf1(tdata) if tdata else {}
    pf2   = get_pf2(tdata) if tdata else {}
    pf1_has_any_full = pf1 and any(
        len(slots.get(role, [])) >= pf1.get(role, 0)
        for role in pf1 if pf1.get(role, 0) > 0
    )
    keys = []
    for role_key in roles:
        is_pf2    = role_key.startswith("PF2:")
        role_name = role_key[4:] if is_pf2 else role_key
        if is_pf2 and not pf1_has_any_full:
            continue
        max_r = pf2.get(role_name) if is_pf2 else (pf1.get(role_key) if pf1 else None)
        if max_r is not None and len(slots.get(role_key, [])) >= max_r:
            continue
        keys.append(role_key)
    return keys


def role_group(role_key: str) -> str:
    """« PF2:TANK · Main tank » → « PF2:TANK » ; « DPS · Weeping » → « DPS »."""
    return ("PF2:" if role_key.startswith("PF2:") else "") + base_role(role_key)


def group_role_keys(keys: list[str]) -> dict[str, list[str]]:
    """Regroupe les clés par rôle de base (ordre conservé) : une compo du site à
    plusieurs builds par rôle se choisit en deux temps, rôle puis build."""
    groups: dict[str, list[str]] = {}
    for key in keys:
        groups.setdefault(role_group(key), []).append(key)
    return groups


def build_label(role_key: str) -> str:
    """Nom du build d'une clé de rôle (« DPS · Weeping » → « Weeping »), sinon la clé sans PF2."""
    role = role_key[4:] if role_key.startswith("PF2:") else role_key
    return role.split(" · ", 1)[1].strip() if " · " in role else role


def _activity_tdata(data: dict) -> dict:
    template = data.get("template")
    return load_all_templates(data.get("guild_id", 0)).get(template, {}) if template else {}


# ── SELECT MENU ──────────────────────────────────────────────────────────────
class RoleSelect(discord.ui.Select):
    def __init__(self, activity_id: int, roles: list[str]):
        self.activity_id = activity_id
        data  = activities.get(activity_id, {})
        tdata = _activity_tdata(data)

        options = []
        for group, keys in group_role_keys(available_role_keys(data, tdata, roles)).items():
            is_pf2 = group.startswith("PF2:")
            if len(keys) == 1:
                # Un seul choix pour ce rôle : inscription directe, comme avant.
                key       = keys[0]
                role_name = key[4:] if is_pf2 else key
                label = f"{role_name} (PF2)" if is_pf2 else role_name
                desc  = f"PF2 — S'inscrire en {role_name}" if is_pf2 else f"S'inscrire en tant que {role_name}"
                value = key
            else:
                role_name = group[4:] if is_pf2 else group
                label = f"{role_name} (PF2)" if is_pf2 else role_name
                desc  = f"{len(keys)} builds au choix"
                value = f"grp:{group}"
            options.append(discord.SelectOption(
                label=label[:100],
                emoji=ROLES.get(base_role(group), "🔹"),
                description=desc[:100],
                value=value[:100],
            ))

        if not options:
            options = [discord.SelectOption(label="⛔ Toutes les places sont prises", value="__full__")]

        super().__init__(
            placeholder="📋  Choisis ton rôle...",
            min_values=1,
            max_values=1,
            options=options[:25],
            custom_id=f"roleselect_{activity_id}",
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "__full__":
            await interaction.response.send_message("⛔ Toutes les places sont prises.", ephemeral=True)
            return
        if not self.values[0].startswith("grp:"):
            await _choose_role(interaction, self.activity_id, self.values[0])
            return
        if not await _can_register(interaction, self.activity_id):
            return
        group = self.values[0][4:]
        view  = BuildSelectView(self.activity_id, group)
        if not view.has_choices:
            await interaction.response.send_message("⛔ Plus de place pour ce rôle.", ephemeral=True)
            return
        role_display = f"{group[4:]} (PF2)" if group.startswith("PF2:") else group
        await interaction.response.send_message(
            f"{ROLES.get(base_role(group), '🔹')} **{role_display}** — Quel build joues-tu ?",
            view=view, ephemeral=True,
        )


# ── SELECT BUILD (2ᵉ étape quand un rôle a plusieurs builds) ─────────────────
class BuildSelect(discord.ui.Select):
    def __init__(self, activity_id: int, options: list[discord.SelectOption]):
        self.activity_id = activity_id
        super().__init__(placeholder="🛠️  Choisis ton build...", min_values=1, max_values=1,
                         options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        await _choose_role(interaction, self.activity_id, self.values[0])


class BuildSelectView(discord.ui.View):
    def __init__(self, activity_id: int, group: str):
        super().__init__(timeout=120)
        data  = activities.get(activity_id, {})
        tdata = _activity_tdata(data)
        pf1   = get_pf1(tdata) if tdata else {}
        pf2   = get_pf2(tdata) if tdata else {}
        roles = list(pf1.keys()) + [f"PF2:{r}" for r in pf2.keys()]
        keys  = [k for k in available_role_keys(data, tdata, roles) if role_group(k) == group]
        options = []
        for key in keys:
            max_r = pf2.get(key[4:]) if key.startswith("PF2:") else pf1.get(key)
            taken = len(data.get("slots", {}).get(key, []))
            options.append(discord.SelectOption(
                label=build_label(key)[:100],
                emoji=ROLES.get(base_role(key), "🔹"),
                description=f"Places : {taken}/{max_r}" if max_r is not None else None,
                value=key[:100],
            ))
        self.has_choices = bool(options)
        if options:
            self.add_item(BuildSelect(activity_id, options))


async def _can_register(interaction: discord.Interaction, activity_id: int) -> bool:
    """Contrôles communs avant une inscription ; répond à l'interaction en cas de refus."""
    if not is_membre(interaction.user):
        await interaction.response.send_message(
            f"⛔ Tu dois avoir le rôle **{MEMBRE_ROLE_NAME}** pour t'inscrire.", ephemeral=True
        )
        return False
    if not activities.get(activity_id):
        await interaction.response.send_message("❌ Activité introuvable.", ephemeral=True)
        return False
    return True


async def _choose_role(interaction: discord.Interaction, activity_id: int, chosen_role: str) -> None:
    """Suite de l'inscription une fois la clé de rôle choisie (arme, spé ou inscription directe)."""
    if not await _can_register(interaction, activity_id):
        return
    data      = activities[activity_id]
    tdata     = _activity_tdata(data)
    type_acti = tdata.get("type_acti", "")

    if chosen_role.startswith("PF2:"):
        hint_spec = tdata.get("weapon_pf2", tdata.get("specs_pf2", {})).get(chosen_role[4:], "")
    else:
        hint_spec = get_specs(tdata).get(chosen_role, "")

    # Compo du site : le rôle a un build imposé → inscription directe au
    # choix du rôle (ni liste d'armes ni saisie de spé), le build fait office d'arme.
    if build_id_for_role(tdata, chosen_role) is not None:
        build_name = hint_spec or chosen_role
        await interaction.response.defer(ephemeral=True)
        await _register_player(interaction, activity_id, chosen_role, build_name)
        return

    if type_acti == "PVP" and hint_spec and not tdata.get("no_spec"):
        if tdata.get("free_pick"):
            await interaction.response.send_modal(
                WeaponAndSpecModal(activity_id, chosen_role, hint_spec)
            )
            return
        weapons_list     = [w.strip() for w in hint_spec.split("·") if w.strip()]
        current_members  = data["slots"].get(chosen_role, [])
        if weapons_list:
            role_display = (chosen_role[4:] + " (PF2)") if chosen_role.startswith("PF2:") else chosen_role
            await interaction.response.send_message(
                f"⚔️ **{role_display}** — Quelle arme joues-tu ?",
                view=WeaponSelectView(activity_id, chosen_role, weapons_list, current_members),
                ephemeral=True,
            )
            return

    if tdata.get("no_spec") and hint_spec and "*" in hint_spec:
        await interaction.response.send_modal(
            FreeWeaponModal(activity_id, chosen_role, hint_spec)
        )
        return

    await interaction.response.defer(ephemeral=True)
    await _register_player(interaction, activity_id, chosen_role, "")


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
            for entry in members[:]:
                if entry[0] == user_id:
                    members.remove(entry)
                    removed = True
                    break
            if removed:
                break

        if not removed and _find_pending(data, user_id):
            data["pending"] = [p for p in data["pending"] if p["uid"] != user_id]
            removed = True

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

        await interaction.response.defer(ephemeral=True)
        await save_activities(only=self.activity_id)
        await interaction.message.edit(embed=build_embed(data), view=build_view(self.activity_id))
        await interaction.followup.send("👋 Tu t'es retiré de l'activité.", ephemeral=True)


# ── BOUTON FILL ───────────────────────────────────────────────────────────────
class FillButton(discord.ui.Button):
    def __init__(self, activity_id: int):
        super().__init__(
            label="Fill", emoji="🔀",
            style=discord.ButtonStyle.primary,
            custom_id=f"fill_{activity_id}",
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

        user_id = interaction.user.id
        slots   = data["slots"]

        already_in = any(entry[0] == user_id for members in slots.values() for entry in members)
        if already_in:
            await interaction.response.send_message("ℹ️ Tu es déjà inscrit à cette activité.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await _register_player(interaction, self.activity_id, "Fill", "")


# ── MODAL FIN D'ACTIVITÉ ─────────────────────────────────────────────────────
class FinActiModal(discord.ui.Modal, title="Clôturer l'activité"):
    recettes = discord.ui.TextInput(
        label="VM du coffre",
        placeholder="Ex : 10000000",
        required=True,
        max_length=20,
    )

    def __init__(self, activity_id: int, data: dict):
        super().__init__()
        self.activity_id = activity_id
        self.data        = data
        self.has_scoot   = bool(data["slots"].get("SCOOT"))

        template        = data.get("template")
        all_tpl         = load_all_templates(data.get("guild_id", 0))
        tpl_data        = all_tpl.get(template, {}) if template else {}
        type_acti       = tpl_data.get("type_acti", "")
        self.is_pve          = (type_acti == "PVE")
        self.zero_pay_roles  = set(tpl_data.get("zero_pay_roles", []))
        self.template_tax    = tpl_data.get("tax_rate")          # None = utilise le taux guilde
        self.role_multipliers = tpl_data.get("role_multipliers", {})

        if self.is_pve:
            self.cout_carte = discord.ui.TextInput(
                label="Carte + Réparations (silver)",
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
        self.sac_pieces = discord.ui.TextInput(
            label="montant des pièces",
            placeholder="Laisser vide si aucune pièce",
            required=False,
            max_length=20,
        )
        self.add_item(self.sac_pieces)

        if self.has_scoot:
            self.scoot_pay = discord.ui.TextInput(
                label="Paiement Scoot (silver/joueur)",
                placeholder="Ex : 500000",
                required=True,
                max_length=20,
            )
            self.add_item(self.scoot_pay)

    async def on_submit(self, interaction: discord.Interaction):

        # Valider les montants AVANT le defer (encore dans les 3s)
        total = parse_silver(self.recettes.value)
        if total is None:
            await interaction.response.send_message("❌ Montant recettes invalide.", ephemeral=True)
            return

        carte_cost = 0
        if self.cout_carte.value.strip():
            carte_cost = parse_silver(self.cout_carte.value)
            if carte_cost is None:
                label_err = "Coût de la carte" if self.is_pve else "Prix des réparations"
                await interaction.response.send_message(f"❌ {label_err} invalide.", ephemeral=True)
                return
        if carte_cost > total:
            await interaction.response.send_message("❌ Les coûts dépassent les recettes.", ephemeral=True)
            return

        sac_pieces = 0
        if self.sac_pieces.value.strip():
            sac_pieces = parse_silver(self.sac_pieces.value)
            if sac_pieces is None:
                await interaction.response.send_message("❌ Montant pièces coffre invalide.", ephemeral=True)
                return

        scoot_amount = 0
        if self.has_scoot:
            scoot_amount = parse_silver(self.scoot_pay.value)
            if scoot_amount is None:
                await interaction.response.send_message("❌ Montant Scoot invalide.", ephemeral=True)
                return

        # Anti double paiement : une seule clôture à la fois, et seulement si l'activité existe encore
        # (pas d'await entre le test et l'ajout → atomique pour la boucle asyncio)
        if self.activity_id in _finishing or self.activity_id not in activities:
            await interaction.response.send_message("❌ Cette activité est déjà clôturée.", ephemeral=True)
            return
        _finishing.add(self.activity_id)
        try:
            await self._finish(interaction, total, carte_cost, sac_pieces, scoot_amount)
        finally:
            _finishing.discard(self.activity_id)

    async def _finish(self, interaction: discord.Interaction, total: int, carte_cost: int,
                      sac_pieces: int, scoot_amount: int):
        # Defer pour éviter le timeout Discord pendant les appels DB
        await interaction.response.defer()

        try:
            data     = activities.get(self.activity_id, self.data)
            settings = await load_settings(guild_id=interaction.guild.id)
            rate     = self.template_tax if self.template_tax is not None else settings.get("bal_rate", 85)

            part_guilde   = (total - carte_cost) * rate // 100
            distributable = part_guilde + sac_pieces

            scoot_members = data["slots"].get("SCOOT", [])
            nb_scoot      = len(scoot_members)
            scoot_total   = scoot_amount * nb_scoot
            remaining     = distributable - scoot_total
            if remaining < 0:
                await interaction.followup.send(
                    f"❌ Le paiement Scoot ({fmt_silver(scoot_total)} silver) dépasse le distribuable "
                    f"({fmt_silver(distributable)} silver). Rien n'a été crédité.", ephemeral=True
                )
                return

            # Liste des membres payés avec leur multiplicateur (uid, name, role, mult)
            paying = [
                (entry[0], entry[1], role,
                 float(self.role_multipliers.get(role, self.role_multipliers.get(base_role(role), 1.0))))
                for role, members in data["slots"].items()
                for entry in members
                if role != "SCOOT" and role not in self.zero_pay_roles and base_role(role) not in self.zero_pay_roles
            ]
            total_weight = sum(m[3] for m in paying)
            part_base    = int(remaining / total_weight) if total_weight > 0 else 0

            # Créditer les BAL via DB (batch)
            deltas: dict[str, int] = {}
            for uid, name, role, mult in paying:
                deltas[str(uid)] = deltas.get(str(uid), 0) + int(part_base * mult)
            for entry in scoot_members:
                key = str(entry[0])
                deltas[key] = deltas.get(key, 0) + scoot_amount

            new_totals = await db.increment_bal_batch(deltas, guild_id=interaction.guild.id)

            # Compter la présence de tous les participants
            all_ids = list({str(entry[0]) for members in data["slots"].values() for entry in members})
            if all_ids:
                await db.increment_acti_count(all_ids, guild_id=interaction.guild.id)

            log_entries = []
            for uid, name, role, mult in paying:
                key = str(uid)
                log_entries.append({"uid": key, "name": name, "delta": int(part_base * mult), "total": new_totals[key]})
            for entry in scoot_members:
                uid, name = entry[0], entry[1]
                key = str(uid)
                log_entries.append({"uid": key, "name": name, "delta": scoot_amount, "total": new_totals[key]})

            await append_bal_log("finacti", interaction.user.display_name, log_entries, template=data.get("template") or "", guild_id=interaction.guild.id)
            await asyncio.gather(*[
                notify_bal_limit(interaction.client, int(uid), total, guild_id=interaction.guild.id)
                for uid, total in new_totals.items()
            ])

            # Supprimer l'activité (mémoire + DB)
            await remove_activity(self.activity_id, "finacti")

            fin_embed       = build_embed(data)
            fin_embed.title = f"🏁 FIN  ·  {fin_embed.title}"
            try:
                channel = interaction.client.get_channel(data["channel_id"])
                msg     = await channel.fetch_message(self.activity_id)
                await msg.edit(embed=fin_embed, view=discord.ui.View())
            except Exception:
                pass

            # ── Grouper les membres par multiplicateur pour le récap ─────────────
            normal_members = [(m[0], m[1]) for m in paying if m[3] == 1.0]
            bonus_groups: dict[tuple, list] = {}
            for uid, name, role, mult in paying:
                if mult != 1.0:
                    key_g = (role, mult)
                    bonus_groups.setdefault(key_g, []).append((uid, name))

            nb_normal  = len(normal_members)
            part_indiv = part_base  # mult=1.0

            label_cout = "Carte + réparations" if self.is_pve else "Réparations"
            summary = (
                f"✅ **Activité clôturée !**\n\n"
                f"💰 Recettes VM : **{fmt_silver(total)} silver**\n"
            )
            if carte_cost:
                summary += f"🗺️ {label_cout} : **-{fmt_silver(carte_cost)} silver**\n"
            summary += f"🏦 Part guilde ({rate} %) : **{fmt_silver(part_guilde)} silver**\n"
            if sac_pieces:
                summary += f"🎒 Pièces : **+{fmt_silver(sac_pieces)} silver** → distributable : **{fmt_silver(distributable)} silver**\n"
            if self.has_scoot:
                summary += f"🏃 Scoot ({nb_scoot} joueur(s)) : **{fmt_silver(scoot_amount)} silver/joueur**\n"
            for (role, mult), members in bonus_groups.items():
                emoji  = ROLES.get(base_role(role), "🔹")
                pay_r  = int(part_base * mult)
                summary += f"{emoji} {role} (×{mult}) : **{fmt_silver(pay_r)} silver/joueur** ({len(members)} joueur(s))\n"
            if self.has_scoot:
                summary += (
                    f"👥 Reste ({nb_normal} joueur(s)) : **{fmt_silver(part_indiv)} silver/joueur**\n"
                    f"📊 BAL crédités — Scoot : **+{fmt_silver(scoot_amount)}** · Reste : **+{fmt_silver(part_indiv)}**"
                )
            else:
                summary += (
                    f"👥 Participants : **{nb_normal}**\n"
                    f"💵 Part individuelle : **{fmt_silver(part_indiv)} silver**\n"
                    f"📊 BAL crédités : **+{fmt_silver(part_indiv)} BAL / joueur**"
                )
            await interaction.followup.send(summary)

        except Exception as e:
            await log_error("activites.FinActiModal", e, guild_id=interaction.guild.id, user_id=interaction.user.id)
            await interaction.followup.send(
                "❌ **Erreur FinActi** — détail enregistré pour le staff (`/errors`).", ephemeral=True
            )


# ── MODAL MODIFICATION D'ACTIVITÉ ────────────────────────────────────────────
class EditActiModal(discord.ui.Modal, title="Modifier l'activité"):
    def __init__(self, activity_id: int, data: dict):
        super().__init__()
        self.activity_id = activity_id
        self.data        = data

        self.desc_input = discord.ui.TextInput(
            label="Description",
            placeholder="Note libre affichée dans le post",
            required=False,
            max_length=500,
            style=discord.TextStyle.paragraph,
            default=data.get("custom_description", "") or None,
        )
        self.tier_input = discord.ui.TextInput(
            label="Tier requis",
            placeholder="Ex : T7, T8.3…",
            required=False,
            max_length=50,
            default=data.get("tier", "") or None,
        )
        self.depart_input = discord.ui.TextInput(
            label="Départ (Ville / HO / Libre)",
            placeholder="Ville, HO ou Libre",
            required=False,
            max_length=10,
            default=data.get("depart", "Libre"),
        )
        self.add_item(self.desc_input)
        self.add_item(self.tier_input)
        self.add_item(self.depart_input)

    async def on_submit(self, interaction: discord.Interaction):
        _depart_map = {"ville": "Ville", "ho": "HO", "libre": "Libre"}
        raw        = self.depart_input.value.strip()
        depart_val = _depart_map.get(raw.lower(), "") if raw else "Libre"
        if raw and not depart_val:
            await interaction.response.send_message(
                "❌ Départ invalide. Choisir parmi : **Ville**, **HO**, **Libre**.", ephemeral=True
            )
            return

        self.data["custom_description"] = self.desc_input.value.strip()
        self.data["tier"]               = self.tier_input.value.strip()
        self.data["depart"]             = depart_val

        await save_activities(only=self.activity_id)
        try:
            channel = interaction.client.get_channel(self.data["channel_id"])
            msg     = await channel.fetch_message(self.activity_id)
            await msg.edit(embed=build_embed(self.data), view=build_view(self.activity_id))
        except Exception:
            pass
        await interaction.response.send_message("✅ Activité mise à jour !", ephemeral=True)


# ── BOUTON MODIFIER L'ACTIVITÉ ────────────────────────────────────────────────
class EditActiButton(discord.ui.Button):
    def __init__(self, activity_id: int):
        super().__init__(
            label="Modifier", emoji="✏️",
            style=discord.ButtonStyle.secondary,
            custom_id=f"editacti_{activity_id}",
        )
        self.activity_id = activity_id

    async def callback(self, interaction: discord.Interaction):
        data = activities.get(self.activity_id)
        if not data:
            await interaction.response.send_message("❌ Activité introuvable.", ephemeral=True)
            return
        is_creator = _is_creator(interaction.user, data)
        if not (is_creator or is_caller_or_admin(interaction.user)):
            await interaction.response.send_message(
                "⛔ Seul l'organisateur ou un **Officier** peut modifier l'activité.", ephemeral=True
            )
            return
        await interaction.response.send_modal(EditActiModal(self.activity_id, data))


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
        try:
            data = activities.get(self.activity_id)
            if not data:
                await interaction.response.send_message("❌ Activité introuvable.", ephemeral=True)
                return

            is_creator = _is_creator(interaction.user, data)
            has_role   = any(r.name == ADMIN_ROLE_NAME for r in interaction.user.roles)
            if not (is_creator or has_role or interaction.user.guild_permissions.administrator):
                await interaction.response.send_message(
                    f"⛔ Seul l'organisateur ou un **{ADMIN_ROLE_NAME}** peut clôturer l'activité.", ephemeral=True
                )
                return

            if data.get("bal"):
                await interaction.response.send_modal(FinActiModal(self.activity_id, data))
                return
        except Exception as e:
            await log_error("activites.FinActiButton", e, guild_id=interaction.guild.id, user_id=interaction.user.id)
            msg = "❌ **Erreur FinActi** — détail enregistré pour le staff (`/errors`)."
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(msg, ephemeral=True)
                else:
                    await interaction.followup.send(msg, ephemeral=True)
            except Exception:
                pass
            return

        # Activité Libre → clôture directe
        await interaction.response.defer(ephemeral=True)
        try:
            fin_embed       = build_embed(data)
            fin_embed.title = f"🏁 FIN  ·  {fin_embed.title}"

            all_ids = list({str(entry[0]) for members in data["slots"].values() for entry in members})
            if all_ids:
                await db.increment_acti_count(all_ids, guild_id=interaction.guild.id)

            await remove_activity(self.activity_id, "fin")
            try:
                channel = interaction.client.get_channel(data["channel_id"])
                msg     = await channel.fetch_message(self.activity_id)
                await msg.edit(embed=fin_embed, view=discord.ui.View())
            except Exception:
                pass

            await interaction.followup.send("✅ Activité clôturée !", ephemeral=True)

        except Exception as e:
            await log_error("activites.FinActiButton_libre", e, guild_id=interaction.guild.id, user_id=interaction.user.id)
            await interaction.followup.send(
                "❌ **Erreur FinActi** — détail enregistré pour le staff (`/errors`).", ephemeral=True
            )


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

        is_creator = _is_creator(interaction.user, data)
        is_admin   = interaction.user.guild_permissions.administrator
        if not (is_creator or is_admin):
            await interaction.response.send_message("⛔ Seul l'organisateur ou un admin peut annuler.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await remove_activity(self.activity_id, "annulée")
        embed = discord.Embed(
            title="🚫 Activité annulée",
            description=f"L'activité a été annulée par {interaction.user.display_name}.",
            color=0x95A5A6,
        )
        await interaction.message.edit(embed=embed, view=discord.ui.View())
        await interaction.followup.send("✅ Activité annulée.", ephemeral=True)


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
                await interaction.response.defer(ephemeral=True)
                await save_activities(only=self.activity_id)
                await interaction.message.edit(embed=build_embed(data), view=build_view(self.activity_id))
                await interaction.followup.send("👋 Tu t'es retiré de la liste d'attente.", ephemeral=True)
                return

        waitlist.append((user_id, user_name))
        await interaction.response.defer(ephemeral=True)
        await save_activities(only=self.activity_id)
        await interaction.message.edit(embed=build_embed(data), view=build_view(self.activity_id))
        pos = len(waitlist)
        await interaction.followup.send(
            f"⏳ Inscrit en liste d'attente — position **{pos}**.", ephemeral=True
        )


# ── VUE PRINCIPALE ───────────────────────────────────────────────────────────
# ── BOUTON « EN ATTENTE » (acti sur validation) ──────────────────────────────
class PendingButton(discord.ui.Button):
    def __init__(self, activity_id: int, count: int = 0):
        super().__init__(
            label=f"En attente ({count})", emoji="⏳",
            style=discord.ButtonStyle.secondary,
            custom_id=f"pending_{activity_id}",
        )
        self.activity_id = activity_id

    async def callback(self, interaction: discord.Interaction):
        data = activities.get(self.activity_id)
        if not data:
            await interaction.response.send_message("❌ Activité introuvable.", ephemeral=True)
            return
        if not can_validate(interaction.user, data):
            await interaction.response.send_message(
                "⛔ Réservé au créateur de l'acti et aux Caller/Officiers/GM.", ephemeral=True
            )
            return
        pending = data.get("pending", [])
        if not pending:
            await interaction.response.send_message("✅ Aucune demande en attente.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"⏳ **{len(pending)}** demande(s) en attente — choisis un joueur puis accepte ou refuse.",
            view=PendingReviewView(self.activity_id, pending), ephemeral=True,
        )


class PendingReviewView(discord.ui.View):
    """Vue éphémère : sélection d'une demande + Accepter / Refuser."""

    def __init__(self, activity_id: int, pending: list[dict]):
        super().__init__(timeout=300)
        self.activity_id = activity_id
        self.selected: int | None = None
        self.select = discord.ui.Select(
            placeholder="Choisis une demande…",
            options=[
                discord.SelectOption(
                    label=f"{p['name']} — {_role_label(p['role'])}"[:100],
                    description=p["spec"][:100] if p.get("spec") else None,
                    value=str(p["uid"]),
                )
                for p in pending[:25]
            ],
        )
        self.select.callback = self._on_select
        self.add_item(self.select)

    async def _on_select(self, interaction: discord.Interaction):
        self.selected = int(self.select.values[0])
        await interaction.response.defer()

    async def _decide_selected(self, interaction: discord.Interaction, accept: bool):
        if self.selected is None:
            await interaction.response.send_message("ℹ️ Choisis d'abord une demande dans la liste.", ephemeral=True)
            return
        await _decide(interaction, self.activity_id, self.selected, None, accept)

    @discord.ui.button(label="Accepter", emoji="✅", style=discord.ButtonStyle.success, row=1)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._decide_selected(interaction, True)

    @discord.ui.button(label="Refuser", emoji="❌", style=discord.ButtonStyle.danger, row=1)
    async def refuse_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._decide_selected(interaction, False)


class ActivityView(discord.ui.View):
    def __init__(self, activity_id: int):
        super().__init__(timeout=None)
        data = activities.get(activity_id)
        if not data:
            return

        all_templates = load_all_templates(data.get("guild_id", 0))
        template      = data.get("template")
        tdata         = all_templates.get(template, {}) if template else {}
        pf1           = get_pf1(tdata) if tdata else {}
        pf2           = get_pf2(tdata) if tdata else {}
        pf1_keys      = list(pf1.keys()) if pf1 else list(ROLES.keys())
        pf2_keys      = [f"PF2:{r}" for r in pf2.keys()]
        roles_to_show = _sort_roles(pf1_keys + pf2_keys)

        if not tdata.get("no_register"):
            self.add_item(RoleSelect(activity_id, roles_to_show))
            self.add_item(LeaveButton(activity_id))
            if not tdata.get("has_waitlist"):
                self.add_item(FillButton(activity_id))
        if tdata.get("has_waitlist"):
            self.add_item(WaitlistButton(activity_id))
        if data.get("validation"):
            self.add_item(PendingButton(activity_id, len(data.get("pending", []))))
        self.add_item(EditActiButton(activity_id))
        self.add_item(FinActiButton(activity_id))
        self.add_item(CancelButton(activity_id))


# ── AUTOCOMPLÉTION : templates disponibles ───────────────────────────────────
async def template_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    all_templates = load_all_templates(interaction.guild.id)
    return [
        app_commands.Choice(name=name, value=name)
        for name in all_templates
        if current.lower() in name.lower()
    ][:25]


# ── COG ACTIVITÉS ─────────────────────────────────────────────────────────────
class Activites(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.refresh_templates_loop.start()
        # Boutons Accepter/Refuser des MP de validation : actifs même après un redémarrage.
        self.bot.add_dynamic_items(ValidationButton)

    async def cog_unload(self):
        self.refresh_templates_loop.cancel()

    # ── Les compos créées depuis le site web (process séparé, même base) ne
    # peuvent pas appeler refresh_templates_cache() en direct : on recharge le
    # cache périodiquement. try/except obligatoire — une exception non
    # rattrapée dans un @tasks.loop arrête la boucle définitivement.
    @tasks.loop(minutes=2)
    async def refresh_templates_loop(self):
        try:
            await refresh_templates_cache()
        except Exception as e:
            await log_error("activites.refresh_templates_loop", e)

    @refresh_templates_loop.before_loop
    async def before_refresh_templates(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        # Charger les caches depuis la DB
        await refresh_templates_cache()
        await refresh_image_overrides()
        await refresh_description_overrides()

        # Charger toutes les activités depuis la DB
        loaded = await db.load_activities()
        activities.update(loaded)

        # Enregistrer les vues persistantes + vérifier que les messages existent
        to_delete = []
        for msg_id in list(activities.keys()):
            data = activities[msg_id]
            changed = False

            # Enrichir thread_name pour les vieilles activités
            channel = self.bot.get_channel(data["channel_id"])
            if channel and data.get("thread_name") is None and isinstance(channel, discord.Thread):
                data["thread_name"] = channel.name
                changed = True

            # Ajouter les slots manquants si le template a évolué
            all_templates = load_all_templates(data.get("guild_id", 0))
            tpl = all_templates.get(data.get("template") or "")
            if tpl:
                for role in list(tpl.get("pf_1", {})) + list(tpl.get("pf_2", {})):
                    if role not in data["slots"]:
                        data["slots"][role] = []
                        changed = True

            if changed:
                await save_activities(only=msg_id)

            # Enregistrer la vue pour que les boutons/selects fonctionnent sans re-edit
            try:
                self.bot.add_view(build_view(msg_id))
            except Exception as e:
                await log_error("activites.add_view", e, guild_id=data.get("guild_id"))
            try:
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
        nametemplate = "Template de composition (optionnel — sans template : activité libre DPS/HEAL/SUPPORT)",
        nbplayer     = "Nombre de joueurs max (calculé automatiquement depuis le template si renseigné)",
        bal          = "Paiement BAL ? (true = BAL, false = Libre)",
        depart       = "Point de départ (Ville / HO / Libre)",
        tier         = "Tier requis (ex : T7, T8.3…)",
        validation   = "Inscriptions sur validation : chaque joueur doit être accepté par toi (MP) ou un Caller",
    )
    @app_commands.autocomplete(nametemplate=template_autocomplete)
    @app_commands.choices(depart=[
        app_commands.Choice(name="Ville", value="Ville"),
        app_commands.Choice(name="HO",    value="HO"),
        app_commands.Choice(name="Libre", value="Libre"),
    ])
    async def acti(
        self,
        interaction:  discord.Interaction,
        nametemplate: str = "",
        nbplayer:     app_commands.Range[int, 1, 100] | None = None,
        bal:          bool = True,
        depart:       str = "Libre",
        tier:         str = "",
        validation:   bool = False,
    ):
        if not is_membre(interaction.user):
            await interaction.response.send_message(
                f"⛔ Tu dois avoir le rôle **{MEMBRE_ROLE_NAME}** pour créer une activité.", ephemeral=True
            )
            return

        # ── Si simple Membre (pas Caller/GM/Officier), bal forcé à False ────
        if not is_caller_or_admin(interaction.user):
            bal = False

        # ── Sans template : activité PVP libre DPS / HEAL / SUPPORT ────────
        if not nametemplate:
            slots         = {"DPS": [], "HEAL": [], "SUPPORT": []}
            template_name = None
            nbplayer      = nbplayer or 100
        else:
            all_templates = load_all_templates(interaction.guild.id)
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

        thread_name = (
            interaction.channel.name
            if isinstance(interaction.channel, discord.Thread)
            else None
        )

        data = {
            "creator":            interaction.user.display_name,
            "creator_id":         interaction.user.id,
            "created_at":         datetime.now(timezone.utc),
            "template":           template_name,
            "thread_name":        thread_name,
            "max_players":        nbplayer,
            "bal":                bal,
            "depart":             depart,
            "tier":               tier,
            "custom_description": "",
            "slots":              slots,
            "channel_id":         interaction.channel_id,
            "guild_id":           interaction.guild.id,
            "waitlist":           [],
            "validation":         validation,
            "pending":            [],
        }

        await interaction.response.send_message(embed=build_embed(data))
        message = await interaction.original_response()
        activities[message.id] = data
        await save_activities()
        await message.edit(view=build_view(message.id))

        # Compo du site : on poste juste après l'embed une image avec tous les builds.
        if template_name:
            await _post_compo_image(interaction, template_name, all_templates[template_name])

    # ── /templates ───────────────────────────────────────────────────────────
    @app_commands.command(name="templates", description="Afficher les templates de compositions disponibles")
    async def list_templates(self, interaction: discord.Interaction):
        if not is_membre(interaction.user):
            await interaction.response.send_message(
                f"⛔ Tu dois avoir le rôle **{MEMBRE_ROLE_NAME}** pour utiliser cette commande.", ephemeral=True
            )
            return
        all_templates = load_all_templates(interaction.guild.id)
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
                emoji    = ROLES.get(base_role(role), "🔹")
                spec_str = f"  `{specs[role]}`" if role in specs else ""
                lines.append(f"{emoji} **{role}** ×{n}{spec_str}")
            # PF2
            if pf2:
                lines.append("🔶 **PF2**")
                for role, n in pf2.items():
                    emoji    = ROLES.get(base_role(role), "🔹")
                    spec_str = f"  `{specs_pf2[role]}`" if role in specs_pf2 else ""
                    lines.append(f"{emoji} **{role}** ×{n}{spec_str}")

            header = f"{tag}  ·  {total} joueurs  ·  {description}" if description else f"{tag}  ·  {total} joueurs"
            value  = f"*{header}*\n" + "\n".join(lines)
            embed.add_field(name=name, value=value[:1024], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ── SETUP ─────────────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(Activites(bot))
