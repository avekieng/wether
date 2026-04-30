import aiosqlite
import json
from database import DB_PATH
from config import DIVISION_TYPES


async def get_divisions(country: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM divisions WHERE LOWER(country) = LOWER(?)", (country,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_divisions_summary(country: str) -> dict:
    divs = await get_divisions(country)
    summary = {}
    for d in divs:
        key = d["div_type"]
        if key not in summary:
            summary[key] = {"total": 0, "reserve": 0, "fronts": {}}
        summary[key]["total"] += d["count"]
        if d["front"] == "reserve":
            summary[key]["reserve"] += d["count"]
        else:
            summary[key]["fronts"][d["front"]] = summary[key]["fronts"].get(d["front"], 0) + d["count"]
    return summary


async def buy_division(country: str, div_type: str, count: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, count FROM divisions WHERE LOWER(country) = LOWER(?) AND div_type = ? AND front = 'reserve'",
            (country, div_type),
        ) as cur:
            row = await cur.fetchone()

        if row:
            await db.execute(
                "UPDATE divisions SET count = count + ? WHERE id = ?",
                (count, row["id"]),
            )
        else:
            await db.execute(
                "INSERT INTO divisions (country, div_type, count, front) VALUES (?, ?, ?, 'reserve')",
                (country.lower(), div_type, count),
            )
        await db.commit()
    return True


async def move_divisions(country: str, div_type: str, count: int, front: str, war_id: int) -> tuple[bool, str]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, count FROM divisions WHERE LOWER(country) = LOWER(?) AND div_type = ? AND front = 'reserve'",
            (country, div_type),
        ) as cur:
            reserve = await cur.fetchone()

        if not reserve or reserve["count"] < count:
            available = reserve["count"] if reserve else 0
            return False, f"Недостаточно дивизий в резерве. Доступно: {available}"

        await db.execute(
            "UPDATE divisions SET count = count - ? WHERE id = ?",
            (count, reserve["id"]),
        )

        async with db.execute(
            "SELECT id FROM divisions WHERE LOWER(country) = LOWER(?) AND div_type = ? AND front = ? AND war_id = ?",
            (country, div_type, front, war_id),
        ) as cur:
            front_row = await cur.fetchone()

        if front_row:
            await db.execute(
                "UPDATE divisions SET count = count + ? WHERE id = ?",
                (count, front_row["id"]),
            )
        else:
            await db.execute(
                "INSERT INTO divisions (country, div_type, count, front, war_id) VALUES (?, ?, ?, ?, ?)",
                (country.lower(), div_type, count, front, war_id),
            )

        await db.commit()
    return True, "OK"


async def get_front_divisions(country: str, war_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM divisions WHERE LOWER(country) = LOWER(?) AND war_id = ? AND front != 'reserve'",
            (country, war_id),
        ) as cur:
            rows = await cur.fetchall()

    result = {}
    for r in rows:
        front = r["front"]
        if front not in result:
            result[front] = {}
        result[front][r["div_type"]] = result[front].get(r["div_type"], 0) + r["count"]
    return result


async def apply_losses(country: str, war_id: int, losses: dict) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        for div_type, lost in losses.items():
            if lost <= 0:
                continue
            async with db.execute(
                "SELECT id, count FROM divisions WHERE LOWER(country) = LOWER(?) AND div_type = ? AND war_id = ?",
                (country, div_type, war_id),
            ) as cur:
                row = await cur.fetchone()
            if row:
                new_count = max(0, row[1] - lost)
                await db.execute("UPDATE divisions SET count = ? WHERE id = ?", (new_count, row[0]))
        await db.commit()


def calc_front_power(divisions: dict) -> dict:
    power = {"total": 0, "has_bpla": False, "has_reb": False, "has_air": False, "has_pvo": False}
    for div_type, count in divisions.items():
        info = DIVISION_TYPES.get(div_type, {})
        power["total"] += info.get("power", 10) * count
        if div_type == "бпла":
            power["has_bpla"] = True
        if div_type == "рэб":
            power["has_reb"] = True
        if div_type == "воздушные":
            power["has_air"] = True
        if div_type == "пво":
            power["has_pvo"] = True
    return power

# pepepopohitler

def apply_counters(attacker_power: dict, defender_power: dict) -> tuple[float, float]:
    atk = float(attacker_power["total"])
    dfn = float(defender_power["total"])

    if attacker_power["has_bpla"] and defender_power["has_reb"]:
        atk *= 0.30
    if attacker_power["has_air"] and defender_power["has_pvo"]:
        atk *= 0.30
    if defender_power["has_bpla"] and attacker_power["has_reb"]:
        dfn *= 0.30
    if defender_power["has_air"] and attacker_power["has_pvo"]:
        dfn *= 0.30

    return atk, dfn
