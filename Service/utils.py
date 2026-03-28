import json
import os
import discord

from datetime import datetime, timezone

from config import ADMIN_ROLE_NAME, GM_ROLE_NAME, MEMBRE_ROLE_NAME, SETTINGS_FILE, DEFAULT_BAL_RATE, BAL_LOG_FILE, BAL_LOG_MAX


# ── HELPER : vérification du rôle admin ──────────────────────────────────────
def is_admin(member: discord.Member) -> bool:
    return (
        member.guild_permissions.administrator
        or any(r.name == ADMIN_ROLE_NAME for r in member.roles)
    )


# ── HELPER : vérification du rôle membre ─────────────────────────────────────
def is_membre(member: discord.Member) -> bool:
    return (
        member.guild_permissions.administrator
        or any(r.name in (ADMIN_ROLE_NAME, GM_ROLE_NAME, MEMBRE_ROLE_NAME) for r in member.roles)
    )


# ── HELPERS : settings persistants (taux de rachat, etc.) ────────────────────
def load_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return {"bal_rate": DEFAULT_BAL_RATE}
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_settings(data: dict) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── HELPERS : log BAL ─────────────────────────────────────────────────────────
def load_bal_log() -> list[dict]:
    if not os.path.exists(BAL_LOG_FILE):
        return []
    with open(BAL_LOG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def append_bal_log(action: str, by: str, entries: list[dict]) -> None:
    """Ajoute une entrée au log BAL (max BAL_LOG_MAX entrées conservées).

    entries : liste de {"uid": str, "name": str, "delta": int, "total": int}
    """
    log = load_bal_log()
    log.append({
        "ts":      datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "action":  action,
        "by":      by,
        "entries": entries,
    })
    if len(log) > BAL_LOG_MAX:
        log = log[-BAL_LOG_MAX:]
    with open(BAL_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


# ── SELECT : choix d'une activité en cours ───────────────────────────────────
class ActivitySelect(discord.ui.Select):
    """Liste déroulante qui affiche les activités en cours.

    Utilise un import tardif de `activities` pour éviter l'import circulaire
    avec Service.activites.
    """

    def __init__(self, callback_fn, placeholder: str = "🗡️ Choisis une activité..."):
        from Service.activites import activities   # import tardif

        self._callback_fn = callback_fn
        options = []
        for msg_id, data in activities.items():
            label = data["template"] or "Sans template"
            desc  = f"Par {data['creator']} • {sum(len(v) for v in data['slots'].values())}/{data['max_players']} joueurs"
            options.append(discord.SelectOption(label=label[:100], description=desc[:100], value=str(msg_id)))

        if not options:
            options = [discord.SelectOption(label="Aucune activité en cours", value="none")]

        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            await self._callback_fn(interaction, self.values[0])
        except Exception as e:
            msg = f"❌ Erreur inattendue : {e}"
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
