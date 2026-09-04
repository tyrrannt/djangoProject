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


class Mailbox(models.Model):
    """Модель корпоративного или дополнительного почтового ящика.

    Представляет собой самостоятельную сущность почтового ящика (отделы, службы,
    общие адреса, внешние ящики), к которому может быть предоставлен доступ
    произвольному набору сотрудников (отношение многие-ко-многим).

    Attributes:
        name (CharField): Наименование ящика (например, 'Отдел кадров').
        email (EmailField): Корпоративный email адрес.
        domain (CharField): Домен почтового адреса (например, 'barkol.ru').
        description (TextField): Описание и назначение ящика.
        is_active (BooleanField): Признак активности.
        incoming_protocol (CharField): Протокол входящей почты ('imap' или 'pop3').
        imap_host (CharField): Сервер IMAP.
        imap_port (IntegerField): Порт IMAP.
        imap_security (CharField): Тип шифрования IMAP ('ssl', 'starttls', 'plain').
        imap_username (CharField): Логин IMAP.
        encrypted_imap_password (CharField): Зашифрованный пароль IMAP.
        smtp_host (CharField): Сервер SMTP.
        smtp_port (IntegerField): Порт SMTP.
        smtp_security (CharField): Тип шифрования SMTP ('ssl', 'starttls', 'plain').
        smtp_username (CharField): Логин SMTP.
        encrypted_smtp_password (CharField): Зашифрованный пароль SMTP.
        display_name (CharField): Имя отправителя для поля From.
        signature_html (TextField): HTML-подпись к письмам.
        users (ManyToManyField): Сотрудники, имеющие доступ к ящику.
        created_at (DateTimeField): Дата создания.
        updated_at (DateTimeField): Дата обновления.
    """

    PROTOCOL_IMAP = "imap"
    PROTOCOL_POP3 = "pop3"
    PROTOCOL_CHOICES = [
        (PROTOCOL_IMAP, "IMAP"),
        (PROTOCOL_POP3, "POP3"),
    ]

    SECURITY_SSL = "ssl"
    SECURITY_STARTTLS = "starttls"
    SECURITY_PLAIN = "plain"
    SECURITY_CHOICES = [
        (SECURITY_SSL, "SSL/TLS"),
        (SECURITY_STARTTLS, "STARTTLS"),
        (SECURITY_PLAIN, "Без шифрования"),
    ]

    class Meta:
        verbose_name = "Корпоративный почтовый ящик"
        verbose_name_plural = "Корпоративные почтовые ящики"
        ordering = ["name", "email"]
        permissions = [
            ("manage_mailboxes", "Может управлять общими и корпоративными почтовыми ящиками"),
        ]

    name = models.CharField(
        verbose_name="Наименование ящика",
        max_length=255,
        help_text="Например: 'Отдел кадров', 'Приёмная', 'Бухгалтерия'",
    )
    email = models.EmailField(
        verbose_name="Почтовый адрес (Email)",
        max_length=255,
        unique=True,
    )
    domain = models.CharField(
        verbose_name="Домен",
        max_length=100,
        blank=True,
        default="",
        help_text="Определяется автоматически из адреса, например: barkol.ru",
    )
    description = models.TextField(
        verbose_name="Описание / Назначение",
        blank=True,
        default="",
    )
    is_active = models.BooleanField(
        verbose_name="Активен",
        default=True,
    )

    # Параметры входящей почты
    incoming_protocol = models.CharField(
        verbose_name="Протокол входящей почты",
        max_length=10,
        choices=PROTOCOL_CHOICES,
        default=PROTOCOL_IMAP,
    )
    imap_host = models.CharField(
        verbose_name="Сервер IMAP",
        max_length=255,
        default="imap.barkol.ru",
    )
    imap_port = models.IntegerField(
        verbose_name="Порт IMAP",
        default=993,
    )
    imap_security = models.CharField(
        verbose_name="Шифрование IMAP",
        max_length=10,
        choices=SECURITY_CHOICES,
        default=SECURITY_SSL,
    )
    imap_username = models.CharField(
        verbose_name="Логин IMAP",
        max_length=255,
        blank=True,
        default="",
        help_text="Если не указан, используется полный email",
    )
    encrypted_imap_password = models.CharField(
        verbose_name="Зашифрованный пароль IMAP",
        max_length=512,
        blank=True,
        default="",
    )

    # Параметры исходящей почты (SMTP)
    smtp_host = models.CharField(
        verbose_name="Сервер SMTP",
        max_length=255,
        default="sm.barkol.ru",
    )
    smtp_port = models.IntegerField(
        verbose_name="Порт SMTP",
        default=465,
    )
    smtp_security = models.CharField(
        verbose_name="Шифрование SMTP",
        max_length=10,
        choices=SECURITY_CHOICES,
        default=SECURITY_SSL,
    )
    smtp_username = models.CharField(
        verbose_name="Логин SMTP",
        max_length=255,
        blank=True,
        default="",
        help_text="Если не указан, используется логин IMAP или email",
    )
    encrypted_smtp_password = models.CharField(
        verbose_name="Зашифрованный пароль SMTP",
        max_length=512,
        blank=True,
        default="",
        help_text="Если не указан, используется пароль входящей почты",
    )

    display_name = models.CharField(
        verbose_name="Имя отправителя",
        max_length=255,
        blank=True,
        default="",
        help_text="Имя в поле 'От кого' (From). Если пусто, берется наименование ящика",
    )
    signature_html = models.TextField(
        verbose_name="Подпись к письмам (HTML)",
        blank=True,
        default="",
    )

    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="accessible_mailboxes",
        blank=True,
        verbose_name="Сотрудники с доступом",
        help_text="Сотрудники, которым разрешена работа с данным почтовым ящиком",
    )

    created_at = models.DateTimeField(verbose_name="Создан", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="Обновлен", auto_now=True)

    def __str__(self) -> str:
        """Строковое представление ящика.

        Returns:
            str: Название и email.
        """
        return f"{self.name} <{self.email}>"

    def save(self, *args, **kwargs) -> None:
        """Автоматически нормализует домен, логины и отображаемое имя перед сохранением."""
        if "@" in self.email:
            self.email = self.email.strip().lower()
            if not self.domain:
                self.domain = self.email.split("@")[1].strip().lower()
        if not self.imap_username:
            self.imap_username = self.email
        if not self.smtp_username:
            self.smtp_username = self.imap_username
        if not self.display_name:
            self.display_name = self.name
        super().save(*args, **kwargs)

    @property
    def password(self) -> str:
        """Расшифровывает и возвращает пароль входящей почты.

        Returns:
            str: Пароль в открытом виде.
        """
        return decrypt_password(self.encrypted_imap_password)

    @password.setter
    def password(self, raw_pass: str) -> None:
        """Шифрует и сохраняет пароль входящей почты.

        Args:
            raw_pass (str): Пароль в открытом виде.
        """
        self.encrypted_imap_password = encrypt_password(raw_pass)

    def set_password(self, raw_pass: str) -> None:
        """Шифрует и сохраняет пароль входящей почты.

        Args:
            raw_pass (str): Исходный пароль.
        """
        self.encrypted_imap_password = encrypt_password(raw_pass)

    def get_password(self) -> str:
        """Возвращает расшифрованный пароль входящей почты.

        Returns:
            str: Пароль в открытом виде.
        """
        return decrypt_password(self.encrypted_imap_password)

    def set_smtp_password(self, raw_pass: str) -> None:
        """Шифрует и сохраняет пароль исходящей почты SMTP.

        Args:
            raw_pass (str): Исходный пароль.
        """
        self.encrypted_smtp_password = encrypt_password(raw_pass)

    def get_smtp_password(self) -> str:
        """Возвращает расшифрованный пароль SMTP (с fallback на пароль IMAP).

        Returns:
            str: Пароль в открытом виде.
        """
        if self.encrypted_smtp_password:
            return decrypt_password(self.encrypted_smtp_password)
        return self.get_password()

    @property
    def imap_use_ssl(self) -> bool:
        """Флаг использования SSL для IMAP.

        Returns:
            bool: True, если тип шифрования SSL.
        """
        return self.imap_security == self.SECURITY_SSL

    @property
    def smtp_use_ssl(self) -> bool:
        """Флаг использования SSL для SMTP.

        Returns:
            bool: True, если тип шифрования SSL.
        """
        return self.smtp_security == self.SECURITY_SSL

    @property
    def smtp_use_tls(self) -> bool:
        """Флаг использования STARTTLS для SMTP.

        Returns:
            bool: True, если тип шифрования STARTTLS.
        """
        return self.smtp_security == self.SECURITY_STARTTLS


