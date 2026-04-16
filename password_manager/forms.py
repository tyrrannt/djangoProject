# password_manager/forms.py
"""
Формы приложения password_manager.

Реализует валидацию паролей, интеграцию с генератором,
проверку ключевой фразы и атомарное создание/обновление записей
с автоматическим шифрованием и ведением истории.

Архитектурные заметки (Этап 3)
Интеграция с генератором: Поле raw_password имеет id="id_raw_password" и data-toggle="password-input". На этапе шаблонов JS будет вешаться на этот атрибут: при клике "Сгенерировать" скрипт вызовет API или локальную функцию PasswordGenerator.generate(), запишет результат в #id_raw_password и скроет/покажет настройки. Форма валидирует итоговое значение на сервере.
Атомарность: @transaction.atomic гарантирует, что если создание истории или обновление created_at упадёт, основная запись не сохранится в повреждённом состоянии.
select_for_update(): При обновлении используем блокировку строки, чтобы избежать race condition при параллельных запросах к одному паролю.
Валидация: Строгая проверка сложности соответствует требованиям этапа. Можно расширить regex под ваши стандарты (например, спецсимволы обязательны).
Готовность к CRUD: Форма полностью готова к использованию в CreateView/UpdateView. Метод save() автоматически выполняет шифрование и аудит.
"""

import re
from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import EncryptedPassword, PasswordGroup, PasswordHistory
from .services import PasswordService


class EncryptedPasswordForm(forms.ModelForm):
    """
    Основная форма CRUD для записей паролей.
    Интегрирует поле ключевой фразы и сырого пароля для последующего шифрования.
    """
    passphrase = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': _('Введите вашу ключевую фразу'),
            'autocomplete': 'new-password'
        }),
        label=_("Ключевая фраза"),
        required=True,
        help_text=_("Необходима для шифрования/дешифрования. Должна совпадать с установленной в профиле.")
    )
    raw_password = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Пароль (будет вставлен генератором или введён вручную)'),
            'id': 'id_raw_password',  # Точка входа для JavaScript-генератора
            'data-toggle': 'password-input'
        }),
        label=_("Пароль"),
        required=True,
        help_text=_("Будет автоматически зашифрован перед сохранением в БД.")
    )

    class Meta:
        model = EncryptedPassword
        fields = ['resource_type', 'url', 'login', 'group', 'notes']
        widgets = {
            'resource_type': forms.Select(attrs={'class': 'form-select'}),
            'url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://example.com',
                'pattern': 'https?://.+'
            }),
            'login': forms.TextInput(attrs={'class': 'form-control'}),
            'group': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        # Извлекаем request для фильтрации групп и доступа к user
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and hasattr(self.request, 'user'):
            # Оптимизация: показываем только группы текущего пользователя
            self.fields['group'].queryset = PasswordGroup.objects.filter(
                owner=self.request.user
            ).select_related('parent_group')

    def clean_passphrase(self):
        """Проверяет корректность ключевой фразы пользователя."""
        passphrase = self.cleaned_data.get('passphrase')
        user = self.request.user
        if not PasswordService.verify_passphrase(user, passphrase):
            raise ValidationError(
                _("Неверная ключевая фраза или она ещё не установлена в настройках профиля.")
            )
        return passphrase

    def clean_raw_password(self):
        """Валидация сложности пароля согласно требованиям безопасности."""
        password = self.cleaned_data.get('raw_password')
        if len(password) < 8:
            raise ValidationError(_("Минимальная длина пароля — 8 символов."))
        if not re.search(r'[A-Z]', password):
            raise ValidationError(_("Требуется минимум одна заглавная латинская буква (A-Z)."))
        if not re.search(r'[a-z]', password):
            raise ValidationError(_("Требуется минимум одна строчная латинская буква (a-z)."))
        if not re.search(r'\d', password):
            raise ValidationError(_("Требуется минимум одна цифра (0-9)."))
        return password

    @transaction.atomic
    def save(self, commit=True):
        """
        Переопределяет сохранение для двойного шифрования и создания истории.

        Логика:
        1. Получает старый экземпляр (если обновление).
        2. Шифрует пароль ключом пользователя и мастер-ключом.
        3. Сохраняет новый экземпляр.
        4. Создаёт запись в PasswordHistory.
        5. Обновляет created_at согласно ТЗ.
        """
        instance = super().save(commit=False)
        user = self.request.user
        passphrase = self.cleaned_data['passphrase']
        raw_password = self.cleaned_data['raw_password']
        is_update = instance.pk is not None

        old_record = None
        if is_update:
            # Фиксируем состояние до изменения для истории
            old_record = EncryptedPassword.objects.select_for_update().get(pk=instance.pk)

        # 1. Шифрование для пользователя
        instance.encrypted_password = PasswordService.encrypt_with_passphrase(
            raw_password, user, passphrase
        )
        # 2. Шифрование для администратора
        instance.admin_encrypted_copy = PasswordService.encrypt_for_admin(raw_password)

        if commit:
            instance.save()

            # 3. Ведение истории (только при обновлении)
            if old_record:
                PasswordHistory.objects.create(
                    encrypted_password=old_record.encrypted_password,
                    admin_encrypted_copy=old_record.admin_encrypted_copy,
                    resource_type=old_record.resource_type,
                    url=old_record.url,
                    login=old_record.login,
                    notes=old_record.notes,
                    original_record=instance,
                    owner=user
                )
                # 4. Обновление created_at согласно ТЗ
                instance.created_at = timezone.now()
                instance.save(update_fields=['created_at'])

        return instance


class UserKeySetupForm(forms.Form):
    """Форма первичной настройки/смены ключевой фразы пользователя."""
    passphrase = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label=_("Новая ключевая фраза"),
        required=True
    )
    confirm_passphrase = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label=_("Подтверждение фразы"),
        required=True
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('passphrase') != cleaned.get('confirm_passphrase'):
            raise ValidationError(_("Ключевые фразы не совпадают."))
        return cleaned

    def save(self, user):
        PasswordService.setup_or_update_key(user, self.cleaned_data['passphrase'])
