"""Формы для приложения корпоративной почты."""

from django import forms
from mailbox_app.models import MailAccount


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
