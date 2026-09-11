# Generated manually for testing_app

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("testing_app", "0005_materialviewlog_last_device"),
    ]

    operations = [
        migrations.AddField(
            model_name="testing",
            name="event_start_datetime",
            field=models.DateTimeField(
                blank=True,
                help_text="С этого момента начинается теоретическая подготовка сотрудников, открывается доступ к лекциям и бланку",
                null=True,
                verbose_name="Дата и время начала мероприятия (обучение)",
            ),
        ),
        migrations.AddField(
            model_name="testing",
            name="required_lectures",
            field=models.ManyToManyField(
                blank=True,
                help_text="Список лекций, с которыми сотрудники должны ознакомиться перед тестированием",
                related_name="required_in_testings",
                to="testing_app.lecturematerial",
                verbose_name="Обязательные лекции",
            ),
        ),
        migrations.AddField(
            model_name="testing",
            name="required_video_lectures",
            field=models.ManyToManyField(
                blank=True,
                help_text="Видеоматериалы, рекомендованные или обязательные к просмотру",
                related_name="required_in_testings",
                to="testing_app.videolecture",
                verbose_name="Обязательные видеолекции (опционально)",
            ),
        ),
        migrations.AlterField(
            model_name="testing",
            name="start_datetime",
            field=models.DateTimeField(
                help_text="С этого момента открывается возможность запуска попыток сдачи теста",
                verbose_name="Дата и время начала тестирования",
            ),
        ),
    ]
