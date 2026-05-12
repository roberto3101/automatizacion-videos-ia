import aiosqlite
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "pipeline.db")


async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = await get_db()
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            personality TEXT,
            voice_id TEXT DEFAULT 'en-US-GuyNeural',
            visual_prompt TEXT,
            sample_hooks TEXT,
            language TEXT DEFAULT 'en',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            topic TEXT,
            script_json TEXT,
            status TEXT DEFAULT 'draft',
            language TEXT DEFAULT 'en',
            duration_target INTEGER DEFAULT 60,
            output_path TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (character_id) REFERENCES characters(id)
        );

        CREATE TABLE IF NOT EXISTS script_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            character_id INTEGER,
            script_json TEXT NOT NULL,
            language TEXT DEFAULT 'en',
            tags TEXT DEFAULT '',
            use_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (character_id) REFERENCES characters(id)
        );

        CREATE TABLE IF NOT EXISTS production_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL,
            step TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            detail TEXT,
            cost_usd REAL DEFAULT 0,
            started_at TEXT,
            finished_at TEXT,
            FOREIGN KEY (video_id) REFERENCES videos(id)
        );
    """)
    await db.commit()
    await db.close()


async def load_default_characters():
    """Load character presets from config/characters/ into DB if not exists."""
    chars_dir = os.path.join(os.path.dirname(__file__), "config", "characters")
    if not os.path.exists(chars_dir):
        return
    db = await get_db()
    for fname in os.listdir(chars_dir):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(chars_dir, fname), "r", encoding="utf-8") as f:
            char = json.load(f)
        existing = await db.execute_fetchall(
            "SELECT id FROM characters WHERE name = ?", (char["name"],)
        )
        if not existing:
            await db.execute(
                """INSERT INTO characters (name, description, personality, voice_id, visual_prompt, sample_hooks, language)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    char["name"],
                    char.get("description", ""),
                    char.get("personality", ""),
                    char.get("voice_id", "en-US-GuyNeural"),
                    char.get("visual_prompt", ""),
                    json.dumps(char.get("sample_hooks", [])),
                    char.get("language", "en"),
                ),
            )
    await db.commit()
    await db.close()
