import os
import traceback
import discord
from discord import app_commands
from discord.ext import commands
import asyncio

from config import ALLOWED_GUILD_IDS, TOKEN
import db

# ── INTENTS ──────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Par défaut : jamais de ping @everyone/@here ni de rôle, même si un texte saisi par un joueur en contient
# (/massup message, pseudos…). Les pings de rôle voulus passent allowed_mentions explicitement.
bot = commands.Bot(
    command_prefix="!", intents=intents,
    allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=True),
)

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

    # Erreur interne (exception dans la commande) : pas de détail technique aux joueurs, il est dans /errors.
    # Les autres (paramètre invalide, check…) sont des messages discord.py destinés à l'utilisateur.
    if isinstance(error, app_commands.CommandInvokeError):
        message = f"❌ Erreur dans `/{cmd_name}` — détail enregistré pour le staff (`/errors`)."
    else:
        message = f"❌ Erreur dans `/{cmd_name}` : {error}"
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        pass


# ── EVENTS ───────────────────────────────────────────────────────────────────
def _guild_allowed(guild: discord.Guild) -> bool:
    return not ALLOWED_GUILD_IDS or guild.id in ALLOWED_GUILD_IDS


@bot.event
async def on_guild_join(guild: discord.Guild):
    if not _guild_allowed(guild):
        print(f"   ⛔ Serveur non autorisé {guild.name} ({guild.id}) — le bot le quitte.")
        await guild.leave()


@bot.event
async def on_ready():
    for guild in list(bot.guilds):
        if not _guild_allowed(guild):
            print(f"   ⛔ Serveur non autorisé {guild.name} ({guild.id}) — le bot le quitte.")
            await guild.leave()
    if not ALLOWED_GUILD_IDS:
        print("   🌍 Bot public : accepté sur tous les serveurs (ALLOWED_GUILD_IDS non défini).")

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
