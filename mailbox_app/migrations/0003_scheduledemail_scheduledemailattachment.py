# Generated for mailbox_app on 2026-09-02

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("mailbox_app", "0002_mailcontact"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScheduledEmail",
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
                    "to_recipients",
                    models.TextField(
                        help_text="Email адреса через запятую",
                        verbose_name="Получатели (Кому)",
                    ),
                ),
                (
                    "cc_recipients",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Email адреса через запятую",
                        verbose_name="Копия (Cc)",
                    ),
                ),
                (
                    "bcc_recipients",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Email адреса через запятую",
                        verbose_name="Скрытая копия (Bcc)",
                    ),
                ),
                (
                    "subject",
                    models.CharField(
                        blank=True,
                        default="(Без темы)",
                        max_length=500,
                        verbose_name="Тема",
                    ),
                ),
                (
                    "body_html",
                    models.TextField(
                        blank=True,
                        default="",
                        verbose_name="Текст сообщения (HTML)",
                    ),
                ),
                (
                    "body_text",
                    models.TextField(
                        blank=True,
                        default="",
                        verbose_name="Текст сообщения (Plain Text)",
                    ),
                ),
                (
                    "scheduled_at",
                    models.DateTimeField(
                        db_index=True,
                        verbose_name="Запланировано на",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "В очереди"),
                            ("processing", "Отправляется"),
                            ("sent", "Отправлено"),
                            ("failed", "Ошибка отправки"),
                            ("cancelled", "Отменено"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                        verbose_name="Статус",
                    ),
                ),
                (
                    "attempts_count",
                    models.IntegerField(
                        default=0,
                        verbose_name="Попыток отправки",
                    ),
                ),
                (
                    "max_attempts",
                    models.IntegerField(
                        default=3,
                        verbose_name="Максимум попыток",
                    ),
                ),
                (
                    "last_error",
                    models.TextField(
                        blank=True,
                        default="",
                        verbose_name="Текст последней ошибки",
                    ),
                ),
                (
                    "sent_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="Отправлено в",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Создано",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        verbose_name="Обновлено",
                    ),
                ),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scheduled_emails",
                        to="mailbox_app.mailaccount",
                        verbose_name="Почтовый ящик",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scheduled_emails",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Автор",
                    ),
                ),
            ],
            options={
                "verbose_name": "Запланированное письмо",
                "verbose_name_plural": "Запланированные письма",
                "ordering": ["scheduled_at"],
            },
        ),
        migrations.CreateModel(
            name="ScheduledEmailAttachment",
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
                    "file",
                    models.FileField(
                        upload_to="mailbox/scheduled_attachments/%Y/%m/",
                        verbose_name="Файл вложения",
                    ),
                ),
                (
                    "filename",
                    models.CharField(
                        max_length=255,
                        verbose_name="Имя файла",
                    ),
                ),
                (
                    "content_type",
                    models.CharField(
                        default="application/octet-stream",
                        max_length=128,
                        verbose_name="MIME-тип",
                    ),
                ),
                (
                    "file_size",
                    models.IntegerField(
                        default=0,
                        verbose_name="Размер (байт)",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Создано",
                    ),
                ),
                (
                    "scheduled_email",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="mailbox_app.scheduledemail",
                        verbose_name="Запланированное письмо",
                    ),
                ),
            ],
            options={
                "verbose_name": "Вложение запланированного письма",
                "verbose_name_plural": "Вложения запланированных писем",
                "ordering": ["created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="scheduledemail",
            index=models.Index(
                fields=["status", "scheduled_at"],
                name="sched_mail_status_time_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="scheduledemail",
            index=models.Index(
                fields=["user", "status"],
                name="sched_mail_user_status_idx",
            ),
        ),
    ]
