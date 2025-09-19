"""
Базовый репозиторий с абстрактными методами
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from .models import UserProfile, UserContext, BotSettings, AccessControl


class BaseUserRepository(ABC):
    """Базовый репозиторий для работы с пользователями"""

    @abstractmethod
    async def get_user(self, user_id: int) -> Optional[UserProfile]:
        """Получить пользователя по ID"""
        pass

    @abstractmethod
    async def create_user(self, user_profile: UserProfile) -> UserProfile:
        """Создать нового пользователя"""
        pass

    @abstractmethod
    async def update_user(self, user_profile: UserProfile) -> UserProfile:
        """Обновить данные пользователя"""
        pass

    @abstractmethod
    async def delete_user(self, user_id: int) -> bool:
        """Удалить пользователя"""
        pass

    @abstractmethod
    async def get_all_users(self) -> List[UserProfile]:
        """Получить всех пользователей"""
        pass

    @abstractmethod
    async def increment_user_requests(self, user_id: int) -> int:
        """Увеличить счетчик запросов пользователя"""
        pass

    @abstractmethod
    async def reset_user_requests(self, user_id: int) -> None:
        """Сбросить счетчик запросов пользователя"""
        pass

    @abstractmethod
    async def set_user_limit(self, user_id: int, limit: int) -> None:
        """Установить лимит запросов для пользователя"""
        pass


class BaseContextRepository(ABC):
    """Базовый репозиторий для работы с контекстом пользователей"""

    @abstractmethod
    async def get_context(self, user_id: int) -> Optional[UserContext]:
        """Получить контекст пользователя"""
        pass

    @abstractmethod
    async def save_context(self, context: UserContext) -> UserContext:
        """Сохранить контекст пользователя"""
        pass

    @abstractmethod
    async def clear_context(self, user_id: int) -> None:
        """Очистить контекст пользователя"""
        pass

    @abstractmethod
    async def delete_context(self, user_id: int) -> bool:
        """Удалить контекст пользователя"""
        pass


class BaseAccessControlRepository(ABC):
    """Базовый репозиторий для работы с управлением доступом"""

    @abstractmethod
    async def get_access_control(self) -> Optional["AccessControl"]:
        """Получить настройки управления доступом"""
        pass

    @abstractmethod
    async def save_access_control(self, access_control: "AccessControl") -> "AccessControl":
        """Сохранить настройки управления доступом"""
        pass

    @abstractmethod
    async def get_access_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Получить историю изменений доступа"""
        pass

    @abstractmethod
    async def add_access_history_record(self, record: Dict[str, Any]) -> None:
        """Добавить запись в историю изменений"""
        pass


class BaseSettingsRepository(ABC):
    """Базовый репозиторий для работы с настройками бота"""

    @abstractmethod
    async def get_settings(self) -> BotSettings:
        """Получить настройки бота"""
        pass

    @abstractmethod
    async def update_settings(self, settings: BotSettings) -> BotSettings:
        """Обновить настройки бота"""
        pass
