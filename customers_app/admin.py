from django.contrib import admin

# Register your models here.
from django.contrib.auth.admin import UserAdmin
from .models import DataBaseUser, AccessLevel, Job, Division, Counteragent, Posts, UserAccessMode


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
                    'surname', 'avatar', 'birthday', 'access_right', 'address', 'type_users', 'internal_phone',
                    'work_phone', 'access_level',
                    'personal_phone', 'gender', 'divisions', 'job',
                ),
            },
        ),
    )


admin.site.register(DataBaseUser, CustomUserAdmin)
admin.site.register(AccessLevel, )
admin.site.register(Posts)
admin.site.register(Job, )
admin.site.register(Division, )
admin.site.register(Counteragent)
admin.site.register(UserAccessMode)
