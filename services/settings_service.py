"""
Сервис для управления настройками бота
"""
from typing import Any

from repositories.base import BaseSettingsRepository, BaseUserRepository, BaseContextRepository
from repositories.models import BotSettings
from config.settings import settings


class SettingsService:
    """Сервис для управления настройками бота"""

    def __init__(
        self,
        settings_repo: BaseSettingsRepository,
        user_repo: BaseUserRepository,
        context_repo: BaseContextRepository,
    ):
        self.settings_repo = settings_repo
        self.user_repo = user_repo
        self.context_repo = context_repo

    async def get_bot_settings(self) -> BotSettings:
        """Получить настройки бота"""
        return await self.settings_repo.get_settings()

    async def update_context_size(self, new_size: int, admin_id: int) -> bool:
        """
        Обновить размер контекста

        Args:
            new_size: Новый размер контекста (1-50)
            admin_id: ID администратора

        Returns:
            True если обновлено успешно
        """
        if not self._is_admin(admin_id):
            return False

        if not (1 <= new_size <= 50):
            return False

        bot_settings = await self.settings_repo.get_settings()
        bot_settings.update_setting('context_size', new_size)
        await self.settings_repo.update_settings(bot_settings)

        # Обновляем у всех пользователей
        all_users = await self.user_repo.get_all_users()
        for user in all_users:
            context = await self.context_repo.get_context(user.user_id)
            if context:
                context.max_messages = new_size
                await self.context_repo.save_context(context)

        return True

    async def update_default_limit(self, new_limit: int, admin_id: int) -> bool:
        """
        Обновить лимит по умолчанию

        Args:
            new_limit: Новый лимит (1-1000)
            admin_id: ID администратора

        Returns:
            True если обновлено успешно
        """
        if not self._is_admin(admin_id):
            return False

        if not (1 <= new_limit <= 1000):
            return False

        bot_settings = await self.settings_repo.get_settings()
        bot_settings.update_setting('default_user_limit', new_limit)
        await self.settings_repo.update_settings(bot_settings)

        # Обновляем у всех пользователей
        all_users = await self.user_repo.get_all_users()
        for user in all_users:
            await self.user_repo.set_user_limit(user.user_id, new_limit)

        return True

    async def update_ai_model(self, new_model: str, admin_id: int) -> bool:
        """
        Обновить модель OpenAI

        Args:
            new_model: Новая модель
            admin_id: ID администратора

        Returns:
            True если обновлено успешно
        """
        if not self._is_admin(admin_id):
            return False

        valid_models = [
            "gpt-3.5-turbo",
            "gpt-4",
            "gpt-4-turbo",
            "gpt-4o",
            "gpt-4o-mini"
        ]

        if new_model not in valid_models:
            return False

        bot_settings = await self.settings_repo.get_settings()
        bot_settings.update_setting('openai_model', new_model)
        await self.settings_repo.update_settings(bot_settings)

        return True

    async def update_welcome_message(self, new_message: str, admin_id: int) -> bool:
        """
        Обновить приветственное сообщение

        Args:
            new_message: Новое сообщение
            admin_id: ID администратора

        Returns:
            True если обновлено успешно
        """
        if not self._is_admin(admin_id):
            return False

        if len(new_message) > 1000:  # Ограничение VK
            return False

        bot_settings = await self.settings_repo.get_settings()
        bot_settings.update_setting('welcome_message', new_message)
        await self.settings_repo.update_settings(bot_settings)

        return True

    async def toggle_rate_limit(self, admin_id: int) -> bool:
        """
        Переключить rate limiting

        Args:
            admin_id: ID администратора

        Returns:
            Новое состояние rate limiting
        """
        if not self._is_admin(admin_id):
            return False

        bot_settings = await self.settings_repo.get_settings()
        new_state = not bot_settings.rate_limit_enabled
        bot_settings.update_setting('rate_limit_enabled', new_state)
        await self.settings_repo.update_settings(bot_settings)

        return new_state

    async def toggle_maintenance_mode(self, admin_id: int) -> bool:
        """
        Переключить режим обслуживания

        Args:
            admin_id: ID администратора

        Returns:
            Новое состояние режима обслуживания
        """
        if not self._is_admin(admin_id):
            return False

        bot_settings = await self.settings_repo.get_settings()
        new_state = not bot_settings.maintenance_mode
        bot_settings.update_setting('maintenance_mode', new_state)
        await self.settings_repo.update_settings(bot_settings)

        return new_state

    async def reset_settings_to_defaults(self, admin_id: int) -> bool:
        """
        Сбросить настройки к значениям по умолчанию

        Args:
            admin_id: ID администратора

        Returns:
            True если сброшено успешно
        """
        if not self._is_admin(admin_id):
            return False

        bot_settings = await self.settings_repo.get_settings()
        bot_settings.reset_to_defaults()
        await self.settings_repo.update_settings(bot_settings)

        return True

    async def get_settings_info(self) -> str:
        """Получить информацию о настройках"""
        bot_settings = await self.settings_repo.get_settings()
        return bot_settings.get_settings_info()

    async def validate_setting_value(self, setting_name: str, value: str) -> tuple[bool, Any, str]:
        """
        Валидировать значение настройки

        Args:
            setting_name: Название настройки
            value: Значение для проверки

        Returns:
            (валидно, преобразованное_значение, сообщение_об_ошибке)
        """
        try:
            if setting_name == "context_size":
                int_value = int(value)
                if 1 <= int_value <= 50:
                    return True, int_value, ""
                else:
                    return False, None, "Размер контекста должен быть от 1 до 50"

            elif setting_name == "default_user_limit":
                int_value = int(value)
                if 1 <= int_value <= 1000:
                    return True, int_value, ""
                else:
                    return False, None, "Лимит должен быть от 1 до 1000"

            elif setting_name == "openai_model":
                valid_models = ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "gpt-4o", "gpt-4o-mini"]
                if value in valid_models:
                    return True, value, ""
                else:
                    return False, None, f"Доступные модели: {', '.join(valid_models)}"

            elif setting_name == "welcome_message":
                if len(value) <= 1000:
                    return True, value, ""
                else:
                    return False, None, "Сообщение не должно превышать 1000 символов"

            else:
                return False, None, "Неизвестная настройка"

        except ValueError:
            return False, None, "Некорректное значение"

    def _is_admin(self, user_id: int) -> bool:
        """Проверить является ли пользователь администратором"""
        return settings.admin_user_id is not None and user_id == settings.admin_user_id

    # Добавьте эти методы в SettingsService класс:

    async def update_rate_limit_settings(self, calls: int, period: int, admin_id: int) -> bool:
        """
        Обновить настройки rate limiting

        Args:
            calls: Количество запросов
            period: Период в секундах
            admin_id: ID администратора

        Returns:
            True если обновлено успешно
        """
        if not self._is_admin(admin_id):
            return False

        if not (1 <= calls <= 100):
            return False

        if not (1 <= period <= 3600):  # От 1 секунды до 1 часа
            return False

        bot_settings = await self.settings_repo.get_settings()
        bot_settings.update_setting('rate_limit_calls', calls)
        bot_settings.update_setting('rate_limit_period', period)
        await self.settings_repo.update_settings(bot_settings)

        return True

    async def get_rate_limit_info(self) -> dict:
        """Получить информацию о текущих настройках rate limiting"""
        bot_settings = await self.settings_repo.get_settings()

        return {
            "enabled": bot_settings.rate_limit_enabled,
            "calls": bot_settings.rate_limit_calls,
            "period": bot_settings.rate_limit_period,
            "description": f"{bot_settings.rate_limit_calls} запросов в {bot_settings.rate_limit_period} сек"
        }

    async def get_openai_connection_info(self) -> dict:
        """Получить информацию о подключении к OpenAI"""
        bot_settings = await self.settings_repo.get_settings()

        return {
            "use_proxy": bot_settings.openai_use_proxy,
            "proxy_url": bot_settings.openai_proxy_url,
            "proxy_key_set": bool(bot_settings.openai_proxy_key),
            "model": bot_settings.openai_model,
            "connection_type": "Прокси" if bot_settings.openai_use_proxy else "Прямое подключение",
            "endpoint": bot_settings.openai_proxy_url if bot_settings.openai_use_proxy else "https://api.openai.com"
        }

    async def update_openai_connection_mode(self, use_proxy: bool, admin_id: int) -> bool:
        """
        Переключить режим подключения к OpenAI (прокси/прямое)

        Args:
            use_proxy: Использовать ли прокси
            admin_id: ID администратора

        Returns:
            True если успешно обновлено
        """
        if not self._is_admin(admin_id):
            return False

        bot_settings = await self.settings_repo.get_settings()
        bot_settings.update_setting('openai_use_proxy', use_proxy)
        await self.settings_repo.update_settings(bot_settings)

        return True

    async def update_openai_proxy_settings(self, proxy_url: str, proxy_key: str, admin_id: int) -> tuple[bool, str]:
        """
        Обновить настройки прокси OpenAI

        Args:
            proxy_url: URL прокси сервера
            proxy_key: Ключ для прокси (может быть пустым)
            admin_id: ID администратора

        Returns:
            Кортеж (успешно, сообщение об ошибке)
        """
        if not self._is_admin(admin_id):
            return False, "Недостаточно прав"

        # Валидация URL
        if not proxy_url.strip():
            return False, "URL прокси не может быть пустым"

        if not proxy_url.startswith(("http://", "https://")):
            return False, "URL должен начинаться с http:// или https://"

        # Очищаем URL от лишних символов
        clean_url = proxy_url.strip().rstrip('/')

        bot_settings = await self.settings_repo.get_settings()
        bot_settings.update_setting('openai_proxy_url', clean_url)
        bot_settings.update_setting('openai_proxy_key', proxy_key.strip())
        await self.settings_repo.update_settings(bot_settings)

        return True, ""

    async def test_openai_connection(self, openai_service, admin_id: int) -> tuple[bool, str]:
        """
        Тестировать текущее подключение к OpenAI

        Args:
            openai_service: Экземпляр OpenAIService
            admin_id: ID администратора

        Returns:
            Кортеж (успешно, сообщение)
        """
        if not self._is_admin(admin_id):
            return False, "Недостаточно прав"

        try:
            return await openai_service.test_connection()
        except Exception as e:
            return False, f"Ошибка тестирования: {str(e)}"

    async def switch_openai_connection_runtime(self, openai_service, use_proxy: bool, admin_id: int) -> tuple[
        bool, str]:
        """
        Переключить подключение OpenAI в runtime без перезапуска

        Args:
            openai_service: Экземпляр OpenAIService
            use_proxy: Использовать ли прокси
            admin_id: ID администратора

        Returns:
            Кортеж (успешно, сообщение)
        """
        if not self._is_admin(admin_id):
            return False, "Недостаточно прав"

        try:
            # Сначала обновляем настройки в БД
            await self.update_openai_connection_mode(use_proxy, admin_id)
            bot_settings = await self.settings_repo.get_settings()

            if use_proxy:
                # Переключаемся на прокси
                return await openai_service.switch_to_proxy(
                    bot_settings.openai_proxy_url,
                    bot_settings.openai_proxy_key or None
                )
            else:
                # Переключаемся на прямое подключение
                return await openai_service.switch_to_direct()

        except Exception as e:
            return False, f"Ошибка переключения: {str(e)}"

    async def validate_proxy_settings(self, proxy_url: str, proxy_key: str = "") -> tuple[bool, str]:
        """
        Валидировать настройки прокси

        Args:
            proxy_url: URL прокси
            proxy_key: Ключ прокси

        Returns:
            Кортеж (валидно, сообщение об ошибке)
        """
        if not proxy_url.strip():
            return False, "URL прокси не может быть пустым"

        if not proxy_url.startswith(("http://", "https://")):
            return False, "URL должен начинаться с http:// или https://"

        # Проверяем, что URL содержит допустимые символы
        try:
            from urllib.parse import urlparse
            parsed = urlparse(proxy_url)
            if not parsed.netloc:
                return False, "Некорректный формат URL"
        except Exception:
            return False, "Некорректный формат URL"

        # Проверяем длину ключа (если указан)
        if proxy_key and len(proxy_key.strip()) < 10:
            return False, "Ключ прокси слишком короткий (минимум 10 символов)"

        return True, ""

    async def validate_rate_limit_values(self, calls_str: str, period_str: str) -> tuple[bool, dict, str]:
        """
        Валидировать значения rate limiting

        Args:
            calls_str: Количество запросов как строка
            period_str: Период как строка

        Returns:
            (валидно, словарь_значений, сообщение_об_ошибке)
        """
        try:
            calls = int(calls_str)
            period = int(period_str)

            if not (1 <= calls <= 100):
                return False, None, "Количество запросов должно быть от 1 до 100"

            if not (1 <= period <= 3600):
                return False, None, "Период должен быть от 1 до 3600 секунд (1 час)"

            return True, {"calls": calls, "period": period}, ""

        except ValueError:
            return False, None, "Введите корректные числа"