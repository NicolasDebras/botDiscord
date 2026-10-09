"""Téléchargement des icônes Albion : lenteurs / erreurs du CDN tolérées, sans réseau réel."""
import asyncio

import pytest

from Service import build_image


class FakeStream:
    """Comme aiohttp : read(n) rend ce qui est arrivé (paquets de NET_CHUNK octets max), b"" à la fin."""
    NET_CHUNK = 4096

    def __init__(self, body):
        self._body = body
        self._pos = 0

    async def read(self, n=-1):
        size = self.NET_CHUNK if n < 0 else min(n, self.NET_CHUNK)
        chunk = self._body[self._pos:self._pos + size]
        self._pos += len(chunk)
        return chunk


class FakeResponse:
    def __init__(self, status, body=b"png"):
        self.status = status
        self.content = FakeStream(body)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    """`script` : url → liste de réponses successives (int = statut, Exception = levée)."""
    def __init__(self, script, delay=0):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls = []
        self.delay = delay

    def get(self, url, **kwargs):
        self.calls.append(url)
        step = self.script.get(url, [404]).pop(0) if self.script.get(url) else 404
        session = self

        class Ctx:
            async def __aenter__(self):
                if session.delay:
                    await asyncio.sleep(session.delay)
                if isinstance(step, BaseException):
                    raise step
                if isinstance(step, tuple):  # (statut, corps)
                    return FakeResponse(*step)
                return FakeResponse(step)

            async def __aexit__(self, *exc):
                return False
        return Ctx()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def url(tier, item_id):
    return build_image._ICON_URL.format(tier=tier, item_id=item_id)


@pytest.fixture(autouse=True)
def clear_cache(tmp_path, monkeypatch):
    """Cache vidé et dossier d'icônes locales vide : ces tests visent le secours CDN."""
    monkeypatch.setattr(build_image, "ICONS_DIR", tmp_path)
    build_image._icon_cache.clear()
    yield
    build_image._icon_cache.clear()


# ── Icônes locales (assets/icons) ────────────────────────────────────────────

def test_local_icon_is_used_without_network(tmp_path):
    (tmp_path / "MAIN_MACE.png").write_bytes(b"local")
    session = FakeSession({})
    assert asyncio.run(build_image.fetch_icon(session, "MAIN_MACE")) == b"local"
    assert session.calls == []


def test_local_icon_rejects_path_traversal(tmp_path):
    (tmp_path.parent / "secret.png").write_bytes(b"x")
    assert build_image.local_icon("../secret") is None
    assert build_image.local_icon("") is None


def test_repo_ships_icons_for_the_site_catalog():
    """Les icônes embarquées existent et sont de vraies images PNG."""
    from PIL import Image
    real_dir = build_image.Path(build_image.__file__).resolve().parent.parent / "assets" / "icons"
    files = list(real_dir.glob("*.png"))
    assert len(files) > 250
    for name in ("MAIN_MACE_HELL", "MEAL_OMELETTE", "POTION_MOB_RESET", "CAPEITEM_FW_CAERLEON"):
        assert Image.open(real_dir / f"{name}.png").format == "PNG"


# ── Secours CDN ──────────────────────────────────────────────────────────────


def test_fetch_icon_falls_back_to_lower_tier_and_caches():
    session = FakeSession({url(8, "MEAL_OMELETTE"): [404], url(7, "MEAL_OMELETTE"): [200]})
    assert asyncio.run(build_image.fetch_icon(session, "MEAL_OMELETTE")) == b"png"
    assert asyncio.run(build_image.fetch_icon(session, "MEAL_OMELETTE")) == b"png"
    assert len(session.calls) == 2  # 2e appel servi par le cache


def test_fetch_icon_retries_after_timeout():
    session = FakeSession({url(8, "A"): [asyncio.TimeoutError(), 200]})
    assert asyncio.run(build_image.fetch_icon(session, "A")) == b"png"


def test_fetch_icon_transient_failure_is_not_cached():
    """Un CDN lent ne doit pas marquer l'icône comme absente pour toujours."""
    session = FakeSession({url(8, "A"): [asyncio.TimeoutError()] * build_image.ICON_RETRIES})
    assert asyncio.run(build_image.fetch_icon(session, "A")) is None
    assert "A" not in build_image._icon_cache


