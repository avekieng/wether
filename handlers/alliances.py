import logging
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message

from config import GROUP_ID, ALLIANCES_TOPIC_ID
from services.player_service import smart_find_country, get_player_by_user_id, get_player_by_country
from services.alliance_service import (
    create_alliance, get_alliance_by_name, get_alliances_for_country,
    get_alliance_members, add_member, create_invite, get_pending_invite,
    accept_invite, get_all_alliances, remove_member,
)
from services.topic_service import send_to_topic, send_announcement

router = Router()
logger = logging.getLogger(__name__)

ALLIANCE_TYPES = {
    "economic": "💰 Экономический (+ВВП)",
    "military": "⚔️ Военный (взаимооборона)",
    "hybrid": "🌐 Гибридный (экономика + военный)",
}


@router.message(Command("alliance"))
async def cmd_alliance(message: Message, bot: Bot):
    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        await message.reply(
            "🤝 <b>Команды альянсов:</b>\n"
            "/alliance create &lt;тип&gt; &lt;название&gt; — создать альянс\n"
            "  Типы: <code>economic</code>, <code>military</code>, <code>hybrid</code>\n"
            "/alliance invite &lt;название альянса&gt; &lt;страна&gt; — пригласить\n"
            "/alliance accept &lt;название альянса&gt; — принять приглашение\n"
            "/alliance leave &lt;название альянса&gt; — покинуть альянс\n"
            "/alliance info &lt;название&gt; — информация об альянсе\n"
            "/alliance list — все альянсы"
        )
        return

    sub = args[1].lower()
    if sub == "create":
        await alliance_create(message, bot, args)
    elif sub == "invite":
        await alliance_invite(message, bot, args)
    elif sub == "accept":
        await alliance_accept(message, bot, args)
    elif sub == "leave":
        await alliance_leave(message, bot, args)
    elif sub == "info":
        await alliance_info(message, args)
    elif sub == "list":
        await alliance_list(message)
    else:
        await message.reply("❌ Неизвестная подкоманда.")


async def alliance_create(message: Message, bot: Bot, args: list):
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        await message.reply(
            "❌ Использование: <code>/alliance create &lt;тип&gt; &lt;название&gt;</code>\n"
            "Типы: <code>economic</code>, <code>military</code>, <code>hybrid</code>"
        )
        return

    player = await get_player_by_user_id(message.from_user.id)
    if not player:
        await message.reply("❌ Ты не зарегистрирован.")
        return

    alliance_type = parts[2].lower()
    if alliance_type not in ALLIANCE_TYPES:
        await message.reply(f"❌ Неверный тип. Доступны: {', '.join(ALLIANCE_TYPES.keys())}")
        return

    alliance_name = parts[3].strip()
    existing = await get_alliance_by_name(alliance_name)
    if existing:
        await message.reply(f"❌ Альянс с именем <b>{alliance_name}</b> уже существует.")
        return

    wait_msg = await message.reply(f"⏳ Создаю альянс <b>{alliance_name}</b>...")
    type_emoji = {"economic": "💰", "military": "⚔️", "hybrid": "🌐"}.get(alliance_type, "🤝")
    alliance_id = await create_alliance(alliance_name, player["country"], alliance_type, ALLIANCES_TOPIC_ID)
    if not alliance_id:
        await wait_msg.edit_text("❌ Альянс с таким именем уже существует.")
        return

    await send_to_topic(
        bot, ALLIANCES_TOPIC_ID,
        f"{type_emoji} <b>{alliance_name}</b>\n"
        f"Тип: {ALLIANCE_TYPES[alliance_type]}\n"
        f"Основатель: {player['flag']} {player['country_display']}\n\n"
        f"Используйте <code>/alliance invite {alliance_name} &lt;страна&gt;</code> для приглашения участников."
    )

    await send_announcement(
        bot,
        f"🆕 {type_emoji} Создан альянс <b>{alliance_name}</b>!\n"
        f"Тип: {ALLIANCE_TYPES[alliance_type]}\n"
        f"Основатель: {player['flag']} {player['country_display']}"
    )

    await wait_msg.edit_text(
        f"✅ Альянс <b>{alliance_name}</b> создан!\n"
        f"Тип: {ALLIANCE_TYPES[alliance_type]}\n"
        f"ID: <code>{alliance_id}</code>"
    )


