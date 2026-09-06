# Generated manually for Passkeys / WebAuthn support

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("customers_app", "0081_sync_auth_groups_to_customers_groups"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserPasskey",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        default="Мобильное устройство",
                        help_text="Например: iPhone (Safari), Samsung (Chrome)",
                        max_length=100,
                        verbose_name="Название устройства",
                    ),
                ),
                (
                    "credential_id",
                    models.CharField(
                        db_index=True,
                        max_length=512,
                        unique=True,
                        verbose_name="Идентификатор учетных данных (Credential ID)",
                    ),
                ),
                (
                    "public_key",
                    models.TextField(
                        help_text="Экспортированный публичный ключ в формате SubjectPublicKeyInfo PEM",
                        verbose_name="Публичный ключ (PEM)",
                    ),
                ),
                (
                    "sign_count",
                    models.BigIntegerField(
                        default=0, verbose_name="Счетчик подписей"
                    ),
                ),
                (
                    "aaguid",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=64,
                        verbose_name="AAGUID аутентификатора",
                    ),
                ),
                (
                    "device_type",
                    models.CharField(
                        blank=True,
                        default="platform",
                        max_length=64,
                        verbose_name="Тип устройства",
                    ),
                ),
                (
                    "transports",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=255,
                        verbose_name="Транспорты",
                    ),
                ),
                (
                    "user_agent",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=512,
                        verbose_name="User-Agent браузера",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Дата регистрации"
                    ),
                ),
                (
                    "last_used_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="Последнее использование",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="passkeys",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Пользователь",
                    ),
                ),
            ],
            options={
                "verbose_name": "Ключ доступа (Passkey / Биометрия)",
                "verbose_name_plural": "Ключи доступа (Passkeys / Биометрия)",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["credential_id"],
                        name="customers_a_credent_495bd5_idx",
                    ),
                    models.Index(
                        fields=["user", "-last_used_at"],
                        name="customers_a_user_id_0fca81_idx",
                    ),
                ],
            },
        ),
    ]
