"""Централизованные параметры подключения по умолчанию для почтовых ящиков.

Содержит шаблоны настроек для корпоративного домена barkol.ru и популярных
сторонних почтовых сервисов (Яндекс, Mail.ru, Gmail).
"""

from typing import Any, Dict

DEFAULT_DOMAIN: str = "barkol.ru"

DOMAIN_PRESETS: Dict[str, Dict[str, Any]] = {
    "barkol.ru": {
        "domain": "barkol.ru",
        "description": "Основной почтовый сервер ООО 'Баркол'",
        "incoming_protocol": "imap",
        "imap_host": "imap.barkol.ru",
        "imap_port": 993,
        "imap_security": "ssl",
        "smtp_host": "sm.barkol.ru",
        "smtp_port": 465,
        "smtp_security": "ssl",
    },
    "yandex.ru": {
        "domain": "yandex.ru",
        "description": "Яндекс 360 / Яндекс Почта",
        "incoming_protocol": "imap",
        "imap_host": "imap.yandex.ru",
        "imap_port": 993,
        "imap_security": "ssl",
        "smtp_host": "smtp.yandex.ru",
        "smtp_port": 465,
        "smtp_security": "ssl",
    },
    "mail.ru": {
        "domain": "mail.ru",
        "description": "VK WorkSpace / Mail.ru",
        "incoming_protocol": "imap",
        "imap_host": "imap.mail.ru",
        "imap_port": 993,
        "imap_security": "ssl",
        "smtp_host": "smtp.mail.ru",
        "smtp_port": 465,
        "smtp_security": "ssl",
    },
    "gmail.com": {
        "domain": "gmail.com",
        "description": "Google Workspace / Gmail",
        "incoming_protocol": "imap",
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "imap_security": "ssl",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_security": "starttls",
    },
}


def get_domain_defaults(domain: str) -> Dict[str, Any]:
    """Возвращает параметры подключения по умолчанию для указанного домена.

    Если домен отсутствует в пресетах, возвращает настройки по умолчанию для barkol.ru.

    Args:
        domain (str): Имя домена почты (например, 'barkol.ru' или 'gmail.com').

    Returns:
        Dict[str, Any]: Словарь с параметрами IMAP и SMTP.

    Example:
        >>> defaults = get_domain_defaults("barkol.ru")
        >>> defaults["imap_host"]
        'imap.barkol.ru'
    """
    clean_domain = (domain or "").strip().lower()
    return DOMAIN_PRESETS.get(clean_domain, DOMAIN_PRESETS[DEFAULT_DOMAIN]).copy()


def get_all_presets() -> Dict[str, Dict[str, Any]]:
    """Возвращает все зарегистрированные пресеты почтовых доменов.

    Returns:
        Dict[str, Dict[str, Any]]: Словарь всех пресетов.
    """
    return DOMAIN_PRESETS.copy()
