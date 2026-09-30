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

## Workflow git (ce repo ET lilium-site)
- **Avant tout `git push`** : lancer la suite de tests (`pytest`) et vérifier qu'elle passe. Un test qui échoue bloque le push — corriger le code ou le test avant de pousser, jamais pousser en l'état.
- **Chaque fonctionnalité/fix terminé doit être poussé** — pas de gros paquet de commits qui traîne en local sans être poussé. Un commit propre et un push dès qu'une fonctionnalité est complète et testée, plutôt que d'accumuler.
- Même règle dans le repo `lilium-site` (voir son propre CLAUDE.md).

## Projet compagnon : site web `lilium-site` (repo séparé)

Le site (API FastAPI + Angular) vit dans son propre repo `lilium-site`. Le site embarqué dans ce bot (`web/`, `ENABLE_WEB`) a été **supprimé**.

**Règle : le bot doit fonctionner sans le site ni son API.** Jamais d'appel HTTP du bot vers l'API du site ; le seul lien est la base Postgres partagée.

Ce bot reste **propriétaire du schéma** (`init_db`) — toute table/colonne utilisée par le site se crée ici :
- `builds` (+ colonne `items` JSONB : `{slot: [1 à 3 ids d'objets]}` ou `["*"]` = au choix ; ancien format `{slot: "ID"}` encore toléré), lue par `/massup` (`Service/build_image.py`)
- `custom_templates` : compos du site, format `/addtemplate` + clés `builds` / `builds_pf2` (`{rôle: build_id}`, build imposé à l'inscription `/acti`)
- `web_staff_config` (`/config` → 🌐 Rôle staff du site web) et `web_admins` (`/webadmin`)
- Rafraîchissement du cache des templates toutes les 2 min (`refresh_templates_loop` dans `Service/activites.py`)
