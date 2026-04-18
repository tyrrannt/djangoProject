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
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from administration_app.utils import make_custom_field
from .models import EncryptedPassword, PasswordGroup, PasswordHistory
from .services import PasswordService


class EncryptedPasswordForm(forms.ModelForm):
    """
    Основная форма CRUD для записей паролей.
    Интегрирует поле ключевой фразы и сырого пароля для последующего шифрования.
    """
    use_saved_passphrase = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'use_saved_passphrase',
            'data-toggle': 'passphrase-toggle'
        }),
        label=_("Я помню свою ключевую фразу"),
        required=False,
        initial=True,
        help_text=_("Если отмечено, фраза будет взята из вашего профиля. Снимите галочку, чтобы ввести фразу вручную.")
    )
    passphrase = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': _('Введите вашу ключевую фразу'),
            'autocomplete': 'new-password'
        }),
        label=_("Ключевая фраза"),
        required=False,
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
        # Извлекаем request и user из kwargs
        self.request = kwargs.pop('request', None)
        user = kwargs.pop('user', None)  # Извлекаем user если передан

        super().__init__(*args, **kwargs)

        # Определяем, какой объект user использовать
        current_user = user or (self.request.user if self.request and hasattr(self.request, 'user') else None)

        if current_user:
            # Оптимизация: показываем только группы текущего пользователя
            self.fields['group'].queryset = PasswordGroup.objects.filter(
                owner=current_user
            ).select_related('parent_group')

            # Делаем поле group необязательным
            self.fields['group'].required = False
            self.fields['group'].empty_label = _('— Без группы —')

            # Проверяем, есть ли у пользователя сохраненная ключевая фраза
            has_saved_passphrase = hasattr(current_user, 'encryption_key_hash') and current_user.encryption_key_hash
            if has_saved_passphrase:
                # Если есть сохраненная фраза, по умолчанию используем её
                self.fields['use_saved_passphrase'].initial = True
                self.fields['passphrase'].required = False
                self.fields['passphrase'].widget.attrs['placeholder'] = _(
                    'Необязательно (будет использована сохраненная)')
                self.fields['passphrase'].help_text = _("Оставьте пустым, если хотите использовать сохраненную фразу.")
            else:
                # Если нет сохраненной фразы, скрываем переключатель и требуем ввод
                self.fields['use_saved_passphrase'].initial = False
                self.fields['use_saved_passphrase'].widget = forms.HiddenInput()
                self.fields['passphrase'].required = True
                self.fields['passphrase'].help_text = _(
                    "Установите ключевую фразу в настройках профиля или введите её здесь.")
                messages.warning(self.request, "У вас не установлена ключевая фраза. Пожалуйста, введите её вручную.")

        # Обрабатываем selected_group, если он передан
        if self.data and self.data.get('selected_group'):
            selected_group_id = self.data.get('selected_group')
            if selected_group_id and selected_group_id != '':
                try:
                    group = PasswordGroup.objects.get(id=selected_group_id, owner=current_user)
                    # Устанавливаем значение в поле group
                    self.initial['group'] = group
                    self.fields['group'].initial = group
                except PasswordGroup.DoesNotExist:
                    pass

        for field in self.fields:
            make_custom_field(self.fields[field])

    def clean_passphrase(self):
        """Проверяет корректность ключевой фразы пользователя."""
        use_saved = self.cleaned_data.get('use_saved_passphrase', False)
        passphrase = self.cleaned_data.get('passphrase')

        # Получаем пользователя
        user = None
        if hasattr(self, 'request') and self.request:
            user = self.request.user
        elif hasattr(self, 'user'):
            user = self.user

        if not user:
            raise ValidationError(_("Пользователь не определен."))

        # Проверяем, есть ли у пользователя сохраненная фраза
        has_saved_passphrase = hasattr(user, 'encryption_key_hash') and user.encryption_key_hash

        if use_saved and has_saved_passphrase:
            # Если используем сохраненную фразу, но фраза не в сессии
            # Требуем ввод для подтверждения (безопасность)
            if not passphrase:
                raise ValidationError(
                    _("Для подтверждения вашей личности, пожалуйста, введите ключевую фразу.")
                )

            # Проверяем фразу
            if not PasswordService.verify_passphrase(user, passphrase):
                raise ValidationError(
                    _("Неверная ключевая фраза.")
                )

            return passphrase

        # Если не используем сохраненную, проверяем введенную
        if not passphrase:
            raise ValidationError(_("Пожалуйста, введите ключевую фразу."))

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

    def clean(self):
        """Дополнительная валидация и обработка selected_group."""
        cleaned_data = super().clean()

        # Обрабатываем selected_group, если он есть в данных
        if self.data and self.data.get('selected_group'):
            selected_group_id = self.data.get('selected_group')
            if selected_group_id and selected_group_id != '':
                user = self.request.user if self.request else None
                try:
                    group = PasswordGroup.objects.get(id=selected_group_id, owner=user)
                    cleaned_data['group'] = group
                except PasswordGroup.DoesNotExist:
                    pass

        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        """
        Переопределяет сохранение для двойного шифрования и создания истории.
        """
        instance = super().save(commit=False)

        # Получаем пользователя
        user = None
        if hasattr(self, 'request') and self.request:
            user = self.request.user
        elif hasattr(self, 'user'):
            user = self.user

        if not user:
            raise ValidationError(_("Пользователь не определен."))

        # Устанавливаем владельца
        instance.owner = user

        # Обрабатываем selected_group
        if self.cleaned_data.get('selected_group'):
            selected_group_id = self.cleaned_data.get('selected_group')
            if selected_group_id and selected_group_id != '':
                try:
                    group = PasswordGroup.objects.get(id=selected_group_id, owner=user)
                    instance.group = group
                except PasswordGroup.DoesNotExist:
                    pass

        raw_password = self.cleaned_data['raw_password']
        is_update = instance.pk is not None

        old_record = None
        if is_update:
            old_record = EncryptedPassword.objects.select_for_update().get(pk=instance.pk)

        # Получаем ключевую фразу (приоритет: форма > сессия)
        passphrase = self.cleaned_data.get('passphrase')

        # Если всё ещё нет фразы, проверяем, можем ли мы использовать сохраненную
        if not passphrase:
            use_saved = self.cleaned_data.get('use_saved_passphrase', False)
            has_saved_passphrase = hasattr(user, 'encryption_key_hash') and user.encryption_key_hash

            if use_saved and has_saved_passphrase:
                # У пользователя есть сохраненная фраза, но мы не можем её получить
                # (хранится только хеш). Требуем ввод.
                raise ValidationError({
                    'passphrase': _(
                        'Пожалуйста, введите ключевую фразу для шифрования. Она не сохранена в открытом виде.')
                })
            else:
                raise ValidationError({
                    'passphrase': _('Ключевая фраза обязательна для шифрования пароля.')
                })

        # Проверяем фразу (если ещё не проверяли)
        if not PasswordService.verify_passphrase(user, passphrase):
            raise ValidationError({
                'passphrase': _('Неверная ключевая фраза.')
            })

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

    def __init__(self, *args, **kwargs):
        super(UserKeySetupForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class PasswordGroupForm(forms.ModelForm):
    """
    Форма для создания и редактирования групп паролей.
    """

    class Meta:
        model = PasswordGroup
        fields = ['name', 'parent_group']
        labels = {
            'name': _('Название группы'),
            'parent_group': _('Родительская группа'),
        }
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Введите название группы'),
            }),
            'parent_group': forms.Select(attrs={
                'class': 'form-select',
            }),
        }
        help_texts = {
            'name': _('Уникальное название для вашей группы паролей.'),
            'parent_group': _('Выберите родительскую группу для создания иерархии.'),
        }

    def __init__(self, *args, **kwargs):
        """
        Ограничиваем выбор родительских групп только группами текущего пользователя
        и исключаем текущую группу (при редактировании) для предотвращения циклических ссылок.
        """
        user = kwargs.pop('user', None)
        instance = kwargs.get('instance', None)

        super().__init__(*args, **kwargs)

        if user:
            # Фильтруем группы только текущего пользователя
            queryset = PasswordGroup.objects.filter(owner=user)

            # При редактировании исключаем текущую группу и её потомков
            if instance and instance.pk:
                # Используем исправленный метод
                descendant_ids = instance.get_descendants_ids()
                excluded_ids = descendant_ids + [instance.pk]
                queryset = queryset.exclude(id__in=excluded_ids)

            self.fields['parent_group'].queryset = queryset

        # Добавляем пустой вариант для родительской группы
        self.fields['parent_group'].empty_label = _('— Без родительской группы —')
        self.fields['parent_group'].required = False

        for field in self.fields:
            make_custom_field(self.fields[field])

    def clean_parent_group(self):
        """Дополнительная проверка на уровне формы для предотвращения циклических ссылок."""
        parent_group = self.cleaned_data.get('parent_group')
        instance = getattr(self, 'instance', None)

        if instance and instance.pk and parent_group:
            # Проверяем, не пытается ли пользователь сделать группу родителем самой себя
            if parent_group.pk == instance.pk:
                raise forms.ValidationError(_("Группа не может быть родителем самой себя."))

            # Проверяем, не создает ли это циклическую зависимость
            descendant_ids = parent_group.get_descendants_ids()
            if instance.pk in descendant_ids:
                raise forms.ValidationError(_("Эта операция создала бы циклическую зависимость."))

        return parent_group

    def clean_name(self):
        """Проверка уникальности имени в рамках одного владельца и родительской группы."""
        name = self.cleaned_data.get('name')
        parent_group = self.cleaned_data.get('parent_group')
        instance = getattr(self, 'instance', None)
        user = getattr(self, 'user', None)

        if user and name:
            # Проверяем уникальность имени среди групп того же владельца и родителя
            queryset = PasswordGroup.objects.filter(
                owner=user,
                name=name,
                parent_group=parent_group
            )

            if instance and instance.pk:
                queryset = queryset.exclude(pk=instance.pk)

            if queryset.exists():
                raise forms.ValidationError(
                    _("Группа с таким именем уже существует в этой категории.")
                )

        return name
