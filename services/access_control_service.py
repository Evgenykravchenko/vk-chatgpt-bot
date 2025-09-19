"""
Сервис управления доступом к боту
"""
from typing import List, Dict, Any
from datetime import datetime

from repositories.base import BaseAccessControlRepository
from repositories.models import AccessControl
from config.settings import settings


class AccessControlService:
    """Сервис для управления доступом к боту"""

    def __init__(self, access_repo: BaseAccessControlRepository):
        self.access_repo = access_repo
        self._access_control = None  # Кэш

    async def _get_access_control(self) -> AccessControl:
        """Получить настройки доступа (с кэшированием)"""
        if self._access_control is None:
            self._access_control = await self.access_repo.get_access_control()
            if self._access_control is None:
                # Создаем настройки по умолчанию
                self._access_control = AccessControl()
                await self.access_repo.save_access_control(self._access_control)
        return self._access_control

    async def _save_access_control(self, access_control: AccessControl) -> None:
        """Сохранить настройки доступа"""
        self._access_control = access_control
        await self.access_repo.save_access_control(access_control)

    async def check_user_access(self, user_id: int) -> bool:
        """
        Проверить имеет ли пользователь доступ к боту

        Args:
            user_id: ID пользователя

        Returns:
            True если доступ разрешен, False если запрещен
        """
        access_control = await self._get_access_control()
        return access_control.is_user_allowed(user_id, settings.admin_user_id)

    async def get_access_mode(self) -> str:
        """Получить текущий режим доступа"""
        access_control = await self._get_access_control()
        return access_control.mode

    async def set_access_mode(self, mode: str, admin_id: int) -> bool:
        """
        Установить режим доступа

        Args:
            mode: Режим доступа ("public", "whitelist", "admin_only")
            admin_id: ID администратора

        Returns:
            True если режим изменен, False если ошибка
        """
        if mode not in ["public", "whitelist", "admin_only"]:
            return False

        if not self._is_admin(admin_id):
            return False

        access_control = await self._get_access_control()
        old_mode = access_control.mode
        access_control.mode = mode

        await self._save_access_control(access_control)

        # Записываем в историю
        await self._add_to_history(f"Режим доступа изменен с {old_mode} на {mode}", admin_id)

        return True

    async def _add_to_history(self, action: str, admin_id: int) -> None:
        """Добавить запись в историю"""
        record = {
            "timestamp": datetime.now(),
            "action": action,
            "admin_id": admin_id
        }
        await self.access_repo.add_access_history_record(record)

    async def add_user_to_whitelist(self, user_id: int, admin_id: int) -> bool:
        """
        Добавить пользователя в белый список

        Args:
            user_id: ID пользователя
            admin_id: ID администратора

        Returns:
            True если пользователь добавлен
        """
        if not self._is_admin(admin_id):
            return False

        access_control = await self._get_access_control()

        if user_id in access_control.whitelist:
            return False  # Уже в списке

        access_control.add_to_whitelist(user_id)
        await self._save_access_control(access_control)
        await self._add_to_history(f"Пользователь {user_id} добавлен в белый список", admin_id)

        return True

    async def remove_user_from_whitelist(self, user_id: int, admin_id: int) -> bool:
        """
        Удалить пользователя из белого списка

        Args:
            user_id: ID пользователя
            admin_id: ID администратора

        Returns:
            True если пользователь удален
        """
        if not self._is_admin(admin_id):
            return False

        access_control = await self._get_access_control()

        if user_id not in access_control.whitelist:
            return False  # Не в списке

        access_control.remove_from_whitelist(user_id)
        await self._save_access_control(access_control)
        await self._add_to_history(f"Пользователь {user_id} удален из белого списка", admin_id)

        return True

    async def add_user_to_blacklist(self, user_id: int, admin_id: int) -> bool:
        """
        Заблокировать пользователя

        Args:
            user_id: ID пользователя
            admin_id: ID администратора

        Returns:
            True если пользователь заблокирован
        """
        if not self._is_admin(admin_id):
            return False

        if user_id == admin_id:
            return False  # Нельзя заблокировать админа

        access_control = await self._get_access_control()
        access_control.add_to_blacklist(user_id)
        await self._save_access_control(access_control)
        await self._add_to_history(f"Пользователь {user_id} заблокирован", admin_id)

        return True

    async def remove_user_from_blacklist(self, user_id: int, admin_id: int) -> bool:
        """
        Разблокировать пользователя

        Args:
            user_id: ID пользователя
            admin_id: ID администратора

        Returns:
            True если пользователь разблокирован
        """
        if not self._is_admin(admin_id):
            return False

        access_control = await self._get_access_control()
        access_control.remove_from_blacklist(user_id)
        await self._save_access_control(access_control)
        await self._add_to_history(f"Пользователь {user_id} разблокирован", admin_id)

        return True

    async def get_whitelist(self) -> List[int]:
        """Получить белый список пользователей"""
        access_control = await self._get_access_control()
        return access_control.whitelist.copy()

    async def get_blacklist(self) -> List[int]:
        """Получить черный список пользователей"""
        access_control = await self._get_access_control()
        return access_control.blacklist.copy()

    async def get_access_stats(self) -> Dict[str, Any]:
        """
        Получить статистику доступа

        Returns:
            Словарь со статистикой
        """
        access_control = await self._get_access_control()
        history = await self.access_repo.get_access_history(10)

        return {
            "mode": access_control.mode,
            "whitelist_count": len(access_control.whitelist),
            "blacklist_count": len(access_control.blacklist),
            "whitelist_users": access_control.whitelist,
            "blacklist_users": access_control.blacklist,
            "history_count": len(history)
        }

    async def get_access_info_text(self) -> str:
        """
        Получить текстовую информацию о настройках доступа

        Returns:
            Форматированная строка с информацией
        """
        mode_names = {
            "public": "🌐 Открытый (для всех)",
            "whitelist": "📋 Белый список",
            "admin_only": "👤 Только администратор"
        }

        stats = await self.get_access_stats()

        text = f"""🔐 Настройки доступа:

🎯 Режим: {mode_names.get(stats['mode'], stats['mode'])}

📊 Статистика:
• Пользователей в белом списке: {stats['whitelist_count']}
• Заблокированных пользователей: {stats['blacklist_count']}
• Изменений в истории: {stats['history_count']}"""

        if stats['mode'] == 'whitelist' and stats['whitelist_count'] > 0:
            text += "\n\n📋 Белый список:\n"
            for user_id in stats['whitelist_users'][:10]:  # Показываем первых 10
                text += f"• {user_id}\n"

            if stats['whitelist_count'] > 10:
                text += f"• ... и еще {stats['whitelist_count'] - 10}\n"

        return text

    async def get_access_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Получить историю изменений доступа

        Args:
            limit: Количество записей

        Returns:
            Список записей истории
        """
        return await self.access_repo.get_access_history(limit)

    def _is_admin(self, user_id: int) -> bool:
        """Проверить является ли пользователь администратором"""
        return settings.admin_user_id is not None and user_id == settings.admin_user_id

    async def get_access_denied_message(self, user_id: int) -> str:
        """
        Получить сообщение об отказе в доступе

        Args:
            user_id: ID пользователя

        Returns:
            Сообщение об отказе в доступе
        """
        access_control = await self._get_access_control()
        return access_control.get_access_denied_message(user_id, settings.admin_user_id)

    async def update_access_messages(
        self,
        admin_id: int,
        whitelist_msg: str = None,
        admin_only_msg: str = None,
        blocked_msg: str = None
    ) -> bool:
        """
        Обновить сообщения об ограничении доступа

        Args:
            admin_id: ID администратора
            whitelist_msg: Сообщение для режима белого списка
            admin_only_msg: Сообщение для режима "только админ"
            blocked_msg: Сообщение для заблокированных пользователей

        Returns:
            True если сообщения обновлены
        """
        if not self._is_admin(admin_id):
            return False

        access_control = await self._get_access_control()

        if whitelist_msg:
            access_control.whitelist_message = whitelist_msg
        if admin_only_msg:
            access_control.admin_only_message = admin_only_msg
        if blocked_msg:
            access_control.blocked_message = blocked_msg

        await self._save_access_control(access_control)
        await self._add_to_history("Сообщения об ограничении доступа обновлены", admin_id)

        return True
