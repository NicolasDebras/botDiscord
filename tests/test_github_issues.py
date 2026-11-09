"""Issues GitHub des erreurs : une seule issue par bug tant qu'elle est ouverte, réapparition
après fermeture, issues fermées → erreurs corrigées, et jamais d'exception vers l'appelant."""
import asyncio
from datetime import datetime, UTC

import pytest

import config
from Service import github_issues, utils


class FakeDb:
    def __init__(self, issues=None):
        self.issues = issues or []          # [{issue_number, command, error_type, closed_at}]
        self.attached = []                  # (error_id, issue_number)
        self.closed = []                    # (issue_number, closed_at)

    async def get_latest_error_issue(self, command, error_type):
        await asyncio.sleep(0)              # laisse passer une erreur concurrente
        mine = [i for i in self.issues if i["command"] == command and i["error_type"] == error_type]
        return {k: mine[-1][k] for k in ("issue_number", "closed_at")} if mine else None

    async def add_error_issue(self, number, command, error_type, error_id):
        self.issues.append({"issue_number": number, "command": command, "error_type": error_type, "closed_at": None})
        self.attached.append((error_id, number))

    async def set_error_issue(self, error_id, number):
        self.attached.append((error_id, number))

    async def get_open_error_issues(self):
        return [i["issue_number"] for i in self.issues if i["closed_at"] is None]

    async def close_error_issue(self, number, closed_at):
        self.closed.append((number, closed_at))


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status, self.payload = status, payload or {}

    async def json(self):
        return self.payload

    async def text(self):
        return str(self.payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    """Répond selon `routes` : {("POST", chemin): FakeResponse | Exception}."""
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def _call(self, method, url, json=None):
        path = url.removeprefix(f"{github_issues._API}/repos/{config.GITHUB_REPO}")
        self.calls.append((method, path, json))
        answer = self.routes[(method, path)]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def post(self, url, json=None):
        return self._call("POST", url, json)

    def get(self, url):
        return self._call("GET", url)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def github(monkeypatch):
    """Active la fonctionnalité avec une base et une API GitHub factices."""
    monkeypatch.setattr(config, "GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(config, "GITHUB_REPO", "owner/repo")
    monkeypatch.setattr(github_issues, "_lock", asyncio.Lock())
    fake_db = FakeDb()
    monkeypatch.setattr(github_issues, "db", fake_db)
    session = FakeSession({("POST", "/issues"): FakeResponse(201, {"number": 7})})
    monkeypatch.setattr(github_issues, "_session", lambda: session)
    return fake_db, session


def _entry(**kw):
    return {"id": 42, "ts": datetime(2026, 11, 9, 10, 0, tzinfo=UTC), "guild_id": 111, "command": "acti",
            "user_id": "456", "error_type": "KeyError", "error_message": "'slots'",
            "traceback": "Traceback (most recent call last):\nKeyError: 'slots'\n", **kw}


# ── Titre et corps ──────────────────────────────────────────────────────────

def test_title_is_one_short_line():
    assert github_issues.issue_title(_entry()) == "[acti] KeyError: 'slots'"
    assert github_issues.issue_title(_entry(error_message="")) == "[acti] KeyError"
    long = github_issues.issue_title(_entry(error_message="ligne 1\nligne 2 " + "x" * 300))
    assert "\n" not in long and len(long) == github_issues.TITLE_MAX and long.endswith("…")


def test_body_keeps_the_end_of_a_long_traceback_and_mentions_reappearance():
    body = github_issues.issue_body(_entry(traceback="début" + "x" * 10_000 + "FIN"), reappeared_after=12)
    assert "FIN" in body and "début" not in body
    assert "#12" in body and "Erreur #42" in body and "`111`" in body


# ── report ──────────────────────────────────────────────────────────────────

def test_disabled_without_token(github, monkeypatch):
    fake_db, session = github
    monkeypatch.setattr(config, "GITHUB_TOKEN", "")
    asyncio.run(github_issues.report(_entry()))
    assert session.calls == [] and fake_db.attached == []


def test_first_occurrence_opens_an_issue(github):
    fake_db, session = github
    asyncio.run(github_issues.report(_entry()))
    [(method, path, payload)] = session.calls
    assert (method, path) == ("POST", "/issues")
    assert payload["title"] == "[acti] KeyError: 'slots'" and payload["labels"] == ["bot-error"]
    assert "Réapparition" not in payload["body"]
    assert fake_db.attached == [(42, 7)]


def test_open_issue_gets_the_error_without_a_new_issue(github):
    fake_db, session = github
    fake_db.issues.append({"issue_number": 5, "command": "acti", "error_type": "KeyError", "closed_at": None})
    asyncio.run(github_issues.report(_entry()))
    assert session.calls == [] and fake_db.attached == [(42, 5)]


def test_other_bug_gets_its_own_issue(github):
    fake_db, session = github
    fake_db.issues.append({"issue_number": 5, "command": "finacti", "error_type": "KeyError", "closed_at": None})
    asyncio.run(github_issues.report(_entry()))
    assert len(session.calls) == 1 and fake_db.attached == [(42, 7)]


def test_reappearance_after_close_opens_a_new_issue(github):
    fake_db, session = github
    fake_db.issues.append({"issue_number": 5, "command": "acti", "error_type": "KeyError",
                           "closed_at": datetime(2026, 11, 1, tzinfo=UTC)})
    asyncio.run(github_issues.report(_entry()))
    assert "Réapparition après la fermeture de #5" in session.calls[0][2]["body"]
    assert fake_db.attached == [(42, 7)]


def test_simultaneous_errors_of_one_bug_open_a_single_issue(github):
    fake_db, session = github

    async def both():
        await asyncio.gather(github_issues.report(_entry(id=1)), github_issues.report(_entry(id=2)))

    asyncio.run(both())
    assert len(session.calls) == 1 and fake_db.attached == [(1, 7), (2, 7)]


@pytest.mark.parametrize("answer", [FakeResponse(500, {"message": "boom"}), OSError("réseau")])
def test_github_failure_is_silent(github, answer):
    fake_db, session = github
    session.routes[("POST", "/issues")] = answer
    asyncio.run(github_issues.report(_entry()))     # ne lève rien
    assert fake_db.attached == []


# ── sync_closed ─────────────────────────────────────────────────────────────

def test_sync_marks_closed_issues_only(github):
    fake_db, session = github
    fake_db.issues += [
        {"issue_number": n, "command": "acti", "error_type": f"E{n}", "closed_at": None} for n in (1, 2, 3, 4)
    ]
    session.routes.update({
        ("GET", "/issues/1"): FakeResponse(200, {"state": "closed", "closed_at": "2026-11-09T10:30:00Z"}),
        ("GET", "/issues/2"): FakeResponse(200, {"state": "open", "closed_at": None}),
        ("GET", "/issues/3"): FakeResponse(410),     # supprimée
        ("GET", "/issues/4"): FakeResponse(404),     # token sans accès : on ne touche à rien
    })
    assert asyncio.run(github_issues.sync_closed()) == 2
    assert [n for n, _ in fake_db.closed] == [1, 3]
    assert fake_db.closed[0][1] == datetime(2026, 11, 9, 10, 30, tzinfo=UTC)


def test_sync_disabled_without_token(github, monkeypatch):
    monkeypatch.setattr(config, "GITHUB_REPO", "")
    assert asyncio.run(github_issues.sync_closed()) == 0


# ── log_error ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("report_issue", [True, False])
def test_log_error_schedules_the_issue_with_the_saved_id(monkeypatch, report_issue):
    async def fake_add(**kwargs):
        return 99

    scheduled = []
    monkeypatch.setattr(utils.db, "add_error_log", fake_add)
    monkeypatch.setattr(utils.github_issues, "schedule_report", scheduled.append)
    try:
        raise KeyError("slots")
    except KeyError as e:
        asyncio.run(utils.log_error("acti", e, guild_id=111, user_id=456, report_issue=report_issue))
    if report_issue:
        [entry] = scheduled
        assert entry["id"] == 99 and entry["command"] == "acti" and entry["user_id"] == "456"
        assert "KeyError" in entry["traceback"]
    else:
        assert scheduled == []
