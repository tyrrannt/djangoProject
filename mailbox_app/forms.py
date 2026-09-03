"""Формы для приложения корпоративной почты."""

from django import forms
from django.contrib.auth import get_user_model
from mailbox_app.models import MailAccount, Mailbox, MailContact, MailPrintSettings, MailTemplate
from mailbox_app.services.mailbox_defaults import DEFAULT_DOMAIN, get_domain_defaults


class MultipleFileInput(forms.ClearableFileInput):
    """Виджет для загрузки нескольких файлов одновременно."""

    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Поле формы для обработки массива файлов."""

    def __init__(self, *args, **kwargs):
        """Инициализация поля с виджетом множественной загрузки."""
        kwargs.setdefault("widget", MultipleFileInput(attrs={"class": "form-control", "multiple": True}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        """Валидация списка загруженных файлов."""
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = single_file_clean(data, initial)
        return result


class MailComposeForm(forms.Form):
    """Форма написания и отправки электронного письма."""

    to = forms.CharField(
        label="Кому",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Введите email или выберите сотрудника...",
                "id": "mailRecipientInput",
                "required": True,
            }
        ),
    )
    cc = forms.CharField(
        label="Копия",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Email адреса через запятую...",
            }
        ),
    )
    bcc = forms.CharField(
        label="Скрытая копия",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Email адреса через запятую...",
            }
        ),
    )
    subject = forms.CharField(
        label="Тема",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Тема сообщения...",
            }
        ),
    )
    body_html = forms.CharField(
        label="Текст сообщения",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control summernote",
                "rows": 12,
                "placeholder": "Текст сообщения...",
            }
        ),
    )
    attachments = MultipleFileField(
        label="Вложения",
        required=False,
    )
    send_mode = forms.CharField(
        required=False,
        initial="now",
        widget=forms.HiddenInput(attrs={"id": "mailSendMode"}),
    )
    scheduled_at = forms.DateTimeField(
        label="Запланированное время",
        required=False,
        widget=forms.HiddenInput(attrs={"id": "mailScheduledAtInput"}),
        input_formats=[
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d.%m.%Y %H:%M",
        ],
    )

    def clean(self):
        """Выполняет кросс-валидацию полей формы с проверкой времени отправки.

        Returns:
            dict: Очищенные данные формы.

        Raises:
            forms.ValidationError: При некорректном времени отправки по расписанию.
        """
        from django.utils import timezone

        cleaned_data = super().clean()
        send_mode = cleaned_data.get("send_mode") or "now"
        scheduled_at = cleaned_data.get("scheduled_at")

        if send_mode == "scheduled":
            if not scheduled_at:
                self.add_error("scheduled_at", "Укажите дату и время запланированной отправки.")
                raise forms.ValidationError("Необходимо указать дату и время запланированной отправки.")
            if timezone.is_naive(scheduled_at):
                scheduled_at = timezone.make_aware(scheduled_at, timezone.get_current_timezone())
            if scheduled_at <= timezone.now():
                self.add_error("scheduled_at", "Время запланированной отправки должно быть в будущем.")
                raise forms.ValidationError("Время запланированной отправки должно быть в будущем.")
            cleaned_data["scheduled_at"] = scheduled_at

        return cleaned_data


class ScheduledEmailEditForm(forms.Form):
    """Форма редактирования параметров и текста запланированного письма."""

    to = forms.CharField(
        label="Кому",
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "email@example.com",
                "id": "mailRecipientInput",
                "autocomplete": "off",
            }
        ),
    )
    cc = forms.CharField(
        label="Копия",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Копия адресатам...",
                "autocomplete": "off",
            }
        ),
    )
    bcc = forms.CharField(
        label="Скрытая копия",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Скрытая копия адресатам...",
                "autocomplete": "off",
            }
        ),
    )
    subject = forms.CharField(
        label="Тема",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Тема сообщения",
            }
        ),
    )
    body_html = forms.CharField(
        label="Текст сообщения",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control summernote",
                "rows": 12,
                "placeholder": "Текст сообщения...",
            }
        ),
    )
    scheduled_at = forms.DateTimeField(
        label="Запланированное время",
        required=False,
        widget=forms.HiddenInput(attrs={"id": "mailScheduledAtInput"}),
        input_formats=[
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d.%m.%Y %H:%M",
        ],
    )
    send_mode = forms.CharField(
        required=False,
        initial="scheduled",
        widget=forms.HiddenInput(attrs={"id": "mailSendMode"}),
    )
    attachments = MultipleFileField(
        label="Новые вложения",
        required=False,
    )

    def clean(self):
        """Выполняет валидацию даты отправки.

        Returns:
            dict: Очищенные данные формы.

        Raises:
            forms.ValidationError: При некорректном времени отправки.
        """
        from django.utils import timezone

        cleaned_data = super().clean()
        send_mode = cleaned_data.get("send_mode") or "scheduled"
        scheduled_at = cleaned_data.get("scheduled_at")

        if send_mode == "scheduled":
            if not scheduled_at:
                self.add_error("scheduled_at", "Укажите дату и время запланированной отправки.")
                raise forms.ValidationError("Необходимо указать дату и время запланированной отправки.")
            if timezone.is_naive(scheduled_at):
                scheduled_at = timezone.make_aware(scheduled_at, timezone.get_current_timezone())
            if scheduled_at <= timezone.now():
                self.add_error("scheduled_at", "Время запланированной отправки должно быть в будущем.")
                raise forms.ValidationError("Время запланированной отправки должно быть в будущем.")
            cleaned_data["scheduled_at"] = scheduled_at

        return cleaned_data


class MailAccountSettingsForm(forms.ModelForm):
    """Форма настроек почтового ящика и подписи пользователя.

    Позволяет пользователям изменять имя отправителя, пароль и подпись.
    Настройки серверов входящей (IMAP) и исходящей (SMTP) почты
    доступны для редактирования исключительно суперпользователям (is_superuser).

    Attributes:
        password (CharField): Поле для ввода нового пароля ящика.
        is_superuser (bool): Флаг наличия прав суперпользователя.
    """

    password = forms.CharField(
        label="Пароль от почты",
        required=False,
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "Оставьте пустым, если не меняется"}
        ),
    )

    class Meta:
        model = MailAccount
        fields = [
            "email",
            "display_name",
            "imap_host",
            "imap_port",
            "smtp_host",
            "smtp_port",
            "signature_html",
        ]
        widgets = {
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "display_name": forms.TextInput(attrs={"class": "form-control"}),
            "imap_host": forms.TextInput(attrs={"class": "form-control"}),
            "imap_port": forms.NumberInput(attrs={"class": "form-control"}),
            "smtp_host": forms.TextInput(attrs={"class": "form-control"}),
            "smtp_port": forms.NumberInput(attrs={"class": "form-control"}),
            "signature_html": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }

    def __init__(self, *args, is_superuser: bool = False, **kwargs):
        """Инициализация формы с разграничением прав на серверные настройки.

        Args:
            *args: Позиционные аргументы формы.
            is_superuser (bool): Флаг прав суперадминистратора (по умолчанию False).
            **kwargs: Именованные аргументы формы.
        """
        super().__init__(*args, **kwargs)
        self.is_superuser = is_superuser
        if not is_superuser:
            # Для не-суперадминистраторов полностью исключаем поля конфигурации серверов
            for server_field in ["imap_host", "imap_port", "smtp_host", "smtp_port"]:
                if server_field in self.fields:
                    del self.fields[server_field]
            # Email доступен только для чтения
            if "email" in self.fields:
                self.fields["email"].widget.attrs["readonly"] = True

    def save(self, commit=True):
        """Сохраняет настройки и шифрует пароль при его изменении.

        Args:
            commit (bool): Сохранять ли объект в базу данных.

        Returns:
            MailAccount: Сохраненный инстанс почтового аккаунта.
        """
        instance = super().save(commit=False)
        raw_password = self.cleaned_data.get("password")
        if raw_password:
            instance.set_password(raw_password)
        if commit:
            instance.save()
        return instance


class MailboxAdminForm(forms.ModelForm):
    """Форма создания и редактирования корпоративного или дополнительного почтового ящика.

    Позволяет администратору настраивать параметры подключения к IMAP и SMTP,
    привязывать сотрудников с доступом Many-to-Many и управлять безопасностью паролей.
    """

    raw_imap_password = forms.CharField(
        label="Пароль IMAP",
        widget=forms.PasswordInput(
            render_value=True,
            attrs={
                "class": "form-control",
                "id": "id_imap_password",
                "placeholder": "Введите пароль...",
                "autocomplete": "new-password",
            },
        ),
        required=False,
        help_text="Оставьте пустым, если не требуется менять текущий пароль",
    )
    raw_smtp_password = forms.CharField(
        label="Пароль SMTP",
        widget=forms.PasswordInput(
            render_value=True,
            attrs={
                "class": "form-control",
                "id": "id_smtp_password",
                "placeholder": "Пароль SMTP...",
                "autocomplete": "new-password",
            },
        ),
        required=False,
        help_text="Если не указан или включено 'Совпадает с IMAP', используется пароль IMAP",
    )
    smtp_same_as_imap = forms.BooleanField(
        label="Параметры авторизации SMTP совпадают с IMAP",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_smtp_same_as_imap"}),
    )

    class Meta:
        model = Mailbox
        fields = [
            "name",
            "email",
            "domain",
            "description",
            "is_active",
            "incoming_protocol",
            "imap_host",
            "imap_port",
            "imap_security",
            "imap_username",
            "smtp_host",
            "smtp_port",
            "smtp_security",
            "smtp_username",
            "display_name",
            "signature_html",
            "users",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Отдел кадров", "required": True}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "hr@barkol.ru", "id": "id_email", "required": True}),
            "domain": forms.TextInput(attrs={"class": "form-control", "placeholder": "barkol.ru", "id": "id_domain"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Назначение почтового ящика..."}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "incoming_protocol": forms.Select(attrs={"class": "form-select", "id": "id_incoming_protocol"}),
            "imap_host": forms.TextInput(attrs={"class": "form-control", "id": "id_imap_host"}),
            "imap_port": forms.NumberInput(attrs={"class": "form-control", "id": "id_imap_port"}),
            "imap_security": forms.Select(attrs={"class": "form-select", "id": "id_imap_security"}),
            "imap_username": forms.TextInput(attrs={"class": "form-control", "id": "id_imap_username", "placeholder": "hr@barkol.ru"}),
            "smtp_host": forms.TextInput(attrs={"class": "form-control", "id": "id_smtp_host"}),
            "smtp_port": forms.NumberInput(attrs={"class": "form-control", "id": "id_smtp_port"}),
            "smtp_security": forms.Select(attrs={"class": "form-select", "id": "id_smtp_security"}),
            "smtp_username": forms.TextInput(attrs={"class": "form-control", "id": "id_smtp_username", "placeholder": "hr@barkol.ru"}),
            "display_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Отдел кадров ООО 'Баркол'"}),
            "signature_html": forms.Textarea(attrs={"class": "form-control summernote-signature", "rows": 4}),
            "users": forms.SelectMultiple(attrs={"class": "form-select select2-users", "style": "width: 100%; min-height: 180px;"}),
        }

    def __init__(self, *args, **kwargs):
        """Инициализирует форму с предзаполнением паролей и доменных пресетов."""
        super().__init__(*args, **kwargs)
        User = get_user_model()
        self.fields["users"].queryset = User.objects.filter(is_active=True).order_by("last_name", "first_name")
        self.fields["users"].label = "Сотрудники с доступом"

        if self.instance and self.instance.pk:
            self.fields["raw_imap_password"].initial = self.instance.get_password()
            self.fields["raw_smtp_password"].initial = self.instance.get_smtp_password()
            if self.instance.encrypted_smtp_password and self.instance.encrypted_smtp_password != self.instance.encrypted_imap_password:
                self.fields["smtp_same_as_imap"].initial = False
        else:
            defaults = get_domain_defaults(DEFAULT_DOMAIN)
            self.initial.setdefault("domain", defaults["domain"])
            self.initial.setdefault("imap_host", defaults["imap_host"])
            self.initial.setdefault("imap_port", defaults["imap_port"])
            self.initial.setdefault("imap_security", defaults["imap_security"])
            self.initial.setdefault("smtp_host", defaults["smtp_host"])
            self.initial.setdefault("smtp_port", defaults["smtp_port"])
            self.initial.setdefault("smtp_security", defaults["smtp_security"])

    def save(self, commit=True):
        """Сохраняет ящик с безопасным шифрованием паролей IMAP и SMTP.

        Args:
            commit (bool): Сохранять ли объект в базу данных.

        Returns:
            Mailbox: Сохраненный инстанс корпоративного ящика.
        """
        instance = super().save(commit=False)
        raw_imap = self.cleaned_data.get("raw_imap_password")
        raw_smtp = self.cleaned_data.get("raw_smtp_password")
        same_as_imap = self.cleaned_data.get("smtp_same_as_imap")

        if raw_imap:
            instance.set_password(raw_imap)

        if same_as_imap:
            instance.smtp_username = instance.imap_username
            if raw_imap:
                instance.set_smtp_password(raw_imap)
            elif instance.encrypted_imap_password:
                instance.encrypted_smtp_password = instance.encrypted_imap_password
        elif raw_smtp:
            instance.set_smtp_password(raw_smtp)

        if commit:
            instance.save()
            self.save_m2m()
        return instance


class MailContactForm(forms.ModelForm):
    """Форма добавления и редактирования контакта в адресной книге сотрудника."""

    class Meta:
        model = MailContact
        fields = ["name", "email"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Иванов Иван Иванович или ООО «Компания»",
                    "required": True,
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "user@example.com",
                    "required": True,
                }
            ),
        }


class MailPrintSettingsForm(forms.ModelForm):
    """Форма настройки официального печатного бланка письма для администраторов почты."""

    class Meta:
        model = MailPrintSettings
        fields = [
            "organization_name",
            "header_title",
            "sub_header",
            "footer_note",
            "show_logo",
        ]
        widgets = {
            "organization_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "ООО «Авиакомпания «Баркол»"}
            ),
            "header_title": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "СЛУЖЕБНАЯ КОРПОРАТИВНАЯ ПЕРЕПИСКА"}
            ),
            "sub_header": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Официальная распечатка электронного сообщения"}
            ),
            "footer_note": forms.Textarea(
                attrs={"class": "form-control", "rows": 3}
            ),
            "show_logo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class MailTemplateForm(forms.ModelForm):
    """Форма создания и редактирования шаблона быстрого ответа / письма."""

    class Meta:
        model = MailTemplate
        fields = ["name", "subject", "body_html", "is_global"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Название шаблона (например, Согласование акта)"}
            ),
            "subject": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Тема письма по умолчанию (необязательно)"}
            ),
            "body_html": forms.Textarea(
                attrs={"class": "form-control", "rows": 6, "placeholder": "Текст сообщения шаблона..."}
            ),
            "is_global": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

