"""Формы для приложения корпоративной почты."""

from typing import Any, Dict, List, Optional, Tuple, Union
from django import forms
from django.contrib.auth import get_user_model
from django_ckeditor_5.widgets import CKEditor5Widget
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
        widget=CKEditor5Widget(
            attrs={"class": "django_ckeditor_5"},
            config_name="mailbox",
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
        widget=CKEditor5Widget(
            attrs={"class": "django_ckeditor_5"},
            config_name="mailbox",
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
            "signature_html": CKEditor5Widget(
                attrs={"class": "django_ckeditor_5"},
                config_name="mailbox",
            ),
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
            "signature_html": CKEditor5Widget(
                attrs={"class": "django_ckeditor_5"},
                config_name="mailbox",
            ),
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


class StaffModelChoiceField(forms.ModelChoiceField):
    """Поле выбора сотрудника портала с расширенным форматированием ФИО, должности и подразделения."""

    def label_from_instance(self, obj: Any) -> str:
        """Формирует информативную метку для выпадающего списка сотрудников.

        Args:
            obj: Объект пользователя (DataBaseUser).

        Returns:
            str: Форматированная строка с ФИО, логином, должностью и подразделением.
        """
        fio = getattr(obj, "title", "") or obj.get_full_name() or obj.username
        parts = []
        if hasattr(obj, "user_work_profile") and obj.user_work_profile:
            wp = obj.user_work_profile
            if getattr(wp, "job", None):
                parts.append(wp.job.name)
            if getattr(wp, "divisions", None):
                parts.append(wp.divisions.name)
        suffix = f" — {' / '.join(parts)}" if parts else ""
        return f"{fio} ({obj.username}){suffix}"


class KerioUserProvisionForm(forms.Form):
    """Форма создания и настройки учетной записи почтового сервера Kerio Connect и интеграции с порталом."""

    link_django_user = StaffModelChoiceField(
        label="Сотрудник на портале BARKOL",
        queryset=None,
        required=False,
        widget=forms.Select(
            attrs={
                "class": "form-select select2-user",
                "id": "id_link_django_user",
                "data-placeholder": "Выберите сотрудника из базы портала для автозаполнения...",
            }
        ),
        help_text="Выберите сотрудника — его ФИО, логин, должность и телефон заполнятся автоматически",
    )
    create_django_account = forms.BooleanField(
        label="Создать учетную запись MailAccount на портале",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input",
                "id": "id_create_django_account",
            }
        ),
        help_text="Автоматически настроит почтовый клиент для выбранного сотрудника портала",
    )
    login_name = forms.CharField(
        label="Логин (имя ящика)",
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "class": "form-control font-monospace",
                "placeholder": "например: a.abramov",
                "id": "id_kerio_login",
                "required": True,
                "autocomplete": "off",
            }
        ),
        help_text="Корпоративный стандарт: первая буква имени, точка, фамилия на латинице (например: a.abramov)",
    )
    domain_name = forms.CharField(
        label="Почтовый домен",
        max_length=100,
        initial="barkol.ru",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "barkol.ru",
                "id": "id_kerio_domain",
                "required": True,
            }
        ),
        help_text="Корпоративный домен (по умолчанию barkol.ru)",
    )
    password = forms.CharField(
        label="Пароль учетной записи (Kerio Connect / Портал)",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control font-monospace",
                "placeholder": "Введите или сгенерируйте надежный пароль...",
                "id": "id_kerio_password",
                "required": True,
                "autocomplete": "new-password",
            }
        ),
        help_text="Основной пароль для входа в Kerio Connect, веб-почту и корпоративный почтовый клиент (work_email_password)",
    )
    confirm_password = forms.CharField(
        label="Подтверждение основного пароля",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control font-monospace",
                "placeholder": "Повторите введенный пароль...",
                "id": "id_kerio_confirm_password",
                "required": True,
                "autocomplete": "new-password",
            }
        ),
    )
    isp_password = forms.CharField(
        label="Внешний пароль ISPManager / Доставка SMTP",
        required=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control font-monospace",
                "placeholder": "Оставьте пустым для совпадения с основным паролем...",
                "id": "id_kerio_isp_password",
                "autocomplete": "new-password",
            }
        ),
        help_text="Пароль внешнего ящика ISPManager (Reg.ru) и авторизации «Доставка SMTP» / «Загрузка POP3» (work_application_password). Если не указан, совпадает с основным.",
    )
    confirm_isp_password = forms.CharField(
        label="Подтверждение внешнего пароля ISPManager",
        required=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control font-monospace",
                "placeholder": "Повторите внешний пароль ISP...",
                "id": "id_kerio_confirm_isp_password",
                "autocomplete": "new-password",
            }
        ),
    )
    full_name = forms.CharField(
        label="ФИО сотрудника",
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Иванов Иван Иванович",
                "id": "id_kerio_fullname",
            }
        ),
        help_text="Отображаемое имя в адресной книге и письмах",
    )
    first_name = forms.CharField(
        label="Имя",
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Иван",
                "id": "id_kerio_firstname",
            }
        ),
        help_text="Имя сотрудника (вкладка «Контакт»)",
    )
    last_name = forms.CharField(
        label="Фамилия",
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Иванов",
                "id": "id_kerio_lastname",
            }
        ),
        help_text="Фамилия сотрудника (вкладка «Контакт»)",
    )
    middle_name = forms.CharField(
        label="Отчество",
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Иванович",
                "id": "id_kerio_middlename",
            }
        ),
        help_text="Отчество сотрудника (вкладка «Контакт»)",
    )
    job_title = forms.CharField(
        label="Должность",
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Командир ВС Ми-8",
                "id": "id_kerio_jobtitle",
            }
        ),
        help_text="Должность сотрудника (вкладка «Контакт»)",
    )
    department = forms.CharField(
        label="Подразделение / Отдел",
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Летный отряд",
                "id": "id_kerio_department",
            }
        ),
        help_text="Подразделение / отдел (вкладка «Контакт»)",
    )
    company = forms.CharField(
        label="Организация / Компания",
        max_length=255,
        required=False,
        initial="Авиакомпания БАРКОЛ",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Авиакомпания БАРКОЛ",
                "id": "id_kerio_company",
            }
        ),
        help_text="Компания (вкладка «Контакт», по умолчанию Авиакомпания БАРКОЛ)",
    )
    phone = forms.CharField(
        label="Рабочий / внутренний телефон",
        max_length=50,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "123",
                "id": "id_kerio_phone",
            }
        ),
        help_text="Внутренний или рабочий телефон (businessPhone)",
    )
    mobile_phone = forms.CharField(
        label="Мобильный телефон",
        max_length=50,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "+7 (999) 000-00-00",
                "id": "id_kerio_mobilephone",
            }
        ),
        help_text="Мобильный телефон сотрудника (mobilePhone)",
    )
    can_change_password = forms.BooleanField(
        label="Пользователь может менять свой пароль в Kerio Connect Client",
        required=False,
        initial=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input",
                "id": "id_can_change_password",
            }
        ),
        help_text="По умолчанию выключено — сотрудникам запрещено менять пароли самостоятельно в Kerio Connect Client",
    )
    description = forms.CharField(
        label="Служебное описание / примечание",
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Командир ВС Ми-8 / Летный отряд",
                "id": "id_kerio_description",
            }
        ),
        help_text="Служебная отметка или примечание к ящику",
    )
    quota_mb = forms.IntegerField(
        label="Дисковая квота ящика (МБ)",
        required=False,
        min_value=0,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "Например: 5120 (оставьте пустым для безлимита)",
                "id": "id_kerio_quota",
            }
        ),
        help_text="Максимальный размер ящика в мегабайтах (пусто — без ограничений)",
    )
    mailing_lists = forms.MultipleChoiceField(
        label="Списки рассылки Kerio Connect",
        required=False,
        widget=forms.CheckboxSelectMultiple(
            attrs={"class": "form-check-input"}
        ),
        choices=(),
        help_text="Отметьте списки рассылки, в которые следует включить сотрудника",
    )
    configure_pop3_download = forms.BooleanField(
        label="Настроить правило внешней доставки «Загрузка POP3» (сборщик почты)",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input",
                "id": "id_configure_pop3",
            }
        ),
        help_text="Автоматически создаст правило в Kerio Connect (Панель «Доставка» -> «Загрузка POP3»)",
    )
    external_pop3_host = forms.CharField(
        label="Внешний POP3 сервер",
        max_length=255,
        required=False,
        initial="mail.barkol.ru",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "mail.barkol.ru",
                "id": "id_ext_pop3_host",
            }
        ),
    )
    external_pop3_port = forms.IntegerField(
        label="Порт POP3",
        required=False,
        initial=995,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "id": "id_ext_pop3_port",
            }
        ),
    )
    external_pop3_ssl = forms.BooleanField(
        label="Использовать SSL шифрование (порт 995)",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input",
                "id": "id_ext_pop3_ssl",
            }
        ),
    )
    external_leave_messages = forms.BooleanField(
        label="Оставлять копии писем на внешнем сервере",
        required=False,
        initial=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input",
                "id": "id_ext_pop3_leave",
            }
        ),
        help_text="По умолчанию выключено (письма удаляются с внешнего сервера после скачивания в Kerio)",
    )
    configure_smtp_delivery = forms.BooleanField(
        label="Настроить правило исходящей «Доставка SMTP» (Ретрансляция smtp.barkol.ru:587)",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input",
                "id": "id_configure_smtp_delivery",
            }
        ),
        help_text="Автоматически создаст правило в Kerio Connect (Конфигурация -> Сервер SMTP -> Доставка SMTP) с авторизацией SMTP AUTH",
    )
    external_smtp_host = forms.CharField(
        label="Сервер ретрансляции SMTP Relay",
        max_length=255,
        required=False,
        initial="smtp.barkol.ru",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "smtp.barkol.ru",
                "id": "id_ext_smtp_host",
            }
        ),
    )
    external_smtp_port = forms.IntegerField(
        label="Порт SMTP Relay",
        required=False,
        initial=587,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "id": "id_ext_smtp_port",
            }
        ),
    )
    save_email_to_user = forms.BooleanField(
        label="Записать созданный адрес электронной почты в модель пользователя",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input",
                "id": "id_save_email_to_user",
            }
        ),
        help_text="Сохраняет email в профиле сотрудника DataBaseUser на корпоративном портале",
    )
    sync_1c = forms.BooleanField(
        label="Передать данные в 1С (ЗУП)",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input",
                "id": "id_sync_1c",
            }
        ),
        help_text="Синхронизирует корпоративный адрес электронной почты с физическим лицом в 1С через OData",
    )

    def __init__(self, *args, mailing_lists_choices: Optional[List[Tuple[str, str]]] = None, **kwargs) -> None:
        """Инициализирует форму, заполняет queryset активных сотрудников и варианты списков рассылки.

        Args:
            *args: Позиционные аргументы формы.
            mailing_lists_choices (Optional[List[Tuple[str, str]]]): Список пар (ID, Название) списков рассылки.
            **kwargs: Именованные аргументы формы.
        """
        super().__init__(*args, **kwargs)
        User = get_user_model()
        self.fields["link_django_user"].queryset = (
            User.objects.filter(is_active=True)
            .select_related("user_work_profile__job", "user_work_profile__divisions")
            .order_by("last_name", "first_name")
        )
        if mailing_lists_choices is not None:
            self.fields["mailing_lists"].choices = mailing_lists_choices

    def clean(self) -> Dict[str, Any]:
        """Проверяет совпадение паролей, заполняет недостающие контактные поля и валидирует логин.

        Returns:
            Dict[str, Any]: Очищенные валидированные данные формы.

        Raises:
            forms.ValidationError: Если пароли не совпадают или логин некорректен.
        """
        cleaned_data = super().clean()
        link_user = cleaned_data.get("link_django_user")

        from mailbox_app.services.kerio.utils import (
            generate_corporate_mailbox_login,
            get_all_existing_logins_set,
            parse_fio_components,
        )

        if link_user:
            fn, ln, mn = parse_fio_components(link_user)
            if not cleaned_data.get("login_name"):
                existing_logins = get_all_existing_logins_set()
                cleaned_data["login_name"] = generate_corporate_mailbox_login(
                    first_name=fn,
                    last_name=ln,
                    middle_name=mn,
                    existing_logins=existing_logins,
                )
            if not cleaned_data.get("first_name") and fn:
                cleaned_data["first_name"] = fn
            if not cleaned_data.get("last_name") and ln:
                cleaned_data["last_name"] = ln
            if not cleaned_data.get("middle_name") and mn:
                cleaned_data["middle_name"] = mn

            if not cleaned_data.get("full_name"):
                cleaned_data["full_name"] = getattr(link_user, "title", "") or link_user.get_full_name() or link_user.username

            if hasattr(link_user, "user_work_profile") and link_user.user_work_profile:
                wp = link_user.user_work_profile
                if not cleaned_data.get("job_title") and getattr(wp, "job", None):
                    cleaned_data["job_title"] = wp.job.name
                if not cleaned_data.get("department") and getattr(wp, "divisions", None):
                    cleaned_data["department"] = wp.divisions.name
                if not cleaned_data.get("phone") and getattr(wp, "internal_phone", None):
                    cleaned_data["phone"] = wp.internal_phone

            if not cleaned_data.get("mobile_phone") and getattr(link_user, "personal_phone", None):
                cleaned_data["mobile_phone"] = link_user.personal_phone

            if not cleaned_data.get("description"):
                desc_parts: List[str] = []
                if cleaned_data.get("job_title"):
                    desc_parts.append(cleaned_data["job_title"])
                if cleaned_data.get("department"):
                    desc_parts.append(cleaned_data["department"])
                if cleaned_data.get("phone"):
                    desc_parts.append(f"вн. {cleaned_data['phone']}")
                elif cleaned_data.get("mobile_phone"):
                    desc_parts.append(f"тел. {cleaned_data['mobile_phone']}")
                cleaned_data["description"] = " / ".join(desc_parts)

        # Синхронизация ФИО и компонентов имени
        full_name_val = cleaned_data.get("full_name", "").strip()
        fn_val = cleaned_data.get("first_name", "").strip()
        ln_val = cleaned_data.get("last_name", "").strip()
        mn_val = cleaned_data.get("middle_name", "").strip()

        if full_name_val and (not fn_val or not ln_val):
            parsed_fn, parsed_ln, parsed_mn = parse_fio_components(full_name_val)
            if not fn_val and parsed_fn:
                cleaned_data["first_name"] = parsed_fn
            if not ln_val and parsed_ln:
                cleaned_data["last_name"] = parsed_ln
            if not mn_val and parsed_mn:
                cleaned_data["middle_name"] = parsed_mn
        elif not full_name_val and (fn_val or ln_val):
            composed_fio = " ".join([p for p in [ln_val, fn_val, mn_val] if p]).strip()
            cleaned_data["full_name"] = composed_fio

        login = cleaned_data.get("login_name", "").strip().lower()
        if "@" in login:
            login = login.split("@")[0]
            cleaned_data["login_name"] = login

        pwd = cleaned_data.get("password")
        pwd_confirm = cleaned_data.get("confirm_password")

        if pwd and pwd_confirm and pwd != pwd_confirm:
            self.add_error("confirm_password", "Введенные основные пароли не совпадают.")

        isp_pwd = cleaned_data.get("isp_password")
        isp_pwd_confirm = cleaned_data.get("confirm_isp_password")

        if isp_pwd and isp_pwd_confirm and isp_pwd != isp_pwd_confirm:
            self.add_error("confirm_isp_password", "Введенные внешние пароли ISPManager не совпадают.")

        return cleaned_data


