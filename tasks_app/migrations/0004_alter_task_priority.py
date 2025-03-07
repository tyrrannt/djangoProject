# Generated by Django 5.0.6 on 2024-12-22 10:46

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tasks_app", "0003_task_end_date_task_start_date_alter_task_repeat"),
    ]

    operations = [
        migrations.AlterField(
            model_name="task",
            name="priority",
            field=models.CharField(
                choices=[
                    ("primary", "Основной"),
                    ("warning", "Предупреждающий"),
                    ("info", "Информационный"),
                    ("danger", "Опасный"),
                    ("dark", "Темный"),
                ],
                default="medium",
                max_length=10,
                verbose_name="Важность",
            ),
        ),
    ]
