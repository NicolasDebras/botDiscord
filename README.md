# LiliumBot

Bot Discord pour la gestion des activités et du système BAL de la guilde.


---

## Fonctionnalités

- **Multi-serveur natif** : le bot se synchronise automatiquement sur tous les serveurs où il est installé, sans configuration manuelle
- Création d'activités de guilde avec inscription par rôle (PF1 + PF2)
- Sélection d'arme et niveau de spécialisation pour les activités PVP
- Liste d'attente automatique pour certains templates (ex : RAID AVA)
- Gestion des templates de compositions (défaut + custom, scopés par serveur)
- Système de recrutement externe configurable par serveur (salon privé par candidature)
- Salons vocaux temporaires (hub → création à la volée, suppression automatique une fois vide)
- Messages de bienvenue / au revoir configurables par serveur
- Panneau `/config` unique pour tout configurer (vocaux temporaires, bienvenue, au revoir)
- Système BAL : paiement, classement, historique des transactions
- Commandes d'administration (kick, ajout forcé, templates custom, taux de rachat)
- Persistance **PostgreSQL** via Railway
- **Site web** (builds & compos) — connexion Discord, bibliothèque de builds et créateur de compos visuel, lancé dans le même process que le bot

---

## Installation

### Prérequis

- Python 3.11+
- Une application Discord avec un bot et son token ([discord.com/developers](https://discord.com/developers/applications))
- Une base PostgreSQL (Railway, Supabase, ou locale)

### Dépendances

```bash
pip install -r requirements.txt
```

### Variables d'environnement

Créer un fichier `.env` à la racine :

```env
DISCORD_TOKEN=ton_token_discord
DISCORD_GUILD_ID=ton_guild_id          # Serveur principal — utilisé pour les migrations DB (legacy)
DATABASE_URL=postgresql://user:password@host:5432/dbname

# Site web (builds & compos) — voir section dédiée plus bas. Désactivé par défaut.
ENABLE_WEB=true                        # à ajouter seulement quand la config OAuth2 ci-dessous est prête
DISCORD_CLIENT_ID=ton_application_id
DISCORD_CLIENT_SECRET=ton_client_secret
DISCORD_REDIRECT_URI=https://ton-domaine/auth/callback
WEB_SESSION_SECRET=une_chaine_aleatoire_longue
PORT=8080                              # injecté automatiquement par Railway
```

> Sur **Railway**, `DATABASE_URL` est injecté automatiquement par le plugin PostgreSQL. Pas besoin de le définir manuellement.

> Le bot n'a besoin d'aucune autre configuration pour être multi-serveur : à chaque démarrage, il synchronise ses commandes sur **tous** les serveurs où il est installé (`bot.guilds`). `DISCORD_GUILD_ID` ne sert plus qu'à identifier le serveur principal pour les anciennes données (migrations DB) et certaines fonctionnalités historiques (voir plus bas).

### Lancement

```bash
python bot.py
```

Les tables SQL sont créées automatiquement au premier démarrage.

### Tests

Tests unitaires sur la logique pure (parsing armes/rôles, formatage, permissions, changelog) — pas de connexion Discord ni Postgres nécessaire, juste des variables d'environnement factices (posées automatiquement par `tests/conftest.py`).

```bash
pip install -r requirements-dev.txt
pytest
```

> Ces tests ne couvrent pas les fonctions qui appellent réellement Discord ou la base de données (out of scope pour de l'unitaire pur) — seulement la logique qui peut casser silencieusement lors d'un refactor (ex. le parsing `_parse_weapon_slots`/`_sort_roles`, déjà responsable d'un bug réel corrigé cette session).

---

## Commandes

### Activités

| Commande | Accès | Description |
|---|---|---|
| `/acti` | Membre | Créer une activité de guilde |
| `/templates` | Membre | Afficher les templates disponibles |
| `/massup [message]` | Membre | Ping tous les inscrits d'une activité ; avec une compo du site, envoie aussi à chacun **l'image de son build en MP** |

**Paramètres de `/acti` :**
- `nametemplate` — Template de composition (optionnel)
- `nbplayer` — Nombre de joueurs max (calculé depuis le template si renseigné, 100 par défaut sans template)
- `bal` — Paiement BAL ? (`true` = BAL, `false` = Libre) — **défaut : true** (forcé à `false` pour les simples Membres)
- `depart` — Point de départ : `Ville` / `HO` / `Libre` — **défaut : Libre**
- `tier` — Tier requis (champ libre, ex : `T8.3`) — optionnel

> Sans template, une activité libre est créée avec les rôles DPS / HEAL / SUPPORT et 100 places max.

**Compos du site (builds imposés)** — une compo créée sur le site `lilium-site` est un ensemble de builds (un build par rôle et par party). Avec `/acti nametemplate:<compo>` :
- à l'inscription, le joueur choisit juste son **rôle** : le build lui est imposé (pas de liste d'armes). En PVP le bot demande toujours le niveau de spé ;
- `/massup` envoie en plus, en **MP**, à chaque joueur inscrit sur un rôle avec build, une **image de son build** (icônes officielles de l'équipement façon inventaire du jeu, choix multiples, cases « au choix », précisions). Le lanceur reçoit un récap éphémère (nombre de MP envoyés, joueurs aux MP fermés).

Une fois l'activité créée :
- Les joueurs choisissent leur rôle via le menu déroulant
- **PVP** : sélection de l'arme puis saisie du niveau de spécialisation (1-1000)
- **PVE** : inscription directe
- Bouton 🔀 **Fill** : s'inscrire dans un rôle **Fill** dédié (affiché comme les autres rôles dans l'embed), sans choisir de rôle/arme — compte dans le total de joueurs et passe en liste d'attente si l'activité est pleine
- Bouton ❌ pour se retirer (slots ou liste d'attente)
- Bouton ⏳ Liste d'attente (sur les templates avec `has_waitlist`)
- Bouton ✏️ Modifier (créateur ou Officier) → change la description, le tier et le départ
- Bouton 🏁 Fin d'activité (organisateur ou Officier) → calcul et crédit BAL automatique
  - Formule : `((recettes VM - réparations) × taux guilde%) + pièces coffre`
  - Les **pièces VM du coffre** s'ajoutent après la taxe guilde (non taxées)
- Bouton 🔴 Annuler le raid (organisateur ou admin)

---

### BAL

| Commande | Accès | Description |
|---|---|---|
| `/monbal` | Membre | Voir son propre solde BAL |
| `/transferbal @joueur montant` | Membre | Transférer de la BAL à un autre joueur (le receveur reçoit un DM de confirmation) |
| `/classement` | Membre | Voir le classement BAL du serveur (top 20) |
| `/addbal @joueur montant` | Officier | Ajouter des BAL à un joueur |
| `/retirebal @joueur montant` | Officier | Retirer des BAL à un joueur |
| `/paybal montant` | Officier | Distribuer des BAL à tous les participants d'une activité |
| `/baljoueur @joueur` | Officier | Voir le solde BAL d'un joueur spécifique |
| `/ballog [page] [joueur] [action]` | Officier | Historique BAL sur 6 mois (paginé, filtrable par joueur et par type d'action) |
| `/statbal [jours]` | Officier | Total silver distribué sur une période (défaut : 7 jours), ventilé par type d'action |

> `/paybal` ne fonctionne que sur les activités créées avec `bal: true`.

---

### Recrutement

| Commande | Accès | Description |
|---|---|---|
| `/recrutement @joueur` | Recruteur, Officier | Enregistrer une candidature de recrutement |
| `/setup-recrutement` | Admin | Configurer et poster le message de candidature sur ce serveur |
| `/register pseudo` | Tous | Enregistrer son pseudo IG quand l'API Albion Online ne l'a pas trouvé automatiquement |

La commande `/recrutement` ouvre une pop-up avec deux champs :
- **Pseudo IG** — pseudo en jeu du candidat (court)
- **Informations** — classe, stuff, IP, disponibilités, motivation… (paragraphe libre)

Une fois soumise, un embed récapitulatif est posté dans le canal avec la mention Discord du joueur, ainsi que la **fame PvP et PvE** récupérée automatiquement via l'API Albion Online. La fame du moment est enregistrée comme **baseline** pour suivre la progression du joueur.

> Accessible aux membres ayant le rôle **Recruteur** (ID `1473779038106685568`) ou **Officier**.

#### Candidature externe (`/setup-recrutement`)

Système de candidature en libre-service, **configurable indépendamment sur chaque serveur** :

1. Un admin lance `/setup-recrutement` avec :
   - `salon_regles` — salon où poster le message avec le bouton de candidature
   - `role_recrutement` — rôle qui aura accès aux salons de candidature créés
   - `role_candidat` — rôle attribué automatiquement aux nouveaux arrivants
   - `categorie` *(optionnel)* — catégorie où créer les salons de candidature
2. Un candidat clique sur **📋 Déposer ma candidature** → répond à un questionnaire (pseudo IG, découverte, disponibilités, contenu recherché, attentes)
3. Le bot recherche automatiquement la **fame PvE/PvP** du pseudo via l'API Albion Online, renomme le candidat sur Discord avec son pseudo in-game, et enregistre son profil (baseline fame) — l'équivalent de `/recrutement` se fait donc automatiquement, sans ressaisie du pseudo
4. Le bot crée un **salon privé** dédié à cette candidature (visible uniquement par le candidat, le rôle recrutement et le rôle **Officier**) avec un bouton **✅ Valider (Staff)**, puis ping le candidat pour lui demander une **capture d'écran de son écran d'accueil** (sélection de personnage) et une **capture de ses stats** — si son pseudo n'a pas été trouvé sur l'API, le message lui indique d'utiliser `/register` pour l'enregistrer manuellement
5. Un membre du staff (rôle recrutement ou Officier) clique sur **✅ Valider (Staff)** → les rôles "en cours" (rôle candidat, rôle par défaut) sont retirés, le rôle configuré via `/config` → ✅ Rôle après validation candidature est attribué au candidat, puis le salon se ferme automatiquement (suppression après quelques secondes)

`/register pseudo` — si l'API Albion Online n'a pas trouvé le candidat au moment de la candidature (nom introuvable, API indisponible…), il peut enregistrer lui-même son pseudo avec cette commande : le bot recherche la fame, renomme le membre, crée son profil, et prévient le salon de candidature en cours s'il y en a un. **Un profil ne peut être enregistré qu'une seule fois** — si le joueur est déjà enregistré, la commande refuse et invite à contacter le staff pour une correction.

> Chaque serveur a sa propre configuration (salon, rôles, catégorie) — un serveur sans configuration ne propose pas la fonctionnalité tant que `/setup-recrutement` n'a pas été exécuté.

---

### Configuration (`/config`)

| Commande | Accès | Description |
|---|---|---|
| `/config` | Officier | Panneau interactif pour configurer le serveur |

`/config` ouvre un panneau éphémère (visible seulement par toi) avec un menu déroulant vers 8 sections :

**🔊 Salons vocaux temporaires**
- **➕ Ajouter un hub** — choisis un salon vocal existant qui servira de déclencheur, une catégorie optionnelle pour les salons créés, puis renseigne le nom (`{pseudo}` = pseudo du créateur) et la limite de places
- **✏️ Gérer un hub** — modifier le nom/la limite ou supprimer un hub existant
- Plusieurs hubs possibles par serveur (ex : un hub "Duo", un hub "Squad")
- Rejoindre un salon hub crée automatiquement un salon vocal temporaire et y déplace le membre ; le créateur reçoit les droits de gestion du salon (renommer, limiter les places, déplacer/expulser) ; le salon est supprimé automatiquement dès qu'il est vide — un balayage de sécurité toutes les 2 minutes rattrape les cas où l'événement Discord a été manqué (déconnexion, redémarrage du bot)

**👋 Message de bienvenue** / **🚪 Message d'au revoir**
- Choisis le salon textuel puis renseigne le message dans la pop-up
- Le message de bienvenue accepte aussi une **image/GIF** (URL) affichée dans l'embed
- Placeholders disponibles : `{mention}` `{pseudo}` `{nom}` `{serveur}` `{membercount}`
- Envoyé sous forme d'**embed** (avatar du membre, numéro de membre pour la bienvenue)
- Bouton **🔕 Désactiver** pour couper le message sans perdre la config

**🎭 Rôle par défaut**
- Choisis le rôle attribué automatiquement à tout nouveau membre qui rejoint le serveur
- Bouton **🔕 Désactiver** pour couper l'attribution automatique
- ⚠️ Le rôle du bot doit être placé **au-dessus** du rôle par défaut dans la liste des rôles du serveur, et le bot doit avoir la permission **Gérer les rôles**, sinon l'attribution échoue silencieusement (visible dans les logs du bot)

**📋 Récap recrutement (22h)**
- Choisis le salon où sera posté le récap recrutement automatique de 22h (voir plus bas)
- **🎭 Configurer les rôles** — 3 rôles à sélectionner :
  - **Rôle Recruteur** — pingé dans le récap de suivi recrutement
  - **Rôle Membre** — utilisé pour détecter les membres inactifs (sans activité depuis 2 semaines)
  - **Rôle Absent** — attribué au joueur lors d'un `/kick` (remplace la valeur hardcodée)
- Bouton **🔕 Désactiver** pour couper le récap sur ce serveur

**✅ Rôle après validation candidature**
- Choisis le rôle attribué automatiquement au candidat quand le staff clique sur **✅ Valider (Staff)** (voir Candidature externe)
- Bouton **🔕 Désactiver** pour couper l'attribution automatique

**🏷️ Rôles à la carte (boutons)**
- **➕ Créer un message de rôles** — choisis le salon de publication, puis jusqu'à 25 rôles dans le menu déroulant, puis renseigne un titre et une description (pop-up) pour l'embed
- Le bot poste un embed avec **un bouton par rôle** ; cliquer sur un bouton **attribue** le rôle s'il ne l'a pas, ou le **retire** s'il l'a déjà (toggle)
- **🗑️ Supprimer un message** — choisis un message existant dans le menu pour le retirer de la config et supprimer le message Discord
- Plusieurs messages de rôles possibles par serveur (ex : un pour les jeux, un pour les fuseaux horaires…)
- Les boutons restent fonctionnels après un redémarrage du bot (vue persistante)

**📢 Annonces de mises à jour**
- Choisis un salon : le bot y poste immédiatement la dernière nouveauté, puis à chaque redémarrage avec une nouvelle version du bot, poste automatiquement les entrées du changelog (`changelog.py`) pas encore annoncées sur ce serveur
- Bouton **🔕 Désactiver** pour couper les annonces sur ce serveur
- Chaque serveur suit sa propre progression dans le changelog (`last_version`), donc configurer le salon plus tard sur un autre serveur ne fait pas manquer les annonces

> Toute la configuration (`/config`, `/setup-recrutement`, `/setrate`, templates custom…) est isolée par serveur (`guild_id`).

### Profil & suivi joueur

| Commande | Accès | Description |
|---|---|---|
| `/info @joueur` | Tous | Voir le profil d'un joueur : pseudo IG, fame Albion, activités terminées |
| `/ancien @joueur` | Recruteur, Officier | Basculer le statut Nouveau joueur ↔ Membre |
| `/reporter @joueur` | Recruteur, Officier | Repousser le suivi d'un nouveau joueur d'une semaine (vacances, maladie…) |
| `/kick @joueur` | Maitre de guilde | Passer un joueur en AFK — retire tous ses rôles, ajoute le rôle Absent, envoie un DM |
| `/recap` | Recruteur, Officier | Relancer manuellement le récap recrutement — purge immédiate des profils des partis |

L'embed `/info` affiche :
- **Pseudo IG** (enregistré via `/recrutement`)
- **Activités terminées** — nombre de fins d'activité auxquelles le joueur était présent
- **Fame PvP / PvE actuelle** (API Albion Online en temps réel, cache si API indisponible)
- **Fame gagnée depuis le recrutement** (différence avec la baseline enregistrée lors du `/recrutement`)
- **Infos recrutement** (notes saisies lors de la candidature)

> Si le joueur n'a jamais été recruté via le bot, seul le compteur d'activités est disponible.

**Rappel automatique 22h** — chaque soir à **22h** (heure de Paris), sur **chaque serveur où le bot est installé et où un salon de récap est configuré** (`/config` → 📋 Salon de récap) :
- Envoie un récap en 3 sections : < 1 semaine / < 2 semaines / à valider via `/ancien` (ping Recruteur)
- Met à jour les fames via l'API Albion Online
- Supprime les profils des joueurs qui ont quitté le Discord depuis plus de **3 jours**
- Affiche un **🏆 Top 3** et un **🐌 Flop 3** des joueurs ayant gagné le plus / le moins de fame (PvP + PvE cumulée) depuis leur recrutement

> Le serveur principal historique (`DISCORD_GUILD_ID`) garde son ancien salon de récap par défaut tant qu'aucun salon n'a été explicitement configuré via `/config` pour lui. Les autres serveurs doivent configurer leur salon de récap via `/config` pour activer le rappel automatique.

> `/recap` permet de déclencher manuellement la même logique avec purge immédiate des profils des partis (sans attendre le délai de 3 jours).

---

### Location d'armes

| Commande | Accès | Description |
|---|---|---|
| `/location @joueur arme duree [caution]` | Officier | Créer une location d'arme |
| `/recaplocation` | Officier | Voir toutes les locations actives avec décompte et montant dû |
| `/closelocation id` | Officier | Clôturer une location et afficher le montant final |

**Tarif :** 100 000 silver / jour.

Le compteur s'incrémente **chaque soir à 22h** — le jour de création ne compte pas.

Chaque location affiche :
- Le joueur locataire et l'arme
- La date de début
- Le nombre de jours comptés et le montant dû
- La caution versée (si renseignée)

Un `id` unique est attribué à chaque location — visible dans `/recaplocation` — à passer à `/closelocation` pour la clôturer.

---

### Administration

| Commande | Accès | Description |
|---|---|---|
| `/kickacti @joueur` | Organisateur, Officier ou Caller | Retirer un joueur d'une activité |
| `/addacti @joueur role` | Officier ou Caller | Ajouter ou déplacer un joueur dans une activité |
| `/addtemplate` | Officier | Ajouter un template custom (format JSON) |
| `/deltemplate nom` | Officier | Supprimer un template custom |
| `/setimage nom [url]` | Officier | Modifier l'image d'un template (laisser url vide pour retirer) |
| `/setdescription nom [description]` | Officier | Modifier la description d'un template (laisser vide pour retirer) |
| `/setrate taux` | Maitre de guilde | Modifier le taux de rachat guilde (%) |
| `/balpartis [vider]` | Officier | Lister les joueurs qui ont quitté le Discord mais ont encore de la BAL |
| `/totalbal` | Officier, GM | Afficher le total des BAL dues par la guilde (classé par montant) |
| `/errors [page] [commande] [id_erreur]` | Officier | Historique des erreurs de commandes slash (30 jours) — `id_erreur` renvoie la traceback complète en fichier |
| `/helpliliumbot` | Tous | Afficher la liste de toutes les commandes du bot |
| `/webadmin add @membre` / `remove @membre` / `list` | Admin serveur, Maitre de guilde | Gérer les **admins du site web** (niveau au-dessus du staff, accès à la page Admin du site `lilium-site`) |

**Journal d'erreurs (`/errors`)** — toute exception inattendue est enregistrée en base (30 jours glissants) : commandes slash (en plus du message éphémère affiché à l'utilisateur), mais aussi les listeners (arrivée/départ de membre, salons vocaux…) et les tâches de fond (récap 22h, locations, annonces de mise à jour), qui ne passent pas par le même flux et étaient auparavant invisibles sans accès aux logs Railway. `/errors` liste les dernières erreurs (paginé, filtrable par commande) ; `/errors id_erreur:<ID>` renvoie la traceback Python complète en pièce jointe.

> Les tâches planifiées (`@tasks.loop`) de discord.py s'arrêtent **définitivement** si une exception s'en échappe. Chaque salon/serveur traité par ces tâches (nettoyage des salons vocaux temporaires, annonces de mise à jour…) est donc isolé dans son propre `try/except` pour qu'une erreur sur un élément n'interrompe jamais le reste.

**Exemple `/addtemplate` — ZvZ PF1+PF2 avec specs :**
```
/addtemplate
  nom: ZvZ Lilium
  type_acti: PVP
  description: Compo ZvZ 20v20 double party
  json_roles: {"TANK": 2, "SUPPORT": 4, "HEAL": 3, "DPS": 6}
  json_roles_pf2: {"TANK": 1, "SUPPORT": 5, "HEAL": 3, "DPS": 6}
  json_specs: {"TANK": "1H Masse controle · Tank flex", "SUPPORT": "Serpent · Locus · Incube", "HEAL": "Sancti · Naturel druide", "DPS": "Pointes · BR · Brassards · Arc Long"}
  json_specs_pf2: {"TANK": "Second repack (golem)", "SUPPORT": "Bec de Corbin · GA · Locus", "HEAL": "Exalté · Sancti", "DPS": "Spirit · Perma · BR · DPS clap range"}
  image: https://exemple.com/image.png
```

---

## Structure du projet

```
LiliumBot/
├── bot.py              # Point d'entrée, init DB, chargement des cogs
├── config.py           # Token, rôles, templates par défaut, couleurs
├── db.py               # Couche d'accès PostgreSQL (asyncpg)
├── albion_api.py       # Client API Albion Online (fame, recherche joueur)
├── changelog.py        # VERSION + entrées annoncées via /config → 📢 Annonces de mises à jour
├── requirements.txt
├── web/                # Site web (builds & compos), lancé dans le process du bot
│   ├── main.py         # App FastAPI, routes racine, guild picker
│   ├── auth.py         # OAuth2 Discord (scope identify) + session cookie signée
│   ├── routes_builds.py
│   ├── routes_compos.py
│   ├── templates/      # Jinja2 (base, login, guilds, builds/, compos/)
│   └── static/style.css
└── Service/
    ├── activites.py    # Commandes /acti et /templates, UI des activités
    ├── admin.py        # Commandes d'administration
    ├── bal.py          # Commandes BAL
    ├── massup.py       # Commande /massup (ping participants + image du build en MP)
    ├── build_image.py  # Image PNG d'un build (Pillow, police Inter dans assets/fonts)
    ├── moderation.py   # Surveillance format canal acti-flash
    ├── recrutement.py  # Commande /recrutement (fiche de candidature + baseline fame)
    ├── joueur.py                # /info, /ancien, /reporter, /kick + tâche 22h
    ├── recrutement_externe.py  # Candidature en libre-service (/setup-recrutement, salon privé par candidat)
    ├── vocal_temp.py            # Salons vocaux temporaires (hubs → création/suppression auto)
    ├── bienvenue.py             # Messages de bienvenue / au revoir
    ├── self_roles.py            # Rôles auto-attribuables par boutons (self-service)
    ├── config.py                # Panneau /config (vocaux temp, bienvenue, au revoir, rôles à la carte, staff web)
    ├── errors.py                # Commande /errors — historique des erreurs (voir plus bas)
    ├── web_admin.py             # /webadmin — admins du site web (table web_admins, lue par lilium-site)
    └── utils.py                # Helpers partagés (is_admin, ActivitySelect, settings, log_error)
```

---

## Templates par défaut

| Template | Type | Composition |
|---|---|---|
| Donjon Groupe 5 | PVE | TANK ×1, DPS ×3, HEAL ×1 |

**RAID AVA BN** est conservé en commentaire dans `config.py` (juste au-dessus de `DEFAULT_TEMPLATES`) pour réactivation facile ; les autres templates par défaut historiques (RAID AVA, MiddleScale Pentacle, STATIK, HeavyMelee, small Naeeeeej, MONKEY BANANA) ont été supprimés du code. Tous les templates custom (`/addtemplate`) ont également été purgés de la base de données (nettoyage ponctuel au démarrage, une seule fois).

Un template par défaut peut être restreint à certains serveurs via la clé `"guild_ids": [id, ...]` (absente ou vide = visible sur tous les serveurs). Les templates custom (`/addtemplate`) sont stockés en base de données et **scopés par serveur** : un template custom créé sur un serveur n'est visible que sur celui-ci.

---

## Rôles disponibles

| Rôle | Emoji |
|---|---|
| TANK | 🛡️ |
| OFF TANK | 🛡️ |
| HEAL | 💚 |
| MAIN HEAL | 💚 |
| IRON ROOT | 🌿 |
| DPS | ⚔️ |
| DAMME | 💥 |
| SUPPORT | 🔮 |
| CALLER | 📢 |
| SCOOT | 🏃 |
| FROST | ❄️ |
| COBRA/GA | 🏹 |
| BM | 🐴 |

---

## Site web (builds & compos)

Un site web tourne **dans le même process que le bot** (serveur FastAPI lancé en tâche de fond dans `bot.py`, à côté de la connexion Discord) — pas de service séparé à héberger. **Désactivé par défaut** (`ENABLE_WEB` absent ou différent de `true`) : le bot démarre normalement sans le site tant que la config OAuth2 n'est pas en place. Il permet, connecté avec son compte Discord :

- **Bibliothèque de builds** — créer/consulter des loadouts individuels (rôle, arme, notes, image, et équipement Albion — colonne `items` — choisi sur le nouveau site `lilium-site`), filtrables par rôle et par type (PVP/PVE)
- **Créateur de compos** — assembler des rôles en composition complète (PF1 + PF2, hints d'armes par rôle). Écrit directement dans la même base que `/addtemplate` : une compo créée sur le site est **immédiatement utilisable dans `/acti`**, sans redémarrer le bot

**Accès** :
- Connexion via Discord OAuth2 (scope `identify` uniquement) — l'appartenance aux serveurs et les rôles sont vérifiés via le cache live du bot, pas via l'API Discord
- Lecture (builds + compos) ouverte à tout membre du serveur
- Création/modification/suppression réservée au rôle configuré via `/config` → 🌐 Rôle staff du site web (site en lecture seule tant qu'aucun rôle n'est configuré)

**Mise en place** (en plus des variables d'environnement du site, voir plus haut) :
1. Dans le [Discord Developer Portal](https://discord.com/developers/applications), onglet **OAuth2** de l'application du bot : générer un **Client Secret**, et ajouter le redirect URI (`https://<domaine>/auth/callback`)
2. Sur Railway, activer le **networking public** sur le service du bot (Railway injecte alors `PORT` et route le trafic HTTP vers le process) et poser `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_REDIRECT_URI`, `WEB_SESSION_SECRET`
3. Configurer le rôle staff via `/config` → 🌐 Rôle staff du site web, sur chaque serveur
4. Poser `ENABLE_WEB=true` en dernier, une fois tout ce qui précède en place

**Aperçu visuel sans setup** — `web/dev_preview.py` sert les mêmes pages avec des données factices (pas de Discord, pas de base) :
```bash
pip install fastapi "uvicorn[standard]" jinja2 python-multipart
python3 -m web.dev_preview   # http://localhost:8080
```

**Nouveau site séparé (`lilium-site`, API + Angular)** — en cours de remplacement de ce site embarqué. Il partage la même base : ce bot crée les tables (dont `web_admins`, alimentée par `/webadmin`) et recharge le cache des templates custom **toutes les 2 minutes**, pour que les compos créées depuis le site séparé soient prises en compte par `/acti` sans redémarrage.

> Hors périmètre pour l'instant (pistes d'évolution) : tableau de roster synchronisé aux inscriptions `/acti`, tracking loot/regear, analytics de présence.

---

## Déploiement Railway

1. Push le repo sur GitHub
2. Créer un projet Railway depuis le repo
3. Ajouter le plugin **PostgreSQL** → les variables `DATABASE_URL` et `PGXXX` sont injectées automatiquement
4. Ajouter les variables d'environnement `DISCORD_TOKEN` et `DISCORD_GUILD_ID` (+ les variables du site web, voir section dédiée, si tu veux l'activer)
5. Inviter le bot sur autant de serveurs Discord que nécessaire — aucune configuration supplémentaire n'est requise, la synchronisation des commandes se fait automatiquement au démarrage
6. Railway build et démarre le bot — les tables sont créées au premier démarrage

> Les soldes BAL, les profils joueurs et les templates custom sont isolés par serveur (`guild_id`). Chaque serveur a son propre pool BAL, son propre taux de rachat (`/setrate`), ses propres profils de recrutement, sa propre configuration de recrutement externe (`/setup-recrutement`) et ses propres templates custom. Les données existantes ont été migrées automatiquement vers le serveur principal (`DISCORD_GUILD_ID`) lors du passage au multi-serveur.

> Les messages personnalisés de `/monbal` et les notifications de limite BAL sont réservés au serveur principal (`DISCORD_GUILD_ID`). La tâche automatique de récap 22h tourne désormais sur **tous** les serveurs ayant un salon configuré via `/config` (le serveur principal garde son ancien salon par défaut).

