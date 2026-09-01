"""Сервис отправки писем по протоколу SMTP с автосохранением в Sent на IMAP."""

from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
import logging
import smtplib
import ssl
import time
from typing import List, Optional, Tuple

from mailbox_app.services.imap_service import ImapMailService

logger = logging.getLogger(__name__)


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
        to_list: List[str],
        subject: str,
        body_html: str,
        body_text: str = "",
        cc_list: Optional[List[str]] = None,
        bcc_list: Optional[List[str]] = None,
        attachments: Optional[List[Tuple[str, str, bytes]]] = None,
    ) -> bool:
        """Формирует и отправляет почтовое сообщение.

        Args:
            to_list (list[str]): Список адресов получателей.
            subject (str): Тема письма.
            body_html (str): HTML-тело письма.
            body_text (str, optional): Текстовая версия письма.
            cc_list (list[str], optional): Список адресов в копии.
            bcc_list (list[str], optional): Список адресов в скрытой копии.
            attachments (list[tuple[str, str, bytes]], optional): Список вложений (filename, content_type, data).

        Returns:
            bool: True в случае успешной отправки.

        Raises:
            Exception: При ошибке подключения или отправки.
        """
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = formataddr((self.display_name, self.email)) if self.display_name else self.email
        msg["To"] = ", ".join(to_list)
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)
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

        # Список всех фактических получателей
        all_recipients = list(set(to_list + (cc_list or []) + (bcc_list or [])))

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
                server.sendmail(self.email, all_recipients, msg.as_string())
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
                    (f["raw_name"] for f in folders if f["type"] == "sent"), "Sent"
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
