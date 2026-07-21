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
```

> Sur **Railway**, `DATABASE_URL` est injecté automatiquement par le plugin PostgreSQL. Pas besoin de le définir manuellement.

> Le bot n'a besoin d'aucune autre configuration pour être multi-serveur : à chaque démarrage, il synchronise ses commandes sur **tous** les serveurs où il est installé (`bot.guilds`). `DISCORD_GUILD_ID` ne sert plus qu'à identifier le serveur principal pour les anciennes données (migrations DB) et certaines fonctionnalités historiques (voir plus bas).

### Lancement

```bash
python bot.py
```

Les tables SQL sont créées automatiquement au premier démarrage.

---

## Commandes

### Activités

| Commande | Accès | Description |
|---|---|---|
| `/acti` | Membre | Créer une activité de guilde |
| `/templates` | Membre | Afficher les templates disponibles |

**Paramètres de `/acti` :**
- `nametemplate` — Template de composition (optionnel)
- `nbplayer` — Nombre de joueurs max (calculé depuis le template si renseigné, 100 par défaut sans template)
- `bal` — Paiement BAL ? (`true` = BAL, `false` = Libre) — **défaut : true** (forcé à `false` pour les simples Membres)
- `depart` — Point de départ : `Ville` / `HO` / `Libre` — **défaut : Libre**
- `tier` — Tier requis (champ libre, ex : `T8.3`) — optionnel

> Sans template, une activité libre est créée avec les rôles DPS / HEAL / SUPPORT et 100 places max.

Une fois l'activité créée :
- Les joueurs choisissent leur rôle via le menu déroulant
- **PVP** : sélection de l'arme puis saisie du niveau de spécialisation (1-1000)
- **PVE** : inscription directe
- Bouton 🔀 **Fill** : s'inscrire automatiquement dans le premier slot disponible (sans choisir de rôle/arme)
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
4. Le bot crée un **salon privé** dédié à cette candidature (visible uniquement par le candidat, le rôle recrutement et le rôle **Officier**) avec un bouton **✅ Valider (Staff)**
5. Un membre du staff (rôle recrutement ou Officier) clique sur **✅ Valider (Staff)** → les rôles "en cours" (rôle candidat, rôle par défaut) sont retirés, le rôle configuré via `/config` → ✅ Rôle après validation candidature est attribué au candidat, puis le salon se ferme automatiquement (suppression après quelques secondes)

> Chaque serveur a sa propre configuration (salon, rôles, catégorie) — un serveur sans configuration ne propose pas la fonctionnalité tant que `/setup-recrutement` n'a pas été exécuté.

---

### Configuration (`/config`)

| Commande | Accès | Description |
|---|---|---|
| `/config` | Officier | Panneau interactif pour configurer le serveur |

`/config` ouvre un panneau éphémère (visible seulement par toi) avec un menu déroulant vers 6 sections :

**🔊 Salons vocaux temporaires**
- **➕ Ajouter un hub** — choisis un salon vocal existant qui servira de déclencheur, une catégorie optionnelle pour les salons créés, puis renseigne le nom (`{pseudo}` = pseudo du créateur) et la limite de places
- **✏️ Gérer un hub** — modifier le nom/la limite ou supprimer un hub existant
- Plusieurs hubs possibles par serveur (ex : un hub "Duo", un hub "Squad")
- Rejoindre un salon hub crée automatiquement un salon vocal temporaire et y déplace le membre ; le créateur reçoit les droits de gestion du salon (renommer, limiter les places, déplacer/expulser) ; le salon est supprimé automatiquement dès qu'il est vide

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

**📋 Salon de récap (22h)**
- Choisis le salon où sera posté le récap recrutement automatique de 22h (voir plus bas)
- Bouton **🔕 Désactiver** pour couper le récap sur ce serveur

**✅ Rôle après validation candidature**
- Choisis le rôle attribué automatiquement au candidat quand le staff clique sur **✅ Valider (Staff)** (voir Candidature externe)
- Bouton **🔕 Désactiver** pour couper l'attribution automatique

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

> Le serveur principal historique (`DISCORD_GUILD_ID`) garde son ancien salon de récap par défaut tant qu'aucun salon n'a été explicitement configuré via `/config` pour lui. Les autres serveurs doivent configurer leur salon de récap via `/config` pour activer le rappel automatique.

> `/recap` permet de déclencher manuellement la même logique avec purge immédiate des profils des partis (sans attendre le délai de 3 jours).

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
| `/helpliliumbot` | Tous | Afficher la liste de toutes les commandes du bot |

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
├── requirements.txt
└── Service/
    ├── activites.py    # Commandes /acti et /templates, UI des activités
    ├── admin.py        # Commandes d'administration
    ├── bal.py          # Commandes BAL
    ├── massup.py       # Commande /massup (ping participants)
    ├── moderation.py   # Surveillance format canal acti-flash
    ├── recrutement.py  # Commande /recrutement (fiche de candidature + baseline fame)
    ├── joueur.py                # /info, /ancien, /reporter, /kick + tâche 22h
    ├── recrutement_externe.py  # Candidature en libre-service (/setup-recrutement, salon privé par candidat)
    ├── vocal_temp.py            # Salons vocaux temporaires (hubs → création/suppression auto)
    ├── bienvenue.py             # Messages de bienvenue / au revoir
    ├── config.py                # Panneau /config (vocaux temp, bienvenue, au revoir)
    └── utils.py                # Helpers partagés (is_admin, ActivitySelect, settings)
```

