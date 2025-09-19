"""
Модели данных для репозиториев
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum


class MessageRole(Enum):
    """Роли сообщений в диалоге"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class Message:
    """Модель сообщения в диалоге"""
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

    def to_openai_format(self) -> Dict[str, str]:
        """Конвертация в формат OpenAI API"""
        return {
            "role": self.role.value,
            "content": self.content
        }

    def to_dict(self) -> Dict[str, str]:
        """Конвертация в словарь для JSON-сериализации"""
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class UserProfile:
    """Профиль пользователя"""
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    # Лимиты и статистика
    requests_limit: int = 50
    requests_used: int = 0

    # Метаданные
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    is_active: bool = True

    # Настройки
    preferred_language: str = "ru"

    @property
    def requests_remaining(self) -> int:
        """Количество оставшихся запросов"""
        return max(0, self.requests_limit - self.requests_used)

    @property
    def can_make_request(self) -> bool:
        """Может ли пользователь делать запросы"""
        return self.requests_remaining > 0 and self.is_active

    @property
    def display_name(self) -> str:
        """Отображаемое имя пользователя"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.username:
            return f"@{self.username}"
        else:
            return f"User {self.user_id}"


@dataclass
class UserContext:
    """Контекст пользователя (история сообщений)"""
    user_id: int
    messages: List[Message] = field(default_factory=list)
    max_messages: int = 10

    def add_message(self, role: MessageRole, content: str) -> None:
        """Добавление сообщения в контекст"""
        message = Message(role=role, content=content)
        self.messages.append(message)

        # Ограничиваем размер контекста
        if len(self.messages) > self.max_messages:
            # Оставляем системное сообщение (если есть) и последние N сообщений
            system_messages = [msg for msg in self.messages if msg.role == MessageRole.SYSTEM]
            other_messages = [msg for msg in self.messages if msg.role != MessageRole.SYSTEM]

            # Берем последние сообщения
            recent_messages = other_messages[-(self.max_messages - len(system_messages)):]

            self.messages = system_messages + recent_messages

    def clear(self) -> None:
        """Очистка контекста"""
        self.messages.clear()

    def to_openai_format(self) -> List[Dict[str, str]]:
        """Конвертация в формат OpenAI API"""
        return [msg.to_openai_format() for msg in self.messages]

    @property
    def message_count(self) -> int:
        """Количество сообщений в контексте"""
        return len(self.messages)


@dataclass
class BotSettings:
    """Глобальные настройки бота"""
    default_user_limit: int = 50
    context_size: int = 10
    openai_model: str = "gpt-3.5-turbo"

    # OpenAI Connection настройки
    openai_use_proxy: bool = False
    openai_proxy_url: str = "https://openai-proxy-vercel-kohl.vercel.app"
    openai_proxy_key: str = ""

    # System настройки
    rate_limit_enabled: bool = True
    rate_limit_calls: int = 5  # Количество запросов
    rate_limit_period: int = 60  # Период в секундах
    maintenance_mode: bool = False
    welcome_message: str = "Привет! Я AI ассистент. Задай мне любой вопрос!"

    # Новые настройки доступа
    whitelist_enabled: bool = False  # Включен ли белый список
    allowed_users: List[int] = field(default_factory=list)  # Список разрешенных пользователей
    access_mode: str = "public"  # "public", "whitelist", "admin_only"

    updated_at: datetime = field(default_factory=datetime.now)

    def update_setting(self, setting_name: str, value: Any) -> bool:
        """Обновить настройку"""
        if hasattr(self, setting_name):
            setattr(self, setting_name, value)
            self.updated_at = datetime.now()
            return True
        return False

    def get_settings_info(self) -> str:
        """Получить информацию о настройках"""
        connection_type = "🔄 Прокси" if self.openai_use_proxy else "🔗 Прямое"
        proxy_info = f" ({self.openai_proxy_url})" if self.openai_use_proxy else ""

        return f"""⚙️ Текущие настройки бота:

🤖 Основные параметры:
• Размер контекста: {self.context_size} сообщений
• Лимит по умолчанию: {self.default_user_limit} запросов
• Модель OpenAI: {self.openai_model}
• Подключение: {connection_type}{proxy_info}
• Приветственное сообщение: {"Настроено" if self.welcome_message != "Привет! Я AI ассистент. Задай мне любой вопрос!" else "По умолчанию"}

⚡ Системные настройки:
• Rate limiting: {"Включен" if self.rate_limit_enabled else "Отключен"}
• Лимит запросов: {self.rate_limit_calls} запросов в {self.rate_limit_period} сек
• Режим обслуживания: {"Включен" if self.maintenance_mode else "Отключен"}

📅 Последнее обновление: {self.updated_at.strftime('%d.%m.%Y %H:%M')}"""

    def get_openai_connection_info(self) -> str:
        """Получить детальную информацию о подключении к OpenAI"""
        if self.openai_use_proxy:
            return f"""🔄 OpenAI через прокси:

🌐 Прокси URL: {self.openai_proxy_url}
🔑 Прокси ключ: {"Настроен" if self.openai_proxy_key else "Не настроен"}
🎯 Модель: {self.openai_model}

💡 Использование прокси позволяет обходить блокировки и повышает стабильность соединения."""
        else:
            return f"""🔗 OpenAI прямое подключение:

🌐 Эндпоинт: https://api.openai.com/v1
🎯 Модель: {self.openai_model}

