import os
import discord
from discord.ext import commands
import asyncio

from config import TOKEN
import db

# ── INTENTS ──────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ── LISTE DES COGS À CHARGER ─────────────────────────────────────────────────
EXTENSIONS = [
    "Service.activites",
    "Service.admin",
    "Service.bal",
    "Service.massup",
]


# ── EVENTS ───────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    # Vider les commandes globales (évite le doublon global + guild)
    bot.tree.clear_commands(guild=None)
    await bot.tree.sync(guild=None)

    for guild in bot.guilds:
        bot.tree.clear_commands(guild=guild)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"   {len(synced)} slash command(s) synchronisées sur {guild.name} ({guild.id})")
    print(f"✅ Bot connecté en tant que {bot.user}  ({bot.user.id})")
    print(f"   Cogs chargés : {', '.join(EXTENSIONS)}")


# ── LANCEMENT ────────────────────────────────────────────────────────────────
async def main():
    # Connexion PostgreSQL
    database_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL introuvable dans les variables d'environnement.")
    await db.init_db(database_url)
    print("✅ Base de données connectée.")

    async with bot:
        for ext in EXTENSIONS:
            try:
                await bot.load_extension(ext)
                print(f"   ✔ {ext} chargé")
            except Exception as e:
                print(f"   ✖ Erreur chargement {ext} : {e}")
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
