import changelog


_FAKE_CHANGELOG = [
    {"version": "3", "title": "C", "items": ["c"]},
    {"version": "2", "title": "B", "items": ["b"]},
    {"version": "1", "title": "A", "items": ["a"]},
]


def _patched(monkeypatch, entries=_FAKE_CHANGELOG):
    monkeypatch.setattr(changelog, "CHANGELOG", entries)


def test_none_returns_only_latest(monkeypatch):
    _patched(monkeypatch)
    result = changelog.get_entries_since(None)
    assert [e["version"] for e in result] == ["3"]


def test_older_version_returns_newer_entries_oldest_first(monkeypatch):
    _patched(monkeypatch)
    result = changelog.get_entries_since("1")
    # "1" est le plus ancien de la liste -> tout ce qui est après lui (2, 3),
    # renvoyé du plus ancien au plus récent pour un affichage chronologique.
    assert [e["version"] for e in result] == ["2", "3"]


def test_current_version_returns_nothing_new(monkeypatch):
    _patched(monkeypatch)
    result = changelog.get_entries_since("3")
    assert result == []


def test_unknown_version_returns_everything(monkeypatch):
    """Si last_version ne correspond à aucune entrée connue (jamais annoncé,
    ou entrée supprimée depuis), la boucle ne trouve jamais de break et
    renvoie tout l'historique — comportement à connaître, pas une erreur."""
    _patched(monkeypatch)
    result = changelog.get_entries_since("version-inconnue")
    assert [e["version"] for e in result] == ["1", "2", "3"]


def test_single_entry_changelog(monkeypatch):
    _patched(monkeypatch, entries=[{"version": "1", "title": "Seule", "items": ["x"]}])
    assert [e["version"] for e in changelog.get_entries_since(None)] == ["1"]
    assert changelog.get_entries_since("1") == []
