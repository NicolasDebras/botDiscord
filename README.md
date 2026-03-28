# LiliumBot

Bot Discord pour la gestion des activités et du système BAL de la guilde **Lilium** sur Albion Online.

---

## Fonctionnalités

- Création d'activités de guilde avec inscription par rôle
- Gestion des templates de compositions
- Système BAL (paiement et classement)
- Commandes d'administration (kick, ajout forcé, templates custom)

---

## Installation

### Prérequis

- Python 3.10+
- Une application Discord avec un bot et son token ([discord.com/developers](https://discord.com/developers/applications))

### Dépendances

```bash
pip install discord.py
```

### Configuration

Dans `config.py`, renseigne :

| Variable | Description |
|---|---|
| `TOKEN` | Token de ton bot Discord |
| `ADMIN_ROLE_NAME` | Nom exact du rôle autorisé à utiliser les commandes admin |

### Lancement

```bash
python bot.py
```

---

## Commandes

### Activités

| Commande | Description |
|---|---|
| `/acti` | Créer une activité de guilde |
| `/templates` | Afficher les templates de compositions disponibles |

**Paramètres de `/acti` :**
- `type_acti` — Type d'activité (ZvZ, HCE, Ganking…)
- `nametemplate` — Template de composition à utiliser
- `nbplayer` — Nombre de joueurs max (calculé automatiquement si un template est choisi)
- `bal` — Paiement BAL ? (`true` = BAL, `false` = Libre)

Une fois l'activité créée, les joueurs peuvent :
- Choisir leur rôle via le menu déroulant
- Se retirer avec le bouton ❌
- L'organisateur ou un admin peut annuler avec le bouton 🔴

---

### BAL

| Commande | Accès | Description |
|---|---|---|
| `/monbal` | Tous | Voir son propre solde BAL |
| `/classement` | Tous | Voir le classement BAL du serveur (top 20) |
| `/addbal @joueur montant` | Admin | Ajouter des BAL à un joueur |
| `/retirebal @joueur montant` | Admin | Retirer des BAL à un joueur |
| `/paybal montant` | Admin | Distribuer des BAL à tous les participants d'une activité |

> `/paybal` ne fonctionne que sur les activités créées avec `bal: true`.

Les données BAL sont sauvegardées dans `bal.json` à la racine du projet.

---

### Administration

| Commande | Description |
|---|---|
| `/kickacti @joueur` | Retirer un joueur d'une activité en cours |
| `/addacti @joueur role` | Ajouter ou déplacer un joueur dans une activité |
| `/addtemplate nom json` | Ajouter un template custom (format JSON) |
| `/deltemplate nom` | Supprimer un template custom |

**Exemple `/addtemplate` :**
```
/addtemplate nom:ZvZ Lilium json_roles:{"TANK": 5, "HEAL": 5, "DPS": 10, "CALLER": 1}
```

Les templates custom sont sauvegardés dans `templates.json`. Les templates par défaut (définis dans `config.py`) ne peuvent pas être modifiés ou supprimés via les commandes.

---

## Structure du projet

```
LiliumBot/
├── bot.py              # Point d'entrée, chargement des cogs
├── config.py           # Token, rôles, templates, couleurs
├── bal.json            # Données BAL (généré automatiquement)
├── templates.json      # Templates custom (généré automatiquement)
└── Service/
    ├── activites.py    # Commandes /acti et /templates, UI des activités
    ├── admin.py        # Commandes d'administration
    ├── bal.py          # Commandes BAL
    └── utils.py        # Helpers partagés (is_admin, ActivitySelect)
```

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

---

## Templates par défaut

| Template | Composition |
|---|---|
| ZvZ Standard | TANK ×5, HEAL ×5, DPS ×10, SUPPORT ×5, CALLER ×1 |
| Small Scale | TANK ×2, HEAL ×2, DPS ×6 |
| HCE 5-man | TANK ×1, HEAL ×1, DPS ×3 |
| Ganking Party | TANK ×1, DPS ×4 |
| RAID AVA | TANK, OFF TANK, DPS ×3, FROST, DAMME, SCOOT, MAIN HEAL, IRON ROOT |
