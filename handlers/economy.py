import logging
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message

from services.player_service import smart_find_country, get_player_by_user_id, get_player_by_country, update_player, update_player_by_country
from services.topic_service import send_announcement
from database import DB_PATH
import aiosqlite

router = Router()
logger = logging.getLogger(__name__)

TAX_LEVELS = {
    "low":    {"label": "Низкие",    "fatigue_mod": -0.1, "gdp_mod": -0.5},
    "normal": {"label": "Нормальные","fatigue_mod": 0,    "gdp_mod": 0},
    "high":   {"label": "Высокие",   "fatigue_mod": 0.3,  "gdp_mod": 1.0},
}


@router.message(Command("economy"))
async def cmd_economy(message: Message):
    player = await get_player_by_user_id(message.from_user.id)
    if not player:
        await message.reply("❌ Ты не зарегистрирован.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM debts WHERE LOWER(borrower_country) = LOWER(?) AND status = 'active'",
            (player["country"],)
        ) as cur:
            debts = [dict(r) for r in await cur.fetchall()]

        async with db.execute(
            "SELECT * FROM debts WHERE LOWER(lender_country) = LOWER(?) AND status = 'active'",
            (player["country"],)
        ) as cur:
            loans = [dict(r) for r in await cur.fetchall()]

        async with db.execute(
            "SELECT * FROM trade_deals WHERE (LOWER(country1)=LOWER(?) OR LOWER(country2)=LOWER(?)) AND status='active'",
            (player["country"], player["country"])
        ) as cur:
            trades = [dict(r) for r in await cur.fetchall()]

    tax_info = TAX_LEVELS.get(player.get("tax_level", "normal"), TAX_LEVELS["normal"])

    debt_total = sum(d["amount"] for d in debts)
    loan_total = sum(l["amount"] for l in loans)

    text = (
        f"💸 <b>Экономика {player['flag']} {player['country_display']}</b>\n\n"
        f"💰 ВВП: ${player['gdp']:.1f}млрд\n"
        f"🏦 Казна (ДД): ${player['treasury']:.2f}млрд\n"
        f"📈 Рост ВВП/день: {2 + player.get('gdp_growth_bonus', 0):.1f}%\n\n"
        f"💼 Налоги: {tax_info['label']}\n"
        f"  Влияние на усталость: {tax_info['fatigue_mod']:+.1f}%/тик\n\n"
    )

    if debts:
        text += f"📉 <b>Долги ({len(debts)}):</b>\n"
        for d in debts:
            text += f"  • {d['lender_country']}: ${d['amount']:.1f}млрд\n"
        text += f"  Итого: ${debt_total:.1f}млрд\n\n"

    if loans:
        text += f"📈 <b>Выданные займы ({len(loans)}):</b>\n"
        for l in loans:
            text += f"  • {l['borrower_country']}: ${l['amount']:.1f}млрд\n"
        text += f"  Итого: ${loan_total:.1f}млрд\n\n"

    if trades:
        text += f"🤝 <b>Торговые соглашения ({len(trades)}):</b>\n"
        for t in trades:
            partner = t["country2"] if t["country1"].lower() == player["country"].lower() else t["country1"]
            my_bonus = t["gdp_bonus_1"] if t["country1"].lower() == player["country"].lower() else t["gdp_bonus_2"]
            text += f"  • {partner}: +{my_bonus:.1f}% ВВП\n"

    text += (
        f"\n📋 <b>Команды:</b>\n"
        f"/tax &lt;low|normal|high&gt; — изменить налоги\n"
        f"/loan &lt;страна&gt; &lt;сумма&gt; — предложить займ\n"
        f"/trade &lt;страна&gt; &lt;мой_бонус&gt; &lt;их_бонус&gt; — предложить торговлю"
    )

    await message.reply(text)


