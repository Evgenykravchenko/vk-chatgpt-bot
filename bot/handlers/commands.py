"""
Обработчики команд VK бота
"""
import json
from typing import Dict, Any, Optional

from services import UserService, OpenAIService, SettingsService
from bot.keyboards import (
    get_main_keyboard,
    get_help_keyboard,
    get_status_keyboard,
    get_admin_keyboard
)


class CommandHandler:
    """Обработчик команд"""

    def __init__(self, user_service: UserService, openai_service: OpenAIService, settings_service: SettingsService):
        self.user_service = user_service
        self.openai_service = openai_service
        self.settings_service = settings_service

    async def handle_start(self, user_id: int, user_info: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка команды начала работы"""
        # Получаем или создаем пользователя
        user = await self.user_service.get_or_create_user(
            user_id=user_id,
            first_name=user_info.get('first_name'),
            last_name=user_info.get('last_name')
        )

        welcome_text = f"""🤖 Привет, {user.display_name}!

Я AI-ассистент, готовый помочь тебе с любыми вопросами!

🔹 У тебя есть {user.requests_remaining} запросов
🔹 Я помню контекст последних {await self._get_context_size()} сообщений
🔹 Используй кнопки меню для удобной навигации

Просто напиши свой вопрос, и я отвечу! 😊"""

        return {
            "message": welcome_text,
            "keyboard": get_main_keyboard()
        }

    async def handle_help(self, user_id: int) -> Dict[str, Any]:
        """Обработка команды помощи"""
        help_text = """📖 Справка по использованию бота:

🔸 **Основные команды:**
• Просто напиши вопрос - получишь ответ от AI
• "Статус" - проверить лимиты и статистику
• "Сброс" - очистить контекст диалога
• "Помощь" - показать эту справку

🔸 **Возможности:**
• Запоминаю контекст беседы
• Отвечаю на вопросы любой сложности
• Помогаю с задачами и проблемами
• Поддерживаю диалог

🔸 **Лимиты:**
• У каждого пользователя есть лимит запросов
• Лимиты обновляются администратором
• Следи за статусом своих запросов

💡 **Совет:** Для лучших результатов формулируй вопросы четко и подробно!"""

        return {
            "message": help_text,
            "keyboard": get_help_keyboard()
        }

    async def handle_status(self, user_id: int) -> Dict[str, Any]:
        """Обработка команды статуса"""
        stats = await self.user_service.get_user_stats(user_id)

        if not stats:
            return {
                "message": "❌ Не удалось получить статистику",
                "keyboard": get_main_keyboard()
            }

        status_text = f"""📊 Твоя статистика:

👤 **Пользователь:** {stats['display_name']}
🔢 **ID:** {stats['user_id']}

📈 **Запросы:**
• Использовано: {stats['requests_used']}/{stats['requests_limit']}
• Осталось: {stats['requests_remaining']}

💬 **Контекст:**
• Сообщений в памяти: {stats['context_messages']}

📅 **Активность:**
• Регистрация: {stats['created_at'].strftime('%d.%m.%Y %H:%M')}
• Последняя активность: {stats['last_activity'].strftime('%d.%m.%Y %H:%M')}

{"🟢 Активен" if stats['is_active'] else "🔴 Неактивен"}"""

        return {
            "message": status_text,
            "keyboard": get_status_keyboard()
        }

    async def handle_reset(self, user_id: int) -> Dict[str, Any]:
        """Обработка команды сброса контекста"""
        await self.user_service.clear_user_context(user_id)

        return {
            "message": "🗑️ Контекст диалога очищен! Теперь я не помню предыдущие сообщения.",
            "keyboard": get_main_keyboard()
        }

    async def handle_admin_panel(self, user_id: int) -> Dict[str, Any]:
        """Обработка административной панели"""
        if not await self.user_service.is_admin(user_id):
            return {
                "message": "❌ У вас нет прав администратора",
                "keyboard": get_main_keyboard()
            }

        users = await self.user_service.get_all_users()
        total_users = len(users)
        active_users = len([u for u in users if u.is_active])
        total_requests = sum(u.requests_used for u in users)

        admin_text = f"""⚙️ Административная панель:

📊 Статистика:
• Всего пользователей: {total_users}
• Активных пользователей: {active_users}
• Общий объем запросов: {total_requests}

🛠️ Доступные функции:
• Просмотр пользователей
• Изменение настроек
• Статистика системы
• Сброс лимитов"""

        return {
            "message": admin_text,
            "keyboard": get_admin_keyboard()
        }

    async def handle_users_list(self, user_id: int) -> Dict[str, Any]:
        """Обработка списка пользователей (только для админов)"""
        if not await self.user_service.is_admin(user_id):
            return {
                "message": "❌ У вас нет прав администратора",
                "keyboard": get_main_keyboard()
            }

        users = await self.user_service.get_all_users()

        if not users:
            return {
                "message": "👥 Пользователей пока нет",
                "keyboard": get_admin_keyboard()
            }

        # Показываем топ-10 активных пользователей
        active_users = sorted(
            [u for u in users if u.is_active],
            key=lambda x: x.requests_used,
            reverse=True
        )[:10]

        users_text = "👥 Топ пользователей по активности:\n\n"

        for i, user in enumerate(active_users, 1):
            users_text += f"{i}. {user.display_name}\n"
            users_text += f"   📊 {user.requests_used}/{user.requests_limit} запросов\n"
            users_text += f"   🕐 {user.last_activity.strftime('%d.%m %H:%M')}\n\n"

        return {
            "message": users_text,
            "keyboard": get_admin_keyboard()
        }

    async def _get_context_size(self) -> int:
        """Получить размер контекста"""
        from config.settings import settings
        return settings.context_size

    async def handle_set_context_size(self, user_id: int, new_size_str: str) -> Dict[str, Any]:
        """Обработка команды установки размера контекста"""
        if not await self.user_service.is_admin(user_id):
            return {
                "message": "❌ У вас нет прав администратора",
                "keyboard": get_main_keyboard()
            }
        try:
            new_size = int(new_size_str)
            success = await self.settings_service.update_context_size(new_size, user_id)
            if success:
                return {
                    "message": f"✅ Размер контекста обновлен на {new_size}.",
                    "keyboard": get_admin_keyboard()
                }
            else:
                return {
                    "message": "❌ Некорректный размер контекста. Допустимо от 1 до 50.",
                    "keyboard": get_admin_keyboard()
                }
        except ValueError:
            return {
                "message": "❌ Некорректное значение. Введите число.",
                "keyboard": get_admin_keyboard()
            }

    async def handle_set_default_limit(self, user_id: int, new_limit_str: str) -> Dict[str, Any]:
        """Обработка команды установки лимита по умолчанию"""
        if not await self.user_service.is_admin(user_id):
            return {
                "message": "❌ У вас нет прав администратора",
                "keyboard": get_main_keyboard()
            }
        try:
            new_limit = int(new_limit_str)
            success = await self.settings_service.update_default_limit(new_limit, user_id)
            if success:
                return {
                    "message": f"✅ Лимит по умолчанию обновлен на {new_limit}.",
                    "keyboard": get_admin_keyboard()
                }
            else:
                return {
                    "message": "❌ Некорректный лимит. Допустимо от 1 до 1000.",
                    "keyboard": get_admin_keyboard()
                }
        except ValueError:
            return {
                "message": "❌ Некорректное значение. Введите число.",
                "keyboard": get_admin_keyboard()
            }
