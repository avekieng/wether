import asyncio
import logging
from aiogram import Bot
from config import (
    GDP_GROWTH_INTERVAL, FATIGUE_WAR_INTERVAL, FATIGUE_WAR_INCREASE,
    FATIGUE_CIVIL_WAR_THRESHOLD, CIVIL_WAR_GDP_LOSS_INTERVAL,
    CIVIL_WAR_GDP_LOSS_PERCENT, BASE_GDP_GROWTH_PERCENT, ANNOUNCE_TOPIC_ID,
)
from services.player_service import (
    get_all_players, update_player_by_country,
    get_players_in_war, get_players_in_civil_war,
)
from services.alliance_service import update_gdp_bonuses
from services.topic_service import send_to_topic
from services.ai_service import evaluate_civil_war

logger = logging.getLogger(__name__)


async def task_gdp_growth(bot: Bot):
    while True:
        await asyncio.sleep(GDP_GROWTH_INTERVAL)
        try:
            await update_gdp_bonuses()
            players = await get_all_players()
            for p in players:
                if p["civil_war"]:
                    continue
                tax = p.get("tax_level", "normal")
                tax_penalty = 0
                if tax == "high":
                    tax_penalty = -1.0

                growth = BASE_GDP_GROWTH_PERCENT + p.get("gdp_growth_bonus", 0) + tax_penalty
                fatigue_penalty = max(0, (p["fatigue"] - 30) * 0.05)
                growth = max(0, growth - fatigue_penalty)

                new_gdp = round(p["gdp"] * (1 + growth / 100), 2)
                await update_player_by_country(p["country"], gdp=new_gdp)

            logger.info("GDP growth tick done")
        except Exception as e:
            logger.error(f"GDP growth error: {e}")


async def task_fatigue_war(bot: Bot):
    while True:
        await asyncio.sleep(FATIGUE_WAR_INTERVAL)
        try:
            players = await get_players_in_war()
            for p in players:
                tax = p.get("tax_level", "normal")
                extra = 0.3 if tax == "high" else 0
                new_fatigue = min(100.0, p["fatigue"] + FATIGUE_WAR_INCREASE + extra)
                await update_player_by_country(p["country"], fatigue=new_fatigue)

                if new_fatigue >= FATIGUE_CIVIL_WAR_THRESHOLD and not p["civil_war"]:
                    await trigger_civil_war(bot, p)

            players_high_tax = await _get_high_tax_players()
            for p in players_high_tax:
                if p["country"] in [pw["country"] for pw in players]:
                    continue
                new_fatigue = min(100.0, p["fatigue"] + 0.2)
                await update_player_by_country(p["country"], fatigue=new_fatigue)
                if new_fatigue >= FATIGUE_CIVIL_WAR_THRESHOLD and not p["civil_war"]:
                    await trigger_civil_war(bot, p)

        except Exception as e:
            logger.error(f"Fatigue tick error: {e}")


async def task_civil_war_gdp(bot: Bot):
    while True:
        await asyncio.sleep(CIVIL_WAR_GDP_LOSS_INTERVAL)
        try:
            players = await get_players_in_civil_war()
            for p in players:
                new_gdp = round(p["gdp"] * (1 - CIVIL_WAR_GDP_LOSS_PERCENT / 100), 2)
                await update_player_by_country(p["country"], gdp=new_gdp)
                logger.info(f"Civil war GDP loss: {p['country']} {p['gdp']} -> {new_gdp}")
        except Exception as e:
            logger.error(f"Civil war GDP tick error: {e}")


async def trigger_civil_war(bot: Bot, player: dict):
    await update_player_by_country(player["country"], civil_war=1)
    description = await evaluate_civil_war(
        player["country_display"], player["fatigue"], player["gdp"]
    )
    text = (
        f"🔥 <b>ГРАЖДАНСКАЯ ВОЙНА!</b>\n\n"
        f"{player['flag']} <b>{player['country_display']}</b>\n"
        f"Усталость населения: {player['fatigue']:.1f}%\n\n"
        f"{description}\n\n"
        f"⚠️ Каждый час ВВП падает на {CIVIL_WAR_GDP_LOSS_PERCENT}%\n"
        f"Используй <code>/civil suppress</code> для подавления восстания"
    )
    await send_to_topic(bot, ANNOUNCE_TOPIC_ID, text)
    if player.get("topic_id"):
        await send_to_topic(bot, player["topic_id"], text)


async def _get_high_tax_players():
    from services.player_service import get_all_players
    players = await get_all_players()
    return [p for p in players if p.get("tax_level") == "high"]


async def start_background_tasks(bot: Bot):
    await asyncio.gather(
        task_gdp_growth(bot),
        task_fatigue_war(bot),
        task_civil_war_gdp(bot),
    )
