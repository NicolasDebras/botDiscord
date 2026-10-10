"""
Service/build_image.py — Image PNG d'un build (envoyée en MP par /massup).

Un build vient du site lilium-site (table builds, colonne items) :
    {"mainhand": ["2H_HOLYSTAFF", "2H_HOLYSTAFF_HELL"], "cape": ["*"], "food": ["MEAL_STEW"], ...}
chaque case = 1 à 3 objets au choix, ["*"] = au choix du joueur. L'ancien
format {"mainhand": "ID"} est aussi accepté. Un objet peut imposer un tier minimum
et un enchantement au format du jeu : "T8_MAIN_SWORD@1" (8.1) ; l'id nu = tier libre.

L'image reprend la disposition de l'inventaire du jeu (grille 3×3) avec les
icônes officielles d'Albion. Le rendu (render_build_image) est une fonction
pure qui reçoit les icônes déjà téléchargées → testable sans réseau.
"""
import asyncio
import io
import json
import re
import textwrap
from functools import lru_cache
from pathlib import Path

import aiohttp
from PIL import Image, ImageDraw, ImageFont

FREE_CHOICE = "*"

LAYOUT: list[list[str | None]] = [
    [None, "head", "cape"],
    ["mainhand", "armor", "offhand"],
    ["potion", "shoes", "food"],
]
SLOT_LABELS = {
    "mainhand": "Arme", "offhand": "Main gauche", "head": "Tête", "armor": "Armure",
    "shoes": "Bottes", "cape": "Cape", "food": "Bouffe", "potion": "Potion",
}

# Thème du site : noir & lilas
BG       = (11, 10, 15)
SURFACE  = (31, 27, 41)
BORDER   = (46, 40, 64)
LILAC    = (200, 162, 255)
LILAC_2  = (167, 123, 243)   # lilas foncé (bas du dégradé)
INK      = (20, 15, 31)      # texte sombre sur fond lilas
TEXT     = (236, 232, 245)
MUTED    = (157, 149, 179)
# Bord de la pastille « 8.1 » selon l'enchantement, comme en jeu (.0 neutre, .1 vert, .2 bleu, .3 violet, .4 or)
ENCHANT_COLORS = {0: (157, 149, 179), 1: (92, 201, 112), 2: (88, 160, 255), 3: (184, 120, 255), 4: (255, 200, 80)}

CELL, LABEL_H, GAP, MARGIN, HEADER_H = 128, 22, 14, 28, 96
WIDTH = MARGIN * 2 + CELL * 3 + GAP * 2

# Inter (licence OFL, assets/fonts/OFL.txt) : la police par défaut de Pillow n'a pas les accents.
_FONT_FILE = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Inter.ttf"

ICONS_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"
_ICON_URL ="https://render.albiononline.com/v1/item/T{tier}_{item_id}.png?size=128"
_icon_cache: dict[str, bytes | None] = {}
ICON_CACHE_MAX = 2000             # entrées : vidé au-delà (les ids viennent de la base)
ICON_MAX_BYTES = 2 * 1024 * 1024  # une icône de 128 px fait ~20 Ko : au-delà, réponse ignorée
_ITEM_ID_RE    = re.compile(r"^[A-Z0-9_@]{1,80}$")  # format des ids Albion (ex. 2H_HOLYSTAFF_HELL@2)
_ICON_URL_EXACT = "https://render.albiononline.com/v1/item/{item_id}.png?size=128"
# Tier + enchantement imposés : « T8_MAIN_SWORD@1 » (même règle que catalog.py du site)
_TIERED_RE     = re.compile(r"^T([1-8])_([A-Z0-9_]+?)(?:@([1-4]))?$")
TIER_FREE_SLOTS = ("food", "potion")   # l'enchantement y change l'effet, pas la puissance : pas d'équivalence


def split_tier(item_id: str) -> tuple[str, int | None, int]:
    """« T8_MAIN_SWORD@1 » → ("MAIN_SWORD", 8, 1) ; « MAIN_SWORD » (tier libre) → ("MAIN_SWORD", None, 0)."""
    match = _TIERED_RE.match(item_id or "")
    if not match:
        return item_id, None, 0
    return match.group(2), int(match.group(1)), int(match.group(3) or 0)


