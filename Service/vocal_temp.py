import discord
from discord.ext import commands

import db

# ── CACHES EN MÉMOIRE ─────────────────────────────────────────────────────────
# {hub_channel_id: {channel_id, guild_id, category_id, name_template, user_limit}}
_hubs: dict[int, dict] = {}
# {temp_channel_id: {guild_id, owner_id, hub_id}}
_temp_channels: dict[int, dict] = {}


async def refresh_cache() -> None:
    global _hubs, _temp_channels
    _hubs = {h["channel_id"]: h for h in await db.get_all_voice_hubs()}
    _temp_channels = {t["channel_id"]: t for t in await db.get_all_temp_voice_channels()}


def list_hubs(guild_id: int) -> list[dict]:
    return [h for h in _hubs.values() if h["guild_id"] == guild_id]


async def add_hub(
    channel_id: int, guild_id: int, category_id: int | None,
    name_template: str = "🔊 {pseudo}", user_limit: int = 0,
) -> None:
    await db.add_voice_hub(channel_id, guild_id, category_id, name_template, user_limit)
    await refresh_cache()


async def update_hub(channel_id: int, name_template: str, user_limit: int) -> None:
    await db.update_voice_hub(channel_id, name_template, user_limit)
    await refresh_cache()


async def remove_hub(channel_id: int) -> None:
    await db.delete_voice_hub(channel_id)
    await refresh_cache()


class VocalTemp(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        await refresh_cache()

        # Nettoyage : salons temp en DB qui n'existent plus ou sont vides
        for channel_id in list(_temp_channels.keys()):
            channel = self.bot.get_channel(channel_id)
            if channel is None or not channel.members:
                if channel is not None:
                    try:
                        await channel.delete(reason="Nettoyage salon vocal temporaire vide")
                    except discord.HTTPException:
                        pass
                await db.delete_temp_voice_channel(channel_id)

        await refresh_cache()
        print(f"   {len(_hubs)} hub(s) vocal(aux), {len(_temp_channels)} salon(s) temporaire(s) rechargé(s).")

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ):
        # ── Rejoint un hub → création du salon temporaire ──────────────────────
        if after.channel and after.channel.id in _hubs:
            hub = _hubs[after.channel.id]
            category = member.guild.get_channel(hub["category_id"]) if hub["category_id"] else after.channel.category
            if not isinstance(category, discord.CategoryChannel):
                category = after.channel.category

            name = hub["name_template"].replace("{pseudo}", member.display_name)[:100]

            overwrites = {
                member: discord.PermissionOverwrite(
                    manage_channels=True, move_members=True, mute_members=True, deafen_members=True,
                ),
            }

            try:
                channel = await member.guild.create_voice_channel(
                    name=name,
                    category=category,
                    user_limit=hub["user_limit"] or None,
                    overwrites=overwrites,
                    reason=f"Salon vocal temporaire pour {member}",
                )
                await member.move_to(channel, reason="Salon vocal temporaire")
            except discord.HTTPException:
                pass
            else:
                await db.add_temp_voice_channel(channel.id, member.guild.id, member.id, after.channel.id)
                _temp_channels[channel.id] = {"guild_id": member.guild.id, "owner_id": member.id, "hub_id": after.channel.id}

        # ── Quitte un salon temporaire devenu vide → suppression ───────────────
        if before.channel and before.channel.id in _temp_channels and not before.channel.members:
            try:
                await before.channel.delete(reason="Salon vocal temporaire vide")
            except discord.HTTPException:
                pass
            _temp_channels.pop(before.channel.id, None)
            await db.delete_temp_voice_channel(before.channel.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(VocalTemp(bot))
