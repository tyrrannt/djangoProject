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


class ScheduledEmail(models.Model):
    """Модель отложенного письма для отправки по расписанию.

    Хранит информацию о письме, ожидающем отправки в заданную дату и время
    через фоновый воркер Celery / Celery Beat.

    Attributes:
        user (ForeignKey): Пользователь, создавший отложенное письмо.
        account (ForeignKey): Почтовый ящик, с которого будет производиться отправка.
        to_recipients (TextField): Получатели письма (email через запятую).
        cc_recipients (TextField): Адреса в копии письма (Cc).
        bcc_recipients (TextField): Адреса в скрытой копии (Bcc).
        subject (CharField): Тема сообщения.
        body_html (TextField): Форматированное тело сообщения (HTML).
        body_text (TextField): Текстовая версия сообщения.
        scheduled_at (DateTimeField): Запланированная дата и время отправки письма.
        status (CharField): Текущий статус обработки (pending, processing, sent, failed, cancelled).
        attempts_count (IntegerField): Количество предпринятых попыток отправки.
        max_attempts (IntegerField): Максимально допустимое число попыток при сбоях.
        last_error (TextField): Текст ошибки последней неудачной попытки.
        sent_at (DateTimeField): Фактическая дата и время успешной отправки.
        created_at (DateTimeField): Дата создания записи.
        updated_at (DateTimeField): Дата последнего обновления записи.
    """

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "В очереди"),
        (STATUS_PROCESSING, "Отправляется"),
        (STATUS_SENT, "Отправлено"),
        (STATUS_FAILED, "Ошибка отправки"),
        (STATUS_CANCELLED, "Отменено"),
    ]

    class Meta:
        verbose_name = "Запланированное письмо"
        verbose_name_plural = "Запланированные письма"
        ordering = ["scheduled_at"]
        indexes = [
            models.Index(fields=["status", "scheduled_at"], name="sched_mail_status_time_idx"),
            models.Index(fields=["user", "status"], name="sched_mail_user_status_idx"),
        ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="scheduled_emails",
        verbose_name="Автор",
    )
    account = models.ForeignKey(
        MailAccount,
        on_delete=models.CASCADE,
        related_name="scheduled_emails",
        verbose_name="Почтовый ящик",
    )
    to_recipients = models.TextField(
        verbose_name="Получатели (Кому)",
        help_text="Email адреса через запятую",
    )
    cc_recipients = models.TextField(
        verbose_name="Копия (Cc)",
        blank=True,
        default="",
        help_text="Email адреса через запятую",
    )
    bcc_recipients = models.TextField(
        verbose_name="Скрытая копия (Bcc)",
        blank=True,
        default="",
        help_text="Email адреса через запятую",
    )
    subject = models.CharField(
        verbose_name="Тема",
        max_length=500,
        blank=True,
        default="(Без темы)",
    )
    body_html = models.TextField(
        verbose_name="Текст сообщения (HTML)",
        blank=True,
        default="",
    )
    body_text = models.TextField(
        verbose_name="Текст сообщения (Plain Text)",
        blank=True,
        default="",
    )
    scheduled_at = models.DateTimeField(
        verbose_name="Запланировано на",
        db_index=True,
    )
    status = models.CharField(
        verbose_name="Статус",
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    attempts_count = models.IntegerField(
        verbose_name="Попыток отправки",
        default=0,
    )
    max_attempts = models.IntegerField(
        verbose_name="Максимум попыток",
        default=3,
    )
    last_error = models.TextField(
        verbose_name="Текст последней ошибки",
        blank=True,
        default="",
    )
    sent_at = models.DateTimeField(
        verbose_name="Отправлено в",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(
        verbose_name="Создано",
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        verbose_name="Обновлено",
        auto_now=True,
    )

    def get_recipients_list(self, field_name: str = "to") -> list[str]:
        """Парсит строковое поле адресатов и возвращает чистый список email.

        Args:
            field_name (str): Имя поля ('to', 'cc', 'bcc').

        Returns:
            list[str]: Список очищенных email-адресов.
        """
        raw_val = ""
        if field_name == "to":
            raw_val = self.to_recipients
        elif field_name == "cc":
            raw_val = self.cc_recipients
        elif field_name == "bcc":
            raw_val = self.bcc_recipients

        if not raw_val:
            return []
        normalized = raw_val.replace(";", ",")
        return [addr.strip() for addr in normalized.split(",") if addr.strip()]

    @property
    def to_display(self) -> str:
        """Возвращает краткое представление получателей для списка писем.

        Returns:
            str: Имя или адрес первого получателя и кол-во остальных.
        """
        recipients = self.get_recipients_list("to")
        if not recipients:
            return "Без получателя"
        if len(recipients) == 1:
            return recipients[0]
        return f"{recipients[0]} (+{len(recipients) - 1})"

    @property
    def can_cancel(self) -> bool:
        """Определяет, можно ли отменить данное запланированное письмо.

        Returns:
            bool: True, если письмо ожидает отправки или завершилось с ошибкой.
        """
        return self.status in (self.STATUS_PENDING, self.STATUS_FAILED)

    @property
    def can_send_now(self) -> bool:
        """Определяет, можно ли отправить письмо немедленно без ожидания таймера.

        Returns:
            bool: True, если письмо ожидает отправки или завершилось с ошибкой.
        """
        return self.status in (self.STATUS_PENDING, self.STATUS_FAILED)

    @property
    def can_reschedule(self) -> bool:
        """Определяет, доступно ли изменение времени отправки.

        Returns:
            bool: True, если статус pending или failed.
        """
        return self.status in (self.STATUS_PENDING, self.STATUS_FAILED)

    def __str__(self) -> str:
        """Строковое представление запланированного письма.

        Returns:
            str: Тема и дата отправки.
        """
        return f"[{self.get_status_display()}] {self.subject} (на {self.scheduled_at:%d.%m.%Y %H:%M})"


class ScheduledEmailAttachment(models.Model):
    """Модель файла-вложения для отложенного письма.

    Хранит файл на диске портала до момента фактической отправки по SMTP.

    Attributes:
        scheduled_email (ForeignKey): Связанное запланированное письмо.
        file (FileField): Файл на диске.
        filename (CharField): Исходное имя файла при загрузке пользователем.
        content_type (CharField): MIME-тип содержимого файла.
        file_size (IntegerField): Размер файла в байтах.
        created_at (DateTimeField): Дата прикрепления файла.
    """

    class Meta:
        verbose_name = "Вложение запланированного письма"
        verbose_name_plural = "Вложения запланированных писем"
        ordering = ["created_at"]

    scheduled_email = models.ForeignKey(
        ScheduledEmail,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name="Запланированное письмо",
    )
    file = models.FileField(
        upload_to="mailbox/scheduled_attachments/%Y/%m/",
        verbose_name="Файл вложения",
    )
    filename = models.CharField(
        max_length=255,
        verbose_name="Имя файла",
    )
    content_type = models.CharField(
        max_length=128,
        default="application/octet-stream",
        verbose_name="MIME-тип",
    )
    file_size = models.IntegerField(
        default=0,
        verbose_name="Размер (байт)",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создано",
    )

    @property
    def file_size_human(self) -> str:
        """Возвращает человекочитаемый размер файла.

        Returns:
            str: Размер в Б, КБ или МБ.
        """
        size = self.file_size or 0
        if size < 1024:
            return f"{size} Б"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} КБ"
        return f"{size / (1024 * 1024):.1f} МБ"

    def __str__(self) -> str:
        """Строковое представление вложения.

        Returns:
            str: Имя файла и его размер.
        """
        return f"{self.filename} ({self.file_size_human})"
