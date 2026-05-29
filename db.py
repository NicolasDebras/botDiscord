"""
db.py — Couche d'accès PostgreSQL (asyncpg).
Remplace tous les fichiers JSON (activities.json, bal.json, bal_log.json,
templates.json, settings.json).
"""
import json
import asyncpg
from datetime import datetime, timezone

from config import DEFAULT_BAL_RATE

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
                message_id          BIGINT PRIMARY KEY,
                channel_id          BIGINT    NOT NULL,
                creator             TEXT      NOT NULL,
                template            TEXT,
                max_players         INT       NOT NULL,
                bal                 BOOLEAN   NOT NULL DEFAULT FALSE,
                created_at          TIMESTAMPTZ NOT NULL,
                slots               JSONB     NOT NULL DEFAULT '{}',
                waitlist            JSONB     NOT NULL DEFAULT '[]'
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

            CREATE TABLE IF NOT EXISTS player_profiles (
                user_id          TEXT PRIMARY KEY,
                ig_name          TEXT        NOT NULL DEFAULT '',
                initial_pve_fame BIGINT      NOT NULL DEFAULT 0,
                initial_pvp_fame BIGINT      NOT NULL DEFAULT 0,
                current_pve_fame BIGINT      NOT NULL DEFAULT 0,
                current_pvp_fame BIGINT      NOT NULL DEFAULT 0,
                fame_updated_at  TIMESTAMPTZ,
                joined_at        TIMESTAMPTZ,
                acti_count       INT         NOT NULL DEFAULT 0,
                recruitment_info TEXT        NOT NULL DEFAULT '',
                is_membre        BOOLEAN     NOT NULL DEFAULT FALSE
            );
        """)
        # Migrations : colonnes ajoutées après le schéma initial
        for col, default in [
            ("depart",             "'Libre'"),
            ("tier",               "''"),
            ("custom_description", "''"),
        ]:
            await conn.execute(
                f"ALTER TABLE activities ADD COLUMN IF NOT EXISTS {col} TEXT NOT NULL DEFAULT {default}"
            )
        await conn.execute(
            "ALTER TABLE bal ADD COLUMN IF NOT EXISTS is_alerted BOOLEAN NOT NULL DEFAULT FALSE"
        )
        await conn.execute(
            "ALTER TABLE player_profiles ADD COLUMN IF NOT EXISTS recruitment_info TEXT NOT NULL DEFAULT ''"
        )
        await conn.execute(
            "ALTER TABLE player_profiles ADD COLUMN IF NOT EXISTS is_membre BOOLEAN NOT NULL DEFAULT FALSE"
        )
        for col, default in [
            ("current_pve_fame", "0"),
            ("current_pvp_fame", "0"),
        ]:
            await conn.execute(
                f"ALTER TABLE player_profiles ADD COLUMN IF NOT EXISTS {col} BIGINT NOT NULL DEFAULT {default}"
            )
        await conn.execute(
            "ALTER TABLE player_profiles ADD COLUMN IF NOT EXISTS fame_updated_at TIMESTAMPTZ"
        )
        await conn.execute(
            "ALTER TABLE bal_log ADD COLUMN IF NOT EXISTS template TEXT NOT NULL DEFAULT ''"
        )


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
            "creator":            row["creator"],
            "created_at":         created,
            "template":           row["template"],
            "max_players":        row["max_players"],
            "bal":                row["bal"],
            "depart":             row["depart"],
            "tier":               row["tier"],
            "custom_description": row["custom_description"],
            "slots":              slots,
            "channel_id":         row["channel_id"],
            "waitlist":           waitlist,
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
                (message_id, channel_id, creator, template, max_players, bal, created_at, slots, waitlist,
                 depart, tier, custom_description)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10, $11, $12)
            ON CONFLICT (message_id) DO UPDATE SET
                channel_id          = EXCLUDED.channel_id,
                creator             = EXCLUDED.creator,
                template            = EXCLUDED.template,
                max_players         = EXCLUDED.max_players,
                bal                 = EXCLUDED.bal,
                created_at          = EXCLUDED.created_at,
                slots               = EXCLUDED.slots,
                waitlist            = EXCLUDED.waitlist,
                depart              = EXCLUDED.depart,
                tier                = EXCLUDED.tier,
                custom_description  = EXCLUDED.custom_description
        """, msg_id, data["channel_id"], data["creator"], data["template"],
             data["max_players"], data["bal"], created_at, slots_json, waitlist_json,
             data.get("depart", "Libre"), data.get("tier", ""), data.get("custom_description", ""))


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


