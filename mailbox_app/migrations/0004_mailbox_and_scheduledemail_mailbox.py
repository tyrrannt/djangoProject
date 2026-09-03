# Generated for mailbox_app on 2026-09-03

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("mailbox_app", "0003_scheduledemail_scheduledemailattachment"),
    ]

    operations = [
        migrations.CreateModel(
            name="Mailbox",
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
                        help_text="Например: 'Отдел кадров', 'Приёмная', 'Бухгалтерия'",
                        max_length=255,
                        verbose_name="Наименование ящика",
                    ),
                ),
                (
                    "email",
                    models.EmailField(
                        max_length=255,
                        unique=True,
                        verbose_name="Почтовый адрес (Email)",
                    ),
                ),
                (
                    "domain",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Определяется автоматически из адреса, например: barkol.ru",
                        max_length=100,
                        verbose_name="Домен",
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        default="",
                        verbose_name="Описание / Назначение",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        verbose_name="Активен",
                    ),
                ),
                (
                    "incoming_protocol",
                    models.CharField(
                        choices=[("imap", "IMAP"), ("pop3", "POP3")],
                        default="imap",
                        max_length=10,
                        verbose_name="Протокол входящей почты",
                    ),
                ),
                (
                    "imap_host",
                    models.CharField(
                        default="imap.barkol.ru",
                        max_length=255,
                        verbose_name="Сервер IMAP",
                    ),
                ),
                (
                    "imap_port",
                    models.IntegerField(
                        default=993,
                        verbose_name="Порт IMAP",
                    ),
                ),
                (
                    "imap_security",
                    models.CharField(
                        choices=[
                            ("ssl", "SSL/TLS"),
                            ("starttls", "STARTTLS"),
                            ("plain", "Без шифрования"),
                        ],
                        default="ssl",
                        max_length=10,
                        verbose_name="Шифрование IMAP",
                    ),
                ),
                (
                    "imap_username",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Если не указан, используется полный email",
                        max_length=255,
                        verbose_name="Логин IMAP",
                    ),
                ),
                (
                    "encrypted_imap_password",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=512,
                        verbose_name="Зашифрованный пароль IMAP",
                    ),
                ),
                (
                    "smtp_host",
                    models.CharField(
                        default="sm.barkol.ru",
                        max_length=255,
                        verbose_name="Сервер SMTP",
                    ),
                ),
                (
                    "smtp_port",
                    models.IntegerField(
                        default=465,
                        verbose_name="Порт SMTP",
                    ),
                ),
                (
                    "smtp_security",
                    models.CharField(
                        choices=[
                            ("ssl", "SSL/TLS"),
                            ("starttls", "STARTTLS"),
                            ("plain", "Без шифрования"),
                        ],
                        default="ssl",
                        max_length=10,
                        verbose_name="Шифрование SMTP",
                    ),
                ),
                (
                    "smtp_username",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Если не указан, используется логин IMAP или email",
                        max_length=255,
                        verbose_name="Логин SMTP",
                    ),
                ),
                (
                    "encrypted_smtp_password",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Если не указан, используется пароль входящей почты",
                        max_length=512,
                        verbose_name="Зашифрованный пароль SMTP",
                    ),
                ),
                (
                    "display_name",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Имя в поле 'От кого' (From). Если пусто, берется наименование ящика",
                        max_length=255,
                        verbose_name="Имя отправителя",
                    ),
                ),
                (
                    "signature_html",
                    models.TextField(
                        blank=True,
                        default="",
                        verbose_name="Подпись к письмам (HTML)",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Создан",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        verbose_name="Обновлен",
                    ),
                ),
                (
                    "users",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Сотрудники, которым разрешена работа с данным почтовым ящиком",
                        related_name="accessible_mailboxes",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Сотрудники с доступом",
                    ),
                ),
            ],
            options={
                "verbose_name": "Корпоративный почтовый ящик",
                "verbose_name_plural": "Корпоративные почтовые ящики",
                "ordering": ["name", "email"],
                "permissions": [
                    (
                        "manage_mailboxes",
                        "Может управлять общими и корпоративными почтовыми ящиками",
                    ),
                ],
            },
        ),
        migrations.AlterField(
            model_name="scheduledemail",
            name="account",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="scheduled_emails",
                to="mailbox_app.mailaccount",
                verbose_name="Почтовый ящик (персональный)",
            ),
        ),
        migrations.AddField(
            model_name="scheduledemail",
            name="mailbox",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="scheduled_emails",
                to="mailbox_app.mailbox",
                verbose_name="Корпоративный ящик",
            ),
        ),
    ]
