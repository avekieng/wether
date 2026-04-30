import aiosqlite
import json
from database import DB_PATH


async def get_active_war(country1: str, country2: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM wars WHERE status = 'active' AND (
               (LOWER(attacker_country) = LOWER(?) AND LOWER(defender_country) = LOWER(?)) OR
               (LOWER(attacker_country) = LOWER(?) AND LOWER(defender_country) = LOWER(?)))""",
            (country1, country2, country2, country1),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_all_wars_for_country(country: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM wars WHERE status = 'active' AND
               (LOWER(attacker_country) = LOWER(?) OR LOWER(defender_country) = LOWER(?))""",
            (country, country),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_all_active_wars() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM wars WHERE status = 'active'") as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def create_war(attacker: str, defender: str, topic_id: int, reason: str = "") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO wars (attacker_country, defender_country, topic_id, reason) VALUES (?, ?, ?, ?)",
            (attacker.lower(), defender.lower(), topic_id, reason),
        )
        await db.commit()
        return cursor.lastrowid


async def end_war(war_id: int, status: str = "ended") -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE wars SET status = ?, ended_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, war_id),
        )
        await db.commit()
    return True


async def update_war(war_id: int, **fields) -> bool:
    if not fields:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [war_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE wars SET {set_clause} WHERE id = ?", values)
        await db.commit()
    return True


async def add_war_action(
    war_id: int, country: str, action_text: str, result_text: str,
    attacker_losses: dict = None, defender_losses: dict = None, territory_change: float = 0
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO war_actions
               (war_id, country, action_text, result_text, attacker_losses, defender_losses, territory_change)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (war_id, country, action_text, result_text,
             json.dumps(attacker_losses or {}), json.dumps(defender_losses or {}), territory_change),
        )
        await db.commit()
        return cursor.lastrowid


async def get_war_history(war_id: int, limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM war_actions WHERE war_id = ? ORDER BY created_at DESC LIMIT ?",
            (war_id, limit),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_war_fronts(war_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM war_fronts WHERE war_id = ?", (war_id,)) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def upsert_front(war_id: int, front_name: str, attacker_divs: dict, defender_divs: dict, control: float) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM war_fronts WHERE war_id = ? AND front_name = ?", (war_id, front_name)
        ) as cur:
            row = await cur.fetchone()
        if row:
            await db.execute(
                "UPDATE war_fronts SET attacker_divisions=?, defender_divisions=?, control=? WHERE id=?",
                (json.dumps(attacker_divs), json.dumps(defender_divs), control, row[0]),
            )
        else:
            await db.execute(
                "INSERT INTO war_fronts (war_id, front_name, attacker_divisions, defender_divisions, control) VALUES (?,?,?,?,?)",
                (war_id, front_name, json.dumps(attacker_divs), json.dumps(defender_divs), control),
            )
        await db.commit()
