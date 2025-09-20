"""
Обработчики сообщений VK бота
"""
import json
import logging
from typing import Dict, Any, Optional

from services import UserService, OpenAIService, SettingsService
from repositories.models import MessageRole
from bot.keyboards import get_main_keyboard
from bot.middlewares import RateLimitMiddleware

logger = logging.getLogger(__name__)


class MessageHandler:
    """Обработчик сообщений"""

    def __init__(
            self,
            user_service: UserService,
            openai_service: OpenAIService,
            settings_service: SettingsService,
            rate_limiter: RateLimitMiddleware
    ):
        self.user_service = user_service
        self.openai_service = openai_service
        self.settings_service = settings_service
        self.rate_limiter = rate_limiter
        
        # Словарь для хранения состояний пользователей (ожидания ввода)
        self.user_states = {}

    async def handle_text_message(
            self,
            user_id: int,
            text: str,
            user_info: Dict[str, Any],
            payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Обработка текстового сообщения

        Args:
            user_id: ID пользователя VK
            text: Текст сообщения
            user_info: Информация о пользователе
            payload: Данные из payload кнопки

        Returns:
            Словарь с ответом
        """
        # Проверяем, находится ли пользователь в состоянии ожидания ввода
        if user_id in self.user_states:
            return await self._handle_user_input_state(user_id, text)
        
        # Проверяем rate limiting
        if await self.rate_limiter.is_rate_limited_async(user_id):
            time_left = await self.rate_limiter.get_time_until_reset_async(user_id)
            return {
                "message": f"⏳ Слишком много запросов! Попробуй через {time_left} секунд.",
                "keyboard": get_main_keyboard()
            }

        # Получаем или создаем пользователя
        await self.user_service.get_or_create_user(
            user_id=user_id,
            first_name=user_info.get('first_name'),
            last_name=user_info.get('last_name')
        )

        # Проверяем лимиты пользователя
        if not await self.user_service.can_make_request(user_id):
            return {
                "message": "❌ У вас закончились запросы! Обратитесь к администратору для увеличения лимита.",
                "keyboard": get_main_keyboard()
            }

        try:
            # Получаем контекст пользователя
            context = await self.user_service.get_user_context(user_id)

            # Добавляем сообщение пользователя в контекст
            await self.user_service.add_message_to_context(
                user_id, MessageRole.USER, text
            )

            # Получаем ответ от OpenAI
            context_messages = context.messages if context else []
            ai_response = await self.openai_service.generate_response_from_context(
                context_messages, text
            )

            # Добавляем ответ AI в контекст
            await self.user_service.add_message_to_context(
                user_id, MessageRole.ASSISTANT, ai_response
            )

            # Увеличиваем счетчик использованных запросов
            await self.user_service.use_request(user_id)

            # Получаем обновленную статистику
            stats = await self.user_service.get_user_stats(user_id)
            requests_left = stats['requests_remaining'] if stats else 0

            # Добавляем информацию о запросах к ответу
            footer = f"\n\n💡 Осталось запросов: {requests_left}"

            return {
                "message": ai_response + footer,
                "keyboard": get_main_keyboard()
            }

        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения от user_id={user_id}: {e}", exc_info=True)

            return {
                "message": "❌ Произошла ошибка при обработке вашего запроса. Попробуйте позже.",
                "keyboard": get_main_keyboard()
            }

    async def _handle_user_input_state(self, user_id: int, text: str) -> Dict[str, Any]:
        """Обработка ввода пользователя в состоянии ожидания"""
        state = self.user_states.get(user_id)
        if not state:
            return {
                "message": "❌ Состояние не найдено",
                "keyboard": get_main_keyboard()
            }
        
        action = state.get("action")
        
        # Импортируем обработчики
        from .openai_handlers import OpenAICommandHandler
        openai_handler = OpenAICommandHandler(
            self.user_service, self.openai_service, self.settings_service
        )
        
        # Очищаем состояние пользователя
        del self.user_states[user_id]
        
        # Обрабатываем ввод в зависимости от действия
        if action == "edit_proxy_url_input":
            return await openai_handler.handle_proxy_url_input(user_id, text)
        elif action == "edit_proxy_key_input":
            return await openai_handler.handle_proxy_key_input(user_id, text)
        else:
            from bot.keyboards.inline import get_openai_connection_menu_keyboard
            return {
                "message": "❌ Неизвестное действие",
                "keyboard": get_openai_connection_menu_keyboard()
            }

    async def handle_button_click(
            self,
            user_id: int,
            payload: Dict[str, Any],
            user_info: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Обработка нажатия на кнопку

        Args:
            user_id: ID пользователя
            payload: Данные из payload кнопки
            user_info: Информация о пользователе

        Returns:
            Словарь с ответом или None
        """
        command = payload.get("command")

        if not command:
            return None

        # Очищаем состояние пользователя при любой команде кнопки
        if user_id in self.user_states:
            del self.user_states[user_id]

        # Импортируем обработчики команд
        from .commands import CommandHandler
        
        command_handler = CommandHandler(self.user_service, self.openai_service, self.settings_service)

        # Основные команды
        if command == "main":
            return {
                "message": "🏠 Главное меню",
                "keyboard": get_main_keyboard()
            }
        elif command == "help":
            return await command_handler.handle_help(user_id)
        elif command == "status":
            return await command_handler.handle_status(user_id)
        elif command == "reset":
            return await command_handler.handle_reset(user_id)
        elif command == "ask":
            return {
                "message": "💬 Напиши свой вопрос, и я отвечу!",
                "keyboard": get_main_keyboard()
            }
        elif command == "admin":
            return await command_handler.handle_admin_panel(user_id)
        elif command == "users" and await self.user_service.is_admin(user_id):
            return await command_handler.handle_users_list(user_id)
        elif command == "commands":
            return await command_handler.handle_help(user_id)
        elif command == "about":
            return {
                "message": """🤖 О боте:

Я современный AI-ассистент, созданный для помощи пользователям VK.

🔸 **Технологии:**
• OpenAI GPT для генерации ответов
• Продвинутая система контекста
• Система лимитов и статистики
• Поддержка прокси для обхода блокировок

🔸 **Разработчик:** Кравченко Евгений
🔸 **Версия:** 1.0.0

💻 Бот написан на Python с использованием VK API и OpenAI API.""",
                "keyboard": get_main_keyboard()
            }
        
        # Команды настроек (только для админов)
        elif command == "settings_basic":
            from bot.keyboards.inline import get_basic_settings_keyboard
            return {
                "message": "🤖 **Основные настройки**\n\nВыберите параметр для настройки:",
                "keyboard": get_basic_settings_keyboard()
            }
        elif command == "settings_menu":
            from bot.keyboards.inline import get_settings_management_keyboard
            return {
                "message": "⚙️ **Управление настройками**",
                "keyboard": get_settings_management_keyboard()
            }
        
        # Команды OpenAI обрабатываются в main.py

        return None

    def extract_payload(self, message_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Извлечение payload из сообщения

        Args:
            message_data: Данные сообщения от VK API

        Returns:
            Словарь с payload или None
        """
        try:
            payload_str = message_data.get("payload")
            if payload_str:
                return json.loads(payload_str)
        except (json.JSONDecodeError, TypeError):
            pass

        return None
