from albion_api import fmt_fame


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
