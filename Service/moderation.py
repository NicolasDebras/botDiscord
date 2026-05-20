import re
import discord
from discord.ext import commands

_ACTI_FLASH_ID = 1466726574509260943
_FORMAT_RE     = re.compile(r"^\d{2}/\d{2}\s*-\s*\d{2}[hH]\d{2}\s*-\s*.+", re.DOTALL)


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        if thread.parent_id != _ACTI_FLASH_ID:
            return
        if _FORMAT_RE.match(thread.name):
            return

        owner_id = thread.owner_id
        try:
            await thread.delete()
        except discord.Forbidden:
            return

        try:
            user = await self.bot.fetch_user(owner_id)
            await user.send(
                f"❌ Ton post dans <#{_ACTI_FLASH_ID}> a été supprimé — format invalide.\n\n"
                f"**Format attendu :** `JJ/MM - HHhMM - Nom de l'activité`\n"
                f"**Exemple :** `21/05 - 21h30 - RAID AVA`"
            )
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
