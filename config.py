import os
from dotenv import load_dotenv

load_dotenv(override=True)

# ── CONFIG ──────────────────────────────────────────────────────────────────
TOKEN = os.environ["DISCORD_TOKEN"]

# ── ADMIN ─────────────────────────────────────────────────────────────────────
# Nom exact du rôle Discord autorisé à utiliser les commandes admin
ADMIN_ROLE_NAME  = "Officier"
# Nom exact du rôle Guild Master (accès aux commandes sensibles)
GM_ROLE_NAME     = "Maitre de guilde"
# Rôle minimum requis pour utiliser les commandes membres
MEMBRE_ROLE_NAME = "Membre"
# Rôle Caller (accès à kickacti / addacti)
CALLER_ROLE_NAME   = "Caller"
# Rôle Recruteur (accès à /recrutement)
RECRUTEUR_ROLE_ID  = 1473779038106685568

# ── GUILD ID (serveur principal — historique/legacy, migrations DB) ───────────
GUILD_ID              = int(os.environ["DISCORD_GUILD_ID"])

# ── RÔLES avec emojis ────────────────────────────────────────────────────────
ROLES: dict[str, str] = {
    "TANK":        "🛡️",
    "MAIN TANK":   "🛡️",
    "TANK OFF":    "🛡️",
    "TANK DEF":    "🛡️",
    "OFF TANK":    "🛡️",
    "HEAL":        "💚",
    "MAIN HEAL":   "💚",
    "IRON ROOT":   "🌿",
    "IRON":        "🌿",
    "DPS":         "⚔️",
    "FAUX":        "🌾",
    "DAMME":       "💥",
    "SUPPORT":     "🔮",
    "CALLER":      "📢",
    "SCOUT":       "👁️",
    "FROST":       "❄️",
    "HURLEGIVRE":  "🌨️",
    "SC":          "💣",
    "COBRA/GA":    "🏹",
    "COBRA":       "🐍",
    "BM":          "🐴",
    "LEACHER PVP": "⚡",
    "HO":          "🏠",
}
 
# ── TEMPLATES PAR DÉFAUT ──────────────────────────────────────────────────────
# Structure : { nom: { "description": str, "type_acti": "PVP"|"PVE", "image": url|"", "pf_1": {rôle: slots} } }
# "guild_ids": [id, ...] (optionnel) restreint le template à certains serveurs.
# Absent ou vide = visible sur tous les serveurs où le bot est installé.
# Les templates custom ajoutés via /addtemplate sont stockés en DB, scopés par serveur.
DEFAULT_TEMPLATES: dict[str, dict] = {}

# ── Templates désactivés (gardés en référence, non actifs) ────────────────────
# Pour réactiver : dé-commenter et remettre dans DEFAULT_TEMPLATES ci-dessus.
#
# "RAID AVA BN": {
#     "description": (
#         "[Doc des stuffs T9](https://docs.google.com/spreadsheets/d/1AshcOMisNmr3BqGWG9ayBpTxlyoaSYWbLBEvHAYBLLM/edit?usp=sharing&utm_source=chatgpt.com)\n"
#         "Tous les stuffs équi T9 sont présents dans le doc "
#         "(c'est pas très beau pour le moment, je sais).\n\n"
#         "Merci de mettre votre IP dans le post (IP Diff priorité). "
#         "Le scout prend une part ×1.5 "
#         "( pas de scout tel, pas de scout grille pain, UN VRAI SCOUT SVP )"
#     ),
#     "type_acti":      "PVE",
#     "image":          "",
#     "no_register":    True,
#     "zero_pay_roles": ["LEACHER PVP"],
#     "tax_rate":       90,
#     "role_multipliers": {"SCOUT": 1.5},
#     "pf_1": {
#         "MAIN TANK":   1,
#         "MAIN HEAL":   1,
#         "OFF TANK":    1,
#         "COBRA":       1,
#         "IRON":        1,
#         "SC":          1,
#         "HURLEGIVRE":  1,
#         "FAUX":        3,
#         "SCOUT":       1,
#         "LEACHER PVP": 1,
#         "HO":          1
#     },
# },

# ── COULEURS par type d'activité ─────────────────────────────────────────────
ACTIVITY_COLORS: dict[str, int] = {
    "ZvZ":               0xE74C3C,
    "HCE":               0x9B59B6,
    "Avalon Road":       0x1ABC9C,
    "Corrupted Dungeon": 0xE67E22,
    "Ganking":           0xE91E63,
    "Rat":               0x95A5A6,
    "Gathering":         0x2ECC71,
    "Mists":             0x3498DB,
}
DEFAULT_COLOR = 0xF1C40F

DEFAULT_BAL_RATE = 90   # % de rachat guilde par défaut