async def increment_bal_batch(deltas: dict[str, int]) -> dict[str, int]:
    """Incrémente plusieurs soldes en une seule transaction. Retourne {user_id: new_total}."""
    async with _pool.acquire() as conn:
        async with conn.transaction():
            results = {}
            for user_id, delta in deltas.items():
                row = await conn.fetchrow("""
                    INSERT INTO bal (user_id, amount) VALUES ($1, $2)
                    ON CONFLICT (user_id) DO UPDATE SET amount = bal.amount + EXCLUDED.amount
                    RETURNING amount
                """, user_id, delta)
                results[user_id] = row["amount"]
    return results


async def set_bal(user_id: str, amount: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO bal (user_id, amount) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET amount = EXCLUDED.amount
        """, user_id, amount)


# ── BAL LOG ───────────────────────────────────────────────────────────────────

async def append_bal_log(action: str, by: str, entries: list, template: str = "") -> None:
    ts           = datetime.now(timezone.utc)
    entries_json = json.dumps(entries, ensure_ascii=False)
    async with _pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO bal_log (ts, action, by_user, entries, template) VALUES ($1, $2, $3, $4::jsonb, $5)",
            ts, action, by, entries_json, template,
        )
        await conn.execute(
            "DELETE FROM bal_log WHERE ts < NOW() - INTERVAL '6 months'"
        )


async def get_silver_stats(days: int = 7) -> list:
    """Retourne le silver distribué (deltas positifs) par type d'action sur les N derniers jours.
    Pour finacti et paybal, distingue les calls RAID AVA des autres."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                CASE
                    WHEN action IN ('finacti', 'paybal') AND template ILIKE '%RAID AVA%'
                        THEN action || '_raid_ava'
                    ELSE action
                END                                            AS action_key,
                template,
                COUNT(DISTINCT id)                             AS nb_actions,
                SUM((elem->>'delta')::bigint)                  AS total_silver,
                COUNT(DISTINCT elem->>'uid')                   AS nb_joueurs
            FROM bal_log,
                 jsonb_array_elements(entries) AS elem
            WHERE ts >= NOW() - ($1 * INTERVAL '1 day')
              AND (elem->>'delta')::bigint > 0
            GROUP BY action_key, template
            ORDER BY total_silver DESC
        """, days)
    return [
        {
            "action":       r["action_key"],
            "template":     r["template"],
            "nb_actions":   r["nb_actions"],
            "total_silver": r["total_silver"],
            "nb_joueurs":   r["nb_joueurs"],
        }
        for r in rows
    ]


async def get_bal_log(action: str | None = None) -> list:
    async with _pool.acquire() as conn:
        if action:
            rows = await conn.fetch(
                "SELECT ts, action, by_user, entries FROM bal_log WHERE action = $1 ORDER BY id DESC LIMIT 1000",
                action,
            )
        else:
            rows = await conn.fetch(
                "SELECT ts, action, by_user, entries FROM bal_log ORDER BY id DESC LIMIT 1000"
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

async def get_image_overrides() -> dict:
    """Retourne toutes les overrides d'image {template_name: url}."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT key, value FROM settings WHERE key LIKE 'img:%'")
    return {row["key"][4:]: row["value"] for row in rows}


async def get_is_alerted(user_id: str) -> bool:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_alerted FROM bal WHERE user_id = $1", user_id)
    return row["is_alerted"] if row else False


async def set_is_alerted(user_id: str, value: bool) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO bal (user_id, amount, is_alerted) VALUES ($1, 0, $2)
            ON CONFLICT (user_id) DO UPDATE SET is_alerted = EXCLUDED.is_alerted
        """, user_id, value)


async def set_image_override(template_name: str, url: str) -> None:
    await set_setting(f"img:{template_name}", url)


async def get_description_overrides() -> dict:
    """Retourne toutes les overrides de description {template_name: description}."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT key, value FROM settings WHERE key LIKE 'desc:%'")
    return {row["key"][5:]: row["value"] for row in rows}


