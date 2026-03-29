import discord
import json
import os
from discord.ext import commands
from discord import app_commands

from config import ADMIN_ROLE_NAME, GM_ROLE_NAME, TEMPLATES_FILE, ROLES, DEFAULT_BAL_RATE, DEFAULT_TEMPLATES
from Service.activites import activities, build_embed, build_view, get_pf1, load_all_templates, save_activities
from Service.utils import is_admin, ActivitySelect, load_settings, save_settings


# ── HELPER : chargement/sauvegarde des templates JSON ────────────────────────
def load_custom_templates() -> dict[str, dict[str, int]]:
    if not os.path.exists(TEMPLATES_FILE):
        return {}
    with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_custom_templates(templates: dict[str, dict[str, int]]) -> None:
    with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(templates, f, ensure_ascii=False, indent=2)


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

    # =========================================================================
    # /kickacti  — virer un joueur d'une activité
    # =========================================================================
    @app_commands.command(name="kickacti", description="[ADMIN] Retirer un joueur d'une activité en cours")
    @app_commands.describe(joueur="Le joueur à retirer de l'activité")
    async def kickacti(self, interaction: discord.Interaction, joueur: discord.Member):
        if not await self.check_admin(interaction):
            return

        if not activities:
            await interaction.response.send_message("ℹ️ Aucune activité en cours.", ephemeral=True)
            return

        # On stocke le joueur ciblé pour le callback du select
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

            # Mettre à jour le message de l'activité
            try:
                channel = inter.client.get_channel(data["channel_id"])
                msg     = await channel.fetch_message(msg_id)
                await msg.edit(embed=build_embed(data), view=build_view(msg_id))
            except Exception:
                pass

            save_activities()
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
        if not await self.check_admin(interaction):
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

            # Vérif que le rôle existe dans cette activité
            if chosen_role not in slots:
                roles_dispo = ", ".join(f"`{r}`" for r in slots)
                await inter.response.send_message(
                    f"❌ Rôle **{chosen_role}** inconnu pour cette activité.\nRôles disponibles : {roles_dispo}",
                    ephemeral=True,
                )
                return

            # Vérif slot global (sauf si déjà inscrit = changement de rôle)
            total      = sum(len(v) for v in slots.values())
            already_in = any(e[0] == target_id for members in slots.values() for e in members)
            if total >= max_p and not already_in:
                await inter.response.send_message(f"⛔ L'activité est complète ({max_p} max).", ephemeral=True)
                return

            # Vérif slot du rôle
            all_templates = load_all_templates()
            if template in all_templates:
                max_role = get_pf1(all_templates[template]).get(chosen_role, 999)
                in_role  = [e[0] for e in slots.get(chosen_role, [])]
                if len(in_role) >= max_role and target_id not in in_role:
                    await inter.response.send_message(
                        f"⛔ Plus de place en **{chosen_role}** ({max_role} max).", ephemeral=True
                    )
                    return

            # Retirer de l'ancien rôle si présent
            action = "ajouté"
            for r, members in slots.items():
                for entry in list(members):
                    if entry[0] == target_id:
                        if r == chosen_role:
                            await inter.response.send_message(
                                f"ℹ️ **{target_name}** est déjà en **{chosen_role}**.", ephemeral=True
                            )
                            return
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

            save_activities()
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
        nom         = "Nom du template (ex: ZvZ Lilium)",
        description = "Description courte du template",
        type_acti   = "Type d'activité",
        json_roles  = 'Rôles en JSON (ex: {"TANK": 2, "HEAL": 2, "DPS": 6})',
        json_specs  = 'Spés requises par rôle, optionnel (ex: {"DPS": "Arc Long", "TANK": "1H Masse"})',
        image       = "URL de l'image à afficher dans l'embed (optionnel)",
    )
    @app_commands.choices(type_acti=[
        app_commands.Choice(name="PVP", value="PVP"),
        app_commands.Choice(name="PVE", value="PVE"),
    ])
    async def addtemplate(
        self,
        interaction: discord.Interaction,
        nom:         str,
        type_acti:   app_commands.Choice[str],
        json_roles:  str,
        description: str = "",
        image:       str = "",
        json_specs:  str = "",
    ):
        if not await self.check_admin(interaction):
            return

        # Parser les rôles
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

        # Parser les specs (optionnel)
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

        pf1    = {k.upper(): v for k, v in roles_dict.items()}
        custom = load_custom_templates()
        action = "mis à jour" if nom in custom else "ajouté"
        custom[nom] = {
            "description": description,
            "type_acti":   type_acti.value,
            "image":       image,
            "pf_1":        pf1,
            "specs":       specs,
        }
        save_custom_templates(custom)

        tag     = "🔴 PVP" if type_acti.value == "PVP" else "🟢 PVE"
        preview = "\n".join(
            f"  {ROLES.get(r, '🔹')} **{r}** × {n}{f'  ·  {specs[r]}' if r in specs else ''}"
            for r, n in pf1.items()
        )
        total   = sum(pf1.values())
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

        custom = load_custom_templates()
        if nom not in custom:
            await interaction.response.send_message(f"❌ Template **{nom}** introuvable.", ephemeral=True)
            return

        del custom[nom]
        save_custom_templates(custom)
        await interaction.response.send_message(f"🗑️ Template **{nom}** supprimé.", ephemeral=True)


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

        settings = load_settings()
        old_rate = settings.get("bal_rate", DEFAULT_BAL_RATE)
        settings["bal_rate"] = taux
        save_settings(settings)

        await interaction.response.send_message(
            f"✅ Taux de rachat mis à jour : **{old_rate} %** → **{taux} %**",
            ephemeral=True,
        )


# ── SETUP ─────────────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))