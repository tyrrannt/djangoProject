from django import forms
from django.contrib.admin import ModelAdmin
from django.db import models
from customers_app.models import DataBaseUser


class ActiveUserModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        if obj.is_active:
            return str(obj)
        return f"{obj} (неактивен)"


class ActiveUserModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        if obj.is_active:
            return str(obj)
        return f"{obj} (неактивен)"


class ActiveUsersFilterMixin:
    def get_user_foreignkey_fields(self):
        return [
            field.name for field in self.model._meta.get_fields()
            if (hasattr(field, 'related_model') and
                field.related_model == DataBaseUser and
                isinstance(field, models.ForeignKey))
        ]

    def get_user_manytomany_fields(self):
        return [
            field.name for field in self.model._meta.get_fields()
            if (hasattr(field, 'related_model') and
                field.related_model == DataBaseUser and
                isinstance(field, models.ManyToManyField))
        ]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        user_fields = self.get_user_foreignkey_fields()
        if db_field.name in user_fields:
            # Показываем всех пользователей, но с пометкой
            kwargs["queryset"] = DataBaseUser.objects.all().order_by('last_name')
            kwargs["form_class"] = ActiveUserModelChoiceField
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        user_fields = self.get_user_manytomany_fields()
        if db_field.name in user_fields:
            kwargs["queryset"] = DataBaseUser.objects.all()
            kwargs["form_class"] = ActiveUserModelMultipleChoiceField
        return super().formfield_for_manytomany(db_field, request, **kwargs)
