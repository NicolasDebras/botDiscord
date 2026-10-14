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


def parse_guild_ids(raw: str) -> frozenset[int]:
    """« 123, 456 » → {123, 456} ; vide → ensemble vide (= pas de restriction)."""
    return frozenset(int(x) for x in raw.replace(";", ",").split(",") if x.strip())


# ── SERVEURS AUTORISÉS (optionnel) ─────────────────────────────────────────────
# Si renseigné, le bot quitte tout autre serveur (au démarrage et à l'invitation) :
# sans ça, le propriétaire de n'importe quel serveur où le bot est ajouté peut
# se nommer admin du site pour son serveur.
ALLOWED_GUILD_IDS = parse_guild_ids(os.environ.get("ALLOWED_GUILD_IDS", ""))

# ── RÔLES et TEMPLATES PAR DÉFAUT : roles_templates.py (partagé avec le site) ──
from roles_templates import DEFAULT_TEMPLATES, ROLES  # noqa: E402,F401

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
