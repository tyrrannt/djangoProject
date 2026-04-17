# password_manager/admin.py
"""
Административная панель приложения password_manager.

Обеспечивает безопасный просмотр, фильтрацию и привилегированное 
дешифрование записей. Все критические поля защищены от ручного 
редактирования во избежание повреждения зашифрованных данных.

Архитектурные заметки (Stage 5)
Безопасность Admin Panel:
Все поля с хешами и ciphertext помечены readonly_fields. Это предотвращает случайную порчу данных при редактировании через админку.
Действие admin_decrypt_selected использует try/except и self.message_user, чтобы падение на одной записи не ломало весь batch-запрос.
PasswordHistoryAdmin полностью закрыт на изменение/удаление (has_add_permission = False и т.д.), так как это аудиторский лог.
Тестовая изоляция:
TestCase.setUpTestData используется для статических данных, ускоряя запуск.
@override_settings гарантирует, что тесты мастер-ключа не зависят от переменных окружения сервера.
RequestFactory + mock-объекты форм тестируют save() и валидацию без поднятия HTTP-сервера.
Как запустить:
# Проверка всех тестов приложения
python manage.py test password_manager

# Запуск конкретного класса тестов
python manage.py test password_manager.tests.CryptoEngineTests

# Генерация отчета покрытия (требует coverage)
coverage run manage.py test password_manager
coverage report


Замечание по DataBaseUser:
В тестах используется прямой импорт из customers_app. Если ваша модель использует кастомные поля (например, full_name вместо email), скорректируйте email="..." в setUp на реальные обязательные поля.

"""

from django.contrib import admin, messages
from django.db.models import Count
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.contrib.admin import display, action

from .models import (
    PasswordGroup, EncryptedPassword, PasswordHistory,
    SharedPassword, UserKeyHash
)
from .services import PasswordService


@admin.register(UserKeyHash)
class UserKeyHashAdmin(admin.ModelAdmin):
    """Управление хешами ключевых фраз пользователей."""
    list_display = ('user', 'key_hash_preview', 'created_display')
    search_fields = ('user__email', 'user__username')
    readonly_fields = ('key_hash',)
    list_per_page = 25

    @display(description='Хеш')
    def key_hash_preview(self, obj):
        """Показывает только первые 16 символов хеша для безопасности."""
        return f"{obj.key_hash[:16]}..." if obj.key_hash else '-'

    @display(description='Дата')
    def created_display(self, obj):
        return obj.user.date_joined if hasattr(obj.user, 'date_joined') else '-'


@admin.register(PasswordGroup)
class PasswordGroupAdmin(admin.ModelAdmin):
    """Управление иерархией групп паролей."""
    list_display = ('name', 'owner', 'parent_group_link', 'passwords_count')
    list_filter = ('owner', 'parent_group')
    search_fields = ('name', 'owner__email', 'owner__username')
    list_select_related = ('owner', 'parent_group')

    @display(description='Родительская группа')
    def parent_group_link(self, obj):
        return obj.parent_group.name if obj.parent_group else 'Корневая'

    @display(description='Записей', ordering='passwords__count')
    def passwords_count(self, obj):
        return obj.passwords.count()

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(passwords_count=Count('passwords'))


class SharedPasswordInline(admin.TabularInline):
    """Встроенная панель управления общим доступом внутри записи пароля."""
    model = SharedPassword
    fields = ('shared_with', 'permissions')
    extra = 1
    autocomplete_fields = ('shared_with',)
    # JSONField в Django 5.x автоматически рендерится с валидацией
    verbose_name_plural = "Совладельцы и права доступа"


@admin.register(EncryptedPassword)
class EncryptedPasswordAdmin(admin.ModelAdmin):
    """Основная панель управления учетными данными."""
    list_display = ('login', 'resource_type', 'owner', 'group', 'url_short', 'created_at', 'is_shared_badge')
    list_filter = ('resource_type', 'owner', 'group', 'created_at')
    search_fields = ('login', 'url', 'notes', 'owner__email')
    readonly_fields = ('encrypted_password', 'admin_encrypted_copy', 'created_at')
    inlines = [SharedPasswordInline]
    actions = ['admin_decrypt_selected']
    list_select_related = ('owner', 'group')

    @display(description='URL')
    def url_short(self, obj):
        return format_html('<a href="{}" target="_blank">{}</a>', obj.url,
                           obj.url[:40] + '...' if len(obj.url) > 40 else obj.url)

    @display(description='Общий', boolean=True)
    def is_shared_badge(self, obj):
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
                # Приоритет: админская копия, fallback: пользовательская
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
class PasswordHistoryAdmin(admin.ModelAdmin):
    """Аудит изменений паролей. Только чтение."""
    list_display = ('original_record', 'owner', 'login', 'url', 'changed_at')
    list_filter = ('owner', 'changed_at', 'original_record__resource_type')
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

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
