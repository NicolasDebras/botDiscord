from albion_api import find_exact_player, fmt_fame, same_guild, tagged_nick


def test_fmt_fame_under_thousand_unchanged():
    assert fmt_fame(999) == "999"


def test_fmt_fame_thousands_uses_k_suffix():
    assert fmt_fame(1500) == "1.5k"


def test_fmt_fame_exact_thousand():
    assert fmt_fame(1000) == "1.0k"


def test_fmt_fame_millions_uses_m_suffix():
    assert fmt_fame(2_500_000) == "2.5M"


def test_fmt_fame_billions_uses_b_suffix():
    assert fmt_fame(1_200_000_000) == "1.2B"


def test_fmt_fame_zero():
    assert fmt_fame(0) == "0"


def test_find_exact_player_ignores_case():
    players = [{"Name": "Naej2", "Id": "b"}, {"Name": "Naej", "Id": "a"}]
    assert find_exact_player(players, "naej")["Id"] == "a"


def test_find_exact_player_no_fallback_on_first_result():
    assert find_exact_player([{"Name": "NaejLeVrai", "Id": "x"}], "Naej") is None


def test_same_guild_ignores_case_and_spaces():
    assert same_guild(" Lilium ", "lilium")


def test_same_guild_empty_vs_name():
    assert not same_guild("", "Lilium")
    assert not same_guild(None, "Lilium")


def test_tagged_nick_normal():
    assert tagged_nick("Lilium", "Naej") == "[Lilium] Naej"


def test_tagged_nick_without_guild_keeps_pseudo():
    assert tagged_nick("", "Naej") == "Naej"
    assert tagged_nick(None, "Naej") == "Naej"


def test_tagged_nick_truncates_guild_not_pseudo():
    nick = tagged_nick("A Very Long Guild Name Indeed", "PseudoAssezLong")
    assert len(nick) == 32
    assert nick.endswith("] PseudoAssezLong")
    assert nick.startswith("[A Very")


def test_tagged_nick_pseudo_too_long_for_tag():
    pseudo = "P" * 30
    assert tagged_nick("Lilium", pseudo) == pseudo
