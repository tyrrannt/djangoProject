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


class MailAccountSettingsForm(forms.ModelForm):
    """Форма настроек почтового ящика и подписи пользователя."""

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

    def save(self, commit=True):
        """Сохраняет настройки и шифрует пароль при его изменении."""
        instance = super().save(commit=False)
        raw_password = self.cleaned_data.get("password")
        if raw_password:
            instance.set_password(raw_password)
        if commit:
            instance.save()
        return instance
