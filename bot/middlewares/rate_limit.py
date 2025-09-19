"""
Middleware для ограничения частоты запросов
"""
import time
import logging
from typing import Dict
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    """Middleware для ограничения частоты запросов с поддержкой динамических настроек"""

    def __init__(self, settings_service=None):
        # Словарь для хранения времени запросов пользователей
        self.user_requests: Dict[int, deque] = defaultdict(lambda: deque())
        self.settings_service = settings_service

        # Кэшируем настройки для производительности
        self._cached_settings = None
        self._cache_time = 0
        self._cache_duration = 30  # Кэшируем на 30 секунд

        # Статистика для мониторинга
        self._total_blocked_requests = 0
        self._total_allowed_requests = 0

    async def _get_rate_limit_settings(self) -> dict:
        """Получить актуальные настройки rate limiting с кэшированием"""
        current_time = time.time()

        # Обновляем кэш если прошло достаточно времени или кэш пуст
        if (not self._cached_settings or
            current_time - self._cache_time > self._cache_duration):

            if self.settings_service:
                try:
                    self._cached_settings = await self.settings_service.get_rate_limit_info()
                    self._cache_time = current_time
                    logger.debug(f"Обновлен кэш настроек rate limiting: {self._cached_settings}")
                except Exception as e:
                    logger.error(f"Ошибка получения настроек rate limiting: {e}")
                    # Используем дефолтные значения при ошибке
                    self._cached_settings = {"enabled": True, "calls": 5, "period": 60}
            else:
                # Если нет сервиса настроек, читаем из config
                try:
                    from config.settings import settings
                    self._cached_settings = {
                        "enabled": True,
                        "calls": settings.rate_limit_calls,
                        "period": settings.rate_limit_period
                    }
                    logger.debug(f"Загружены настройки из config: {self._cached_settings}")
                except ImportError:
                    logger.warning("Не удалось загрузить настройки, используются дефолтные")
                    self._cached_settings = {"enabled": True, "calls": 5, "period": 60}

                self._cache_time = current_time

        return self._cached_settings

    async def is_rate_limited(self, user_id: int) -> bool:
        """
        Проверить, превышен ли лимит частоты запросов

        Args:
            user_id: ID пользователя

        Returns:
            True если лимит превышен, False в противном случае
        """
        settings = await self._get_rate_limit_settings()

        # Если rate limiting отключен, не ограничиваем
        if not settings.get("enabled", True):
            self._total_allowed_requests += 1
            return False

        current_time = time.time()
        user_queue = self.user_requests[user_id]

        # Ограничиваем размер очереди для предотвращения утечек памяти
        max_queue_size = settings.get("calls", 5) * 2
        if len(user_queue) > max_queue_size:
            # Очищаем очень старые записи
            cutoff_time = current_time - settings.get("period", 60) * 2
            while user_queue and user_queue[0] < cutoff_time:
                user_queue.popleft()

        # Удаляем старые запросы (старше чем rate_limit_period секунд)
        period = settings.get("period", 60)
        while user_queue and current_time - user_queue[0] > period:
            user_queue.popleft()

        # Проверяем количество запросов
        max_calls = settings.get("calls", 5)
        if len(user_queue) >= max_calls:
            self._total_blocked_requests += 1
            logger.info(f"Rate limit exceeded for user {user_id}: {len(user_queue)}/{max_calls} requests in {period}s")
            return True

        # Добавляем текущий запрос
        user_queue.append(current_time)
        self._total_allowed_requests += 1
        return False



    def get_time_until_reset(self, user_id: int) -> int:
        """
        DEPRECATED: Синхронная версия для обратной совместимости
        Используйте await get_time_until_reset_async(user_id) вместо этого
        """
        logger.warning(
            "Используется устаревший синхронный метод get_time_until_reset. Обновите код для использования await.")

        try:
            from config.settings import settings
            period = settings.rate_limit_period
        except ImportError:
            period = 60

        user_queue = self.user_requests[user_id]
        if not user_queue:
            return 0

        current_time = time.time()
        oldest_request = user_queue[0]
        return max(0, int(period - (current_time - oldest_request)))

    def get_time_until_reset_sync(self, user_id: int) -> int:
        """
        Синхронная версия получения времени до сброса
        DEPRECATED: Используйте get_time_until_reset() вместо этого метода
        """
        try:
            from config.settings import settings
            period = settings.rate_limit_period
        except ImportError:
            period = 60

        user_queue = self.user_requests[user_id]
        if not user_queue:
            return 0

        current_time = time.time()
        oldest_request = user_queue[0]
        return max(0, int(period - (current_time - oldest_request)))

    def reset_user_limit(self, user_id: int) -> None:
        """
        Сбросить лимит для пользователя

        Args:
            user_id: ID пользователя
        """
        if user_id in self.user_requests:
            requests_count = len(self.user_requests[user_id])
            self.user_requests[user_id].clear()
            logger.info(f"Сброшен лимит для пользователя {user_id} ({requests_count} запросов)")

    async def get_user_request_count(self, user_id: int) -> int:
        """
        Получить количество запросов пользователя за период

        Args:
            user_id: ID пользователя

        Returns:
            Количество запросов
        """
        settings = await self._get_rate_limit_settings()
        current_time = time.time()
        user_queue = self.user_requests[user_id]

        # Удаляем старые запросы
        period = settings.get("period", 60)
        while user_queue and current_time - user_queue[0] > period:
            user_queue.popleft()

        return len(user_queue)

    async def get_rate_limit_status(self, user_id: int) -> dict:
        """
        Получить полную информацию о статусе rate limiting для пользователя

        Args:
            user_id: ID пользователя

        Returns:
            Словарь со статистикой
        """
        settings = await self._get_rate_limit_settings()
        current_count = await self.get_user_request_count(user_id)
        max_calls = settings.get("calls", 5)

        return {
            "enabled": settings.get("enabled", True),
            "current_requests": current_count,
            "max_requests": max_calls,
            "remaining_requests": max(0, max_calls - current_count),
            "period": settings.get("period", 60),
            "time_until_reset": await self.get_time_until_reset(user_id),
            "is_limited": current_count >= max_calls
        }

    async def get_global_statistics(self) -> dict:
        """
        Получить глобальную статистику rate limiting

        Returns:
            Словарь со статистикой
        """
        settings = await self._get_rate_limit_settings()

        # Подсчитываем активных пользователей
        active_users = 0
        total_active_requests = 0
        limited_users = 0

        current_time = time.time()
        period = settings.get("period", 60)
        max_calls = settings.get("calls", 5)

        for user_id, user_queue in self.user_requests.items():
            # Очищаем старые запросы для точного подсчета
            while user_queue and current_time - user_queue[0] > period:
                user_queue.popleft()

            if user_queue:
                active_users += 1
                total_active_requests += len(user_queue)

                if len(user_queue) >= max_calls:
                    limited_users += 1

        return {
            "enabled": settings.get("enabled", True),
            "settings": settings,
            "active_users": active_users,
            "limited_users": limited_users,
            "total_active_requests": total_active_requests,
            "total_blocked_requests": self._total_blocked_requests,
            "total_allowed_requests": self._total_allowed_requests,
            "average_requests_per_user": total_active_requests / max(active_users, 1)
        }

    def clear_old_requests(self) -> dict:
        """
        Очистить старые запросы для всех пользователей (для обслуживания)

        Returns:
            Статистика очистки
        """
        try:
            from config.settings import settings
            period = settings.rate_limit_period
        except ImportError:
            period = 60

        current_time = time.time()
        cutoff_time = current_time - period * 2  # Удаляем записи старше двух периодов

        removed_count = 0
        users_cleaned = 0
        users_to_remove = []

        for user_id, user_queue in self.user_requests.items():
            old_count = len(user_queue)

            while user_queue and user_queue[0] < cutoff_time:
                user_queue.popleft()
                removed_count += 1

            if old_count > len(user_queue):
                users_cleaned += 1

            # Если очередь пуста, помечаем пользователя для удаления
            if not user_queue:
                users_to_remove.append(user_id)

        # Удаляем пустые очереди
        for user_id in users_to_remove:
            del self.user_requests[user_id]

        cleanup_stats = {
            "removed_requests": removed_count,
            "users_cleaned": users_cleaned,
            "empty_users_removed": len(users_to_remove),
            "remaining_users": len(self.user_requests)
        }

        logger.info(f"Rate limit cleanup completed: {cleanup_stats}")
        return cleanup_stats

    def force_cache_refresh(self):
        """Принудительно обновить кэш настроек"""
        self._cached_settings = None
        self._cache_time = 0
        logger.info("Кэш настроек rate limiting принудительно сброшен")

    async def disable_for_user(self, user_id: int, duration: int = 300):
        """
        Временно отключить rate limiting для конкретного пользователя

        Args:
            user_id: ID пользователя
            duration: Длительность в секундах (по умолчанию 5 минут)
        """
        if not hasattr(self, '_disabled_users'):
            self._disabled_users = {}

        self._disabled_users[user_id] = time.time() + duration
        logger.info(f"Rate limiting отключен для пользователя {user_id} на {duration} секунд")

    async def _is_user_disabled(self, user_id: int) -> bool:
        """Проверить, отключен ли rate limiting для пользователя"""
        if not hasattr(self, '_disabled_users'):
            return False

        if user_id in self._disabled_users:
            if time.time() < self._disabled_users[user_id]:
                return True
            else:
                # Время истекло, удаляем из списка
                del self._disabled_users[user_id]

        return False

    async def is_rate_limited_with_bypass(self, user_id: int) -> bool:
        """
        Проверка rate limiting с поддержкой временного отключения

        Args:
            user_id: ID пользователя

        Returns:
            True если лимит превышен, False в противном случае
        """
        # Проверяем, отключен ли rate limiting для этого пользователя
        if await self._is_user_disabled(user_id):
            return False

        return await self.is_rate_limited(user_id)

    async def is_rate_limited_async(self, user_id: int) -> bool:
        """
        Асинхронная проверка, превышен ли лимит частоты запросов
        """
        # Весь код из старого is_rate_limited метода
        settings = await self._get_rate_limit_settings()

        if not settings.get("enabled", True):
            self._total_allowed_requests += 1
            return False

        current_time = time.time()
        user_queue = self.user_requests[user_id]

        max_queue_size = settings.get("calls", 5) * 2
        if len(user_queue) > max_queue_size:
            cutoff_time = current_time - settings.get("period", 60) * 2
            while user_queue and user_queue[0] < cutoff_time:
                user_queue.popleft()

        period = settings.get("period", 60)
        while user_queue and current_time - user_queue[0] > period:
            user_queue.popleft()

        max_calls = settings.get("calls", 5)
        if len(user_queue) >= max_calls:
            self._total_blocked_requests += 1
            logger.info(f"Rate limit exceeded for user {user_id}: {len(user_queue)}/{max_calls} requests in {period}s")
            return True

        user_queue.append(current_time)
        self._total_allowed_requests += 1
        return False

    async def get_time_until_reset_async(self, user_id: int) -> int:
        """
        Асинхронное получение времени до сброса лимита в секундах
        """
        settings = await self._get_rate_limit_settings()
        user_queue = self.user_requests[user_id]

        if not user_queue:
            return 0

        current_time = time.time()
        oldest_request = user_queue[0]
        period = settings.get("period", 60)

        return max(0, int(period - (current_time - oldest_request)))

    def __str__(self) -> str:
        """Строковое представление middleware"""
        if self._cached_settings:
            return (f"RateLimitMiddleware(enabled={self._cached_settings.get('enabled')}, "
                   f"calls={self._cached_settings.get('calls')}, "
                   f"period={self._cached_settings.get('period')})")
        else:
            return "RateLimitMiddleware(settings not loaded)"

    def __repr__(self) -> str:
        """Детальное представление middleware"""
        return (f"RateLimitMiddleware(users={len(self.user_requests)}, "
               f"blocked={self._total_blocked_requests}, "
               f"allowed={self._total_allowed_requests})")