---

## Templates par défaut

| Template | Type | Composition |
|---|---|---|
| RAID AVA | PVE | TANK, OFF TANK, FROST, DAMME, SCOOT, MAIN HEAL, IRON ROOT, DPS ×3, COBRA/GA — liste d'attente activée |
| MiddleScale de G3 LE GOAT | PVP | PF1 : CALLER ×1, TANK ×4, SUPPORT ×4, HEAL ×4, DPS ×7, BM ×1 · PF2 : TANK ×4, SUPPORT ×4, HEAL ×4, DPS ×7 |
| RAID AVA BN | PVE | MAIN TANK ×1, MAIN HEAL ×1, OFF TANK ×1, COBRA ×1, IRON ×1, SC ×1, HURLEGIVRE ×1, FAUX ×3, SCOUT ×1, LEACHER PVP ×1 — inscription via `/addacti` uniquement, LEACHER PVP reçoit 0 BAL |
| STATIK | PVE | TANK ×2, HEAL ×2, SUPPORT ×1, DPS ×5 |
| HeavyMelee | PVP (sans spé) | TANK ×4, SUPPORT ×4, HEAL ×4, DPS ×7 — armes affichées à titre indicatif, inscription directe sans saisie de spé |
| small Naeeeeej | PVP | PF1 : CALLER ×1, 2ND REPACK ×1, TANK DEF ×2, TANK OFF ×2, SUPPORT DEF ×2, SUPPORT OFF ×2, HEAL ×3, HEAL SUPP ×1, DPS ×5, FINISHER ×1 · PF2 : TANK DEF ×1, TANK OFF ×1, SUPPORT DEF ×1, SUPPORT OFF ×1, HEAL ×1, HEAL SUPP ×1, DPS ×4 — sélection arme + spé |

Les templates par défaut sont définis dans `config.py` et ne peuvent pas être modifiés via les commandes. Un template par défaut peut être restreint à certains serveurs via la clé `"guild_ids": [id, ...]` (absente ou vide = visible sur tous les serveurs). Les templates custom (`/addtemplate`) sont stockés en base de données et **scopés par serveur** : un template custom créé sur un serveur n'est visible que sur celui-ci.

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

## Déploiement Railway

1. Push le repo sur GitHub
2. Créer un projet Railway depuis le repo
3. Ajouter le plugin **PostgreSQL** → les variables `DATABASE_URL` et `PGXXX` sont injectées automatiquement
4. Ajouter les variables d'environnement `DISCORD_TOKEN` et `DISCORD_GUILD_ID`
5. Inviter le bot sur autant de serveurs Discord que nécessaire — aucune configuration supplémentaire n'est requise, la synchronisation des commandes se fait automatiquement au démarrage
6. Railway build et démarre le bot — les tables sont créées au premier démarrage

> Les soldes BAL, les profils joueurs et les templates custom sont isolés par serveur (`guild_id`). Chaque serveur a son propre pool BAL, son propre taux de rachat (`/setrate`), ses propres profils de recrutement, sa propre configuration de recrutement externe (`/setup-recrutement`) et ses propres templates custom. Les données existantes ont été migrées automatiquement vers le serveur principal (`DISCORD_GUILD_ID`) lors du passage au multi-serveur.

> Les messages personnalisés de `/monbal` et les notifications de limite BAL sont réservés au serveur principal (`DISCORD_GUILD_ID`). La tâche automatique de récap 22h tourne désormais sur **tous** les serveurs ayant un salon configuré via `/config` (le serveur principal garde son ancien salon par défaut).

