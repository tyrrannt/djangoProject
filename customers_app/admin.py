from django.contrib import admin, messages

# Register your models here.
from django.contrib.auth.admin import UserAdmin
from django.urls import reverse
from django.utils.html import format_html

from .models import (
    DataBaseUser,
    Job,
    Division,
    Counteragent,
    Posts,
    AccessLevel,
    DataBaseUserProfile,
    Citizenships,
    IdentityDocuments,
    DataBaseUserWorkProfile,
    HarmfulWorkingConditions,
    ViewDocumentsPhysical,
    HistoryChange,
    HappyBirthdayGreetings,
    Affiliation,
    VacationScheduleList,
    VacationSchedule,
    CounteragentDocuments,
    UserStats,
    Apartments,
)


class CustomUserAdmin(UserAdmin):
    """
    Расширяем модель UserAdmin
    fieldsets: исходный набор полей формы
    *UserAdmin.fieldsets: добавляем расширенный набор полей формы,
        тип: кортеж содержащий ('заголовок группы по вашему выбору', {словарь c новыми полями})
    """
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': (
            'title', 'first_name', 'last_name', 'surname', 'email', 'birthday')}),
        ('Profile info', {'fields': (
            'avatar', 'address', 'type_users', 'service_number', 'user_access', 'personal_phone', 'gender',
            'user_work_profile', 'user_profile', 'ref_key', 'person_ref_key', 'passphrase', 'telegram_id', 'is_ppa')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions', 'type_of_role')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'email', 'birthday'),
        }),
    )

    list_display = ("pk", "username", "last_login", "last_name", "first_name", "surname", "birthday", "email", "is_active", 'is_ppa')
    search_fields = ('pk', 'title', 'ref_key', 'person_ref_key')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups', 'is_ppa')
    list_editable = ('is_active', 'is_ppa')
    list_per_page = 50
    ordering = ('last_name', 'first_name')
    empty_value_display = '-empty-'
    actions = ['activate_users', 'deactivate_users']

    def activate_users(self, request, queryset):
        queryset.update(is_active=True)
    activate_users.short_description = "Активируйте выбранных пользователей"

    def deactivate_users(self, request, queryset):
        queryset.update(is_active=False)
    deactivate_users.short_description = "Деактивировать выбранных пользователей"


admin.site.register(DataBaseUser, CustomUserAdmin)
admin.site.register(Job)
admin.site.register(AccessLevel)
admin.site.register(DataBaseUserProfile)
admin.site.register(Citizenships)
admin.site.register(DataBaseUserWorkProfile)
admin.site.register(HarmfulWorkingConditions)
admin.site.register(ViewDocumentsPhysical)
admin.site.register(HistoryChange)
admin.site.register(HappyBirthdayGreetings)
admin.site.register(Affiliation)
admin.site.register(VacationScheduleList)
admin.site.register(VacationSchedule)


@admin.register(IdentityDocuments)
class IdentityDocumentsAdmin(admin.ModelAdmin):
    list_display = ("series", "number", "issued_by_whom", "date_of_issue",
                    "division_code",)  #


@admin.register(CounteragentDocuments)
class CounteragentDocumentsAdmin(admin.ModelAdmin):
    list_display = ("package", "date_of_creation", "description", "document",)  #


# @admin.register(Counteragent)
# class CounteragentAdmin(admin.ModelAdmin):
#     list_display = ("pk", "short_name", "inn", "kpp", "ogrn", "type_counteragent",)
#     search_fields = ("short_name", "inn", "kpp", "ogrn")
#     ordering = ('pk',)

@admin.register(Posts)
class PostsAdmin(admin.ModelAdmin):
    list_display = ("pk", "post_title", "creation_date", "allowed_placed", "email_send", "post_date_start", "post_date_end")
    search_fields = ("post_title", "creation_date")
    ordering = ('-pk',)
    list_filter = ("creation_date", "allowed_placed", "email_send",)

@admin.register(Division)
class CounteragentAdmin(admin.ModelAdmin):
    list_display = ("pk", "code", "name", "active",)
    search_fields = ("name", "code",)
    ordering = ('code',)

@admin.register(UserStats)
class UserStatsAdmin(admin.ModelAdmin):
    list_display = ("pk", "score", "level", "lines_cleared", "games_played")
    # search_fields = ("name", "code",)
    ordering = ('created_at',)

@admin.register(Apartments)
class ApartmentsAdmin(admin.ModelAdmin):
    list_display = ("pk", "title", "place", "beds_number",)
    search_fields = ("title",)
    ordering = ('pk',)


@admin.register(Counteragent)
class CounteragentAdmin(admin.ModelAdmin):
    list_display = ["pk", 'short_name', 'inn', 'kpp', 'type_counteragent', 'duplicates_info']
    list_filter = ['type_counteragent']
    search_fields = ['short_name', 'inn', 'kpp']
    actions = ['find_and_mark_duplicates', 'merge_duplicates']
    ordering = ('pk',)

    def duplicates_info(self, obj):
        """Отображает информацию о дубликатах в списке"""
        duplicates = obj.get_potential_duplicates(obj)
        if duplicates.exists():
            count = duplicates.count()
            url = reverse('admin:customers_app_counteragent_changelist')
            return format_html(
                '<span style="color: red;">⚠ Дубликатов: {}</span><br>'
                '<a href="{}?inn={}" target="_blank">Показать</a>',
                count, url, obj.inn
            )
        return "✓ Уникальный"

    duplicates_info.short_description = "Дубликаты"

    def find_and_mark_duplicates(self, request, queryset):
        """Находит и помечает дубликаты"""
        all_duplicates = Counteragent.find_duplicates_by_inn_kpp()

        if not all_duplicates:
            self.message_user(request, "Дубликатов не найдено", messages.INFO)
            return

        message_parts = ["Найдены дубликаты:"]
        for (inn, kpp), objects in all_duplicates.items():
            ids = [str(obj.id) for obj in objects]
            message_parts.append(f"ИНН: {inn}, КПП: {kpp} - ID: {', '.join(ids)}")

        self.message_user(request, "\n".join(message_parts), messages.WARNING)

    find_and_mark_duplicates.short_description = "Найти дубликаты"

    def merge_duplicates(self, request, queryset):
        """
        Объединяет выбранные дубликаты
        ВАЖНО: Это упрощенный пример, расширьте логику под свои нужды
        """
        # Сначала группируем по ИНН
        grouped = {}
        for obj in queryset:
            key = (obj.inn, obj.kpp)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(obj)

        merged_count = 0
        for (inn, kpp), objects in grouped.items():
            if len(objects) > 1:
                # Выбираем "основной" объект (первый или самый старый)
                main_obj = objects[0]
                duplicates = objects[1:]

                # Здесь должна быть логика объединения:
                # 1. Перенос связанных записей на main_obj
                # 2. Удаление дубликатов
                # 3. Обновление полей при необходимости

                for dup in duplicates:
                    # TODO: Перенести все связанные объекты на main_obj
                    # dup.invoice_set.update(counteragent=main_obj)
                    # dup.contract_set.update(counteragent=main_obj)
                    # и т.д.

                    dup.delete()
                    merged_count += 1

        self.message_user(
            request,
            f"Объединено {merged_count} дубликатов",
            messages.SUCCESS
        )

    merge_duplicates.short_description = "Объединить выбранные дубликаты"