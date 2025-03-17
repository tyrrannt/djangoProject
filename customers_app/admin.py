from django.contrib import admin

# Register your models here.
from django.contrib.auth.admin import UserAdmin

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
    VacationSchedule, CounteragentDocuments, UserStats,
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
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'email', 'birthday'),
        }),
    )

    list_display = ("pk", "username", "last_login", "last_name", "first_name", "surname", "birthday", "email", "is_active")
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


@admin.register(Counteragent)
class CounteragentAdmin(admin.ModelAdmin):
    list_display = ("pk", "short_name", "inn", "kpp", "ogrn", "type_counteragent",)
    search_fields = ("short_name", "inn", "kpp", "ogrn")
    ordering = ('pk',)

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
