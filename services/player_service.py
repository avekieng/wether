import aiosqlite
from database import DB_PATH


async def get_player_by_user_id(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM players WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_player_by_country(country: str) -> dict | None:
    name = country.strip()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # ищем и по country (slug), и по country_display
        async with db.execute(
            """SELECT * FROM players
               WHERE LOWER(country) = LOWER(?)
                  OR LOWER(country_display) = LOWER(?)""",
            (name, name),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_all_players() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM players ORDER BY gdp DESC") as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def create_player(
    user_id: int, username: str, country: str, country_display: str,
    flag: str, topic_id: int, gdp: float, area: float, population: int,
    military_power: int, total_divisions: int = 20,
) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO players
                   (user_id, username, country, country_display, flag, topic_id,
                    gdp, area, population, military_power, total_divisions, treasury)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, username, country.lower(), country_display, flag, topic_id,
                 gdp, area, population, military_power, total_divisions, round(gdp * 0.1, 2)),
            )
            await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False


async def update_player(user_id: int, **fields) -> bool:
    if not fields:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [user_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE players SET {set_clause} WHERE user_id = ?", values)
        await db.commit()
    return True


async def update_player_by_country(country: str, **fields) -> bool:
    if not fields:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [country.lower()]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE players SET {set_clause} WHERE LOWER(country) = LOWER(?)", values)
        await db.commit()
    return True


async def rename_country(user_id: int, new_display: str, new_flag: str = None) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        if new_flag:
            await db.execute(
                "UPDATE players SET country_display = ?, flag = ? WHERE user_id = ?",
                (new_display, new_flag, user_id),
            )
        else:
            await db.execute(
                "UPDATE players SET country_display = ? WHERE user_id = ?",
                (new_display, user_id),
            )
        await db.commit()
    return True


async def get_players_in_war() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT DISTINCT p.* FROM players p
               JOIN wars w ON (LOWER(w.attacker_country) = LOWER(p.country)
                            OR LOWER(w.defender_country) = LOWER(p.country))
               WHERE w.status = 'active'"""
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_players_in_civil_war() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM players WHERE civil_war = 1") as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_all_country_slugs() -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT country, country_display FROM players") as cur:
            rows = await cur.fetchall()
            # возвращаем оба варианта для лучшего матчинга
            result = []
            for slug, display in rows:
                result.append(slug)
                if display.lower() != slug:
                    result.append(display.lower())
            return result


async def smart_find_country(raw_name: str) -> dict | None:
    """Ищет страну сначала напрямую, потом через AI если не нашёл."""
    # Сначала прямой поиск
    player = await get_player_by_country(raw_name)
    if player:
        return player

    # Если не нашли — спрашиваем AI
    from services.ai_service import resolve_country_name
    slugs = await get_all_country_slugs()
    if not slugs:
        return None

    resolved = await resolve_country_name(raw_name, slugs)
    if not resolved:
        return None

    return await get_player_by_country(resolved)
