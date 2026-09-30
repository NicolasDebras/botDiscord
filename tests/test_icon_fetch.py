"""Téléchargement des icônes Albion : lenteurs / erreurs du CDN tolérées, sans réseau réel."""
import asyncio

import pytest

from Service import build_image


class FakeResponse:
    def __init__(self, status, body=b"png"):
        self.status = status
        self._body = body

    async def read(self):
        return self._body

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


def test_fetch_icon_unknown_item_is_cached_as_missing():
    session = FakeSession({})
    assert asyncio.run(build_image.fetch_icon(session, "INCONNU")) is None
    assert build_image._icon_cache["INCONNU"] is None
    assert len(session.calls) == 8  # T8 → T1


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
