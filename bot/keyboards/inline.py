"""
Клавиатуры для VK бота
"""
import json
from typing import Dict, Any


class VKKeyboard:
    """Класс для создания клавиатур VK"""

    def __init__(self, one_time: bool = False, inline: bool = False):
        self.keyboard = {
            "one_time": one_time,
            "inline": inline,
            "buttons": []
        }
        self.current_row = []

    def add_button(self, text: str, color: str = "secondary", payload: Dict[str, Any] = None) -> "VKKeyboard":
        """
        Добавить кнопку в текущий ряд

        Args:
            text: Текст кнопки
            color: Цвет кнопки (primary, secondary, negative, positive)
            payload: Дополнительные данные
        """
        button = {
            "action": {
                "type": "text",
                "label": text,
                "payload": json.dumps(payload or {})
            },
            "color": color
        }
        self.current_row.append(button)
        return self

    def add_row(self) -> "VKKeyboard":
        """Добавить новый ряд кнопок"""
        if self.current_row:
            self.keyboard["buttons"].append(self.current_row)
            self.current_row = []
        return self

    def get_keyboard(self) -> str:
        """Получить JSON клавиатуры"""
        if self.current_row:
            self.keyboard["buttons"].append(self.current_row)
            self.current_row = []
        return json.dumps(self.keyboard, ensure_ascii=False)


def get_main_keyboard() -> str:
    """Главная клавиатура"""
    keyboard = VKKeyboard(one_time=False)

    keyboard.add_button("💬 Спросить AI", "primary", {"command": "ask"})
    keyboard.add_button("📊 Статус", "secondary", {"command": "status"})
    keyboard.add_row()

    keyboard.add_button("🗑️ Сброс", "negative", {"command": "reset"})
    keyboard.add_button("❓ Помощь", "secondary", {"command": "help"})
    keyboard.add_row()

    return keyboard.get_keyboard()


def get_help_keyboard() -> str:
    """Клавиатура помощи"""
    keyboard = VKKeyboard(one_time=False)

    keyboard.add_button("📋 Команды", "secondary", {"command": "commands"})
    keyboard.add_button("ℹ️ О боте", "secondary", {"command": "about"})
    keyboard.add_row()

    keyboard.add_button("🏠 Главная", "primary", {"command": "main"})
    keyboard.add_row()

    return keyboard.get_keyboard()


def get_status_keyboard() -> str:
    """Клавиатура статуса"""
    keyboard = VKKeyboard(one_time=False)

    keyboard.add_button("🔄 Обновить", "secondary", {"command": "status"})
    keyboard.add_button("🗑️ Сброс контекста", "negative", {"command": "reset"})
    keyboard.add_row()

    keyboard.add_button("🏠 Главная", "primary", {"command": "main"})
    keyboard.add_row()

    return keyboard.get_keyboard()


def get_admin_keyboard() -> str:
    """Административная клавиатура"""
    keyboard = VKKeyboard(one_time=False)

    keyboard.add_button("👥 Пользователи", "secondary", {"command": "users"})
    keyboard.add_button("⚙️ Настройки", "secondary", {"command": "settings"})
    keyboard.add_row()

    keyboard.add_button("🔐 Доступ", "secondary", {"command": "access_control"})
    keyboard.add_button("👤 Упр. пользователем", "secondary", {"command": "manage_user"})
    keyboard.add_row()

    keyboard.add_button("🔄 Сбросить лимиты", "negative", {"command": "reset_all_limits_confirm"})
    keyboard.add_button("📊 Статистика", "secondary", {"command": "stats"})
    keyboard.add_row()

    keyboard.add_button("🏠 Главная", "primary", {"command": "main"})
    keyboard.add_row()

    return keyboard.get_keyboard()

def get_user_management_keyboard(user_id: int) -> str:
    """Клавиатура управления конкретным пользователем"""
    keyboard = VKKeyboard(one_time=False)

    keyboard.add_button("🎯 Изменить лимит", "primary", {"command": "user_set_limit", "target_user_id": user_id})
    keyboard.add_button("🔄 Сбросить лимит", "negative", {"command": "user_reset_limit", "target_user_id": user_id})
    keyboard.add_row()

    keyboard.add_button("📊 Статистика", "secondary", {"command": "user_show_stats", "target_user_id": user_id})
    keyboard.add_row()

    keyboard.add_button("⬅️ Назад", "secondary", {"command": "admin"})
    keyboard.add_row()

    return keyboard.get_keyboard()


