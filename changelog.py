"""
Changelog du bot — annoncé automatiquement dans le salon configuré via
/config → 📢 Annonces mises à jour, dès qu'une nouvelle version est détectée
au démarrage du bot.

Pour annoncer une nouvelle fonctionnalité : incrémenter VERSION et ajouter
une entrée en tête de CHANGELOG (ordre du plus récent au plus ancien).
"""

VERSION = "2026.10.09.3"

CHANGELOG: list[dict] = [
    {
        "version": "2026.10.09.3",
        "title": "⚔️ Tier et enchantement dans les builds",
        "items": [
            "Un build du site peut imposer, objet par objet, un tier (T6, T7, T8) et un enchantement (.0 à .4).",
            "Sur l'image du build en MP (`/massup`) et sur l'image de la compo : icône du bon tier et pastille « 8.1 » colorée selon l'enchantement.",
            "Le tier est un minimum : un équivalent convient (8.1 = 7.2 = 6.3), rappelé dans le MP.",
        ],
    },
    {
        "version": "2026.10.09.2",
        "title": "🗂️ Rôles regroupés par catégorie",
        "items": [
            "Dans l'embed `/acti`, les lignes d'un même rôle (ex. 2 tanks avec des builds différents) sont regroupées sous une seule catégorie 🛡️ TANK, avec un compteur cumulé.",
        ],
    },
    {
        "version": "2026.10.09.1",
        "title": "🛡️ Plusieurs lignes pour un même rôle",
        "items": [
            "Une compo du site peut avoir plusieurs lignes du même rôle avec des builds différents (ex. 1 Def tank + 1 Main tank).",
            "Dans `/acti`, chacune est un rôle séparé (« TANK · Def tank », « TANK · Main tank ») avec ses places et son build envoyé en MP par `/massup`.",
            "Correctif : sur une compo du site en PvP, une ligne avec plusieurs places (ex. DPS ×3) n'acceptait qu'un seul joueur.",
        ],
    },
    {
        "version": "2026.10.09",
        "title": "🔁 Swaps dans les builds",
        "items": [
            "Un build du site peut indiquer jusqu'à 6 **swaps** (objets de rechange, tous emplacements).",
            "Ils apparaissent à droite de l'équipement sur l'image du build envoyée en MP par `/massup` et sur l'image de la compo.",
        ],
    },
    {
        "version": "2026.10.08",
        "title": "🔒 Sécurité renforcée",
        "items": [
            "`/transferbal`, `/finacti` et `/paybal` ne peuvent plus payer deux fois (double clic, envois simultanés).",
            "`/finacti` refuse les montants négatifs, des coûts supérieurs aux recettes et un paiement Scoot supérieur au distribuable.",
            "`/massup` est réservé au créateur de l'activité, aux Callers et aux Officiers, une fois toutes les 2 minutes par activité.",
            "Le bot ne pingue plus jamais @everyone, @here ni un rôle à partir d'un texte saisi par un joueur.",
            "`/kick` ne peut plus viser un Officier, le Maitre de guilde ni quelqu'un de rang égal ou supérieur.",
            "Les rôles de staff et les rôles à permissions sensibles ne peuvent plus être distribués par les rôles à la carte, le rôle d'arrivée ou le rôle de validation.",
            "`/info` est réservé aux membres ; les réponses de candidature ne sont visibles que par les Recruteurs et Officiers.",
            "Le pseudo Albion doit correspondre exactement (majuscules ignorées) pour `/register` et la candidature.",
            "Le propriétaire d'un vocal temporaire ne peut plus rendre muet ou sourd un autre joueur.",
            "Les erreurs internes ne sont plus affichées aux joueurs (le détail reste dans `/errors`).",
        ],
    },
    {
        "version": "2026.10.03.1",
        "title": "🧹 Rôles simplifiés + image de compo rangée",
        "items": [
            "Les rôles proposés sont réduits à **TANK, HEAL, DPS et SUPPORT**.",
            "L'image de la compo sous `/acti` range les builds par rôle dans chaque party (PF1 puis PF2), "
            "et les noms de build trop longs sont coupés proprement.",
        ],
    },
    {
        "version": "2026.10.01.6",
        "title": "🎨 Image de la compo plus lisible",
        "items": [
            "Les autres choix possibles d'une case s'affichent en mini-icônes, et les cases libres "
            "indiquent « Au choix ».",
            "Le nom de l'acti n'est plus répété sur l'image (il est déjà dans l'embed).",
        ],
    },
    {
        "version": "2026.10.01.5",
        "title": "🩹 Image de la compo fiable + récap recrutement",
        "items": [
            "L'image de la compo sous `/acti` (et celle des builds en MP) s'affiche maintenant à coup "
            "sûr : les icônes des objets sont intégrées au bot au lieu d'être téléchargées à chaque fois.",
            "Le récap recrutement de 22h ne plante plus quand il y a beaucoup de recrues : il est "
            "découpé en plusieurs messages.",
        ],
    },
    {
        "version": "2026.10.01.4",
        "title": "🖼️ Image de la compo sous chaque acti",
        "items": [
            "Quand une acti est lancée avec une compo de builds, le bot poste juste en dessous une "
            "image récapitulative : chaque build avec son rôle, son nombre de places et son équipement.",
        ],
    },
    {
        "version": "2026.10.01.3",
        "title": "🩹 Inscription simplifiée sur les compos de builds",
        "items": [
            "Sur une acti lancée avec une compo de builds, choisir son rôle suffit : plus de "
            "fenêtre de niveau de spé qui bloquait l'inscription.",
        ],
    },
    {
        "version": "2026.10.01.2",
        "title": "🧩 Compos de builds + build en MP avec /massup",
        "items": [
            "Les compos créées sur le site sont maintenant des ensembles de builds : avec `/acti`, "
            "tu choisis ton rôle et le build t'est imposé (plus de liste d'armes).",
            "`/massup` envoie à chaque joueur, en MP, une image de son build (équipement, bouffe, "
            "potion, choix possibles). Pense à ouvrir tes MP pour la recevoir !",
        ],
    },
    {
        "version": "2026.10.01.1",
        "title": "🛡️ Admins du site web — /webadmin",
        "items": [
            "Nouvelle commande `/webadmin add|remove|list` (administrateurs du serveur et Maitre de "
            "guilde) : nomme des **admins du site web**, un niveau au-dessus du staff, qui ont accès "
            "à la page Admin du site.",
            "Les compos créées depuis le site sont prises en compte par `/acti` en 2 minutes maximum, "
            "même quand le site tourne séparément du bot.",
        ],
    },
    {
        "version": "2026.10.01",
        "title": "🌐 Site web — builds & compos",
        "items": [
            "Nouveau site web, connecté avec ton compte Discord : bibliothèque de builds (loadouts "
            "par rôle) et créateur de compos visuel.",
            "Les compos créées sur le site sont immédiatement utilisables dans `/acti` — même base "
            "que `/addtemplate`, pas besoin de redémarrer le bot.",
            "Accès en création réservé au rôle configuré via `/config` → 🌐 Rôle staff du site web "
            "(lecture seule tant qu'aucun rôle n'est configuré).",
            "Désactivé pour l'instant (`ENABLE_WEB`) — nécessite la config OAuth2 Discord côté serveur, "
            "voir le README.",
        ],
    },
    {
        "version": "2026.09.28.3",
        "title": "🩹 Journal d'erreurs étendu à tout le bot + fix fiabilité",
        "items": [
            "Les erreurs dans les listeners (arrivée/départ de membre, salons vocaux…) et les tâches "
            "de fond (récap 22h, locations, annonces de mise à jour) sont désormais enregistrées en "
            "base et consultables via `/errors` — avant, seules les commandes slash étaient couvertes.",
            "Fix fiabilité : une erreur inattendue dans le balayage des salons vocaux temporaires "
            "arrêtait la tâche de fond **définitivement** (comportement des tâches planifiées "
            "discord.py). Chaque salon est maintenant traité isolément.",
            "Fix : sur un bot multi-serveurs, une erreur en annonçant une mise à jour sur un serveur "
            "bloquait l'annonce pour tous les serveurs suivants. Chaque serveur est maintenant isolé.",
        ],
    },
    {
        "version": "2026.09.28.2",
        "title": "⚔️ Nouveau template Donjon Groupe 5",
        "items": [
            "Nouveau template par défaut **Donjon Groupe 5** (PVE) : TANK ×1, DPS ×3, HEAL ×1.",
        ],
    },
    {
        "version": "2026.09.28.1",
        "title": "🧹 Suppression de tous les templates de compositions",
        "items": [
            "Tous les templates par défaut ont été retirés (RAID AVA, MiddleScale Pentacle, STATIK, "
            "HeavyMelee, small Naeeeeej, MONKEY BANANA…) — **RAID AVA BN** est conservé en commentaire "
            "dans `config.py` pour réactivation facile.",
            "Tous les templates custom (`/addtemplate`) ont été purgés de la base de données.",
        ],
    },
    {
        "version": "2026.09.28",
        "title": "🩹 Journal d'erreurs persistant + commande /errors",
        "items": [
            "Toute erreur de commande slash est désormais enregistrée en base (30 jours glissants) "
            "en plus du message éphémère affiché à l'utilisateur.",
            "Nouvelle commande `/errors [page] [commande]` — historique paginé des erreurs, filtrable "
            "par commande.",
            "`/errors id_erreur:<ID>` renvoie la traceback Python complète en pièce jointe.",
        ],
    },
    {
        "version": "2026.09.27",
        "title": "🩹 Erreurs de commandes visibles dans Discord",
        "items": [
            "Toute erreur inattendue dans une commande slash s'affiche maintenant en message d'erreur "
            "éphémère, au lieu de faire échouer silencieusement l'interaction (\"ne répond plus\").",
            "La synchronisation des commandes par serveur au démarrage n'interrompt plus les serveurs "
            "suivants si un serveur échoue.",
        ],
    },
    {
        "version": "2026.09.24",
        "title": "🔧 Fix rôle Fill affiché en double dans l'embed",
        "items": [
            "Le rôle **Fill** n'apparaît plus deux fois dans l'embed d'activité. "
            "Il était dupliqué sur certains templates sans `pf_1` défini.",
        ],
    },
    {
        "version": "2026.09.22",
        "title": "❌ Bouton Refuser dans les candidatures",
        "items": [
            "Un bouton **❌ Refuser la candidature** (staff uniquement) est désormais présent dans chaque salon de candidature. "
            "Il clôture le ticket sans attribuer de rôle de validation.",
        ],
    },
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
