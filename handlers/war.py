import logging
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message

from config import GROUP_ID, DIVISION_TYPES, WARS_TOPIC_ID
from services.player_service import smart_find_country, get_player_by_user_id, get_player_by_country, update_player, update_player_by_country
from services.war_service import (
    get_active_war, get_all_wars_for_country, create_war, end_war,
    update_war, add_war_action, get_war_history, get_war_fronts,
)
from services.division_service import (
    get_divisions_summary, get_front_divisions, move_divisions,
    apply_losses, calc_front_power, apply_counters,
)
from services.alliance_service import get_military_allies
from services.topic_service import send_to_topic, send_announcement
from services.ai_service import simulate_war_action

router = Router()
logger = logging.getLogger(__name__)

MILITARY_KEYWORDS = [
    "атак", "удар", "наступл", "захват", "взят", "штурм", "бомб", "ракет", "обстрел",
    "операц", "разведк", "оборон", "отступ", "перегрупп", "окружен", "блокад",
    "высадк", "десант", "переброс", "ликвид", "уничтож", "подавл", "форсир",
    "прорыв", "фланг", "окоп", "артилл", "миномет", "снайпер", "засад",
    "deploy", "advance", "retreat", "assault", "capture", "strike",
]

def is_military_action(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in MILITARY_KEYWORDS)


@router.message(Command("war"))
async def cmd_war(message: Message, bot: Bot):
    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        await message.reply(
            "⚔️ <b>Команды войны:</b>\n"
            "/war start &lt;страна&gt; [причина] — объявить войну\n"
            "/war action &lt;действие&gt; — военная операция\n"
            "/war deploy &lt;направление&gt; &lt;тип&gt; &lt;кол-во&gt; — перебросить дивизии\n"
            "/war fronts — состояние фронтов\n"
            "/war stop &lt;страна&gt; — предложить мир\n"
            "/war status — активные войны"
        )
        return

    sub = args[1].lower()
    if sub == "start":
        await war_start(message, bot, args)
    elif sub == "action":
        await war_action(message, bot, args)
    elif sub == "deploy":
        await war_deploy(message, args)
    elif sub == "fronts":
        await war_fronts(message)
    elif sub == "stop":
        await war_stop(message, bot, args)
    elif sub == "status":
        await war_status(message)
    else:
        await message.reply("❌ Неизвестная подкоманда.")


