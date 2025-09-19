"""
Реализация репозиториев для хранения данных в SQLite.
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
import aiosqlite

from .base import BaseUserRepository, BaseContextRepository, BaseSettingsRepository, BaseAccessControlRepository
from .models import UserProfile, UserContext, BotSettings, AccessControl, Message, MessageRole

# Путь к файлу базы данных
DB_PATH = "data/bot_database.db"
logger = logging.getLogger(__name__)

async def init_db():
    """Инициализирует базу данных и создает таблицы, если они не существуют."""
    # Гарантируем, что директория data существует
    import os
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Таблица пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                requests_limit INTEGER NOT NULL,
                requests_used INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                last_activity TEXT NOT NULL
            )
        """)
        
        # Таблица контекстов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS contexts (
                user_id INTEGER PRIMARY KEY,
                messages TEXT NOT NULL,
                max_messages INTEGER NOT NULL
            )
        """)

        # Таблица настроек (ключ-значение)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Таблица контроля доступа
        await db.execute("""
            CREATE TABLE IF NOT EXISTS access_control (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        # Таблица истории доступа
        await db.execute("""
            CREATE TABLE IF NOT EXISTS access_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                admin_id INTEGER NOT NULL
            )
        """)
        
        await db.commit()
    logger.info("База данных SQLite инициализирована.")

class SQLiteUserRepository(BaseUserRepository):
    """Репозиторий пользователей на SQLite."""

    async def get_user(self, user_id: int) -> Optional[UserProfile]:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
            if row:
                return UserProfile(
                    user_id=row[0],
                    username=row[1],
                    first_name=row[2],
                    last_name=row[3],
                    requests_limit=row[4],
                    requests_used=row[5],
                    created_at=datetime.fromisoformat(row[6]),
                    last_activity=datetime.fromisoformat(row[7])
                )
            return None

    async def create_user(self, user_profile: UserProfile) -> UserProfile:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    user_profile.user_id, user_profile.username, user_profile.first_name,
                    user_profile.last_name, user_profile.requests_limit, user_profile.requests_used,
                    user_profile.created_at.isoformat(), user_profile.last_activity.isoformat()
                )
            )
            await db.commit()
        return user_profile

    async def update_user(self, user_profile: UserProfile) -> UserProfile:
        user_profile.last_activity = datetime.now()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """UPDATE users SET username = ?, first_name = ?, last_name = ?, 
                   requests_limit = ?, requests_used = ?, last_activity = ?
                   WHERE user_id = ?""",
                (
                    user_profile.username, user_profile.first_name, user_profile.last_name,
                    user_profile.requests_limit, user_profile.requests_used,
                    user_profile.last_activity.isoformat(), user_profile.user_id
                )
            )
            await db.commit()
        return user_profile

    async def delete_user(self, user_id: int) -> bool:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def get_all_users(self) -> List[UserProfile]:
        users = []
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT * FROM users")
            rows = await cursor.fetchall()
            for row in rows:
                users.append(UserProfile(
                    user_id=row[0], username=row[1], first_name=row[2], last_name=row[3],
                    requests_limit=row[4], requests_used=row[5],
                    created_at=datetime.fromisoformat(row[6]), last_activity=datetime.fromisoformat(row[7])
                ))
        return users

    async def increment_user_requests(self, user_id: int) -> int:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET requests_used = requests_used + 1, last_activity = ? WHERE user_id = ?",
                (datetime.now().isoformat(), user_id)
            )
            cursor = await db.execute("SELECT requests_used FROM users WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
            await db.commit()
            if row:
                return row[0]
            raise ValueError(f"Пользователь {user_id} не найден")

    async def reset_user_requests(self, user_id: int) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET requests_used = 0, last_activity = ? WHERE user_id = ?",
                (datetime.now().isoformat(), user_id)
            )
            await db.commit()

    async def set_user_limit(self, user_id: int, limit: int) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE users SET requests_limit = ?, last_activity = ? WHERE user_id = ?",
                (limit, datetime.now().isoformat(), user_id)
            )
            await db.commit()

