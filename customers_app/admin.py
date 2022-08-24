from django.contrib import admin
# Register your models here.
from django.contrib.auth.admin import UserAdmin

from .models import DataBaseUser, Job, Division, Counteragent, Posts, UserAccessMode, AccessLevel, DataBaseUserProfile, Citizenships, IdentityDocuments


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
                    'surname', 'avatar', 'birthday', 'access_level', 'address', 'type_users', 'internal_phone',
                    'work_phone', 'personal_phone', 'gender', 'divisions', 'job', 'user_profile',
                ),
            },
        ),
    )


admin.site.register(DataBaseUser, CustomUserAdmin)
admin.site.register(Posts)
admin.site.register(Job, )
admin.site.register(Division, )
admin.site.register(Counteragent)
admin.site.register(UserAccessMode)
admin.site.register(AccessLevel)
admin.site.register(DataBaseUserProfile)
admin.site.register(Citizenships)
admin.site.register(IdentityDocuments)
