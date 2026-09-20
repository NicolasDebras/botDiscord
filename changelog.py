"""
Changelog du bot — annoncé automatiquement dans le salon configuré via
/config → 📢 Annonces mises à jour, dès qu'une nouvelle version est détectée
au démarrage du bot.

Pour annoncer une nouvelle fonctionnalité : incrémenter VERSION et ajouter
une entrée en tête de CHANGELOG (ordre du plus récent au plus ancien).
"""

VERSION = "2026.09.20"

CHANGELOG: list[dict] = [
    {
        "version": "2026.09.20",
        "title": "🔊 Fix suppression des salons vocaux temporaires",
        "items": [
            "Les salons vocaux temporaires qui restaient parfois orphelins (déconnexion sale, "
            "redémarrage du bot pile au mauvais moment) sont maintenant rattrapés par un balayage "
            "automatique toutes les 2 minutes en plus de la suppression instantanée.",
        ],
    },
    {
        "version": "2026.09.10.1",
        "title": "🔀 Fix du bouton Fill",
        "items": [
            "Le bouton **Fill** sur les activités inscrit maintenant dans un rôle **Fill** dédié, "
            "affiché comme les autres rôles dans l'embed — avant, il inscrivait silencieusement "
            "dans un vrai rôle du template (DPS, TANK…) sans que ça apparaisse.",
        ],
    },
    {
        "version": "2026.09.10",
        "title": "📢 Annonces de mises à jour",
        "items": [
            "Nouvelle section `/config` → 📢 Annonces mises à jour : choisis un salon qui recevra "
            "automatiquement un message à chaque nouvelle fonctionnalité du bot.",
        ],
    },
]


def get_entries_since(last_version: str | None) -> list[dict]:
    """Entrées à annoncer, de la plus ancienne à la plus récente.

    Si last_version est None (premier réglage du salon), ne renvoie que la
    plus récente (message de bienvenue), pas tout l'historique.
    """
    if last_version is None:
        return CHANGELOG[:1]

    result = []
    for entry in CHANGELOG:
        if entry["version"] == last_version:
            break
        result.append(entry)
    return list(reversed(result))