def test_split_tier_and_tiered_gear():
    assert build_image.split_tier("T8_MAIN_SWORD@1") == ("MAIN_SWORD", 8, 1)
    assert build_image.split_tier("T7_2H_HOLYSTAFF") == ("2H_HOLYSTAFF", 7, 0)
    assert build_image.split_tier("MAIN_SWORD") == ("MAIN_SWORD", None, 0)
    assert build_image.has_tiered_gear({"mainhand": ["T8_MAIN_SWORD@1"]})
    assert build_image.has_tiered_gear({"swaps": ["T7_OFF_SHIELD"]})
    assert not build_image.has_tiered_gear({"mainhand": ["MAIN_SWORD"], "food": ["T8_MEAL_STEW@1"]})


def test_tiered_item_uses_exact_icon_first(tmp_path):
    (tmp_path / "MAIN_SWORD.png").write_bytes(b"local")
    exact = build_image._ICON_URL_EXACT.format(item_id="T7_MAIN_SWORD@2")
    session = FakeSession({exact: [(200, b"t72")]})
    assert asyncio.run(build_image.fetch_icon(session, "T7_MAIN_SWORD@2")) == b"t72"
    assert session.calls == [exact]
    assert build_image._icon_cache["T7_MAIN_SWORD@2"] == b"t72"


def test_tiered_item_missing_on_cdn_falls_back_to_base_icon(tmp_path):
    (tmp_path / "MAIN_SWORD.png").write_bytes(b"local")
    session = FakeSession({})   # 404 sur l'URL exacte
    assert asyncio.run(build_image.fetch_icon(session, "T6_MAIN_SWORD@4")) == b"local"
    session = FakeSession({url(8, "OFF_SHIELD"): [200]})
    assert asyncio.run(build_image.fetch_icon(session, "T6_OFF_SHIELD@1")) == b"png"
    assert session.calls[-1] == url(8, "OFF_SHIELD")


def test_fetch_icon_unknown_item_is_cached_as_missing():
    session = FakeSession({})
    assert asyncio.run(build_image.fetch_icon(session, "INCONNU")) is None
    assert build_image._icon_cache["INCONNU"] is None
    assert len(session.calls) == 8  # T8 → T1


def test_fetch_icon_ignores_oversized_body():
    """Une réponse anormalement grosse n'est ni chargée en entier ni gardée."""
    big = b"x" * (build_image.ICON_MAX_BYTES + 10)
    session = FakeSession({url(8, "A"): [(200, big)]})
    assert asyncio.run(build_image.fetch_icon(session, "A")) is None


def test_icon_larger_than_one_network_chunk_is_read_entirely():
    """Régression : read(n) seul ne rendait que le 1er paquet → PNG tronqué, dessiné « ? »."""
    body = bytes(range(256)) * 100   # 25,6 Ko, comme une vraie icône 128 px
    session = FakeSession({build_image._ICON_URL_EXACT.format(item_id="T6_2H_CROSSBOW@4"): [(200, body)]})
    assert asyncio.run(build_image.fetch_icon(session, "T6_2H_CROSSBOW@4")) == body


def test_fetch_icon_rejects_malformed_item_id_without_network():
    session = FakeSession({})
    for bad in ("../../x", "A?size=99999", "a b", "", "A/B"):
        assert asyncio.run(build_image.fetch_icon(session, bad)) is None
    assert session.calls == []


def test_fetch_icons_never_raises_and_limits_concurrency(monkeypatch):
    running, peak = 0, 0

    async def slow_fetch(session, item_id):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1
        if item_id == "BOOM":
            raise RuntimeError("panne")
        return b"png"

    monkeypatch.setattr(build_image, "fetch_icon", slow_fetch)
    ids = [f"I{n}" for n in range(20)] + ["BOOM"]
    icons = asyncio.run(build_image.fetch_icons(None, ids))
    assert icons["BOOM"] is None
    assert all(icons[f"I{n}"] == b"png" for n in range(20))
    assert peak <= build_image.ICON_CONCURRENCY


def test_fetch_icons_deadline_turns_slow_icons_into_none(monkeypatch):
    async def fetch(session, item_id):
        await asyncio.sleep(5 if item_id == "LENT" else 0)
        return b"png"

    monkeypatch.setattr(build_image, "fetch_icon", fetch)
    monkeypatch.setattr(build_image, "ICONS_DEADLINE", 0.2)
    icons = asyncio.run(build_image.fetch_icons(None, ["OK", "LENT"]))
    assert icons == {"OK": b"png", "LENT": None}


def test_fetch_icons_empty():
    assert asyncio.run(build_image.fetch_icons(None, [])) == {}
