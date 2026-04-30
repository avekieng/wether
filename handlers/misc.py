import logging
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message

from services.player_service import smart_find_country, get_player_by_user_id, get_player_by_country, get_all_players
from services.ai_service import answer_question, mediate_conflict
from config import COURT_TOPIC_ID, ANNOUNCE_TOPIC_ID
from services.topic_service import send_to_topic, send_announcement
from database import DB_PATH
import aiosqlite

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.reply(
        "🌍 <b>Геополитическая RP — Команды</b>\n\n"
        "👤 <b>Игроки:</b>\n"
        "/adduser &lt;id&gt; &lt;страна&gt; — зарегистрировать игрока\n"
        "/info [страна] — информация о стране\n"
        "/top — рейтинг стран по ВВП\n"
        "/rename &lt;название&gt; — переименовать страну\n"
        "/buydiv &lt;тип&gt; &lt;кол-во&gt; — купить дивизии\n\n"
        "⚔️ <b>Война:</b>\n"
        "/war start &lt;страна&gt; [причина] — объявить войну\n"
        "/war deploy &lt;направление&gt; &lt;тип&gt; &lt;кол-во&gt; — перебросить дивизии\n"
        "/war action &lt;действие&gt; — военная операция\n"
        "/war fronts — состояние фронтов\n"
        "/war stop &lt;страна&gt; — мирный договор (название целиком)\n"
        "/war status — активные войны\n"
        "/civil suppress — подавить гражданское восстание\n\n"
        "🤝 <b>Альянсы:</b>\n"
        "/alliance create &lt;тип&gt; &lt;название&gt;\n"
        "/alliance invite &lt;альянс&gt; &lt;страна&gt;\n"
        "/alliance accept &lt;альянс&gt;\n"
        "/alliance leave &lt;альянс&gt;\n"
        "/alliance info [альянс]\n"
        "/alliance list\n\n"
        "💸 <b>Экономика:</b>\n"
        "/economy — экономическая сводка\n"
        "/tax &lt;low|normal|high&gt; — налоги\n"
        "/loan &lt;страна&gt; &lt;сумма&gt; — выдать займ\n"
        "/trade &lt;страна&gt; &lt;мой%&gt; &lt;их%&gt; — торговое соглашение\n\n"
        "🌐 <b>Прочее:</b>\n"
        "/quest &lt;вопрос&gt; — вопрос к AI-арбитру\n"
        "/third &lt;страна1&gt; | &lt;страна2&gt; | &lt;суть&gt; — международный суд\n"
        "/map — карта расстановки сил\n"
        "/rules — правила игры"
    )


@router.message(Command("rules"))
async def cmd_rules(message: Message):
    await message.reply(
        "📜 <b>Правила геополитической RP</b>\n\n"
        "💥 <b>Войны</b>\n"
        "• Для начала войны нужна причина\n"
        "• Дивизии распределяются по направлениям (/war deploy)\n"
        "• 1 дивизия = 10 000 солдат\n"
        "• БПЛА vs РЭБ — РЭБ глушит БПЛА на 70%\n"
        "• Воздушные vs ПВО — ПВО сбивает воздушные на 70%\n"
        "• Спорные моменты решает AI-арбитр\n\n"
        "👥 <b>Альянсы</b>\n"
        "• Экономические: +ВВП (чем больше членов, тем выше бонус)\n"
        "• Военные: взаимооборона при нападении\n"
        "• Гибридные: всё сразу\n\n"
        "💸 <b>Экономика</b>\n"
        "• ВВП растёт на 2%/день + бонусы\n"
        "• ДД (казна) — деньги на закупки и проекты\n"
        "• Высокие налоги = больше казны, но +усталость\n"
        "• Долги — договор между игроками\n\n"
        "🪖 <b>Дивизии</b>\n"
        "🛸 БПЛА — мощные, дорогие ($15млрд)\n"
        "📡 РЭБ — глушит БПЛА 70% ($10млрд)\n"
        "🪖 Пехота — базовая ($5млрд)\n"
        "✈️ Воздушные — авиация ($12млрд)\n"
        "🚀 ПВО — сбивает авиацию 70% ($8млрд)\n\n"
        "😓 <b>Усталость</b>\n"
        "• Старт: 0%\n"
        "• Война: +0.5% каждые 10 минут\n"
        "• 70%+ → гражданская война 🔥\n"
        "• При гражданской войне ВВП -2%/час\n"
        "• Высокие налоги усиливают усталость"
    )