def has_tiered_gear(items: dict | str | None) -> bool:
    """Vrai si au moins un équipement (hors bouffe/potion) impose un tier."""
    return any(split_tier(c)[1] is not None
               for slot, choices in normalize_items(items).items() if slot not in TIER_FREE_SLOTS
               for c in choices)


def normalize_items(items: dict | str | None) -> dict[str, list[str]]:
    if isinstance(items, str):  # colonne JSONB lue brute par asyncpg
        items = json.loads(items or "{}")
    out: dict[str, list[str]] = {}
    for slot, value in (items or {}).items():
        choices = [value] if isinstance(value, str) else list(value or [])
        choices = [c for c in choices if c]
        if choices:
            out[slot] = choices
    return out


def item_ids(items: dict | None) -> list[str]:
    """Ids d'objets à télécharger (sans doublon, sans « au choix »)."""
    seen: list[str] = []
    for choices in normalize_items(items).values():
        for c in choices:
            if c != FREE_CHOICE and c not in seen:
                seen.append(c)
    return seen


ICON_REQUEST_TIMEOUT = 8     # s, par requête vers le CDN
ICON_RETRIES         = 2     # tentatives par requête en cas de lenteur / erreur réseau
ICON_CONCURRENCY     = 6     # requêtes simultanées max (le CDN n'aime pas les rafales)
ICONS_DEADLINE       = 40    # s, budget total : au-delà, les icônes manquantes deviennent « ? »


def local_icon(item_id: str) -> bytes | None:
    """Icône embarquée dans le repo (assets/icons/<ID>.png, cf. scripts/download_icons.py)."""
    if not item_id or "/" in item_id or "\\" in item_id or ".." in item_id:
        return None
    path = ICONS_DIR / f"{item_id}.png"
    try:
        return path.read_bytes()
    except OSError:
        return None


async def _get_icon(session: aiohttp.ClientSession, url: str) -> tuple[bool, bytes | None]:
    """(réponse sûre, contenu). Réponse sûre = 200 (contenu) ou 404 (None) ;
    sinon (lenteur, erreur réseau, 5xx) on renvoie (False, None) après les tentatives."""
    for _ in range(ICON_RETRIES):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=ICON_REQUEST_TIMEOUT)) as resp:
                if resp.status == 200:
                    # read(n) rend ce qui est déjà arrivé (au plus n octets), pas tout le corps :
                    # on lit jusqu'à la fin, en abandonnant au-delà de ICON_MAX_BYTES.
                    chunks, size = [], 0
                    while chunk := await resp.content.read(64 * 1024):
                        size += len(chunk)
                        if size > ICON_MAX_BYTES:
                            return True, None
                        chunks.append(chunk)
                    return True, b"".join(chunks)
                if resp.status == 404:
                    return True, None
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass
    return False, None


async def fetch_icon(session: aiohttp.ClientSession, item_id: str) -> bytes | None:
    """Icône officielle : on part du tier 8 et on descend (la bouffe/les potions
    n'existent pas à tous les tiers). Seules les réponses sûres sont mises en cache :
    une lenteur passagère du CDN ne doit pas marquer l'icône comme absente."""
    if item_id in _icon_cache:
        return _icon_cache[item_id]
    if not _ITEM_ID_RE.match(item_id or ""):
        return None
    if len(_icon_cache) >= ICON_CACHE_MAX:
        _icon_cache.clear()
    base, tier, _ = split_tier(item_id)
    if tier is not None:   # tier imposé : icône exacte (chiffre du tier, lueur d'enchantement), sinon celle de base
        sure, data = await _get_icon(session, _ICON_URL_EXACT.format(item_id=item_id))
        if not sure:
            return None
        if data is not None:
            _icon_cache[item_id] = data
            return data
    local = local_icon(base)
    if local is not None:
        _icon_cache[item_id] = local
        return local
    for t in range(8, 0, -1):
        sure, data = await _get_icon(session, _ICON_URL.format(tier=t, item_id=base))
        if not sure:
            return None
        if data is not None:
            _icon_cache[item_id] = data
            return data
    _icon_cache[item_id] = None
    return None


