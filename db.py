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
        from config import GUILD_ID as _GUILD_ID_ACT
        await conn.execute(
            "ALTER TABLE activities ADD COLUMN IF NOT EXISTS guild_id BIGINT NOT NULL DEFAULT 0"
        )
        await conn.execute(f"UPDATE activities SET guild_id = {_GUILD_ID_ACT} WHERE guild_id = 0")
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
        await conn.execute(
            "ALTER TABLE player_profiles ADD COLUMN IF NOT EXISTS last_acti_at TIMESTAMPTZ"
        )
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS recruitment_tickets (
                user_id    TEXT PRIMARY KEY,
                thread_id  BIGINT      NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            )
        """)

        # ── Migration guild_id sur bal ────────────────────────────────────────
        await conn.execute(
            "ALTER TABLE bal ADD COLUMN IF NOT EXISTS guild_id BIGINT NOT NULL DEFAULT 0"
        )
        # Backfill : données existantes → serveur principal
        from config import GUILD_ID as _GUILD_ID
        await conn.execute(f"UPDATE bal SET guild_id = {_GUILD_ID} WHERE guild_id = 0")

        # Recréer la PK en composite si elle est encore simple
        pk_cols = await conn.fetch("""
            SELECT column_name FROM information_schema.key_column_usage
            WHERE table_name = 'bal' AND constraint_name = 'bal_pkey'
            ORDER BY ordinal_position
        """)
        if [r['column_name'] for r in pk_cols] == ['user_id']:
            await conn.execute("ALTER TABLE bal DROP CONSTRAINT bal_pkey")
            await conn.execute("ALTER TABLE bal ADD PRIMARY KEY (user_id, guild_id)")

        # ── Migration guild_id sur bal_log ────────────────────────────────────
        await conn.execute(
            "ALTER TABLE bal_log ADD COLUMN IF NOT EXISTS guild_id BIGINT NOT NULL DEFAULT 0"
        )
        await conn.execute(f"UPDATE bal_log SET guild_id = {_GUILD_ID} WHERE guild_id = 0")

        # ── Migration guild_id sur player_profiles ────────────────────────────
        await conn.execute(
            "ALTER TABLE player_profiles ADD COLUMN IF NOT EXISTS guild_id BIGINT NOT NULL DEFAULT 0"
        )
        await conn.execute(f"UPDATE player_profiles SET guild_id = {_GUILD_ID} WHERE guild_id = 0")

        pk_cols_pp = await conn.fetch("""
            SELECT column_name FROM information_schema.key_column_usage
            WHERE table_name = 'player_profiles' AND constraint_name = 'player_profiles_pkey'
            ORDER BY ordinal_position
        """)
        if [r['column_name'] for r in pk_cols_pp] == ['user_id']:
            await conn.execute("ALTER TABLE player_profiles DROP CONSTRAINT player_profiles_pkey")
            await conn.execute("ALTER TABLE player_profiles ADD PRIMARY KEY (user_id, guild_id)")

        # ── Migration guild_id sur custom_templates ───────────────────────────
        await conn.execute(
            "ALTER TABLE custom_templates ADD COLUMN IF NOT EXISTS guild_id BIGINT NOT NULL DEFAULT 0"
        )
        await conn.execute(f"UPDATE custom_templates SET guild_id = {_GUILD_ID} WHERE guild_id = 0")

        pk_cols_ct = await conn.fetch("""
            SELECT column_name FROM information_schema.key_column_usage
            WHERE table_name = 'custom_templates' AND constraint_name = 'custom_templates_pkey'
            ORDER BY ordinal_position
        """)
        if [r['column_name'] for r in pk_cols_ct] == ['name']:
            await conn.execute("ALTER TABLE custom_templates DROP CONSTRAINT custom_templates_pkey")
            await conn.execute("ALTER TABLE custom_templates ADD PRIMARY KEY (name, guild_id)")

        # ── Migration guild_id sur recruitment_tickets ────────────────────────
        await conn.execute(
            "ALTER TABLE recruitment_tickets ADD COLUMN IF NOT EXISTS guild_id BIGINT NOT NULL DEFAULT 0"
        )
        await conn.execute(f"UPDATE recruitment_tickets SET guild_id = {_GUILD_ID} WHERE guild_id = 0")

        pk_cols_rt = await conn.fetch("""
            SELECT column_name FROM information_schema.key_column_usage
            WHERE table_name = 'recruitment_tickets' AND constraint_name = 'recruitment_tickets_pkey'
            ORDER BY ordinal_position
        """)
        if [r['column_name'] for r in pk_cols_rt] == ['user_id']:
            await conn.execute("ALTER TABLE recruitment_tickets DROP CONSTRAINT recruitment_tickets_pkey")
            await conn.execute("ALTER TABLE recruitment_tickets ADD PRIMARY KEY (user_id, guild_id)")

        # ── Migration ancien format img:{nom}/desc:{nom} → img:{guild_id}:{nom} ──
        old_overrides = await conn.fetch(
            "SELECT key, value FROM settings WHERE key LIKE 'img:%' OR key LIKE 'desc:%'"
        )
        for row in old_overrides:
            parts = row["key"].split(":")
            if len(parts) == 2:  # ancien format, pas encore de guild_id dans la clé
                prefix, name = parts
                new_key = f"{prefix}:{_GUILD_ID}:{name}"
                await conn.execute("""
                    INSERT INTO settings (key, value) VALUES ($1, $2)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """, new_key, row["value"])
                await conn.execute("DELETE FROM settings WHERE key = $1", row["key"])

        # ── Config recrutement par serveur ────────────────────────────────────
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS recruitment_config (
                guild_id             BIGINT PRIMARY KEY,
                rules_channel_id     BIGINT,
                category_id          BIGINT,
                recruitment_role_id  BIGINT,
                candidat_role_id     BIGINT
            )
        """)
        await conn.execute(
            "ALTER TABLE recruitment_config ADD COLUMN IF NOT EXISTS validated_role_id BIGINT"
        )

        # ── Salons vocaux temporaires ──────────────────────────────────────────
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS voice_hubs (
                channel_id     BIGINT PRIMARY KEY,
                guild_id       BIGINT NOT NULL,
                category_id    BIGINT,
                name_template  TEXT   NOT NULL DEFAULT '🔊 {pseudo}',
                user_limit     INT    NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS temp_voice_channels (
                channel_id  BIGINT PRIMARY KEY,
                guild_id    BIGINT NOT NULL,
                owner_id    BIGINT NOT NULL,
                hub_id      BIGINT NOT NULL
            );
        """)

        # ── Messages bienvenue / au revoir + rôle par défaut par serveur ───────
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS member_events_config (
                guild_id            BIGINT PRIMARY KEY,
                welcome_channel_id  BIGINT,
                welcome_message     TEXT,
                goodbye_channel_id  BIGINT,
                goodbye_message     TEXT
            )
        """)
        await conn.execute(
            "ALTER TABLE member_events_config ADD COLUMN IF NOT EXISTS default_role_id BIGINT"
        )
        await conn.execute(
            "ALTER TABLE member_events_config ADD COLUMN IF NOT EXISTS welcome_image TEXT"
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
            "guild_id":           row["guild_id"],
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
                (message_id, channel_id, guild_id, creator, template, max_players, bal, created_at, slots, waitlist,
                 depart, tier, custom_description)
            VALUES ($1, $2, $13, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10, $11, $12)
            ON CONFLICT (message_id) DO UPDATE SET
                channel_id          = EXCLUDED.channel_id,
                guild_id            = EXCLUDED.guild_id,
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
             data.get("depart", "Libre"), data.get("tier", ""), data.get("custom_description", ""),
             data.get("guild_id", 0))


