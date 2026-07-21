import discord
from discord.ext import commands

import db

# ── CACHE EN MÉMOIRE {guild_id: {welcome_channel_id, welcome_message, goodbye_channel_id, goodbye_message}} ─
_configs: dict[int, dict] = {}


async def refresh_cache() -> None:
    global _configs
    _configs = await db.get_all_member_events_configs()


def _format(template: str, member: discord.Member | discord.User, guild: discord.Guild) -> str:
    return (
        template
        .replace("{mention}", member.mention)
        .replace("{pseudo}", member.display_name)
        .replace("{nom}", str(member))
        .replace("{serveur}", guild.name)
        .replace("{membercount}", str(guild.member_count))
    )


async def set_welcome(guild_id: int, channel_id: int | None, message: str | None, image: str | None = None) -> None:
    await db.set_welcome_config(guild_id, channel_id, message, image)
    await refresh_cache()


async def set_goodbye(guild_id: int, channel_id: int | None, message: str | None) -> None:
    await db.set_goodbye_config(guild_id, channel_id, message)
    await refresh_cache()


async def set_default_role(guild_id: int, role_id: int | None) -> None:
    await db.set_default_role(guild_id, role_id)
    await refresh_cache()


class Bienvenue(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        await refresh_cache()
        print(f"   {len(_configs)} config(s) bienvenue/au revoir rechargée(s).")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = _configs.get(member.guild.id)
        if not cfg:
            return

        if cfg["default_role_id"]:
            role = member.guild.get_role(cfg["default_role_id"])
            if not role:
                print(f"[bienvenue] Rôle par défaut introuvable (ID {cfg['default_role_id']}) sur {member.guild.name}.")
            else:
                try:
                    await member.add_roles(role, reason="Rôle par défaut à l'arrivée")
                except discord.Forbidden:
                    print(
                        f"[bienvenue] ⛔ Impossible d'attribuer le rôle {role.name} à {member} sur {member.guild.name} — "
                        f"vérifie que le rôle du bot est bien AU-DESSUS de {role.name} dans la liste des rôles, "
                        f"et qu'il a la permission Gérer les rôles."
                    )

        if cfg["welcome_channel_id"] and cfg["welcome_message"]:
            channel = member.guild.get_channel(cfg["welcome_channel_id"])
            if channel:
                embed = discord.Embed(
                    title=f"🎉 Bienvenue sur {member.guild.name} !",
                    description=_format(cfg["welcome_message"], member, member.guild),
                    color=0x2ECC71,
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                if cfg.get("welcome_image"):
                    embed.set_image(url=cfg["welcome_image"])
                embed.set_footer(text=f"Membre #{member.guild.member_count}")
                try:
                    await channel.send(content=member.mention, embed=embed)
                except discord.Forbidden:
                    print(f"[bienvenue] ⛔ Impossible d'envoyer le message de bienvenue sur {member.guild.name} (permissions du salon).")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        cfg = _configs.get(member.guild.id)
        if not cfg or not cfg["goodbye_channel_id"] or not cfg["goodbye_message"]:
            return
        channel = member.guild.get_channel(cfg["goodbye_channel_id"])
        if not channel:
            return
        embed = discord.Embed(
            title=f"👋 Départ de {member.guild.name}",
            description=_format(cfg["goodbye_message"], member, member.guild),
            color=0xE74C3C,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            print(f"[bienvenue] ⛔ Impossible d'envoyer le message d'au revoir sur {member.guild.name} (permissions du salon).")


async def setup(bot: commands.Bot):
    await bot.add_cog(Bienvenue(bot))
