import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "токен")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "токен опенроутер типо")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini-tts-2025-12-15")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

GROUP_ID = int(os.getenv("GROUP_ID", "айди групы"))
ANNOUNCE_TOPIC_ID = int(os.getenv("ANNOUNCE_TOPIC_ID", "1"))
COUNTRIES_TOPIC_ID = int(os.getenv("COUNTRIES_TOPIC_ID", "13"))
WARS_TOPIC_ID = int(os.getenv("WARS_TOPIC_ID", "146"))
ALLIANCES_TOPIC_ID = int(os.getenv("ALLIANCES_TOPIC_ID", "5001"))
COURT_TOPIC_ID = int(os.getenv("COURT_TOPIC_ID", "1086  ")) # тут типо поменяй ща тут от wether группы

GDP_GROWTH_INTERVAL = 86400
FATIGUE_WAR_INTERVAL = 600
FATIGUE_WAR_INCREASE = 0.5
FATIGUE_CIVIL_WAR_THRESHOLD = 70.0
CIVIL_WAR_GDP_LOSS_INTERVAL = 3600
CIVIL_WAR_GDP_LOSS_PERCENT = 2.0
BASE_GDP_GROWTH_PERCENT = 2.0

DIVISION_TYPES = {
    "бпла": {"name": "БПЛА", "cost": 15.0, "power": 25, "emoji": "🛸"},
    "рэб":  {"name": "РЭБ",  "cost": 10.0, "power": 10, "emoji": "📡"},
    "пехота": {"name": "Пехота", "cost": 5.0, "power": 15, "emoji": "🪖"},
    "воздушные": {"name": "Воздушные войска", "cost": 12.0, "power": 20, "emoji": "✈️"},
    "пво": {"name": "ПВО", "cost": 8.0, "power": 10, "emoji": "🚀"},
}
