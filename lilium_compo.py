"""
lilium_compo.py — Lignes de l'image d'une compo à partir d'un template Lilium, PARTAGÉ avec le site.

⚠️ Copié tel quel dans lilium-site (api/app/shared/lilium_compo.py) : pur Python, sans
variable d'environnement ni import du bot. Après une modification, lancer
`python -m scripts.sync_from_bot` dans lilium-site/api (sa CI vérifie la copie).

Le rendu de l'image vient de la lib AlbionCreateImageBuild ; ici, seulement le format
des templates Lilium : {"pf_1": {rôle: nombre}, "builds": {rôle: id ou [ids]}, "pf_2"…, "builds_pf2"…}.
"""
from albion_create_image_build import role_rank


def compo_rows(template_data: dict) -> list[tuple[str, str, int, int]]:
    """[(party, rôle, nombre, build_id), ...] pour les rôles de la compo qui ont un build.
    PF1 puis PF2 ; dans chaque party, regroupés par rôle : TANK, HEAL, SUPPORT, DPS, puis le reste."""
    rows = []
    for party, count_key, builds_key in (("Party 1", "pf_1", "builds"), ("Party 2", "pf_2", "builds_pf2")):
        builds = template_data.get(builds_key) or {}
        party_rows = []
        for role, count in (template_data.get(count_key) or {}).items():
            value = builds.get(role)
            if value is None:
                continue
            # {rôle: id} ou {rôle: [id, id…]} (plusieurs builds au choix → une ligne par build)
            for bid in (value if isinstance(value, list) else [value]):
                party_rows.append((party, role, int(count), int(bid)))
        rows.extend(sorted(party_rows, key=lambda r: role_rank(r[1])))   # tri stable
    return rows