async def delete_activity(msg_id: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM activities WHERE message_id = $1", msg_id)


# ── BAL ───────────────────────────────────────────────────────────────────────

async def get_all_bal(guild_id: int = 0) -> dict:
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, amount FROM bal WHERE guild_id = $1", guild_id)
    return {row["user_id"]: row["amount"] for row in rows}


async def get_bal(user_id: str, guild_id: int = 0) -> int:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT amount FROM bal WHERE user_id = $1 AND guild_id = $2", user_id, guild_id
        )
    return row["amount"] if row else 0


async def increment_bal(user_id: str, delta: int, guild_id: int = 0) -> int:
    """Incrémente (ou décrémente si delta < 0) le solde et retourne le nouveau total."""
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO bal (user_id, guild_id, amount) VALUES ($1, $2, $3)
            ON CONFLICT (user_id, guild_id) DO UPDATE SET amount = bal.amount + EXCLUDED.amount
            RETURNING amount
        """, user_id, guild_id, delta)
    return row["amount"]


async def increment_bal_batch(deltas: dict[str, int], guild_id: int = 0) -> dict[str, int]:
    """Incrémente plusieurs soldes en une seule transaction. Retourne {user_id: new_total}."""
    async with _pool.acquire() as conn:
        async with conn.transaction():
            results = {}
            for user_id, delta in deltas.items():
                row = await conn.fetchrow("""
                    INSERT INTO bal (user_id, guild_id, amount) VALUES ($1, $2, $3)
                    ON CONFLICT (user_id, guild_id) DO UPDATE SET amount = bal.amount + EXCLUDED.amount
                    RETURNING amount
                """, user_id, guild_id, delta)
                results[user_id] = row["amount"]
    return results


async def set_bal(user_id: str, amount: int, guild_id: int = 0) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO bal (user_id, guild_id, amount) VALUES ($1, $2, $3)
            ON CONFLICT (user_id, guild_id) DO UPDATE SET amount = EXCLUDED.amount
        """, user_id, guild_id, amount)


