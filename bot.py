import discord
from discord.ext import commands
import asyncio

from config import TOKEN, GUILD_ID

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
    guild = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)
    print(f"✅ Bot connecté en tant que {bot.user}  ({bot.user.id})")
    print(f"   Cogs chargés : {', '.join(EXTENSIONS)}")
    print(f"   {len(synced)} slash command(s) synchronisées sur le serveur {GUILD_ID}.")


# ── LANCEMENT ────────────────────────────────────────────────────────────────
async def main():
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
