# Generated by Django 5.0.3 on 2024-04-27 09:31

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("logistics_app", "0013_package_executor"),
    ]

    operations = [
        migrations.AddField(
            model_name="package",
            name="type_of_dispatch",
            field=models.CharField(
                choices=[
                    ("0", "Логистическая компания"),
                    ("1", "Водитель"),
                    ("2", "Сотрудник"),
                ],
                default="0",
                max_length=100,
                verbose_name="Тип отправки",
            ),
        ),
    ]
