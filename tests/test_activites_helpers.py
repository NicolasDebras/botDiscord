from Service import activites
from Service.activites import (
    _parse_weapon_slots, _player_weapon, _sort_roles,
    get_pf1, get_pf2, get_specs, load_all_templates,
    _acti_label, _is_creator, parse_silver, MAX_SILVER, MAX_WEAPON_SLOTS,
)
from tests.fakes import fake_member
from datetime import UTC


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
    assert _sort_roles(roles) == ["TANK", "HEAL", "PF2:TANK", "PF2:DPS", "SCOOT"]


def test_sort_roles_tank_heal_support_dps_in_each_party():
    roles = ["DPS", "SUPPORT", "HEAL", "TANK", "PF2:DPS", "PF2:SUPPORT", "PF2:TANK"]
    assert _sort_roles(roles) == ["TANK", "HEAL", "SUPPORT", "DPS", "PF2:TANK", "PF2:SUPPORT", "PF2:DPS"]


def test_sort_roles_keeps_build_lines_with_their_role_and_custom_roles_last_in_template_order():
    roles = ["DPS · Arcane", "COBRA", "TANK · Main tank", "FAUX", "SUPPORT 2", "TANK · Def tank"]
    assert _sort_roles(roles) == ["TANK · Main tank", "TANK · Def tank", "SUPPORT 2", "DPS · Arcane", "COBRA", "FAUX"]


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


# ── Plusieurs lignes du même rôle (2 tanks avec builds différents) ───────────

def test_base_role_strips_party_build_name_and_duplicate_number():
    from Service.activites import base_role
    assert base_role("TANK") == "TANK"
    assert base_role("TANK · Main tank") == "TANK"
    assert base_role("PF2:HEAL · Heal sacré") == "HEAL"
    assert base_role("DPS 2") == "DPS"
    assert base_role("RAID 2") == "RAID 2"          # pas un rôle connu : on ne touche pas
    assert base_role("SCOOT") == "SCOOT"


def test_group_role_keys_groups_builds_under_their_role_and_keeps_order():
    from Service.activites import group_role_keys
    keys = ["TANK · Def tank", "HEAL", "DPS · Weeping", "TANK · Main tank",
            "DPS · One shot", "PF2:DPS · Weeping", "SCOOT"]
    assert group_role_keys(keys) == {
        "TANK": ["TANK · Def tank", "TANK · Main tank"],
        "HEAL": ["HEAL"],
        "DPS": ["DPS · Weeping", "DPS · One shot"],
        "PF2:DPS": ["PF2:DPS · Weeping"],
        "SCOOT": ["SCOOT"],
    }


def test_build_label_keeps_only_the_build_name():
    from Service.activites import build_label
    assert build_label("SUPPORT · Dragon - BR") == "Dragon - BR"
    assert build_label("PF2:DPS · Weeping") == "Weeping"
    assert build_label("DPS 2") == "DPS 2"
    assert build_label("PF2:HEAL") == "HEAL"
    assert build_label("TANK", "Main tank") == "Main tank"       # 1re ligne : clé nue
    assert build_label("TANK · Def tank", "Autre") == "Def tank"


def test_slot_title_uses_build_name_for_bare_first_line_only_when_it_has_a_build():
    from Service.activites import slot_title
    tdata = {"pf_1": {"TANK": 1, "TANK · Def tank": 1, "DPS": 2},
             "weapon": {"TANK": "Main tank", "TANK · Def tank": "Def tank", "DPS": "Arcane · Curse"},
             "builds": {"TANK": 12, "TANK · Def tank": 13}}
    assert slot_title(tdata, "TANK") == "Main tank"
    assert slot_title(tdata, "TANK · Def tank") == "Def tank"
    assert slot_title(tdata, "DPS") == "DPS"          # liste d'armes, pas un nom de build


def test_role_share_exact_key_then_base_role_then_one():
    from Service.activites import role_share
    mult = {"TANK": 2, "PF2:TANK": 1, "DPS · Arc": 0.5}
    assert role_share(mult, "TANK") == 2
    assert role_share(mult, "PF2:TANK") == 1             # clé PF2 exacte, pas la part PF1
    assert role_share(mult, "TANK · Off") == 2           # rôle de base
    assert role_share(mult, "DPS · Arc") == 0.5
    assert role_share(mult, "HEAL") == 1
    assert role_share({}, "Fill") == 1


def test_share_tag_french_format_and_hidden_for_one():
    from Service.activites import share_tag
    assert share_tag(1) == ""
    assert share_tag(1.0) == ""
    assert share_tag(2) == "💰 2 parts"
    assert share_tag(1.5) == "💰 1,5 part"
    assert share_tag(0) == "💰 0 part"


