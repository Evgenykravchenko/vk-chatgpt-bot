"""
Сервис для работы с пользователями
"""
from datetime import datetime
from typing import Optional, List

from repositories.base import BaseUserRepository, BaseContextRepository
from repositories.models import UserProfile, UserContext, MessageRole
from config.settings import settings


class UserService:
    """Сервис для работы с пользователями"""

    def __init__(
            self,
            user_repo: BaseUserRepository,
            context_repo: BaseContextRepository
    ):
        self.user_repo = user_repo
        self.context_repo = context_repo

    async def get_or_create_user(
            self,
            user_id: int,
            username: Optional[str] = None,
            first_name: Optional[str] = None,
            last_name: Optional[str] = None
    ) -> UserProfile:
        """
        Получить пользователя или создать нового

        Args:
            user_id: ID пользователя VK
            username: Имя пользователя (screen_name)
            first_name: Имя
            last_name: Фамилия

        Returns:
            Профиль пользователя
        """
        user = await self.user_repo.get_user(user_id)

        if user is None:
            # Создаем нового пользователя
            user = UserProfile(
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                requests_limit=settings.default_user_limit,
                requests_used=0
            )
            user = await self.user_repo.create_user(user)
        else:
            # Обновляем информацию о пользователе если изменилась
            updated = False
            if username and user.username != username:
                user.username = username
                updated = True
            if first_name and user.first_name != first_name:
                user.first_name = first_name
                updated = True
            if last_name and user.last_name != last_name:
                user.last_name = last_name
                updated = True

            if updated:
                user = await self.user_repo.update_user(user)

        return user

    async def can_make_request(self, user_id: int) -> bool:
        """
        Проверить может ли пользователь сделать запрос

        Args:
            user_id: ID пользователя

        Returns:
            True если может, False в противном случае
        """
        user = await self.user_repo.get_user(user_id)
        return user is not None and user.can_make_request

    async def use_request(self, user_id: int) -> int:
        """
        Использовать один запрос пользователя

        Args:
            user_id: ID пользователя

        Returns:
            Количество использованных запросов
        """
        return await self.user_repo.increment_user_requests(user_id)

    async def get_user_stats(self, user_id: int) -> Optional[dict]:
        """
        Получить статистику пользователя

        Args:
            user_id: ID пользователя

        Returns:
            Словарь со статистикой или None
        """
        user = await self.user_repo.get_user(user_id)
        if user is None:
            return None

        context = await self.context_repo.get_context(user_id)

        return {
            "user_id": user.user_id,
            "display_name": user.display_name,
            "requests_used": user.requests_used,
            "requests_limit": user.requests_limit,
            "requests_remaining": user.requests_remaining,
            "context_messages": context.message_count if context else 0,
            "created_at": user.created_at,
            "last_activity": user.last_activity,
            "is_active": user.is_active
        }

    async def reset_user_requests(self, user_id: int) -> None:
        """
        Сбросить счетчик запросов пользователя

        Args:
            user_id: ID пользователя
        """
        await self.user_repo.reset_user_requests(user_id)

    async def reset_all_users_requests(self) -> None:
        """Сбросить счетчик запросов для всех пользователей"""
        all_users = await self.user_repo.get_all_users()
        for user in all_users:
            await self.user_repo.reset_user_requests(user.user_id)

    async def set_user_limit(self, user_id: int, limit: int) -> None:
        """
        Установить лимит запросов для пользователя

        Args:
            user_id: ID пользователя
            limit: Новый лимит
        """
        await self.user_repo.set_user_limit(user_id, limit)

    async def get_all_users(self) -> List[UserProfile]:
        """
        Получить всех пользователей (только для админов)

        Returns:
            Список всех пользователей
        """
        return await self.user_repo.get_all_users()

    async def add_message_to_context(
            self,
            user_id: int,
            role: MessageRole,
            content: str
    ) -> None:
        """
        Добавить сообщение в контекст пользователя

        Args:
            user_id: ID пользователя
            role: Роль сообщения
            content: Содержимое сообщения
        """
        context = await self.context_repo.get_context(user_id)
        if context is None:
            context = UserContext(user_id=user_id, max_messages=settings.context_size)

        context.add_message(role, content)
        await self.context_repo.save_context(context)

    async def get_user_context(self, user_id: int) -> Optional[UserContext]:
        """
        Получить контекст пользователя

        Args:
            user_id: ID пользователя

        Returns:
            Контекст пользователя или None
        """
        return await self.context_repo.get_context(user_id)

    async def clear_user_context(self, user_id: int) -> None:
        """
        Очистить контекст пользователя

        Args:
            user_id: ID пользователя
        """
        await self.context_repo.clear_context(user_id)

    async def is_admin(self, user_id: int) -> bool:
        """
        Проверить является ли пользователь администратором

        Args:
            user_id: ID пользователя

        Returns:
            True если администратор, False в противном случае
        """
        return settings.admin_user_id is not None and user_id == settings.admin_user_id
