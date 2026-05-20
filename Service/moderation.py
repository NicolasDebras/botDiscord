import re
import discord
from discord.ext import commands

_ACTI_FLASH_ID = 1466726574509260943
_FORMAT_RE     = re.compile(r"^\d{2}/\d{2}\s*-\s*\d{2}[hH]\d{2}\s*-\s*.+", re.DOTALL)


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id != _ACTI_FLASH_ID:
            return
        if _FORMAT_RE.match(message.content):
            return

        try:
            await message.delete()
        except discord.Forbidden:
            return

        try:
            await message.author.send(
                f"❌ Ton message dans <#{_ACTI_FLASH_ID}> a été supprimé — format invalide.\n\n"
                f"**Format attendu :** `JJ/MM - HHhMM - Nom de l'activité`\n"
                f"**Exemple :** `21/05 - 21h30 - RAID AVA`"
            )
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
