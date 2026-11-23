# -*- coding: utf-8 -*-
"""Сериализаторы DRF для приложения customers_app."""

from rest_framework import serializers
from .models import DataBaseUser


class DataBaseUserSerializer(serializers.ModelSerializer):
    """Безопасный read-only сериализатор основных нечувствительных полей сотрудника.

    Исключает конфиденциальные и привилегированные поля (``password``, ``passphrase``,
    ``is_superuser``, ``is_staff``, ``groups``, ``user_permissions``, ``personal_groups``),
    предотвращая утечку хэшей и атаки Mass Assignment.
    """

    class Meta:
        model = DataBaseUser
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "surname",
            "title",
            "email",
            "avatar",
            "is_active",
        )
        read_only_fields = fields
