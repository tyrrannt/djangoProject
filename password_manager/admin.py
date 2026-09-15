# password_manager/admin.py
"""
Административная панель приложения password_manager.

Обеспечивает безопасный просмотр, фильтрацию и привилегированное 
дешифрование записей. Все критические поля защищены от ручного 
редактирования во избежание повреждения зашифрованных данных.
"""

from typing import Optional, Tuple
from django.contrib import admin, messages
from django.db.models import Count
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display, action
from unfold.contrib.filters.admin import RangeDateFilter

from .models import (
    PasswordGroup,
    EncryptedPassword,
    PasswordHistory,
    SharedPassword,
    UserKeyHash,
)
from .services import PasswordService


@admin.register(UserKeyHash)
class UserKeyHashAdmin(ModelAdmin):
    """Управление хешами ключевых фраз пользователей."""
    list_display = ('user', 'key_hash_preview', 'created_display')
    search_fields = ('user__email', 'user__username')
    readonly_fields = ('key_hash',)
    list_per_page = 25
    compressed_fields = True
    warn_unsaved_form = True

    @display(description='Хеш')
    def key_hash_preview(self, obj: UserKeyHash) -> str:
        """Показывает только первые 16 символов хеша для безопасности."""
        return f"{obj.key_hash[:16]}..." if obj.key_hash else '-'

    @display(description='Дата')
    def created_display(self, obj: UserKeyHash) -> str:
        return str(obj.user.date_joined) if hasattr(obj.user, 'date_joined') else '-'


@admin.register(PasswordGroup)
class PasswordGroupAdmin(ModelAdmin):
    """Управление иерархией групп паролей."""
    list_display = ('display_group_header', 'owner', 'parent_group_link', 'passwords_count')
    list_filter = ('owner', 'parent_group')
    search_fields = ('name', 'owner__email', 'owner__username')
    autocomplete_fields = ['owner', 'parent_group']
    list_select_related = ('owner', 'parent_group')
    compressed_fields = True
    warn_unsaved_form = True

    @display(description='Группа', header=True)
    def display_group_header(self, obj: PasswordGroup) -> Tuple[str, str]:
        owner_name = obj.owner.username if obj.owner else "Общая"
        return obj.name, f"Владелец: {owner_name}"

    @display(description='Родительская группа')
    def parent_group_link(self, obj: PasswordGroup) -> str:
        return obj.parent_group.name if obj.parent_group else 'Корневая'

    @display(description='Записей', ordering='passwords__count')
    def passwords_count(self, obj: PasswordGroup) -> int:
        return obj.passwords.count()

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(passwords_count=Count('passwords'))


class SharedPasswordInline(TabularInline):
    """Встроенная панель управления общим доступом внутри записи пароля."""
    model = SharedPassword
    fields = ('shared_with', 'permissions')
    extra = 1
    autocomplete_fields = ('shared_with',)
    verbose_name_plural = "Совладельцы и права доступа"


@admin.register(EncryptedPassword)
class EncryptedPasswordAdmin(ModelAdmin):
    """Основная панель управления учетными данными."""
    list_display = (
        'display_password_header',
        'resource_type',
        'owner',
        'group',
        'url_short',
        'created_at',
        'display_shared',
    )
    list_filter = (
        'resource_type',
        'owner',
        'group',
        ('created_at', RangeDateFilter),
    )
    search_fields = ('login', 'url', 'notes', 'owner__email', 'owner__username')
    readonly_fields = ('encrypted_password', 'admin_encrypted_copy', 'created_at')
    autocomplete_fields = ['owner', 'group']
    inlines = [SharedPasswordInline]
    actions = ['admin_decrypt_selected']
    list_select_related = ('owner', 'group')
    compressed_fields = True
    warn_unsaved_form = True

    @display(description='Учетная запись', header=True)
    def display_password_header(self, obj: EncryptedPassword) -> Tuple[str, str]:
        grp_name = obj.group.name if obj.group else "Без группы"
        return obj.login, f"Группа: {grp_name}"

    @display(description='URL')
    def url_short(self, obj: EncryptedPassword) -> str:
        if not obj.url:
            return "—"
        return format_html('<a href="{}" target="_blank">{}</a>', obj.url,
                           obj.url[:40] + '...' if len(obj.url) > 40 else obj.url)

    @display(description='Общий доступ', boolean=True)
    def display_shared(self, obj: EncryptedPassword) -> bool:
        return hasattr(obj, 'shared_access')

    @action(description='🔓 Расшифровать выбранные пароли (Master Key)')
    def admin_decrypt_selected(self, request, queryset):
        """
        Привилегированная операция дешифрования.
        Использует PASSWORD_MANAGER_MASTER_KEY из settings.py.
        """
        success_count = 0
        for obj in queryset:
            try:
                ciphertext = obj.admin_encrypted_copy or obj.encrypted_password
                decrypted = PasswordService.admin_decrypt(ciphertext)
                self.message_user(request, f'✅ {obj.login} ({obj.url}): {decrypted}', messages.SUCCESS)
                success_count += 1
            except Exception as e:
                self.message_user(request, f'❌ Ошибка для {obj.login}: {str(e)}', messages.ERROR)

        if not success_count:
            self.message_user(request, 'Не удалось расшифровать ни одну запись. Проверьте настройки MASTER_KEY.',
                              messages.WARNING)


@admin.register(PasswordHistory)
class PasswordHistoryAdmin(ModelAdmin):
    """Аудит изменений паролей. Только чтение."""
    list_display = ('original_record', 'owner', 'login', 'url', 'changed_at')
    list_filter = ('owner', ('changed_at', RangeDateFilter))
    search_fields = ('login', 'url', 'owner__email')
    readonly_fields = (
        'encrypted_password',
        'resource_type',
        'url',
        'login',
        'notes',
        'changed_at',
        'original_record',
        'owner',
        'admin_encrypted_copy'
    )
    date_hierarchy = 'changed_at'
    list_select_related = ('original_record', 'owner')
    compressed_fields = True

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
