import os
import traceback
import discord
from discord import app_commands
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
    "Service.moderation",
    "Service.recrutement",
    "Service.joueur",
    "Service.recrutement_externe",
    "Service.vocal_temp",
    "Service.bienvenue",
    "Service.self_roles",
    "Service.config",
    "Service.location",
    "Service.errors",
    "Service.web_admin",
]


# ── ERREURS SLASH COMMANDS ───────────────────────────────────────────────────
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    original = getattr(error, "original", error)
    cmd_name = interaction.command.name if interaction.command else "?"
    print(f"[slash command error] /{cmd_name} : {type(original).__name__}: {original}")
    tb_str = "".join(traceback.format_exception(type(original), original, original.__traceback__))
    print(tb_str)

    try:
        await db.add_error_log(
            command=cmd_name,
            error_type=type(original).__name__,
            error_message=str(original),
            traceback_str=tb_str,
            guild_id=interaction.guild.id if interaction.guild else None,
            user_id=str(interaction.user.id) if interaction.user else None,
        )
    except Exception as e:
        print(f"[slash command error] Impossible d'enregistrer l'erreur en base : {e}")

    message = f"❌ Erreur dans `/{cmd_name}` : `{type(original).__name__}: {original}`"
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        pass


# ── EVENTS ───────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    # Sync des commandes sur tous les serveurs où le bot est installé
    for guild in bot.guilds:
        g = discord.Object(id=guild.id)
        try:
            bot.tree.copy_global_to(guild=g)
            synced = await bot.tree.sync(guild=g)
            print(f"   {len(synced)} commande(s) synchronisées sur {guild.name} ({guild.id})")
        except discord.HTTPException as e:
            print(f"   ✖ Erreur de synchronisation sur {guild.name} ({guild.id}) : {e}")

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
