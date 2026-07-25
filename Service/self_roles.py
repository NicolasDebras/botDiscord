import discord
from discord.ext import commands

import db

# ── CACHE EN MÉMOIRE {message_id: {channel_id, guild_id, roles}} ───────────────
_menus: dict[int, dict] = {}


async def refresh_cache() -> None:
    global _menus
    _menus = {m["message_id"]: m for m in await db.get_all_self_role_menus()}


def list_menus(guild_id: int) -> list[dict]:
    return [{**m, "message_id": mid} for mid, m in _menus.items() if m["guild_id"] == guild_id]


async def create_menu(message_id: int, channel_id: int, guild_id: int, roles: list[dict]) -> None:
    await db.add_self_role_menu(message_id, channel_id, guild_id, roles)
    await refresh_cache()


async def delete_menu(message_id: int) -> None:
    await db.delete_self_role_menu(message_id)
    await refresh_cache()


class RoleToggleButton(discord.ui.Button):
    def __init__(self, message_id: int, role_id: int, label: str):
        super().__init__(
            label=label[:80],
            style=discord.ButtonStyle.secondary,
            custom_id=f"selfrole_{message_id}_{role_id}",
        )
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message("❌ Ce rôle n'existe plus.", ephemeral=True)
            return

        member = interaction.user
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Auto-rôle (bouton)")
                await interaction.response.send_message(f"🔄 Rôle {role.mention} retiré.", ephemeral=True)
            else:
                await member.add_roles(role, reason="Auto-rôle (bouton)")
                await interaction.response.send_message(f"✅ Rôle {role.mention} attribué !", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                "⛔ Je n'ai pas la permission de gérer ce rôle — vérifie que le rôle du bot est "
                "bien AU-DESSUS de ce rôle dans la liste des rôles, et qu'il a la permission Gérer les rôles.",
                ephemeral=True,
            )


def build_view(message_id: int, roles: list[dict]) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for i, r in enumerate(roles):
        button = RoleToggleButton(message_id, r["role_id"], r["label"])
        button.row = i // 5
        view.add_item(button)
    return view


class SelfRoles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        await refresh_cache()
        for message_id, menu in _menus.items():
            try:
                self.bot.add_view(build_view(message_id, menu["roles"]), message_id=message_id)
            except Exception as e:
                print(f"[self_roles] Erreur add_view {message_id}: {type(e).__name__}: {e}")
        print(f"   {len(_menus)} menu(x) de rôles auto-attribuables rechargé(s).")


async def setup(bot: commands.Bot):
    await bot.add_cog(SelfRoles(bot))