# ── BAL LOG ───────────────────────────────────────────────────────────────────

async def append_bal_log(action: str, by: str, entries: list, template: str = "", guild_id: int = 0) -> None:
    ts           = datetime.now(timezone.utc)
    entries_json = json.dumps(entries, ensure_ascii=False)
    async with _pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO bal_log (ts, action, by_user, entries, template, guild_id) VALUES ($1, $2, $3, $4::jsonb, $5, $6)",
            ts, action, by, entries_json, template, guild_id,
        )
        await conn.execute(
            "DELETE FROM bal_log WHERE ts < NOW() - INTERVAL '6 months'"
        )


async def get_silver_stats(days: int = 7, guild_id: int = 0) -> list:
    """Retourne le silver distribué (deltas positifs) par type d'action et template.
    Les actions finacti/paybal RAID AVA sont distinguées des autres.
    Les autres fins d'activité sont détaillées par template."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                CASE
                    WHEN action IN ('finacti', 'paybal') AND template ILIKE '%RAID AVA%'
                        THEN action || '_raid_ava'
                    ELSE action
                END                                            AS action_key,
                CASE
                    WHEN action IN ('finacti', 'paybal') AND template ILIKE '%RAID AVA%'
                        THEN ''
                    ELSE template
                END                                            AS template_label,
                COUNT(DISTINCT id)                             AS nb_actions,
                SUM((elem->>'delta')::bigint)                  AS total_silver,
                COUNT(DISTINCT elem->>'uid')                   AS nb_joueurs
            FROM bal_log,
                 jsonb_array_elements(entries) AS elem
            WHERE ts >= NOW() - ($1 * INTERVAL '1 day')
              AND (elem->>'delta')::bigint > 0
              AND guild_id = $2
            GROUP BY action_key, template_label
            ORDER BY total_silver DESC
        """, days, guild_id)
    return [
        {
            "action":       r["action_key"],
            "template":     r["template_label"],
            "nb_actions":   r["nb_actions"],
            "total_silver": r["total_silver"],
            "nb_joueurs":   r["nb_joueurs"],
        }
        for r in rows
    ]