def test_available_role_keys_hides_full_roles_and_pf2_until_a_pf1_role_is_full():
    from Service.activites import available_role_keys
    tdata = {"pf_1": {"TANK · Def tank": 1, "DPS · Weeping": 2}, "pf_2": {"DPS · Weeping": 1}}
    roles = ["TANK · Def tank", "DPS · Weeping", "PF2:DPS · Weeping"]
    data = {"slots": {"TANK · Def tank": [], "DPS · Weeping": [(1, "a")]}}
    assert available_role_keys(data, tdata, roles) == ["TANK · Def tank", "DPS · Weeping"]
    data["slots"]["TANK · Def tank"] = [(2, "b")]
    assert available_role_keys(data, tdata, roles) == ["DPS · Weeping", "PF2:DPS · Weeping"]


def test_compo_image_sorts_duplicate_roles_with_their_base_role():
    from albion_create_image_build import role_rank
    assert role_rank("TANK · Main tank") == role_rank("TANK") < role_rank("HEAL · X") < role_rank("SUPPORT") < role_rank("DPS 2")


def test_build_line_accepts_as_many_players_as_its_count():
    """Régression : sur une compo du site (PvP), le nom du build était pris pour une arme
    limitée à 1 place → une ligne « DPS ×3 » refusait le 2e joueur."""
    from Service.activites import registration_error, _place_player
    tdata = {"type_acti": "PVP", "pf_1": {"DPS": 3, "TANK": 1, "TANK · Main tank": 1},
             "weapon": {"DPS": "DPS mono cible", "TANK": "Def tank", "TANK · Main tank": "Main tank"},
             "builds": {"DPS": 4, "TANK": 1, "TANK · Main tank": 2}}
    data = {"slots": {}}
    for uid in (1, 2, 3):
        assert registration_error(data, tdata, uid, "DPS", "DPS mono cible") is None
        _place_player(data, uid, f"J{uid}", "DPS", "DPS mono cible")
    assert "Plus de place en" in registration_error(data, tdata, 4, "DPS", "DPS mono cible")
    # 2 tanks : chaque ligne a sa place
    assert registration_error(data, tdata, 5, "TANK", "Def tank") is None
    assert registration_error(data, tdata, 6, "TANK · Main tank", "Main tank") is None


def test_weapon_sub_limit_still_applies_without_build():
    from Service.activites import registration_error, _place_player
    tdata = {"type_acti": "PVP", "pf_1": {"DPS": 3}, "weapon": {"DPS": "Arc (×1) · Épée (×2)"}}
    data = {"slots": {}}
    _place_player(data, 1, "J1", "DPS", "Arc")
    assert "Plus de place pour **Arc**" in registration_error(data, tdata, 2, "DPS", "Arc")


# ── Historique des activités (stats d'activité du site) ──────────────────────

def test_activity_log_row_snapshot():
    from datetime import datetime
    from Service.activites import activity_log_row
    created = datetime(2026, 10, 8, 20, 0, tzinfo=UTC)
    data = {"guild_id": 111, "template": "ZvZ", "creator_id": 42, "max_players": 6, "created_at": created,
            "slots": {"TANK": [(1, "A", ""), (2, "B", "")], "HEAL": [], "PF2:DPS": [(3, "C", "")]}}
    tdata = {"type_acti": "PVP", "pf_1": {"TANK": 2, "HEAL": 1}, "pf_2": {"DPS": 3}}
    row = activity_log_row(data, tdata, "finacti")
    assert row["slots"] == {"TANK": ["1", "2"], "PF2:DPS": ["3"]}           # rôles vides omis
    assert row["capacity"] == {"TANK": 2, "HEAL": 1, "PF2:DPS": 3}
    assert row["creator_id"] == "42" and row["type_acti"] == "PVP" and row["outcome"] == "finacti"
    assert activity_log_row({"slots": {}}, {}, "annulée")["capacity"] == {}


def test_remove_activity_logs_then_deletes_and_survives_log_errors(monkeypatch):
    import asyncio
    from Service import activites
    calls = []

    async def fake_log(row):
        calls.append(("log", row["outcome"]))
        raise RuntimeError("base indisponible")

    async def fake_delete(msg_id):
        calls.append(("delete", msg_id))

    async def fake_error(*a, **k):
        calls.append(("error",))

    monkeypatch.setattr(activites.db, "add_activity_log", fake_log, raising=False)
    monkeypatch.setattr(activites.db, "delete_activity", fake_delete)
    monkeypatch.setattr("Service.utils.log_error", fake_error)
    activites.activities[5] = {"guild_id": 1, "template": "", "slots": {}}
    asyncio.run(activites.remove_activity(5, "fin"))
    assert calls == [("log", "fin"), ("error",), ("delete", 5)] and 5 not in activites.activities


# ── refresh_view_on_startup (on_ready) : seule une suppression confirmée retire l'acti ──

def _http_error(cls, status: int):
    from types import SimpleNamespace
    return cls(SimpleNamespace(status=status, reason=""), "")