async def war_start(message: Message, bot: Bot, args: list):
    # формат: /war start <страна> | <причина>  или  /war start <страна>
    raw = message.text.split(maxsplit=2)
    if len(raw) < 3:
        await message.reply("❌ Использование: <code>/war start &lt;страна&gt; | &lt;причина&gt;</code>")
        return

    attacker = await get_player_by_user_id(message.from_user.id)
    if not attacker:
        await message.reply("❌ Ты не зарегистрирован.")
        return

    rest = raw[2]
    if "|" in rest:
        defender_name, reason = [x.strip() for x in rest.split("|", 1)]
    else:
        defender_name, reason = rest.strip(), "Не указана"
    defender = await smart_find_country(defender_name)
    if not defender:
        await message.reply(f"❌ Страна <b>{defender_name}</b> не найдена.")
        return

    if attacker["country"] == defender["country"]:
        await message.reply("❌ Нельзя объявить войну самому себе.")
        return

    existing = await get_active_war(attacker["country"], defender["country"])
    if existing:
        await message.reply("❌ Между этими странами уже идёт война!")
        return

    war_id = await create_war(attacker["country"], defender["country"], WARS_TOPIC_ID, reason)

    atk_divs = await get_divisions_summary(attacker["country"])

    def fmt_divs_summary(d: dict) -> str:
        lines = []
        for dt, info in DIVISION_TYPES.items():
            total = d.get(dt, {}).get("total", 0)
            if total > 0:
                lines.append(f"{info['emoji']} {info['name']}: {total}")
        return "\n".join(lines) if lines else "нет данных"

    allies = await get_military_allies(defender["country"])
    ally_text = f"\n🤝 Союзники защитника: {', '.join(allies)}" if allies else ""

    war_intro = (
        f"🚨 <b>ОБЪЯВЛЕНИЕ ВОЙНЫ</b> 🚨\n\n"
        f"{attacker['flag']} <b>{attacker['country_display']}</b> объявляет войну "
        f"{defender['flag']} <b>{defender['country_display']}</b>!\n\n"
        f"📋 Причина: {reason}\n\n"
        f"📊 <b>Баланс сил:</b>\n"
        f"{attacker['flag']} Военная мощь: {attacker['military_power']}/100\n"
        f"{fmt_divs_summary(atk_divs)}\n\n"
        f"{defender['flag']} Военная мощь: {defender['military_power']}/100\n"
        f"нет данных{ally_text}\n\n"
        f"💰 ВВП: {attacker['flag']} ${attacker['gdp']:.0f}млрд vs {defender['flag']} ${defender['gdp']:.0f}млрд\n\n"
        f"🆔 ID войны: <code>{war_id}</code>\n"
        f"📌 Переброска: <code>/war deploy &lt;направление&gt; &lt;тип&gt; &lt;кол-во&gt;</code>\n"
        f"📌 Операция: <code>/war action &lt;описание&gt;</code>"
    )
    await send_to_topic(bot, WARS_TOPIC_ID, war_intro)
    await send_announcement(
        bot,
        f"🚨 {attacker['flag']} <b>{attacker['country_display']}</b> объявляет войну "
        f"{defender['flag']} <b>{defender['country_display']}</b>!{ally_text}"
    )
    await message.reply(
        f"⚔️ Война объявлена! ID: <code>{war_id}</code>\n"
        f"Перебрасывай дивизии: /war deploy"
    )


async def war_deploy(message: Message, args: list):
    parts = message.text.split(maxsplit=4)
    if len(parts) < 5:
        types_hint = ", ".join(f"<code>{k}</code>" for k in DIVISION_TYPES)
        await message.reply(
            f"❌ Использование: <code>/war deploy &lt;направление&gt; &lt;тип&gt; &lt;кол-во&gt;</code>\n"
            f"Пример: <code>/war deploy вашингтон бпла 10</code>\n"
            f"Типы: {types_hint}"
        )
        return

    player = await get_player_by_user_id(message.from_user.id)
    if not player:
        await message.reply("❌ Ты не зарегистрирован.")
        return

    wars = await get_all_wars_for_country(player["country"])
    if not wars:
        await message.reply("❌ У тебя нет активных войн.")
        return

    war = wars[0]
    front_name = parts[2].strip().lower().replace(" ", "_")
    div_type = parts[3].strip().lower()
    try:
        count = int(parts[4])
        if count < 1:
            raise ValueError
    except ValueError:
        await message.reply("❌ Количество должно быть положительным числом.")
        return

    if div_type not in DIVISION_TYPES:
        await message.reply(f"❌ Неизвестный тип: <code>{div_type}</code>")
        return

    ok, msg = await move_divisions(player["country"], div_type, count, front_name, war["id"])
    if not ok:
        await message.reply(f"❌ {msg}")
        return

    info = DIVISION_TYPES[div_type]
    await message.reply(
        f"✅ {info['emoji']} {info['name']} × {count} переброшено на направление <b>{front_name}</b>"
    )


