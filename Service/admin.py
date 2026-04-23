import discord
import json
import re
from discord.ext import commands
from discord import app_commands

import db
from config import ADMIN_ROLE_NAME, GM_ROLE_NAME, ROLES, DEFAULT_BAL_RATE, DEFAULT_TEMPLATES
from Service.activites import (
    activities, build_embed, build_view, get_pf1, get_pf2,
    load_all_templates, save_activities, refresh_templates_cache, refresh_image_overrides,
)
from Service.utils import is_admin, is_membre, is_caller_or_admin, ActivitySelect, load_settings, save_settings


# ── AUTOCOMPLÉTION : rôles disponibles ───────────────────────────────────────
async def role_autocomplete(
    _interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=role, value=role)
        for role in ROLES
        if current.lower() in role.lower()
    ][:25]


# ── FLOW ARME + NIVEAU pour /addacti PVP ─────────────────────────────────────
class AdminSpecLevelModal(discord.ui.Modal):
    def __init__(self, msg_id: int, target_id: int, target_name: str,
                 chosen_role: str, chosen_weapon: str, data: dict):
        super().__init__(title=f"⚔️ {chosen_weapon}"[:45])
        self.msg_id        = msg_id
        self.target_id     = target_id
        self.target_name   = target_name
        self.chosen_role   = chosen_role
        self.chosen_weapon = chosen_weapon
        self.data          = data
        self.level_input   = discord.ui.TextInput(
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

        spec  = f"{self.chosen_weapon} ({level})"
        data  = self.data
        slots = data["slots"]

        action = "ajouté"
        for r, members in slots.items():
            for entry in list(members):
                if entry[0] == self.target_id:
                    members.remove(entry)
                    action = "déplacé"
                    break

        slots.setdefault(self.chosen_role, []).append((self.target_id, self.target_name, spec))
        await save_activities()

        try:
            channel = interaction.client.get_channel(data["channel_id"])
            msg     = await channel.fetch_message(self.msg_id)
            await msg.edit(embed=build_embed(data), view=build_view(self.msg_id))
        except Exception:
            pass

        label = f"{self.chosen_role[4:]} PF2" if self.chosen_role.startswith("PF2:") else self.chosen_role
        await interaction.response.send_message(
            f"✅ **{self.target_name}** {action} en **{label}**  —  {spec} !", ephemeral=True
        )


class AdminWeaponSelect(discord.ui.Select):
    def __init__(self, msg_id: int, target_id: int, target_name: str,
                 chosen_role: str, weapons_list: list[str], data: dict):
        self.msg_id      = msg_id
        self.target_id   = target_id
        self.target_name = target_name
        self.chosen_role = chosen_role
        self.data        = data
        from Service.activites import _parse_weapon_slots, _player_weapon
        current_members = data["slots"].get(chosen_role, [])
        options = []
        for w in weapons_list:
            parsed = _parse_weapon_slots(w)
            if not parsed:
                continue
            _display, clean, n_slots = parsed[0]
            taken = sum(1 for e in current_members if _player_weapon(e[2]) == clean)
            label = clean[:97] + (" ✅" if n_slots is None or taken < n_slots else " ⛔")
            options.append(discord.SelectOption(label=label[:100], value=clean[:100]))
        if not options:
            options = [discord.SelectOption(label="Aucune arme disponible", value="__full__")]
        super().__init__(placeholder="⚔️  Choisis l'arme du joueur...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "__full__":
            await interaction.response.send_message("⛔ Aucune arme disponible pour ce rôle.", ephemeral=True)
            return
        await interaction.response.send_modal(
            AdminSpecLevelModal(self.msg_id, self.target_id, self.target_name,
                                self.chosen_role, self.values[0], self.data)
        )


class AdminWeaponSelectView(discord.ui.View):
    def __init__(self, msg_id: int, target_id: int, target_name: str,
                 chosen_role: str, weapons_list: list[str], data: dict):
        super().__init__(timeout=120)
        self.add_item(AdminWeaponSelect(msg_id, target_id, target_name, chosen_role, weapons_list, data))


# ══════════════════════════════════════════════════════════════════════════════
# COG ADMIN
# ══════════════════════════════════════════════════════════════════════════════
class Admin(commands.Cog):
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

    async def check_caller_or_admin(self, interaction: discord.Interaction) -> bool:
        if not is_caller_or_admin(interaction.user):
            await interaction.response.send_message(
                "⛔ Tu dois avoir le rôle **Officier** ou **Caller** pour utiliser cette commande.",
                ephemeral=True,
            )
            return False
        return True

    # =========================================================================
    # /kickacti  — virer un joueur d'une activité
    # =========================================================================
    @app_commands.command(name="kickacti", description="Retirer un joueur d'une activité (organisateur ou Officier)")
    @app_commands.describe(joueur="Le joueur à retirer de l'activité")
    async def kickacti(self, interaction: discord.Interaction, joueur: discord.Member):
        if not is_caller_or_admin(interaction.user):
            await interaction.response.send_message(
                "⛔ Tu dois avoir le rôle **Officier** ou **Caller** pour utiliser cette commande.", ephemeral=True
            )
            return

        if not activities:
            await interaction.response.send_message("ℹ️ Aucune activité en cours.", ephemeral=True)
            return

        target_id   = joueur.id
        target_name = joueur.display_name

        async def on_select(inter: discord.Interaction, value: str):
            if value == "none":
                await inter.response.send_message("ℹ️ Aucune activité disponible.", ephemeral=True)
                return

            msg_id = int(value)
            data   = activities.get(msg_id)
            if not data:
                await inter.response.send_message("❌ Activité introuvable.", ephemeral=True)
                return

            is_creator = inter.user.display_name == data["creator"]
            if not (is_caller_or_admin(inter.user) or is_creator):
                await inter.response.send_message(
                    f"⛔ Seul l'organisateur (**{data['creator']}**), un **Officier** ou un **Caller** peut retirer un joueur.",
                    ephemeral=True,
                )
                return

            removed = False
            for members in data["slots"].values():
                for entry in list(members):
                    if entry[0] == target_id:
                        members.remove(entry)
                        removed = True
                        break
                if removed:
                    break

            if not removed:
                await inter.response.send_message(
                    f"ℹ️ **{target_name}** n'est pas inscrit dans cette activité.", ephemeral=True
                )
                return

            try:
                channel = inter.client.get_channel(data["channel_id"])
                msg     = await channel.fetch_message(msg_id)
                await msg.edit(embed=build_embed(data), view=build_view(msg_id))
            except Exception:
                pass

            await save_activities()
            await inter.response.send_message(
                f"✅ **{target_name}** a été retiré de l'activité.", ephemeral=True
            )

        view = discord.ui.View(timeout=60)
        view.add_item(ActivitySelect(on_select, "🗡️ De quelle activité le retirer ?"))
        await interaction.response.send_message(
            f"Choisis l'activité dont retirer **{target_name}** :", view=view, ephemeral=True
        )

    # =========================================================================
    # /addacti  — ajouter un joueur dans une activité (ou changer de rôle)
    # =========================================================================
    @app_commands.command(name="addacti", description="[ADMIN] Ajouter un joueur à une activité (ou changer son rôle)")
    @app_commands.describe(joueur="Le joueur à ajouter", role="Le rôle à lui attribuer")
    @app_commands.autocomplete(role=role_autocomplete)
    async def addacti(self, interaction: discord.Interaction, joueur: discord.Member, role: str):
        if not await self.check_caller_or_admin(interaction):
            return

        if not activities:
            await interaction.response.send_message("ℹ️ Aucune activité en cours.", ephemeral=True)
            return

        target_id   = joueur.id
        target_name = joueur.display_name
        chosen_role = role.upper()

        async def on_select(inter: discord.Interaction, value: str):
            if value == "none":
                await inter.response.send_message("ℹ️ Aucune activité disponible.", ephemeral=True)
                return

            msg_id   = int(value)
            data     = activities.get(msg_id)
            if not data:
                await inter.response.send_message("❌ Activité introuvable.", ephemeral=True)
                return

            slots    = data["slots"]
            max_p    = data["max_players"]
            template = data.get("template")

            if chosen_role not in slots:
                roles_dispo = ", ".join(f"`{r}`" for r in slots)
                await inter.response.send_message(
                    f"❌ Rôle **{chosen_role}** inconnu.\nRôles disponibles : {roles_dispo}", ephemeral=True
                )
                return

            total      = sum(len(v) for v in slots.values())
            already_in = any(e[0] == target_id for members in slots.values() for e in members)
            if total >= max_p and not already_in:
                await inter.response.send_message(f"⛔ L'activité est complète ({max_p} max).", ephemeral=True)
                return

            all_templates = load_all_templates()
            tdata    = all_templates.get(template, {}) if template else {}
            is_pf2   = chosen_role.startswith("PF2:")
            rn       = chosen_role[4:] if is_pf2 else chosen_role
            max_role = get_pf2(tdata).get(rn, 999) if is_pf2 else get_pf1(tdata).get(chosen_role, 999)
            in_role  = [e[0] for e in slots.get(chosen_role, [])]
            if len(in_role) >= max_role and target_id not in in_role:
                await inter.response.send_message(
                    f"⛔ Plus de place en **{chosen_role}** ({max_role} max).", ephemeral=True
                )
                return

            for entry in slots.get(chosen_role, []):
                if entry[0] == target_id:
                    await inter.response.send_message(
                        f"ℹ️ **{target_name}** est déjà en **{chosen_role}**.", ephemeral=True
                    )
                    return

            # PVP avec armes → dropdown arme → modal niveau
            type_acti = tdata.get("type_acti", "")
            if type_acti == "PVP":
                hint_spec = (
                    tdata.get("weapon_pf2", tdata.get("specs_pf2", {})).get(rn, "")
                    if is_pf2 else
                    tdata.get("weapon", tdata.get("specs", {})).get(chosen_role, "")
                )
                if hint_spec:
                    weapons_list = [w.strip() for w in hint_spec.split("·") if w.strip()]
                    if weapons_list:
                        label = f"{rn} (PF2)" if is_pf2 else chosen_role
                        await inter.response.send_message(
                            f"⚔️ **{label}** pour **{target_name}** — Quelle arme ?",
                            view=AdminWeaponSelectView(msg_id, target_id, target_name, chosen_role, weapons_list, data),
                            ephemeral=True,
                        )
                        return

            # PVE ou pas d'armes → inscription directe
            action = "ajouté"
            for r, members in slots.items():
                for entry in list(members):
                    if entry[0] == target_id:
                        members.remove(entry)
                        action = "déplacé"
                        break

            slots[chosen_role].append((target_id, target_name, ""))
            try:
                channel = inter.client.get_channel(data["channel_id"])
                msg     = await channel.fetch_message(msg_id)
                await msg.edit(embed=build_embed(data), view=build_view(msg_id))
            except Exception:
                pass
            await save_activities()
            await inter.response.send_message(
                f"✅ **{target_name}** {action} en **{chosen_role}** !", ephemeral=True
            )

        view = discord.ui.View(timeout=60)
        view.add_item(ActivitySelect(on_select, "🗡️ Dans quelle activité l'ajouter ?"))
        await interaction.response.send_message(
            f"Choisis l'activité où ajouter **{target_name}** en **{chosen_role}** :",
            view=view, ephemeral=True,
        )

    # =========================================================================
    # /addtemplate  — ajouter un template via JSON
    # =========================================================================
    @app_commands.command(name="addtemplate", description="[ADMIN] Ajouter un template de composition (format JSON)")
    @app_commands.describe(
        nom            = "Nom du template (ex: ZvZ Lilium)",
        description    = "Description courte du template",
        type_acti      = "Type d'activité",
        json_roles     = 'Rôles PF1 en JSON (ex: {"TANK": 2, "HEAL": 2, "DPS": 6})',
        json_roles_pf2 = 'Rôles PF2 en JSON optionnel (ex: {"TANK": 1, "HEAL": 4, "DPS": 8})',
        json_specs     = 'Spés PF1 par rôle, optionnel (ex: {"DPS": "Arc Long", "TANK": "1H Masse"})',
        json_specs_pf2 = 'Spés PF2 par rôle, optionnel (ex: {"DPS": "DPS clap range"})',
        image          = "URL de l'image à afficher dans l'embed (optionnel)",
    )
    @app_commands.choices(type_acti=[
        app_commands.Choice(name="PVP", value="PVP"),
        app_commands.Choice(name="PVE", value="PVE"),
    ])
    async def addtemplate(
        self,
        interaction:    discord.Interaction,
        nom:            str,
        type_acti:      app_commands.Choice[str],
        json_roles:     str,
        description:    str = "",
        image:          str = "",
        json_specs:     str = "",
        json_roles_pf2: str = "",
        json_specs_pf2: str = "",
    ):
        if not await self.check_admin(interaction):
            return

        try:
            roles_dict: dict = json.loads(json_roles)
        except json.JSONDecodeError as e:
            await interaction.response.send_message(
                f"❌ JSON invalide : `{e}`\n\nExemple :\n```json\n{{\"TANK\": 1, \"HEAL\": 1, \"DPS\": 3}}\n```",
                ephemeral=True,
            )
            return

        if not isinstance(roles_dict, dict) or not all(isinstance(v, int) and v > 0 for v in roles_dict.values()):
            await interaction.response.send_message(
                "❌ Le JSON doit être un objet `{rôle: nombre}` avec des entiers > 0.", ephemeral=True
            )
            return

        specs: dict[str, str] = {}
        if json_specs.strip():
            try:
                specs_raw = json.loads(json_specs)
                if not isinstance(specs_raw, dict):
                    raise ValueError("not a dict")
                specs = {k.upper(): str(v) for k, v in specs_raw.items()}
            except (json.JSONDecodeError, ValueError) as e:
                await interaction.response.send_message(
                    f"❌ json_specs invalide : `{e}`\n\nExemple :\n```json\n{{\"DPS\": \"Arc Long\", \"TANK\": \"1H Masse\"}}\n```",
                    ephemeral=True,
                )
                return

        if nom in DEFAULT_TEMPLATES:
            await interaction.response.send_message(
                f"❌ **{nom}** est un template par défaut, il ne peut pas être écrasé.", ephemeral=True
            )
            return

        pf2: dict[str, int] = {}
        if json_roles_pf2.strip():
            try:
                pf2_raw = json.loads(json_roles_pf2)
                if not isinstance(pf2_raw, dict) or not all(isinstance(v, int) and v > 0 for v in pf2_raw.values()):
                    raise ValueError("invalid format")
                pf2 = {k.upper(): v for k, v in pf2_raw.items()}
            except (json.JSONDecodeError, ValueError) as e:
                await interaction.response.send_message(
                    f"❌ json_roles_pf2 invalide : `{e}`", ephemeral=True
                )
                return

        specs_pf2: dict[str, str] = {}
        if json_specs_pf2.strip():
            try:
                sp2_raw = json.loads(json_specs_pf2)
                if not isinstance(sp2_raw, dict):
                    raise ValueError("not a dict")
                specs_pf2 = {k.upper(): str(v) for k, v in sp2_raw.items()}
            except (json.JSONDecodeError, ValueError) as e:
                await interaction.response.send_message(
                    f"❌ json_specs_pf2 invalide : `{e}`", ephemeral=True
                )
                return

        pf1   = {k.upper(): v for k, v in roles_dict.items()}
        # Vérifier si déjà existant pour le message d'action
        existing = await db.get_custom_templates()
        action   = "mis à jour" if nom in existing else "ajouté"
        entry = {
            "description": description,
            "type_acti":   type_acti.value,
            "image":       image,
            "pf_1":        pf1,
            "weapon":      specs,
        }
        if pf2:
            entry["pf_2"]        = pf2
            entry["weapon_pf2"]  = specs_pf2

        await db.save_custom_template(nom, entry)
        await refresh_templates_cache()

        tag      = "🔴 PVP" if type_acti.value == "PVP" else "🟢 PVE"
        preview  = "\n".join(
            f"  {ROLES.get(r, '🔹')} **{r}** × {n}{f'  ·  {specs[r]}' if r in specs else ''}"
            for r, n in pf1.items()
        )
        total = sum(pf1.values())
        if pf2:
            preview += "\n  ── PF2 ──\n" + "\n".join(
                f"  {ROLES.get(r, '🔹')} **{r}** × {n}{f'  ·  {specs_pf2[r]}' if r in specs_pf2 else ''}"
                for r, n in pf2.items()
            )
            total += sum(pf2.values())
        await interaction.response.send_message(
            f"✅ Template **{nom}** {action} — {tag} — {total} joueurs\n{preview}",
            ephemeral=True,
        )

    # =========================================================================
    # /deltemplate  — supprimer un template custom
    # =========================================================================
    @app_commands.command(name="deltemplate", description="[ADMIN] Supprimer un template custom")
    @app_commands.describe(nom="Nom du template à supprimer")
    async def deltemplate(self, interaction: discord.Interaction, nom: str):
        if not await self.check_admin(interaction):
            return

        if nom in DEFAULT_TEMPLATES:
            await interaction.response.send_message(
                f"❌ **{nom}** est un template par défaut, il ne peut pas être supprimé ici.", ephemeral=True
            )
            return

        custom = await db.get_custom_templates()
        if nom not in custom:
            await interaction.response.send_message(f"❌ Template **{nom}** introuvable.", ephemeral=True)
            return

        await db.delete_custom_template(nom)
        await refresh_templates_cache()
        await interaction.response.send_message(f"🗑️ Template **{nom}** supprimé.", ephemeral=True)

    # =========================================================================
    # /setimage  — modifier l'image d'un template
    # =========================================================================
    @app_commands.command(name="setimage", description="[OFFICIER] Modifier l'image d'un template")
    @app_commands.describe(nom="Nom du template", url="URL de la nouvelle image (laisser vide pour retirer)")
    async def setimage(self, interaction: discord.Interaction, nom: str, url: str = ""):
        if not await self.check_admin(interaction):
            return

        all_templates = load_all_templates()
        if nom not in all_templates:
            templates_list = ", ".join(f"`{k}`" for k in all_templates)
            await interaction.response.send_message(
                f"❌ Template **{nom}** introuvable.\nTemplates disponibles : {templates_list}", ephemeral=True
            )
            return

        await db.set_image_override(nom, url)
        await refresh_image_overrides()

        if url:
            await interaction.response.send_message(
                f"✅ Image du template **{nom}** mise à jour.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"✅ Image du template **{nom}** retirée (image par défaut restaurée).", ephemeral=True
            )

    # =========================================================================
    # /setrate  — modifier le taux de rachat guilde
    # =========================================================================
    @app_commands.command(name="setrate", description="[GM] Modifier le taux de rachat guilde pour la fin d'activité")
    @app_commands.describe(taux="Pourcentage de rachat (1-100)")
    async def setrate(self, interaction: discord.Interaction, taux: app_commands.Range[int, 1, 100]):
        is_gm = (
            interaction.user.guild_permissions.administrator
            or any(r.name == GM_ROLE_NAME for r in interaction.user.roles)
        )
        if not is_gm:
            await interaction.response.send_message(
                f"⛔ Seul un **{GM_ROLE_NAME}** peut modifier le taux de rachat.", ephemeral=True
            )
            return

        settings = await load_settings()
        old_rate = settings.get("bal_rate", DEFAULT_BAL_RATE)
        await save_settings({"bal_rate": taux})

        await interaction.response.send_message(
            f"✅ Taux de rachat mis à jour : **{old_rate} %** → **{taux} %**",
            ephemeral=True,
        )

    # ── /balpartis ───────────────────────────────────────────────────────────
    @app_commands.command(name="balpartis", description="[OFFICIER] Lister les joueurs partis du Discord qui ont encore de la BAL")
    @app_commands.describe(vider="Vider la BAL des joueurs partis (défaut : false)")
    async def balpartis(self, interaction: discord.Interaction, vider: bool = False):
        if not is_admin(interaction.user):
            await interaction.response.send_message(
                "⛔ Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        all_bal = await db.get_all_bal()
        if not all_bal:
            await interaction.followup.send("ℹ️ Aucune BAL enregistrée.", ephemeral=True)
            return

        fmt    = lambda n: f"{n:,}".replace(",", " ")
        partis = []
        for user_id_str, amount in all_bal.items():
            if amount <= 0:
                continue
            member = interaction.guild.get_member(int(user_id_str))
            if member is None:
                try:
                    user = await interaction.client.fetch_user(int(user_id_str))
                    name = f"{user.name} (ID: {user_id_str})"
                except Exception:
                    name = f"Inconnu (ID: {user_id_str})"
                partis.append((user_id_str, name, amount))

        if not partis:
            await interaction.followup.send("✅ Aucun joueur parti n'a de BAL en attente.", ephemeral=True)
            return

        partis.sort(key=lambda x: x[2], reverse=True)
        total = sum(a for _, _, a in partis)

        if vider:
            from Service.utils import append_bal_log
            log_entries = []
            for user_id_str, name, amount in partis:
                await db.set_bal(user_id_str, 0)
                log_entries.append({"uid": user_id_str, "name": name, "delta": -amount, "total": 0})
            await append_bal_log("retirebal", interaction.user.display_name, log_entries)

            lines = "\n".join(f"**{name}** — ~~{fmt(amount)} silver~~ → 0" for _, name, amount in partis)
            embed = discord.Embed(
                title="🗑️ BAL des joueurs partis vidées",
                description=lines,
                color=0xE74C3C,
            )
            embed.set_footer(text=f"{len(partis)} joueur(s) · {fmt(total)} silver supprimés")
        else:
            lines = "\n".join(f"**{name}** — {fmt(amount)} silver" for _, name, amount in partis)
            embed = discord.Embed(
                title="🚪 Joueurs partis avec de la BAL",
                description=lines,
                color=0xE74C3C,
            )
            embed.set_footer(text=f"{len(partis)} joueur(s) · Total : {fmt(total)} silver")

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /totalbal ────────────────────────────────────────────────────────────
    @app_commands.command(name="totalbal", description="Afficher le total des BAL dues par la guilde")
    async def totalbal(self, interaction: discord.Interaction):
        is_gm_or_admin = (
            interaction.user.guild_permissions.administrator
            or any(r.name in (ADMIN_ROLE_NAME, GM_ROLE_NAME) for r in interaction.user.roles)
        )
        if not is_gm_or_admin:
            await interaction.response.send_message(
                "⛔ Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
            )
            return

        all_bal = await db.get_all_bal()
        if not all_bal:
            await interaction.response.send_message("ℹ️ Aucune BAL enregistrée.", ephemeral=True)
            return

        total = sum(all_bal.values())
        fmt   = lambda n: f"{n:,}".replace(",", " ")

        lines = sorted(all_bal.items(), key=lambda x: x[1], reverse=True)
        desc  = "\n".join(f"<@{uid}> — **{fmt(amount)}** silver" for uid, amount in lines if amount > 0)

        embed = discord.Embed(
            title="💰 Total BAL — Ce que la guilde doit",
            description=desc or "Aucun solde positif.",
            color=0xF1C40F,
        )
        embed.set_footer(text=f"Total : {fmt(total)} silver")
        await interaction.response.send_message(embed=embed)


# ── SETUP ─────────────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
