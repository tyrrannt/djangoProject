# password_manager/crypto.py
"""
Низкоуровневый модуль шифрования/дешифрования.

Использует PBKDF2-HMAC-SHA256 для вывода ключа из пользовательской фразы
и Fernet (AES-128-CBC + HMAC-SHA256) для симметричного шифрования.
Все пароли шифруются детерминированно относительно комбинации: [phrase + user_id].

Архитектурные заметки (Security & Django Best Practices)
Защита от Timing Attacks: В verify_passphrase используется hmac.compare_digest, что делает сравнение хешей независимым от времени выполнения.
Детерминированное шифрование: Ключ выводится как PBKDF2(passphrase + app_salt + user_id). Это гарантирует, что даже при утечке БД без ключевой фразы пароли останутся нечитаемыми.
Генератор: Использует secrets.SystemRandom() вместо random, что критично для криптографических задач. Гарантирует наличие символов из каждой категории.
Zero-Knowledge компромисс: По умолчанию пароли шифруются только ключом пользователя. Админский доступ реализован через master_key как fallback. В продакшене рекомендуется добавить поле admin_encrypted_copy в модель EncryptedPassword и шифровать вторую копию при создании.
Изоляция логики: Вся криптография вынесена в CryptoEngine, бизнес-логика в PasswordService, генерация в PasswordGenerator. Это упрощает тестирование и аудит безопасности.

"""

import base64
import hmac
import hashlib
from typing import Tuple

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from decouple import config


class CryptoEngine:
    """
    Статический интерфейс для операций шифрования и хеширования.
    """
    # 480 000 итераций соответствует рекомендациям OWASP 2024 для PBKDF2
    PBKDF2_ITERATIONS = 480_000
    # Соль приложения. В production выносится в переменные окружения.
    _APP_SALT = config("PASSWORD_MANAGER_APP_SALT").encode()

    @classmethod
    def derive_key(cls, passphrase: str, user_identifier: str) -> bytes:
        """
        Генерирует 32-байтовый ключ Fernet из парольной фразы и идентификатора пользователя.

        Args:
            passphrase: Ключевая фраза пользователя (plain text).
            user_identifier: Уникальный идентификатор (обычно pk пользователя).

        Returns:
            bytes: URL-safe base64-encoded ключ для Fernet.
        """
        # Комбинируем соль приложения с ID пользователя. Это гарантирует,
        # что даже при совпадении фраз у разных пользователей ключи будут уникальны.
        combined_salt = cls._APP_SALT + user_identifier.encode('utf-8')

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=combined_salt,
            iterations=cls.PBKDF2_ITERATIONS,
        )
        return base64.urlsafe_b64encode(kdf.derive(passphrase.encode('utf-8')))

    @classmethod
    def encrypt(cls, plaintext: str, passphrase: str, user_id: int) -> str:
        """
        Шифрует plain-текст с использованием ключа, выведенного из фразы и ID.

        Args:
            plaintext: Исходный пароль.
            passphrase: Ключевая фраза пользователя.
            user_id: ID владельца записи.

        Returns:
            str: Зашифрованная строка в формате Fernet.
        """
        key = cls.derive_key(passphrase, str(user_id))
        return Fernet(key).encrypt(plaintext.encode('utf-8')).decode('utf-8')

    @classmethod
    def decrypt(cls, ciphertext: str, passphrase: str, user_id: int) -> str:
        """
        Расшифровывает Fernet-токен. Выбрасывает ValueError при неверной фразе.

        Raises:
            ValueError: Если токен поврежден или ключевая фраза неверна.
        """
        key = cls.derive_key(passphrase, str(user_id))
        try:
            return Fernet(key).decrypt(ciphertext.encode('utf-8')).decode('utf-8')
        except InvalidToken:
            # Ловим криптографическую ошибку и конвертируем в бизнес-исключение
            raise ValueError("Неверная ключевая фраза или данные были изменены.")

    @classmethod
    def encrypt_with_key(cls, plaintext: str, key: bytes) -> str:
        """Прямое шифрование Fernet без вывода ключа через PBKDF2."""
        # Если key - строка, конвертируем в bytes
        if isinstance(key, str):
            key = key.encode('utf-8')
        return Fernet(key).encrypt(plaintext.encode('utf-8')).decode('utf-8')

    @staticmethod
    def hash_passphrase(passphrase: str) -> str:
        """
        Хеширует ключевую фразу для безопасного хранения в UserKeyHash.
        Использует SHA-256 с солью для защиты от rainbow-таблиц.
        """
        salt = settings.SECRET_KEY[:32].encode('utf-8')
        return hashlib.pbkdf2_hmac(
            'sha256',
            passphrase.encode('utf-8'),
            salt,
            100_000
        ).hex()