async def set_description_override(template_name: str, desc: str) -> None:
    await set_setting(f"desc:{template_name}", desc)


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


# ── PLAYER PROFILES ───────────────────────────────────────────────────────────

async def get_player_profile(user_id: str) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM player_profiles WHERE user_id = $1", user_id)
    if not row:
        return None
    return {
        "user_id":          row["user_id"],
        "ig_name":          row["ig_name"],
        "initial_pve_fame": row["initial_pve_fame"],
        "initial_pvp_fame": row["initial_pvp_fame"],
        "joined_at":        row["joined_at"],
        "acti_count":       row["acti_count"],
        "recruitment_info": row["recruitment_info"],
        "is_membre":        row["is_membre"],
        "current_pve_fame": row["current_pve_fame"],
        "current_pvp_fame": row["current_pvp_fame"],
        "fame_updated_at":  row["fame_updated_at"],
    }


async def save_player_profile(user_id: str, ig_name: str, initial_pve: int, initial_pvp: int, recruitment_info: str = "", is_membre: bool = False) -> None:
    joined_at = datetime.now(timezone.utc)
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO player_profiles (user_id, ig_name, initial_pve_fame, initial_pvp_fame, joined_at, recruitment_info, is_membre)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (user_id) DO UPDATE SET
                ig_name          = EXCLUDED.ig_name,
                initial_pve_fame = EXCLUDED.initial_pve_fame,
                initial_pvp_fame = EXCLUDED.initial_pvp_fame,
                joined_at        = EXCLUDED.joined_at,
                recruitment_info = EXCLUDED.recruitment_info,
                is_membre        = EXCLUDED.is_membre
        """, user_id, ig_name, initial_pve, initial_pvp, joined_at, recruitment_info, is_membre)


async def get_pending_new_players(min_days: int = 14) -> list[dict]:
    """Nouveaux joueurs (is_membre=FALSE) présents depuis plus de min_days jours."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT user_id, ig_name, joined_at FROM player_profiles
            WHERE is_membre = FALSE
              AND joined_at IS NOT NULL
              AND joined_at <= NOW() - ($1 * INTERVAL '1 day')
            ORDER BY joined_at ASC
        """, min_days)
    return [{"user_id": r["user_id"], "ig_name": r["ig_name"], "joined_at": r["joined_at"]} for r in rows]


async def get_all_profiles() -> list[dict]:
    """Retourne tous les profils recrutés."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, ig_name, joined_at, is_membre FROM player_profiles")
    return [{"user_id": r["user_id"], "ig_name": r["ig_name"], "joined_at": r["joined_at"], "is_membre": r["is_membre"]} for r in rows]


async def set_player_is_membre(user_id: str, value: bool) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE player_profiles SET is_membre = $2 WHERE user_id = $1",
            user_id, value,
        )


async def update_player_igname(user_id: str, ig_name: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE player_profiles SET ig_name = $2 WHERE user_id = $1",
            user_id, ig_name,
        )


async def update_player_fame(user_id: str, ig_name: str, pve: int, pvp: int) -> None:
    updated_at = datetime.now(timezone.utc)
    async with _pool.acquire() as conn:
        await conn.execute("""
            UPDATE player_profiles
            SET ig_name = $2, current_pve_fame = $3, current_pvp_fame = $4, fame_updated_at = $5
            WHERE user_id = $1
        """, user_id, ig_name, pve, pvp, updated_at)


async def postpone_player_check(user_id: str, days: int = 7) -> None:
    """Repousse le suivi d'un joueur de `days` jours en décalant joined_at."""
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE player_profiles SET joined_at = joined_at + ($2 * INTERVAL '1 day') WHERE user_id = $1",
            user_id, days,
        )


async def delete_player_profile(user_id: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM player_profiles WHERE user_id = $1", user_id)


async def increment_acti_count(user_ids: list[str]) -> None:
    async with _pool.acquire() as conn:
        async with conn.transaction():
            for user_id in user_ids:
                await conn.execute("""
                    INSERT INTO player_profiles (user_id, acti_count)
                    VALUES ($1, 1)
                    ON CONFLICT (user_id) DO UPDATE SET acti_count = player_profiles.acti_count + 1
                """, user_id)
