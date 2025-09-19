"""
Утилиты для работы с изображениями VK
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class VKImageUploader:
    """Класс для загрузки изображений на VK сервер"""

    def __init__(self, vk_api_instance, upload_instance):
        self.vk = vk_api_instance
        self.upload = upload_instance
        self._cached_images = {}  # Кэш загруженных изображений

    def upload_photo_for_message(self, image_path: str) -> Optional[str]:
        """
        Загружает фото на VK сервер для отправки в сообщении

        Args:
            image_path: Путь к изображению

        Returns:
            Attachment строка для отправки или None при ошибке
        """
        try:
            # Проверяем кэш
            if image_path in self._cached_images:
                logger.info(f"📷 Использую кэшированное изображение: {image_path}")
                return self._cached_images[image_path]

            # Проверяем существование файла
            if not os.path.exists(image_path):
                logger.error(f"❌ Файл не найден: {image_path}")
                return None

            logger.info(f"📤 Загружаю изображение: {image_path}")

            # Загружаем фото на VK сервер
            photo = self.upload.photo_messages(image_path)[0]

            # Формируем attachment строку
            owner_id = photo['owner_id']
            photo_id = photo['id']
            access_key = photo.get('access_key', '')

            if access_key:
                attachment = f"photo{owner_id}_{photo_id}_{access_key}"
            else:
                attachment = f"photo{owner_id}_{photo_id}"

            # Сохраняем в кэш
            self._cached_images[image_path] = attachment

            logger.info(f"✅ Изображение загружено: {attachment}")
            return attachment

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки изображения {image_path}: {e}")
            return None

    def get_welcome_image(self) -> Optional[str]:
        """
        Получить attachment для приветственного изображения

        Returns:
            Attachment строка или None
        """
        welcome_path = os.path.join("resources", "welcome.png")
        return self.upload_photo_for_message(welcome_path)

    def clear_cache(self):
        """Очистить кэш изображений"""
        self._cached_images.clear()
        logger.info("🗑️ Кэш изображений очищен")


def ensure_resources_directory():
    """Создает папку resources если её нет"""
    resources_dir = "resources"
    if not os.path.exists(resources_dir):
        os.makedirs(resources_dir)
        logger.info(f"📁 Создана папка: {resources_dir}")

        # Создаем README файл с инструкциями
        readme_path = os.path.join(resources_dir, "README.md")
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write("""# Ресурсы бота

## Изображения

### welcome.png
Приветственное изображение, которое отправляется новым пользователям при команде "Начать".

**Требования:**
- Формат: PNG, JPG, JPEG
- Максимальный размер: 50 МБ
- Рекомендуемое разрешение: 1200x800 или меньше
- Соотношение сторон: 3:2 или 16:9

### Добавление новых изображений

1. Поместите изображение в папку `resources/`
2. Используйте `VKImageUploader` для загрузки
3. Добавьте соответствующую логику в обработчики

## Примеры использования

```python
# Загрузка изображения
uploader = VKImageUploader(vk_api, upload)
attachment = uploader.upload_photo_for_message("resources/my_image.png")

# Отправка с изображением
vk.messages.send(
    user_id=user_id,
    message="Текст сообщения",
    attachment=attachment,
    random_id=get_random_id()
)
```
""")
        logger.info(f"📄 Создан файл: {readme_path}")

    return resources_dir
