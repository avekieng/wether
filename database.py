import aiosqlite
import logging

DB_PATH = "geopolitics.db"
logger = logging.getLogger(__name__)


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS players (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                country TEXT UNIQUE,
                country_display TEXT,
                flag TEXT,
                topic_id INTEGER,
                gdp REAL DEFAULT 100,
                area REAL DEFAULT 100000,
                population INTEGER DEFAULT 5000000,
                military_power INTEGER DEFAULT 50,
                stability INTEGER DEFAULT 80,
                treasury REAL DEFAULT 100,
                fatigue REAL DEFAULT 0,
                tax_level TEXT DEFAULT 'normal',
                gdp_growth_bonus REAL DEFAULT 0,
                total_divisions INTEGER DEFAULT 20,
                civil_war INTEGER DEFAULT 0,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS divisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                country TEXT,
                div_type TEXT,
                count INTEGER DEFAULT 0,
                front TEXT DEFAULT 'reserve',
                war_id INTEGER,
                FOREIGN KEY (country) REFERENCES players(country)
            );

            CREATE TABLE IF NOT EXISTS wars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attacker_country TEXT,
                defender_country TEXT,
                status TEXT DEFAULT 'active',
                attacker_territory REAL DEFAULT 0,
                defender_territory REAL DEFAULT 0,
                topic_id INTEGER,
                reason TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP,
                FOREIGN KEY (attacker_country) REFERENCES players(country),
                FOREIGN KEY (defender_country) REFERENCES players(country)
            );

            CREATE TABLE IF NOT EXISTS war_fronts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                war_id INTEGER,
                front_name TEXT,
                attacker_divisions TEXT DEFAULT '{}',
                defender_divisions TEXT DEFAULT '{}',
                control REAL DEFAULT 50,
                FOREIGN KEY (war_id) REFERENCES wars(id)
            );

            CREATE TABLE IF NOT EXISTS war_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                war_id INTEGER,
                country TEXT,
                action_text TEXT,
                result_text TEXT,
                attacker_losses TEXT DEFAULT '{}',
                defender_losses TEXT DEFAULT '{}',
                territory_change REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (war_id) REFERENCES wars(id)
            );

            CREATE TABLE IF NOT EXISTS alliances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                founder_country TEXT,
                alliance_type TEXT DEFAULT 'hybrid',
                topic_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS alliance_members (
                alliance_id INTEGER,
                country TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (alliance_id, country),
                FOREIGN KEY (alliance_id) REFERENCES alliances(id)
            );

            CREATE TABLE IF NOT EXISTS alliance_invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alliance_id INTEGER,
                from_country TEXT,
                to_country TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS treaties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                country1 TEXT,
                country2 TEXT,
                treaty_type TEXT,
                terms TEXT,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS debts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lender_country TEXT,
                borrower_country TEXT,
                amount REAL,
                interest_rate REAL DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS court_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plaintiff TEXT,
                defendant TEXT,
                description TEXT,
                status TEXT DEFAULT 'open',
                verdict TEXT,
                topic_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS trade_deals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                country1 TEXT,
                country2 TEXT,
                gdp_bonus_1 REAL DEFAULT 0,
                gdp_bonus_2 REAL DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await db.commit()
    logger.info("База данных инициализирована") #fixme // #fuck off nigger>> i dont fix this shit


async def get_db():
    return aiosqlite.connect(DB_PATH)
