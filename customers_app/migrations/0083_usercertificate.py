# Generated for Digital Signature / CryptoPro / GOST X.509 Certificate Authentication

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("customers_app", "0082_userpasskey"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserCertificate",
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
                        default="Сертификат ЭЦП",
                        help_text="Например: Рутокен ЭЦП 3.0 (Иванов И.И.), КЭП ФНС",
                        max_length=200,
                        verbose_name="Название сертификата",
                    ),
                ),
                (
                    "thumbprint",
                    models.CharField(
                        db_index=True,
                        max_length=64,
                        unique=True,
                        verbose_name="Отпечаток SHA-1 (Thumbprint)",
                    ),
                ),
                (
                    "serial_number",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=128,
                        verbose_name="Серийный номер",
                    ),
                ),
                (
                    "subject_name",
                    models.TextField(
                        help_text="Полная строка DN субъекта сертификата",
                        verbose_name="Субъект (Владелец)",
                    ),
                ),
                (
                    "issuer_name",
                    models.TextField(
                        help_text="Полная строка DN издателя сертификата",
                        verbose_name="Издатель (Удостоверяющий центр)",
                    ),
                ),
                (
                    "snils",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        max_length=20,
                        verbose_name="СНИЛС владельца",
                    ),
                ),
                (
                    "inn",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        max_length=20,
                        verbose_name="ИНН владельца",
                    ),
                ),
                (
                    "cn",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=255,
                        verbose_name="ФИО владельца (Common Name)",
                    ),
                ),
                (
                    "valid_from",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Действителен с"
                    ),
                ),
                (
                    "valid_to",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Действителен по"
                    ),
                ),
                (
                    "certificate_data",
                    models.TextField(
                        blank=True,
                        default="",
                        verbose_name="Данные сертификата (Base64)",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True, verbose_name="Активен для входа"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Дата привязки"
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
                        related_name="certificates",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Пользователь",
                    ),
                ),
            ],
            options={
                "verbose_name": "Сертификат ЭЦП (КЭП / ГОСТ)",
                "verbose_name_plural": "Сертификаты ЭЦП (КЭП / ГОСТ)",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["thumbprint"],
                        name="customers_a_thumbpr_6f8092_idx",
                    ),
                    models.Index(
                        fields=["snils"],
                        name="customers_a_snils_47e928_idx",
                    ),
                    models.Index(
                        fields=["inn"],
                        name="customers_a_inn_0a174c_idx",
                    ),
                    models.Index(
                        fields=["user", "-last_used_at"],
                        name="customers_a_user_id_0f8ce9_idx",
                    ),
                ],
            },
        ),
    ]
