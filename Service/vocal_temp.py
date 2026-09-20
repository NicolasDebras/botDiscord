import discord
from discord.ext import commands, tasks

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


async def _resolve_channel(bot: commands.Bot, channel_id: int) -> discord.abc.GuildChannel | None:
    """Comme bot.get_channel, mais vérifie via l'API en cas de cache manquant
    au lieu de considérer le salon comme supprimé à tort."""
    channel = bot.get_channel(channel_id)
    if channel is not None:
        return channel
    try:
        return await bot.fetch_channel(channel_id)
    except discord.NotFound:
        return None
    except discord.HTTPException:
        return "unknown"  # panne API temporaire : ne pas conclure à une suppression


class VocalTemp(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.cleanup_empty_channels.start()

    async def cog_unload(self):
        self.cleanup_empty_channels.cancel()

    async def _cleanup_channel(self, channel_id: int) -> None:
        channel = await _resolve_channel(self.bot, channel_id)
        if channel == "unknown":
            return  # panne API : on retentera au prochain passage
        if channel is None:
            _temp_channels.pop(channel_id, None)
            await db.delete_temp_voice_channel(channel_id)
            return
        if not channel.members:
            try:
                await channel.delete(reason="Nettoyage salon vocal temporaire vide")
            except discord.HTTPException:
                pass
            _temp_channels.pop(channel_id, None)
            await db.delete_temp_voice_channel(channel_id)

    @commands.Cog.listener()
    async def on_ready(self):
        await refresh_cache()
        for channel_id in list(_temp_channels.keys()):
            await self._cleanup_channel(channel_id)
        await refresh_cache()
        print(f"   {len(_hubs)} hub(s) vocal(aux), {len(_temp_channels)} salon(s) temporaire(s) rechargé(s).")

    # ── Filet de sécurité : rattrape les salons jamais nettoyés par l'event
    # (ex : déconnexion sale, event manqué, cache pas encore prêt au démarrage) ──
    @tasks.loop(minutes=2)
    async def cleanup_empty_channels(self):
        for channel_id in list(_temp_channels.keys()):
            await self._cleanup_channel(channel_id)

    @cleanup_empty_channels.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

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

            # Reprend les permissions de la catégorie (rôles autorisés/refusés)
            # puis ajoute les droits de gestion du créateur par-dessus.
            overwrites = dict(category.overwrites) if isinstance(category, discord.CategoryChannel) else {}
            member_overwrite = overwrites.get(member, discord.PermissionOverwrite())
            member_overwrite.update(manage_channels=True, move_members=True, mute_members=True, deafen_members=True)
            overwrites[member] = member_overwrite

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