async def war_action(message: Message, bot: Bot, args: list):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.reply("❌ Использование: <code>/war action &lt;описание действия&gt;</code>")
        return

    player = await get_player_by_user_id(message.from_user.id)
    if not player:
        await message.reply("❌ Ты не зарегистрирован.")
        return

    wars = await get_all_wars_for_country(player["country"])
    if not wars:
        await message.reply("❌ У тебя нет активных войн.")
        return

    action_text = parts[2].strip()

    if not is_military_action(action_text):
        await message.reply(
            "❌ Это не похоже на военное действие.\n"
            "Опиши конкретную операцию: атаку, наступление, оборону, удар и т.д."
        )
        return

    war = wars[0]
    is_attacker = war["attacker_country"] == player["country"]
    enemy_country = war["defender_country"] if is_attacker else war["attacker_country"]
    enemy = await smart_find_country(enemy_country)
    if not enemy:
        await message.reply("❌ Противник не найден.")
        return

    wait_msg = await message.reply("⚙️ Симулирую боевое действие...")

    history = await get_war_history(war["id"], limit=5)
    history_texts = [f"[{h['country']}]: {h['action_text']} → {h['result_text'][:80]}" for h in reversed(history)]

    player_fronts = await get_front_divisions(player["country"], war["id"])
    enemy_fronts = await get_front_divisions(enemy["country"], war["id"])

    # Суммируем все войска со всех фронтов атакующего
    atk_divs_total: dict[str, int] = {}
    for front_divs in player_fronts.values():
        for dt, cnt in front_divs.items():
            atk_divs_total[dt] = atk_divs_total.get(dt, 0) + cnt

    dfn_divs_total: dict[str, int] = {}
    for front_divs in enemy_fronts.values():
        for dt, cnt in front_divs.items():
            dfn_divs_total[dt] = dfn_divs_total.get(dt, 0) + cnt

    # Определяем главный активный фронт (где больше войск у атакующего)
    main_front = "главное направление"
    if player_fronts:
        main_front = max(
            player_fronts,
            key=lambda f: sum(player_fronts[f].values())
        )

    if is_attacker:
        atk_divs = atk_divs_total
        dfn_divs = dfn_divs_total
        attacker_data = player
        defender_data = enemy
    else:
        atk_divs = dfn_divs_total
        dfn_divs = atk_divs_total
        attacker_data = enemy
        defender_data = player

    result = await simulate_war_action(
        attacker=attacker_data,
        defender=defender_data,
        action=action_text,
        front_name=main_front,
        attacker_divs=atk_divs,
        defender_divs=dfn_divs,
        war_history=history_texts,
        attacker_territory=war["attacker_territory"],
    )

    atk_power = calc_front_power(atk_divs)
    dfn_power = calc_front_power(dfn_divs)
    atk_eff, dfn_eff = apply_counters(atk_power, dfn_power)

    territory_change = result.get("territory_change", 0)
    atk_losses = result.get("attacker_losses", {})
    dfn_losses = result.get("defender_losses", {})

    if is_attacker:
        await apply_losses(player["country"], war["id"], atk_losses)
        await apply_losses(enemy["country"], war["id"], dfn_losses)
        new_territory = max(0.0, min(100.0, war["attacker_territory"] + territory_change))
    else:
        await apply_losses(enemy["country"], war["id"], atk_losses)
        await apply_losses(player["country"], war["id"], dfn_losses)
        new_territory = max(0.0, min(100.0, war["attacker_territory"] - territory_change))

    await update_war(war["id"], attacker_territory=new_territory)

    atk_mp = max(10, min(100, attacker_data["military_power"] + result.get("attacker_morale_change", 0)))
    dfn_mp = max(10, min(100, defender_data["military_power"] + result.get("defender_morale_change", 0)))
    await update_player(attacker_data["user_id"], military_power=atk_mp)
    await update_player(defender_data["user_id"], military_power=dfn_mp)

    await add_war_action(
        war_id=war["id"],
        country=player["country"],
        action_text=action_text,
        result_text=result.get("narrative", ""),
        attacker_losses=atk_losses,
        defender_losses=dfn_losses,
        territory_change=territory_change,
    )

    def fmt_losses(d: dict) -> str:
        parts = [f"{DIVISION_TYPES[k]['emoji']}{v}" for k, v in d.items() if v > 0 and k in DIVISION_TYPES]
        return ", ".join(parts) if parts else "—"

    narrative = result.get("narrative", "Операция выполнена.")
    has_atk = any(v > 0 for v in atk_losses.values())
    has_dfn = any(v > 0 for v in dfn_losses.values())

    # Формируем список войск на фронте
    def fmt_front(d: dict) -> str:
        parts = [f"{DIVISION_TYPES[k]['emoji']}{v}" for k, v in d.items() if v > 0 and k in DIVISION_TYPES]
        return " ".join(parts) if parts else "нет войск"

    report = (
        f"{'⚔️' if is_attacker else '🛡️'} <b>{player['flag']} {player['country_display']}</b>\n"
        f"<i>«{action_text[:120]}»</i>\n\n"
        f"📜 {narrative}\n\n"
        f"📊 <b>Потери:</b>\n"
        f"{attacker_data['flag']} {attacker_data['country_display']}: {fmt_losses(atk_losses) if has_atk else '—'}\n"
        f"{defender_data['flag']} {defender_data['country_display']}: {fmt_losses(dfn_losses) if has_dfn else '—'}\n\n"
        f"🪖 Войска: {attacker_data['flag']} {fmt_front(atk_divs)} vs {defender_data['flag']} {fmt_front(dfn_divs)}\n"
        f"🗺️ Изменение: {territory_change:+.1f}% → итого {new_territory:.1f}%"
    )
    hint = result.get("next_hint", "")
    if hint and hint != "подсказка":
        report += f"\n\n💡 {hint}"

    await send_to_topic(bot, WARS_TOPIC_ID, report)
    await wait_msg.edit_text("✅ Операция выполнена. Результат — в топике войны.")


