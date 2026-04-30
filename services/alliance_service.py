import aiosqlite
from database import DB_PATH


async def create_alliance(name: str, founder_country: str, alliance_type: str, topic_id: int) -> int | None:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "INSERT INTO alliances (name, founder_country, alliance_type, topic_id) VALUES (?, ?, ?, ?)",
                (name, founder_country.lower(), alliance_type, topic_id),
            )
            alliance_id = cursor.lastrowid
            await db.execute(
                "INSERT INTO alliance_members (alliance_id, country) VALUES (?, ?)",
                (alliance_id, founder_country.lower()),
            )
            await db.commit()
            return alliance_id
    except aiosqlite.IntegrityError:
        return None


async def get_alliance_by_name(name: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM alliances WHERE LOWER(name) = LOWER(?)", (name,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_alliance_by_id(alliance_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM alliances WHERE id = ?", (alliance_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_alliances_for_country(country: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT a.* FROM alliances a
               JOIN alliance_members am ON a.id = am.alliance_id
               WHERE LOWER(am.country) = LOWER(?)""",
            (country,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_alliance_members(alliance_id: int) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT country FROM alliance_members WHERE alliance_id = ?", (alliance_id,)
        ) as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]


async def add_member(alliance_id: int, country: str) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO alliance_members (alliance_id, country) VALUES (?, ?)",
                (alliance_id, country.lower()),
            )
            await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False


async def remove_member(alliance_id: int, country: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM alliance_members WHERE alliance_id = ? AND LOWER(country) = LOWER(?)",
            (alliance_id, country),
        )
        await db.commit()
    return True


async def create_invite(alliance_id: int, from_country: str, to_country: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO alliance_invites (alliance_id, from_country, to_country) VALUES (?, ?, ?)",
            (alliance_id, from_country.lower(), to_country.lower()),
        )
        await db.commit()
        return cursor.lastrowid


async def get_pending_invite(to_country: str, alliance_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM alliance_invites WHERE LOWER(to_country) = LOWER(?) AND alliance_id = ? AND status = 'pending'",
            (to_country, alliance_id),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def accept_invite(invite_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE alliance_invites SET status = 'accepted' WHERE id = ?", (invite_id,)
        )
        await db.commit()
    return True


async def get_all_alliances() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM alliances ORDER BY created_at DESC") as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_military_allies(country: str) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT am2.country FROM alliance_members am1
               JOIN alliances a ON a.id = am1.alliance_id
               JOIN alliance_members am2 ON am2.alliance_id = a.id
               WHERE LOWER(am1.country) = LOWER(?) AND a.alliance_type IN ('military', 'hybrid')
               AND LOWER(am2.country) != LOWER(?)""",
            (country, country),
        ) as cur:
            rows = await cur.fetchall()
            return [r["country"] for r in rows]


async def update_gdp_bonuses():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id FROM alliances WHERE alliance_type IN ('economic', 'hybrid')"
        ) as cur:
            eco_alliances = await cur.fetchall()

        for alliance in eco_alliances:
            async with db.execute(
                "SELECT country FROM alliance_members WHERE alliance_id = ?", (alliance["id"],)
            ) as cur:
                members = await cur.fetchall()
            member_count = len(members)
            bonus = min(member_count * 0.5, 5.0)
            for m in members:
                await db.execute(
                    "UPDATE players SET gdp_growth_bonus = MAX(gdp_growth_bonus, ?) WHERE LOWER(country) = LOWER(?)",
                    (bonus, m["country"]),
                )
        await db.commit()
