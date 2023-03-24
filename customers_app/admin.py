from django.contrib import admin
# Register your models here.
from django.contrib.auth.admin import UserAdmin

from .models import DataBaseUser, Job, Division, Counteragent, Posts, AccessLevel, DataBaseUserProfile, \
    Citizenships, IdentityDocuments, DataBaseUserWorkProfile, HarmfulWorkingConditions, ViewDocumentsPhysical


class CustomUserAdmin(UserAdmin):
    """
    Расширяем модель UserAdmin
    fieldsets: исходный набор полей формы
    *UserAdmin.fieldsets: добавляем расширенный набор полей формы,
        тип: кортеж содержащий ('заголовок группы по вашему выбору', {словарь c новыми полями})
    """
    fieldsets = (
        *UserAdmin.fieldsets,
        # (
        #     'Данные для активации',
        #     {
        #         'fields': (
        #             'activate_key', 'activate_key_expires',
        #         ),
        #     },
        # ),
        (
            'Профиль',
            {
                'fields': (
                    'surname', 'avatar', 'birthday', 'address', 'type_users', 'service_number', 'user_access',
                    'personal_phone', 'gender', 'user_work_profile', 'user_profile', 'ref_key', 'person_ref_key',
                ),
            },
        ),
    )


admin.site.register(DataBaseUser, CustomUserAdmin)
admin.site.register(Posts)
admin.site.register(Job, )
admin.site.register(Division, )
admin.site.register(Counteragent)
admin.site.register(AccessLevel)
admin.site.register(DataBaseUserProfile)
admin.site.register(Citizenships)
admin.site.register(IdentityDocuments)
admin.site.register(DataBaseUserWorkProfile)
admin.site.register(HarmfulWorkingConditions)
admin.site.register(ViewDocumentsPhysical)
