import aiohttp
import logging
import json
import re
from config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_BASE_URL
from services._markdown import strip_markdown

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — ИИ-арбитр геополитической ролевой игры в Telegram.
Симуляция реального мира с реальными странами и реалистичной военной логикой.

Правила:
- Опирайся на реальные данные: ВВП, население, военная мощь, география
- Военные действия реалистичны: потери, логистика, снабжение, рельеф
- Дивизии: БПЛА (мощные, дорогие), РЭБ (глушит БПЛА на 70%), Пехота, Воздушные, ПВО (глушит воздушные на 70%)
- ВАЖНО: игроки не могут придумывать результаты. Только ты решаешь исход.
- Отвечай на русском языке, без markdown-форматирования (без **, *, _, #)
- Используй только эмодзи для выделения, не markdown"""


async def _post(messages: list, max_tokens: int = 1000, temperature: float = 0.7, _retry: int = 3) -> str:
    import asyncio
    for attempt in range(_retry):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://geopolitics-rp-bot.tg",
                        "X-Title": "Geopolitics RP Bot",
                    },
                    json={
                        "model": OPENROUTER_MODEL,
                        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    },
                    timeout=aiohttp.ClientTimeout(total=45),
                ) as resp:
                    data = await resp.json()
                    if "choices" in data and data["choices"]:
                        raw = data["choices"][0]["message"]["content"]
                        return strip_markdown(raw)
                    elif "error" in data:
                        err = data["error"]
                        code = err.get("code", 0)
                        msg = err.get("message", "Неизвестная ошибка")
                        if code == 429 and attempt < _retry - 1:
                            wait = 5 * (attempt + 1)
                            logger.warning(f"Rate limit 429, retry {attempt+1}/{_retry} after {wait}s")
                            await asyncio.sleep(wait)
                            continue
                        logger.error(f"OpenRouter error: {err}")
                        return f"❌ Ошибка AI: {msg}"
                    return "❌ Пустой ответ от AI"
        except aiohttp.ClientTimeout:
            if attempt < _retry - 1:
                await asyncio.sleep(3)
                continue
            return "❌ AI не отвечает (таймаут). Попробуй позже."
        except Exception as e:
            logger.error(f"AI request failed: {e}")
            return f"❌ Ошибка подключения к AI: {e}"
    return "❌ AI временно недоступен, попробуй через минуту."


def _parse_json(text: str) -> dict | None:
    if not text:
        return None
    clean = re.sub(r'```(?:json)?\s*|\s*```', '', text).strip()
    match = re.search(r'\{[\s\S]*\}', clean)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    for attempt in [clean + '"}}', clean + '"}', clean + '}']:
        try:
            return json.loads(attempt)
        except Exception:
            pass
    return None


def _sanitize_war_result(result: dict, attacker_divs: dict, defender_divs: dict) -> dict:
    narrative = result.get("narrative", "")
    if not isinstance(narrative, str) or narrative.startswith("{"):
        narrative = "Операция проведена. Результат оценивается командованием."
    result["narrative"] = strip_markdown(narrative[:600])

    try:
        sl = float(result.get("success_level", 0.5))
        result["success_level"] = max(0.0, min(1.0, sl))
    except Exception:
        result["success_level"] = 0.5

    try:
        tc = float(result.get("territory_change", 0))
        result["territory_change"] = max(-15.0, min(15.0, tc))
    except Exception:
        result["territory_change"] = 0.0

    valid_types = {"пехота", "бпла", "рэб", "воздушные", "пво"}

    def clean_losses(losses_raw, div_pool: dict) -> dict:
        if not isinstance(losses_raw, dict):
            return {}
        cleaned = {}
        for k, v in losses_raw.items():
            k = k.lower()
            if k not in valid_types:
                continue
            try:
                v = int(v)
            except Exception:
                continue
            if v <= 0:
                continue
            available = div_pool.get(k, 0)
            cleaned[k] = min(v, max(0, available))
        return cleaned

    result["attacker_losses"] = clean_losses(result.get("attacker_losses", {}), attacker_divs)
    result["defender_losses"] = clean_losses(result.get("defender_losses", {}), defender_divs)

    for key in ("attacker_morale_change", "defender_morale_change"):
        try:
            result[key] = max(-10, min(10, int(result.get(key, 0))))
        except Exception:
            result[key] = 0

    hint = strip_markdown(result.get("next_hint", ""))
    result["next_hint"] = hint if hint and hint != "подсказка" else ""
    return result


async def simulate_war_action(
    attacker: dict, defender: dict, action: str,
    front_name: str, attacker_divs: dict, defender_divs: dict,
    war_history: list[str] = None,
    attacker_territory: float = 0.0,
) -> dict:
    history_text = "\n".join(war_history[-5:]) if war_history else "Начало конфликта"

    def fmt_divs(d: dict) -> str:
        if not d:
            return "нет войск"
        return ", ".join(f"{k}: {v} див." for k, v in d.items() if v > 0)

    atk_has_troops = bool(attacker_divs) and sum(v for v in attacker_divs.values() if isinstance(v, (int, float))) > 0
    dfn_has_troops = bool(defender_divs) and sum(v for v in defender_divs.values() if isinstance(v, (int, float))) > 0

    prompt = f"""Военная симуляция. Ты арбитр — только ты решаешь исход.

АТАКУЮЩИЙ: {attacker['country_display']} {attacker['flag']}
Военная мощь: {attacker['military_power']}/100 | ВВП: ${attacker['gdp']:.0f}млрд | Население: {attacker['population']:,}
Войска на направлении «{front_name}»: {fmt_divs(attacker_divs)}
Есть войска: {"ДА" if atk_has_troops else "НЕТ"}
Захвачено территории: {attacker_territory:.1f}%

ЗАЩИЩАЮЩИЙСЯ: {defender['country_display']} {defender['flag']}
Военная мощь: {defender['military_power']}/100 | ВВП: ${defender['gdp']:.0f}млрд | Население: {defender['population']:,}
Войска на направлении «{front_name}»: {fmt_divs(defender_divs)}
Есть войска: {"ДА" if dfn_has_troops else "НЕТ"}

ИСТОРИЯ:
{history_text}

ДЕЙСТВИЕ: {action}

ПРАВИЛА:
1. Нет войск у атакующего → провал, territory_change=0
2. Есть войска у атакующего, нет у защитника → успех, territory_change 5-12%
3. Оба имеют войска → рассчитай реалистично
4. РЭБ глушит БПЛА на 70%, ПВО глушит воздушные на 70%
5. Максимум territory_change за действие: ±15%
6. Потери — только из реально имеющихся дивизий
7. Ликвидация лидеров, мгновенная капитуляция — невозможны

Ответь ТОЛЬКО чистым JSON без markdown:
{{"narrative":"2-3 предложения без форматирования","success_level":0.5,"attacker_losses":{{"пехота":0}},"defender_losses":{{"пехота":0}},"territory_change":0.0,"attacker_morale_change":0,"defender_morale_change":0,"next_hint":"короткая подсказка"}}"""

    response = await _post([{"role": "user", "content": prompt}], max_tokens=500, temperature=0.5)
    parsed = _parse_json(response)

    if parsed and "narrative" in parsed:
        return _sanitize_war_result(parsed, attacker_divs, defender_divs)

    logger.warning(f"War action parse failed. Raw: {response[:200]}")
    return _sanitize_war_result({
        "narrative": "Операция проведена. Командование оценивает обстановку.",
        "success_level": 0.3,
        "attacker_losses": {},
        "defender_losses": {},
        "territory_change": 0.0,
        "attacker_morale_change": 0,
        "defender_morale_change": 0,
        "next_hint": "",
    }, attacker_divs, defender_divs)


async def ask_ai(prompt: str, context: str = "") -> str:
    messages = []
    if context:
        messages.append({"role": "user", "content": f"Контекст симуляции:\n{context}"})
        messages.append({"role": "assistant", "content": "Понял, учту контекст."})
    messages.append({"role": "user", "content": prompt})
    return await _post(messages)


async def get_country_info(country_name: str, player_data: dict) -> str:
    prompt = f"""Напиши краткое досье страны для геополитической ролевой игры. Без markdown-форматирования, только эмодзи.

Страна: {country_name}
ВВП: ${player_data.get('gdp', '?')}млрд | Площадь: {player_data.get('area', 0):,.0f} км²
Население: {player_data.get('population', 0):,} | Военная мощь: {player_data.get('military', 50)}/100

Включи: столицу, форму правления, ключевые ресурсы, армию, союзников, слабые стороны.
Не более 15 строк. Без **, без *, без #."""
    return await _post([{"role": "user", "content": prompt}])


async def answer_question(question: str, game_context: str) -> str:
    prompt = f"""Ответь на вопрос игрока в контексте геополитической симуляции. Без markdown.

Контекст:
{game_context}

Вопрос: {question}"""
    return await _post([{"role": "user", "content": prompt}])


async def mediate_conflict(plaintiff: str, defendant: str, description: str, context: str) -> str:
    prompt = f"""Ты международный арбитр. Вынеси решение. Без markdown-форматирования.

Истец: {plaintiff}
Ответчик: {defendant}
Суть: {description}
Контекст: {context}

Укажи: кто прав, санкции/компенсации, рекомендации."""
    return await _post([{"role": "user", "content": prompt}], max_tokens=600)


async def evaluate_civil_war(country: str, fatigue: float, gdp: float) -> str:
    prompt = f"""В стране {country} началась гражданская война. Усталость: {fatigue:.1f}% | ВВП: ${gdp:.0f}млрд.
2-3 предложения: кто поднял восстание, ключевые регионы, угрозы правительству. Без markdown."""
    return await _post([{"role": "user", "content": prompt}], max_tokens=250)


async def generate_country_data(raw_input: str) -> dict:
    """Принимает любое написание страны (финляндия, finland, фины, Suomi и т.д.)
    и возвращает нормализованные данные с правильным названием на русском."""
    prompt = f"""Пользователь написал название страны: "{raw_input}"
Определи какая это страна (даже если написано с ошибкой, на другом языке или неофициально).
Верни ТОЛЬКО чистый JSON без markdown и пояснений:
{{"name_ru":"Официальное название на русском","flag":"эмодзи флага","gdp":ВВП в млрд USD число,"area":площадь км2 число,"population":население число,"military":военная мощь 0-100 число,"divisions":количество дивизий число}}
Данные должны быть реальными актуальными. military — реальная боеспособность армии от 0 до 100."""
    response = await _post([{"role": "user", "content": prompt}], max_tokens=200, temperature=0.1)
    parsed = _parse_json(response)
    if parsed and "gdp" in parsed and "flag" in parsed:
        return {
            "name_ru": str(parsed.get("name_ru", raw_input.title())),
            "flag": str(parsed.get("flag", "🏳️")),
            "gdp": float(parsed.get("gdp", 100)),
            "area": float(parsed.get("area", 100000)),
            "population": int(parsed.get("population", 5_000_000)),
            "military": int(parsed.get("military", 40)),
            "divisions": int(parsed.get("divisions", 15)),
        }
    return {
        "name_ru": raw_input.title(),
        "flag": "🏳️", "gdp": 100.0, "area": 100000.0,
        "population": 5_000_000, "military": 40, "divisions": 15,
    }


async def resolve_country_name(raw: str, known_countries: list[str]) -> str | None:
    """Определяет страну по любому написанию и возвращает slug из БД или None."""
    if not raw.strip():
        return None

    known_list = "\n".join(known_countries[:80])
    prompt = f"""Пользователь написал название страны: "{raw}"
Это может быть сокращение, аббревиатура, название на другом языке или с ошибкой.
Примеры: КНР=Китай, USA=США, deutschland=Германия, uk=Великобритания

Список стран зарегистрированных в игре (в нижнем регистре):
{known_list}

Найди наиболее подходящую страну из списка и верни ТОЛЬКО её точное название из списка, без пояснений.
Если совпадения нет — верни: НЕТ"""
    response = await _post([{"role": "user", "content": prompt}], max_tokens=30, temperature=0.1)
    result = response.strip().lower()
    if result == "нет" or not result:
        return None
    
    for country in known_countries:
        if country.lower() == result.lower():
            return country

    for country in known_countries:
        if result in country.lower() or country.lower() in result:
            return country
    return None
