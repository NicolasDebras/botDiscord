"""/massup (qui reçoit quel build), lignes de compo des templates Lilium, signature des images.
Le rendu lui-même est testé dans la lib AlbionCreateImageBuild."""
import asyncio
import io

from PIL import Image

from lilium_compo import compo_rows
from Service import build_image
from Service.activites import build_id_for_role
from Service.massup import build_recipients, dm_summary

TEMPLATE = {
    "pf_1": {"TANK": 1, "HEAL": 2, "CALLER": 1},
    "builds": {"TANK": 12, "HEAL": "15"},
    "pf_2": {"DPS": 3},
    "builds_pf2": {"DPS": 20},
}


# ── build_id_for_role ────────────────────────────────────────────────────────

def test_build_id_for_role_pf1_pf2_and_missing():
    assert build_id_for_role(TEMPLATE, "TANK") == 12
    assert build_id_for_role(TEMPLATE, "HEAL") == 15      # id stocké en texte → int
    assert build_id_for_role(TEMPLATE, "PF2:DPS") == 20
    assert build_id_for_role(TEMPLATE, "CALLER") is None
    assert build_id_for_role(TEMPLATE, "DPS") is None      # DPS n'a un build qu'en PF2
    assert build_id_for_role({}, "TANK") is None


# ── build_recipients / dm_summary (/massup) ──────────────────────────────────

def test_build_recipients_groups_players_by_build():
    slots = {
        "TANK": [(1, "A", "Tank Masse (700)")],
        "HEAL": [(2, "B", ""), (3, "C", "")],
        "CALLER": [(4, "D", "")],
        "PF2:DPS": [(5, "E", "")],
        "Fill": [(6, "F", "")],
    }
    assert build_recipients(slots, TEMPLATE) == {
        12: [(1, "TANK")],
        15: [(2, "HEAL"), (3, "HEAL")],
        20: [(5, "DPS (PF2)")],
    }


def test_build_recipients_without_builds_is_empty():
    assert build_recipients({"TANK": [(1, "A", "")]}, {"pf_1": {"TANK": 1}}) == {}


def test_dm_summary():
    assert dm_summary(0, []) is None
    assert dm_summary(3, []) == "✉️ 3 build(s) envoyé(s) en MP."
    assert "<@7> <@8>" in dm_summary(1, [7, 8])


# ── compo_rows (lilium_compo.py) ─────────────────────────────────────────────

def test_compo_rows_lists_only_roles_with_builds_in_party_order():
    assert compo_rows(TEMPLATE) == [
        ("Party 1", "TANK", 1, 12),
        ("Party 1", "HEAL", 2, 15),
        ("Party 2", "DPS", 3, 20),
    ]
    assert compo_rows({"pf_1": {"TANK": 1}}) == []


def test_compo_rows_grouped_by_role_inside_each_party():
    template = {
        "pf_1": {"SUPPORT": 1, "DPS": 3, "TANK": 1, "HEAL": 2},
        "builds": {"SUPPORT": 4, "DPS": 3, "TANK": 1, "HEAL": 2},
        "pf_2": {"DPS": 2, "TANK": 1},
        "builds_pf2": {"DPS": 6, "TANK": 5},
    }
    assert [(p, r) for p, r, _, _ in compo_rows(template)] == [
        ("Party 1", "TANK"), ("Party 1", "HEAL"), ("Party 1", "SUPPORT"), ("Party 1", "DPS"),
        ("Party 2", "TANK"), ("Party 2", "DPS"),
    ]


# ── Plusieurs builds au choix pour un rôle ───────────────────────────────────

MULTI = {"pf_1": {"TANK": 2, "HEAL": 1}, "builds": {"TANK": [12, 13], "HEAL": 15}}


def test_build_ids_for_role_reads_old_and_new_format():
    from Service.activites import build_ids_for_role
    assert build_ids_for_role(MULTI, "TANK") == [12, 13]
    assert build_ids_for_role(MULTI, "HEAL") == [15]
    assert build_ids_for_role(MULTI, "DPS") == []
    assert build_id_for_role(MULTI, "TANK") == 12


def test_massup_sends_the_build_each_player_chose():
    slots = {"TANK": [(1, "A", "Main tank"), (2, "B", "Inconnu")], "HEAL": [(3, "C", "")]}
    out = build_recipients(slots, MULTI, {12: "Def tank", 13: "Main tank", 15: "Heal"})
    assert out == {13: [(1, "TANK")], 12: [(2, "TANK")], 15: [(3, "HEAL")]}


def test_compo_rows_one_line_per_proposed_build():
    assert [(r, b) for _, r, _, b in compo_rows(MULTI)] == [("TANK", 12), ("TANK", 13), ("HEAL", 15)]


# ── Branchement sur la lib (Service/build_image.py) ──────────────────────────

class FakeFetcher:
    def __init__(self):
        self.calls = []

    async def fetch(self, ids):
        self.calls.append(list(ids))
        return {}


def test_build_image_uses_the_lib_with_the_bot_signature(monkeypatch):
    fake = FakeFetcher()
    monkeypatch.setattr(build_image, "fetcher", fake)
    build = {"name": "Heal", "role": "HEAL", "items": {"mainhand": ["2H_HOLYSTAFF"]}}
    plain = Image.open(io.BytesIO(asyncio.run(build_image.build_image(build))))
    signed = Image.open(io.BytesIO(asyncio.run(build_image.build_image(build, "Lilium · Lily"))))
    assert plain.format == "PNG" and signed.height > plain.height
    assert fake.calls == [["2H_HOLYSTAFF"], ["2H_HOLYSTAFF"]]


def test_role_order_is_the_lib_default():
    assert build_image.ROLE_ORDER == ("TANK", "HEAL", "SUPPORT", "DPS")


# ── Signature « Serveur · Bot » en bas des images ────────────────────────────

def test_image_signature_uses_the_bot_nickname_on_the_server():
    from types import SimpleNamespace

    from Service.utils import image_signature
    inter = SimpleNamespace(guild=SimpleNamespace(name="Lilium", me=SimpleNamespace(display_name="Lily")),
                            client=SimpleNamespace(user=SimpleNamespace(name="LiliumBot")))
    assert image_signature(inter) == "Lilium · Lily"
    inter.guild.me = None
    assert image_signature(inter) == "Lilium · LiliumBot"
