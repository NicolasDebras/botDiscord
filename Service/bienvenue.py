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


async def set_welcome(guild_id: int, channel_id: int | None, message: str | None) -> None:
    await db.set_welcome_config(guild_id, channel_id, message)
    await refresh_cache()


async def set_goodbye(guild_id: int, channel_id: int | None, message: str | None) -> None:
    await db.set_goodbye_config(guild_id, channel_id, message)
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
        if not cfg or not cfg["welcome_channel_id"] or not cfg["welcome_message"]:
            return
        channel = member.guild.get_channel(cfg["welcome_channel_id"])
        if not channel:
            return
        try:
            await channel.send(_format(cfg["welcome_message"], member, member.guild))
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        cfg = _configs.get(member.guild.id)
        if not cfg or not cfg["goodbye_channel_id"] or not cfg["goodbye_message"]:
            return
        channel = member.guild.get_channel(cfg["goodbye_channel_id"])
        if not channel:
            return
        try:
            await channel.send(_format(cfg["goodbye_message"], member, member.guild))
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Bienvenue(bot))
