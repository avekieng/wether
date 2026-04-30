import logging
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message

from config import GROUP_ID, DIVISION_TYPES, COUNTRIES_TOPIC_ID
from services.player_service import (
    smart_find_country, get_player_by_user_id, get_player_by_country,
    create_player, rename_country, get_all_players, update_player,
)
from services.division_service import get_divisions_summary, buy_division
from services.topic_service import send_to_topic, send_announcement
from services.ai_service import get_country_info, generate_country_data

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("adduser"))
async def cmd_adduser(message: Message, bot: Bot):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.reply("❌ Использование: <code>/adduser &lt;user_id&gt; &lt;Страна&gt;</code>")
        return

    try:
        target_user_id = int(args[1])
    except ValueError:
        await message.reply("❌ Неверный user_id.")
        return

    raw_country = args[2].strip()

    existing_player = await get_player_by_user_id(target_user_id)
    if existing_player:
        await message.reply(f"❌ Игрок уже играет за <b>{existing_player['country_display']}</b>.")
        return

    try:
        chat_member = await bot.get_chat_member(GROUP_ID, target_user_id)
        username = chat_member.user.username or chat_member.user.first_name
        mention = f"@{username}" if chat_member.user.username else f"<a href='tg://user?id={target_user_id}'>{username}</a>"
    except Exception:
        username = str(target_user_id)
        mention = str(target_user_id)

    wait_msg = await message.reply(f"⏳ Определяю страну <b>{raw_country}</b>...")

    data = await generate_country_data(raw_country)
    country_display = data["name_ru"]
    country_slug = country_display.lower().strip()
    flag = data["flag"]

    existing = await smart_find_country(country_slug)
    if existing:
        await wait_msg.edit_text(f"❌ Страна <b>{country_display}</b> уже занята.")
        return

    success = await create_player(
        user_id=target_user_id,
        username=username,
        country=country_slug,
        country_display=country_display,
        flag=flag,
        topic_id=COUNTRIES_TOPIC_ID,
        gdp=data["gdp"],
        area=data["area"],
        population=data["population"],
        military_power=data["military"],
        total_divisions=data["divisions"],
    )

    if not success:
        await wait_msg.edit_text("❌ Ошибка сохранения в БД.")
        return

    country_info = await get_country_info(country_display, data)

    await send_to_topic(
        bot, COUNTRIES_TOPIC_ID,
        f"{flag} <b>{country_display}</b>\n"
        f"👤 Игрок: {mention}\n\n"
        f"📐 Площадь: {data['area']:,.0f} км²\n"
        f"👥 Население: {data['population']:,}\n"
        f"💰 ВВП: ${data['gdp']:.0f}млрд\n"
        f"🪖 Военная мощь: {data['military']}/100\n"
        f"⚔️ Дивизий: {data['divisions']}\n\n"
        f"{country_info}"
    )

    await wait_msg.edit_text(f"✅ {flag} <b>{country_display}</b> зарегистрирована! 👤 {mention}")


