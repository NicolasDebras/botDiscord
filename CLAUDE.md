# Instructions pour Claude Code

## README
Mettre à jour README.md à chaque modification du code (nouvelles commandes, changements de comportement, nouvelles dépendances, etc.). Le commit du README doit être inclus dans le même commit que les changements de code.

## CHANGELOG
Mettre à jour changelog.py à chaque modification du code visible par les utilisateurs (nouvelle commande, nouveau comportement, fix notable). Le commit de changelog.py doit être inclus dans le même commit que les changements de code.

Règles :
- Incrémenter VERSION (format YYYY.MM.DD ou YYYY.MM.DD.N si plusieurs releases le même jour)
- Ajouter une entrée en tête de CHANGELOG (ordre du plus récent au plus ancien)
- Chaque entrée a : "version", "title" (emoji + titre court), "items" (liste de phrases claires pour les utilisateurs)

## Tests
Le repo a une suite de tests unitaires (`tests/`, `pytest`) sur la logique pure — parsing armes/rôles (`Service/activites.py`), permissions (`Service/utils.py`), formatage, `changelog.get_entries_since`. Pas de vraie connexion Discord/Postgres (variables d'environnement factices posées par `tests/conftest.py`).

- Lancer `pytest` avant/après un refactor touchant à cette logique (voir `README.md` → section Tests pour l'install)
- Ajouter un test quand on ajoute une fonction de logique pure non triviale (parsing, calcul, règle de permission) — pas la peine pour du code qui ne fait qu'appeler Discord/DB directement
- Ne pas casser les tests existants sans les mettre à jour consciemment (s'ils échouent après un changement volontaire de comportement, corriger l'assertion, pas juste supprimer le test)

## Workflow git (ce repo ET le futur repo lilium-web)
- **Avant tout `git push`** : lancer la suite de tests (`pytest`) et vérifier qu'elle passe. Un test qui échoue bloque le push — corriger le code ou le test avant de pousser, jamais pousser en l'état.
- **Chaque fonctionnalité/fix terminé doit être poussé** — pas de gros paquet de commits qui traîne en local sans être poussé. Un commit propre et un push dès qu'une fonctionnalité est complète et testée, plutôt que d'accumuler.
- Cette règle s'applique aussi au futur repo `lilium-web` (API + Angular, voir section suivante) une fois créé — répliquer ce paragraphe dans son propre CLAUDE.md à sa création.

## Projet compagnon : site web "builds & compos" (repo séparé, pas encore démarré)

Une v1 du site avait été embarquée directement dans le process du bot (FastAPI + Jinja2, dossier `web/`, activable via `ENABLE_WEB`). Décision prise ensuite : repartir sur un **repo séparé** (`lilium-web`, à créer), plus facile à maintenir à terme, contenant à la fois l'API et le frontend **Angular**. Le dossier `web/` embarqué dans ce repo est donc destiné à être retiré (ainsi que `ENABLE_WEB` et les dépendances `fastapi`/`uvicorn`/`jinja2`/`itsdangerous`/`python-multipart`) une fois la bascule faite — `bot.py` reviendra à un simple `await bot.start(TOKEN)`.

**Ce qui reste dans ce repo** (partagé avec la future API via la même base Postgres, ce bot reste propriétaire du schéma via `init_db`) :
- Tables `builds` et `web_staff_config` (`db.py`)
- Section `/config` → 🌐 Rôle staff du site web
- À ajouter : rafraîchissement périodique du cache des templates custom dans `Service/activites.py` (ex. toutes les 2 min, même pattern que le balayage de `vocal_temp.py`), car une API dans un process séparé ne peut plus appeler `refresh_templates_cache()` en direct — nécessaire pour que les compos créées depuis le site soient prises en compte par `/acti` sans redémarrage.

**Architecture décidée pour `lilium-web`** :
- API : FastAPI + asyncpg (même stack que ce bot, réutilise sa logique d'auth/DB). Frontend : Angular. Les deux dans le même repo (`api/` + `frontend/`).
- Connexion : Discord OAuth2 (scope `identify` seulement). Le lien vers une guilde se fait via la commande **`/register` existante** (`Service/recrutement_externe.py`, table `player_profiles`) — pas via le scope OAuth `guilds`. Un utilisateur qui n'a jamais fait `/register` n'a pas de guilde résolue côté site.
- Permissions à deux niveaux :
  - **Rôle staff** (`web_staff_config.staff_role_id`, vérifié via un appel REST Discord `GET /guilds/{id}/members/{id}` avec le token du bot, puisque l'API n'a pas accès au cache live du bot) → créer/modifier **compos** (écrites dans `custom_templates`, même table que `/addtemplate`) et **builds**
  - **Rôle de base** (simplement lié via `/register`) → lecture seule : sa BAL (`db.get_bal`) et les builds de la guilde
- Builds : sélection d'arme/armure avec image in-game (CDN `https://render.albiononline.com/v1/item/{unique_name}.png`), catalogue d'objets sourcé depuis de vraies données Albion (pas inventé de mémoire), champ texte libre gardé en fallback.
- Thème CSS : **noir et lilas**.

Plan détaillé (structure de fichiers, routes, étapes) : `/Users/debrasnicolas/.claude/plans/humble-dreaming-meteor.md`. Rien n'a encore été implémenté pour cette bascule — l'utilisateur reprendra la main depuis son ordi principal.