async def get_bal_log(action: str | None = None, guild_id: int = 0) -> list:
    async with _pool.acquire() as conn:
        if action:
            rows = await conn.fetch(
                "SELECT ts, action, by_user, entries FROM bal_log WHERE action = $1 AND guild_id = $2 ORDER BY id DESC LIMIT 1000",
                action, guild_id,
            )
        else:
            rows = await conn.fetch(
                "SELECT ts, action, by_user, entries FROM bal_log WHERE guild_id = $1 ORDER BY id DESC LIMIT 1000",
                guild_id,
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

async def get_custom_templates() -> dict[int, dict]:
    """Retourne {guild_id: {template_name: data}}."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT name, guild_id, data FROM custom_templates")
    result: dict[int, dict] = {}
    for row in rows:
        result.setdefault(row["guild_id"], {})[row["name"]] = _jloads(row["data"])
    return result


async def save_custom_template(name: str, data: dict, guild_id: int = 0) -> None:
    data_json = json.dumps(data, ensure_ascii=False)
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO custom_templates (name, guild_id, data) VALUES ($1, $2, $3::jsonb)
            ON CONFLICT (name, guild_id) DO UPDATE SET data = EXCLUDED.data
        """, name, guild_id, data_json)


async def delete_custom_template(name: str, guild_id: int = 0) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM custom_templates WHERE name = $1 AND guild_id = $2", name, guild_id)


# ── SETTINGS ──────────────────────────────────────────────────────────────────

async def get_image_overrides() -> dict[int, dict]:
    """Retourne {guild_id: {template_name: url}}."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT key, value FROM settings WHERE key LIKE 'img:%'")
    result: dict[int, dict] = {}
    for row in rows:
        _, guild_id_str, name = row["key"].split(":", 2)
        result.setdefault(int(guild_id_str), {})[name] = row["value"]
    return result


async def get_is_alerted(user_id: str, guild_id: int = 0) -> bool:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT is_alerted FROM bal WHERE user_id = $1 AND guild_id = $2", user_id, guild_id
        )
    return row["is_alerted"] if row else False


async def set_is_alerted(user_id: str, value: bool, guild_id: int = 0) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO bal (user_id, guild_id, amount, is_alerted) VALUES ($1, $2, 0, $3)
            ON CONFLICT (user_id, guild_id) DO UPDATE SET is_alerted = EXCLUDED.is_alerted
        """, user_id, guild_id, value)


async def set_image_override(template_name: str, url: str, guild_id: int = 0) -> None:
    await set_setting(f"img:{guild_id}:{template_name}", url)


