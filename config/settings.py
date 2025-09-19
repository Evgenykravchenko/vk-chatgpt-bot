"""
Конфигурация приложения
"""
import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    """Настройки приложения"""

    # VK настройки
    vk_token: str

    # OpenAI настройки
    openai_api_key: str
    openai_model: str = "gpt-3.5-turbo"

    # OpenAI Proxy настройки
    openai_use_proxy: bool = False
    openai_proxy_url: str = "https://api.openai.com"
    openai_proxy_key: Optional[str] = None

    # Настройки контекста и лимитов
    context_size: int = 10
    default_user_limit: int = 50

    # Настройки rate limiting
    rate_limit_calls: int = 5
    rate_limit_period: int = 60  # секунд

    # VK настройки
    group_id: Optional[int] = None
    admin_user_id: Optional[int] = None

    @classmethod
    def from_env(cls) -> "Settings":
        """Создание настроек из переменных окружения"""
        return cls(
            vk_token=os.getenv("VK_TOKEN", ""),
            group_id=int(os.getenv("GROUP_ID")) if os.getenv("GROUP_ID") else None,
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
            openai_use_proxy=os.getenv("OPENAI_USE_PROXY", "false").lower() in ("true", "1", "yes"),
            openai_proxy_url=os.getenv("OPENAI_PROXY_URL", "https://api.openai.com"),
            openai_proxy_key=os.getenv("OPENAI_PROXY_KEY"),
            context_size=int(os.getenv("CONTEXT_SIZE", "10")),
            default_user_limit=int(os.getenv("DEFAULT_USER_LIMIT", "50")),
            admin_user_id=int(os.getenv("ADMIN_USER_ID")) if os.getenv("ADMIN_USER_ID") else None,
            rate_limit_calls=int(os.getenv("RATE_LIMIT_CALLS", "5")),
            rate_limit_period=int(os.getenv("RATE_LIMIT_PERIOD", "60")),
        )

    def validate(self) -> None:
        """Валидация настроек"""
        if not self.vk_token:
            raise ValueError("VK_TOKEN не установлен")

        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY не установлен")

        if self.context_size < 1:
            raise ValueError("CONTEXT_SIZE должен быть больше 0")

        if self.default_user_limit < 0:
            raise ValueError("DEFAULT_USER_LIMIT не может быть отрицательным")

        if self.rate_limit_calls < 1:
            raise ValueError("RATE_LIMIT_CALLS должен быть больше 0")

        if self.rate_limit_period < 1:
            raise ValueError("RATE_LIMIT_PERIOD должен быть больше 0")

        # Валидация прокси настроек
        if self.openai_use_proxy:
            if not self.openai_proxy_url:
                raise ValueError("OPENAI_PROXY_URL не может быть пустым при включенном прокси")

            if not self.openai_proxy_url.startswith(("http://", "https://")):
                raise ValueError("OPENAI_PROXY_URL должен начинаться с http:// или https://")

    def get_openai_base_url(self) -> str:
        """Получить базовый URL для OpenAI API"""
        if self.openai_use_proxy:
            # Убираем trailing slash если есть
            return self.openai_proxy_url.rstrip('/')
        return "https://api.openai.com"

    def get_openai_api_key(self) -> str:
        """Получить API ключ для OpenAI (или прокси)"""
        if self.openai_use_proxy and self.openai_proxy_key:
            return self.openai_proxy_key
        return self.openai_api_key

    def get_openai_info(self) -> dict:
        """Получить информацию о текущих настройках OpenAI"""
        return {
            "use_proxy": self.openai_use_proxy,
            "base_url": self.get_openai_base_url(),
            "model": self.openai_model,
            "proxy_url": self.openai_proxy_url if self.openai_use_proxy else None,
            "connection_type": "Прокси" if self.openai_use_proxy else "Прямое подключение"
        }


# Глобальные настройки
settings = Settings.from_env()
settings.validate()
