# Generated by Django 5.0.6 on 2024-12-24 17:21

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tasks_app", "0005_remove_task_due_date_alter_task_priority"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="shared_with",
            field=models.ManyToManyField(
                blank=True,
                related_name="shared_tasks",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Доступ для",
            ),
        ),
        migrations.AlterField(
            model_name="task",
            name="repeat",
            field=models.CharField(
                choices=[
                    ("daily", "Ежедневно"),
                    ("weekly", "Еженедельно"),
                    ("monthly", "Ежемесячно"),
                    ("yearly", "Ежегодно"),
                ],
                default="none",
                max_length=10,
                verbose_name="Повторяемость",
            ),
        ),
    ]
