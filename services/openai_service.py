"""
Сервис для работы с OpenAI API с поддержкой прокси
"""
import logging
import json
from typing import List, Dict, Optional
import openai
from openai import AsyncOpenAI
import httpx

from config.settings import settings
from repositories.models import Message

# Добавляем logger
logger = logging.getLogger(__name__)


class OpenAIService:
    """Сервис для работы с OpenAI API с поддержкой прокси"""

    def __init__(self, settings_service=None):
        self.model = settings.openai_model
        self.settings_service = settings_service
        
        # Инициализируем с настройками из .env (по умолчанию)
        self.use_proxy = settings.openai_use_proxy
        self.base_url = settings.get_openai_base_url()
        self.api_key = settings.get_openai_api_key()

        # Системное сообщение по умолчанию
        self.system_message = """Ты полезный AI-ассистент. Отвечай дружелюбно и информативно. 
        Старайся давать четкие и полезные ответы. Если не знаешь что-то точно, честно об этом скажи. Не используй markdown оформление. Используй исключительно plain text оформление."""

        # Инициализация клиента
        self.client = self._create_client()

        logger.info(f"OpenAI Service инициализирован: {self._get_connection_info()}")

    async def sync_with_db_settings(self):
        """Синхронизация с настройками из БД"""
        if self.settings_service:
            try:
                bot_settings = await self.settings_service.get_bot_settings()
                
                # Обновляем настройки если они отличаются
                if (self.use_proxy != bot_settings.openai_use_proxy or 
                    self.base_url != (bot_settings.openai_proxy_url if bot_settings.openai_use_proxy else "https://api.openai.com") or
                    self.model != bot_settings.openai_model):
                    
                    logger.info("Обновление OpenAI настроек из БД...")
                    
                    self.use_proxy = bot_settings.openai_use_proxy
                    self.model = bot_settings.openai_model
                    
                    if bot_settings.openai_use_proxy:
                        self.base_url = bot_settings.openai_proxy_url
                        self.api_key = bot_settings.openai_proxy_key or settings.openai_api_key
                    else:
                        self.base_url = "https://api.openai.com"
                        self.api_key = settings.openai_api_key
                    
                    # Пересоздаем клиента с новыми настройками
                    self.client = self._create_client()
                    
                    logger.info(f"Настройки обновлены: {self._get_connection_info()}")
                    
            except Exception as e:
                logger.error(f"Ошибка синхронизации с БД: {e}")

    def _create_client(self) -> AsyncOpenAI:
        """Создание клиента OpenAI с учетом настроек прокси"""
        client_kwargs = {
            "api_key": self.api_key,
            "timeout": httpx.Timeout(30.0, connect=10.0),
        }

        if self.use_proxy:
            # Для прокси устанавливаем custom base_url
            client_kwargs["base_url"] = f"{self.base_url}/v1"
            
            # Добавляем дополнительные заголовки для прокси
            client_kwargs["default_headers"] = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "VK-ChatGPT-Bot/1.0"
            }
            
            logger.info(f"Используется прокси: {self.base_url}")
        else:
            # Для прямого подключения используем стандартный URL
            logger.info("Используется прямое подключение к OpenAI")

        return AsyncOpenAI(**client_kwargs)

    def _get_connection_info(self) -> str:
        """Получить информацию о типе подключения"""
        if self.use_proxy:
            return f"Прокси подключение через {self.base_url}"
        else:
            return "Прямое подключение к OpenAI API"

    async def test_connection(self) -> tuple[bool, str]:
        """
        Тестирование соединения с OpenAI API или прокси

        Returns:
            Кортеж (успешно, сообщение)
        """
        try:
            logger.info(f"Тестирование соединения: {self._get_connection_info()}")

            await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=10
            )

            connection_type = "прокси" if self.use_proxy else "прямое"
            success_msg = f"✅ Соединение ({connection_type}) успешно установлено"
            logger.info(success_msg)
            return True, success_msg

        except openai.AuthenticationError as e:
            error_msg = f"❌ Ошибка аутентификации: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

        except openai.APIConnectionError as e:
            error_msg = f"❌ Ошибка подключения к {'прокси' if self.use_proxy else 'OpenAI'}: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

        except Exception as e:
            error_msg = f"❌ Неизвестная ошибка тестирования: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    def _parse_response(self, response) -> str:
        """
        Парсинг ответа от API (прямого или прокси)
        
        Args:
            response: Ответ от API (может быть объектом или строкой для прокси)
            
        Returns:
            Обработанный текст ответа
        """
        try:
            # Если response является строкой, пытаемся парсить как JSON
            if isinstance(response, str):
                try:
                    response_data = json.loads(response)
                    if 'choices' in response_data and response_data['choices']:
                        content = response_data['choices'][0]['message']['content']
                        logger.debug(f"Получен JSON ответ от прокси длиной {len(content)} символов")
                        return content.strip()
                except (json.JSONDecodeError, KeyError, IndexError) as e:
                    logger.warning(f"Не удалось парсить JSON от прокси: {e}")
                    # Если не удалось парсить JSON, возвращаем как есть
                    logger.debug(f"Получен строковый ответ от прокси длиной {len(response)} символов")
                    return response.strip()
            
            # Стандартный объект OpenAI
            elif hasattr(response, 'choices') and response.choices:
                generated_text = response.choices[0].message.content.strip()
                logger.debug(f"Получен ответ от OpenAI длиной {len(generated_text)} символов")
                return generated_text
            
            else:
                logger.error(f"Неожиданный формат ответа: {type(response)}")
                return "❌ Получен неожиданный формат ответа от API"
                
        except Exception as e:
            logger.error(f"Ошибка парсинга ответа: {e}")
            return "❌ Ошибка обработки ответа от API"

    async def _make_direct_proxy_request(self, request_params: dict) -> str:
        """
        Прямой HTTP-запрос к прокси через httpx для обхода проблем с OpenAI клиентом
        
        Args:
            request_params: Параметры запроса
            
        Returns:
            Обработанный ответ
        """
        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "VK-ChatGPT-Bot/1.0"
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, json=request_params, headers=headers)
                response.raise_for_status()
                
                # Получаем текст ответа
                response_text = response.text
                logger.debug(f"Получен ответ от прокси: {len(response_text)} символов")
                
                # Пытаемся парсить как JSON
                try:
                    response_data = response.json()
                    if 'choices' in response_data and response_data['choices']:
                        content = response_data['choices'][0]['message']['content']
                        logger.debug(f"Получен JSON ответ от прокси длиной {len(content)} символов")
                        return content.strip()
                    else:
                        logger.warning(f"Неожиданная структура JSON: {response_data}")
                        return "❌ Получен некорректный ответ от прокси"
                        
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Не удалось парсить JSON от прокси: {e}")
                    # Если не JSON, возвращаем как есть
                    return response_text.strip()
                    
            except httpx.HTTPStatusError as e:
                logger.error(f"Ошибка HTTP от прокси: {e.response.status_code}")
                raise openai.APIStatusError(f"HTTP {e.response.status_code}", response=e.response, body=None)
                
            except httpx.TimeoutException:
                logger.error("Таймаут запроса к прокси")
                raise openai.APITimeoutError("Request timeout")
                
            except httpx.ConnectError as e:
                logger.error(f"Ошибка соединения с прокси: {e}")
                raise openai.APIConnectionError(f"Connection error: {e}")

    async def _make_request_with_retry(self, request_params: dict, max_retries: int = 2) -> str:
        """
        Выполнение запроса с повторными попытками при ошибках прокси
        
        Args:
            request_params: Параметры запроса
            max_retries: Максимальное количество повторных попыток
            
        Returns:
            Обработанный ответ
        """
        # Используем прямой HTTP-запрос для прокси чтобы избежать проблем с OpenAI клиентом
        if self.use_proxy:
            for attempt in range(max_retries + 1):
                try:
                    if attempt > 0:
                        logger.info(f"Повторная попытка {attempt}/{max_retries}")
                    
                    return await self._make_direct_proxy_request(request_params)
                    
                except (openai.APIConnectionError, openai.APITimeoutError, httpx.ConnectError, httpx.TimeoutException) as e:
                    if attempt < max_retries:
                        logger.warning(f"Ошибка соединения с прокси (попытка {attempt + 1}): {e}")
                        continue
                    else:
                        raise e
                
                except Exception as e:
                    # Любая другая ошибка - пробрасываем дальше
                    raise e
        else:
            # Для прямого соединения используем стандартный клиент
            response = await self.client.chat.completions.create(**request_params)
            return self._parse_response(response)

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: float = 0.7
    ) -> str:
        """
        Генерация ответа от OpenAI

        Args:
            messages: Список сообщений в формате OpenAI
            max_tokens: Максимальное количество токенов в ответе
            temperature: Температура генерации (0.0 - 2.0)

        Returns:
            Сгенерированный ответ
        """
        try:
            # Добавляем системное сообщение если его нет
            if not messages or messages[0].get("role") != "system":
                messages = [{"role": "system", "content": self.system_message}] + messages

            # Подготавливаем параметры запроса
            request_params = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }

            # Добавляем max_tokens только если указан
            if max_tokens:
                request_params["max_tokens"] = max_tokens

            logger.debug(f"Отправка запроса к {'прокси' if self.use_proxy else 'OpenAI'}: {len(messages)} сообщений")

            # Используем метод с повторными попытками
            return await self._make_request_with_retry(request_params)

        except openai.RateLimitError as e:
            logger.warning(f"Rate limit превышен ({'прокси' if self.use_proxy else 'OpenAI'}): {e}")
            return "⚠️ Превышен лимит запросов к OpenAI. Попробуйте позже."

        except openai.AuthenticationError as e:
            logger.error(f"Ошибка аутентификации ({'прокси' if self.use_proxy else 'OpenAI'}): {e}")
            return f"❌ Ошибка аутентификации {'прокси' if self.use_proxy else 'OpenAI'}. Проверьте API ключ."

        except openai.APITimeoutError as e:
            logger.warning(f"Timeout ({'прокси' if self.use_proxy else 'OpenAI'}): {e}")
            return "⏱️ Превышено время ожидания ответа. Попробуйте еще раз."

        except openai.APIConnectionError as e:
            logger.error(f"Ошибка соединения ({'прокси' if self.use_proxy else 'OpenAI'}): {e}")
            if self.use_proxy:
                return f"❌ Ошибка подключения к прокси серверу. Проверьте доступность {self.base_url}"
            else:
                return "❌ Ошибка подключения к OpenAI API. Проверьте интернет соединение."

        except openai.BadRequestError as e:
            logger.error(f"Некорректный запрос ({'прокси' if self.use_proxy else 'OpenAI'}): {e}")
            if 'moderation' in str(e):
                return "❌ Ваш запрос был отклонен системой модерации контента."
            return "❌ Ошибка в запросе к OpenAI: Некорректный запрос."

        except openai.APIStatusError as e:
            logger.error(f"Ошибка статуса API ({'прокси' if self.use_proxy else 'OpenAI'}): {e}")
            return f"❌ Ошибка {'прокси сервера' if self.use_proxy else 'OpenAI API'}: {e.status_code}"

        except openai.APIError as e:
            logger.error(f"Общая ошибка API ({'прокси' if self.use_proxy else 'OpenAI'}): {e}")
            return f"❌ Произошла ошибка на стороне {'прокси' if self.use_proxy else 'OpenAI'}."


    async def generate_response_from_context(
        self,
        context_messages: List[Message],
        user_message: str,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Генерация ответа с учетом контекста

        Args:
            context_messages: Список сообщений контекста
            user_message: Новое сообщение пользователя
            max_tokens: Максимальное количество токенов в ответе

        Returns:
            Сгенерированный ответ
        """
        # Конвертируем контекст в формат OpenAI
        messages = [msg.to_openai_format() for msg in context_messages]

        # Добавляем новое сообщение пользователя
        messages.append({
            "role": "user",
            "content": user_message
        })

        return await self.generate_response(messages, max_tokens)

    def set_system_message(self, system_message: str) -> None:
        """
        Установка системного сообщения

        Args:
            system_message: Новое системное сообщение
        """
        self.system_message = system_message
        logger.info("Системное сообщение обновлено")

    def set_model(self, model: str) -> None:
        """
        Установка модели OpenAI

        Args:
            model: Название модели (например, gpt-3.5-turbo, gpt-4)
        """
        self.model = model
        logger.info(f"Модель OpenAI изменена на: {model}")

    async def switch_to_proxy(self, proxy_url: str, proxy_key: Optional[str] = None) -> tuple[bool, str]:
        """
        Переключение на прокси в runtime

        Args:
            proxy_url: URL прокси сервера
            proxy_key: Ключ для прокси (опционально)

        Returns:
            Кортеж (успешно, сообщение)
        """
        try:
            old_client = self.client
            old_base_url = self.base_url
            old_use_proxy = self.use_proxy
            old_api_key = self.api_key

            # Обновляем настройки
            self.use_proxy = True
            self.base_url = proxy_url.rstrip('/')
            if proxy_key:
                self.api_key = proxy_key

            # Создаем новый клиент
            self.client = self._create_client()

            # Тестируем соединение
            test_success, test_message = await self.test_connection()

            if test_success:
                # Закрываем старый клиент
                try:
                    await old_client.close()
                except Exception:
                    pass

                logger.info(f"Успешно переключено на прокси: {proxy_url}")
                return True, f"✅ Переключено на прокси: {proxy_url}"
            else:
                # Откатываем изменения при неудаче
                self.use_proxy = old_use_proxy
                self.base_url = old_base_url
                self.api_key = old_api_key
                self.client = old_client

                return False, f"❌ Не удалось переключиться на прокси: {test_message}"

        except Exception as e:
            logger.error(f"Ошибка переключения на прокси: {e}")
            return False, f"❌ Ошибка переключения на прокси: {str(e)}"

    async def switch_to_direct(self) -> tuple[bool, str]:
        """
        Переключение на прямое соединение в runtime

        Returns:
            Кортеж (успешно, сообщение)
        """
        try:
            old_client = self.client
            old_base_url = self.base_url
            old_use_proxy = self.use_proxy

            # Обновляем настройки
            self.use_proxy = False
            self.base_url = "https://api.openai.com"
            self.api_key = settings.openai_api_key

            # Создаем новый клиент
            self.client = self._create_client()

            # Тестируем соединение
            test_success, test_message = await self.test_connection()

            if test_success:
                # Закрываем старый клиент
                try:
                    await old_client.close()
                except Exception:
                    pass

                logger.info("Успешно переключено на прямое соединение")
                return True, "✅ Переключено на прямое соединение к OpenAI"
            else:
                # Откатываем изменения при неудаче
                self.use_proxy = old_use_proxy
                self.base_url = old_base_url
                self.client = old_client

                return False, f"❌ Не удалось переключиться на прямое соединение: {test_message}"

        except Exception as e:
            logger.error(f"Ошибка переключения на прямое соединение: {e}")
            return False, f"❌ Ошибка переключения: {str(e)}"

    def get_connection_status(self) -> dict:
        """
        Получить текущий статус соединения

        Returns:
            Словарь с информацией о соединении
        """
        return {
            "use_proxy": self.use_proxy,
            "base_url": self.base_url,
            "model": self.model,
            "connection_type": "Прокси" if self.use_proxy else "Прямое подключение",
            "api_endpoint": f"{self.base_url}/v1" if self.use_proxy else "https://api.openai.com/v1"
        }

    async def close(self):
        """Закрытие клиента"""
        try:
            await self.client.close()
            logger.info("OpenAI клиент закрыт")
        except Exception as e:
            logger.error(f"Ошибка закрытия клиента: {e}")

    def __str__(self) -> str:
        """Строковое представление сервиса"""
        return f"OpenAIService(model={self.model}, proxy={self.use_proxy}, url={self.base_url})"

    def __repr__(self) -> str:
        """Детальное представление сервиса"""
        return (f"OpenAIService(model='{self.model}', use_proxy={self.use_proxy}, "
               f"base_url='{self.base_url}', api_key_set={bool(self.api_key)})")
