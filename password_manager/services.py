# password_manager/services.py
"""
Сервисный слой приложения password_manager.

Инкапсулирует бизнес-логику: проверку ключевых фраз,
шифрование/дешифрование, генерацию и административный доступ.
"""
import hmac
from .models import UserKeyHash
from .crypto import CryptoEngine
from .generator import PasswordGenerator
from decouple import config
from cryptography.fernet import Fernet
from core import logger


class PasswordService:
    """
    Высокоуровневый интерфейс для работы с учетными данными.
    Все методы статические, так как сервис не хранит состояние.
    """

    @classmethod
    def setup_or_update_key(cls, user, passphrase: str) -> bool:
        """
        Создает или обновляет хеш ключевой фразы пользователя.
        Вызывается при первой настройке менеджера паролей.

        Args:
            user: Экземпляр DataBaseUser.
            passphrase: Новая ключевая фраза.

        Returns:
            bool: True при успешном сохранении хеша.
        """
        key_hash = CryptoEngine.hash_passphrase(passphrase)
        UserKeyHash.objects.update_or_create(
            user=user,
            defaults={'key_hash': key_hash}
        )
        return True

    @classmethod
    def verify_passphrase(cls, user, passphrase: str) -> bool:
        """
        Безопасно проверяет введенную ключевую фразу.
        Использует hmac.compare_digest для защиты от timing-атак.
        """
        try:
            stored_hash = UserKeyHash.objects.get(user=user).key_hash
            computed_hash = CryptoEngine.hash_passphrase(passphrase)
            # Constant-time comparison предотвращает атаку по времени отклика
            return hmac.compare_digest(stored_hash, computed_hash)
        except UserKeyHash.DoesNotExist:
            return False

    @classmethod
    def encrypt_with_passphrase(cls, plaintext: str, user, passphrase: str) -> str:
        """
        Шифрует пароль после успешной верификации фразы.
        """
        if not cls.verify_passphrase(user, passphrase):
            raise ValueError("Неверная ключевая фраза.")
        return CryptoEngine.encrypt(plaintext, passphrase, user.pk)

    @classmethod
    def decrypt_with_passphrase(cls, ciphertext: str, user, passphrase: str) -> str:
        """
        Расшифровывает пароль после успешной верификации фразы.
        """
        if not cls.verify_passphrase(user, passphrase):
            raise ValueError("Неверная ключевая фраза.")
        return CryptoEngine.decrypt(ciphertext, passphrase, user.pk)

    @classmethod
    def admin_decrypt(cls, ciphertext: str) -> str:
        master_key = config("PASSWORD_MANAGER_MASTER_KEY", default=None)
        if not master_key:
            raise PermissionError("Мастер-ключ не найден в конфигурации.")

        try:
            # Убеждаемся, что ключ в байтах
            key_bytes = master_key.encode() if isinstance(master_key, str) else master_key
            f = Fernet(key_bytes)

            # Если ciphertext — это TextField в Django, он может быть str
            token = ciphertext.encode() if isinstance(ciphertext, str) else ciphertext
            return f.decrypt(token).decode('utf-8')
        except Exception as e:
            # Логируем для себя, но пользователю отдаем общую ошибку
            logger.error(f"Admin decryption failed: {str(e)}")
            raise PermissionError("Не удалось расшифровать запись мастер-ключом.")

    @classmethod
    def encrypt_for_admin(cls, plaintext: str) -> str:
        """
        Шифрует пароль мастер-ключом для создания административной копии.

        Raises:
            PermissionError: Если PASSWORD_MANAGER_MASTER_KEY не настроен.
        """
        master_key = config("PASSWORD_MANAGER_MASTER_KEY", default=None)
        if not master_key:
            raise PermissionError(
                "Административное шифрование недоступно: не настроен PASSWORD_MANAGER_MASTER_KEY."
            )
        # Fernet ожидает bytes. Если в settings str, конвертируем.
        key_bytes = master_key.encode() if isinstance(master_key, str) else master_key
        return CryptoEngine.encrypt_with_key(plaintext, key_bytes)

    @staticmethod
    def generate_password(**kwargs) -> str:
        """Обертка над генератором для использования в forms/views."""
        return PasswordGenerator.generate(**kwargs)