async def get_description_overrides() -> dict[int, dict]:
    """Retourne {guild_id: {template_name: description}}."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT key, value FROM settings WHERE key LIKE 'desc:%'")
    result: dict[int, dict] = {}
    for row in rows:
        _, guild_id_str, name = row["key"].split(":", 2)
        result.setdefault(int(guild_id_str), {})[name] = row["value"]
    return result


async def set_description_override(template_name: str, desc: str, guild_id: int = 0) -> None:
    await set_setting(f"desc:{guild_id}:{template_name}", desc)


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


async def get_bal_rate(guild_id: int) -> int:
    val = await get_setting(f"bal_rate:{guild_id}", str(DEFAULT_BAL_RATE))
    return int(val)


async def set_bal_rate(guild_id: int, rate: int) -> None:
    await set_setting(f"bal_rate:{guild_id}", str(rate))


async def get_recap_channel(guild_id: int) -> int | None:
    val = await get_setting(f"recap_channel:{guild_id}", "")
    return int(val) if val else None


async def set_recap_channel(guild_id: int, channel_id: int | None) -> None:
    await set_setting(f"recap_channel:{guild_id}", str(channel_id) if channel_id else "")


# ── PLAYER PROFILES ───────────────────────────────────────────────────────────

async def get_player_profile(user_id: str, guild_id: int = 0) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM player_profiles WHERE user_id = $1 AND guild_id = $2", user_id, guild_id
        )
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


async def save_player_profile(user_id: str, ig_name: str, initial_pve: int, initial_pvp: int, recruitment_info: str = "", is_membre: bool = False, guild_id: int = 0) -> None:
    joined_at = datetime.now(timezone.utc)
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO player_profiles (user_id, guild_id, ig_name, initial_pve_fame, initial_pvp_fame, joined_at, recruitment_info, is_membre)
            VALUES ($1, $8, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (user_id, guild_id) DO UPDATE SET
                ig_name          = EXCLUDED.ig_name,
                initial_pve_fame = EXCLUDED.initial_pve_fame,
                initial_pvp_fame = EXCLUDED.initial_pvp_fame,
                joined_at        = EXCLUDED.joined_at,
                recruitment_info = EXCLUDED.recruitment_info,
                is_membre        = EXCLUDED.is_membre
        """, user_id, ig_name, initial_pve, initial_pvp, joined_at, recruitment_info, is_membre, guild_id)


async def get_pending_new_players(min_days: int = 14, guild_id: int = 0) -> list[dict]:
    """Nouveaux joueurs (is_membre=FALSE) présents depuis plus de min_days jours."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT user_id, ig_name, joined_at FROM player_profiles
            WHERE is_membre = FALSE
              AND joined_at IS NOT NULL
              AND joined_at <= NOW() - ($1 * INTERVAL '1 day')
              AND guild_id = $2
            ORDER BY joined_at ASC
        """, min_days, guild_id)
    return [{"user_id": r["user_id"], "ig_name": r["ig_name"], "joined_at": r["joined_at"]} for r in rows]


async def get_all_profiles(guild_id: int = 0) -> list[dict]:
    """Retourne tous les profils recrutés."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT user_id, ig_name, joined_at, is_membre FROM player_profiles WHERE guild_id = $1",
            guild_id,
        )
    return [{"user_id": r["user_id"], "ig_name": r["ig_name"], "joined_at": r["joined_at"], "is_membre": r["is_membre"]} for r in rows]


async def set_player_is_membre(user_id: str, value: bool, guild_id: int = 0) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE player_profiles SET is_membre = $2 WHERE user_id = $1 AND guild_id = $3",
            user_id, value, guild_id,
        )


async def update_player_igname(user_id: str, ig_name: str, guild_id: int = 0) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE player_profiles SET ig_name = $2 WHERE user_id = $1 AND guild_id = $3",
            user_id, ig_name, guild_id,
        )


async def update_player_fame(user_id: str, ig_name: str, pve: int, pvp: int, guild_id: int = 0) -> None:
    updated_at = datetime.now(timezone.utc)
    async with _pool.acquire() as conn:
        await conn.execute("""
            UPDATE player_profiles
            SET ig_name = $2, current_pve_fame = $3, current_pvp_fame = $4, fame_updated_at = $5
            WHERE user_id = $1 AND guild_id = $6
        """, user_id, ig_name, pve, pvp, updated_at, guild_id)


async def postpone_player_check(user_id: str, days: int = 7, guild_id: int = 0) -> None:
    """Repousse le suivi d'un joueur de `days` jours en décalant joined_at."""
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE player_profiles SET joined_at = joined_at + ($2 * INTERVAL '1 day') WHERE user_id = $1 AND guild_id = $3",
            user_id, days, guild_id,
        )


async def delete_player_profile(user_id: str, guild_id: int = 0) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM player_profiles WHERE user_id = $1 AND guild_id = $2", user_id, guild_id)


