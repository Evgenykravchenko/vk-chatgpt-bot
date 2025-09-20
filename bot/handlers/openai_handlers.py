"""
Обработчики команд OpenAI настроек
"""
from typing import Dict, Any
from services import UserService, OpenAIService, SettingsService
from bot.keyboards.inline import (
    get_openai_connection_menu_keyboard,
    get_proxy_settings_keyboard,
    get_openai_input_keyboard,
    get_proxy_examples_keyboard,
    get_admin_keyboard,
)


class OpenAICommandHandler:
    """Обработчик команд настроек OpenAI"""

    def __init__(self, user_service: UserService, openai_service: OpenAIService, settings_service: SettingsService):
        self.user_service = user_service
        self.openai_service = openai_service
        self.settings_service = settings_service

    async def _check_admin(self, user_id: int) -> bool:
        """Проверка прав администратора"""
        return await self.user_service.is_admin(user_id)

    async def handle_openai_connection_menu(self, user_id: int) -> Dict[str, Any]:
        """Меню настроек подключения OpenAI"""
        if not await self._check_admin(user_id):
            return {
                "message": "❌ У вас нет прав администратора",
                "keyboard": get_admin_keyboard()
            }

        status_info = self.openai_service.get_connection_status()
        
        menu_text = f"""🔌 Настройки подключения OpenAI

📊 Текущий статус:
• Тип подключения: {status_info['connection_type']}
• Модель: {status_info['model']}
• Эндпоинт: {status_info['api_endpoint']}

🔧 Доступные действия:
• Переключение между прямым и прокси подключением
• Настройка параметров прокси
• Тестирование соединения
• Просмотр статуса

💡 Совет: Используйте прокси для обхода блокировок OpenAI API."""

        return {
            "message": menu_text,
            "keyboard": get_openai_connection_menu_keyboard()
        }

    async def handle_set_openai_direct(self, user_id: int) -> Dict[str, Any]:
        """Переключение на прямое подключение"""
        if not await self._check_admin(user_id):
            return {
                "message": "❌ У вас нет прав администратора",
                "keyboard": get_admin_keyboard()
            }

        success, message = await self.openai_service.switch_to_direct()
        
        return {
            "message": f"🔗 Переключение на прямое подключение\n\n{message}",
            "keyboard": get_openai_connection_menu_keyboard()
        }

    async def handle_set_openai_proxy(self, user_id: int) -> Dict[str, Any]:
        """Переключение на прокси подключение"""
        if not await self._check_admin(user_id):
            return {
                "message": "❌ У вас нет прав администратора",
                "keyboard": get_admin_keyboard()
            }

        from config.settings import settings
        
        if not settings.openai_proxy_url or settings.openai_proxy_url == "https://api.openai.com":
            return {
                "message": """🔄 Настройка прокси подключения

❗ Прокси URL не настроен. 

Сначала настройте URL прокси в "⚙️ Настройки прокси", затем попробуйте снова.""",
                "keyboard": get_openai_connection_menu_keyboard()
            }

        success, message = await self.openai_service.switch_to_proxy(
            settings.openai_proxy_url,
            settings.openai_proxy_key
        )
        
        return {
            "message": f"🔄 Переключение на прокси\n\n{message}",
            "keyboard": get_openai_connection_menu_keyboard()
        }

    async def handle_test_openai_connection(self, user_id: int) -> Dict[str, Any]:
        """Тестирование соединения OpenAI"""
        if not await self._check_admin(user_id):
            return {
                "message": "❌ У вас нет прав администратора",
                "keyboard": get_admin_keyboard()
            }

        success, message = await self.openai_service.test_connection()
        
        test_text = f"""🔍 Тестирование соединения

{message}

ℹ️ Тест отправляет короткий запрос к API для проверки доступности."""

        return {
            "message": test_text,
            "keyboard": get_openai_connection_menu_keyboard()
        }

    async def handle_show_openai_status(self, user_id: int) -> Dict[str, Any]:
        """Показать статус подключения OpenAI"""
        if not await self._check_admin(user_id):
            return {
                "message": "❌ У вас нет прав администратора",
                "keyboard": get_admin_keyboard()
            }

        status_info = self.openai_service.get_connection_status()
        
        status_icon = "🟢" if status_info['use_proxy'] else "🔵"
        
        status_text = f"""📊 Статус подключения OpenAI

{status_icon} Текущее подключение:
• Тип: {status_info['connection_type']}
• Base URL: {status_info['base_url']}
• API Endpoint: {status_info['api_endpoint']}
• Модель: {status_info['model']}

🔧 Настройки:
• Прокси активен: {"✅ Да" if status_info['use_proxy'] else "❌ Нет"}"""

        if status_info['use_proxy']:
            from config.settings import settings
            status_text += f"\n• Прокси URL: {settings.openai_proxy_url}"
            status_text += f"\n• Прокси ключ: {'✅ Настроен' if settings.openai_proxy_key else '❌ Не настроен'}"

        return {
            "message": status_text,
            "keyboard": get_openai_connection_menu_keyboard()
        }

    async def handle_proxy_settings_menu(self, user_id: int) -> Dict[str, Any]:
        """Меню настроек прокси"""
        if not await self._check_admin(user_id):
            return {
                "message": "❌ У вас нет прав администратора",
                "keyboard": get_admin_keyboard()
            }

        from config.settings import settings
        
        proxy_text = f"""⚙️ Настройки прокси

🌐 Текущий URL: 
{settings.openai_proxy_url}

🔑 API ключ: 
{'✅ Настроен' if settings.openai_proxy_key else '❌ Не настроен'}

📝 Примечание:
Изменения применяются сразу, но для переключения на прокси необходимо выбрать "🔄 Через прокси" в главном меню."""

        return {
            "message": proxy_text,
            "keyboard": get_proxy_settings_keyboard()
        }

    async def handle_show_proxy_examples(self, user_id: int) -> Dict[str, Any]:
        """Показать примеры прокси URL"""
        if not await self._check_admin(user_id):
            return {
                "message": "❌ У вас нет прав администратора",
                "keyboard": get_admin_keyboard()
            }

        examples_text = """💡 Примеры прокси URL

🚀 Vercel прокси (рекомендуется):
https://openai-proxy-vercel-kohl.vercel.app

🌐 Общий формат:
https://your-proxy-domain.com

⚠️ Важно:
• URL должен начинаться с https://
• Не добавляйте /v1 в конец - это добавится автоматически
• Убедитесь, что прокси поддерживает OpenAI API

✅ Проверенные прокси:
• Vercel deployment - стабильно работает
• Cloudflare Workers - хорошая скорость"""

        return {
            "message": examples_text,
            "keyboard": get_proxy_examples_keyboard()
        }

    async def handle_use_vercel_proxy(self, user_id: int) -> Dict[str, Any]:
        """Использовать Vercel прокси"""
        if not await self._check_admin(user_id):
            return {
                "message": "❌ У вас нет прав администратора",
                "keyboard": get_admin_keyboard()
            }

        vercel_url = "https://openai-proxy-vercel-kohl.vercel.app"
        
        # Обновляем настройки
        success = await self.settings_service.update_proxy_url(vercel_url, user_id)
        
        if success:
            return {
                "message": f"""✅ Vercel прокси настроен

🌐 URL установлен: {vercel_url}

🔧 Что дальше:
1. При необходимости настройте API ключ
2. Выберите "🔄 Через прокси" для активации
3. Протестируйте соединение

💡 Этот прокси уже проверен и должен работать стабильно.""",
                "keyboard": get_proxy_settings_keyboard()
            }
        else:
            return {
                "message": "❌ Не удалось обновить настройки прокси",
                "keyboard": get_proxy_settings_keyboard()
            }

    async def handle_edit_proxy_url(self, user_id: int) -> Dict[str, Any]:
        """Начать редактирование URL прокси"""
        if not await self._check_admin(user_id):
            return {
                "message": "❌ У вас нет прав администратора",
                "keyboard": get_admin_keyboard()
            }

        return {
            "message": """🌐 Изменение URL прокси

Введите новый URL прокси (например: https://your-proxy.com):

⚠️ Требования:
• Должен начинаться с https://
• Не добавляйте /v1 в конец
• URL должен быть действующим

📝 Пример: https://openai-proxy-vercel-kohl.vercel.app""",
            "keyboard": get_openai_input_keyboard(),
            "next_action": "edit_proxy_url_input"
        }

    async def handle_edit_proxy_key(self, user_id: int) -> Dict[str, Any]:
        """Начать редактирование ключа прокси"""
        if not await self._check_admin(user_id):
            return {
                "message": "❌ У вас нет прав администратора",
                "keyboard": get_admin_keyboard()
            }

        return {
            "message": """🔑 Изменение API ключа для прокси

Введите новый API ключ:

💡 Примечание:
• Некоторые прокси используют свои ключи
• Другие используют оригинальный OpenAI ключ
• Оставьте пустым, если прокси не требует отдельного ключа

📝 Отправьте "skip" чтобы оставить текущий ключ""",
            "keyboard": get_openai_input_keyboard(),
            "next_action": "edit_proxy_key_input"
        }

    async def handle_proxy_url_input(self, user_id: int, url: str) -> Dict[str, Any]:
        """Обработка ввода URL прокси"""
        if not await self._check_admin(user_id):
            return {
                "message": "❌ У вас нет прав администратора",
                "keyboard": get_admin_keyboard()
            }

        # Валидация URL
        url = url.strip()
        
        if not url.startswith(('http://', 'https://')):
            return {
                "message": "❌ URL должен начинаться с http:// или https://",
                "keyboard": get_openai_input_keyboard(),
                "next_action": "edit_proxy_url_input"
            }

        if url.endswith('/v1'):
            url = url[:-3]  # Убираем /v1 если есть

        # Обновляем настройки
        success = await self.settings_service.update_proxy_url(url, user_id)
        
        if success:
            return {
                "message": f"✅ URL прокси обновлен: {url}",
                "keyboard": get_proxy_settings_keyboard()
            }
        else:
            return {
                "message": "❌ Не удалось обновить URL прокси",
                "keyboard": get_proxy_settings_keyboard()
            }

    async def handle_proxy_key_input(self, user_id: int, key: str) -> Dict[str, Any]:
        """Обработка ввода ключа прокси"""
        if not await self._check_admin(user_id):
            return {
                "message": "❌ У вас нет прав администратора",
                "keyboard": get_admin_keyboard()
            }

        key = key.strip()
        
        if key.lower() == "skip":
            return {
                "message": "ℹ️ Ключ прокси не изменен",
                "keyboard": get_proxy_settings_keyboard()
            }

        # Обновляем настройки
        success = await self.settings_service.update_proxy_key(key if key else None, user_id)
        
        if success:
            status = "установлен" if key else "очищен"
            return {
                "message": f"✅ API ключ прокси {status}",
                "keyboard": get_proxy_settings_keyboard()
            }
        else:
            return {
                "message": "❌ Не удалось обновить ключ прокси",
                "keyboard": get_proxy_settings_keyboard()
            }

    async def handle_test_proxy_connection(self, user_id: int) -> Dict[str, Any]:
        """Тестирование прокси соединения"""
        if not await self._check_admin(user_id):
            return {
                "message": "❌ У вас нет прав администратора",
                "keyboard": get_admin_keyboard()
            }

        from config.settings import settings
        
        if not settings.openai_proxy_url or settings.openai_proxy_url == "https://api.openai.com":
            return {
                "message": "❌ URL прокси не настроен. Сначала укажите URL прокси.",
                "keyboard": get_proxy_settings_keyboard()
            }

        # Временно переключаемся на прокси для теста
        success, message = await self.openai_service.switch_to_proxy(
            settings.openai_proxy_url,
            settings.openai_proxy_key
        )

        test_text = f"""🔍 Тест прокси соединения

📡 Тестируемый прокси: {settings.openai_proxy_url}

{message}

💡 Примечание: Это тестовое подключение. Для постоянного использования выберите "🔄 Через прокси" в основном меню."""

        return {
            "message": test_text,
            "keyboard": get_proxy_settings_keyboard()
        }