def get_access_control_keyboard() -> str:
    """Клавиатура управления доступом"""
    keyboard = VKKeyboard(one_time=False)

    keyboard.add_button("🎯 Режим доступа", "secondary", {"command": "access_mode"})
    keyboard.add_button("📋 Белый список", "secondary", {"command": "whitelist"})
    keyboard.add_row()

    keyboard.add_button("🚫 Черный список", "negative", {"command": "blacklist"})
    keyboard.add_button("📈 Статистика", "secondary", {"command": "access_stats"})
    keyboard.add_row()

    keyboard.add_button("💬 Сообщения", "secondary", {"command": "access_messages"})
    keyboard.add_button("⬅️ Назад", "primary", {"command": "admin"})
    keyboard.add_row()

    return keyboard.get_keyboard()


def get_access_messages_keyboard() -> str:
    """Клавиатура управления сообщениями доступа"""
    keyboard = VKKeyboard(one_time=False)

    keyboard.add_button("📋 Бета-тест", "secondary", {"command": "edit_whitelist_msg"})
    keyboard.add_button("🔧 Тех. работы", "secondary", {"command": "edit_admin_msg"})
    keyboard.add_row()

    keyboard.add_button("🚫 Блокировка", "negative", {"command": "edit_blocked_msg"})
    keyboard.add_button("📖 Просмотр", "secondary", {"command": "view_messages"})
    keyboard.add_row()

    keyboard.add_button("⬅️ Назад", "primary", {"command": "access_control"})
    keyboard.add_row()

    return keyboard.get_keyboard()


def get_access_mode_keyboard() -> str:
    """Клавиатура выбора режима доступа"""
    keyboard = VKKeyboard(one_time=False)

    keyboard.add_button("🌐 Открытый", "positive", {"command": "set_mode_public"})
    keyboard.add_row()

    keyboard.add_button("📋 Белый список", "secondary", {"command": "set_mode_whitelist"})
    keyboard.add_row()

    keyboard.add_button("👤 Только админ", "negative", {"command": "set_mode_admin"})
    keyboard.add_row()

    keyboard.add_button("⬅️ Назад", "primary", {"command": "access_control"})
    keyboard.add_row()

    return keyboard.get_keyboard()


def get_whitelist_management_keyboard() -> str:
    """Клавиатура управления белым списком"""
    keyboard = VKKeyboard(one_time=False)

    keyboard.add_button("➕ Добавить", "positive", {"command": "whitelist_add"})
    keyboard.add_button("➖ Удалить", "negative", {"command": "whitelist_remove"})
    keyboard.add_row()

    keyboard.add_button("📋 Показать список", "secondary", {"command": "whitelist_show"})
    keyboard.add_row()

    keyboard.add_button("⬅️ Назад", "primary", {"command": "access_control"})
    keyboard.add_row()

    return keyboard.get_keyboard()


def get_cancel_keyboard() -> str:
    """Клавиатура только с отменой"""
    keyboard = VKKeyboard(one_time=False)

    keyboard.add_button("❌ Отмена", "negative", {"command": "whitelist"})
    keyboard.add_row()

    return keyboard.get_keyboard()


def get_settings_management_keyboard() -> str:
    """Клавиатура управления настройками"""
    keyboard = VKKeyboard(one_time=False)

    keyboard.add_button("🤖 Основные", "secondary", {"command": "settings_basic"})
    keyboard.add_button("⚡ Система", "secondary", {"command": "settings_system"})
    keyboard.add_row()

    keyboard.add_button("🔄 Сброс", "negative", {"command": "settings_reset"})
    keyboard.add_button("📖 Просмотр", "secondary", {"command": "settings_view"})
    keyboard.add_row()

    keyboard.add_button("⬅️ Назад", "primary", {"command": "admin"})
    keyboard.add_row()

    return keyboard.get_keyboard()


def get_basic_settings_keyboard() -> str:
    """Клавиатура основных настроек"""
    keyboard = VKKeyboard(one_time=False)

    keyboard.add_button("💭 Контекст", "secondary", {"command": "edit_context_size"})
    keyboard.add_button("🎯 Лимиты", "secondary", {"command": "edit_default_limit"})
    keyboard.add_row()

    keyboard.add_button("🧠 Модель AI", "secondary", {"command": "edit_ai_model"})
    keyboard.add_button("💬 Приветствие", "secondary", {"command": "edit_welcome"})
    keyboard.add_row()

    keyboard.add_button("⬅️ Назад", "primary", {"command": "settings_menu"})
    keyboard.add_row()

    return keyboard.get_keyboard()


def get_system_settings_keyboard() -> str:
    """Клавиатура системных настроек"""
    keyboard = VKKeyboard(one_time=False)

    keyboard.add_button("⏱️ Rate Limit", "secondary", {"command": "toggle_rate_limit"})
    keyboard.add_button("🔧 Обслуживание", "secondary", {"command": "toggle_maintenance"})
    keyboard.add_row()

    keyboard.add_button("⬅️ Назад", "primary", {"command": "settings_menu"})
    keyboard.add_row()

    return keyboard.get_keyboard()