💡 Прямое подключение к официальному API OpenAI."""

    def reset_to_defaults(self) -> None:
        """Сбросить настройки к значениям по умолчанию"""
        # Получаем актуальные значения из config при сбросе
        try:
            from config.settings import settings
            self.default_user_limit = settings.default_user_limit
            self.context_size = settings.context_size
            self.openai_model = settings.openai_model
            self.rate_limit_calls = settings.rate_limit_calls
            self.rate_limit_period = settings.rate_limit_period
            self.openai_use_proxy = settings.openai_use_proxy
            self.openai_proxy_url = settings.openai_proxy_url
            self.openai_proxy_key = settings.openai_proxy_key or ""
        except ImportError:
            # Хардкодные дефолтные значения
            self.default_user_limit = 50
            self.context_size = 10
            self.openai_model = "gpt-3.5-turbo"
            self.rate_limit_calls = 5
            self.rate_limit_period = 60
            self.openai_use_proxy = False
            self.openai_proxy_url = "https://openai-proxy-vercel-kohl.vercel.app"
            self.openai_proxy_key = ""

        self.rate_limit_enabled = True
        self.maintenance_mode = False
        self.welcome_message = "Привет! Я AI ассистент. Задай мне любой вопрос!"
        self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        """Конвертация в словарь для JSON-сериализации"""
        return {
            "default_user_limit": self.default_user_limit,
            "context_size": self.context_size,
            "openai_model": self.openai_model,
            "openai_use_proxy": self.openai_use_proxy,
            "openai_proxy_url": self.openai_proxy_url,
            "openai_proxy_key": self.openai_proxy_key,
            "rate_limit_enabled": self.rate_limit_enabled,
            "rate_limit_calls": self.rate_limit_calls,
            "rate_limit_period": self.rate_limit_period,
            "maintenance_mode": self.maintenance_mode,
            "welcome_message": self.welcome_message,
            "whitelist_enabled": self.whitelist_enabled,
            "allowed_users": self.allowed_users,
            "access_mode": self.access_mode,
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BotSettings":
        """Создание из словаря"""
        # Преобразуем updated_at обратно в datetime
        if 'updated_at' in data and isinstance(data['updated_at'], str):
            try:
                data['updated_at'] = datetime.fromisoformat(data['updated_at'])
            except ValueError:
                data['updated_at'] = datetime.now()
        elif 'updated_at' not in data:
            data['updated_at'] = datetime.now()

        # Убираем поля которых нет в dataclass если они попали в data
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}

        return cls(**filtered_data)


@dataclass
class AccessControl:
    """Управление доступом к боту"""
    mode: str = "public"  # "public", "whitelist", "admin_only"
    whitelist: List[int] = field(default_factory=list)
    blacklist: List[int] = field(default_factory=list)  # Заблокированные пользователи

    # Кастомные сообщения для разных режимов
    whitelist_message: str = """🔒 Доступ ограничен

Бот находится в режиме бета-тестирования и доступен только участникам из списка.

📬 Для получения доступа:
• Напишите администратору сообщества
• Укажите цель использования бота
• Ожидайте добавления в список

💡 Это временное ограничение на период тестирования новых функций."""

    admin_only_message: str = """🔧 Техническое обслуживание

Бот временно недоступен для пользователей.

🛠️ Причины:
• Обновление функций
• Техническое обслуживание  
• Настройка системы

📬 Информация:
• Напишите администратору сообщества для уточнения времени восстановления
• Следите за новостями в сообществе

⏰ Обычно работы занимают не более 30 минут."""

    blocked_message: str = """🚫 Доступ запрещен

Ваш аккаунт заблокирован для использования бота.

📬 Для разблокировки:
• Напишите администратору сообщества
• Укажите причину обращения
• Ожидайте рассмотрения запроса

💬 Администратор рассмотрит ваше обращение в ближайшее время."""

    def is_user_allowed(self, user_id: int, admin_id: int = None) -> bool:
        """Проверить разрешен ли доступ пользователю"""
        # Проверяем черный список
        if user_id in self.blacklist:
            return False

        # Админ всегда имеет доступ
        if admin_id and user_id == admin_id:
            return True

        # Проверяем режим доступа
        if self.mode == "public":
            return True
        elif self.mode == "whitelist":
            return user_id in self.whitelist
        elif self.mode == "admin_only":
            return admin_id and user_id == admin_id

        return False

    def get_access_denied_message(self, user_id: int, admin_id: int = None) -> str:
        """Получить сообщение об отказе в доступе"""
        # Проверяем причину отказа
        if user_id in self.blacklist:
            return self.blocked_message
        elif self.mode == "whitelist":
            return self.whitelist_message
        elif self.mode == "admin_only":
            return self.admin_only_message
        else:
            return self.blocked_message

    def add_to_whitelist(self, user_id: int) -> None:
        """Добавить пользователя в белый список"""
        if user_id not in self.whitelist:
            self.whitelist.append(user_id)

    def remove_from_whitelist(self, user_id: int) -> None:
        """Удалить пользователя из белого списка"""
        if user_id in self.whitelist:
            self.whitelist.remove(user_id)

    def add_to_blacklist(self, user_id: int) -> None:
        """Добавить пользователя в черный список"""
        if user_id not in self.blacklist:
            self.blacklist.append(user_id)
            # Удаляем из белого списка если есть
            self.remove_from_whitelist(user_id)

    def remove_from_blacklist(self, user_id: int) -> None:
        """Удалить пользователя из черного списка"""
        if user_id in self.blacklist:
            self.blacklist.remove(user_id)

    def to_dict(self) -> dict:
        """Конвертация в словарь для JSON-сериализации"""
        return {
            "mode": self.mode,
            "whitelist": self.whitelist,
            "blacklist": self.blacklist,
            "whitelist_message": self.whitelist_message,
            "admin_only_message": self.admin_only_message,
            "blocked_message": self.blocked_message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AccessControl":
        """Создание из словаря"""
        # Убираем поля которых нет в dataclass если они попали в data
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}

        return cls(**filtered_data)