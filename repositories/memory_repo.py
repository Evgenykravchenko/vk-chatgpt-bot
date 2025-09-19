"""
In-memory репозитории для разработки и тестирования
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from copy import deepcopy

from .base import BaseUserRepository, BaseContextRepository, BaseSettingsRepository, BaseAccessControlRepository
from .models import UserProfile, UserContext, BotSettings, AccessControl


class MemoryAccessControlRepository(BaseAccessControlRepository):
    """In-memory репозиторий для управления доступом"""

    def __init__(self):
        self._access_control = AccessControl()
        self._access_history = []

    async def get_access_control(self) -> Optional[AccessControl]:
        """Получить настройки управления доступом"""
        return deepcopy(self._access_control)

    async def save_access_control(self, access_control: AccessControl) -> AccessControl:
        """Сохранить настройки управления доступом"""
        self._access_control = deepcopy(access_control)
        return deepcopy(access_control)

    async def get_access_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Получить историю изменений доступа"""
        return deepcopy(self._access_history[-limit:])

    async def add_access_history_record(self, record: Dict[str, Any]) -> None:
        """Добавить запись в историю изменений"""
        self._access_history.append(deepcopy(record))

        # Ограничиваем размер истории
        if len(self._access_history) > 100:
            self._access_history = self._access_history[-50:]


class MemoryUserRepository(BaseUserRepository):
    """In-memory репозиторий для пользователей"""

    def __init__(self):
        self._users: Dict[int, UserProfile] = {}

    async def get_user(self, user_id: int) -> Optional[UserProfile]:
        """Получить пользователя по ID"""
        return deepcopy(self._users.get(user_id))

    async def create_user(self, user_profile: UserProfile) -> UserProfile:
        """Создать нового пользователя"""
        self._users[user_profile.user_id] = deepcopy(user_profile)
        return deepcopy(user_profile)

    async def update_user(self, user_profile: UserProfile) -> UserProfile:
        """Обновить данные пользователя"""
        user_profile.last_activity = datetime.now()
        self._users[user_profile.user_id] = deepcopy(user_profile)
        return deepcopy(user_profile)

    async def delete_user(self, user_id: int) -> bool:
        """Удалить пользователя"""
        if user_id in self._users:
            del self._users[user_id]
            return True
        return False

    async def get_all_users(self) -> List[UserProfile]:
        """Получить всех пользователей"""
        return [deepcopy(user) for user in self._users.values()]

    async def increment_user_requests(self, user_id: int) -> int:
        """Увеличить счетчик запросов пользователя"""
        if user_id in self._users:
            self._users[user_id].requests_used += 1
            self._users[user_id].last_activity = datetime.now()
            return self._users[user_id].requests_used
        raise ValueError(f"Пользователь {user_id} не найден")

    async def reset_user_requests(self, user_id: int) -> None:
        """Сбросить счетчик запросов пользователя"""
        if user_id in self._users:
            self._users[user_id].requests_used = 0
            self._users[user_id].last_activity = datetime.now()
        else:
            raise ValueError(f"Пользователь {user_id} не найден")

    async def set_user_limit(self, user_id: int, limit: int) -> None:
        """Установить лимит запросов для пользователя"""
        if user_id in self._users:
            self._users[user_id].requests_limit = limit
            self._users[user_id].last_activity = datetime.now()
        else:
            raise ValueError(f"Пользователь {user_id} не найден")


class MemoryContextRepository(BaseContextRepository):
    """In-memory репозиторий для контекста пользователей"""

    def __init__(self):
        self._contexts: Dict[int, UserContext] = {}

    async def get_context(self, user_id: int) -> Optional[UserContext]:
        """Получить контекст пользователя"""
        if user_id not in self._contexts:
            # Получаем актуальный размер контекста из настроек
            try:
                from config.settings import settings
                max_messages = settings.context_size
            except ImportError:
                max_messages = 10  # Дефолтное значение

            # Создаем новый контекст для пользователя с актуальным размером
            self._contexts[user_id] = UserContext(
                user_id=user_id,
                max_messages=max_messages
            )
        return deepcopy(self._contexts[user_id])

    async def save_context(self, context: UserContext) -> UserContext:
        """Сохранить контекст пользователя"""
        self._contexts[context.user_id] = deepcopy(context)
        return deepcopy(context)

    async def clear_context(self, user_id: int) -> None:
        """Очистить контекст пользователя"""
        if user_id in self._contexts:
            self._contexts[user_id].clear()

    async def delete_context(self, user_id: int) -> bool:
        """Удалить контекст пользователя"""
        if user_id in self._contexts:
            del self._contexts[user_id]
            return True
        return False


class MemorySettingsRepository(BaseSettingsRepository):
    """In-memory репозиторий для настроек бота"""

    def __init__(self):
        self._settings = None
        self._initialize_settings()

    def _initialize_settings(self):
        """Инициализация настроек с актуальными значениями из config"""
        # Импортируем настройки здесь, чтобы избежать циклических импортов
        try:
            from config.settings import settings
            default_limit = settings.default_user_limit
            context_size = settings.context_size
            openai_model = settings.openai_model
            rate_limit_calls = settings.rate_limit_calls
            rate_limit_period = settings.rate_limit_period
        except ImportError:
            # Дефолтные значения если настройки недоступны
            default_limit = 50
            context_size = 10
            openai_model = "gpt-3.5-turbo"
            rate_limit_calls = 5
            rate_limit_period = 60

        self._settings = BotSettings(
            default_user_limit=default_limit,
            context_size=context_size,
            openai_model=openai_model,
            rate_limit_calls=rate_limit_calls,
            rate_limit_period=rate_limit_period,
        )

    async def get_settings(self) -> BotSettings:
        """Получить настройки бота"""
        # Проверяем, нужно ли обновить настройки из конфига
        try:
            from config.settings import settings
            # Обновляем настройки из актуальной конфигурации
            if self._settings.openai_model != settings.openai_model:
                self._settings.openai_model = settings.openai_model
            if self._settings.context_size != settings.context_size:
                self._settings.context_size = settings.context_size
            if self._settings.default_user_limit != settings.default_user_limit:
                self._settings.default_user_limit = settings.default_user_limit
            if self._settings.rate_limit_calls != settings.rate_limit_calls:
                self._settings.rate_limit_calls = settings.rate_limit_calls
            if self._settings.rate_limit_period != settings.rate_limit_period:
                self._settings.rate_limit_period = settings.rate_limit_period
        except ImportError:
            pass

        return deepcopy(self._settings)

    async def update_settings(self, new_settings: BotSettings) -> BotSettings:
        """Обновить настройки бота"""
        new_settings.updated_at = datetime.now()
        self._settings = deepcopy(new_settings)
        return deepcopy(self._settings)
