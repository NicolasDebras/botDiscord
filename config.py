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
CALLER_ROLE_NAME = "Caller"

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
    "COBRA/GA":  "🏹",
    "BM":        "🐴",
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
    "RAID AVA": {
        "description": "Compo beban Raid AVA",
        "type_acti":   "PVE",
        "image":       "https://media.discordapp.net/attachments/1486773126888165437/1486773128792375437/thaisalbion3.png?ex=69c80a60&is=69c6b8e0&hm=a2846dc24737560c373df6276ab8e847e82544e87add31b550e31e223cc7cd2f&=&format=webp&quality=lossless",
        "has_waitlist": True,
        "pf_1": {
            "TANK": 1, "OFF TANK": 1, "FROST": 1,
            "DAMME": 1, "SCOOT": 1, "MAIN HEAL": 1, "IRON ROOT": 1,
            "DPS": 3, "COBRA/GA": 1,
        },
    },
    "STATIK": {
        "description": "Donjon statique PVE — 10 joueurs",
        "type_acti":   "PVE",
        "image":       "",
        "pf_1": {"TANK": 2, "HEAL": 2, "SUPPORT": 1, "DPS": 5},
    },
    "MiddleScale de G3 LE GOAT": {
        "description": "Compo ZvZ G3 — 40 joueurs (PF1 + PF2) · T8 mini",
        "type_acti":   "PVP",
        "image":       "https://cdn.discordapp.com/attachments/94518390546255872/1284345624732635230/fatwizardBlick.gif?ex=69c9e512&is=69c89392&hm=4053fd8f86c884ba21d4193d893b325268ce1c54bba2c643419971a59d494875&",
        "pf_1": {"CALLER": 1, "TANK": 4, "SUPPORT": 4, "HEAL": 4, "DPS": 7, "BM": 1},
        "pf_2": {"TANK": 4, "SUPPORT": 4, "HEAL": 4, "DPS": 7},
        "weapon": {
            "CALLER":  "Selon strat",
            "TANK":    "1H Masse controle (×2)  ·  Bec de corbin (×1)  ·  Serpent (off) (×1)",
            "SUPPORT": "Locus (×1)  ·  Incube (×1)  ·  Mande ténèbres (×1)  ·  Malédiction de vie (×1)",
            "HEAL":    "Sancti cuir (×2)  ·  Sancti Plaque (×1)  ·  1H nature (×1)",
            "DPS":     "Pointes (×1)  ·  Tranchante (×1)  ·  BR (×2)  ·  Brassards (×infini)  ·  Mains Infernales (×infini)",
            "BM":      "Tour mobile (×1)  ·  Venom (×1)",
        },
        "weapon_pf2": {
            "TANK":    "Second Repack (×1)  ·  1h arcane / heavy (×1)  ·  Bec de Corbin (×1)  ·  GA (×1)",
            "SUPPORT": "Locus (×1)  ·  Garde-Serment / Enraciné (×1)  ·  Damnation (×1)  ·  Putréfaction (×1)",
            "HEAL":    "Exalté (×1)  ·  Sancti cuir (×2)  ·  Effrené (×1)",
            "DPS":     "Ursines (×1)  ·  Spirit (×1)  ·  Perma (×1)  ·  BR (×1)  ·  Mains infernales (×infini)  ·  Arc long / aria (×1)",
        },
    },
    "MONKEY BANANA": {
        "description": "Compo monkey banana Spé 80 dps minimum, sinon go heal/tank/support. Pas de tiers minimum. 1 tank et heal pour 5 minimum.",
        "type_acti":   "PVP",
        "image":       "https://media.discordapp.net/attachments/749187175823704165/1492503179718299798/my-image.png?ex=69dc3a27&is=69dae8a7&hm=68e6f0ac0003dca8fb9f5a3e9e567c5a2c0f09e9417f62ba61e54f7bbc4738d8&=&format=webp&quality=lossless",
        "pf_1": {"TANK": 4, "SUPPORT": 3, "HEAL": 4, "DPS": 30},
        "weapon": {
            "TANK":    "Monarque (×1)  ·  Heavy mace (×1)  ·  Gardes serments (×1)  ·  Tank fill (×2)",
            "SUPPORT": "Mande Charogne (×1)  ·  Support fill (×2)",
            "HEAL":    "Sancti plaque/cuir (×3)  ·  Druide 1h/Effréné plaque (×1)",
            "DPS":     "Marteau forgés (×infini)  ·  Vesperien (×infini)  ·  Eagle (×infini)  ·  Dps fill de l'image (×infini)  ·  Saigneur (×1)  ·  Astral (×1)  ·  Ursines (×1)",
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