import io

from PIL import Image

from Service.activites import build_id_for_role
from Service.build_image import WIDTH, item_ids, normalize_items, render_build_image
from Service.massup import build_recipients, dm_summary


def _png(color=(200, 0, 0)) -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", (128, 128), color).save(out, format="PNG")
    return out.getvalue()


def _open(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


TEMPLATE = {
    "pf_1": {"TANK": 1, "HEAL": 2, "CALLER": 1},
    "builds": {"TANK": 12, "HEAL": "15"},
    "pf_2": {"DPS": 3},
    "builds_pf2": {"DPS": 20},
}


# ── build_id_for_role ────────────────────────────────────────────────────────

def test_build_id_for_role_pf1_pf2_and_missing():
    assert build_id_for_role(TEMPLATE, "TANK") == 12
    assert build_id_for_role(TEMPLATE, "HEAL") == 15      # id stocké en texte → int
    assert build_id_for_role(TEMPLATE, "PF2:DPS") == 20
    assert build_id_for_role(TEMPLATE, "CALLER") is None
    assert build_id_for_role(TEMPLATE, "DPS") is None      # DPS n'a un build qu'en PF2
    assert build_id_for_role({}, "TANK") is None


# ── build_recipients / dm_summary (/massup) ──────────────────────────────────

def test_build_recipients_groups_players_by_build():
    slots = {
        "TANK": [(1, "A", "Tank Masse (700)")],
        "HEAL": [(2, "B", ""), (3, "C", "")],
        "CALLER": [(4, "D", "")],
        "PF2:DPS": [(5, "E", "")],
        "Fill": [(6, "F", "")],
    }
    assert build_recipients(slots, TEMPLATE) == {
        12: [(1, "TANK")],
        15: [(2, "HEAL"), (3, "HEAL")],
        20: [(5, "DPS (PF2)")],
    }


def test_build_recipients_without_builds_is_empty():
    assert build_recipients({"TANK": [(1, "A", "")]}, {"pf_1": {"TANK": 1}}) == {}


def test_dm_summary():
    assert dm_summary(0, []) is None
    assert dm_summary(3, []) == "✉️ 3 build(s) envoyé(s) en MP."
    assert "<@7> <@8>" in dm_summary(1, [7, 8])


# ── normalize_items / item_ids ───────────────────────────────────────────────

def test_normalize_items_accepts_old_format_and_json_string():
    assert normalize_items({"mainhand": "MAIN_SWORD", "head": [], "cape": ["*"]}) == {
        "mainhand": ["MAIN_SWORD"], "cape": ["*"],
    }
    assert normalize_items('{"head": ["HEAD_PLATE_SET1"]}') == {"head": ["HEAD_PLATE_SET1"]}
    assert normalize_items(None) == {}


def test_item_ids_skips_free_choice_and_duplicates():
    items = {"mainhand": ["A", "B"], "offhand": ["A"], "cape": ["*"]}
    assert item_ids(items) == ["A", "B"]


# ── render_build_image ───────────────────────────────────────────────────────

BUILD = {
    "name": "Heal Sacré", "role": "HEAL", "type_acti": "PVP",
    "items": {"mainhand": ["2H_HOLYSTAFF", "2H_HOLYSTAFF_HELL"], "head": ["HEAD_CLOTH_SET2"],
              "cape": ["*"], "food": ["MEAL_STEW"]},
    "weapon": "", "notes": "",
}


def test_render_produces_png_with_expected_width():
    icons = {i: _png() for i in item_ids(BUILD["items"])}
    img = _open(render_build_image(BUILD, icons))
    assert img.format == "PNG"
    assert img.width == WIDTH


def test_render_grows_with_notes():
    icons = {i: _png() for i in item_ids(BUILD["items"])}
    short = _open(render_build_image(BUILD, icons))
    long = _open(render_build_image({**BUILD, "notes": "Ligne\n" * 5, "weapon": "Tier 8"}, icons))
    assert long.height > short.height


def test_render_tolerates_missing_or_broken_icons_and_empty_build():
    icons = {"2H_HOLYSTAFF": None, "HEAD_CLOTH_SET2": b"pas une image"}
    assert _open(render_build_image(BUILD, icons)).width == WIDTH
    assert _open(render_build_image({"name": "Vide", "items": {}}, {})).width == WIDTH


def test_render_draws_icon_pixels():
    """L'icône (rouge) doit apparaître dans l'image finale."""
    build = {"name": "X", "items": {"armor": ["ARMOR_X"]}}
    img = _open(render_build_image(build, {"ARMOR_X": _png((255, 0, 0))})).convert("RGB")
    assert (255, 0, 0) in {img.getpixel((x, y)) for x in range(0, img.width, 4) for y in range(0, img.height, 4)}


# ── Image de la compo (/acti) ────────────────────────────────────────────────

from Service.build_image import COMPO_WIDTH, LILAC, compo_rows, render_compo_image  # noqa: E402


def test_compo_rows_lists_only_roles_with_builds_in_party_order():
    assert compo_rows(TEMPLATE) == [
        ("Party 1", "TANK", 1, 12),
        ("Party 1", "HEAL", 2, 15),
        ("Party 2", "DPS", 3, 20),
    ]
    assert compo_rows({"pf_1": {"TANK": 1}}) == []


def test_compo_rows_grouped_by_role_inside_each_party():
    template = {
        "pf_1": {"SUPPORT": 1, "DPS": 3, "TANK": 1, "HEAL": 2},
        "builds": {"SUPPORT": 4, "DPS": 3, "TANK": 1, "HEAL": 2},
        "pf_2": {"DPS": 2, "TANK": 1},
        "builds_pf2": {"DPS": 6, "TANK": 5},
    }
    assert [(p, r) for p, r, _, _ in compo_rows(template)] == [
        ("Party 1", "TANK"), ("Party 1", "HEAL"), ("Party 1", "DPS"), ("Party 1", "SUPPORT"),
        ("Party 2", "TANK"), ("Party 2", "DPS"),
    ]


def _compo_rows(n_pf2=0):
    build = {"name": "Tank Masse", "items": {"mainhand": ["A", "B"], "cape": ["*"]}}
    rows = [("Party 1", "TANK", 2, build), ("Party 1", "HEAL", 1, {"name": "Heal", "items": {}})]
    rows += [("Party 2", "DPS", 3, build)] * n_pf2
    return rows


def test_render_compo_image_size_and_lilac_background():
    img = _open(render_compo_image("Traque", _compo_rows(), {"A": _png(), "B": None}))
    assert img.format == "PNG"
    assert img.width == COMPO_WIDTH
    assert img.convert("RGB").getpixel((2, 2)) == LILAC  # haut du dégradé = lilas clair


def test_render_compo_image_draws_alternative_choices_as_mini_icons():
    """Les choix alternatifs (2e, 3e objet) apparaissent en mini-icônes, pas en « +N »."""
    build = {"name": "B", "items": {"mainhand": ["MAIN", "ALT"]}}
    icons = {"MAIN": _png((255, 0, 0)), "ALT": _png((0, 0, 255))}
    img = _open(render_compo_image("X", [("Party 1", "DPS", 1, build)], icons)).convert("RGB")
    pixels = {img.getpixel((x, y)) for x in range(0, img.width, 2) for y in range(0, img.height, 2)}
    assert (0, 0, 255) in pixels and (255, 0, 0) in pixels


def test_fit_text_cuts_between_words_with_ellipsis():
    from Service.build_image import _font, fit_text
    font = _font(16)
    assert fit_text("Tank", font, 200) == "Tank"
    cut = fit_text("Tank build numéro onze avec un nom vraiment très long", font, 200)
    assert cut.endswith("…") and font.getlength(cut) <= 200
    assert not cut[:-1].endswith(" ")                        # coupé entre deux mots
    assert "Tank build numéro onze avec un nom vraiment très long".startswith(cut[:-1])
    one_word = fit_text("Supercalifragilisticexpialidocious" * 3, font, 120)
    assert one_word.endswith("…") and font.getlength(one_word) <= 120


def test_render_compo_image_with_twenty_builds():
    """Grosse compo : 20 builds sur 2 parties, noms longs — l'image reste légère et lisible."""
    build = {"name": "Build avec un nom beaucoup trop long pour la carte", "items": {"mainhand": ["A", "B", "C"], "cape": ["*"]}}
    rows = [("Party 1" if i < 10 else "Party 2", f"ROLE{i}", 5, build) for i in range(20)]
    data = render_compo_image("ZvZ", rows, {"A": _png(), "B": _png(), "C": None})
    img = _open(data)
    assert img.width == COMPO_WIDTH
    assert img.height > 20 * 76
    assert len(data) < 8 * 1024 * 1024                      # largement sous la limite d'envoi Discord


def test_render_compo_image_grows_with_rows_and_second_party():
    one = _open(render_compo_image("X", _compo_rows(), {}))
    two = _open(render_compo_image("X", _compo_rows(n_pf2=1), {}))
    assert two.height > one.height


def test_render_compo_image_height_is_capped():
    """Une compo géante (5 000 lignes) ne doit pas produire une image de plusieurs Go."""
    from Service.build_image import COMPO_MAX_ROWS
    capped = _open(render_compo_image("X", _compo_rows(n_pf2=COMPO_MAX_ROWS), {}))
    huge = _open(render_compo_image("X", _compo_rows(n_pf2=5000), {}))
    assert huge.height == capped.height
