"""/errors : erreurs corrigées (site ou issue GitHub fermée) signalées par ✅."""
from datetime import datetime, UTC

from Service.errors import error_field_name, error_status


def _entry(**kw):
    return {"id": 42, "command": "acti", "ts": datetime(2026, 10, 8, 9, 12, tzinfo=UTC),
            "is_fixed": False, "github_issue": None, **kw}


def test_field_name_unfixed():
    assert error_field_name(_entry()) == "#42  ·  /acti  ·  08/10 09:12"


def test_field_name_fixed_gets_a_check_mark():
    assert error_field_name(_entry(is_fixed=True)) == "✅ #42  ·  /acti  ·  08/10 09:12"


def test_status_lists_fixed_and_issue():
    assert error_status(_entry()) == ""
    assert error_status(_entry(github_issue=12)) == " · issue #12"
    assert error_status(_entry(is_fixed=True, github_issue=12)) == " · ✅ corrigée · issue #12"