class ScheduledEmail(models.Model):
    """Модель отложенного письма для отправки по расписанию.

    Хранит информацию о письме, ожидающем отправки в заданную дату и время
    через фоновый воркер Celery / Celery Beat.

    Attributes:
        user (ForeignKey): Пользователь, создавший отложенное письмо.
        account (ForeignKey): Персональный почтовый ящик автора.
        mailbox (ForeignKey): Корпоративный или дополнительный почтовый ящик.
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
        verbose_name="Почтовый ящик (персональный)",
        null=True,
        blank=True,
    )
    mailbox = models.ForeignKey(
        Mailbox,
        on_delete=models.CASCADE,
        related_name="scheduled_emails",
        verbose_name="Корпоративный ящик",
        null=True,
        blank=True,
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

        from email.utils import parseaddr
        name_part, email_part = parseaddr(recipients[0])
        first_display = name_part.strip().strip("\"'") or email_part.strip() or recipients[0]

        if len(recipients) == 1:
            return first_display
        return f"{first_display} (+{len(recipients) - 1})"

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

    def get_mail_service_account(self):
        """Возвращает активный объект ящика для отправки (Mailbox или MailAccount).

        Returns:
            Mailbox | MailAccount: Объект ящика для подключения к почтовым сервисам.
        """
        return self.mailbox or self.account

    @property
    def sender_email(self) -> str:
        """Возвращает адрес отправителя.

        Returns:
            str: Корпоративный email ящика.
        """
        acc = self.get_mail_service_account()
        return acc.email if acc else ""

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

    @property
    def security_info(self) -> dict:
        """Возвращает метаданные безопасности и форматирования вложения.

        Returns:
            dict: Словарь с уровнем риска, иконками и разобранным именем.
        """
        from mailbox_app.services.attachment_security import get_attachment_security_info
        if not hasattr(self, "_cached_sec_info"):
            self._cached_sec_info = get_attachment_security_info(self.filename, self.content_type)
        return self._cached_sec_info

    @property
    def name_base(self) -> str:
        """Возвращает базовое имя файла без расширения."""
        return self.security_info.get("name_base", self.filename)

    @property
    def ext(self) -> str:
        """Возвращает расширение файла с точкой."""
        return self.security_info.get("ext", "")

    @property
    def short_base(self) -> str:
        """Возвращает укороченное базовое имя файла для 2-строчного блока."""
        return self.security_info.get("short_base", self.filename)

    @property
    def risk_level(self) -> str:
        """Возвращает уровень риска (high, medium, low, neutral)."""
        return self.security_info.get("risk_level", "low")

    @property
    def risk_label(self) -> str:
        """Возвращает текстовое наименование уровня риска."""
        return self.security_info.get("risk_label", "Безопасный")

    @property
    def risk_tooltip(self) -> str:
        """Возвращает подсказку с описанием уровня риска."""
        return self.security_info.get("risk_tooltip", "")

    @property
    def risk_color_class(self) -> str:
        """Возвращает CSS-класс цвета текста уровня риска."""
        return self.security_info.get("risk_color_class", "text-success")

    @property
    def risk_badge_class(self) -> str:
        """Возвращает CSS-класс бейджа уровня риска."""
        return self.security_info.get("risk_badge_class", "badge bg-success text-white")

    @property
    def risk_icon(self) -> str:
        """Возвращает Boxicons-класс значка щита безопасности."""
        return self.security_info.get("risk_icon", "bx bxs-check-shield")

    @property
    def file_icon(self) -> str:
        """Возвращает Boxicons-класс значка типа файла."""
        return self.security_info.get("file_icon", "bx bx-file text-primary")

    @property
    def preview_type(self) -> str:
        """Возвращает поддерживаемый режим предпросмотра."""
        return self.security_info.get("preview_type", "unsupported")

    def __str__(self) -> str:
        """Строковое представление вложения.

        Returns:
            str: Имя файла и его размер.
        """
        return f"{self.filename} ({self.file_size_human})"


class MailTemplate(models.Model):
    """Модель шаблона письма для быстрого написания и типовых ответов сотрудников.

    Attributes:
        name (CharField): Название шаблона (например, «Согласование документов»).
        subject (CharField): Тема письма по умолчанию.
        body_html (TextField): Текст шаблона.
        is_global (BooleanField): Общекорпоративный шаблон (доступен всем).
        user (ForeignKey): Автор шаблона (для персональных шаблонов).
        created_at (DateTimeField): Дата создания.
        updated_at (DateTimeField): Дата обновления.
    """

    class Meta:
        verbose_name = "Шаблон письма"
        verbose_name_plural = "Шаблоны писем"
        ordering = ["-is_global", "name"]

    name = models.CharField(max_length=255, verbose_name="Название шаблона")
    subject = models.CharField(
        max_length=255, blank=True, default="", verbose_name="Тема по умолчанию"
    )
    body_html = models.TextField(verbose_name="Текст шаблона")
    is_global = models.BooleanField(
        default=False,
        verbose_name="Общекорпоративный шаблон",
        help_text="Если включено, шаблон доступен всем сотрудникам компании",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mail_templates",
        null=True,
        blank=True,
        verbose_name="Автор",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")

    def __str__(self) -> str:
        prefix = "🏢 [Общий] " if self.is_global else "👤 "
        return f"{prefix}{self.name}"


class MailPrintSettings(models.Model):
    """Модель настроек официального печатного бланка письма (для подшивки в дела и архив).

    Настраивается администраторами почты (is_mailbox_admin) для всей организации.

    Attributes:
        organization_name (CharField): Наименование организации.
        header_title (CharField): Заголовок бланка.
        sub_header (CharField): Подзаголовок бланка.
        footer_note (TextField): Примечание в подвале бланка.
        show_logo (BooleanField): Отображать логотип компании.
        updated_at (DateTimeField): Дата последнего изменения.
        updated_by (ForeignKey): Пользователь, обновивший настройки.
    """

    class Meta:
        verbose_name = "Настройки бланка печати почты"
        verbose_name_plural = "Настройки бланка печати почты"

    organization_name = models.CharField(
        max_length=255,
        default="ООО «Авиакомпания «Баркол»",
        verbose_name="Наименование организации",
    )
    header_title = models.CharField(
        max_length=255,
        default="СЛУЖЕБНАЯ КОРПОРАТИВНАЯ ПЕРЕПИСКА",
        verbose_name="Заголовок бланка",
    )
    sub_header = models.CharField(
        max_length=255,
        default="Официальная распечатка электронного сообщения",
        verbose_name="Подзаголовок",
    )
    footer_note = models.TextField(
        default="Электронный документ сформирован в корпоративном портале. Подлинность подтверждена сервером почты.",
        verbose_name="Примечание в подвале",
    )
    show_logo = models.BooleanField(
        default=True,
        verbose_name="Отображать логотип",
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Кто обновил",
    )

    @classmethod
    def get_settings(cls) -> "MailPrintSettings":
        """Возвращает действующие настройки печати (Singleton pattern).

        Returns:
            MailPrintSettings: Единственный экземпляр настроек.
        """
        instance = cls.objects.first()
        if not instance:
            instance = cls.objects.create()
        return instance

    def __str__(self) -> str:
        return f"Настройки бланка: {self.organization_name}"

