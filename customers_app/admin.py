from django.contrib import admin

# Register your models here.
from django.contrib.auth.admin import UserAdmin
from .models import DataBaseUser


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
                    'avatar', 'birthday', 'access_right', 'address', 'type_users', 'phone', 'corp_phone', 'works', 'gender',
                ),
            },
        ),
    )


admin.site.register(DataBaseUser, CustomUserAdmin)
