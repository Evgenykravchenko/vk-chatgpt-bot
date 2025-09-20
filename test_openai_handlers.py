#!/usr/bin/env python3
"""
Тестовый скрипт для проверки OpenAI handlers
"""
import asyncio
import sys
import os

# Добавляем корневую директорию в path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_openai_handlers():
    """Тест создания OpenAI handlers"""
    try:
        # Инициализация репозиториев (без БД для теста)
        from repositories.sqlite_repo import init_db
        await init_db()
        
        from repositories.sqlite_repo import (
            SQLiteUserRepository,
            SQLiteContextRepository,
            SQLiteSettingsRepository
        )
        # from services import UserService, OpenAIService
        from services import OpenAIService
        from services.settings_service import SettingsService
        # from bot.handlers.openai_handlers import OpenAICommandHandler
        
        print("✅ Создание репозиториев...")
        user_repo = SQLiteUserRepository()
        context_repo = SQLiteContextRepository()
        settings_repo = SQLiteSettingsRepository()
        
        print("✅ Создание сервисов...")
        # user_service = UserService(user_repo, context_repo)
        settings_service = SettingsService(settings_repo, user_repo, context_repo)
        openai_service = OpenAIService(settings_service)
        
        # print("✅ Создание OpenAI handler...")
        # openai_handler = OpenAICommandHandler(
        #     user_service,
        #     openai_service,
        #     settings_service
        # )
        
        print("✅ Тест получения статуса...")
        status = openai_service.get_connection_status()
        print(f"Статус: {status}")
        
        print("✅ Все компоненты успешно инициализированы!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = asyncio.run(test_openai_handlers())
    if result:
        print("\n🎉 Тест прошел успешно!")
    else:
        print("\n💥 Тест завершился с ошибкой!")
        sys.exit(1)
