# Instructions pour Claude Code

## README
Mettre à jour README.md à chaque modification du code (nouvelles commandes, changements de comportement, nouvelles dépendances, etc.). Le commit du README doit être inclus dans le même commit que les changements de code.

## CHANGELOG
Mettre à jour changelog.py à chaque modification du code visible par les utilisateurs (nouvelle commande, nouveau comportement, fix notable). Le commit de changelog.py doit être inclus dans le même commit que les changements de code.

Règles :
- Incrémenter VERSION (format YYYY.MM.DD ou YYYY.MM.DD.N si plusieurs releases le même jour)
- Ajouter une entrée en tête de CHANGELOG (ordre du plus récent au plus ancien)
- Chaque entrée a : "version", "title" (emoji + titre court), "items" (liste de phrases claires pour les utilisateurs)
