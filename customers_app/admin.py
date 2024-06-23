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
    VacationSchedule, CounteragentDocuments,
)


class CustomUserAdmin(UserAdmin):
    """
    Расширяем модель UserAdmin
    fieldsets: исходный набор полей формы
    *UserAdmin.fieldsets: добавляем расширенный набор полей формы,
        тип: кортеж содержащий ('заголовок группы по вашему выбору', {словарь c новыми полями})
    """

    fieldsets = (
        *UserAdmin.fieldsets,
        (
            "Личные данные",
            {
                "fields": (
                    "surname",
                    "title",
                    "birthday",
                ),
            },
        ),
        (
            "Профиль",
            {
                "fields": (
                    "avatar",
                    "address",
                    "type_users",
                    "service_number",
                    "user_access",
                    "personal_phone",
                    "gender",
                    "user_work_profile",
                    "user_profile",
                    "ref_key",
                    "person_ref_key",
                    "passphrase",
                    "telegram_id",
                ),
            },
        ),
    )
    list_display = (
    "pk", "username", "last_login", "last_name", "first_name", "surname", "birthday", "email", "is_active")
    search_fields = ('pk', 'title', 'ref_key', 'person_ref_key')
    ordering = ('last_name', 'first_name')


admin.site.register(DataBaseUser, CustomUserAdmin)
admin.site.register(Posts)
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


@admin.register(Division)
class CounteragentAdmin(admin.ModelAdmin):
    list_display = ("pk", "code", "name", "active",)
    search_fields = ("name", "code",)
    ordering = ('code',)
