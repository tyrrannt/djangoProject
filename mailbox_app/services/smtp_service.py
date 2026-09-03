"""Сервис отправки писем по протоколу SMTP с автосохранением в Sent на IMAP."""

from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, getaddresses, make_msgid, parseaddr
import logging
import re
import smtplib
import ssl
import time
from typing import List, Optional, Tuple, Union

from mailbox_app.services.imap_service import ImapMailService

logger = logging.getLogger(__name__)


def format_recipient_addresses(
    recipients: Union[str, List[str], Tuple[str, ...], None]
) -> Tuple[str, List[str]]:
    """Форматирует адресатов для MIME-заголовков (RFC 5322/2047) и SMTP-конверта (RFC 5321).

    Разделяет отображаемое имя и email-адрес, кодирует имя по стандарту RFC 2047
    в кодировке UTF-8 через formataddr, оставляя email-адрес в открытом ASCII (<user@domain>).
    Это устраняет баг сторонних почтовых клиентов (Outlook, Thunderbird, Apple Mail, The Bat,
    мобильные и веб-клиенты), когда при кодировании всей строки целиком парсер клиента
    не находит адресной спецификации и отображает получателя пустым.

    Args:
        recipients (str | list[str] | tuple[str, ...] | None): Адресаты в виде строки
            или списка/кортежа строк. Поддерживает разделение запятыми и точками с запятой.

    Returns:
        tuple[str, list[str]]: Кортеж из:
            - header_str: Строка для MIME-заголовка (To / Cc / Bcc), например:
              '=?utf-8?b?...?= <ivan@barkol.ru>, petrov@barkol.ru'
            - envelope_addrs: Список чистых email-адресов без имен для SMTP RCPT TO,
              например: ['ivan@barkol.ru', 'petrov@barkol.ru']

    Example:
        >>> format_recipient_addresses('"Иван Иванов" <ivan@barkol.ru>')
        ('=?utf-8?b?0JjQstCw0L0g0JjQstCw0L3QvtCy?= <ivan@barkol.ru>', ['ivan@barkol.ru'])
    """
    if not recipients:
        return "", []

    if isinstance(recipients, str):
        raw_items = [recipients]
    else:
        raw_items = list(recipients)

    # Нормализуем разделители: заменяем точки с запятой на запятые
    normalized_items = [item.replace(";", ",") for item in raw_items if item]
    if not normalized_items:
        return "", []

    parsed = getaddresses(normalized_items)
    formatted_headers: List[str] = []
    envelope_addresses: List[str] = []
    seen_envelope = set()

    for name, email_addr in parsed:
        email_clean = email_addr.strip().strip("<>").strip()
        name_clean = name.strip().strip("\"'").strip()

        # Если email_clean пустой или содержит пробелы, пробуем извлечь регулярным выражением
        if (" " in email_clean or not email_clean) and "@" in (email_clean or name_clean):
            target = email_clean or name_clean
            match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", target)
            if match:
                email_clean = match.group(0)
                extracted_name = (target[:match.start()] + " " + target[match.end():]).strip("\"' \t\r\n<>")
                if not name_clean or name_clean == target:
                    name_clean = extracted_name

        if not email_clean or "@" not in email_clean:
            continue

        clean_lower = email_clean.lower()
        if clean_lower not in seen_envelope:
            seen_envelope.add(clean_lower)
            envelope_addresses.append(email_clean)

        if name_clean:
            formatted_headers.append(formataddr((name_clean, email_clean)))
        else:
            formatted_headers.append(email_clean)

    header_str = ", ".join(formatted_headers)
    return header_str, envelope_addresses


