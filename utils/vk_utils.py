"""
Утилиты для работы с VK API и ссылками
"""
import re
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class VKUserResolver:
    """Класс для разрешения VK ссылок в ID пользователей"""

    def __init__(self, vk_api):
        self.vk = vk_api

    def extract_user_info_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Извлекает информацию о пользователе из текста (ID, ссылка или username)

        Args:
            text: Текст с ID, ссылкой или username

        Returns:
            Словарь с информацией о пользователе или None
        """
        # Очищаем текст
        text = text.strip()

        # Паттерны для поиска VK ссылок и ID
        patterns = [
            # Прямой ID
            r'^(\d+)$',
            # vk.com/id123456
            r'(?:https?://)?(?:www\.)?vk\.com/id(\d+)',
            # vk.com/username
            r'(?:https?://)?(?:www\.)?vk\.com/([a-zA-Z][a-zA-Z0-9_\.]{2,})',
            # m.vk.com/id123456
            r'(?:https?://)?(?:www\.)?m\.vk\.com/id(\d+)',
            # m.vk.com/username
            r'(?:https?://)?(?:www\.)?m\.vk\.com/([a-zA-Z][a-zA-Z0-9_\.]{2,})',
            # Без протокола: vk.com/username
            r'^vk\.com/([a-zA-Z][a-zA-Z0-9_\.]{2,})$',
            # Без протокола: vk.com/id123456
            r'^vk\.com/id(\d+)$',
            # Только username без vk.com
            r'^@?([a-zA-Z][a-zA-Z0-9_\.]{2,})$',
        ]

        user_identifier = None
        is_numeric_id = False

        # Пробуем найти совпадение
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                user_identifier = match.group(1)
                # Проверяем, является ли это числовым ID
                if user_identifier.isdigit():
                    is_numeric_id = True
                break

        if not user_identifier:
            return None

        try:
            # Если это уже числовой ID, просто возвращаем его
            if is_numeric_id:
                user_id = int(user_identifier)
                user_info = self._get_user_info_by_id(user_id)
                if user_info:
                    return {
                        'user_id': user_id,
                        'first_name': user_info.get('first_name', ''),
                        'last_name': user_info.get('last_name', ''),
                        'screen_name': user_info.get('screen_name', ''),
                        'source': f'ID: {user_id}'
                    }
            else:
                # Это username, нужно резолвить через API
                user_info = self._resolve_username(user_identifier)
                if user_info:
                    return {
                        'user_id': user_info['id'],
                        'first_name': user_info.get('first_name', ''),
                        'last_name': user_info.get('last_name', ''),
                        'screen_name': user_info.get('screen_name', ''),
                        'source': f'Username: {user_identifier}'
                    }

        except Exception as e:
            logger.error(f"Ошибка разрешения пользователя '{user_identifier}': {e}")

        return None

    def _get_user_info_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить информацию о пользователе по ID"""
        try:
            users = self.vk.users.get(
                user_ids=user_id,
                fields='first_name,last_name,screen_name'
            )
            if users and len(users) > 0:
                return users[0]
        except Exception as e:
            logger.error(f"Ошибка получения пользователя по ID {user_id}: {e}")

        return None

    def _resolve_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Разрешить username в информацию о пользователе"""
        try:
            # Используем utils.resolveScreenName для разрешения username
            result = self.vk.utils.resolveScreenName(screen_name=username)

            if result and result.get('type') == 'user':
                user_id = result.get('object_id')
                if user_id:
                    return self._get_user_info_by_id(user_id)

        except Exception as e:
            logger.error(f"Ошибка разрешения username '{username}': {e}")

            # Fallback: пробуем напрямую через users.get
            try:
                users = self.vk.users.get(
                    user_ids=username,
                    fields='first_name,last_name,screen_name'
                )
                if users and len(users) > 0:
                    return users[0]
            except Exception as e2:
                logger.error(f"Fallback ошибка для username '{username}': {e2}")

        return None

    def format_user_display(self, user_info: Dict[str, Any]) -> str:
        """Форматирует информацию о пользователе для отображения"""
        user_id = user_info['user_id']
        first_name = user_info.get('first_name', '')
        last_name = user_info.get('last_name', '')
        screen_name = user_info.get('screen_name', '')

        # Формируем отображаемое имя
        display_parts = []
        if first_name or last_name:
            name = f"{first_name} {last_name}".strip()
            if name:
                display_parts.append(name)

        if screen_name:
            display_parts.append(f"@{screen_name}")

        display_parts.append(f"ID: {user_id}")

        return " | ".join(display_parts)


def extract_vk_links_from_text(text: str) -> list:
    """
    Извлекает все VK ссылки из текста

    Args:
        text: Текст для поиска ссылок

    Returns:
        Список найденных ссылок
    """
    patterns = [
        r'https?://(?:www\.)?vk\.com/[a-zA-Z0-9_.]+',
        r'https?://(?:www\.)?m\.vk\.com/[a-zA-Z0-9_.]+',
        r'vk\.com/[a-zA-Z0-9_.]+'
    ]

    links = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        links.extend(matches)

    return links


def validate_vk_user_input(text: str) -> Dict[str, Any]:
    """
    Валидирует ввод пользователя для поиска VK аккаунтов

    Args:
        text: Ввод пользователя

    Returns:
        Словарь с результатом валидации
    """
    text = text.strip()

    result = {
        'is_valid': False,
        'input_type': None,
        'value': None,
        'error': None
    }

    # Проверяем на числовой ID
    if text.isdigit():
        user_id = int(text)
        if 1 <= user_id <= 999999999:  # Примерные лимиты VK ID
            result.update({
                'is_valid': True,
                'input_type': 'user_id',
                'value': user_id
            })
        else:
            result['error'] = "ID пользователя должен быть от 1 до 999999999"
        return result

    # Проверяем на VK ссылку
    vk_patterns = [
        r'(?:https?://)?(?:www\.)?vk\.com/(.+)',
        r'(?:https?://)?(?:www\.)?m\.vk\.com/(.+)'
    ]

    for pattern in vk_patterns:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            identifier = match.group(1)
            if identifier.startswith('id') and identifier[2:].isdigit():
                result.update({
                    'is_valid': True,
                    'input_type': 'user_id_link',
                    'value': int(identifier[2:])
                })
            elif re.match(r'^[a-zA-Z][a-zA-Z0-9_\.]{1,}$', identifier):
                result.update({
                    'is_valid': True,
                    'input_type': 'username_link',
                    'value': identifier
                })
            else:
                result['error'] = "Некорректная VK ссылка"
            return result

    # Проверяем на username
    if re.match(r'^@?[a-zA-Z][a-zA-Z0-9_\.]{1,}$', text):
        username = text.lstrip('@')
        result.update({
            'is_valid': True,
            'input_type': 'username',
            'value': username
        })
        return result

    result['error'] = "Неопознанный формат. Используйте ID, ссылку VK или username"
    return result
