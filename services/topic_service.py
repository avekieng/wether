import logging
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from config import GROUP_ID, ANNOUNCE_TOPIC_ID

logger = logging.getLogger(__name__)


async def create_topic(bot: Bot, name: str) -> int | None:
    try:
        result = await bot.create_forum_topic(chat_id=GROUP_ID, name=name)
        return result.message_thread_id
    except TelegramBadRequest as e:
        logger.error(f"Не удалось создать топик '{name}': {e}")
        return None
    except Exception as e:
        logger.error(f"Ошибка создания топика: {e}")
        return None


async def send_to_topic(bot: Bot, topic_id: int, text: str, **kwargs) -> bool:
    try:
        await bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=topic_id,
            text=text,
            **kwargs
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки в топик {topic_id}: {e}")
        return False


async def send_announcement(bot: Bot, text: str) -> bool:
    return await send_to_topic(bot, ANNOUNCE_TOPIC_ID, text)


async def rename_topic(bot: Bot, topic_id: int, new_name: str) -> bool:
    try:
        await bot.edit_forum_topic(chat_id=GROUP_ID, message_thread_id=topic_id, name=new_name)
        return True
    except Exception as e:
        logger.error(f"Ошибка переименования топика: {e}")
        return False
