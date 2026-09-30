"""Image de la compo postée par /acti : _post_compo_image, compo_image, fetch_icons.
Aucun appel réseau ni base : Discord, la base et le CDN sont remplacés par des faux."""
import asyncio
import io
from types import SimpleNamespace

from PIL import Image

import db
from Service import activites, build_image

TEMPLATE = {
    "pf_1": {"TANK": 1, "HEAL": 2, "CALLER": 1},
    "builds": {"TANK": 12, "HEAL": 15},
    "pf_2": {"DPS": 3},
    "builds_pf2": {"DPS": 20},
}
BUILDS = {
    12: {"id": 12, "name": "Tank Masse", "role": "TANK", "items": {"mainhand": ["MAIN_MACE"], "cape": ["*"]}},
    15: {"id": 15, "name": "Heal Sacré", "role": "HEAL", "items": '{"mainhand": ["2H_HOLYSTAFF", "MAIN_HOLYSTAFF"]}'},
    20: {"id": 20, "name": "DPS Arc", "role": "DPS", "items": {}},
}


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", (64, 64), (0, 200, 0)).save(out, format="PNG")
    return out.getvalue()


def _fake_interaction():
    sent = []

    async def send(**kwargs):
        sent.append(kwargs)

    inter = SimpleNamespace(
        guild=SimpleNamespace(id=111),
        user=SimpleNamespace(id=1),
        followup=SimpleNamespace(send=send),
    )
    return inter, sent


def _fake_fetch_icons(calls):
    async def fetch_icons(items, extra_ids=None):
        calls.append(list(extra_ids or []))
        return {i: _png() for i in extra_ids or []}
    return fetch_icons


# ── compo_image ──────────────────────────────────────────────────────────────

def test_compo_image_none_without_builds(monkeypatch):
    monkeypatch.setattr(build_image, "fetch_icons", _fake_fetch_icons([]))
    assert asyncio.run(build_image.compo_image("X", {"pf_1": {"TANK": 1}}, {})) is None


def test_compo_image_ignores_deleted_builds(monkeypatch):
    """Build supprimé côté site : sa ligne est simplement absente de l'image."""
    monkeypatch.setattr(build_image, "fetch_icons", _fake_fetch_icons([]))
    only_tank = {12: BUILDS[12]}
    png = asyncio.run(build_image.compo_image("Traque", TEMPLATE, only_tank))
    full = asyncio.run(build_image.compo_image("Traque", TEMPLATE, BUILDS))
    assert Image.open(io.BytesIO(png)).height < Image.open(io.BytesIO(full)).height


def test_compo_image_fetches_each_icon_once_across_builds(monkeypatch):
    calls = []
    monkeypatch.setattr(build_image, "fetch_icons", _fake_fetch_icons(calls))
    builds = {**BUILDS, 20: {**BUILDS[20], "items": {"mainhand": ["MAIN_MACE"]}}}  # même arme que le tank
    asyncio.run(build_image.compo_image("Traque", TEMPLATE, builds))
    assert calls == [["MAIN_MACE", "2H_HOLYSTAFF", "MAIN_HOLYSTAFF"]]


# ── fetch_icons (fusion des ids, sans réseau) ────────────────────────────────

def test_fetch_icons_merges_items_and_extra_ids(monkeypatch):
    fetched = []

    async def fake_fetch_icon(session, item_id):
        fetched.append(item_id)
        return b"png"

    monkeypatch.setattr(build_image, "fetch_icon", fake_fetch_icon)
    icons = asyncio.run(build_image.fetch_icons({"mainhand": ["A"], "cape": ["*"]}, ["B", "A"]))
    assert fetched == ["A", "B"]
    assert icons == {"A": b"png", "B": b"png"}


# ── _post_compo_image (/acti) ────────────────────────────────────────────────

def test_post_compo_image_sends_png_after_embed(monkeypatch):
    asked = []

    async def fake_get_builds(ids, guild_id):
        asked.append((sorted(ids), guild_id))
        return BUILDS

    monkeypatch.setattr(db, "get_builds_by_ids", fake_get_builds)
    monkeypatch.setattr(build_image, "fetch_icons", _fake_fetch_icons([]))
    inter, sent = _fake_interaction()

    asyncio.run(activites._post_compo_image(inter, "Traque", TEMPLATE))

    assert asked == [([12, 15, 20], 111)]
    assert len(sent) == 1
    file = sent[0]["file"]
    assert file.filename == "compo.png"
    assert Image.open(file.fp).format == "PNG"


def test_post_compo_image_does_nothing_for_templates_without_builds(monkeypatch):
    async def fail(*args, **kwargs):
        raise AssertionError("ne doit pas interroger la base")

    monkeypatch.setattr(db, "get_builds_by_ids", fail)
    inter, sent = _fake_interaction()
    asyncio.run(activites._post_compo_image(inter, "Donjon", {"pf_1": {"TANK": 1, "DPS": 3}}))
    assert sent == []


def test_post_compo_image_errors_are_logged_not_raised(monkeypatch):
    """Une panne (base, CDN, Discord) ne doit jamais faire échouer /acti."""
    async def boom(ids, guild_id):
        raise RuntimeError("base indisponible")

    logged = []

    async def fake_log_error(source, error, **kwargs):
        logged.append((source, str(error)))

    monkeypatch.setattr(db, "get_builds_by_ids", boom)
    monkeypatch.setattr(activites, "log_error", fake_log_error)
    inter, sent = _fake_interaction()

    asyncio.run(activites._post_compo_image(inter, "Traque", TEMPLATE))

    assert sent == []
    assert logged == [("activites.compo_image", "base indisponible")]


def test_get_builds_by_ids_empty_list_skips_database():
    """Pas de requête (ni de pool) quand la compo n'a aucun build."""
    assert asyncio.run(db.get_builds_by_ids([], 111)) == {}
