# botDiscord

Règles communes (invariants, workflow git, lecture économe) : `../CLAUDE.md`.

## Carte
- `bot.py` — démarrage, cogs, `allowed_mentions` par défaut, liste blanche `ALLOWED_GUILD_IDS`, handler d'erreurs
- `config.py` — env, noms de rôles (Officier, Maitre de guilde, Membre, Caller), ROLES, DEFAULT_TEMPLATES
- `db.py` — schéma (`init_db`) + toutes les requêtes ; tables du site : `builds`, `custom_templates`, `web_staff_config`, `web_admins`, `public_compos`, `activity_log`
- `Service/utils.py` — permissions (`is_admin`, `is_membre`…, `role_grant_refusal`, `kick_refusal`), `log_error`
- `Service/activites.py` — /acti, inscriptions, `/finacti` (`FinActiModal`), cache templates (2 min)
- `Service/bal.py` — commandes BAL ; `Service/massup.py` + `build_image.py` — ping + images de build/compo
- `Service/config.py` — panneau /config ; `self_roles.py`, `bienvenue.py`, `vocal_temp.py`, `recrutement*.py`, `joueur.py`, `web_admin.py`, `errors.py`

## À chaque changement
- Commande ajoutée/modifiée → mettre à jour `lilium-site/frontend/src/app/pages/guide/guide-content.ts` (vérifié par `tests/test_guide_sync.py`).
- README.md mis à jour si visible.
- `changelog.py` si visible par les joueurs : VERSION `YYYY.MM.DD[.N]`, entrée en tête `{"version", "title": emoji + titre, "items": [...]}`.

## Tests (`tests/`, pytest, logique pure)
- Pas de Discord/Postgres réels (env factice dans `tests/conftest.py`, doubles dans `tests/fakes.py`).
- Test pour toute logique pure non triviale (parsing, calcul, permission) ; pas pour du simple appel Discord/DB.
- Test rouge après un changement voulu : corriger l'assertion, jamais supprimer le test.
- Local Windows : `Service/joueur.py` exige `tzdata` (absent du Python système) — pas un bug.
