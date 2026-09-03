# Generated migration for MailTemplate and MailPrintSettings

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_initial_templates_and_settings(apps, schema_editor):
    """Создает базовые корпоративные шаблоны и начальные настройки бланка печати."""
    MailPrintSettings = apps.get_model("mailbox_app", "MailPrintSettings")
    MailTemplate = apps.get_model("mailbox_app", "MailTemplate")

    # Создаем дефолтные настройки бланка печати
    if not MailPrintSettings.objects.exists():
        MailPrintSettings.objects.create(
            organization_name="ООО «Авиакомпания «Баркол»",
            header_title="СЛУЖЕБНАЯ КОРПОРАТИВНАЯ ПЕРЕПИСКА",
            sub_header="Официальная распечатка электронного сообщения",
            footer_note="Электронный документ сформирован в корпоративном портале. Подлинность подтверждена сервером почты.",
            show_logo=True,
        )

    # Создаем популярные типовые корпоративные шаблоны ответов
    initial_templates = [
        {
            "name": "Согласование документов",
            "subject": "Согласовано",
            "body_html": "<p>Добрый день!</p><p>Документы проверены и согласованы без замечаний.</p><p>С уважением,</p>",
            "is_global": True,
        },
        {
            "name": "Документы во вложении",
            "subject": "Документы во вложении",
            "body_html": "<p>Добрый день!</p><p>Направляю запрашиваемые документы во вложении к данному письму. Прошу подтвердить получение.</p><p>С уважением,</p>",
            "is_global": True,
        },
        {
            "name": "Запрос информации / документов",
            "subject": "Запрос документов и информации",
            "body_html": "<p>Добрый день!</p><p>Прошу предоставить актуальную информацию и сканы подтверждающих документов по объекту / договору.</p><p>С уважением,</p>",
            "is_global": True,
        },
        {
            "name": "Входящее принято в работу",
            "subject": "Принято в работу",
            "body_html": "<p>Добрый день!</p><p>Ваше обращение получено и принято в работу профильным отделом. О готовности сообщим дополнительно.</p><p>С уважением,</p>",
            "is_global": True,
        },
    ]

    for tmpl in initial_templates:
        if not MailTemplate.objects.filter(name=tmpl["name"], is_global=True).exists():
            MailTemplate.objects.create(**tmpl)


def remove_initial_templates_and_settings(apps, schema_editor):
    """Безопасный откат."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("mailbox_app", "0005_create_mail_administrators_group"),
    ]

    operations = [
        migrations.CreateModel(
            name="MailPrintSettings",
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
                    "organization_name",
                    models.CharField(
                        default="ООО «Авиакомпания «Баркол»",
                        max_length=255,
                        verbose_name="Наименование организации",
                    ),
                ),
                (
                    "header_title",
                    models.CharField(
                        default="СЛУЖЕБНАЯ КОРПОРАТИВНАЯ ПЕРЕПИСКА",
                        max_length=255,
                        verbose_name="Заголовок бланка",
                    ),
                ),
                (
                    "sub_header",
                    models.CharField(
                        default="Официальная распечатка электронного сообщения",
                        max_length=255,
                        verbose_name="Подзаголовок",
                    ),
                ),
                (
                    "footer_note",
                    models.TextField(
                        default="Электронный документ сформирован в корпоративном портале. Подлинность подтверждена сервером почты.",
                        verbose_name="Примечание в подвале",
                    ),
                ),
                (
                    "show_logo",
                    models.BooleanField(
                        default=True, verbose_name="Отображать логотип"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Обновлено"),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Кто обновил",
                    ),
                ),
            ],
            options={
                "verbose_name": "Настройки бланка печати почты",
                "verbose_name_plural": "Настройки бланка печати почты",
            },
        ),
        migrations.CreateModel(
            name="MailTemplate",
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
                        max_length=255, verbose_name="Название шаблона"
                    ),
                ),
                (
                    "subject",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=255,
                        verbose_name="Тема по умолчанию",
                    ),
                ),
                ("body_html", models.TextField(verbose_name="Текст шаблона")),
                (
                    "is_global",
                    models.BooleanField(
                        default=False,
                        help_text="Если включено, шаблон доступен всем сотрудникам компании",
                        verbose_name="Общекорпоративный шаблон",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Создан"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Обновлен"),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mail_templates",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Автор",
                    ),
                ),
            ],
            options={
                "verbose_name": "Шаблон письма",
                "verbose_name_plural": "Шаблоны писем",
                "ordering": ["-is_global", "name"],
            },
        ),
        migrations.RunPython(
            create_initial_templates_and_settings,
            remove_initial_templates_and_settings,
        ),
    ]