class KerioUserEditForm(forms.Form):
    """Форма редактирования параметров существующего пользователя в Kerio Connect."""

    full_name = forms.CharField(
        label="ФИО сотрудника",
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Иванов Иван Иванович",
                "id": "id_edit_fullname",
            }
        ),
    )
    first_name = forms.CharField(
        label="Имя",
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Иван",
                "id": "id_edit_firstname",
            }
        ),
    )
    last_name = forms.CharField(
        label="Фамилия",
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Иванов",
                "id": "id_edit_lastname",
            }
        ),
    )
    middle_name = forms.CharField(
        label="Отчество",
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Иванович",
                "id": "id_edit_middlename",
            }
        ),
    )
    job_title = forms.CharField(
        label="Должность",
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Командир ВС Ми-8",
                "id": "id_edit_jobtitle",
            }
        ),
    )
    department = forms.CharField(
        label="Подразделение / Отдел",
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Летный отряд",
                "id": "id_edit_department",
            }
        ),
    )
    company = forms.CharField(
        label="Организация / Компания",
        max_length=255,
        required=False,
        initial="Авиакомпания БАРКОЛ",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Авиакомпания БАРКОЛ",
                "id": "id_edit_company",
            }
        ),
    )
    phone = forms.CharField(
        label="Рабочий / внутренний телефон",
        max_length=50,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "123",
                "id": "id_edit_phone",
            }
        ),
    )
    mobile_phone = forms.CharField(
        label="Мобильный телефон",
        max_length=50,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "+7 (999) 000-00-00",
                "id": "id_edit_mobilephone",
            }
        ),
    )
    description = forms.CharField(
        label="Служебное описание / примечание",
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Должность или подразделение...",
                "id": "id_edit_description",
            }
        ),
    )
    quota_mb = forms.IntegerField(
        label="Дисковая квота (МБ)",
        required=False,
        min_value=0,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "Без ограничений (0 или пусто)",
                "id": "id_edit_quota",
            }
        ),
        help_text="Оставьте пустым для снятия ограничений по размеру",
    )
    can_change_password = forms.BooleanField(
        label="Пользователь может менять свой пароль в Kerio Connect Client",
        required=False,
        initial=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input",
                "id": "id_edit_can_change_password",
            }
        ),
        help_text="Разрешить ли сотруднику менять свой пароль самостоятельно в Kerio Connect Client",
    )
    mailing_lists = forms.MultipleChoiceField(
        label="Списки рассылки Kerio Connect",
        required=False,
        widget=forms.CheckboxSelectMultiple(
            attrs={"class": "form-check-input"}
        ),
        choices=(),
        help_text="Отметьте списки рассылки, в которые включен сотрудник",
    )
    is_enabled = forms.BooleanField(
        label="Учетная запись активна",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input",
                "id": "id_edit_is_enabled",
            }
        ),
        help_text="При отключении вход в почту и прием корреспонденции блокируются",
    )
    sync_1c = forms.BooleanField(
        label="Синхронизировать email с профилем сотрудника и 1С (ЗУП)",
        required=False,
        initial=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input",
                "id": "id_edit_sync_1c",
            }
        ),
        help_text="При включении обновит email в профиле DataBaseUser на портале и отправит данные в 1С (ЗУП)",
    )

    def __init__(self, *args, mailing_lists_choices: Optional[List[Tuple[str, str]]] = None, **kwargs) -> None:
        """Инициализирует форму редактирования пользователя.

        Args:
            *args: Позиционные аргументы.
            mailing_lists_choices (Optional[List[Tuple[str, str]]]): Список пар (ID, Название) рассылок.
            **kwargs: Именованные аргументы.
        """
        super().__init__(*args, **kwargs)
        if mailing_lists_choices is not None:
            self.fields["mailing_lists"].choices = mailing_lists_choices

    def clean(self) -> Dict[str, Any]:
        """Синхронизирует full_name и контактные поля при редактировании.

        Returns:
            Dict[str, Any]: Валидированные данные.
        """
        cleaned_data = super().clean()
        from mailbox_app.services.kerio.utils import parse_fio_components

        full_name_val = cleaned_data.get("full_name", "").strip()
        fn_val = cleaned_data.get("first_name", "").strip()
        ln_val = cleaned_data.get("last_name", "").strip()
        mn_val = cleaned_data.get("middle_name", "").strip()

        if full_name_val and (not fn_val or not ln_val):
            parsed_fn, parsed_ln, parsed_mn = parse_fio_components(full_name_val)
            if not fn_val and parsed_fn:
                cleaned_data["first_name"] = parsed_fn
            if not ln_val and parsed_ln:
                cleaned_data["last_name"] = parsed_ln
            if not mn_val and parsed_mn:
                cleaned_data["middle_name"] = parsed_mn
        elif not full_name_val and (fn_val or ln_val):
            composed_fio = " ".join([p for p in [ln_val, fn_val, mn_val] if p]).strip()
            cleaned_data["full_name"] = composed_fio

        return cleaned_data


