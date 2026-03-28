import os
from dotenv import load_dotenv

load_dotenv(override=True)

# ── CONFIG ──────────────────────────────────────────────────────────────────
TOKEN = os.environ["DISCORD_TOKEN"]

# ── ADMIN ─────────────────────────────────────────────────────────────────────
# Nom exact du rôle Discord autorisé à utiliser les commandes admin
ADMIN_ROLE_NAME = "Officer"
# Nom exact du rôle Guild Master (accès aux commandes sensibles)
GM_ROLE_NAME    = "GM"

# ── GUILD ID (sync instantanée des slash commands) ────────────────────────────
GUILD_ID = int(os.environ["DISCORD_GUILD_ID"])
 
# ── FICHIER DE TEMPLATES PERSISTANT ──────────────────────────────────────────
TEMPLATES_FILE = "templates.json"
 
# ── RÔLES avec emojis ────────────────────────────────────────────────────────
ROLES: dict[str, str] = {
    "TANK":      "🛡️",
    "OFF TANK":  "🛡️",
    "HEAL":      "💚",
    "MAIN HEAL": "💚",
    "IRON ROOT": "🌿",
    "DPS":       "⚔️",
    "DAMME":     "💥",
    "SUPPORT":   "🔮",
    "CALLER":    "📢",
    "SCOOT":     "🏃",
    "FROST":     "❄️",
}
 
# ── TYPES D'ACTIVITÉS ────────────────────────────────────────────────────────
ACTIVITY_TYPES: list[str] = [
    "ZvZ",
    "HCE",
    "Avalon Road",
    "Corrupted Dungeon",
    "Ganking",
    "Rat",
    "Gathering",
    "Mists",
]
 
# ── TEMPLATES PAR DÉFAUT ──────────────────────────────────────────────────────
# Structure : { nom: { "description": str, "type_acti": "PVP"|"PVE", "image": url|"", "pf_1": {rôle: slots} } }
# Les templates custom ajoutés via /addtemplate sont dans templates.json
DEFAULT_TEMPLATES: dict[str, dict] = {
    "ZvZ Standard": {
        "description": "Composition standard pour les ZvZ",
        "type_acti":   "PVP",
        "image":       "",
        "pf_1": {"TANK": 5, "HEAL": 5, "DPS": 10, "SUPPORT": 5, "CALLER": 1},
    },
    "Small Scale": {
        "description": "Petit groupe PvP polyvalent",
        "type_acti":   "PVP",
        "image":       "",
        "pf_1": {"TANK": 2, "HEAL": 2, "DPS": 6},
    },
    "HCE 5-man": {
        "description": "Haute Cour des Enfers en groupe de 5",
        "type_acti":   "PVE",
        "image":       "",
        "pf_1": {"TANK": 1, "HEAL": 1, "DPS": 3},
    },
    "Ganking Party": {
        "description": "Groupe de ganking mobile",
        "type_acti":   "PVP",
        "image":       "",
        "pf_1": {"TANK": 1, "DPS": 4},
    },
    "RAID AVA": {
        "description": "Compo beban Raid AVA",
        "type_acti":   "PVE",
        "image":       "https://media.discordapp.net/attachments/1486773126888165437/1486773128792375437/thaisalbion3.png?ex=69c80a60&is=69c6b8e0&hm=a2846dc24737560c373df6276ab8e847e82544e87add31b550e31e223cc7cd2f&=&format=webp&quality=lossless",
        "pf_1": {
            "TANK": 1, "OFF TANK": 1, "FROST": 1,
            "DAMME": 1, "SCOOT": 1, "MAIN HEAL": 1, "IRON ROOT": 1,  "DPS": 3,
        },
    },
}
 
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

# ── FICHIER SETTINGS (taux de rachat, etc.) ───────────────────────────────────
SETTINGS_FILE   = "settings.json"
DEFAULT_BAL_RATE = 90   # % de rachat guilde par défaut

# ── FICHIER LOG BAL ───────────────────────────────────────────────────────────
BAL_LOG_FILE    = "bal_log.json"
BAL_LOG_MAX     = 100   # nombre max d'entrées conservées