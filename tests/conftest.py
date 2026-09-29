"""
Variables d'environnement factices posées AVANT tout import du projet —
config.py lit DISCORD_TOKEN/DISCORD_GUILD_ID au niveau module et plante à
l'import si elles sont absentes. Ces valeurs ne servent à aucun appel réseau
dans les tests (aucun test ne se connecte à Discord ni à Postgres).
"""
import os

os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("DISCORD_GUILD_ID", "123456789")