class SmtpMailService:
    """Сервис отправки исходящей почты через SMTP."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        email_addr: str,
        password: str,
        display_name: str = "",
        use_ssl: bool = True,
        use_tls: bool = False,
        imap_host: Optional[str] = None,
        imap_port: int = 993,
        imap_use_ssl: bool = True,
    ):
        """Инициализирует SMTP-сервис.

        Args:
            smtp_host (str): Хост SMTP сервера.
            smtp_port (int): Порт SMTP сервера.
            email_addr (str): Email адрес отправителя.
            password (str): Пароль учетной записи.
            display_name (str, optional): Отображаемое имя отправителя.
            use_ssl (bool): Использовать SSL.
            use_tls (bool): Использовать STARTTLS.
            imap_host (str, optional): Хост IMAP для сохранения в Sent.
            imap_port (int): Порт IMAP.
            imap_use_ssl (bool): SSL для IMAP.
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.email = email_addr
        self.password = password
        self.display_name = display_name
        self.use_ssl = use_ssl
        self.use_tls = use_tls
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.imap_use_ssl = imap_use_ssl

    def send_email(
        self,
        to_list: Union[str, List[str]],
        subject: str,
        body_html: str,
        body_text: str = "",
        cc_list: Optional[Union[str, List[str]]] = None,
        bcc_list: Optional[Union[str, List[str]]] = None,
        attachments: Optional[List[Tuple[str, str, bytes]]] = None,
    ) -> bool:
        """Формирует и отправляет почтовое сообщение.

        Args:
            to_list (str | list[str]): Список или строка адресов получателей.
            subject (str): Тема письма.
            body_html (str): HTML-тело письма.
            body_text (str, optional): Текстовая версия письма.
            cc_list (str | list[str], optional): Список или строка адресов в копии.
            bcc_list (str | list[str], optional): Список или строка адресов в скрытой копии.
            attachments (list[tuple[str, str, bytes]], optional): Список вложений (filename, content_type, data).

        Returns:
            bool: True в случае успешной отправки.

        Raises:
            ValueError: Если не указан ни один корректный получатель.
            Exception: При ошибке подключения или отправки.
        """
        to_header, to_envelope = format_recipient_addresses(to_list)
        if not to_envelope:
            raise ValueError("Не указан ни один корректный email-адрес получателя.")

        cc_header, cc_envelope = format_recipient_addresses(cc_list)
        _, bcc_envelope = format_recipient_addresses(bcc_list)

        msg = MIMEMultipart("mixed")
        msg["Subject"] = Header(subject or "(Без темы)", "utf-8")

        clean_from_name = (self.display_name or "").strip().strip("\"'")
        clean_from_email = (self.email or "").strip().strip("<>")
        msg["From"] = formataddr((clean_from_name, clean_from_email)) if clean_from_name else clean_from_email
        msg["To"] = to_header
        if cc_header:
            msg["Cc"] = cc_header
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=self.email.split("@")[-1] if "@" in self.email else "barkol.ru")

        # Текстовая и HTML часть
        msg_alternative = MIMEMultipart("alternative")
        if body_text:
            msg_alternative.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            msg_alternative.attach(MIMEText(body_html, "html", "utf-8"))
        msg.attach(msg_alternative)

        # Прикрепление файлов
        if attachments:
            for filename, content_type, data in attachments:
                maintype, subtype = "application", "octet-stream"
                if content_type and "/" in content_type:
                    maintype, subtype = content_type.split("/", 1)
                part = MIMEBase(maintype, subtype)
                part.set_payload(data)
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=filename,
                )
                part.add_header("Content-ID", f"<{filename}>")
                msg.attach(part)

        # Список всех фактических получателей для SMTP-конверта (RFC 5321 RCPT TO)
        all_envelope_recipients = list(dict.fromkeys(to_envelope + cc_envelope + bcc_envelope))

        # Авторизация и отправка по SMTP
        logins_to_try = [self.email.strip()]
        if "@" in self.email:
            short_user = self.email.split("@")[0].strip()
            if short_user and short_user not in logins_to_try:
                logins_to_try.append(short_user)

        last_smtp_error = None
        for login_candidate in logins_to_try:
            ssl_context = ssl.create_default_context()
            clean_smtp_host = (self.smtp_host or "").strip()
            if clean_smtp_host.replace(".", "").isdigit():
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=15, context=ssl_context)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15)
                if self.use_tls:
                    server.starttls(context=ssl_context)
            try:
                server.login(login_candidate, self.password)
                server.sendmail(self.email, all_envelope_recipients, msg.as_string())
                last_smtp_error = None
                break
            except Exception as err:
                last_smtp_error = err
            finally:
                try:
                    server.quit()
                except Exception:
                    pass

        if last_smtp_error:
            raise last_smtp_error

        # Сохраняем копию в папку Sent на IMAP
        if self.imap_host:
            self._save_to_sent_folder(msg)

        return True

    def _save_to_sent_folder(self, msg: MIMEMultipart) -> None:
        """Сохраняет отправленное письмо в папку Отправленные на IMAP-сервере.

        Args:
            msg (MIMEMultipart): Объект отправленного сообщения.
        """
        try:
            with ImapMailService(
                host=self.imap_host,
                port=self.imap_port,
                email_addr=self.email,
                password=self.password,
                use_ssl=self.imap_use_ssl,
            ) as imap_svc:
                folders = imap_svc.get_folders()
                sent_folder = next(
                    (
                        f["raw_name"]
                        for f in folders
                        if f.get("type") == "sent" or f.get("root_type") == "sent"
                    ),
                    "Sent",
                )
                raw_bytes = msg.as_bytes()
                imap_svc.client.append(
                    f'"{sent_folder}"',
                    "(\\Seen)",
                    time.localtime(),
                    raw_bytes,
                )
        except Exception as e:
            logger.warning(f"[SMTP] Не удалось сохранить копию в Sent: {e}")
