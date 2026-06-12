# LiliumBot

Bot Discord pour la gestion des activités et du système BAL de la guilde.


---

## Fonctionnalités

- Création d'activités de guilde avec inscription par rôle (PF1 + PF2)
- Sélection d'arme et niveau de spécialisation pour les activités PVP
- Liste d'attente automatique pour certains templates (ex : RAID AVA)
- Gestion des templates de compositions (défaut + custom)
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
DISCORD_GUILD_ID=ton_guild_id          # Serveur principal (ID : 1466706466051330061)
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

> Sur **Railway**, `DATABASE_URL` est injecté automatiquement par le plugin PostgreSQL. Pas besoin de le définir manuellement.

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

La commande ouvre une pop-up avec deux champs :
- **Pseudo IG** — pseudo en jeu du candidat (court)
- **Informations** — classe, stuff, IP, disponibilités, motivation… (paragraphe libre)

Une fois soumise, un embed récapitulatif est posté dans le canal avec la mention Discord du joueur, ainsi que la **fame PvP et PvE** récupérée automatiquement via l'API Albion Online. La fame du moment est enregistrée comme **baseline** pour suivre la progression du joueur.

> Accessible aux membres ayant le rôle **Recruteur** (ID `1473779038106685568`) ou **Officier**.

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

**Rappel automatique 22h** — chaque soir à **22h** (heure de Paris), le bot :
- Envoie un récap en 3 sections : < 1 semaine / < 2 semaines / à valider via `/ancien` (ping Recruteur)
- Met à jour les fames via l'API Albion Online
- Supprime les profils des joueurs qui ont quitté le Discord depuis plus de **3 jours**

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
    ├── recrutement_externe.py  # Système de candidature automatique (second serveur)
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

Les templates par défaut sont définis dans `config.py` et ne peuvent pas être modifiés via les commandes. Les templates custom sont stockés en base de données.

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
5. Railway build et démarre le bot — les tables sont créées au premier démarrage

> Les soldes BAL **et les profils joueurs** sont isolés par serveur (`guild_id`). Chaque serveur a son propre pool BAL, son propre taux de rachat (`/setrate`) et ses propres profils de recrutement. Les données existantes sont migrées automatiquement vers le serveur principal au démarrage.

> Les messages personnalisés de `/monbal` et les notifications de limite BAL sont réservés au serveur principal (`DISCORD_GUILD_ID`). La tâche automatique de récap 22h ne tourne que sur le serveur principal.

