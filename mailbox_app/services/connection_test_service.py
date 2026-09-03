"""Сервис проверки подключения к почтовым серверам (IMAP и SMTP).

Предоставляет диагностические методы проверки валидности учетных данных
и доступности почтовых серверов для административного интерфейса.
"""

import imaplib
import logging
import smtplib
import socket
import ssl
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

SOCKET_TIMEOUT_SECONDS: int = 7


def test_imap_connection(
    host: str,
    port: int,
    security: str,
    username: str,
    password: str,
) -> Tuple[bool, str]:
    """Проверяет сетевое подключение и авторизацию на сервере IMAP.

    Args:
        host (str): Адрес IMAP-сервера.
        port (int): Порт IMAP.
        security (str): Тип шифрования ('ssl', 'starttls', 'plain').
        username (str): Логин пользователя.
        password (str): Пароль пользователя.

    Returns:
        Tuple[bool, str]: Кортеж (успех, текстовое сообщение о результате/ошибке).

    Example:
        >>> ok, msg = test_imap_connection("imap.barkol.ru", 993, "ssl", "user@barkol.ru", "secret")
    """
    if not host or not username or not password:
        return False, "Не заполнены обязательные параметры (сервер, логин или пароль)."

    client = None
    try:
        if security == "ssl":
            ssl_context = ssl.create_default_context()
            client = imaplib.IMAP4_SSL(host=host, port=port, ssl_context=ssl_context)
        else:
            client = imaplib.IMAP4(host=host, port=port)
            if security == "starttls":
                client.starttls()

        typ, res = client.login(username, password)
        if typ == "OK":
            return True, f"Успешное подключение к IMAP ({host}:{port}). Авторизация пройдена."
        return False, f"Ошибка авторизации IMAP: {res}"
    except imaplib.IMAP4.error as e:
        logger.warning(f"[MailboxTest] Ошибка авторизации IMAP {host}:{port}: {e}")
        return False, f"Ошибка авторизации IMAP (неверный логин или пароль): {e}"
    except (socket.timeout, TimeoutError):
        return False, f"Таймаут подключения к IMAP-серверу {host}:{port}. Проверьте адрес и порт."
    except (socket.gaierror, ConnectionRefusedError, OSError) as e:
        logger.warning(f"[MailboxTest] Ошибка сети IMAP {host}:{port}: {e}")
        return False, f"Не удалось установить соединение с сервером IMAP {host}:{port}: {e}"
    except Exception as e:
        logger.exception(f"[MailboxTest] Непредвиденная ошибка IMAP: {e}")
        return False, f"Сбой при проверке IMAP: {e}"
    finally:
        if client:
            try:
                client.logout()
            except Exception:
                pass


def test_smtp_connection(
    host: str,
    port: int,
    security: str,
    username: str,
    password: str,
) -> Tuple[bool, str]:
    """Проверяет сетевое подключение и авторизацию на сервере SMTP.

    Args:
        host (str): Адрес SMTP-сервера.
        port (int): Порт SMTP.
        security (str): Тип шифрования ('ssl', 'starttls', 'plain').
        username (str): Логин пользователя.
        password (str): Пароль пользователя.

    Returns:
        Tuple[bool, str]: Кортеж (успех, текстовое сообщение о результате/ошибке).

    Example:
        >>> ok, msg = test_smtp_connection("sm.barkol.ru", 465, "ssl", "user@barkol.ru", "secret")
    """
    if not host or not username or not password:
        return False, "Не заполнены обязательные параметры (сервер, логин или пароль SMTP)."

    server = None
    try:
        if security == "ssl":
            ssl_context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(host=host, port=port, timeout=SOCKET_TIMEOUT_SECONDS, context=ssl_context)
        else:
            server = smtplib.SMTP(host=host, port=port, timeout=SOCKET_TIMEOUT_SECONDS)
            if security == "starttls":
                server.ehlo()
                server.starttls()
                server.ehlo()

        server.login(username, password)
        return True, f"Успешное подключение к SMTP ({host}:{port}). Авторизация пройдена."
    except smtplib.SMTPAuthenticationError as e:
        logger.warning(f"[MailboxTest] Ошибка аутентификации SMTP {host}:{port}: {e}")
        return False, f"Ошибка авторизации SMTP: {e.smtp_error.decode('utf-8', errors='replace') if isinstance(e.smtp_error, bytes) else e.smtp_error}"
    except (socket.timeout, TimeoutError):
        return False, f"Таймаут подключения к SMTP-серверу {host}:{port}."
    except (socket.gaierror, ConnectionRefusedError, OSError) as e:
        logger.warning(f"[MailboxTest] Ошибка сети SMTP {host}:{port}: {e}")
        return False, f"Не удалось установить соединение с сервером SMTP {host}:{port}: {e}"
    except Exception as e:
        logger.exception(f"[MailboxTest] Непредвиденная ошибка SMTP: {e}")
        return False, f"Сбой при проверке SMTP: {e}"
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass


def test_full_mailbox_connection(
    imap_host: str,
    imap_port: int,
    imap_security: str,
    imap_username: str,
    imap_password: str,
    smtp_host: str,
    smtp_port: int,
    smtp_security: str,
    smtp_username: str,
    smtp_password: str,
) -> Dict[str, Any]:
    """Выполняет комплексное тестирование подключения к IMAP и SMTP.

    Args:
        imap_host (str): Сервер IMAP.
        imap_port (int): Порт IMAP.
        imap_security (str): Шифрование IMAP.
        imap_username (str): Логин IMAP.
        imap_password (str): Пароль IMAP.
        smtp_host (str): Сервер SMTP.
        smtp_port (int): Порт SMTP.
        smtp_security (str): Шифрование SMTP.
        smtp_username (str): Логин SMTP.
        smtp_password (str): Пароль SMTP.

    Returns:
        Dict[str, Any]: Словарь с результатами тестов IMAP и SMTP:
            {
                "imap_ok": bool,
                "imap_message": str,
                "smtp_ok": bool,
                "smtp_message": str,
                "success": bool
            }
    """
    imap_ok, imap_msg = test_imap_connection(
        host=imap_host,
        port=imap_port,
        security=imap_security,
        username=imap_username,
        password=imap_password,
    )

    smtp_user = smtp_username or imap_username
    smtp_pass = smtp_password or imap_password

    smtp_ok, smtp_msg = test_smtp_connection(
        host=smtp_host,
        port=smtp_port,
        security=smtp_security,
        username=smtp_user,
        password=smtp_pass,
    )

    return {
        "imap_ok": imap_ok,
        "imap_message": imap_msg,
        "smtp_ok": smtp_ok,
        "smtp_message": smtp_msg,
        "success": imap_ok and smtp_ok,
    }
