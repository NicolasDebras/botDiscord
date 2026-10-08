"""Le guide du site (lilium-site/frontend/.../guide-content.ts) doit documenter chaque commande slash.
Ignoré si le repo du site n'est pas à côté (ex. déploiement du bot seul)."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT.parent / "lilium-site" / "frontend" / "src" / "app" / "pages" / "guide" / "guide-content.ts"
SUBCOMMANDS = {"add", "remove", "list"}  # sous-commandes de /webadmin


def _bot_commands() -> set[str]:
    names = set()
    for file in [ROOT / "bot.py", *(ROOT / "Service").glob("*.py")]:
        names |= set(re.findall(r'app_commands\.command\(\s*name="([a-z_-]+)"', file.read_text(encoding="utf-8")))
        names |= set(re.findall(r'app_commands\.Group\(\s*name="([a-z_-]+)"', file.read_text(encoding="utf-8")))
        names |= set(re.findall(r'group_name="([a-z_-]+)"', file.read_text(encoding="utf-8")))   # GroupCog
    return names - SUBCOMMANDS


@pytest.mark.skipif(not GUIDE.exists(), reason="repo lilium-site absent")
def test_every_slash_command_is_in_the_site_guide():
    # « webadmin add » documente la commande « webadmin » (sous-commande) : on garde le 1er mot
    documented = set(re.findall(r"name: '([a-z_-]+)[ ']", GUIDE.read_text(encoding="utf-8")))
    bot = _bot_commands()
    assert bot, "aucune commande trouvée dans le code du bot"
    assert sorted(bot - documented) == [], "commandes absentes du guide du site (guide-content.ts)"
    assert sorted(documented - bot) == [], "commandes du guide qui n'existent plus dans le bot"
