from Service import activites
from Service.activites import (
    _parse_weapon_slots, _player_weapon, _sort_roles,
    get_pf1, get_pf2, get_specs, load_all_templates,
    _acti_label, _is_creator, parse_silver, MAX_SILVER, MAX_WEAPON_SLOTS,
)
from tests.fakes import fake_member


# ── _parse_weapon_slots ─────────────────────────────────────────────────────

def test_parse_weapon_slots_with_explicit_count():
    result = _parse_weapon_slots("1H Masse (×2)")
    assert result == [("1H Masse (×2)", "1H Masse", 2)]


def test_parse_weapon_slots_unlimited_infini():
    result = _parse_weapon_slots("Brassards (×infini)")
    assert result == [("Brassards (×infini)", "Brassards", None)]


def test_parse_weapon_slots_unlimited_infinity_symbol():
    result = _parse_weapon_slots("Brassards (×∞)")
    assert result[0][2] is None


def test_parse_weapon_slots_no_count_defaults_to_one():
    result = _parse_weapon_slots("Sancti Plaque")
    assert result == [("Sancti Plaque", "Sancti Plaque", 1)]


def test_parse_weapon_slots_multiple_entries_separated_by_dot():
    result = _parse_weapon_slots("1H Masse (×2)  ·  Brassards (×infini)  ·  Sancti (×1)")
    assert [clean for _, clean, _ in result] == ["1H Masse", "Brassards", "Sancti"]
    assert [count for _, _, count in result] == [2, None, 1]


def test_parse_weapon_slots_empty_string():
    assert _parse_weapon_slots("") == []


def test_parse_weapon_slots_ignores_empty_segments():
    result = _parse_weapon_slots("1H Masse (×2) · · ")
    assert len(result) == 1


# ── _player_weapon ───────────────────────────────────────────────────────────

def test_player_weapon_strips_trailing_level():
    assert _player_weapon("Arc Long (750)") == "Arc Long"


def test_player_weapon_no_level_unchanged():
    assert _player_weapon("Arc Long") == "Arc Long"


def test_player_weapon_empty_string():
    assert _player_weapon("") == ""


# ── _sort_roles ──────────────────────────────────────────────────────────────

def test_sort_roles_pf1_before_pf2_before_scoot():
    roles = ["SCOOT", "PF2:DPS", "TANK", "PF2:TANK", "HEAL"]
    assert _sort_roles(roles) == ["TANK", "HEAL", "PF2:DPS", "PF2:TANK", "SCOOT"]


def test_sort_roles_preserves_relative_order_within_group():
    roles = ["DPS", "HEAL", "TANK"]
    assert _sort_roles(roles) == ["DPS", "HEAL", "TANK"]


def test_sort_roles_empty_list():
    assert _sort_roles([]) == []


# ── get_pf1 / get_pf2 / get_specs ───────────────────────────────────────────

def test_get_pf1_reads_pf_1_key():
    assert get_pf1({"pf_1": {"TANK": 1}, "weapon": {}}) == {"TANK": 1}


def test_get_pf1_falls_back_to_int_valued_keys():
    """Ancien format de template sans clé pf_1 explicite : les valeurs
    entières du dict sont traitées comme des rôles."""
    assert get_pf1({"TANK": 2, "description": "texte", "type_acti": "PVE"}) == {"TANK": 2}


def test_get_pf2_defaults_to_empty_dict():
    assert get_pf2({"pf_1": {"TANK": 1}}) == {}


def test_get_specs_reads_weapon_key():
    assert get_specs({"weapon": {"TANK": "1H Masse"}}) == {"TANK": "1H Masse"}


def test_get_specs_falls_back_to_specs_key():
    assert get_specs({"specs": {"TANK": "1H Masse"}}) == {"TANK": "1H Masse"}


def test_get_specs_defaults_to_empty_dict():
    assert get_specs({}) == {}


# ── load_all_templates ──────────────────────────────────────────────────────

def test_load_all_templates_merges_defaults_and_custom(monkeypatch):
    monkeypatch.setattr(activites, "DEFAULT_TEMPLATES", {"Défaut": {"type_acti": "PVE"}})
    monkeypatch.setattr(activites, "_templates_cache", {1: {"Custom": {"type_acti": "PVP"}}})
    result = load_all_templates(1)
    assert set(result.keys()) == {"Défaut", "Custom"}


def test_load_all_templates_scopes_custom_by_guild(monkeypatch):
    monkeypatch.setattr(activites, "DEFAULT_TEMPLATES", {})
    monkeypatch.setattr(activites, "_templates_cache", {1: {"CompoServeur1": {}}})
    assert load_all_templates(2) == {}
    assert "CompoServeur1" in load_all_templates(1)


def test_load_all_templates_default_restricted_to_guild_ids(monkeypatch):
    monkeypatch.setattr(activites, "DEFAULT_TEMPLATES", {
        "Restreint": {"type_acti": "PVE", "guild_ids": [42]},
    })
    monkeypatch.setattr(activites, "_templates_cache", {})
    assert load_all_templates(42) == {"Restreint": {"type_acti": "PVE", "guild_ids": [42]}}
    assert load_all_templates(99) == {}


# ── _acti_label ──────────────────────────────────────────────────────────────

def test_acti_label_prefers_thread_name():
    assert _acti_label({"thread_name": "mon-thread", "template": "RAID"}) == "mon-thread"


def test_acti_label_falls_back_to_template():
    assert _acti_label({"thread_name": None, "template": "RAID"}) == "RAID"


def test_acti_label_falls_back_to_default():
    assert _acti_label({}) == "Activité"


# ── _is_creator ──────────────────────────────────────────────────────────────

def test_is_creator_by_id_when_creator_id_present():
    user = fake_member(user_id=42)
    assert _is_creator(user, {"creator_id": 42, "creator": "AutreNom"}) is True
    assert _is_creator(user, {"creator_id": 99, "creator": "AutreNom"}) is False


def test_is_creator_never_by_display_name():
    """Sans creator_id (vieilles activités), personne n'est créateur : un pseudo s'usurpe
    (n'importe qui peut prendre le même display_name). Les officiers gardent la main."""
    user = fake_member(display_name="Naej")
    assert _is_creator(user, {"creator": "Naej"}) is False


def test_parse_weapon_slots_caps_huge_count():
    """« (×999999999) » ne doit pas générer un milliard de lignes à l'affichage."""
    assert _parse_weapon_slots("Arc (×999999999)") == [("Arc (×999999999)", "Arc", MAX_WEAPON_SLOTS)]


def test_parse_silver_accepts_separators():
    assert parse_silver("1 200 000") == 1_200_000
    assert parse_silver("1,200,000") == 1_200_000
    assert parse_silver("1.200.000") == 1_200_000
    assert parse_silver("0") == 0


def test_parse_silver_rejects_negative_garbage_and_absurd():
    assert parse_silver("-500000") is None
    assert parse_silver("abc") is None
    assert parse_silver("") is None
    assert parse_silver("²") is None
    assert parse_silver(str(MAX_SILVER + 1)) is None