def _startup_bot(fetch_message, cached=True):
    from types import SimpleNamespace
    edits = []

    async def edit(**kw):
        edits.append(kw)

    async def _fetch_message(msg_id):
        if isinstance(fetch_message, Exception):
            raise fetch_message
        return SimpleNamespace(edit=edit)

    channel = SimpleNamespace(fetch_message=_fetch_message)

    async def fetch_channel(channel_id):
        return channel

    bot = SimpleNamespace(get_channel=lambda cid: channel if cached else None, fetch_channel=fetch_channel)
    return bot, edits


def _run_startup(monkeypatch, bot):
    import asyncio
    errors = []

    async def fake_error(source, e, **k):
        errors.append(source)

    monkeypatch.setattr(activites, "log_error", fake_error)
    monkeypatch.setattr(activites, "build_view", lambda msg_id: f"view-{msg_id}")
    return asyncio.run(activites.refresh_view_on_startup(bot, 7, {"channel_id": 1, "guild_id": 2})), errors


def test_refresh_view_on_startup_reattaches_view(monkeypatch):
    bot, edits = _startup_bot(None)
    assert _run_startup(monkeypatch, bot) == (True, [])
    assert edits == [{"view": "view-7"}]


def test_refresh_view_on_startup_fetches_archived_thread_missing_from_cache(monkeypatch):
    bot, edits = _startup_bot(None, cached=False)
    assert _run_startup(monkeypatch, bot) == (True, [])
    assert edits == [{"view": "view-7"}]


def test_refresh_view_on_startup_deleted_message_is_dropped(monkeypatch):
    import discord
    bot, _ = _startup_bot(_http_error(discord.NotFound, 404))
    assert _run_startup(monkeypatch, bot) == (False, [])


def test_refresh_view_on_startup_keeps_activity_on_transient_error(monkeypatch):
    import discord
    for error in (_http_error(discord.DiscordServerError, 503), _http_error(discord.Forbidden, 403)):
        bot, _ = _startup_bot(error)
        assert _run_startup(monkeypatch, bot) == (True, ["activites.on_ready"])


# ── special_pay_lines (récap /finacti) ──────────────────────────────────────

def test_special_pay_lines_names_players_of_roles_paid_differently():
    from Service.activites import special_pay_lines
    slots = {
        "TANK":  [(1, "Alpha", ""), (2, "Bravo", "")],
        "HEAL":  [(3, "Charlie", "")],
        "PF2:HEAL": [(4, "Delta", "")],
        "DPS":   [(5, "Echo", "")],
        "SCOOT": [(6, "Fox", "")],
        "SUPPORT": [],
    }
    lines = special_pay_lines(slots, {"TANK": 2, "SUPPORT": 3}, {"HEAL"}, 1_000_000)
    assert len(lines) == 3                                   # TANK ×2, HEAL et PF2:HEAL non payés
    assert "2 parts" in lines[0] and lines[0].endswith("— Alpha, Bravo")
    assert lines[1].startswith("🚫") and "Charlie" in lines[1] and "non payé" in lines[1]
    assert "Delta" in lines[2]                               # zero_pay par rôle de base
    assert not any("Echo" in l or "Fox" in l for l in lines)  # 1 part / Scoot : pas listés


def test_special_pay_lines_empty_when_everyone_has_one_share():
    from Service.activites import special_pay_lines
    assert special_pay_lines({"DPS": [(1, "A", "")]}, {}, set(), 500) == []


# ── Ligne à plusieurs builds au choix (« Ardent ou Aria », places partagées) ──

def test_row_build_names_and_slot_title():
    from Service.activites import row_build_names, slot_title
    tdata = {"pf_1": {"DPS": 2, "DPS · Ardent": 1}, "builds": {"DPS": 20, "DPS · Ardent": [21, 22]},
             "weapon": {"DPS": "DPS Arc", "DPS · Ardent": "Ardent / Aria"}}
    assert row_build_names([21, 22, 99], {21: {"name": "Ardent"}, 22: {"name": "Aria"}}) == ["Ardent", "Aria"]
    assert slot_title(tdata, "DPS · Ardent") == "Ardent / Aria"
    assert slot_title(tdata, "DPS") == "DPS Arc"


def test_row_builds_share_places():
    """Les builds au choix sont sur la même clé : une place prise par Aria bloque aussi Ardent."""
    from Service.activites import registration_error
    tdata = {"pf_1": {"DPS": 1}, "builds": {"DPS": [21, 22]}, "type_acti": "PVP"}
    data = {"slots": {"DPS": [(1, "A", "Aria")]}}
    assert "Plus de place" in registration_error(data, tdata, 2, "DPS", "Ardent")
    assert registration_error({"slots": {"DPS": []}}, tdata, 2, "DPS", "Ardent") is None
