"""
Service/build_image.py — Image PNG d'un build (envoyée en MP par /massup).

Un build vient du site lilium-site (table builds, colonne items) :
    {"mainhand": ["2H_HOLYSTAFF", "2H_HOLYSTAFF_HELL"], "cape": ["*"], "food": ["MEAL_STEW"], ...}
chaque case = 1 à 3 objets au choix, ["*"] = au choix du joueur. L'ancien
format {"mainhand": "ID"} est aussi accepté.

L'image reprend la disposition de l'inventaire du jeu (grille 3×3) avec les
icônes officielles d'Albion. Le rendu (render_build_image) est une fonction
pure qui reçoit les icônes déjà téléchargées → testable sans réseau.
"""
import asyncio
import io
import json
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

CELL, LABEL_H, GAP, MARGIN, HEADER_H = 128, 22, 14, 28, 96
WIDTH = MARGIN * 2 + CELL * 3 + GAP * 2

# Inter (licence OFL, assets/fonts/OFL.txt) : la police par défaut de Pillow n'a pas les accents.
_FONT_FILE = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Inter.ttf"

_ICON_URL = "https://render.albiononline.com/v1/item/T{tier}_{item_id}.png?size=128"
_icon_cache: dict[str, bytes | None] = {}


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


async def fetch_icon(session: aiohttp.ClientSession, item_id: str) -> bytes | None:
    """Icône officielle : on part du tier 8 et on descend (la bouffe/les potions
    n'existent pas à tous les tiers). Résultat mis en cache (y compris l'absence)."""
    if item_id in _icon_cache:
        return _icon_cache[item_id]
    data = None
    for tier in range(8, 0, -1):
        try:
            async with session.get(_ICON_URL.format(tier=tier, item_id=item_id)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    break
        except aiohttp.ClientError:
            break
    _icon_cache[item_id] = data
    return data


async def fetch_icons(items: dict | None, extra_ids: list[str] | None = None) -> dict[str, bytes | None]:
    ids = item_ids(items)
    for i in extra_ids or []:
        if i not in ids:
            ids.append(i)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        results = await asyncio.gather(*(fetch_icon(session, i) for i in ids))
    return dict(zip(ids, results))


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


def _centered_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, font, fill) -> None:
    x0, y0, x1, y1 = box
    w = draw.textlength(text, font=font)
    draw.text((x0 + (x1 - x0 - w) / 2, y0 + (y1 - y0 - font.size) / 2), text, font=font, fill=fill)


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
    if n > 1:
        _centered_text(draw, (x, y + CELL - 22, x + CELL, y + CELL - 4), f"{n} au choix", _font(13, "SemiBold"), LILAC)


def render_build_image(build: dict, icons: dict[str, bytes | None]) -> bytes:
    """PNG du build : titre, rôle, grille façon inventaire, précisions en bas."""
    items = normalize_items(build.get("items"))
    footer = [t for t in (build.get("weapon", ""), build.get("notes", "")) if t and t.strip()]
    footer_lines: list[str] = []
    for block in footer:
        for para in block.strip().splitlines():
            footer_lines.extend(textwrap.wrap(para, width=52) or [""])
    footer_lines = footer_lines[:8]

    grid_h = 3 * (CELL + LABEL_H) + 2 * GAP
    footer_h = (len(footer_lines) * 22 + 24) if footer_lines else 0
    height = HEADER_H + grid_h + footer_h + MARGIN

    img = Image.new("RGBA", (WIDTH, height), BG)
    draw = ImageDraw.Draw(img)
    draw.text((MARGIN, 22), (build.get("name") or "Build")[:40], font=_font(30, "Bold"), fill=LILAC)
    subtitle = " · ".join(t for t in (build.get("role", ""), build.get("type_acti", "")) if t)
    draw.text((MARGIN, 60), subtitle, font=_font(18), fill=MUTED)

    for r, row in enumerate(LAYOUT):
        for c, slot in enumerate(row):
            if slot is None:
                continue
            x = MARGIN + c * (CELL + GAP)
            y = HEADER_H + r * (CELL + LABEL_H + GAP)
            _draw_cell(img, draw, x, y, slot, items.get(slot, []), icons)

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
COMPO_WIDTH = MARGIN * 2 + C_LEFT + len(COMPO_SLOTS) * (C_ICON + C_ICON_GAP)


def compo_rows(template_data: dict) -> list[tuple[str, str, int, int]]:
    """[(party, rôle, nombre, build_id), ...] pour les rôles de la compo qui ont un build."""
    rows = []
    for party, count_key, builds_key in (("Party 1", "pf_1", "builds"), ("Party 2", "pf_2", "builds_pf2")):
        builds = template_data.get(builds_key) or {}
        for role, count in (template_data.get(count_key) or {}).items():
            if builds.get(role) is not None:
                rows.append((party, role, int(count), int(builds[role])))
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
        _centered_text(draw, (x, y, x + C_ICON, y + C_ICON), "?", _font(24, "Bold"), LILAC)
        return
    icon = _open_icon(icons.get(choices[0]), C_ICON)
    if icon:
        img.paste(icon, (x, y), icon)
    else:
        _centered_text(draw, (x, y, x + C_ICON, y + C_ICON), "?", _font(24, "Bold"), LILAC)
    if len(choices) > 1:  # alternatives : pastille « +N »
        bx, by = x + C_ICON - 20, y + C_ICON - 16
        draw.rounded_rectangle((bx, by, bx + 22, by + 16), radius=8, fill=LILAC)
        _centered_text(draw, (bx, by, bx + 22, by + 16), f"+{len(choices) - 1}", _font(11, "Bold"), INK)


def render_compo_image(name: str, rows: list[tuple[str, str, int, dict]], icons: dict[str, bytes | None]) -> bytes:
    """rows = [(party, rôle, nombre, build)] → PNG : fond lilas, une carte sombre par build
    (rôle × nombre, nom du build, icônes des 8 emplacements)."""
    parties = list(dict.fromkeys(r[0] for r in rows))
    multi_party = len(parties) > 1
    height = 110 + len(rows) * (C_ROW_H + 10) + (len(parties) * 34 if multi_party else 0) + MARGIN
    img = _lilac_background(COMPO_WIDTH, height)
    draw = ImageDraw.Draw(img)

    total = sum(r[2] for r in rows)
    draw.text((MARGIN, 24), name[:40], font=_font(34, "Bold"), fill=INK)
    draw.text((MARGIN, 68), f"{total} joueurs · {len(rows)} builds", font=_font(17, "Medium"), fill=INK)

    y = 110
    for party in parties:
        if multi_party:
            draw.text((MARGIN, y), party.upper(), font=_font(16, "Bold"), fill=INK)
            y += 34
        for _, role, count, build in (r for r in rows if r[0] == party):
            draw.rounded_rectangle((MARGIN, y, COMPO_WIDTH - MARGIN, y + C_ROW_H), radius=14, fill=BG)
            draw.text((MARGIN + 18, y + 12), f"{role}  ×{count}", font=_font(20, "Bold"), fill=LILAC)
            draw.text((MARGIN + 18, y + 42), (build.get("name") or "")[:26], font=_font(16), fill=TEXT)
            items = normalize_items(build.get("items"))
            ix = MARGIN + C_LEFT
            for slot in COMPO_SLOTS:
                _draw_small_slot(img, draw, ix, y + (C_ROW_H - C_ICON) // 2, items.get(slot, []), icons)
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