class KerioUserPasswordResetForm(forms.Form):
    """Форма смены и сброса пароля пользователя почтового сервера Kerio Connect."""

    new_password = forms.CharField(
        label="Новый пароль",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control font-monospace",
                "placeholder": "Введите новый пароль...",
                "required": True,
                "autocomplete": "new-password",
            }
        ),
    )
    confirm_password = forms.CharField(
        label="Подтверждение нового пароля",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control font-monospace",
                "placeholder": "Повторите новый пароль...",
                "required": True,
                "autocomplete": "new-password",
            }
        ),
    )

    def clean(self) -> Dict[str, Any]:
        """Проверяет совпадение нового пароля и подтверждения.

        Returns:
            Dict[str, Any]: Очищенные валидированные данные.

        Raises:
            forms.ValidationError: Если пароли не совпадают.
        """
        cleaned_data = super().clean()
        pwd = cleaned_data.get("new_password")
        pwd_confirm = cleaned_data.get("confirm_password")
        if pwd and pwd_confirm and pwd != pwd_confirm:
            self.add_error("confirm_password", "Введенные пароли не совпадают.")
        return cleaned_data


class KerioUserIspPasswordResetForm(forms.Form):
    """Форма смены и сброса внешнего пароля ISPManager / Доставка SMTP (work_application_password)."""

    new_isp_password = forms.CharField(
        label="Новый пароль ISPManager / Доставка SMTP",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control font-monospace",
                "placeholder": "Введите новый внешний пароль ISP...",
                "required": True,
                "autocomplete": "new-password",
            }
        ),
        help_text="Синхронно обновится на сервере ISPManager (Reg.ru), в правилах «Доставка SMTP» / «Загрузка POP3» и в профиле сотрудника.",
    )
    confirm_isp_password = forms.CharField(
        label="Подтверждение нового внешнего пароля",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control font-monospace",
                "placeholder": "Повторите новый внешний пароль...",
                "required": True,
                "autocomplete": "new-password",
            }
        ),
    )

    def clean(self) -> Dict[str, Any]:
        """Проверяет совпадение нового внешнего пароля ISPManager и подтверждения.

        Returns:
            Dict[str, Any]: Очищенные валидированные данные.

        Raises:
            forms.ValidationError: Если пароли не совпадают.
        """
        cleaned_data = super().clean()
        pwd = cleaned_data.get("new_isp_password")
        pwd_confirm = cleaned_data.get("confirm_isp_password")
        if pwd and pwd_confirm and pwd != pwd_confirm:
            self.add_error("confirm_isp_password", "Введенные внешние пароли ISPManager не совпадают.")
        return cleaned_data

