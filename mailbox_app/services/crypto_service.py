"""Модуль безопасного симметричного шифрования паролей почтовых ящиков."""

import base64
import hashlib
from cryptography.fernet import Fernet
from django.conf import settings


def _get_fernet_key() -> bytes:
    """Генерирует 32-байтный URL-safe Base64 ключ Fernet на основе SECRET_KEY проекта.

    Returns:
        bytes: 32-байтный ключ в формате URL-safe base64.
    """
    key_material = hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(key_material)


def encrypt_password(raw_password: str) -> str:
    """Шифрует пароль почтового ящика для безопасного сохранения в БД.

    Args:
        raw_password (str): Исходный пароль в открытом виде.

    Returns:
        str: Зашифрованная строка в формате Base64.
    """
    if not raw_password:
        return ""
    fernet = Fernet(_get_fernet_key())
    encrypted_bytes = fernet.encrypt(raw_password.encode('utf-8'))
    return encrypted_bytes.decode('utf-8')


def decrypt_password(encrypted_password: str) -> str:
    """Расшифровывает пароль почтового ящика.

    Args:
        encrypted_password (str): Зашифрованная строка.

    Returns:
        str: Расшифрованный пароль в открытом виде.
    """
    if not encrypted_password:
        return ""
    try:
        fernet = Fernet(_get_fernet_key())
        decrypted_bytes = fernet.decrypt(encrypted_password.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')
    except Exception:
        # Если расшифровать не удалось (например, если пароль был сохранен в открытом виде)
        return encrypted_password