async def war_fronts(message: Message):
    player = await get_player_by_user_id(message.from_user.id)
    if not player:
        await message.reply("❌ Ты не зарегистрирован.")
        return

    wars = await get_all_wars_for_country(player["country"])
    if not wars:
        await message.reply("✅ Нет активных войн.")
        return

    war = wars[0]
    is_attacker = war["attacker_country"] == player["country"]
    enemy_country = war["defender_country"] if is_attacker else war["attacker_country"]

    my_fronts = await get_front_divisions(player["country"], war["id"])
    enemy_fronts = await get_front_divisions(enemy_country, war["id"])
    reserve = await get_divisions_summary(player["country"])

    lines = [f"🗺️ <b>Фронты: {player['flag']} {player['country_display']}</b>\n"]

    all_fronts = set(list(my_fronts.keys()) + list(enemy_fronts.keys()))
    if all_fronts:
        for front in sorted(all_fronts):
            my = my_fronts.get(front, {})
            en = enemy_fronts.get(front, {})
            my_str = " ".join(f"{DIVISION_TYPES[k]['emoji']}{v}" for k, v in my.items() if v > 0 and k in DIVISION_TYPES) or "нет войск"
            en_str = " ".join(f"{DIVISION_TYPES[k]['emoji']}{v}" for k, v in en.items() if v > 0 and k in DIVISION_TYPES) or "нет войск"
            lines.append(f"📍 <b>{front}</b>")
            lines.append(f"  {player['flag']} {my_str}  vs  {enemy_country} {en_str}")
    else:
        lines.append("Нет активных направлений. Используй /war deploy")

    lines.append(f"\n📦 <b>Резерв:</b>")
    has_reserve = False
    for dt, info in DIVISION_TYPES.items():
        r = reserve.get(dt, {}).get("reserve", 0)
        if r > 0:
            has_reserve = True
            lines.append(f"  {info['emoji']} {info['name']}: {r} див.")
    if not has_reserve:
        lines.append("  пусто")

    lines.append(f"\n🗺️ Захвачено: {war['attacker_territory']:.1f}%")

    await message.reply("\n".join(lines))