async def save_recruitment_ticket(user_id: str, channel_id: int, guild_id: int = 0) -> None:
    ts = datetime.now(timezone.utc)
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO recruitment_tickets (user_id, guild_id, thread_id, created_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id, guild_id) DO UPDATE SET thread_id = EXCLUDED.thread_id, created_at = EXCLUDED.created_at
        """, user_id, guild_id, channel_id, ts)


async def get_recruitment_ticket(user_id: str, guild_id: int = 0) -> int | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT thread_id FROM recruitment_tickets WHERE user_id = $1 AND guild_id = $2", user_id, guild_id
        )
    return row["thread_id"] if row else None


async def delete_recruitment_ticket(user_id: str, guild_id: int = 0) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM recruitment_tickets WHERE user_id = $1 AND guild_id = $2", user_id, guild_id)


async def delete_recruitment_ticket_by_channel(channel_id: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM recruitment_tickets WHERE thread_id = $1", channel_id)


async def get_recruitment_ticket_user(channel_id: int) -> str | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT user_id FROM recruitment_tickets WHERE thread_id = $1", channel_id)
    return row["user_id"] if row else None


# ── CONFIG RECRUTEMENT PAR SERVEUR ─────────────────────────────────────────────

async def get_recruitment_config(guild_id: int) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM recruitment_config WHERE guild_id = $1", guild_id)
    if not row:
        return None
    return {
        "rules_channel_id":    row["rules_channel_id"],
        "category_id":         row["category_id"],
        "recruitment_role_id": row["recruitment_role_id"],
        "candidat_role_id":    row["candidat_role_id"],
        "validated_role_id":   row["validated_role_id"],
    }


async def set_recruitment_validated_role(guild_id: int, role_id: int | None) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO recruitment_config (guild_id, validated_role_id)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET validated_role_id = EXCLUDED.validated_role_id
        """, guild_id, role_id)


async def set_recruitment_config(
    guild_id: int,
    rules_channel_id: int,
    recruitment_role_id: int,
    candidat_role_id: int,
    category_id: int | None = None,
) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO recruitment_config (guild_id, rules_channel_id, category_id, recruitment_role_id, candidat_role_id)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (guild_id) DO UPDATE SET
                rules_channel_id     = EXCLUDED.rules_channel_id,
                category_id          = EXCLUDED.category_id,
                recruitment_role_id  = EXCLUDED.recruitment_role_id,
                candidat_role_id     = EXCLUDED.candidat_role_id
        """, guild_id, rules_channel_id, category_id, recruitment_role_id, candidat_role_id)


async def increment_acti_count(user_ids: list[str], guild_id: int = 0) -> None:
    now = datetime.now(timezone.utc)
    async with _pool.acquire() as conn:
        async with conn.transaction():
            for user_id in user_ids:
                await conn.execute("""
                    INSERT INTO player_profiles (user_id, guild_id, acti_count, last_acti_at)
                    VALUES ($1, $3, 1, $2)
                    ON CONFLICT (user_id, guild_id) DO UPDATE
                        SET acti_count   = player_profiles.acti_count + 1,
                            last_acti_at = $2
                """, user_id, now, guild_id)


async def get_inactive_member_ids(days: int, guild_id: int = 0) -> set[str]:
    """Retourne les user_ids n'ayant pas participé à une activité depuis N jours."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT user_id FROM player_profiles
            WHERE guild_id = $2
              AND (last_acti_at IS NULL OR last_acti_at < NOW() - ($1 * INTERVAL '1 day'))
        """, days, guild_id)
    return {r["user_id"] for r in rows}


# ── SALONS VOCAUX TEMPORAIRES ──────────────────────────────────────────────────

async def get_voice_hubs(guild_id: int) -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM voice_hubs WHERE guild_id = $1", guild_id)
    return [
        {
            "channel_id":    r["channel_id"],
            "guild_id":      r["guild_id"],
            "category_id":   r["category_id"],
            "name_template": r["name_template"],
            "user_limit":    r["user_limit"],
        }
        for r in rows
    ]


async def get_all_voice_hubs() -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM voice_hubs")
    return [
        {
            "channel_id":    r["channel_id"],
            "guild_id":      r["guild_id"],
            "category_id":   r["category_id"],
            "name_template": r["name_template"],
            "user_limit":    r["user_limit"],
        }
        for r in rows
    ]


async def add_voice_hub(
    channel_id: int, guild_id: int, category_id: int | None,
    name_template: str = "🔊 {pseudo}", user_limit: int = 0,
) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO voice_hubs (channel_id, guild_id, category_id, name_template, user_limit)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (channel_id) DO UPDATE SET
                category_id   = EXCLUDED.category_id,
                name_template = EXCLUDED.name_template,
                user_limit    = EXCLUDED.user_limit
        """, channel_id, guild_id, category_id, name_template, user_limit)


