"""
Service/build_image.py — Images PNG d'un build (MP de /massup) et d'une compo (sous /acti).

Le rendu vient de la lib AlbionCreateImageBuild (requirements.txt) : thème lilas et textes
français par défaut. Ici, seulement le lien avec les données du bot (templates Lilium → lignes
de compo, voir lilium_compo.py). Modifier le rendu = modifier la lib, publier un tag, puis
monter ce tag dans requirements.txt du bot et du site.
"""
import albion_create_image_build as lib
from albion_create_image_build import DEFAULT_THEME, IconFetcher, has_tiered_gear  # noqa: F401 (massup)
from lilium_compo import compo_rows

ROLE_ORDER = DEFAULT_THEME.role_order

# None = IconFetcher partagé de la lib ; les tests y mettent un faux (aucun réseau).
fetcher: IconFetcher | None = None


async def build_image(build: dict, signature: str = "") -> bytes:
    """PNG du build (ligne de la table builds), icônes téléchargées, Pillow dans un thread.
    Les anciennes notes ne sont plus dessinées (champ retiré du site) ; les sorts (colonne
    `spells`, JSON brut accepté par la lib) le sont."""
    build = {k: v for k, v in build.items() if k != "notes"}
    return await lib.build_image(build, signature=signature, fetcher=fetcher)


async def compo_image(name: str, template_data: dict, builds_by_id: dict[int, dict], signature: str = "") -> bytes | None:
    """Image de la compo, ou None si aucun de ses rôles n'a de build (encore) en base."""
    rows = [(party, role, count, builds_by_id[bid])
            for party, role, count, bid in compo_rows(template_data) if bid in builds_by_id]
    return await lib.compo_image(rows, signature=signature, fetcher=fetcher)