def get_ai_model_keyboard() -> str:
    """Клавиатура выбора AI модели"""
    keyboard = VKKeyboard(one_time=False)

    keyboard.add_button("🚀 GPT-4", "secondary", {"command": "set_model_gpt4"})
    keyboard.add_button("⚡ GPT-3.5", "secondary", {"command": "set_model_gpt35"})
    keyboard.add_row()

    keyboard.add_button("🧪 GPT-4-turbo", "secondary", {"command": "set_model_gpt4_turbo"})
    keyboard.add_row()

    keyboard.add_button("⬅️ Назад", "primary", {"command": "settings_basic"})
    keyboard.add_row()

    return keyboard.get_keyboard()


def get_confirmation_keyboard(action: str) -> str:
    """Клавиатура подтверждения действия"""
    keyboard = VKKeyboard(one_time=True)

    keyboard.add_button("✅ Да", "positive", {"command": f"confirm_{action}"})
    keyboard.add_button("❌ Нет", "negative", {"command": "cancel"})
    keyboard.add_row()

    return keyboard.get_keyboard()


def remove_keyboard() -> str:
    """Убрать клавиатуру"""
    keyboard = {
        "buttons": [],
        "one_time": True
    }
    return json.dumps(keyboard, ensure_ascii=False)


# Добавьте эти новые функции в bot/keyboards/inline.py:

def get_input_cancel_keyboard(return_command: str = "admin") -> str:
    """Клавиатура для отмены ввода с возвратом в определенное меню"""
    keyboard = VKKeyboard(one_time=False)

    keyboard.add_button("❌ Отмена", "negative", {"command": return_command})
    keyboard.add_row()

    return keyboard.get_keyboard()


def get_settings_input_keyboard() -> str:
    """Клавиатура для ввода настроек с отменой"""
    keyboard = VKKeyboard(one_time=False)

    keyboard.add_button("⬅️ Назад", "secondary", {"command": "settings_basic"})
    keyboard.add_button("❌ Отмена", "negative", {"command": "admin"})
    keyboard.add_row()

    return keyboard.get_keyboard()


def get_whitelist_input_keyboard() -> str:
    """Клавиатура для ввода в белый список с отменой"""
    keyboard = VKKeyboard(one_time=False)

    keyboard.add_button("⬅️ Назад", "secondary", {"command": "whitelist"})
    keyboard.add_button("❌ Отмена", "negative", {"command": "access_control"})
    keyboard.add_row()

    return keyboard.get_keyboard()


def get_user_input_keyboard() -> str:
    """Клавиатура для ввода пользователя с отменой"""
    keyboard = VKKeyboard(one_time=False)

    keyboard.add_button("⬅️ Назад", "secondary", {"command": "admin"})
    keyboard.add_button("❌ Отмена", "negative", {"command": "admin"})
    keyboard.add_row()

    return keyboard.get_keyboard()





def get_rate_limit_keyboard() -> str:
    """Клавиатура управления Rate Limiting"""
    keyboard = VKKeyboard(one_time=False)

    keyboard.add_button("🔢 Изменить лимит", "secondary", {"command": "edit_rate_limit_calls"})
    keyboard.add_button("⏱️ Изменить период", "secondary", {"command": "edit_rate_limit_period"})
    keyboard.add_row()

    keyboard.add_button("📊 Подробная информация", "secondary", {"command": "show_rate_limit_info"})
    keyboard.add_row()

    keyboard.add_button("🔄 Включить/Отключить", "secondary", {"command": "toggle_rate_limit"})
    keyboard.add_row()

    keyboard.add_button("⬅️ Назад", "primary", {"command": "settings_system"})
    keyboard.add_row()

    return keyboard.get_keyboard()


def get_system_settings_keyboard() -> str:
    """Клавиатура системных настроек (обновленная)"""
    keyboard = VKKeyboard(one_time=False)

    keyboard.add_button("⏱️ Rate Limiting", "secondary", {"command": "rate_limit_menu"})
    keyboard.add_button("🔧 Обслуживание", "secondary", {"command": "toggle_maintenance"})
    keyboard.add_row()

    keyboard.add_button("⬅️ Назад", "primary", {"command": "settings_menu"})
    keyboard.add_row()

    return keyboard.get_keyboard()


def get_rate_limit_input_keyboard() -> str:
    """Клавиатура для ввода настроек rate limiting"""
    keyboard = VKKeyboard(one_time=False)

    keyboard.add_button("⬅️ Назад", "secondary", {"command": "rate_limit_menu"})
    keyboard.add_button("❌ Отмена", "negative", {"command": "settings_system"})
    keyboard.add_row()

    return keyboard.get_keyboard()