async def alliance_invite(message: Message, bot: Bot, args: list):
    # формат: /alliance invite <альянс> | <страна>
    raw = message.text.split(maxsplit=2)
    if len(raw) < 3 or "|" not in raw[2]:
        await message.reply("❌ Использование: <code>/alliance invite &lt;альянс&gt; | &lt;страна&gt;</code>\nПример: <code>/alliance invite НАТО | Китайская Народная Республика</code>")

        return

    player = await get_player_by_user_id(message.from_user.id)
    if not player:
        await message.reply("❌ Ты не зарегистрирован.")
        return

    alliance_name, target_country_name = [x.strip() for x in raw[2].split("|", 1)]

    alliance = await get_alliance_by_name(alliance_name)
    if not alliance:
        await message.reply(f"❌ Альянс <b>{alliance_name}</b> не найден.")
        return

    members = await get_alliance_members(alliance["id"])
    if player["country"].lower() not in [m.lower() for m in members]:
        await message.reply("❌ Ты не состоишь в этом альянсе.")
        return

    target = await smart_find_country(target_country_name)
    if not target:
        await message.reply(f"❌ Страна <b>{target_country_name}</b> не найдена.")
        return

    if target["country"].lower() in [m.lower() for m in members]:
        await message.reply(f"❌ {target['flag']} {target['country_display']} уже в альянсе.")
        return

    invite_id = await create_invite(alliance["id"], player["country"], target["country"])

    type_emoji = {"economic": "💰", "military": "⚔️", "hybrid": "🌐"}.get(alliance["alliance_type"], "🤝")

    if True:
        await send_to_topic(
            bot, ALLIANCES_TOPIC_ID,
            f"📨 {player['flag']} {player['country_display']} приглашает "
            f"{target['flag']} {target['country_display']} в альянс!"
        )

    await send_announcement(
        bot,
        f"📨 {target['flag']} <b>{target['country_display']}</b> (@{target['username']}), тебя приглашают в альянс "
        f"{type_emoji} <b>{alliance_name}</b>!\n"
        f"Чтобы принять: <code>/alliance accept {alliance_name}</code>\n"
        f"(команду пишет игрок за {target['country_display']})"
    )

    await message.reply(
        f"✅ Приглашение отправлено {target['flag']} {target['country_display']} (@{target['username']})!\n"
        f"Игрок за {target['country_display']} должен написать: <code>/alliance accept {alliance_name}</code>"
    )


async def alliance_accept(message: Message, bot: Bot, args: list):
    raw = message.text.split(maxsplit=2)
    if len(raw) < 3:
        await message.reply("❌ Использование: <code>/alliance accept &lt;название альянса&gt;</code>")
        return

    player = await get_player_by_user_id(message.from_user.id)
    if not player:
        await message.reply("❌ Ты не зарегистрирован.")
        return

    alliance_name = raw[2].strip()
    alliance = await get_alliance_by_name(alliance_name)
    if not alliance:
        await message.reply(f"❌ Альянс <b>{alliance_name}</b> не найден.")
        return

    invite = await get_pending_invite(player["country"], alliance["id"])
    if not invite:
        player_country = player['country_display']
        await message.reply(
            f"❌ У страны <b>{player_country}</b> нет приглашения в <b>{alliance_name}</b>.\n"
            f"Принять может только игрок за страну, которую пригласили."
        )
        return

    await accept_invite(invite["id"])
    ok = await add_member(alliance["id"], player["country"])
    if not ok:
        await message.reply("❌ Ты уже в этом альянсе.")
        return

    type_emoji = {"economic": "💰", "military": "⚔️", "hybrid": "🌐"}.get(alliance["alliance_type"], "🤝")

    if True:
        await send_to_topic(
            bot, ALLIANCES_TOPIC_ID,
            f"🎉 {player['flag']} <b>{player['country_display']}</b> вступил(а) в альянс!"
        )

    await send_announcement(
        bot,
        f"🤝 {player['flag']} <b>{player['country_display']}</b> вступает в альянс "
        f"{type_emoji} <b>{alliance_name}</b>!"
    )

    await message.reply(f"✅ Ты вступил(а) в альянс {type_emoji} <b>{alliance_name}</b>!")


