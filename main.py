"""
Полная версия VK OpenAI бота с управлением доступом
"""
import asyncio
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, Any

import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.utils import get_random_id

from config.settings import settings
from repositories import (
    MemoryUserRepository,
    MemoryContextRepository,
    MemorySettingsRepository,
    MemoryAccessControlRepository
)
from repositories.sqlite_repo import (
    init_db,
    SQLiteUserRepository,
    SQLiteContextRepository,
    SQLiteSettingsRepository,
    SQLiteAccessControlRepository
)
from services import UserService, OpenAIService
from services.access_control_service import AccessControlService
from services.settings_service import SettingsService
from bot.handlers import CommandHandler, MessageHandler
from bot.middlewares import RateLimitMiddleware
from utils import VKImageUploader, ensure_resources_directory, VKUserResolver

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VKBot:
    """Основной класс VK бота"""

    def __init__(self):
        # Инициализация VK API
        self.vk_session = vk_api.VkApi(token=settings.vk_token)
        self.vk = self.vk_session.get_api()
        self.longpoll = VkLongPoll(self.vk_session)

        # Инициализация загрузчика изображений
        self.upload = vk_api.VkUpload(self.vk_session)
        self.image_uploader = VKImageUploader(self.vk, self.upload)

        # Инициализация resolver для VK ссылок
        self.user_resolver = VKUserResolver(self.vk)

        # Создаем папку resources если её нет
        ensure_resources_directory()

        # Инициализация репозиториев
        self.user_repo = SQLiteUserRepository()
        self.context_repo = SQLiteContextRepository()
        self.settings_repo = SQLiteSettingsRepository()
        self.access_repo = SQLiteAccessControlRepository()

        # Инициализация сервисов
        self.user_service = UserService(self.user_repo, self.context_repo)
        self.openai_service = OpenAIService()
        self.access_service = AccessControlService(self.access_repo)
        self.settings_service = SettingsService(self.settings_repo, self.user_repo, self.context_repo)

        # Инициализация middleware
        self.rate_limiter = RateLimitMiddleware(self.settings_service)

        # Инициализация обработчиков
        self.command_handler = CommandHandler(self.user_service, self.openai_service, self.settings_service)
        self.message_handler = MessageHandler(
            self.user_service,
            self.openai_service,
            self.rate_limiter
        )

        # Состояния пользователей для диалогов
        self._user_states = {}

    async def daily_reset_scheduler(self):
        """Асинхронный фоновый планировщик для ежедневного сброса лимитов"""
        while True:
            now = datetime.now()
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            seconds_until_midnight = (midnight - now).total_seconds()

            logger.info(f"Планировщик: сброс лимитов через {seconds_until_midnight:.0f} секунд.")
            
            await asyncio.sleep(seconds_until_midnight)

            logger.info("Планировщик: Начало ежедневного сброса лимитов запросов.")
            try:
                await self.user_service.reset_all_users_requests()
                logger.info("Планировщик: Ежедневный сброс лимитов запросов успешно завершен.")
            except Exception as e:
                logger.error(f"Планировщик: Ошибка при сбросе лимитов: {e}")
            
            # Небольшая задержка, чтобы избежать выполнения дважды в одну и ту же секунду
            await asyncio.sleep(1)

    async def start(self):
        """Асинхронный запуск бота и всех фоновых задач."""
        logger.info("🤖 VK OpenAI Bot запускается...")

        # Запускаем фоновые задачи: прослушивание событий и ежедневный сброс лимитов
        listener_task = asyncio.create_task(self._listen_events())
        scheduler_task = asyncio.create_task(self.daily_reset_scheduler())

        logger.info("✅ Планировщик сброса лимитов запущен.")
        logger.info("✅ Бот готов к работе и слушает события.")

        # Ожидаем завершения всех задач
        await asyncio.gather(listener_task, scheduler_task)

    async def _listen_events(self):
        """Асинхронное прослушивание событий VK."""
        loop = asyncio.get_running_loop()
        logger.info("🎧 Начинаю асинхронное прослушивание событий...")
        
        while True:
            try:
                # Выполняем блокирующий вызов в отдельном потоке, чтобы не блокировать основной цикл
                events = await loop.run_in_executor(None, self.longpoll.check)
                
                if events:
                    for event in events:
                        if event.type == VkEventType.MESSAGE_NEW and event.to_me:
                            # Запускаем обработку каждого сообщения как отдельную задачу
                            asyncio.create_task(self._handle_message(event))
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле прослушивания событий: {e}")
                # Пауза перед повторной попыткой, чтобы избежать спама логов при сбое сети
                await asyncio.sleep(5)

    async def _handle_message(self, event):
        """Обработка входящего сообщения"""
        try:
            user_id = event.user_id
            message_text = event.text

            logger.info(f"📨 Сообщение от {user_id}: {message_text}")

            # Проверяем доступ пользователя
            has_access = await self.access_service.check_user_access(user_id)

            if not has_access:
                # Получаем кастомное сообщение об отказе
                access_message = await self.access_service.get_access_denied_message(user_id)
                access_mode = await self.access_service.get_access_mode()

                self._send_message(user_id, access_message)
                logger.info(f"🚫 Доступ запрещен пользователю {user_id} (режим: {access_mode})")
                return

            # Получаем информацию о пользователе
            user_info = self._get_user_info(user_id)

            # Проверяем payload (для кнопок)
            payload = self._extract_payload(event)

            # Определяем команду
            response_data = None

            # Проверяем состояния пользователя (ожидание ввода)
            state_result = await self._handle_user_state(user_id, message_text)
            if state_result:
                response_data = state_result
            # Сначала проверяем payload (нажатие кнопки)
            elif payload:
                response_data = await self._handle_button_click(user_id, payload, user_info)
            elif message_text.lower() in ['начать', 'start', '/start']:
                response_data = await self._handle_start_command(user_id, user_info)
            elif message_text.lower() in ['помощь', 'help', '/help']:
                response_data = await self._handle_help_command(user_id)
            elif message_text.lower() in ['статус', 'status', '/status']:
                response_data = await self._handle_status_command(user_id)
            elif message_text.lower() in ['сброс', 'reset', '/reset']:
                response_data = await self._handle_reset_command(user_id)
            elif message_text.lower() in ['админ', 'admin']:
                response_data = await self._handle_admin_command(user_id)
            else:
                # Обрабатываем как обычное сообщение к AI
                response_data = await self._handle_ai_message(user_id, message_text, user_info)

            # Отправляем ответ
            if response_data:
                self._send_message(
                    user_id,
                    response_data.get('message', 'Ошибка обработки'),
                    response_data.get('keyboard'),
                    response_data.get('attachment')
                )

        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщения от {event.user_id}: {e}")
            self._send_message(
                event.user_id,
                "❌ Произошла внутренняя ошибка. Попробуйте позже."
            )

    def _extract_payload(self, event) -> dict:
        """Извлечение payload из события VK"""
        try:
            # В VK API payload может быть в разных местах
            if hasattr(event, 'extra_values') and 'payload' in event.extra_values:
                import json
                return json.loads(event.extra_values['payload'])
            elif hasattr(event, 'message') and isinstance(event.message, dict):
                if 'payload' in event.message:
                    import json
                    return json.loads(event.message['payload'])
        except (json.JSONDecodeError, TypeError, KeyError):
            pass
        return {}

    async def _handle_start_command(self, user_id: int, user_info: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка команды начала работы"""
        try:
            from bot.keyboards import get_main_keyboard

            # Проверяем, новый ли это пользователь
            existing_user = await self.user_service.user_repo.get_user(user_id)
            is_new_user = existing_user is None

            user = await self.user_service.get_or_create_user(
                user_id=user_id,
                first_name=user_info.get('first_name'),
                last_name=user_info.get('last_name')
            )

            welcome_text = f"""🤖 Привет, {user.display_name}!

Я AI-ассистент, готовый помочь тебе с любыми вопросами!

🔹 У тебя есть {user.requests_remaining} запросов
🔹 Я помню контекст последних {settings.context_size} сообщений

Просто напиши свой вопрос, и я отвечу! 😊

Используй кнопки меню для удобной навигации."""

            result = {
                "message": welcome_text,
                "keyboard": get_main_keyboard()
            }

            # Если это новый пользователь, добавляем приветственное изображение
            if is_new_user:
                logger.info(f"🆕 Новый пользователь: {user.display_name} (ID: {user_id})")
                welcome_image = self.image_uploader.get_welcome_image()
                if welcome_image:
                    result["attachment"] = welcome_image
                    logger.info(f"📷 Отправляю приветственное изображение пользователю {user_id}")
                else:
                    logger.warning("⚠️ Приветственное изображение не найдено или не удалось загрузить")

            return result

        except Exception as e:
            logger.error(f"Ошибка создания пользователя: {e}")
            from bot.keyboards import get_main_keyboard
            return {
                "message": "❌ Ошибка регистрации. Попробуйте позже.",
                "keyboard": get_main_keyboard()
            }

    async def _handle_help_command(self, user_id: int) -> Dict[str, Any]:
        """Обработка команды помощи"""
        from bot.keyboards import get_help_keyboard

        help_text = """📖 Справка по использованию бота:

🔸 Основные команды:
• Просто напиши вопрос - получишь ответ от AI
• "Статус" - проверить лимиты и статистику
• "Сброс" - очистить контекст диалога
• "Помощь" - показать эту справку

🔸 Возможности:
• Запоминаю контекст беседы
• Отвечаю на вопросы любой сложности
• Помогаю с задачами и проблемами
• Поддерживаю диалог

💡 Совет: Для лучших результатов формулируй вопросы четко и подробно!"""

        return {
            "message": help_text,
            "keyboard": get_help_keyboard()
        }

    async def _handle_status_command(self, user_id: int) -> Dict[str, Any]:
        """Обработка команды статуса"""
        try:
            from bot.keyboards import get_status_keyboard, get_main_keyboard

            stats = await self.user_service.get_user_stats(user_id)

            if not stats:
                return {
                    "message": "❌ Пользователь не найден. Отправьте 'Начать'",
                    "keyboard": get_main_keyboard()
                }

            status_text = f"""📊 Твоя статистика:

👤 Пользователь: {stats['display_name']}
🔢 ID: {stats['user_id']}

📈 Запросы (на день):
• Использовано: {stats['requests_used']}/{stats['requests_limit']}
• Осталось: {stats['requests_remaining']}

💬 Контекст:
• Сообщений в памяти: {stats['context_messages']}

📅 Активность:
• Регистрация: {stats['created_at'].strftime('%d.%m.%Y %H:%M')}
• Последняя активность: {stats['last_activity'].strftime('%d.%m.%Y %H:%M')}

🔄 Лимиты сбрасываются ежедневно в 00:00."""

            return {
                "message": status_text,
                "keyboard": get_status_keyboard()
            }

        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            from bot.keyboards import get_main_keyboard
            return {
                "message": "❌ Ошибка получения статистики",
                "keyboard": get_main_keyboard()
            }

    async def _handle_reset_command(self, user_id: int) -> Dict[str, Any]:
        """Обработка команды сброса контекста"""
        try:
            from bot.keyboards import get_main_keyboard

            await self.user_service.clear_user_context(user_id)

            return {
                "message": "🗑️ Контекст диалога очищен! Теперь я не помню предыдущие сообщения.",
                "keyboard": get_main_keyboard()
            }

        except Exception as e:
            logger.error(f"Ошибка сброса контекста: {e}")
            from bot.keyboards import get_main_keyboard
            return {
                "message": "❌ Ошибка сброса контекста",
                "keyboard": get_main_keyboard()
            }

    async def _handle_admin_command(self, user_id: int) -> Dict[str, Any]:
        """Обработка административной команды"""
        from bot.keyboards import get_admin_keyboard, get_main_keyboard

        is_admin = await self.user_service.is_admin(user_id)

        if not is_admin:
            return {
                "message": "❌ У вас нет прав администратора",
                "keyboard": get_main_keyboard()
            }

        users = await self.user_service.get_all_users()
        access_stats = await self.access_service.get_access_stats()

        total_users = len(users)
        active_users = len([u for u in users if u.is_active])
        total_requests = sum(u.requests_used for u in users)

        mode_names = {
            "public": "🌐 Открытый",
            "whitelist": "📋 Белый список",
            "admin_only": "👤 Только админ"
        }

        admin_text = f"""⚙️ Административная панель:

📊 Статистика пользователей:
• Всего пользователей: {total_users}
• Активных пользователей: {active_users}
• Общий объем запросов: {total_requests}

🔐 Доступ к боту:
• Режим: {mode_names.get(access_stats['mode'], access_stats['mode'])}
• В белом списке: {access_stats['whitelist_count']}
• Заблокировано: {access_stats['blacklist_count']}"""

        return {
            "message": admin_text,
            "keyboard": get_admin_keyboard()
        }

    async def _handle_settings_commands(self, user_id: int, command: str) -> Dict[str, Any]:
        """Обработка команд управления настройками"""
        from bot.keyboards import (
            get_admin_keyboard, get_main_keyboard, get_settings_management_keyboard,
            get_basic_settings_keyboard, get_system_settings_keyboard, get_ai_model_keyboard
        )

        # Проверяем права админа
        is_admin = await self.user_service.is_admin(user_id)

        if not is_admin:
            return {
                "message": "❌ У вас нет прав администратора",
                "keyboard": get_main_keyboard()
            }

        if command == "settings_menu":
            settings_info = await self.settings_service.get_settings_info()

            return {
                "message": f"""{settings_info}

💡 Выберите категорию настроек для изменения:""",
                "keyboard": get_settings_management_keyboard()
            }

        elif command == "settings_view":
            settings_info = await self.settings_service.get_settings_info()

            return {
                "message": settings_info,
                "keyboard": get_settings_management_keyboard()
            }

        elif command == "settings_basic":
            bot_settings = await self.settings_service.get_bot_settings()

            text = f"""🤖 Основные настройки:

💭 Размер контекста: {bot_settings.context_size} сообщений
🎯 Лимит по умолчанию: {bot_settings.default_user_limit} запросов  
🧠 Модель AI: {bot_settings.openai_model}
💬 Приветствие: {"Настроено" if bot_settings.welcome_message != "Привет! Я AI ассистент. Задай мне любой вопрос!" else "По умолчанию"}

Выберите параметр для изменения:"""

            return {
                "message": text,
                "keyboard": get_basic_settings_keyboard()
            }

        elif command == "settings_system":
            bot_settings = await self.settings_service.get_bot_settings()

            text = f"""⚡ Системные настройки:

⏱️ Rate Limiting: {"🟢 Включен" if bot_settings.rate_limit_enabled else "🔴 Отключен"}
🔧 Режим обслуживания: {"🟢 Включен" if bot_settings.maintenance_mode else "🔴 Отключен"}

Нажмите на параметр для переключения:"""

            return {
                "message": text,
                "keyboard": get_system_settings_keyboard()
            }

        elif command == "edit_ai_model":
            bot_settings = await self.settings_service.get_bot_settings()

            text = f"""🧠 Выбор модели OpenAI:

Текущая модель: {bot_settings.openai_model}

Доступные модели:
🚀 GPT-4 - самая мощная модель
⚡ GPT-3.5 - быстрая и экономичная  
🧪 GPT-4-turbo - оптимизированная версия

Выберите новую модель:"""

            return {
                "message": text,
                "keyboard": get_ai_model_keyboard()
            }

        # Изменение модели AI
        elif command.startswith("set_model_"):
            model_map = {
                "set_model_gpt35": "gpt-3.5-turbo",
                "set_model_gpt4": "gpt-4",
                "set_model_gpt4_turbo": "gpt-4-turbo"
            }

            new_model = model_map.get(command)
            if new_model:
                success = await self.settings_service.update_ai_model(new_model, user_id)

                if success:
                    return {
                        "message": f"✅ Модель AI изменена на: {new_model}",
                        "keyboard": get_basic_settings_keyboard()
                    }
                else:
                    return {
                        "message": "❌ Ошибка изменения модели",
                        "keyboard": get_ai_model_keyboard()
                    }

        # Переключение системных настроек
        elif command == "toggle_rate_limit":
            new_state = await self.settings_service.toggle_rate_limit(user_id)

            status = "включен" if new_state else "отключен"
            return {
                "message": f"✅ Rate Limiting {status}",
                "keyboard": get_system_settings_keyboard()
            }

        elif command == "toggle_maintenance":
            new_state = await self.settings_service.toggle_maintenance_mode(user_id)

            status = "включен" if new_state else "отключен"
            message = f"✅ Режим обслуживания {status}"
            if new_state:
                message += "\n\n⚠️ В режиме обслуживания бот доступен только администратору!"

            return {
                "message": message,
                "keyboard": get_system_settings_keyboard()
            }

        # Сброс настроек
        elif command == "settings_reset":
            success = await self.settings_service.reset_settings_to_defaults(user_id)

            if success:
                return {
                    "message": "✅ Настройки сброшены к значениям по умолчанию",
                    "keyboard": get_settings_management_keyboard()
                }
            else:
                return {
                    "message": "❌ Ошибка сброса настроек",
                    "keyboard": get_settings_management_keyboard()
                }

        # Изменение числовых параметров через состояния
        elif command in ["edit_context_size", "edit_default_limit", "edit_welcome"]:
            self._user_states[user_id] = command

            prompts = {
                "edit_context_size": "💭 Изменение размера контекста\n\nВведите новый размер (от 1 до 50):\nТекущий размер: ",
                "edit_default_limit": "🎯 Изменение лимита по умолчанию\n\nВведите новый лимит (от 1 до 1000):\nТекущий лимит: ",
                "edit_welcome": "💬 Изменение приветственного сообщения\n\nВведите новое сообщение (до 1000 символов):"
            }

            from bot.keyboards import get_settings_input_keyboard

            return {
                "message": prompts[command],
                "keyboard": get_settings_input_keyboard()
            }

        elif command == "rate_limit_menu":
            rate_limit_info = await self.settings_service.get_rate_limit_info()

            status_emoji = "🟢" if rate_limit_info["enabled"] else "🔴"
            status_text = "Включен" if rate_limit_info["enabled"] else "Отключен"

            text = f"""⏱️ Настройки Rate Limiting:

        {status_emoji} Статус: {status_text}
        🔢 Лимит: {rate_limit_info["calls"]} запросов
        ⏱️ Период: {rate_limit_info["period"]} секунд
        📊 Итого: {rate_limit_info["description"]}

        💡 Rate Limiting защищает бота от спама, ограничивая количество запросов к OpenAI от одного пользователя за определенный период времени."""

            from bot.keyboards import get_rate_limit_keyboard

            return {
                "message": text,
                "keyboard": get_rate_limit_keyboard()
            }

        elif command == "show_rate_limit_info":
            rate_limit_info = await self.settings_service.get_rate_limit_info()

            # Получаем информацию о текущих активных ограничениях
            active_limits = []
            if hasattr(self, 'rate_limiter'):
                # Подсчитываем сколько пользователей сейчас имеют активные ограничения
                active_count = len(
                    [user_id for user_id, queue in self.rate_limiter.user_requests.items() if len(queue) > 0])
                if active_count > 0:
                    active_limits.append(f"Активных ограничений: {active_count} пользователей")

            text = f"""📊 Подробная информация Rate Limiting:

        ⚙️ Настройки:
        • Статус: {"🟢 Включен" if rate_limit_info["enabled"] else "🔴 Отключен"}
        • Максимум запросов: {rate_limit_info["calls"]}
        • Период сброса: {rate_limit_info["period"]} сек
        • Описание: {rate_limit_info["description"]}

        📈 Статистика:
        {active_limits[0] if active_limits else "• Нет активных ограничений"}

        💡 Как работает:
        Каждый пользователь может сделать максимум {rate_limit_info["calls"]} запросов за {rate_limit_info["period"]} секунд. После превышения лимита пользователь получает сообщение о необходимости подождать."""

            from bot.keyboards import get_rate_limit_keyboard

            return {
                "message": text,
                "keyboard": get_rate_limit_keyboard()
            }

        elif command in ["edit_rate_limit_calls", "edit_rate_limit_period"]:
            rate_limit_info = await self.settings_service.get_rate_limit_info()

            if command == "edit_rate_limit_calls":
                self._user_states[user_id] = "edit_rate_limit_calls"
                message = f"""🔢 Изменение лимита запросов

        Введите новое количество запросов (от 1 до 100):
        Текущее значение: {rate_limit_info["calls"]}

        💡 Рекомендуемые значения:
        • 3-5 для строгого ограничения
        • 5-10 для обычного использования  
        • 10-20 для активных пользователей"""
            else:
                self._user_states[user_id] = "edit_rate_limit_period"
                message = f"""⏱️ Изменение периода сброса

        Введите новый период в секундах (от 1 до 3600):
        Текущее значение: {rate_limit_info["period"]} сек

        💡 Рекомендуемые значения:
        • 30-60 сек для быстрого сброса
        • 60-300 сек для обычного использования
        • 300+ сек для строгого контроля"""

            from bot.keyboards import get_rate_limit_input_keyboard

            return {
                "message": message,
                "keyboard": get_rate_limit_input_keyboard()
            }

        elif command == "rate_limit_menu":
            rate_limit_info = await self.settings_service.get_rate_limit_info()

            status_emoji = "🟢" if rate_limit_info["enabled"] else "🔴"
            status_text = "Включен" if rate_limit_info["enabled"] else "Отключен"

            text = f"""⏱️ Настройки Rate Limiting:

        {status_emoji} Статус: {status_text}
        🔢 Лимит: {rate_limit_info["calls"]} запросов
        ⏱️ Период: {rate_limit_info["period"]} секунд
        📊 Итого: {rate_limit_info["description"]}

        💡 Rate Limiting защищает бота от спама, ограничивая количество запросов к OpenAI от одного пользователя за определенный период времени."""

            from bot.keyboards import get_rate_limit_keyboard

            return {
                "message": text,
                "keyboard": get_rate_limit_keyboard()
            }

        elif command == "show_rate_limit_info":
            rate_limit_info = await self.settings_service.get_rate_limit_info()

            # Получаем информацию о текущих активных ограничениях
            active_limits = []
            if hasattr(self, 'rate_limiter'):
                try:
                    # Подсчитываем сколько пользователей сейчас имеют активные ограничения
                    stats = await self.rate_limiter.get_global_statistics()
                    active_count = stats.get('limited_users', 0)
                    total_active = stats.get('active_users', 0)
                    if active_count > 0:
                        active_limits.append(f"Ограничено: {active_count} из {total_active} активных пользователей")
                    elif total_active > 0:
                        active_limits.append(f"Активных пользователей: {total_active}, ограничений нет")
                except Exception as e:
                    active_limits.append("Не удалось получить статистику активных ограничений")

            text = f"""📊 Подробная информация Rate Limiting:

        ⚙️ Настройки:
        • Статус: {"🟢 Включен" if rate_limit_info["enabled"] else "🔴 Отключен"}
        • Максимум запросов: {rate_limit_info["calls"]}
        • Период сброса: {rate_limit_info["period"]} сек
        • Описание: {rate_limit_info["description"]}

        📈 Статистика:
        {active_limits[0] if active_limits else "• Нет данных о текущих ограничениях"}

        💡 Как работает:
        Каждый пользователь может сделать максимум {rate_limit_info["calls"]} запросов за {rate_limit_info["period"]} секунд. После превышения лимита пользователь получает сообщение о необходимости подождать."""

            from bot.keyboards import get_rate_limit_keyboard

            return {
                "message": text,
                "keyboard": get_rate_limit_keyboard()
            }

        elif command in ["edit_rate_limit_calls", "edit_rate_limit_period"]:
            rate_limit_info = await self.settings_service.get_rate_limit_info()

            if command == "edit_rate_limit_calls":
                self._user_states[user_id] = "edit_rate_limit_calls"
                message = f"""🔢 Изменение лимита запросов

        Введите новое количество запросов (от 1 до 100):
        Текущее значение: {rate_limit_info["calls"]}

        💡 Рекомендуемые значения:
        • 3-5 для строгого ограничения
        • 5-10 для обычного использования  
        • 10-20 для активных пользователей"""
            else:
                self._user_states[user_id] = "edit_rate_limit_period"
                message = f"""⏱️ Изменение периода сброса

        Введите новый период в секундах (от 1 до 3600):
        Текущее значение: {rate_limit_info["period"]} сек

        💡 Рекомендуемые значения:
        • 30-60 сек для быстрого сброса
        • 60-300 сек для обычного использования
        • 300+ сек для строгого контроля"""

            from bot.keyboards import get_rate_limit_input_keyboard

            return {
                "message": message,
                "keyboard": get_rate_limit_input_keyboard()
            }

        return {
            "message": "❓ Неизвестная команда настроек",
            "keyboard": get_settings_management_keyboard()
        }

    async def _handle_ai_message(self, user_id: int, message_text: str, user_info: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка сообщения для AI"""
        try:
            from bot.keyboards import get_main_keyboard

            # Проверяем лимиты
            can_request = await self.user_service.can_make_request(user_id)

            if not can_request:
                return {
                    "message": "❌ У вас закончились запросы! Обратитесь к администратору.",
                    "keyboard": get_main_keyboard()
                }

            # Получаем ответ от AI
            response_data = await self.message_handler.handle_text_message(
                user_id, message_text, user_info, None
            )

            # Добавляем клавиатуру к ответу AI
            if response_data and not response_data.get('keyboard'):
                response_data['keyboard'] = get_main_keyboard()

            return response_data

        except Exception as e:
            from bot.keyboards import get_main_keyboard
            logger.error(f"Ошибка обработки AI сообщения: {e}")
            return {
                "message": "❌ Ошибка обработки запроса. Попробуйте позже.",
                "keyboard": get_main_keyboard()
            }

    async def _handle_button_click(self, user_id: int, payload: dict, user_info: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка нажатия на кнопку"""
        command = payload.get("command")

        if not command:
            return None

        logger.info(f"🔘 Нажата кнопка: {command} от {user_id}")

        # ВАЖНО: Сбрасываем состояние пользователя при нажатии любой кнопки навигации
        # кроме кнопок подтверждения действий
        navigation_buttons = [
            "main", "help", "status", "reset", "admin", "settings_menu", "settings_basic",
            "settings_system", "access_control", "whitelist", "users", "stats", "about",
            "commands", "ask", "cancel"
        ]

        if command in navigation_buttons and user_id in self._user_states:
            del self._user_states[user_id]
            logger.info(f"🔄 Сброшено состояние для пользователя {user_id} при нажатии кнопки {command}")

        # Команды управления доступом
        access_commands = [
            "access_control", "access_mode", "access_stats",
            "set_mode_public", "set_mode_whitelist", "set_mode_admin",
            "whitelist", "whitelist_show", "whitelist_add", "whitelist_remove",
            "blacklist", "cancel", "access_messages", "view_messages",
            "edit_whitelist_msg", "edit_admin_msg", "edit_blocked_msg"
        ]

        # Команды админ панели
        admin_commands = ["users", "settings", "stats", "manage_user", "reset_all_limits_confirm", "confirm_reset_all_limits"] 

        # Команды управления пользователем
        user_manage_commands = ["user_set_limit", "user_reset_limit", "user_show_stats"]

        # Команды управления настройками
        settings_commands = [
            "settings_menu", "settings_basic", "settings_system", "settings_view", "settings_reset",
            "edit_context_size", "edit_default_limit", "edit_ai_model", "edit_welcome",
            "set_model_gpt35", "set_model_gpt4", "set_model_gpt4_turbo", "set_model_gpt4o",
            "toggle_rate_limit", "toggle_maintenance",
            "rate_limit_menu", "show_rate_limit_info", "edit_rate_limit_calls", "edit_rate_limit_period"
        ]

        if command in access_commands:
            return await self._handle_access_control_commands(user_id, command, payload)
        elif command in admin_commands:
            return await self._handle_admin_commands(user_id, command, payload)
        elif command in user_manage_commands:
            return await self._handle_user_management_commands(user_id, command, payload)
        elif command in settings_commands:
            return await self._handle_settings_commands(user_id, command)

        # Обрабатываем стандартные команды кнопок
        if command == "ask":
            from bot.keyboards import get_main_keyboard
            return {
                "message": "💬 Напиши свой вопрос, и я отвечу!",
                "keyboard": get_main_keyboard()
            }
        elif command == "status":
            return await self._handle_status_command(user_id)
        elif command == "reset":
            return await self._handle_reset_command(user_id)
        elif command == "help":
            return await self._handle_help_command(user_id)
        elif command == "main":
            from bot.keyboards import get_main_keyboard
            return {
                "message": "🏠 Главное меню",
                "keyboard": get_main_keyboard()
            }
        elif command == "whitelist":
            return await self._handle_access_control_commands(user_id, command, payload)
        elif command == "admin":
            # Сбрасываем состояние если пользователь вернулся в админ панель
            if user_id in self._user_states:
                del self._user_states[user_id]
            return await self._handle_admin_command(user_id)
        elif command == "settings_menu":
            # Сбрасываем состояние если пользователь перешел в настройки
            if user_id in self._user_states:
                del self._user_states[user_id]
            return await self._handle_settings_commands(user_id, command)
        elif command == "commands":
            return await self._handle_help_command(user_id)
        elif command == "about":
            from bot.keyboards import get_main_keyboard
            return {
                "message": """🤖 О боте:

Я современный AI-ассистент, созданный для помощи пользователям VK.

🔸 Технологии:
• OpenAI GPT для генерации ответов
• Продвинутая система контекста
• Система лимитов и статистики

🔸 Разработчик: Python Developer
🔸 Версия: 1.0.0

💻 Бот написан на Python с использованием VK API и OpenAI API.""",
                "keyboard": get_main_keyboard()
            }
        
        return None
    
    async def _handle_access_control_commands(self, user_id: int, command: str, payload: dict = None) -> Dict[str, Any]:
        """Обработка команд управления доступом"""
        from bot.keyboards import (
            get_access_control_keyboard, get_access_mode_keyboard,
            get_whitelist_management_keyboard, get_main_keyboard,
            get_admin_keyboard, get_confirmation_keyboard,
            get_access_messages_keyboard
        )
        
        # Проверяем права админа
        is_admin = await self.user_service.is_admin(user_id)
        
        if not is_admin:
            return {
                "message": "❌ У вас нет прав администратора",
                "keyboard": get_main_keyboard()
            }
        
        # Главное меню управления доступом
        if command == "access_control":
            info_text = await self.access_service.get_access_info_text()
            
            return {
                "message": info_text,
                "keyboard": get_access_control_keyboard()
            }
        
        # Меню выбора режима доступа
        elif command == "access_mode":
            current_mode = await self.access_service.get_access_mode()
            
            mode_names = {
                "public": "🌐 Открытый (для всех)",
                "whitelist": "📋 Белый список", 
                "admin_only": "👤 Только администратор"
            }
            
            text = f"""🎯 Выбор режима доступа:

Текущий режим: {mode_names.get(current_mode, current_mode)}

Режимы:
🌐 Открытый - все пользователи могут использовать бота
📋 Белый список - только пользователи из списка
👤 Только админ - доступ только у администратора"""
            
            return {
                "message": text,
                "keyboard": get_access_mode_keyboard()
            }
        
        # Установка режимов доступа
        elif command.startswith("set_mode_"):
            mode = command.replace("set_mode_", "")
            success = await self.access_service.set_access_mode(mode, user_id)
            
            if success:
                mode_names = {
                    "public": "🌐 Открытый доступ",
                    "whitelist": "📋 Белый список",
                    "admin": "👤 Только администратор"
                }
                return {
                    "message": f"✅ Режим доступа изменен на: {mode_names.get(mode, mode)}",
                    "keyboard": get_access_control_keyboard()
                }
            else:
                return {
                    "message": "❌ Ошибка изменения режима",
                    "keyboard": get_access_mode_keyboard()
                }
        
        # Управление белым списком
        elif command == "whitelist":
            # Сбрасываем состояние ожидания ввода если пользователь вернулся в меню
            if user_id in self._user_states:
                del self._user_states[user_id]
                
            whitelist = await self.access_service.get_whitelist()
            
            text = f"""📋 Управление белым списком:

Пользователей в списке: {len(whitelist)}

Команды:
➕ Добавить - добавить пользователя по ID
➖ Удалить - удалить пользователя из списка
📋 Показать - показать весь список"""
            
            if whitelist:
                text += "\n\nПервые 5 пользователей:"
                for user_id_item in whitelist[:5]:
                    text += f"\n• {user_id_item}"
                if len(whitelist) > 5:
                    text += f"\n• ... и еще {len(whitelist) - 5}"
            
            return {
                "message": text,
                "keyboard": get_whitelist_management_keyboard()
            }
        
        # Показать полный белый список
        elif command == "whitelist_show":
            whitelist = await self.access_service.get_whitelist()
            
            if not whitelist:
                text = "📋 Белый список пуст"
            else:
                text = f"📋 Белый список ({len(whitelist)} пользователей):\n\n"
                
                # Получаем информацию о пользователях
                for i, user_id_item in enumerate(whitelist, 1):
                    try:
                        user_info = self._get_user_info(user_id_item)
                        if user_info and (user_info.get('first_name') or user_info.get('last_name')):
                            name = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
                            text += f"{i}. {name} (ID: {user_id_item})\n"
                        else:
                            text += f"{i}. ID: {user_id_item}\n"
                    except:
                        text += f"{i}. ID: {user_id_item}\n"
                    
                    if i >= 15:  # Ограничиваем вывод
                        text += f"... и еще {len(whitelist) - 15} пользователей\n"
                        text += "\n💡 Полный список слишком большой для отображения"
                        break
            
            return {
                "message": text,
                "keyboard": get_whitelist_management_keyboard()
            }
        
        # Статистика доступа
        elif command == "access_stats":
            stats = await self.access_service.get_access_stats()
            history = await self.access_service.get_access_history(5)
            
            text = f"""📈 Статистика доступа:

🎯 Текущий режим: {stats['mode']}
📋 В белом списке: {stats['whitelist_count']} пользователей
🚫 Заблокировано: {stats['blacklist_count']} пользователей

📜 Последние изменения:"""
            
            if history:
                for record in history:
                    time_str = record['timestamp'].strftime('%d.%m %H:%M')
                    text += f"\n• {time_str}: {record['action']}"
            else:
                text += "\nИзменений нет"
            
            return {
                "message": text,
                "keyboard": get_access_control_keyboard()
            }
        
        # Состояние ожидания ID для добавления/удаления
        elif command == "whitelist_add":
            # Сохраняем состояние пользователя
            self._user_states[user_id] = "waiting_user_id_add"

            help_text = """➕ Добавление в белый список

        Отправьте одним сообщением:
        • ID пользователя: 123456789
        • Ссылку VK: https://vk.com/id123456789
        • Ссылку VK: https://vk.com/username  
        • Username: @username или username

        Пример: https://vk.com/durov"""

            from bot.keyboards import get_whitelist_input_keyboard

            return {
                "message": help_text,
                "keyboard": get_whitelist_input_keyboard()
            }

        elif command == "whitelist_remove":
            self._user_states[user_id] = "waiting_user_id_remove"

            help_text = """➖ Удаление из белого списка

        Отправьте одним сообщением:
        • ID пользователя: 123456789
        • Ссылку VK: https://vk.com/id123456789
        • Ссылку VK: https://vk.com/username
        • Username: @username или username

        Пример: https://vk.com/durov"""

            from bot.keyboards import get_whitelist_input_keyboard

            return {
                "message": help_text,
                "keyboard": get_whitelist_input_keyboard()
            }
        
        # Отмена операции
        elif command == "cancel":
            if user_id in self._user_states:
                del self._user_states[user_id]
            
            return {
                "message": "❌ Операция отменена",
                "keyboard": get_access_control_keyboard()
            }
        
        # Управление сообщениями
        elif command == "access_messages":
            return {
                "message": """💬 Управление сообщениями доступа:

Здесь вы можете настроить текст сообщений, которые видят пользователи при ограничении доступа.

🔸 Бета-тест - сообщение для режима белого списка
🔸 Тех. работы - сообщение для режима "только админ"  
🔸 Блокировка - сообщение для заблокированных пользователей
🔸 Просмотр - посмотреть текущие сообщения""",
                "keyboard": get_access_messages_keyboard()
            }
        
        elif command == "view_messages":
            access_control = await self.access_service._get_access_control()
            
            text = """📖 Текущие сообщения доступа:

🔸 Режим бета-тестирования:
""" + access_control.whitelist_message + """

🔸 Техническое обслуживание:
""" + access_control.admin_only_message + """

🔸 Блокировка пользователя:
""" + access_control.blocked_message
            
            return {
                "message": text,
                "keyboard": get_access_messages_keyboard()
            }
        
        return {
            "message": "❓ Неизвестная команда",
            "keyboard": get_access_control_keyboard()
        }

    async def _handle_user_state(self, user_id: int, message_text: str) -> Dict[str, Any]:
        """Обработка состояний пользователя (ожидание ввода)"""
        from bot.keyboards import (
            get_whitelist_management_keyboard, get_settings_management_keyboard,
            get_basic_settings_keyboard, get_user_management_keyboard, get_admin_keyboard,
            get_rate_limit_keyboard
        )

        state_data = self._user_states.get(user_id)
        if not state_data:
            return None

        state = state_data if isinstance(state_data, str) else state_data.get("state")

        # Отмена любой операции
        if message_text.lower() in ["отмена", "❌ отмена", "⬅️ назад", "назад"]:
            del self._user_states[user_id]

            # Возвращаем в соответствующее меню в зависимости от состояния
            if state in ["edit_context_size", "edit_default_limit", "edit_welcome"]:
                return {
                    "message": "❌ Действие отменено. Возвращаемся к настройкам.",
                    "keyboard": get_basic_settings_keyboard()
                }
            elif state in ["edit_rate_limit_calls", "edit_rate_limit_period"]:
                return {
                    "message": "❌ Действие отменено. Возвращаемся к настройкам rate limiting.",
                    "keyboard": get_rate_limit_keyboard()
                }
            elif state in ["waiting_user_id_add", "waiting_user_id_remove"]:
                return {
                    "message": "❌ Действие отменено. Возвращаемся к управлению белым списком.",
                    "keyboard": get_whitelist_management_keyboard()
                }
            elif state in ["waiting_user_to_manage", "user_waiting_new_limit"]:
                return {
                    "message": "❌ Действие отменено. Возвращаемся в админ панель.",
                    "keyboard": get_admin_keyboard()
                }
            else:
                return {
                    "message": "❌ Действие отменено.",
                    "keyboard": get_admin_keyboard()
                }

        # Обработка настроек rate limiting
        if state in ["edit_rate_limit_calls", "edit_rate_limit_period"]:
            if state == "edit_rate_limit_calls":
                try:
                    calls = int(message_text)
                    if not (1 <= calls <= 100):
                        raise ValueError("Неверный диапазон")

                    # Получаем текущие настройки для периода
                    rate_info = await self.settings_service.get_rate_limit_info()
                    success = await self.settings_service.update_rate_limit_settings(
                        calls, rate_info["period"], user_id
                    )

                    del self._user_states[user_id]

                    if success:
                        return {
                            "message": f"✅ Лимит запросов обновлен на {calls}",
                            "keyboard": get_rate_limit_keyboard()
                        }
                    else:
                        return {
                            "message": "❌ Ошибка обновления настройки",
                            "keyboard": get_rate_limit_keyboard()
                        }

                except ValueError:
                    from bot.keyboards import get_rate_limit_input_keyboard
                    return {
                        "message": "❌ Введите число от 1 до 100 или нажмите 'Назад' для отмены:",
                        "keyboard": get_rate_limit_input_keyboard()
                    }

            elif state == "edit_rate_limit_period":
                try:
                    period = int(message_text)
                    if not (1 <= period <= 3600):
                        raise ValueError("Неверный диапазон")

                    # Получаем текущие настройки для количества запросов
                    rate_info = await self.settings_service.get_rate_limit_info()
                    success = await self.settings_service.update_rate_limit_settings(
                        rate_info["calls"], period, user_id
                    )

                    del self._user_states[user_id]

                    if success:
                        return {
                            "message": f"✅ Период сброса обновлен на {period} секунд",
                            "keyboard": get_rate_limit_keyboard()
                        }
                    else:
                        return {
                            "message": "❌ Ошибка обновления настройки",
                            "keyboard": get_rate_limit_keyboard()
                        }

                except ValueError:
                    from bot.keyboards import get_rate_limit_input_keyboard
                    return {
                        "message": "❌ Введите число от 1 до 3600 секунд или нажмите 'Назад' для отмены:",
                        "keyboard": get_rate_limit_input_keyboard()
                    }

        # Обработка состояний админа
        if state == "waiting_user_to_manage":
            del self._user_states[user_id]
            user_info = self.user_resolver.extract_user_info_from_text(message_text)
            if not user_info or not user_info.get('user_id'):
                return {
                    "message": "❌ Не удалось распознать пользователя. Попробуйте снова или нажмите 'Админ' для возврата в главное меню.",
                    "keyboard": get_admin_keyboard()
                }

            target_user_id = user_info['user_id']
            target_user = await self.user_service.get_or_create_user(target_user_id)

            return {
                "message": f"Выбран пользователь: {target_user.display_name} (ID: {target_user_id})\n\nВыберите действие:",
                "keyboard": get_user_management_keyboard(target_user_id)
            }

        if state == "user_waiting_new_limit":
            target_user_id = state_data.get("target_user_id")
            del self._user_states[user_id]
            try:
                new_limit = int(message_text)
                if not (0 <= new_limit <= 10000):
                    raise ValueError("Invalid limit range")

                await self.user_service.set_user_limit(target_user_id, new_limit)
                return {
                    "message": f"✅ Новый лимит {new_limit} для пользователя {target_user_id} установлен.",
                    "keyboard": get_user_management_keyboard(target_user_id)
                }
            except ValueError:
                return {
                    "message": "❌ Некорректное значение. Введите число от 0 до 10000 или нажмите 'Админ' для выхода.",
                    "keyboard": get_admin_keyboard()
                }

        # Обработка настроек бота
        if state in ["edit_context_size", "edit_default_limit", "edit_welcome"]:
            # Правильный маппинг состояний к именам настроек
            setting_map = {
                "edit_context_size": "context_size",
                "edit_default_limit": "default_user_limit",
                "edit_welcome": "welcome_message"
            }

            setting_name = setting_map.get(state)

            # Валидируем значение
            is_valid, validated_value, error_msg = await self.settings_service.validate_setting_value(
                setting_name,
                message_text
            )

            if not is_valid:
                from bot.keyboards import get_settings_input_keyboard
                return {
                    "message": f"❌ {error_msg}\n\nПопробуйте еще раз или нажмите '⬅️ Назад' для отмены:",
                    "keyboard": get_settings_input_keyboard()
                }

            # Обновляем настройку
            success = False
            display_name = ""

            if state == "edit_context_size":
                success = await self.settings_service.update_context_size(validated_value, user_id)
                display_name = "Размер контекста"
            elif state == "edit_default_limit":
                success = await self.settings_service.update_default_limit(validated_value, user_id)
                display_name = "Лимит по умолчанию"
            elif state == "edit_welcome":
                success = await self.settings_service.update_welcome_message(validated_value, user_id)
                display_name = "Приветственное сообщение"

            del self._user_states[user_id]

            if success:
                return {
                    "message": f"✅ {display_name} обновлен!\n\nНовое значение: {validated_value}",
                    "keyboard": get_basic_settings_keyboard()
                }
            else:
                return {
                    "message": f"❌ Ошибка обновления настройки",
                    "keyboard": get_basic_settings_keyboard()
                }

        # Обработка белого списка
        # Пробуем извлечь информацию о пользователе из сообщения
        user_info = self.user_resolver.extract_user_info_from_text(message_text)

        if not user_info:
            # Показываем подсказку по форматам
            help_text = """❌ Не удалось найти пользователя.

    Поддерживаемые форматы:
    • ID: 123456789
    • Ссылка: https://vk.com/id123456789
    • Ссылка: https://vk.com/username
    • Username: @username или username

    Попробуйте еще раз или нажмите "⬅️ Назад" для отмены:"""

            return {
                "message": help_text,
                "keyboard": get_whitelist_management_keyboard()
            }

        target_user_id = user_info['user_id']
        user_display = self.user_resolver.format_user_display(user_info)

        if state == "waiting_user_id_add":
            success = await self.access_service.add_user_to_whitelist(target_user_id, user_id)
            del self._user_states[user_id]

            if success:
                success_text = f"""✅ Пользователь добавлен в белый список:

    👤 {user_display}

    🎯 Теперь этот пользователь может использовать бота в режиме белого списка.

    💡 Вы можете:
    • Добавить еще пользователей
    • Посмотреть полный список  
    • Вернуться к управлению доступом"""

                return {
                    "message": success_text,
                    "keyboard": get_whitelist_management_keyboard()
                }
            else:
                return {
                    "message": f"❌ Не удалось добавить пользователя (возможно, уже в списке):\n{user_display}",
                    "keyboard": get_whitelist_management_keyboard()
                }

        elif state == "waiting_user_id_remove":
            success = await self.access_service.remove_user_from_whitelist(target_user_id, user_id)
            del self._user_states[user_id]

            if success:
                success_text = f"""✅ Пользователь удален из белого списка:

    👤 {user_display}

    🎯 Теперь этот пользователь не сможет использовать бота в режиме белого списка.

    💡 Вы можете:
    • Удалить еще пользователей
    • Посмотреть актуальный список
    • Вернуться к управлению доступом"""

                return {
                    "message": success_text,
                    "keyboard": get_whitelist_management_keyboard()
                }
            else:
                return {
                    "message": f"❌ Не удалось удалить пользователя (возможно, не в списке):\n{user_display}",
                    "keyboard": get_whitelist_management_keyboard()
                }

        return None
    async def _handle_admin_commands(self, user_id: int, command: str, payload: dict = None) -> Dict[str, Any]:
        """Обработка команд админ панели"""
        from bot.keyboards import get_admin_keyboard, get_main_keyboard, get_confirmation_keyboard
        
        # Проверяем права админа
        is_admin = await self.user_service.is_admin(user_id)
        
        if not is_admin:
            return {
                "message": "❌ У вас нет прав администратора",
                "keyboard": get_main_keyboard()
            }

        if command == "manage_user":
            self._user_states[user_id] = "waiting_user_to_manage"

            from bot.keyboards import get_user_input_keyboard

            return {
                "message": "👤 Введите ID пользователя, ссылку на его страницу или screen name (например, @durov) для управления.\n\nДля отмены используйте кнопки ниже.",
                "keyboard": get_user_input_keyboard()
            }
        
        if command == "reset_all_limits_confirm":
            return {
                "message": "Вы уверены, что хотите сбросить дневные лимиты для ВСЕХ пользователей? Это действие нельзя отменить.",
                "keyboard": get_confirmation_keyboard("reset_all_limits")
            }

        if command == "confirm_reset_all_limits":
            await self.user_service.reset_all_users_requests()
            return {
                "message": "✅ Дневные лимиты сброшены для всех пользователей.",
                "keyboard": get_admin_keyboard()
            }
        
        if command == "users":
            users = await self.user_service.get_all_users()
            
            if not users:
                return {
                    "message": "👥 Пользователей пока нет",
                    "keyboard": get_admin_keyboard()
                }
            
            # Сортируем пользователей по активности
            active_users = sorted(
                [u for u in users if u.is_active], 
                key=lambda x: x.requests_used, 
                reverse=True
            )[:15]  # Показываем топ-15
            
            users_text = f"👥 Пользователи бота (топ-{len(active_users)} из {len(users)}):\n\n"
            
            for i, user in enumerate(active_users, 1):
                status_emoji = "🟢" if user.can_make_request else "🔴"
                users_text += f"{i}. {status_emoji} {user.display_name}\n"
                users_text += f"   📊 {user.requests_used}/{user.requests_limit} запросов\n"
                users_text += f"   🕐 {user.last_activity.strftime('%d.%m %H:%M')}\n"
                users_text += f"   🆔 {user.user_id}\n\n"
            
            if len(users) > 15:
                users_text += f"📝 Показано {len(active_users)} из {len(users)} пользователей"
            
            return {
                "message": users_text,
                "keyboard": get_admin_keyboard()
            }
        
        elif command == "settings":
            # Перенаправляем в меню управления настройками
            return await self._handle_settings_commands(user_id, "settings_menu")
        
        elif command == "stats":
            users = await self.user_service.get_all_users()
            access_stats = await self.access_service.get_access_stats()
            access_history = await self.access_service.get_access_history(5)
            
            # Вычисляем статистику
            total_users = len(users)
            active_users = len([u for u in users if u.is_active])
            total_requests = sum(u.requests_used for u in users)
            users_with_limits = len([u for u in users if not u.can_make_request])
            
            # Топ пользователи по активности
            top_users = sorted(users, key=lambda x: x.requests_used, reverse=True)[:3]
            
            stats_text = f"""📊 Статистика бота:

👥 Пользователи:
• Всего зарегистрировано: {total_users}
• Активных: {active_users}
• Исчерпали лимит: {users_with_limits}

📈 Использование:
• Общий объем запросов: {total_requests}
• Среднее на пользователя: {total_requests // max(total_users, 1)}

🔐 Доступ:
• Режим: {access_stats['mode']}
• В белом списке: {access_stats['whitelist_count']}
• Заблокировано: {access_stats['blacklist_count']}

🏆 Топ пользователи:"""
            
            for i, user in enumerate(top_users, 1):
                if user.requests_used > 0:
                    stats_text += f"\n{i}. {user.display_name}: {user.requests_used} запросов"
            
            if access_history:
                stats_text += "\n\n📜 Последние изменения доступа:"
                for record in access_history[:3]:
                    time_str = record['timestamp'].strftime('%d.%m %H:%M')
                    stats_text += f"\n• {time_str}: {record['action']}"
            
            return {
                "message": stats_text,
                "keyboard": get_admin_keyboard()
            }
        
        return {
            "message": "❓ Неизвестная команда",
            "keyboard": get_admin_keyboard()
        }

    async def _handle_user_management_commands(self, user_id: int, command: str, payload: dict) -> Dict[str, Any]:
        """Обработка команд управления конкретным пользователем"""
        from bot.keyboards import get_user_management_keyboard, get_admin_keyboard

        target_user_id = payload.get("target_user_id")
        if not target_user_id:
            return {"message": "Ошибка: не найден ID целевого пользователя.", "keyboard": get_admin_keyboard()}

        if command == "user_show_stats":
            stats = await self.user_service.get_user_stats(target_user_id)
            if not stats:
                return {"message": f"Не удалось получить статистику для пользователя {target_user_id}.", "keyboard": get_admin_keyboard()}

            status_text = f"""📊 Статистика для {stats['display_name']} (ID: {target_user_id}):

📈 Запросы (на день):
• Использовано: {stats['requests_used']}/{stats['requests_limit']}
• Осталось: {stats['requests_remaining']}

💬 Контекст: {stats['context_messages']} сообщений

📅 Активность:
• Регистрация: {stats['created_at'].strftime('%d.%m.%Y %H:%M')}
• Последняя активность: {stats['last_activity'].strftime('%d.%m.%Y %H:%M')}"""
            return {"message": status_text, "keyboard": get_user_management_keyboard(target_user_id)}

        elif command == "user_reset_limit":
            await self.user_service.reset_user_requests(target_user_id)
            return {
                "message": f"✅ Дневной лимит для пользователя {target_user_id} сброшен.",
                "keyboard": get_user_management_keyboard(target_user_id)
            }

        elif command == "user_set_limit":
            self._user_states[user_id] = {"state": "user_waiting_new_limit", "target_user_id": target_user_id}

            from bot.keyboards import get_user_input_keyboard
            return {
                "message": f"Введите новый дневной лимит для пользователя {target_user_id} (число от 0 до 10000).\n\nДля отмены используйте кнопки ниже.",
                "keyboard": get_user_input_keyboard()
            }

        return {"message": "Неизвестная команда.", "keyboard": get_admin_keyboard()}
    
    def _get_user_info(self, user_id: int) -> Dict[str, Any]:
        """Получение информации о пользователе из VK API"""
        try:
            users = self.vk.users.get(
                user_ids=user_id, 
                fields='first_name,last_name,screen_name'
            )
            if users:
                user = users[0]
                return {
                    'first_name': user.get('first_name', ''),
                    'last_name': user.get('last_name', ''),
                    'screen_name': user.get('screen_name', ''),
                    'user_id': user_id
                }
        except Exception as e:
            logger.error(f"❌ Ошибка получения информации о пользователе {user_id}: {e}")
        
        return {
            'first_name': '',
            'last_name': '',
            'screen_name': '',
            'user_id': user_id
        }
    
    def _send_message(self, user_id: int, message: str, keyboard: str = None, attachment: str = None):
        """Отправка сообщения пользователю"""
        try:
            params = {
                'user_id': user_id,
                'message': message,
                'random_id': get_random_id()
            }
            
            if keyboard:
                params['keyboard'] = keyboard
            
            if attachment:
                params['attachment'] = attachment
                logger.info(f"📎 Отправляю сообщение с вложением: {attachment}")
            
            self.vk.messages.send(**params)
            logger.info(f"✅ Сообщение отправлено пользователю {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки сообщения пользователю {user_id}: {e}")
            
            # Попытаемся отправить без вложения если была ошибка
            if attachment:
                try:
                    params_without_attachment = {
                        'user_id': user_id,
                        'message': message,
                        'random_id': get_random_id()
                    }
                    if keyboard:
                        params_without_attachment['keyboard'] = keyboard
                    
                    self.vk.messages.send(**params_without_attachment)
                    logger.info(f"✅ Сообщение отправлено без вложения пользователю {user_id}")
                except Exception as e2:
                    logger.error(f"❌ Ошибка отправки сообщения без вложения: {e2}")


async def main():
    """Асинхронная главная функция"""
    try:
        # Инициализация БД
        await init_db()

        # Валидация настроек
        settings.validate()
        
        # Создание и запуск бота
        bot = VKBot()
        await bot.start()
        
    except ValueError as e:
        logger.error(f"❌ Ошибка конфигурации: {e}")
        print(f"\n❌ Ошибка конфигурации: {e}")
        print("📝 Проверьте файл .env и убедитесь, что все необходимые переменные установлены.")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        print(f"\n❌ Критическая ошибка: {e}")


if __name__ == "__main__":
    asyncio.run(main())