@router.message(Command("info"))
async def cmd_info(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) == 1:
        player = await get_player_by_user_id(message.from_user.id)
        if not player:
            await message.reply("❌ Ты не зарегистрирован.")
            return
    else:
        player = await smart_find_country(args[1].strip())
        if not player:
            await message.reply("❌ Страна не найдена.")
            return

    divs = await get_divisions_summary(player["country"])
    div_lines = []
    for dt, info in DIVISION_TYPES.items():
        d = divs.get(dt, {})
        total = d.get("total", 0)
        if total > 0:
            div_lines.append(f"  {info['emoji']} {info['name']}: {total} див.")

    fatigue_bar = "🟩" * int(player["fatigue"] // 10) + "⬜" * (10 - int(player["fatigue"] // 10))

    text = (
        f"{player['flag']} <b>{player['country_display']}</b>\n"
        f"👤 @{player['username']}\n\n"
        f"📊 <b>Экономика:</b>\n"
        f"  💰 ВВП: ${player['gdp']:.0f}млрд\n"
        f"  🏦 Казна: ${player['treasury']:.1f}млрд\n"
        f"  📈 Бонус роста: +{player.get('gdp_growth_bonus', 0):.1f}%\n"
        f"  💼 Налоги: {player.get('tax_level', 'normal')}\n\n"
        f"🗺️ <b>Территория:</b>\n"
        f"  📐 {player['area']:,.0f} км² | 👥 {player['population']:,}\n\n"
        f"⚔️ <b>Армия:</b>\n"
        f"  🪖 Мощь: {player['military_power']}/100\n"
        f"  📦 Дивизий: {player['total_divisions']}\n"
    )
    if div_lines:
        text += "\n".join(div_lines) + "\n"
    text += f"\n😓 <b>Усталость:</b> {player['fatigue']:.1f}%\n  {fatigue_bar}\n"
    if player.get("civil_war"):
        text += "🔥 <b>ГРАЖДАНСКАЯ ВОЙНА!</b>\n"

    await message.reply(text)


@router.message(Command("top"))
async def cmd_top(message: Message):
    players = await get_all_players()
    if not players:
        await message.reply("❌ Нет зарегистрированных стран.")
        return
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🌍 <b>Топ стран по ВВП:</b>\n"]
    for i, p in enumerate(players[:15], 1):
        medal = medals[i - 1] if i <= 3 else f"{i}."
        cw = " 🔥" if p.get("civil_war") else ""
        lines.append(
            f"{medal} {p['flag']} <b>{p['country_display']}</b>{cw} — "
            f"${p['gdp']:.0f}млрд | 🪖{p['military_power']}"
        )
    await message.reply("\n".join(lines))


@router.message(Command("rename"))
async def cmd_rename(message: Message, bot: Bot):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("❌ Использование: <code>/rename &lt;Новое название&gt;</code>")
        return

    player = await get_player_by_user_id(message.from_user.id)
    if not player:
        await message.reply("❌ Ты не зарегистрирован.")
        return

    new_name = args[1].strip()
    old_name = player["country_display"]
    await rename_country(message.from_user.id, new_name)
    await send_announcement(bot, f"📝 {player['flag']} <b>{old_name}</b> переименована в <b>{new_name}</b>")
    await message.reply(f"✅ Переименовано: <b>{old_name}</b> → <b>{new_name}</b>")


@router.message(Command("buydiv"))
async def cmd_buydiv(message: Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        types_list = "\n".join(
            f"  <code>{k}</code> — {v['name']} {v['emoji']} (${v['cost']}млрд/дивизия)"
            for k, v in DIVISION_TYPES.items()
        )
        await message.reply(
            f"❌ Использование: <code>/buydiv &lt;тип&gt; &lt;количество&gt;</code>\n\n"
            f"Типы дивизий:\n{types_list}"
        )
        return

    player = await get_player_by_user_id(message.from_user.id)
    if not player:
        await message.reply("❌ Ты не зарегистрирован.")
        return

    div_type = args[1].strip().lower()
    if div_type not in DIVISION_TYPES:
        await message.reply(f"❌ Неизвестный тип: <code>{div_type}</code>")
        return

    try:
        count = int(args[2])
        if count < 1:
            raise ValueError
    except ValueError:
        await message.reply("❌ Количество должно быть положительным числом.")
        return

    info = DIVISION_TYPES[div_type]
    total_cost = info["cost"] * count

    if player["treasury"] < total_cost:
        await message.reply(
            f"❌ Недостаточно средств.\n"
            f"Нужно: ${total_cost:.1f}млрд | Казна: ${player['treasury']:.1f}млрд"
        )
        return

    await buy_division(player["country"], div_type, count)
    new_treasury = round(player["treasury"] - total_cost, 2)
    new_total = player["total_divisions"] + count
    await update_player(player["user_id"], treasury=new_treasury, total_divisions=new_total)

    await message.reply(
        f"✅ Куплено: {info['emoji']} {info['name']} × {count}\n"
        f"💸 Потрачено: ${total_cost:.1f}млрд\n"
        f"🏦 Остаток казны: ${new_treasury:.1f}млрд"
    )