async def alliance_leave(message: Message, bot: Bot, args: list):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.reply("❌ Использование: <code>/alliance leave &lt;название альянса&gt;</code>")
        return

    player = await get_player_by_user_id(message.from_user.id)
    if not player:
        await message.reply("❌ Ты не зарегистрирован.")
        return

    alliance_name = parts[2].strip()
    alliance = await get_alliance_by_name(alliance_name)
    if not alliance:
        await message.reply(f"❌ Альянс <b>{alliance_name}</b> не найден.")
        return

    members = await get_alliance_members(alliance["id"])
    if player["country"].lower() not in [m.lower() for m in members]:
        await message.reply("❌ Ты не состоишь в этом альянсе.")
        return

    await remove_member(alliance["id"], player["country"])

    type_emoji = {"economic": "💰", "military": "⚔️", "hybrid": "🌐"}.get(alliance["alliance_type"], "🤝")

    if True:
        await send_to_topic(
            bot, ALLIANCES_TOPIC_ID,
            f"👋 {player['flag']} {player['country_display']} покинул(а) альянс."
        )

    await send_announcement(
        bot,
        f"👋 {player['flag']} <b>{player['country_display']}</b> покинул(а) альянс "
        f"{type_emoji} <b>{alliance_name}</b>."
    )

    await message.reply(f"✅ Ты покинул(а) альянс <b>{alliance_name}</b>.")


async def alliance_info(message: Message, args: list):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        player = await get_player_by_user_id(message.from_user.id)
        if not player:
            await message.reply("❌ Использование: <code>/alliance info &lt;название&gt;</code>")
            return
        alliances = await get_alliances_for_country(player["country"])
        if not alliances:
            await message.reply("❌ Ты не состоишь ни в одном альянсе.")
            return
        alliance = alliances[0]
    else:
        alliance = await get_alliance_by_name(parts[2].strip())
        if not alliance:
            await message.reply(f"❌ Альянс не найден.")
            return

    members = await get_alliance_members(alliance["id"])
    type_emoji = {"economic": "💰", "military": "⚔️", "hybrid": "🌐"}.get(alliance["alliance_type"], "🤝")

    member_lines = []
    for country in members:
        p = await smart_find_country(country)
        if p:
            member_lines.append(f"  {p['flag']} {p['country_display']} — ${p['gdp']:.0f}млрд")
        else:
            member_lines.append(f"  🏳️ {country}")

    text = (
        f"{type_emoji} <b>{alliance['name']}</b>\n"
        f"Тип: {ALLIANCE_TYPES.get(alliance['alliance_type'], alliance['alliance_type'])}\n"
        f"Основатель: {alliance['founder_country']}\n\n"
        f"👥 Участники ({len(members)}):\n"
        + "\n".join(member_lines)
    )
    await message.reply(text)


async def alliance_list(message: Message):
    alliances = await get_all_alliances()
    if not alliances:
        await message.reply("❌ Нет созданных альянсов.")
        return

    lines = ["🌐 <b>Все альянсы:</b>\n"]
    for a in alliances:
        type_emoji = {"economic": "💰", "military": "⚔️", "hybrid": "🌐"}.get(a["alliance_type"], "🤝")
        members = await get_alliance_members(a["id"])
        lines.append(f"{type_emoji} <b>{a['name']}</b> — {len(members)} участн.")

    await message.reply("\n".join(lines))
