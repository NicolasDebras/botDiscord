from albion_api import find_exact_player, fmt_fame, majority_guild, same_guild, tagged_nick


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


def test_tagged_nick_uses_first_three_chars():
    assert tagged_nick("Lilium", "Naej") == "[Lil] Naej"


def test_tagged_nick_short_guild_name_kept():
    assert tagged_nick("OK", "Naej") == "[OK] Naej"


def test_tagged_nick_without_guild_keeps_pseudo():
    assert tagged_nick("", "Naej") == "Naej"
    assert tagged_nick(None, "Naej") == "Naej"


def test_tagged_nick_tag_trailing_space_stripped():
    assert tagged_nick("Le Clan", "Naej") == "[Le] Naej"


def test_tagged_nick_pseudo_too_long_for_tag():
    pseudo = "P" * 30
    assert tagged_nick("Lilium", pseudo) == pseudo


def test_majority_guild_ignores_case_and_empty():
    assert majority_guild(["Lilium", "", "lilium", "Autre", None]) == "Lilium"


def test_majority_guild_none_when_no_guild():
    assert majority_guild(["", None]) is None


def test_tagged_nick_custom_length():
    assert tagged_nick("Lilium", "Naej", tag_len=5) == "[Liliu] Naej"