async def fetch_icons(items: dict | None, extra_ids: list[str] | None = None) -> dict[str, bytes | None]:
    """Télécharge les icônes en parallèle (limité). Ne lève jamais d'erreur réseau :
    une icône en échec ou hors délai vaut None (dessinée « ? »)."""
    ids = item_ids(items)
    for i in extra_ids or []:
        if i not in ids:
            ids.append(i)
    if not ids:
        return {}
    sem = asyncio.Semaphore(ICON_CONCURRENCY)

    async def one(session, item_id):
        async with sem:
            return await fetch_icon(session, item_id)

    async with aiohttp.ClientSession() as session:
        tasks = {asyncio.ensure_future(one(session, i)): i for i in ids}
        done, pending = await asyncio.wait(tasks, timeout=ICONS_DEADLINE)
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    icons = {i: None for i in ids}
    for t in done:
        if not t.cancelled() and t.exception() is None:
            icons[tasks[t]] = t.result()
    return icons


@lru_cache(maxsize=32)
def _font(size: int, weight: str = "Regular") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        font = ImageFont.truetype(str(_FONT_FILE), size)
        font.set_variation_by_name(weight)
        return font
    except (OSError, ValueError):
        return ImageFont.load_default(size=size)


def _open_icon(data: bytes | None, size: int) -> Image.Image | None:
    if not data:
        return None
    try:
        return Image.open(io.BytesIO(data)).convert("RGBA").resize((size, size), Image.LANCZOS)
    except Exception:
        return None


def fit_text(text: str, font, max_width: float) -> str:
    """Raccourcit le texte (avec « … ») pour qu'il tienne en `max_width` pixels,
    en coupant de préférence entre deux mots."""
    if font.getlength(text) <= max_width:
        return text
    words = text.split()
    while len(words) > 1:
        words.pop()
        candidate = " ".join(words) + "…"
        if font.getlength(candidate) <= max_width:
            return candidate
    while text and font.getlength(text + "…") > max_width:   # un seul mot trop long
        text = text[:-1]
    return text + "…"


def _centered_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, font, fill) -> None:
    x0, y0, x1, y1 = box
    w = draw.textlength(text, font=font)
    draw.text((x0 + (x1 - x0 - w) / 2, y0 + (y1 - y0 - font.size) / 2), text, font=font, fill=fill)


def _draw_tier_badge(draw: ImageDraw.ImageDraw, x: int, bottom: int, item_id: str, size: int = 13) -> None:
    """Pastille « 8.1 » posée au coin bas-gauche d'une icône (x, bottom) ; rien si le tier est libre."""
    _, tier, enchant = split_tier(item_id)
    if tier is None:
        return
    text, font = f"{tier}.{enchant}", _font(size, "Bold")
    pad, h = 4, size + 6
    w = draw.textlength(text, font=font) + 2 * pad
    draw.rounded_rectangle((x, bottom - h, x + w, bottom), radius=h // 2, fill=BG,
                           outline=ENCHANT_COLORS.get(enchant, MUTED), width=2)
    draw.text((x + pad, bottom - h + (h - size) / 2 - 1), text, font=font, fill=TEXT)