async def update_voice_hub(channel_id: int, name_template: str, user_limit: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE voice_hubs SET name_template = $2, user_limit = $3 WHERE channel_id = $1",
            channel_id, name_template, user_limit,
        )


async def delete_voice_hub(channel_id: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM voice_hubs WHERE channel_id = $1", channel_id)


async def add_temp_voice_channel(channel_id: int, guild_id: int, owner_id: int, hub_id: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO temp_voice_channels (channel_id, guild_id, owner_id, hub_id)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (channel_id) DO NOTHING
        """, channel_id, guild_id, owner_id, hub_id)


async def get_all_temp_voice_channels() -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM temp_voice_channels")
    return [
        {"channel_id": r["channel_id"], "guild_id": r["guild_id"], "owner_id": r["owner_id"], "hub_id": r["hub_id"]}
        for r in rows
    ]


async def delete_temp_voice_channel(channel_id: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM temp_voice_channels WHERE channel_id = $1", channel_id)


# ── MESSAGES BIENVENUE / AU REVOIR ─────────────────────────────────────────────

async def get_member_events_config(guild_id: int) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM member_events_config WHERE guild_id = $1", guild_id)
    if not row:
        return None
    return {
        "welcome_channel_id": row["welcome_channel_id"],
        "welcome_message":    row["welcome_message"],
        "welcome_image":      row["welcome_image"],
        "goodbye_channel_id": row["goodbye_channel_id"],
        "goodbye_message":    row["goodbye_message"],
        "default_role_id":    row["default_role_id"],
    }


async def get_all_member_events_configs() -> dict[int, dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM member_events_config")
    return {
        r["guild_id"]: {
            "welcome_channel_id": r["welcome_channel_id"],
            "welcome_message":    r["welcome_message"],
            "welcome_image":      r["welcome_image"],
            "goodbye_channel_id": r["goodbye_channel_id"],
            "goodbye_message":    r["goodbye_message"],
            "default_role_id":    r["default_role_id"],
        }
        for r in rows
    }


async def set_welcome_config(guild_id: int, channel_id: int | None, message: str | None, image: str | None = None) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO member_events_config (guild_id, welcome_channel_id, welcome_message, welcome_image)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id) DO UPDATE SET
                welcome_channel_id = EXCLUDED.welcome_channel_id,
                welcome_message    = EXCLUDED.welcome_message,
                welcome_image      = EXCLUDED.welcome_image
        """, guild_id, channel_id, message, image)


async def set_goodbye_config(guild_id: int, channel_id: int | None, message: str | None) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO member_events_config (guild_id, goodbye_channel_id, goodbye_message)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE SET
                goodbye_channel_id = EXCLUDED.goodbye_channel_id,
                goodbye_message    = EXCLUDED.goodbye_message
        """, guild_id, channel_id, message)


async def set_default_role(guild_id: int, role_id: int | None) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO member_events_config (guild_id, default_role_id)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET default_role_id = EXCLUDED.default_role_id
        """, guild_id, role_id)
