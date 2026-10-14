"""Les erreurs des MP de validation et du nettoyage des vocaux temporaires sont rattachées
à leur serveur : sinon elles n'apparaissent dans aucun /errors (filtré par serveur)."""
import asyncio
from types import SimpleNamespace

from Service import activites, vocal_temp


def _capture(monkeypatch, module):
    logged = []

    async def fake_log_error(source, error, guild_id=None, user_id=None):
        logged.append({"source": source, "guild_id": guild_id, "user_id": user_id})

    monkeypatch.setattr(module, "log_error", fake_log_error)
    return logged


def test_validation_dm_error_is_logged_for_the_activity_guild(monkeypatch):
    logged = _capture(monkeypatch, activites)

    class Boom:
        async def send(self, *args, **kwargs):
            raise RuntimeError("Discord en panne")

    client = SimpleNamespace(get_user=lambda uid: Boom())
    sent = asyncio.run(activites._dm(client, 42, "salut", guild_id=111))
    assert sent is False
    assert logged == [{"source": "activites.validation_dm", "guild_id": 111, "user_id": 42}]


def test_temp_voice_cleanup_error_is_logged_for_the_channel_guild(monkeypatch):
    logged = _capture(monkeypatch, vocal_temp)
    monkeypatch.setattr(vocal_temp, "_temp_channels", {7: {"guild_id": 222, "owner_id": 1, "hub_id": 2}})
    cog = vocal_temp.VocalTemp.__new__(vocal_temp.VocalTemp)

    async def boom(channel_id):
        vocal_temp._temp_channels.pop(channel_id, None)   # le nettoyage retire le salon avant d'échouer
        raise RuntimeError("API Discord")

    cog._cleanup_channel = boom
    asyncio.run(cog._safe_cleanup_channel(7))
    assert logged == [{"source": "vocal_temp.cleanup_channel", "guild_id": 222, "user_id": None}]
