from Service.utils import fmt_silver, is_admin, is_membre, is_caller_or_admin, can_manage_web_admins, split_message
from tests.fakes import fake_member, fake_role


# ── split_message (limite Discord de 2000 caractères) ────────────────────────

def test_split_message_short_text_unchanged():
    assert split_message("a\n\nb") == ["a\n\nb"]


def test_split_message_cuts_between_lines_under_limit():
    lines = [f"• Joueur{n} — <@{10**17 + n}> — recruté le 01/09/2026" for n in range(80)]
    parts = split_message("\n".join(lines))
    assert len(parts) > 1
    assert all(len(p) <= 2000 for p in parts)
    assert "\n".join(parts) == "\n".join(lines)  # rien de perdu, aucune ligne coupée


def test_split_message_hard_cuts_single_huge_line():
    parts = split_message("x" * 4500, limit=2000)
    assert [len(p) for p in parts] == [2000, 2000, 500]


# ── fmt_silver ───────────────────────────────────────────────────────────────

def test_fmt_silver_adds_space_thousands_separators():
    assert fmt_silver(1234567) == "1 234 567"


def test_fmt_silver_zero():
    assert fmt_silver(0) == "0"


def test_fmt_silver_negative():
    assert fmt_silver(-1000) == "-1 000"


def test_fmt_silver_small_number_unchanged():
    assert fmt_silver(42) == "42"


# ── is_admin ─────────────────────────────────────────────────────────────────

def test_is_admin_true_for_guild_administrator():
    member = fake_member(administrator=True)
    assert is_admin(member) is True


def test_is_admin_true_with_officier_role():
    member = fake_member(roles=[fake_role("Officier")])
    assert is_admin(member) is True


def test_is_admin_false_without_role_or_permission():
    member = fake_member(roles=[fake_role("Membre")])
    assert is_admin(member) is False


# ── is_membre ────────────────────────────────────────────────────────────────

def test_is_membre_true_for_membre_role():
    member = fake_member(roles=[fake_role("Membre")])
    assert is_membre(member) is True


def test_is_membre_true_for_officier_role_too():
    """Officier et Maitre de guilde ont aussi accès aux commandes Membre."""
    member = fake_member(roles=[fake_role("Officier")])
    assert is_membre(member) is True


def test_is_membre_false_for_unrelated_role():
    member = fake_member(roles=[fake_role("Recruteur")])
    assert is_membre(member) is False


# ── is_caller_or_admin ─────────────────────────────────────────────────────────

def test_is_caller_or_admin_true_for_caller_role():
    member = fake_member(roles=[fake_role("Caller")])
    assert is_caller_or_admin(member) is True


def test_is_caller_or_admin_false_for_simple_membre():
    member = fake_member(roles=[fake_role("Membre")])
    assert is_caller_or_admin(member) is False


def test_is_caller_or_admin_true_for_guild_administrator():
    member = fake_member(administrator=True, roles=[])
    assert is_caller_or_admin(member) is True


# ── can_manage_web_admins (/webadmin) ────────────────────────────────────────

def test_can_manage_web_admins_true_for_guild_administrator():
    assert can_manage_web_admins(fake_member(administrator=True)) is True


def test_can_manage_web_admins_true_for_maitre_de_guilde():
    assert can_manage_web_admins(fake_member(roles=[fake_role("Maitre de guilde")])) is True


def test_can_manage_web_admins_false_for_officier():
    """Officier gère le staff du site via /config, mais ne nomme pas les admins."""
    assert can_manage_web_admins(fake_member(roles=[fake_role("Officier")])) is False


def test_can_manage_web_admins_false_for_simple_membre():
    assert can_manage_web_admins(fake_member(roles=[fake_role("Membre")])) is False
