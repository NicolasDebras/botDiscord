"""
roles_templates.py — Rôles et templates de compo par défaut, PARTAGÉS avec le site.

⚠️ Copié tel quel dans lilium-site (api/app/shared/roles_templates.py) : pur Python,
sans variable d'environnement ni import du bot. Après une modification, lancer
`python -m scripts.sync_from_bot` dans lilium-site/api (sa CI vérifie la copie).
"""

# ── RÔLES avec emojis ────────────────────────────────────────────────────────
ROLES: dict[str, str] = {
    "TANK":    "🛡️",
    "HEAL":    "💚",
    "DPS":     "⚔️",
    "SUPPORT": "🔮",
}

# ── TEMPLATES PAR DÉFAUT ──────────────────────────────────────────────────────
# Structure : { nom: { "description": str, "type_acti": "PVP"|"PVE", "image": url|"", "pf_1": {rôle: slots} } }
# "guild_ids": [id, ...] (optionnel) restreint le template à certains serveurs.
# Absent ou vide = visible sur tous les serveurs où le bot est installé.
# Les templates custom ajoutés via /addtemplate sont stockés en DB, scopés par serveur.
DEFAULT_TEMPLATES: dict[str, dict] = {
    "Donjon Groupe 5": {
        "description": "Donjon de groupe — 5 joueurs",
        "type_acti":   "PVE",
        "image":       "",
        "pf_1": {"TANK": 1, "DPS": 3, "HEAL": 1},
    },
}

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