@router.message(Command("quest"))
async def cmd_quest(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("❌ Использование: <code>/quest &lt;вопрос&gt;</code>")
        return

    question = args[1].strip()
    player = await get_player_by_user_id(message.from_user.id)

    context_parts = []
    if player:
        context_parts.append(
            f"Спрашивает: {player['country_display']} {player['flag']} "
            f"(ВВП ${player['gdp']:.0f}млрд, военная мощь {player['military_power']}/100)"
        )

    players = await get_all_players()
    if players:
        context_parts.append(f"Зарегистрировано стран: {len(players)}")
        top3 = [f"{p['flag']} {p['country_display']} (${p['gdp']:.0f}млрд)" for p in players[:3]]
        context_parts.append("Топ-3 по ВВП: " + ", ".join(top3))

    context = "\n".join(context_parts)

    wait_msg = await message.reply("🤔 AI-арбитр думает...")
    answer = await answer_question(question, context)
    await wait_msg.edit_text(f"🌐 <b>AI-арбитр:</b>\n\n{answer}")


@router.message(Command("third"))
async def cmd_third(message: Message, bot: Bot):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or "|" not in args[1]:
        await message.reply(
            "❌ Использование: <code>/third &lt;страна1&gt; | &lt;страна2&gt; | &lt;суть конфликта&gt;</code>\n"
            "Пример: <code>/third Германия | Франция | Германия нарушила торговое соглашение</code>"
        )
        return

    parts = [p.strip() for p in args[1].split("|")]
    if len(parts) < 3:
        await message.reply("❌ Нужно указать обе страны и суть через символ |")
        return

    plaintiff_name, defendant_name, description = parts[0], parts[1], "|".join(parts[2:])

    plaintiff = await smart_find_country(plaintiff_name)
    defendant = await smart_find_country(defendant_name)

    if not plaintiff:
        await message.reply(f"❌ Страна-истец <b>{plaintiff_name}</b> не найдена.")
        return
    if not defendant:
        await message.reply(f"❌ Страна-ответчик <b>{defendant_name}</b> не найдена.")
        return

    wait_msg = await message.reply("⚖️ Международный трибунал рассматривает дело...")

    context = (
        f"ИСТЕЦ: {plaintiff['country_display']} {plaintiff['flag']} — "
        f"ВВП ${plaintiff['gdp']:.0f}млрд, военная мощь {plaintiff['military_power']}/100\n"
        f"ОТВЕТЧИК: {defendant['country_display']} {defendant['flag']} — "
        f"ВВП ${defendant['gdp']:.0f}млрд, военная мощь {defendant['military_power']}/100"
    )

    verdict = await mediate_conflict(
        plaintiff=f"{plaintiff['country_display']} {plaintiff['flag']}",
        defendant=f"{defendant['country_display']} {defendant['flag']}",
        description=description,
        context=context,
    )

    topic_id = COURT_TOPIC_ID

    case_text = (
        f"⚖️ <b>МЕЖДУНАРОДНЫЙ ТРИБУНАЛ</b>\n\n"
        f"🔵 Истец: {plaintiff['flag']} {plaintiff['country_display']}\n"
        f"🔴 Ответчик: {defendant['flag']} {defendant['country_display']}\n\n"
        f"📋 Суть: {description}\n\n"
        f"🏛️ <b>Решение AI-арбитра:</b>\n\n{verdict}"
    )

    await send_to_topic(bot, topic_id, case_text)
    await send_announcement(
            bot,
            f"⚖️ Открыто дело: {plaintiff['flag']} {plaintiff['country_display']} "
            f"vs {defendant['flag']} {defendant['country_display']}\n"
            f"Решение опубликовано."
        )
    await wait_msg.edit_text("✅ Решение вынесено.")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO court_cases (plaintiff, defendant, description, status, verdict, topic_id)
               VALUES (?, ?, ?, 'closed', ?, ?)""",
            (plaintiff["country"], defendant["country"], description, verdict[:1000], topic_id),
        )
        await db.commit()


@router.message(Command("map"))
async def cmd_map(message: Message):
    players = await get_all_players()
    if not players:
        await message.reply("❌ Нет зарегистрированных стран.")
        return

    lines = ["🌍 <b>Карта мира — расстановка сил</b>\n"]

    total_gdp = sum(p["gdp"] for p in players)
    top_military = sorted(players, key=lambda p: p["military_power"], reverse=True)

    lines.append("💰 <b>Экономика (топ-10):</b>")
    for i, p in enumerate(players[:10], 1):
        share = (p["gdp"] / total_gdp * 100) if total_gdp else 0
        cw = " 🔥" if p.get("civil_war") else ""
        lines.append(f"  {i}. {p['flag']} {p['country_display']}{cw} — ${p['gdp']:.0f}млрд ({share:.1f}%)")

    lines.append("\n🪖 <b>Военная мощь (топ-10):</b>")
    for i, p in enumerate(top_military[:10], 1):
        fatigue_icon = "🔥" if p["fatigue"] >= 70 else ("⚠️" if p["fatigue"] >= 50 else "")
        lines.append(
            f"  {i}. {p['flag']} {p['country_display']} — {p['military_power']}/100 "
            f"😓{p['fatigue']:.0f}% {fatigue_icon}"
        )

    civil_wars = [p for p in players if p.get("civil_war")]
    if civil_wars:
        lines.append("\n🔥 <b>Гражданские войны:</b>")
        for p in civil_wars:
            lines.append(f"  {p['flag']} {p['country_display']} — усталость {p['fatigue']:.1f}%")

    await message.reply("\n".join(lines))
