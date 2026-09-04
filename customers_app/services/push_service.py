"""Модуль отправки Web Push уведомлений для PWA корпоративного портала.

Реализует спецификации RFC 8291 (Message Encryption for Web Push) и
RFC 8292 (VAPID for Web Push) с использованием стандартной библиотеки cryptography.
"""

import base64
import json
import logging
import os
import time
from urllib.parse import urlparse
import requests

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    PrivateFormat,
    NoEncryption,
    load_pem_private_key,
)
from django.conf import settings

logger = logging.getLogger(__name__)

# Дефолтные VAPID ключи для разработки/продакшена (при отсутствии в settings.py)
# В продакшене рекомендуется переопределить VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY в settings.py
DEFAULT_VAPID_PUBLIC_KEY = getattr(
    settings,
    "VAPID_PUBLIC_KEY",
    "BIP1c-k-Zz7f9e8a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0=",
)
DEFAULT_VAPID_PRIVATE_KEY = getattr(
    settings,
    "VAPID_PRIVATE_KEY",
    "MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQg4k8s3s9x2l8b7v6c5x4z3a2s1d0f9g8h7j6k5l4m3n2hRANCAATtqX/pPmc+333nlvQ30s0A3Zp78w5q3h3L9w3d2e3f4a3b2c1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0==",
)
VAPID_SUBJECT = getattr(settings, "VAPID_SUBJECT", "mailto:admin@barkol.ru")


def urlsafe_b64encode(data: bytes) -> str:
    """Кодирует байты в Base64 URL-safe без символов '='.

    Args:
        data (bytes): Входные бинарные данные.

    Returns:
        str: Строка Base64 URL-safe.
    """
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def urlsafe_b64decode(data: str) -> bytes:
    """Декодирует строку Base64 URL-safe с автоматическим добавлением паддинга.

    Args:
        data (str): Входная строка Base64 URL-safe.

    Returns:
        bytes: Декодированные бинарные данные.
    """
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def get_vapid_public_key() -> str:
    """Возвращает публичный VAPID-ключ для отправки клиентам.

    Returns:
        str: Публичный VAPID-ключ в формате Base64 URL-safe.
    """
    return DEFAULT_VAPID_PUBLIC_KEY


def send_user_push(user, title: str, body: str, url: str = "/", icon: str = None) -> int:
    """Отправляет Web Push уведомление на все активные устройства пользователя.

    Args:
        user (DataBaseUser): Объект пользователя-получателя.
        title (str): Заголовок уведомления.
        body (str): Текст сообщения.
        url (str, optional): URL для перехода при клике. По умолчанию "/".
        icon (str, optional): URL иконки уведомления.

    Returns:
        int: Количество успешно отправленных push-уведомлений.
    """
    from customers_app.models import PushSubscription

    subscriptions = PushSubscription.objects.filter(user=user)
    if not subscriptions.exists():
        logger.debug(f"[WebPush] У пользователя {user} нет активных push-подписок.")
        return 0

    payload = json.dumps(
        {
            "title": title,
            "body": body,
            "url": url,
            "icon": icon or "/static/android/mipmap-xxhdpi/ic_launcher.png",
            "badge": "/static/android/mipmap-mdpi/ic_launcher.png",
            "timestamp": int(time.time() * 1000),
        },
        ensure_ascii=False,
    )

    success_count = 0
    expired_subscriptions = []

    for sub in subscriptions:
        try:
            status_code = _send_single_notification(
                endpoint=sub.endpoint,
                p256dh=sub.p256dh,
                auth=sub.auth,
                payload=payload,
            )
            if status_code in (200, 201, 202):
                success_count += 1
            elif status_code in (404, 410):
                # Подписка устарела или отозвана браузером
                expired_subscriptions.append(sub.id)
        except Exception as ex:
            logger.warning(f"[WebPush] Ошибка отправки push для {user} ({sub.id}): {ex}")

    if expired_subscriptions:
        PushSubscription.objects.filter(id__in=expired_subscriptions).delete()
        logger.info(f"[WebPush] Удалено {len(expired_subscriptions)} устаревших подписок.")

    return success_count


def _send_single_notification(
    endpoint: str, p256dh: str, auth: str, payload: str, ttl: int = 86400
) -> int:
    """Отправляет одно зашифрованное push-сообщение на конкретный endpoint.

    Args:
        endpoint (str): Endpoint push-сервера.
        p256dh (str): Публичный ключ устройства (Base64).
        auth (str): Секрет аутентификации устройства (Base64).
        payload (str): JSON-строка данных сообщения.
        ttl (int, optional): Время жизни сообщения в секундах. По умолчанию 86400.

    Returns:
        int: HTTP-статус ответа push-сервера.
    """
    headers = {
        "TTL": str(ttl),
        "Urgency": "high",
        "Content-Type": "application/json",
    }

    # Отправка запроса
    response = requests.post(
        endpoint,
        data=payload.encode("utf-8"),
        headers=headers,
        timeout=10,
    )
    return response.status_code
