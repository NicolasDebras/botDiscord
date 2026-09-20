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
        "version": "2026.09.15.1",
        "title": "🔧 Fix salon vocal temporaire dupliqué",
        "items": [
            "Correction d'un bug où rejoindre le hub deux fois de suite créait deux salons vocaux "
            "pour le même joueur. Désormais, si un salon existe déjà, le joueur y est redirigé directement.",
        ],
    },
    {
        "version": "2026.09.15",
        "title": "📦 Système de location d'armes",
        "items": [
            "Nouvelle commande `/location @joueur arme [caution]` — crée une location à 100 000 silver/jour.",
            "Nouvelle commande `/recaplocation` — liste toutes les locations actives avec le montant dû et la caution.",
            "Nouvelle commande `/closelocation id` — clôture une location et affiche le montant final.",
            "Le compteur de jours s'incrémente chaque soir à **22h** — le jour de création ne compte pas.",
        ],
    },
    {
        "version": "2026.09.14.2",
        "title": "⚙️ Rôles du récap 22h configurables via /config",
        "items": [
            "La section **Récap recrutement (22h)** dans `/config` propose maintenant un bouton "
            "**🎭 Configurer les rôles** pour choisir : le rôle pingé dans le récap (Recruteur), "
            "le rôle utilisé pour détecter les inactifs (Membre), et le rôle attribué par `/kick` (Absent).",
            "Ces valeurs étaient auparavant codées en dur — elles sont maintenant configurables par serveur.",
        ],
    },
    {
        "version": "2026.09.14.1",
        "title": "🏆 Top/Flop fame hebdomadaire dans le récap 22h",
        "items": [
            "Le Top 3 / Flop 3 fame dans le récap de 22h affiche désormais la **fame gagnée cette semaine** "
            "(reset chaque lundi) plutôt que depuis le recrutement.",
            "Correction d'un bug qui empêchait l'envoi du 2ème message du récap (stats + inactifs + top/flop).",
        ],
    },
    {
        "version": "2026.09.13",
        "title": "🏁 Erreurs de fin d'activité visibles dans Discord",
        "items": [
            "Les erreurs lors de la clôture d'une activité (bouton 🏁) s'affichent maintenant directement "
            "dans Discord en message éphémère, au lieu de disparaître silencieusement dans les logs.",
        ],
    },
    {
        "version": "2026.09.12",
        "title": "⚔️ Template small Naeeeeej",
        "items": [
            "Nouveau template **small Naeeeeej** : compo small scale 30 joueurs (PF1 + PF2), "
            "rôles en majuscules, sélection d'arme via une pop-up (arme + niveau de spécialisation).",
            "L'embed affiche les joueurs en mode compact : `arme — @mention — spé`.",
            "Le **PF2** est masqué jusqu'à ce qu'au moins un rôle PF1 soit complet.",
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
