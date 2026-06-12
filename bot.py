import os
import discord
from discord.ext import commands
import asyncio

from config import TOKEN, GUILD_ID, RECRUTEMENT_GUILD_ID, GUILD_ID_3
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
    "Service.moderation",
    "Service.recrutement",
    "Service.joueur",
    "Service.recrutement_externe",
]


# ── EVENTS ───────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    # Serveur principal — toutes les commandes globales
    g1 = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=g1)
    synced1 = await bot.tree.sync(guild=g1)
    print(f"   {len(synced1)} commande(s) synchronisées sur le serveur principal ({GUILD_ID})")

    # Serveur de recrutement — uniquement les commandes guild-spécifiques
    g2 = discord.Object(id=RECRUTEMENT_GUILD_ID)
    synced2 = await bot.tree.sync(guild=g2)
    print(f"   {len(synced2)} commande(s) synchronisées sur le serveur recrutement ({RECRUTEMENT_GUILD_ID})")

    # Serveur 3 (optionnel) — toutes les commandes globales
    if GUILD_ID_3:
        g3 = discord.Object(id=GUILD_ID_3)
        bot.tree.copy_global_to(guild=g3)
        synced3 = await bot.tree.sync(guild=g3)
        print(f"   {len(synced3)} commande(s) synchronisées sur le serveur 3 ({GUILD_ID_3})")

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
