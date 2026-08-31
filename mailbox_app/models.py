"""Модели базы данных приложения корпоративной почты mailbox_app."""

from django.conf import settings
from django.db import models

from mailbox_app.services.crypto_service import encrypt_password, decrypt_password


class MailAccount(models.Model):
    """Модель персонального почтового ящика пользователя портала.

    Attributes:
        user (OneToOneField): Пользователь портала.
        email (EmailField): Корпоративный email адрес.
        display_name (CharField): Имя отправителя для поля From.
        imap_host (CharField): Адрес IMAP сервера.
        imap_port (IntegerField): Порт IMAP сервера.
        imap_use_ssl (BooleanField): Использовать SSL для IMAP.
        smtp_host (CharField): Адрес SMTP сервера.
        smtp_port (IntegerField): Порт SMTP сервера.
        smtp_use_ssl (BooleanField): Использовать SSL для SMTP.
        smtp_use_tls (BooleanField): Использовать STARTTLS для SMTP.
        encrypted_password (CharField): Зашифрованный пароль ящика.
        signature_html (TextField): HTML-подпись к письмам.
        is_active (BooleanField): Флаг активности ящика.
        created_at (DateTimeField): Дата создания.
        updated_at (DateTimeField): Дата обновления.
    """

    class Meta:
        verbose_name = "Почтовый аккаунт"
        verbose_name_plural = "Почтовые аккаунты"
        ordering = ["user__last_name", "email"]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mail_account",
        verbose_name="Сотрудник",
    )
    email = models.EmailField(verbose_name="Корпоративный Email", max_length=255)
    display_name = models.CharField(
        verbose_name="Имя отправителя", max_length=255, blank=True, default=""
    )
    imap_host = models.CharField(
        verbose_name="Сервер IMAP", max_length=255, default="imap.barkol.ru"
    )
    imap_port = models.IntegerField(verbose_name="Порт IMAP", default=993)
    imap_use_ssl = models.BooleanField(verbose_name="IMAP SSL", default=True)

    smtp_host = models.CharField(
        verbose_name="Сервер SMTP", max_length=255, default="sm.barkol.ru"
    )
    smtp_port = models.IntegerField(verbose_name="Порт SMTP", default=465)
    smtp_use_ssl = models.BooleanField(verbose_name="SMTP SSL", default=True)
    smtp_use_tls = models.BooleanField(verbose_name="SMTP STARTTLS", default=False)

    encrypted_password = models.CharField(
        verbose_name="Зашифрованный пароль", max_length=512, blank=True, default=""
    )
    signature_html = models.TextField(
        verbose_name="Подпись (HTML)", blank=True, default=""
    )
    is_active = models.BooleanField(verbose_name="Активен", default=True)

    created_at = models.DateTimeField(verbose_name="Создан", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="Обновлен", auto_now=True)

    @property
    def password(self) -> str:
        """Расшифровывает и возвращает пароль почтового ящика.

        Returns:
            str: Пароль в открытом виде.
        """
        return decrypt_password(self.encrypted_password)

    @password.setter
    def password(self, raw_pass: str) -> None:
        """Шифрует и сохраняет пароль почтового ящика.

        Args:
            raw_pass (str): Пароль в открытом виде.
        """
        self.encrypted_password = encrypt_password(raw_pass)

    def set_password(self, raw_pass: str) -> None:
        """Шифрует и сохраняет пароль почтового ящика.

        Args:
            raw_pass (str): Исходный пароль в открытом виде.
        """
        self.encrypted_password = encrypt_password(raw_pass)

    def get_password(self) -> str:
        """Возвращает расшифрованный пароль.

        Returns:
            str: Пароль в открытом виде.
        """
        return decrypt_password(self.encrypted_password)

    def __str__(self) -> str:
        """Строковое представление аккаунта.

        Returns:
            str: Email и имя владельца.
        """
        return f"{self.user} ({self.email})"


class MailContact(models.Model):
    """Модель контакта персональной адресной книги пользователя.

    Хранит внешних адресатов, с которыми пользователь вел переписку,
    а также вручную добавленные контакты для автодополнения.

    Attributes:
        user (ForeignKey): Владелец адресной книги.
        name (CharField): Имя контакта или наименование организации.
        email (EmailField): Электронный адрес.
        source (CharField): Источник (вручную или автосбор).
        created_at (DateTimeField): Дата добавления.
        updated_at (DateTimeField): Дата последнего обновления.
    """

    class Meta:
        verbose_name = "Почтовый контакт"
        verbose_name_plural = "Почтовые контакты (Адресная книга)"
        unique_together = ("user", "email")
        ordering = ["name", "email"]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mail_contacts",
        verbose_name="Владелец",
    )
    name = models.CharField(
        verbose_name="Имя / Организация", max_length=255, blank=True, default=""
    )
    email = models.EmailField(verbose_name="Email адрес", max_length=255)
    source = models.CharField(
        verbose_name="Источник",
        max_length=32,
        default="auto",
        choices=[
            ("manual", "Вручную"),
            ("auto", "Автоматически из переписки"),
        ],
    )
    created_at = models.DateTimeField(verbose_name="Создан", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="Обновлен", auto_now=True)

    def __str__(self) -> str:
        """Строковое представление контакта.

        Returns:
            str: Имя и email.
        """
        return f"{self.name} <{self.email}>" if self.name else self.email