@router.message(Command("tax"))
async def cmd_tax(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or args[1].lower() not in TAX_LEVELS:
        await message.reply(
            "❌ Использование: <code>/tax &lt;low|normal|high&gt;</code>\n\n"
            "💼 <b>Уровни налогов:</b>\n"
            "low — низкие: меньше усталости, меньше ВВП\n"
            "normal — нормальные: без изменений\n"
            "high — высокие: больше усталости (+0.3%/тик), больше казны"
        )
        return

    player = await get_player_by_user_id(message.from_user.id)
    if not player:
        await message.reply("❌ Ты не зарегистрирован.")
        return

    new_tax = args[1].lower()
    await update_player(player["user_id"], tax_level=new_tax)
    info = TAX_LEVELS[new_tax]
    await message.reply(
        f"✅ Налоговый режим изменён на <b>{info['label']}</b>\n"
        f"Влияние на усталость: {info['fatigue_mod']:+.1f}%/тик"
    )


@router.message(Command("loan"))
async def cmd_loan(message: Message, bot: Bot):
    # формат: /loan <страна> | <сумма>
    raw = message.text.split(maxsplit=1)
    rest = raw[1].strip() if len(raw) > 1 else ""
    if "|" in rest:
        borrower_name, amount_raw = [x.strip() for x in rest.split("|", 1)]
    else:
        parts2 = rest.rsplit(maxsplit=1)
        if len(parts2) < 2:
            await message.reply("❌ Использование: <code>/loan &lt;страна&gt; | &lt;сумма&gt;</code>\nПример: <code>/loan Китайская Народная Республика | 500</code>")
            return
        borrower_name, amount_raw = parts2[0].strip(), parts2[1].strip()

    lender = await get_player_by_user_id(message.from_user.id)
    if not lender:
        await message.reply("❌ Ты не зарегистрирован.")
        return

    borrower = await smart_find_country(borrower_name)
    if not borrower:
        await message.reply(f"❌ Страна <b>{borrower_name}</b> не найдена.")
        return

    try:
        amount = float(amount_raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.reply("❌ Введи корректную сумму.")
        return

    if lender["treasury"] < amount:
        await message.reply(f"❌ Недостаточно средств. Казна: ${lender['treasury']:.1f}млрд")
        return

    await update_player(lender["user_id"], treasury=round(lender["treasury"] - amount, 2))
    await update_player(borrower["user_id"], treasury=round(borrower["treasury"] + amount, 2))

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO debts (lender_country, borrower_country, amount) VALUES (?, ?, ?)",
            (lender["country"], borrower["country"], amount),
        )
        await db.commit()

    await send_announcement(
        bot,
        f"💸 {lender['flag']} <b>{lender['country_display']}</b> выдал займ "
        f"{borrower['flag']} <b>{borrower['country_display']}</b> на ${amount:.1f}млрд"
    )
    await message.reply(
        f"✅ Займ выдан!\n"
        f"{borrower['flag']} {borrower['country_display']} получил ${amount:.1f}млрд\n"
        f"Твоя казна: ${lender['treasury'] - amount:.1f}млрд"
    )


@router.message(Command("trade"))
async def cmd_trade(message: Message, bot: Bot):
    # формат: /trade <страна> | <мой%> | <их%>
    raw = message.text.split(maxsplit=1)
    rest = raw[1].strip() if len(raw) > 1 else ""
    parts2 = [x.strip() for x in rest.split("|")]
    if len(parts2) < 3:
        await message.reply(
            "❌ Использование: <code>/trade &lt;страна&gt; | &lt;мой%&gt; | &lt;их%&gt;</code>\n"
            "Пример: <code>/trade Китайская Народная Республика | 1.5 | 1.5</code>"
        )
        return

    player = await get_player_by_user_id(message.from_user.id)
    if not player:
        await message.reply("❌ Ты не зарегистрирован.")
        return

    partner_name = parts2[0]
    partner = await smart_find_country(partner_name)
    if not partner:
        await message.reply(f"❌ Страна <b>{partner_name}</b> не найдена.")
        return

    try:
        my_bonus = float(parts2[1])
        their_bonus = float(parts2[2])
        if my_bonus < 0 or their_bonus < 0:
            raise ValueError
    except ValueError:
        await message.reply("❌ Введи корректные значения бонусов.")
        return

    MAX_TRADE_BONUS = 10.0
    if my_bonus > MAX_TRADE_BONUS or their_bonus > MAX_TRADE_BONUS:
        await message.reply(f"❌ Максимальный бонус от торговли — {MAX_TRADE_BONUS}% ВВП.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO trade_deals (country1, country2, gdp_bonus_1, gdp_bonus_2)
               VALUES (?, ?, ?, ?)""",
            (player["country"], partner["country"], my_bonus, their_bonus),
        )
        trade_id = (await (await db.execute("SELECT last_insert_rowid()")).fetchone())[0]
        await db.commit()

    bonus_1 = player.get("gdp_growth_bonus", 0) + my_bonus
    bonus_2 = partner.get("gdp_growth_bonus", 0) + their_bonus
    await update_player(player["user_id"], gdp_growth_bonus=round(bonus_1, 2))
    await update_player(partner["user_id"], gdp_growth_bonus=round(bonus_2, 2))

    await send_announcement(
        bot,
        f"🤝 Торговое соглашение!\n"
        f"{player['flag']} <b>{player['country_display']}</b> +{my_bonus:.1f}% ВВП\n"
        f"{partner['flag']} <b>{partner['country_display']}</b> +{their_bonus:.1f}% ВВП"
    )
    await message.reply(
        f"✅ Торговое соглашение с {partner['flag']} {partner['country_display']} заключено!\n"
        f"Твой бонус: +{my_bonus:.1f}% ВВП/день\n"
        f"Их бонус: +{their_bonus:.1f}% ВВП/день"
    )