class SQLiteContextRepository(BaseContextRepository):
    """Репозиторий контекстов на SQLite."""

    async def get_context(self, user_id: int) -> Optional[UserContext]:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT messages, max_messages FROM contexts WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
            if row:
                messages_json = json.loads(row[0])
                messages = [Message(role=MessageRole(m["role"]), content=m["content"]) for m in messages_json]
                context = UserContext(user_id=user_id, max_messages=row[1])
                context.messages = messages
                return context
            return None

    async def save_context(self, context: UserContext) -> UserContext:
        messages_json = json.dumps([m.to_dict() for m in context.messages])
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO contexts (user_id, messages, max_messages) VALUES (?, ?, ?)",
                (context.user_id, messages_json, context.max_messages)
            )
            await db.commit()
        return context

    async def clear_context(self, user_id: int) -> None:
        context = await self.get_context(user_id)
        if context:
            context.clear()
            await self.save_context(context)

    async def delete_context(self, user_id: int) -> bool:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("DELETE FROM contexts WHERE user_id = ?", (user_id,))
            await db.commit()
            return cursor.rowcount > 0

class SQLiteSettingsRepository(BaseSettingsRepository):
    """Репозиторий настроек на SQLite."""

    async def get_settings(self) -> BotSettings:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT value FROM settings WHERE key = 'bot_settings'")
            row = await cursor.fetchone()
            if row:
                data = json.loads(row[0])
                settings_obj = BotSettings.from_dict(data)

                # Обновляем настройки из актуальной конфигурации если они отличаются
                try:
                    from config.settings import settings
                    needs_update = False

                    if settings_obj.openai_model != settings.openai_model:
                        settings_obj.openai_model = settings.openai_model
                        needs_update = True
                    if settings_obj.context_size != settings.context_size:
                        settings_obj.context_size = settings.context_size
                        needs_update = True
                    if settings_obj.default_user_limit != settings.default_user_limit:
                        settings_obj.default_user_limit = settings.default_user_limit
                        needs_update = True

                    # Если настройки изменились, сохраняем их
                    if needs_update:
                        await self.update_settings(settings_obj)

                except ImportError:
                    pass

                return settings_obj

            # Если в БД нет настроек, создаем их с актуальными значениями из config
            try:
                from config.settings import settings
                new_settings = BotSettings(
                    default_user_limit=settings.default_user_limit,
                    context_size=settings.context_size,
                    openai_model=settings.openai_model,
                )
            except ImportError:
                # Дефолтные значения если настройки недоступны
                new_settings = BotSettings()

            # Сохраняем новые настройки в БД
            await self.update_settings(new_settings)
            return new_settings

    async def update_settings(self, settings: BotSettings) -> BotSettings:
        settings.updated_at = datetime.now()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('bot_settings', ?)",
                (json.dumps(settings.to_dict()),)
            )
            await db.commit()
        return settings

class SQLiteAccessControlRepository(BaseAccessControlRepository):
    """Репозиторий контроля доступа на SQLite."""

    async def get_access_control(self) -> Optional[AccessControl]:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT value FROM access_control WHERE key = 'access_control'")
            row = await cursor.fetchone()
            if row:
                data = json.loads(row[0])
                return AccessControl.from_dict(data)
            return AccessControl() # Возвращаем дефолтный

    async def save_access_control(self, access_control: AccessControl) -> AccessControl:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO access_control (key, value) VALUES ('access_control', ?)",
                (json.dumps(access_control.to_dict()),)
            )
            await db.commit()
        return access_control

    async def get_access_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        history = []
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT timestamp, action, admin_id FROM access_history ORDER BY id DESC LIMIT ?", (limit,))
            rows = await cursor.fetchall()
            for row in rows:
                history.append({
                    "timestamp": datetime.fromisoformat(row[0]),
                    "action": row[1],
                    "admin_id": row[2]
                })
        return history

    async def add_access_history_record(self, record: Dict[str, Any]) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO access_history (timestamp, action, admin_id) VALUES (?, ?, ?)",
                (record['timestamp'].isoformat(), record['action'], record['admin_id'])
            )
            await db.commit()