def _draw_cell(img: Image.Image, draw: ImageDraw.ImageDraw, x: int, y: int,
               slot: str, choices: list[str], icons: dict[str, bytes | None]) -> None:
    filled = bool(choices)
    draw.rounded_rectangle((x, y, x + CELL, y + CELL), radius=14,
                           fill=SURFACE, outline=LILAC if filled else BORDER, width=2 if filled else 1)
    _centered_text(draw, (x, y + CELL + 2, x + CELL, y + CELL + LABEL_H), SLOT_LABELS[slot], _font(14), MUTED)

    if not filled:
        return
    if choices == [FREE_CHOICE]:
        _centered_text(draw, (x, y, x + CELL, y + CELL), "Au choix", _font(20, "SemiBold"), LILAC)
        return

    n = len(choices)
    size = {1: 112, 2: 58, 3: 40}.get(n, 40)
    total_w = size * n + 4 * (n - 1)
    start_x = x + (CELL - total_w) // 2
    top = y + (CELL - size) // 2
    for i, item_id in enumerate(choices[:3]):
        ix = start_x + i * (size + 4)
        icon = _open_icon(icons.get(item_id), size)
        if icon:
            img.paste(icon, (ix, top), icon)
        else:
            _centered_text(draw, (ix, top, ix + size, top + size), "?", _font(size // 2), LILAC)
        _draw_tier_badge(draw, ix + 2, top + size - 2, item_id, 14 if n == 1 else 11)
    if n > 1:
        _centered_text(draw, (x, y + CELL - 22, x + CELL, y + CELL - 4), f"{n} au choix", _font(13, "SemiBold"), LILAC)


SWAPS_KEY = "swaps"     # dans items : objets de rechange (n'importe quel emplacement)
SWAPS_MAX = 6
SWAP_CELL, SWAP_GAP = 64, 8


def _draw_swaps_column(img: Image.Image, draw: ImageDraw.ImageDraw, x: int, top: int,
                       swaps: list[str], icons: dict[str, bytes | None]) -> None:
    """Colonne « Swaps » à droite de la grille : une petite case par objet de rechange."""
    draw.text((x, top - 26), "Swaps", font=_font(14, "SemiBold"), fill=MUTED)
    for i, item_id in enumerate(swaps):
        y = top + i * (SWAP_CELL + SWAP_GAP)
        draw.rounded_rectangle((x, y, x + SWAP_CELL, y + SWAP_CELL), radius=10, fill=SURFACE, outline=LILAC, width=2)
        icon = _open_icon(icons.get(item_id), SWAP_CELL - 8)
        if icon:
            img.paste(icon, (x + 4, y + 4), icon)
        else:
            _centered_text(draw, (x, y, x + SWAP_CELL, y + SWAP_CELL), "?", _font(24), LILAC)
        _draw_tier_badge(draw, x + 3, y + SWAP_CELL - 3, item_id, 11)


def render_build_image(build: dict, icons: dict[str, bytes | None]) -> bytes:
    """PNG du build : titre, rôle, grille façon inventaire (+ colonne Swaps à droite), précisions en bas."""
    items = normalize_items(build.get("items"))
    swaps = [s for s in items.pop(SWAPS_KEY, []) if s != FREE_CHOICE][:SWAPS_MAX]
    footer = [t for t in (build.get("weapon", ""), build.get("notes", "")) if t and t.strip()]
    footer_lines: list[str] = []
    for block in footer:
        for para in block.strip().splitlines():
            footer_lines.extend(textwrap.wrap(para, width=52) or [""])
    footer_lines = footer_lines[:8]

    grid_h = 3 * (CELL + LABEL_H) + 2 * GAP
    footer_h = (len(footer_lines) * 22 + 24) if footer_lines else 0
    height = HEADER_H + grid_h + footer_h + MARGIN

    width = WIDTH + (SWAP_CELL + GAP) if swaps else WIDTH
    img = Image.new("RGBA", (width, height), BG)
    draw = ImageDraw.Draw(img)
    title_font = _font(30, "Bold")
    draw.text((MARGIN, 22), fit_text(build.get("name") or "Build", title_font, width - 2 * MARGIN),
              font=title_font, fill=LILAC)
    subtitle = " · ".join(t for t in (build.get("role", ""), build.get("type_acti", "")) if t)
    draw.text((MARGIN, 60), subtitle, font=_font(18), fill=MUTED)

    for r, row in enumerate(LAYOUT):
        for c, slot in enumerate(row):
            if slot is None:
                continue
            x = MARGIN + c * (CELL + GAP)
            y = HEADER_H + r * (CELL + LABEL_H + GAP)
            _draw_cell(img, draw, x, y, slot, items.get(slot, []), icons)

    if swaps:
        _draw_swaps_column(img, draw, WIDTH - MARGIN + GAP, HEADER_H + 22, swaps, icons)

    y = HEADER_H + grid_h + 16
    for line in footer_lines:
        draw.text((MARGIN, y), line, font=_font(16), fill=TEXT)
        y += 22

    out = io.BytesIO()
    img.convert("RGB").save(out, format="PNG")
    return out.getvalue()


async def build_image(build: dict) -> bytes:
    """Télécharge les icônes du build puis génère l'image."""
    return render_build_image(build, await fetch_icons(build.get("items")))


# ══════════════════════════════════════════════════════════════════════════════
# IMAGE DE LA COMPO (postée par /acti juste après l'embed)
# ══════════════════════════════════════════════════════════════════════════════
COMPO_SLOTS = ("mainhand", "offhand", "head", "armor", "shoes", "cape", "food", "potion")
C_ICON, C_ICON_GAP, C_ROW_H, C_LEFT = 52, 6, 76, 250
C_HEADER = 56  # hauteur de l'en-tête (« N joueurs · M builds »)
C_MINI = 22  # mini-icône d'un choix alternatif (coin bas-droit de la case)
COMPO_WIDTH = MARGIN * 2 + C_LEFT + len(COMPO_SLOTS) * (C_ICON + C_ICON_GAP)


ROLE_ORDER = ("TANK", "HEAL", "DPS", "SUPPORT")


def _role_rank(role: str) -> int:
    """Ordre TANK, HEAL, DPS, SUPPORT puis le reste ; « TANK · Main tank » se range avec TANK."""
    base = role.split(" · ", 1)[0].strip()
    unnumbered = re.sub(r" \d+$", "", base)          # « TANK 2 » (ligne libre en double)
    if unnumbered in ROLE_ORDER:
        base = unnumbered
    return ROLE_ORDER.index(base) if base in ROLE_ORDER else len(ROLE_ORDER)


def compo_rows(template_data: dict) -> list[tuple[str, str, int, int]]:
    """[(party, rôle, nombre, build_id), ...] pour les rôles de la compo qui ont un build.
    PF1 puis PF2 ; dans chaque party, regroupés par rôle : TANK, HEAL, DPS, SUPPORT, puis le reste."""
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
        rows.extend(sorted(party_rows, key=lambda r: _role_rank(r[1])))   # tri stable
    return rows


def _lilac_background(width: int, height: int) -> Image.Image:
    """Dégradé vertical lilas clair → lilas foncé."""
    img = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / max(height - 1, 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(LILAC, LILAC_2))
        draw.line([(0, y), (width, y)], fill=color)
    return img


def _draw_small_slot(img: Image.Image, draw: ImageDraw.ImageDraw, x: int, y: int,
                     choices: list[str], icons: dict[str, bytes | None]) -> None:
    draw.rounded_rectangle((x, y, x + C_ICON, y + C_ICON), radius=8, fill=SURFACE)
    if not choices:
        return
    if choices == [FREE_CHOICE]:
        mid = y + C_ICON // 2
        _centered_text(draw, (x, mid - 15, x + C_ICON, mid), "Au", _font(12, "Bold"), LILAC)
        _centered_text(draw, (x, mid - 1, x + C_ICON, mid + 14), "choix", _font(12, "Bold"), LILAC)
        return
    icon = _open_icon(icons.get(choices[0]), C_ICON)
    if icon:
        img.paste(icon, (x, y), icon)
    else:
        _centered_text(draw, (x, y, x + C_ICON, y + C_ICON), "?", _font(24, "Bold"), LILAC)
    # En haut à gauche (sur le chiffre du tier) : le bas est pris par les mini-icônes des autres choix
    _draw_tier_badge(draw, x + 1, y + 17, choices[0], 10)
    # Autres choix possibles : mini-icônes cerclées de lilas dans le coin bas-droit.
    by = y + C_ICON - C_MINI + 4
    for i, alt in enumerate(choices[1:]):
        bx = x + C_ICON - C_MINI + 4 - i * (C_MINI + 2)
        draw.rounded_rectangle((bx - 1, by - 1, bx + C_MINI + 1, by + C_MINI + 1), radius=6, fill=SURFACE, outline=LILAC, width=2)
        mini = _open_icon(icons.get(alt), C_MINI)
        if mini:
            img.paste(mini, (bx, by), mini)
        else:
            _centered_text(draw, (bx, by, bx + C_MINI, by + C_MINI), "?", _font(12, "Bold"), LILAC)


COMPO_MAX_ROWS = 40  # la hauteur de l'image suit le nombre de lignes : au-delà, mémoire (image de plusieurs Go)

# Couleur d'accent par build (lisibles sur la carte sombre) : bande, contour, rôle et fond teinté.
BUILD_COLORS = (
    (200, 162, 255),  # lilas
    (94, 214, 196),   # turquoise
    (255, 186, 92),   # ambre
    (255, 122, 138),  # corail
    (110, 176, 255),  # bleu ciel
    (140, 220, 100),  # vert
    (255, 130, 210),  # rose
    (255, 150, 80),   # orange
    (225, 225, 110),  # jaune
    (150, 140, 255),  # pervenche
)


def build_colors(builds: list[dict]) -> list[tuple[int, int, int]]:
    """Couleur de chaque ligne : une par build distinct, dans l'ordre d'apparition (en boucle
    au-delà de la palette). Un même build en Party 1 et Party 2 garde sa couleur."""
    assigned: dict = {}
    colors = []
    for build in builds:
        key = build.get("id", build.get("name"))
        if key not in assigned:
            assigned[key] = BUILD_COLORS[len(assigned) % len(BUILD_COLORS)]
        colors.append(assigned[key])
    return colors


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def render_compo_image(name: str, rows: list[tuple[str, str, int, dict]], icons: dict[str, bytes | None]) -> bytes:
    """rows = [(party, rôle, nombre, build)] → PNG : fond lilas, une carte sombre par build
    (rôle × nombre, nom du build, icônes des 8 emplacements), une couleur d'accent par build.
    Au plus COMPO_MAX_ROWS lignes."""
    rows = rows[:COMPO_MAX_ROWS]
    accents = build_colors([r[3] for r in rows])
    max_swaps = max((len(normalize_items(r[3].get("items")).get(SWAPS_KEY, [])[:SWAPS_MAX]) for r in rows), default=0)
    width = COMPO_WIDTH + (14 + max_swaps * (C_ICON + C_ICON_GAP) if max_swaps else 0)
    parties = list(dict.fromkeys(r[0] for r in rows))
    multi_party = len(parties) > 1
    height = C_HEADER + len(rows) * (C_ROW_H + 10) + (len(parties) * 34 if multi_party else 0) + MARGIN
    img = _lilac_background(width, height)
    draw = ImageDraw.Draw(img)

    # Pas de titre : le nom de l'acti est déjà dans l'embed juste au-dessus.
    total = sum(r[2] for r in rows)
    draw.text((MARGIN, 20), f"{total} joueurs · {len(rows)} builds", font=_font(17, "Bold"), fill=INK)

    y = C_HEADER
    for party in parties:
        if multi_party:
            draw.text((MARGIN, y), party.upper(), font=_font(16, "Bold"), fill=INK)
            y += 34
        for (row_party, role, count, build), accent in zip(rows, accents):
            if row_party != party:
                continue
            draw.rounded_rectangle((MARGIN, y, width - MARGIN, y + C_ROW_H), radius=14,
                                   fill=_mix(BG, accent, .10), outline=_mix(BG, accent, .55), width=2)
            draw.rounded_rectangle((MARGIN + 10, y + 12, MARGIN + 15, y + C_ROW_H - 12), radius=3, fill=accent)
            # Rôle et nom du build : tout l'espace avant les icônes, coupés proprement avec « … »
            text_w = C_LEFT - 26 - 12
            draw.text((MARGIN + 26, y + 12), fit_text(f"{role}  ×{count}", _font(20, "Bold"), text_w),
                      font=_font(20, "Bold"), fill=accent)
            draw.text((MARGIN + 26, y + 42), fit_text(build.get("name") or "", _font(16), text_w),
                      font=_font(16), fill=TEXT)
            items = normalize_items(build.get("items"))
            ix = MARGIN + C_LEFT
            for slot in COMPO_SLOTS:
                _draw_small_slot(img, draw, ix, y + (C_ROW_H - C_ICON) // 2, items.get(slot, []), icons)
                ix += C_ICON + C_ICON_GAP
            swaps = [s for s in items.get(SWAPS_KEY, []) if s != FREE_CHOICE][:SWAPS_MAX]
            if swaps:   # swaps à droite des 8 cases, après un trait de la couleur du build
                draw.line((ix + 4, y + 14, ix + 4, y + C_ROW_H - 14), fill=accent, width=2)
                ix += 14
                for item_id in swaps:
                    _draw_small_slot(img, draw, ix, y + (C_ROW_H - C_ICON) // 2, [item_id], icons)
                    ix += C_ICON + C_ICON_GAP
            y += C_ROW_H + 10

    out = io.BytesIO()
    img.convert("RGB").save(out, format="PNG")
    return out.getvalue()


async def compo_image(name: str, template_data: dict, builds_by_id: dict[int, dict]) -> bytes | None:
    """Image de la compo, ou None si aucun de ses rôles n'a de build."""
    rows = [(party, role, count, builds_by_id[bid])
            for party, role, count, bid in compo_rows(template_data) if bid in builds_by_id]
    if not rows:
        return None
    ids: list[str] = []
    for *_, build in rows:
        ids.extend(i for i in item_ids(build.get("items")) if i not in ids)
    icons = await fetch_icons(None, ids)
    return render_compo_image(name, rows, icons)
