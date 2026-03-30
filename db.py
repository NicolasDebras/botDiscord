"""
db.py — Couche d'accès PostgreSQL (asyncpg).
Remplace tous les fichiers JSON (activities.json, bal.json, bal_log.json,
templates.json, settings.json).
"""
import json
import asyncpg
from datetime import datetime, timezone

from config import BAL_LOG_MAX, DEFAULT_BAL_RATE

_pool: asyncpg.Pool | None = None


def _jloads(v):
    """Décode du JSONB : renvoie v tel quel si déjà un dict/list, sinon json.loads."""
    if isinstance(v, (dict, list)):
        return v
    return json.loads(v)


# ── INIT ──────────────────────────────────────────────────────────────────────

async def init_db(database_url: str) -> None:
    global _pool
    _pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                message_id   BIGINT PRIMARY KEY,
                channel_id   BIGINT    NOT NULL,
                creator      TEXT      NOT NULL,
                template     TEXT,
                max_players  INT       NOT NULL,
                bal          BOOLEAN   NOT NULL DEFAULT FALSE,
                created_at   TIMESTAMPTZ NOT NULL,
                slots        JSONB     NOT NULL DEFAULT '{}',
                waitlist     JSONB     NOT NULL DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS bal (
                user_id  TEXT PRIMARY KEY,
                amount   INT  NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS bal_log (
                id       SERIAL PRIMARY KEY,
                ts       TIMESTAMPTZ NOT NULL,
                action   TEXT        NOT NULL,
                by_user  TEXT        NOT NULL,
                entries  JSONB       NOT NULL
            );

            CREATE TABLE IF NOT EXISTS custom_templates (
                name  TEXT PRIMARY KEY,
                data  JSONB NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key    TEXT PRIMARY KEY,
                value  TEXT NOT NULL
            );
        """)


# ── ACTIVITIES ────────────────────────────────────────────────────────────────

async def load_activities() -> dict:
    """Retourne toutes les activités sous forme {message_id: data}."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM activities")
    result = {}
    for row in rows:
        msg_id    = row["message_id"]
        slots_raw = _jloads(row["slots"])
        slots     = {
            role: [(e[0], e[1], e[2] if len(e) > 2 else "") for e in members]
            for role, members in slots_raw.items()
        }
        wl_raw   = _jloads(row["waitlist"])
        waitlist = [(e[0], e[1]) for e in wl_raw]
        created  = row["created_at"]
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        result[msg_id] = {
            "creator":     row["creator"],
            "created_at":  created,
            "template":    row["template"],
            "max_players": row["max_players"],
            "bal":         row["bal"],
            "slots":       slots,
            "channel_id":  row["channel_id"],
            "waitlist":    waitlist,
        }
    return result


async def save_activity(msg_id: int, data: dict) -> None:
    """Insère ou met à jour une activité."""
    slots_json = json.dumps({
        role: [list(e) for e in members]
        for role, members in data["slots"].items()
    })
    waitlist_json = json.dumps([[uid, name] for uid, name in data.get("waitlist", [])])
    created_at = data["created_at"]
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO activities
                (message_id, channel_id, creator, template, max_players, bal, created_at, slots, waitlist)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb)
            ON CONFLICT (message_id) DO UPDATE SET
                channel_id   = EXCLUDED.channel_id,
                creator      = EXCLUDED.creator,
                template     = EXCLUDED.template,
                max_players  = EXCLUDED.max_players,
                bal          = EXCLUDED.bal,
                created_at   = EXCLUDED.created_at,
                slots        = EXCLUDED.slots,
                waitlist     = EXCLUDED.waitlist
        """, msg_id, data["channel_id"], data["creator"], data["template"],
             data["max_players"], data["bal"], created_at, slots_json, waitlist_json)


async def delete_activity(msg_id: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM activities WHERE message_id = $1", msg_id)


# ── BAL ───────────────────────────────────────────────────────────────────────

async def get_all_bal() -> dict:
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, amount FROM bal")
    return {row["user_id"]: row["amount"] for row in rows}


async def get_bal(user_id: str) -> int:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT amount FROM bal WHERE user_id = $1", user_id)
    return row["amount"] if row else 0


async def increment_bal(user_id: str, delta: int) -> int:
    """Incrémente (ou décrémente si delta < 0) le solde et retourne le nouveau total."""
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO bal (user_id, amount) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET amount = bal.amount + EXCLUDED.amount
            RETURNING amount
        """, user_id, delta)
    return row["amount"]


async def set_bal(user_id: str, amount: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO bal (user_id, amount) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET amount = EXCLUDED.amount
        """, user_id, amount)


# ── BAL LOG ───────────────────────────────────────────────────────────────────

async def append_bal_log(action: str, by: str, entries: list) -> None:
    ts           = datetime.now(timezone.utc)
    entries_json = json.dumps(entries, ensure_ascii=False)
    async with _pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO bal_log (ts, action, by_user, entries) VALUES ($1, $2, $3, $4::jsonb)",
            ts, action, by, entries_json,
        )
        # Conserver uniquement les BAL_LOG_MAX dernières entrées
        await conn.execute(f"""
            DELETE FROM bal_log WHERE id NOT IN (
                SELECT id FROM bal_log ORDER BY id DESC LIMIT {BAL_LOG_MAX}
            )
        """)


async def get_bal_log() -> list:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ts, action, by_user, entries FROM bal_log ORDER BY id DESC LIMIT $1",
            BAL_LOG_MAX,
        )
    return [
        {
            "ts":      row["ts"].strftime("%Y-%m-%dT%H:%M:%S"),
            "action":  row["action"],
            "by":      row["by_user"],
            "entries": _jloads(row["entries"]),
        }
        for row in rows
    ]


# ── CUSTOM TEMPLATES ──────────────────────────────────────────────────────────

async def get_custom_templates() -> dict:
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT name, data FROM custom_templates")
    return {row["name"]: _jloads(row["data"]) for row in rows}


async def save_custom_template(name: str, data: dict) -> None:
    data_json = json.dumps(data, ensure_ascii=False)
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO custom_templates (name, data) VALUES ($1, $2::jsonb)
            ON CONFLICT (name) DO UPDATE SET data = EXCLUDED.data
        """, name, data_json)


async def delete_custom_template(name: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM custom_templates WHERE name = $1", name)


# ── SETTINGS ──────────────────────────────────────────────────────────────────

async def get_setting(key: str, default: str = "") -> str:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM settings WHERE key = $1", key)
    return row["value"] if row else default


async def set_setting(key: str, value: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO settings (key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, key, value)