async def war_stop(message: Message, bot: Bot, args: list):
    raw = message.text.split(maxsplit=2)
    if len(raw) < 3:
        await message.reply("❌ Использование: <code>/war stop &lt;страна&gt;</code>")
        return

    player = await get_player_by_user_id(message.from_user.id)
    if not player:
        await message.reply("❌ Ты не зарегистрирован.")
        return

    enemy_name = raw[2].strip()
    enemy = await smart_find_country(enemy_name)
    if not enemy:
        await message.reply(f"❌ Страна {enemy_name} не найдена.")
        return

    war = await get_active_war(player["country"], enemy["country"])
    if not war:
        await message.reply(f"❌ Нет активной войны с {enemy['flag']} {enemy['country_display']}.")
        return

    await end_war(war["id"], status="peace")

    history = await get_war_history(war["id"], limit=200)

    peace_report = (
        f"🕊️ <b>МИРНЫЙ ДОГОВОР</b>\n\n"
        f"{war['attacker_country'].upper()} ↔️ {war['defender_country'].upper()}\n\n"
        f"📊 <b>Итоги:</b>\n"
        f"📋 Сражений: {len(history)}\n"
        f"🗺️ Территория (атакующий): {war['attacker_territory']:+.1f}%\n\n"
        f"✍️ Мир подписан по инициативе {player['flag']} {player['country_display']}"
    )

    await send_to_topic(bot, WARS_TOPIC_ID, peace_report)
    await send_announcement(
        bot,
        f"🕊️ Война {war['attacker_country']} ↔️ {war['defender_country']} завершена миром!"
    )
    await message.reply(f"✅ Мирный договор с {enemy['flag']} {enemy['country_display']} подписан.")


async def war_status(message: Message):
    player = await get_player_by_user_id(message.from_user.id)
    if not player:
        await message.reply("❌ Ты не зарегистрирован.")
        return

    wars = await get_all_wars_for_country(player["country"])
    if not wars:
        await message.reply("✅ Нет активных войн. Мирное время.")
        return

    lines = [f"⚔️ <b>Активные войны {player['flag']} {player['country_display']}:</b>\n"]
    for w in wars:
        is_atk = w["attacker_country"] == player["country"]
        enemy = w["defender_country"] if is_atk else w["attacker_country"]
        role = "⚔️ Атакующий" if is_atk else "🛡️ Защитник"
        lines.append(
            f"• vs <b>{enemy}</b> | {role}\n"
            f"  🗺️ Фронт: {w['attacker_territory']:+.1f}% | ID: <code>{w['id']}</code>"
        )
    await message.reply("\n".join(lines))


@router.message(Command("civil"))
async def cmd_civil(message: Message, bot: Bot):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or args[1].lower() != "suppress":
        await message.reply(
            "🔥 <b>Гражданская война:</b>\n"
            "/civil suppress — бросить ресурсы на подавление восстания"
        )
        return

    player = await get_player_by_user_id(message.from_user.id)
    if not player:
        await message.reply("❌ Ты не зарегистрирован.")
        return

    if not player.get("civil_war"):
        await message.reply("✅ У тебя нет гражданской войны.")
        return

    cost = round(player["gdp"] * 0.05, 2)
    if player["treasury"] < cost:
        await message.reply(
            f"❌ Недостаточно средств для подавления.\n"
            f"Нужно: ${cost:.1f}млрд | Казна: ${player['treasury']:.1f}млрд"
        )
        return

    new_treasury = round(player["treasury"] - cost, 2)
    new_fatigue = max(0, player["fatigue"] - 20)

    if new_fatigue < 70:
        await update_player(player["user_id"], civil_war=0, fatigue=new_fatigue, treasury=new_treasury)
        await send_announcement(
            bot,
            f"🕊️ {player['flag']} <b>{player['country_display']}</b> подавила восстание! "
            f"Усталость: {new_fatigue:.1f}%"
        )
        await message.reply(
            f"✅ Восстание подавлено!\n"
            f"💸 Потрачено: ${cost:.1f}млрд | 😓 Усталость: {new_fatigue:.1f}%"
        )
    else:
        await update_player(player["user_id"], fatigue=new_fatigue, treasury=new_treasury)
        await message.reply(
            f"⚠️ Частично подавлено, но восстание продолжается.\n"
            f"💸 Потрачено: ${cost:.1f}млрд | 😓 Усталость: {new_fatigue:.1f}% (нужно <70%)\n"
            f"Используй /civil suppress повторно."
        )
